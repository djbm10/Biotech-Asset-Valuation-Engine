from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from bve.intelligence.extraction.raw_document import EntityHints, RawDocument
from bve.intelligence.knowledge_graph import EdgeType, KGEdge, KGNode, NodeType
from bve.intelligence.knowledge_layer import (
    DossierRecord,
    KnowledgeStore,
    SourceTrace,
    StoredValuationDiff,
)
from bve.intelligence.research_report import ResearchReportGenerator
from bve.intelligence.schemas.signals import Event
from bve.intelligence.taxonomy import EventType

_NOW = datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc)


def _trace(ref: str) -> SourceTrace:
    return SourceTrace(source_type="unit_test", source_ref=ref, ingested_at=_NOW)


def _seed_store(store: KnowledgeStore, *, asset_id: str, company_id: str) -> None:
    asset = KGNode(
        node_type=NodeType.ASSET,
        name="Seed Asset",
        external_id=asset_id,
        properties={
            "moa_summary": {
                "target_class": "EGFR",
                "novelty_score": 0.62,
                "moa_confidence": 0.7,
            }
        },
    )
    competitor = KGNode(
        node_type=NodeType.COMPETITOR_PROGRAM,
        name="Comp Seed",
        external_id="NCT123",
        properties={
            "company": "CompCo",
            "phase": "PHASE3",
            "status": "RECRUITING",
            "mechanism": "EGFR inhibitor",
            "primary_completion_date": "2026-11-01",
        },
    )
    store.add_node(asset)
    store.add_node(competitor)
    store.add_edge(
        KGEdge(
            source_node_id=asset.node_id,
            target_node_id=competitor.node_id,
            edge_type=EdgeType.COMPETES_WITH,
        )
    )

    raw_document = RawDocument.from_text(
        id="12345",
        source="pubmed",
        source_url="https://pubmed.ncbi.nlm.nih.gov/12345/",
        title="Efficacy and safety in phase 3",
        raw_text=(
            "Primary endpoint met with improved response rate. "
            "Safety profile remained manageable."
        ),
        retrieved_at=_NOW,
        entity_hints=EntityHints(
            asset_id=asset_id,
            company_id=company_id,
            drug_name="SeedDrug",
            indication="NSCLC",
        ),
    )
    store.add_raw_document(raw_document, _trace("raw"))

    event = Event(
        id="evt-1",
        event_type=EventType.TRIAL_READOUT,
        asset_id=asset_id,
        company_id=company_id,
        observed_at=_NOW,
        ingested_at=_NOW,
        source_type="publication",
        source_url=raw_document.source_url,
        headline="trial readout",
        confidence=0.9,
    )
    diff = StoredValuationDiff(
        run_id="run-1",
        event_id=event.id,
        asset_id=asset_id,
        valuation_before={"rnpv_millions": 100.0, "nav_per_share": 4.0},
        valuation_after={"rnpv_millions": 130.0, "nav_per_share": 4.3},
        delta_npv=30.0,
        created_at=_NOW,
        assumptions_changed=[
            {"field": "trials[*].success_probability", "old_value": 0.5, "new_value": 0.6}
        ],
    )
    dossier = DossierRecord(
        id="dossier-1",
        company_id=company_id,
        asset_id=asset_id,
        generated_at=_NOW,
        recent_events=[event],
        current_assumptions={"trials[*].success_probability": 0.6},
        latest_valuation_snapshot={"rnpv_millions": 130.0, "nav_per_share": 4.3},
        recent_changes=[diff],
        open_questions=["Need durability update"],
        source_trace=_trace("dossier"),
    )
    store.add_dossier(dossier)
    store.write_company_sotp_snapshots(
        [
            SimpleNamespace(
                ticker="SEED",
                company_id=company_id,
                company_name="Seed Company",
                snapshot_date=date(2026, 3, 10),
                rank=1,
                market_cap_millions=420.0,
                enterprise_value_millions=350.0,
                sotp_equity_value_millions=560.0,
                sotp_per_share=5.6,
                sotp_discount=1.333333,
                ranked_sotp_discount=1.30,
                modeled_asset_coverage_pct=0.84,
                asset_count_modeled=1,
                modeled_asset_ids=[asset_id],
                config_quality_summary="curated",
                modeled_asset_confidence_min=0.85,
                modeled_asset_confidence_avg=0.90,
                action_policy="watch",
                action_reason="ranked_discount_above_watch_threshold:1.30x",
                market_cap_source="unit_test",
                balance_sheet_source="sec_edgar_company_facts",
                balance_sheet_source_ref="unit-test",
                balance_sheet_snapshot_date=date(2026, 2, 28),
                balance_sheet_period_end_date=date(2025, 12, 31),
                balance_sheet_form_type="10-K",
                balance_sheet_is_point_in_time=True,
                balance_sheet_age_days=11,
                balance_sheet_passes_recency_gate=True,
                balance_sheet_recency_penalty=1.0,
                buckets=[],
                limitations=[],
                notes=None,
            )
        ]
    )


def test_research_report_assemble_then_render(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        _seed_store(store, asset_id="asset-r", company_id="company-r")
        generator = ResearchReportGenerator()
        context = generator.assemble_context(
            store,
            asset_id="asset-r",
            company_id="company-r",
            generated_at=_NOW,
        )
        rendered = generator.render(context)

        assert context.report_version == "v1.2"
        assert context.model_version == "deterministic-research-report-1.2"
        assert set(context.input_snapshot.keys()) == {
            "captured_at",
            "valuation_parameters",
            "event_scores",
            "propagation_parameters",
            "company_sotp_snapshot",
        }
        assert context.company_sotp_snapshot is not None
        assert context.competitive_entries
        assert "## Executive Summary" in rendered
        assert "## Competitive Analysis" in rendered
        assert "Distance to Market" in rendered
        assert "Report Version:" in rendered
        assert "mechanism_similarity" in rendered
        assert "Company SOTP Snapshot" in rendered
    finally:
        store.close()


def test_research_report_persistence_round_trip(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        _seed_store(store, asset_id="asset-r", company_id="company-r")
        report = ResearchReportGenerator().generate(
            store,
            asset_id="asset-r",
            company_id="company-r",
            generated_at=_NOW,
            persist=True,
            source_trace=_trace("report"),
        )
        rows = store.get_research_reports(asset_id="asset-r")
        assert len(rows) == 1
        assert rows[0]["report_id"] == report.report_id
        assert rows[0]["report_version"] == "v1.2"
        assert "input_snapshot" in rows[0]

        stored_row = store._conn.execute(
            "SELECT report_version, model_version FROM research_reports WHERE id = ?",
            (report.report_id,),
        ).fetchone()
        assert stored_row is not None
        assert stored_row["report_version"] == "v1.2"
        assert stored_row["model_version"] == "deterministic-research-report-1.2"

        traced = store.get_record_with_trace("research_reports", report.report_id)
        assert traced.record_id == report.report_id
        assert traced.provenance_chain["raw_document"] is not None
    finally:
        store.close()


def test_research_report_cli_hook_persists(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "knowledge.db"
    seed_store = KnowledgeStore(db_path)
    try:
        _seed_store(seed_store, asset_id="asset-cli", company_id="company-cli")
    finally:
        seed_store.close()

    from bve.cli.research_report import main

    monkeypatch.setattr(
        "sys.argv",
        [
            "bve-research-report",
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
    assert '"report_version": "v1.2"' in captured.out

    verify_store = KnowledgeStore(db_path)
    try:
        reports = verify_store.get_research_reports(asset_id="asset-cli")
        assert len(reports) == 1
        assert reports[0]["asset_id"] == "asset-cli"
        assert reports[0]["model_version"] == "deterministic-research-report-1.2"
    finally:
        verify_store.close()
