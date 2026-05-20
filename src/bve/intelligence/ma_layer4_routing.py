"""
Layer 4 — BD Watchlist Classification and Action Routing.

After Layer 3 gates the composite score, Layer 4 routes each target-acquirer
pair into a BD watchlist class and produces a full action recommendation:

  pass               → Archive; do not monitor unless facts change
  data_insufficient  → Fill data gaps before acting
  strategic_radar    → Strategically relevant; no urgency — review quarterly
  relationship_build → Strong fit, not actionable yet — build trust first
  catalyst_watch     → Important event approaching — monitor closely
  active_pursuit     → High fit + real transaction setup — begin BD process
  process_ready      → Strong target likely to transact soon — prepare now

Each output includes:
  watchlist_class         seven-tier BD routing class
  recommended_bd_action   short imperative action string
  recommended_structure   deal structure (full_acquisition, option_to_acquire, …)
  time_horizon            expected transaction window
  review_cadence          how often to revisit
  promotion_trigger       signals that would move target to a higher class
  demotion_trigger        signals that would move target to a lower class
  confidence_level        how confident the classification is
  reason_codes            machine-readable codes explaining the decision
  owner_next_step         first BD action for the responsible team

Key design principles:
  • Classification rules are applied in strict priority order; first match wins.
  • Persistence suppression: a class change requires 2 consecutive weekly
    observations OR one major-event override to prevent noisy churn.
  • Deal structure is chosen from 8 options based on asset quality, clinical
    stage, strategic fit, feasibility, and control.
  • Promotion and demotion triggers are per-class advisory strings.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class WatchlistClass(str, Enum):
    PASS = "pass"
    DATA_INSUFFICIENT = "data_insufficient"
    STRATEGIC_RADAR = "strategic_radar"
    RELATIONSHIP_BUILD = "relationship_build"
    CATALYST_WATCH = "catalyst_watch"
    ACTIVE_PURSUIT = "active_pursuit"
    PROCESS_READY = "process_ready"


class DealStructure(str, Enum):
    FULL_ACQUISITION = "full_acquisition"
    ASSET_LICENSE = "asset_license"
    OPTION_TO_ACQUIRE = "option_to_acquire"
    CO_DEVELOPMENT = "co_development"
    REGIONAL_RIGHTS = "regional_rights"
    RESEARCH_COLLABORATION = "research_collaboration"
    MINORITY_EQUITY = "minority_equity"
    MONITOR_ONLY = "monitor_only"


class ReviewCadence(str, Enum):
    NONE = "none"
    AS_NEEDED = "as_needed"
    QUARTERLY = "quarterly"
    MONTHLY = "monthly"
    BI_WEEKLY = "bi_weekly"
    WEEKLY = "weekly"


class TimeHorizon(str, Enum):
    NOT_APPLICABLE = "n/a"
    BEYOND_24_MONTHS = "24+ months"
    TWELVE_TO_24_MONTHS = "12–24 months"
    SIX_TO_18_MONTHS = "6–18 months"
    THREE_TO_12_MONTHS = "3–12 months"
    ZERO_TO_6_MONTHS = "0–6 months"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT = "insufficient"


# ---------------------------------------------------------------------------
# Per-class advisory triggers
# ---------------------------------------------------------------------------

_PROMOTION_TRIGGERS: dict[WatchlistClass, list[str]] = {
    WatchlistClass.PASS: [
        "major_clinical_success_in_indication",
        "new_acquirer_with_right_to_win_identified",
        "FDA_breakthrough_designation_granted",
    ],
    WatchlistClass.DATA_INSUFFICIENT: [
        "diligence_checklist_completed",
        "Phase2_data_published",
        "acquirer_completes_scientific_review",
    ],
    WatchlistClass.STRATEGIC_RADAR: [
        "strategic_priority_increases_by_0.10",
        "acquirer_gap_urgency_becomes_high",
        "competitor_deal_activity_increases",
        "seller_hires_investment_banker",
        "activist_takes_board_seat",
    ],
    WatchlistClass.RELATIONSHIP_BUILD: [
        "positive_Phase2_PoC_readout",
        "FDA_alignment_achieved",
        "cash_runway_falls_below_6_quarters",
        "seller_hires_investment_banker",
        "competitor_acquires_similar_asset",
        "activist_launches_campaign",
    ],
    WatchlistClass.CATALYST_WATCH: [
        "positive_Phase2_PoC_readout",
        "FDA_alignment_achieved",
        "cash_runway_falls_below_6_quarters",
        "seller_hires_investment_banker",
        "board_initiates_strategic_review",
    ],
    WatchlistClass.ACTIVE_PURSUIT: [
        "seller_launches_formal_process",
        "deal_feasibility_improves_to_0.60",
        "seller_willingness_rises_above_0.60",
        "competing_bidder_identified",
    ],
    WatchlistClass.PROCESS_READY: [
        "immediate_BD_pursuit_only",
    ],
}

_DEMOTION_TRIGGERS: dict[WatchlistClass, list[str]] = {
    WatchlistClass.PASS: [],
    WatchlistClass.DATA_INSUFFICIENT: [],
    WatchlistClass.STRATEGIC_RADAR: [
        "safety_issue_emerges",
        "competitor_data_weakens_differentiation",
        "FDA_requires_larger_longer_trial",
        "strategic_fit_drops_below_0.35",
        "acquirer_pipeline_gap_filled_by_another_deal",
    ],
    WatchlistClass.RELATIONSHIP_BUILD: [
        "safety_issue_emerges",
        "target_closes_long_runway_financing",
        "competitor_data_weakens_differentiation",
        "acquirer_gap_filled_by_another_deal",
        "strategic_priority_drops_below_0.65",
    ],
    WatchlistClass.CATALYST_WATCH: [
        "negative_Phase2_PoC_readout",
        "FDA_clinical_hold_issued",
        "target_closes_long_runway_financing",
        "safety_issue_emerges",
        "catalyst_delayed_beyond_180_days",
    ],
    WatchlistClass.ACTIVE_PURSUIT: [
        "safety_issue_emerges",
        "target_completes_financing_with_long_runway",
        "competitor_data_weakens_differentiation",
        "FDA_requires_larger_longer_trial",
        "acquirer_gap_filled_by_another_deal",
        "seller_willingness_drops_below_0.30",
    ],
    WatchlistClass.PROCESS_READY: [
        "safety_issue_emerges",
        "deal_economics_deteriorate_materially",
        "competing_bidder_acquires_target",
        "FDA_clinical_hold_issued",
    ],
}

# BD actions per class
_BD_ACTIONS: dict[WatchlistClass, str] = {
    WatchlistClass.PASS: "Archive with reason code",
    WatchlistClass.DATA_INSUFFICIENT: "Assign diligence checklist",
    WatchlistClass.STRATEGIC_RADAR: "Monitor quarterly",
    WatchlistClass.RELATIONSHIP_BUILD: "Identify CEO/CBO/BD contact; attend same conferences",
    WatchlistClass.CATALYST_WATCH: "Build pre/post-catalyst scenario memo",
    WatchlistClass.ACTIVE_PURSUIT: "Create internal opportunity memo",
    WatchlistClass.PROCESS_READY: "Prepare outreach strategy / deal model / competitive bidder map",
}

# Owner next step per class
_OWNER_NEXT_STEPS: dict[WatchlistClass, str] = {
    WatchlistClass.PASS: "Log archive reason; set 12-month revisit flag",
    WatchlistClass.DATA_INSUFFICIENT: "Assign diligence lead; complete data gaps within 30 days",
    WatchlistClass.STRATEGIC_RADAR: "Add to quarterly BD review agenda",
    WatchlistClass.RELATIONSHIP_BUILD: "Map management contacts; schedule conference attendance",
    WatchlistClass.CATALYST_WATCH: "Draft pre-catalyst thesis; schedule post-catalyst call",
    WatchlistClass.ACTIVE_PURSUIT: "Draft internal opportunity memo; present to BD committee",
    WatchlistClass.PROCESS_READY: "Launch outreach strategy; prepare deal model; map competitive bidders",
}

# Review cadence per class
_REVIEW_CADENCES: dict[WatchlistClass, ReviewCadence] = {
    WatchlistClass.PASS: ReviewCadence.NONE,
    WatchlistClass.DATA_INSUFFICIENT: ReviewCadence.AS_NEEDED,
    WatchlistClass.STRATEGIC_RADAR: ReviewCadence.QUARTERLY,
    WatchlistClass.RELATIONSHIP_BUILD: ReviewCadence.MONTHLY,
    WatchlistClass.CATALYST_WATCH: ReviewCadence.BI_WEEKLY,
    WatchlistClass.ACTIVE_PURSUIT: ReviewCadence.WEEKLY,
    WatchlistClass.PROCESS_READY: ReviewCadence.WEEKLY,
}

# Time horizons per class
_TIME_HORIZONS: dict[WatchlistClass, TimeHorizon] = {
    WatchlistClass.PASS: TimeHorizon.NOT_APPLICABLE,
    WatchlistClass.DATA_INSUFFICIENT: TimeHorizon.NOT_APPLICABLE,
    WatchlistClass.STRATEGIC_RADAR: TimeHorizon.BEYOND_24_MONTHS,
    WatchlistClass.RELATIONSHIP_BUILD: TimeHorizon.TWELVE_TO_24_MONTHS,
    WatchlistClass.CATALYST_WATCH: TimeHorizon.ZERO_TO_6_MONTHS,
    WatchlistClass.ACTIVE_PURSUIT: TimeHorizon.THREE_TO_12_MONTHS,
    WatchlistClass.PROCESS_READY: TimeHorizon.ZERO_TO_6_MONTHS,
}


# ---------------------------------------------------------------------------
# Classification thresholds
# ---------------------------------------------------------------------------

# Pass hard gates
_PASS_ASSET_QUALITY_MIN: float = 0.35
_PASS_STRATEGIC_FIT_MIN: float = 0.35
_PASS_DEAL_FEASIBILITY_MIN: float = 0.30

# Data confidence threshold
_DATA_CONFIDENCE_MIN: float = 0.60

# Process ready thresholds
_PR_STRATEGIC_PRIORITY_MIN: float = 0.75
_PR_TRANSACTION_READINESS_MIN: float = 0.70
_PR_SELLER_WILLINGNESS_MIN: float = 0.60
_PR_DEAL_FEASIBILITY_MIN: float = 0.60

# Active pursuit thresholds
_AP_STRATEGIC_PRIORITY_MIN: float = 0.70
_AP_TRANSACTION_READINESS_MIN: float = 0.60
_AP_SELLER_WILLINGNESS_MIN: float = 0.40
_AP_DRIVER_BUCKETS_MIN: int = 2

# Catalyst watch thresholds
_CW_ASSET_QUALITY_MIN: float = 0.55
_CW_STRATEGIC_FIT_MIN: float = 0.60

# Relationship build thresholds
_RB_STRATEGIC_PRIORITY_MIN: float = 0.70
_RB_SELLER_WILLINGNESS_MAX: float = 0.40   # exclusive
_RB_TRANSACTION_READINESS_LO: float = 0.35
_RB_TRANSACTION_READINESS_HI: float = 0.55  # inclusive

# Strategic radar thresholds
_SR_STRATEGIC_PRIORITY_MIN: float = 0.65
_SR_TRANSACTION_READINESS_MAX: float = 0.40  # exclusive

# Deal structure thresholds
_STRUCT_FULL_ACQ_QUALITY_MIN: float = 0.70
_STRUCT_FULL_ACQ_READINESS_MIN: float = 0.65
_STRUCT_OPTION_QUALITY_MIN: float = 0.65
_STRUCT_OPTION_DERISKING_MAX: float = 0.55  # still has clinical risk
_STRUCT_LICENSE_FIT_MIN: float = 0.65
_STRUCT_LICENSE_FEASIBILITY_MAX: float = 0.50  # company unattractive at whole-co level
_STRUCT_COLLAB_FIT_MIN: float = 0.60
_STRUCT_COLLAB_DERISKING_MAX: float = 0.35  # early platform
_STRUCT_REGIONAL_CONTROL_MAX: float = 0.50  # encumbered rights

# Persistence threshold
_PERSISTENCE_MIN_CONSECUTIVE: int = 2


# ---------------------------------------------------------------------------
# Input / Output models
# ---------------------------------------------------------------------------

class Layer4Inputs(BaseModel):
    """Flat input model for Layer 4 classification.

    Values are sourced from upstream layers:
      Layer 1 (BDMAOutput):   asset_quality, strategic_fit, deal_feasibility,
                               seller_willingness, de_risking_stage, asset_control
      Layer 2 (Layer2Output): strategic_priority, transaction_probability,
                               data_confidence_score, n_drivers
      Layer 3 (Layer3Output): final_score, active_driver_bucket_count

    Persistence fields (caller-managed across weekly observations):
      prior_classification, consecutive_new_class_signals, major_event_override
    """
    model_config = ConfigDict(frozen=True)

    # Asset characteristics (from Layer 1)
    asset_quality: float = Field(..., ge=0.0, le=1.0,
        description="Overall asset quality score (Layer 1 1A)")
    strategic_fit: float = Field(..., ge=0.0, le=1.0,
        description="Acquirer strategic fit / right-to-win (Layer 1 1D)")
    deal_feasibility: float = Field(..., ge=0.0, le=1.0,
        description="Deal feasibility score (Layer 1 1E)")
    seller_willingness: float = Field(..., ge=0.0, le=1.0,
        description="Management/board willingness to transact (Layer 1 1C)")
    de_risking_stage: float = Field(..., ge=0.0, le=1.0,
        description="Clinical/regulatory stage advancement (0=preclinical, 1=approved)")
    asset_control: float = Field(default=1.0, ge=0.0, le=1.0,
        description="Degree of clean title and absence of blocking rights (Layer 1 1E)")

    # Composite scores (from Layer 2)
    strategic_priority: float = Field(..., ge=0.0, le=1.0,
        description="Layer 2 strategic priority score")
    transaction_probability: float = Field(..., ge=0.0, le=1.0,
        description="Layer 2 transaction probability (used as transaction readiness)")
    data_confidence_score: float = Field(default=1.0, ge=0.0, le=1.0,
        description="Data completeness/confidence (0=no data, 1=fully verified)")

    # Transaction driver context (from Layer 3)
    active_driver_bucket_count: int = Field(default=0, ge=0,
        description="Number of active driver buckets (Layer 3 DriverBucketResult)")
    final_score: float = Field(default=0.5, ge=0.0, le=1.0,
        description="Layer 3 post-gate final score")

    # Event flag
    catalyst_within_180_days: bool = Field(default=False,
        description="True if a binary catalyst (readout, PDUFA, etc.) is within 180 days")

    # Persistence / churn suppression
    prior_classification: Optional[str] = Field(default=None,
        description="Watchlist class assigned in the previous observation period")
    consecutive_new_class_signals: int = Field(default=0, ge=0,
        description="Consecutive weekly periods the candidate class has differed from prior")
    major_event_override: bool = Field(default=False,
        description="True when a major event (safety alert, deal announcement, FDA hold) "
                    "justifies immediate class change without waiting for 2 observations")

    # Deal-type classification from Layer 0 (optional enrichment)
    deal_type_classification: Optional[Any] = Field(default=None,
        description="DealTypeClassification from Layer 0 0B gate; used to annotate output")


class Layer4Output(BaseModel):
    """Full BD watchlist classification and action routing output."""
    model_config = ConfigDict(frozen=True)

    target_name: str
    acquirer_id: Optional[str]

    # Primary classification outputs (9 spec fields)
    watchlist_class: str = Field(...,
        description="Seven-tier BD routing class")
    recommended_bd_action: str = Field(...,
        description="Short imperative BD action for this class")
    recommended_structure: str = Field(...,
        description="Recommended deal structure")
    time_horizon: str = Field(...,
        description="Expected transaction window")
    review_cadence: str = Field(...,
        description="How often this target should be re-evaluated")
    promotion_trigger: list[str] = Field(...,
        description="Signals that would move the target to a higher class")
    demotion_trigger: list[str] = Field(...,
        description="Signals that would move the target to a lower class")
    confidence_level: str = Field(...,
        description="How confident the classification is")
    owner_next_step: str = Field(...,
        description="Immediate BD action for the responsible team")

    # Additional diagnostic fields
    reason_codes: list[str] = Field(...,
        description="Machine-readable codes explaining the classification decision")
    classification_suppressed: bool = Field(default=False,
        description="True when persistence logic held the prior classification "
                    "against a candidate change (churn suppression)")
    candidate_class: str = Field(...,
        description="Classification the rules would produce before persistence check")

    # Deal-type fields from Layer 0 0B classification (None when not provided)
    primary_deal_type: Optional[str] = Field(default=None,
        description="Primary deal archetype from DealTypeClassification (Layer 0 0B)")
    secondary_deal_types: list[str] = Field(default_factory=list,
        description="Secondary deal archetypes with weight >= 0.20")
    recommended_model: Optional[str] = Field(default=None,
        description="Recommended scoring model from DealTypeClassification")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _classify_candidate(inputs: Layer4Inputs) -> tuple[WatchlistClass, list[str]]:
    """Apply classification rules in priority order. Returns (class, reason_codes)."""
    codes: list[str] = []

    # 1. Pass — hard quality gates
    if inputs.asset_quality < _PASS_ASSET_QUALITY_MIN:
        codes.append(f"asset_quality={inputs.asset_quality:.2f} < {_PASS_ASSET_QUALITY_MIN}")
        return WatchlistClass.PASS, codes
    if inputs.strategic_fit < _PASS_STRATEGIC_FIT_MIN:
        codes.append(f"strategic_fit={inputs.strategic_fit:.2f} < {_PASS_STRATEGIC_FIT_MIN}")
        return WatchlistClass.PASS, codes
    if inputs.deal_feasibility < _PASS_DEAL_FEASIBILITY_MIN:
        codes.append(f"deal_feasibility={inputs.deal_feasibility:.2f} < {_PASS_DEAL_FEASIBILITY_MIN}")
        return WatchlistClass.PASS, codes

    # 2. Data insufficient — don't pretend the model knows enough
    if inputs.data_confidence_score < _DATA_CONFIDENCE_MIN:
        codes.append(
            f"data_confidence_score={inputs.data_confidence_score:.2f} < {_DATA_CONFIDENCE_MIN}"
        )
        return WatchlistClass.DATA_INSUFFICIENT, codes

    # 3. Process ready — most actionable class; checked before active pursuit
    if (
        inputs.strategic_priority >= _PR_STRATEGIC_PRIORITY_MIN
        and inputs.transaction_probability >= _PR_TRANSACTION_READINESS_MIN
        and inputs.seller_willingness >= _PR_SELLER_WILLINGNESS_MIN
        and inputs.deal_feasibility >= _PR_DEAL_FEASIBILITY_MIN
    ):
        codes.append(
            f"SP={inputs.strategic_priority:.2f}>={_PR_STRATEGIC_PRIORITY_MIN} "
            f"TP={inputs.transaction_probability:.2f}>={_PR_TRANSACTION_READINESS_MIN} "
            f"SW={inputs.seller_willingness:.2f}>={_PR_SELLER_WILLINGNESS_MIN} "
            f"DF={inputs.deal_feasibility:.2f}>={_PR_DEAL_FEASIBILITY_MIN}"
        )
        return WatchlistClass.PROCESS_READY, codes

    # 4. Active pursuit — high fit + real transaction setup
    if (
        inputs.strategic_priority >= _AP_STRATEGIC_PRIORITY_MIN
        and inputs.transaction_probability >= _AP_TRANSACTION_READINESS_MIN
        and inputs.active_driver_bucket_count >= _AP_DRIVER_BUCKETS_MIN
        and inputs.seller_willingness >= _AP_SELLER_WILLINGNESS_MIN
    ):
        codes.append(
            f"SP={inputs.strategic_priority:.2f}>={_AP_STRATEGIC_PRIORITY_MIN} "
            f"TP={inputs.transaction_probability:.2f}>={_AP_TRANSACTION_READINESS_MIN} "
            f"drivers={inputs.active_driver_bucket_count}>={_AP_DRIVER_BUCKETS_MIN} "
            f"SW={inputs.seller_willingness:.2f}>={_AP_SELLER_WILLINGNESS_MIN}"
        )
        return WatchlistClass.ACTIVE_PURSUIT, codes

    # 5. Catalyst watch — important event approaching
    if (
        inputs.catalyst_within_180_days
        and inputs.asset_quality >= _CW_ASSET_QUALITY_MIN
        and inputs.strategic_fit >= _CW_STRATEGIC_FIT_MIN
    ):
        codes.append(
            f"catalyst_within_180_days=True "
            f"AQ={inputs.asset_quality:.2f}>={_CW_ASSET_QUALITY_MIN} "
            f"SF={inputs.strategic_fit:.2f}>={_CW_STRATEGIC_FIT_MIN}"
        )
        return WatchlistClass.CATALYST_WATCH, codes

    # 6. Relationship build — strong fit, willing seller unlikely, mid readiness
    if (
        inputs.strategic_priority >= _RB_STRATEGIC_PRIORITY_MIN
        and inputs.seller_willingness < _RB_SELLER_WILLINGNESS_MAX
        and _RB_TRANSACTION_READINESS_LO <= inputs.transaction_probability <= _RB_TRANSACTION_READINESS_HI
    ):
        codes.append(
            f"SP={inputs.strategic_priority:.2f}>={_RB_STRATEGIC_PRIORITY_MIN} "
            f"SW={inputs.seller_willingness:.2f}<{_RB_SELLER_WILLINGNESS_MAX} "
            f"TP={inputs.transaction_probability:.2f} in "
            f"[{_RB_TRANSACTION_READINESS_LO},{_RB_TRANSACTION_READINESS_HI}]"
        )
        return WatchlistClass.RELATIONSHIP_BUILD, codes

    # 7. Strategic radar — good fit, no urgency
    if (
        inputs.strategic_priority >= _SR_STRATEGIC_PRIORITY_MIN
        and inputs.transaction_probability < _SR_TRANSACTION_READINESS_MAX
    ):
        codes.append(
            f"SP={inputs.strategic_priority:.2f}>={_SR_STRATEGIC_PRIORITY_MIN} "
            f"TP={inputs.transaction_probability:.2f}<{_SR_TRANSACTION_READINESS_MAX}"
        )
        return WatchlistClass.STRATEGIC_RADAR, codes

    # 8. Default fallback
    codes.append(
        f"no_class_conditions_met SP={inputs.strategic_priority:.2f} "
        f"TP={inputs.transaction_probability:.2f}"
    )
    return WatchlistClass.DATA_INSUFFICIENT, codes


def _apply_persistence(
    candidate: WatchlistClass,
    inputs: Layer4Inputs,
) -> tuple[WatchlistClass, bool]:
    """Apply churn-suppression persistence rule.

    A class change is suppressed unless:
      - major_event_override is True, OR
      - consecutive_new_class_signals >= _PERSISTENCE_MIN_CONSECUTIVE

    Returns (final_class, was_suppressed).
    """
    if inputs.prior_classification is None:
        return candidate, False
    if candidate.value == inputs.prior_classification:
        return candidate, False
    if inputs.major_event_override:
        return candidate, False
    if inputs.consecutive_new_class_signals >= _PERSISTENCE_MIN_CONSECUTIVE:
        return candidate, False
    # Suppress — hold prior classification
    try:
        prior_enum = WatchlistClass(inputs.prior_classification)
    except ValueError:
        return candidate, False
    return prior_enum, True


def _recommend_structure(inputs: Layer4Inputs, watchlist_class: WatchlistClass) -> DealStructure:
    """Choose the recommended deal structure from 8 options."""
    # Pass or data_insufficient → monitor only
    if watchlist_class in (WatchlistClass.PASS, WatchlistClass.DATA_INSUFFICIENT):
        return DealStructure.MONITOR_ONLY

    # Encumbered rights block full acquisition
    if inputs.asset_control < _STRUCT_REGIONAL_CONTROL_MAX:
        return DealStructure.REGIONAL_RIGHTS

    # Full acquisition: high quality AND high transaction readiness
    if (
        inputs.asset_quality >= _STRUCT_FULL_ACQ_QUALITY_MIN
        and inputs.transaction_probability >= _STRUCT_FULL_ACQ_READINESS_MIN
    ):
        return DealStructure.FULL_ACQUISITION

    # Option to acquire: high quality but still meaningful clinical risk
    if (
        inputs.asset_quality >= _STRUCT_OPTION_QUALITY_MIN
        and inputs.de_risking_stage < _STRUCT_OPTION_DERISKING_MAX
    ):
        return DealStructure.OPTION_TO_ACQUIRE

    # Asset license: strong fit but full company unattractively priced / feasibility low
    if (
        inputs.strategic_fit >= _STRUCT_LICENSE_FIT_MIN
        and inputs.deal_feasibility < _STRUCT_LICENSE_FEASIBILITY_MAX
    ):
        return DealStructure.ASSET_LICENSE

    # Research collaboration: strategic fit high but asset is early-stage platform
    if (
        inputs.strategic_fit >= _STRUCT_COLLAB_FIT_MIN
        and inputs.de_risking_stage < _STRUCT_COLLAB_DERISKING_MAX
    ):
        return DealStructure.RESEARCH_COLLABORATION

    # Relationship build: minority equity to establish option value
    if watchlist_class == WatchlistClass.RELATIONSHIP_BUILD:
        return DealStructure.MINORITY_EQUITY

    # Strategic radar: monitor-only until actionable
    if watchlist_class == WatchlistClass.STRATEGIC_RADAR:
        return DealStructure.MONITOR_ONLY

    # Moderate signals: co-development
    if inputs.asset_quality >= 0.55 and inputs.strategic_fit >= 0.55:
        return DealStructure.CO_DEVELOPMENT

    return DealStructure.MONITOR_ONLY


def _confidence_level(inputs: Layer4Inputs, watchlist_class: WatchlistClass) -> ConfidenceLevel:
    """Derive confidence from data completeness and classification strength."""
    if watchlist_class == WatchlistClass.DATA_INSUFFICIENT:
        return ConfidenceLevel.INSUFFICIENT
    if inputs.data_confidence_score >= 0.85:
        return ConfidenceLevel.HIGH
    if inputs.data_confidence_score >= 0.70:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_layer4(
    inputs: Layer4Inputs,
    target_name: str = "Unknown",
    acquirer_id: Optional[str] = None,
) -> Layer4Output:
    """Layer 4 BD Watchlist Classification and Action Routing.

    Takes Layer 3's post-gate score and associated asset/deal signals and
    routes the target-acquirer pair into one of seven watchlist classes with
    a complete BD action recommendation.

    Args:
        inputs: Layer4Inputs with all scoring signals and persistence state.
        target_name: Display name of the target company.
        acquirer_id: Identifier of the acquirer being evaluated.

    Returns:
        Layer4Output with watchlist_class, recommended_bd_action,
        recommended_structure, time_horizon, review_cadence,
        promotion_trigger, demotion_trigger, confidence_level,
        owner_next_step, reason_codes.
    """
    # Step 1: classify (pre-persistence)
    candidate_class, reason_codes = _classify_candidate(inputs)

    # Step 2: apply persistence suppression
    final_class, suppressed = _apply_persistence(candidate_class, inputs)

    # Step 3: deal structure (based on final class)
    structure = _recommend_structure(inputs, final_class)

    # Step 4: confidence
    confidence = _confidence_level(inputs, final_class)

    # Step 5: add suppression reason code if applicable
    if suppressed:
        reason_codes = reason_codes + [
            f"persistence_suppressed: held {final_class.value} "
            f"(candidate={candidate_class.value}, "
            f"consecutive_signals={inputs.consecutive_new_class_signals})"
        ]

    # Propagate deal-type classification fields if provided
    dtc = inputs.deal_type_classification
    primary_deal_type: Optional[str] = None
    secondary_deal_types: list[str] = []
    recommended_model: Optional[str] = None
    if dtc is not None:
        primary_deal_type = getattr(dtc, "primary_deal_type", None)
        if primary_deal_type is not None:
            primary_deal_type = str(primary_deal_type.value) if hasattr(primary_deal_type, "value") else str(primary_deal_type)
        secondary_deal_types = [
            str(s.value) if hasattr(s, "value") else str(s)
            for s in getattr(dtc, "secondary_deal_types", [])
        ]
        rm = getattr(dtc, "recommended_model", None)
        if rm is not None:
            recommended_model = str(rm.value) if hasattr(rm, "value") else str(rm)

    return Layer4Output(
        target_name=target_name,
        acquirer_id=acquirer_id,
        watchlist_class=final_class.value,
        recommended_bd_action=_BD_ACTIONS[final_class],
        recommended_structure=structure.value,
        time_horizon=_TIME_HORIZONS[final_class].value,
        review_cadence=_REVIEW_CADENCES[final_class].value,
        promotion_trigger=_PROMOTION_TRIGGERS[final_class],
        demotion_trigger=_DEMOTION_TRIGGERS[final_class],
        confidence_level=confidence.value,
        owner_next_step=_OWNER_NEXT_STEPS[final_class],
        reason_codes=reason_codes,
        classification_suppressed=suppressed,
        candidate_class=candidate_class.value,
        primary_deal_type=primary_deal_type,
        secondary_deal_types=secondary_deal_types,
        recommended_model=recommended_model,
    )
