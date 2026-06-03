"""
Tests for P2.5 — Catalyst payoff simulation wired into ValuationOutput.

Verifies:
- compute_catalyst_payoff returns CatalystPayoffResult with all fields
- value_if_success >= current_value (success has non-negative upside)
- value_if_failure <= current_value (failure has non-negative downside)
- upside + downside > 0 (there is real catalyst value)
- delta_ev = pos * upside - (1-pos) * downside (formula check)
- std_dev >= 0
- asymmetry_ratio = upside/downside when downside > 0
- signal_strength direction matches delta_ev sign
- is_asymmetric_upside True when ratio > 1.5
- ev_label categories: positive / negative / neutral
- ValuationOutput.catalyst_payoff is populated by ValuationEngine.run()
- summary_dict contains catalyst keys with correct values
"""
from __future__ import annotations

import math

import pytest

from bve.models.catalyst_payoff import CatalystPayoffResult, compute_catalyst_payoff


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _build_inputs():
    from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
    from bve.entities.trial import ClinicalTrial, TrialPhase
    from bve.models.market_model import MarketModel

    asset = Asset(
        id="cat-test-01",
        name="Catalyst Test",
        indication="Oncology",
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        modality=Modality.SMALL_MOLECULE,
        stage=DevelopmentStage.PHASE_3,
        discount_rate=0.10,
    )
    trials = [
        ClinicalTrial(
            asset_id="cat-test-01",
            phase=TrialPhase.PHASE_3,
            success_probability=0.55,
            duration_years=3.0,
            cost_millions=80.0,
        )
    ]
    market_model = MarketModel(
        asset_id="cat-test-01",
        total_addressable_market_millions=5000.0,
        peak_penetration=0.05,
        years_to_peak=4,
        patent_life_years=10,
    )
    return asset, trials, market_model


def _compute(asset=None, trials=None, market_model=None) -> CatalystPayoffResult:
    from bve.models.rnpv_model import compute_rnpv_full
    if asset is None:
        asset, trials, market_model = _build_inputs()
    rnpv = compute_rnpv_full(asset, trials, market_model)
    return compute_catalyst_payoff(asset, trials, market_model, rnpv)


# ---------------------------------------------------------------------------
# compute_catalyst_payoff unit tests
# ---------------------------------------------------------------------------

class TestComputeCatalystPayoff:
    def setup_method(self):
        self.result = _compute()

    def test_returns_catalyst_payoff_result(self):
        assert isinstance(self.result, CatalystPayoffResult)

    def test_value_if_success_gte_current(self):
        assert self.result.value_if_success >= self.result.current_value

    def test_value_if_failure_lte_current(self):
        assert self.result.value_if_failure <= self.result.current_value

    def test_upside_non_negative(self):
        assert self.result.upside >= 0

    def test_downside_non_negative(self):
        assert self.result.downside >= 0

    def test_upside_plus_downside_positive(self):
        assert self.result.upside + self.result.downside > 0

    def test_delta_ev_formula(self):
        pos = self.result.current_pos
        expected = pos * self.result.upside - (1 - pos) * self.result.downside
        assert self.result.delta_ev == pytest.approx(expected, abs=0.1)

    def test_std_dev_non_negative(self):
        assert self.result.std_dev >= 0

    def test_std_dev_is_finite(self):
        assert math.isfinite(self.result.std_dev)

    def test_signal_strength_direction_matches_delta_ev(self):
        if self.result.delta_ev > 0:
            assert self.result.signal_strength > 0
        elif self.result.delta_ev < 0:
            assert self.result.signal_strength < 0

    def test_asymmetry_ratio_when_downside_positive(self):
        if self.result.downside > 0:
            expected = self.result.upside / self.result.downside
            assert self.result.asymmetry_ratio == pytest.approx(expected, rel=1e-4)

    def test_pos_in_unit_interval(self):
        assert 0 < self.result.current_pos < 1

    def test_is_asymmetric_upside_consistent(self):
        if math.isfinite(self.result.asymmetry_ratio):
            expected = self.result.asymmetry_ratio > 1.5
            assert self.result.is_asymmetric_upside == expected
        else:
            # inf asymmetry_ratio → always asymmetric upside
            assert self.result.is_asymmetric_upside

    def test_ev_label_values(self):
        assert self.result.ev_label in {"positive", "negative", "neutral"}

    def test_ev_label_positive_when_delta_ev_large_positive(self):
        # With pos=0.55, upside >> 0, downside > 0 → delta_ev should be positive
        if self.result.delta_ev > 10:
            assert self.result.ev_label == "positive"

    def test_high_pos_produces_positive_delta_ev(self):
        """With pos=0.90, strongly positive delta_ev expected."""
        from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
        from bve.entities.trial import ClinicalTrial, TrialPhase
        from bve.models.market_model import MarketModel
        from bve.models.rnpv_model import compute_rnpv_full

        asset = Asset(
            id="cat-high", name="High POS", indication="Oncology",
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            modality=Modality.SMALL_MOLECULE,
            stage=DevelopmentStage.PHASE_3,
            discount_rate=0.10,
        )
        trials = [
            ClinicalTrial(
                asset_id="cat-high", phase=TrialPhase.PHASE_3,
                success_probability=0.90,
                duration_years=2.0, cost_millions=50.0,
            )
        ]
        market_model = MarketModel(
            asset_id="cat-high",
            total_addressable_market_millions=5000.0,
            peak_penetration=0.05, years_to_peak=4, patent_life_years=10,
        )
        rnpv = compute_rnpv_full(asset, trials, market_model)
        result = compute_catalyst_payoff(asset, trials, market_model, rnpv)
        assert result.delta_ev > 0
        assert result.signal_strength > 0


# ---------------------------------------------------------------------------
# ValuationOutput integration tests
# ---------------------------------------------------------------------------

class TestValuationOutputCatalystPayoff:
    def _make_output(self):
        from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
        from bve.entities.company import Company
        from bve.entities.trial import ClinicalTrial, TrialPhase
        from bve.models.market_model import MarketModel
        from bve.valuation.valuation_engine import ValuationEngine

        asset = Asset(
            id="cat-val-01", name="Catalyst Val",
            indication="Oncology",
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            modality=Modality.SMALL_MOLECULE,
            stage=DevelopmentStage.PHASE_3,
            discount_rate=0.10,
        )
        company = Company(
            id="co-01", name="Test Co", ticker="TST",
            shares_outstanding_millions=100.0,
            cash_millions=150.0,
        )
        trials = [
            ClinicalTrial(
                asset_id="cat-val-01", phase=TrialPhase.PHASE_3,
                success_probability=0.55, duration_years=3.0, cost_millions=80.0,
            )
        ]
        market_model = MarketModel(
            asset_id="cat-val-01",
            total_addressable_market_millions=5000.0,
            peak_penetration=0.05, years_to_peak=4, patent_life_years=10,
        )
        return ValuationEngine(
            asset=asset, company=company, trials=trials, market_model=market_model
        ).run()

    def test_catalyst_payoff_populated(self):
        output = self._make_output()
        assert output.catalyst_payoff is not None
        assert isinstance(output.catalyst_payoff, CatalystPayoffResult)

    def test_summary_dict_catalyst_keys(self):
        output = self._make_output()
        sd = output.summary_dict
        for key in [
            "catalyst_upside_millions", "catalyst_downside_millions",
            "catalyst_delta_ev_millions", "catalyst_signal_strength",
            "catalyst_asymmetry_ratio", "catalyst_ev_label",
        ]:
            assert key in sd

    def test_summary_dict_catalyst_values_populated(self):
        output = self._make_output()
        sd = output.summary_dict
        assert sd["catalyst_upside_millions"] is not None
        assert sd["catalyst_downside_millions"] is not None
        assert sd["catalyst_ev_label"] in {"positive", "negative", "neutral"}

    def test_summary_dict_upside_matches_payoff(self):
        output = self._make_output()
        sd = output.summary_dict
        assert sd["catalyst_upside_millions"] == pytest.approx(
            output.catalyst_payoff.upside, abs=0.5
        )
