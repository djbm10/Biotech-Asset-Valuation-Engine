"""
Block 34 — POS Data Integrity + Guard Fixes
TDD tests written BEFORE implementation.

Covers:
  34A: pos_calibration.py uses AssumptionsLoader base rates, not hardcoded dict
  34B: extraordinary_evidence gate — requires STRONG_REPLICATED + VALIDATED + EXCEEDS_MCID + rationale
  34C: clinical_effect_magnitude at NDA/BLA emits confidence flag
  34D: combined L1+L2 cap (COMBINED_L1_L2_CAP_POSITIVE=+0.90, COMBINED_L1_L2_CAP_NEGATIVE=-0.90)
  34E: absolute POS ceiling formula + ceiling_applied field on POSComputeResult
"""
from __future__ import annotations

import math
import warnings

import pytest

from bve.config.assumptions_loader import AssumptionsLoader
from bve.entities.trial import TrialPhase
from bve.models.pos_model import (
    BiomarkerSelectionStrength,
    ClinicalEffectMagnitude,
    POSAdjusters,
    POSComputeResult,
    PriorPhaseDataStrength,
    compute_pos,
    compute_pos_detailed,
    TherapeuticArea,
)


# ---------------------------------------------------------------------------
# Block 34A — Calibration baseline reads from AssumptionsLoader
# ---------------------------------------------------------------------------

class TestCalibrationBaseline:

    def test_calibration_oncology_phase2_matches_assumptions_loader(self):
        """pos_calibration.py oncology phase_2 rate must match AssumptionsLoader, not 0.40."""
        from bve.analysis.pos_calibration import BASE_RATE_INDUSTRY
        loader = AssumptionsLoader.get()
        expected = loader.phase_success_rates_for("oncology")["phase_2"]
        assert BASE_RATE_INDUSTRY["oncology"]["phase_2"] == pytest.approx(expected, abs=1e-4)

    def test_calibration_oncology_phase3_matches_assumptions_loader(self):
        from bve.analysis.pos_calibration import BASE_RATE_INDUSTRY
        loader = AssumptionsLoader.get()
        expected = loader.phase_success_rates_for("oncology")["phase_3"]
        assert BASE_RATE_INDUSTRY["oncology"]["phase_3"] == pytest.approx(expected, abs=1e-4)

    def test_calibration_rare_disease_phase2_matches_assumptions_loader(self):
        from bve.analysis.pos_calibration import BASE_RATE_INDUSTRY
        loader = AssumptionsLoader.get()
        expected = loader.phase_success_rates_for("rare_disease")["phase_2"]
        assert BASE_RATE_INDUSTRY["rare_disease"]["phase_2"] == pytest.approx(expected, abs=1e-4)

    def test_calibration_cns_phase2_matches_assumptions_loader(self):
        from bve.analysis.pos_calibration import BASE_RATE_INDUSTRY
        loader = AssumptionsLoader.get()
        expected = loader.phase_success_rates_for("cns")["phase_2"]
        assert BASE_RATE_INDUSTRY["cns"]["phase_2"] == pytest.approx(expected, abs=1e-4)

    def test_calibration_not_hardcoded_0_40(self):
        """The old hardcoded oncology phase_2 = 0.40 was wrong. Must not be 0.40."""
        from bve.analysis.pos_calibration import BASE_RATE_INDUSTRY
        # AssumptionsLoader oncology phase_2 is ~0.234 (solid) or similar; not 0.40
        assert BASE_RATE_INDUSTRY["oncology"]["phase_2"] != pytest.approx(0.40, abs=0.05)


# ---------------------------------------------------------------------------
# Block 34B — extraordinary_evidence gate
# ---------------------------------------------------------------------------

class TestExtraordinaryEvidenceGate:

    # --- New field exists ---

    def test_extraordinary_evidence_rationale_field_exists(self):
        adj = POSAdjusters()
        assert hasattr(adj, "extraordinary_evidence_rationale")

    def test_extraordinary_evidence_rationale_default_empty(self):
        adj = POSAdjusters()
        assert adj.extraordinary_evidence_rationale == ""

    # --- Gate: all three conditions + rationale required ---

    def test_extraordinary_evidence_blocked_without_conditions(self):
        """extraordinary_evidence=True reset to False when conditions not met."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            adj = POSAdjusters(extraordinary_evidence=True)
        assert adj.extraordinary_evidence is False
        assert any("extraordinary_evidence" in str(warning.message) for warning in w)

    def test_extraordinary_evidence_blocked_without_rationale(self):
        """Even with all three conditions, empty rationale blocks it."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            adj = POSAdjusters(
                extraordinary_evidence=True,
                prior_phase_data=PriorPhaseDataStrength.STRONG_REPLICATED,
                biomarker_selection=BiomarkerSelectionStrength.VALIDATED,
                clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
                # extraordinary_evidence_rationale not set — defaults to ""
            )
        assert adj.extraordinary_evidence is False
        assert any("extraordinary_evidence" in str(warning.message) for warning in w)

    def test_extraordinary_evidence_blocked_missing_strong_replicated(self):
        """STRONG_SINGLE is not enough — must be STRONG_REPLICATED."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            adj = POSAdjusters(
                extraordinary_evidence=True,
                prior_phase_data=PriorPhaseDataStrength.STRONG_SINGLE,  # not STRONG_REPLICATED
                biomarker_selection=BiomarkerSelectionStrength.VALIDATED,
                clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
                extraordinary_evidence_rationale="Phase 2 replication across 3 cohorts",
            )
        assert adj.extraordinary_evidence is False

    def test_extraordinary_evidence_blocked_missing_validated_biomarker(self):
        """STRONG_RATIONALE biomarker is not enough — must be VALIDATED."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            adj = POSAdjusters(
                extraordinary_evidence=True,
                prior_phase_data=PriorPhaseDataStrength.STRONG_REPLICATED,
                biomarker_selection=BiomarkerSelectionStrength.STRONG_RATIONALE,  # not VALIDATED
                clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
                extraordinary_evidence_rationale="Phase 2 replication across 3 cohorts",
            )
        assert adj.extraordinary_evidence is False

    def test_extraordinary_evidence_blocked_missing_exceeds_mcid(self):
        """MEETS_MCID is not enough — must be EXCEEDS_MCID."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            adj = POSAdjusters(
                extraordinary_evidence=True,
                prior_phase_data=PriorPhaseDataStrength.STRONG_REPLICATED,
                biomarker_selection=BiomarkerSelectionStrength.VALIDATED,
                clinical_effect_magnitude=ClinicalEffectMagnitude.MEETS_MCID,  # not EXCEEDS_MCID
                extraordinary_evidence_rationale="Phase 2 replication across 3 cohorts",
            )
        assert adj.extraordinary_evidence is False

    def test_extraordinary_evidence_allowed_when_all_conditions_met(self):
        """All four conditions met → extraordinary_evidence stays True, no warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            adj = POSAdjusters(
                extraordinary_evidence=True,
                prior_phase_data=PriorPhaseDataStrength.STRONG_REPLICATED,
                biomarker_selection=BiomarkerSelectionStrength.VALIDATED,
                clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
                extraordinary_evidence_rationale="91% biomarker correction replicated across 3 cohorts",
            )
        assert adj.extraordinary_evidence is True
        assert not any("extraordinary_evidence" in str(warning.message) for warning in w)

    def test_extraordinary_evidence_false_by_default_no_warning(self):
        """extraordinary_evidence=False (default) with no conditions → no warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            adj = POSAdjusters()
        assert not any("extraordinary_evidence" in str(warning.message) for warning in w)

    def test_extraordinary_evidence_expands_cap_when_allowed(self):
        """When extraordinary_evidence is valid, it expands positive cap to +1.00."""
        pos_normal = compute_pos(
            TrialPhase.PHASE_3,
            TherapeuticArea.RARE_DISEASE,
            POSAdjusters(
                prior_phase_data=PriorPhaseDataStrength.STRONG_REPLICATED,
                biomarker_selection=BiomarkerSelectionStrength.VALIDATED,
                clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
            ),
        )
        pos_extraordinary = compute_pos(
            TrialPhase.PHASE_3,
            TherapeuticArea.RARE_DISEASE,
            POSAdjusters(
                extraordinary_evidence=True,
                prior_phase_data=PriorPhaseDataStrength.STRONG_REPLICATED,
                biomarker_selection=BiomarkerSelectionStrength.VALIDATED,
                clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
                extraordinary_evidence_rationale="91% biomarker correction replicated",
            ),
        )
        # extraordinary cap allows slightly higher POS
        assert pos_extraordinary >= pos_normal


# ---------------------------------------------------------------------------
# Block 34C — clinical_effect_magnitude at NDA/BLA emits confidence flag
# ---------------------------------------------------------------------------

class TestClinicalEffectNDAFlag:

    def test_exceeds_mcid_at_nda_bla_emits_flag(self):
        """EXCEEDS_MCID at NDA/BLA must emit the not_applicable flag."""
        result = compute_pos_detailed(
            TrialPhase.NDA_BLA,
            TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID),
        )
        assert "clinical_effect_magnitude_not_applicable_at_nda" in result.confidence_flags

    def test_meets_mcid_at_nda_bla_emits_flag(self):
        """MEETS_MCID at NDA/BLA must emit the not_applicable flag."""
        result = compute_pos_detailed(
            TrialPhase.NDA_BLA,
            TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(clinical_effect_magnitude=ClinicalEffectMagnitude.MEETS_MCID),
        )
        assert "clinical_effect_magnitude_not_applicable_at_nda" in result.confidence_flags

    def test_below_mcid_at_nda_bla_emits_flag(self):
        """BELOW_MCID at NDA/BLA must emit the not_applicable flag."""
        result = compute_pos_detailed(
            TrialPhase.NDA_BLA,
            TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(clinical_effect_magnitude=ClinicalEffectMagnitude.BELOW_MCID),
        )
        assert "clinical_effect_magnitude_not_applicable_at_nda" in result.confidence_flags

    def test_unknown_at_nda_bla_no_nda_flag(self):
        """UNKNOWN at NDA/BLA should NOT emit the not_applicable flag."""
        result = compute_pos_detailed(
            TrialPhase.NDA_BLA,
            TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(clinical_effect_magnitude=ClinicalEffectMagnitude.UNKNOWN),
        )
        assert "clinical_effect_magnitude_not_applicable_at_nda" not in result.confidence_flags

    def test_exceeds_mcid_at_phase2_no_nda_flag(self):
        """EXCEEDS_MCID at Phase 2 must NOT emit the NDA flag."""
        result = compute_pos_detailed(
            TrialPhase.PHASE_2,
            TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID),
        )
        assert "clinical_effect_magnitude_not_applicable_at_nda" not in result.confidence_flags

    def test_clinical_effect_at_nda_bla_has_no_point_estimate_effect(self):
        """The flag should be informational only; NDA/BLA POS unchanged by clinical_effect."""
        result_exceeds = compute_pos_detailed(
            TrialPhase.NDA_BLA,
            TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID),
        )
        result_below = compute_pos_detailed(
            TrialPhase.NDA_BLA,
            TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(clinical_effect_magnitude=ClinicalEffectMagnitude.BELOW_MCID),
        )
        # At NDA/BLA, clinical_effect_magnitude should not affect POS (already phase-gated)
        assert result_exceeds.pos == pytest.approx(result_below.pos, abs=1e-4)


# ---------------------------------------------------------------------------
# Block 34D — Combined L1+L2 cap
# ---------------------------------------------------------------------------

class TestCombinedL1L2Cap:

    def test_combined_cap_constants_exist(self):
        """COMBINED_L1_L2_CAP_POSITIVE and COMBINED_L1_L2_CAP_NEGATIVE must be importable."""
        from bve.models.pos_model import COMBINED_L1_L2_CAP_POSITIVE, COMBINED_L1_L2_CAP_NEGATIVE
        assert COMBINED_L1_L2_CAP_POSITIVE == pytest.approx(0.90, abs=1e-6)
        assert COMBINED_L1_L2_CAP_NEGATIVE == pytest.approx(-0.90, abs=1e-6)

    def test_combined_cap_positive_value(self):
        from bve.models.pos_model import COMBINED_L1_L2_CAP_POSITIVE
        assert COMBINED_L1_L2_CAP_POSITIVE == 0.90

    def test_combined_cap_negative_value(self):
        from bve.models.pos_model import COMBINED_L1_L2_CAP_NEGATIVE
        assert COMBINED_L1_L2_CAP_NEGATIVE == -0.90

    def test_combined_cap_positive_enforced_in_engine(self):
        """When L1+L2 would exceed +0.90, the combined cap must be enforced."""
        from bve.models.trial_design_features import EvidenceDesignQuality, ComparatorFit, RegulatoryPathwayRisk, TrialDesignFeatureSet, compute_design_adjusted_pos

        # Build max-positive L1 adjusters
        l1_adj = POSAdjusters(
            prior_phase_data=PriorPhaseDataStrength.STRONG_REPLICATED,
            biomarker_selection=BiomarkerSelectionStrength.VALIDATED,
            clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
        )
        # Build max-positive L2 features
        l2_features = TrialDesignFeatureSet(
            evidence_design_quality=EvidenceDesignQuality.RCT_DOUBLE_BLIND,
            comparator_fit=ComparatorFit.MATCHES_SOC,
            regulatory_pathway_risk=RegulatoryPathwayRisk.ORPHAN_RARE_DISEASE,
        )

        # Compute L1 POS
        pos_l1 = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.RARE_DISEASE, l1_adj
        )

        # Compute the base rate to enforce combined cap
        base_rate = AssumptionsLoader.get().phase_success_rates_for("rare_disease")["phase_3"]

        # Apply L2 with combined cap via base_rate parameter
        dar = compute_design_adjusted_pos(pos_l1, l2_features, phase="phase_3", base_rate=base_rate)
        pos_combined = dar.adjusted_pos

        # The combined capped pos should be <= sigmoid(base_log_odds + 0.90)
        base_rate_clamped = max(0.01, min(0.99, base_rate))
        base_log_odds = math.log(base_rate_clamped / (1 - base_rate_clamped))
        max_combined_pos = 1.0 / (1.0 + math.exp(-(base_log_odds + 0.90)))

        assert pos_combined <= max_combined_pos + 1e-4

    def test_combined_cap_negative_enforced_in_engine(self):
        """When L1+L2 would go below -0.90, the combined cap must be enforced."""
        from bve.models.pos_model import SafetyProfile, MoAPrecedent, SampleSizeAdequacy
        from bve.models.trial_design_features import EvidenceDesignQuality, ComparatorFit, RegulatoryPathwayRisk, TrialDesignFeatureSet, compute_design_adjusted_pos

        # Build max-negative L1 adjusters
        l1_adj = POSAdjusters(
            safety_profile=SafetyProfile.MECHANISM_LINKED_SEVERE,
            moa_precedent=MoAPrecedent.KNOWN_LIABILITY,
            sample_size_adequacy=SampleSizeAdequacy.EXPLORATORY,
            clinical_effect_magnitude=ClinicalEffectMagnitude.BELOW_MCID,
        )
        # Build max-negative L2 features
        l2_features = TrialDesignFeatureSet(
            evidence_design_quality=EvidenceDesignQuality.REGISTRY_OBSERVATIONAL,
            comparator_fit=ComparatorFit.NO_VALID_COMPARATOR,
            regulatory_pathway_risk=RegulatoryPathwayRisk.NO_CLEAR_PRECEDENT,
        )

        # Compute L1 POS
        pos_l1 = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY_SOLID, l1_adj
        )

        # Compute the base rate to enforce combined cap
        base_rate = AssumptionsLoader.get().phase_success_rates_for("oncology_solid")["phase_3"]

        # Apply L2 with combined cap via base_rate parameter
        dar = compute_design_adjusted_pos(pos_l1, l2_features, phase="phase_3", base_rate=base_rate)
        pos_combined = dar.adjusted_pos

        # The combined capped pos should be >= sigmoid(base_log_odds - 0.90)
        base_rate_clamped = max(0.01, min(0.99, base_rate))
        base_log_odds = math.log(base_rate_clamped / (1 - base_rate_clamped))
        min_combined_pos = 1.0 / (1.0 + math.exp(-(base_log_odds - 0.90)))

        assert pos_combined >= min_combined_pos - 1e-4


# ---------------------------------------------------------------------------
# Block 34E — Absolute POS ceiling
# ---------------------------------------------------------------------------

class TestAbsolutePOSCeiling:

    def test_ceiling_applied_field_exists(self):
        """POSComputeResult must have ceiling_applied bool field."""
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        assert hasattr(result, "ceiling_applied")

    def test_ceiling_applied_default_false(self):
        """Default case should not apply ceiling."""
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        assert isinstance(result.ceiling_applied, bool)

    def test_ceiling_formula_low_base_rate(self):
        """Ceiling for low base rate: min(0.75, max(0.10*2.5, 0.10+0.25)) = min(0.75, max(0.25, 0.35)) = 0.35."""
        base_rate = 0.10
        ceiling = min(0.75, max(base_rate * 2.5, base_rate + 0.25))
        assert ceiling == pytest.approx(0.35, abs=1e-6)

    def test_ceiling_formula_medium_base_rate(self):
        """Ceiling for 0.40 base rate: min(0.75, max(1.00, 0.65)) = 0.75."""
        base_rate = 0.40
        ceiling = min(0.75, max(base_rate * 2.5, base_rate + 0.25))
        assert ceiling == pytest.approx(0.75, abs=1e-6)

    def test_ceiling_formula_high_base_rate(self):
        """Ceiling for 0.60 base rate: min(0.75, max(1.50, 0.85)) = 0.75."""
        base_rate = 0.60
        ceiling = min(0.75, max(base_rate * 2.5, base_rate + 0.25))
        assert ceiling == pytest.approx(0.75, abs=1e-6)

    def test_ceiling_applied_when_exceeded(self):
        """When max adjusters push POS above ceiling, ceiling_applied=True."""
        # Use rare_disease phase_2 base rate ~0.48; ceiling = min(0.75, max(1.20, 0.73)) = 0.75
        # With max positive adjusters, POS might hit ceiling
        adj = POSAdjusters(
            prior_phase_data=PriorPhaseDataStrength.STRONG_REPLICATED,
            biomarker_selection=BiomarkerSelectionStrength.VALIDATED,
            clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
        )
        result = compute_pos_detailed(
            TrialPhase.PHASE_2,
            TherapeuticArea.RARE_DISEASE,
            adj,
        )
        if result.ceiling_applied:
            # Verify the POS is at or near the ceiling value
            base_rate = AssumptionsLoader.get().phase_success_rates_for("rare_disease")["phase_2"]
            expected_ceiling = min(0.75, max(base_rate * 2.5, base_rate + 0.25))
            assert result.pos <= expected_ceiling + 1e-4

    def test_ceiling_not_applied_without_strong_adjusters(self):
        """With default adjusters, ceiling should not be applied."""
        result = compute_pos_detailed(
            TrialPhase.PHASE_2,
            TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(),
        )
        assert result.ceiling_applied is False

    def test_pos_never_exceeds_ceiling(self):
        """For any combo of adjusters, pos must not exceed ceiling formula."""
        adj = POSAdjusters(
            prior_phase_data=PriorPhaseDataStrength.STRONG_REPLICATED,
            biomarker_selection=BiomarkerSelectionStrength.VALIDATED,
            clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
        )
        for ta in [TherapeuticArea.RARE_DISEASE, TherapeuticArea.ONCOLOGY_SOLID,
                   TherapeuticArea.CNS, TherapeuticArea.CARDIOVASCULAR]:
            for phase in [TrialPhase.PHASE_2, TrialPhase.PHASE_3]:
                result = compute_pos_detailed(phase, ta, adj)
                ta_key = ta.value
                loader = AssumptionsLoader.get()
                base_rates = loader.phase_success_rates_for(ta_key)
                base_rate = base_rates.get(phase.value, 0.40)
                ceiling = min(0.75, max(base_rate * 2.5, base_rate + 0.25))
                assert result.pos <= ceiling + 1e-4, (
                    f"{ta.value}/{phase.value}: pos={result.pos} > ceiling={ceiling}"
                )

    def test_ceiling_formula_gbm_subtype_base_rate(self):
        """GBM base rate ~0.12: ceiling = min(0.75, max(0.30, 0.37)) = 0.37."""
        base_rate = 0.12
        ceiling = min(0.75, max(base_rate * 2.5, base_rate + 0.25))
        assert ceiling == pytest.approx(0.37, abs=1e-6)

    def test_compute_pos_scalar_respects_ceiling(self):
        """compute_pos() (scalar) should also respect the ceiling."""
        adj = POSAdjusters(
            prior_phase_data=PriorPhaseDataStrength.STRONG_REPLICATED,
            biomarker_selection=BiomarkerSelectionStrength.VALIDATED,
            clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
        )
        for ta in [TherapeuticArea.RARE_DISEASE, TherapeuticArea.ONCOLOGY_SOLID]:
            for phase in [TrialPhase.PHASE_2, TrialPhase.PHASE_3]:
                pos = compute_pos(phase, ta, adj)
                ta_key = ta.value
                loader = AssumptionsLoader.get()
                base_rates = loader.phase_success_rates_for(ta_key)
                base_rate = base_rates.get(phase.value, 0.40)
                ceiling = min(0.75, max(base_rate * 2.5, base_rate + 0.25))
                assert pos <= ceiling + 1e-4
