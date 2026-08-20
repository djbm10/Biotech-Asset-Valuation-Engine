"""Publish an ontology snapshot as a durable, re-verifiable artifact.

An ontology snapshot is an *input to evidence*, so it needs the same treatment as the
evidence itself: pinned upstream releases, hashes over the bytes actually read, a
manifest that states what was built and a receipt that can be recomputed later to prove
the manifest still describes the files on disk.

The layout mirrors the benchmark lineage already in use::

    ontology/<version>/
      manifest.json     what was built, from what, with which code
      receipt.json      hashes binding the manifest to the files beside it
      normalized/       the snapshot the resolver reads
      export/           archive + checksum for durable off-repo storage

Two hash families are kept apart on purpose. *Source* hashes cover the upstream bytes;
*code* hashes cover the parsers and resolver that interpreted them. When a rebuild
differs, those two answer different questions — "upstream moved" and "we read it
differently" — and collapsing them into one digest destroys the distinction exactly when
it is needed.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import tarfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bve.se.ontology.bulk import RawFileDigest, file_sha256
from bve.se.ontology.modality import MODALITY_ONTOLOGY_VERSION
from bve.se.ontology.records import EntityType
from bve.se.ontology.resolver import BiomedicalEntityResolver
from bve.se.ontology.snapshot import RESOLVER_VERSION, OntologySnapshot

MANIFEST_FILENAME = "manifest.json"
RECEIPT_FILENAME = "receipt.json"
NORMALIZED_DIRNAME = "normalized"
EXPORT_DIRNAME = "export"
ARCHIVE_NAME = "ontology_snapshot.tar.gz"

#: Modules whose behaviour decides what the normalized view looks like. Hashed so that a
#: snapshot rebuilt after a parser change is visibly a different build even when every
#: upstream byte is identical.
_CODE_MODULES = (
    "bve/se/ontology/records.py",
    "bve/se/ontology/resolver.py",
    "bve/se/ontology/modality.py",
    "bve/se/ontology/targets.py",
    "bve/se/ontology/bulk.py",
    "bve/se/ontology/sources/open_targets.py",
    "bve/se/ontology/sources/chembl.py",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def code_hashes() -> dict[str, str]:
    """Digest each module that participates in interpreting the upstream data."""

    root = _repo_root()
    hashes: dict[str, str] = {}
    for relative in _CODE_MODULES:
        path = root / relative
        if path.is_file():
            hashes[relative] = file_sha256(path)[0]
    return hashes


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None if result.returncode == 0 else None


def summarize_entities(resolver: BiomedicalEntityResolver) -> dict[str, Any]:
    """Count what the normalized view contains and what it could not agree on.

    Conflicts are summarized rather than suppressed. A snapshot with zero recorded
    conflicts over tens of thousands of entities is not clean data — it is a resolver
    that stopped looking.
    """

    counts: dict[str, int] = {}
    conflict_counts: Counter[str] = Counter()
    conflicted_entities = 0
    multi_source = 0
    symbol_less = 0

    for entity_type in EntityType:
        entities = resolver.entities_of_type(entity_type)
        counts[entity_type.value] = len(entities)
        for entity in entities:
            if entity.conflicts:
                conflicted_entities += 1
                for conflict in entity.conflicts:
                    conflict_counts[conflict.conflict_type.value] += 1
            if len(entity.contributing_sources) > 1:
                multi_source += 1
            if not entity.canonical_symbol:
                symbol_less += 1

    return {
        "entity_counts": counts,
        "total_entities": sum(counts.values()),
        "entities_with_multiple_sources": multi_source,
        "entities_without_canonical_symbol": symbol_less,
        "entities_with_conflicts": conflicted_entities,
        "conflicts_by_type": dict(sorted(conflict_counts.items())),
    }


def build_manifest(
    snapshot: OntologySnapshot,
    resolver: BiomedicalEntityResolver,
    raw_files: dict[str, list[RawFileDigest]],
    *,
    built_at: datetime | None = None,
) -> dict[str, Any]:
    """Describe the build completely enough that a reader can challenge it."""

    return {
        "artifact_type": "ontology_snapshot",
        "ontology_version": snapshot.ontology_version,
        "resolver_version": RESOLVER_VERSION,
        "modality_version": MODALITY_ONTOLOGY_VERSION,
        "built_at": (built_at or datetime.now(timezone.utc)).isoformat(),
        "built_by": {
            "git_commit": _git_commit(),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "sources": [
            {
                **source.model_dump(mode="json"),
                "raw_files": [
                    digest.as_dict() for digest in raw_files.get(source.source, [])
                ],
            }
            for source in sorted(snapshot.sources, key=lambda item: item.source)
        ],
        "source_record_count": len(snapshot.records),
        "code_hashes": code_hashes(),
        "normalized": summarize_entities(resolver),
    }


def _hash_tree(directory: Path) -> dict[str, str]:
    """Hash every file under a directory, keyed by its path relative to it."""

    return {
        str(path.relative_to(directory)): file_sha256(path)[0]
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def build_receipt(artifact_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Bind the manifest to the bytes sitting beside it.

    The receipt hashes the manifest as well as the files it describes, so a manifest
    edited after publication fails revalidation instead of quietly redefining what was
    published.
    """

    manifest_bytes = _canonical_json(manifest)
    return {
        "artifact_type": "ontology_snapshot_receipt",
        "ontology_version": manifest["ontology_version"],
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "bound_files": _hash_tree(artifact_dir / NORMALIZED_DIRNAME),
        "issued_at": datetime.now(timezone.utc).isoformat(),
    }


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def publish(
    snapshot: OntologySnapshot,
    raw_files: dict[str, list[RawFileDigest]],
    *,
    root: Path,
    built_at: datetime | None = None,
) -> Path:
    """Write the full artifact tree and its archive; returns the artifact directory."""

    resolver = BiomedicalEntityResolver(snapshot)
    artifact_dir = root / snapshot.ontology_version
    (artifact_dir / NORMALIZED_DIRNAME).mkdir(parents=True, exist_ok=True)
    (artifact_dir / EXPORT_DIRNAME).mkdir(parents=True, exist_ok=True)

    snapshot.write(artifact_dir / NORMALIZED_DIRNAME)

    manifest = build_manifest(snapshot, resolver, raw_files, built_at=built_at)
    (artifact_dir / MANIFEST_FILENAME).write_bytes(_canonical_json(manifest))

    receipt = build_receipt(artifact_dir, manifest)
    (artifact_dir / RECEIPT_FILENAME).write_bytes(_canonical_json(receipt))

    archive_path = artifact_dir / EXPORT_DIRNAME / ARCHIVE_NAME
    _write_archive(artifact_dir, archive_path)
    checksum, byte_length = file_sha256(archive_path)
    (archive_path.parent / f"{ARCHIVE_NAME}.sha256").write_text(
        f"{checksum}  {ARCHIVE_NAME}\n", encoding="utf-8"
    )
    (artifact_dir / EXPORT_DIRNAME / "STORAGE_STATUS.json").write_text(
        json.dumps(
            {
                "archive": ARCHIVE_NAME,
                "sha256": checksum,
                "byte_length": byte_length,
                "ontology_version": snapshot.ontology_version,
                "storage_status": "LOCAL_ONLY",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return artifact_dir


def _write_archive(artifact_dir: Path, archive_path: Path) -> None:
    """Archive the manifest, receipt and normalized snapshot reproducibly.

    Members are sorted and stripped of mtime, uid and gid: an archive whose bytes depend
    on when it was rolled cannot be compared against a later rebuild, which is most of
    the reason to publish a checksum at all.
    """

    members = sorted(
        path
        for path in artifact_dir.rglob("*")
        if path.is_file() and EXPORT_DIRNAME not in path.relative_to(artifact_dir).parts
    )
    with tarfile.open(archive_path, "w:gz", compresslevel=9, format=tarfile.GNU_FORMAT) as tar:
        for path in members:
            info = tar.gettarinfo(str(path), arcname=str(path.relative_to(artifact_dir)))
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with path.open("rb") as handle:
                tar.addfile(info, handle)


def revalidate(artifact_dir: Path) -> list[str]:
    """Recompute the receipt against the files on disk; returns mismatches.

    An empty list means the artifact still is what it says it is. Used both after a local
    build and after a fresh download from durable storage, which is the only way to know
    the published copy is the built one.
    """

    problems: list[str] = []
    manifest_path = artifact_dir / MANIFEST_FILENAME
    receipt_path = artifact_dir / RECEIPT_FILENAME
    for path in (manifest_path, receipt_path):
        if not path.is_file():
            problems.append(f"missing {path.name}")
    if problems:
        return problems

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    recomputed = hashlib.sha256(_canonical_json(manifest)).hexdigest()
    if recomputed != receipt.get("manifest_sha256"):
        problems.append("manifest_sha256 mismatch: the manifest changed after the receipt")

    observed = _hash_tree(artifact_dir / NORMALIZED_DIRNAME)
    bound = receipt.get("bound_files") or {}
    for name, expected in sorted(bound.items()):
        actual = observed.get(name)
        if actual is None:
            problems.append(f"bound file missing: {name}")
        elif actual != expected:
            problems.append(f"bound file changed: {name}")
    for name in sorted(set(observed) - set(bound)):
        problems.append(f"unbound file present: {name}")

    snapshot = OntologySnapshot.read(artifact_dir / NORMALIZED_DIRNAME)
    if snapshot.ontology_version != manifest.get("ontology_version"):
        problems.append(
            f"ontology_version mismatch: snapshot says {snapshot.ontology_version}, "
            f"manifest says {manifest.get('ontology_version')}"
        )
    return problems
