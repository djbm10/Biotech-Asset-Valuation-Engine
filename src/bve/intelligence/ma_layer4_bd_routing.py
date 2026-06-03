"""
Layer 4 — BD Routing & Execution Playbook.

Consumes outputs from Layers 0–3 and produces a practical BD workflow:
route class, deal structure, urgency, escalation, outreach status,
diligence workplan, remediation plan, monitoring triggers, and memo output.

Layer 4 deliberately does NOT:
    • Re-score asset quality                   → Layer 1
    • Re-score BD action priority              → Layer 2
    • Re-run pair-specific deal feasibility    → Layer 3
    • Produce calibrated acquisition probability → Layer 5

It answers one question:
    "Given the scores, caps, blockers, and confidence from Layers 0–3,
     what should BD actually do next?"

Design principles:
    • Deterministic, auditable, no LLM calls.
    • All thresholds centralised in _T (easy to adjust).
    • Rules applied in strict priority order; first match wins.
    • Every routing decision has a reason string.
    • Every hard-fail / DO_NOT_CONTACT decision has an explicit reason.

Backward compatibility:
    LEGACY_ROUTE_MAP maps old WatchlistClass string values to new RouteClass.
    The old compute_layer4() in ma_layer4_routing.py is NOT touched.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RouteClass(str, Enum):
    ACTIVE_PURSUIT                = "active_pursuit"
    HIGH_PRIORITY_DILIGENCE       = "high_priority_diligence"
    PARTNER_OR_LICENSE_CANDIDATE  = "partner_or_license_candidate"
    OPTION_TO_ACQUIRE_CANDIDATE   = "option_to_acquire_candidate"
    CATALYST_WATCH                = "catalyst_watch"
    STRATEGIC_WATCH               = "strategic_watch"
    RELATIONSHIP_BUILD            = "relationship_build"
    ACQUIRER_MAPPING_NEEDED       = "acquirer_mapping_needed"
    REMEDIATION_REQUIRED          = "remediation_required"
    MONITOR_ONLY                  = "monitor_only"
    PASS_DO_NOT_PURSUE            = "pass_do_not_pursue"
    PAIR_LEVEL_HARD_FAIL          = "pair_level_hard_fail"


class NewDealStructure(str, Enum):
    FULL_ACQUISITION                      = "full_acquisition"
    ASSET_ACQUISITION                     = "asset_acquisition"
    GLOBAL_LICENSE                        = "global_license"
    REGIONAL_LICENSE                      = "regional_license"
    CO_DEVELOPMENT                        = "co_development"
    CO_COMMERCIALIZATION                  = "co_commercialization"
    OPTION_TO_ACQUIRE                     = "option_to_acquire"
    OPTION_TO_LICENSE                     = "option_to_license"
    MINORITY_EQUITY_INVESTMENT            = "minority_equity_investment"
    STRATEGIC_COLLABORATION               = "strategic_collaboration"
    CVR_HEAVY_ACQUISITION                 = "cvr_heavy_acquisition"
    STRUCTURED_ACQUISITION_WITH_MILESTONES = "structured_acquisition_with_milestones"
    MONITOR_ONLY                          = "monitor_only"
    NO_ACTION                             = "no_action"


class UrgencyLevel(str, Enum):
    IMMEDIATE_0_TO_30_DAYS       = "immediate_0_to_30_days"
    NEAR_TERM_1_TO_3_MONTHS      = "near_term_1_to_3_months"
    MEDIUM_TERM_3_TO_12_MONTHS   = "medium_term_3_to_12_months"
    WATCH_12_PLUS_MONTHS         = "watch_12_plus_months"
    DORMANT_OR_PASS              = "dormant_or_pass"


class EscalationLevel(str, Enum):
    ANALYST_REVIEW                   = "analyst_review"
    BD_MANAGER_REVIEW                = "bd_manager_review"
    SENIOR_BD_REVIEW                 = "senior_bd_review"
    INVESTMENT_COMMITTEE_PREP        = "investment_committee_prep"
    EXECUTIVE_SPONSOR_REVIEW         = "executive_sponsor_review"
    BOARD_LEVEL_STRATEGIC_DISCUSSION = "board_level_strategic_discussion"
    NO_ESCALATION                    = "no_escalation"


class OutreachStatus(str, Enum):
    OUTREACH_READY      = "outreach_ready"
    DO_NOT_CONTACT_YET  = "do_not_contact_yet"
    SOFT_TOUCH_ONLY     = "soft_touch_only"
    MONITOR_ONLY        = "monitor_only"
    BLOCKED             = "blocked"


class MonitoringFrequency(str, Enum):
    DAILY_EVENT_DRIVEN     = "daily_event_driven"
    WEEKLY                 = "weekly"
    WEEKLY_OR_EVENT_DRIVEN = "weekly_or_event_driven"
    MONTHLY                = "monthly"
    QUARTERLY              = "quarterly"
    ANNUAL_REFRESH         = "annual_refresh"
    NONE                   = "none"


class WorkflowState(str, Enum):
    NEW_TARGET          = "new_target"
    SCREENED            = "screened"
    DILIGENCE_NEEDED    = "diligence_needed"
    READY_FOR_BD_REVIEW = "ready_for_bd_review"
    SENIOR_REVIEW       = "senior_review"
    OUTREACH_READY      = "outreach_ready"
    MONITORING          = "monitoring"
    BLOCKED             = "blocked"
    PASSED              = "passed"


# ---------------------------------------------------------------------------
# Routing thresholds — change here, nowhere else
# ---------------------------------------------------------------------------

_T: dict[str, float] = {
    # Pass
    "pass_layer1_max":          0.45,
    "pass_bd_action_max":       0.40,
    # Active pursuit
    "ap_bd_action_min":         0.75,
    "ap_pair_feasibility_min":  0.70,
    "ap_info_readiness_min":    0.60,
    # High-priority diligence
    "hpd_bd_action_min":        0.70,
    "hpd_info_readiness_max":   0.60,  # strictly less than
    # Partner / license
    "pl_asset_quality_min":     0.65,
    "pl_pair_feasibility_max":  0.65,
    # Option to acquire
    "ota_asset_quality_min":    0.60,
    "ota_catalyst_min":         0.60,
    "ota_pair_feasibility_min": 0.55,
    # Catalyst watch
    "cw_strategic_priority_min": 0.55,
    "cw_catalyst_min":           0.65,
    "cw_bd_action_max":          0.75,  # below active pursuit
    # Strategic watch
    "sw_strategic_priority_min": 0.70,
    "sw_deal_momentum_max":      0.45,
    # Relationship build
    "rb_strategic_priority_min": 0.65,
    "rb_acquirer_pull_min":      0.60,
    "rb_deal_momentum_max":      0.50,
    "rb_relationship_max":       0.40,
    # Acquirer mapping needed
    "amn_layer1_min":            0.65,
    "amn_pull_confidence_max":   0.50,
    # Remediation required
    "rr_severe_cap_max":         0.70,  # pair_level_cap <= this = severe
    # Urgency score
    "urgency_immediate_min":     0.80,
    "urgency_near_term_min":     0.65,
    "urgency_medium_term_min":   0.45,
    "urgency_watch_sp_min":      0.70,
    # Escalation
    "esc_ic_bd_score_min":       0.85,
    "esc_ic_feasibility_min":    0.75,
    # Route confidence
    "route_conf_min_for_ap":     0.50,
    # Deal structure
    "full_acq_feasibility_min":  0.70,
    "full_acq_rights_min":       0.70,
    "full_acq_afford_min":       0.70,
    "full_acq_integ_min":        0.60,
    "full_acq_anti_min":         0.65,
    "asset_acq_lead_share_min":  0.70,
    "global_lic_aq_min":         0.65,
    "global_lic_feasibility_max": 0.65,
    "cvr_valuation_gap_min":     0.60,
    "cvr_catalyst_risk_min":     0.60,
}


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class DiligenceTask(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: str
    question: str
    priority: str          # Critical / High / Medium / Low
    owner: str
    source_needed: list[str] = Field(default_factory=list)
    due_window: str = "before outreach"
    blocker_severity: str = "medium"
    expected_score_impact: str = ""
    generated_from: list[str] = Field(default_factory=list)


class RemediationStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    blocker: str
    remediation_path: str
    owner: str = "BD"
    feasibility: float = Field(default=0.50, ge=0.0, le=1.0)
    expected_effect: str = ""
    route_if_successful: Optional[str] = None
    route_if_unsuccessful: Optional[str] = None


class MonitoringTrigger(BaseModel):
    model_config = ConfigDict(frozen=True)

    trigger_type: str
    description: str
    direction: str          # upgrade / downgrade / refresh
    severity: str           # high / medium / low
    source_to_monitor: list[str] = Field(default_factory=list)
    expected_route_change: Optional[str] = None


class Layer4UpstreamScores(BaseModel):
    model_config = ConfigDict(frozen=True)

    layer1_score: Optional[float] = None
    layer2_score: Optional[float] = None
    layer3_adjusted_score: Optional[float] = None
    layer3_pair_feasibility_score: Optional[float] = None
    information_readiness: Optional[float] = None
    route_relevant_confidence: Optional[float] = None


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

_NEUTRAL = 0.50


class Layer4BDInputs(BaseModel):
    """All inputs for Layer 4 BD routing.

    Fields are Optional because upstream layers may not all be wired yet.
    Missing fields lower route_confidence and are tracked in missing_data.
    """
    model_config = ConfigDict(frozen=True)

    target_id: str
    acquirer_id: Optional[str] = None

    # --- Layer 0 signals ---
    target_passed_layer0: bool = True
    deal_type: Optional[str] = None
    hard_exclusions: list[str] = Field(default_factory=list)
    distress_flags: list[str] = Field(default_factory=list)
    layer0_data_confidence: float = Field(default=_NEUTRAL, ge=0.0, le=1.0)
    global_rights_available: bool = True
    regional_rights_available: bool = True

    # --- Layer 1 signals ---
    layer1_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    layer1_confidence: float = Field(default=_NEUTRAL, ge=0.0, le=1.0)
    asset_quality: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    strategic_scarcity: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    value_creation: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    transaction_setup: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    structural_cleanliness: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    layer1_thesis_type: Optional[str] = None
    layer1_positive_drivers: list[str] = Field(default_factory=list)
    layer1_negative_drivers: list[str] = Field(default_factory=list)
    layer1_missing_data: list[str] = Field(default_factory=list)
    # Convenience: is lead asset driving most value?
    lead_asset_value_share: float = Field(default=_NEUTRAL, ge=0.0, le=1.0)
    company_level_complexity_high: bool = False
    clinical_uncertainty_high: bool = False
    valuation_gap_high: bool = False
    binary_catalyst_risk_high: bool = False
    cost_to_complete_high: bool = False
    target_likely_wants_upside: bool = False
    seller_openness: float = Field(default=_NEUTRAL, ge=0.0, le=1.0)

    # --- Layer 2 signals ---
    bd_action_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    layer2_confidence: float = Field(default=_NEUTRAL, ge=0.0, le=1.0)
    strategic_priority: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    deal_momentum: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    acquirer_pull: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    acquirer_pull_confidence: float = Field(default=_NEUTRAL, ge=0.0, le=1.0)
    information_readiness: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    action_classification: Optional[str] = None
    expected_action_window: Optional[str] = None
    top_acquirers: list[str] = Field(default_factory=list)
    catalyst_proximity: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    financing_pressure: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    competitive_process_risk: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    buyer_universe_depth: float = Field(default=_NEUTRAL, ge=0.0, le=1.0)
    layer2_missing_data: list[str] = Field(default_factory=list)

    # --- Layer 3 signals ---
    layer3_adjusted_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    layer3_pair_feasibility_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    pair_level_cap: float = Field(default=1.0, ge=0.0, le=1.0)
    hard_fail: bool = False
    hard_fail_reasons: list[str] = Field(default_factory=list)
    active_caps: list[str] = Field(default_factory=list)
    layer3_confidence: float = Field(default=_NEUTRAL, ge=0.0, le=1.0)
    affordability_realism: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    consideration_realism: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    rights_control_fit: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    integration_capability: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    antitrust_feasibility: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    strategic_conflict_feasibility: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    process_closing_feasibility: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    diligence_blockers: list[str] = Field(default_factory=list)
    layer3_remediation_paths: list[str] = Field(default_factory=list)
    layer3_missing_data: list[str] = Field(default_factory=list)

    # Pair-level helper flags (can be derived or explicitly supplied)
    layer3_has_severe_cap: bool = False
    rights_control_data_missing: bool = False
    existing_relationship_strength: float = Field(default=_NEUTRAL, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class Layer4BDOutput(BaseModel):
    """Full Layer 4 BD Routing & Execution Playbook output."""
    model_config = ConfigDict(frozen=True)

    target_id: str
    acquirer_id: Optional[str]

    # Route
    route_class: RouteClass
    route_confidence: float = Field(..., ge=0.0, le=1.0)
    route_reason: str

    # Deal structure
    recommended_deal_structure: NewDealStructure
    secondary_deal_structures: list[NewDealStructure] = Field(default_factory=list)
    structure_confidence: float = Field(..., ge=0.0, le=1.0)
    structure_rationale: str = ""

    # Urgency / escalation / outreach
    urgency_level: UrgencyLevel
    escalation_level: EscalationLevel
    outreach_status: OutreachStatus
    outreach_reason: str = ""
    next_best_action: str

    # Execution detail
    required_diligence: list[DiligenceTask] = Field(default_factory=list)
    remediation_plan: list[RemediationStep] = Field(default_factory=list)

    # Monitoring
    monitoring_frequency: MonitoringFrequency
    upgrade_triggers: list[MonitoringTrigger] = Field(default_factory=list)
    downgrade_triggers: list[MonitoringTrigger] = Field(default_factory=list)
    refresh_triggers: list[MonitoringTrigger] = Field(default_factory=list)

    # Diagnostics
    key_blockers: list[str] = Field(default_factory=list)
    key_supporting_factors: list[str] = Field(default_factory=list)
    active_caps: list[str] = Field(default_factory=list)
    hard_fail_reasons: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    # Workflow
    owner_workflow_state: WorkflowState

    # Memo
    memo_summary: str
    plain_english_rationale: str

    # Upstream scores passthrough
    upstream_scores: Layer4UpstreamScores


# ---------------------------------------------------------------------------
# Backward compatibility mapping
# ---------------------------------------------------------------------------

LEGACY_ROUTE_MAP: dict[str, RouteClass] = {
    "pass":              RouteClass.PASS_DO_NOT_PURSUE,
    "data_insufficient": RouteClass.HIGH_PRIORITY_DILIGENCE,
    "strategic_radar":   RouteClass.STRATEGIC_WATCH,
    "relationship_build": RouteClass.RELATIONSHIP_BUILD,
    "catalyst_watch":    RouteClass.CATALYST_WATCH,
    "active_pursuit":    RouteClass.ACTIVE_PURSUIT,
    "process_ready":     RouteClass.ACTIVE_PURSUIT,
    "hard_fail":         RouteClass.PAIR_LEVEL_HARD_FAIL,
    "route_to_license":  RouteClass.PARTNER_OR_LICENSE_CANDIDATE,
    "monitor":           RouteClass.MONITOR_ONLY,
}


# ---------------------------------------------------------------------------
# 4A — Route classification
# ---------------------------------------------------------------------------

def classify_route(inp: Layer4BDInputs) -> tuple[RouteClass, str]:
    """Apply routing rules in strict priority order. Returns (route, reason)."""

    bd = inp.bd_action_score
    l1 = inp.layer1_score
    aq = inp.asset_quality or _NEUTRAL
    sp = inp.strategic_priority or _NEUTRAL
    dm = inp.deal_momentum or _NEUTRAL
    ap = inp.acquirer_pull or _NEUTRAL
    ir = inp.information_readiness or _NEUTRAL
    pf = inp.layer3_pair_feasibility_score or _NEUTRAL
    cp = inp.catalyst_proximity or 0.0

    # 0. Layer 0 hard exclusion
    if not inp.target_passed_layer0 or inp.hard_exclusions:
        excl = "; ".join(inp.hard_exclusions[:2]) if inp.hard_exclusions else "Layer 0 eligibility failed"
        return RouteClass.PASS_DO_NOT_PURSUE, f"Layer 0 hard exclusion: {excl}"

    # 1. Pair-level hard fail (Layer 3)
    if inp.hard_fail:
        reasons = "; ".join(inp.hard_fail_reasons[:2]) if inp.hard_fail_reasons else "Layer 3 hard fail"
        return RouteClass.PAIR_LEVEL_HARD_FAIL, f"Layer 3 hard fail: {reasons}"

    # 2. Pass — very low quality or very low BD action score
    if l1 is not None and l1 < _T["pass_layer1_max"]:
        return RouteClass.PASS_DO_NOT_PURSUE, f"Layer 1 score {l1:.2f} < {_T['pass_layer1_max']}"
    if bd is not None and bd < _T["pass_bd_action_max"]:
        return RouteClass.PASS_DO_NOT_PURSUE, f"BD action score {bd:.2f} < {_T['pass_bd_action_max']}"

    # 3. Active pursuit — high BD score, high feasibility, sufficient info readiness
    if (
        bd is not None
        and bd >= _T["ap_bd_action_min"]
        and pf >= _T["ap_pair_feasibility_min"]
        and ir >= _T["ap_info_readiness_min"]
        and not inp.hard_fail
    ):
        return (
            RouteClass.ACTIVE_PURSUIT,
            f"BD={bd:.2f}>={_T['ap_bd_action_min']}, "
            f"pf={pf:.2f}>={_T['ap_pair_feasibility_min']}, "
            f"ir={ir:.2f}>={_T['ap_info_readiness_min']}",
        )

    # 4. High-priority diligence — attractive but info readiness too low
    if (
        bd is not None
        and bd >= _T["hpd_bd_action_min"]
        and ir < _T["hpd_info_readiness_max"]
        and not inp.hard_fail
    ):
        return (
            RouteClass.HIGH_PRIORITY_DILIGENCE,
            f"BD={bd:.2f}>={_T['hpd_bd_action_min']} but ir={ir:.2f}<{_T['hpd_info_readiness_max']}",
        )

    # 5. Acquirer mapping needed — good asset, buyer universe unclear
    if (
        (l1 is not None and l1 >= _T["amn_layer1_min"])
        and inp.acquirer_pull_confidence < _T["amn_pull_confidence_max"]
    ):
        return (
            RouteClass.ACQUIRER_MAPPING_NEEDED,
            f"Layer 1={l1:.2f}>={_T['amn_layer1_min']} but "
            f"acquirer_pull_confidence={inp.acquirer_pull_confidence:.2f}<{_T['amn_pull_confidence_max']}",
        )

    # 6. Remediation required — severe cap with remediation path, no hard fail
    if (
        inp.layer3_has_severe_cap
        or (inp.pair_level_cap <= _T["rr_severe_cap_max"] and inp.pair_level_cap < 1.0)
    ) and inp.layer3_remediation_paths and not inp.hard_fail:
        return (
            RouteClass.REMEDIATION_REQUIRED,
            f"Severe pair_level_cap={inp.pair_level_cap:.2f} with "
            f"{len(inp.layer3_remediation_paths)} remediation path(s)",
        )

    # 7. Partner / license candidate — good asset quality, weak full-acq feasibility
    if (
        aq >= _T["pl_asset_quality_min"]
        and pf < _T["pl_pair_feasibility_max"]
        and not inp.hard_fail
    ):
        return (
            RouteClass.PARTNER_OR_LICENSE_CANDIDATE,
            f"asset_quality={aq:.2f}>={_T['pl_asset_quality_min']} but "
            f"pair_feasibility={pf:.2f}<{_T['pl_pair_feasibility_max']}",
        )

    # 8. Option-to-acquire — good asset, near-term catalyst, high uncertainty
    if (
        aq >= _T["ota_asset_quality_min"]
        and cp >= _T["ota_catalyst_min"]
        and inp.clinical_uncertainty_high
        and pf >= _T["ota_pair_feasibility_min"]
    ):
        return (
            RouteClass.OPTION_TO_ACQUIRE_CANDIDATE,
            f"aq={aq:.2f}, catalyst={cp:.2f}>={_T['ota_catalyst_min']}, "
            "clinical_uncertainty_high, pf sufficient",
        )

    # 9. Catalyst watch — strategic priority, catalyst near, BD score below active pursuit
    if (
        sp >= _T["cw_strategic_priority_min"]
        and cp >= _T["cw_catalyst_min"]
        and (bd is None or bd < _T["cw_bd_action_max"])
    ):
        return (
            RouteClass.CATALYST_WATCH,
            f"sp={sp:.2f}>={_T['cw_strategic_priority_min']}, "
            f"catalyst={cp:.2f}>={_T['cw_catalyst_min']}",
        )

    # 10. Relationship build
    if (
        sp >= _T["rb_strategic_priority_min"]
        and ap >= _T["rb_acquirer_pull_min"]
        and dm < _T["rb_deal_momentum_max"]
        and inp.existing_relationship_strength < _T["rb_relationship_max"]
    ):
        return (
            RouteClass.RELATIONSHIP_BUILD,
            f"sp={sp:.2f}, ap={ap:.2f}, dm={dm:.2f}<{_T['rb_deal_momentum_max']}, "
            f"rel={inp.existing_relationship_strength:.2f}<{_T['rb_relationship_max']}",
        )

    # 11. Strategic watch — high strategic priority but low deal momentum
    if sp >= _T["sw_strategic_priority_min"] and dm < _T["sw_deal_momentum_max"]:
        return (
            RouteClass.STRATEGIC_WATCH,
            f"sp={sp:.2f}>={_T['sw_strategic_priority_min']}, "
            f"dm={dm:.2f}<{_T['sw_deal_momentum_max']}",
        )

    # 12. Monitor only — moderate signals, not worth active BD
    if (l1 is not None and l1 >= 0.45) or (bd is not None and bd >= 0.40):
        return RouteClass.MONITOR_ONLY, "Moderate signals; no active BD trigger met"

    # Fallback
    return RouteClass.MONITOR_ONLY, "No routing condition met; default monitor"


# ---------------------------------------------------------------------------
# 4B — Deal structure recommendation
# ---------------------------------------------------------------------------

def recommend_deal_structure(
    inp: Layer4BDInputs,
    route: RouteClass,
) -> tuple[NewDealStructure, list[NewDealStructure], float, str]:
    """Return (primary, secondaries, confidence, rationale)."""

    # Hard fail / pass → no action
    if route in (RouteClass.PAIR_LEVEL_HARD_FAIL, RouteClass.PASS_DO_NOT_PURSUE):
        return NewDealStructure.NO_ACTION, [], 1.0, "Hard fail or pass; no transaction appropriate."

    aq = inp.asset_quality or _NEUTRAL
    pf = inp.layer3_pair_feasibility_score or _NEUTRAL
    rc = inp.rights_control_fit or _NEUTRAL
    af = inp.affordability_realism or _NEUTRAL
    ic = inp.integration_capability or _NEUTRAL
    anti = inp.antitrust_feasibility or _NEUTRAL
    cp = inp.catalyst_proximity or 0.0

    conf = min(inp.layer1_confidence, inp.layer3_confidence)

    # Full acquisition: clean rights, strong affordability, low antitrust
    if (
        not inp.hard_fail
        and pf >= _T["full_acq_feasibility_min"]
        and rc >= _T["full_acq_rights_min"]
        and af >= _T["full_acq_afford_min"]
        and ic >= _T["full_acq_integ_min"]
        and anti >= _T["full_acq_anti_min"]
    ):
        return (
            NewDealStructure.FULL_ACQUISITION,
            [NewDealStructure.STRUCTURED_ACQUISITION_WITH_MILESTONES],
            conf,
            "Clean rights, affordable, integration feasible, low antitrust risk.",
        )

    # CVR-heavy acquisition: acquisition feasible, valuation gap, binary catalyst
    if (
        not inp.hard_fail
        and pf >= 0.55
        and inp.valuation_gap_high
        and inp.binary_catalyst_risk_high
        and af >= 0.50
    ):
        return (
            NewDealStructure.CVR_HEAVY_ACQUISITION,
            [NewDealStructure.STRUCTURED_ACQUISITION_WITH_MILESTONES,
             NewDealStructure.OPTION_TO_ACQUIRE],
            conf,
            "Acquisition feasible; valuation gap and binary risk favour CVR structure.",
        )

    # Asset acquisition: lead asset drives value, company complexity high
    if (
        inp.lead_asset_value_share >= _T["asset_acq_lead_share_min"]
        and aq >= 0.65
        and inp.company_level_complexity_high
    ):
        return (
            NewDealStructure.ASSET_ACQUISITION,
            [NewDealStructure.GLOBAL_LICENSE],
            conf,
            "Lead asset drives most value; company-level complexity favours asset deal.",
        )

    # Option to acquire: good asset, catalyst near, clinical uncertainty
    if aq >= _T["ota_asset_quality_min"] and cp >= _T["ota_catalyst_min"] and inp.clinical_uncertainty_high:
        return (
            NewDealStructure.OPTION_TO_ACQUIRE,
            [NewDealStructure.CVR_HEAVY_ACQUISITION, NewDealStructure.OPTION_TO_LICENSE],
            conf,
            "Attractive asset with near-term catalyst and clinical uncertainty; option structure preferred.",
        )

    # Regional license: regional rights, global not available / not needed
    if inp.regional_rights_available and not inp.global_rights_available:
        return (
            NewDealStructure.REGIONAL_LICENSE,
            [NewDealStructure.CO_DEVELOPMENT],
            conf,
            "Global rights unavailable; regional license matches rights profile.",
        )

    # Global license: asset good, full acquisition weak, global rights available
    if (
        aq >= _T["global_lic_aq_min"]
        and pf < _T["global_lic_feasibility_max"]
        and inp.global_rights_available
    ):
        return (
            NewDealStructure.GLOBAL_LICENSE,
            [NewDealStructure.CO_DEVELOPMENT, NewDealStructure.OPTION_TO_LICENSE],
            conf,
            "Asset quality sufficient but full acquisition feasibility is low; global license preferred.",
        )

    # Co-development: high cost, clinical stage, risk-sharing makes sense
    if inp.cost_to_complete_high and aq >= 0.60:
        return (
            NewDealStructure.CO_DEVELOPMENT,
            [NewDealStructure.CO_COMMERCIALIZATION, NewDealStructure.OPTION_TO_LICENSE],
            conf,
            "High development cost and risk-sharing signal; co-development preferred.",
        )

    # Minority equity investment: relationship building, seller not ready
    if route == RouteClass.RELATIONSHIP_BUILD:
        return (
            NewDealStructure.MINORITY_EQUITY_INVESTMENT,
            [NewDealStructure.STRATEGIC_COLLABORATION],
            conf * 0.80,
            "Relationship build phase; minority equity establishes option value.",
        )

    # Strategic collaboration: strategic watch or early-stage
    if route in (RouteClass.STRATEGIC_WATCH, RouteClass.CATALYST_WATCH):
        return (
            NewDealStructure.STRATEGIC_COLLABORATION,
            [NewDealStructure.MONITOR_ONLY, NewDealStructure.OPTION_TO_ACQUIRE],
            conf * 0.80,
            "Strategic watch; collaboration preserves optionality before transaction.",
        )

    # Monitor only or remediation
    if route in (RouteClass.MONITOR_ONLY, RouteClass.REMEDIATION_REQUIRED,
                 RouteClass.ACQUIRER_MAPPING_NEEDED, RouteClass.HIGH_PRIORITY_DILIGENCE):
        return NewDealStructure.MONITOR_ONLY, [], conf * 0.70, "Route requires diligence/remediation before structure decision."

    return NewDealStructure.MONITOR_ONLY, [], 0.40, "Insufficient signals for structure recommendation."


# ---------------------------------------------------------------------------
# 4C — Urgency
# ---------------------------------------------------------------------------

def compute_urgency(inp: Layer4BDInputs, route: RouteClass) -> UrgencyLevel:
    """Compute urgency from weighted score of momentum signals."""
    if route in (RouteClass.PAIR_LEVEL_HARD_FAIL, RouteClass.PASS_DO_NOT_PURSUE):
        return UrgencyLevel.DORMANT_OR_PASS

    dm  = inp.deal_momentum      or _NEUTRAL
    cp  = inp.catalyst_proximity or 0.0
    fp  = inp.financing_pressure or 0.0
    cpr = inp.competitive_process_risk or 0.0
    ir  = inp.information_readiness or _NEUTRAL
    pf  = inp.layer3_pair_feasibility_score or _NEUTRAL

    # Weighted urgency score (only available signals)
    n_weights = sum([
        0.30, 0.25, 0.20, 0.15, 0.10
    ])
    urgency_score = (
        0.30 * dm
        + 0.25 * cp
        + 0.20 * fp
        + 0.15 * cpr
        + 0.10 * ir
    ) / n_weights

    if urgency_score >= _T["urgency_immediate_min"] and pf >= 0.70:
        return UrgencyLevel.IMMEDIATE_0_TO_30_DAYS
    if urgency_score >= _T["urgency_near_term_min"]:
        return UrgencyLevel.NEAR_TERM_1_TO_3_MONTHS
    if urgency_score >= _T["urgency_medium_term_min"]:
        return UrgencyLevel.MEDIUM_TERM_3_TO_12_MONTHS
    sp = inp.strategic_priority or 0.0
    if sp >= _T["urgency_watch_sp_min"] and dm < 0.45:
        return UrgencyLevel.WATCH_12_PLUS_MONTHS
    return UrgencyLevel.DORMANT_OR_PASS


# ---------------------------------------------------------------------------
# 4C — Escalation
# ---------------------------------------------------------------------------

def determine_escalation(
    inp: Layer4BDInputs,
    route: RouteClass,
) -> EscalationLevel:
    bd = inp.bd_action_score or 0.0
    pf = inp.layer3_pair_feasibility_score or _NEUTRAL

    if route == RouteClass.PAIR_LEVEL_HARD_FAIL:
        return EscalationLevel.NO_ESCALATION
    if route == RouteClass.PASS_DO_NOT_PURSUE:
        return EscalationLevel.NO_ESCALATION
    if route == RouteClass.ACTIVE_PURSUIT:
        if bd >= _T["esc_ic_bd_score_min"] and pf >= _T["esc_ic_feasibility_min"]:
            return EscalationLevel.INVESTMENT_COMMITTEE_PREP
        return EscalationLevel.SENIOR_BD_REVIEW
    if route == RouteClass.HIGH_PRIORITY_DILIGENCE:
        return EscalationLevel.BD_MANAGER_REVIEW if bd < 0.80 else EscalationLevel.SENIOR_BD_REVIEW
    if route in (RouteClass.CATALYST_WATCH, RouteClass.OPTION_TO_ACQUIRE_CANDIDATE):
        return EscalationLevel.BD_MANAGER_REVIEW
    if route in (RouteClass.STRATEGIC_WATCH, RouteClass.RELATIONSHIP_BUILD,
                 RouteClass.ACQUIRER_MAPPING_NEEDED):
        return EscalationLevel.ANALYST_REVIEW
    if route == RouteClass.REMEDIATION_REQUIRED:
        return EscalationLevel.BD_MANAGER_REVIEW
    if route == RouteClass.PARTNER_OR_LICENSE_CANDIDATE:
        return EscalationLevel.BD_MANAGER_REVIEW
    return EscalationLevel.ANALYST_REVIEW


# ---------------------------------------------------------------------------
# 7 — Outreach status
# ---------------------------------------------------------------------------

def determine_outreach_status(
    inp: Layer4BDInputs,
    route: RouteClass,
) -> tuple[OutreachStatus, str]:
    """Return (status, reason)."""

    if route == RouteClass.PAIR_LEVEL_HARD_FAIL:
        return OutreachStatus.BLOCKED, "Layer 3 hard fail: do not contact this acquirer-target pair."
    if route == RouteClass.PASS_DO_NOT_PURSUE:
        return OutreachStatus.DO_NOT_CONTACT_YET, "Target is not pursued; no outreach warranted."
    if inp.rights_control_data_missing or (
        inp.rights_control_fit is not None and inp.rights_control_fit < 0.40
    ):
        return (
            OutreachStatus.DO_NOT_CONTACT_YET,
            "Critical rights/control data missing or rights fit very low; validate before outreach.",
        )
    if route == RouteClass.ACTIVE_PURSUIT and (inp.information_readiness or _NEUTRAL) >= 0.60:
        return OutreachStatus.OUTREACH_READY, "Active pursuit with sufficient information readiness."
    if route in (RouteClass.HIGH_PRIORITY_DILIGENCE, RouteClass.REMEDIATION_REQUIRED):
        return (
            OutreachStatus.DO_NOT_CONTACT_YET,
            f"Route is {route.value}; complete diligence/remediation before outreach.",
        )
    if route in (RouteClass.RELATIONSHIP_BUILD, RouteClass.STRATEGIC_WATCH):
        return OutreachStatus.SOFT_TOUCH_ONLY, "Relationship/watch stage; non-transactional contact only."
    if route == RouteClass.OPTION_TO_ACQUIRE_CANDIDATE:
        return OutreachStatus.SOFT_TOUCH_ONLY, "Option candidate; soft touch to explore structure."
    if route == RouteClass.PARTNER_OR_LICENSE_CANDIDATE:
        return OutreachStatus.SOFT_TOUCH_ONLY, "License/partner candidate; explore non-transactional contact."
    if route in (RouteClass.CATALYST_WATCH, RouteClass.MONITOR_ONLY):
        return OutreachStatus.MONITOR_ONLY, "Monitoring phase; no active outreach yet."
    if route == RouteClass.ACQUIRER_MAPPING_NEEDED:
        return OutreachStatus.DO_NOT_CONTACT_YET, "Acquirer mapping incomplete; do not contact yet."
    return OutreachStatus.DO_NOT_CONTACT_YET, "Conditions for outreach not yet met."


# ---------------------------------------------------------------------------
# 4D — Diligence workplan
# ---------------------------------------------------------------------------

def generate_diligence_tasks(inp: Layer4BDInputs) -> list[DiligenceTask]:
    tasks: list[DiligenceTask] = []

    # Rights / contracts — always critical when rights fit is low or data missing
    rc = inp.rights_control_fit
    if rc is None or rc < 0.65 or inp.rights_control_data_missing:
        tasks.append(DiligenceTask(
            category="Rights / contracts",
            question="Review ROFR, ROFN, opt-in rights, consent, change-of-control, "
                     "regional rights, and collaboration agreement.",
            priority="Critical",
            owner="Legal / BD contracts",
            source_needed=["10-K exhibits", "collaboration agreement", "licensing agreement", "legal review"],
            due_window="before outreach",
            blocker_severity="high",
            expected_score_impact="Could remove hard fail or severe cap if rights are cleaner than assumed.",
            generated_from=["rights_control_fit_low", "rights_control_data_missing"],
        ))

    # Antitrust — when antitrust feasibility is low
    anti = inp.antitrust_feasibility
    if anti is not None and anti < 0.65:
        tasks.append(DiligenceTask(
            category="Antitrust",
            question="Map product and pipeline overlap; estimate divestiture risk, "
                     "market concentration, and jurisdictional review complexity.",
            priority="Critical" if anti < 0.45 else "High",
            owner="Legal / Antitrust",
            source_needed=["product label", "pipeline databases", "market share data", "DOJ/FTC precedent"],
            due_window="before deal model",
            blocker_severity="high" if anti < 0.45 else "medium",
            expected_score_impact="Could remove antitrust cap or avoid hard fail.",
            generated_from=["antitrust_feasibility_low"],
        ))

    # Clinical / scientific — when layer1_score is low or asset_quality uncertain
    aq = inp.asset_quality
    if aq is None or aq < 0.65:
        tasks.append(DiligenceTask(
            category="Clinical / scientific",
            question="Validate trial design, endpoint quality, effect size, safety, "
                     "subgroup consistency, and durability.",
            priority="High",
            owner="Clinical",
            source_needed=["trial publication", "ClinicalTrials.gov", "company deck", "FDA documents"],
            due_window="before outreach",
            blocker_severity="high",
            expected_score_impact="Low asset quality is the primary driver of a pass decision.",
            generated_from=["asset_quality_low_or_missing"],
        ))

    # Acquirer profile / buyer mapping — when acquirer pull confidence is low
    if inp.acquirer_pull_confidence < 0.55 or not inp.top_acquirers:
        tasks.append(DiligenceTask(
            category="Acquirer profile / buyer mapping",
            question="Refresh acquirer profile: recent BD commentary, pipeline gaps, "
                     "recent deals, stated strategic priorities, and BD team contacts.",
            priority="High",
            owner="BD / Analyst",
            source_needed=["earnings calls", "investor day transcripts", "pipeline databases", "press releases"],
            due_window="within 30 days",
            blocker_severity="medium",
            expected_score_impact="Low acquirer pull confidence blocks ACTIVE_PURSUIT routing.",
            generated_from=["acquirer_pull_confidence_low"],
        ))

    # Financial / valuation — when affordability is uncertain or information readiness low
    af = inp.affordability_realism
    ir = inp.information_readiness or _NEUTRAL
    if (af is not None and af < 0.60) or ir < 0.55:
        tasks.append(DiligenceTask(
            category="Financial / valuation",
            question="Test cash/debt/stock/CVR structures and acquirer capital allocation limits; "
                     "refresh EV, net cash, implied asset value, and premium-adjusted rNPV.",
            priority="High",
            owner="Finance / BD",
            source_needed=["balance sheet", "credit ratings", "analyst models", "comparable deals"],
            due_window="before deal model",
            blocker_severity="medium",
            expected_score_impact="Affordability hard fail or severe cap may be avoidable.",
            generated_from=["affordability_low", "information_readiness_low"],
        ))

    # Integration — when integration capability is low
    ic = inp.integration_capability
    if ic is not None and ic < 0.55:
        tasks.append(DiligenceTask(
            category="Integration",
            question="Assess commercial, manufacturing, payer, geographic, systems, "
                     "and medical affairs fit.",
            priority="Medium",
            owner="Integration / Commercial / CMC",
            source_needed=["commercial org chart", "CMC package", "payer access data"],
            due_window="before term sheet",
            blocker_severity="medium",
            expected_score_impact="Integration cap may be removed with CDMO or co-promote structure.",
            generated_from=["integration_capability_low"],
        ))

    return tasks


# ---------------------------------------------------------------------------
# 4E — Remediation plan
# ---------------------------------------------------------------------------

def generate_remediation_plan(inp: Layer4BDInputs) -> list[RemediationStep]:
    steps: list[RemediationStep] = []

    # Layer 3 remediation paths → convert to RemediationStep
    for path_text in inp.layer3_remediation_paths:
        steps.append(RemediationStep(
            blocker="Layer 3 blocker",
            remediation_path=path_text,
            owner="BD / Legal",
            feasibility=0.55,
            expected_effect="Reduces or removes cap enabling higher BD route.",
            route_if_successful=RouteClass.PARTNER_OR_LICENSE_CANDIDATE.value,
            route_if_unsuccessful=RouteClass.MONITOR_ONLY.value,
        ))

    # Affordability remediation
    af = inp.affordability_realism
    if af is not None and af < 0.60:
        steps.append(RemediationStep(
            blocker="affordability_constraint",
            remediation_path="Consider license, option-to-acquire, CVR-heavy acquisition, "
                             "asset acquisition, or staged milestones instead of full acquisition.",
            owner="BD / Finance",
            feasibility=0.60,
            expected_effect="Opens license or option route even when full acquisition infeasible.",
            route_if_successful=RouteClass.PARTNER_OR_LICENSE_CANDIDATE.value,
            route_if_unsuccessful=RouteClass.PASS_DO_NOT_PURSUE.value,
        ))

    # Rights / ROFR remediation
    rc = inp.rights_control_fit
    if rc is not None and rc < 0.60:
        steps.append(RemediationStep(
            blocker="rights_control_blocker",
            remediation_path="Determine whether existing partner can waive ROFR, "
                             "whether asset carve-out is possible, or whether regional license is feasible.",
            owner="Legal / BD",
            feasibility=0.45,
            expected_effect="Removes ROFR cap; may open ACTIVE_PURSUIT for existing partner.",
            route_if_successful=RouteClass.ACTIVE_PURSUIT.value,
            route_if_unsuccessful=RouteClass.PAIR_LEVEL_HARD_FAIL.value,
        ))

    # Antitrust remediation
    anti = inp.antitrust_feasibility
    if anti is not None and anti < 0.55:
        steps.append(RemediationStep(
            blocker="antitrust_risk",
            remediation_path="Assess divestiture scope; consider narrower asset deal or license; "
                             "pre-clear with DOJ/FTC if risk is manageable.",
            owner="Legal / Antitrust",
            feasibility=0.40,
            expected_effect="May convert hard fail to manageable cap with divestiture.",
            route_if_successful=RouteClass.PARTNER_OR_LICENSE_CANDIDATE.value,
            route_if_unsuccessful=RouteClass.PASS_DO_NOT_PURSUE.value,
        ))

    # Clinical uncertainty
    if inp.clinical_uncertainty_high and (inp.asset_quality or 0.0) >= 0.55:
        steps.append(RemediationStep(
            blocker="clinical_uncertainty",
            remediation_path="Use option-to-acquire, option-to-license, CVR-heavy acquisition, "
                             "or wait for catalyst data before committing full deal economics.",
            owner="BD / Clinical",
            feasibility=0.65,
            expected_effect="Converts PASS_DO_NOT_PURSUE or MONITOR_ONLY to OPTION_TO_ACQUIRE_CANDIDATE.",
            route_if_successful=RouteClass.OPTION_TO_ACQUIRE_CANDIDATE.value,
            route_if_unsuccessful=RouteClass.CATALYST_WATCH.value,
        ))

    return steps


# ---------------------------------------------------------------------------
# 4F — Monitoring triggers
# ---------------------------------------------------------------------------

def generate_monitoring_triggers(
    inp: Layer4BDInputs,
    route: RouteClass,
) -> tuple[list[MonitoringTrigger], list[MonitoringTrigger], list[MonitoringTrigger]]:
    """Return (upgrade_triggers, downgrade_triggers, refresh_triggers)."""
    upgrade: list[MonitoringTrigger] = []
    downgrade: list[MonitoringTrigger] = []
    refresh: list[MonitoringTrigger] = []

    # Always add clinical catalyst upgrade / downgrade
    upgrade.append(MonitoringTrigger(
        trigger_type="clinical_catalyst",
        description="Positive Phase 2/3 data with clean safety and durable effect",
        direction="upgrade",
        severity="high",
        source_to_monitor=["ClinicalTrials.gov", "company press release", "NEJM/JAMA/Lancet"],
        expected_route_change=RouteClass.ACTIVE_PURSUIT.value,
    ))
    downgrade.append(MonitoringTrigger(
        trigger_type="clinical_catalyst",
        description="Negative clinical data, safety signal, or FDA clinical hold",
        direction="downgrade",
        severity="high",
        source_to_monitor=["ClinicalTrials.gov", "FDA safety database", "press release"],
        expected_route_change=RouteClass.PASS_DO_NOT_PURSUE.value,
    ))

    # Financing event
    upgrade.append(MonitoringTrigger(
        trigger_type="financing_event",
        description="Cash runway falls below 12 months; seller pressure increases",
        direction="upgrade",
        severity="high",
        source_to_monitor=["10-Q cash burn", "press releases", "analyst estimates"],
        expected_route_change=RouteClass.ACTIVE_PURSUIT.value,
    ))
    downgrade.append(MonitoringTrigger(
        trigger_type="financing_event",
        description="Target completes large financing, extending runway >24 months",
        direction="downgrade",
        severity="medium",
        source_to_monitor=["SEC filings", "press releases"],
        expected_route_change=RouteClass.STRATEGIC_WATCH.value,
    ))

    # M&A comparables
    upgrade.append(MonitoringTrigger(
        trigger_type="comparable_deal",
        description="Comparable deal in same TA at premium valuation; or competitor acquires similar asset",
        direction="upgrade",
        severity="medium",
        source_to_monitor=["M&A databases", "press releases", "sell-side research"],
        expected_route_change=RouteClass.HIGH_PRIORITY_DILIGENCE.value,
    ))

    # Strategic review
    upgrade.append(MonitoringTrigger(
        trigger_type="governance_change",
        description="Target announces strategic review, hires investment banker, or activist takes board seat",
        direction="upgrade",
        severity="high",
        source_to_monitor=["SEC 8-K", "press release", "board filings"],
        expected_route_change=RouteClass.ACTIVE_PURSUIT.value,
    ))

    # Acquirer pipeline failure
    upgrade.append(MonitoringTrigger(
        trigger_type="acquirer_pipeline_failure",
        description="Acquirer's competing internal program fails, increasing gap urgency",
        direction="upgrade",
        severity="medium",
        source_to_monitor=["acquirer earnings", "press releases"],
        expected_route_change=RouteClass.ACTIVE_PURSUIT.value,
    ))

    # Standard refresh triggers
    for event in [
        "quarterly_earnings", "new_10Q_10K", "investor_day", "major_medical_conference",
        "clinicaltrials_gov_update", "competitor_readout", "ma_deal_in_same_ta",
    ]:
        refresh.append(MonitoringTrigger(
            trigger_type="periodic_refresh",
            description=f"Scheduled refresh: {event.replace('_', ' ')}",
            direction="refresh",
            severity="low",
            source_to_monitor=["SEC filings", "company website", "conference program"],
        ))

    return upgrade, downgrade, refresh


# ---------------------------------------------------------------------------
# Monitoring frequency mapping
# ---------------------------------------------------------------------------

_MONITORING_FREQUENCY: dict[RouteClass, MonitoringFrequency] = {
    RouteClass.ACTIVE_PURSUIT:               MonitoringFrequency.WEEKLY,
    RouteClass.HIGH_PRIORITY_DILIGENCE:      MonitoringFrequency.WEEKLY,
    RouteClass.PARTNER_OR_LICENSE_CANDIDATE: MonitoringFrequency.WEEKLY,
    RouteClass.OPTION_TO_ACQUIRE_CANDIDATE:  MonitoringFrequency.WEEKLY_OR_EVENT_DRIVEN,
    RouteClass.CATALYST_WATCH:               MonitoringFrequency.WEEKLY_OR_EVENT_DRIVEN,
    RouteClass.STRATEGIC_WATCH:              MonitoringFrequency.MONTHLY,
    RouteClass.RELATIONSHIP_BUILD:           MonitoringFrequency.MONTHLY,
    RouteClass.ACQUIRER_MAPPING_NEEDED:      MonitoringFrequency.MONTHLY,
    RouteClass.REMEDIATION_REQUIRED:         MonitoringFrequency.MONTHLY,
    RouteClass.MONITOR_ONLY:                 MonitoringFrequency.QUARTERLY,
    RouteClass.PASS_DO_NOT_PURSUE:           MonitoringFrequency.ANNUAL_REFRESH,
    RouteClass.PAIR_LEVEL_HARD_FAIL:         MonitoringFrequency.NONE,
}

_WORKFLOW_STATE: dict[RouteClass, WorkflowState] = {
    RouteClass.ACTIVE_PURSUIT:               WorkflowState.READY_FOR_BD_REVIEW,
    RouteClass.HIGH_PRIORITY_DILIGENCE:      WorkflowState.DILIGENCE_NEEDED,
    RouteClass.PARTNER_OR_LICENSE_CANDIDATE: WorkflowState.READY_FOR_BD_REVIEW,
    RouteClass.OPTION_TO_ACQUIRE_CANDIDATE:  WorkflowState.READY_FOR_BD_REVIEW,
    RouteClass.CATALYST_WATCH:               WorkflowState.MONITORING,
    RouteClass.STRATEGIC_WATCH:              WorkflowState.MONITORING,
    RouteClass.RELATIONSHIP_BUILD:           WorkflowState.MONITORING,
    RouteClass.ACQUIRER_MAPPING_NEEDED:      WorkflowState.DILIGENCE_NEEDED,
    RouteClass.REMEDIATION_REQUIRED:         WorkflowState.BLOCKED,
    RouteClass.MONITOR_ONLY:                 WorkflowState.MONITORING,
    RouteClass.PASS_DO_NOT_PURSUE:           WorkflowState.PASSED,
    RouteClass.PAIR_LEVEL_HARD_FAIL:         WorkflowState.BLOCKED,
}

_NEXT_BEST_ACTION: dict[RouteClass, str] = {
    RouteClass.ACTIVE_PURSUIT:
        "Prepare internal BD memo and begin appropriate outreach/diligence.",
    RouteClass.HIGH_PRIORITY_DILIGENCE:
        "Complete critical diligence items before outreach.",
    RouteClass.PARTNER_OR_LICENSE_CANDIDATE:
        "Draft license/partnership term sheet and identify BD contact.",
    RouteClass.OPTION_TO_ACQUIRE_CANDIDATE:
        "Evaluate option economics and post-catalyst acquisition trigger.",
    RouteClass.CATALYST_WATCH:
        "Monitor catalyst and update valuation / route immediately after event.",
    RouteClass.STRATEGIC_WATCH:
        "Track quarterly updates, financing, management commentary, and competitor events.",
    RouteClass.RELATIONSHIP_BUILD:
        "Begin non-transactional relationship coverage (conferences, scientific exchange).",
    RouteClass.ACQUIRER_MAPPING_NEEDED:
        "Map top 10 likely buyers and refresh acquirer profiles.",
    RouteClass.REMEDIATION_REQUIRED:
        "Execute remediation plan; re-evaluate route after resolution.",
    RouteClass.MONITOR_ONLY:
        "Set quarterly review flag; monitor for upgrade triggers.",
    RouteClass.PASS_DO_NOT_PURSUE:
        "Archive with reason code; set 12-month revisit flag.",
    RouteClass.PAIR_LEVEL_HARD_FAIL:
        "Do not pursue this acquirer-target pair unless blocker is remediated.",
}


# ---------------------------------------------------------------------------
# 4G — Route confidence
# ---------------------------------------------------------------------------

def _compute_route_confidence(inp: Layer4BDInputs) -> tuple[float, list[str]]:
    """Compute route_confidence. Returns (score, missing_data)."""
    missing: list[str] = list(inp.layer1_missing_data) + list(inp.layer2_missing_data) + list(inp.layer3_missing_data)
    weights_used: list[tuple[float, float]] = []  # (weight, value)

    if inp.layer1_score is not None:
        weights_used.append((0.30, inp.layer1_confidence))
    else:
        missing.append("layer1_score")

    if inp.bd_action_score is not None:
        weights_used.append((0.25, inp.layer2_confidence))
    else:
        missing.append("bd_action_score")

    if inp.layer3_adjusted_score is not None or inp.hard_fail:
        weights_used.append((0.25, inp.layer3_confidence))
    else:
        missing.append("layer3_adjusted_score")

    if inp.information_readiness is not None:
        weights_used.append((0.20, inp.information_readiness))
    else:
        missing.append("information_readiness")

    if not weights_used:
        return 0.30, missing

    total_weight = sum(w for w, _ in weights_used)
    raw = sum(w * v for w, v in weights_used) / total_weight
    return max(0.0, min(1.0, round(raw, 4))), missing


# ---------------------------------------------------------------------------
# 4G — Memo
# ---------------------------------------------------------------------------

def generate_memo_summary(
    inp: Layer4BDInputs,
    route: RouteClass,
    structure: NewDealStructure,
    urgency: UrgencyLevel,
    blockers: list[str],
    remediation: list[RemediationStep],
    diligence: list[DiligenceTask],
    route_reason: str,
) -> tuple[str, str]:
    """Return (memo_summary, plain_english_rationale)."""
    bd = inp.bd_action_score
    l1 = inp.layer1_score
    pf = inp.layer3_pair_feasibility_score
    cp = inp.catalyst_proximity or 0.0

    route_label = route.value.replace("_", " ").title()
    struct_label = structure.value.replace("_", " ").title()
    urgency_label = urgency.value.replace("_", " ").title()
    acq = inp.acquirer_id or "unspecified acquirer"

    # Key blockers text
    blockers_text = "; ".join(blockers[:3]) if blockers else "None identified"

    # Next diligence steps
    top_diligence = "; ".join(
        f"{t.category} [{t.priority}]" for t in diligence[:3]
    ) if diligence else "No outstanding diligence."

    # Remediation text
    remed_text = "; ".join(
        r.blocker for r in remediation[:2]
    ) if remediation else "No active remediation required."

    bd_str = f"{bd:.2f}" if bd is not None else "N/A"
    l1_str = f"{l1:.2f}" if l1 is not None else "N/A"
    pf_str = f"{pf:.2f}" if pf is not None else "N/A"

    memo = (
        f"RECOMMENDATION: {route_label} — {struct_label}\n"
        f"Target: {inp.target_id} | Acquirer: {acq} | Urgency: {urgency_label}\n"
        f"BD Action Score: {bd_str} | "
        f"Layer 1: {l1_str} | "
        f"Pair Feasibility: {pf_str}\n"
        f"Key Blockers: {blockers_text}\n"
        f"Remediation: {remed_text}\n"
        f"Next Diligence: {top_diligence}\n"
        f"Upgrade Trigger: Positive clinical data, financing pressure, or comparable deal.\n"
        f"Downgrade Trigger: Negative data, safety signal, or target completes large financing."
    )

    rationale = (
        f"The target {inp.target_id} is routed to {route_label} for {acq}. "
        f"Reason: {route_reason}. "
    )
    if route == RouteClass.ACTIVE_PURSUIT:
        rationale += (
            "All key conditions are met: strong BD action score, acceptable pair feasibility, "
            "and sufficient information readiness. Outreach can begin."
        )
    elif route == RouteClass.HIGH_PRIORITY_DILIGENCE:
        rationale += (
            "BD action score is strong but information readiness is insufficient for outreach. "
            "Complete critical diligence before engaging."
        )
    elif route == RouteClass.CATALYST_WATCH:
        rationale += (
            f"A near-term catalyst (proximity={cp:.2f}) is approaching. "
            "Full acquisition before the catalyst would overpay for unresolved risk. "
            "Monitor and update route immediately after the event."
        )
    elif route == RouteClass.PAIR_LEVEL_HARD_FAIL:
        rationale += (
            "This specific acquirer-target pair is not executable due to hard blockers from Layer 3. "
            "The target may still be viable for other acquirers. "
            "Do not proceed unless the named blocker is resolved."
        )
    elif route == RouteClass.PARTNER_OR_LICENSE_CANDIDATE:
        rationale += (
            "Asset quality is sufficient for a licensing or partnership deal, "
            "but full acquisition feasibility is too low. "
            "Recommend exploring license, co-development, or option structure."
        )
    else:
        rationale += (
            f"Recommended structure is {struct_label}. "
            f"Review blockers and execute next best action."
        )

    return memo, rationale


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def route_layer4_opportunity(inputs: Layer4BDInputs) -> Layer4BDOutput:
    """Layer 4 BD Routing & Execution Playbook.

    Consumes Layer 0–3 outputs and produces a complete BD action recommendation:
    route class, deal structure, urgency, escalation, outreach status, diligence
    workplan, remediation plan, monitoring triggers, and memo output.

    Args:
        inputs: Layer4BDInputs with all upstream signals.

    Returns:
        Layer4BDOutput with full BD playbook.
    """
    warnings: list[str] = []

    # 1. Route classification
    route, route_reason = classify_route(inputs)

    # 2. Route confidence
    route_confidence, missing_data = _compute_route_confidence(inputs)
    if route_confidence < _T["route_conf_min_for_ap"] and route == RouteClass.ACTIVE_PURSUIT:
        # Downgrade to high-priority diligence when confidence too low
        warnings.append(
            f"route_confidence={route_confidence:.2f} < {_T['route_conf_min_for_ap']}; "
            "downgraded from ACTIVE_PURSUIT to HIGH_PRIORITY_DILIGENCE"
        )
        route = RouteClass.HIGH_PRIORITY_DILIGENCE
        route_reason = f"Low route confidence ({route_confidence:.2f}) prevents ACTIVE_PURSUIT."

    # 3. Deal structure
    structure, secondaries, struct_conf, struct_rationale = recommend_deal_structure(inputs, route)

    # 4. Urgency
    urgency = compute_urgency(inputs, route)

    # 5. Escalation
    escalation = determine_escalation(inputs, route)

    # 6. Outreach
    outreach_status, outreach_reason = determine_outreach_status(inputs, route)

    # 7. Diligence workplan
    diligence_tasks = generate_diligence_tasks(inputs)

    # 8. Remediation plan
    remediation_steps = generate_remediation_plan(inputs)

    # 9. Monitoring
    upgrade_t, downgrade_t, refresh_t = generate_monitoring_triggers(inputs, route)
    monitoring_freq = _MONITORING_FREQUENCY.get(route, MonitoringFrequency.QUARTERLY)

    # 10. Key blockers and supporting factors
    blockers = list(inputs.hard_fail_reasons) + list(inputs.diligence_blockers)
    if inputs.active_caps:
        blockers += [f"active_cap: {c}" for c in inputs.active_caps[:3]]
    supporting = list(inputs.layer1_positive_drivers)[:3]

    # 11. Memo
    memo_text, rationale = generate_memo_summary(
        inputs, route, structure, urgency,
        blockers, remediation_steps, diligence_tasks, route_reason,
    )

    # 12. Upstream scores passthrough
    upstream = Layer4UpstreamScores(
        layer1_score=inputs.layer1_score,
        layer2_score=inputs.bd_action_score,
        layer3_adjusted_score=inputs.layer3_adjusted_score,
        layer3_pair_feasibility_score=inputs.layer3_pair_feasibility_score,
        information_readiness=inputs.information_readiness,
        route_relevant_confidence=route_confidence,
    )

    return Layer4BDOutput(
        target_id=inputs.target_id,
        acquirer_id=inputs.acquirer_id,
        route_class=route,
        route_confidence=route_confidence,
        route_reason=route_reason,
        recommended_deal_structure=structure,
        secondary_deal_structures=secondaries,
        structure_confidence=struct_conf,
        structure_rationale=struct_rationale,
        urgency_level=urgency,
        escalation_level=escalation,
        outreach_status=outreach_status,
        outreach_reason=outreach_reason,
        next_best_action=_NEXT_BEST_ACTION[route],
        required_diligence=diligence_tasks,
        remediation_plan=remediation_steps,
        monitoring_frequency=monitoring_freq,
        upgrade_triggers=upgrade_t,
        downgrade_triggers=downgrade_t,
        refresh_triggers=refresh_t,
        key_blockers=blockers,
        key_supporting_factors=supporting,
        active_caps=list(inputs.active_caps),
        hard_fail_reasons=list(inputs.hard_fail_reasons),
        missing_data=missing_data,
        warnings=warnings,
        owner_workflow_state=_WORKFLOW_STATE[route],
        memo_summary=memo_text,
        plain_english_rationale=rationale,
        upstream_scores=upstream,
    )
