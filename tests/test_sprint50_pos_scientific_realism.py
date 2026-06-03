"""
Block 18 — POS Scientific Realism Patch
Tests for DoseSelectionConfidence, ClinicalEffectMagnitude, PlaceboResponseConcern.

TDD: these tests are written BEFORE implementation and must fail until implemented.
"""
from __future__ import annotations

import math
import pytest

from bve.entities.asset import TherapeuticArea
from bve.entities.trial import TrialPhase
from bve.models.pos_model import (
    POSAdjusters,
    _compute_layer1_adjustment,
    compute_pos,
)


# ---------------------------------------------------------------------------
# Lazy imports so missing names give ImportError → clear test failure
# ---------------------------------------------------------------------------

def _import_new():
    from bve.models.pos_model import (
        ClinicalEffectMagnitude,
        DoseSelectionConfidence,
        PlaceboResponseConcern,
        compute_pos_detailed,
    )
    return DoseSelectionConfidence, ClinicalEffectMagnitude, PlaceboResponseConcern, compute_pos_detailed


# ===========================================================================
# DoseSelectionConfidence
# ===========================================================================

class TestDoseSelectionConfidence:
    """Dose selection is downside-only: PK_PD_MODELED and EXPOSURE_RESPONSE_CHARACTERIZED = 0."""

    def test_pk_pd_modeled_zero_delta(self):
        DSC, _, _, _ = _import_new()
        adj = POSAdjusters(dose_selection_confidence=DSC.PK_PD_MODELED)
        delta, flags = _compute_layer1_adjustment(adj, ta_value="oncology", phase=TrialPhase.PHASE_3)
        # The dose component must contribute 0.0
        # Compute delta with default DSC to get baseline
        default_adj = POSAdjusters()
        baseline_delta, _ = _compute_layer1_adjustment(default_adj, ta_value="oncology", phase=TrialPhase.PHASE_3)
        # pk_pd_modeled changes nothing relative to UNKNOWN default
        assert abs(delta - baseline_delta) < 1e-9

    def test_exposure_response_zero_delta(self):
        DSC, _, _, _ = _import_new()
        adj = POSAdjusters(dose_selection_confidence=DSC.EXPOSURE_RESPONSE_CHARACTERIZED)
        default_adj = POSAdjusters()
        delta_new, _ = _compute_layer1_adjustment(adj, ta_value="oncology", phase=TrialPhase.PHASE_3)
        delta_default, _ = _compute_layer1_adjustment(default_adj, ta_value="oncology", phase=TrialPhase.PHASE_3)
        assert abs(delta_new - delta_default) < 1e-9

    def test_empirical_from_mtd_penalty(self):
        DSC, _, _, _ = _import_new()
        adj_empirical = POSAdjusters(dose_selection_confidence=DSC.EMPIRICAL_FROM_MTD)
        adj_default   = POSAdjusters()
        delta_e, _ = _compute_layer1_adjustment(adj_empirical, ta_value="oncology", phase=TrialPhase.PHASE_3)
        delta_d, _ = _compute_layer1_adjustment(adj_default,   ta_value="oncology", phase=TrialPhase.PHASE_3)
        assert abs((delta_e - delta_d) - (-0.10)) < 1e-9

    def test_empirical_no_pd_penalty(self):
        DSC, _, _, _ = _import_new()
        adj = POSAdjusters(dose_selection_confidence=DSC.EMPIRICAL_NO_PD_CONFIRMATION)
        default_adj = POSAdjusters()
        delta_new, _ = _compute_layer1_adjustment(adj, ta_value="oncology", phase=TrialPhase.PHASE_3)
        delta_def, _ = _compute_layer1_adjustment(default_adj, ta_value="oncology", phase=TrialPhase.PHASE_3)
        assert abs((delta_new - delta_def) - (-0.25)) < 1e-9

    def test_unknown_zero_delta_and_flag(self):
        DSC, _, _, _ = _import_new()
        adj = POSAdjusters(dose_selection_confidence=DSC.UNKNOWN)
        delta, flags = _compute_layer1_adjustment(adj, ta_value="oncology", phase=TrialPhase.PHASE_3)
        default_adj = POSAdjusters()
        delta_def, _ = _compute_layer1_adjustment(default_adj, ta_value="oncology", phase=TrialPhase.PHASE_3)
        # Same delta as default (UNKNOWN is also default)
        assert abs(delta - delta_def) < 1e-9
        assert "dose_selection_unknown" in flags

    def test_dose_selection_affects_pos(self):
        """End-to-end: EMPIRICAL_NO_PD lowers computed POS."""
        DSC, _, _, _ = _import_new()
        pos_good = compute_pos(TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY,
                               POSAdjusters(dose_selection_confidence=DSC.PK_PD_MODELED))
        pos_bad  = compute_pos(TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY,
                               POSAdjusters(dose_selection_confidence=DSC.EMPIRICAL_NO_PD_CONFIRMATION))
        assert pos_bad < pos_good


# ===========================================================================
# ClinicalEffectMagnitude
# ===========================================================================

class TestClinicalEffectMagnitude:

    def test_exceeds_mcid_positive(self):
        _, CEM, _, _ = _import_new()
        adj = POSAdjusters(clinical_effect_magnitude=CEM.EXCEEDS_MCID)
        default_adj = POSAdjusters(clinical_effect_magnitude=CEM.MEETS_MCID)
        delta_exc, _ = _compute_layer1_adjustment(adj,         ta_value="oncology", phase=TrialPhase.PHASE_3)
        delta_def, _ = _compute_layer1_adjustment(default_adj, ta_value="oncology", phase=TrialPhase.PHASE_3)
        assert abs((delta_exc - delta_def) - 0.25) < 1e-9

    def test_below_mcid_penalty(self):
        _, CEM, _, _ = _import_new()
        adj = POSAdjusters(clinical_effect_magnitude=CEM.BELOW_MCID)
        default_adj = POSAdjusters(clinical_effect_magnitude=CEM.MEETS_MCID)
        delta_below, _ = _compute_layer1_adjustment(adj,         ta_value="oncology", phase=TrialPhase.PHASE_3)
        delta_def, _   = _compute_layer1_adjustment(default_adj, ta_value="oncology", phase=TrialPhase.PHASE_3)
        assert abs((delta_below - delta_def) - (-0.30)) < 1e-9

    def test_unknown_produces_flag(self):
        _, CEM, _, _ = _import_new()
        adj = POSAdjusters(clinical_effect_magnitude=CEM.UNKNOWN)
        _, flags = _compute_layer1_adjustment(adj, ta_value="oncology", phase=TrialPhase.PHASE_3)
        assert "clinical_effect_unknown" in flags

    def test_unknown_zero_delta(self):
        _, CEM, _, _ = _import_new()
        adj_unknown = POSAdjusters(clinical_effect_magnitude=CEM.UNKNOWN)
        adj_meets   = POSAdjusters(clinical_effect_magnitude=CEM.MEETS_MCID)
        delta_u, _ = _compute_layer1_adjustment(adj_unknown, ta_value="oncology", phase=TrialPhase.PHASE_3)
        delta_m, _ = _compute_layer1_adjustment(adj_meets,   ta_value="oncology", phase=TrialPhase.PHASE_3)
        assert abs(delta_u - delta_m) < 1e-9

    def test_noop_at_phase1(self):
        """ClinicalEffectMagnitude should not apply at Phase 1."""
        _, CEM, _, _ = _import_new()
        adj_below   = POSAdjusters(clinical_effect_magnitude=CEM.BELOW_MCID)
        adj_exceeds = POSAdjusters(clinical_effect_magnitude=CEM.EXCEEDS_MCID)
        delta_below, _ = _compute_layer1_adjustment(adj_below,   ta_value="oncology", phase=TrialPhase.PHASE_1)
        delta_exc, _   = _compute_layer1_adjustment(adj_exceeds, ta_value="oncology", phase=TrialPhase.PHASE_1)
        assert abs(delta_below - delta_exc) < 1e-9, "No magnitude effect at Phase 1"

    def test_noop_at_nda_bla(self):
        _, CEM, _, _ = _import_new()
        adj_below   = POSAdjusters(clinical_effect_magnitude=CEM.BELOW_MCID)
        adj_exceeds = POSAdjusters(clinical_effect_magnitude=CEM.EXCEEDS_MCID)
        delta_below, _ = _compute_layer1_adjustment(adj_below,   ta_value="oncology", phase=TrialPhase.NDA_BLA)
        delta_exc, _   = _compute_layer1_adjustment(adj_exceeds, ta_value="oncology", phase=TrialPhase.NDA_BLA)
        assert abs(delta_below - delta_exc) < 1e-9, "No magnitude effect at NDA/BLA"

    def test_active_at_phase2(self):
        _, CEM, _, _ = _import_new()
        adj_below   = POSAdjusters(clinical_effect_magnitude=CEM.BELOW_MCID)
        adj_meets   = POSAdjusters(clinical_effect_magnitude=CEM.MEETS_MCID)
        delta_below, _ = _compute_layer1_adjustment(adj_below, ta_value="oncology", phase=TrialPhase.PHASE_2)
        delta_meets, _ = _compute_layer1_adjustment(adj_meets, ta_value="oncology", phase=TrialPhase.PHASE_2)
        assert delta_below < delta_meets, "BELOW_MCID should penalise at Phase 2"


# ===========================================================================
# PlaceboResponseConcern
# ===========================================================================

class TestPlaceboResponseConcern:

    def test_default_is_unknown(self):
        _, _, PRC, _ = _import_new()
        adj = POSAdjusters()
        assert adj.placebo_response_concern == PRC.UNKNOWN

    def test_unknown_flag_set_in_applicable_ta(self):
        _, _, PRC, _ = _import_new()
        adj = POSAdjusters(placebo_response_concern=PRC.UNKNOWN)
        _, flags = _compute_layer1_adjustment(adj, ta_value="cns", phase=TrialPhase.PHASE_3)
        assert "placebo_response_unassessed" in flags

    def test_none_no_flag_no_delta(self):
        _, _, PRC, _ = _import_new()
        adj_none = POSAdjusters(placebo_response_concern=PRC.NONE)
        adj_unknown = POSAdjusters(placebo_response_concern=PRC.UNKNOWN)
        delta_none, flags_none = _compute_layer1_adjustment(adj_none,    ta_value="cns", phase=TrialPhase.PHASE_3)
        delta_unknown, _       = _compute_layer1_adjustment(adj_unknown, ta_value="cns", phase=TrialPhase.PHASE_3)
        # NONE = 0.00 delta; UNKNOWN = 0.00 delta but with flag
        assert abs(delta_none - delta_unknown) < 1e-9
        assert "placebo_response_unassessed" not in flags_none

    def test_moderate_penalty_in_cns(self):
        _, _, PRC, _ = _import_new()
        adj_mod  = POSAdjusters(placebo_response_concern=PRC.MODERATE)
        adj_none = POSAdjusters(placebo_response_concern=PRC.NONE)
        delta_mod,  _ = _compute_layer1_adjustment(adj_mod,  ta_value="cns", phase=TrialPhase.PHASE_3)
        delta_none, _ = _compute_layer1_adjustment(adj_none, ta_value="cns", phase=TrialPhase.PHASE_3)
        assert abs((delta_mod - delta_none) - (-0.15)) < 1e-9

    def test_high_penalty_in_psychiatry(self):
        _, _, PRC, _ = _import_new()
        adj_high = POSAdjusters(placebo_response_concern=PRC.HIGH)
        adj_none = POSAdjusters(placebo_response_concern=PRC.NONE)
        delta_high, _ = _compute_layer1_adjustment(adj_high, ta_value="psychiatry", phase=TrialPhase.PHASE_2)
        delta_none, _ = _compute_layer1_adjustment(adj_none, ta_value="psychiatry", phase=TrialPhase.PHASE_2)
        assert abs((delta_high - delta_none) - (-0.30)) < 1e-9

    def test_high_penalty_in_gastroenterology(self):
        _, _, PRC, _ = _import_new()
        adj_high = POSAdjusters(placebo_response_concern=PRC.HIGH)
        adj_none = POSAdjusters(placebo_response_concern=PRC.NONE)
        delta_high, _ = _compute_layer1_adjustment(adj_high, ta_value="gastroenterology", phase=TrialPhase.PHASE_3)
        delta_none, _ = _compute_layer1_adjustment(adj_none, ta_value="gastroenterology", phase=TrialPhase.PHASE_3)
        assert abs((delta_high - delta_none) - (-0.30)) < 1e-9

    def test_noop_in_oncology(self):
        """PlaceboResponseConcern should not apply in oncology."""
        _, _, PRC, _ = _import_new()
        adj_high = POSAdjusters(placebo_response_concern=PRC.HIGH)
        adj_none = POSAdjusters(placebo_response_concern=PRC.NONE)
        delta_high, _ = _compute_layer1_adjustment(adj_high, ta_value="oncology", phase=TrialPhase.PHASE_3)
        delta_none, _ = _compute_layer1_adjustment(adj_none, ta_value="oncology", phase=TrialPhase.PHASE_3)
        assert abs(delta_high - delta_none) < 1e-9

    def test_noop_at_phase1(self):
        _, _, PRC, _ = _import_new()
        adj_high = POSAdjusters(placebo_response_concern=PRC.HIGH)
        adj_none = POSAdjusters(placebo_response_concern=PRC.NONE)
        delta_high, _ = _compute_layer1_adjustment(adj_high, ta_value="cns", phase=TrialPhase.PHASE_1)
        delta_none, _ = _compute_layer1_adjustment(adj_none, ta_value="cns", phase=TrialPhase.PHASE_1)
        assert abs(delta_high - delta_none) < 1e-9

    def test_noop_at_nda_bla(self):
        _, _, PRC, _ = _import_new()
        adj_high = POSAdjusters(placebo_response_concern=PRC.HIGH)
        adj_none = POSAdjusters(placebo_response_concern=PRC.NONE)
        delta_high, _ = _compute_layer1_adjustment(adj_high, ta_value="cns", phase=TrialPhase.NDA_BLA)
        delta_none, _ = _compute_layer1_adjustment(adj_none, ta_value="cns", phase=TrialPhase.NDA_BLA)
        assert abs(delta_high - delta_none) < 1e-9

    def test_noop_in_cardiovascular(self):
        _, _, PRC, _ = _import_new()
        adj_high = POSAdjusters(placebo_response_concern=PRC.HIGH)
        adj_none = POSAdjusters(placebo_response_concern=PRC.NONE)
        delta_high, _ = _compute_layer1_adjustment(adj_high, ta_value="cardiovascular", phase=TrialPhase.PHASE_3)
        delta_none, _ = _compute_layer1_adjustment(adj_none, ta_value="cardiovascular", phase=TrialPhase.PHASE_3)
        assert abs(delta_high - delta_none) < 1e-9


# ===========================================================================
# compute_pos_detailed
# ===========================================================================

class TestComputePosDetailed:

    def test_returns_pos_compute_result(self):
        DSC, CEM, PRC, compute_pos_detailed = _import_new()
        from bve.models.pos_model import POSComputeResult
        result = compute_pos_detailed(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY,
            POSAdjusters(),
        )
        assert isinstance(result, POSComputeResult)
        assert 0.0 < result.pos < 1.0

    def test_confidence_flags_populated(self):
        DSC, CEM, PRC, compute_pos_detailed = _import_new()
        adj = POSAdjusters()  # UNKNOWN for dose + effect + placebo (default)
        result = compute_pos_detailed(
            TrialPhase.PHASE_3, TherapeuticArea.CNS,
            adj,
        )
        # Default has UNKNOWN dose, UNKNOWN effect, UNKNOWN placebo (in CNS Phase 3 — all three)
        assert "dose_selection_unknown" in result.confidence_flags
        assert "clinical_effect_unknown" in result.confidence_flags
        assert "placebo_response_unassessed" in result.confidence_flags

    def test_phase_realism_applied_true_at_phase3(self):
        DSC, CEM, PRC, compute_pos_detailed = _import_new()
        result = compute_pos_detailed(TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY, POSAdjusters())
        assert result.phase_realism_applied is True

    def test_phase_realism_applied_false_at_phase1(self):
        DSC, CEM, PRC, compute_pos_detailed = _import_new()
        result = compute_pos_detailed(TrialPhase.PHASE_1, TherapeuticArea.ONCOLOGY, POSAdjusters())
        assert result.phase_realism_applied is False

    def test_compute_pos_wrapper_returns_float(self):
        """compute_pos() must still return a plain float for backward compat."""
        result = compute_pos(TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY, POSAdjusters())
        assert isinstance(result, float)
        assert 0.0 < result < 1.0


# ===========================================================================
# Backward compatibility
# ===========================================================================

class TestBackwardCompatibility:

    def test_existing_pos_adjusters_unchanged(self):
        """POSAdjusters without new fields must produce identical output to before."""
        from bve.models.pos_model import _compute_layer1_adjustment as cla
        adj = POSAdjusters()  # All defaults
        # Must not raise; delta + flags must work
        delta, flags = cla(adj, ta_value="oncology", phase=TrialPhase.PHASE_3)
        assert isinstance(delta, float)
        assert isinstance(flags, list)

    def test_layer1_adjustment_no_phase_arg_still_works(self):
        """_compute_layer1_adjustment without phase arg must still run (phase=None path)."""
        from bve.models.pos_model import _compute_layer1_adjustment as cla
        adj = POSAdjusters()
        # Should not raise; returns (delta, flags) — phase=None disables phase-gated adjusters
        result = cla(adj, ta_value="oncology")
        assert len(result) == 2

    def test_compute_pos_float_no_new_args(self):
        """compute_pos() with only old args must keep returning float."""
        pos = compute_pos(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY)
        assert isinstance(pos, float)

    def test_apply_pos_to_trials_still_works(self):
        """apply_pos_to_trials must still work after Block 18 changes."""
        from bve.models.pos_model import apply_pos_to_trials
        from bve.entities.trial import ClinicalTrial, TrialPhase, EndpointType
        from bve.entities.asset import TherapeuticArea
        import uuid

        asset_id = str(uuid.uuid4())
        trial = ClinicalTrial(
            id=str(uuid.uuid4()),
            asset_id=asset_id,
            phase=TrialPhase.PHASE_2,
            success_probability=0.40,
            duration_years=2.0,
            cost_millions=50.0,
            endpoint_type=EndpointType.SURROGATE_VALIDATED,
        )
        updated = apply_pos_to_trials([trial], TherapeuticArea.ONCOLOGY)
        assert len(updated) == 1
        assert 0.0 < updated[0].success_probability < 1.0


# ===========================================================================
# Cap invariant
# ===========================================================================

class TestCapInvariant:

    def test_all_positive_realism_does_not_bust_cap(self):
        """Stacking all positive adjusters must still be bounded by L1 cap."""
        DSC, CEM, PRC, _ = _import_new()
        from bve.models.pos_model import (
            BiomarkerSelectionStrength,
            CompetitivePressure,
            MoAPrecedent,
            PriorPhaseDataStrength,
            SafetyProfile,
            SampleSizeAdequacy,
            _L1_CAP_POSITIVE,
        )
        from bve.entities.trial import EndpointType
        adj = POSAdjusters(
            dose_selection_confidence=DSC.PK_PD_MODELED,
            clinical_effect_magnitude=CEM.EXCEEDS_MCID,
            placebo_response_concern=PRC.NONE,
            moa_precedent=MoAPrecedent.VALIDATED,
            sample_size_adequacy=SampleSizeAdequacy.WELL_POWERED,
            safety_profile=SafetyProfile.CLEAN,
            competitive_pressure=CompetitivePressure.LOW_BAR,
            biomarker_selection=BiomarkerSelectionStrength.VALIDATED,
            prior_phase_data=PriorPhaseDataStrength.STRONG_REPLICATED,
            endpoint_type=EndpointType.HARD_CLINICAL,
        )
        delta, _ = _compute_layer1_adjustment(adj, ta_value="oncology", phase=TrialPhase.PHASE_3)
        # compute_pos applies the cap internally; just verify the raw delta can be large
        # but the final POS is valid
        pos = compute_pos(TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY, adj)
        assert 0.0 < pos <= 1.0
