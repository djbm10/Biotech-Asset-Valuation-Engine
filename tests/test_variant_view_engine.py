from __future__ import annotations

from datetime import date, datetime, timezone

from bve.intelligence.market_expectations import MarketExpectationEngine
from bve.intelligence.thesis_tracker import ClaimType, ThesisTracker
from bve.intelligence.variant_view_engine import VariantViewEngine, VariantViewValue
from bve.intelligence.knowledge_layer import KnowledgeStore


def _market_expectation():
    return MarketExpectationEngine().build_comparison(
        asset_id="asset-rly2608",
        ticker="RLAY",
        model_pos=0.60,
        model_peak_sales_millions=1400.0,
        market_cap_millions=650.0,
        cash_estimate_millions=150.0,
        financing_adjusted_intrinsic_value_millions=1200.0,
        model_dilution_pct=0.18,
        implied_dilution_pct=0.09,
        consensus_valuation_range_low_millions=500.0,
        consensus_valuation_range_high_millions=900.0,
        patent_life_years=10,
        discount_rate=0.0,
        margin_rate=0.40,
        freshness=datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc),
    )


def test_phase_j_builds_machine_readable_variant_view() -> None:
    store = KnowledgeStore(db_path=":memory:")
    try:
        tracker = ThesisTracker(store)
        confirmed = tracker.add_claim(
            asset_id="asset-rly2608",
            company_id="company-rly",
            claim_type=ClaimType.ENDPOINT_MET,
            assertion="The pivotal readout should meet the primary endpoint.",
        )
        tracker.resolve_claim(
            confirmed.claim_id,
            "confirmed",
            evidence="Phase 2 signal and biomarker selection remain supportive.",
        )
        open_claim = tracker.add_claim(
            asset_id="asset-rly2608",
            company_id="company-rly",
            claim_type=ClaimType.LABEL_EXPANSION,
            assertion="Label breadth should exceed what the market is pricing.",
            resolution_date=date(2026, 9, 1),
        )
        snapshot = tracker.snapshot("asset-rly2608")

        assessment = VariantViewEngine().build(
            asset_id="asset-rly2608",
            company_id="company-rly",
            market_expectation=_market_expectation(),
            thesis_snapshot=snapshot,
            catalyst_calendar=[
                {"date": "2026-08-15", "description": "Phase 3 readout"},
                {"date": "2026-11-20", "description": "FDA meeting"},
            ],
            now=datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc),
        )

        value = VariantViewValue.model_validate(assessment.output.value)
        assert value.thesis_card.market_is_pricing
        assert value.thesis_card.model_thinks
        assert value.thesis_card.gap_exists_because
        assert len(value.deltas) >= 2
        assert any(delta.dimension == "PoS" for delta in value.deltas)
        pos_delta = next(delta for delta in value.deltas if delta.dimension == "PoS")
        assert "Market-implied PoS" in pos_delta.consensus_assumption
        assert "Model PoS" in pos_delta.model_assumption
        assert pos_delta.evidence_supporting_delta
        assert pos_delta.expected_time_to_resolution_days == 120
        assert open_claim.assertion in pos_delta.falsifier
        assert "thesis_snapshot:asset-rly2608" in assessment.output.provenance
    finally:
        store.close()


def test_phase_j_handles_missing_thesis_snapshot() -> None:
    assessment = VariantViewEngine().build(
        asset_id="asset-rly2608",
        company_id="company-rly",
        market_expectation=_market_expectation(),
        thesis_snapshot=None,
        catalyst_calendar=[],
        now=datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc),
    )
    value = VariantViewValue.model_validate(assessment.output.value)
    assert value.deltas
    assert assessment.output.confidence >= 0.6
    assert value.thesis_card.gap_exists_because
