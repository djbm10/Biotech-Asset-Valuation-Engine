from __future__ import annotations

from datetime import datetime, timezone

from bve.intelligence.extraction.raw_document import EntityHints, RawDocument
from bve.intelligence.knowledge_layer import (
    KnowledgeStore,
    OpportunityAlertRecord,
    SourceTrace,
)


def _trace(ref: str) -> SourceTrace:
    return SourceTrace(source_type="test", source_ref=ref)


def test_run_state_round_trip():
    store = KnowledgeStore(":memory:")
    started = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    finished = datetime(2026, 3, 9, 12, 5, tzinfo=timezone.utc)

    store.mark_run_state_started(
        run_id="run-1",
        stage="extract",
        asset_id="asset-1",
        started_at=started,
        checkpoint_json={"document_id": "doc-1"},
    )
    store.mark_run_state_finished(
        run_id="run-1",
        stage="extract",
        asset_id="asset-1",
        status="success",
        started_at=started,
        finished_at=finished,
        checkpoint_json={"document_id": "doc-1", "event_id": "evt-1"},
    )

    rows = store.get_run_states(run_id="run-1", asset_id="asset-1")
    assert len(rows) == 1
    assert rows[0].status == "success"
    assert rows[0].checkpoint_json["event_id"] == "evt-1"
    store.close()


def test_raw_document_idempotency_by_source_and_hash():
    store = KnowledgeStore(":memory:")
    hints = EntityHints(asset_id="asset-1", company_id="company-1")
    doc_a = RawDocument.from_text(
        id="doc-a",
        source="press_release",
        title="Update A",
        raw_text="same normalized text",
        source_url="https://example.org/a",
        entity_hints=hints,
    )
    doc_b = RawDocument.from_text(
        id="doc-b",
        source="press_release",
        title="Update B",
        raw_text="same normalized text",
        source_url="https://example.org/b",
        entity_hints=hints,
    )

    store.add_raw_document(doc_a, _trace("a"))
    store.add_raw_document(doc_b, _trace("b"))
    docs = store.get_raw_documents(limit=10)
    assert len(docs) == 1
    store.close()


def test_opportunity_alert_idempotency_key():
    store = KnowledgeStore(":memory:")
    record = OpportunityAlertRecord(
        asset_id="asset-1",
        event_type="trial_readout",
        window="2026-03-09T00:00:00+00:00__2026-03-10T00:00:00+00:00",
        run_id="run-1",
        created_at=datetime(2026, 3, 9, tzinfo=timezone.utc),
        payload_json={"score": 0.9},
    )

    inserted_first = store.add_opportunity_alert(record)
    inserted_second = store.add_opportunity_alert(record)
    alerts = store.get_opportunity_alerts(asset_id="asset-1")

    assert inserted_first is True
    assert inserted_second is False
    assert len(alerts) == 1
    store.close()
