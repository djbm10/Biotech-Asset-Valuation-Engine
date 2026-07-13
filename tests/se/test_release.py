from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from bve.se.release import (
    LiveReleaseManifest,
    ReleaseVerificationError,
    build_release_manifest,
    required_release_files,
    sha256_file,
    verify_release_manifest,
)


POLICY_HASH = "a" * 64
SPECIFICATION_PATH = "config/spec.yaml"
SPECIFICATION_HASH = "b" * 64
FILE_HASH = "c" * 64
OTHER_FILE_HASH = "d" * 64
CONTROLLED_FILES = (
    ".github/workflows/se_public_pipeline.yml",
    "examples/configs/se/benchmarks/cd19_or_bcma_tce.yaml",
    "examples/configs/se/live_cd19_bcma_tce_policy.yaml",
    "pyproject.toml",
    "requirements/se-public-pipeline.txt",
    "src/bve/cli/se_run.py",
)


def _manifest(**updates) -> LiveReleaseManifest:
    payload = {
        "schema_version": "se_live_release_manifest_v2",
        "release_id": "se-live-v2",
        "validated_on": "2026-07-12",
        "interval_days": 180,
        "policy_hash": POLICY_HASH,
        "specification_path": SPECIFICATION_PATH,
        "specification_hash": SPECIFICATION_HASH,
        "evaluator_version": "evaluator-v1",
        "validated_files": {
            SPECIFICATION_PATH: SPECIFICATION_HASH,
            "src/bve/se/pipeline.py": FILE_HASH,
        },
    }
    payload.update(updates)
    return LiveReleaseManifest.model_validate(payload)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _release_repo(tmp_path: Path) -> tuple[str, tuple[str, ...]]:
    _write(tmp_path / "src/bve/se/__init__.py", "\n")
    _write(tmp_path / "src/bve/se/runtime.py", "RUNTIME = True\n")
    for relative_path in CONTROLLED_FILES:
        _write(tmp_path / relative_path, f"controlled: {relative_path}\n")
    _write(tmp_path / SPECIFICATION_PATH, "specification: v1\n")
    return SPECIFICATION_PATH, required_release_files(tmp_path, SPECIFICATION_PATH)


def _built_manifest(
    tmp_path: Path,
    *,
    interval_days: int = 180,
    extra_files: tuple[str, ...] = (),
) -> LiveReleaseManifest:
    specification_path, required_files = _release_repo(tmp_path)
    return build_release_manifest(
        release_id="release-1",
        validated_on=date(2026, 7, 12),
        interval_days=interval_days,
        policy_hash=POLICY_HASH,
        specification_path=specification_path,
        specification_hash=sha256_file(tmp_path / specification_path),
        evaluator_version="evaluator-v1",
        repo_root=tmp_path,
        files=(*required_files, *extra_files),
    )


def test_release_manifest_is_strict_frozen_and_versioned() -> None:
    manifest = _manifest()

    assert manifest.schema_version == "se_live_release_manifest_v2"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _manifest(unexpected=True)
    with pytest.raises(ValidationError, match="frozen"):
        manifest.release_id = "changed"
    with pytest.raises(TypeError):
        manifest.validated_files["src/changed.py"] = OTHER_FILE_HASH


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "../secret.txt",
        "src/../../secret.txt",
        "./src/bve/se/pipeline.py",
        "src//bve/se/pipeline.py",
        "src\\bve\\se\\pipeline.py",
        "C:\\Windows\\system.ini",
    ],
)
def test_release_manifest_rejects_unsafe_file_paths(path: str) -> None:
    with pytest.raises(ValidationError, match="path"):
        _manifest(validated_files={path: FILE_HASH})
    with pytest.raises(ValidationError, match="path"):
        _manifest(specification_path=path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("policy_hash", "short"),
        ("specification_hash", "A" * 64),
        (
            "validated_files",
            {SPECIFICATION_PATH: SPECIFICATION_HASH, "src/bve/se/pipeline.py": "z" * 64},
        ),
    ],
)
def test_release_manifest_rejects_invalid_hashes(field: str, value) -> None:
    with pytest.raises(ValidationError, match="SHA-256"):
        _manifest(**{field: value})


def test_release_manifest_binds_specification_path_to_hash() -> None:
    with pytest.raises(ValidationError, match="present in validated_files"):
        _manifest(validated_files={"src/bve/se/pipeline.py": FILE_HASH})
    with pytest.raises(ValidationError, match="specification_hash must match"):
        _manifest(
            validated_files={
                SPECIFICATION_PATH: OTHER_FILE_HASH,
                "src/bve/se/pipeline.py": FILE_HASH,
            }
        )


def test_release_manifest_allows_duplicate_content_hashes() -> None:
    manifest = _manifest(
        validated_files={
            SPECIFICATION_PATH: SPECIFICATION_HASH,
            "src/bve/se/pipeline.py": FILE_HASH,
            "src/bve/se/operations.py": FILE_HASH,
        }
    )

    assert manifest.validated_files["src/bve/se/pipeline.py"] == FILE_HASH
    assert manifest.validated_files["src/bve/se/operations.py"] == FILE_HASH


def test_sha256_file_streams_regular_file(tmp_path: Path) -> None:
    path = tmp_path / "payload.txt"
    path.write_bytes(b"abc")

    assert sha256_file(path) == hashlib.sha256(b"abc").hexdigest()
    with pytest.raises(ValueError, match="not a regular file"):
        sha256_file(tmp_path)
    with pytest.raises(FileNotFoundError):
        sha256_file(tmp_path / "missing")


def test_build_release_manifest_hashes_complete_runtime_closure(tmp_path: Path) -> None:
    specification_path, required_files = _release_repo(tmp_path)
    extra = "config/extra.yaml"
    _write(tmp_path / extra, "extra: true\n")

    manifest = build_release_manifest(
        release_id="release-1",
        validated_on=date(2026, 7, 12),
        interval_days=180,
        policy_hash=POLICY_HASH,
        specification_path=specification_path,
        specification_hash=sha256_file(tmp_path / specification_path),
        evaluator_version="evaluator-v1",
        repo_root=tmp_path,
        files=(*required_files, extra),
    )

    assert set(required_files).issubset(manifest.validated_files)
    assert manifest.validated_files[extra] == sha256_file(tmp_path / extra)
    assert manifest.specification_path == specification_path
    assert manifest.specification_hash == manifest.validated_files[specification_path]


def test_build_release_manifest_rejects_omitted_runtime_file(tmp_path: Path) -> None:
    specification_path, required_files = _release_repo(tmp_path)
    omitted = "src/bve/se/runtime.py"

    with pytest.raises(ValueError, match=f"runtime closure: {omitted}"):
        build_release_manifest(
            release_id="release-1",
            validated_on=date(2026, 7, 12),
            interval_days=180,
            policy_hash=POLICY_HASH,
            specification_path=specification_path,
            specification_hash=sha256_file(tmp_path / specification_path),
            evaluator_version="evaluator-v1",
            repo_root=tmp_path,
            files=[path for path in required_files if path != omitted],
        )


def test_build_release_manifest_rejects_specification_mismatch(tmp_path: Path) -> None:
    specification_path, required_files = _release_repo(tmp_path)

    with pytest.raises(ValueError, match="specification hash mismatch while building"):
        build_release_manifest(
            release_id="release-1",
            validated_on=date(2026, 7, 12),
            interval_days=180,
            policy_hash=POLICY_HASH,
            specification_path=specification_path,
            specification_hash=SPECIFICATION_HASH,
            evaluator_version="evaluator-v1",
            repo_root=tmp_path,
            files=required_files,
        )


def test_build_release_manifest_rejects_duplicate_paths(tmp_path: Path) -> None:
    specification_path, required_files = _release_repo(tmp_path)

    with pytest.raises(ValueError, match="duplicate validated file path"):
        build_release_manifest(
            release_id="release-1",
            validated_on=date(2026, 7, 12),
            interval_days=180,
            policy_hash=POLICY_HASH,
            specification_path=specification_path,
            specification_hash=sha256_file(tmp_path / specification_path),
            evaluator_version="evaluator-v1",
            repo_root=tmp_path,
            files=(*required_files, required_files[0]),
        )


def test_manifest_hash_is_deterministic_across_mapping_order() -> None:
    files = {
        SPECIFICATION_PATH: SPECIFICATION_HASH,
        "src/a.py": FILE_HASH,
        "src/b.py": OTHER_FILE_HASH,
    }
    first = _manifest(validated_files=files)
    reordered = _manifest(validated_files=dict(reversed(list(files.items()))))

    assert len(first.manifest_hash) == 64
    assert first.canonical_json() == reordered.canonical_json()
    assert first.manifest_hash == reordered.manifest_hash


def test_verify_release_manifest_accepts_exact_current_release(tmp_path: Path) -> None:
    manifest = _built_manifest(tmp_path)

    verify_release_manifest(
        manifest,
        repo_root=tmp_path,
        policy_hash=POLICY_HASH,
        as_of=date(2026, 7, 13),
    )


def test_verify_release_manifest_independently_detects_omitted_runtime_file(
    tmp_path: Path,
) -> None:
    specification_path, required_files = _release_repo(tmp_path)
    omitted = "src/bve/se/runtime.py"
    validated_files = {
        path: sha256_file(tmp_path / path)
        for path in required_files
        if path != omitted
    }
    manifest = _manifest(
        specification_path=specification_path,
        specification_hash=validated_files[specification_path],
        validated_files=validated_files,
    )

    with pytest.raises(ReleaseVerificationError, match=f"runtime closure: {omitted}"):
        verify_release_manifest(
            manifest,
            repo_root=tmp_path,
            policy_hash=POLICY_HASH,
            as_of=date(2026, 7, 13),
        )


def test_verify_release_manifest_detects_missing_and_changed_files(tmp_path: Path) -> None:
    changed = "extras/changed.py"
    missing = "extras/missing.py"
    _write(tmp_path / changed, "prior\n")
    _write(tmp_path / missing, "present\n")
    manifest = _built_manifest(tmp_path, extra_files=(changed, missing))
    _write(tmp_path / changed, "current\n")
    (tmp_path / missing).unlink()

    with pytest.raises(ReleaseVerificationError) as exc_info:
        verify_release_manifest(
            manifest,
            repo_root=tmp_path,
            policy_hash=POLICY_HASH,
            as_of=date(2026, 7, 13),
        )
    message = str(exc_info.value)
    assert f"validated file changed: {changed}" in message
    assert f"validated file is missing: {missing}" in message


def test_verify_release_manifest_detects_specification_change(tmp_path: Path) -> None:
    manifest = _built_manifest(tmp_path)
    _write(tmp_path / SPECIFICATION_PATH, "specification: changed\n")

    with pytest.raises(ReleaseVerificationError) as exc_info:
        verify_release_manifest(
            manifest,
            repo_root=tmp_path,
            policy_hash=POLICY_HASH,
            as_of=date(2026, 7, 13),
        )
    message = str(exc_info.value)
    assert f"validated file changed: {SPECIFICATION_PATH}" in message
    assert "specification hash mismatch" in message


def test_verify_release_manifest_detects_policy_mismatch(tmp_path: Path) -> None:
    manifest = _built_manifest(tmp_path)

    with pytest.raises(ReleaseVerificationError, match="policy hash mismatch"):
        verify_release_manifest(
            manifest,
            repo_root=tmp_path,
            policy_hash="e" * 64,
            as_of=date(2026, 7, 13),
        )


def test_verify_release_manifest_fails_on_expiry_boundary(tmp_path: Path) -> None:
    manifest = _built_manifest(tmp_path, interval_days=2)

    verify_release_manifest(
        manifest,
        repo_root=tmp_path,
        policy_hash=POLICY_HASH,
        as_of=date(2026, 7, 13),
    )
    with pytest.raises(ReleaseVerificationError, match="release expired on 2026-07-14"):
        verify_release_manifest(
            manifest,
            repo_root=tmp_path,
            policy_hash=POLICY_HASH,
            as_of=date(2026, 7, 14),
        )


def test_verify_release_manifest_rejects_future_validation_date(tmp_path: Path) -> None:
    manifest = _built_manifest(tmp_path)

    with pytest.raises(ReleaseVerificationError, match="after as-of date"):
        verify_release_manifest(
            manifest,
            repo_root=tmp_path,
            policy_hash=POLICY_HASH,
            as_of=date(2026, 7, 11),
        )
