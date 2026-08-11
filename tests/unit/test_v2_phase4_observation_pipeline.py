from __future__ import annotations

import sqlite3
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from spy_market_agent.market_data.errors import ChecksumMismatch, ManifestValidationFailure
from spy_market_agent.persistence.serialization import datetime_to_text
from spy_market_agent.shadow import (
    SHADOW_DB_SCHEMA_VERSION,
    SHADOW_OPERATION_CONFIGURATION_VERSION,
    SHADOW_OPERATION_FEATURE_SCHEMA,
    FreshnessStatus,
    ModelAdmissionStatus,
    ShadowHealthStatus,
    ShadowMode,
    ShadowModelMetadata,
    ShadowObservationResult,
    ShadowOperationalRunStatus,
    ShadowPersistenceError,
    ShadowRecoveryRequiredError,
    ShadowRunRecord,
    ShadowSchemaError,
    ShadowSQLiteRepository,
    build_operational_snapshot,
    evaluate_market_data_freshness,
    initialize_shadow_database,
    run_observation,
    shadow_run_identity,
)
from spy_market_agent.shadow.persistence import ShadowDuplicateRunError
from spy_market_agent.shadow.runner import ShadowOperationalError
from unit.phase4_shadow_helpers import SyntheticPhase1Dataset, write_synthetic_phase1_dataset

ROOT = Path(__file__).resolve().parents[2]
FIXED_CREATED = datetime(2025, 1, 3, 0, 1, tzinfo=UTC)
FIXED_COMPLETED = datetime(2025, 1, 3, 0, 2, tzinfo=UTC)


class FixedClock:
    def __init__(self) -> None:
        self._values = [FIXED_CREATED, FIXED_COMPLETED, FIXED_COMPLETED]

    def __call__(self) -> datetime:
        return self._values.pop(0)


def _approved_model_metadata() -> ShadowModelMetadata:
    return ShadowModelMetadata(
        model_id="synthetic-approved-shadow-model",
        experiment_id="synthetic-experiment",
        campaign_id="synthetic-campaign",
        model_artifact_checksum="a" * 64,
        feature_schema=SHADOW_OPERATION_FEATURE_SCHEMA,
        label_schema="synthetic-label-schema-v1",
        git_commit_sha="abcdef1234567890",
        source_lineage="synthetic-test-only",
        approval_status="approved",
        approved_for_shadow=True,
    )


def _run_healthy(tmp_path: Path) -> tuple[SyntheticPhase1Dataset, ShadowObservationResult]:
    dataset = write_synthetic_phase1_dataset(tmp_path)
    result = run_observation(
        manifest_path=dataset.manifest_path,
        data_root=dataset.data_root,
        shadow_db=tmp_path / "shadow.sqlite3",
        session=date(2025, 1, 2),
        as_of=datetime(2025, 1, 3, 0, 0, tzinfo=UTC),
        provider_finalized=True,
        provider_finalization_policy_id="synthetic-provider-finalized-v1",
        repository_root=tmp_path,
        clock=FixedClock(),
    )
    return dataset, result


def test_shadow_database_initializes_with_dedicated_schema(tmp_path: Path) -> None:
    repository = initialize_shadow_database(tmp_path / "shadow.sqlite3")
    repository.initialize()

    with sqlite3.connect(tmp_path / "shadow.sqlite3") as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
            if not str(row[0]).startswith("sqlite_")
        }
        version = connection.execute(
            "SELECT schema_version FROM shadow_schema_metadata WHERE singleton_id = 1"
        ).fetchone()[0]

    assert version == SHADOW_DB_SCHEMA_VERSION
    assert tables == {
        "shadow_schema_metadata",
        "shadow_runs",
        "shadow_input_snapshots",
        "shadow_health_events",
        "shadow_alerts",
    }


def test_shadow_database_rejects_incompatible_or_mixed_schema(tmp_path: Path) -> None:
    incompatible = tmp_path / "incompatible.sqlite3"
    with sqlite3.connect(incompatible) as connection:
        connection.execute(
            "CREATE TABLE shadow_schema_metadata "
            "(singleton_id INTEGER PRIMARY KEY, schema_version TEXT NOT NULL)"
        )
        connection.execute("INSERT INTO shadow_schema_metadata VALUES (1, 'future-shadow-schema')")
        connection.execute("CREATE TABLE shadow_runs (shadow_run_id TEXT PRIMARY KEY)")

    with pytest.raises(ShadowSchemaError, match="incomplete_shadow_schema"):
        ShadowSQLiteRepository(incompatible).initialize()

    mixed = tmp_path / "mixed.sqlite3"
    with sqlite3.connect(mixed) as connection:
        connection.execute("CREATE TABLE paper_execution_attempts (id TEXT)")

    with pytest.raises(ShadowSchemaError, match="mixed_shadow_database"):
        ShadowSQLiteRepository(mixed).initialize()


def test_deterministic_run_id_survives_persistence_reload(tmp_path: Path) -> None:
    dataset, result = _run_healthy(tmp_path)
    stored = ShadowSQLiteRepository(tmp_path / "shadow.sqlite3").get_run(result.shadow_run_id)
    snapshot = build_operational_snapshot(
        manifest=dataset.manifest,
        canonical_bars=dataset.canonical_bars,
        session=date(2025, 1, 2),
        as_of=datetime(2025, 1, 3, 0, 0, tzinfo=UTC),
        provider_finalized=True,
        provider_finalization_policy_id="synthetic-provider-finalized-v1",
    )

    assert result.shadow_run_id == shadow_run_identity(snapshot.request)
    assert stored.run.shadow_run_id == result.shadow_run_id
    assert stored.input_snapshot is not None
    assert stored.input_snapshot.parent_dataset_id == dataset.manifest.dataset_id
    assert stored.input_snapshot.canonical_dataset_checksum == (
        dataset.manifest.canonical_content_checksum
    )


def test_completed_and_blocked_runs_block_duplicate_retry(tmp_path: Path) -> None:
    dataset, result = _run_healthy(tmp_path)

    with pytest.raises(ShadowDuplicateRunError, match="duplicate_run"):
        run_observation(
            manifest_path=dataset.manifest_path,
            data_root=dataset.data_root,
            shadow_db=tmp_path / "shadow.sqlite3",
            session=date(2025, 1, 2),
            as_of=datetime(2025, 1, 3, 0, 0, tzinfo=UTC),
            provider_finalized=True,
            provider_finalization_policy_id="synthetic-provider-finalized-v1",
            repository_root=tmp_path,
            clock=FixedClock(),
        )
    assert result.run_status == ShadowOperationalRunStatus.COMPLETED

    blocked_dataset = write_synthetic_phase1_dataset(
        tmp_path / "blocked",
        start_session=date(2025, 1, 2),
        end_session=date(2025, 1, 2),
    )
    shadow_db = tmp_path / "blocked.sqlite3"
    blocked_result = run_observation(
        manifest_path=blocked_dataset.manifest_path,
        data_root=blocked_dataset.data_root,
        shadow_db=shadow_db,
        session=date(2025, 1, 2),
        as_of=datetime(2025, 1, 3, 0, 0, tzinfo=UTC),
        provider_finalized=False,
        provider_finalization_policy_id="synthetic-provider-finalized-v1",
        repository_root=tmp_path / "blocked",
        clock=FixedClock(),
    )
    with pytest.raises(ShadowDuplicateRunError, match="duplicate_run"):
        run_observation(
            manifest_path=blocked_dataset.manifest_path,
            data_root=blocked_dataset.data_root,
            shadow_db=shadow_db,
            session=date(2025, 1, 2),
            as_of=datetime(2025, 1, 3, 0, 0, tzinfo=UTC),
            provider_finalized=False,
            provider_finalization_policy_id="synthetic-provider-finalized-v1",
            repository_root=tmp_path / "blocked",
            clock=FixedClock(),
        )
    assert blocked_result.run_status == ShadowOperationalRunStatus.BLOCKED


def test_incomplete_reserved_run_requires_recovery_review(tmp_path: Path) -> None:
    dataset = write_synthetic_phase1_dataset(tmp_path)
    snapshot = build_operational_snapshot(
        manifest=dataset.manifest,
        canonical_bars=dataset.canonical_bars,
        session=date(2025, 1, 2),
        as_of=datetime(2025, 1, 3, 0, 0, tzinfo=UTC),
        provider_finalized=True,
        provider_finalization_policy_id="synthetic-provider-finalized-v1",
    )
    run_id = shadow_run_identity(snapshot.request)
    repository = initialize_shadow_database(tmp_path / "shadow.sqlite3")
    repository.reserve_run(
        ShadowRunRecord(
            shadow_run_id=run_id,
            configuration_version=SHADOW_OPERATION_CONFIGURATION_VERSION,
            mode=ShadowMode.OBSERVATION_ONLY_NO_MODEL,
            symbol="SPY",
            timeframe="1Day",
            signal_session="2025-01-02",
            as_of="2025-01-03T00:00:00Z",
            parent_dataset_id=dataset.manifest.dataset_id,
            canonical_dataset_checksum=dataset.manifest.canonical_content_checksum,
            provider_finalization_policy_id="synthetic-provider-finalized-v1",
            run_status=ShadowOperationalRunStatus.RESERVED,
            freshness_status=FreshnessStatus.BLOCKED,
            monitoring_status=ShadowHealthStatus.BLOCKED,
            model_gate_status=ModelAdmissionStatus.BLOCKED_NO_APPROVED_MODEL,
            created_at=datetime_to_text(FIXED_CREATED),
        )
    )

    with pytest.raises(ShadowRecoveryRequiredError, match="recovery_required"):
        run_observation(
            manifest_path=dataset.manifest_path,
            data_root=dataset.data_root,
            shadow_db=tmp_path / "shadow.sqlite3",
            session=date(2025, 1, 2),
            as_of=datetime(2025, 1, 3, 0, 0, tzinfo=UTC),
            provider_finalized=True,
            provider_finalization_policy_id="synthetic-provider-finalized-v1",
            repository_root=tmp_path,
            clock=FixedClock(),
        )


def test_target_contract_rejects_wrong_lineage_scope_and_sessions(tmp_path: Path) -> None:
    dataset = write_synthetic_phase1_dataset(
        tmp_path,
        start_session=date(2025, 1, 2),
        end_session=date(2025, 1, 3),
        retrieval_timestamp=datetime(2025, 1, 4, 0, 0, tzinfo=UTC),
    )

    with pytest.raises(ManifestValidationFailure, match="symbol"):
        build_operational_snapshot(
            manifest=dataset.manifest.model_copy(update={"symbol": "AAPL"}),
            canonical_bars=dataset.canonical_bars,
            session=date(2025, 1, 3),
            as_of=datetime(2025, 1, 4, 0, 0, tzinfo=UTC),
            provider_finalized=True,
            provider_finalization_policy_id="synthetic-provider-finalized-v1",
        )
    with pytest.raises(ManifestValidationFailure, match="timeframe"):
        build_operational_snapshot(
            manifest=dataset.manifest.model_copy(update={"timeframe": "1Min"}),
            canonical_bars=dataset.canonical_bars,
            session=date(2025, 1, 3),
            as_of=datetime(2025, 1, 4, 0, 0, tzinfo=UTC),
            provider_finalized=True,
            provider_finalization_policy_id="synthetic-provider-finalized-v1",
        )
    with pytest.raises(ManifestValidationFailure, match="calendar"):
        build_operational_snapshot(
            manifest=dataset.manifest.model_copy(
                update={"relevant_configuration": {"calendar": "XNAS"}}
            ),
            canonical_bars=dataset.canonical_bars,
            session=date(2025, 1, 3),
            as_of=datetime(2025, 1, 4, 0, 0, tzinfo=UTC),
            provider_finalized=True,
            provider_finalization_policy_id="synthetic-provider-finalized-v1",
        )
    with pytest.raises(ShadowOperationalError, match="not_xnys_session"):
        build_operational_snapshot(
            manifest=dataset.manifest,
            canonical_bars=dataset.canonical_bars,
            session=date(2025, 1, 4),
            as_of=datetime(2025, 1, 5, 0, 0, tzinfo=UTC),
            provider_finalized=True,
            provider_finalization_policy_id="synthetic-provider-finalized-v1",
        )
    with pytest.raises(ShadowOperationalError, match="target_session_not_latest"):
        build_operational_snapshot(
            manifest=dataset.manifest,
            canonical_bars=dataset.canonical_bars,
            session=date(2025, 1, 2),
            as_of=datetime(2025, 1, 4, 0, 0, tzinfo=UTC),
            provider_finalized=True,
            provider_finalization_policy_id="synthetic-provider-finalized-v1",
        )
    with pytest.raises(ShadowOperationalError, match="missing_session"):
        build_operational_snapshot(
            manifest=dataset.manifest,
            canonical_bars=dataset.canonical_bars[:1],
            session=date(2025, 1, 3),
            as_of=datetime(2025, 1, 4, 0, 0, tzinfo=UTC),
            provider_finalized=True,
            provider_finalization_policy_id="synthetic-provider-finalized-v1",
        )


def test_stale_incomplete_provider_unfinalized_and_invalid_ohlcv_block(tmp_path: Path) -> None:
    stale_dataset = write_synthetic_phase1_dataset(tmp_path / "stale")
    stale_result = run_observation(
        manifest_path=stale_dataset.manifest_path,
        data_root=stale_dataset.data_root,
        shadow_db=tmp_path / "stale.sqlite3",
        session=date(2025, 1, 2),
        as_of=datetime(2025, 1, 4, 0, 0, tzinfo=UTC),
        provider_finalized=True,
        provider_finalization_policy_id="synthetic-provider-finalized-v1",
        repository_root=tmp_path / "stale",
        clock=FixedClock(),
    )
    stale_stored = ShadowSQLiteRepository(tmp_path / "stale.sqlite3").get_run(
        stale_result.shadow_run_id
    )
    assert stale_result.run_status == ShadowOperationalRunStatus.BLOCKED
    assert "stale_data" in stale_result.alerts
    assert "stale_data" in {event.event_code for event in stale_stored.health_events}

    incomplete_dataset = write_synthetic_phase1_dataset(tmp_path / "incomplete")
    incomplete_result = run_observation(
        manifest_path=incomplete_dataset.manifest_path,
        data_root=incomplete_dataset.data_root,
        shadow_db=tmp_path / "incomplete.sqlite3",
        session=date(2025, 1, 2),
        as_of=datetime(2025, 1, 2, 12, 0, tzinfo=UTC),
        provider_finalized=True,
        provider_finalization_policy_id="synthetic-provider-finalized-v1",
        repository_root=tmp_path / "incomplete",
        clock=FixedClock(),
    )
    incomplete_events = (
        ShadowSQLiteRepository(tmp_path / "incomplete.sqlite3")
        .get_run(incomplete_result.shadow_run_id)
        .health_events
    )
    assert incomplete_result.run_status == ShadowOperationalRunStatus.BLOCKED
    assert "incomplete_session" in {event.event_code for event in incomplete_events}

    unfinalized_dataset = write_synthetic_phase1_dataset(tmp_path / "unfinalized")
    unfinalized_result = run_observation(
        manifest_path=unfinalized_dataset.manifest_path,
        data_root=unfinalized_dataset.data_root,
        shadow_db=tmp_path / "unfinalized.sqlite3",
        session=date(2025, 1, 2),
        as_of=datetime(2025, 1, 3, 0, 0, tzinfo=UTC),
        provider_finalized=False,
        provider_finalization_policy_id="synthetic-provider-finalized-v1",
        repository_root=tmp_path / "unfinalized",
        clock=FixedClock(),
    )
    assert unfinalized_result.run_status == ShadowOperationalRunStatus.BLOCKED
    assert "provider_not_finalized" in unfinalized_result.alerts

    invalid_bar = unfinalized_dataset.canonical_bars[-1].model_copy(update={"high": "1"})
    invalid_snapshot = build_operational_snapshot(
        manifest=unfinalized_dataset.manifest,
        canonical_bars=(invalid_bar,),
        session=date(2025, 1, 2),
        as_of=datetime(2025, 1, 3, 0, 0, tzinfo=UTC),
        provider_finalized=True,
        provider_finalization_policy_id="synthetic-provider-finalized-v1",
    )
    freshness = evaluate_market_data_freshness(invalid_snapshot.market_data_status)
    assert invalid_snapshot.market_data_status.ohlcv_valid is False
    assert "invalid_ohlcv" in freshness.reasons


def test_healthy_observation_only_run_persists_expected_state(tmp_path: Path) -> None:
    _, result = _run_healthy(tmp_path)
    stored = ShadowSQLiteRepository(tmp_path / "shadow.sqlite3").get_run(result.shadow_run_id)

    assert result.run_status == ShadowOperationalRunStatus.COMPLETED
    assert result.monitoring_status == ShadowHealthStatus.HEALTHY
    assert result.model_gate_status == ModelAdmissionStatus.BLOCKED_NO_APPROVED_MODEL
    assert result.proposal_generated is False
    assert stored.run.run_status == ShadowOperationalRunStatus.COMPLETED
    assert stored.run.model_gate_status == ModelAdmissionStatus.BLOCKED_NO_APPROVED_MODEL
    assert stored.input_snapshot is not None
    assert stored.input_snapshot.target_session == "2025-01-02"
    assert {event.event_code for event in stored.health_events} == {
        "fresh_data",
        "model_not_approved",
    }
    assert stored.alerts == ()


def test_show_run_cli_is_read_only_and_deterministic(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, result = _run_healthy(tmp_path)
    before = ShadowSQLiteRepository(tmp_path / "shadow.sqlite3").get_run(result.shadow_run_id)

    from spy_market_agent.shadow.cli import main

    exit_code = main(
        [
            "show-run",
            "--shadow-db",
            str(tmp_path / "shadow.sqlite3"),
            "--run-id",
            result.shadow_run_id,
        ]
    )
    captured = capsys.readouterr().out
    after = ShadowSQLiteRepository(tmp_path / "shadow.sqlite3").get_run(result.shadow_run_id)

    assert exit_code == 0
    assert f"shadow_run_id={result.shadow_run_id}" in captured
    assert "model_gate_status=blocked_no_approved_model" in captured
    assert before == after


def test_lineage_checksum_failure_blocks_before_healthy_state(tmp_path: Path) -> None:
    dataset = write_synthetic_phase1_dataset(tmp_path)
    canonical_path = tmp_path / dataset.manifest.generated_file_locations.canonical_path
    canonical_path.write_text(canonical_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ChecksumMismatch):
        run_observation(
            manifest_path=dataset.manifest_path,
            data_root=dataset.data_root,
            shadow_db=tmp_path / "shadow.sqlite3",
            session=date(2025, 1, 2),
            as_of=datetime(2025, 1, 3, 0, 0, tzinfo=UTC),
            provider_finalized=True,
            provider_finalization_policy_id="synthetic-provider-finalized-v1",
            repository_root=tmp_path,
            clock=FixedClock(),
        )
    assert not (tmp_path / "shadow.sqlite3").exists()


def test_observation_runner_rejects_model_connected_mode_and_self_declared_metadata(
    tmp_path: Path,
) -> None:
    with pytest.raises(ShadowOperationalError, match="observation_only_mode_required"):
        run_observation(
            manifest_path=tmp_path / "unused.manifest.json",
            data_root=Path("data"),
            shadow_db=tmp_path / "shadow.sqlite3",
            session=date(2025, 1, 2),
            as_of=datetime(2025, 1, 3, 0, 0, tzinfo=UTC),
            provider_finalized=True,
            provider_finalization_policy_id="synthetic-provider-finalized-v1",
            repository_root=tmp_path,
            mode=ShadowMode.MODEL_CONNECTED,
            model_metadata=_approved_model_metadata(),
        )
    with pytest.raises(ShadowOperationalError, match="model_metadata"):
        run_observation(
            manifest_path=tmp_path / "unused.manifest.json",
            data_root=Path("data"),
            shadow_db=tmp_path / "shadow.sqlite3",
            session=date(2025, 1, 2),
            as_of=datetime(2025, 1, 3, 0, 0, tzinfo=UTC),
            provider_finalized=True,
            provider_finalization_policy_id="synthetic-provider-finalized-v1",
            repository_root=tmp_path,
            model_metadata=_approved_model_metadata(),
        )


def test_shadow_cli_does_not_require_credential_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dataset = write_synthetic_phase1_dataset(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ALPACA_MARKET_DATA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_MARKET_DATA_SECRET_KEY", raising=False)
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)

    from spy_market_agent.shadow.cli import main

    exit_code = main(
        [
            "run-observation",
            "--manifest",
            str(dataset.manifest_path),
            "--data-root",
            str(dataset.data_root),
            "--shadow-db",
            str(tmp_path / "shadow.sqlite3"),
            "--session",
            "2025-01-02",
            "--as-of",
            "2025-01-03T00:00:00Z",
            "--provider-finalized",
            "--provider-finalization-policy-id",
            "synthetic-provider-finalized-v1",
        ]
    )
    captured = capsys.readouterr().out

    assert exit_code == 0
    assert "run_status=completed" in captured
    assert "model_gate_status=blocked_no_approved_model" in captured


def test_shadow_static_boundary_excludes_execution_network_and_credential_names() -> None:
    shadow_files = sorted((ROOT / "src/spy_market_agent/shadow").glob("*.py"))
    assert shadow_files
    forbidden_fragments = (
        "alpaca.trading",
        "TradingClient",
        "spy_market_agent.execution",
        "AlpacaPaperBroker",
        "submit_order",
        "submit_approved_order",
        "APCA_API_KEY_ID",
        "APCA_API_SECRET_KEY",
        "ALPACA_MARKET_DATA_API_KEY",
        "ALPACA_MARKET_DATA_SECRET_KEY",
        "APScheduler",
        "Celery",
        "cron",
    )

    for path in shadow_files:
        text = path.read_text(encoding="utf-8")
        for fragment in forbidden_fragments:
            assert fragment not in text, f"{path}: {fragment}"


def test_shadow_import_has_no_side_effects_or_forbidden_modules(tmp_path: Path) -> None:
    script = """
import sys
import spy_market_agent.shadow
import spy_market_agent.shadow.cli

for name in (
    "alpaca.trading",
    "spy_market_agent.execution",
    "spy_market_agent.execution.alpaca_paper",
    "spy_market_agent.execution.service",
):
    assert name not in sys.modules, name
print("clean")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "clean"


def test_shadow_sqlite_errors_remain_typed(tmp_path: Path) -> None:
    repository = initialize_shadow_database(tmp_path / "shadow.sqlite3")

    with pytest.raises(ShadowPersistenceError, match="list limit"):
        repository.list_runs(limit=0)


def test_manifest_adjustment_policy_must_be_all(tmp_path: Path) -> None:
    dataset = write_synthetic_phase1_dataset(
        tmp_path,
        adjustment_mode="raw",
    )

    with pytest.raises(ManifestValidationFailure, match="adjustment"):
        run_observation(
            manifest_path=dataset.manifest_path,
            data_root=dataset.data_root,
            shadow_db=tmp_path / "shadow.sqlite3",
            session=date(2025, 1, 2),
            as_of=datetime(2025, 1, 3, 0, 0, tzinfo=UTC),
            provider_finalized=True,
            provider_finalization_policy_id="synthetic-provider-finalized-v1",
            repository_root=tmp_path,
            clock=FixedClock(),
        )
