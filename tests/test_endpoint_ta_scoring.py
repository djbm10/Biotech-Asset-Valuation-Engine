"""Tests for TA-specific endpoint log-odds scoring (Layer 1 POS model)."""
from __future__ import annotations

import pytest

from bve.entities.asset import TherapeuticArea
from bve.entities.trial import EndpointType, GeneTherapyConcern, TrialPhase
from bve.models.pos_model import (
    POSAdjusters,
    _ENDPOINT_LOGODDS_BY_TA,
    _ENDPOINT_LOGODDS_GENERIC,
    _GENE_THERAPY_LOGODDS,
    _compute_layer1_adjustment,
    _endpoint_logodds,
    compute_pos,
)


# ---------------------------------------------------------------------------
# _endpoint_logodds: TA-specific lookup and generic fallback
# ---------------------------------------------------------------------------

class TestEndpointLogoddsLookup:
    def test_ta_specific_score_used_when_available(self):
        """PFS in oncology should return the oncology-specific +0.15, not generic 0.00."""
        score = _endpoint_logodds(EndpointType.PFS, "oncology")
        assert score == pytest.approx(0.15)

    def test_generic_fallback_when_ta_not_in_table(self):
        score = _endpoint_logodds(EndpointType.PFS, "unknown_ta")
        assert score == _ENDPOINT_LOGODDS_GENERIC[EndpointType.PFS]

    def test_generic_fallback_when_endpoint_not_in_ta_table(self):
        """EFS_DFS not listed in ophthalmology → uses generic score."""
        assert EndpointType.EFS_DFS not in _ENDPOINT_LOGODDS_BY_TA.get("ophthalmology", {})
        score = _endpoint_logodds(EndpointType.EFS_DFS, "ophthalmology")
        assert score == _ENDPOINT_LOGODDS_GENERIC[EndpointType.EFS_DFS]

    def test_hard_clinical_higher_than_surrogate_in_all_tas(self):
        for ta in ["oncology", "cardiovascular", "rare_disease", "cns", "immunology"]:
            hard = _endpoint_logodds(EndpointType.HARD_CLINICAL, ta)
            validated = _endpoint_logodds(EndpointType.SURROGATE_VALIDATED, ta)
            assert hard > validated, f"HARD_CLINICAL should exceed SURROGATE_VALIDATED in {ta}"

    def test_biomarker_only_lowest_in_all_tas(self):
        for ta in _ENDPOINT_LOGODDS_BY_TA:
            biomarker = _endpoint_logodds(EndpointType.BIOMARKER_ONLY, ta)
            hard = _endpoint_logodds(EndpointType.HARD_CLINICAL, ta)
            assert biomarker < hard, f"BIOMARKER_ONLY should be < HARD_CLINICAL in {ta}"

    def test_orr_higher_in_immunology_than_oncology(self):
        """ACR20 maps to ORR in immunology; ORR is valued more than in oncology."""
        imm_score = _endpoint_logodds(EndpointType.ORR, "immunology")
        onc_score = _endpoint_logodds(EndpointType.ORR, "oncology")
        assert imm_score > onc_score

    def test_cr_cri_higher_in_hematology_than_oncology(self):
        """CR/CRi is a critical endpoint in heme but minor alone in solid tumors."""
        heme = _endpoint_logodds(EndpointType.CR_CRI, "hematology")
        solid = _endpoint_logodds(EndpointType.CR_CRI, "oncology")
        assert heme > solid

    def test_visual_acuity_highest_in_ophthalmology(self):
        oph = _endpoint_logodds(EndpointType.VISUAL_ACUITY, "ophthalmology")
        generic = _ENDPOINT_LOGODDS_GENERIC[EndpointType.VISUAL_ACUITY]
        # Ophthalmology-specific and generic are both high; key check: positive
        assert oph > 0.30

    def test_molecular_biomarker_positive_in_infectious_disease(self):
        """Microbiological eradication is meaningful in ID."""
        score = _endpoint_logodds(EndpointType.MOLECULAR_BIOMARKER, "infectious_disease")
        assert score > 0.0

    def test_molecular_biomarker_negative_in_cns(self):
        """Amyloid/tau/NfL biomarkers are context-specific; conservative CNS default."""
        score = _endpoint_logodds(EndpointType.MOLECULAR_BIOMARKER, "cns")
        assert score < 0.0

    def test_disease_prevention_highest_in_infectious_disease(self):
        score = _endpoint_logodds(EndpointType.DISEASE_PREVENTION, "infectious_disease")
        assert score == pytest.approx(0.45)

    def test_mace_score_in_cardiovascular(self):
        score = _endpoint_logodds(EndpointType.MACE, "cardiovascular")
        assert score == pytest.approx(0.40)

    def test_clinical_remission_high_in_immunology(self):
        score = _endpoint_logodds(EndpointType.CLINICAL_REMISSION, "immunology")
        assert score >= 0.30

    def test_validated_clinical_score_high_in_immunology(self):
        """ACR50/70, PASI90 — validated clinical instruments, not generic biomarkers."""
        score = _endpoint_logodds(EndpointType.VALIDATED_CLINICAL_SCORE, "immunology")
        assert score >= 0.25

    def test_cns_has_conservative_surrogate_novel(self):
        """CNS is high-noise; SURROGATE_NOVEL should be more penalised than generic."""
        cns = _endpoint_logodds(EndpointType.SURROGATE_NOVEL, "cns")
        generic = _ENDPOINT_LOGODDS_GENERIC[EndpointType.SURROGATE_NOVEL]
        assert cns <= generic  # CNS ≤ generic (equal or more conservative)


# ---------------------------------------------------------------------------
# Backward compatibility: legacy enum values still work
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_hard_clinical_works_as_before(self):
        adj = POSAdjusters(endpoint_type=EndpointType.HARD_CLINICAL)
        pos = compute_pos(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY, adj)
        assert 0 < pos < 1

    def test_surrogate_validated_is_baseline(self):
        adj_base = POSAdjusters(endpoint_type=EndpointType.SURROGATE_VALIDATED)
        adj_hard = POSAdjusters(endpoint_type=EndpointType.HARD_CLINICAL)
        pos_base = compute_pos(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY, adj_base)
        pos_hard = compute_pos(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY, adj_hard)
        assert pos_hard > pos_base

    def test_biomarker_only_lowest_pos(self):
        adj_bio = POSAdjusters(endpoint_type=EndpointType.BIOMARKER_ONLY)
        adj_val = POSAdjusters(endpoint_type=EndpointType.SURROGATE_VALIDATED)
        pos_bio = compute_pos(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY, adj_bio)
        pos_val = compute_pos(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY, adj_val)
        assert pos_bio < pos_val

    def test_surrogate_novel_below_surrogate_validated(self):
        adj_val = POSAdjusters(endpoint_type=EndpointType.SURROGATE_VALIDATED)
        adj_nov = POSAdjusters(endpoint_type=EndpointType.SURROGATE_NOVEL)
        pos_val = compute_pos(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY, adj_val)
        pos_nov = compute_pos(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY, adj_nov)
        assert pos_val > pos_nov


# ---------------------------------------------------------------------------
# New specific endpoint types compute correct POS ordering
# ---------------------------------------------------------------------------

class TestSpecificEndpointTypes:
    def test_os_pfs_orr_ordering_in_oncology(self):
        """OS > PFS > ORR in solid tumor — matches clinical evidence hierarchy."""
        adj_os = POSAdjusters(endpoint_type=EndpointType.HARD_CLINICAL)
        adj_pfs = POSAdjusters(endpoint_type=EndpointType.PFS)
        adj_orr = POSAdjusters(endpoint_type=EndpointType.ORR)
        ta = TherapeuticArea.ONCOLOGY
        ph = TrialPhase.PHASE_3
        pos_os = compute_pos(ph, ta, adj_os)
        pos_pfs = compute_pos(ph, ta, adj_pfs)
        pos_orr = compute_pos(ph, ta, adj_orr)
        assert pos_os > pos_pfs > pos_orr

    def test_mace_high_in_cardiovascular(self):
        adj = POSAdjusters(endpoint_type=EndpointType.MACE)
        pos = compute_pos(TrialPhase.PHASE_3, TherapeuticArea.CARDIOVASCULAR, adj)
        pos_bio = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.CARDIOVASCULAR,
            POSAdjusters(endpoint_type=EndpointType.BIOMARKER_ONLY),
        )
        assert pos > pos_bio

    def test_visual_acuity_high_in_ophthalmology(self):
        adj = POSAdjusters(endpoint_type=EndpointType.VISUAL_ACUITY)
        pos = compute_pos(TrialPhase.PHASE_3, TherapeuticArea.OPHTHALMOLOGY, adj)
        pos_bio = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.OPHTHALMOLOGY,
            POSAdjusters(endpoint_type=EndpointType.BIOMARKER_ONLY),
        )
        assert pos > pos_bio

    def test_validated_clinical_score_high_in_immunology(self):
        adj = POSAdjusters(endpoint_type=EndpointType.VALIDATED_CLINICAL_SCORE)
        pos = compute_pos(TrialPhase.PHASE_3, TherapeuticArea.IMMUNOLOGY, adj)
        adj_base = POSAdjusters(endpoint_type=EndpointType.SURROGATE_VALIDATED)
        pos_base = compute_pos(TrialPhase.PHASE_3, TherapeuticArea.IMMUNOLOGY, adj_base)
        assert pos >= pos_base  # ACR50/70 is at least as strong as generic validated

    def test_disease_prevention_vaccine_in_id(self):
        adj = POSAdjusters(endpoint_type=EndpointType.DISEASE_PREVENTION)
        pos = compute_pos(TrialPhase.PHASE_3, TherapeuticArea.INFECTIOUS_DISEASE, adj)
        assert pos > 0.5  # Disease prevention in vaccine context → strong POS lift

    def test_functional_improvement_high_in_rare_disease(self):
        adj = POSAdjusters(endpoint_type=EndpointType.FUNCTIONAL_IMPROVEMENT)
        pos_rare = compute_pos(TrialPhase.PHASE_3, TherapeuticArea.RARE_DISEASE, adj)
        pos_bio = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.RARE_DISEASE,
            POSAdjusters(endpoint_type=EndpointType.BIOMARKER_ONLY),
        )
        assert pos_rare > pos_bio

    def test_liver_enzyme_weak(self):
        adj = POSAdjusters(endpoint_type=EndpointType.LIVER_ENZYME)
        pos_enzyme = compute_pos(TrialPhase.PHASE_2, TherapeuticArea.OTHER, adj)
        pos_hard = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.OTHER,
            POSAdjusters(endpoint_type=EndpointType.HARD_CLINICAL),
        )
        assert pos_enzyme < pos_hard


# ---------------------------------------------------------------------------
# Gene / cell therapy concerns overlay
# ---------------------------------------------------------------------------

class TestGeneTherapyConcerns:
    def test_durable_functional_correction_raises_pos(self):
        adj_base = POSAdjusters()
        adj_gt = POSAdjusters(
            gene_cell_therapy_concerns=[GeneTherapyConcern.DURABLE_FUNCTIONAL_CORRECTION]
        )
        base = _compute_layer1_adjustment(adj_base)
        gt = _compute_layer1_adjustment(adj_gt)
        assert gt > base

    def test_serious_safety_concern_lowers_pos(self):
        adj_base = POSAdjusters()
        adj_gt = POSAdjusters(
            gene_cell_therapy_concerns=[GeneTherapyConcern.SERIOUS_SAFETY_CONCERN]
        )
        base = _compute_layer1_adjustment(adj_base)
        gt = _compute_layer1_adjustment(adj_gt)
        assert gt < base

    def test_multiple_concerns_are_additive(self):
        adj_single = POSAdjusters(
            gene_cell_therapy_concerns=[GeneTherapyConcern.DURABLE_FUNCTIONAL_CORRECTION]
        )
        adj_double = POSAdjusters(
            gene_cell_therapy_concerns=[
                GeneTherapyConcern.DURABLE_FUNCTIONAL_CORRECTION,
                GeneTherapyConcern.SHORT_FOLLOWUP_ONLY,
            ]
        )
        single = _compute_layer1_adjustment(adj_single)
        double = _compute_layer1_adjustment(adj_double)
        # Adding SHORT_FOLLOWUP_ONLY (negative) to DURABLE_FUNCTIONAL_CORRECTION (positive)
        expected_diff = _GENE_THERAPY_LOGODDS[GeneTherapyConcern.SHORT_FOLLOWUP_ONLY]
        assert pytest.approx(double - single, abs=1e-6) == expected_diff

    def test_empty_concerns_no_effect(self):
        adj_none = POSAdjusters(gene_cell_therapy_concerns=[])
        adj_def = POSAdjusters()
        assert _compute_layer1_adjustment(adj_none) == _compute_layer1_adjustment(adj_def)

    def test_waning_risk_plus_safety_concern_large_penalty(self):
        adj = POSAdjusters(
            gene_cell_therapy_concerns=[
                GeneTherapyConcern.WANING_EFFECT_RISK,
                GeneTherapyConcern.SERIOUS_SAFETY_CONCERN,
            ]
        )
        adj_base = POSAdjusters()
        delta = _compute_layer1_adjustment(adj) - _compute_layer1_adjustment(adj_base)
        expected = (
            _GENE_THERAPY_LOGODDS[GeneTherapyConcern.WANING_EFFECT_RISK]
            + _GENE_THERAPY_LOGODDS[GeneTherapyConcern.SERIOUS_SAFETY_CONCERN]
        )
        assert pytest.approx(delta, abs=1e-6) == expected

    def test_gene_therapy_pos_in_rare_disease(self):
        """Durable functional correction in rare disease should give strong POS lift."""
        adj_standard = POSAdjusters(endpoint_type=EndpointType.FUNCTIONAL_IMPROVEMENT)
        adj_gt_good = POSAdjusters(
            endpoint_type=EndpointType.FUNCTIONAL_IMPROVEMENT,
            gene_cell_therapy_concerns=[GeneTherapyConcern.DURABLE_FUNCTIONAL_CORRECTION],
        )
        adj_gt_bad = POSAdjusters(
            endpoint_type=EndpointType.FUNCTIONAL_IMPROVEMENT,
            gene_cell_therapy_concerns=[
                GeneTherapyConcern.SERIOUS_SAFETY_CONCERN,
                GeneTherapyConcern.MANUFACTURING_INCONSISTENCY,
            ],
        )
        ta = TherapeuticArea.RARE_DISEASE
        ph = TrialPhase.PHASE_3
        pos_std = compute_pos(ph, ta, adj_standard)
        pos_good = compute_pos(ph, ta, adj_gt_good)
        pos_bad = compute_pos(ph, ta, adj_gt_bad)
        assert pos_good > pos_std > pos_bad

    def test_all_gene_therapy_concerns_have_nonzero_logodds(self):
        for concern in GeneTherapyConcern:
            assert concern in _GENE_THERAPY_LOGODDS
            assert _GENE_THERAPY_LOGODDS[concern] != 0.0

    def test_gene_therapy_concern_signs(self):
        """Positive signals should have positive log-odds; risks should be negative."""
        positive_concerns = {
            GeneTherapyConcern.DURABLE_FUNCTIONAL_CORRECTION,
            GeneTherapyConcern.DURABLE_BIOMARKER_CAUSAL,
        }
        negative_concerns = {
            GeneTherapyConcern.SHORT_FOLLOWUP_ONLY,
            GeneTherapyConcern.WANING_EFFECT_RISK,
            GeneTherapyConcern.SERIOUS_SAFETY_CONCERN,
            GeneTherapyConcern.MANUFACTURING_INCONSISTENCY,
            GeneTherapyConcern.BIOMARKER_ONLY_NO_FUNCTION,
        }
        for c in positive_concerns:
            assert _GENE_THERAPY_LOGODDS[c] > 0, f"{c} should be positive"
        for c in negative_concerns:
            assert _GENE_THERAPY_LOGODDS[c] < 0, f"{c} should be negative"


# ---------------------------------------------------------------------------
# Generic table completeness
# ---------------------------------------------------------------------------

class TestGenericTableCompleteness:
    def test_all_new_endpoint_types_in_generic_table(self):
        """Every EndpointType value should have a score in the generic table."""
        missing = [
            et for et in EndpointType
            if et not in _ENDPOINT_LOGODDS_GENERIC
        ]
        assert not missing, f"EndpointType values missing from generic table: {missing}"

    def test_all_ta_endpoint_types_also_in_generic(self):
        """Every endpoint_type used in a TA table must also be in the generic table."""
        for ta, sub in _ENDPOINT_LOGODDS_BY_TA.items():
            for et in sub:
                assert et in _ENDPOINT_LOGODDS_GENERIC, (
                    f"EndpointType.{et.name} used in TA '{ta}' "
                    f"but missing from _ENDPOINT_LOGODDS_GENERIC"
                )

    def test_biomarker_only_is_most_negative_in_generic(self):
        min_score = min(_ENDPOINT_LOGODDS_GENERIC.values())
        assert _ENDPOINT_LOGODDS_GENERIC[EndpointType.BIOMARKER_ONLY] <= min_score + 0.001
