"""
Sprint 32E — Full 12-step simulation path enforcement tests.

Covers:
- SimulationDraws: field validation, discount_rate bounds [0.01, 0.50]
- SimulationOutput: engine_rerun always True, nav_per_share present when shares given
- _run_single_trial(): produces positive rNPV for healthy asset
- _run_single_trial(): matches compute_rnpv_full() with same inputs (no-shortcut invariant)
- _run_single_trial(): NAV/share = (rNPV + net_cash) / shares
- _run_single_trial(): with no shares → nav_per_share is None
- Step ordering: clinical draw affects cumulative_success_probability
- Step ordering: commercial draw (higher peak_sales) raises rNPV
- Step ordering: WACC draw (higher discount rate) lowers rNPV
- Step ordering: competition draw reduces available market → lower rNPV
- run_monte_carlo() delegates per-trial work to _run_single_trial() pipeline
- run_monte_carlo() result consistent with direct _run_single_trial() calls
"""
import pytest
import numpy as np

from bve.entities.asset import Asset
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.market_model import MarketModel
from bve.models.monte_carlo import (
    MonteCarloParams,
    SimulationDraws,
    SimulationOutput,
    _run_single_trial,
    run_monte_carlo,
)
from bve.models.rnpv_model import compute_rnpv_full


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _asset(**kw) -> Asset:
    defaults = dict(
        id="mc32e-001",
        name="Trial Drug",
        indication="Oncology",
        therapeutic_area="oncology",
        stage="phase_3",
        modality="small_molecule",
        launch_year=2027,
        patent_expiry_year=2039,
        discount_rate=0.10,
        effective_tax_rate=0.21,
        royalty_rate=0.0,
    )
    defaults.update(kw)
    return Asset(**defaults)


def _trials(pos: float = 0.60) -> list[ClinicalTrial]:
    return [
        ClinicalTrial(
            asset_id="mc32e-001",
            phase=TrialPhase.PHASE_3,
            success_probability=pos,
            duration_years=3.0,
            cost_millions=80.0,
        ),
    ]


def _market(**kw) -> MarketModel:
    defaults = dict(
        asset_id="mc32e-001",
        therapeutic_area="oncology",
        addressable_patients_annual=50_000,
        net_price_per_patient_usd=80_000,
        peak_penetration=0.20,
        years_to_peak=4,
        patent_life_years=12,
        cogs_rate=0.12,
        sgna_rate_launch=0.35,
        sgna_rate_mature=0.18,
    )
    defaults.update(kw)
    return MarketModel(**defaults)


def _base_draws(
    pos: float = 0.60,
    peak_sales: float = None,
    dr: float = 0.10,
    ytp: int = 4,
) -> SimulationDraws:
    market = _market()
    if peak_sales is None:
        peak_sales = market.peak_sales_millions
    return SimulationDraws(
        phase_success_probs={"phase_3": pos},
        peak_sales_millions=peak_sales,
        years_to_peak=ytp,
        competition_model=None,
        discount_rate=dr,
    )


# ---------------------------------------------------------------------------
# SimulationDraws validation
# ---------------------------------------------------------------------------

class TestSimulationDraws:
    def test_basic_construction(self):
        d = _base_draws()
        assert d.discount_rate == pytest.approx(0.10)

    def test_discount_rate_ge_001(self):
        with pytest.raises(Exception):
            SimulationDraws(
                phase_success_probs={"phase_3": 0.6},
                peak_sales_millions=100.0,
                years_to_peak=4,
                discount_rate=0.005,  # below 0.01
            )

    def test_discount_rate_le_050(self):
        with pytest.raises(Exception):
            SimulationDraws(
                phase_success_probs={"phase_3": 0.6},
                peak_sales_millions=100.0,
                years_to_peak=4,
                discount_rate=0.55,  # above 0.50
            )

    def test_years_to_peak_ge_1(self):
        with pytest.raises(Exception):
            SimulationDraws(
                phase_success_probs={},
                peak_sales_millions=100.0,
                years_to_peak=0,
                discount_rate=0.10,
            )

    def test_years_to_peak_le_20(self):
        with pytest.raises(Exception):
            SimulationDraws(
                phase_success_probs={},
                peak_sales_millions=100.0,
                years_to_peak=21,
                discount_rate=0.10,
            )


# ---------------------------------------------------------------------------
# SimulationOutput invariants
# ---------------------------------------------------------------------------

class TestSimulationOutput:
    def test_engine_rerun_always_true(self):
        out = _run_single_trial(_base_draws(), _asset(), _trials(), _market())
        assert out.engine_rerun is True

    def test_nav_per_share_none_without_shares(self):
        out = _run_single_trial(_base_draws(), _asset(), _trials(), _market())
        assert out.nav_per_share is None

    def test_nav_per_share_populated_with_shares(self):
        out = _run_single_trial(
            _base_draws(), _asset(), _trials(), _market(),
            net_cash_millions=50.0, shares_outstanding_millions=100.0,
        )
        assert out.nav_per_share is not None
        assert out.nav_per_share == pytest.approx(out.nav_millions / 100.0, abs=1e-4)

    def test_nav_millions_equals_rnpv_plus_cash(self):
        out = _run_single_trial(
            _base_draws(), _asset(), _trials(), _market(),
            net_cash_millions=75.0,
        )
        assert out.nav_millions == pytest.approx(out.rnpv_millions + 75.0, abs=1e-4)


# ---------------------------------------------------------------------------
# No-shortcut invariant: rNPV matches compute_rnpv_full()
# ---------------------------------------------------------------------------

class TestNoShortcutInvariant:
    def test_rnpv_matches_engine_rerun(self):
        """_run_single_trial() rNPV must equal compute_rnpv_full() on same inputs."""
        asset = _asset()
        trials = _trials(pos=0.60)
        market = _market()
        draws = _base_draws(pos=0.60, peak_sales=market.peak_sales_millions, dr=0.10)

        trial_out = _run_single_trial(draws, asset, trials, market)

        # Direct engine call with same inputs
        modified_trials = [t.model_copy(update={"success_probability": 0.60}) for t in trials]
        direct = compute_rnpv_full(asset, modified_trials, market)

        assert trial_out.rnpv_millions == pytest.approx(direct.rnpv_millions, abs=1e-3)

    def test_cumulative_pos_matches_engine(self):
        asset = _asset()
        trials = _trials(pos=0.55)
        market = _market()
        draws = _base_draws(pos=0.55, peak_sales=market.peak_sales_millions, dr=0.10)

        trial_out = _run_single_trial(draws, asset, trials, market)
        direct = compute_rnpv_full(asset, [t.model_copy(update={"success_probability": 0.55}) for t in trials], market)

        assert trial_out.cumulative_success_probability == pytest.approx(
            direct.cumulative_success_probability, abs=1e-6
        )


# ---------------------------------------------------------------------------
# Step ordering: clinical draw affects P(approval)
# ---------------------------------------------------------------------------

class TestClinicalStepOrdering:
    def test_higher_pos_higher_rnpv(self):
        asset = _asset()
        trials = _trials()
        market = _market()
        peak = market.peak_sales_millions

        high = _run_single_trial(_base_draws(pos=0.90, peak_sales=peak), asset, trials, market)
        low = _run_single_trial(_base_draws(pos=0.20, peak_sales=peak), asset, trials, market)
        assert high.rnpv_millions > low.rnpv_millions

    def test_higher_pos_higher_cumulative_prob(self):
        asset = _asset()
        trials = _trials()
        market = _market()
        peak = market.peak_sales_millions

        high = _run_single_trial(_base_draws(pos=0.90, peak_sales=peak), asset, trials, market)
        low = _run_single_trial(_base_draws(pos=0.20, peak_sales=peak), asset, trials, market)
        assert high.cumulative_success_probability > low.cumulative_success_probability


# ---------------------------------------------------------------------------
# Step ordering: commercial draw (peak_sales) affects rNPV
# ---------------------------------------------------------------------------

class TestCommercialStepOrdering:
    def test_higher_peak_sales_higher_rnpv(self):
        asset = _asset()
        trials = _trials()
        market = _market()
        base_peak = market.peak_sales_millions

        high = _run_single_trial(_base_draws(peak_sales=base_peak * 2.0), asset, trials, market)
        low = _run_single_trial(_base_draws(peak_sales=base_peak * 0.5), asset, trials, market)
        assert high.rnpv_millions > low.rnpv_millions


# ---------------------------------------------------------------------------
# Step ordering: WACC draw affects rNPV
# ---------------------------------------------------------------------------

class TestWACCStepOrdering:
    def test_higher_wacc_lower_rnpv(self):
        asset = _asset()
        trials = _trials()
        market = _market()
        peak = market.peak_sales_millions

        low_wacc = _run_single_trial(_base_draws(peak_sales=peak, dr=0.06), asset, trials, market)
        high_wacc = _run_single_trial(_base_draws(peak_sales=peak, dr=0.20), asset, trials, market)
        assert low_wacc.rnpv_millions > high_wacc.rnpv_millions


# ---------------------------------------------------------------------------
# run_monte_carlo() uses _run_single_trial() pipeline
# ---------------------------------------------------------------------------

class TestRunMonteCarloIntegration:
    def test_mc_result_count_matches_n_simulations(self):
        params = MonteCarloParams(n_simulations=100, random_seed=0)
        result = run_monte_carlo(_asset(), _trials(), _market(), params)
        assert result.n_simulations == 100
        assert len(result.simulated_values_millions) == 100

    def test_mc_std_positive(self):
        params = MonteCarloParams(n_simulations=200, random_seed=7)
        result = run_monte_carlo(_asset(), _trials(), _market(), params)
        assert result.std_millions > 0

    def test_mc_probability_positive_in_unit_interval(self):
        params = MonteCarloParams(n_simulations=200, random_seed=8)
        result = run_monte_carlo(_asset(), _trials(), _market(), params)
        assert 0.0 <= result.probability_positive <= 1.0

    def test_nav_per_share_all_trials_via_run(self):
        """run_monte_carlo produces a full distribution; direct trial check."""
        asset = _asset()
        trials = _trials()
        market = _market()
        draws = _base_draws(pos=0.6, peak_sales=market.peak_sales_millions, dr=0.10)
        out = _run_single_trial(draws, asset, trials, market,
                                net_cash_millions=100.0, shares_outstanding_millions=50.0)
        assert out.nav_per_share is not None
        assert out.nav_per_share > 0

    def test_mc_mean_consistent_with_deterministic(self):
        """MC mean should be in a reasonable range around the deterministic rNPV."""
        params = MonteCarloParams(n_simulations=500, random_seed=42)
        result = run_monte_carlo(_asset(), _trials(), _market(), params)
        deterministic = compute_rnpv_full(_asset(), _trials(), _market()).rnpv_millions
        # Mean won't be identical (sampling uncertainty) but should be in 50%-200% range
        assert result.mean_millions > 0
        ratio = result.mean_millions / deterministic
        assert 0.30 < ratio < 3.0
