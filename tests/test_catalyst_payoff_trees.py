from __future__ import annotations

from datetime import datetime, timezone

from bve.intelligence.catalyst_payoff_trees import (
    CatalystPayoffTreeEngine,
    CatalystPayoffTreeValue,
)
from bve.intelligence.financing_engine import BurnPath, FinancingAssessment, FinancingModuleOutput
from bve.intelligence.market_expectations import (
    MarketExpectationComparison,
    MarketExpectationModuleOutput,
)
from bve.intelligence.variant_view_engine import (
    ThesisCard,
    VariantDelta,
    VariantViewAssessment,
    VariantViewModuleOutput,
)
from bve.models.catalyst_model import CatalystValuation


def _catalyst_valuation() -> CatalystValuation:
    return CatalystValuation(
        event_key="cat-rly2608-ph3",
        asset_id="asset-rly2608",
        event_type="trial_readout",
        p_positive_outcome=0.58,
        design_adjusted_p_positive_outcome=0.64,
        design_quality_multiplier=1.1,
        expected_return_pct=4.2,
        expected_move_magnitude_pct=26.0,
        current_price=4.0,
        expected_move_dollars=1.04,
        profile_source="calibrated",
    )


def _financing_assessment() -> FinancingAssessment:
    return FinancingAssessment(
        asset_id="asset-rly2608",
        company_id="company-rly",
        company_name="Relay",
        output=FinancingModuleOutput(
            value={
                "asset_id": "asset-rly2608",
                "company_id": "company-rly",
                "company_name": "Relay",
                "months_of_runway": 11.0,
                "burn_path": BurnPath(
                    base_quarterly_burn_millions=40.0,
                    bull_quarterly_burn_millions=34.0,
                    bear_quarterly_burn_millions=50.0,
                ).model_dump(),
                "capital_needed_to_next_catalyst_millions": 55.0,
                "capital_needed_to_approval_millions": 130.0,
                "likely_raise_timing_months": 7.0,
                "likely_raise_size_millions": 90.0,
                "expected_dilution_pct_low": 0.10,
                "expected_dilution_pct_base": 0.16,
                "expected_dilution_pct_high": 0.24,
                "probability_of_pre_catalyst_financing": 0.62,
                "financing_risk_score": 0.43,
                "financing_risk_tier": "medium",
                "balance_sheet_stress_score": 0.41,
                "partnership_alternative_value_millions": 45.0,
                "financing_adjusted_intrinsic_value_millions": 980.0,
                "financing_overhang_impact_pct": -0.14,
            },
            confidence=0.78,
            provenance=["10-Q:2026Q1", "financing_engine"],
            freshness=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
            explainability="Financing context.",
            downstream_dependencies=["probability_stack", "market_expectations"],
        ),
        plain_english_summary="Runway extends past the catalyst but financing remains relevant.",
    )


def _market_expectation() -> MarketExpectationComparison:
    return MarketExpectationComparison(
        asset_id="asset-rly2608",
        ticker="RLAY",
        output=MarketExpectationModuleOutput(
            value={
                "asset_id": "asset-rly2608",
                "ticker": "RLAY",
                "model_pos": 0.64,
                "implied_pos": 0.42,
                "pos_delta": 0.22,
                "model_peak_sales_millions": 1600.0,
                "implied_peak_sales_millions": 980.0,
                "peak_sales_delta_millions": 620.0,
                "model_dilution_pct": 0.16,
                "implied_dilution_pct": 0.10,
                "dilution_delta": 0.06,
                "financing_adjusted_intrinsic_value_millions": 980.0,
                "current_ev_millions": 520.0,
                "upside_downside_pct": 0.88,
                "consensus_valuation_range_low_millions": 450.0,
                "consensus_valuation_range_high_millions": 700.0,
                "optionality_not_reflected_millions": 180.0,
                "market_cap_millions": 700.0,
            },
            confidence=0.86,
            provenance=["market_snapshot:2026-04-18", "market_expectations"],
            freshness=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
            explainability="Market expectation comparison.",
            downstream_dependencies=["variant_view_engine", "catalyst_payoff_trees"],
        ),
        plain_english_summary="Market is underpricing the program.",
    )


def _variant_view() -> VariantViewAssessment:
    return VariantViewAssessment(
        asset_id="asset-rly2608",
        output=VariantViewModuleOutput(
            value={
                "asset_id": "asset-rly2608",
                "company_id": "company-rly",
                "thesis_card": ThesisCard(
                    headline="Market underwrites an average readout; model sees differentiated signal.",
                    market_is_pricing="PoS 42%, peak sales $980M.",
                    model_thinks="PoS 64%, peak sales $1.6B.",
                    gap_exists_because="Biomarker and design evidence look better than consensus assumes.",
                    catalysts_to_resolve=["Phase 3 readout", "FDA meeting"],
                ).model_dump(),
                "deltas": [
                    VariantDelta(
                        dimension="PoS",
                        consensus_assumption="Market-implied PoS 42%",
                        model_assumption="Model PoS 64%",
                        delta="+22.0%",
                        evidence_supporting_delta=["Biomarker enrichment remains intact."],
                        falsifier="A readout that misses the endpoint.",
                        expected_time_to_resolution_days=120,
                        confidence=0.82,
                    ).model_dump(),
                    VariantDelta(
                        dimension="Peak sales",
                        consensus_assumption="Market-implied peak sales $980M",
                        model_assumption="Model peak sales $1,600M",
                        delta="+$620M",
                        evidence_supporting_delta=["Access and uptake look better than priced."],
                        falsifier="Weak launch or pricing data.",
                        expected_time_to_resolution_days=180,
                        confidence=0.76,
                    ).model_dump(),
                    VariantDelta(
                        dimension="Financing",
                        consensus_assumption="Market-implied dilution 10%",
                        model_assumption="Model dilution 16%",
                        delta="+6.0%",
                        evidence_supporting_delta=["Runway does not fully clear approval."],
                        falsifier="A non-dilutive partnership.",
                        expected_time_to_resolution_days=90,
                        confidence=0.71,
                    ).model_dump(),
                ],
            },
            confidence=0.83,
            provenance=["market_expectations", "thesis_snapshot:asset-rly2608"],
            freshness=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
            explainability="Variant thesis context.",
            downstream_dependencies=["catalyst_payoff_trees", "portfolio_decision_engine"],
        ),
        plain_english_summary="Three structured deltas remain open.",
    )


def test_phase_k_builds_catalyst_payoff_tree_with_scenario_distribution() -> None:
    assessment = CatalystPayoffTreeEngine().build(
        asset_id="asset-rly2608",
        catalyst_valuation=_catalyst_valuation(),
        financing_assessment=_financing_assessment(),
        market_expectation=_market_expectation(),
        variant_view=_variant_view(),
        freshness=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )

    value = CatalystPayoffTreeValue.model_validate(assessment.output.value)
    assert value.event_type == "trial_readout"
    assert len(value.scenarios) == 8
    assert round(sum(item.probability for item in value.scenarios), 4) == 1.0
    assert any(item.name == "clear_win" and item.price_move_pct > 0 for item in value.scenarios)
    assert any(item.name == "fail" and item.price_move_pct < 0 for item in value.scenarios)
    assert value.expected_return_pct > 0.0
    assert 0.0 <= value.downside_skew <= 1.0
    assert value.recommended_pre_event_size_pct > 0.0
    assert "Cut immediately on a fail or CRL outcome." in value.recommended_post_event_action_logic
    assert "top delta: PoS" in value.recommended_post_event_action_logic
    assert assessment.output.confidence == 0.9
    assert "portfolio_decision_engine" in assessment.output.downstream_dependencies
    assert "10-Q:2026Q1" in assessment.output.provenance


def test_phase_k_handles_missing_optional_context() -> None:
    assessment = CatalystPayoffTreeEngine().build(
        asset_id="asset-rly2608",
        catalyst_valuation=_catalyst_valuation().model_copy(
            update={
                "profile_source": "default",
                "design_adjusted_p_positive_outcome": 0.48,
                "expected_move_magnitude_pct": 18.0,
            }
        ),
        financing_assessment=None,
        market_expectation=None,
        variant_view=None,
        freshness=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )

    value = CatalystPayoffTreeValue.model_validate(assessment.output.value)
    assert len(value.scenarios) == 8
    assert assessment.output.confidence == 0.55
    assert value.recommended_pre_event_size_pct >= 0.0
    assert assessment.plain_english_summary
