"""
Tests for Sprint C2: competition-driven price pressure.

Coverage areas
--------------
1. Default behavior — no effect (backward compat)
2. effective_annual_erosion_rate() formula
3. price_pressure_multiplier() cumulative mechanics
4. No competitors → base erosion only
5. Active approved competitors increase erosion
6. Pipeline-only competitors do NOT count toward price pressure (base case)
7. Year-by-year ramp: new competitor entry mid-patent increases pressure
8. Revenue in MarketModel — TAM mode
9. Revenue in MarketModel — patient-based mode
10. No double-counting with market-fraction logic
11. sample_launch_outcomes() propagates price pressure fields
12. Edge cases: high pressure, zero pressure, fast path
"""
from __future__ import annotations

import pytest

from bve.models.competition_model import CompetitionModel, CompetitorLaunch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _comp(
    name: str = "Drug-A",
    status: str = "approved",
    launch_year_relative: float = -2,
    peak_market_share: float = 0.20,
    years_to_peak: int = 2,
    approval_probability: float = 1.0,
) -> CompetitorLaunch:
    return CompetitorLaunch(
        name=name,
        status=status,
        launch_year_relative=launch_year_relative,
        peak_market_share=peak_market_share,
        years_to_peak=years_to_peak,
        approval_probability=approval_probability,
    )


def _model_with_pressure(
    competitors: list[CompetitorLaunch],
    base_rate: float = 0.0,
    factor: float = 0.02,
) -> CompetitionModel:
    return CompetitionModel(
        competitors=competitors,
        base_annual_price_erosion_rate=base_rate,
        price_pressure_factor_per_competitor=factor,
    )


def _tam_market(
    competition: CompetitionModel | None = None,
    tam: float = 1_000.0,
    peak_pen: float = 0.20,
    patent_life: int = 12,
):
    from bve.models.market_model import MarketModel
    kwargs: dict = dict(
        asset_id="test",
        total_addressable_market_millions=tam,
        peak_penetration=peak_pen,
        patent_life_years=patent_life,
        adoption_curve_mode="s_curve",
        years_to_peak=4,
    )
    if competition is not None:
        kwargs["competition_model"] = competition
    return MarketModel(**kwargs)


# ---------------------------------------------------------------------------
# 1. Default behavior — backward compat
# ---------------------------------------------------------------------------

class TestDefaultNoEffect:
    def test_default_fields(self):
        m = CompetitionModel()
        assert m.price_pressure_factor_per_competitor == pytest.approx(0.0)
        assert m.base_annual_price_erosion_rate == pytest.approx(0.0)

    def test_effective_rate_returns_zero_by_default(self):
        m = CompetitionModel(competitors=[_comp()])
        for yr in range(1, 13):
            assert m.effective_annual_erosion_rate(yr) == pytest.approx(0.0)

    def test_multiplier_returns_one_by_default(self):
        m = CompetitionModel(competitors=[_comp()])
        for yr in range(1, 13):
            assert m.price_pressure_multiplier(yr) == pytest.approx(1.0)

    def test_market_revenue_unchanged_without_pressure(self):
        comp = CompetitionModel(competitors=[_comp()])
        comp_pp = CompetitionModel(
            competitors=[_comp()],
            price_pressure_factor_per_competitor=0.0,
            base_annual_price_erosion_rate=0.0,
        )
        for yr in range(1, 13):
            assert comp.our_available_market_fraction(yr) == pytest.approx(
                comp_pp.our_available_market_fraction(yr)
            )
            assert comp.price_pressure_multiplier(yr) == pytest.approx(
                comp_pp.price_pressure_multiplier(yr)
            )


# ---------------------------------------------------------------------------
# 2. effective_annual_erosion_rate() formula
# ---------------------------------------------------------------------------

class TestEffectiveErosionRate:
    def test_no_competitors_base_rate_only(self):
        m = CompetitionModel(base_annual_price_erosion_rate=0.03)
        # No competitors, no active count → rate = base
        assert m.effective_annual_erosion_rate(1) == pytest.approx(0.03)
        assert m.effective_annual_erosion_rate(5) == pytest.approx(0.03)

    def test_one_approved_active_competitor(self):
        # Competitor launched -2 years ago, peaks over 2yr → already at peak by y1
        comp = _comp(launch_year_relative=-2, years_to_peak=2)
        m = CompetitionModel(
            competitors=[comp],
            base_annual_price_erosion_rate=0.01,
            price_pressure_factor_per_competitor=0.02,
        )
        # Year 1: 1 active approved competitor → 0.01 + 1 × 0.02 = 0.03
        assert m.effective_annual_erosion_rate(1) == pytest.approx(0.03)

    def test_two_approved_active_competitors(self):
        comps = [
            _comp("A", launch_year_relative=-3, years_to_peak=2),
            _comp("B", launch_year_relative=-1, years_to_peak=2),
        ]
        m = CompetitionModel(
            competitors=comps,
            base_annual_price_erosion_rate=0.01,
            price_pressure_factor_per_competitor=0.02,
        )
        # Year 1: both active → 0.01 + 2 × 0.02 = 0.05
        assert m.effective_annual_erosion_rate(1) == pytest.approx(0.05)

    def test_factor_only_no_base_rate(self):
        comp = _comp(launch_year_relative=-2, years_to_peak=1)
        m = CompetitionModel(
            competitors=[comp],
            price_pressure_factor_per_competitor=0.025,
        )
        assert m.effective_annual_erosion_rate(1) == pytest.approx(0.025)

    def test_capped_at_one(self):
        # Many competitors × high factor can exceed 1.0 — should be capped
        comps = [_comp(f"Drug-{i}", launch_year_relative=-3, years_to_peak=1) for i in range(10)]
        m = CompetitionModel(
            competitors=comps,
            price_pressure_factor_per_competitor=0.20,
        )
        assert m.effective_annual_erosion_rate(1) <= 1.0

    def test_both_fields_zero_returns_zero(self):
        comp = _comp()
        m = CompetitionModel(competitors=[comp])
        assert m.effective_annual_erosion_rate(1) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 3. price_pressure_multiplier() cumulative mechanics
# ---------------------------------------------------------------------------

class TestPricePressureMultiplier:
    def test_year_1_always_one(self):
        """Year 1 = launch year. No erosion has occurred yet."""
        m = _model_with_pressure([_comp(launch_year_relative=-2, years_to_peak=1)])
        assert m.price_pressure_multiplier(1) == pytest.approx(1.0)

    def test_year_2_applies_one_period(self):
        comp = _comp(launch_year_relative=-2, years_to_peak=1)
        m = _model_with_pressure([comp], base_rate=0.0, factor=0.04)
        # effective_rate(y=1) = 0.04 (1 active competitor)
        # multiplier(2) = 1 - 0.04 = 0.96
        assert m.price_pressure_multiplier(2) == pytest.approx(0.96)

    def test_year_3_compounds(self):
        comp = _comp(launch_year_relative=-2, years_to_peak=1)
        m = _model_with_pressure([comp], factor=0.04)
        # multiplier(3) = 0.96 × 0.96 = 0.9216
        assert m.price_pressure_multiplier(3) == pytest.approx(0.96 ** 2)

    def test_cumulative_with_constant_rate(self):
        """With static competitor count, multiplier = (1-rate)^(year-1)."""
        comp = _comp(launch_year_relative=-5, years_to_peak=1)  # fully ramped before y1
        factor = 0.03
        m = _model_with_pressure([comp], factor=factor)
        for yr in range(1, 8):
            expected = (1.0 - factor) ** (yr - 1)
            assert m.price_pressure_multiplier(yr) == pytest.approx(expected, rel=1e-6)

    def test_fast_path_both_zero(self):
        """When both fields are 0, multiplier returns 1.0 without iteration."""
        m = CompetitionModel(competitors=[_comp()])
        for yr in range(1, 15):
            assert m.price_pressure_multiplier(yr) == pytest.approx(1.0)

    def test_multiplier_decreasing_monotonically(self):
        comp = _comp(launch_year_relative=-3, years_to_peak=1)
        m = _model_with_pressure([comp], factor=0.02)
        mults = [m.price_pressure_multiplier(yr) for yr in range(1, 13)]
        for i in range(len(mults) - 1):
            assert mults[i] >= mults[i + 1]

    def test_multiplier_non_negative(self):
        comps = [_comp(f"D{i}", launch_year_relative=-5, years_to_peak=1) for i in range(5)]
        m = _model_with_pressure(comps, base_rate=0.10, factor=0.20)
        for yr in range(1, 20):
            assert m.price_pressure_multiplier(yr) >= 0.0


# ---------------------------------------------------------------------------
# 4. No competitors → base erosion only
# ---------------------------------------------------------------------------

class TestNoCompetitors:
    def test_no_competitors_base_rate_applies(self):
        m = CompetitionModel(
            competitors=[],
            base_annual_price_erosion_rate=0.03,
            price_pressure_factor_per_competitor=0.05,
        )
        # With no competitors, N_active=0 → rate = base_rate = 0.03
        assert m.effective_annual_erosion_rate(1) == pytest.approx(0.03)
        assert m.price_pressure_multiplier(2) == pytest.approx(0.97)
        assert m.price_pressure_multiplier(3) == pytest.approx(0.97 ** 2)

    def test_no_competitors_factor_alone_no_effect(self):
        m = CompetitionModel(
            competitors=[],
            price_pressure_factor_per_competitor=0.05,
        )
        # N_active=0, base_rate=0 → rate = 0 → multiplier = 1.0
        for yr in range(1, 13):
            assert m.price_pressure_multiplier(yr) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 5. Active approved competitors increase erosion
# ---------------------------------------------------------------------------

class TestActiveCompetitorsIncreaseErosion:
    def test_one_vs_two_competitors(self):
        comp_a = _comp("A", launch_year_relative=-3, years_to_peak=1)
        comp_b = _comp("B", launch_year_relative=-3, years_to_peak=1)
        m1 = _model_with_pressure([comp_a], factor=0.02)
        m2 = _model_with_pressure([comp_a, comp_b], factor=0.02)
        # m2 has 2 active → higher erosion → lower multiplier at year 3+
        assert m2.price_pressure_multiplier(5) < m1.price_pressure_multiplier(5)

    def test_competitor_not_yet_launched_does_not_count(self):
        # Future competitor launches at year 3
        comp = _comp(launch_year_relative=3, years_to_peak=2)
        m = _model_with_pressure([comp], factor=0.05)
        # Years 1, 2: competitor not yet launched → N_active=0 → rate=0 → mult=1
        assert m.effective_annual_erosion_rate(1) == pytest.approx(0.0)
        assert m.effective_annual_erosion_rate(2) == pytest.approx(0.0)
        assert m.price_pressure_multiplier(1) == pytest.approx(1.0)
        assert m.price_pressure_multiplier(2) == pytest.approx(1.0)
        assert m.price_pressure_multiplier(3) == pytest.approx(1.0)

    def test_competitor_launch_activates_pressure_from_that_year(self):
        # Competitor enters at year 3 (launch_year_relative=3, ytp=1)
        comp = _comp(launch_year_relative=3, years_to_peak=1)
        m = _model_with_pressure([comp], factor=0.04)
        # Year 3: competitor has just entered; _single_competitor_share(year=3):
        # years_from_their_launch = 3 - 3 = 0 → share = 0 → not counted yet
        # Year 4: years_from_their_launch = 1 → ramp starts → positive share
        assert m.effective_annual_erosion_rate(3) == pytest.approx(0.0)
        assert m.effective_annual_erosion_rate(4) == pytest.approx(0.04)
        # multiplier(5) should start decaying because effective_rate(4) > 0
        assert m.price_pressure_multiplier(5) < m.price_pressure_multiplier(4)


# ---------------------------------------------------------------------------
# 6. Pipeline competitors do NOT count in base case
# ---------------------------------------------------------------------------

class TestPipelineCompetitors:
    def test_pipeline_phase3_not_counted(self):
        """status='phase_3' competitor should NOT count in _n_active_approved_competitors."""
        pipeline = _comp(
            status="phase_3",
            launch_year_relative=-2,
            years_to_peak=2,
            approval_probability=0.70,
        )
        m = _model_with_pressure([pipeline], factor=0.05)
        # Pipeline competitor: approval_probability=0.70 weights their market share,
        # but _n_active_approved_competitors() requires status=="approved" → count=0
        assert m.effective_annual_erosion_rate(1) == pytest.approx(0.0)
        assert m.price_pressure_multiplier(2) == pytest.approx(1.0)

    def test_approved_plus_pipeline_only_approved_counts(self):
        approved = _comp("Approved", status="approved", launch_year_relative=-2, years_to_peak=1)
        pipeline = _comp("Pipeline", status="phase_3", launch_year_relative=-1,
                          years_to_peak=2, approval_probability=0.60)
        m = _model_with_pressure([approved, pipeline], factor=0.03)
        # Only 1 approved active competitor counted → rate = 0.03
        assert m.effective_annual_erosion_rate(1) == pytest.approx(0.03)

    def test_pipeline_still_affects_market_fraction(self):
        """Pipeline competitors affect volume (market fraction) but not price pressure."""
        pipeline = _comp(
            status="phase_3",
            launch_year_relative=-2,
            years_to_peak=2,
            approval_probability=0.70,
        )
        m = _model_with_pressure([pipeline], factor=0.05)
        # Market fraction IS reduced by pipeline (probability-weighted share)
        assert m.combined_competitor_share(1) > 0.0
        assert m.our_available_market_fraction(1) < 1.0
        # But price pressure is NOT triggered
        assert m.price_pressure_multiplier(2) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 7. New competitor entry mid-patent increases pressure from that year
# ---------------------------------------------------------------------------

class TestMidPatentCompetitorEntry:
    def test_step_change_at_entry_year(self):
        # Two competitors: one pre-existing, one entering at year 4
        early = _comp("Early", launch_year_relative=-2, years_to_peak=1)
        late = _comp("Late", launch_year_relative=4, years_to_peak=1)
        m = _model_with_pressure([early, late], factor=0.02)
        # Years 1-4: 1 active → rate=0.02
        assert m.effective_annual_erosion_rate(1) == pytest.approx(0.02)
        assert m.effective_annual_erosion_rate(4) == pytest.approx(0.02)
        # Year 5: late has launched (yr=4+1=5 from our launch → years_from_their_launch=1)
        assert m.effective_annual_erosion_rate(5) == pytest.approx(0.04)

    def test_multiplier_steepens_after_new_entry(self):
        early = _comp("Early", launch_year_relative=-2, years_to_peak=1)
        late = _comp("Late", launch_year_relative=3, years_to_peak=1)
        m = _model_with_pressure([early, late], factor=0.03)
        # Pre-entry: slope = -0.03/yr; post-entry: slope = -0.06/yr
        mult_3 = m.price_pressure_multiplier(3)
        mult_4 = m.price_pressure_multiplier(4)
        mult_5 = m.price_pressure_multiplier(5)
        mult_6 = m.price_pressure_multiplier(6)
        drop_pre = mult_3 - mult_4   # pre-entry period
        drop_post = mult_5 - mult_6  # post-entry period (assuming late enters at yr 4)
        assert drop_post > drop_pre  # steeper drop after second competitor active


# ---------------------------------------------------------------------------
# 8. Revenue in MarketModel — TAM mode
# ---------------------------------------------------------------------------

class TestMarketModelTAM:
    def test_no_pressure_same_revenue(self):
        comp_no_pp = CompetitionModel(competitors=[_comp()])
        comp_with_pp = CompetitionModel(
            competitors=[_comp()],
            price_pressure_factor_per_competitor=0.0,
        )
        m1 = _tam_market(comp_no_pp)
        m2 = _tam_market(comp_with_pp)
        for yr in range(1, 13):
            assert m1.revenue_in_year(yr) == pytest.approx(m2.revenue_in_year(yr))

    def test_price_pressure_reduces_late_year_revenue(self):
        comp_base = CompetitionModel(competitors=[_comp(launch_year_relative=-2, years_to_peak=1)])
        comp_pp = CompetitionModel(
            competitors=[_comp(launch_year_relative=-2, years_to_peak=1)],
            price_pressure_factor_per_competitor=0.03,
        )
        m_base = _tam_market(comp_base)
        m_pp = _tam_market(comp_pp)
        # Year 1: multiplier=1.0 (no erosion yet) → same fraction from market
        # Year 5: multiplier < 1.0 → lower revenue
        # (market fraction itself might be the same — same competitor share)
        for yr in range(2, 13):
            assert m_pp.revenue_in_year(yr) <= m_base.revenue_in_year(yr) + 1e-9

    def test_price_pressure_proportional_at_each_year(self):
        """
        Revenue with price pressure = base_revenue × price_pressure_multiplier(yr).
        Market fraction and uptake curve are the same — only price erodes.
        """
        comp = _comp(launch_year_relative=-3, years_to_peak=1)
        comp_model_base = CompetitionModel(competitors=[comp])
        comp_model_pp = CompetitionModel(
            competitors=[comp],
            price_pressure_factor_per_competitor=0.04,
        )
        m_base = _tam_market(comp_model_base)
        m_pp = _tam_market(comp_model_pp)
        for yr in range(1, 13):
            expected = m_base.revenue_in_year(yr) * comp_model_pp.price_pressure_multiplier(yr)
            assert m_pp.revenue_in_year(yr) == pytest.approx(expected, rel=1e-6)

    def test_year1_revenue_unaffected_by_price_pressure(self):
        """Year 1 = launch year: price_pressure_multiplier = 1.0."""
        comp = _comp(launch_year_relative=-2, years_to_peak=1)
        comp_base = CompetitionModel(competitors=[comp])
        comp_pp = CompetitionModel(
            competitors=[comp],
            price_pressure_factor_per_competitor=0.10,
        )
        m_base = _tam_market(comp_base)
        m_pp = _tam_market(comp_pp)
        assert m_pp.revenue_in_year(1) == pytest.approx(m_base.revenue_in_year(1), rel=1e-6)


# ---------------------------------------------------------------------------
# 9. Revenue in MarketModel — patient-based mode
# ---------------------------------------------------------------------------

class TestMarketModelPatientBased:
    def _patient_market(self, competition: CompetitionModel):
        from bve.models.market_model import MarketModel
        return MarketModel(
            asset_id="test",
            addressable_patients_annual=50_000,
            net_price_per_patient_usd=80_000.0,
            peak_penetration=0.20,
            patent_life_years=12,
            adoption_curve_mode="s_curve",
            years_to_peak=4,
            competition_model=competition,
        )

    def test_price_pressure_reduces_patient_revenue(self):
        comp = _comp(launch_year_relative=-2, years_to_peak=1)
        m_base = self._patient_market(CompetitionModel(competitors=[comp]))
        m_pp = self._patient_market(CompetitionModel(
            competitors=[comp],
            price_pressure_factor_per_competitor=0.04,
        ))
        for yr in range(2, 13):
            assert m_pp.revenue_in_year(yr) <= m_base.revenue_in_year(yr) + 1e-9

    def test_proportional_reduction_patient_mode(self):
        comp = _comp(launch_year_relative=-3, years_to_peak=1)
        comp_base = CompetitionModel(competitors=[comp])
        comp_pp = CompetitionModel(
            competitors=[comp],
            price_pressure_factor_per_competitor=0.03,
        )
        m_base = self._patient_market(comp_base)
        m_pp = self._patient_market(comp_pp)
        for yr in range(1, 13):
            expected = m_base.revenue_in_year(yr) * comp_pp.price_pressure_multiplier(yr)
            assert m_pp.revenue_in_year(yr) == pytest.approx(expected, rel=1e-6)


# ---------------------------------------------------------------------------
# 10. No double-counting with market fraction logic
# ---------------------------------------------------------------------------

class TestNoDoubleCountingWithMarketFraction:
    def test_price_pressure_independent_of_market_fraction(self):
        """
        market_fraction × price_multiplier = total revenue factor.
        Neither is applied more than once.
        """
        comp = _comp(launch_year_relative=-2, years_to_peak=2, peak_market_share=0.30)
        comp_model = CompetitionModel(
            competitors=[comp],
            price_pressure_factor_per_competitor=0.03,
        )
        m_pp = _tam_market(comp_model)
        m_no_comp = _tam_market()  # no competition at all

        for yr in range(1, 13):
            frac = comp_model.our_available_market_fraction(yr)
            price_mult = comp_model.price_pressure_multiplier(yr)
            # Revenue with both = no-competition revenue × fraction × price_mult
            assert m_pp.revenue_in_year(yr) == pytest.approx(
                m_no_comp.revenue_in_year(yr) * frac * price_mult,
                rel=1e-5,
            )

    def test_market_fraction_unchanged_by_adding_price_pressure(self):
        """our_available_market_fraction() must be identical with/without price pressure."""
        comp = _comp(launch_year_relative=-2, years_to_peak=2)
        m_base = CompetitionModel(competitors=[comp])
        m_pp = CompetitionModel(
            competitors=[comp],
            price_pressure_factor_per_competitor=0.05,
            base_annual_price_erosion_rate=0.02,
        )
        for yr in range(1, 13):
            assert m_base.our_available_market_fraction(yr) == pytest.approx(
                m_pp.our_available_market_fraction(yr)
            )


# ---------------------------------------------------------------------------
# 11. sample_launch_outcomes() propagates price pressure fields
# ---------------------------------------------------------------------------

class TestSampleLaunchOutcomesPropagation:
    def test_price_pressure_fields_propagated(self):
        import numpy as np
        rng = np.random.default_rng(42)
        m = CompetitionModel(
            competitors=[
                _comp("Approved", status="approved"),
                _comp("Pipeline", status="phase_3", approval_probability=0.70),
            ],
            base_annual_price_erosion_rate=0.02,
            price_pressure_factor_per_competitor=0.03,
        )
        sampled = m.sample_launch_outcomes(rng)
        assert sampled.base_annual_price_erosion_rate == pytest.approx(0.02)
        assert sampled.price_pressure_factor_per_competitor == pytest.approx(0.03)

    def test_pipeline_not_counted_even_when_sampled(self):
        """
        Pipeline competitor sampled into simulation retains status='phase_3',
        so it STILL does not count toward _n_active_approved_competitors
        and hence does not increase price pressure.
        """
        import numpy as np
        # Force pipeline to always be included: approval_probability=1.0 but status=phase_3
        pipeline = _comp("Pipeline", status="phase_3",
                          launch_year_relative=-2, years_to_peak=1,
                          approval_probability=1.0)
        m = CompetitionModel(
            competitors=[pipeline],
            price_pressure_factor_per_competitor=0.05,
        )
        rng = np.random.default_rng(0)
        sampled = m.sample_launch_outcomes(rng)
        # Pipeline is included (probability=1.0) but status still "phase_3"
        assert any(c.name == "Pipeline" for c in sampled.competitors)
        # Price pressure still 0 because status != "approved"
        assert sampled.effective_annual_erosion_rate(1) == pytest.approx(0.0)
        assert sampled.price_pressure_multiplier(2) == pytest.approx(1.0)

    def test_other_fields_also_propagated(self):
        import numpy as np
        rng = np.random.default_rng(1)
        from bve.models.competition_model import CrowdingModel, FirstMoverConfig
        m = CompetitionModel(
            competitors=[_comp()],
            floor_residual_share=0.10,
            competition_mode="steal",
            crowding_model=CrowdingModel(enabled=True),
            first_mover_config=FirstMoverConfig(enabled=True),
            base_annual_price_erosion_rate=0.015,
            price_pressure_factor_per_competitor=0.025,
        )
        sampled = m.sample_launch_outcomes(rng)
        assert sampled.floor_residual_share == pytest.approx(0.10)
        assert sampled.crowding_model.enabled is True
        assert sampled.first_mover_config.enabled is True
        assert sampled.base_annual_price_erosion_rate == pytest.approx(0.015)
        assert sampled.price_pressure_factor_per_competitor == pytest.approx(0.025)


# ---------------------------------------------------------------------------
# 12. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_high_factor_cap_prevents_negative_multiplier(self):
        comps = [_comp(f"D{i}", launch_year_relative=-5, years_to_peak=1) for i in range(5)]
        m = _model_with_pressure(comps, base_rate=0.0, factor=0.30)
        # effective_rate = 5 × 0.30 = 1.50 → capped at 1.0
        assert m.effective_annual_erosion_rate(1) == pytest.approx(1.0)
        # multiplier(2) = 1 - 1.0 = 0.0 → not negative
        assert m.price_pressure_multiplier(2) == pytest.approx(0.0)

    def test_base_rate_only_behaves_like_constant_erosion(self):
        m = CompetitionModel(
            competitors=[],
            base_annual_price_erosion_rate=0.05,
        )
        for yr in range(1, 10):
            expected = 0.95 ** (yr - 1)
            assert m.price_pressure_multiplier(yr) == pytest.approx(expected, rel=1e-6)

    def test_field_validation_bounds(self):
        with pytest.raises(Exception):
            CompetitionModel(price_pressure_factor_per_competitor=-0.01)
        with pytest.raises(Exception):
            CompetitionModel(price_pressure_factor_per_competitor=0.31)
        with pytest.raises(Exception):
            CompetitionModel(base_annual_price_erosion_rate=-0.01)
        with pytest.raises(Exception):
            CompetitionModel(base_annual_price_erosion_rate=0.51)

    def test_existing_competition_tests_still_pass(self):
        """Quick smoke-test that pre-existing CompetitionModel invariants hold."""
        m = CompetitionModel(competitors=[_comp()])
        assert 0.0 <= m.our_available_market_fraction(1) <= 1.0
        assert m.combined_competitor_share(1) >= 0.0
