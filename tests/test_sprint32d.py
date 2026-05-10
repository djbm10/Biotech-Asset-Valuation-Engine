"""
Sprint 32D — Enhanced pipeline competitor sampling tests.

Covers:
- Approved competitors always included in sampled model
- Pipeline competitor: Bernoulli inclusion by approval_probability
- When competitor succeeds: approval_probability set to 1.0 in sampled model
- When competitor fails: excluded from sampled model → no effect
- Launch timing jitter: included pipeline competitors can have launch_year_relative varied
- Launch timing std=0: no jitter (backward-compatible)
- Price pressure: present when competitor sampled-in; absent when sampled-out
- Available market fraction: lower with competitor vs without
- MC std measurably wider when approval_probability ≈ 0.5 vs 1.0
- Timing jitter clips launch_year_relative to ≥ 0
"""
import numpy as np
import pytest

from bve.entities.asset import Asset
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.competition_model import CompetitionModel, CompetitorLaunch
from bve.models.market_model import MarketModel
from bve.models.monte_carlo import MonteCarloParams, run_monte_carlo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _approved_comp(name: str = "ApprovedRival") -> CompetitorLaunch:
    return CompetitorLaunch(
        name=name,
        status="approved",
        launch_year_relative=-2,
        peak_market_share=0.25,
        years_to_peak=3,
        approval_probability=1.0,
    )


def _pipeline_comp(name: str = "PipelineRival", p: float = 0.60,
                   launch_yr: float = 1.0) -> CompetitorLaunch:
    return CompetitorLaunch(
        name=name,
        status="phase_3",
        launch_year_relative=launch_yr,
        peak_market_share=0.20,
        years_to_peak=3,
        approval_probability=p,
    )


def _model(competitors: list[CompetitorLaunch],
           price_pressure: float = 0.0) -> CompetitionModel:
    return CompetitionModel(
        competitors=competitors,
        price_pressure_factor_per_competitor=price_pressure,
    )


def _asset() -> Asset:
    return Asset(
        id="mc32d-001",
        name="Test Drug",
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


def _trials() -> list[ClinicalTrial]:
    return [
        ClinicalTrial(
            asset_id="mc32d-001",
            phase=TrialPhase.PHASE_3,
            success_probability=0.70,
            duration_years=3.0,
            cost_millions=80.0,
        ),
    ]


def _market(comp_model: CompetitionModel | None = None) -> MarketModel:
    return MarketModel(
        asset_id="mc32d-001",
        therapeutic_area="oncology",
        addressable_patients_annual=50_000,
        net_price_per_patient_usd=80_000,
        peak_penetration=0.20,
        years_to_peak=4,
        patent_life_years=12,
        cogs_rate=0.12,
        sgna_rate_launch=0.35,
        sgna_rate_mature=0.18,
        competition_model=comp_model,
    )


# ---------------------------------------------------------------------------
# Approved competitor always included
# ---------------------------------------------------------------------------

class TestApprovedCompetitorAlwaysIncluded:
    def test_approved_always_present(self):
        model = _model([_approved_comp()])
        rng = np.random.default_rng(42)
        for _ in range(20):
            sampled = model.sample_launch_outcomes(rng)
            assert len(sampled.competitors) == 1

    def test_approved_approval_prob_unchanged(self):
        model = _model([_approved_comp()])
        rng = np.random.default_rng(0)
        sampled = model.sample_launch_outcomes(rng)
        assert sampled.competitors[0].approval_probability == 1.0

    def test_approved_launch_year_not_jittered(self):
        model = _model([_approved_comp()])
        rng = np.random.default_rng(1)
        original_yr = _approved_comp().launch_year_relative
        sampled = model.sample_launch_outcomes(rng, launch_timing_std_years=1.0)
        assert sampled.competitors[0].launch_year_relative == original_yr


# ---------------------------------------------------------------------------
# Pipeline competitor Bernoulli sampling
# ---------------------------------------------------------------------------

class TestPipelineBernoulliSampling:
    def test_pipeline_always_present_when_p1(self):
        model = _model([_pipeline_comp(p=1.0)])
        rng = np.random.default_rng(42)
        for _ in range(20):
            sampled = model.sample_launch_outcomes(rng)
            assert len(sampled.competitors) == 1

    def test_pipeline_never_present_when_p0(self):
        model = _model([_pipeline_comp(p=0.0)])
        rng = np.random.default_rng(42)
        for _ in range(20):
            sampled = model.sample_launch_outcomes(rng)
            assert len(sampled.competitors) == 0

    def test_pipeline_sometimes_present_at_p05(self):
        model = _model([_pipeline_comp(p=0.5)])
        rng = np.random.default_rng(77)
        counts = [len(model.sample_launch_outcomes(rng).competitors) for _ in range(200)]
        assert 0 < sum(counts) < 200

    def test_included_pipeline_approval_prob_set_to_one(self):
        model = _model([_pipeline_comp(p=1.0)])
        rng = np.random.default_rng(0)
        sampled = model.sample_launch_outcomes(rng)
        assert sampled.competitors[0].approval_probability == 1.0

    def test_excluded_pipeline_no_competitors(self):
        model = _model([_pipeline_comp(p=0.0)])
        rng = np.random.default_rng(0)
        sampled = model.sample_launch_outcomes(rng)
        assert sampled.competitors == []


# ---------------------------------------------------------------------------
# Launch timing jitter
# ---------------------------------------------------------------------------

class TestLaunchTimingJitter:
    def test_zero_std_preserves_launch_year(self):
        model = _model([_pipeline_comp(p=1.0, launch_yr=3.0)])
        rng = np.random.default_rng(5)
        sampled = model.sample_launch_outcomes(rng, launch_timing_std_years=0.0)
        assert sampled.competitors[0].launch_year_relative == pytest.approx(3.0)

    def test_nonzero_std_varies_launch_year(self):
        model = _model([_pipeline_comp(p=1.0, launch_yr=3.0)])
        launch_years = []
        for seed in range(100):
            rng = np.random.default_rng(seed)
            sampled = model.sample_launch_outcomes(rng, launch_timing_std_years=1.0)
            if sampled.competitors:
                launch_years.append(sampled.competitors[0].launch_year_relative)
        assert len(set(round(y, 4) for y in launch_years)) > 5

    def test_launch_year_clipped_to_zero(self):
        """Even with large negative jitter, launch_year_relative >= 0."""
        model = _model([_pipeline_comp(p=1.0, launch_yr=0.5)])
        for seed in range(50):
            rng = np.random.default_rng(seed)
            sampled = model.sample_launch_outcomes(rng, launch_timing_std_years=10.0)
            if sampled.competitors:
                assert sampled.competitors[0].launch_year_relative >= 0.0

    def test_approved_competitor_launch_year_not_jittered(self):
        """Jitter only applies to pipeline competitors, not approved."""
        model = _model([_approved_comp(), _pipeline_comp(p=1.0, launch_yr=2.0)])
        rng = np.random.default_rng(9)
        sampled = model.sample_launch_outcomes(rng, launch_timing_std_years=2.0)
        approved = next(c for c in sampled.competitors if c.status == "approved")
        assert approved.launch_year_relative == _approved_comp().launch_year_relative


# ---------------------------------------------------------------------------
# Price pressure: present when competitor in, absent when out
# ---------------------------------------------------------------------------

class TestPricePressure:
    def test_no_competitor_no_price_pressure(self):
        model = CompetitionModel(
            competitors=[],
            price_pressure_factor_per_competitor=0.05,
        )
        # With no competitors, price_pressure_multiplier should be 1.0 at all years
        for yr in range(1, 6):
            assert model.price_pressure_multiplier(yr) == pytest.approx(1.0)

    def test_approved_competitor_applies_price_pressure(self):
        model = CompetitionModel(
            competitors=[_approved_comp()],
            price_pressure_factor_per_competitor=0.05,
        )
        rng = np.random.default_rng(0)
        sampled = model.sample_launch_outcomes(rng)
        # sampled has approved comp → price pressure applies at year ≥ 1
        assert sampled.price_pressure_multiplier(3) < 1.0

    def test_excluded_pipeline_no_price_pressure(self):
        model = CompetitionModel(
            competitors=[_pipeline_comp(p=0.0)],
            price_pressure_factor_per_competitor=0.05,
        )
        rng = np.random.default_rng(0)
        sampled = model.sample_launch_outcomes(rng)
        assert sampled.price_pressure_multiplier(3) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Available market fraction: lower with competitor
# ---------------------------------------------------------------------------

class TestAvailableMarketFraction:
    def test_no_competitors_full_market(self):
        model = _model([])
        assert model.our_available_market_fraction(1) == pytest.approx(1.0)

    def test_approved_competitor_reduces_fraction(self):
        model = _model([_approved_comp()])
        assert model.our_available_market_fraction(5) < 1.0

    def test_sampled_in_competitor_reduces_fraction(self):
        model = _model([_pipeline_comp(p=1.0)])
        rng = np.random.default_rng(0)
        sampled = model.sample_launch_outcomes(rng)
        assert sampled.our_available_market_fraction(5) < 1.0

    def test_sampled_out_competitor_full_fraction(self):
        model = _model([_pipeline_comp(p=0.0)])
        rng = np.random.default_rng(0)
        sampled = model.sample_launch_outcomes(rng)
        # no competitor sampled → full market available
        assert sampled.our_available_market_fraction(5) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# MC std wider at P=0.5 vs P=1.0
# ---------------------------------------------------------------------------

class TestMCStdWidthByApprovalProb:
    def _std_for_p(self, p: float, n: int = 800, seed: int = 0) -> float:
        comp = CompetitionModel(
            competitors=[_pipeline_comp(p=p)],
        )
        market = _market(comp)
        params = MonteCarloParams(n_simulations=n, random_seed=seed)
        result = run_monte_carlo(_asset(), _trials(), market, params)
        return result.std_millions

    def test_std_wider_at_p05_than_p10(self):
        std_p05 = self._std_for_p(0.5, n=600, seed=1)
        std_p10 = self._std_for_p(1.0, n=600, seed=1)
        assert std_p05 > std_p10, (
            f"Expected wider std at P=0.5 ({std_p05:.1f}) vs P=1.0 ({std_p10:.1f})"
        )
