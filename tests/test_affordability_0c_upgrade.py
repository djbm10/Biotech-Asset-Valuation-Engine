"""Tests for 0C Pair-Specific Affordability Gate — upgrades:

1. Pair-level clarity:
   - AffordabilityResult carries pair_scope_note + is_pair_level_only property
   - HARD_FAIL for one acquirer does not propagate to other acquirers

2. Stock-deal realism:
   - Formula path: stock = market_cap × max_stock_issuance_pct × stock_quality_multiplier
   - SQM auto-computed from P/B, volatility, and investor_dilution_tolerance
   - Explicit stock_quality_multiplier override skips sub-signal computation
   - Pre-computed path (realistic_stock_component_millions) remains backward compat
   - SQM clamped to [0.10, 1.0]
   - AffordabilityResult exposes stock_component_millions and sqm_applied
"""
from __future__ import annotations

import pytest

from bve.intelligence.ma_eligibility import (
    AffordabilityBand,
    AcquirerCapacityInput,
    AffordabilityResult,
    _compute_stock_quality_multiplier,
    _effective_stock_component,
    _evaluate_affordability,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _acq(
    acq_id: str = "ACQ",
    *,
    cash: float = 5000.0,
    debt_cap: float = 2000.0,
    stock: float = 1000.0,
    buffer: float = 500.0,
    premium: float = 0.35,
    # Formula-path fields
    market_cap: float | None = None,
    max_pct: float = 0.10,
    pb: float | None = None,
    vol: float | None = None,
    dilution_tol: float = 0.50,
    sqm: float | None = None,
) -> AcquirerCapacityInput:
    return AcquirerCapacityInput(
        acquirer_id=acq_id,
        cash_available_millions=cash,
        estimated_debt_capacity_millions=debt_cap,
        realistic_stock_component_millions=stock,
        minimum_balance_buffer_millions=buffer,
        expected_takeout_premium=premium,
        acquirer_market_cap_millions=market_cap,
        max_stock_issuance_pct=max_pct,
        acquirer_price_to_book=pb,
        acquirer_stock_volatility_pct=vol,
        investor_dilution_tolerance=dilution_tol,
        stock_quality_multiplier=sqm,
    )


# ---------------------------------------------------------------------------
# 1. Pair-level clarity
# ---------------------------------------------------------------------------

class TestPairLevelClarity:

    def test_result_has_pair_scope_note(self):
        r = _evaluate_affordability(500.0, [_acq()])
        assert r[0].pair_scope_note != ""
        assert "pair" in r[0].pair_scope_note.lower()

    def test_is_pair_level_only_always_true(self):
        r = _evaluate_affordability(500.0, [_acq()])
        assert r[0].is_pair_level_only is True

    def test_hard_fail_one_acquirer_does_not_affect_other(self):
        """A $5B target is affordable for Pfizer but fails for a mid-cap."""
        rich = _acq("PFIZER", cash=50_000, debt_cap=20_000, stock=5_000, buffer=0, premium=0.35)
        poor = _acq("MID_CAP", cash=200, debt_cap=0, stock=0, buffer=0, premium=0.35)
        results = _evaluate_affordability(5000.0, [rich, poor])

        rich_r = next(r for r in results if r.acquirer_id == "PFIZER")
        poor_r = next(r for r in results if r.acquirer_id == "MID_CAP")

        # Rich acquirer should not be hard-failed
        assert rich_r.band != AffordabilityBand.HARD_FAIL
        # Poor acquirer hard-fails — independently
        assert poor_r.band == AffordabilityBand.HARD_FAIL
        # Both still produce results; target is not globally excluded
        assert len(results) == 2

    def test_hard_fail_pair_score_multiplier_zero(self):
        """HARD_FAIL pair has score_multiplier=0 — only that pair is zeroed."""
        poor = _acq("POOR", cash=100, debt_cap=0, stock=0, buffer=0, premium=0.35)
        results = _evaluate_affordability(500.0, [poor])
        assert results[0].is_hard_fail is True
        assert results[0].score_multiplier == pytest.approx(0.0)

    def test_affordability_result_frozen(self):
        r = _evaluate_affordability(300.0, [_acq()])[0]
        with pytest.raises(Exception):
            r.band = AffordabilityBand.NO_PENALTY  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. Stock-deal realism — formula path
# ---------------------------------------------------------------------------

class TestStockFormulaPath:

    def test_formula_path_active_when_market_cap_provided(self):
        acq = _acq(market_cap=50_000, max_pct=0.10, sqm=0.70)
        stock, sqm_applied = _effective_stock_component(acq)
        # 50_000 × 0.10 × 0.70 = 3_500
        assert stock == pytest.approx(3_500.0)
        assert sqm_applied == pytest.approx(0.70)

    def test_formula_path_uses_sqm_override(self):
        acq = _acq(market_cap=10_000, max_pct=0.15, sqm=0.80)
        stock, sqm_applied = _effective_stock_component(acq)
        assert stock == pytest.approx(10_000 * 0.15 * 0.80)
        assert sqm_applied is not None

    def test_formula_path_stock_appears_in_deal_capacity(self):
        # cash=0, debt=0, buffer=0, market_cap=10_000, pct=0.10, sqm=1.0
        # deal_capacity = 0 + 0 + 1_000 - 0 = 1_000
        # target_ev=600, premium=0.35 → cost=810, ratio=0.81 → MILD
        acq = _acq(cash=0, debt_cap=0, stock=0, buffer=0, market_cap=10_000,
                   max_pct=0.10, sqm=1.0)
        results = _evaluate_affordability(600.0, [acq])
        r = results[0]
        assert r.deal_capacity_millions == pytest.approx(1_000.0)
        assert r.band == AffordabilityBand.MILD_PENALTY
        assert r.stock_component_millions == pytest.approx(1_000.0)
        assert r.stock_quality_multiplier_applied == pytest.approx(1.0)

    def test_sqm_applied_exposed_in_result(self):
        acq = _acq(market_cap=20_000, max_pct=0.10, sqm=0.60)
        results = _evaluate_affordability(500.0, [acq])
        r = results[0]
        assert r.stock_quality_multiplier_applied == pytest.approx(0.60, abs=1e-4)


# ---------------------------------------------------------------------------
# 3. Stock quality multiplier (SQM) auto-computation
# ---------------------------------------------------------------------------

class TestStockQualityMultiplier:

    def test_default_no_signals_returns_base_dilution_tolerance(self):
        # No P/B or vol provided → sqm = investor_dilution_tolerance = 0.50
        acq = _acq(market_cap=10_000, dilution_tol=0.50)
        sqm = _compute_stock_quality_multiplier(acq)
        assert sqm == pytest.approx(0.50)

    def test_high_pb_adds_bonus(self):
        acq_neutral = _acq(market_cap=10_000, dilution_tol=0.50, pb=2.0)  # neutral P/B
        acq_high_pb = _acq(market_cap=10_000, dilution_tol=0.50, pb=5.0)  # P/B ≥ 4
        sqm_neutral = _compute_stock_quality_multiplier(acq_neutral)
        sqm_high = _compute_stock_quality_multiplier(acq_high_pb)
        assert sqm_high > sqm_neutral
        assert sqm_high == pytest.approx(0.50 + 0.15)

    def test_low_pb_applies_penalty(self):
        acq = _acq(market_cap=10_000, dilution_tol=0.50, pb=1.2)  # P/B < 1.5
        sqm = _compute_stock_quality_multiplier(acq)
        assert sqm == pytest.approx(0.50 - 0.20)

    def test_low_volatility_adds_bonus(self):
        acq = _acq(market_cap=10_000, dilution_tol=0.50, vol=15.0)  # vol < 20%
        sqm = _compute_stock_quality_multiplier(acq)
        assert sqm == pytest.approx(0.50 + 0.10)

    def test_high_volatility_applies_large_penalty(self):
        acq = _acq(market_cap=10_000, dilution_tol=0.50, vol=50.0)  # vol > 40%
        sqm = _compute_stock_quality_multiplier(acq)
        assert sqm == pytest.approx(0.50 - 0.25)

    def test_moderate_volatility_applies_mild_penalty(self):
        acq = _acq(market_cap=10_000, dilution_tol=0.50, vol=30.0)  # 20-40%
        sqm = _compute_stock_quality_multiplier(acq)
        assert sqm == pytest.approx(0.50 - 0.10)

    def test_combined_high_pb_low_vol_near_one(self):
        # base=0.80, pb_adj=0.15, vol_adj=0.10 → 1.05 → clamped to 1.0
        acq = _acq(market_cap=10_000, dilution_tol=0.80, pb=5.0, vol=10.0)
        sqm = _compute_stock_quality_multiplier(acq)
        assert sqm == pytest.approx(1.0)

    def test_sqm_floor_at_010(self):
        # base=0.10, pb_adj=-0.20, vol_adj=-0.25 → -0.35 → clamped to 0.10
        acq = _acq(market_cap=10_000, dilution_tol=0.10, pb=1.0, vol=60.0)
        sqm = _compute_stock_quality_multiplier(acq)
        assert sqm == pytest.approx(0.10)

    def test_explicit_sqm_override_skips_sub_signals(self):
        # Even with high P/B and low vol, explicit SQM=0.30 is used
        acq = _acq(market_cap=10_000, dilution_tol=0.90, pb=6.0, vol=5.0, sqm=0.30)
        sqm = _compute_stock_quality_multiplier(acq)
        assert sqm == pytest.approx(0.30)

    def test_explicit_sqm_is_clamped_to_floor(self):
        acq = _acq(market_cap=10_000, sqm=0.0)
        sqm = _compute_stock_quality_multiplier(acq)
        assert sqm == pytest.approx(0.10)

    def test_auto_computed_sqm_is_clamped_to_ceiling(self):
        # base=0.80, pb_adj=+0.15, vol_adj=+0.10 → 1.05 → clamped to 1.0
        acq = _acq(market_cap=10_000, dilution_tol=0.80, pb=5.0, vol=10.0)
        sqm = _compute_stock_quality_multiplier(acq)
        assert sqm == pytest.approx(1.0)

    def test_high_dilution_tolerance_raises_sqm(self):
        lo = _acq(market_cap=10_000, dilution_tol=0.20)
        hi = _acq(market_cap=10_000, dilution_tol=0.80)
        assert _compute_stock_quality_multiplier(hi) > _compute_stock_quality_multiplier(lo)


# ---------------------------------------------------------------------------
# 4. Backward compatibility — pre-computed path
# ---------------------------------------------------------------------------

class TestBackwardCompatPrecomputedPath:

    def test_no_market_cap_uses_precomputed_stock(self):
        acq = _acq(stock=1500.0)  # no market_cap → pre-computed path
        stock, sqm = _effective_stock_component(acq)
        assert stock == pytest.approx(1500.0)
        assert sqm is None

    def test_sqm_applied_is_none_on_precomputed_path(self):
        acq = _acq(stock=2000.0)
        results = _evaluate_affordability(1000.0, [acq])
        assert results[0].stock_quality_multiplier_applied is None

    def test_precomputed_stock_in_result_stock_component(self):
        acq = _acq(stock=888.0)
        results = _evaluate_affordability(100.0, [acq])
        assert results[0].stock_component_millions == pytest.approx(888.0)

    def test_existing_capacity_formula_unchanged(self):
        # Original formula: capacity = cash + debt + stock - buffer
        # 5000 + 2000 + 1000 - 500 = 7500
        acq = _acq(cash=5000, debt_cap=2000, stock=1000, buffer=500, premium=0.35)
        results = _evaluate_affordability(500.0, [acq])
        r = results[0]
        assert r.deal_capacity_millions == pytest.approx(7500.0)
        assert r.band == AffordabilityBand.NO_PENALTY

    def test_existing_band_thresholds_unchanged(self):
        # Mild penalty: capacity=1000, ev=600, cost=810, ratio=0.81
        acq = _acq(cash=1000, debt_cap=0, stock=0, buffer=0, premium=0.35)
        results = _evaluate_affordability(600.0, [acq])
        assert results[0].band == AffordabilityBand.MILD_PENALTY
        assert results[0].score_multiplier == pytest.approx(0.90)

    def test_existing_hard_fail_unchanged(self):
        # capacity=500, ev=500, cost=675, ratio=1.35 → hard fail
        acq = _acq(cash=500, debt_cap=0, stock=0, buffer=0, premium=0.35)
        results = _evaluate_affordability(500.0, [acq])
        assert results[0].band == AffordabilityBand.HARD_FAIL


# ---------------------------------------------------------------------------
# 5. End-to-end: formula path vs pre-computed comparison
# ---------------------------------------------------------------------------

class TestFormulaVsPrecomputed:

    def test_formula_produces_same_result_when_equivalent(self):
        """Formula with sqm=1.0 and 10% of market_cap should match a pre-supplied stock."""
        # market_cap=10_000, pct=0.10, sqm=1.0 → stock=1_000
        acq_formula = _acq(cash=5000, debt_cap=2000, stock=0, buffer=500, premium=0.35,
                           market_cap=10_000, max_pct=0.10, sqm=1.0)
        acq_precomputed = _acq(cash=5000, debt_cap=2000, stock=1000, buffer=500, premium=0.35)

        r_formula = _evaluate_affordability(500.0, [acq_formula])[0]
        r_precomp = _evaluate_affordability(500.0, [acq_precomputed])[0]

        assert r_formula.deal_capacity_millions == pytest.approx(r_precomp.deal_capacity_millions)
        assert r_formula.band == r_precomp.band
        assert r_formula.affordability_ratio == pytest.approx(r_precomp.affordability_ratio)

    def test_degraded_sqm_lowers_capacity_vs_precomputed(self):
        """SQM < 1.0 reduces the stock component vs a pre-computed equivalent."""
        # Pre-computed assumes 1_000M stock
        acq_precomputed = _acq(cash=0, debt_cap=0, stock=1000, buffer=0, premium=0.35)
        # Formula: market_cap=10_000, pct=0.10, sqm=0.60 → stock=600
        acq_formula = _acq(cash=0, debt_cap=0, stock=0, buffer=0, premium=0.35,
                           market_cap=10_000, max_pct=0.10, sqm=0.60)

        r_pre = _evaluate_affordability(500.0, [acq_precomputed])[0]
        r_form = _evaluate_affordability(500.0, [acq_formula])[0]

        assert r_form.deal_capacity_millions < r_pre.deal_capacity_millions
        assert r_form.affordability_ratio > r_pre.affordability_ratio
