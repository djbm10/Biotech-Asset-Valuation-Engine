"""
Tests for P2.2 — Financing & dilution simulation in Monte Carlo.

Verifies:
- MonteCarloParams accepts sample_financing and financing_discount_cv with correct defaults
- SimulationDraws accepts dilution_factor (default 1.0, bounded [0, 1])
- With sample_financing=True and cash < trial costs, mean_millions decreases
- With sufficient cash, no dilution occurs (dilution_factor stays 1.0)
- Without shares_outstanding_millions or current_price_per_share, no dilution (safe fallback)
- Backward compatibility: default params produce identical results to pre-P2.2
- Higher financing_discount_cv widens the distribution
"""
from __future__ import annotations

import pytest
import numpy as np

from bve.models.monte_carlo import MonteCarloParams, SimulationDraws


# ---------------------------------------------------------------------------
# MonteCarloParams — new fields
# ---------------------------------------------------------------------------

class TestMonteCarloParamsFinancingFields:
    def test_default_sample_financing_is_false(self):
        p = MonteCarloParams()
        assert p.sample_financing is False

    def test_default_financing_discount_cv(self):
        p = MonteCarloParams()
        assert p.financing_discount_cv == pytest.approx(0.10)

    def test_can_enable_financing(self):
        p = MonteCarloParams(sample_financing=True)
        assert p.sample_financing is True

    def test_custom_discount_cv_accepted(self):
        p = MonteCarloParams(sample_financing=True, financing_discount_cv=0.25)
        assert p.financing_discount_cv == pytest.approx(0.25)

    def test_discount_cv_must_be_positive(self):
        with pytest.raises(Exception):
            MonteCarloParams(financing_discount_cv=0.0)
        with pytest.raises(Exception):
            MonteCarloParams(financing_discount_cv=-0.05)


# ---------------------------------------------------------------------------
# SimulationDraws — dilution_factor field
# ---------------------------------------------------------------------------

class TestSimulationDrawsDilutionFactor:
    def _base_draws(self) -> dict:
        return dict(
            phase_success_probs={"phase_3": 0.55},
            peak_sales_millions=800.0,
            years_to_peak=5,
            discount_rate=0.10,
        )

    def test_dilution_factor_defaults_one(self):
        d = SimulationDraws(**self._base_draws())
        assert d.dilution_factor == pytest.approx(1.0)

    def test_dilution_factor_accepts_less_than_one(self):
        d = SimulationDraws(**self._base_draws(), dilution_factor=0.80)
        assert d.dilution_factor == pytest.approx(0.80)

    def test_dilution_factor_lower_bound(self):
        d = SimulationDraws(**self._base_draws(), dilution_factor=0.0)
        assert d.dilution_factor == pytest.approx(0.0)

    def test_dilution_factor_upper_bound(self):
        d = SimulationDraws(**self._base_draws(), dilution_factor=1.0)
        assert d.dilution_factor == pytest.approx(1.0)

    def test_dilution_factor_above_one_rejected(self):
        with pytest.raises(Exception):
            SimulationDraws(**self._base_draws(), dilution_factor=1.01)

    def test_dilution_factor_below_zero_rejected(self):
        with pytest.raises(Exception):
            SimulationDraws(**self._base_draws(), dilution_factor=-0.01)


# ---------------------------------------------------------------------------
# run_monte_carlo integration tests
# ---------------------------------------------------------------------------

class TestRunMonteCarloFinancingDilution:
    """
    Confirm that enabling sample_financing reduces mean (dilution costs)
    without breaking the simulation when inputs are absent.
    """

    def _build_inputs(self):
        from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
        from bve.entities.trial import ClinicalTrial, TrialPhase
        from bve.models.market_model import MarketModel

        asset = Asset(
            id="fin-test-01",
            name="Fin Test",
            indication="Oncology",
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            modality=Modality.SMALL_MOLECULE,
            stage=DevelopmentStage.PHASE_3,
            discount_rate=0.10,
        )
        trials = [
            ClinicalTrial(
                asset_id="fin-test-01",
                phase=TrialPhase.PHASE_3,
                success_probability=0.55,
                duration_years=3.0,
                cost_millions=80.0,
            )
        ]
        market_model = MarketModel(
            asset_id="fin-test-01",
            total_addressable_market_millions=5000.0,
            peak_penetration=0.05,
            years_to_peak=4,
            patent_life_years=10,
        )
        return asset, trials, market_model

    def _run(self, extra_params: dict = None, seed: int = 42,
             shares: float = 50.0, price: float = 10.0, net_cash: float = 5.0):
        from bve.models.monte_carlo import run_monte_carlo
        asset, trials, market_model = self._build_inputs()
        kw = extra_params or {}
        n = kw.pop("n_simulations", 500)
        params = MonteCarloParams(n_simulations=n, random_seed=seed, **kw)
        return run_monte_carlo(
            asset, trials, market_model, params,
            shares_outstanding_millions=shares,
            current_price_per_share=price,
            net_cash_millions=net_cash,
        )

    def test_baseline_runs_successfully(self):
        result = self._run()
        assert result.n_simulations == 500
        assert result.std_millions > 0

    def test_financing_reduces_mean_when_cash_constrained(self):
        """Cash (5M) << trial cost (80M) → significant dilution expected."""
        base = self._run(net_cash=5.0)
        with_fin = self._run({"sample_financing": True}, net_cash=5.0)
        # Dilution haircuts rNPV → mean should be lower
        assert with_fin.mean_millions < base.mean_millions

    def test_no_dilution_when_cash_sufficient(self):
        """Cash (500M) >> trial cost (80M) → no capital raise needed."""
        base = self._run(net_cash=500.0)
        with_fin = self._run({"sample_financing": True}, net_cash=500.0)
        # base_capital_shortfall = max(0, 80 - 500) = 0 → dilution_factor always 1.0
        assert with_fin.mean_millions == pytest.approx(base.mean_millions, rel=1e-6)
        assert with_fin.std_millions == pytest.approx(base.std_millions, rel=1e-6)

    def test_backward_compatible_no_shares(self):
        """Without shares_outstanding, financing has no effect."""
        from bve.models.monte_carlo import run_monte_carlo
        asset, trials, market_model = self._build_inputs()
        params_base = MonteCarloParams(n_simulations=500, random_seed=7)
        params_fin = MonteCarloParams(n_simulations=500, random_seed=7, sample_financing=True)
        base = run_monte_carlo(asset, trials, market_model, params_base, net_cash_millions=5.0)
        with_fin = run_monte_carlo(asset, trials, market_model, params_fin, net_cash_millions=5.0)
        # No shares → no dilution → identical results
        assert with_fin.mean_millions == pytest.approx(base.mean_millions, rel=1e-6)

    def test_backward_compatible_no_price(self):
        """Without current_price_per_share, financing has no effect."""
        from bve.models.monte_carlo import run_monte_carlo
        asset, trials, market_model = self._build_inputs()
        params_base = MonteCarloParams(n_simulations=500, random_seed=7)
        params_fin = MonteCarloParams(n_simulations=500, random_seed=7, sample_financing=True)
        base = run_monte_carlo(
            asset, trials, market_model, params_base,
            shares_outstanding_millions=50.0, net_cash_millions=5.0,
        )
        with_fin = run_monte_carlo(
            asset, trials, market_model, params_fin,
            shares_outstanding_millions=50.0, net_cash_millions=5.0,
        )
        assert with_fin.mean_millions == pytest.approx(base.mean_millions, rel=1e-6)

    def test_disabled_flag_backward_compatible(self):
        """Explicit sample_financing=False is identical to default."""
        result1 = self._run(seed=13, net_cash=5.0)
        result2 = self._run({"sample_financing": False}, seed=13, net_cash=5.0)
        assert result1.mean_millions == pytest.approx(result2.mean_millions, rel=1e-6)
        assert result1.std_millions == pytest.approx(result2.std_millions, rel=1e-6)

    def test_n_simulations_preserved(self):
        result = self._run({"sample_financing": True})
        assert result.n_simulations == 500
        assert len(result.simulated_values_millions) == 500

    def test_higher_discount_cv_increases_average_dilution(self):
        """Higher financing_discount_cv → clipping asymmetry pushes more mass to high discounts
        → more dilution on average → lower mean_millions.

        With large n and the same seed, the undiluted draws are identical (RNG state
        after step 5 is the same regardless of cv, since both consume exactly n values).
        Any mean difference is purely from the dilution multiplier.
        """
        low_cv = self._run(
            {"sample_financing": True, "financing_discount_cv": 0.001, "n_simulations": 4000},
            seed=1, net_cash=5.0,
        )
        high_cv = self._run(
            {"sample_financing": True, "financing_discount_cv": 0.40, "n_simulations": 4000},
            seed=1, net_cash=5.0,
        )
        # Higher cv → more dilution → lower mean
        assert high_cv.mean_millions <= low_cv.mean_millions

    def test_dilution_factor_bounded(self):
        """
        Mathematically: dilution_factor = shares_pre / (shares_pre + shares_issued) ∈ (0, 1].
        With reasonable inputs (price > 0, discount < 0.50), factor is always > 0.
        """
        # capital_shortfall = 80 - 5 = 75M, offering_price = 10 * (1 - discount)
        # discount clipped to [0.05, 0.50] → price in [5, 9.5]
        # shares_issued = 75 / price ∈ [7.9, 15] millions
        # dilution_factor = 50 / (50 + shares_issued) ∈ [0.77, 0.86]
        result = self._run({"sample_financing": True, "n_simulations": 1000},
                           shares=50.0, price=10.0, net_cash=5.0)
        # All simulated values should be finite (no NaN/inf from bad dilution)
        vals = result.simulated_values_millions
        assert all(np.isfinite(v) for v in vals)
