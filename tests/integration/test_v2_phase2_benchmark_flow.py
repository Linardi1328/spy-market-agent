from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from spy_market_agent.benchmark.dataset import record_feed_availability
from spy_market_agent.benchmark.errors import BenchmarkArtifactError, BenchmarkFinalTestAccessError
from spy_market_agent.benchmark.locks import BenchmarkRole
from spy_market_agent.benchmark.pipeline import (
    finalize_lock,
    prepare_benchmark,
    run_final_test,
    run_validation,
)
from spy_market_agent.benchmark.verification import verify_benchmark_directory
from unit.v2_phase2_helpers import SYNTHETIC_NOW, write_synthetic_phase1_dataset


def _prepared_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    manifest_path = write_synthetic_phase1_dataset(tmp_path)
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
        owner_acknowledgement=True,
        evidence_source_description="synthetic owner-provided offline probe record",
        output=Path("feed.json"),
    )
    lock = prepare_benchmark(
        manifest_path=manifest_path,
        feed_record_path=tmp_path / "feed.json",
        benchmark_role=BenchmarkRole.PRIMARY,
        latest_complete_research_year=2025,
        artifact_root=Path("artifacts/benchmarks"),
        owner_approve_assumptions=True,
        repository_root=tmp_path,
    )
    return tmp_path / "artifacts" / "benchmarks" / lock.benchmark_id / "benchmark_lock.json"


def test_synthetic_manifest_to_prepare_validation_final_and_audit_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = _prepared_lock(tmp_path, monkeypatch)
    benchmark_root = lock_path.parent

    verify_benchmark_directory(benchmark_root, repository_root=tmp_path)
    validation = run_validation(benchmark_lock_path=lock_path)
    assert validation.selected_model_name in {"logistic_regression", "gradient_boosting"}
    assert not (benchmark_root / "final_test_results.json").exists()

    final_lock = finalize_lock(
        benchmark_lock_path=lock_path,
        acknowledge_final_test_policy=True,
    )
    final_lock_path = benchmark_root / "final_test_lock.json"
    assert final_lock.selected_model_name == validation.selected_model_name

    final_results = run_final_test(
        final_test_lock_path=final_lock_path,
        acknowledge_final_test_access=True,
    )
    assert final_results["selected_model_name"] == validation.selected_model_name
    assert (benchmark_root / "final_test_access.json").exists()
    assert (benchmark_root / "cost_sensitivity.json").exists()
    assert (benchmark_root / "regime_results.json").exists()

    replay = run_final_test(
        final_test_lock_path=final_lock_path,
        acknowledge_final_test_access=False,
        audit_replay=True,
    )
    assert replay["audit_replay"] == "passed"


def test_final_test_before_final_lock_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = _prepared_lock(tmp_path, monkeypatch)

    with pytest.raises(BenchmarkFinalTestAccessError):
        run_final_test(
            final_test_lock_path=lock_path.parent / "final_test_lock.json",
            acknowledge_final_test_access=True,
        )


def test_corrupted_artifact_fails_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = _prepared_lock(tmp_path, monkeypatch)
    (lock_path.parent / "benchmark_lock.sha256").write_text("bad\n", encoding="utf-8")

    with pytest.raises(BenchmarkArtifactError):
        verify_benchmark_directory(lock_path.parent, repository_root=tmp_path)
