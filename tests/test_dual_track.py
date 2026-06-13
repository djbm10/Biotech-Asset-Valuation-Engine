"""Tests for the dual-track investment / BD-M&A verdict synthesis layer.

The synthesis layer must produce TWO independent verdicts plus an interpretive
cross-read — never a single blended score. These tests pin the four quadrants,
the divergence case (the "bad stock / good BD target" sophistication), and
graceful degradation when either side's inputs are missing.

Inputs are duck-typed (the production callers pass real ``ValuationOutput`` /
``MAProbabilityRow`` / ``BDMAOutput`` objects), so the fakes here are
``SimpleNamespace`` stand-ins carrying only the fields the builder reads.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from bve.analysis.dual_track import (
    BDVerdict,
    DualTrackAssessment,
    DualTrackThresholds,
    InvestmentVerdict,
    build_dual_track,
    dual_track_columns,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

def _valuation(
    *,
    implied_upside_pct: float | None,
    rnpv_millions: float = 500.0,
    asset_implied_ev_millions: float | None = 400.0,
    company_ev_millions: float = 900.0,
    mispricing_direction: str = "aligned",
    mispricing_magnitude: str = "moderate",
    confidence: float = 0.6,
    prob_positive: float = 0.7,
    has_price: bool = True,
) -> SimpleNamespace:
    """Build a ValuationOutput stand-in."""
    market_expectation = SimpleNamespace(
        mispricing_direction=mispricing_direction,
        mispricing_magnitude=mispricing_magnitude,
        confidence=confidence,
        pos_gap=0.05,
        implied_pos=0.40,
        implied_peak_sales_millions=800.0,
        current_ev_millions=company_ev_millions,
    )
    variant_perception = SimpleNamespace(
        company_ev_millions=company_ev_millions,
        base=SimpleNamespace(asset_implied_ev_millions=asset_implied_ev_millions),
        variant_perception_category="commercial",
        memo_interpretation="Market prices a conservative commercial ramp.",
    )
    return SimpleNamespace(
        implied_upside_pct=implied_upside_pct,
        rnpv=SimpleNamespace(rnpv_millions=rnpv_millions),
        nav_per_share=12.5,
        company=SimpleNamespace(
            current_price=10.0 if has_price else None,
            shares_outstanding_millions=100.0,
            net_cash_millions=200.0,
        ),
        market_expectation=market_expectation if has_price else None,
        variant_perception=variant_perception if has_price else None,
        monte_carlo=SimpleNamespace(probability_positive=prob_positive),
    )


def _ma_row(
    *,
    strategic_fit_score: float = 0.7,
    mna_probability_score: float = 0.65,
    best_acquirer_name: str = "Vertex",
    p_takeout_calibrated: float | None = 0.35,
    recommended_deal_structure: str | None = None,
    watchlist_type: str | None = "active",
    gap_urgency: str | None = "high",
    transaction_realism_label: str | None = "HIGH",
    days_to_catalyst: int | None = 30,
    matched_therapeutic_gap: str | None = "cystic fibrosis adjacency",
) -> SimpleNamespace:
    return SimpleNamespace(
        strategic_fit_score=strategic_fit_score,
        mna_probability_score=mna_probability_score,
        best_acquirer_name=best_acquirer_name,
        best_acquirer_fit_score=0.72,
        p_takeout_calibrated=p_takeout_calibrated,
        recommended_deal_structure=recommended_deal_structure,
        watchlist_type=watchlist_type,
        gap_urgency=gap_urgency,
        transaction_realism_label=transaction_realism_label,
        days_to_catalyst=days_to_catalyst,
        matched_therapeutic_gap=matched_therapeutic_gap,
        matched_priorities=["respiratory", "rare disease"],
        score_drivers=["clean IP", "motivated seller"],
        estimated_deal_value_low_millions=800.0,
        estimated_deal_value_high_millions=1200.0,
    )


def _bdma(
    *,
    bd_ma_score: float = 0.7,
    recommended_structure: str = "full_acquisition",
    recommended_action: str = "pursue",
    feasibility_score: float = 0.65,
    timing_score: float = 0.6,
) -> SimpleNamespace:
    return SimpleNamespace(
        bd_ma_score=bd_ma_score,
        best_acquirer_id="vrtx",
        recommended_structure=SimpleNamespace(value=recommended_structure),
        recommended_action=SimpleNamespace(value=recommended_action),
        primary_rationale=["Strong asset quality.", "High strategic fit."],
        main_risks=["Antitrust overlap in CF franchise."],
        component_scores={
            "deal_feasibility": SimpleNamespace(score=feasibility_score),
            "transaction_timing": SimpleNamespace(score=timing_score),
            "strategic_fit": SimpleNamespace(score=0.7),
        },
    )


# ---------------------------------------------------------------------------
# Quadrant tests
# ---------------------------------------------------------------------------

def test_undervalued_high_bd_is_dual_opportunity():
    res = build_dual_track(
        _valuation(implied_upside_pct=40.0, mispricing_direction="underpriced"),
        ma_row=_ma_row(strategic_fit_score=0.75),
    )
    assert isinstance(res, DualTrackAssessment)
    assert res.investment.stance == "long"
    assert res.bd.strategic_relevance == "high"
    assert res.quadrant == "dual_opportunity"
    assert res.divergence is False


def test_rich_stock_high_bd_is_bd_only_the_vertex_example():
    """A bad stock investment (richly priced) that is still a great BD target."""
    res = build_dual_track(
        _valuation(implied_upside_pct=-30.0, mispricing_direction="overpriced"),
        ma_row=_ma_row(strategic_fit_score=0.78, best_acquirer_name="Vertex"),
    )
    assert res.investment.stance in ("avoid", "neutral")
    assert res.investment.valuation_label == "overvalued"
    assert res.bd.strategic_relevance == "high"
    assert res.quadrant == "bd_only"
    assert res.divergence is True
    # Headline must articulate the split, not a blended score.
    assert "BD" in res.headline or "strategic" in res.headline.lower()
    assert "Vertex" in res.headline


def test_undervalued_low_bd_is_investment_only():
    res = build_dual_track(
        _valuation(implied_upside_pct=45.0, mispricing_direction="underpriced"),
        ma_row=_ma_row(strategic_fit_score=0.25, mna_probability_score=0.2),
    )
    assert res.investment.stance == "long"
    assert res.bd.strategic_relevance == "low"
    assert res.quadrant == "investment_only"
    assert res.divergence is True


def test_weak_both_is_low_conviction():
    res = build_dual_track(
        _valuation(implied_upside_pct=-25.0, mispricing_direction="overpriced"),
        ma_row=_ma_row(strategic_fit_score=0.2, mna_probability_score=0.2),
    )
    assert res.quadrant == "low_conviction"
    assert res.divergence is False


# ---------------------------------------------------------------------------
# Degradation tests
# ---------------------------------------------------------------------------

def test_missing_bd_inputs_marks_incomplete():
    res = build_dual_track(_valuation(implied_upside_pct=40.0))
    assert res.investment.assessed is True
    assert res.bd.assessed is False
    assert res.bd.strategic_relevance == "not_assessed"
    assert res.quadrant == "incomplete"


def test_missing_valuation_inputs_marks_incomplete():
    res = build_dual_track(None, ma_row=_ma_row())
    assert res.investment.assessed is False
    assert res.investment.stance == "not_assessed"
    assert res.bd.assessed is True
    assert res.quadrant == "incomplete"


def test_no_price_data_makes_investment_not_assessed():
    res = build_dual_track(
        _valuation(implied_upside_pct=None, has_price=False),
        ma_row=_ma_row(),
    )
    assert res.investment.assessed is False


# ---------------------------------------------------------------------------
# Market-read and route mapping
# ---------------------------------------------------------------------------

def test_market_read_maps_overpriced_to_too_high():
    res = build_dual_track(
        _valuation(implied_upside_pct=-20.0, mispricing_direction="overpriced"),
        ma_row=_ma_row(),
    )
    assert res.investment.market_expectation_read == "market_expectation_too_high"


def test_market_read_maps_underpriced_to_too_low():
    res = build_dual_track(
        _valuation(implied_upside_pct=30.0, mispricing_direction="underpriced"),
        ma_row=_ma_row(),
    )
    assert res.investment.market_expectation_read == "market_expectation_too_low"


def test_bdma_output_preferred_for_route_and_action():
    res = build_dual_track(
        _valuation(implied_upside_pct=10.0),
        bdma_output=_bdma(recommended_structure="license_partnership"),
    )
    assert res.bd.recommended_route == "license"
    assert res.bd.recommended_action == "pursue"


def test_ma_row_option_structure_maps_to_option_route():
    res = build_dual_track(
        _valuation(implied_upside_pct=10.0),
        ma_row=_ma_row(recommended_deal_structure="option_to_acquire"),
    )
    assert res.bd.recommended_route == "option"


def test_rnpv_vs_ev_uses_asset_implied_ev_when_available():
    res = build_dual_track(
        _valuation(
            implied_upside_pct=20.0,
            rnpv_millions=500.0,
            asset_implied_ev_millions=400.0,
        ),
        ma_row=_ma_row(),
    )
    # (500 - 400) / 400 = +25%
    assert res.investment.rnpv_vs_ev_pct == pytest.approx(25.0, abs=0.1)
    assert res.investment.comparison_ev_basis == "asset_implied"


# ---------------------------------------------------------------------------
# Configurability + independence
# ---------------------------------------------------------------------------

def test_thresholds_are_configurable():
    strict = DualTrackThresholds(bd_high=0.9)
    res = build_dual_track(
        _valuation(implied_upside_pct=40.0),
        ma_row=_ma_row(strategic_fit_score=0.8),
        thresholds=strict,
    )
    # 0.8 < 0.9 → no longer "high"
    assert res.bd.strategic_relevance != "high"


def test_decision_report_renders_dual_track_from_json_shim():
    """The bve-report path loads a flat summary_dict shim; the section must render."""
    from bve.reporting.decision_report import (
        DecisionReportInput,
        render_decision_report,
    )

    class _Shim:
        def __init__(self, sd: dict) -> None:
            self._sd = sd

        @property
        def summary_dict(self) -> dict:
            return self._sd

        def __getattr__(self, name: str):
            return self._sd.get(name)

    shim = _Shim(
        {
            "implied_upside_pct": -30.0,
            "rnpv_millions": 500.0,
            "nav_per_share": 7.0,
            "current_price": 10.0,
            "shares_outstanding_millions": 100.0,
            "net_cash_millions": 200.0,
            "market_mispricing_direction": "overpriced",
            "market_mispricing_magnitude": "large",
            "market_implied_peak_sales_millions": 800.0,
            "vp_category": "commercial",
            "vp_memo": "Market prices an aggressive ramp.",
            "mc_prob_positive": 0.6,
        }
    )
    report = render_decision_report(
        DecisionReportInput(ticker="VRTX", valuation_output=shim, ma_row=_ma_row())
    )
    assert "## Dual-Track Verdict" in report
    assert "Quadrant:" in report
    # Rich stock + strong BD target → the divergence cross-read.
    assert "bd_only" in report or "diverge" in report


def test_dual_track_columns_returns_two_flat_fields():
    cols = dual_track_columns(
        _valuation(implied_upside_pct=-30.0, mispricing_direction="overpriced"),
        ma_row=_ma_row(strategic_fit_score=0.78, recommended_deal_structure="full_acquisition"),
    )
    assert set(cols) == {"investment_stance", "bd_route"}
    assert cols["investment_stance"] == "avoid"
    assert cols["bd_route"] == "acquire"


def test_dual_track_columns_degrade_to_not_assessed():
    cols = dual_track_columns(None)
    assert cols == {"investment_stance": "not_assessed", "bd_route": "not_assessed"}


def test_actionable_opportunity_accepts_dual_track_columns():
    from bve.intelligence.actionable_output import ActionableOpportunity

    opp = ActionableOpportunity(
        asset_id="a1",
        ticker="VRTX",
        recommended_action="monitor",
        recommended_size_pct=0.0,
        composite_score=0.42,
        ranking_component=0.2,
        thesis_component=0.15,
        opportunity_component=0.07,
        score_version="v1.0",
        investment_stance="avoid",
        bd_route="acquire",
    )
    assert opp.investment_stance == "avoid"
    assert opp.bd_route == "acquire"
    # Existing rows without the columns still default cleanly.
    legacy = ActionableOpportunity(
        asset_id="a2",
        ticker="XBI",
        recommended_action="avoid",
        recommended_size_pct=0.0,
        composite_score=0.1,
        ranking_component=0.05,
        thesis_component=0.03,
        opportunity_component=0.02,
        score_version="v1.0",
    )
    assert legacy.investment_stance is None
    assert legacy.bd_route is None


def test_decision_report_marks_bd_not_run_when_no_ma_scan():
    """An investment-only report must not read as a negative BD conclusion."""
    from bve.reporting.decision_report import (
        DecisionReportInput,
        render_decision_report,
    )

    class _Shim:
        def __init__(self, sd: dict) -> None:
            self._sd = sd

        @property
        def summary_dict(self) -> dict:
            return self._sd

        def __getattr__(self, name: str):
            return self._sd.get(name)

    shim = _Shim(
        {
            "implied_upside_pct": 40.0,
            "rnpv_millions": 500.0,
            "nav_per_share": 14.0,
            "current_price": 10.0,
            "shares_outstanding_millions": 100.0,
            "net_cash_millions": 200.0,
            "market_mispricing_direction": "underpriced",
        }
    )
    report = render_decision_report(
        DecisionReportInput(ticker="VKTX", valuation_output=shim)  # no ma_row
    )
    assert "Not run (no M&A scan)" in report
    assert "not run" in report.lower()
    assert "not a negative BD conclusion" in report


def test_verdicts_carry_independent_rationale():
    res = build_dual_track(
        _valuation(implied_upside_pct=-30.0, mispricing_direction="overpriced"),
        ma_row=_ma_row(strategic_fit_score=0.78),
    )
    assert isinstance(res.investment, InvestmentVerdict)
    assert isinstance(res.bd, BDVerdict)
    assert res.investment.rationale
    assert res.bd.rationale
    # There is no single blended composite score on the assessment.
    assert not hasattr(res, "composite_score")
