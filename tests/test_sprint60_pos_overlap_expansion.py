"""
Block 24 — POS Overlap Expansion
TDD tests written BEFORE implementation.

Tests for three new double-count patterns in check_pos_layer_overlap():

  Pattern 3: VALIDATED/STRONG_RATIONALE biomarker selection + ClinicalEffectMagnitude.EXCEEDS_MCID
  Pattern 4: MoAExceptionFlag (STRONG_BIOMARKER_RESPONSE or HUMAN_PROOF_OF_MECHANISM) + EXCEEDS_MCID
  Pattern 5: intra-Layer-1 — HUMAN_PROOF_OF_MECHANISM + CLINICALLY_VALIDATED_TARGET

Also tests that existing patterns 1 and 2 still work (backward compat).
"""
from __future__ import annotations

import pytest

from bve.models.trial_design_features import (
    TrialDesignFeatureSet,
    EvidenceDesignQuality,
    ComparatorFit,
    RegulatoryPathwayRisk,
    ClinicalEffectMagnitude,
    check_pos_layer_overlap,
    LayerOverlapReport,
)
from bve.models.pos_model import (
    POSAdjusters,
    BiomarkerSelectionStrength,
    MoAExceptionFlag,
    MoAPrecedent,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _clean_adjusters() -> POSAdjusters:
    """No overlapping signals."""
    return POSAdjusters(
        moa_precedent=MoAPrecedent.PARTIAL,
        moa_exception_flags=[],
        biomarker_selection=BiomarkerSelectionStrength.NO_SELECTION,
    )


def _clean_features() -> TrialDesignFeatureSet:
    """Default (no elevated signals)."""
    return TrialDesignFeatureSet()


# ---------------------------------------------------------------------------
# Block 24-A: Pattern 3 — strong biomarker selection + EXCEEDS_MCID
# ---------------------------------------------------------------------------

class TestOverlapPattern3BiomarkerMCID:

    def test_validated_biomarker_plus_exceeds_mcid_detected(self):
        adj = POSAdjusters(
            biomarker_selection=BiomarkerSelectionStrength.VALIDATED,
            moa_exception_flags=[],
        )
        feat = TrialDesignFeatureSet(
            clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
        )
        report = check_pos_layer_overlap(adj, feat)
        assert not report.is_clean()
        assert any("EXCEEDS_MCID" in s or "exceeds_mcid" in s.lower() for s in report.overlapping_signals)

    def test_strong_rationale_plus_exceeds_mcid_detected(self):
        adj = POSAdjusters(
            biomarker_selection=BiomarkerSelectionStrength.STRONG_RATIONALE,
            moa_exception_flags=[],
        )
        feat = TrialDesignFeatureSet(
            clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
        )
        report = check_pos_layer_overlap(adj, feat)
        assert not report.is_clean()

    def test_validated_biomarker_plus_meets_mcid_no_overlap(self):
        """MEETS_MCID does not trigger Pattern 3 — only EXCEEDS_MCID does."""
        adj = POSAdjusters(
            biomarker_selection=BiomarkerSelectionStrength.VALIDATED,
            moa_exception_flags=[],
        )
        feat = TrialDesignFeatureSet(
            clinical_effect_magnitude=ClinicalEffectMagnitude.MEETS_MCID,
        )
        report = check_pos_layer_overlap(adj, feat)
        # Pattern 3 should NOT fire for MEETS_MCID
        assert not any(
            ("biomarker" in s.lower() and "mcid" in s.lower())
            for s in report.overlapping_signals
        )

    def test_no_biomarker_plus_exceeds_mcid_no_overlap(self):
        """EXCEEDS_MCID alone (no strong biomarker) does not trigger Pattern 3."""
        adj = POSAdjusters(
            biomarker_selection=BiomarkerSelectionStrength.NO_SELECTION,
            moa_exception_flags=[],
        )
        feat = TrialDesignFeatureSet(
            clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
        )
        report = check_pos_layer_overlap(adj, feat)
        # Pattern 3 should not fire
        assert all(
            not ("biomarker" in s.lower() and "mcid" in s.lower())
            for s in report.overlapping_signals
        )

    def test_pattern3_double_count_is_015(self):
        adj = POSAdjusters(
            biomarker_selection=BiomarkerSelectionStrength.VALIDATED,
            moa_exception_flags=[],
        )
        feat = TrialDesignFeatureSet(
            clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
        )
        report = check_pos_layer_overlap(adj, feat)
        assert report.estimated_double_count_logodds >= 0.15 - 1e-6

    def test_pattern3_has_recommendation(self):
        adj = POSAdjusters(
            biomarker_selection=BiomarkerSelectionStrength.VALIDATED,
            moa_exception_flags=[],
        )
        feat = TrialDesignFeatureSet(
            clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
        )
        report = check_pos_layer_overlap(adj, feat)
        assert len(report.recommendations) >= 1


# ---------------------------------------------------------------------------
# Block 24-B: Pattern 4 — MoA exception flag + EXCEEDS_MCID
# ---------------------------------------------------------------------------

class TestOverlapPattern4MoAExceptionMCID:

    def test_strong_biomarker_response_plus_exceeds_mcid_detected(self):
        adj = POSAdjusters(
            moa_exception_flags=[MoAExceptionFlag.STRONG_BIOMARKER_RESPONSE],
            biomarker_selection=BiomarkerSelectionStrength.NO_SELECTION,
        )
        feat = TrialDesignFeatureSet(
            clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
        )
        report = check_pos_layer_overlap(adj, feat)
        assert not report.is_clean()
        assert any(
            "strong_biomarker_response" in s.lower() or "exceeds_mcid" in s.lower()
            for s in report.overlapping_signals
        )

    def test_human_pom_plus_exceeds_mcid_detected(self):
        adj = POSAdjusters(
            moa_exception_flags=[MoAExceptionFlag.HUMAN_PROOF_OF_MECHANISM],
            biomarker_selection=BiomarkerSelectionStrength.NO_SELECTION,
        )
        feat = TrialDesignFeatureSet(
            clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
        )
        report = check_pos_layer_overlap(adj, feat)
        assert not report.is_clean()

    def test_strong_biomarker_response_plus_meets_mcid_no_overlap(self):
        """Pattern 4 only fires for EXCEEDS_MCID, not MEETS_MCID."""
        adj = POSAdjusters(
            moa_exception_flags=[MoAExceptionFlag.STRONG_BIOMARKER_RESPONSE],
            biomarker_selection=BiomarkerSelectionStrength.NO_SELECTION,
        )
        feat = TrialDesignFeatureSet(
            clinical_effect_magnitude=ClinicalEffectMagnitude.MEETS_MCID,
        )
        report = check_pos_layer_overlap(adj, feat)
        # Pattern 4 should NOT fire for MEETS_MCID
        assert all(
            not ("proof_of_mechanism" in s.lower() or
                 ("biomarker_response" in s.lower() and "mcid" in s.lower()))
            for s in report.overlapping_signals
        )

    def test_pattern4_double_count_is_010(self):
        adj = POSAdjusters(
            moa_exception_flags=[MoAExceptionFlag.STRONG_BIOMARKER_RESPONSE],
            biomarker_selection=BiomarkerSelectionStrength.NO_SELECTION,
        )
        feat = TrialDesignFeatureSet(
            clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
        )
        report = check_pos_layer_overlap(adj, feat)
        # Pattern 4 adds 0.10; we check that at least 0.10 is accounted for
        assert report.estimated_double_count_logodds >= 0.10 - 1e-6


# ---------------------------------------------------------------------------
# Block 24-C: Pattern 5 — intra-Layer-1: HUMAN_PROOF_OF_MECHANISM + CLINICALLY_VALIDATED_TARGET
# ---------------------------------------------------------------------------

class TestOverlapPattern5IntraLayer1HumanPOM:

    def test_human_pom_plus_clinically_validated_target_detected(self):
        adj = POSAdjusters(
            moa_precedent=MoAPrecedent.CLINICALLY_VALIDATED_TARGET,
            moa_exception_flags=[MoAExceptionFlag.HUMAN_PROOF_OF_MECHANISM],
            biomarker_selection=BiomarkerSelectionStrength.NO_SELECTION,
        )
        report = check_pos_layer_overlap(adj, _clean_features())
        assert not report.is_clean()
        assert any(
            "human_proof_of_mechanism" in s.lower() or "clinically_validated_target" in s.lower()
            for s in report.overlapping_signals
        )

    def test_human_pom_plus_validated_class_no_overlap(self):
        """VALIDATED_CLASS (= VALIDATED) with HUMAN_POM does NOT trigger Pattern 5."""
        adj = POSAdjusters(
            moa_precedent=MoAPrecedent.VALIDATED_CLASS,
            moa_exception_flags=[MoAExceptionFlag.HUMAN_PROOF_OF_MECHANISM],
            biomarker_selection=BiomarkerSelectionStrength.NO_SELECTION,
        )
        report = check_pos_layer_overlap(adj, _clean_features())
        # Pattern 5 specifically targets CLINICALLY_VALIDATED_TARGET, not VALIDATED_CLASS
        assert all(
            not ("human_proof_of_mechanism" in s.lower() and "validated_class" in s.lower())
            for s in report.overlapping_signals
        )

    def test_human_pom_alone_no_overlap(self):
        adj = POSAdjusters(
            moa_precedent=MoAPrecedent.PARTIAL,
            moa_exception_flags=[MoAExceptionFlag.HUMAN_PROOF_OF_MECHANISM],
            biomarker_selection=BiomarkerSelectionStrength.NO_SELECTION,
        )
        report = check_pos_layer_overlap(adj, _clean_features())
        # No Pattern 5 overlap — HUMAN_POM alone is fine
        assert not any(
            "clinically_validated_target" in s.lower()
            for s in report.overlapping_signals
        )

    def test_clinically_validated_target_alone_no_overlap(self):
        adj = POSAdjusters(
            moa_precedent=MoAPrecedent.CLINICALLY_VALIDATED_TARGET,
            moa_exception_flags=[],
            biomarker_selection=BiomarkerSelectionStrength.NO_SELECTION,
        )
        report = check_pos_layer_overlap(adj, _clean_features())
        # No Pattern 5 overlap — CLINICALLY_VALIDATED_TARGET alone is fine
        assert all(
            not ("human_proof_of_mechanism" in s.lower())
            for s in report.overlapping_signals
        )

    def test_pattern5_double_count_is_015(self):
        adj = POSAdjusters(
            moa_precedent=MoAPrecedent.CLINICALLY_VALIDATED_TARGET,
            moa_exception_flags=[MoAExceptionFlag.HUMAN_PROOF_OF_MECHANISM],
            biomarker_selection=BiomarkerSelectionStrength.NO_SELECTION,
        )
        report = check_pos_layer_overlap(adj, _clean_features())
        assert report.estimated_double_count_logodds >= 0.15 - 1e-6

    def test_pattern5_has_recommendation(self):
        adj = POSAdjusters(
            moa_precedent=MoAPrecedent.CLINICALLY_VALIDATED_TARGET,
            moa_exception_flags=[MoAExceptionFlag.HUMAN_PROOF_OF_MECHANISM],
            biomarker_selection=BiomarkerSelectionStrength.NO_SELECTION,
        )
        report = check_pos_layer_overlap(adj, _clean_features())
        assert len(report.recommendations) >= 1
        assert any("human_proof_of_mechanism" in r.lower() or "clinically_validated" in r.lower()
                   for r in report.recommendations)

    def test_estimated_double_count_accumulated_correctly(self):
        """When multiple patterns fire simultaneously, double_count is cumulative."""
        adj = POSAdjusters(
            moa_precedent=MoAPrecedent.CLINICALLY_VALIDATED_TARGET,
            moa_exception_flags=[MoAExceptionFlag.HUMAN_PROOF_OF_MECHANISM],
            biomarker_selection=BiomarkerSelectionStrength.VALIDATED,
        )
        feat = TrialDesignFeatureSet(
            clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID,
        )
        report = check_pos_layer_overlap(adj, feat)
        # Pattern 3 (0.15) + Pattern 4 (0.10) + Pattern 5 (0.15) = 0.40
        # (Pattern 2 may also fire: STRONG_BIOMARKER_RESPONSE not set, so no)
        assert report.estimated_double_count_logodds >= 0.25 - 1e-6


# ---------------------------------------------------------------------------
# Block 24-D: ClinicalEffectMagnitude enum
# ---------------------------------------------------------------------------

class TestClinicalEffectMagnitudeEnum:

    def test_exceeds_mcid_value(self):
        assert ClinicalEffectMagnitude.EXCEEDS_MCID.value == "exceeds_mcid"

    def test_meets_mcid_value(self):
        assert ClinicalEffectMagnitude.MEETS_MCID.value == "meets_mcid"

    def test_below_mcid_value(self):
        assert ClinicalEffectMagnitude.BELOW_MCID.value == "below_mcid"

    def test_unknown_value(self):
        assert ClinicalEffectMagnitude.UNKNOWN.value == "unknown"

    def test_default_is_unknown(self):
        """Default TrialDesignFeatureSet uses UNKNOWN (zero adjustment)."""
        feat = TrialDesignFeatureSet()
        assert feat.clinical_effect_magnitude == ClinicalEffectMagnitude.UNKNOWN

    def test_exceeds_mcid_positive_logodds(self):
        """EXCEEDS_MCID should produce a positive POS adjustment."""
        from bve.models.trial_design_features import compute_design_adjusted_pos
        feat_with = TrialDesignFeatureSet(clinical_effect_magnitude=ClinicalEffectMagnitude.EXCEEDS_MCID)
        feat_ref  = TrialDesignFeatureSet()  # UNKNOWN = reference
        res_with  = compute_design_adjusted_pos(0.50, feat_with, phase="phase_3")
        res_ref   = compute_design_adjusted_pos(0.50, feat_ref,  phase="phase_3")
        assert res_with.adjusted_pos > res_ref.adjusted_pos

    def test_below_mcid_negative_logodds(self):
        """BELOW_MCID should produce a lower POS than UNKNOWN reference."""
        from bve.models.trial_design_features import compute_design_adjusted_pos
        feat_below = TrialDesignFeatureSet(clinical_effect_magnitude=ClinicalEffectMagnitude.BELOW_MCID)
        feat_ref   = TrialDesignFeatureSet()
        res_below  = compute_design_adjusted_pos(0.50, feat_below, phase="phase_3")
        res_ref    = compute_design_adjusted_pos(0.50, feat_ref,   phase="phase_3")
        assert res_below.adjusted_pos < res_ref.adjusted_pos

    def test_unknown_is_reference_zero(self):
        """UNKNOWN produces exactly the same POS as the baseline (zero contribution)."""
        from bve.models.trial_design_features import compute_design_adjusted_pos
        feat_unknown = TrialDesignFeatureSet(clinical_effect_magnitude=ClinicalEffectMagnitude.UNKNOWN)
        feat_default = TrialDesignFeatureSet()
        res_unknown  = compute_design_adjusted_pos(0.50, feat_unknown, phase="phase_3")
        res_default  = compute_design_adjusted_pos(0.50, feat_default, phase="phase_3")
        assert res_unknown.adjusted_pos == pytest.approx(res_default.adjusted_pos, abs=1e-9)


# ---------------------------------------------------------------------------
# Block 24-E: Backward compatibility — existing patterns 1 and 2 still work
# ---------------------------------------------------------------------------

class TestOverlapBackwardCompat:

    def test_existing_pattern1_surrogate_endpoint_plus_novel_pathway_detected(self):
        """Pattern 1 (Block 19) still fires: surrogate endpoint + ACCELERATED_NOVEL_SURROGATE."""
        from bve.entities.trial import EndpointType
        adj = POSAdjusters(
            endpoint_type=EndpointType.SURROGATE_NOVEL,
            moa_exception_flags=[],
            biomarker_selection=BiomarkerSelectionStrength.NO_SELECTION,
        )
        feat = TrialDesignFeatureSet(
            regulatory_pathway_risk=RegulatoryPathwayRisk.ACCELERATED_NOVEL_SURROGATE,
        )
        report = check_pos_layer_overlap(adj, feat)
        assert not report.is_clean()
        assert report.has_critical_overlap

    def test_existing_pattern2_biomarker_double_count_detected(self):
        """Pattern 2 (Block 19) still fires: STRONG_BIOMARKER_RESPONSE + VALIDATED biomarker."""
        adj = POSAdjusters(
            moa_exception_flags=[MoAExceptionFlag.STRONG_BIOMARKER_RESPONSE],
            biomarker_selection=BiomarkerSelectionStrength.VALIDATED,
        )
        feat = _clean_features()
        report = check_pos_layer_overlap(adj, feat)
        assert not report.is_clean()

    def test_clean_inputs_no_regression(self):
        """All-default inputs produce a clean report (backward compat)."""
        report = check_pos_layer_overlap(_clean_adjusters(), _clean_features())
        assert report.is_clean()
        assert report.estimated_double_count_logodds == 0.0
        assert report.overlapping_signals == []

    def test_allow_overlap_still_bypasses(self):
        """allow_overlap=True returns clean report regardless of signals."""
        adj = POSAdjusters(
            moa_precedent=MoAPrecedent.CLINICALLY_VALIDATED_TARGET,
            moa_exception_flags=[MoAExceptionFlag.HUMAN_PROOF_OF_MECHANISM],
            biomarker_selection=BiomarkerSelectionStrength.NO_SELECTION,
        )
        report = check_pos_layer_overlap(adj, _clean_features(), allow_overlap=True)
        assert report.is_clean()

    def test_existing_output_fields_all_present(self):
        """LayerOverlapReport still has all original fields."""
        report = check_pos_layer_overlap(_clean_adjusters(), _clean_features())
        assert hasattr(report, "overlapping_signals")
        assert hasattr(report, "recommendations")
        assert hasattr(report, "has_critical_overlap")
        assert hasattr(report, "estimated_double_count_logodds")
        assert hasattr(report, "is_clean")
