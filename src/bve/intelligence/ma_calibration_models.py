"""Layer 5 — Calibration, Validation, Learning, and Governance models.

All Pydantic v2 models and enums shared across Layer 5 submodules.
No business logic here — only data containers and enums.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class OutcomeType(str, Enum):
    FULL_ACQUISITION_ANNOUNCED                 = "full_acquisition_announced"
    FULL_ACQUISITION_CLOSED                    = "full_acquisition_closed"
    ASSET_ACQUISITION                          = "asset_acquisition"
    GLOBAL_LICENSE                             = "global_license"
    REGIONAL_LICENSE                           = "regional_license"
    CO_DEVELOPMENT                             = "co_development"
    CO_COMMERCIALIZATION                       = "co_commercialization"
    OPTION_TO_ACQUIRE                          = "option_to_acquire"
    OPTION_TO_LICENSE                          = "option_to_license"
    MINORITY_EQUITY_INVESTMENT                 = "minority_equity_investment"
    STRATEGIC_COLLABORATION                    = "strategic_collaboration"
    CVR_HEAVY_ACQUISITION                      = "cvr_heavy_acquisition"
    STRUCTURED_ACQUISITION_WITH_MILESTONES     = "structured_acquisition_with_milestones"
    RUMORED_PROCESS_NO_DEAL                    = "rumored_process_no_deal"
    STRATEGIC_REVIEW_NO_DEAL                   = "strategic_review_no_deal"
    REMAINED_INDEPENDENT_PERFORMED_WELL        = "remained_independent_performed_well"
    REMAINED_INDEPENDENT_FAILED                = "remained_independent_failed"
    DISTRESSED_FINANCING                       = "distressed_financing"
    BANKRUPTCY_OR_WIND_DOWN                    = "bankruptcy_or_wind_down"
    CLINICAL_FAILURE                           = "clinical_failure"
    TARGET_SIGNED_DIFFERENT_PARTNER            = "target_signed_different_partner"
    ACQUIRER_FILLED_GAP_ELSEWHERE              = "acquirer_filled_gap_elsewhere"
    FALSE_POSITIVE_NO_TRANSACTION              = "false_positive_no_transaction"
    FALSE_NEGATIVE_TRANSACTION_OCCURRED        = "false_negative_transaction_occurred"
    UNKNOWN_OR_UNRESOLVED                      = "unknown_or_unresolved"


# Outcome types that count as "full acquisition"
FULL_ACQUISITION_OUTCOME_TYPES: frozenset[OutcomeType] = frozenset({
    OutcomeType.FULL_ACQUISITION_ANNOUNCED,
    OutcomeType.FULL_ACQUISITION_CLOSED,
    OutcomeType.CVR_HEAVY_ACQUISITION,
    OutcomeType.STRUCTURED_ACQUISITION_WITH_MILESTONES,
})

# Outcome types that count as any strategic transaction
STRATEGIC_TRANSACTION_OUTCOME_TYPES: frozenset[OutcomeType] = frozenset({
    OutcomeType.FULL_ACQUISITION_ANNOUNCED,
    OutcomeType.FULL_ACQUISITION_CLOSED,
    OutcomeType.ASSET_ACQUISITION,
    OutcomeType.GLOBAL_LICENSE,
    OutcomeType.REGIONAL_LICENSE,
    OutcomeType.CO_DEVELOPMENT,
    OutcomeType.CO_COMMERCIALIZATION,
    OutcomeType.OPTION_TO_ACQUIRE,
    OutcomeType.OPTION_TO_LICENSE,
    OutcomeType.MINORITY_EQUITY_INVESTMENT,
    OutcomeType.STRATEGIC_COLLABORATION,
    OutcomeType.CVR_HEAVY_ACQUISITION,
    OutcomeType.STRUCTURED_ACQUISITION_WITH_MILESTONES,
    OutcomeType.FALSE_NEGATIVE_TRANSACTION_OCCURRED,
})

LICENSE_OR_PARTNER_OUTCOME_TYPES: frozenset[OutcomeType] = frozenset({
    OutcomeType.GLOBAL_LICENSE,
    OutcomeType.REGIONAL_LICENSE,
    OutcomeType.CO_DEVELOPMENT,
    OutcomeType.CO_COMMERCIALIZATION,
    OutcomeType.OPTION_TO_LICENSE,
    OutcomeType.STRATEGIC_COLLABORATION,
    OutcomeType.TARGET_SIGNED_DIFFERENT_PARTNER,
})

ACTIVE_PROCESS_OUTCOME_TYPES: frozenset[OutcomeType] = frozenset({
    OutcomeType.FULL_ACQUISITION_ANNOUNCED,
    OutcomeType.FULL_ACQUISITION_CLOSED,
    OutcomeType.ASSET_ACQUISITION,
    OutcomeType.RUMORED_PROCESS_NO_DEAL,
    OutcomeType.STRATEGIC_REVIEW_NO_DEAL,
    OutcomeType.CVR_HEAVY_ACQUISITION,
    OutcomeType.STRUCTURED_ACQUISITION_WITH_MILESTONES,
    OutcomeType.FALSE_NEGATIVE_TRANSACTION_OCCURRED,
})


class CalibrationMethod(str, Enum):
    PLATT_SCALING              = "platt_scaling"
    ISOTONIC_REGRESSION        = "isotonic_regression"
    BAYESIAN_BIN_CALIBRATION   = "bayesian_bin_calibration"
    SURVIVAL_HAZARD            = "survival_hazard"
    COMPETING_RISK             = "competing_risk"
    GLOBAL_BASE_RATE           = "global_base_rate"
    SEGMENT_BLEND              = "segment_blend"
    RANK_ONLY_NO_PROBABILITY   = "rank_only_no_probability"


class CalibrationQualityLabel(str, Enum):
    HIGH_CONFIDENCE                = "high_confidence"
    MEDIUM_CONFIDENCE              = "medium_confidence"
    LOW_CONFIDENCE                 = "low_confidence"
    INSUFFICIENT_DATA_RANK_ONLY    = "insufficient_data_rank_only"
    OUT_OF_DOMAIN                  = "out_of_domain"


class LayerValidated(str, Enum):
    LAYER_0    = "layer_0"
    LAYER_1    = "layer_1"
    LAYER_2    = "layer_2"
    LAYER_3    = "layer_3"
    LAYER_4    = "layer_4"
    END_TO_END = "end_to_end"


class ErrorType(str, Enum):
    FALSE_POSITIVE_ASSET_QUALITY              = "false_positive_asset_quality"
    FALSE_POSITIVE_BUYER_FIT                  = "false_positive_buyer_fit"
    FALSE_POSITIVE_TRANSACTION_MOMENTUM       = "false_positive_transaction_momentum"
    FALSE_POSITIVE_AFFORDABILITY              = "false_positive_affordability"
    FALSE_POSITIVE_RIGHTS_CONTROL             = "false_positive_rights_control"
    FALSE_POSITIVE_ANTITRUST                  = "false_positive_antitrust"
    FALSE_POSITIVE_SELLER_WILLINGNESS         = "false_positive_seller_willingness"
    FALSE_POSITIVE_MARKET_HYPE                = "false_positive_market_hype"
    FALSE_NEGATIVE_HIDDEN_BUYER               = "false_negative_hidden_buyer"
    FALSE_NEGATIVE_UNDERESTIMATED_SCARCITY    = "false_negative_underestimated_scarcity"
    FALSE_NEGATIVE_UNDERESTIMATED_DISTRESS    = "false_negative_underestimated_distress"
    FALSE_NEGATIVE_UNDERESTIMATED_BUYER_URGENCY = "false_negative_underestimated_buyer_urgency"
    FALSE_NEGATIVE_WRONG_ROUTE                = "false_negative_wrong_route"
    FALSE_NEGATIVE_WRONG_STRUCTURE            = "false_negative_wrong_structure"
    TIMING_ERROR                              = "timing_error"
    DATA_STALENESS_ERROR                      = "data_staleness_error"
    CALIBRATION_ERROR                         = "calibration_error"
    ROUTE_ERROR                               = "route_error"
    STRUCTURE_ERROR                           = "structure_error"
    THRESHOLD_ERROR                           = "threshold_error"
    UNKNOWN_ERROR                             = "unknown_error"


class DriftType(str, Enum):
    MARKET_REGIME_DRIFT          = "market_regime_drift"
    FINANCING_REGIME_DRIFT       = "financing_regime_drift"
    ANTITRUST_REGIME_DRIFT       = "antitrust_regime_drift"
    PREMIUM_REGIME_DRIFT         = "premium_regime_drift"
    ACQUIRER_APPETITE_DRIFT      = "acquirer_appetite_drift"
    DEAL_STRUCTURE_DRIFT         = "deal_structure_drift"
    CALIBRATION_DRIFT            = "calibration_drift"
    FEATURE_DISTRIBUTION_DRIFT   = "feature_distribution_drift"
    OUTCOME_BASE_RATE_DRIFT      = "outcome_base_rate_drift"


class OperatingMode(str, Enum):
    HIGH_PRECISION          = "high_precision"
    HIGH_RECALL             = "high_recall"
    BALANCED                = "balanced"
    STRATEGIC_SCARCITY      = "strategic_scarcity"
    CAPITAL_DISCIPLINE      = "capital_discipline"
    RELATIONSHIP_BUILDING   = "relationship_building"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class HistoricalTargetFeatures(BaseModel):
    model_config = ConfigDict(frozen=True)

    therapeutic_area: Optional[str] = None
    modality: Optional[str] = None
    stage: Optional[str] = None
    market_cap_bucket: Optional[str] = None
    enterprise_value: Optional[float] = None
    cash_runway_months: Optional[float] = None
    deal_type: Optional[str] = None
    distress_level: Optional[str] = None
    rights_encumbrance_level: Optional[str] = None
    asset_quality_bucket: Optional[str] = None
    strategic_scarcity_bucket: Optional[str] = None
    route_class: Optional[str] = None
    catalyst_proximity_bucket: Optional[str] = None
    public_private_status: Optional[str] = None


class HistoricalAcquirerFeatures(BaseModel):
    model_config = ConfigDict(frozen=True)

    acquirer_type: Optional[str] = None
    therapeutic_area_fit: Optional[float] = None
    modality_fit: Optional[float] = None
    pipeline_gap: Optional[float] = None
    deal_capacity_bucket: Optional[str] = None
    recent_deal_activity: Optional[str] = None
    acquirer_pull_score: Optional[float] = None
    profile_freshness_days: Optional[int] = None


class OutcomeLabels(BaseModel):
    model_config = ConfigDict(frozen=True)

    acquired_within_6m: bool = False
    acquired_within_12m: bool = False
    acquired_within_24m: bool = False
    any_strategic_transaction_12m: bool = False
    any_strategic_transaction_24m: bool = False
    license_or_partner_12m: bool = False
    license_or_partner_24m: bool = False
    active_process_observed_12m: bool = False
    remained_independent_12m: bool = False
    clinical_failure_12m: bool = False
    distressed_financing_12m: bool = False


class ProbabilityInterval(BaseModel):
    model_config = ConfigDict(frozen=True)

    lower: float = Field(ge=0.0, le=1.0)
    median: float = Field(ge=0.0, le=1.0)
    upper: float = Field(ge=0.0, le=1.0)
    confidence_level: float = Field(default=0.80, ge=0.0, le=1.0)


class HistoricalMAOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    target_id: str
    acquirer_id: Optional[str] = None
    prediction_date: date
    outcome_date: Optional[date] = None
    observation_window_months: int = 12
    as_of_date: date

    layer0_snapshot: dict = Field(default_factory=dict)
    layer1_snapshot: dict = Field(default_factory=dict)
    layer2_snapshot: dict = Field(default_factory=dict)
    layer3_snapshot: Optional[dict] = None
    layer4_snapshot: Optional[dict] = None

    target_features: HistoricalTargetFeatures = Field(
        default_factory=HistoricalTargetFeatures
    )
    acquirer_features: Optional[HistoricalAcquirerFeatures] = None

    outcome_type: OutcomeType
    deal_value: Optional[float] = None
    premium: Optional[float] = None
    consideration_mix: Optional[dict] = None
    deal_structure: Optional[str] = None
    time_to_outcome_days: Optional[int] = None
    successful_close: Optional[bool] = None
    reason_no_deal: Optional[str] = None

    labels: OutcomeLabels = Field(default_factory=OutcomeLabels)

    source_refs: list[str] = Field(default_factory=list)
    leakage_checks_passed: bool = True
    leakage_warnings: list[str] = Field(default_factory=list)
    excluded_from_training: bool = False
    exclusion_reason: Optional[str] = None


class CalibratedProbabilitySet(BaseModel):
    model_config = ConfigDict(frozen=True)

    p_full_acquisition_6m: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    p_full_acquisition_12m: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    p_full_acquisition_24m: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    p_any_strategic_transaction_12m: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    p_any_strategic_transaction_24m: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    p_partnership_or_license_12m: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    p_partnership_or_license_24m: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    p_active_process_12m: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    probability_intervals: dict[str, ProbabilityInterval] = Field(default_factory=dict)


class CalibrationDiagnostics(BaseModel):
    model_config = ConfigDict(frozen=True)

    calibration_method: CalibrationMethod
    sample_size: int
    effective_sample_size: float
    base_rate: Optional[float] = None
    brier_score: Optional[float] = None
    log_loss: Optional[float] = None
    expected_calibration_error: Optional[float] = None
    maximum_calibration_error: Optional[float] = None
    calibration_intercept: Optional[float] = None
    calibration_slope: Optional[float] = None
    auc: Optional[float] = None
    average_precision: Optional[float] = None
    precision_at_k: dict[str, float] = Field(default_factory=dict)
    recall_at_k: dict[str, float] = Field(default_factory=dict)
    top_decile_hit_rate: Optional[float] = None
    lift_vs_base_rate: Optional[float] = None
    reliability_table: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SegmentDiagnostics(BaseModel):
    model_config = ConfigDict(frozen=True)

    segment_key: str
    segment_filters: dict = Field(default_factory=dict)
    sample_size: int
    effective_sample_size: float
    base_rate: Optional[float] = None
    calibrated_rate: Optional[float] = None
    brier_score: Optional[float] = None
    expected_calibration_error: Optional[float] = None
    auc: Optional[float] = None
    precision_at_k: dict[str, float] = Field(default_factory=dict)
    reliability_label: CalibrationQualityLabel
    out_of_domain_warning: bool = False
    notes: list[str] = Field(default_factory=list)


class ThresholdRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True)

    threshold_name: str
    current_threshold: float
    recommended_threshold: float
    operating_mode: OperatingMode
    expected_precision: Optional[float] = None
    expected_recall: Optional[float] = None
    expected_false_positive_rate: Optional[float] = None
    expected_false_negative_rate: Optional[float] = None
    tradeoff_explanation: str
    should_auto_apply: bool = False       # NEVER true by default
    requires_human_review: bool = True    # ALWAYS true by default


class PostmortemRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_id: str
    acquirer_id: Optional[str] = None
    prediction_date: date
    outcome_date: Optional[date] = None
    initial_layer0_snapshot: dict = Field(default_factory=dict)
    initial_layer1_score: Optional[float] = None
    initial_layer2_score: Optional[float] = None
    initial_layer3_score: Optional[float] = None
    initial_layer4_route: Optional[str] = None
    predicted_probabilities: dict = Field(default_factory=dict)
    actual_outcome: OutcomeType
    time_to_outcome_days: Optional[int] = None
    prediction_error: Optional[float] = None
    primary_error_type: ErrorType
    secondary_error_types: list[ErrorType] = Field(default_factory=list)
    root_cause: str
    recommended_model_update: str
    should_update_thresholds: bool = False
    should_update_weights: bool = False
    data_quality_issue: bool = False
    notes: list[str] = Field(default_factory=list)


class DriftReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    drift_status: str   # none / mild / moderate / severe
    drift_types: list[DriftType] = Field(default_factory=list)
    affected_layers: list[LayerValidated] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    metric_changes: dict = Field(default_factory=dict)
    recommended_action: str = ""
    requires_recalibration: bool = False
    temporary_weighting_caution: list[str] = Field(default_factory=list)


class CalibrationGovernanceMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_version: str
    calibration_dataset_version: str
    calibration_date: date
    training_window_start: Optional[date] = None
    training_window_end: Optional[date] = None
    feature_schema_version: str = "v1"
    calibration_artifact_id: Optional[str] = None
    excluded_case_count: int = 0
    known_limitations: list[str] = Field(default_factory=list)


class Layer5CalibrationOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_id: Optional[str] = None
    acquirer_id: Optional[str] = None
    prediction_date: Optional[date] = None

    raw_scores: dict = Field(default_factory=dict)
    layer4_route: Optional[str] = None

    calibrated_probabilities: CalibratedProbabilitySet = Field(
        default_factory=CalibratedProbabilitySet
    )
    calibration_quality: CalibrationQualityLabel
    calibration_diagnostics: CalibrationDiagnostics
    segment_diagnostics: list[SegmentDiagnostics] = Field(default_factory=list)

    threshold_guidance: list[ThresholdRecommendation] = Field(default_factory=list)
    postmortem_notes: list[str] = Field(default_factory=list)
    drift_warnings: list[str] = Field(default_factory=list)

    confidence_intervals: dict[str, ProbabilityInterval] = Field(default_factory=dict)
    do_not_use_as_probability: bool = False
    do_not_use_as_probability_reason: Optional[str] = None

    governance: CalibrationGovernanceMetadata
    warnings: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Config objects used by public API
# ---------------------------------------------------------------------------

class OutcomeDatasetConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    observation_window_months: int = 12
    require_leakage_check: bool = True
    exclude_leaky_cases: bool = True
    min_observation_window_days: int = 30


class Layer5CalibrationConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    calibration_method: CalibrationMethod = CalibrationMethod.BAYESIAN_BIN_CALIBRATION
    min_sample_size_for_platt: int = 30
    min_sample_size_for_isotonic: int = 50
    min_sample_size_for_segment: int = 30
    n_bins: int = 10
    model_version: str = "v1"
    dataset_version: str = "v1"
    feature_schema_version: str = "v1"


class Layer5ValidationConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    top_k: int = 15
    observation_window_months: int = 12
    min_cases_per_layer: int = 5


# ---------------------------------------------------------------------------
# CalibrationArtifact — holds fitted model parameters (no scipy objects)
# ---------------------------------------------------------------------------

class CalibrationArtifact(BaseModel):
    """Serialisable fitted Layer 5 calibration artifact."""
    model_config = ConfigDict(frozen=True)

    artifact_id: str
    governance: CalibrationGovernanceMetadata

    # Platt scaling parameters (A, B in P = sigmoid(A*score + B))
    platt_intercept: Optional[float] = None
    platt_slope: Optional[float] = None

    # Bayesian bin table: list of {"lower":, "upper":, "count":, "positives":}
    bayesian_bins: list[dict] = Field(default_factory=list)

    # Global base rate
    global_base_rate: Optional[float] = None
    global_sample_size: int = 0

    # Diagnostics snapshot from training
    training_diagnostics: Optional[CalibrationDiagnostics] = None
