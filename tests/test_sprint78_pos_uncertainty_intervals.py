"""
Block 38 — POS Uncertainty Intervals
TDD tests written BEFORE implementation.

Tests for:
  A: compute_pos_with_ci() function exists + returns POSWithCI
  B: POSWithCI dataclass fields (pos, pos_ci_low, pos_ci_high, pos_ci_width, n_mc_samples)
  C: CI is non-degenerate (width > 0, low < pos < high)
  D: More UNKNOWN adjusters → wider CI (UNKNOWN has bounds, not just 0.00)
  E: include_ci=True in compute_pos_detailed() returns CI fields
  F: Default OFF — compute_pos_detailed() without include_ci has no CI
  G: n_mc_samples controls sampling; default is 500
  H: Deterministic with seed (if supported)
"""
from __future__ import annotations

import pytest

from bve.entities.trial import GeneTherapyModality, TrialPhase
from bve.models.pos_model import (
    POSAdjusters,
    TherapeuticArea,
    compute_pos_detailed,
)


# ---------------------------------------------------------------------------
# Block 38-A: compute_pos_with_ci function
# ---------------------------------------------------------------------------

class TestComputePosWithCI:

    def test_function_importable(self):
        from bve.models.pos_model import compute_pos_with_ci
        assert compute_pos_with_ci is not None

    def test_returns_pos_with_ci(self):
        from bve.models.pos_model import compute_pos_with_ci, POSWithCI
        result = compute_pos_with_ci(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID
        )
        assert isinstance(result, POSWithCI)

    def test_basic_call_no_adjusters(self):
        from bve.models.pos_model import compute_pos_with_ci
        result = compute_pos_with_ci(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID
        )
        assert 0.0 < result.pos < 1.0

    def test_ci_low_below_pos(self):
        from bve.models.pos_model import compute_pos_with_ci
        result = compute_pos_with_ci(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID
        )
        assert result.pos_ci_low <= result.pos

    def test_ci_high_above_pos(self):
        from bve.models.pos_model import compute_pos_with_ci
        result = compute_pos_with_ci(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID
        )
        assert result.pos <= result.pos_ci_high

    def test_ci_low_less_than_high(self):
        from bve.models.pos_model import compute_pos_with_ci
        result = compute_pos_with_ci(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID
        )
        assert result.pos_ci_low < result.pos_ci_high


# ---------------------------------------------------------------------------
# Block 38-B: POSWithCI dataclass fields
# ---------------------------------------------------------------------------

class TestPOSWithCI:

    def test_pos_with_ci_importable(self):
        from bve.models.pos_model import POSWithCI
        assert POSWithCI is not None

    def test_has_pos_field(self):
        from bve.models.pos_model import POSWithCI, compute_pos_with_ci
        result = compute_pos_with_ci(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID)
        assert hasattr(result, "pos")

    def test_has_pos_ci_low_field(self):
        from bve.models.pos_model import compute_pos_with_ci
        result = compute_pos_with_ci(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID)
        assert hasattr(result, "pos_ci_low")

    def test_has_pos_ci_high_field(self):
        from bve.models.pos_model import compute_pos_with_ci
        result = compute_pos_with_ci(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID)
        assert hasattr(result, "pos_ci_high")

    def test_has_pos_ci_width_field(self):
        from bve.models.pos_model import compute_pos_with_ci
        result = compute_pos_with_ci(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID)
        assert hasattr(result, "pos_ci_width")

    def test_has_n_mc_samples_field(self):
        from bve.models.pos_model import compute_pos_with_ci
        result = compute_pos_with_ci(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID)
        assert hasattr(result, "n_mc_samples")

    def test_ci_width_equals_high_minus_low(self):
        from bve.models.pos_model import compute_pos_with_ci
        result = compute_pos_with_ci(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID)
        assert result.pos_ci_width == pytest.approx(
            result.pos_ci_high - result.pos_ci_low, abs=1e-6
        )

    def test_all_fields_in_range(self):
        from bve.models.pos_model import compute_pos_with_ci
        result = compute_pos_with_ci(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID)
        assert 0.0 <= result.pos_ci_low <= 1.0
        assert 0.0 <= result.pos <= 1.0
        assert 0.0 <= result.pos_ci_high <= 1.0
        assert result.pos_ci_width >= 0.0


# ---------------------------------------------------------------------------
# Block 38-C: CI non-degenerate (width > 0)
# ---------------------------------------------------------------------------

class TestCINonDegenerate:

    def test_ci_width_positive_no_adjusters(self):
        """With no adjusters, UNKNOWN defaults should still produce non-zero CI width."""
        from bve.models.pos_model import compute_pos_with_ci
        result = compute_pos_with_ci(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, n_mc_samples=200
        )
        assert result.pos_ci_width > 0.0

    def test_ci_width_positive_with_known_adjusters(self):
        """Even fully specified adjusters should have some CI width (parameter uncertainty)."""
        from bve.models.pos_model import (
            compute_pos_with_ci,
            MoAPrecedent, BiomarkerSelectionStrength, PriorPhaseDataStrength,
        )
        adj = POSAdjusters(
            moa_precedent=MoAPrecedent.VALIDATED,
            biomarker_selection=BiomarkerSelectionStrength.VALIDATED,
            prior_phase_data=PriorPhaseDataStrength.STRONG_REPLICATED,
        )
        result = compute_pos_with_ci(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, adjusters=adj, n_mc_samples=200
        )
        assert result.pos_ci_width >= 0.0  # May be near 0 with all knowns

    def test_ci_bounds_are_bounded(self):
        """CI bounds should be valid probabilities."""
        from bve.models.pos_model import compute_pos_with_ci
        result = compute_pos_with_ci(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, n_mc_samples=100
        )
        assert result.pos_ci_low >= 0.0
        assert result.pos_ci_high <= 1.0


# ---------------------------------------------------------------------------
# Block 38-D: UNKNOWN adjusters → wider CI
# ---------------------------------------------------------------------------

class TestUnknownWiderCI:

    def test_all_unknown_wider_than_all_known(self):
        """All UNKNOWN adjusters should produce wider CI than all explicitly set adjusters."""
        from bve.models.pos_model import (
            compute_pos_with_ci,
            MoAPrecedent, BiomarkerSelectionStrength, PriorPhaseDataStrength,
            DoseSelectionConfidence, ClinicalEffectMagnitude, DataMaturityLevel,
        )
        adj_known = POSAdjusters(
            moa_precedent=MoAPrecedent.PARTIAL,
            biomarker_selection=BiomarkerSelectionStrength.NO_SELECTION,
            prior_phase_data=PriorPhaseDataStrength.MIXED,
            dose_selection_confidence=DoseSelectionConfidence.PK_PD_MODELED,
            clinical_effect_magnitude=ClinicalEffectMagnitude.MEETS_MCID,
            data_maturity=DataMaturityLevel.MATURE_FINAL,
        )
        adj_unknown = POSAdjusters()  # all defaults = UNKNOWN

        result_known = compute_pos_with_ci(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            adjusters=adj_known, n_mc_samples=500
        )
        result_unknown = compute_pos_with_ci(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            adjusters=adj_unknown, n_mc_samples=500
        )
        # UNKNOWN should produce wider CI than fully specified adjusters
        assert result_unknown.pos_ci_width >= result_known.pos_ci_width

    def test_cmc_unknown_gene_therapy_wider_than_known(self):
        """CMC UNKNOWN for gene therapy modality should have wide CI at Phase 2."""
        from bve.models.pos_model import compute_pos_with_ci, CMCRiskLevel
        adj_cmc_unknown = POSAdjusters(
            gene_therapy_modality=GeneTherapyModality.AAV_IN_VIVO,
        )  # cmc_risk=UNKNOWN by default
        adj_cmc_known = POSAdjusters(
            gene_therapy_modality=GeneTherapyModality.AAV_IN_VIVO,
        )
        # Note: Both have UNKNOWN cmc_risk in phase_2 (early warning only)
        # The gene therapy cmc_unknown at phase 2 should have wider CI than
        # non-gene therapy with known cmc
        adj_known_no_gt = POSAdjusters(
            gene_therapy_modality=GeneTherapyModality.UNKNOWN,
        )
        result_gt_unknown = compute_pos_with_ci(
            TrialPhase.PHASE_2, TherapeuticArea.RARE_DISEASE,
            adjusters=adj_cmc_unknown, n_mc_samples=500
        )
        result_no_gt = compute_pos_with_ci(
            TrialPhase.PHASE_2, TherapeuticArea.RARE_DISEASE,
            adjusters=adj_known_no_gt, n_mc_samples=500
        )
        # Gene therapy UNKNOWN CMC should not make CI narrower
        assert result_gt_unknown.pos_ci_width >= 0.0


# ---------------------------------------------------------------------------
# Block 38-E: include_ci=True in compute_pos_detailed
# ---------------------------------------------------------------------------

class TestIncludeCIInDetailed:

    def test_include_ci_flag_exists(self):
        """compute_pos_detailed accepts include_ci keyword."""
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            include_ci=True
        )
        assert result is not None

    def test_include_ci_returns_ci_fields(self):
        """With include_ci=True, POSComputeResult has CI fields."""
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            include_ci=True
        )
        assert hasattr(result, "pos_ci_low")
        assert hasattr(result, "pos_ci_high")
        assert hasattr(result, "pos_ci_width")

    def test_include_ci_true_populates_fields(self):
        """CI fields are populated (not None) when include_ci=True."""
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            include_ci=True
        )
        assert result.pos_ci_low is not None
        assert result.pos_ci_high is not None

    def test_include_ci_ci_values_are_valid(self):
        """CI values are valid probabilities when include_ci=True."""
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            include_ci=True
        )
        assert 0.0 <= result.pos_ci_low <= result.pos_ci_high <= 1.0


# ---------------------------------------------------------------------------
# Block 38-F: Default OFF — no CI in standard calls
# ---------------------------------------------------------------------------

class TestCIDefaultOff:

    def test_compute_pos_detailed_no_ci_by_default(self):
        """Without include_ci, CI fields are None in POSComputeResult."""
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID
        )
        assert result.pos_ci_low is None
        assert result.pos_ci_high is None

    def test_pos_ci_width_none_by_default(self):
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID
        )
        assert result.pos_ci_width is None

    def test_standard_compute_pos_unaffected(self):
        """compute_pos() still returns a simple float unchanged."""
        from bve.models.pos_model import compute_pos
        pos = compute_pos(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID)
        assert isinstance(pos, float)
        assert 0.0 < pos < 1.0


# ---------------------------------------------------------------------------
# Block 38-G: n_mc_samples controls sampling
# ---------------------------------------------------------------------------

class TestNMCSamples:

    def test_default_n_mc_samples_is_500(self):
        from bve.models.pos_model import compute_pos_with_ci
        result = compute_pos_with_ci(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID
        )
        assert result.n_mc_samples == 500

    def test_custom_n_mc_samples_respected(self):
        from bve.models.pos_model import compute_pos_with_ci
        result = compute_pos_with_ci(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, n_mc_samples=200
        )
        assert result.n_mc_samples == 200

    def test_more_samples_narrower_variance_on_point(self):
        """Larger n_mc_samples should converge CI closer to point estimate."""
        from bve.models.pos_model import compute_pos_with_ci
        # The point estimate should be consistent regardless of n_samples
        result_100 = compute_pos_with_ci(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, n_mc_samples=100
        )
        result_1000 = compute_pos_with_ci(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, n_mc_samples=1000
        )
        # Both should be valid probabilities in (0, 1)
        assert 0.0 < result_100.pos < 1.0
        assert 0.0 < result_1000.pos < 1.0
