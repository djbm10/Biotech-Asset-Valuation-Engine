"""Tests for sample_size_scorer.score_sample_size()."""
from __future__ import annotations

import pytest

from bve.entities.trial import TrialPhase
from bve.models.pos_model import SampleSizeAdequacy
from bve.models.sample_size_scorer import (
    SampleSizeParams,
    SampleSizeScoringResult,
    SampleSizeTrialDesign,
    score_sample_size,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _params(**kwargs) -> SampleSizeParams:
    defaults = dict(
        planned_sample_size=200,
        phase=TrialPhase.PHASE_2,
        indication_rarity="other",
    )
    defaults.update(kwargs)
    return SampleSizeParams(**defaults)


# ---------------------------------------------------------------------------
# Direct power input → correct tier
# ---------------------------------------------------------------------------

class TestAnalystProvidedPower:
    def test_well_powered_at_90_pct(self):
        p = _params(statistical_power=0.90)
        r = score_sample_size(p)
        assert r.tier == SampleSizeAdequacy.WELL_POWERED
        assert r.power_source == "analyst_provided"
        assert r.computed_power == pytest.approx(0.90)

    def test_adequate_at_85_pct(self):
        p = _params(statistical_power=0.85)
        r = score_sample_size(p)
        assert r.tier == SampleSizeAdequacy.ADEQUATE
        assert r.power_source == "analyst_provided"

    def test_borderline_at_75_pct(self):
        p = _params(statistical_power=0.75)
        r = score_sample_size(p)
        assert r.tier == SampleSizeAdequacy.BORDERLINE

    def test_underpowered_at_60_pct(self):
        p = _params(statistical_power=0.60)
        r = score_sample_size(p)
        assert r.tier == SampleSizeAdequacy.UNDERPOWERED

    def test_boundary_exactly_80_pct_is_adequate(self):
        p = _params(statistical_power=0.80)
        r = score_sample_size(p)
        assert r.tier == SampleSizeAdequacy.ADEQUATE

    def test_boundary_exactly_90_pct_is_well_powered(self):
        p = _params(statistical_power=0.90)
        r = score_sample_size(p)
        assert r.tier == SampleSizeAdequacy.WELL_POWERED


# ---------------------------------------------------------------------------
# Computed power — continuous endpoint
# ---------------------------------------------------------------------------

class TestComputedPowerContinuous:
    def test_large_cohens_d_yields_high_power(self):
        # Cohen's d = 1.0, n=200 → should be well_powered
        p = _params(
            planned_sample_size=200,
            expected_effect_size=1.0,   # Cohen's d (no variability given)
            phase=TrialPhase.PHASE_3,
        )
        r = score_sample_size(p)
        assert r.power_source == "computed_continuous"
        assert r.computed_power is not None
        assert r.computed_power > 0.80

    def test_raw_effect_and_variability_standardized(self):
        # raw=10, SD=20 → Cohen's d=0.5; raw=10, SD=10 → Cohen's d=1.0
        p_small_d = _params(expected_effect_size=10.0, endpoint_variability=20.0, planned_sample_size=200)
        p_large_d = _params(expected_effect_size=10.0, endpoint_variability=10.0, planned_sample_size=200)
        r_small = score_sample_size(p_small_d)
        r_large = score_sample_size(p_large_d)
        assert r_large.computed_power > r_small.computed_power

    def test_larger_n_yields_higher_power(self):
        kwargs = dict(expected_effect_size=0.4, phase=TrialPhase.PHASE_2)
        r_small = score_sample_size(_params(planned_sample_size=100, **kwargs))
        r_large = score_sample_size(_params(planned_sample_size=400, **kwargs))
        assert r_large.computed_power > r_small.computed_power


# ---------------------------------------------------------------------------
# Computed power — binary endpoint
# ---------------------------------------------------------------------------

class TestComputedPowerBinary:
    def test_binary_path_used_when_control_rate_given(self):
        p = _params(
            planned_sample_size=300,
            expected_effect_size=0.15,            # absolute risk diff
            control_rate_or_placebo_response=0.30,
            phase=TrialPhase.PHASE_3,
        )
        r = score_sample_size(p)
        assert r.power_source == "computed_binary"
        assert r.computed_power is not None

    def test_larger_effect_size_gives_higher_power(self):
        kwargs = dict(
            planned_sample_size=300,
            control_rate_or_placebo_response=0.30,
            phase=TrialPhase.PHASE_3,
        )
        r_small = score_sample_size(_params(expected_effect_size=0.05, **kwargs))
        r_large = score_sample_size(_params(expected_effect_size=0.20, **kwargs))
        assert r_large.computed_power > r_small.computed_power


# ---------------------------------------------------------------------------
# UNVERIFIABLE when no power parameters
# ---------------------------------------------------------------------------

class TestUnverifiable:
    def test_no_power_params_returns_unverifiable(self):
        p = _params(planned_sample_size=100)  # no effect size, no power
        r = score_sample_size(p)
        assert r.tier == SampleSizeAdequacy.UNVERIFIABLE
        assert r.power_source == "unverifiable"
        assert r.computed_power is None

    def test_effect_size_zero_returns_unverifiable(self):
        p = _params(planned_sample_size=100, expected_effect_size=0.0)
        r = score_sample_size(p)
        assert r.tier == SampleSizeAdequacy.UNVERIFIABLE

    def test_only_variability_no_effect_returns_unverifiable(self):
        p = _params(planned_sample_size=100, endpoint_variability=10.0)
        r = score_sample_size(p)
        assert r.tier == SampleSizeAdequacy.UNVERIFIABLE


# ---------------------------------------------------------------------------
# Design tier caps
# ---------------------------------------------------------------------------

class TestDesignTierCap:
    def test_exploratory_always_capped_at_exploratory(self):
        p = _params(
            planned_sample_size=500,
            statistical_power=0.95,
            trial_design=SampleSizeTrialDesign.EXPLORATORY,
        )
        r = score_sample_size(p)
        assert r.tier == SampleSizeAdequacy.EXPLORATORY
        assert r.design_cap_applied == SampleSizeAdequacy.EXPLORATORY

    def test_registry_always_capped_at_exploratory(self):
        p = _params(
            planned_sample_size=500,
            statistical_power=0.95,
            trial_design=SampleSizeTrialDesign.REGISTRY,
        )
        r = score_sample_size(p)
        assert r.tier == SampleSizeAdequacy.EXPLORATORY

    def test_single_arm_capped_at_borderline(self):
        p = _params(
            planned_sample_size=500,
            statistical_power=0.95,
            trial_design=SampleSizeTrialDesign.SINGLE_ARM,
        )
        r = score_sample_size(p)
        assert r.tier == SampleSizeAdequacy.BORDERLINE
        assert r.design_cap_applied == SampleSizeAdequacy.BORDERLINE

    def test_basket_capped_at_borderline(self):
        p = _params(
            planned_sample_size=500,
            statistical_power=0.95,
            trial_design=SampleSizeTrialDesign.BASKET,
        )
        r = score_sample_size(p)
        assert r.tier == SampleSizeAdequacy.BORDERLINE

    def test_rct_no_cap_applied(self):
        p = _params(
            planned_sample_size=500,
            statistical_power=0.95,
            trial_design=SampleSizeTrialDesign.RCT,
        )
        r = score_sample_size(p)
        assert r.tier == SampleSizeAdequacy.WELL_POWERED
        assert r.design_cap_applied is None

    def test_cap_does_not_upgrade_already_worse_tier(self):
        # SINGLE_ARM cap = BORDERLINE; but power = 0.60 → UNDERPOWERED
        # cap only applies when tier > cap, so UNDERPOWERED stays UNDERPOWERED
        p = _params(
            planned_sample_size=10,
            statistical_power=0.60,
            trial_design=SampleSizeTrialDesign.SINGLE_ARM,
        )
        r = score_sample_size(p)
        assert r.tier == SampleSizeAdequacy.UNDERPOWERED


# ---------------------------------------------------------------------------
# TA minimum-N threshold downgrade
# ---------------------------------------------------------------------------

class TestTAMinNDowngrade:
    def test_cardiovascular_phase2_requires_300(self):
        # cardiovascular Phase 2 min = 300; n=100 well-powered → downgraded
        p = _params(
            planned_sample_size=100,
            statistical_power=0.90,
            phase=TrialPhase.PHASE_2,
            indication_rarity="cardiovascular",
        )
        r = score_sample_size(p)
        assert r.ta_downgraded is True
        # WELL_POWERED downgraded to ADEQUATE
        assert r.tier == SampleSizeAdequacy.ADEQUATE

    def test_rare_disease_small_n_not_downgraded(self):
        # rare_disease Phase 2 min = 15; n=20 → not downgraded
        p = _params(
            planned_sample_size=20,
            statistical_power=0.90,
            phase=TrialPhase.PHASE_2,
            indication_rarity="rare_disease",
        )
        r = score_sample_size(p)
        assert r.ta_downgraded is False
        assert r.tier == SampleSizeAdequacy.WELL_POWERED

    def test_ta_downgrade_does_not_apply_to_borderline(self):
        # downgrade only applies when tier is WELL_POWERED or ADEQUATE
        p = _params(
            planned_sample_size=100,
            statistical_power=0.75,
            phase=TrialPhase.PHASE_2,
            indication_rarity="cardiovascular",
        )
        r = score_sample_size(p)
        assert r.ta_downgraded is False
        assert r.tier == SampleSizeAdequacy.BORDERLINE

    def test_oncology_phase3_min_120(self):
        # oncology Phase 3 min = 120; n=80 adequate → downgraded
        p = _params(
            planned_sample_size=80,
            statistical_power=0.85,
            phase=TrialPhase.PHASE_3,
            indication_rarity="oncology",
        )
        r = score_sample_size(p)
        assert r.ta_downgraded is True
        assert r.ta_min_n == 120


# ---------------------------------------------------------------------------
# CNS/Psychiatry high-placebo penalty
# ---------------------------------------------------------------------------

class TestCNSPlaceboNoisePenalty:
    def test_cns_high_placebo_downgrades_adequate(self):
        p = _params(
            planned_sample_size=200,
            statistical_power=0.85,
            phase=TrialPhase.PHASE_2,
            indication_rarity="cns",
            control_rate_or_placebo_response=0.40,  # >35% → penalty
        )
        r = score_sample_size(p)
        assert r.tier == SampleSizeAdequacy.BORDERLINE
        assert "CNS" in r.rationale or "placebo" in r.rationale

    def test_psychiatry_high_placebo_downgrades_adequate(self):
        p = _params(
            planned_sample_size=200,
            statistical_power=0.85,
            phase=TrialPhase.PHASE_2,
            indication_rarity="psychiatry",
            control_rate_or_placebo_response=0.50,
        )
        r = score_sample_size(p)
        assert r.tier == SampleSizeAdequacy.BORDERLINE

    def test_cns_low_placebo_not_penalized(self):
        p = _params(
            planned_sample_size=200,
            statistical_power=0.85,
            phase=TrialPhase.PHASE_2,
            indication_rarity="cns",
            control_rate_or_placebo_response=0.20,  # ≤35% → no penalty
        )
        r = score_sample_size(p)
        assert r.tier == SampleSizeAdequacy.ADEQUATE

    def test_non_cns_high_placebo_not_penalized(self):
        p = _params(
            planned_sample_size=200,
            statistical_power=0.85,
            phase=TrialPhase.PHASE_2,
            indication_rarity="oncology",
            control_rate_or_placebo_response=0.50,
        )
        r = score_sample_size(p)
        assert r.tier == SampleSizeAdequacy.ADEQUATE


# ---------------------------------------------------------------------------
# Effective N computation
# ---------------------------------------------------------------------------

class TestEffectiveN:
    def test_dropout_reduces_effective_n(self):
        p_no_dropout = _params(planned_sample_size=200, dropout_rate=0.0)
        p_dropout = _params(planned_sample_size=200, dropout_rate=0.20)
        r_no = score_sample_size(p_no_dropout)
        r_do = score_sample_size(p_dropout)
        assert r_no.effective_n == pytest.approx(200.0)
        assert r_do.effective_n == pytest.approx(160.0)

    def test_crossover_boosts_effective_n(self):
        p_rct = _params(planned_sample_size=100, trial_design=SampleSizeTrialDesign.RCT)
        p_cross = _params(planned_sample_size=100, trial_design=SampleSizeTrialDesign.CROSSOVER)
        r_rct = score_sample_size(p_rct)
        r_cross = score_sample_size(p_cross)
        assert r_cross.effective_n > r_rct.effective_n
        assert r_cross.effective_n == pytest.approx(170.0)

    def test_adaptive_mild_boost(self):
        p = _params(planned_sample_size=100, trial_design=SampleSizeTrialDesign.ADAPTIVE)
        r = score_sample_size(p)
        assert r.effective_n == pytest.approx(110.0)


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------

class TestResultStructure:
    def test_returns_scoring_result_instance(self):
        p = _params(statistical_power=0.85)
        r = score_sample_size(p)
        assert isinstance(r, SampleSizeScoringResult)

    def test_rationale_is_non_empty_string(self):
        p = _params(statistical_power=0.85)
        r = score_sample_size(p)
        assert isinstance(r.rationale, str)
        assert len(r.rationale) > 0

    def test_ta_min_n_populated_for_known_ta(self):
        p = _params(
            planned_sample_size=200,
            statistical_power=0.85,
            phase=TrialPhase.PHASE_2,
            indication_rarity="cardiovascular",
        )
        r = score_sample_size(p)
        assert r.ta_min_n == 300

    def test_ta_min_n_populated_for_unknown_ta_falls_back(self):
        p = _params(
            planned_sample_size=200,
            statistical_power=0.85,
            phase=TrialPhase.PHASE_2,
            indication_rarity="unknown_area",
        )
        r = score_sample_size(p)
        # falls back to "other" → Phase 2 = 60
        assert r.ta_min_n == 60
