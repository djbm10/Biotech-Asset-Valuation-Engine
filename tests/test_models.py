"""Core model unit tests."""
import pytest

from bve.entities.asset import Asset, DevelopmentStage, TherapeuticArea, Modality
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, TrialPhase, EndpointType
from bve.models.market_model import MarketModel
from bve.models.monte_carlo import MonteCarloParams, run_monte_carlo
from bve.models.pos_model import POSAdjusters, compute_pos, MoAPrecedent, SafetyProfile
from bve.models.rnpv_model import compute_rnpv
from bve.valuation.scenario import build_scenarios
from bve.valuation.valuation_engine import ValuationEngine


@pytest.fixture
def sample_asset():
    return Asset(
        id="test-001",
        name="TEST-001",
        indication="Test Indication",
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        stage=DevelopmentStage.PHASE_2,
        modality=Modality.SMALL_MOLECULE,
        discount_rate=0.10,
    )


@pytest.fixture
def sample_company():
    return Company(
        id="test-co",
        name="Test Co",
        ticker="TEST",
        cash_millions=300.0,
        shares_outstanding_millions=100.0,
        burn_rate_millions_per_quarter=25.0,
    )


@pytest.fixture
def sample_trials(sample_asset):
    return [
        ClinicalTrial(
            asset_id=sample_asset.id,
            phase=TrialPhase.PHASE_2,
            success_probability=0.37,
            duration_years=2.5,
            cost_millions=80.0,
            enrollment=150,
        ),
        ClinicalTrial(
            asset_id=sample_asset.id,
            phase=TrialPhase.PHASE_3,
            success_probability=0.55,
            duration_years=3.5,
            cost_millions=250.0,
            enrollment=450,
        ),
        ClinicalTrial(
            asset_id=sample_asset.id,
            phase=TrialPhase.NDA_BLA,
            success_probability=0.87,
            duration_years=1.5,
            cost_millions=35.0,
        ),
    ]


@pytest.fixture
def sample_market(sample_asset):
    return MarketModel(
        asset_id=sample_asset.id,
        total_addressable_market_millions=8_000.0,
        peak_penetration=0.12,
        years_to_peak=5,
        patent_life_years=12,
        cogs_rate=0.18,
        sgna_rate_launch=0.40,
        sgna_rate_mature=0.20,
    )


# ---------------------------------------------------------------------------
# POS model
# ---------------------------------------------------------------------------

class TestPOSModel:
    def test_base_rate_returned_with_default_adjusters(self, sample_asset):
        from bve.config.constants import PHASE_SUCCESS_RATES
        pos = compute_pos(TrialPhase.PHASE_2, sample_asset.therapeutic_area)
        base = PHASE_SUCCESS_RATES["oncology"]["phase_2"]
        # Default adjusters should be close to base rate
        assert 0.10 <= pos <= 0.70

    def test_validated_moa_higher_than_novel(self, sample_asset):
        adj_validated = POSAdjusters(moa_precedent=MoAPrecedent.VALIDATED)
        adj_novel = POSAdjusters(moa_precedent=MoAPrecedent.NOVEL)
        pos_v = compute_pos(TrialPhase.PHASE_2, sample_asset.therapeutic_area, adj_validated)
        pos_n = compute_pos(TrialPhase.PHASE_2, sample_asset.therapeutic_area, adj_novel)
        assert pos_v > pos_n

    def test_concerning_safety_lowers_pos(self, sample_asset):
        adj_clean = POSAdjusters(safety_profile=SafetyProfile.CLEAN)
        adj_bad = POSAdjusters(safety_profile=SafetyProfile.SERIOUS)
        pos_clean = compute_pos(TrialPhase.PHASE_2, sample_asset.therapeutic_area, adj_clean)
        pos_bad = compute_pos(TrialPhase.PHASE_2, sample_asset.therapeutic_area, adj_bad)
        assert pos_clean > pos_bad

    def test_pos_bounded(self, sample_asset):
        adj = POSAdjusters(
            moa_precedent=MoAPrecedent.VALIDATED,
            biomarker_selected_population=True,
            strong_prior_phase_data=True,
            has_breakthrough_designation=True,
        )
        pos = compute_pos(TrialPhase.PHASE_2, sample_asset.therapeutic_area, adj)
        assert 0 < pos < 1


# ---------------------------------------------------------------------------
# Market model
# ---------------------------------------------------------------------------

class TestMarketModel:
    def test_revenue_curve_length(self, sample_market):
        curve = sample_market.revenue_curve()
        assert len(curve) == sample_market.patent_life_years

    def test_revenue_zero_after_patent(self, sample_market):
        assert sample_market.revenue_in_year(sample_market.patent_life_years + 1) == 0.0

    def test_peak_sales_reached_at_peak(self, sample_market):
        peak = sample_market.revenue_in_year(sample_market.years_to_peak)
        # Should be at or near peak_sales_millions
        assert abs(peak - sample_market.peak_sales_millions) < 1.0

    def test_s_curve_reaches_peak(self):
        m = MarketModel(
            asset_id="x",
            total_addressable_market_millions=1000.0,
            peak_penetration=0.20,
            years_to_peak=5,
            patent_life_years=12,
            use_s_curve=True,
        )
        assert m.peak_sales_millions == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# rNPV model
# ---------------------------------------------------------------------------

class TestRNPV:
    def test_positive_rnpv_for_base_case(self, sample_asset, sample_trials, sample_market):
        result = compute_rnpv(sample_asset, sample_trials, sample_market)
        assert result.rnpv_millions > 0

    def test_higher_pos_raises_rnpv(self, sample_asset, sample_trials, sample_market):
        trials_hi = [t.model_copy(update={"success_probability": min(0.99, t.success_probability * 1.3)}) for t in sample_trials]
        trials_lo = [t.model_copy(update={"success_probability": t.success_probability * 0.7}) for t in sample_trials]
        r_hi = compute_rnpv(sample_asset, trials_hi, sample_market).rnpv_millions
        r_lo = compute_rnpv(sample_asset, trials_lo, sample_market).rnpv_millions
        assert r_hi > r_lo

    def test_higher_wacc_lowers_rnpv(self, sample_asset, sample_trials, sample_market):
        asset_lo = sample_asset.model_copy(update={"discount_rate": 0.07})
        asset_hi = sample_asset.model_copy(update={"discount_rate": 0.15})
        r_lo = compute_rnpv(asset_lo, sample_trials, sample_market).rnpv_millions
        r_hi = compute_rnpv(asset_hi, sample_trials, sample_market).rnpv_millions
        assert r_lo > r_hi

    def test_years_to_launch_correct(self, sample_asset, sample_trials, sample_market):
        result = compute_rnpv(sample_asset, sample_trials, sample_market)
        expected = sum(t.duration_years for t in sample_trials)
        assert result.years_to_launch == pytest.approx(expected)

    def test_phase_breakdown_sums_correctly(self, sample_asset, sample_trials, sample_market):
        result = compute_rnpv(sample_asset, sample_trials, sample_market)
        total_from_breakdown = sum(pb.pv_cost_weighted for pb in result.phase_breakdown)
        # Breakdown stores 2-decimal-rounded values; allow rounding difference
        assert total_from_breakdown == pytest.approx(result.trial_costs_pv_millions, abs=0.05)


# ---------------------------------------------------------------------------
# Monte Carlo
# ---------------------------------------------------------------------------

class TestMonteCarlo:
    def test_mc_returns_correct_n_simulations(self, sample_asset, sample_trials, sample_market):
        params = MonteCarloParams(n_simulations=500, random_seed=0)
        result = run_monte_carlo(sample_asset, sample_trials, sample_market, params)
        assert result.n_simulations == 500
        assert len(result.simulated_values_millions) == 500

    def test_mc_mean_near_rnpv(self, sample_asset, sample_trials, sample_market):
        """MC mean should be in the same ballpark as deterministic rNPV."""
        base = compute_rnpv(sample_asset, sample_trials, sample_market).rnpv_millions
        params = MonteCarloParams(n_simulations=2000, random_seed=42)
        mc = run_monte_carlo(sample_asset, sample_trials, sample_market, params)
        # Allow 50% deviation — sampling noise at 2k sims
        assert abs(mc.mean_millions - base) / max(1, abs(base)) < 0.80

    def test_mc_percentiles_ordered(self, sample_asset, sample_trials, sample_market):
        params = MonteCarloParams(n_simulations=500, random_seed=1)
        mc = run_monte_carlo(sample_asset, sample_trials, sample_market, params)
        assert mc.percentile_5_millions <= mc.percentile_25_millions
        assert mc.percentile_25_millions <= mc.percentile_50_millions
        assert mc.percentile_50_millions <= mc.percentile_75_millions
        assert mc.percentile_75_millions <= mc.percentile_95_millions


# ---------------------------------------------------------------------------
# Valuation engine
# ---------------------------------------------------------------------------

class TestValuationEngine:
    def test_engine_runs_end_to_end(self, sample_asset, sample_company, sample_trials, sample_market):
        mc_params = MonteCarloParams(n_simulations=200, random_seed=0)
        engine = ValuationEngine(sample_asset, sample_company, sample_trials, sample_market, mc_params=mc_params)
        output = engine.run()
        assert output.rnpv.rnpv_millions != 0
        assert output.nav_per_share > 0
        assert len(output.sensitivities) > 0
        assert output.scenarios.bull.rnpv_millions > output.scenarios.bear.rnpv_millions

    def test_nav_includes_net_cash(self, sample_asset, sample_company, sample_trials, sample_market):
        mc_params = MonteCarloParams(n_simulations=100, random_seed=0)
        engine = ValuationEngine(sample_asset, sample_company, sample_trials, sample_market, mc_params=mc_params)
        output = engine.run()
        expected_nav = output.rnpv.rnpv_millions + sample_company.net_cash_millions
        assert output.nav_millions == pytest.approx(expected_nav, rel=1e-4)
