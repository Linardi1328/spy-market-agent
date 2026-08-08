from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from spy_market_agent.benchmark.artifacts import BenchmarkArtifactStore, sha256_bytes
from spy_market_agent.benchmark.errors import (
    BenchmarkArtifactError,
    BenchmarkLockError,
    raise_benchmark_error,
)
from spy_market_agent.benchmark.locks import (
    BenchmarkArtifactIndex,
    BenchmarkLock,
    VerificationResult,
)


def verify_benchmark_directory(
    benchmark_root: Path,
    *,
    repository_root: Path | None = None,
) -> VerificationResult:
    repo_root = (repository_root or Path.cwd()).resolve()
    benchmark_dir = benchmark_root.resolve(strict=False)
    if not benchmark_dir.exists() or not benchmark_dir.is_dir():
        raise_benchmark_error(
            BenchmarkArtifactError,
            "benchmark_directory_missing",
            "benchmark directory is missing.",
        )
    artifact_root = benchmark_dir.parent
    store = BenchmarkArtifactStore(artifact_root, repository_root=repo_root)
    benchmark_id = benchmark_dir.name
    lock = _load_lock(store, benchmark_id)
    reasons: list[str] = []
    checked: list[str] = []
    lock_path = store.artifact_path(benchmark_id, "benchmark_lock.json")
    lock_checksum_path = store.artifact_path(benchmark_id, "benchmark_lock.sha256")
    if not lock_checksum_path.exists():
        reasons.append("benchmark_lock.sha256 is missing")
    else:
        checked.append("benchmark_lock.sha256")
        if lock_checksum_path.read_text(encoding="utf-8").strip() != sha256_bytes(
            lock_path.read_bytes()
        ):
            reasons.append("benchmark_lock.sha256 does not match benchmark_lock.json")
    if lock.benchmark_id != benchmark_id:
        reasons.append("benchmark ID does not match directory name")

    index_path = store.artifact_path(benchmark_id, "artifact_index.json")
    if index_path.exists():
        try:
            index = BenchmarkArtifactIndex.model_validate(
                store.read_json(benchmark_id, "artifact_index.json")
            )
        except ValidationError:
            raise_benchmark_error(
                BenchmarkArtifactError,
                "artifact_index_invalid",
                "artifact index failed schema validation.",
            )
        checked.append("artifact_index.json")
        for name, metadata in index.artifacts.items():
            path = store.artifact_path(benchmark_id, name)
            if not path.exists():
                reasons.append(f"{name} listed in artifact_index.json is missing")
                continue
            checked.append(name)
            expected = metadata.get("sha256")
            if expected and sha256_bytes(path.read_bytes()) != expected:
                reasons.append(f"{name} checksum mismatch")
    result = VerificationResult(
        benchmark_id=lock.benchmark_id,
        dataset_id=lock.dataset_id,
        passed=not reasons,
        checked_artifacts=tuple(sorted(set(checked))),
        reasons=tuple(reasons),
    )
    if reasons:
        raise_benchmark_error(
            BenchmarkArtifactError,
            "benchmark_verification_failed",
            "; ".join(reasons),
        )
    return result


def _load_lock(store: BenchmarkArtifactStore, benchmark_id: str) -> BenchmarkLock:
    try:
        return BenchmarkLock.model_validate(store.read_json(benchmark_id, "benchmark_lock.json"))
    except ValidationError:
        raise_benchmark_error(
            BenchmarkLockError,
            "benchmark_lock_invalid",
            "benchmark lock failed schema validation.",
        )
