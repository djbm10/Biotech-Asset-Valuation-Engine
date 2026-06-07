from __future__ import annotations

from datetime import datetime, timezone

from bve.intelligence.catalyst_payoff_trees import (
    CatalystPayoffModuleOutput,
    CatalystPayoffTreeAssessment,
)
from bve.intelligence.portfolio_decision_engine import (
    PortfolioContextSnapshot,
    PortfolioDecisionEngine,
    PortfolioDecisionPolicy,
    PortfolioDecisionValue,
)


def _payoff_tree() -> CatalystPayoffTreeAssessment:
    return CatalystPayoffTreeAssessment(
        asset_id="asset-rly2608",
        output=CatalystPayoffModuleOutput(
            value={
                "asset_id": "asset-rly2608",
                "event_type": "trial_readout",
                "scenarios": [
                    {
                        "name": "clear_win",
                        "probability": 0.30,
                        "price_move_pct": 35.0,
                        "post_event_financing_state": "funded",
                        "post_event_valuation_regime": "premium",
                        "thesis_status": "confirmed",
                        "next_catalyst": "launch prep",
                    },
                    {
                        "name": "mixed_but_fundable",
                        "probability": 0.15,
                        "price_move_pct": 12.0,
                        "post_event_financing_state": "funded",
                        "post_event_valuation_regime": "base_plus",
                        "thesis_status": "partially_confirmed",
                        "next_catalyst": "follow-up dataset",
                    },
                    {
                        "name": "delay",
                        "probability": 0.10,
                        "price_move_pct": -8.0,
                        "post_event_financing_state": "watch_runway",
                        "post_event_valuation_regime": "time_shifted",
                        "thesis_status": "delayed",
                        "next_catalyst": "updated date",
                    },
                    {
                        "name": "narrow_label",
                        "probability": 0.10,
                        "price_move_pct": 4.0,
                        "post_event_financing_state": "watch_dilution",
                        "post_event_valuation_regime": "narrow_label",
                        "thesis_status": "partially_confirmed",
                        "next_catalyst": "commercial execution",
                    },
                    {
                        "name": "fail",
                        "probability": 0.18,
                        "price_move_pct": -28.0,
                        "post_event_financing_state": "distressed",
                        "post_event_valuation_regime": "bear",
                        "thesis_status": "broken",
                        "next_catalyst": "program triage",
                    },
                    {
                        "name": "crl",
                        "probability": 0.07,
                        "price_move_pct": -20.0,
                        "post_event_financing_state": "bridge_financing_likely",
                        "post_event_valuation_regime": "regulatory_reset",
                        "thesis_status": "broken",
                        "next_catalyst": "resubmission",
                    },
                    {
                        "name": "safety_overhang",
                        "probability": 0.05,
                        "price_move_pct": -12.0,
                        "post_event_financing_state": "higher_cash_burn",
                        "post_event_valuation_regime": "risk_reset",
                        "thesis_status": "challenged",
                        "next_catalyst": "safety follow-up",
                    },
                    {
                        "name": "competitive_overshadowing",
                        "probability": 0.05,
                        "price_move_pct": -6.0,
                        "post_event_financing_state": "unchanged",
                        "post_event_valuation_regime": "crowded",
                        "thesis_status": "unchanged",
                        "next_catalyst": "relative update",
                    },
                ],
                "expected_return_pct": 5.8,
                "downside_skew": 0.42,
                "sharpe_like_setup_score": 0.18,
                "recommended_pre_event_size_pct": 0.06,
                "recommended_post_event_action_logic": "Add on win, cut on fail.",
            },
            confidence=0.88,
            provenance=["catalyst_model", "market_expectations", "financing_engine"],
            freshness=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
            explainability="Catalyst payoff tree.",
            downstream_dependencies=["portfolio_decision_engine"],
        ),
        plain_english_summary="Positive skew with manageable tail risk.",
    )


def test_phase_l_builds_portfolio_aware_target_size() -> None:
    assessment = PortfolioDecisionEngine().build(
        asset_id="asset-rly2608",
        ticker="RLAY",
        payoff_tree=_payoff_tree(),
        portfolio_context=PortfolioContextSnapshot(
            portfolio_snapshot_id="snap-1",
            snapshot_at=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
            current_gross_exposure_pct=0.68,
            current_net_exposure_pct=0.52,
            therapeutic_area_exposure_pct=0.18,
            modality_exposure_pct=0.10,
            catalyst_cluster_exposure_pct=0.08,
            factor_sensitivity_score=0.20,
            liquidity_score=0.85,
            outcome_correlation_score=0.25,
            crowding_score=0.22,
            gross_risk_budget_pct=1.0,
            net_risk_budget_pct=0.80,
            current_position_pct=0.01,
        ),
    )
    value = PortfolioDecisionValue.model_validate(assessment.output.value)

    assert value.target_position_pct > 0.02
    assert value.add_reduce_pct > 0.0
    assert value.recommended_action == "add"
    assert value.event_cap_pct <= 0.07
    assert value.watchlist_priority_score > 0.5
    assert value.scenario_weighted_exposure_pct > 0.0
    assert "portfolio_snapshot:snap-1" in assessment.output.provenance
    assert "continuous_monitoring" in assessment.output.downstream_dependencies


def test_phase_l_reduces_target_when_portfolio_is_crowded_and_illiquid() -> None:
    assessment = PortfolioDecisionEngine().build(
        asset_id="asset-rly2608",
        ticker="RLAY",
        payoff_tree=_payoff_tree(),
        portfolio_context=PortfolioContextSnapshot(
            portfolio_snapshot_id="snap-2",
            snapshot_at=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
            current_gross_exposure_pct=0.98,
            current_net_exposure_pct=0.90,
            therapeutic_area_exposure_pct=0.32,
            modality_exposure_pct=0.31,
            catalyst_cluster_exposure_pct=0.28,
            factor_sensitivity_score=0.55,
            liquidity_score=0.18,
            outcome_correlation_score=0.84,
            crowding_score=0.88,
            gross_risk_budget_pct=1.0,
            net_risk_budget_pct=0.95,
            current_position_pct=0.05,
        ),
        policy=PortfolioDecisionPolicy(
            max_single_position_pct=0.10,
            max_event_position_pct=0.07,
            max_loss_budget_pct=0.02,
        ),
    )
    value = PortfolioDecisionValue.model_validate(assessment.output.value)

    assert value.target_position_pct < 0.05
    assert value.add_reduce_pct < 0.0
    assert value.recommended_action == "reduce"
    assert value.concentration_penalty > 0.0
    assert value.liquidity_penalty > 0.0
    assert value.correlation_penalty > 0.0
    assert value.crowding_penalty > 0.0
    assert "liquidity cap applied" in value.rationale_flags
    assert "event cap tightened by portfolio context" in value.rationale_flags
