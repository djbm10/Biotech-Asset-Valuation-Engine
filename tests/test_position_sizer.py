"""Tests for bve.analysis.position_sizer."""
import pytest
from bve.analysis.position_sizer import (
    PositionSizerInput, size_position, ConvictionTier,
)


def _base(**kwargs):
    defaults = dict(
        model_pos=0.50,
        market_implied_pos=0.30,
        downside_pct=0.60,
        conviction=ConvictionTier.MEDIUM,
    )
    defaults.update(kwargs)
    return PositionSizerInput(**defaults)


class TestValidation:
    def test_model_pos_out_of_range_raises(self):
        with pytest.raises(ValueError):
            size_position(_base(model_pos=1.5))

    def test_market_implied_pos_out_of_range_raises(self):
        with pytest.raises(ValueError):
            size_position(_base(market_implied_pos=-0.1))

    def test_downside_zero_raises(self):
        with pytest.raises(ValueError):
            size_position(_base(downside_pct=0.0))

    def test_downside_above_one_raises(self):
        with pytest.raises(ValueError):
            size_position(_base(downside_pct=1.01))

    def test_kelly_fraction_zero_raises(self):
        with pytest.raises(ValueError):
            size_position(_base(kelly_fraction=0.0))


class TestEdge:
    def test_positive_edge_produces_nonzero_size(self):
        r = size_position(_base(model_pos=0.50, market_implied_pos=0.20))
        assert r.recommended_size_pct > 0.0

    def test_zero_edge_produces_zero_size(self):
        r = size_position(_base(model_pos=0.30, market_implied_pos=0.30))
        assert r.recommended_size_pct == 0.0

    def test_negative_edge_produces_zero_size(self):
        r = size_position(_base(model_pos=0.20, market_implied_pos=0.40))
        assert r.recommended_size_pct == 0.0

    def test_pos_edge_stored_correctly(self):
        r = size_position(_base(model_pos=0.50, market_implied_pos=0.30))
        assert abs(r.pos_edge - 0.20) < 0.001

    def test_larger_edge_larger_size(self):
        small = size_position(_base(model_pos=0.35, market_implied_pos=0.30))
        large = size_position(_base(model_pos=0.60, market_implied_pos=0.30))
        assert large.recommended_size_pct > small.recommended_size_pct


class TestConviction:
    def test_higher_conviction_larger_size(self):
        low = size_position(_base(conviction=ConvictionTier.LOW))
        high = size_position(_base(conviction=ConvictionTier.HIGH))
        assert high.recommended_size_pct > low.recommended_size_pct

    def test_speculative_capped_at_max(self):
        r = size_position(_base(
            conviction=ConvictionTier.SPECULATIVE,
            model_pos=0.60,
            market_implied_pos=0.10,
            downside_pct=0.20,
        ))
        assert r.recommended_size_pct <= 2.0

    def test_conviction_weight_stored(self):
        r = size_position(_base(conviction=ConvictionTier.HIGH))
        assert r.conviction_weight == pytest.approx(0.85)

    def test_very_high_conviction_weight(self):
        r = size_position(_base(conviction=ConvictionTier.VERY_HIGH))
        assert r.conviction_weight == pytest.approx(1.00)


class TestPortfolioCap:
    def test_size_never_exceeds_max_single_position(self):
        r = size_position(_base(
            model_pos=0.99,
            market_implied_pos=0.01,
            downside_pct=0.10,
            max_single_position_pct=5.0,
            conviction=ConvictionTier.VERY_HIGH,
            kelly_fraction=1.0,
        ))
        assert r.recommended_size_pct <= 5.0

    def test_max_size_pct_returned(self):
        r = size_position(_base(max_single_position_pct=6.0))
        assert r.max_size_pct == pytest.approx(6.0)

    def test_constraints_hit_populated_when_capped(self):
        r = size_position(_base(
            model_pos=0.99,
            market_implied_pos=0.01,
            downside_pct=0.05,
            max_single_position_pct=3.0,
            kelly_fraction=1.0,
        ))
        assert len(r.constraints_hit) > 0


class TestFinancingDiscount:
    def test_no_discount_for_long_runway(self):
        r = size_position(_base(financing_runway_months=30))
        assert r.financing_discount == pytest.approx(1.0)

    def test_heavy_discount_for_short_runway(self):
        long = size_position(_base(financing_runway_months=30))
        short = size_position(_base(financing_runway_months=4))
        assert short.recommended_size_pct < long.recommended_size_pct

    def test_distress_discount_severe(self):
        r = size_position(_base(financing_runway_months=3))
        assert r.financing_discount == pytest.approx(0.30)

    def test_unknown_runway_slight_haircut(self):
        r = size_position(_base(financing_runway_months=None))
        assert r.financing_discount == pytest.approx(0.90)


class TestCatalystBoost:
    def test_imminent_catalyst_boosts_size(self):
        base = size_position(_base())
        near = size_position(_base(catalyst_months_out=2.0))
        assert near.recommended_size_pct > base.recommended_size_pct

    def test_boost_at_1_month_is_1_25(self):
        r = size_position(_base(catalyst_months_out=1.0))
        assert r.catalyst_boost == pytest.approx(1.25)

    def test_boost_at_5_months_is_1_15(self):
        r = size_position(_base(catalyst_months_out=5.0))
        assert r.catalyst_boost == pytest.approx(1.15)

    def test_no_boost_for_far_catalyst(self):
        r = size_position(_base(catalyst_months_out=18.0))
        assert r.catalyst_boost == pytest.approx(1.00)


class TestAddSize:
    def test_add_size_is_incremental(self):
        r = size_position(_base(portfolio_current_pct=1.0))
        assert r.add_size_pct == pytest.approx(
            max(0.0, r.recommended_size_pct - 1.0), abs=0.01
        )

    def test_add_size_zero_when_already_at_cap(self):
        r = size_position(_base(portfolio_current_pct=10.0, max_single_position_pct=8.0))
        assert r.add_size_pct == 0.0


class TestOutput:
    def test_rationale_is_string(self):
        r = size_position(_base())
        assert isinstance(r.rationale, str)
        assert len(r.rationale) > 0

    def test_raw_kelly_stored(self):
        r = size_position(_base())
        assert isinstance(r.raw_kelly_pct, float)

    def test_all_sizes_non_negative(self):
        r = size_position(_base())
        assert r.recommended_size_pct >= 0.0
        assert r.add_size_pct >= 0.0
