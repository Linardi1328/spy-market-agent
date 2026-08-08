from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from spy_market_agent.benchmark.artifacts import BenchmarkArtifactStore, canonical_json_bytes
from spy_market_agent.benchmark.baselines import classification_baseline_metrics
from spy_market_agent.benchmark.dataset import (
    feed_limitation_decision,
    load_verified_phase1_dataset,
    record_feed_availability,
)
from spy_market_agent.benchmark.errors import (
    BenchmarkArtifactError,
    BenchmarkEligibilityError,
    BenchmarkFinalTestAccessError,
    BenchmarkInputError,
)
from spy_market_agent.benchmark.locks import BenchmarkRole, exact_phase2_cost_scenarios
from spy_market_agent.benchmark.metrics import classification_metric_set
from spy_market_agent.benchmark.pipeline import _reconstruct, prepare_benchmark
from spy_market_agent.benchmark.regimes import regime_frame, training_volatility_threshold
from spy_market_agent.benchmark.splits import BOUNDARY_EXCLUSION_SESSIONS, stage_a_bundle
from spy_market_agent.market_data.calendar import XNYSCalendar
from unit.v2_phase2_helpers import SYNTHETIC_NOW, write_synthetic_phase1_dataset


def _feed_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, feed: str = "sip") -> Path:
    monkeypatch.chdir(tmp_path)
    record = record_feed_availability(
        provider="alpaca",
        requested_feed=feed,
        symbol="SPY",
        timeframe="1Day",
        adjustment_mode="all",
        requested_start=date(2016, 1, 4),
        requested_end=date(2025, 12, 31),
        probe_timestamp=SYNTHETIC_NOW,
        success=True,
        owner_acknowledgement=True,
        evidence_source_description="synthetic owner-provided offline probe record",
        output=Path("feed.json"),
    )
    assert record.contains_credentials is False
    return tmp_path / "feed.json"


def test_exact_phase2_cost_matrix_is_locked() -> None:
    costs = exact_phase2_cost_scenarios()

    observed_costs = [
        (item.name, item.commission_bps_per_side, item.slippage_bps_per_side) for item in costs
    ]
    assert observed_costs == [
        ("idealized", Decimal("0"), Decimal("0")),
        ("base", Decimal("0.125"), Decimal("0.25")),
        ("adverse", Decimal("1"), Decimal("2")),
        ("severe", Decimal("10"), Decimal("20")),
    ]
    assert costs[1].side_cost_bps == Decimal("0.375")
    assert costs[1].round_trip_cost_bps == Decimal("0.750")


def test_feed_records_are_non_sensitive_and_feed_policy_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _feed_record(tmp_path, monkeypatch, feed="iex")

    iex = feed_limitation_decision("iex")
    sip = feed_limitation_decision("sip")

    assert iex.primary_allowed is False
    assert iex.diagnostic_allowed is True
    assert sip.primary_allowed is True
    with pytest.raises(BenchmarkEligibilityError):
        feed_limitation_decision("other")


def test_feed_record_requires_owner_acknowledgement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(BenchmarkInputError):
        record_feed_availability(
            provider="alpaca",
            requested_feed="sip",
            symbol="SPY",
            timeframe="1Day",
            adjustment_mode="all",
            requested_start=date(2016, 1, 4),
            requested_end=date(2025, 12, 31),
            probe_timestamp=SYNTHETIC_NOW,
            success=True,
            owner_acknowledgement=False,
            evidence_source_description="synthetic",
            output=Path("feed.json"),
        )


def test_manifest_integration_loads_v1_market_data_after_deep_verification(tmp_path: Path) -> None:
    manifest_path = write_synthetic_phase1_dataset(tmp_path)

    manifest, batch = load_verified_phase1_dataset(manifest_path, repository_root=tmp_path)

    assert manifest.adjustment_mode == "all"
    assert batch.metadata.provider_name == "alpaca"
    assert tuple(batch.data.columns) == ("session", "open", "high", "low", "close", "volume")
    assert batch.data.iloc[0]["session"] == date(2016, 1, 4)


def test_prepare_builds_deterministic_split_lock_and_stage_a_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = write_synthetic_phase1_dataset(tmp_path)
    feed_record = _feed_record(tmp_path, monkeypatch)

    lock = prepare_benchmark(
        manifest_path=manifest_path,
        feed_record_path=feed_record,
        benchmark_role=BenchmarkRole.PRIMARY,
        latest_complete_research_year=2025,
        artifact_root=Path("artifacts/benchmarks"),
        owner_approve_assumptions=True,
        repository_root=tmp_path,
    )

    store = BenchmarkArtifactStore(Path("artifacts/benchmarks"), repository_root=tmp_path)
    split = store.read_json(lock.benchmark_id, "split_manifest.json")
    assert split["boundary_exclusion_sessions"] == BOUNDARY_EXCLUSION_SESSIONS
    assert split["final_test"]["included_row_count"] >= 252
    assert split["final_test"]["positive_count"] >= 40
    assert split["final_test"]["negative_count"] >= 40
    assert (store.benchmark_dir(lock.benchmark_id) / "benchmark_lock.sha256").exists()
    assert lock.package_version == "2.0.0a1"


def test_iex_primary_benchmark_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = write_synthetic_phase1_dataset(tmp_path, feed="iex")
    feed_record = _feed_record(tmp_path, monkeypatch, feed="iex")

    with pytest.raises(BenchmarkEligibilityError):
        prepare_benchmark(
            manifest_path=manifest_path,
            feed_record_path=feed_record,
            benchmark_role=BenchmarkRole.PRIMARY,
            latest_complete_research_year=2025,
            artifact_root=Path("artifacts/benchmarks"),
            owner_approve_assumptions=True,
            repository_root=tmp_path,
        )


def test_classification_baselines_use_training_only_prevalence() -> None:
    baselines = classification_baseline_metrics(
        benchmark_id="bench",
        dataset_id="dataset",
        training_targets=[0, 0, 1, 1],
        evaluation_targets=[1, 1, 0, 0],
        partition_name="validation",
    )

    assert baselines["majority_class"].predicted_positive_count == 0
    assert baselines["training_prevalence"].predicted_positive_count == 4
    assert baselines["always_positive"].metrics["recall"].value == 1.0


def test_undefined_classification_metrics_are_explicit() -> None:
    metrics = classification_metric_set(
        benchmark_id="bench",
        dataset_id="dataset",
        model_name="diagnostic",
        partition_name="regime",
        targets=[1, 1, 1],
        probabilities=[0.7, 0.8, 0.9],
        predictions=[1, 1, 1],
    )

    assert metrics.metrics["roc_auc"].value is None
    assert metrics.metrics["roc_auc"].undefined_reason
    assert metrics.metrics["precision"].value == 1.0


def test_regime_policy_uses_training_only_volatility_threshold() -> None:
    sessions = XNYSCalendar().sessions_between(date(2020, 1, 2), date(2021, 12, 31))
    prices = [100.0 + index * 0.05 + 4.0 * (index % 7) for index, _ in enumerate(sessions)]
    frame = pd.DataFrame({"session": sessions, "close": prices})

    threshold = training_volatility_threshold(frame, training_sessions=sessions[:260])
    regimes = regime_frame(frame, volatility_threshold=threshold)

    assert threshold >= Decimal("0")
    assert {"bull", "bear", "unavailable"} >= set(regimes.data["trend_200"].unique())
    assert {"high_volatility", "lower_volatility", "unavailable"} >= set(
        regimes.data["realized_volatility_20"].unique()
    )
    assert {"drawdown", "normal"} >= set(regimes.data["drawdown_10"].unique())


def test_stage_a_final_labels_are_guarded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest_path = write_synthetic_phase1_dataset(tmp_path)
    feed_record = _feed_record(tmp_path, monkeypatch)
    lock = prepare_benchmark(
        manifest_path=manifest_path,
        feed_record_path=feed_record,
        benchmark_role=BenchmarkRole.PRIMARY,
        latest_complete_research_year=2025,
        artifact_root=Path("artifacts/benchmarks"),
        owner_approve_assumptions=True,
        repository_root=tmp_path,
    )
    store = BenchmarkArtifactStore(Path("artifacts/benchmarks"), repository_root=tmp_path)
    _, split_manifest, _, partitions = _reconstruct(lock, store)
    split_payload = store.read_json(lock.benchmark_id, "split_manifest.json")
    bundle = stage_a_bundle(split_manifest=split_manifest, partitions=partitions)

    assert split_payload["final_test"]["positive_count"] >= 40
    with pytest.raises(BenchmarkFinalTestAccessError):
        _ = bundle.final_test_labels


def test_artifact_store_reuses_matching_and_rejects_conflicts(tmp_path: Path) -> None:
    store = BenchmarkArtifactStore(Path("artifacts/benchmarks"), repository_root=tmp_path)
    checksum = store.write_json("bench", "benchmark_lock.json", {"a": 1})

    assert store.write_json("bench", "benchmark_lock.json", {"a": 1}) == checksum
    with pytest.raises(BenchmarkArtifactError):
        store.write_json("bench", "benchmark_lock.json", {"a": 2})
    benchmark_lock = store.benchmark_dir("bench") / "benchmark_lock.json"
    assert canonical_json_bytes({"a": 1}) == benchmark_lock.read_bytes()


def test_prepare_rejects_insufficient_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = write_synthetic_phase1_dataset(
        tmp_path,
        start=date(2023, 1, 3),
        end=date(2025, 12, 31),
    )
    feed_record = _feed_record(tmp_path, monkeypatch)

    with pytest.raises(BenchmarkEligibilityError):
        prepare_benchmark(
            manifest_path=manifest_path,
            feed_record_path=feed_record,
            benchmark_role=BenchmarkRole.PRIMARY,
            latest_complete_research_year=2025,
            artifact_root=Path("artifacts/benchmarks"),
            owner_approve_assumptions=True,
            repository_root=tmp_path,
        )


def test_benchmark_imports_do_not_construct_network_or_broker_clients() -> None:
    import spy_market_agent
    import spy_market_agent.benchmark
    import spy_market_agent.benchmark.cli

    assert spy_market_agent.__version__ == "2.0.0a1"
    assert spy_market_agent.benchmark.BENCHMARK_SCHEMA_VERSION
    with pytest.raises(SystemExit):
        spy_market_agent.benchmark.cli.main(["--help"])
