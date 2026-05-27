"""
Block 19 — POS Overlap + Calibration Patch
Tests for:
  1. check_pos_layer_overlap() real detection (was always-clean)
  2. Intra-Layer-1 biomarker double-count warning
  3. Reliability diagram (ReliabilityBin + build_reliability_diagram)
  4. TA-stratified calibration insufficient-data warning

TDD: tests written BEFORE implementation.
"""
from __future__ import annotations

import math
import pytest

from bve.entities.trial import EndpointType
from bve.models.pos_model import (
    BiomarkerSelectionStrength,
    MoAExceptionFlag,
    POSAdjusters,
)
from bve.models.trial_design_features import (
    ComparatorFit,
    EvidenceDesignQuality,
    LayerOverlapReport,
    RegulatoryPathwayRisk,
    TrialDesignFeatureSet,
    check_pos_layer_overlap,
)
from bve.analysis.pos_calibration import (
    MIN_N_FOR_RELIABLE_ESTIMATE,
    POSCalibrationRecord,
    TACalibrationResult,
    run_pos_calibration_from_records,
)


# ===========================================================================
# Helper builders
# ===========================================================================

def _clean_pair() -> tuple[POSAdjusters, TrialDesignFeatureSet]:
    """A combination with no overlaps."""
    adj = POSAdjusters()
    feat = TrialDesignFeatureSet()
    return adj, feat


def _make_records(ta: str, phase: str, n: int, base_pred: float = 0.45) -> list[POSCalibrationRecord]:
    """Make n calibration records alternating success/failure."""
    records = []
    for i in range(n):
        records.append(POSCalibrationRecord(
            therapeutic_area=ta,
            phase=phase,
            predicted_pos=base_pred + (i % 3) * 0.05,
            actual_success=(i % 2 == 0),
        ))
    return records


# ===========================================================================
# Block 19-A: check_pos_layer_overlap real detection
# ===========================================================================

class TestLayerOverlapRealDetection:

    def test_clean_combination_returns_clean(self):
        adj, feat = _clean_pair()
        report = check_pos_layer_overlap(adj, feat)
        assert report.is_clean()
        assert report.has_critical_overlap is False
        assert report.estimated_double_count_logodds == 0.0

    def test_surrogate_novel_plus_accelerated_novel_surrogate_detected(self):
        """SURROGATE_NOVEL endpoint + ACCELERATED_NOVEL_SURROGATE pathway = double-count."""
        adj = POSAdjusters(endpoint_type=EndpointType.SURROGATE_NOVEL)
        feat = TrialDesignFeatureSet(
            regulatory_pathway_risk=RegulatoryPathwayRisk.ACCELERATED_NOVEL_SURROGATE
        )
        report = check_pos_layer_overlap(adj, feat)
        assert not report.is_clean()
        assert report.has_critical_overlap is True
        assert report.estimated_double_count_logodds > 0.0
        assert len(report.overlapping_signals) >= 1
        assert len(report.recommendations) >= 1

    def test_biomarker_only_plus_accelerated_novel_surrogate_detected(self):
        adj = POSAdjusters(endpoint_type=EndpointType.BIOMARKER_ONLY)
        feat = TrialDesignFeatureSet(
            regulatory_pathway_risk=RegulatoryPathwayRisk.ACCELERATED_NOVEL_SURROGATE
        )
        report = check_pos_layer_overlap(adj, feat)
        assert not report.is_clean()
        assert report.has_critical_overlap is True

    def test_molecular_biomarker_plus_accelerated_novel_surrogate_detected(self):
        adj = POSAdjusters(endpoint_type=EndpointType.MOLECULAR_BIOMARKER)
        feat = TrialDesignFeatureSet(
            regulatory_pathway_risk=RegulatoryPathwayRisk.ACCELERATED_NOVEL_SURROGATE
        )
        report = check_pos_layer_overlap(adj, feat)
        assert not report.is_clean()

    def test_hard_clinical_plus_accelerated_novel_surrogate_is_clean(self):
        """Hard clinical endpoint + accelerated pathway = no surrogate overlap."""
        adj = POSAdjusters(endpoint_type=EndpointType.HARD_CLINICAL)
        feat = TrialDesignFeatureSet(
            regulatory_pathway_risk=RegulatoryPathwayRisk.ACCELERATED_NOVEL_SURROGATE
        )
        report = check_pos_layer_overlap(adj, feat)
        # No surrogate overlap; may or may not flag depending on implementation
        # Key: hard clinical is NOT a surrogate type, so no critical overlap
        assert report.has_critical_overlap is False

    def test_surrogate_novel_plus_standard_pathway_is_clean(self):
        adj = POSAdjusters(endpoint_type=EndpointType.SURROGATE_NOVEL)
        feat = TrialDesignFeatureSet(
            regulatory_pathway_risk=RegulatoryPathwayRisk.STANDARD
        )
        report = check_pos_layer_overlap(adj, feat)
        assert report.is_clean()

    def test_pfs_plus_accelerated_validated_surrogate_is_clean(self):
        """PFS + ACCELERATED_VALIDATED_SURROGATE: different risk tier, not the same concept."""
        adj = POSAdjusters(endpoint_type=EndpointType.PFS)
        feat = TrialDesignFeatureSet(
            regulatory_pathway_risk=RegulatoryPathwayRisk.ACCELERATED_VALIDATED_SURROGATE
        )
        report = check_pos_layer_overlap(adj, feat)
        # Validated surrogate pathway does not double-count with a non-novel endpoint
        assert report.has_critical_overlap is False


# ===========================================================================
# Block 19-B: intra-Layer-1 biomarker double-count
# ===========================================================================

class TestIntraLayer1BiomarkerOverlap:

    def test_strong_biomarker_response_plus_strong_rationale_detected(self):
        """MoAExceptionFlag.STRONG_BIOMARKER_RESPONSE + STRONG_RATIONALE = double-count."""
        adj = POSAdjusters(
            moa_exception_flags=[MoAExceptionFlag.STRONG_BIOMARKER_RESPONSE],
            biomarker_selection=BiomarkerSelectionStrength.STRONG_RATIONALE,
        )
        feat = TrialDesignFeatureSet()
        report = check_pos_layer_overlap(adj, feat)
        assert not report.is_clean()
        assert report.estimated_double_count_logodds > 0.0
        assert len(report.overlapping_signals) >= 1

    def test_strong_biomarker_response_plus_validated_detected(self):
        adj = POSAdjusters(
            moa_exception_flags=[MoAExceptionFlag.STRONG_BIOMARKER_RESPONSE],
            biomarker_selection=BiomarkerSelectionStrength.VALIDATED,
        )
        feat = TrialDesignFeatureSet()
        report = check_pos_layer_overlap(adj, feat)
        assert not report.is_clean()
        assert report.estimated_double_count_logodds > 0.0

    def test_strong_biomarker_response_plus_no_selection_is_clean(self):
        """STRONG_BIOMARKER_RESPONSE + NO_SELECTION: no double-count."""
        adj = POSAdjusters(
            moa_exception_flags=[MoAExceptionFlag.STRONG_BIOMARKER_RESPONSE],
            biomarker_selection=BiomarkerSelectionStrength.NO_SELECTION,
        )
        feat = TrialDesignFeatureSet()
        report = check_pos_layer_overlap(adj, feat)
        assert report.is_clean()

    def test_genetically_validated_plus_validated_biomarker_is_clean(self):
        """Different exception flag + validated biomarker: no biomarker double-count."""
        adj = POSAdjusters(
            moa_exception_flags=[MoAExceptionFlag.GENETICALLY_VALIDATED_TARGET],
            biomarker_selection=BiomarkerSelectionStrength.VALIDATED,
        )
        feat = TrialDesignFeatureSet()
        report = check_pos_layer_overlap(adj, feat)
        # This combination has no defined overlap
        assert report.is_clean()

    def test_double_count_magnitude_is_min_of_both(self):
        """Estimated double-count = min(STRONG_BIOMARKER_RESPONSE logodds, biomarker logodds)."""
        adj = POSAdjusters(
            moa_exception_flags=[MoAExceptionFlag.STRONG_BIOMARKER_RESPONSE],
            biomarker_selection=BiomarkerSelectionStrength.STRONG_RATIONALE,
        )
        feat = TrialDesignFeatureSet()
        report = check_pos_layer_overlap(adj, feat)
        # STRONG_BIOMARKER_RESPONSE = 0.10, STRONG_RATIONALE = 0.25 → min = 0.10
        assert abs(report.estimated_double_count_logodds - 0.10) < 1e-9

    def test_both_overlaps_stack(self):
        """When both overlap types present, both are reported."""
        adj = POSAdjusters(
            endpoint_type=EndpointType.SURROGATE_NOVEL,
            moa_exception_flags=[MoAExceptionFlag.STRONG_BIOMARKER_RESPONSE],
            biomarker_selection=BiomarkerSelectionStrength.STRONG_RATIONALE,
        )
        feat = TrialDesignFeatureSet(
            regulatory_pathway_risk=RegulatoryPathwayRisk.ACCELERATED_NOVEL_SURROGATE
        )
        report = check_pos_layer_overlap(adj, feat)
        assert not report.is_clean()
        assert len(report.overlapping_signals) >= 2
        assert report.estimated_double_count_logodds > 0.10  # both overlaps contribute


# ===========================================================================
# Block 19-C: Reliability diagram
# ===========================================================================

class TestReliabilityDiagram:

    def _import_reliability(self):
        from bve.analysis.pos_calibration import ReliabilityBin, build_reliability_diagram
        return ReliabilityBin, build_reliability_diagram

    def test_build_returns_list_of_reliability_bins(self):
        ReliabilityBin, build_reliability_diagram = self._import_reliability()
        records = _make_records("oncology", "phase_2", 30)
        bins = build_reliability_diagram(records, n_bins=5)
        assert isinstance(bins, list)
        assert len(bins) == 5
        for b in bins:
            assert isinstance(b, ReliabilityBin)

    def test_bin_fields_present(self):
        ReliabilityBin, build_reliability_diagram = self._import_reliability()
        records = _make_records("oncology", "phase_2", 20)
        bins = build_reliability_diagram(records, n_bins=5)
        b = bins[0]
        assert hasattr(b, "bin_label")
        assert hasattr(b, "n")
        assert hasattr(b, "n_success")
        assert hasattr(b, "predicted_mean")
        assert hasattr(b, "actual_rate")
        assert hasattr(b, "calibration_error")

    def test_empty_bins_have_nan_rate(self):
        ReliabilityBin, build_reliability_diagram = self._import_reliability()
        # All records in a narrow range → some bins empty
        records = [POSCalibrationRecord(
            therapeutic_area="oncology", phase="phase_2",
            predicted_pos=0.42, actual_success=True,
        ) for _ in range(10)]
        bins = build_reliability_diagram(records, n_bins=10)
        empty_bins = [b for b in bins if b.n == 0]
        for b in empty_bins:
            assert math.isnan(b.actual_rate)

    def test_n_across_bins_sums_to_total(self):
        ReliabilityBin, build_reliability_diagram = self._import_reliability()
        records = _make_records("oncology", "phase_2", 50)
        bins = build_reliability_diagram(records, n_bins=5)
        assert sum(b.n for b in bins) == 50

    def test_n_success_is_correct(self):
        ReliabilityBin, build_reliability_diagram = self._import_reliability()
        # All succeed
        records = [POSCalibrationRecord(
            therapeutic_area="oncology", phase="phase_2",
            predicted_pos=0.5, actual_success=True,
        ) for _ in range(10)]
        bins = build_reliability_diagram(records, n_bins=5)
        total_success = sum(b.n_success for b in bins)
        assert total_success == 10

    def test_calibration_error_is_actual_minus_predicted(self):
        ReliabilityBin, build_reliability_diagram = self._import_reliability()
        records = _make_records("oncology", "phase_2", 20)
        bins = build_reliability_diagram(records, n_bins=5)
        for b in bins:
            if b.n > 0 and not math.isnan(b.actual_rate):
                expected_err = b.actual_rate - b.predicted_mean
                assert abs(b.calibration_error - expected_err) < 1e-9

    def test_default_n_bins_is_five(self):
        ReliabilityBin, build_reliability_diagram = self._import_reliability()
        records = _make_records("oncology", "phase_2", 20)
        bins = build_reliability_diagram(records)
        assert len(bins) == 5


# ===========================================================================
# Block 19-D: TA-stratified calibration — insufficient-data warning
# ===========================================================================

class TestTACalibrationInsufficientData:

    def test_insufficient_data_warning_when_n_below_minimum(self):
        records = _make_records("cns", "phase_2", MIN_N_FOR_RELIABLE_ESTIMATE - 1)
        suite = run_pos_calibration_from_records(records)
        cns_result = next(r for r in suite.ta_results if r.therapeutic_area == "cns")
        assert cns_result.insufficient_data_warning is True
        assert cns_result.insufficient_data_message != ""

    def test_no_warning_when_n_meets_minimum(self):
        records = _make_records("oncology", "phase_2", MIN_N_FOR_RELIABLE_ESTIMATE)
        suite = run_pos_calibration_from_records(records)
        onc_result = next(r for r in suite.ta_results if r.therapeutic_area == "oncology")
        assert onc_result.insufficient_data_warning is False

    def test_insufficient_data_message_contains_n(self):
        n = MIN_N_FOR_RELIABLE_ESTIMATE - 3
        records = _make_records("cns", "phase_2", n)
        suite = run_pos_calibration_from_records(records)
        cns_result = next(r for r in suite.ta_results if r.therapeutic_area == "cns")
        assert str(n) in cns_result.insufficient_data_message

    def test_metrics_still_computed_but_flagged(self):
        """Even with insufficient data, Brier is computed for reference."""
        records = _make_records("rare_disease", "phase_2", 5)
        suite = run_pos_calibration_from_records(records)
        rare_result = next(
            (r for r in suite.ta_results if r.therapeutic_area == "rare_disease"), None
        )
        if rare_result is not None:
            assert rare_result.insufficient_data_warning is True
            assert rare_result.brier_score is not None

    def test_reliability_diagram_attached_to_ta_result(self):
        records = _make_records("oncology", "phase_2", 30)
        suite = run_pos_calibration_from_records(records)
        onc_result = next(r for r in suite.ta_results if r.therapeutic_area == "oncology")
        assert hasattr(onc_result, "reliability_diagram")
        assert isinstance(onc_result.reliability_diagram, list)

    def test_combined_suite_has_n_total(self):
        records = (
            _make_records("oncology", "phase_2", 25) +
            _make_records("cns",      "phase_2", 10)
        )
        suite = run_pos_calibration_from_records(records)
        assert suite.n_total == 35

    def test_summary_output_non_empty(self):
        records = _make_records("oncology", "phase_2", 25)
        suite = run_pos_calibration_from_records(records)
        summary = suite.summary()
        assert isinstance(summary, str)
        assert len(summary) > 0
