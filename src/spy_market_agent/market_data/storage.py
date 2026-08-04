from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from spy_market_agent.market_data.acquisition import AcquisitionRequest, DatasetManifest
from spy_market_agent.market_data.errors import (
    AtomicWriteFailure,
    ChecksumMismatch,
    ExistingDatasetConflict,
    UnsafeDataPath,
)
from spy_market_agent.market_data.manifest import (
    canonical_json_bytes,
    load_manifest_bytes,
    manifest_json_bytes,
    sha256_bytes,
)


@dataclass(frozen=True)
class DatasetArtifactPaths:
    raw_snapshot_path: Path
    canonical_path: Path
    manifest_path: Path

    def as_tuple(self) -> tuple[Path, Path, Path]:
        return (self.raw_snapshot_path, self.canonical_path, self.manifest_path)


@dataclass(frozen=True)
class ArtifactWriteResult:
    path: Path
    created: bool


class DatasetStore:
    """Safe repository-local storage for ignored Phase 1 data artifacts."""

    def __init__(self, data_root: Path, *, repository_root: Path | None = None) -> None:
        self.repository_root = (repository_root or Path.cwd()).resolve()
        self.data_root = self._resolve_data_root(data_root)

    def artifact_paths(
        self, *, request: AcquisitionRequest, dataset_id: str
    ) -> DatasetArtifactPaths:
        components = (
            request.provider,
            request.symbol,
            request.timeframe,
            request.feed,
            request.adjustment_mode,
        )
        raw_dir = self._safe_child(self.data_root / "raw", *components)
        canonical_dir = self._safe_child(self.data_root / "canonical", *components)
        manifest_dir = self._safe_child(self.data_root / "manifests", *components)
        filename_base = dataset_id
        return DatasetArtifactPaths(
            raw_snapshot_path=raw_dir / f"{filename_base}.raw.json",
            canonical_path=canonical_dir / f"{filename_base}.canonical.csv",
            manifest_path=manifest_dir / f"{filename_base}.manifest.json",
        )

    def relative_path(self, path: Path) -> str:
        resolved = self._safe_existing_or_parent_path(path)
        return resolved.relative_to(self.repository_root).as_posix()

    def write_dataset(
        self,
        *,
        paths: DatasetArtifactPaths,
        raw_bytes: bytes,
        canonical_bytes: bytes,
        manifest_bytes: bytes,
        expected_raw_checksum: str,
        expected_canonical_checksum: str,
        expected_manifest_checksum: str,
    ) -> tuple[ArtifactWriteResult, ArtifactWriteResult, ArtifactWriteResult]:
        raw_result = self._write_atomic_if_needed(
            paths.raw_snapshot_path,
            raw_bytes,
            expected_checksum=expected_raw_checksum,
        )
        canonical_result: ArtifactWriteResult | None = None
        try:
            canonical_result = self._write_atomic_if_needed(
                paths.canonical_path,
                canonical_bytes,
                expected_checksum=expected_canonical_checksum,
            )
            manifest_result = self._write_atomic_if_needed(
                paths.manifest_path,
                manifest_bytes,
                expected_checksum=expected_manifest_checksum,
            )
        except ExistingDatasetConflict:
            if raw_result.created:
                _best_effort_unlink(paths.raw_snapshot_path)
            if canonical_result is not None and canonical_result.created:
                _best_effort_unlink(paths.canonical_path)
            raise
        return raw_result, canonical_result, manifest_result

    def load_existing_manifest(self, path: Path) -> DatasetManifest:
        safe_path = self._safe_existing_or_parent_path(path)
        if not safe_path.exists():
            raise ChecksumMismatch(f"manifest does not exist: {self.relative_path(path)}")
        return load_manifest_bytes(safe_path.read_bytes())

    def verify_manifest_artifacts(self, manifest_path: Path) -> DatasetManifest:
        safe_manifest_path = self._safe_existing_or_parent_path(manifest_path)
        if not safe_manifest_path.exists():
            raise ChecksumMismatch("manifest artifact is missing.")
        manifest = load_manifest_bytes(safe_manifest_path.read_bytes())
        manifest_without_checksum = manifest.model_copy(update={"manifest_artifact_checksum": None})
        expected_manifest_checksum = sha256_bytes(manifest_json_bytes(manifest_without_checksum))
        if manifest.manifest_artifact_checksum != expected_manifest_checksum:
            raise ChecksumMismatch("manifest self-checksum does not match.")

        repository_root = self.repository_root
        raw_path = self._safe_existing_or_parent_path(
            repository_root / manifest.generated_file_locations.raw_snapshot_path
        )
        canonical_path = self._safe_existing_or_parent_path(
            repository_root / manifest.generated_file_locations.canonical_path
        )
        if not raw_path.exists() or not canonical_path.exists():
            raise ChecksumMismatch("raw or canonical artifact is missing.")
        if sha256_bytes(raw_path.read_bytes()) != manifest.raw_artifact_checksum:
            raise ChecksumMismatch("raw artifact checksum does not match manifest.")
        if sha256_bytes(canonical_path.read_bytes()) != manifest.artifact_checksum:
            raise ChecksumMismatch("canonical artifact checksum does not match manifest.")
        return manifest

    def _resolve_data_root(self, data_root: Path) -> Path:
        if data_root.is_absolute():
            raise UnsafeDataPath("data_root must be repository-relative.")
        if any(part == ".." for part in data_root.parts):
            raise UnsafeDataPath("data_root must not contain '..'.")
        candidate = (self.repository_root / data_root).resolve(strict=False)
        self._validate_inside_repository(candidate)
        blocked = (
            self.repository_root / ".git",
            self.repository_root / "src",
            self.repository_root / "tests",
            self.repository_root / "docs",
            self.repository_root / "reviews",
        )
        for blocked_path in blocked:
            try:
                candidate.relative_to(blocked_path.resolve(strict=False))
            except ValueError:
                continue
            raise UnsafeDataPath("data_root must not point inside source, test, doc, or Git paths.")
        return candidate

    def _safe_child(self, base: Path, *components: str) -> Path:
        if any(not component or "/" in component or "\\" in component for component in components):
            raise UnsafeDataPath("artifact path component is unsafe.")
        candidate = base.joinpath(*components).resolve(strict=False)
        self._validate_inside_data_root(candidate)
        return candidate

    def _safe_existing_or_parent_path(self, path: Path) -> Path:
        resolved_parent = path.parent.resolve(strict=False)
        self._validate_inside_data_root(resolved_parent)
        resolved_path = resolved_parent / path.name
        if path.name.startswith(".") or path.name.endswith(".tmp"):
            raise UnsafeDataPath("artifact filename is unsafe.")
        return resolved_path

    def _write_atomic_if_needed(
        self,
        path: Path,
        payload: bytes,
        *,
        expected_checksum: str,
    ) -> ArtifactWriteResult:
        safe_path = self._safe_existing_or_parent_path(path)
        if safe_path.exists():
            if safe_path.is_symlink():
                raise UnsafeDataPath("artifact path must not be a symlink.")
            existing_checksum = sha256_bytes(safe_path.read_bytes())
            if existing_checksum == expected_checksum:
                return ArtifactWriteResult(path=safe_path, created=False)
            raise ExistingDatasetConflict(
                f"existing artifact has conflicting checksum: {self.relative_path(safe_path)}"
            )

        safe_path.parent.mkdir(parents=True, exist_ok=True)
        actual_checksum = sha256_bytes(payload)
        if actual_checksum != expected_checksum:
            raise ChecksumMismatch("generated artifact checksum did not match expectation.")

        temp_path: Path | None = None
        try:
            descriptor, temp_name = tempfile.mkstemp(
                prefix=f".{safe_path.name}.",
                suffix=".tmp",
                dir=safe_path.parent,
            )
            temp_path = Path(temp_name)
            with os.fdopen(descriptor, "wb") as file_handle:
                file_handle.write(payload)
                file_handle.flush()
                os.fsync(file_handle.fileno())
            if sha256_bytes(temp_path.read_bytes()) != expected_checksum:
                raise ChecksumMismatch("temporary artifact checksum did not match expectation.")
            temp_path.replace(safe_path)
            if sha256_bytes(safe_path.read_bytes()) != expected_checksum:
                raise ChecksumMismatch("final artifact checksum did not match expectation.")
        except (OSError, ChecksumMismatch) as exc:
            if temp_path is not None:
                _best_effort_unlink(temp_path)
            if isinstance(exc, ChecksumMismatch):
                raise
            raise AtomicWriteFailure(f"atomic write failed for {safe_path.name}: {exc}") from exc
        return ArtifactWriteResult(path=safe_path, created=True)

    def _validate_inside_repository(self, path: Path) -> None:
        try:
            path.relative_to(self.repository_root)
        except ValueError as exc:
            raise UnsafeDataPath("path must remain inside the repository root.") from exc

    def _validate_inside_data_root(self, path: Path) -> None:
        self._validate_inside_repository(path)
        try:
            path.relative_to(self.data_root)
        except ValueError as exc:
            raise UnsafeDataPath("artifact path must remain inside data_root.") from exc


def raw_snapshot_json_bytes(snapshot: object) -> bytes:
    return canonical_json_bytes(snapshot)


def manifest_bytes_with_checksum(manifest: DatasetManifest) -> tuple[bytes, str]:
    payload = canonical_json_bytes(manifest)
    return payload, sha256_bytes(payload)


def _best_effort_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return
