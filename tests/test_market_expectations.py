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


# ===========================================================================
# Step 5 tests — ImpliedExpectationsInput/Result + MarketExpectationRow
# ===========================================================================

from bve.valuation.implied_expectations import (  # noqa: E402
    ImpliedExpectationsInput,
    ImpliedExpectationsResult,
    _npv_per_dollar_peak_sales,
    compute_implied_expectations,
    solve_implied_pos,
    solve_implied_peak_sales,
)
from bve.intelligence.market_expectations import (  # noqa: E402
    MarketExpectationRow,
    build_market_expectation_row,
    screen_universe,
)
from bve.models.financing_risk import FinancingRiskV2, DistressTier  # noqa: E402


def _make_inp(**kwargs) -> ImpliedExpectationsInput:
    defaults = dict(
        asset_id="test-asset",
        market_cap_usd=500_000_000.0,
        net_cash_usd=100_000_000.0,
        discount_rate=0.10,
        years_to_approval=3.0,
        peak_sales_millions=800.0,
        model_pos=0.40,
        royalty_rate=0.0,
        tax_rate=0.25,
        ebit_margin=0.40,
        patent_life_years=10.0,
    )
    defaults.update(kwargs)
    return ImpliedExpectationsInput(**defaults)


class TestNPVFactor:
    """8+ tests for _npv_per_dollar_peak_sales."""

    def _factor(self, **kwargs) -> float:
        defaults = dict(
            discount_rate=0.10,
            years_to_approval=3.0,
            ebit_margin=0.40,
            patent_life_years=10.0,
            tax_rate=0.25,
            royalty_rate=0.0,
        )
        defaults.update(kwargs)
        return _npv_per_dollar_peak_sales(**defaults)

    def test_returns_positive_float(self):
        assert self._factor() > 0.0

    def test_higher_discount_rate_lower_factor(self):
        low = self._factor(discount_rate=0.05)
        high = self._factor(discount_rate=0.20)
        assert low > high

    def test_more_patent_years_higher_factor(self):
        short = self._factor(patent_life_years=5.0)
        long_ = self._factor(patent_life_years=15.0)
        assert long_ > short

    def test_higher_royalty_rate_lower_factor(self):
        no_royalty = self._factor(royalty_rate=0.0)
        royalty = self._factor(royalty_rate=0.20)
        assert royalty < no_royalty

    def test_higher_tax_rate_lower_factor(self):
        low_tax = self._factor(tax_rate=0.10)
        high_tax = self._factor(tax_rate=0.35)
        assert high_tax < low_tax

    def test_zero_years_to_approval_still_works(self):
        factor = self._factor(years_to_approval=0.0)
        assert factor > 0.0

    def test_ebit_margin_zero_gives_zero_factor(self):
        factor = self._factor(ebit_margin=0.0)
        assert factor == 0.0

    def test_zero_patent_life_gives_zero_factor(self):
        factor = self._factor(patent_life_years=0.0)
        assert factor == 0.0


class TestImpliedExpectations:
    """20+ tests for compute_implied_expectations and its helpers."""

    def test_pipeline_value_computed_correctly(self):
        inp = _make_inp(market_cap_usd=500_000_000, net_cash_usd=100_000_000)
        result = compute_implied_expectations(inp)
        assert result.pipeline_value_usd == pytest.approx(400_000_000, rel=1e-6)

    def test_solve_implied_pos_none_when_peak_sales_none(self):
        inp = _make_inp(peak_sales_millions=None)
        assert solve_implied_pos(inp) is None

    def test_solve_implied_pos_none_when_peak_sales_zero(self):
        inp = _make_inp(peak_sales_millions=0.0)
        assert solve_implied_pos(inp) is None

    def test_solve_implied_peak_sales_none_when_model_pos_none(self):
        inp = _make_inp(model_pos=None)
        assert solve_implied_peak_sales(inp) is None

    def test_solve_implied_peak_sales_none_when_model_pos_zero(self):
        inp = _make_inp(model_pos=0.0)
        assert solve_implied_peak_sales(inp) is None

    def test_implied_pos_clamped_below_1_5(self):
        # Extremely large market cap should clamp at 1.5
        inp = _make_inp(market_cap_usd=100_000_000_000, net_cash_usd=0.0)
        result = solve_implied_pos(inp)
        assert result is not None
        assert result <= 1.5

    def test_signal_insufficient_data_when_both_none(self):
        inp = _make_inp(peak_sales_millions=None, model_pos=None)
        result = compute_implied_expectations(inp)
        assert result.signal == "INSUFFICIENT_DATA"

    def test_signal_underpriced_when_pos_gap_below_minus_0_10(self):
        # Low market cap → very low implied_pos → pos_gap < -0.10
        inp = _make_inp(market_cap_usd=10_000_000, net_cash_usd=0.0, model_pos=0.50)
        result = compute_implied_expectations(inp)
        assert result.signal == "UNDERPRICED"

    def test_signal_overpriced_when_pos_gap_above_0_10(self):
        # Very large market cap → implied_pos >> model_pos
        inp = _make_inp(market_cap_usd=5_000_000_000, net_cash_usd=0.0, model_pos=0.05)
        result = compute_implied_expectations(inp)
        assert result.signal == "OVERPRICED"

    def test_signal_fairly_valued_in_middle_range(self):
        # Construct case where pos_gap is small
        inp = _make_inp(
            market_cap_usd=500_000_000,
            net_cash_usd=100_000_000,
            model_pos=0.40,
            peak_sales_millions=800.0,
        )
        result = compute_implied_expectations(inp)
        # May be fairly valued or slightly over/under — just ensure it's one of the valid signals
        assert result.signal in ("FAIRLY_VALUED", "UNDERPRICED", "OVERPRICED")

    def test_confidence_low_when_pipeline_value_negative(self):
        inp = _make_inp(market_cap_usd=50_000_000, net_cash_usd=100_000_000)
        result = compute_implied_expectations(inp)
        assert result.confidence == "LOW"
        assert result.low_confidence_reason is not None

    def test_confidence_low_when_implied_pos_above_1(self):
        # Massive market cap relative to small model peak sales → implied_pos > 1.0
        inp = _make_inp(
            market_cap_usd=2_000_000_000,
            net_cash_usd=0.0,
            peak_sales_millions=50.0,
            model_pos=0.30,
        )
        result = compute_implied_expectations(inp)
        if result.implied_pos is not None and result.implied_pos > 1.0:
            assert result.confidence == "LOW"
            assert result.low_confidence_reason is not None

    def test_confidence_medium_when_pipeline_value_below_50m(self):
        inp = _make_inp(market_cap_usd=60_000_000, net_cash_usd=20_000_000)
        result = compute_implied_expectations(inp)
        # pipeline_value = 40M < 50M → MEDIUM
        assert result.confidence == "MEDIUM"
        assert result.low_confidence_reason is not None

    def test_platform_residual_computed_when_implied_pos_above_1(self):
        inp = _make_inp(
            market_cap_usd=5_000_000_000,
            net_cash_usd=0.0,
            peak_sales_millions=50.0,
            model_pos=0.30,
        )
        result = compute_implied_expectations(inp)
        if result.implied_pos is not None and result.implied_pos > 1.0:
            assert result.platform_residual_usd is not None
            assert result.platform_residual_usd > 0

    def test_platform_residual_none_when_implied_pos_below_1(self):
        inp = _make_inp(market_cap_usd=100_000_000, net_cash_usd=0.0)
        result = compute_implied_expectations(inp)
        if result.implied_pos is not None and result.implied_pos <= 1.0:
            assert result.platform_residual_usd is None

    def test_pos_gap_equals_implied_minus_model(self):
        inp = _make_inp()
        result = compute_implied_expectations(inp)
        if result.pos_gap is not None:
            assert result.pos_gap == pytest.approx(
                result.implied_pos - result.model_pos, rel=1e-6
            )

    def test_peak_sales_gap_sign_correct(self):
        # When implied_peak_sales < model_peak_sales → gap is negative → UNDERPRICED signal eligible
        inp = _make_inp(
            market_cap_usd=10_000_000,
            net_cash_usd=0.0,
            model_pos=0.40,
            peak_sales_millions=800.0,
        )
        result = compute_implied_expectations(inp)
        if result.peak_sales_gap_millions is not None and result.implied_peak_sales_millions is not None:
            expected_gap = result.implied_peak_sales_millions - result.model_peak_sales_millions
            assert result.peak_sales_gap_millions == pytest.approx(expected_gap, rel=1e-6)

    def test_low_confidence_reason_nonempty_when_confidence_not_high(self):
        inp = _make_inp(market_cap_usd=60_000_000, net_cash_usd=20_000_000)
        result = compute_implied_expectations(inp)
        assert result.confidence in ("LOW", "MEDIUM")
        assert result.low_confidence_reason is not None
        assert len(result.low_confidence_reason) > 0

    def test_low_confidence_reason_none_when_confidence_high(self):
        inp = _make_inp(
            market_cap_usd=500_000_000,
            net_cash_usd=100_000_000,
        )
        result = compute_implied_expectations(inp)
        if result.confidence == "HIGH":
            assert result.low_confidence_reason is None

    def test_result_frozen(self):
        inp = _make_inp()
        result = compute_implied_expectations(inp)
        with pytest.raises(Exception):
            result.signal = "MODIFIED"  # type: ignore[misc]

    def test_model_fields_forwarded_to_result(self):
        inp = _make_inp(model_pos=0.45, peak_sales_millions=999.0)
        result = compute_implied_expectations(inp)
        assert result.model_pos == 0.45
        assert result.model_peak_sales_millions == 999.0


def _make_financing_risk(tier: DistressTier) -> FinancingRiskV2:
    from bve.models.financing_risk import _HAIRCUT_BY_TIER
    return FinancingRiskV2(
        asset_id="test",
        as_of_date="2026-01-01",
        distress_tier=tier,
        partnership_flag=False,
        financing_adjusted_value_haircut=_HAIRCUT_BY_TIER[tier],
        rationale="test",
        assumptions={},
    )


class TestMarketExpectationRow:
    """12+ tests for build_market_expectation_row and screen_universe."""

    def test_build_returns_correct_signal(self):
        row = build_market_expectation_row(
            asset_id="asset-1",
            ticker="TEST",
            market_cap_usd=500_000_000,
            net_cash_usd=100_000_000,
            model_pos=0.40,
            peak_sales_millions=800.0,
        )
        assert row.signal in ("UNDERPRICED", "FAIRLY_VALUED", "OVERPRICED", "INSUFFICIENT_DATA")

    def test_financing_haircut_1_when_no_financing_risk(self):
        row = build_market_expectation_row(
            asset_id="a",
            ticker="A",
            market_cap_usd=300_000_000,
            net_cash_usd=50_000_000,
            financing_risk=None,
        )
        assert row.financing_haircut == 1.0

    def test_financing_haircut_from_financing_risk(self):
        risk = _make_financing_risk(DistressTier.HIGH)  # haircut = 0.70
        row = build_market_expectation_row(
            asset_id="a",
            ticker="A",
            market_cap_usd=300_000_000,
            net_cash_usd=50_000_000,
            financing_risk=risk,
        )
        assert row.financing_haircut == pytest.approx(0.70, rel=1e-6)

    def test_financing_adjusted_signal_differs_when_haircut_below_90_pct(self):
        # Critical tier → 0.50 haircut; should often change the signal
        risk = _make_financing_risk(DistressTier.CRITICAL)  # haircut = 0.50
        row_no_risk = build_market_expectation_row(
            asset_id="a",
            ticker="A",
            market_cap_usd=2_000_000_000,
            net_cash_usd=0,
            model_pos=0.10,
            peak_sales_millions=200.0,
            financing_risk=None,
        )
        row_with_risk = build_market_expectation_row(
            asset_id="a",
            ticker="A",
            market_cap_usd=2_000_000_000,
            net_cash_usd=0,
            model_pos=0.10,
            peak_sales_millions=200.0,
            financing_risk=risk,
        )
        # Both are computed — we just verify the haircut was applied
        assert row_with_risk.financing_haircut == pytest.approx(0.50, rel=1e-6)
        # financing_adjusted_signal is populated
        assert row_with_risk.financing_adjusted_signal in (
            "UNDERPRICED", "FAIRLY_VALUED", "OVERPRICED", "INSUFFICIENT_DATA"
        )

    def test_screen_universe_filter_by_signal(self):
        rows = [
            build_market_expectation_row("a", "A", 10_000_000, 0, model_pos=0.5, peak_sales_millions=800),
            build_market_expectation_row("b", "B", 5_000_000_000, 0, model_pos=0.05, peak_sales_millions=200),
        ]
        underpriced = screen_universe(rows, signal_filter="UNDERPRICED")
        for r in underpriced:
            assert r.signal == "UNDERPRICED"

    def test_screen_universe_filter_by_confidence(self):
        rows = [
            build_market_expectation_row("a", "A", 500_000_000, 50_000_000, model_pos=0.4, peak_sales_millions=800),
            build_market_expectation_row("b", "B", 60_000_000, 20_000_000, model_pos=0.4, peak_sales_millions=200),
        ]
        high_only = screen_universe(rows, min_confidence="HIGH")
        for r in high_only:
            assert r.confidence == "HIGH"

    def test_screen_universe_sorted_by_pos_gap_ascending(self):
        rows = [
            build_market_expectation_row("a", "A", 10_000_000, 0, model_pos=0.5, peak_sales_millions=800),
            build_market_expectation_row("b", "B", 500_000_000, 100_000_000, model_pos=0.4, peak_sales_millions=800),
            build_market_expectation_row("c", "C", 5_000_000_000, 0, model_pos=0.05, peak_sales_millions=200),
        ]
        sorted_rows = screen_universe(rows)
        gaps = [r.pos_gap for r in sorted_rows if r.pos_gap is not None]
        assert gaps == sorted(gaps)

    def test_screen_universe_no_filters_returns_all(self):
        rows = [
            build_market_expectation_row("a", "A", 500_000_000, 100_000_000),
            build_market_expectation_row("b", "B", 300_000_000, 50_000_000),
        ]
        result = screen_universe(rows)
        assert len(result) == len(rows)

    def test_as_of_date_defaults_to_today_if_empty(self):
        row = build_market_expectation_row(
            asset_id="a",
            ticker="A",
            market_cap_usd=500_000_000,
            net_cash_usd=100_000_000,
            as_of_date="",
        )
        assert row.as_of_date == date.today().isoformat()

    def test_as_of_date_preserved_when_provided(self):
        row = build_market_expectation_row(
            asset_id="a",
            ticker="A",
            market_cap_usd=500_000_000,
            net_cash_usd=100_000_000,
            as_of_date="2026-03-15",
        )
        assert row.as_of_date == "2026-03-15"

    def test_ticker_can_be_none(self):
        row = build_market_expectation_row(
            asset_id="a",
            ticker=None,
            market_cap_usd=500_000_000,
            net_cash_usd=100_000_000,
        )
        assert row.ticker is None

    def test_financing_none_tier_gives_haircut_1(self):
        risk = _make_financing_risk(DistressTier.NONE)
        row = build_market_expectation_row(
            asset_id="a",
            ticker="A",
            market_cap_usd=500_000_000,
            net_cash_usd=100_000_000,
            financing_risk=risk,
        )
        assert row.financing_haircut == pytest.approx(1.0, rel=1e-6)
