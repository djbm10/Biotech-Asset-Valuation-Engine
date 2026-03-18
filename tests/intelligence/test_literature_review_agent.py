from __future__ import annotations

from datetime import datetime, timezone

from bve.intelligence.extraction.raw_document import EntityHints, RawDocument
from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace
from bve.intelligence.literature_review_agent import (
    DocumentTopicGrouper,
    LiteratureReviewAgent,
    LiteratureTopic,
)

_NOW = datetime(2026, 3, 9, 15, 0, tzinfo=timezone.utc)


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
) -> None:
    raw_document = RawDocument.from_text(
        id=doc_id,
        source="pubmed",
        source_url=f"https://pubmed.ncbi.nlm.nih.gov/{doc_id}",
        title=title,
        raw_text=text,
        retrieved_at=_NOW,
        entity_hints=EntityHints(
            asset_id=asset_id,
            company_id=company_id,
            drug_name="ABC-101",
            indication="NSCLC",
        ),
    )
    store.add_raw_document(raw_document, _trace(f"raw:{doc_id}"))


def test_topic_grouping_clusters_documents_by_keyword_hits():
    grouper = DocumentTopicGrouper()
    grouped = grouper.group(
        [
            {
                "id": "doc-efficacy",
                "text": "Phase 2 efficacy was strong with improved response rate and OS benefit.",
            },
            {
                "id": "doc-safety",
                "text": "Safety profile showed low grade 3 adverse event burden and good tolerability.",
            },
            {
                "id": "doc-mech",
                "text": "The inhibitor mechanism targets EGFR signaling pathway in tumor cells.",
            },
        ]
    )

    assert [d.doc_id for d in grouped[LiteratureTopic.EFFICACY]] == ["doc-efficacy"]
    assert [d.doc_id for d in grouped[LiteratureTopic.SAFETY]] == ["doc-safety"]
    assert [d.doc_id for d in grouped[LiteratureTopic.MECHANISM]] == ["doc-mech"]


def test_literature_review_agent_generates_required_fields(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        _add_raw_document(
            store,
            doc_id="1",
            asset_id="asset-a",
            company_id="company-a",
            title="Efficacy readout",
            text=(
                "Primary endpoint met in phase 2. Efficacy and response rate improved over control."
            ),
        )
        _add_raw_document(
            store,
            doc_id="2",
            asset_id="asset-a",
            company_id="company-a",
            title="Mechanism paper",
            text=(
                "The target pathway mechanism confirms selective inhibitor activity with biomarker expression."
            ),
        )
        _add_raw_document(
            store,
            doc_id="3",
            asset_id="asset-a",
            company_id="company-a",
            title="Outcomes update",
            text=(
                "Interim analysis readout: primary endpoint met and secondary endpoint trend favorable."
            ),
        )

        review = LiteratureReviewAgent().generate(
            store,
            asset_id="asset-a",
            company_id="company-a",
            generated_at=_NOW,
        )

        assert review.efficacy_summary
        assert review.safety_summary.startswith("No safety evidence identified")
        assert review.mechanism_summary
        assert review.trial_outcomes_summary
        assert any("safety: no supporting documents." == gap for gap in review.knowledge_gaps)
        assert review.cited_raw_document_ids == ["1", "2", "3"]
        efficacy_section = next(s for s in review.sections if s.topic == LiteratureTopic.EFFICACY)
        mechanism_section = next(s for s in review.sections if s.topic == LiteratureTopic.MECHANISM)
        assert efficacy_section.supporting_pmids == ["1"]
        assert mechanism_section.supporting_pmids == ["2"]
    finally:
        store.close()


def test_knowledge_store_persists_literature_reviews(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        _add_raw_document(
            store,
            doc_id="doc-persist",
            asset_id="asset-x",
            company_id="company-x",
            title="Safety abstract",
            text="Safety profile was acceptable with low serious adverse event rates.",
        )
        review = LiteratureReviewAgent().generate(
            store,
            asset_id="asset-x",
            company_id="company-x",
            generated_at=_NOW,
        )
        record = store.add_literature_review(
            review,
            source_trace=_trace("lit-review"),
        )
        loaded = store.get_literature_reviews(asset_id="asset-x")

        assert record.id == review.review_id
        assert len(loaded) == 1
        assert loaded[0]["review_id"] == review.review_id

        traced = store.get_record_with_trace("literature_reviews", review.review_id)
        assert traced.record_id == review.review_id
        assert traced.provenance_chain["raw_document"] is not None
    finally:
        store.close()


def test_literature_review_cli_hook_persists(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "knowledge.db"
    store = KnowledgeStore(db_path)
    try:
        _add_raw_document(
            store,
            doc_id="doc-cli",
            asset_id="asset-cli",
            company_id="company-cli",
            title="Biomarker publication",
            text="Biomarker subgroup demonstrated response rate enrichment.",
        )
    finally:
        store.close()

    from bve.cli.literature_review import main

    monkeypatch.setattr(
        "sys.argv",
        [
            "bve-literature-review",
            "--db",
            str(db_path),
            "--asset-id",
            "asset-cli",
            "--company-id",
            "company-cli",
            "--persist",
            "--json",
        ],
    )
    main()
    captured = capsys.readouterr()
    assert '"asset_id": "asset-cli"' in captured.out

    verify_store = KnowledgeStore(db_path)
    try:
        reviews = verify_store.get_literature_reviews(asset_id="asset-cli")
        assert len(reviews) == 1
        assert reviews[0]["asset_id"] == "asset-cli"
    finally:
        verify_store.close()
