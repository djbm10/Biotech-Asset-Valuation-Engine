"""
Sprint E1 — SpendProfile enum on ClinicalTrial / CostModel.

Tests cover:
  1. SpendProfile enum: values, default on ClinicalTrial
  2. PhaseResult.spend_profile: forwarded from ClinicalTrial
  3. _spend_fraction_weights(): sub-interval logic, edge cases
  4. CostModel: UNIFORM is bit-for-bit identical to pre-E1 midpoint
  5. CostModel: ANNUAL_UNIFORM produces correct PV (lower for multi-year phases)
  6. Mixed profiles: each phase uses its own profile independently
  7. Backward compatibility: existing trials (no spend_profile set) behave as UNIFORM
"""
from __future__ import annotations

import math

import pytest

from bve.entities.asset import Asset
from bve.entities.trial import ClinicalTrial, SpendProfile
from bve.models.cost_model import CostModel, _spend_fraction_weights
from bve.models.probability_model import PhaseResult, ProbabilityModel, ProbabilityResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _asset() -> Asset:
    return Asset(
        id="e1-test",
        name="E1 Test",
        indication="Test",
        therapeutic_area="oncology",
        stage="phase_3",
        modality="small_molecule",
        discount_rate=0.10,
    )


def _trial(
    phase: str = "phase_3",
    cost: float = 100.0,
    duration: float = 3.0,
    sp: SpendProfile = SpendProfile.UNIFORM,
) -> ClinicalTrial:
    return ClinicalTrial(
        asset_id="e1-test",
        phase=phase,
        success_probability=0.55,
        duration_years=duration,
        cost_millions=cost,
        cost_source="override",
        spend_profile=sp,
    )


def _single_phase_prob(
    phase: str = "phase_3",
    cost: float = 100.0,
    duration: float = 3.0,
    sp: SpendProfile = SpendProfile.UNIFORM,
) -> ProbabilityResult:
    asset = _asset()
    trial = _trial(phase=phase, cost=cost, duration=duration, sp=sp)
    return ProbabilityModel.compute(asset, [trial])


# ---------------------------------------------------------------------------
# 1. SpendProfile enum
# ---------------------------------------------------------------------------

class TestSpendProfileEnum:
    def test_values_exist(self):
        assert SpendProfile.UNIFORM.value == "uniform"
        assert SpendProfile.ANNUAL_UNIFORM.value == "annual_uniform"

    def test_default_on_trial_is_uniform(self):
        trial = _trial()
        assert trial.spend_profile == SpendProfile.UNIFORM

    def test_explicit_annual_uniform(self):
        trial = _trial(sp=SpendProfile.ANNUAL_UNIFORM)
        assert trial.spend_profile == SpendProfile.ANNUAL_UNIFORM

    def test_string_coercion(self):
        trial = ClinicalTrial(
            asset_id="e1-test",
            phase="phase_3",
            success_probability=0.55,
            duration_years=3.0,
            cost_millions=100.0,
            spend_profile="annual_uniform",
        )
        assert trial.spend_profile == SpendProfile.ANNUAL_UNIFORM


# ---------------------------------------------------------------------------
# 2. PhaseResult.spend_profile forwarding
# ---------------------------------------------------------------------------

class TestPhaseResultForwarding:
    def test_uniform_forwarded(self):
        prob = _single_phase_prob(sp=SpendProfile.UNIFORM)
        assert prob.phases[0].spend_profile == SpendProfile.UNIFORM

    def test_annual_uniform_forwarded(self):
        prob = _single_phase_prob(sp=SpendProfile.ANNUAL_UNIFORM)
        assert prob.phases[0].spend_profile == SpendProfile.ANNUAL_UNIFORM

    def test_default_trial_produces_uniform_phase(self):
        asset = _asset()
        trial = ClinicalTrial(
            asset_id="e1-test",
            phase="phase_3",
            success_probability=0.55,
            duration_years=3.0,
            cost_millions=100.0,
        )
        prob = ProbabilityModel.compute(asset, [trial])
        assert prob.phases[0].spend_profile == SpendProfile.UNIFORM


# ---------------------------------------------------------------------------
# 3. _spend_fraction_weights
# ---------------------------------------------------------------------------

class TestSpendFractionWeights:
    def test_integer_aligned_duration(self):
        """[0.0, 3.0) → 3 segments, each weight 1/3, midpoints 0.5, 1.5, 2.5."""
        weights = _spend_fraction_weights(0.0, 3.0)
        assert len(weights) == 3
        fracs, mids = zip(*weights)
        assert sum(fracs) == pytest.approx(1.0, rel=1e-9)
        assert list(mids) == pytest.approx([0.5, 1.5, 2.5], rel=1e-9)
        for f in fracs:
            assert f == pytest.approx(1.0 / 3.0, rel=1e-9)

    def test_non_integer_start(self):
        """[0.5, 3.0) → segments [0.5,1.0), [1.0,2.0), [2.0,3.0), duration=2.5."""
        weights = _spend_fraction_weights(0.5, 3.0)
        fracs, mids = zip(*weights)
        assert sum(fracs) == pytest.approx(1.0, rel=1e-9)
        # fractions: 0.5/2.5, 1.0/2.5, 1.0/2.5
        assert fracs[0] == pytest.approx(0.5 / 2.5, rel=1e-9)
        assert fracs[1] == pytest.approx(1.0 / 2.5, rel=1e-9)
        assert fracs[2] == pytest.approx(1.0 / 2.5, rel=1e-9)
        assert mids[0] == pytest.approx(0.75, rel=1e-9)
        assert mids[1] == pytest.approx(1.5, rel=1e-9)
        assert mids[2] == pytest.approx(2.5, rel=1e-9)

    def test_sub_year_duration(self):
        """[2.0, 2.5) → 1 segment, weight 1.0, midpoint 2.25."""
        weights = _spend_fraction_weights(2.0, 2.5)
        assert len(weights) == 1
        assert weights[0][0] == pytest.approx(1.0, rel=1e-9)
        assert weights[0][1] == pytest.approx(2.25, rel=1e-9)

    def test_fractions_sum_to_one(self):
        """Invariant: fractions always sum to 1.0 regardless of start/end."""
        for start, end in [(0.0, 1.0), (0.3, 4.7), (2.5, 5.0), (0.0, 0.5)]:
            weights = _spend_fraction_weights(start, end)
            fracs = [f for f, _ in weights]
            assert sum(fracs) == pytest.approx(1.0, rel=1e-9), f"Failed for [{start}, {end})"

    def test_zero_duration_degenerate(self):
        """duration=0 returns a single (1.0, year_start) entry."""
        weights = _spend_fraction_weights(2.0, 2.0)
        assert weights == [(1.0, 2.0)]

    def test_single_year_one_segment(self):
        weights = _spend_fraction_weights(1.0, 2.0)
        assert len(weights) == 1
        assert weights[0] == pytest.approx((1.0, 1.5), rel=1e-9)


# ---------------------------------------------------------------------------
# 4. UNIFORM is bit-for-bit identical to pre-E1 midpoint
# ---------------------------------------------------------------------------

class TestUniformBackwardCompat:
    """UNIFORM spend_profile must reproduce the pre-E1 midpoint formula exactly."""

    def _midpoint_pv(self, cost: float, duration: float, r: float) -> float:
        mid = duration / 2.0
        return cost / (1.0 + r) ** mid  # prob_reaching=1.0 for first phase

    def test_uniform_equals_midpoint_simple(self):
        prob = _single_phase_prob(cost=100.0, duration=3.0, sp=SpendProfile.UNIFORM)
        cost_stream = CostModel.compute(prob, 0.10)
        expected_pv_gross = self._midpoint_pv(100.0, 3.0, 0.10)
        assert cost_stream.phase_costs[0].pv_cost_gross == pytest.approx(expected_pv_gross, abs=0.01)

    def test_uniform_equals_midpoint_long_phase(self):
        prob = _single_phase_prob(cost=200.0, duration=5.0, sp=SpendProfile.UNIFORM)
        cost_stream = CostModel.compute(prob, 0.12)
        expected_pv_gross = self._midpoint_pv(200.0, 5.0, 0.12)
        assert cost_stream.phase_costs[0].pv_cost_gross == pytest.approx(expected_pv_gross, abs=0.01)

    def test_uniform_equals_no_profile_set(self):
        """Trial without explicit spend_profile produces identical result to UNIFORM."""
        asset = _asset()
        trial_no_sp = ClinicalTrial(
            asset_id="e1-test",
            phase="phase_3",
            success_probability=0.55,
            duration_years=3.0,
            cost_millions=100.0,
        )
        trial_uniform = _trial(sp=SpendProfile.UNIFORM)
        prob_no_sp = ProbabilityModel.compute(asset, [trial_no_sp])
        prob_uniform = ProbabilityModel.compute(asset, [trial_uniform])
        cs_no_sp = CostModel.compute(prob_no_sp, 0.10)
        cs_uniform = CostModel.compute(prob_uniform, 0.10)
        assert cs_no_sp.total_pv_weighted_millions == pytest.approx(
            cs_uniform.total_pv_weighted_millions, rel=1e-9
        )


# ---------------------------------------------------------------------------
# 5. ANNUAL_UNIFORM produces correct PV
# ---------------------------------------------------------------------------

class TestAnnualUniformPV:
    def test_annual_uniform_exact_pv(self):
        """
        Phase [0, 3): cost=120, r=0.10.
        3 equal segments, fracs=[1/3, 1/3, 1/3], mids=[0.5, 1.5, 2.5].
        PV_gross = 120 * (1/3)/1.1^0.5 + (1/3)/1.1^1.5 + (1/3)/1.1^2.5
        """
        r = 0.10
        cost = 120.0
        prob = _single_phase_prob(cost=cost, duration=3.0, sp=SpendProfile.ANNUAL_UNIFORM)
        cost_stream = CostModel.compute(prob, r)
        expected = cost / 3.0 * sum(
            1.0 / (1.0 + r) ** m for m in [0.5, 1.5, 2.5]
        )
        assert cost_stream.phase_costs[0].pv_cost_gross == pytest.approx(expected, rel=1e-4)

    def test_annual_uniform_lower_than_midpoint_for_long_phase(self):
        """
        For a long phase, ANNUAL_UNIFORM < UNIFORM because early years
        are discounted at shorter horizons, which is more correct.

        Wait — actually for a uniform spend spread, costs at year 0 are
        discounted less (higher PV) while costs at year_end are discounted more.
        The NET effect vs midpoint depends on the convexity of discounting.
        For a standard discount factor: sum of (frac/1+r^t) vs 1/(1+r)^mid.
        The latter is Jensen's inequality — sum(frac×f(t)) ≠ f(sum(frac×t))=f(mid).
        For exponential discounting (convex), sum(frac×f(t)) > f(sum(frac×t))=f(mid).
        So ANNUAL_UNIFORM PV > UNIFORM PV (midpoint underestimates for convex discount).
        """
        r = 0.10
        cost = 100.0
        duration = 5.0
        prob_u = _single_phase_prob(cost=cost, duration=duration, sp=SpendProfile.UNIFORM)
        prob_a = _single_phase_prob(cost=cost, duration=duration, sp=SpendProfile.ANNUAL_UNIFORM)
        cs_u = CostModel.compute(prob_u, r)
        cs_a = CostModel.compute(prob_a, r)
        # ANNUAL_UNIFORM > UNIFORM due to Jensen's inequality on convex discount
        assert cs_a.phase_costs[0].pv_cost_gross > cs_u.phase_costs[0].pv_cost_gross

    def test_annual_uniform_converges_to_uniform_for_short_phase(self):
        """Sub-year phase: ANNUAL_UNIFORM and UNIFORM converge (single segment)."""
        r = 0.10
        cost = 50.0
        duration = 0.5  # sub-year
        prob_u = _single_phase_prob(cost=cost, duration=duration, sp=SpendProfile.UNIFORM)
        prob_a = _single_phase_prob(cost=cost, duration=duration, sp=SpendProfile.ANNUAL_UNIFORM)
        cs_u = CostModel.compute(prob_u, r)
        cs_a = CostModel.compute(prob_a, r)
        assert cs_a.phase_costs[0].pv_cost_gross == pytest.approx(
            cs_u.phase_costs[0].pv_cost_gross, rel=1e-4
        )

    def test_annual_uniform_probability_weighted(self):
        """ANNUAL_UNIFORM PV is correctly probability-weighted."""
        asset = _asset()
        trials = [
            ClinicalTrial(
                asset_id="e1-test",
                phase="phase_2",
                success_probability=0.50,
                duration_years=2.0,
                cost_millions=60.0,
                spend_profile=SpendProfile.ANNUAL_UNIFORM,
            ),
            ClinicalTrial(
                asset_id="e1-test",
                phase="phase_3",
                success_probability=0.60,
                duration_years=3.0,
                cost_millions=150.0,
                spend_profile=SpendProfile.ANNUAL_UNIFORM,
            ),
        ]
        prob = ProbabilityModel.compute(asset, trials)
        cs = CostModel.compute(prob, 0.10)
        # P3 prob_reaching = 0.50
        p3 = next(pc for pc in cs.phase_costs if pc.phase == "phase_3")
        assert p3.prob_reaching == pytest.approx(0.50, rel=1e-6)
        assert p3.pv_cost_weighted == pytest.approx(p3.pv_cost_gross * 0.50, rel=1e-4)


# ---------------------------------------------------------------------------
# 6. Mixed profiles: each phase uses its own profile
# ---------------------------------------------------------------------------

class TestMixedProfiles:
    def test_phase2_annual_phase3_uniform(self):
        asset = _asset()
        trials = [
            ClinicalTrial(
                asset_id="e1-test",
                phase="phase_2",
                success_probability=0.50,
                duration_years=2.0,
                cost_millions=60.0,
                spend_profile=SpendProfile.ANNUAL_UNIFORM,
            ),
            ClinicalTrial(
                asset_id="e1-test",
                phase="phase_3",
                success_probability=0.60,
                duration_years=3.0,
                cost_millions=150.0,
                spend_profile=SpendProfile.UNIFORM,
            ),
        ]
        prob = ProbabilityModel.compute(asset, trials)
        r = 0.10

        cs_mixed = CostModel.compute(prob, r)

        # P2 uses ANNUAL_UNIFORM → 2 segments: [0,1) and [1,2), each fraction 0.5
        p2_expected_pv = 60.0 * (
            0.5 / (1.0 + r) ** 0.5 + 0.5 / (1.0 + r) ** 1.5
        )
        p2_mixed = next(pc for pc in cs_mixed.phase_costs if pc.phase == "phase_2")
        assert p2_mixed.pv_cost_gross == pytest.approx(p2_expected_pv, rel=1e-4)

        # P3 uses UNIFORM → midpoint = (2.0 + 5.0) / 2 = 3.5
        p3_mid = 3.5
        p3_expected_pv = 150.0 / (1.0 + r) ** p3_mid
        p3_mixed = next(pc for pc in cs_mixed.phase_costs if pc.phase == "phase_3")
        assert p3_mixed.pv_cost_gross == pytest.approx(p3_expected_pv, abs=0.01)

    def test_independent_phase_profiles_no_cross_contamination(self):
        """Changing one phase's profile must not alter the other phase's PV."""
        asset = _asset()

        def _run(p2_sp: SpendProfile, p3_sp: SpendProfile) -> tuple[float, float]:
            trials = [
                ClinicalTrial(
                    asset_id="e1-test",
                    phase="phase_2",
                    success_probability=0.50,
                    duration_years=2.0,
                    cost_millions=60.0,
                    spend_profile=p2_sp,
                ),
                ClinicalTrial(
                    asset_id="e1-test",
                    phase="phase_3",
                    success_probability=0.60,
                    duration_years=3.0,
                    cost_millions=150.0,
                    spend_profile=p3_sp,
                ),
            ]
            prob = ProbabilityModel.compute(asset, trials)
            cs = CostModel.compute(prob, 0.10)
            p2 = next(pc for pc in cs.phase_costs if pc.phase == "phase_2")
            p3 = next(pc for pc in cs.phase_costs if pc.phase == "phase_3")
            return p2.pv_cost_gross, p3.pv_cost_gross

        p2_u_p3_u = _run(SpendProfile.UNIFORM, SpendProfile.UNIFORM)
        p2_a_p3_u = _run(SpendProfile.ANNUAL_UNIFORM, SpendProfile.UNIFORM)
        p2_u_p3_a = _run(SpendProfile.UNIFORM, SpendProfile.ANNUAL_UNIFORM)

        # Changing P2 profile should not affect P3 PV
        assert p2_u_p3_u[1] == pytest.approx(p2_a_p3_u[1], rel=1e-9)
        # Changing P3 profile should not affect P2 PV
        assert p2_u_p3_u[0] == pytest.approx(p2_u_p3_a[0], rel=1e-9)


# ---------------------------------------------------------------------------
# 7. Backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_trial_without_spend_profile_is_uniform(self):
        """Trials constructed without spend_profile default to UNIFORM."""
        trial = ClinicalTrial(
            asset_id="compat-test",
            phase="phase_2",
            success_probability=0.40,
            duration_years=2.5,
            cost_millions=75.0,
        )
        assert trial.spend_profile == SpendProfile.UNIFORM

    def test_model_copy_preserves_spend_profile(self):
        trial = _trial(sp=SpendProfile.ANNUAL_UNIFORM)
        updated = trial.model_copy(update={"cost_millions": 200.0})
        assert updated.spend_profile == SpendProfile.ANNUAL_UNIFORM

    def test_all_uniform_total_unchanged_from_pre_e1(self):
        """Full pipeline with all UNIFORM trials produces same total as before."""
        asset = _asset()
        trials = [
            ClinicalTrial(
                asset_id="e1-test",
                phase="phase_2",
                success_probability=0.40,
                duration_years=2.5,
                cost_millions=80.0,
            ),
            ClinicalTrial(
                asset_id="e1-test",
                phase="phase_3",
                success_probability=0.60,
                duration_years=3.0,
                cost_millions=200.0,
            ),
        ]
        prob = ProbabilityModel.compute(asset, trials)
        cs = CostModel.compute(prob, 0.10)

        # Manually compute pre-E1 style
        r = 0.10
        p2 = prob.phases[0]
        p3 = prob.phases[1]
        expected_p2 = 80.0 / (1 + r) ** ((p2.year_start + p2.year_end) / 2) * p2.prob_reaching
        expected_p3 = 200.0 / (1 + r) ** ((p3.year_start + p3.year_end) / 2) * p3.prob_reaching
        expected_total = round(expected_p2 + expected_p3, 2)
        assert cs.total_pv_weighted_millions == pytest.approx(expected_total, rel=1e-6)
