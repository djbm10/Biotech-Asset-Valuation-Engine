"""
Tests for ImpliedPoSEstimator (Wave 1D — market expectation modeling).

Covers NAV math, clamping, pos_gap sign, edge cases (zero peak sales,
zero discount rate, market cap below cash), and field population.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from bve.intelligence.market_expectations import (
    ImpliedPoSEstimator,
    build_market_expectation_from_snapshot,
    compute_implied_success_probability,
    MarketExpectation,
    compute_market_mispricing,
)

_ESTIMATOR = ImpliedPoSEstimator()


def _compute(
    market_cap_millions: float = 500.0,
    model_pos: float = 0.30,
    peak_sales_millions: float = 1_000.0,
    patent_life_years: int = 12,
    discount_rate: float = 0.12,
    margin_rate: float = 0.35,
    cash_estimate_millions: float = 0.0,
) -> MarketExpectation:
    return _ESTIMATOR.compute(
        asset_id="test-asset",
        ticker="TEST",
        market_cap_millions=market_cap_millions,
        model_pos=model_pos,
        peak_sales_millions=peak_sales_millions,
        patent_life_years=patent_life_years,
        discount_rate=discount_rate,
        margin_rate=margin_rate,
        cash_estimate_millions=cash_estimate_millions,
    )


class TestNavMath:
    def test_basic_implied_pos_in_range(self):
        exp = _compute()
        assert exp.implied_pos is not None
        assert 0.0 <= exp.implied_pos <= 1.0

    def test_pos_gap_sign_when_market_pessimistic(self):
        # market cap very low → implied_pos < model_pos → pos_gap < 0
        exp = _compute(market_cap_millions=100.0, model_pos=0.50)
        assert exp.pos_gap is not None
        assert exp.pos_gap < 0

    def test_pos_gap_sign_when_market_optimistic(self):
        # market cap very high → implied_pos > model_pos → pos_gap > 0
        exp = _compute(market_cap_millions=2_000.0, model_pos=0.10)
        assert exp.pos_gap is not None
        assert exp.pos_gap > 0

    def test_pos_gap_equals_implied_minus_model(self):
        exp = _compute()
        assert exp.pos_gap is not None
        assert abs(exp.pos_gap - (exp.implied_pos - exp.model_pos)) < 1e-6

    def test_cash_subtracted_from_equity_value(self):
        without_cash = _compute(market_cap_millions=500.0, cash_estimate_millions=0.0)
        with_cash = _compute(market_cap_millions=500.0, cash_estimate_millions=200.0)
        # With cash subtracted, equity value lower → implied_pos lower
        assert with_cash.implied_pos < without_cash.implied_pos

    def test_annuity_formula_zero_discount_rate(self):
        # When discount_rate=0, pv_factor = patent_life_years
        exp = _compute(discount_rate=0.0, patent_life_years=10)
        # pipeline_pv = peak_sales × margin × patent_life = 1000 × 0.35 × 10 = 3500
        # implied_pos = 500 / 3500 ≈ 0.1429
        assert exp.implied_pos is not None
        assert abs(exp.implied_pos - (500.0 / (1000.0 * 0.35 * 10))) < 1e-3

    def test_model_pos_stored_correctly(self):
        exp = _compute(model_pos=0.45)
        assert exp.model_pos == 0.45

    def test_identity_fields(self):
        exp = _compute()
        assert exp.asset_id == "test-asset"
        assert exp.ticker == "TEST"
        assert exp.methodology == "nav_backsolve"


class TestClamping:
    def test_clamped_to_zero_when_equity_negative(self):
        # market_cap < cash → equity_value < 0 → raw implied_pos < 0 → clamped to 0
        exp = _compute(market_cap_millions=50.0, cash_estimate_millions=100.0)
        assert exp.implied_pos == 0.0

    def test_clamped_to_one_when_market_cap_extreme(self):
        # market_cap very large → raw > 1 → clamped to 1
        exp = _compute(market_cap_millions=100_000.0)
        assert exp.implied_pos == 1.0

    def test_not_clamped_in_normal_range(self):
        exp = _compute(market_cap_millions=500.0)
        assert 0.0 < exp.implied_pos < 1.0


class TestEdgeCases:
    def test_zero_peak_sales_returns_none(self):
        exp = _compute(peak_sales_millions=0.0)
        assert exp.implied_pos is None
        assert exp.pos_gap is None

    def test_negative_peak_sales_returns_none(self):
        exp = _compute(peak_sales_millions=-100.0)
        assert exp.implied_pos is None

    def test_no_model_pos_still_computes_implied(self):
        exp = _ESTIMATOR.compute(
            asset_id="x",
            ticker="X",
            market_cap_millions=500.0,
            model_pos=None,
            peak_sales_millions=1_000.0,
        )
        assert exp.implied_pos is not None
        assert exp.pos_gap is None  # can't compute gap without model_pos

    def test_expectation_date_defaults_to_today(self):
        exp = _compute()
        assert exp.expectation_date == datetime.now(timezone.utc).date()

    def test_explicit_expectation_date(self):
        d = date(2024, 3, 15)
        exp = _ESTIMATOR.compute(
            asset_id="x",
            ticker="X",
            market_cap_millions=500.0,
            model_pos=0.3,
            peak_sales_millions=1_000.0,
            expectation_date=d,
        )
        assert exp.expectation_date == d

    def test_expectation_id_is_unique(self):
        exp1 = _compute()
        exp2 = _compute()
        assert exp1.expectation_id != exp2.expectation_id


class TestMarketMispricing:
    def test_market_mispricing_matches_formula(self):
        mispricing = compute_market_mispricing(
            model_rnpv_millions=150.0,
            market_cap_millions=100.0,
        )
        assert mispricing is not None
        assert mispricing.mispricing == pytest.approx(0.5, abs=1e-9)

    def test_market_mispricing_none_when_market_cap_missing(self):
        mispricing = compute_market_mispricing(
            model_rnpv_millions=150.0,
            market_cap_millions=None,
        )
        assert mispricing is None

    def test_market_mispricing_none_when_market_cap_non_positive(self):
        mispricing = compute_market_mispricing(
            model_rnpv_millions=150.0,
            market_cap_millions=0.0,
        )
        assert mispricing is None


class TestStoredSnapshotBacksolve:
    def test_compute_implied_success_probability_from_stored_snapshot(self):
        implied = compute_implied_success_probability(
            model_rnpv_millions=150.0,
            market_cap_millions=100.0,
            model_pos=0.40,
        )
        assert implied == pytest.approx(0.2667, abs=1e-4)

    def test_build_market_expectation_from_snapshot_populates_core_fields(self):
        expectation = build_market_expectation_from_snapshot(
            asset_id="asset-1",
            ticker="TEST",
            model_rnpv_millions=150.0,
            market_cap_millions=100.0,
            model_pos=0.40,
            expectation_date=date(2024, 6, 15),
        )
        assert expectation.model_rnpv_millions == 150.0
        assert expectation.market_cap_millions == 100.0
        assert expectation.mispricing == pytest.approx(0.5, abs=1e-6)
        assert expectation.implied_success_probability == pytest.approx(0.2667, abs=1e-4)
        assert expectation.pos_gap == pytest.approx(-0.1333, abs=1e-4)

    def test_estimator_compute_from_snapshot_uses_db_only_math(self):
        expectation = _ESTIMATOR.compute_from_snapshot(
            asset_id="asset-1",
            ticker="TEST",
            model_rnpv_millions=240.0,
            market_cap_millions=120.0,
            model_pos=0.50,
            expectation_date=date(2024, 6, 15),
        )
        assert expectation.implied_pos == pytest.approx(0.25, abs=1e-4)
        assert expectation.implied_success_probability == pytest.approx(0.25, abs=1e-4)
        assert expectation.pos_gap == pytest.approx(-0.25, abs=1e-4)
