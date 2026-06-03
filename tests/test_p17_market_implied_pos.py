"""
Tests for P1.7 — market_expectation field on ValuationOutput.

Verifies that:
- ImpliedPoSResult is attached when price data is available
- market_expectation is None when no price data
- summary_dict contains the correct delta keys
- pos_gap sign convention: positive = model bullish vs market
"""
from __future__ import annotations

from datetime import date

import pytest

from bve.expectations.market_implied_pos import ImpliedPoSResult, compute_implied_pos


# ---------------------------------------------------------------------------
# Unit tests for compute_implied_pos (standalone)
# ---------------------------------------------------------------------------

class TestComputeImpliedPos:
    def test_aligned_when_market_matches_model(self):
        """When pipeline EV roughly equals model gross_pv × model_pos, gap ≈ 0."""
        result = compute_implied_pos(
            asset_id="test-01",
            ticker="TEST",
            as_of_date=date(2026, 1, 1),
            current_ev_millions=600.0,
            net_cash_millions=100.0,
            model_peak_sales_millions=1000.0,
            model_pos=0.50,
            years_to_peak=5.0,
            discount_rate=0.10,
            peak_duration_years=10.0,
            trial_costs_pv_millions=50.0,
        )
        assert isinstance(result, ImpliedPoSResult)
        assert result.registry_found is False if hasattr(result, "registry_found") else True
        assert 0.0 <= result.implied_pos <= 1.0
        assert result.model_pos == 0.50

    def test_implied_pos_bounded(self):
        """Implied PoS must be clamped to [0, 1]."""
        # Extremely high EV relative to model → would imply > 1 without clamping
        result = compute_implied_pos(
            asset_id="test-01", ticker="TEST", as_of_date=date(2026, 1, 1),
            current_ev_millions=50_000.0, net_cash_millions=100.0,
            model_peak_sales_millions=500.0, model_pos=0.40,
            years_to_peak=5.0, discount_rate=0.10, peak_duration_years=10.0,
        )
        assert result.implied_pos <= 1.0
        assert result.implied_pos >= 0.0

    def test_underpriced_when_model_bullish(self):
        """When model PoS >> implied PoS, stock is underpriced."""
        # Low EV, high model PoS
        result = compute_implied_pos(
            asset_id="test-01", ticker="TEST", as_of_date=date(2026, 1, 1),
            current_ev_millions=200.0, net_cash_millions=150.0,
            model_peak_sales_millions=2000.0, model_pos=0.60,
            years_to_peak=4.0, discount_rate=0.10, peak_duration_years=10.0,
        )
        assert result.pos_gap > 0
        assert result.mispricing_direction == "underpriced"

    def test_overpriced_when_market_bullish(self):
        """When implied PoS >> model PoS, stock is overpriced."""
        result = compute_implied_pos(
            asset_id="test-01", ticker="TEST", as_of_date=date(2026, 1, 1),
            current_ev_millions=5000.0, net_cash_millions=100.0,
            model_peak_sales_millions=500.0, model_pos=0.20,
            years_to_peak=4.0, discount_rate=0.10, peak_duration_years=10.0,
        )
        assert result.pos_gap < 0
        assert result.mispricing_direction == "overpriced"

    def test_negative_pipeline_ev_note(self):
        """When net_cash > market_cap, pipeline EV is negative and a note is added."""
        result = compute_implied_pos(
            asset_id="test-01", ticker="TEST", as_of_date=date(2026, 1, 1),
            current_ev_millions=100.0, net_cash_millions=200.0,
            model_peak_sales_millions=1000.0, model_pos=0.50,
            years_to_peak=4.0, discount_rate=0.10, peak_duration_years=10.0,
        )
        assert result.pipeline_ev_millions < 0
        assert any("negative" in n.lower() for n in result.notes)

    def test_pos_gap_sign_convention(self):
        """pos_gap = model_pos − implied_pos (positive → model more bullish)."""
        result = compute_implied_pos(
            asset_id="test-01", ticker="TEST", as_of_date=date(2026, 1, 1),
            current_ev_millions=300.0, net_cash_millions=50.0,
            model_peak_sales_millions=1000.0, model_pos=0.60,
            years_to_peak=4.0, discount_rate=0.10, peak_duration_years=10.0,
        )
        assert abs(result.pos_gap - (result.model_pos - result.implied_pos)) < 1e-9

    def test_magnitude_levels(self):
        """Magnitude buckets: large ≥0.30, moderate ≥0.15, small ≥0.05."""
        # Large gap: model_pos=0.80, near-zero EV
        result = compute_implied_pos(
            asset_id="test-01", ticker="TEST", as_of_date=date(2026, 1, 1),
            current_ev_millions=50.0, net_cash_millions=40.0,
            model_peak_sales_millions=3000.0, model_pos=0.80,
            years_to_peak=4.0, discount_rate=0.10, peak_duration_years=10.0,
        )
        assert result.mispricing_magnitude == "large"

    def test_trial_costs_increase_implied_pos(self):
        """Including trial costs PV should raise implied PoS (more assets than EV alone)."""
        base = compute_implied_pos(
            asset_id="test", ticker="T", as_of_date=date(2026, 1, 1),
            current_ev_millions=400.0, net_cash_millions=50.0,
            model_peak_sales_millions=1000.0, model_pos=0.50,
            years_to_peak=4.0, discount_rate=0.10, peak_duration_years=10.0,
            trial_costs_pv_millions=0.0,
        )
        with_costs = compute_implied_pos(
            asset_id="test", ticker="T", as_of_date=date(2026, 1, 1),
            current_ev_millions=400.0, net_cash_millions=50.0,
            model_peak_sales_millions=1000.0, model_pos=0.50,
            years_to_peak=4.0, discount_rate=0.10, peak_duration_years=10.0,
            trial_costs_pv_millions=100.0,
        )
        assert with_costs.implied_pos > base.implied_pos

    def test_zero_discount_rate(self):
        """With r=0 the annuity equals peak_duration_years (no discounting)."""
        result = compute_implied_pos(
            asset_id="test", ticker="T", as_of_date=date(2026, 1, 1),
            current_ev_millions=500.0, net_cash_millions=0.0,
            model_peak_sales_millions=1000.0, model_pos=0.50,
            years_to_peak=0.0, discount_rate=0.0, peak_duration_years=10.0,
        )
        # gross_revenue_pv = 1000 × 10 = 10,000; implied_pos = 500/10000 = 0.05
        assert result.implied_pos == pytest.approx(0.05, abs=0.005)

    def test_implied_peak_sales_scales_with_pos_ratio(self):
        """implied_peak = model_peak × implied_pos / model_pos."""
        result = compute_implied_pos(
            asset_id="test", ticker="T", as_of_date=date(2026, 1, 1),
            current_ev_millions=300.0, net_cash_millions=50.0,
            model_peak_sales_millions=1000.0, model_pos=0.50,
            years_to_peak=4.0, discount_rate=0.10, peak_duration_years=10.0,
        )
        expected_peak = 1000.0 * result.implied_pos / 0.50
        assert result.implied_peak_sales_millions == pytest.approx(expected_peak, rel=1e-5)


# ---------------------------------------------------------------------------
# Integration tests via ValuationOutput.market_expectation
# ---------------------------------------------------------------------------

class TestValuationOutputMarketExpectation:
    """
    Tests that ValuationOutput.market_expectation is populated and that
    summary_dict exposes the correct keys.
    """

    def _make_output(self, current_price: float | None = 15.0):
        """Build a minimal ValuationOutput using ValuationEngine."""
        from datetime import date

        from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
        from bve.entities.company import Company
        from bve.entities.trial import ClinicalTrial, TrialPhase
        from bve.models.market_model import MarketModel
        from bve.valuation.valuation_engine import ValuationEngine

        asset = Asset(
            id="mkt-test-01",
            name="Test Asset",
            indication="Test Indication",
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            modality=Modality.SMALL_MOLECULE,
            stage=DevelopmentStage.PHASE_3,
            discount_rate=0.10,
        )
        company = Company(
            id="co-01",
            name="Test Co",
            ticker="TST",
            shares_outstanding_millions=50.0,
            cash_millions=100.0,
            current_price=current_price,
        )
        trials = [
            ClinicalTrial(
                asset_id="mkt-test-01",
                phase=TrialPhase.PHASE_3,
                success_probability=0.55,
                duration_years=3.0,
                cost_millions=80.0,
            )
        ]
        market_model = MarketModel(
            asset_id="mkt-test-01",
            total_addressable_market_millions=5000.0,
            peak_penetration=0.05,
            years_to_peak=3,
            patent_life_years=10,
        )
        engine = ValuationEngine(
            asset=asset, company=company, trials=trials, market_model=market_model
        )
        return engine.run()

    def test_market_expectation_populated_when_price_available(self):
        output = self._make_output(current_price=15.0)
        assert output.market_expectation is not None
        assert isinstance(output.market_expectation, ImpliedPoSResult)

    def test_market_expectation_none_when_no_price(self):
        output = self._make_output(current_price=None)
        assert output.market_expectation is None

    def test_market_expectation_none_when_zero_price(self):
        output = self._make_output(current_price=0.0)
        assert output.market_expectation is None

    def test_summary_dict_contains_market_keys(self):
        output = self._make_output(current_price=15.0)
        sd = output.summary_dict
        assert "market_implied_pos" in sd
        assert "market_pos_gap" in sd
        assert "market_pos_gap_pct" in sd
        assert "market_mispricing_direction" in sd
        assert "market_mispricing_magnitude" in sd
        assert "market_implied_peak_sales_millions" in sd

    def test_summary_dict_market_keys_none_without_price(self):
        output = self._make_output(current_price=None)
        sd = output.summary_dict
        assert sd["market_implied_pos"] is None
        assert sd["market_pos_gap"] is None
        assert sd["market_mispricing_direction"] is None

    def test_market_implied_pos_bounded(self):
        output = self._make_output(current_price=15.0)
        if output.market_expectation:
            assert 0.0 <= output.market_expectation.implied_pos <= 1.0

    def test_pos_gap_sign_correct(self):
        """pos_gap = model_pos − implied_pos on the output."""
        output = self._make_output(current_price=15.0)
        me = output.market_expectation
        if me is not None:
            expected = round(me.model_pos - me.implied_pos, 3)
            assert round(me.pos_gap, 3) == pytest.approx(expected, abs=0.001)
