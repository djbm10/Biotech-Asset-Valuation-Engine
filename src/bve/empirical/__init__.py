"""
Empirical POS foundation — real clinical trial outcome data and derived models.

Public API
----------
POSOutcomeRecord    — validated data model for one phase-transition outcome
load_outcome_records — load + validate records from a CSV
SponsorTrackRecord  — aggregated sponsor success history
build_sponsor_tracks — compute sponsor-level records from a list of outcomes
BaseRateTable       — stratified empirical base rates with Laplace smoothing
EmpiricalPOSEngine  — drop-in replacement for heuristic compute_pos(), backed by
                      real data; use compute_pos_with_adjusters() to apply
                      heuristic log-odds adjusters on top of empirical base rates

Sprint 8 additions
------------------
OverlayArtifact     — fitted logistic regression overlay (interpretable coefficients)
fit_overlay         — fit overlay from records + BaseRateTable
fit_overlay_time_split — fit with temporal train/test split
FEATURE_NAMES       — ordered list of 11 binary feature names
build_feature_vector — extract feature vector from POSOutcomeRecord
build_feature_vector_from_adjusters — extract feature vector from POSAdjusters
record_to_adjusters  — convert POSOutcomeRecord to POSAdjusters for heuristic eval
feature_coverage    — fraction of records with each feature set
sparsity_report     — dataset sparsity summary
FittedOverlayContribution — provenance for fitted overlay step
ModeEvalResult      — per-mode evaluation metrics
POSModeComparison   — cross-mode comparison result
compare_all_modes   — compare heuristic / base / heuristic+emp / fitted modes

Sprint 7 additions
------------------
CoverageReport      — dataset coverage and sparsity summary
build_coverage_report — construct a CoverageReport from records + BaseRateTable
POSProvenance       — full decomposition of one empirical POS prediction
LookupProvenance    — which stratification cell was matched and its contents
CalibrationArtifact — Platt/isotonic calibration artifact (fit, apply, serialize)
fit_calibration     — fit a CalibrationArtifact from predictions + outcomes
fit_calibration_time_split — fit with train/test time split
POSMode             — enum controlling which POS layer ValuationEngine uses
compare_pos_modes   — side-by-side heuristic vs empirical comparison
HeuristicVsEmpiricalComparison — result of compare_pos_modes()
"""
from bve.empirical.pos_outcome import (
    POSOutcomeRecord,
    SponsorTrackRecord,
    build_sponsor_tracks,
    load_outcome_records,
)
from bve.empirical.base_rate_table import BaseRateTable
from bve.empirical.engine import EmpiricalPOSEngine
from bve.empirical.coverage import CoverageReport, build_coverage_report
from bve.empirical.provenance import LookupProvenance, POSProvenance
from bve.empirical.calibration import (
    CalibrationArtifact,
    fit_calibration,
    fit_calibration_time_split,
)
from bve.empirical.pos_mode import (
    POSMode,
    HeuristicVsEmpiricalComparison,
    compare_pos_modes,
)
from bve.empirical.features import (
    EXPECTED_SIGNS,
    FEATURE_NAMES,
    build_feature_vector,
    build_feature_vector_from_adjusters,
    record_to_adjusters,
    feature_coverage,
    sparsity_report,
)
from bve.empirical.overlay_model import (
    AlphaSweepEntry,
    OverlayArtifact,
    fit_overlay,
    fit_overlay_time_split,
    sweep_alpha,
)
from bve.empirical.overlay_gates import (
    PromotionGateResult,
    check_promotion_gates,
    promotion_summary,
)
from bve.empirical.comparison import (
    ModeEvalResult,
    POSModeComparison,
    compare_all_modes,
)
from bve.empirical.provenance import FittedOverlayContribution

__all__ = [
    # Sprint 6
    "POSOutcomeRecord",
    "SponsorTrackRecord",
    "build_sponsor_tracks",
    "load_outcome_records",
    "BaseRateTable",
    "EmpiricalPOSEngine",
    # Sprint 7 — coverage
    "CoverageReport",
    "build_coverage_report",
    # Sprint 7 — provenance
    "LookupProvenance",
    "POSProvenance",
    # Sprint 7 — calibration
    "CalibrationArtifact",
    "fit_calibration",
    "fit_calibration_time_split",
    # Sprint 7 — mode routing
    "POSMode",
    "HeuristicVsEmpiricalComparison",
    "compare_pos_modes",
    # Sprint 8 — feature engineering
    "EXPECTED_SIGNS",
    "FEATURE_NAMES",
    "build_feature_vector",
    "build_feature_vector_from_adjusters",
    "record_to_adjusters",
    "feature_coverage",
    "sparsity_report",
    # Sprint 8 — fitted overlay
    "AlphaSweepEntry",
    "OverlayArtifact",
    "fit_overlay",
    "fit_overlay_time_split",
    "sweep_alpha",
    # Sprint 9 — hardening
    "PromotionGateResult",
    "check_promotion_gates",
    "promotion_summary",
    # Sprint 8 — comparison
    "ModeEvalResult",
    "POSModeComparison",
    "compare_all_modes",
    # Sprint 8 — provenance
    "FittedOverlayContribution",
]
