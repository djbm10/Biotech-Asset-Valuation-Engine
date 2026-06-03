"""Tests for Phase 2 Decision Intelligence modules."""
from __future__ import annotations

from datetime import date

import pytest

# --- market_implied_pos ---
from bve.expectations.market_implied_pos import ImpliedPoSResult, compute_implied_pos

# --- implied_move ---
from bve.expectations.implied_move import estimate_implied_move

# --- variant_perception ---
from bve.expectations.variant_perception import (
    EvidenceItem,
    PerceptionDimension,
    VariantPerception,
)

# --- scenario_tree ---
from bve.valuation.scenario_tree import ScenarioTreeBuilder

# --- financing_model ---
from bve.valuation.financing_model import (
    BurnProfile,
    FinancingModelResult,
    compute_financing_model,
)

# --- asymmetry_score ---
from bve.alpha.asymmetry_score import (
    AsymmetryScoreInput,
    compute_asymmetry_score,
)

# --- readthrough_engine ---
from bve.alpha.readthrough_engine import (
    CompetitorEvent,
    ReadthroughEngine,
)


# =============================================================================
# market_implied_pos (8 tests)
# =============================================================================

def _basic_pos_result() -> ImpliedPoSResult:
    return compute_implied_pos(
        asset_id="asset-001",
        ticker="TEST",
        as_of_date=date(2025, 1, 1),
        current_ev_millions=500.0,
        net_cash_millions=100.0,
        model_peak_sales_millions=1000.0,
        model_pos=0.30,
        years_to_peak=8.0,
        discount_rate=0.10,
        peak_duration_years=10.0,
        trial_costs_pv_millions=50.0,
    )


def test_compute_implied_pos_returns_result():
    result = _basic_pos_result()
    assert isinstance(result, ImpliedPoSResult)
    assert result.ticker == "TEST"


def test_compute_implied_pos_underpriced():
    # model_pos=0.30 but market only prices very low EV → underpriced
    result = compute_implied_pos(
        asset_id="a1", ticker="T1",
        as_of_date=date(2025, 1, 1),
        current_ev_millions=200.0,
        net_cash_millions=50.0,
        model_peak_sales_millions=2000.0,
        model_pos=0.40,
        trial_costs_pv_millions=30.0,
    )
    # model_pos should be higher than implied_pos if EV is low relative to pipeline value
    assert result.mispricing_direction == "underpriced"
    assert result.pos_gap > 0


def test_compute_implied_pos_overpriced():
    # High market EV relative to model assumptions → overpriced
    result = compute_implied_pos(
        asset_id="a2", ticker="T2",
        as_of_date=date(2025, 1, 1),
        current_ev_millions=5000.0,
        net_cash_millions=100.0,
        model_peak_sales_millions=500.0,
        model_pos=0.10,
        trial_costs_pv_millions=0.0,
    )
    assert result.mispricing_direction == "overpriced"
    assert result.pos_gap < 0


def test_compute_implied_pos_aligned():
    # Craft scenario where implied_pos ≈ model_pos → aligned
    # Set pipeline_ev = gross_revenue_pv * model_pos → implied_pos ≈ model_pos
    model_pos = 0.25
    discount_rate = 0.10
    peak_duration = 10.0
    years_to_peak = 8.0
    peak_sales = 1000.0
    annuity = (1 - (1 + discount_rate) ** (-peak_duration)) / discount_rate
    df = (1 + discount_rate) ** (-years_to_peak)
    gross_pv = peak_sales * annuity * df
    pipeline_ev = gross_pv * model_pos  # exactly aligned
    result = compute_implied_pos(
        asset_id="a3", ticker="T3",
        as_of_date=date(2025, 1, 1),
        current_ev_millions=pipeline_ev + 100.0,  # +100 net cash
        net_cash_millions=100.0,
        model_peak_sales_millions=peak_sales,
        model_pos=model_pos,
        discount_rate=discount_rate,
        peak_duration_years=peak_duration,
        years_to_peak=years_to_peak,
        trial_costs_pv_millions=0.0,
    )
    assert result.mispricing_direction == "aligned"
    assert abs(result.pos_gap) < 0.10


def test_compute_implied_pos_clamped_to_zero_one():
    # Negative pipeline EV → implied_pos clamped to 0.0
    result = compute_implied_pos(
        asset_id="a4", ticker="T4",
        as_of_date=date(2025, 1, 1),
        current_ev_millions=50.0,
        net_cash_millions=200.0,  # net cash > EV → negative pipeline EV
        model_peak_sales_millions=1000.0,
        model_pos=0.30,
        trial_costs_pv_millions=0.0,
    )
    assert 0.0 <= result.implied_pos <= 1.0
    assert result.implied_pos == 0.0


def test_compute_implied_pos_large_gap_magnitude():
    # Very underpriced → large magnitude
    result = compute_implied_pos(
        asset_id="a5", ticker="T5",
        as_of_date=date(2025, 1, 1),
        current_ev_millions=50.0,
        net_cash_millions=10.0,
        model_peak_sales_millions=3000.0,
        model_pos=0.50,
        trial_costs_pv_millions=0.0,
    )
    assert result.mispricing_magnitude == "large"
    assert abs(result.pos_gap) >= 0.30


def test_compute_implied_pos_negative_pipeline_ev_note():
    result = compute_implied_pos(
        asset_id="a6", ticker="T6",
        as_of_date=date(2025, 1, 1),
        current_ev_millions=100.0,
        net_cash_millions=300.0,  # net cash > EV
        model_peak_sales_millions=1000.0,
        model_pos=0.30,
        trial_costs_pv_millions=0.0,
    )
    assert any("negative" in note.lower() for note in result.notes)


def test_compute_implied_pos_peak_sales_gap_direction():
    # Underpriced → implied peak < model peak → peak_sales_gap > 0
    result = compute_implied_pos(
        asset_id="a7", ticker="T7",
        as_of_date=date(2025, 1, 1),
        current_ev_millions=200.0,
        net_cash_millions=50.0,
        model_peak_sales_millions=2000.0,
        model_pos=0.40,
        trial_costs_pv_millions=0.0,
    )
    assert result.peak_sales_gap_millions > 0
    assert result.implied_peak_sales_millions < result.model_peak_sales_millions


# =============================================================================
# implied_move (7 tests)
# =============================================================================

def test_estimate_implied_move_with_iv_method():
    result = estimate_implied_move(
        asset_id="a1", ticker="T1",
        event_date=date(2025, 6, 1),
        days_to_event=30,
        implied_volatility_annual=1.20,
    )
    assert result.method == "iv_approximation"
    assert result.implied_move_pct is not None


def test_estimate_implied_move_without_iv_uses_analog():
    result = estimate_implied_move(
        asset_id="a1", ticker="T1",
        event_date=date(2025, 6, 1),
        days_to_event=30,
        phase="3",
        therapeutic_area="oncology",
    )
    assert result.method == "historical_analog"
    assert result.implied_move_pct is not None


def test_estimate_implied_move_phase3_oncology_analog():
    result = estimate_implied_move(
        asset_id="a1", ticker="T1",
        event_date=date(2025, 6, 1),
        days_to_event=30,
        phase="3",
        therapeutic_area="oncology",
    )
    # Phase 3 oncology: upside 0.30, downside -0.40; analog = (0.30+0.40)/2 = 0.35
    assert result.upside_move_pct == pytest.approx(0.30)
    assert result.downside_move_pct == pytest.approx(-0.40)
    assert result.historical_analog_move_pct == pytest.approx(0.35)


def test_estimate_implied_move_expected_move_computed():
    result = estimate_implied_move(
        asset_id="a1", ticker="T1",
        event_date=date(2025, 6, 1),
        days_to_event=30,
        phase="3",
        therapeutic_area="oncology",
        prob_success=0.40,
    )
    assert result.expected_move_pct is not None
    expected = 0.40 * 0.30 + 0.60 * (-0.40)
    assert result.expected_move_pct == pytest.approx(expected, abs=1e-4)


def test_estimate_implied_move_high_iv_richness_rich():
    # IV is much higher than analog → rich
    result = estimate_implied_move(
        asset_id="a1", ticker="T1",
        event_date=date(2025, 6, 1),
        days_to_event=30,
        implied_volatility_annual=5.0,  # very high
        phase="3",
        therapeutic_area="oncology",
    )
    assert result.iv_richness == "rich"


def test_estimate_implied_move_low_iv_richness_cheap():
    # IV is much lower than analog → cheap
    result = estimate_implied_move(
        asset_id="a1", ticker="T1",
        event_date=date(2025, 6, 1),
        days_to_event=30,
        implied_volatility_annual=0.05,  # very low
        phase="3",
        therapeutic_area="oncology",
    )
    assert result.iv_richness == "cheap"


def test_estimate_implied_move_fair_iv():
    # Approximate: analog for phase3/oncology = 0.35
    # IV implied move ≈ IV * sqrt(30/365); need ratio between 0.7 and 1.3
    # Target ratio ~1.0: IV * sqrt(30/365) ≈ 0.35 → IV ≈ 0.35 / sqrt(30/365) ≈ 2.31
    import math
    analog = 0.35
    iv = analog / math.sqrt(30 / 365.0)  # exactly fair
    result = estimate_implied_move(
        asset_id="a1", ticker="T1",
        event_date=date(2025, 6, 1),
        days_to_event=30,
        implied_volatility_annual=iv,
        phase="3",
        therapeutic_area="oncology",
    )
    assert result.iv_richness == "fair"


# =============================================================================
# variant_perception (7 tests)
# =============================================================================

def _make_dimension(gap_direction: str = "bullish") -> PerceptionDimension:
    return PerceptionDimension(
        dimension="pos",
        market_view="Market thinks PoS is low",
        model_view="Model thinks PoS is higher",
        gap_direction=gap_direction,
        gap_magnitude="moderate",
        falsifier="Phase 3 failure",
    )


def test_variant_perception_instantiation():
    vp = VariantPerception(
        asset_id="a1",
        ticker="TEST",
        market_believes="The market prices low probability of approval.",
        model_thinks="The model sees higher PoS based on Phase 2 data.",
        why_gap_exists="Market underweights biomarker data.",
    )
    assert vp.asset_id == "a1"
    assert vp.is_documented is True


def test_variant_perception_bullish_dimensions():
    vp = VariantPerception(
        asset_id="a1", ticker="TEST",
        market_believes="x", model_thinks="y", why_gap_exists="z",
        dimensions=[
            _make_dimension("bullish"),
            _make_dimension("bullish"),
            _make_dimension("bearish"),
        ],
    )
    assert len(vp.bullish_dimensions()) == 2


def test_variant_perception_bearish_dimensions():
    vp = VariantPerception(
        asset_id="a1", ticker="TEST",
        market_believes="x", model_thinks="y", why_gap_exists="z",
        dimensions=[
            _make_dimension("bullish"),
            _make_dimension("bearish"),
            _make_dimension("bearish"),
        ],
    )
    assert len(vp.bearish_dimensions()) == 2


def test_variant_perception_net_conviction_bullish():
    vp = VariantPerception(
        asset_id="a1", ticker="TEST",
        market_believes="x", model_thinks="y", why_gap_exists="z",
        dimensions=[
            _make_dimension("bullish"),
            _make_dimension("bullish"),
            _make_dimension("bearish"),
        ],
    )
    assert vp.net_conviction_direction() == "bullish"


def test_variant_perception_net_conviction_mixed():
    vp = VariantPerception(
        asset_id="a1", ticker="TEST",
        market_believes="x", model_thinks="y", why_gap_exists="z",
        dimensions=[
            _make_dimension("bullish"),
            _make_dimension("bearish"),
        ],
    )
    assert vp.net_conviction_direction() == "mixed"


def test_perception_dimension_instantiation():
    dim = _make_dimension()
    assert dim.dimension == "pos"
    assert dim.gap_direction == "bullish"


def test_evidence_item_instantiation():
    item = EvidenceItem(
        description="Phase 2 biomarker enrichment shows strong signal",
        supports_model=True,
        strength="strong",
    )
    assert item.supports_model is True
    assert item.strength == "strong"


# =============================================================================
# scenario_tree (8 tests)
# =============================================================================

def test_scenario_tree_builder_default_phase3_six_branches():
    builder = ScenarioTreeBuilder()
    tree = builder.build(
        asset_id="a1", ticker="TEST",
        catalyst_label="Phase 3 Readout",
        catalyst_date=date(2025, 12, 1),
        catalyst_type="phase3_readout",
    )
    assert len(tree.branches) == 6


def test_scenario_tree_builder_fda_decision_three_branches():
    builder = ScenarioTreeBuilder()
    tree = builder.build(
        asset_id="a1", ticker="TEST",
        catalyst_label="FDA Decision",
        catalyst_date=date(2025, 12, 1),
        catalyst_type="fda_decision",
    )
    assert len(tree.branches) == 3


def test_scenario_tree_expected_return_computed():
    builder = ScenarioTreeBuilder()
    tree = builder.build(
        asset_id="a1", ticker="TEST",
        catalyst_label="FDA Decision",
        catalyst_date=date(2025, 12, 1),
        catalyst_type="fda_decision",
    )
    # fda_decision: 0.65*0.25 + 0.20*(-0.45) + 0.15*(-0.15)
    expected = 0.65 * 0.25 + 0.20 * (-0.45) + 0.15 * (-0.15)
    assert tree.expected_return_pct == pytest.approx(expected, abs=1e-4)


def test_scenario_tree_skew_ratio_positive():
    builder = ScenarioTreeBuilder()
    tree = builder.build(
        asset_id="a1", ticker="TEST",
        catalyst_label="Phase 3 Readout",
        catalyst_date=date(2025, 12, 1),
        catalyst_type="phase3_readout",
    )
    assert tree.skew_ratio > 0


def test_scenario_tree_is_valid_probs_sum_to_one():
    builder = ScenarioTreeBuilder()
    tree = builder.build(
        asset_id="a1", ticker="TEST",
        catalyst_label="FDA Decision",
        catalyst_date=date(2025, 12, 1),
        catalyst_type="fda_decision",
    )
    assert tree.is_valid()
    assert abs(tree.prob_sum() - 1.0) <= 0.01


def test_scenario_tree_success_branches():
    builder = ScenarioTreeBuilder()
    tree = builder.build(
        asset_id="a1", ticker="TEST",
        catalyst_label="FDA Decision",
        catalyst_date=date(2025, 12, 1),
        catalyst_type="fda_decision",
    )
    success = tree.success_branches()
    assert all(b.expected_price_move_pct > 0 for b in success)
    assert len(success) == 1  # only "approval" in fda_decision defaults


def test_scenario_tree_failure_branches():
    builder = ScenarioTreeBuilder()
    tree = builder.build(
        asset_id="a1", ticker="TEST",
        catalyst_label="FDA Decision",
        catalyst_date=date(2025, 12, 1),
        catalyst_type="fda_decision",
    )
    failure = tree.failure_branches()
    assert all(b.expected_price_move_pct <= 0 for b in failure)
    assert len(failure) == 2  # crl and delay


def test_scenario_tree_builder_branch_overrides():
    overrides = [
        {"label": "success", "probability": 0.60, "expected_price_move_pct": 0.50, "post_event_thesis_state": "confirmed", "iv_reaction": "compress"},
        {"label": "failure", "probability": 0.40, "expected_price_move_pct": -0.50, "post_event_thesis_state": "broken", "iv_reaction": "expand"},
    ]
    builder = ScenarioTreeBuilder()
    tree = builder.build(
        asset_id="a1", ticker="TEST",
        catalyst_label="Custom",
        catalyst_date=date(2025, 12, 1),
        branch_overrides=overrides,
    )
    assert len(tree.branches) == 2
    assert tree.is_valid()


# =============================================================================
# financing_model (6 tests)
# =============================================================================

def _make_burn_profile(bull=5.0, base=8.0, bear=12.0) -> BurnProfile:
    return BurnProfile(
        bull_quarterly_burn_millions=bull,
        base_quarterly_burn_millions=base,
        bear_quarterly_burn_millions=bear,
    )


def test_compute_financing_model_basic_call():
    result = compute_financing_model(
        company_id="co1",
        as_of_date=date(2025, 1, 1),
        cash_millions=100.0,
        debt_millions=0.0,
        burn_profile=_make_burn_profile(),
        months_to_next_catalyst=12.0,
        current_ev_millions=500.0,
    )
    assert isinstance(result, FinancingModelResult)
    assert result.company_id == "co1"


def test_compute_financing_model_runway_base_correct():
    # base quarterly burn = 6.0M → monthly = 2.0M; net cash = 24.0 → runway = 12 months
    result = compute_financing_model(
        company_id="co1",
        as_of_date=date(2025, 1, 1),
        cash_millions=24.0,
        debt_millions=0.0,
        burn_profile=_make_burn_profile(base=6.0),
        current_ev_millions=200.0,
    )
    assert result.runway_months_base == pytest.approx(12.0, abs=0.1)


def test_compute_financing_model_short_runway_high_p_raise():
    # runway_base < months_to_next_catalyst → p_raise = 0.75
    result = compute_financing_model(
        company_id="co1",
        as_of_date=date(2025, 1, 1),
        cash_millions=10.0,   # very little cash
        debt_millions=0.0,
        burn_profile=_make_burn_profile(base=15.0),  # high burn
        months_to_next_catalyst=24.0,
        current_ev_millions=200.0,
    )
    assert result.probability_needs_raise_before_catalyst == 0.75


def test_compute_financing_model_plenty_of_cash_low_risk():
    # Massive cash, low burn → low risk tier
    result = compute_financing_model(
        company_id="co1",
        as_of_date=date(2025, 1, 1),
        cash_millions=500.0,
        debt_millions=0.0,
        burn_profile=_make_burn_profile(bull=2.0, base=3.0, bear=4.0),
        months_to_next_catalyst=6.0,
        current_ev_millions=1000.0,
    )
    assert result.financing_risk_tier == "low"


def test_compute_financing_model_distress_risk_high_bear_runway():
    # Bear runway < 3 months → distress = 0.80
    result = compute_financing_model(
        company_id="co1",
        as_of_date=date(2025, 1, 1),
        cash_millions=5.0,
        debt_millions=0.0,
        burn_profile=_make_burn_profile(bear=30.0),  # burn 10M/month, only 5M cash → <1 month bear runway
        current_ev_millions=100.0,
    )
    assert result.distress_risk == pytest.approx(0.80)


def test_compute_financing_model_adjusted_ev_lower_when_dilution():
    result = compute_financing_model(
        company_id="co1",
        as_of_date=date(2025, 1, 1),
        cash_millions=10.0,
        debt_millions=0.0,
        burn_profile=_make_burn_profile(base=12.0),  # high burn
        months_to_next_catalyst=18.0,
        current_ev_millions=200.0,
    )
    if result.expected_dilution_pct_base > 0:
        assert result.financing_adjusted_ev_millions < 200.0


# =============================================================================
# asymmetry_score (7 tests)
# =============================================================================

def _make_asym_input(**kwargs) -> AsymmetryScoreInput:
    defaults = dict(
        asset_id="a1",
        ticker="TEST",
        model_ev_millions=600.0,
        market_ev_millions=400.0,
        enterprise_value_millions=400.0,
        expected_catalyst_return_pct=0.15,
        catalytic_magnitude=0.7,
        confidence=0.6,
        time_urgency=0.5,
        liquidity_adjustment=1.0,
        crowding_risk=0.0,
    )
    defaults.update(kwargs)
    return AsymmetryScoreInput(**defaults)


def test_asymmetry_score_positive_ev_gap_positive_composite():
    inputs = _make_asym_input(model_ev_millions=600.0, market_ev_millions=400.0)
    result = compute_asymmetry_score(inputs)
    assert result.composite_score > 0


def test_asymmetry_score_negative_ev_gap_lower_composite():
    positive = compute_asymmetry_score(_make_asym_input(model_ev_millions=600.0, market_ev_millions=400.0))
    negative = compute_asymmetry_score(_make_asym_input(model_ev_millions=200.0, market_ev_millions=400.0))
    assert negative.composite_score < positive.composite_score


def test_asymmetry_score_high_composite_instrument_call_or_equity():
    inputs = _make_asym_input(
        model_ev_millions=1000.0,
        market_ev_millions=400.0,
        enterprise_value_millions=400.0,
        catalytic_magnitude=0.9,
        confidence=0.8,
        time_urgency=0.6,
        expected_catalyst_return_pct=0.40,
    )
    result = compute_asymmetry_score(inputs)
    assert result.recommended_instrument in ("call", "equity", "straddle")


def test_asymmetry_score_high_crowding_reduces_score():
    low_crowd = compute_asymmetry_score(_make_asym_input(crowding_risk=0.0))
    high_crowd = compute_asymmetry_score(_make_asym_input(crowding_risk=1.0))
    assert high_crowd.composite_score < low_crowd.composite_score


def test_asymmetry_score_large_gap_expectation_mismatch():
    inputs = _make_asym_input(
        model_ev_millions=900.0,
        market_ev_millions=400.0,
        enterprise_value_millions=400.0,
    )
    result = compute_asymmetry_score(inputs)
    assert result.alpha_source == "expectation_mismatch"


def test_asymmetry_score_confidence_tier_high():
    inputs = _make_asym_input(confidence=0.75)
    result = compute_asymmetry_score(inputs)
    assert result.confidence_tier == "high"


def test_asymmetry_score_straddle_large_composite_high_urgency():
    inputs = _make_asym_input(
        model_ev_millions=1000.0,
        market_ev_millions=400.0,
        enterprise_value_millions=400.0,
        catalytic_magnitude=1.0,
        confidence=0.9,
        time_urgency=0.9,
        liquidity_adjustment=1.0,
        crowding_risk=0.0,
        expected_catalyst_return_pct=0.5,
    )
    result = compute_asymmetry_score(inputs)
    assert result.recommended_instrument == "straddle"


# =============================================================================
# readthrough_engine (6 tests)
# =============================================================================

def _make_event(event_type: str, magnitude: str = "moderate") -> CompetitorEvent:
    return CompetitorEvent(
        competitor_name="CompetitorCo",
        competitor_asset="COMP-001",
        event_type=event_type,
        event_date=date(2025, 6, 1),
        indication="NSCLC",
        description=f"Competitor {event_type} event",
        magnitude=magnitude,
    )


def test_readthrough_phase3_success_positive():
    engine = ReadthroughEngine()
    assessment = engine.assess("a1", "TEST", _make_event("phase3_success"))
    assert assessment.readthrough_direction == "positive"
    assert assessment.pos_delta > 0


def test_readthrough_phase3_failure_negative():
    engine = ReadthroughEngine()
    assessment = engine.assess("a1", "TEST", _make_event("phase3_failure"))
    assert assessment.readthrough_direction == "negative"
    assert assessment.pos_delta < 0


def test_readthrough_discontinuation_positive():
    engine = ReadthroughEngine()
    assessment = engine.assess("a1", "TEST", _make_event("discontinuation"))
    assert assessment.readthrough_direction == "positive"
    assert assessment.pos_delta > 0


def test_readthrough_safety_hold_negative():
    engine = ReadthroughEngine()
    assessment = engine.assess("a1", "TEST", _make_event("safety_hold"))
    assert assessment.readthrough_direction == "negative"
    assert assessment.pos_delta < 0


def test_readthrough_not_same_mechanism_smaller_delta():
    engine = ReadthroughEngine()
    same_mech = engine.assess("a1", "TEST", _make_event("phase3_success"), same_mechanism=True)
    diff_mech = engine.assess("a1", "TEST", _make_event("phase3_success"), same_mechanism=False)
    assert abs(diff_mech.pos_delta) < abs(same_mech.pos_delta)


def test_readthrough_large_magnitude_larger_delta():
    engine = ReadthroughEngine()
    small = engine.assess("a1", "TEST", _make_event("phase3_success", magnitude="small"))
    large = engine.assess("a1", "TEST", _make_event("phase3_success", magnitude="large"))
    assert abs(large.pos_delta) > abs(small.pos_delta)
