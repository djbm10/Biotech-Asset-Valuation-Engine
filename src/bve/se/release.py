"""Fail-closed release custody for the live public-data S&E pipeline."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from datetime import date, timedelta
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import MappingProxyType
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_HASH_CHUNK_SIZE = 1024 * 1024
_PYTHON_SOURCE_ROOT = "src/bve"
_REQUIRED_CONTROLLED_FILES = (
    ".github/workflows/se_public_pipeline.yml",
    "examples/configs/se/benchmarks/cd19_or_bcma_tce.yaml",
    "examples/configs/se/live_cd19_bcma_tce_policy.yaml",
    "pyproject.toml",
    "requirements/se-public-pipeline.txt",
    "src/bve/cli/se_run.py",
)


class ReleaseVerificationError(RuntimeError):
    """Raised when a live release cannot be verified exactly."""


def _validate_sha256(value: str, *, field_name: str) -> str:
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a 64-character lowercase SHA-256")
    return value


def _validate_repo_relative_path(value: str) -> str:
    if not value or value != value.strip():
        raise ValueError("validated file path must be a nonempty canonical repo-relative path")
    if "\\" in value or "\x00" in value:
        raise ValueError("validated file path contains unsafe path characters")

    posix_path = PurePosixPath(value)
    windows_path = PureWindowsPath(value)
    raw_parts = value.split("/")
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ValueError("validated file path must be repo-relative, not absolute")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ValueError("validated file path must not contain empty, current, or parent segments")
    if posix_path.as_posix() != value:
        raise ValueError("validated file path must use canonical POSIX form")
    return value


class LiveReleaseManifest(BaseModel):
    """Immutable identity and file-custody envelope for a validated live release."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["se_live_release_manifest_v2"] = "se_live_release_manifest_v2"
    release_id: str = Field(min_length=1)
    validated_on: date
    interval_days: int = Field(ge=1)
    policy_hash: str
    specification_path: str
    specification_hash: str
    evaluator_version: str = Field(min_length=1)
    validated_files: Mapping[str, str] = Field(min_length=1)

    @field_validator("release_id", "evaluator_version")
    @classmethod
    def validate_nonblank_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("release identity fields must not be blank")
        return value.strip()

    @field_validator("policy_hash", "specification_hash")
    @classmethod
    def validate_top_level_hashes(cls, value: str, info) -> str:
        return _validate_sha256(value, field_name=info.field_name)

    @field_validator("specification_path")
    @classmethod
    def validate_specification_path(cls, value: str) -> str:
        return _validate_repo_relative_path(value)

    @field_validator("validated_files")
    @classmethod
    def validate_file_hashes(cls, values: Mapping[str, str]) -> Mapping[str, str]:
        validated: dict[str, str] = {}
        for raw_path, raw_hash in values.items():
            path = _validate_repo_relative_path(raw_path)
            validated[path] = _validate_sha256(
                raw_hash,
                field_name=f"validated_files[{path!r}]",
            )
        return MappingProxyType(validated)

    @field_serializer("validated_files")
    def serialize_validated_files(self, values: Mapping[str, str]) -> dict[str, str]:
        return dict(values)

    @model_validator(mode="after")
    def bind_specification_to_validated_file(self) -> "LiveReleaseManifest":
        file_hash = self.validated_files.get(self.specification_path)
        if file_hash is None:
            raise ValueError("specification_path must be present in validated_files")
        if file_hash != self.specification_hash:
            raise ValueError(
                "specification_hash must match the validated_files hash for "
                "specification_path"
            )
        return self

    def canonical_payload(self) -> dict[str, object]:
        """Return a deterministic JSON-compatible release representation."""

        return {
            "schema_version": self.schema_version,
            "release_id": self.release_id,
            "validated_on": self.validated_on.isoformat(),
            "interval_days": self.interval_days,
            "policy_hash": self.policy_hash,
            "specification_path": self.specification_path,
            "specification_hash": self.specification_hash,
            "evaluator_version": self.evaluator_version,
            "validated_files": {
                path: self.validated_files[path]
                for path in sorted(self.validated_files)
            },
        }

    def canonical_json(self) -> str:
        """Serialize the release without insignificant whitespace or map-order drift."""

        return json.dumps(
            self.canonical_payload(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @property
    def manifest_hash(self) -> str:
        """SHA-256 identity of the canonical release manifest."""

        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    """Hash one regular file without loading it fully into memory."""

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"release file does not exist: {file_path}")
    if not file_path.is_file():
        raise ValueError(f"release path is not a regular file: {file_path}")

    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_file(repo_root: Path, relative_path: str) -> Path:
    """Resolve a validated path while preventing symlink escape from ``repo_root``."""

    safe_relative = _validate_repo_relative_path(relative_path)
    root = repo_root.resolve()
    candidate = (root / safe_relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"validated file resolves outside the repository: {safe_relative}"
        ) from exc
    return candidate


def required_release_files(
    repo_root: str | Path,
    specification_path: str | Path,
) -> tuple[str, ...]:
    """Return the deterministic minimum custody closure for ``bve-se-run``.

    The closure is derived from the repository rather than accepted from the
    manifest, so both release construction and verification detect a newly
    added or omitted runtime module independently. The whole ``bve`` package
    is covered because importing the console entry point executes
    ``bve.__init__`` before loading ``bve.cli.se_run``.
    """

    root = Path(repo_root)
    if not root.exists() or not root.is_dir():
        raise ValueError(f"repo_root must be an existing directory: {root}")
    root = root.resolve()
    specification = _validate_repo_relative_path(Path(specification_path).as_posix())

    source_root = _repo_file(root, _PYTHON_SOURCE_ROOT)
    if not source_root.exists() or not source_root.is_dir():
        raise ValueError(
            f"required release source directory is missing: {_PYTHON_SOURCE_ROOT}"
        )

    source_files: set[str] = set()
    for path in source_root.rglob("*.py"):
        if not path.is_file():
            continue
        relative_path = path.relative_to(root).as_posix()
        # Re-resolve each discovered file so a symlink cannot escape custody.
        _repo_file(root, relative_path)
        source_files.add(_validate_repo_relative_path(relative_path))
    if not source_files:
        raise ValueError(
            f"required release source directory has no Python files: {_PYTHON_SOURCE_ROOT}"
        )

    required = source_files | set(_REQUIRED_CONTROLLED_FILES) | {specification}
    for relative_path in sorted(required):
        file_path = _repo_file(root, relative_path)
        if not file_path.exists() or not file_path.is_file():
            raise ValueError(f"required release file is missing: {relative_path}")
    return tuple(sorted(required))


def build_release_manifest(
    *,
    release_id: str,
    validated_on: date,
    interval_days: int,
    policy_hash: str,
    specification_path: str | Path,
    specification_hash: str,
    evaluator_version: str,
    repo_root: str | Path,
    files: Iterable[str | Path],
) -> LiveReleaseManifest:
    """Hash a complete set of repo-relative files into a strict release manifest."""

    root = Path(repo_root)
    if not root.exists() or not root.is_dir():
        raise ValueError(f"repo_root must be an existing directory: {root}")

    relative_paths: list[str] = []
    seen: set[str] = set()
    for file_path in files:
        relative_path = _validate_repo_relative_path(Path(file_path).as_posix())
        if relative_path in seen:
            raise ValueError(f"duplicate validated file path: {relative_path}")
        seen.add(relative_path)
        relative_paths.append(relative_path)
    if not relative_paths:
        raise ValueError("at least one validated release file is required")

    required_files = set(required_release_files(root, specification_path))
    missing_files = sorted(required_files - seen)
    if missing_files:
        raise ValueError(
            "validated release files omit required runtime closure: "
            + ", ".join(missing_files)
        )

    validated_files = {
        relative_path: sha256_file(_repo_file(root, relative_path))
        for relative_path in sorted(relative_paths)
    }
    normalized_specification_path = Path(specification_path).as_posix()
    actual_specification_hash = validated_files[normalized_specification_path]
    if specification_hash != actual_specification_hash:
        raise ValueError(
            "specification hash mismatch while building release: "
            f"expected={specification_hash} actual={actual_specification_hash}"
        )
    return LiveReleaseManifest(
        release_id=release_id,
        validated_on=validated_on,
        interval_days=interval_days,
        policy_hash=policy_hash,
        specification_path=normalized_specification_path,
        specification_hash=specification_hash,
        evaluator_version=evaluator_version,
        validated_files=validated_files,
    )


def verify_release_manifest(
    manifest: LiveReleaseManifest,
    repo_root: str | Path,
    policy_hash: str,
    as_of: date,
) -> None:
    """Verify policy identity, validity interval, and every released file or fail."""

    failures: list[str] = []
    if not _SHA256_RE.fullmatch(policy_hash):
        failures.append("current policy hash is not a valid lowercase SHA-256")
    elif policy_hash != manifest.policy_hash:
        failures.append(
            f"policy hash mismatch: release={manifest.policy_hash} current={policy_hash}"
        )

    if as_of < manifest.validated_on:
        failures.append(
            f"release validation date {manifest.validated_on} is after as-of date {as_of}"
        )
    else:
        expires_on = manifest.validated_on + timedelta(days=manifest.interval_days)
        if as_of >= expires_on:
            failures.append(
                f"release expired on {expires_on}; revalidation is required as of {as_of}"
            )

    root = Path(repo_root)
    if not root.exists() or not root.is_dir():
        failures.append(f"repo root is missing or not a directory: {root}")
    else:
        try:
            required_files = set(
                required_release_files(root, manifest.specification_path)
            )
        except ValueError as exc:
            failures.append(str(exc))
            required_files = set()
        missing_files = sorted(required_files - set(manifest.validated_files))
        if missing_files:
            failures.append(
                "manifest omits required runtime closure: " + ", ".join(missing_files)
            )

        for relative_path, expected_hash in sorted(manifest.validated_files.items()):
            try:
                file_path = _repo_file(root, relative_path)
            except ValueError as exc:
                failures.append(str(exc))
                continue
            if not file_path.exists() or not file_path.is_file():
                failures.append(f"validated file is missing: {relative_path}")
                continue
            actual_hash = sha256_file(file_path)
            if actual_hash != expected_hash:
                failures.append(
                    f"validated file changed: {relative_path} "
                    f"expected={expected_hash} actual={actual_hash}"
                )

        try:
            actual_specification_hash = sha256_file(
                _repo_file(root, manifest.specification_path)
            )
        except (FileNotFoundError, ValueError):
            # The general validated-file loop already reports this path precisely.
            pass
        else:
            if actual_specification_hash != manifest.specification_hash:
                failures.append(
                    "specification hash mismatch: "
                    f"release={manifest.specification_hash} "
                    f"current={actual_specification_hash}"
                )

    if failures:
        raise ReleaseVerificationError(
            f"live release {manifest.release_id!r} verification failed: "
            + "; ".join(failures)
        )


__all__ = [
    "LiveReleaseManifest",
    "ReleaseVerificationError",
    "build_release_manifest",
    "required_release_files",
    "sha256_file",
    "verify_release_manifest",
]
