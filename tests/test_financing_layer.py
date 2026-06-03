"""
Tests for the Step 4 financing + dilution layer.

Covers:
  - TestFinancingRisk    (20+ tests)
  - TestDilutionModel    (12+ tests)
  - TestRunwayForecast   (15+ tests)
"""

from __future__ import annotations

import math
from datetime import date

import pytest

from bve.models.dilution_model import (
    DilutionAnalysis,
    DilutionScenarioV2,
    compute_dilution_scenarios,
)
from bve.models.financing_risk import (
    DistressTier,
    FinancingRiskV2,
    compute_financing_risk,
)
from bve.models.runway_forecast import (
    BurnRateEstimate,
    RunwayForecastV2,
    compute_runway,
    estimate_burn_rate,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _base_risk(**overrides) -> FinancingRiskV2:
    """A typical medium-risk scenario that can be overridden."""
    kwargs = dict(
        cash_usd=24_000_000,
        monthly_burn_usd=2_000_000,
        market_cap_usd=150_000_000,
        catalyst_months_away=12.0,
        asset_id="asset-test",
        as_of_date="2026-01-01",
    )
    kwargs.update(overrides)
    return compute_financing_risk(**kwargs)


# ===========================================================================
# TestFinancingRisk
# ===========================================================================


class TestFinancingRisk:

    # --- Basic runway calculation ---

    def test_runway_calculation_correct(self):
        risk = compute_financing_risk(
            cash_usd=60_000_000,
            monthly_burn_usd=5_000_000,
            market_cap_usd=300_000_000,
            catalyst_months_away=None,
        )
        assert risk.runway_months == pytest.approx(12.0)

    def test_runway_zero_burn_returns_none(self):
        risk = compute_financing_risk(
            cash_usd=60_000_000,
            monthly_burn_usd=0,
            market_cap_usd=300_000_000,
            catalyst_months_away=None,
        )
        assert risk.runway_months is None

    # --- p_pre_catalyst_raise threshold bands ---

    def test_p_pre_catalyst_plenty_of_cash(self):
        # runway > catalyst * 1.5 → 0.05
        risk = compute_financing_risk(
            cash_usd=48_000_000,   # 24 months runway
            monthly_burn_usd=2_000_000,
            market_cap_usd=200_000_000,
            catalyst_months_away=12.0,  # 24 > 18 → plenty
        )
        assert risk.p_pre_catalyst_raise == pytest.approx(0.05)

    def test_p_pre_catalyst_comfortable(self):
        # runway between 1.2x and 1.5x → 0.30
        risk = compute_financing_risk(
            cash_usd=30_000_000,   # 15 months runway
            monthly_burn_usd=2_000_000,
            market_cap_usd=200_000_000,
            catalyst_months_away=12.0,  # 15 > 14.4 but ≤ 18 → 0.30
        )
        assert risk.p_pre_catalyst_raise == pytest.approx(0.30)

    def test_p_pre_catalyst_moderate(self):
        # runway between 0.8x and 1.2x → 0.60
        risk = compute_financing_risk(
            cash_usd=22_000_000,   # 11 months runway
            monthly_burn_usd=2_000_000,
            market_cap_usd=200_000_000,
            catalyst_months_away=12.0,  # 11 > 9.6 but ≤ 14.4 → 0.60
        )
        assert risk.p_pre_catalyst_raise == pytest.approx(0.60)

    def test_p_pre_catalyst_tight(self):
        # runway between 0.5x and 0.8x → 0.85
        risk = compute_financing_risk(
            cash_usd=14_000_000,   # 7 months runway
            monthly_burn_usd=2_000_000,
            market_cap_usd=200_000_000,
            catalyst_months_away=12.0,  # 7 > 6 but ≤ 9.6 → 0.85
        )
        assert risk.p_pre_catalyst_raise == pytest.approx(0.85)

    def test_p_pre_catalyst_critical(self):
        # runway ≤ 0.5x → 0.95
        risk = compute_financing_risk(
            cash_usd=10_000_000,   # 5 months runway
            monthly_burn_usd=2_000_000,
            market_cap_usd=200_000_000,
            catalyst_months_away=12.0,  # 5 ≤ 6 → 0.95
        )
        assert risk.p_pre_catalyst_raise == pytest.approx(0.95)

    def test_p_pre_catalyst_none_when_no_catalyst(self):
        risk = compute_financing_risk(
            cash_usd=24_000_000,
            monthly_burn_usd=2_000_000,
            market_cap_usd=None,
            catalyst_months_away=None,
        )
        assert risk.p_pre_catalyst_raise is None

    # --- Dilution estimates ---

    def test_dilution_low_mid_high_scaling(self):
        risk = compute_financing_risk(
            cash_usd=0,
            monthly_burn_usd=1_000_000,
            market_cap_usd=100_000_000,
            catalyst_months_away=10.0,
        )
        # capital_needed = 10M, market_cap = 100M → raw = 0.10
        assert risk.dilution_low_pct == pytest.approx(0.10 * 0.85 * 100, rel=1e-6)
        assert risk.dilution_mid_pct == pytest.approx(0.10 * 1.10 * 100, rel=1e-6)
        assert risk.dilution_high_pct == pytest.approx(0.10 * 1.40 * 100, rel=1e-6)

    def test_dilution_capped_at_200(self):
        # capital = $400M, market_cap = $100M → raw = 4.0 → all > 200
        risk = compute_financing_risk(
            cash_usd=0,
            monthly_burn_usd=1_000_000,
            market_cap_usd=100_000_000,
            catalyst_months_away=None,
            trial_cost_remaining_usd=400_000_000,
        )
        assert risk.dilution_low_pct == pytest.approx(200.0)
        assert risk.dilution_mid_pct == pytest.approx(200.0)
        assert risk.dilution_high_pct == pytest.approx(200.0)

    def test_dilution_none_when_no_market_cap(self):
        risk = compute_financing_risk(
            cash_usd=10_000_000,
            monthly_burn_usd=2_000_000,
            market_cap_usd=None,
            catalyst_months_away=6.0,
        )
        assert risk.dilution_low_pct is None
        assert risk.dilution_mid_pct is None
        assert risk.dilution_high_pct is None

    # --- Distress tier ---

    def test_distress_tier_critical_when_runway_under_6(self):
        risk = compute_financing_risk(
            cash_usd=10_000_000,
            monthly_burn_usd=4_000_000,  # 2.5 months runway
            market_cap_usd=200_000_000,
            catalyst_months_away=None,
        )
        assert risk.distress_tier == DistressTier.CRITICAL

    def test_distress_tier_high_when_runway_6_to_12(self):
        risk = compute_financing_risk(
            cash_usd=18_000_000,
            monthly_burn_usd=2_000_000,  # 9 months runway
            market_cap_usd=500_000_000,
            catalyst_months_away=None,
        )
        assert risk.distress_tier == DistressTier.HIGH

    def test_distress_tier_medium_when_runway_12_to_18(self):
        risk = compute_financing_risk(
            cash_usd=30_000_000,
            monthly_burn_usd=2_000_000,  # 15 months runway
            market_cap_usd=500_000_000,
            catalyst_months_away=None,
        )
        assert risk.distress_tier == DistressTier.MEDIUM

    def test_distress_tier_low_when_runway_18_to_30(self):
        risk = compute_financing_risk(
            cash_usd=48_000_000,
            monthly_burn_usd=2_000_000,  # 24 months runway
            market_cap_usd=500_000_000,
            catalyst_months_away=None,
        )
        assert risk.distress_tier == DistressTier.LOW

    def test_distress_tier_none_when_runway_over_30(self):
        risk = compute_financing_risk(
            cash_usd=80_000_000,
            monthly_burn_usd=2_000_000,  # 40 months runway
            market_cap_usd=500_000_000,
            catalyst_months_away=None,
        )
        assert risk.distress_tier == DistressTier.NONE

    def test_distress_tier_medium_when_runway_is_none(self):
        risk = compute_financing_risk(
            cash_usd=50_000_000,
            monthly_burn_usd=0,  # forces runway_months = None
            market_cap_usd=200_000_000,
            catalyst_months_away=None,
        )
        assert risk.distress_tier == DistressTier.MEDIUM

    # --- Partnership flag ---

    def test_partnership_flag_true_when_distressed_small_cap(self):
        risk = compute_financing_risk(
            cash_usd=5_000_000,
            monthly_burn_usd=2_000_000,  # 2.5mo → CRITICAL
            market_cap_usd=200_000_000,
            catalyst_months_away=None,
        )
        assert risk.partnership_flag is True

    def test_partnership_flag_false_when_large_cap(self):
        risk = compute_financing_risk(
            cash_usd=5_000_000,
            monthly_burn_usd=2_000_000,  # CRITICAL
            market_cap_usd=700_000_000,  # > 500M → no flag
            catalyst_months_away=None,
        )
        assert risk.partnership_flag is False

    def test_partnership_flag_false_when_low_distress(self):
        risk = compute_financing_risk(
            cash_usd=80_000_000,
            monthly_burn_usd=2_000_000,  # 40mo → NONE
            market_cap_usd=200_000_000,
            catalyst_months_away=None,
        )
        assert risk.partnership_flag is False

    # --- Value haircut ---

    def test_haircut_none_tier(self):
        risk = compute_financing_risk(
            cash_usd=100_000_000,
            monthly_burn_usd=2_000_000,  # 50mo → NONE
            market_cap_usd=500_000_000,
            catalyst_months_away=None,
        )
        assert risk.financing_adjusted_value_haircut == pytest.approx(1.00)

    def test_haircut_critical_tier(self):
        risk = compute_financing_risk(
            cash_usd=5_000_000,
            monthly_burn_usd=2_000_000,  # 2.5mo → CRITICAL
            market_cap_usd=200_000_000,
            catalyst_months_away=None,
        )
        assert risk.financing_adjusted_value_haircut == pytest.approx(0.50)

    def test_haircut_high_tier(self):
        risk = compute_financing_risk(
            cash_usd=18_000_000,
            monthly_burn_usd=2_000_000,  # 9mo → HIGH
            market_cap_usd=500_000_000,
            catalyst_months_away=None,
        )
        assert risk.financing_adjusted_value_haircut == pytest.approx(0.70)

    # --- Capital needed ---

    def test_capital_needed_when_trial_cost_provided(self):
        risk = compute_financing_risk(
            cash_usd=30_000_000,
            monthly_burn_usd=2_000_000,
            market_cap_usd=200_000_000,
            catalyst_months_away=None,
            trial_cost_remaining_usd=80_000_000,
        )
        assert risk.capital_needed_usd == pytest.approx(50_000_000)

    def test_capital_needed_when_only_catalyst_months_provided(self):
        risk = compute_financing_risk(
            cash_usd=10_000_000,
            monthly_burn_usd=2_000_000,
            market_cap_usd=200_000_000,
            catalyst_months_away=10.0,
        )
        # 2M * 10 - 10M = 10M
        assert risk.capital_needed_usd == pytest.approx(10_000_000)

    def test_capital_needed_none_when_neither_provided(self):
        risk = compute_financing_risk(
            cash_usd=10_000_000,
            monthly_burn_usd=2_000_000,
            market_cap_usd=None,
            catalyst_months_away=None,
        )
        assert risk.capital_needed_usd is None

    def test_capital_needed_floored_at_zero(self):
        # cash > trial cost → no capital needed
        risk = compute_financing_risk(
            cash_usd=100_000_000,
            monthly_burn_usd=2_000_000,
            market_cap_usd=200_000_000,
            catalyst_months_away=None,
            trial_cost_remaining_usd=50_000_000,
        )
        assert risk.capital_needed_usd == pytest.approx(0.0)

    # --- Rationale and assumptions ---

    def test_rationale_is_nonempty_string(self):
        risk = _base_risk()
        assert isinstance(risk.rationale, str)
        assert len(risk.rationale) > 0

    def test_assumptions_contains_expected_keys(self):
        risk = _base_risk()
        assert "monthly_burn_usd" in risk.assumptions
        assert "cash_usd" in risk.assumptions
        assert "runway_months" in risk.assumptions

    def test_model_is_frozen(self):
        risk = _base_risk()
        with pytest.raises(Exception):
            risk.rationale = "mutated"  # type: ignore[misc]


# ===========================================================================
# TestDilutionModel
# ===========================================================================


class TestDilutionModel:

    def _analysis(self, capital: float = 20_000_000) -> DilutionAnalysis:
        return compute_dilution_scenarios(
            asset_id="asset-test",
            current_shares=100_000_000,
            current_price=10.0,
            capital_needed_usd=capital,
        )

    def test_three_scenarios_returned(self):
        analysis = self._analysis()
        assert len(analysis.scenarios) == 3

    def test_scenarios_labeled_correctly(self):
        analysis = self._analysis()
        labels = [s.label for s in analysis.scenarios]
        assert labels == ["bull", "base", "bear"]

    def test_bull_has_higher_price_than_base(self):
        analysis = self._analysis()
        bull = next(s for s in analysis.scenarios if s.label == "bull")
        base = next(s for s in analysis.scenarios if s.label == "base")
        assert bull.price_per_share > base.price_per_share

    def test_bear_has_lower_price_than_base(self):
        analysis = self._analysis()
        base = next(s for s in analysis.scenarios if s.label == "base")
        bear = next(s for s in analysis.scenarios if s.label == "bear")
        assert bear.price_per_share < base.price_per_share

    def test_bull_has_lower_dilution_than_base(self):
        analysis = self._analysis()
        bull = next(s for s in analysis.scenarios if s.label == "bull")
        base = next(s for s in analysis.scenarios if s.label == "base")
        assert bull.dilution_pct < base.dilution_pct

    def test_bear_has_higher_dilution_than_base(self):
        analysis = self._analysis()
        base = next(s for s in analysis.scenarios if s.label == "base")
        bear = next(s for s in analysis.scenarios if s.label == "bear")
        assert bear.dilution_pct > base.dilution_pct

    def test_dilution_pct_formula(self):
        """dilution_pct = new_shares / (shares_before + new_shares) * 100"""
        analysis = self._analysis()
        for scenario in analysis.scenarios:
            total = scenario.shares_before + scenario.new_shares_issued
            expected = scenario.new_shares_issued / total * 100.0
            assert scenario.dilution_pct == pytest.approx(expected, rel=1e-6)

    def test_ownership_pct_plus_dilution_pct_sums_to_100(self):
        analysis = self._analysis()
        for scenario in analysis.scenarios:
            total = scenario.post_raise_ownership_pct + scenario.dilution_pct
            assert total == pytest.approx(100.0, abs=1e-9)

    def test_weighted_dilution_between_bull_and_bear(self):
        analysis = self._analysis()
        bull = next(s for s in analysis.scenarios if s.label == "bull")
        bear = next(s for s in analysis.scenarios if s.label == "bear")
        assert bull.dilution_pct <= analysis.weighted_dilution_pct <= bear.dilution_pct

    def test_weighted_dilution_formula(self):
        analysis = self._analysis()
        bull = next(s for s in analysis.scenarios if s.label == "bull")
        base = next(s for s in analysis.scenarios if s.label == "base")
        bear = next(s for s in analysis.scenarios if s.label == "bear")
        expected = 0.25 * bull.dilution_pct + 0.50 * base.dilution_pct + 0.25 * bear.dilution_pct
        assert analysis.weighted_dilution_pct == pytest.approx(expected, rel=1e-6)

    def test_zero_capital_results_in_zero_dilution(self):
        analysis = compute_dilution_scenarios(
            asset_id="asset-zero",
            current_shares=100_000_000,
            current_price=10.0,
            capital_needed_usd=0.0,
        )
        for scenario in analysis.scenarios:
            assert scenario.dilution_pct == pytest.approx(0.0)
            assert scenario.new_shares_issued == pytest.approx(0.0)

    def test_large_raise_results_in_high_dilution(self):
        analysis = compute_dilution_scenarios(
            asset_id="asset-big",
            current_shares=10_000_000,
            current_price=5.0,
            capital_needed_usd=500_000_000,  # 500M raise on $50M market cap
        )
        bear = next(s for s in analysis.scenarios if s.label == "bear")
        assert bear.dilution_pct > 50.0

    def test_dilution_analysis_is_frozen(self):
        analysis = self._analysis()
        with pytest.raises(Exception):
            analysis.current_price = 999.0  # type: ignore[misc]


# ===========================================================================
# TestRunwayForecast
# ===========================================================================


class TestRunwayForecast:

    # --- estimate_burn_rate ---

    def test_direct_source_wins_over_others(self):
        burn = estimate_burn_rate(
            direct_monthly_usd=1_000_000,
            rd_expense_annual_usd=18_000_000,
            opex_annual_usd=24_000_000,
        )
        assert burn.source == "direct"
        assert burn.monthly_burn_usd == pytest.approx(1_000_000)
        assert burn.confidence == pytest.approx(0.90)

    def test_rd_expense_grossed_up(self):
        # Annual R&D = 12M → monthly = 1M, grossed up by 1/0.65
        burn = estimate_burn_rate(rd_expense_annual_usd=12_000_000)
        expected = (12_000_000 / 12.0) / 0.65
        assert burn.monthly_burn_usd == pytest.approx(expected, rel=1e-6)
        assert burn.source == "rd_expense_annualized"
        assert burn.confidence == pytest.approx(0.75)

    def test_opex_fallback(self):
        burn = estimate_burn_rate(opex_annual_usd=24_000_000)
        assert burn.monthly_burn_usd == pytest.approx(2_000_000)
        assert burn.source == "opex_estimate"
        assert burn.confidence == pytest.approx(0.60)

    def test_estimate_burn_rate_raises_when_no_inputs(self):
        with pytest.raises(ValueError, match="At least one burn rate input required"):
            estimate_burn_rate()

    def test_annualized_burn_equals_monthly_times_12(self):
        burn = estimate_burn_rate(direct_monthly_usd=2_500_000)
        assert burn.annualized_burn_usd == pytest.approx(burn.monthly_burn_usd * 12.0)

    # --- compute_runway ---

    def test_runway_months_correct(self):
        burn = estimate_burn_rate(direct_monthly_usd=2_000_000)
        forecast = compute_runway("a1", 24_000_000, burn, "2026-01-01")
        assert forecast.runway_months == pytest.approx(12.0)

    def test_runway_risk_critical_when_under_6_months(self):
        burn = estimate_burn_rate(direct_monthly_usd=5_000_000)
        forecast = compute_runway("a1", 10_000_000, burn)  # 2 months
        assert forecast.runway_risk == "critical"

    def test_runway_risk_high_when_6_to_12_months(self):
        burn = estimate_burn_rate(direct_monthly_usd=2_000_000)
        forecast = compute_runway("a1", 18_000_000, burn)  # 9 months
        assert forecast.runway_risk == "high"

    def test_runway_risk_medium_when_12_to_18_months(self):
        burn = estimate_burn_rate(direct_monthly_usd=2_000_000)
        forecast = compute_runway("a1", 30_000_000, burn)  # 15 months
        assert forecast.runway_risk == "medium"

    def test_runway_risk_low_when_18_to_30_months(self):
        burn = estimate_burn_rate(direct_monthly_usd=2_000_000)
        forecast = compute_runway("a1", 48_000_000, burn)  # 24 months
        assert forecast.runway_risk == "low"

    def test_runway_risk_comfortable_when_over_30_months(self):
        burn = estimate_burn_rate(direct_monthly_usd=2_000_000)
        forecast = compute_runway("a1", 80_000_000, burn)  # 40 months
        assert forecast.runway_risk == "comfortable"

    def test_next_financing_needed_3_months_before_runway_date(self):
        burn = estimate_burn_rate(direct_monthly_usd=2_000_000)
        forecast = compute_runway("a1", 24_000_000, burn, "2026-01-01")
        # runway = 12 months → runway_date ~2027-01-01 → financing by ~2026-10-01
        runway_dt = date.fromisoformat(forecast.runway_date)
        fin_dt = date.fromisoformat(forecast.next_financing_needed_by)
        diff_days = (runway_dt - fin_dt).days
        # Should be approximately 3 months (~91 days); allow ±5 days
        assert 85 <= diff_days <= 97

    def test_next_financing_needed_is_none_when_runway_under_3_months(self):
        burn = estimate_burn_rate(direct_monthly_usd=10_000_000)
        forecast = compute_runway("a1", 20_000_000, burn)  # 2 months
        assert forecast.next_financing_needed_by is None

    def test_runway_date_is_parseable_iso_string(self):
        burn = estimate_burn_rate(direct_monthly_usd=2_000_000)
        forecast = compute_runway("a1", 24_000_000, burn, "2026-01-01")
        # Should not raise
        parsed = date.fromisoformat(forecast.runway_date)
        assert parsed > date.fromisoformat("2026-01-01")

    def test_as_of_date_defaults_to_today(self):
        burn = estimate_burn_rate(direct_monthly_usd=2_000_000)
        forecast = compute_runway("a1", 24_000_000, burn)
        # as_of_date should equal today
        assert forecast.as_of_date == date.today().isoformat()

    def test_runway_forecast_is_frozen(self):
        burn = estimate_burn_rate(direct_monthly_usd=2_000_000)
        forecast = compute_runway("a1", 24_000_000, burn, "2026-01-01")
        with pytest.raises(Exception):
            forecast.runway_risk = "none"  # type: ignore[misc]

    def test_burn_rate_model_is_frozen(self):
        burn = estimate_burn_rate(direct_monthly_usd=2_000_000)
        with pytest.raises(Exception):
            burn.monthly_burn_usd = 999_999  # type: ignore[misc]

    def test_rd_expense_wins_over_opex_alone(self):
        burn = estimate_burn_rate(
            rd_expense_annual_usd=12_000_000,
            opex_annual_usd=24_000_000,
        )
        assert burn.source == "rd_expense_annualized"
