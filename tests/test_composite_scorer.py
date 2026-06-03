"""
Tests for CompositeScorer and ActionableGenerator v2.0 signal integration.

Coverage
--------
1.  Score increases when catalyst signal_strength is high
2.  Score decreases when enrollment flags are negative (stalling / velocity_low)
3.  Score decreases more when slippage_alert is set (larger penalty)
4.  Score unchanged (adjustments all 0.0) when no signals supplied
5.  Capital risk HIGH applies −0.08 discount (with default weight=1.0)
6.  Capital risk CRITICAL applies −0.15 discount
7.  Capital risk LOW applies no discount
8.  Phase correlation posterior > prior lifts score
9.  Phase correlation posterior < prior drags score
10. Phase correlation missing (no prior/posterior) → 0.0 contribution
11. Endpoint z_score positive → lift; negative → drag
12. Competitor signal_strength positive → drag (negated)
13. Multiple enrollment flags stack
14. Signal adjustments sum correctly in total()
15. All weights load from YAML (scoring_weights section)
16. ActionableGenerator with contexts raises composite above base
17. ActionableGenerator without contexts → score_version=v1.0, no signal_adjustments
18. ActionableGenerator with contexts → score_version=v2.0, signal_adjustments populated
19. ActionableGenerator: missing context for an asset → 0 adjustments, not blocked
20. Composite clamped to [0.0, 1.0] even with large negative adjustments
"""
from __future__ import annotations

from datetime import date

import pytest

from bve.intelligence.capital_structure import CapitalRiskLevel
from bve.intelligence.composite_scorer import (
    SCORING_WEIGHT_DEFAULTS,
    CompositeScoreContext,
    CompositeScorer,
)
from bve.intelligence.actionable_output import (
    ActionableGenerator,
    ScoredCandidate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scorer(overrides: dict | None = None) -> CompositeScorer:
    """Build a CompositeScorer with default weights, optionally overridden."""
    weights = dict(SCORING_WEIGHT_DEFAULTS)
    if overrides:
        weights.update(overrides)
    return CompositeScorer(weights=weights)


def _candidate(
    asset_id: str = "a-test",
    ticker: str = "TEST",
    ranking: float = 0.60,
    opportunity: float = 0.60,
    thesis: float | None = None,
) -> ScoredCandidate:
    return ScoredCandidate(
        asset_id=asset_id,
        ticker=ticker,
        ranking_score=ranking,
        opportunity_score=opportunity,
        thesis_strength=thesis,
    )


# ---------------------------------------------------------------------------
# 1. Score increases when catalyst signal_strength is high
# ---------------------------------------------------------------------------

def test_catalyst_high_signal_lifts_score():
    scorer = _scorer()
    ctx = CompositeScoreContext(catalyst_signal_strength=1.0)
    adj = scorer.compute_adjustments(ctx)
    assert adj["catalyst_ev"] > 0


def test_catalyst_signal_strength_clipped_at_1():
    """signal_strength above 1.0 is clipped — same effect as 1.0."""
    scorer = _scorer()
    adj_high  = scorer.compute_adjustments(CompositeScoreContext(catalyst_signal_strength=5.0))
    adj_one   = scorer.compute_adjustments(CompositeScoreContext(catalyst_signal_strength=1.0))
    assert adj_high["catalyst_ev"] == adj_one["catalyst_ev"]


def test_catalyst_negative_signal_drags_score():
    scorer = _scorer()
    ctx = CompositeScoreContext(catalyst_signal_strength=-1.0)
    adj = scorer.compute_adjustments(ctx)
    assert adj["catalyst_ev"] < 0


# ---------------------------------------------------------------------------
# 2 & 3. Enrollment flags decrease score; slippage is larger
# ---------------------------------------------------------------------------

def test_enrollment_stalling_penalty():
    scorer = _scorer()
    adj = scorer.compute_adjustments(CompositeScoreContext(enrollment_site_stalling=True))
    assert adj["enrollment"] < 0


def test_enrollment_velocity_low_penalty():
    scorer = _scorer()
    adj = scorer.compute_adjustments(CompositeScoreContext(enrollment_velocity_low=True))
    assert adj["enrollment"] < 0


def test_enrollment_slippage_larger_than_stalling():
    scorer = _scorer()
    adj_slip  = scorer.compute_adjustments(CompositeScoreContext(enrollment_slippage_alert=True))
    adj_stall = scorer.compute_adjustments(CompositeScoreContext(enrollment_site_stalling=True))
    assert adj_slip["enrollment"] < adj_stall["enrollment"]


def test_enrollment_multiple_flags_stack():
    scorer = _scorer()
    adj_both = scorer.compute_adjustments(
        CompositeScoreContext(enrollment_site_stalling=True, enrollment_velocity_low=True)
    )
    adj_one  = scorer.compute_adjustments(CompositeScoreContext(enrollment_site_stalling=True))
    assert adj_both["enrollment"] < adj_one["enrollment"]


# ---------------------------------------------------------------------------
# 4. Score unchanged when no signals supplied
# ---------------------------------------------------------------------------

def test_no_signals_all_zero():
    scorer = _scorer()
    ctx = CompositeScoreContext()  # all defaults
    adj = scorer.compute_adjustments(ctx)
    for signal, value in adj.items():
        assert value == 0.0, f"{signal} should be 0.0 with no data, got {value}"
    assert CompositeScorer.total(adj) == 0.0


# ---------------------------------------------------------------------------
# 5–7. Capital risk discounts
# ---------------------------------------------------------------------------

def test_capital_risk_high_discount():
    scorer = _scorer()
    adj = scorer.compute_adjustments(CompositeScoreContext(capital_risk=CapitalRiskLevel.HIGH))
    assert adj["capital_risk"] == pytest.approx(-0.08)


def test_capital_risk_critical_discount():
    scorer = _scorer()
    adj = scorer.compute_adjustments(CompositeScoreContext(capital_risk=CapitalRiskLevel.CRITICAL))
    assert adj["capital_risk"] == pytest.approx(-0.15)


def test_capital_risk_low_no_discount():
    scorer = _scorer()
    adj = scorer.compute_adjustments(CompositeScoreContext(capital_risk=CapitalRiskLevel.LOW))
    assert adj["capital_risk"] == 0.0


def test_capital_risk_medium_discount():
    scorer = _scorer()
    adj = scorer.compute_adjustments(CompositeScoreContext(capital_risk=CapitalRiskLevel.MEDIUM))
    assert adj["capital_risk"] == pytest.approx(-0.03)


# ---------------------------------------------------------------------------
# 8–10. Phase correlation
# ---------------------------------------------------------------------------

def test_phase_correlation_posterior_higher_lifts():
    scorer = _scorer()
    ctx = CompositeScoreContext(phase_prior_pos=0.40, phase_posterior_pos=0.55)
    adj = scorer.compute_adjustments(ctx)
    assert adj["phase_correlation"] > 0


def test_phase_correlation_posterior_lower_drags():
    scorer = _scorer()
    ctx = CompositeScoreContext(phase_prior_pos=0.50, phase_posterior_pos=0.35)
    adj = scorer.compute_adjustments(ctx)
    assert adj["phase_correlation"] < 0


def test_phase_correlation_missing_is_zero():
    scorer = _scorer()
    adj = scorer.compute_adjustments(CompositeScoreContext(phase_prior_pos=0.40))
    assert adj["phase_correlation"] == 0.0

    adj2 = scorer.compute_adjustments(CompositeScoreContext(phase_posterior_pos=0.50))
    assert adj2["phase_correlation"] == 0.0


def test_phase_correlation_magnitude():
    """delta=0.20 × weight=0.25 = 0.05 exactly."""
    scorer = _scorer()
    ctx = CompositeScoreContext(phase_prior_pos=0.40, phase_posterior_pos=0.60)
    adj = scorer.compute_adjustments(ctx)
    assert adj["phase_correlation"] == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# 11. Endpoint z-score
# ---------------------------------------------------------------------------

def test_endpoint_high_z_lifts():
    scorer = _scorer()
    adj = scorer.compute_adjustments(CompositeScoreContext(endpoint_z_score=2.0))
    assert adj["endpoint_z"] > 0


def test_endpoint_negative_z_drags():
    scorer = _scorer()
    adj = scorer.compute_adjustments(CompositeScoreContext(endpoint_z_score=-2.0))
    assert adj["endpoint_z"] < 0


def test_endpoint_z_clipped_at_2():
    scorer = _scorer()
    adj_extreme = scorer.compute_adjustments(CompositeScoreContext(endpoint_z_score=10.0))
    adj_two     = scorer.compute_adjustments(CompositeScoreContext(endpoint_z_score=2.0))
    assert adj_extreme["endpoint_z"] == adj_two["endpoint_z"]


# ---------------------------------------------------------------------------
# 12. Competitor signal_strength drags score (negated)
# ---------------------------------------------------------------------------

def test_competitor_high_signal_drags():
    scorer = _scorer()
    adj = scorer.compute_adjustments(
        CompositeScoreContext(competitor_signal_strengths=[1.0, 0.8])
    )
    assert adj["competitor_impact"] < 0


def test_competitor_empty_list_is_zero():
    scorer = _scorer()
    adj = scorer.compute_adjustments(CompositeScoreContext(competitor_signal_strengths=[]))
    assert adj["competitor_impact"] == 0.0


def test_competitor_negative_signal_lifts():
    """Competitor with negative signal (bad readout) → positive lift for us."""
    scorer = _scorer()
    adj = scorer.compute_adjustments(
        CompositeScoreContext(competitor_signal_strengths=[-1.0])
    )
    assert adj["competitor_impact"] > 0


# ---------------------------------------------------------------------------
# 13 & 14. Total helper
# ---------------------------------------------------------------------------

def test_total_sums_all_adjustments():
    scorer = _scorer()
    ctx = CompositeScoreContext(
        catalyst_signal_strength=0.5,
        enrollment_velocity_low=True,
        capital_risk=CapitalRiskLevel.HIGH,
    )
    adj = scorer.compute_adjustments(ctx)
    expected = sum(adj.values())
    assert CompositeScorer.total(adj) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# 15. Weights load from YAML (scoring_weights section present)
# ---------------------------------------------------------------------------

def test_weights_loaded_from_yaml():
    """YAML has scoring_weights section; loaded weights should match defaults."""
    # This exercises the real _load_weights() path.
    scorer = CompositeScorer()  # no override → loads from YAML (or defaults)
    w = scorer._weights
    for key in SCORING_WEIGHT_DEFAULTS:
        assert key in w, f"Weight key {key!r} missing"
        assert isinstance(w[key], float)


def test_custom_weights_applied():
    """Passing explicit weights overrides YAML defaults."""
    weights = dict(SCORING_WEIGHT_DEFAULTS)
    weights["catalyst_ev"] = 0.50  # 5× the default

    scorer_custom  = CompositeScorer(weights=weights)
    scorer_default = _scorer()

    ctx = CompositeScoreContext(catalyst_signal_strength=1.0)
    adj_custom  = scorer_custom.compute_adjustments(ctx)
    adj_default = scorer_default.compute_adjustments(ctx)

    assert adj_custom["catalyst_ev"] > adj_default["catalyst_ev"]


# ---------------------------------------------------------------------------
# 16. ActionableGenerator with contexts raises composite above base
# ---------------------------------------------------------------------------

def test_actionable_generator_contexts_raise_composite():
    """High catalyst signal_strength should lift the composite and may change action."""
    gen = ActionableGenerator()

    cand = _candidate(asset_id="a-vktx", ranking=0.55, opportunity=0.55)
    # Base composite without contexts: 0.50×0.55 + 0×0 + 0.20×0.55 = 0.385

    report_base = gen.generate([cand], week_ending=date(2025, 6, 2))
    base_score = report_base.opportunities[0].composite_score

    ctx = CompositeScoreContext(catalyst_signal_strength=1.0)  # +0.15 lift
    report_sig = gen.generate(
        [cand],
        week_ending=date(2025, 6, 2),
        contexts={"a-vktx": ctx},
    )
    sig_score = report_sig.opportunities[0].composite_score

    assert sig_score > base_score


# ---------------------------------------------------------------------------
# 17. Without contexts → v1.0, no signal_adjustments
# ---------------------------------------------------------------------------

def test_no_contexts_v1_no_adjustments():
    gen = ActionableGenerator()
    cand = _candidate()
    report = gen.generate([cand], week_ending=date(2025, 6, 2))
    opp = report.opportunities[0]
    assert opp.score_version == "v1.0"
    assert opp.signal_adjustments == {}
    assert opp.signal_adjustment_total == 0.0


# ---------------------------------------------------------------------------
# 18. With contexts → v2.0, signal_adjustments populated
# ---------------------------------------------------------------------------

def test_with_contexts_v2_adjustments_populated():
    gen = ActionableGenerator()
    cand = _candidate(asset_id="a-alny")
    ctx = CompositeScoreContext(
        catalyst_signal_strength=0.8,
        capital_risk=CapitalRiskLevel.HIGH,
    )
    report = gen.generate(
        [cand],
        week_ending=date(2025, 6, 2),
        contexts={"a-alny": ctx},
    )
    opp = report.opportunities[0]
    assert opp.score_version == "v2.0"
    assert "catalyst_ev" in opp.signal_adjustments
    assert "capital_risk" in opp.signal_adjustments
    assert opp.signal_adjustment_total != 0.0


# ---------------------------------------------------------------------------
# 19. Missing context for asset → 0 adjustments, not blocked
# ---------------------------------------------------------------------------

def test_missing_context_for_asset_not_blocked():
    gen = ActionableGenerator()
    cand_with = _candidate(asset_id="a-has-ctx")
    cand_without = _candidate(asset_id="a-no-ctx", ticker="NONE")

    ctx = {"a-has-ctx": CompositeScoreContext(catalyst_signal_strength=0.5)}
    report = gen.generate(
        [cand_with, cand_without],
        week_ending=date(2025, 6, 2),
        contexts=ctx,
    )

    opp_with    = next(o for o in report.opportunities if o.asset_id == "a-has-ctx")
    opp_without = next(o for o in report.opportunities if o.asset_id == "a-no-ctx")

    assert opp_with.signal_adjustment_total != 0.0
    assert opp_without.signal_adjustment_total == 0.0
    # Both appear in the report
    assert len(report.opportunities) == 2


# ---------------------------------------------------------------------------
# 20. Composite clamped to [0.0, 1.0] with large negative adjustments
# ---------------------------------------------------------------------------

def test_composite_clamped_to_zero_floor():
    gen = ActionableGenerator()
    # Very low base score
    cand = _candidate(ranking=0.05, opportunity=0.05)
    ctx = CompositeScoreContext(
        enrollment_site_stalling=True,
        enrollment_velocity_low=True,
        enrollment_slippage_alert=True,
        capital_risk=CapitalRiskLevel.CRITICAL,
    )
    report = gen.generate(
        [cand],
        week_ending=date(2025, 6, 2),
        contexts={cand.asset_id: ctx},
    )
    for opp in report.opportunities:
        assert opp.composite_score >= 0.0


def test_composite_clamped_to_one_ceiling():
    gen = ActionableGenerator()
    cand = _candidate(ranking=1.0, opportunity=1.0, thesis=1.0)
    ctx = CompositeScoreContext(catalyst_signal_strength=1.0)
    report = gen.generate(
        [cand],
        week_ending=date(2025, 6, 2),
        contexts={cand.asset_id: ctx},
    )
    for opp in report.opportunities:
        assert opp.composite_score <= 1.0
