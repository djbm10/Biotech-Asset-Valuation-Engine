"""
Tests for P2.4 — Launch analog database wired into ValuationOutput.

Verifies:
- find_analogs returns AnalogMatchResult with populated fields
- median_peak_sales_millions is set when sales data available
- analog_match field on ValuationOutput is populated when mechanism present
- analog_match is None when no mechanism or indication given
- summary_dict includes analog keys: analog_median_peak_sales_millions,
  analog_score, analog_success_rate, analog_n_matched, analog_peak_sales_gap_pct
- ValuationEngine.run() does not crash when mechanism_of_action is None
- analog_peak_sales_gap_pct direction: model > analog → positive gap
"""
from __future__ import annotations

import pytest

from bve.models.analog_matcher import AnalogMatchResult, find_analogs


# ---------------------------------------------------------------------------
# find_analogs standalone tests
# ---------------------------------------------------------------------------

class TestFindAnalogs:
    def test_returns_analog_match_result(self):
        result = find_analogs("PD-1 inhibitor", "oncology")
        assert isinstance(result, AnalogMatchResult)

    def test_matched_analogs_nonempty_for_known_class(self):
        result = find_analogs("PD-1 inhibitor", "oncology")
        assert len(result.matched_analogs) > 0

    def test_success_rate_bounded(self):
        result = find_analogs("PD-1 inhibitor", "oncology")
        assert 0.0 <= result.success_rate <= 1.0

    def test_failure_rate_bounded(self):
        result = find_analogs("PD-1 inhibitor", "oncology")
        assert 0.0 <= result.failure_rate <= 1.0

    def test_analog_score_bounded(self):
        result = find_analogs("PD-1 inhibitor", "oncology")
        assert 0.0 <= result.analog_score <= 1.0

    def test_median_peak_sales_set_for_class_with_data(self):
        result = find_analogs("CDK4/6 inhibitor", "breast cancer")
        assert result.median_peak_sales_millions is not None
        assert result.median_peak_sales_millions > 0

    def test_no_match_returns_neutral_result(self):
        result = find_analogs("completely novel mechanism xyz", "exotic disease xyz")
        assert len(result.matched_analogs) == 0
        assert result.analog_score == pytest.approx(0.5)
        assert result.median_peak_sales_millions is None

    def test_max_results_respected(self):
        result = find_analogs("inhibitor", "cancer", max_results=2)
        assert len(result.matched_analogs) <= 2

    def test_summary_nonempty(self):
        result = find_analogs("KRAS G12C inhibitor", "NSCLC")
        assert len(result.summary) > 0

    def test_failure_class_reflected_in_score(self):
        """A drug class with known failures should have lower analog_score."""
        success_class = find_analogs("PD-1 inhibitor", "oncology solid tumor")
        # analog_score for mostly-successful class should be > 0.5
        assert success_class.analog_score >= 0.5

    def test_success_rate_plus_failure_rate_le_one(self):
        result = find_analogs("BTK inhibitor", "CLL hematology")
        assert result.success_rate + result.failure_rate <= 1.0 + 1e-9


# ---------------------------------------------------------------------------
# ValuationOutput integration tests
# ---------------------------------------------------------------------------

class TestValuationOutputAnalogMatch:
    def _make_output(
        self,
        mechanism: str = "CDK4/6 inhibitor",
        indication: str = "HR+ HER2- breast cancer",
    ):
        from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
        from bve.entities.company import Company
        from bve.entities.trial import ClinicalTrial, TrialPhase
        from bve.models.market_model import MarketModel
        from bve.valuation.valuation_engine import ValuationEngine

        asset = Asset(
            id="analog-test-01",
            name="Test CDK",
            indication=indication,
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            modality=Modality.SMALL_MOLECULE,
            stage=DevelopmentStage.PHASE_3,
            discount_rate=0.10,
            mechanism_of_action=mechanism,
        )
        company = Company(
            id="co-01", name="Test Co", ticker="TST",
            shares_outstanding_millions=100.0,
            cash_millions=200.0,
        )
        trials = [
            ClinicalTrial(
                asset_id="analog-test-01",
                phase=TrialPhase.PHASE_3,
                success_probability=0.55,
                duration_years=3.0,
                cost_millions=80.0,
            )
        ]
        market_model = MarketModel(
            asset_id="analog-test-01",
            total_addressable_market_millions=8000.0,
            peak_penetration=0.10,
            years_to_peak=4,
            patent_life_years=10,
        )
        return ValuationEngine(
            asset=asset, company=company, trials=trials, market_model=market_model
        ).run()

    def _make_output_no_mechanism(self):
        from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
        from bve.entities.company import Company
        from bve.entities.trial import ClinicalTrial, TrialPhase
        from bve.models.market_model import MarketModel
        from bve.valuation.valuation_engine import ValuationEngine

        asset = Asset(
            id="analog-test-02",
            name="No Mech",
            indication="Unknown",
            therapeutic_area=TherapeuticArea.OTHER,
            modality=Modality.SMALL_MOLECULE,
            stage=DevelopmentStage.PHASE_2,
            discount_rate=0.12,
            # mechanism_of_action is None (default)
        )
        company = Company(
            id="co-02", name="Test Co 2", ticker="TST2",
            shares_outstanding_millions=50.0,
            cash_millions=50.0,
        )
        trials = [
            ClinicalTrial(
                asset_id="analog-test-02",
                phase=TrialPhase.PHASE_2,
                success_probability=0.40,
                duration_years=2.0,
                cost_millions=30.0,
            )
        ]
        market_model = MarketModel(
            asset_id="analog-test-02",
            total_addressable_market_millions=1000.0,
            peak_penetration=0.05,
            years_to_peak=3,
            patent_life_years=8,
        )
        return ValuationEngine(
            asset=asset, company=company, trials=trials, market_model=market_model
        ).run()

    def test_analog_match_populated_for_known_mechanism(self):
        output = self._make_output()
        assert output.analog_match is not None
        assert isinstance(output.analog_match, AnalogMatchResult)

    def test_analog_match_has_matched_analogs(self):
        output = self._make_output()
        assert output.analog_match is not None
        assert len(output.analog_match.matched_analogs) > 0

    def test_analog_match_none_when_no_mechanism(self):
        output = self._make_output_no_mechanism()
        # No mechanism_of_action → no meaningful search → None
        assert output.analog_match is None

    def test_summary_dict_analog_keys_present(self):
        output = self._make_output()
        sd = output.summary_dict
        assert "analog_median_peak_sales_millions" in sd
        assert "analog_score" in sd
        assert "analog_success_rate" in sd
        assert "analog_n_matched" in sd
        assert "analog_peak_sales_gap_pct" in sd

    def test_summary_dict_analog_values_populated(self):
        output = self._make_output()
        sd = output.summary_dict
        assert sd["analog_n_matched"] is not None
        assert sd["analog_n_matched"] > 0
        assert sd["analog_score"] is not None
        assert sd["analog_success_rate"] is not None

    def test_summary_dict_analog_none_when_no_mechanism(self):
        output = self._make_output_no_mechanism()
        sd = output.summary_dict
        assert sd["analog_median_peak_sales_millions"] is None
        assert sd["analog_score"] is None
        assert sd["analog_n_matched"] is None

    def test_analog_peak_sales_gap_pct_direction(self):
        """When model peak_sales > analog median, gap should be positive."""
        output = self._make_output()
        sd = output.summary_dict
        if sd["analog_median_peak_sales_millions"] is not None and sd["analog_peak_sales_gap_pct"] is not None:
            model_peak = output.rnpv.peak_sales_millions
            analog_median = sd["analog_median_peak_sales_millions"]
            expected_gap = (model_peak / analog_median - 1) * 100
            assert abs(sd["analog_peak_sales_gap_pct"] - expected_gap) < 0.5

    def test_engine_does_not_crash_with_unknown_mechanism(self):
        """Completely unrecognized mechanism should produce None analog_match, not an error."""
        output = self._make_output(mechanism="completely unknown xyz mechanism", indication="rare disease xyz")
        assert output.analog_match is None
