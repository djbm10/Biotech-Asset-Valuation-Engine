"""Tests for the Step 10 unified recommendation engine.

Covers:
- PortfolioContext + helpers (portfolio_context.py)
- Kelly sizer (kelly_sizer.py)
- Signal generator (signal_generator.py)
- Recommender / signal fusion (recommender.py)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from bve.trading.portfolio_context import (
    PortfolioContext,
    PositionRecord,
    available_capacity,
    concentration_penalty,
)
from bve.trading.kelly_sizer import (
    SizingResult,
    compute_kelly,
    size_position,
)
from bve.trading.asymmetry_score import AsymmetryResult, InstrumentType
from bve.trading.signal_generator import (
    TradeAction,
    TradeSignal,
    generate_signal,
)
from bve.intelligence.recommender import (
    DOMAIN_WEIGHTS,
    DomainSignal,
    FusedRecommendation,
    RecommendationStrength,
    fuse_signals,
    screen_recommendations,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_position(
    asset_id: str = "asset-1",
    ticker: str = "TICK",
    weight: float = 0.05,
    cost_basis_return: float = 0.0,
    phase: str = "Phase 2",
    therapeutic_area: str = "oncology",
    days_held: int = 30,
) -> PositionRecord:
    return PositionRecord(
        asset_id=asset_id,
        ticker=ticker,
        weight=weight,
        cost_basis_return=cost_basis_return,
        phase=phase,
        therapeutic_area=therapeutic_area,
        days_held=days_held,
    )


def _make_context(
    positions: list[PositionRecord] | None = None,
    total_nav: float = 1_000_000.0,
    cash_pct: float = 0.30,
    max_single_position: float = 0.10,
    max_ta_concentration: float = 0.35,
    max_phase_concentration: float = 0.40,
) -> PortfolioContext:
    return PortfolioContext(
        positions=positions or [],
        total_nav=total_nav,
        cash_pct=cash_pct,
        max_single_position=max_single_position,
        max_ta_concentration=max_ta_concentration,
        max_phase_concentration=max_phase_concentration,
    )


def _make_asymmetry(
    asset_id: str = "asset-1",
    asymmetry_score: float = 0.65,
    pos_delta: float = 0.10,
    skew_ratio: float = 2.0,
    implied_move_pct: float = 0.25,
    expected_return: float = 0.30,
    recommended_instrument: InstrumentType = InstrumentType.EQUITY,
    rationale: str = "test rationale",
) -> AsymmetryResult:
    return AsymmetryResult(
        asset_id=asset_id,
        asymmetry_score=asymmetry_score,
        recommended_instrument=recommended_instrument,
        pos_delta=pos_delta,
        skew_ratio=skew_ratio,
        implied_move_pct=implied_move_pct,
        expected_return=expected_return,
        rationale=rationale,
    )


def _make_sizing(
    asset_id: str = "asset-1",
    raw_kelly: float = 0.10,
    kelly_half: float = 0.05,
    capacity_cap: float = 0.08,
    concentration_mult: float = 1.0,
    final_weight: float = 0.05,
    position_size_usd: float = 50_000.0,
    rationale: str = "test sizing",
) -> SizingResult:
    return SizingResult(
        asset_id=asset_id,
        raw_kelly=raw_kelly,
        kelly_half=kelly_half,
        capacity_cap=capacity_cap,
        concentration_mult=concentration_mult,
        final_weight=final_weight,
        position_size_usd=position_size_usd,
        rationale=rationale,
    )


# ===========================================================================
# TestPortfolioContext
# ===========================================================================

class TestPortfolioContext:
    def test_ta_weights_computed_from_single_position(self):
        pos = _make_position(therapeutic_area="oncology", weight=0.08)
        ctx = _make_context(positions=[pos])
        assert ctx.ta_weights["oncology"] == pytest.approx(0.08)

    def test_ta_weights_accumulates_multiple_positions_same_ta(self):
        p1 = _make_position(asset_id="a1", therapeutic_area="oncology", weight=0.06)
        p2 = _make_position(asset_id="a2", therapeutic_area="oncology", weight=0.04)
        ctx = _make_context(positions=[p1, p2])
        assert ctx.ta_weights["oncology"] == pytest.approx(0.10)

    def test_ta_weights_separates_different_tas(self):
        p1 = _make_position(asset_id="a1", therapeutic_area="oncology", weight=0.06)
        p2 = _make_position(asset_id="a2", therapeutic_area="rare_disease", weight=0.05)
        ctx = _make_context(positions=[p1, p2])
        assert ctx.ta_weights["oncology"] == pytest.approx(0.06)
        assert ctx.ta_weights["rare_disease"] == pytest.approx(0.05)

    def test_phase_weights_computed_correctly(self):
        pos = _make_position(phase="Phase 2", weight=0.07)
        ctx = _make_context(positions=[pos])
        assert ctx.phase_weights["Phase 2"] == pytest.approx(0.07)

    def test_phase_weights_accumulates_same_phase(self):
        p1 = _make_position(asset_id="a1", phase="Phase 2", weight=0.06)
        p2 = _make_position(asset_id="a2", phase="Phase 2", weight=0.04)
        ctx = _make_context(positions=[p1, p2])
        assert ctx.phase_weights["Phase 2"] == pytest.approx(0.10)

    def test_phase_weights_separates_different_phases(self):
        p1 = _make_position(asset_id="a1", phase="Phase 2", weight=0.06)
        p2 = _make_position(asset_id="a2", phase="Phase 3", weight=0.08)
        ctx = _make_context(positions=[p1, p2])
        assert ctx.phase_weights["Phase 2"] == pytest.approx(0.06)
        assert ctx.phase_weights["Phase 3"] == pytest.approx(0.08)

    def test_n_positions_correct_empty(self):
        ctx = _make_context(positions=[])
        assert ctx.n_positions == 0

    def test_n_positions_correct_with_positions(self):
        positions = [_make_position(asset_id=f"a{i}") for i in range(4)]
        ctx = _make_context(positions=positions)
        assert ctx.n_positions == 4

    def test_total_invested_pct_equals_one_minus_cash(self):
        ctx = _make_context(cash_pct=0.25)
        assert ctx.total_invested_pct == pytest.approx(0.75)

    def test_total_invested_pct_full_cash(self):
        ctx = _make_context(cash_pct=1.0)
        assert ctx.total_invested_pct == pytest.approx(0.0)

    def test_available_capacity_respects_single_position_cap(self):
        ctx = _make_context(positions=[], cash_pct=0.50, max_single_position=0.10)
        capacity = available_capacity(ctx, "new-asset", "oncology", "Phase 2")
        # Limited by max_single_position=0.10 (less than cash=0.50)
        assert capacity == pytest.approx(0.10)

    def test_available_capacity_respects_ta_concentration_cap(self):
        # Already have 0.30 in oncology, cap is 0.35 → only 0.05 more allowed
        p1 = _make_position(asset_id="a1", therapeutic_area="oncology", weight=0.30)
        ctx = _make_context(
            positions=[p1], cash_pct=0.70,
            max_single_position=0.10,
            max_ta_concentration=0.35,
        )
        capacity = available_capacity(ctx, "new-asset", "oncology", "Phase 2")
        assert capacity == pytest.approx(0.05)

    def test_available_capacity_respects_phase_concentration_cap(self):
        # Already have 0.35 in Phase 2 (rare_disease TA), cap is 0.40 → only 0.05 more
        # Use "rare_disease" TA so TA headroom doesn't bind for "oncology"
        p1 = _make_position(asset_id="a1", phase="Phase 2", weight=0.35, therapeutic_area="rare_disease")
        ctx = _make_context(
            positions=[p1], cash_pct=0.70,
            max_single_position=0.10,
            max_ta_concentration=0.35,
            max_phase_concentration=0.40,
        )
        capacity = available_capacity(ctx, "new-asset", "oncology", "Phase 2")
        assert capacity == pytest.approx(0.05)

    def test_available_capacity_respects_cash_pct(self):
        # Only 0.02 cash available
        ctx = _make_context(positions=[], cash_pct=0.02, max_single_position=0.10)
        capacity = available_capacity(ctx, "new-asset", "oncology", "Phase 2")
        assert capacity == pytest.approx(0.02)

    def test_available_capacity_returns_zero_when_fully_concentrated(self):
        # TA concentration already at cap
        p1 = _make_position(asset_id="a1", therapeutic_area="oncology", weight=0.35)
        ctx = _make_context(
            positions=[p1], cash_pct=0.65,
            max_ta_concentration=0.35,
        )
        capacity = available_capacity(ctx, "new-asset", "oncology", "Phase 2")
        assert capacity == 0.0

    def test_available_capacity_existing_position_reduces_capacity(self):
        # Already hold 0.04 in asset-1, cap is 0.10 → can add 0.06 more
        p1 = _make_position(asset_id="asset-1", weight=0.04, therapeutic_area="rare_disease")
        ctx = _make_context(
            positions=[p1], cash_pct=0.50,
            max_single_position=0.10,
            max_ta_concentration=0.35,
            max_phase_concentration=0.40,
        )
        capacity = available_capacity(ctx, "asset-1", "rare_disease", "Phase 2")
        assert capacity == pytest.approx(0.06)

    def test_concentration_penalty_returns_1_when_under_limits(self):
        ctx = _make_context(positions=[], cash_pct=1.0)
        mult = concentration_penalty(ctx, "oncology", "Phase 2")
        assert mult == pytest.approx(1.0)

    def test_concentration_penalty_returns_075_at_mid_ta_threshold(self):
        # TA weight = 0.25 → 0.75 penalty
        pos = _make_position(therapeutic_area="oncology", weight=0.25)
        ctx = _make_context(positions=[pos])
        mult = concentration_penalty(ctx, "oncology", "Phase 2")
        assert mult == pytest.approx(0.75)

    def test_concentration_penalty_returns_075_at_mid_phase_threshold(self):
        # Phase weight = 0.30 → 0.75 penalty (use "rare_disease" TA so oncology TA weight stays 0)
        pos = _make_position(phase="Phase 2", weight=0.30, therapeutic_area="rare_disease")
        ctx = _make_context(positions=[pos])
        mult = concentration_penalty(ctx, "oncology", "Phase 2")
        assert mult == pytest.approx(0.75)

    def test_concentration_penalty_returns_050_at_high_ta_threshold(self):
        # TA weight = 0.30 → 0.50 penalty
        pos = _make_position(therapeutic_area="oncology", weight=0.30)
        ctx = _make_context(positions=[pos])
        mult = concentration_penalty(ctx, "oncology", "Phase 2")
        assert mult == pytest.approx(0.50)

    def test_concentration_penalty_returns_050_at_high_phase_threshold(self):
        # Phase weight = 0.35 → 0.50 penalty
        pos = _make_position(phase="Phase 2", weight=0.35)
        ctx = _make_context(positions=[pos])
        mult = concentration_penalty(ctx, "oncology", "Phase 2")
        assert mult == pytest.approx(0.50)

    def test_empty_portfolio_context(self):
        ctx = _make_context(positions=[], cash_pct=1.0)
        assert ctx.n_positions == 0
        assert ctx.ta_weights == {}
        assert ctx.phase_weights == {}
        assert ctx.total_invested_pct == pytest.approx(0.0)

    def test_multiple_positions_same_ta_accumulate(self):
        positions = [
            _make_position(asset_id=f"a{i}", therapeutic_area="oncology", weight=0.05)
            for i in range(4)
        ]
        ctx = _make_context(positions=positions)
        assert ctx.ta_weights["oncology"] == pytest.approx(0.20)


# ===========================================================================
# TestPositionSizer
# ===========================================================================

class TestPositionSizer:
    def test_compute_kelly_basic_formula(self):
        # Use parameters where raw Kelly < 0.25 to avoid clamping
        # Kelly = (0.55 * 0.20 - 0.45 * 0.20) / 0.20 = (0.11 - 0.09) / 0.20 = 0.10
        result = compute_kelly(win_prob=0.55, win_return=0.20, loss_return=-0.20)
        expected = (0.55 * 0.20 - 0.45 * 0.20) / 0.20
        assert result == pytest.approx(expected, abs=1e-6)

    def test_compute_kelly_clamped_to_025_maximum(self):
        # Very favorable odds → raw Kelly > 0.25, should be clamped
        result = compute_kelly(win_prob=0.95, win_return=0.80, loss_return=-0.05)
        assert result == pytest.approx(0.25)

    def test_compute_kelly_returns_zero_when_win_return_zero(self):
        result = compute_kelly(win_prob=0.60, win_return=0.0, loss_return=-0.30)
        assert result == 0.0

    def test_compute_kelly_returns_zero_when_win_return_negative(self):
        result = compute_kelly(win_prob=0.60, win_return=-0.10, loss_return=-0.30)
        assert result == 0.0

    def test_compute_kelly_returns_zero_when_kelly_negative(self):
        # Low win_prob leads to negative Kelly
        result = compute_kelly(win_prob=0.10, win_return=0.50, loss_return=-0.90)
        assert result == 0.0

    def test_size_position_kelly_half_equals_raw_kelly_divided_by_two(self):
        ctx = _make_context(cash_pct=0.50)
        asymmetry = _make_asymmetry(expected_return=0.40, implied_move_pct=0.20)
        result = size_position(asymmetry, ctx, "oncology", "Phase 2", base_pos=0.50)
        assert result.kelly_half == pytest.approx(result.raw_kelly / 2.0)

    def test_size_position_capacity_cap_applied(self):
        # capacity is very small → final_weight <= capacity_cap
        pos = _make_position(asset_id="x", therapeutic_area="oncology", weight=0.34)
        ctx = _make_context(
            positions=[pos], cash_pct=0.50,
            max_ta_concentration=0.35,
        )
        asymmetry = _make_asymmetry(expected_return=0.50, implied_move_pct=0.10)
        result = size_position(asymmetry, ctx, "oncology", "Phase 2", base_pos=0.60)
        # TA headroom = 0.35 - 0.34 = 0.01 (smallest constraint)
        assert result.final_weight <= result.capacity_cap + 1e-9

    def test_size_position_concentration_mult_applied(self):
        # High TA concentration → 0.50 multiplier
        pos = _make_position(therapeutic_area="oncology", weight=0.30)
        ctx = _make_context(positions=[pos], cash_pct=0.70)
        asymmetry = _make_asymmetry(expected_return=0.40, implied_move_pct=0.20)
        result = size_position(asymmetry, ctx, "oncology", "Phase 2", base_pos=0.50)
        assert result.concentration_mult == pytest.approx(0.50)

    def test_size_position_final_weight_floored_at_zero(self):
        # Zero capacity → final weight is 0
        pos = _make_position(therapeutic_area="oncology", weight=0.35)
        ctx = _make_context(
            positions=[pos], cash_pct=0.65,
            max_ta_concentration=0.35,
        )
        asymmetry = _make_asymmetry(expected_return=0.40, implied_move_pct=0.20)
        result = size_position(asymmetry, ctx, "oncology", "Phase 2", base_pos=0.50)
        assert result.final_weight == 0.0

    def test_size_position_usd_equals_weight_times_nav(self):
        ctx = _make_context(cash_pct=0.50, total_nav=2_000_000.0)
        asymmetry = _make_asymmetry(expected_return=0.40, implied_move_pct=0.20)
        result = size_position(asymmetry, ctx, "oncology", "Phase 2", base_pos=0.50)
        assert result.position_size_usd == pytest.approx(result.final_weight * 2_000_000.0)

    def test_size_position_zero_capacity_yields_zero_weight(self):
        # Phase at cap → zero capacity
        pos = _make_position(phase="Phase 2", weight=0.40)
        ctx = _make_context(
            positions=[pos], cash_pct=0.60,
            max_phase_concentration=0.40,
        )
        asymmetry = _make_asymmetry(expected_return=0.50, implied_move_pct=0.20)
        result = size_position(asymmetry, ctx, "oncology", "Phase 2", base_pos=0.55)
        assert result.final_weight == 0.0

    def test_size_position_returns_sizing_result_type(self):
        ctx = _make_context(cash_pct=0.50)
        asymmetry = _make_asymmetry()
        result = size_position(asymmetry, ctx, "oncology", "Phase 2", base_pos=0.40)
        assert isinstance(result, SizingResult)

    def test_size_position_asset_id_preserved(self):
        ctx = _make_context(cash_pct=0.50)
        asymmetry = _make_asymmetry(asset_id="my-asset")
        result = size_position(asymmetry, ctx, "oncology", "Phase 2", base_pos=0.40)
        assert result.asset_id == "my-asset"

    def test_size_position_rationale_non_empty(self):
        ctx = _make_context(cash_pct=0.50)
        asymmetry = _make_asymmetry()
        result = size_position(asymmetry, ctx, "oncology", "Phase 2", base_pos=0.40)
        assert len(result.rationale) > 0

    def test_compute_kelly_positive_edge_scenario(self):
        # 55% win, 30% upside, -20% downside
        # Kelly = (0.55*0.30 - 0.45*0.20) / 0.30 = (0.165 - 0.09)/0.30 = 0.25
        result = compute_kelly(win_prob=0.55, win_return=0.30, loss_return=-0.20)
        expected = (0.55 * 0.30 - 0.45 * 0.20) / 0.30
        expected = min(0.25, max(0.0, expected))
        assert result == pytest.approx(expected, abs=1e-6)


# ===========================================================================
# TestTradeSignal
# ===========================================================================

class TestTradeSignal:
    def _signal(self, **kwargs) -> TradeSignal:
        defaults = dict(
            asset_id="asset-1",
            ticker="TICK",
            asymmetry=_make_asymmetry(),
            sizing=_make_sizing(),
            kill_triggered=False,
            thesis_strength="bullish",
        )
        defaults.update(kwargs)
        return generate_signal(**defaults)

    def test_exit_when_kill_triggered(self):
        sig = self._signal(kill_triggered=True, asymmetry=_make_asymmetry(asymmetry_score=0.80))
        assert sig.action == TradeAction.EXIT

    def test_exit_when_strong_bear_and_negative_delta(self):
        sig = self._signal(
            thesis_strength="strong_bear",
            asymmetry=_make_asymmetry(pos_delta=-0.20, asymmetry_score=0.60),
        )
        assert sig.action == TradeAction.EXIT

    def test_reduce_for_bear_thesis(self):
        sig = self._signal(
            thesis_strength="bear",
            asymmetry=_make_asymmetry(pos_delta=0.05, asymmetry_score=0.55),
        )
        assert sig.action == TradeAction.REDUCE

    def test_strong_buy_at_asymmetry_score_gte_070(self):
        sig = self._signal(asymmetry=_make_asymmetry(asymmetry_score=0.72))
        assert sig.action == TradeAction.STRONG_BUY

    def test_buy_at_asymmetry_score_gte_050(self):
        sig = self._signal(asymmetry=_make_asymmetry(asymmetry_score=0.55))
        assert sig.action == TradeAction.BUY

    def test_watch_at_asymmetry_score_gte_035(self):
        sig = self._signal(asymmetry=_make_asymmetry(asymmetry_score=0.40))
        assert sig.action == TradeAction.WATCH

    def test_no_action_below_threshold(self):
        sig = self._signal(asymmetry=_make_asymmetry(asymmetry_score=0.20))
        assert sig.action == TradeAction.NO_ACTION

    def test_signal_id_is_unique_uuid(self):
        sig1 = self._signal()
        sig2 = self._signal()
        assert sig1.signal_id != sig2.signal_id
        # validate UUID format
        uuid.UUID(sig1.signal_id)
        uuid.UUID(sig2.signal_id)

    def test_generated_at_is_utc_datetime(self):
        sig = self._signal()
        assert isinstance(sig.generated_at, datetime)
        assert sig.generated_at.tzinfo is not None

    def test_kill_triggered_overrides_strong_score_to_exit(self):
        sig = self._signal(
            kill_triggered=True,
            asymmetry=_make_asymmetry(asymmetry_score=0.95),
        )
        assert sig.action == TradeAction.EXIT

    def test_strong_bear_with_weak_delta_not_exit(self):
        # strong_bear but pos_delta >= -0.15 → not EXIT (goes to bear path or score check)
        sig = self._signal(
            thesis_strength="strong_bear",
            asymmetry=_make_asymmetry(pos_delta=-0.10, asymmetry_score=0.60),
            kill_triggered=False,
        )
        # pos_delta=-0.10 is not < -0.15, so should not be EXIT from strong_bear rule
        # thesis_strength="strong_bear" is not "bear" so not REDUCE either
        # Score=0.60 → BUY
        assert sig.action == TradeAction.BUY

    def test_signal_contains_asset_id(self):
        sig = self._signal(asset_id="biotech-x")
        assert sig.asset_id == "biotech-x"

    def test_signal_contains_ticker(self):
        sig = self._signal(ticker="BNTX")
        assert sig.ticker == "BNTX"

    def test_kill_triggered_flag_preserved(self):
        sig = self._signal(kill_triggered=True)
        assert sig.kill_triggered is True

    def test_strong_buy_has_positive_suggested_weight(self):
        sizing = _make_sizing(final_weight=0.07)
        sig = self._signal(
            asymmetry=_make_asymmetry(asymmetry_score=0.80),
            sizing=sizing,
        )
        assert sig.action == TradeAction.STRONG_BUY
        assert sig.suggested_weight == pytest.approx(0.07)

    def test_non_buy_action_has_zero_suggested_weight(self):
        sig = self._signal(asymmetry=_make_asymmetry(asymmetry_score=0.20))
        assert sig.action == TradeAction.NO_ACTION
        assert sig.suggested_weight == 0.0


# ===========================================================================
# TestRecommender
# ===========================================================================

class TestRecommender:
    def _all_signals(self, default: float = 0.60) -> dict[str, float | None]:
        return {domain: default for domain in DOMAIN_WEIGHTS}

    def test_domain_weights_sum_to_one(self):
        total = sum(DOMAIN_WEIGHTS.values())
        assert total == pytest.approx(1.0)

    def test_all_7_domains_present(self):
        assert len(DOMAIN_WEIGHTS) == 7

    def test_fused_score_is_weighted_average(self):
        signals = self._all_signals(0.60)
        rec = fuse_signals("asset-1", signals)
        assert rec.fused_score == pytest.approx(0.60)

    def test_missing_domain_uses_neutral_05_contribution(self):
        signals = self._all_signals(0.80)
        signals["valuation_gap"] = None  # missing → treated as 0.5
        rec = fuse_signals("asset-1", signals)
        # Expected: valuation_gap contributes 0.5*0.25, rest contribute 0.8 * their weight
        expected = 0.5 * 0.25 + sum(
            score * weight
            for domain, (score, weight) in {
                d: (0.80, w) for d, w in DOMAIN_WEIGHTS.items() if d != "valuation_gap"
            }.items()
        )
        assert rec.fused_score == pytest.approx(expected, abs=1e-6)

    def test_missing_domains_list_populated_correctly(self):
        signals = self._all_signals(0.60)
        signals["science"] = None
        signals["financing"] = None
        rec = fuse_signals("asset-1", signals)
        assert "science" in rec.missing_domains
        assert "financing" in rec.missing_domains
        assert len(rec.missing_domains) == 2

    def test_strong_strength_at_gte_070(self):
        rec = fuse_signals("asset-1", self._all_signals(0.75))
        assert rec.strength == RecommendationStrength.STRONG

    def test_moderate_strength_at_gte_055(self):
        rec = fuse_signals("asset-1", self._all_signals(0.60))
        assert rec.strength == RecommendationStrength.MODERATE

    def test_weak_strength_at_gte_040(self):
        rec = fuse_signals("asset-1", self._all_signals(0.45))
        assert rec.strength == RecommendationStrength.WEAK

    def test_neutral_strength_at_gte_030(self):
        rec = fuse_signals("asset-1", self._all_signals(0.32))
        assert rec.strength == RecommendationStrength.NEUTRAL

    def test_negative_strength_below_030(self):
        rec = fuse_signals("asset-1", self._all_signals(0.20))
        assert rec.strength == RecommendationStrength.NEGATIVE

    def test_all_domains_present_no_missing(self):
        rec = fuse_signals("asset-1", self._all_signals(0.65))
        assert rec.missing_domains == []

    def test_screen_recommendations_filters_by_min_strength(self):
        rec_strong = fuse_signals("a1", self._all_signals(0.75))
        rec_moderate = fuse_signals("a2", self._all_signals(0.60))
        rec_negative = fuse_signals("a3", self._all_signals(0.20))
        results = screen_recommendations(
            [rec_strong, rec_moderate, rec_negative],
            min_strength=RecommendationStrength.MODERATE,
        )
        assert len(results) == 2
        assert all(r.strength in (
            RecommendationStrength.STRONG, RecommendationStrength.MODERATE
        ) for r in results)

    def test_screen_recommendations_sorted_by_fused_score_descending(self):
        rec_a = fuse_signals("a1", self._all_signals(0.55))
        rec_b = fuse_signals("a2", self._all_signals(0.75))
        rec_c = fuse_signals("a3", self._all_signals(0.65))
        results = screen_recommendations([rec_a, rec_b, rec_c])
        scores = [r.fused_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_require_trade_signal_filter_works(self):
        rec_with = fuse_signals("a1", self._all_signals(0.70), trade_signal=None)
        # Build a minimal TradeSignal
        asymmetry = _make_asymmetry(asymmetry_score=0.72)
        sizing = _make_sizing()
        ts = generate_signal("a2", "TICK", asymmetry, sizing, False, "bullish")
        rec_without_ts = fuse_signals("a1", self._all_signals(0.70), trade_signal=None)
        rec_with_ts = fuse_signals("a2", self._all_signals(0.70), trade_signal=ts)
        results = screen_recommendations(
            [rec_without_ts, rec_with_ts],
            require_trade_signal=True,
        )
        assert len(results) == 1
        assert results[0].asset_id == "a2"

    def test_fused_score_in_0_to_1_range(self):
        rec = fuse_signals("asset-1", self._all_signals(0.60))
        assert 0.0 <= rec.fused_score <= 1.0

    def test_rationale_is_non_empty(self):
        rec = fuse_signals("asset-1", self._all_signals(0.60))
        assert len(rec.rationale) > 0

    def test_domain_signals_contain_all_7_domains(self):
        rec = fuse_signals("asset-1", self._all_signals(0.60))
        domains = {ds.domain for ds in rec.domain_signals}
        assert domains == set(DOMAIN_WEIGHTS.keys())

    def test_fused_recommendation_is_frozen(self):
        rec = fuse_signals("asset-1", self._all_signals(0.60))
        with pytest.raises((TypeError, ValueError)):
            rec.fused_score = 0.99  # type: ignore[misc]

    def test_fuse_signals_partial_missing(self):
        signals: dict[str, float | None] = {d: None for d in DOMAIN_WEIGHTS}
        # All missing → all neutral 0.5
        rec = fuse_signals("asset-1", signals)
        assert rec.fused_score == pytest.approx(0.50)
        assert len(rec.missing_domains) == 7

    def test_screen_all_pass_min_weak(self):
        recs = [
            fuse_signals(f"a{i}", self._all_signals(0.45))
            for i in range(5)
        ]
        results = screen_recommendations(recs, min_strength=RecommendationStrength.WEAK)
        assert len(results) == 5

    def test_screen_empty_list(self):
        results = screen_recommendations([])
        assert results == []
