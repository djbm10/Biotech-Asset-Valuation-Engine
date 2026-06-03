"""Tests for CrowdingModel, FirstMoverConfig, ClassSaturationProfile, and S-curve ramps."""
import pytest

from bve.models.competition_model import (
    ClassSaturationProfile,
    CompetitionModel,
    CompetitorLaunch,
    CrowdingModel,
    FirstMoverConfig,
)


@pytest.fixture
def four_approved_competitors():
    """Four approved competitors active from year 1, each with 0.10 market share."""
    return [
        CompetitorLaunch(
            name=f"comp_{i}",
            status="approved",
            launch_year_relative=-2,   # already on market
            peak_market_share=0.10,
            years_to_peak=1,
            approval_probability=1.0,
        )
        for i in range(4)
    ]


class TestCrowdingModelDefaults:
    def test_crowding_disabled_by_default(self):
        model = CompetitionModel()
        assert not model.crowding_model.enabled

    def test_crowding_has_no_effect_when_disabled(self, four_approved_competitors):
        model = CompetitionModel(
            competitors=four_approved_competitors,
            crowding_model=CrowdingModel(enabled=False),
        )
        model_no_crowd = CompetitionModel(competitors=four_approved_competitors)
        assert model.our_available_market_fraction(1) == model_no_crowd.our_available_market_fraction(1)


class TestCrowdingApplied:
    def test_crowding_reduces_available_fraction(self, four_approved_competitors):
        """4 approved competitors > threshold(3) → crowding reduces available fraction."""
        model_with = CompetitionModel(
            competitors=four_approved_competitors,
            crowding_model=CrowdingModel(enabled=True, crowding_threshold=3, share_decay_per_competitor=0.15),
        )
        model_without = CompetitionModel(
            competitors=four_approved_competitors,
            crowding_model=CrowdingModel(enabled=False),
        )
        assert model_with.our_available_market_fraction(1) < model_without.our_available_market_fraction(1)

    def test_crowding_decay_math(self, four_approved_competitors):
        """With 4 active and threshold=3, excess=1 → multiplier = (1 - 0.15)^1 = 0.85."""
        model = CompetitionModel(
            competitors=four_approved_competitors,
            crowding_model=CrowdingModel(enabled=True, crowding_threshold=3, share_decay_per_competitor=0.15),
        )
        base = max(0.10, 1.0 - 4 * 0.10)  # = 0.60
        expected = max(0.10, base * (1 - 0.15) ** 1)  # excess = 1
        assert abs(model.our_available_market_fraction(1) - expected) < 1e-9

    def test_crowding_no_effect_below_threshold(self, four_approved_competitors):
        """Threshold=5 > 4 active → no crowding applied."""
        model = CompetitionModel(
            competitors=four_approved_competitors,
            crowding_model=CrowdingModel(enabled=True, crowding_threshold=5, share_decay_per_competitor=0.15),
        )
        base = max(0.10, 1.0 - 4 * 0.10)
        assert abs(model.our_available_market_fraction(1) - base) < 1e-9

    def test_crowding_respects_floor(self):
        """Very aggressive crowding should not push below the configured floor.
        floor_residual_share defaults to 0.0 (configurable); set 0.10 to test floor behavior."""
        heavy_competitors = [
            CompetitorLaunch(
                name=f"c{i}",
                status="approved",
                launch_year_relative=-1,
                peak_market_share=0.25,
                years_to_peak=1,
                approval_probability=1.0,
            )
            for i in range(6)
        ]
        model = CompetitionModel(
            competitors=heavy_competitors,
            crowding_model=CrowdingModel(enabled=True, crowding_threshold=2, share_decay_per_competitor=0.50),
            floor_residual_share=0.10,  # explicit floor; default is 0.0
        )
        assert model.our_available_market_fraction(1) >= 0.10

    def test_only_approved_competitors_counted(self):
        """Pipeline competitors (not yet launched) should not count toward crowding."""
        competitors = [
            # 2 approved, already on market
            CompetitorLaunch(name="approved_1", status="approved", launch_year_relative=-1,
                             peak_market_share=0.10, years_to_peak=1, approval_probability=1.0),
            CompetitorLaunch(name="approved_2", status="approved", launch_year_relative=-1,
                             peak_market_share=0.10, years_to_peak=1, approval_probability=1.0),
            # 2 pipeline — not approved, should NOT count
            CompetitorLaunch(name="pipeline_1", status="phase_3", launch_year_relative=2,
                             peak_market_share=0.10, years_to_peak=2, approval_probability=0.6),
            CompetitorLaunch(name="pipeline_2", status="phase_3", launch_year_relative=3,
                             peak_market_share=0.10, years_to_peak=2, approval_probability=0.5),
        ]
        model = CompetitionModel(
            competitors=competitors,
            crowding_model=CrowdingModel(enabled=True, crowding_threshold=3, share_decay_per_competitor=0.15),
        )
        # Only 2 approved with share in year 1 — below threshold; no crowding
        base = max(0.10, 1.0 - 2 * 0.10)
        assert abs(model.our_available_market_fraction(1) - base) < 1e-9


class TestCrowdingPreservedInMonteCarlo:
    def test_sample_launch_outcomes_preserves_crowding_model(self, four_approved_competitors):
        """sample_launch_outcomes() must carry the CrowdingModel to the sampled copy."""
        import numpy as np
        rng = np.random.default_rng(42)
        crowding = CrowdingModel(enabled=True, crowding_threshold=2, share_decay_per_competitor=0.20)
        model = CompetitionModel(competitors=four_approved_competitors, crowding_model=crowding)
        sampled = model.sample_launch_outcomes(rng)
        assert sampled.crowding_model.enabled
        assert sampled.crowding_model.crowding_threshold == 2
        assert sampled.crowding_model.share_decay_per_competitor == 0.20


# ---------------------------------------------------------------------------
# First-Mover Advantage
# ---------------------------------------------------------------------------

def _approved(name: str, launch_year: float, peak: float = 0.20, years_to_peak: int = 3):
    return CompetitorLaunch(
        name=name,
        status="approved",
        launch_year_relative=launch_year,
        peak_market_share=peak,
        years_to_peak=years_to_peak,
        approval_probability=1.0,
    )


class TestFirstMoverDefaults:
    def test_disabled_by_default(self):
        model = CompetitionModel()
        assert not model.first_mover_config.enabled

    def test_no_effect_when_disabled(self):
        """With first_mover disabled, shares are identical to no-config baseline."""
        comp = _approved("early", -3, peak=0.20)
        late = _approved("late", -1, peak=0.20)
        model_on = CompetitionModel(
            competitors=[comp, late],
            first_mover_config=FirstMoverConfig(enabled=False),
        )
        model_off = CompetitionModel(competitors=[comp, late])
        for yr in range(1, 6):
            assert model_on.combined_competitor_share(yr) == model_off.combined_competitor_share(yr)


class TestFirstMoverBonus:
    def test_first_mover_gets_bonus(self):
        """First mover's share > late entrant's share even with equal peak."""
        comp_early = _approved("early", -3, peak=0.20)
        comp_late = _approved("late", -1, peak=0.20)
        model = CompetitionModel(
            competitors=[comp_early, comp_late],
            first_mover_config=FirstMoverConfig(enabled=True, first_mover_bonus=0.25, late_entrant_penalty=0.10),
        )
        # At year 5 both are at peak — check individual shares
        early_share = model._single_competitor_share(comp_early, 5)
        late_share = model._single_competitor_share(comp_late, 5)
        assert early_share > late_share

    def test_first_mover_bonus_math(self):
        """First mover's effective share == peak × (1 + bonus) at peak."""
        comp = _approved("first", -3, peak=0.20, years_to_peak=1)
        model = CompetitionModel(
            competitors=[comp],
            first_mover_config=FirstMoverConfig(enabled=True, first_mover_bonus=0.25, late_entrant_penalty=0.10),
        )
        # At year 1: years_from_their_launch=4, ramp=1.0 → share = 0.20 × 1.25
        share = model._single_competitor_share(comp, 1)
        assert abs(share - 0.20 * 1.25) < 1e-9

    def test_late_entrant_penalty_math(self):
        """Late entrant's effective share == peak × (1 - penalty) at peak."""
        early = _approved("first", -3, peak=0.20, years_to_peak=1)
        late = _approved("late", -1, peak=0.20, years_to_peak=1)
        model = CompetitionModel(
            competitors=[early, late],
            first_mover_config=FirstMoverConfig(enabled=True, first_mover_bonus=0.25, late_entrant_penalty=0.10),
        )
        late_share = model._single_competitor_share(late, 5)
        assert abs(late_share - 0.20 * 0.90) < 1e-9

    def test_tied_first_movers_both_get_bonus(self):
        """Two competitors with the same earliest launch year both receive the bonus."""
        comp_a = _approved("a", -3, peak=0.20, years_to_peak=1)
        comp_b = _approved("b", -3, peak=0.20, years_to_peak=1)
        comp_c = _approved("c", -1, peak=0.20, years_to_peak=1)
        model = CompetitionModel(
            competitors=[comp_a, comp_b, comp_c],
            first_mover_config=FirstMoverConfig(enabled=True, first_mover_bonus=0.25, late_entrant_penalty=0.10),
        )
        share_a = model._single_competitor_share(comp_a, 5)
        share_b = model._single_competitor_share(comp_b, 5)
        share_c = model._single_competitor_share(comp_c, 5)
        assert abs(share_a - 0.20 * 1.25) < 1e-9
        assert abs(share_b - 0.20 * 1.25) < 1e-9
        assert abs(share_c - 0.20 * 0.90) < 1e-9

    def test_first_mover_applied_before_crowding(self):
        """
        Crowding operates on first-mover-adjusted combined share.
        With first-mover enabled, combined share is higher for first movers,
        so the available fraction for us should differ from crowding-only result.
        """
        comps = [_approved(f"c{i}", -3 if i == 0 else -1, peak=0.10, years_to_peak=1) for i in range(4)]
        model_fm_crowd = CompetitionModel(
            competitors=comps,
            first_mover_config=FirstMoverConfig(enabled=True, first_mover_bonus=0.25, late_entrant_penalty=0.10),
            crowding_model=CrowdingModel(enabled=True, crowding_threshold=3, share_decay_per_competitor=0.15),
        )
        model_crowd_only = CompetitionModel(
            competitors=comps,
            first_mover_config=FirstMoverConfig(enabled=False),
            crowding_model=CrowdingModel(enabled=True, crowding_threshold=3, share_decay_per_competitor=0.15),
        )
        # With first-mover adjustments, combined share changes, affecting available fraction
        fm_combined = model_fm_crowd.combined_competitor_share(5)
        base_combined = model_crowd_only.combined_competitor_share(5)
        assert fm_combined != base_combined  # first-mover shifts the combined share

    def test_first_mover_preserved_in_monte_carlo(self):
        """sample_launch_outcomes() carries first_mover_config to the sampled model."""
        import numpy as np
        rng = np.random.default_rng(0)
        comp = _approved("x", -2, peak=0.15)
        fm = FirstMoverConfig(enabled=True, first_mover_bonus=0.30, late_entrant_penalty=0.05)
        model = CompetitionModel(competitors=[comp], first_mover_config=fm)
        sampled = model.sample_launch_outcomes(rng)
        assert sampled.first_mover_config.enabled
        assert sampled.first_mover_config.first_mover_bonus == 0.30
        assert sampled.first_mover_config.late_entrant_penalty == 0.05


# ---------------------------------------------------------------------------
# Class Saturation Curves
# ---------------------------------------------------------------------------

class TestClassSaturationDefaults:
    def test_disabled_by_default(self):
        model = CompetitionModel()
        assert not model.saturation_profile.enabled

    def test_no_effect_when_disabled(self, four_approved_competitors):
        model_on = CompetitionModel(
            competitors=four_approved_competitors,
            saturation_profile=ClassSaturationProfile(enabled=False),
        )
        model_off = CompetitionModel(competitors=four_approved_competitors)
        for yr in range(1, 6):
            assert model_on.our_available_market_fraction(yr) == model_off.our_available_market_fraction(yr)


class TestClassSaturationCeiling:
    def test_ceiling_caps_available_fraction(self):
        """When combined share approaches the ceiling, available fraction is capped."""
        # Two competitors holding 0.60 combined share; ceiling = 0.70 → headroom = 0.10
        comps = [
            _approved("a", -2, peak=0.30, years_to_peak=1),
            _approved("b", -2, peak=0.30, years_to_peak=1),
        ]
        model = CompetitionModel(
            competitors=comps,
            saturation_profile=ClassSaturationProfile(enabled=True, saturation_ceiling=0.70),
        )
        # combined = 0.60 at year 1; headroom = 0.10; expansion = 1.0
        available = model.our_available_market_fraction(1)
        assert available <= 0.70 - 0.60 + 1e-9  # ≤ headroom

    def test_saturation_ceiling_invariant(self):
        """available ≤ ceiling - combined always holds."""
        comps = [_approved(f"c{i}", -2, peak=0.15, years_to_peak=1) for i in range(4)]
        model = CompetitionModel(
            competitors=comps,
            saturation_profile=ClassSaturationProfile(enabled=True, saturation_ceiling=0.65),
        )
        for yr in range(1, 8):
            combined = model.combined_competitor_share(yr)
            available = model.our_available_market_fraction(yr)
            ceiling = 0.65
            assert available <= max(0.0, ceiling - combined) + 1e-9, (
                f"year={yr}: available={available:.4f}, ceiling-combined={ceiling-combined:.4f}"
            )

    def test_floor_capped_at_headroom(self):
        """When headroom < 0.10, floor = headroom (not 0.10), preserving invariant."""
        # Combined share = 0.65, ceiling = 0.70 → headroom = 0.05 < 0.10
        comps = [
            _approved("a", -1, peak=0.35, years_to_peak=1),
            _approved("b", -1, peak=0.30, years_to_peak=1),
        ]
        model = CompetitionModel(
            competitors=comps,
            saturation_profile=ClassSaturationProfile(enabled=True, saturation_ceiling=0.70),
        )
        combined = model.combined_competitor_share(1)
        headroom = max(0.0, 0.70 - combined)
        available = model.our_available_market_fraction(1)
        assert available <= headroom + 1e-9

    def test_fully_saturated_market(self):
        """When combined share ≥ ceiling, available fraction = 0 (floor = min(0.10, 0) = 0)."""
        comps = [
            _approved("a", -1, peak=0.50, years_to_peak=1),
            _approved("b", -1, peak=0.40, years_to_peak=1),
        ]
        model = CompetitionModel(
            competitors=comps,
            saturation_profile=ClassSaturationProfile(enabled=True, saturation_ceiling=0.70),
        )
        available = model.our_available_market_fraction(1)
        assert available == 0.0


class TestMarketExpansionFactor:
    def test_expansion_increases_available_fraction(self):
        """market_expansion_factor > 1 increases available fraction relative to no expansion."""
        comps = [_approved("a", -1, peak=0.20, years_to_peak=1)]
        model_expand = CompetitionModel(
            competitors=comps,
            saturation_profile=ClassSaturationProfile(
                enabled=True, saturation_ceiling=0.80, market_expansion_factor=1.20
            ),
        )
        model_static = CompetitionModel(
            competitors=comps,
            saturation_profile=ClassSaturationProfile(
                enabled=True, saturation_ceiling=0.80, market_expansion_factor=1.0
            ),
        )
        assert model_expand.our_available_market_fraction(1) >= model_static.our_available_market_fraction(1)

    def test_expansion_bounded_by_one_minus_combined(self):
        """
        market_expansion_factor scales headroom beyond ceiling-combined, but
        available is always bounded by (1.0 - combined_share).

        The expansion factor represents market growth (new treatable patients),
        so it can push available above the static ceiling - combined headroom.
        The hard upper bound is 1.0 - combined (no drug can hold more than the
        remaining market not already held by competitors).
        """
        comps = [_approved("a", -1, peak=0.50, years_to_peak=1)]
        model = CompetitionModel(
            competitors=comps,
            saturation_profile=ClassSaturationProfile(
                enabled=True, saturation_ceiling=0.70, market_expansion_factor=2.0
            ),
        )
        combined = model.combined_competitor_share(1)
        available = model.our_available_market_fraction(1)
        assert available <= 1.0 - combined + 1e-9
        # And expansion gives us more than the static headroom (0.20) would allow
        assert available > max(0.0, 0.70 - combined) - 1e-9


class TestSaturationAndCrowdingCombined:
    def test_saturation_and_crowding_can_combine(self, four_approved_competitors):
        """Saturation and crowding are independent and can stack."""
        model_both = CompetitionModel(
            competitors=four_approved_competitors,
            crowding_model=CrowdingModel(enabled=True, crowding_threshold=3, share_decay_per_competitor=0.15),
            saturation_profile=ClassSaturationProfile(enabled=True, saturation_ceiling=0.80),
        )
        model_sat_only = CompetitionModel(
            competitors=four_approved_competitors,
            crowding_model=CrowdingModel(enabled=False),
            saturation_profile=ClassSaturationProfile(enabled=True, saturation_ceiling=0.80),
        )
        # Crowding can only reduce, so model_both ≤ model_sat_only
        assert model_both.our_available_market_fraction(1) <= model_sat_only.our_available_market_fraction(1)

    def test_combined_saturation_invariant_still_holds(self, four_approved_competitors):
        """Saturation ceiling invariant holds even when crowding is also active."""
        ceiling = 0.80
        model = CompetitionModel(
            competitors=four_approved_competitors,
            crowding_model=CrowdingModel(enabled=True, crowding_threshold=3, share_decay_per_competitor=0.15),
            saturation_profile=ClassSaturationProfile(enabled=True, saturation_ceiling=ceiling),
        )
        for yr in range(1, 6):
            combined = model.combined_competitor_share(yr)
            available = model.our_available_market_fraction(yr)
            assert available <= max(0.0, ceiling - combined) + 1e-9

    def test_saturation_preserved_in_monte_carlo(self):
        """sample_launch_outcomes() carries saturation_profile to the sampled model."""
        import numpy as np
        rng = np.random.default_rng(7)
        comp = _approved("x", -2, peak=0.15)
        profile = ClassSaturationProfile(enabled=True, saturation_ceiling=0.75, market_expansion_factor=1.15)
        model = CompetitionModel(competitors=[comp], saturation_profile=profile)
        sampled = model.sample_launch_outcomes(rng)
        assert sampled.saturation_profile.enabled
        assert sampled.saturation_profile.saturation_ceiling == 0.75
        assert sampled.saturation_profile.market_expansion_factor == 1.15


# ---------------------------------------------------------------------------
# Dynamic competitor share curves (S-curve vs linear ramp)
# ---------------------------------------------------------------------------

def _comp_s(name: str, peak: float = 0.30, years_to_peak: int = 4, use_s_curve: bool = True):
    return CompetitorLaunch(
        name=name,
        status="approved",
        launch_year_relative=0,   # concurrent launch — t = year
        peak_market_share=peak,
        years_to_peak=years_to_peak,
        approval_probability=1.0,
        use_s_curve=use_s_curve,
    )


class TestSCurveDefaults:
    def test_use_s_curve_false_by_default(self):
        comp = CompetitorLaunch(
            name="x", launch_year_relative=0, peak_market_share=0.20, years_to_peak=3
        )
        assert comp.use_s_curve is False

    def test_linear_unchanged_when_s_curve_disabled(self):
        """use_s_curve=False produces identical results to the pre-existing baseline."""
        comp_linear = _comp_s("linear", use_s_curve=False)
        comp_base = CompetitorLaunch(
            name="base", launch_year_relative=0, peak_market_share=0.30,
            years_to_peak=4, approval_probability=1.0
        )
        m_linear = CompetitionModel(competitors=[comp_linear])
        m_base = CompetitionModel(competitors=[comp_base])
        for yr in range(1, 8):
            assert abs(m_linear.combined_competitor_share(yr) - m_base.combined_competitor_share(yr)) < 1e-9


class TestSCurveRampShape:
    def test_s_curve_lower_than_linear_in_early_years(self):
        """S-curve: slower initial adoption → lower combined share in early years."""
        ytp = 6
        comp_s = _comp_s("s", years_to_peak=ytp, use_s_curve=True)
        comp_l = _comp_s("l", years_to_peak=ytp, use_s_curve=False)
        m_s = CompetitionModel(competitors=[comp_s])
        m_l = CompetitionModel(competitors=[comp_l])
        # At year 1 (early), S-curve share < linear share
        assert m_s.combined_competitor_share(1) < m_l.combined_competitor_share(1)

    def test_s_curve_higher_than_linear_in_late_years(self):
        """S-curve: faster mid-cycle adoption → higher combined share in later years before peak."""
        ytp = 6
        comp_s = _comp_s("s", years_to_peak=ytp, use_s_curve=True)
        comp_l = _comp_s("l", years_to_peak=ytp, use_s_curve=False)
        m_s = CompetitionModel(competitors=[comp_s])
        m_l = CompetitionModel(competitors=[comp_l])
        # At year 4–5, S-curve inflection has passed → S-curve share > linear
        assert m_s.combined_competitor_share(4) > m_l.combined_competitor_share(4)

    def test_s_curve_converges_at_years_to_peak(self):
        """At years_to_peak, S-curve ramp == 1.0 == linear ramp (both reach full peak)."""
        ytp = 5
        comp_s = _comp_s("s", years_to_peak=ytp, use_s_curve=True)
        comp_l = _comp_s("l", years_to_peak=ytp, use_s_curve=False)
        m_s = CompetitionModel(competitors=[comp_s])
        m_l = CompetitionModel(competitors=[comp_l])
        assert abs(m_s.combined_competitor_share(ytp) - m_l.combined_competitor_share(ytp)) < 1e-6

    def test_s_curve_ramp_never_exceeds_peak_share(self):
        """S-curve ramp is bounded by peak_market_share for all years."""
        ytp = 4
        peak = 0.30
        comp = _comp_s("x", peak=peak, years_to_peak=ytp, use_s_curve=True)
        model = CompetitionModel(competitors=[comp])
        for yr in range(1, 15):
            assert model.combined_competitor_share(yr) <= peak + 1e-9

    def test_s_curve_ramp_monotone(self):
        """S-curve share is non-decreasing until peak, then constant."""
        ytp = 5
        comp = _comp_s("x", years_to_peak=ytp, use_s_curve=True)
        model = CompetitionModel(competitors=[comp])
        shares = [model.combined_competitor_share(yr) for yr in range(1, 12)]
        for i in range(len(shares) - 1):
            assert shares[i] <= shares[i + 1] + 1e-9

    def test_negative_peak_share_unaffected_by_use_s_curve(self):
        """Market-expanding drugs (negative peak_market_share) are unaffected by S-curve flag."""
        comp_s = CompetitorLaunch(
            name="expander", status="approved", launch_year_relative=0,
            peak_market_share=-0.05, years_to_peak=3,
            approval_probability=1.0, use_s_curve=True,
        )
        comp_l = CompetitorLaunch(
            name="expander", status="approved", launch_year_relative=0,
            peak_market_share=-0.05, years_to_peak=3,
            approval_probability=1.0, use_s_curve=False,
        )
        m_s = CompetitionModel(competitors=[comp_s])
        m_l = CompetitionModel(competitors=[comp_l])
        # combined is floored at 0 for negative shares — both should be 0
        for yr in range(1, 5):
            assert m_s.combined_competitor_share(yr) == 0.0
            assert m_l.combined_competitor_share(yr) == 0.0


class TestSCurveWithCrowding:
    def test_s_curve_less_early_crowding_pressure(self):
        """
        With S-curve competitors: lower early combined share → our available fraction
        is >= the same model with linear ramps in early years.
        """
        ytp = 6
        comps_s = [_comp_s(f"c{i}", years_to_peak=ytp, use_s_curve=True) for i in range(4)]
        comps_l = [_comp_s(f"c{i}", years_to_peak=ytp, use_s_curve=False) for i in range(4)]
        crowding = CrowdingModel(enabled=True, crowding_threshold=3, share_decay_per_competitor=0.15)
        m_s = CompetitionModel(competitors=comps_s, crowding_model=crowding)
        m_l = CompetitionModel(competitors=comps_l, crowding_model=crowding)
        # Year 1: S-curve combined share is lower → our fraction is higher or equal
        assert m_s.our_available_market_fraction(1) >= m_l.our_available_market_fraction(1) - 1e-9

    def test_s_curve_converges_with_linear_at_steady_state(self):
        """After years_to_peak, both S-curve and linear reach same combined share → same fraction."""
        ytp = 4
        comps_s = [_comp_s(f"c{i}", years_to_peak=ytp, use_s_curve=True) for i in range(3)]
        comps_l = [_comp_s(f"c{i}", years_to_peak=ytp, use_s_curve=False) for i in range(3)]
        m_s = CompetitionModel(competitors=comps_s)
        m_l = CompetitionModel(competitors=comps_l)
        # Well past years_to_peak (year 10), both should be identical
        assert abs(m_s.our_available_market_fraction(10) - m_l.our_available_market_fraction(10)) < 1e-6
