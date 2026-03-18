from __future__ import annotations

from datetime import datetime, timedelta, timezone

from bve.intelligence.extraction.raw_document import EntityHints, RawDocument
from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace


def _trace(ref: str) -> SourceTrace:
    return SourceTrace(source_type="unit_test", source_ref=ref)


def _doc(*, doc_id: str, asset_id: str, retrieved_at: datetime) -> RawDocument:
    return RawDocument.from_text(
        id=doc_id,
        source="press_release",
        title=f"{asset_id} update",
        raw_text=f"payload-{doc_id}",
        source_url=f"https://example.org/{doc_id}",
        published_at=retrieved_at,
        retrieved_at=retrieved_at,
        entity_hints=EntityHints(asset_id=asset_id, company_id=f"co-{asset_id}"),
    )


def test_retention_policy_prunes_old_raw_documents_without_losing_hash_dedupe() -> None:
    store = KnowledgeStore(":memory:")
    try:
        reference_time = datetime(2026, 3, 11, 12, 0, tzinfo=timezone.utc)
        old_doc = _doc(
            doc_id="doc-old",
            asset_id="asset-a",
            retrieved_at=reference_time - timedelta(days=120),
        )
        recent_doc = _doc(
            doc_id="doc-new",
            asset_id="asset-a",
            retrieved_at=reference_time - timedelta(days=5),
        )
        store.add_raw_document(old_doc, _trace("doc-old"))
        store.add_raw_document(recent_doc, _trace("doc-new"))
        store.add_extraction_result(
            {
                "id": "extract-old",
                "created_at": (reference_time - timedelta(days=119)).isoformat(),
            },
            _trace("extract-old"),
            raw_document_id=old_doc.id,
        )

        assert store.processed_document_hash_exists(
            source=old_doc.source,
            document_hash=old_doc.document_hash,
        )

        result = store.apply_retention_policy(
            raw_documents_days=90,
            reference_time=reference_time,
        )

        remaining_ids = {row.id for row in store.get_raw_documents(limit=10)}
        assert result.raw_documents_deleted == 1
        assert old_doc.id not in remaining_ids
        assert recent_doc.id in remaining_ids
        assert result.structured_signals_deleted == 0
        assert store.processed_document_hash_exists(
            source=old_doc.source,
            document_hash=old_doc.document_hash,
        )
    finally:
        store.close()
