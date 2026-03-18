from __future__ import annotations

from datetime import datetime, timezone

from bve.intelligence.investment_memo_agent import InvestmentMemoAgent
from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace, StoredValuationDiff
from bve.intelligence.schemas.signals import Event
from bve.intelligence.taxonomy import EventType


def _seed(store: KnowledgeStore) -> None:
    t0 = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    trace = SourceTrace(source_type="test", source_ref="seed")
    event = Event(
        id="evt-1",
        event_type=EventType.TRIAL_READOUT,
        asset_id="asset-1",
        company_id="company-1",
        observed_at=t0,
        ingested_at=t0,
        source_type="press_release",
        headline="Topline positive",
        confidence=0.9,
    )
    diff = StoredValuationDiff(
        run_id="run-1",
        event_id="evt-1",
        asset_id="asset-1",
        valuation_before={"rnpv_millions": 100.0, "nav_per_share": 4.0},
        valuation_after={"rnpv_millions": 120.0, "nav_per_share": 4.2},
        delta_npv=20.0,
        created_at=t0,
    )
    report_payload = {
        "report_id": "report-1",
        "asset_id": "asset-1",
        "company_id": "company-1",
        "generated_at": t0.isoformat(),
        "executive_summary": "Momentum improved after recent readout.",
        "investment_thesis": "Probability-weighted upside remains underpriced.",
        "risk_factors": "- Trial execution risk remains elevated.",
    }
    store.add_event(event, trace)
    store.add_valuation_diff(diff, company_id="company-1", source_trace=trace)
    store.add_research_report(
        report_payload,
        source_trace=trace,
        company_id="company-1",
        asset_id="asset-1",
    )


def test_investment_memo_agent_generates_markdown():
    store = KnowledgeStore(":memory:")
    _seed(store)
    memo = InvestmentMemoAgent().generate(
        store,
        asset_id="asset-1",
        company_id="company-1",
        persist=False,
    )
    assert memo.memo_version == "v1.0"
    assert memo.model_version.startswith("deterministic-investment-memo")
    assert "## Investment Thesis" in memo.rendered_markdown
    assert memo.cited_report_ids == ["report-1"]
    store.close()


def test_investment_memo_agent_persists_when_requested():
    store = KnowledgeStore(":memory:")
    _seed(store)
    memo = InvestmentMemoAgent().generate(
        store,
        asset_id="asset-1",
        company_id="company-1",
        persist=True,
    )
    memos = store.get_memos(company_id="company-1", asset_id="asset-1", limit=10)
    assert any(m.memo_type == "investment_memo" and m.id == memo.memo_id for m in memos)
    store.close()
