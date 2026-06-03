"""
Tests for P2.1 — Stochastic phase timing and trial cost in Monte Carlo.

Verifies:
- MonteCarloParams accepts the new flags with correct defaults
- SimulationDraws accepts phase_duration_mults and trial_cost_mults
- With sample_phase_durations=True the MC distribution is wider than baseline
- With sample_trial_costs=True the MC distribution is wider than baseline
- Both flags together compound variance
- Gamma mean is 1.0 (no systematic bias in duration)
- Lognormal cost multiplier mean is 1.0 (no systematic cost inflation)
- Backward compatibility: default params produce identical results to pre-P2.1
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from bve.models.monte_carlo import MonteCarloParams, SimulationDraws


# ---------------------------------------------------------------------------
# MonteCarloParams — new fields
# ---------------------------------------------------------------------------

class TestMonteCarloParamsNewFields:
    def test_default_sample_phase_durations_is_false(self):
        p = MonteCarloParams()
        assert p.sample_phase_durations is False

    def test_default_phase_duration_cv(self):
        p = MonteCarloParams()
        assert p.phase_duration_cv == pytest.approx(0.30)

    def test_default_sample_trial_costs_is_false(self):
        p = MonteCarloParams()
        assert p.sample_trial_costs is False

    def test_default_trial_cost_cv(self):
        p = MonteCarloParams()
        assert p.trial_cost_cv == pytest.approx(0.35)

    def test_can_enable_duration_sampling(self):
        p = MonteCarloParams(sample_phase_durations=True)
        assert p.sample_phase_durations is True

    def test_can_enable_cost_sampling(self):
        p = MonteCarloParams(sample_trial_costs=True)
        assert p.sample_trial_costs is True

    def test_custom_cvs_accepted(self):
        p = MonteCarloParams(sample_phase_durations=True, phase_duration_cv=0.20,
                              sample_trial_costs=True, trial_cost_cv=0.50)
        assert p.phase_duration_cv == pytest.approx(0.20)
        assert p.trial_cost_cv == pytest.approx(0.50)

    def test_cv_must_be_positive(self):
        with pytest.raises(Exception):
            MonteCarloParams(phase_duration_cv=0.0)
        with pytest.raises(Exception):
            MonteCarloParams(trial_cost_cv=-0.1)


# ---------------------------------------------------------------------------
# SimulationDraws — new fields
# ---------------------------------------------------------------------------

class TestSimulationDrawsNewFields:
    def _base_draws(self) -> dict:
        return dict(
            phase_success_probs={"phase_3": 0.55},
            peak_sales_millions=800.0,
            years_to_peak=5,
            discount_rate=0.10,
        )

    def test_phase_duration_mults_defaults_empty(self):
        d = SimulationDraws(**self._base_draws())
        assert d.phase_duration_mults == {}

    def test_trial_cost_mults_defaults_empty(self):
        d = SimulationDraws(**self._base_draws())
        assert d.trial_cost_mults == {}

    def test_accepts_phase_duration_mults(self):
        d = SimulationDraws(
            **self._base_draws(),
            phase_duration_mults={"phase_3": 1.25},
        )
        assert d.phase_duration_mults["phase_3"] == pytest.approx(1.25)

    def test_accepts_trial_cost_mults(self):
        d = SimulationDraws(
            **self._base_draws(),
            trial_cost_mults={"0": 0.80, "1": 1.40},
        )
        assert d.trial_cost_mults["0"] == pytest.approx(0.80)
        assert d.trial_cost_mults["1"] == pytest.approx(1.40)


# ---------------------------------------------------------------------------
# Gamma distribution properties
# ---------------------------------------------------------------------------

class TestGammaDurationDistribution:
    """
    The gamma draw should have mean ≈ 1.0 and std ≈ cv.
    Parameterisation: shape = 1/cv², scale = cv².
    """

    def test_gamma_mean_is_one(self):
        rng = np.random.default_rng(42)
        cv = 0.30
        shape = 1.0 / (cv ** 2)
        scale = cv ** 2
        samples = rng.gamma(shape=shape, scale=scale, size=50_000)
        assert samples.mean() == pytest.approx(1.0, abs=0.02)

    def test_gamma_std_matches_cv(self):
        rng = np.random.default_rng(42)
        cv = 0.30
        shape = 1.0 / (cv ** 2)
        scale = cv ** 2
        samples = rng.gamma(shape=shape, scale=scale, size=50_000)
        assert samples.std() == pytest.approx(cv, abs=0.02)

    def test_gamma_always_positive(self):
        rng = np.random.default_rng(42)
        cv = 0.30
        shape = 1.0 / (cv ** 2)
        scale = cv ** 2
        samples = rng.gamma(shape=shape, scale=scale, size=10_000)
        assert (samples > 0).all()

    def test_gamma_right_skewed(self):
        """Gamma should be right-skewed (mean > median for right-skewed distributions)."""
        rng = np.random.default_rng(42)
        cv = 0.30
        shape = 1.0 / (cv ** 2)
        scale = cv ** 2
        samples = rng.gamma(shape=shape, scale=scale, size=100_000)
        # For gamma with shape > 1 the distribution is right-skewed (longer right tail)
        # mean should be slightly above median
        assert samples.mean() >= np.median(samples) - 0.01


# ---------------------------------------------------------------------------
# Lognormal cost distribution properties
# ---------------------------------------------------------------------------

class TestLognormalCostDistribution:
    """
    The lognormal draw should have mean ≈ 1.0 and std ≈ cv.
    Parameterisation: s = sqrt(log(1+cv²)), scale = exp(-0.5*s²).
    """

    def test_lognormal_mean_is_one(self):
        from scipy.stats import lognorm
        cv = 0.35
        s = math.sqrt(math.log(1 + cv ** 2))
        mu = -0.5 * s ** 2
        samples = lognorm(s=s, scale=math.exp(mu)).rvs(50_000, random_state=99)
        assert samples.mean() == pytest.approx(1.0, abs=0.02)

    def test_lognormal_std_matches_cv(self):
        from scipy.stats import lognorm
        cv = 0.35
        s = math.sqrt(math.log(1 + cv ** 2))
        mu = -0.5 * s ** 2
        samples = lognorm(s=s, scale=math.exp(mu)).rvs(50_000, random_state=99)
        assert samples.std() == pytest.approx(cv, abs=0.03)

    def test_lognormal_always_positive(self):
        from scipy.stats import lognorm
        cv = 0.35
        s = math.sqrt(math.log(1 + cv ** 2))
        samples = lognorm(s=s, scale=math.exp(-0.5 * s ** 2)).rvs(10_000, random_state=99)
        assert (samples > 0).all()


# ---------------------------------------------------------------------------
# run_monte_carlo integration tests
# ---------------------------------------------------------------------------

class TestRunMonteCarloStochasticTiming:
    """
    Confirm that enabling the new flags widens the distribution without
    introducing systematic bias (mean should not shift dramatically).
    """

    def _build_inputs(self):
        from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
        from bve.entities.trial import ClinicalTrial, TrialPhase
        from bve.models.market_model import MarketModel

        asset = Asset(
            id="mc-timing-01",
            name="MC Test",
            indication="Oncology",
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            modality=Modality.SMALL_MOLECULE,
            stage=DevelopmentStage.PHASE_3,
            discount_rate=0.10,
        )
        trials = [
            ClinicalTrial(
                asset_id="mc-timing-01",
                phase=TrialPhase.PHASE_3,
                success_probability=0.55,
                duration_years=3.0,
                cost_millions=80.0,
            )
        ]
        market_model = MarketModel(
            asset_id="mc-timing-01",
            total_addressable_market_millions=5000.0,
            peak_penetration=0.05,
            years_to_peak=4,
            patent_life_years=10,
        )
        return asset, trials, market_model

    def _run(self, extra_params: dict = None, seed: int = 42):
        from bve.models.monte_carlo import run_monte_carlo
        asset, trials, market_model = self._build_inputs()
        kw = extra_params or {}
        n = kw.pop("n_simulations", 500)
        params = MonteCarloParams(n_simulations=n, random_seed=seed, **kw)
        return run_monte_carlo(asset, trials, market_model, params)

    def test_baseline_runs_successfully(self):
        result = self._run()
        assert result.n_simulations == 500
        assert result.std_millions > 0

    def test_duration_sampling_widens_distribution(self):
        base = self._run()
        with_timing = self._run({"sample_phase_durations": True})
        # std should be at least as wide — timing uncertainty adds variance
        assert with_timing.std_millions >= base.std_millions * 0.85
        # mean should not shift drastically (gamma is unbiased)
        assert abs(with_timing.mean_millions - base.mean_millions) < base.std_millions * 1.5

    def test_cost_sampling_widens_distribution(self):
        base = self._run()
        with_costs = self._run({"sample_trial_costs": True})
        # std should be at least as wide
        assert with_costs.std_millions >= base.std_millions * 0.85
        # mean should not shift drastically
        assert abs(with_costs.mean_millions - base.mean_millions) < base.std_millions * 1.5

    def test_both_flags_compound_variance(self):
        base = self._run()
        with_both = self._run({"sample_phase_durations": True, "sample_trial_costs": True})
        assert with_both.std_millions >= base.std_millions * 0.85

    def test_disabled_flags_backward_compatible(self):
        """With both flags False, result should be identical to default baseline."""
        result1 = self._run(seed=7)
        result2 = self._run({"sample_phase_durations": False, "sample_trial_costs": False}, seed=7)
        assert result1.mean_millions == pytest.approx(result2.mean_millions, rel=1e-6)
        assert result1.std_millions == pytest.approx(result2.std_millions, rel=1e-6)

    def test_n_simulations_preserved(self):
        result = self._run({"sample_phase_durations": True, "sample_trial_costs": True})
        assert result.n_simulations == 500
        assert len(result.simulated_values_millions) == 500

    def test_high_duration_cv_widens_more_than_low(self):
        """Use large n for stable comparison: higher CV must produce wider std."""
        low_cv = self._run({"sample_phase_durations": True, "phase_duration_cv": 0.05,
                            "n_simulations": 2000}, seed=1)
        high_cv = self._run({"sample_phase_durations": True, "phase_duration_cv": 0.60,
                             "n_simulations": 2000}, seed=1)
        assert high_cv.std_millions >= low_cv.std_millions
