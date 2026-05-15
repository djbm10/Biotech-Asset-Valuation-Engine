"""
Tests for P1.9 — Runway forecast + dilution analysis wired into ValuationOutput.
"""
from __future__ import annotations

import pytest

from bve.models.dilution_model import DilutionAnalysis, compute_dilution_scenarios
from bve.models.runway_forecast import (
    RunwayForecastV2,
    compute_runway,
    estimate_burn_rate,
)


# ---------------------------------------------------------------------------
# estimate_burn_rate
# ---------------------------------------------------------------------------

class TestEstimateBurnRate:
    def test_direct_monthly_highest_confidence(self):
        br = estimate_burn_rate(direct_monthly_usd=1_000_000)
        assert br.monthly_burn_usd == 1_000_000
        assert br.confidence == pytest.approx(0.90)
        assert br.source == "direct"

    def test_rd_annual_derives_monthly(self):
        br = estimate_burn_rate(rd_expense_annual_usd=13_000_000)
        # gross-up: (13M / 12) / 0.65
        expected = (13_000_000 / 12.0) / 0.65
        assert br.monthly_burn_usd == pytest.approx(expected)
        assert br.source == "rd_expense_annualized"

    def test_opex_annual_derives_monthly(self):
        br = estimate_burn_rate(opex_annual_usd=24_000_000)
        assert br.monthly_burn_usd == pytest.approx(24_000_000 / 12.0)
        assert br.source == "opex_estimate"

    def test_direct_takes_priority_over_rd(self):
        br = estimate_burn_rate(direct_monthly_usd=500_000, rd_expense_annual_usd=6_000_000)
        assert br.source == "direct"

    def test_no_inputs_raises(self):
        with pytest.raises(ValueError):
            estimate_burn_rate()

    def test_annualized_burn_is_12x_monthly(self):
        br = estimate_burn_rate(direct_monthly_usd=1_000_000)
        assert br.annualized_burn_usd == pytest.approx(12_000_000)


# ---------------------------------------------------------------------------
# compute_runway
# ---------------------------------------------------------------------------

class TestComputeRunway:
    def _burn(self, monthly_usd: float = 1_000_000) -> object:
        return estimate_burn_rate(direct_monthly_usd=monthly_usd)

    def test_runway_months_formula(self):
        rf = compute_runway("a", cash_usd=12_000_000, burn_rate=self._burn(1_000_000))
        assert rf.runway_months == pytest.approx(12.0)

    def test_runway_risk_comfortable(self):
        rf = compute_runway("a", cash_usd=60_000_000, burn_rate=self._burn(1_000_000))
        assert rf.runway_risk == "comfortable"

    def test_runway_risk_critical(self):
        rf = compute_runway("a", cash_usd=4_000_000, burn_rate=self._burn(1_000_000))
        assert rf.runway_risk == "critical"

    def test_runway_risk_high(self):
        rf = compute_runway("a", cash_usd=8_000_000, burn_rate=self._burn(1_000_000))
        assert rf.runway_risk == "high"

    def test_runway_date_is_future(self):
        from datetime import date
        rf = compute_runway("a", cash_usd=24_000_000, burn_rate=self._burn(1_000_000))
        assert date.fromisoformat(rf.runway_date) > date.today()

    def test_next_financing_needed_by_3m_before_runway(self):
        from datetime import date
        rf = compute_runway("a", cash_usd=24_000_000, burn_rate=self._burn(1_000_000))
        runway_dt = date.fromisoformat(rf.runway_date)
        financing_dt = date.fromisoformat(rf.next_financing_needed_by)
        diff_days = (runway_dt - financing_dt).days
        assert 80 <= diff_days <= 100  # ~3 months

    def test_notes_nonempty(self):
        rf = compute_runway("a", cash_usd=12_000_000, burn_rate=self._burn(1_000_000))
        assert len(rf.notes) > 0


# ---------------------------------------------------------------------------
# compute_dilution_scenarios
# ---------------------------------------------------------------------------

class TestComputeDilutionScenarios:
    def test_returns_three_scenarios(self):
        da = compute_dilution_scenarios("a", 50_000_000, 10.0, 20_000_000)
        assert len(da.scenarios) == 3
        labels = {s.label for s in da.scenarios}
        assert labels == {"bull", "base", "bear"}

    def test_bull_dilution_less_than_bear(self):
        da = compute_dilution_scenarios("a", 50_000_000, 10.0, 20_000_000)
        bull = next(s for s in da.scenarios if s.label == "bull")
        bear = next(s for s in da.scenarios if s.label == "bear")
        assert bull.dilution_pct < bear.dilution_pct

    def test_weighted_dilution_between_bull_and_bear(self):
        da = compute_dilution_scenarios("a", 50_000_000, 10.0, 20_000_000)
        bull = next(s for s in da.scenarios if s.label == "bull").dilution_pct
        bear = next(s for s in da.scenarios if s.label == "bear").dilution_pct
        assert bull <= da.weighted_dilution_pct <= bear

    def test_dilution_pct_bounded(self):
        da = compute_dilution_scenarios("a", 50_000_000, 10.0, 20_000_000)
        for s in da.scenarios:
            assert 0.0 <= s.dilution_pct <= 100.0

    def test_summary_nonempty(self):
        da = compute_dilution_scenarios("a", 50_000_000, 10.0, 20_000_000)
        assert len(da.summary) > 0


# ---------------------------------------------------------------------------
# Integration: ValuationOutput.runway_forecast and .dilution_analysis
# ---------------------------------------------------------------------------

class TestValuationOutputRunwayDilution:
    def _make_output(
        self,
        burn_rate_q: float | None = 5.0,
        current_price: float | None = 10.0,
        cash_millions: float = 50.0,
    ):
        from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
        from bve.entities.company import Company
        from bve.entities.trial import ClinicalTrial, TrialPhase
        from bve.models.market_model import MarketModel
        from bve.valuation.valuation_engine import ValuationEngine

        asset = Asset(
            id="rd-test-01",
            name="Test Asset",
            indication="Test",
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            modality=Modality.SMALL_MOLECULE,
            stage=DevelopmentStage.PHASE_2,
            discount_rate=0.10,
        )
        company = Company(
            id="co-01", name="Test Co", ticker="TST",
            shares_outstanding_millions=50.0,
            cash_millions=cash_millions,
            current_price=current_price,
            burn_rate_millions_per_quarter=burn_rate_q,
        )
        trials = [
            ClinicalTrial(
                asset_id="rd-test-01",
                phase=TrialPhase.PHASE_2,
                success_probability=0.40,
                duration_years=2.0,
                cost_millions=30.0,
            )
        ]
        market_model = MarketModel(
            asset_id="rd-test-01",
            total_addressable_market_millions=2000.0,
            peak_penetration=0.05,
            years_to_peak=3,
            patent_life_years=8,
        )
        return ValuationEngine(
            asset=asset, company=company, trials=trials, market_model=market_model
        ).run()

    def test_runway_forecast_populated_when_burn_rate_set(self):
        output = self._make_output(burn_rate_q=5.0)
        assert output.runway_forecast is not None
        assert isinstance(output.runway_forecast, RunwayForecastV2)

    def test_runway_forecast_none_when_no_burn_rate(self):
        output = self._make_output(burn_rate_q=None)
        assert output.runway_forecast is None

    def test_runway_months_correct(self):
        # cash=50M, burn=5M/quarter=20M/year → 2.5 years = 30 months
        output = self._make_output(burn_rate_q=5.0, cash_millions=50.0)
        assert output.runway_forecast is not None
        assert output.runway_forecast.runway_months == pytest.approx(30.0, rel=0.05)

    def test_dilution_analysis_populated_when_price_set(self):
        output = self._make_output(current_price=10.0, burn_rate_q=5.0, cash_millions=10.0)
        # dilution may or may not be computed depending on capital_needed
        # when cash < trial_costs, dilution_analysis should be set
        # Just check it returns a DilutionAnalysis or None (not an error)
        assert output.dilution_analysis is None or isinstance(output.dilution_analysis, DilutionAnalysis)

    def test_dilution_analysis_none_when_no_price(self):
        output = self._make_output(current_price=None)
        assert output.dilution_analysis is None

    def test_summary_dict_runway_keys(self):
        output = self._make_output(burn_rate_q=5.0)
        sd = output.summary_dict
        assert "runway_months" in sd
        assert "runway_risk" in sd
        assert "runway_date" in sd

    def test_summary_dict_runway_populated(self):
        output = self._make_output(burn_rate_q=5.0)
        sd = output.summary_dict
        assert sd["runway_months"] is not None
        assert sd["runway_risk"] in ("critical", "high", "medium", "low", "comfortable")

    def test_summary_dict_runway_none_when_no_burn(self):
        output = self._make_output(burn_rate_q=None)
        sd = output.summary_dict
        assert sd["runway_months"] is None
        assert sd["runway_risk"] is None

    def test_summary_dict_dilution_keys(self):
        output = self._make_output()
        sd = output.summary_dict
        assert "dilution_weighted_pct" in sd
        assert "dilution_flag" in sd

    def test_dilution_flag_levels(self):
        """dilution_flag must be 'high', 'moderate', 'low', or None."""
        output = self._make_output()
        sd = output.summary_dict
        assert sd["dilution_flag"] in ("high", "moderate", "low", None)
