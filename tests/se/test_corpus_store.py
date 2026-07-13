from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pytest

import bve.se.acquisition.corpus_store as corpus_store_module
from bve.se.acquisition.corpus_store import (
    CorpusIntegrityError,
    CorpusStore,
    IndexStatus,
    ParserStatus,
)
from bve.se.schemas.contracts import SourceTier

AS_OF = date(2026, 7, 10)


def _add(
    store: CorpusStore,
    *,
    payload,
    text: str,
    family: str = "pubmed",
    url: str = "https://example.test/doc",
    native: bool = False,
):
    return store.add(
        source_family=family,
        source_url=url,
        publisher="Example",
        document_type="publication_abstract",
        source_tier=SourceTier.PRIMARY,
        raw_payload=payload,
        text=text,
        as_of_date=AS_OF,
        native_snapshot=native,
    )


def test_content_addressing_is_idempotent(tmp_path) -> None:
    store = CorpusStore(tmp_path)
    first = _add(store, payload={"pmid": "1", "body": "CD19 bispecific"}, text="CD19 bispecific")
    second = _add(store, payload={"pmid": "1", "body": "CD19 bispecific"}, text="CD19 bispecific")
    assert first.document_id == second.document_id
    assert len(store.documents()) == 1
    assert tmp_path.joinpath("manifest.jsonl").read_text().count("\n") == 1


def test_document_identity_retains_provenance_for_identical_payload(tmp_path) -> None:
    store = CorpusStore(tmp_path)
    payload = {"body": "shared public payload"}
    first = _add(store, payload=payload, text="one", family="pubmed", url="https://one.test")
    second = _add(store, payload=payload, text="two", family="pubmed", url="https://two.test")
    third = _add(store, payload=payload, text="three", family="sec_edgar", url="https://one.test")

    expected_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    assert {first.content_hash, second.content_hash, third.content_hash} == {expected_hash}
    assert len({first.document_id, second.document_id, third.document_id}) == 3
    assert first.snapshot_path == second.snapshot_path
    assert third.snapshot_path != first.snapshot_path
    assert len(store.documents()) == 3


def test_health_metadata_recorded(tmp_path) -> None:
    store = CorpusStore(tmp_path)
    ok = _add(store, payload={"a": 1}, text="usable text")
    empty = _add(store, payload={"a": 2}, text="   ")
    assert ok.parser_status is ParserStatus.OK
    assert ok.index_status is IndexStatus.INDEXED
    assert empty.parser_status is ParserStatus.EMPTY
    assert empty.index_status is IndexStatus.UNINDEXED
    assert ok.content_hash != empty.content_hash
    assert ok.snapshot_path and date.fromisoformat(ok.as_of_date.isoformat())


def test_manifest_reload_across_instances(tmp_path) -> None:
    store = CorpusStore(tmp_path)
    _add(store, payload={"x": 1}, text="one")
    reloaded = CorpusStore(tmp_path)
    assert len(reloaded.documents()) == 1
    # Re-adding the same bytes through a fresh store stays idempotent.
    _add(reloaded, payload={"x": 1}, text="one")
    assert len(reloaded.documents()) == 1


def test_stale_store_reloads_manifest_under_lock_before_deduplication(tmp_path) -> None:
    first_store = CorpusStore(tmp_path)
    stale_store = CorpusStore(tmp_path)

    first = _add(first_store, payload={"x": 1}, text="one")
    duplicate = _add(stale_store, payload={"x": 1}, text="one")

    assert duplicate.document_id == first.document_id
    assert len(stale_store.documents()) == 1
    assert tmp_path.joinpath("manifest.jsonl").read_text().count("\n") == 1


def test_concurrent_store_instances_append_same_identity_once(tmp_path) -> None:
    stores = [CorpusStore(tmp_path), CorpusStore(tmp_path)]
    ready = threading.Barrier(2)

    def add_after_barrier(store: CorpusStore):
        ready.wait()
        return _add(store, payload={"concurrent": True}, text="concurrent")

    with ThreadPoolExecutor(max_workers=2) as executor:
        documents = list(executor.map(add_after_barrier, stores))

    assert documents[0].document_id == documents[1].document_id
    assert tmp_path.joinpath("manifest.jsonl").read_text().count("\n") == 1
    assert len(CorpusStore(tmp_path).documents()) == 1


def test_legacy_payload_only_document_id_remains_idempotent(tmp_path) -> None:
    store = CorpusStore(tmp_path)
    original = _add(store, payload={"legacy": True}, text="legacy")
    manifest_path = tmp_path / "manifest.jsonl"
    row = json.loads(manifest_path.read_text())
    legacy_id = f"corpusdoc:{original.content_hash[:24]}"
    row["document_id"] = legacy_id
    manifest_path.write_text(json.dumps(row) + "\n")

    reloaded = CorpusStore(tmp_path)
    duplicate = _add(reloaded, payload={"legacy": True}, text="legacy")

    assert duplicate.document_id == legacy_id
    assert len(reloaded.documents()) == 1
    assert manifest_path.read_text().count("\n") == 1


def test_legacy_repo_relative_snapshot_path_rebases_from_store_root(tmp_path, monkeypatch) -> None:
    root = tmp_path / "repo" / "corpus"
    store = CorpusStore(root)
    document = _add(store, payload="legacy raw text", text="legacy raw text")
    manifest_path = root / "manifest.jsonl"
    row = json.loads(manifest_path.read_text())
    row["snapshot_path"] = f"research/legacy/corpus/snapshots/pubmed/{document.content_hash}.json"
    manifest_path.write_text(json.dumps(row) + "\n")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    reloaded = CorpusStore(root)

    assert reloaded.validate().valid is True
    assert reloaded.documents()[0].document_id == document.document_id


def test_snapshot_write_is_atomic_and_fsynced(tmp_path, monkeypatch) -> None:
    replacements: list[tuple[Path, Path]] = []
    fsynced_descriptors: list[int] = []
    real_replace = corpus_store_module.os.replace
    real_fsync = corpus_store_module.os.fsync

    def recording_replace(source, destination) -> None:
        replacements.append((Path(source), Path(destination)))
        real_replace(source, destination)

    def recording_fsync(descriptor: int) -> None:
        fsynced_descriptors.append(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr(corpus_store_module.os, "replace", recording_replace)
    monkeypatch.setattr(corpus_store_module.os, "fsync", recording_fsync)

    document = _add(CorpusStore(tmp_path), payload={"durable": True}, text="durable")

    assert len(replacements) == 1
    temporary, destination = replacements[0]
    assert temporary.name.endswith(".tmp")
    assert destination == Path(document.snapshot_path)
    assert not temporary.exists()
    # Snapshot file, snapshot directory, manifest file, and new-manifest directory.
    assert len(fsynced_descriptors) >= 4


def test_validate_returns_integrity_report(tmp_path) -> None:
    store = CorpusStore(tmp_path)
    _add(store, payload={"a": 1}, text="one", url="https://one.test")
    _add(store, payload={"a": 1}, text="two", url="https://two.test")

    report = store.validate()

    assert report.valid is True
    assert report.document_count == 2
    assert report.snapshot_count == 1
    assert report.errors == ()


def test_corrupt_manifest_row_is_rejected(tmp_path) -> None:
    tmp_path.joinpath("manifest.jsonl").write_text("{not-json}\n")

    with pytest.raises(CorpusIntegrityError, match="invalid CorpusDocument"):
        CorpusStore(tmp_path)


def test_duplicate_manifest_row_is_rejected(tmp_path) -> None:
    store = CorpusStore(tmp_path)
    _add(store, payload={"duplicate": True}, text="duplicate")
    manifest_path = tmp_path / "manifest.jsonl"
    row = manifest_path.read_text()
    manifest_path.write_text(row + row)

    with pytest.raises(CorpusIntegrityError, match="duplicate document_id"):
        CorpusStore(tmp_path)


def test_snapshot_path_outside_store_is_rejected(tmp_path) -> None:
    store = CorpusStore(tmp_path)
    _add(store, payload={"safe": True}, text="safe")
    manifest_path = tmp_path / "manifest.jsonl"
    row = json.loads(manifest_path.read_text())
    row["snapshot_path"] = str(tmp_path.parent / f"{row['content_hash']}.json")
    manifest_path.write_text(json.dumps(row) + "\n")

    with pytest.raises(CorpusIntegrityError, match="escapes store root"):
        CorpusStore(tmp_path)


def test_snapshot_symlink_target_is_rejected(tmp_path) -> None:
    payload = {"unsafe": True}
    content_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    family_dir = tmp_path / "snapshots" / "pubmed"
    family_dir.mkdir(parents=True)
    outside = tmp_path.parent / "outside-snapshot.json"
    outside.write_text(json.dumps(payload) + "\n")
    family_dir.joinpath(f"{content_hash}.json").symlink_to(outside)

    with pytest.raises(CorpusIntegrityError, match="escapes store root|symbolic link"):
        _add(CorpusStore(tmp_path), payload=payload, text="unsafe")


def test_missing_and_tampered_snapshots_are_rejected(tmp_path) -> None:
    missing_root = tmp_path / "missing"
    missing_store = CorpusStore(missing_root)
    missing = _add(missing_store, payload={"value": 1}, text="one")
    Path(missing.snapshot_path).unlink()

    missing_report = missing_store.validate(raise_on_error=False)
    assert missing_report.valid is False
    assert "snapshot does not exist" in missing_report.errors[0]
    with pytest.raises(CorpusIntegrityError, match="snapshot does not exist"):
        missing_store.validate()

    tampered_root = tmp_path / "tampered"
    tampered_store = CorpusStore(tampered_root)
    tampered = _add(tampered_store, payload={"value": 1}, text="one")
    Path(tampered.snapshot_path).write_text(json.dumps({"value": 2}) + "\n")

    with pytest.raises(CorpusIntegrityError, match="SHA-256 mismatch"):
        tampered_store.validate()


def test_export_source_index_excludes_native(tmp_path) -> None:
    store = CorpusStore(tmp_path)
    _add(store, payload={"n": 1}, text="native ct.gov", family="clinicaltrials_gov", native=True)
    _add(store, payload={"s": 1}, text="sec disclosure", family="sec_edgar")
    index = store.export_source_index(tmp_path / "source_index.yaml")
    assert "clinicaltrials_gov" not in index
    assert "sec_edgar" in index
    assert index["sec_edgar"][0]["text"] == "sec disclosure"
