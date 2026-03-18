from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from bve.intelligence.extraction.raw_document import EntityHints, RawDocument
from bve.intelligence.knowledge_graph import NodeType
from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace
from bve.intelligence.moa_summary_agent import MechanismOfActionSummaryAgent
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import EventType

_NOW = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store() -> KnowledgeStore:
    ks = KnowledgeStore(db_path=":memory:")
    yield ks
    ks.close()


def _trace(ref: str) -> SourceTrace:
    return SourceTrace(source_type="unit_test", source_ref=ref, ingested_at=_NOW)


def _add_raw_document(
    store: KnowledgeStore,
    *,
    doc_id: str,
    asset_id: str,
    company_id: str,
    title: str,
    text: str,
    retrieved_at: datetime,
) -> None:
    doc = RawDocument.from_text(
        id=doc_id,
        source="publication",
        source_url=f"https://example.org/{doc_id}",
        title=title,
        raw_text=text,
        retrieved_at=retrieved_at,
        entity_hints=EntityHints(
            asset_id=asset_id,
            company_id=company_id,
            drug_name="TEST",
            indication="oncology",
        ),
    )
    store.add_raw_document(doc, _trace(f"raw:{doc_id}"))


def _add_signal(
    store: KnowledgeStore,
    *,
    signal_id: str,
    event_id: str,
    asset_id: str,
    company_id: str,
) -> None:
    signal = StructuredSignal(
        id=signal_id,
        event_id=event_id,
        asset_id=asset_id,
        company_id=company_id,
        event_type=EventType.TRIAL_READOUT,
        signal_date=date(2026, 3, 9),
        extraction_confidence=0.91,
        extraction_model="unit-test",
        created_at=_NOW,
    )
    store.add_structured_signal(
        signal,
        _trace(f"signal:{signal_id}"),
        extraction_result_id=f"x-{signal_id}",
    )


def test_moa_summary_extracts_target_and_mechanism(store: KnowledgeStore):
    _add_raw_document(
        store,
        doc_id="doc-1",
        asset_id="asset-a",
        company_id="company-a",
        title="Selective BTK inhibitor update",
        text=(
            "ABC-101 is a selective BTK inhibitor with improved tolerability versus "
            "first-generation therapies."
        ),
        retrieved_at=_NOW - timedelta(days=2),
    )
    _add_raw_document(
        store,
        doc_id="doc-2",
        asset_id="asset-a",
        company_id="company-a",
        title="Program differentiation",
        text=(
            "Management described the candidate as first-in-class and highly "
            "differentiated in potency versus peers."
        ),
        retrieved_at=_NOW - timedelta(days=1),
    )
    _add_signal(
        store,
        signal_id="sig-1",
        event_id="evt-1",
        asset_id="asset-a",
        company_id="company-a",
    )

    summary = MechanismOfActionSummaryAgent().summarize(
        store,
        asset_id="asset-a",
        company_id="company-a",
        generated_at=_NOW,
    )

    assert summary.target_class == "BTK"
    assert "inhibitor" in summary.mechanism_description.lower()
    assert "BTK" in summary.mechanism_description
    assert summary.novelty_score > 0.5
    assert summary.moa_confidence == pytest.approx(0.477, abs=1e-3)
    assert summary.competitive_differentiation.startswith("Differentiation cues:")
    assert summary.cited_raw_document_ids == ["doc-1", "doc-2"]
    assert summary.cited_signal_ids == ["sig-1"]

    node = store.find_node_by_external_id(NodeType.ASSET, "asset-a")
    assert node is not None
    assert node.properties["moa_summary"]["target_class"] == "BTK"
    assert node.properties["moa_summary"]["moa_confidence"] == summary.moa_confidence


def test_moa_summary_novelty_penalized_when_target_is_common(store: KnowledgeStore):
    _add_raw_document(
        store,
        doc_id="doc-main",
        asset_id="asset-main",
        company_id="company-main",
        title="EGFR inhibitor program",
        text="This program is an EGFR inhibitor for NSCLC.",
        retrieved_at=_NOW,
    )

    for idx in range(5):
        _add_raw_document(
            store,
            doc_id=f"doc-other-{idx}",
            asset_id=f"asset-other-{idx}",
            company_id=f"company-other-{idx}",
            title="Comparable EGFR program",
            text="Peer pipeline update on an EGFR inhibitor candidate.",
            retrieved_at=_NOW + timedelta(minutes=idx),
        )

    summary = MechanismOfActionSummaryAgent().summarize(
        store,
        asset_id="asset-main",
        company_id="company-main",
        generated_at=_NOW,
    )

    assert summary.target_class == "EGFR"
    assert summary.novelty_score <= 0.45
    assert summary.moa_confidence == pytest.approx(0.301, abs=1e-3)


def test_moa_summary_deterministic_with_no_documents(store: KnowledgeStore):
    agent = MechanismOfActionSummaryAgent()
    summary_a = agent.summarize(
        store,
        asset_id="asset-missing",
        company_id="company-missing",
        generated_at=_NOW,
    )
    summary_b = agent.summarize(
        store,
        asset_id="asset-missing",
        company_id="company-missing",
        generated_at=_NOW,
    )

    assert summary_a == summary_b
    assert summary_a.target_class == "undetermined"
    assert summary_a.novelty_score == 0.50
    assert summary_a.moa_confidence == 0.0
    assert summary_a.cited_raw_document_ids == []
