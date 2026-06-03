"""
Block 28 — BTD Context-Conditional Adjustment
TDD tests written BEFORE implementation.

Tests for:
  1. BreakthroughDesignationType enum (7 values)
  2. _BTD_LOGODDS_BY_TYPE table
  3. POSAdjusters new field: breakthrough_designation (Optional, default None)
  4. BTD log-odds applied correctly per type
  5. btd_timeline_acceleration_flag in POSComputeResult
  6. btd_overlap_warning in POSComputeResult
  7. Backward compat: has_breakthrough_designation=True → GRANTED_STANDARD (+0.05)
"""
from __future__ import annotations

import warnings

import pytest

from bve.entities.trial import BreakthroughDesignationType
from bve.models.pos_model import (
    POSAdjusters,
    POSComputeResult,
    compute_pos,
    compute_pos_detailed,
)
from bve.entities.trial import TrialPhase
from bve.models.pos_model import (
    ClinicalEffectMagnitude,
    PriorPhaseDataStrength,
    TherapeuticArea,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _base_adjusters(**kwargs) -> POSAdjusters:
    return POSAdjusters(**kwargs)


# ---------------------------------------------------------------------------
# Block 28-A: BreakthroughDesignationType enum
# ---------------------------------------------------------------------------

class TestBreakthroughDesignationTypeEnum:

    def test_seven_values_present(self):
        expected = {
            "none", "fast_track_only", "granted_standard",
            "granted_rare_heme", "granted_solid_tumor",
            "granted_early_phase", "breakthrough_revoked",
        }
        actual = {v.value for v in BreakthroughDesignationType}
        assert expected.issubset(actual)

    def test_none_value(self):
        assert BreakthroughDesignationType.NONE.value == "none"

    def test_granted_standard_value(self):
        assert BreakthroughDesignationType.GRANTED_STANDARD.value == "granted_standard"

    def test_granted_rare_heme_value(self):
        assert BreakthroughDesignationType.GRANTED_RARE_HEME.value == "granted_rare_heme"

    def test_revoked_value(self):
        assert BreakthroughDesignationType.BREAKTHROUGH_REVOKED.value == "breakthrough_revoked"


# ---------------------------------------------------------------------------
# Block 28-B: POSAdjusters new field
# ---------------------------------------------------------------------------

class TestPOSAdjustersBreakthroughField:

    def test_breakthrough_designation_field_exists(self):
        adj = _base_adjusters()
        assert hasattr(adj, "breakthrough_designation")

    def test_breakthrough_designation_default_none(self):
        adj = _base_adjusters()
        assert adj.breakthrough_designation is None

    def test_breakthrough_designation_accepts_granted_standard(self):
        adj = _base_adjusters(
            breakthrough_designation=BreakthroughDesignationType.GRANTED_STANDARD
        )
        assert adj.breakthrough_designation == BreakthroughDesignationType.GRANTED_STANDARD

    def test_breakthrough_designation_accepts_rare_heme(self):
        adj = _base_adjusters(
            breakthrough_designation=BreakthroughDesignationType.GRANTED_RARE_HEME
        )
        assert adj.breakthrough_designation == BreakthroughDesignationType.GRANTED_RARE_HEME

    def test_breakthrough_designation_accepts_revoked(self):
        adj = _base_adjusters(
            breakthrough_designation=BreakthroughDesignationType.BREAKTHROUGH_REVOKED
        )
        assert adj.breakthrough_designation == BreakthroughDesignationType.BREAKTHROUGH_REVOKED


# ---------------------------------------------------------------------------
# Block 28-C: BTD log-odds values
# ---------------------------------------------------------------------------

class TestBTDLogodds:

    def _delta_pos(self, btd_type) -> float:
        """Compute POS delta introduced by setting a BTD type vs NONE."""
        base = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            _base_adjusters(),
        )
        with_btd = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            _base_adjusters(breakthrough_designation=btd_type),
        )
        return with_btd - base

    def test_none_no_change(self):
        delta = self._delta_pos(BreakthroughDesignationType.NONE)
        assert abs(delta) < 1e-9

    def test_granted_standard_positive(self):
        delta = self._delta_pos(BreakthroughDesignationType.GRANTED_STANDARD)
        assert delta > 0

    def test_granted_rare_heme_higher_than_standard(self):
        """GRANTED_RARE_HEME +0.10 > GRANTED_STANDARD +0.05."""
        delta_std = self._delta_pos(BreakthroughDesignationType.GRANTED_STANDARD)
        delta_rare = self._delta_pos(BreakthroughDesignationType.GRANTED_RARE_HEME)
        assert delta_rare > delta_std

    def test_fast_track_weaker_than_granted_standard(self):
        delta_fast = self._delta_pos(BreakthroughDesignationType.FAST_TRACK_ONLY)
        delta_std = self._delta_pos(BreakthroughDesignationType.GRANTED_STANDARD)
        assert delta_fast < delta_std

    def test_revoked_is_negative(self):
        delta = self._delta_pos(BreakthroughDesignationType.BREAKTHROUGH_REVOKED)
        assert delta < 0

    def test_granted_solid_tumor_weaker_than_rare_heme(self):
        delta_solid = self._delta_pos(BreakthroughDesignationType.GRANTED_SOLID_TUMOR)
        delta_rare = self._delta_pos(BreakthroughDesignationType.GRANTED_RARE_HEME)
        assert delta_solid < delta_rare


# ---------------------------------------------------------------------------
# Block 28-D: btd_timeline_acceleration_flag in POSComputeResult
# ---------------------------------------------------------------------------

class TestBTDTimelineFlag:

    def _result(self, btd_type) -> POSComputeResult:
        return compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            _base_adjusters(breakthrough_designation=btd_type),
        )

    def test_granted_standard_sets_timeline_flag(self):
        result = self._result(BreakthroughDesignationType.GRANTED_STANDARD)
        assert hasattr(result, "btd_timeline_acceleration_flag")
        assert result.btd_timeline_acceleration_flag is True

    def test_granted_rare_heme_sets_timeline_flag(self):
        result = self._result(BreakthroughDesignationType.GRANTED_RARE_HEME)
        assert result.btd_timeline_acceleration_flag is True

    def test_granted_early_phase_sets_timeline_flag(self):
        result = self._result(BreakthroughDesignationType.GRANTED_EARLY_PHASE)
        assert result.btd_timeline_acceleration_flag is True

    def test_none_no_timeline_flag(self):
        result = self._result(BreakthroughDesignationType.NONE)
        assert result.btd_timeline_acceleration_flag is False

    def test_revoked_no_timeline_flag(self):
        result = self._result(BreakthroughDesignationType.BREAKTHROUGH_REVOKED)
        assert result.btd_timeline_acceleration_flag is False

    def test_none_btd_field_no_timeline_flag(self):
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            _base_adjusters(),
        )
        assert result.btd_timeline_acceleration_flag is False


# ---------------------------------------------------------------------------
# Block 28-E: btd_overlap_warning
# ---------------------------------------------------------------------------

class TestBTDOverlapWarning:

    def test_overlap_warning_field_exists(self):
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            _base_adjusters(),
        )
        assert hasattr(result, "btd_overlap_warning")

    def test_no_overlap_by_default(self):
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            _base_adjusters(),
        )
        assert result.btd_overlap_warning is None

    def test_rare_heme_plus_strong_replicated_plus_exceeds_mcid_sets_warning(self):
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            _base_adjusters(
                breakthrough_designation=BreakthroughDesignationType.GRANTED_RARE_HEME,
                prior_phase_data=PriorPhaseDataStrength.STRONG_REPLICATED,
                clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
            ),
        )
        assert result.btd_overlap_warning is not None
        assert len(result.btd_overlap_warning) > 0

    def test_early_phase_plus_strong_single_plus_exceeds_mcid_sets_warning(self):
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            _base_adjusters(
                breakthrough_designation=BreakthroughDesignationType.GRANTED_EARLY_PHASE,
                prior_phase_data=PriorPhaseDataStrength.STRONG_SINGLE,
                clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
            ),
        )
        assert result.btd_overlap_warning is not None

    def test_granted_standard_no_overlap_flag(self):
        """Standard BTD + strong data: no overlap warning (only RARE_HEME/EARLY trigger it)."""
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            _base_adjusters(
                breakthrough_designation=BreakthroughDesignationType.GRANTED_STANDARD,
                prior_phase_data=PriorPhaseDataStrength.STRONG_REPLICATED,
                clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
            ),
        )
        assert result.btd_overlap_warning is None

    def test_no_overlap_when_prior_data_mixed(self):
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            _base_adjusters(
                breakthrough_designation=BreakthroughDesignationType.GRANTED_RARE_HEME,
                prior_phase_data=PriorPhaseDataStrength.MIXED,
                clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
            ),
        )
        assert result.btd_overlap_warning is None

    def test_overlap_warning_also_in_confidence_flags(self):
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            _base_adjusters(
                breakthrough_designation=BreakthroughDesignationType.GRANTED_RARE_HEME,
                prior_phase_data=PriorPhaseDataStrength.STRONG_REPLICATED,
                clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
            ),
        )
        assert any("btd" in f for f in result.confidence_flags)


# ---------------------------------------------------------------------------
# Block 28-F: backward compatibility
# ---------------------------------------------------------------------------

class TestBTDBackwardCompat:

    def test_has_btd_true_same_as_granted_standard(self):
        """has_breakthrough_designation=True must give same POS as GRANTED_STANDARD."""
        pos_old = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(has_breakthrough_designation=True),
        )
        pos_new = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(
                breakthrough_designation=BreakthroughDesignationType.GRANTED_STANDARD
            ),
        )
        assert pos_old == pytest.approx(pos_new, abs=1e-6)

    def test_has_btd_false_same_as_none(self):
        pos_old = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(has_breakthrough_designation=False),
        )
        pos_none = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(
                breakthrough_designation=BreakthroughDesignationType.NONE
            ),
        )
        assert pos_old == pytest.approx(pos_none, abs=1e-6)

    def test_has_btd_false_same_as_no_field(self):
        """has_breakthrough_designation=False default is backward compat with None."""
        pos_default = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(),
        )
        pos_explicit_false = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(has_breakthrough_designation=False),
        )
        assert pos_default == pytest.approx(pos_explicit_false, abs=1e-6)

    def test_existing_pos_adjusters_unchanged(self):
        """All existing fields still work; no regressions."""
        adj = POSAdjusters(
            has_breakthrough_designation=True,
            prior_phase_data=PriorPhaseDataStrength.STRONG_SINGLE,
        )
        pos = compute_pos(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, adj)
        assert 0.0 < pos < 1.0

    def test_both_fields_set_new_takes_precedence(self):
        """When breakthrough_designation is set, it takes precedence over has_breakthrough_designation."""
        pos_new_takes = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(
                has_breakthrough_designation=False,
                breakthrough_designation=BreakthroughDesignationType.GRANTED_RARE_HEME,
            ),
        )
        pos_rare_only = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(
                breakthrough_designation=BreakthroughDesignationType.GRANTED_RARE_HEME
            ),
        )
        assert pos_new_takes == pytest.approx(pos_rare_only, abs=1e-6)
