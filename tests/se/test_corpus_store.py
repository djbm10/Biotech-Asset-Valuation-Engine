from __future__ import annotations

from datetime import date

from bve.se.acquisition.corpus_store import CorpusStore, IndexStatus, ParserStatus
from bve.se.schemas.contracts import SourceTier

AS_OF = date(2026, 7, 10)


def _add(store: CorpusStore, *, payload, text: str, family: str = "pubmed", native: bool = False):
    return store.add(
        source_family=family,
        source_url="https://example.test/doc",
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


def test_export_source_index_excludes_native(tmp_path) -> None:
    store = CorpusStore(tmp_path)
    _add(store, payload={"n": 1}, text="native ct.gov", family="clinicaltrials_gov", native=True)
    _add(store, payload={"s": 1}, text="sec disclosure", family="sec_edgar")
    index = store.export_source_index(tmp_path / "source_index.yaml")
    assert "clinicaltrials_gov" not in index
    assert "sec_edgar" in index
    assert index["sec_edgar"][0]["text"] == "sec disclosure"
