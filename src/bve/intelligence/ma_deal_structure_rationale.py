"""
Deal Structure Rationale — Block 3.

Connects BuyerTargetThesis + TransactionRealismScore → a specific deal structure
recommendation with human-readable rationale.

Routing logic (priority order):
  1. PASS thesis → NO_ACTION
  2. BLOCKING conflict in thesis → NO_ACTION
  3. All inputs unknown (low conf) → DILIGENCE_FIRST
  4. STRONG_BUY + HIGH realism → FULL_ACQUISITION
  5. STRONG_BUY + MODERATE/MODERATE_HIGH realism → STRUCTURED_ACQUISITION_WITH_MILESTONES
  6. BUY + HIGH/MODERATE_HIGH realism → FULL_ACQUISITION or STRUCTURED
  7. BUY + MODERATE/MODERATE_LOW realism → OPTION_TO_ACQUIRE
  8. MONITOR thesis → MONITOR_ONLY
  9. Fallback → DILIGENCE_FIRST

ROFR present → steer toward STRUCTURED or OPTION structures and add caveat.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from bve.intelligence.ma_buyer_thesis import BuyerTargetThesis, UnderwriteThesis, ConflictLevel
from bve.intelligence.ma_transaction_realism import TransactionRealismScore


# ---------------------------------------------------------------------------
# Enum
# ---------------------------------------------------------------------------

class RecommendedStructure(str, Enum):
    FULL_ACQUISITION = "full_acquisition"
    STRUCTURED_ACQUISITION_WITH_MILESTONES = "structured_acquisition_with_milestones"
    OPTION_TO_ACQUIRE = "option_to_acquire"
    CO_DEVELOPMENT = "co_development"
    MINORITY_EQUITY_INVESTMENT = "minority_equity_investment"
    DILIGENCE_FIRST = "diligence_first"
    MONITOR_ONLY = "monitor_only"
    NO_ACTION = "no_action"


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class DealStructureRationale(BaseModel):
    model_config = ConfigDict(frozen=True)

    recommended_structure: RecommendedStructure
    rationale_text: str
    overall_confidence: float = Field(..., ge=0.0, le=1.0)
    caveats: list[str] = Field(default_factory=list)
    diligence_items: list[str] = Field(default_factory=list)
    thesis_tier: str = ""
    realism_label: str = ""

    # Block 6 management quality overlay (optional)
    management_risk_band: Optional[str] = None
    management_gate: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))


def _build_rationale(
    structure: RecommendedStructure,
    thesis: BuyerTargetThesis,
    realism: TransactionRealismScore,
) -> str:
    parts = [
        f"Buyer thesis: {thesis.underwrite_thesis.value} "
        f"(mandate={thesis.mandate_score:.2f}, conflict={thesis.conflict_level.value}).",
        f"Transaction realism: {realism.realism_label} "
        f"(seller_readiness={realism.seller_readiness_score:.2f}, "
        f"price_alignment={realism.price_alignment_score:.2f}).",
        f"Recommended structure: {structure.value.replace('_', ' ')}.",
    ]
    return " ".join(parts)


def _compute_confidence(thesis: BuyerTargetThesis, realism: TransactionRealismScore) -> float:
    return _clamp(
        0.55 * thesis.overall_confidence
        + 0.45 * realism.overall_confidence
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_deal_structure_rationale(
    *,
    thesis: BuyerTargetThesis,
    realism: TransactionRealismScore,
    management_quality=None,
) -> DealStructureRationale:
    """
    Produce a DealStructureRationale from BuyerTargetThesis + TransactionRealismScore.

    Routing is deterministic and priority-ordered. Confidence propagates from
    both inputs proportionally.

    management_quality: optional ManagementQualityScore — when provided, weak trial
    execution or poor capital allocation can bias the structure recommendation toward
    staged/option structures. Governance risk adds a caveat. Does NOT hard-kill.
    """
    caveats: list[str] = []
    diligence_items: list[list[str]] = [realism.diligence_items]

    # Collect friction context
    rofr_friction = any("rofr" in note.lower() for note in realism.friction_notes)
    if rofr_friction:
        caveats.append("rofr_present:legal_review_required_before_outreach")

    # Block 6: extract management signals (do not hard-kill; bias structure only)
    mgmt_risk_band: Optional[str] = None
    mgmt_gate: Optional[str] = None
    _mgmt_weak_trial_design = False
    _mgmt_poor_capital_allocation = False
    _mgmt_governance_risk = False
    _mgmt_unknown = False
    if management_quality is not None:
        mgmt_risk_band = management_quality.risk_band.value
        mgmt_gate = management_quality.gate.value
        bd = management_quality.component_breakdown
        if bd.get("trial_design_judgment", 1.0) < 0.40:
            _mgmt_weak_trial_design = True
            caveats.append("management_trial_design_risk:consider_staged_structure")
        if bd.get("capital_allocation_discipline", 1.0) < 0.35:
            _mgmt_poor_capital_allocation = True
            caveats.append("management_capital_risk:prefer_milestone_heavy_structure")
        if bd.get("governance_alignment", 1.0) < 0.35:
            _mgmt_governance_risk = True
            caveats.append("management_governance_risk:legal_review_required")
        if mgmt_risk_band == "unknown":
            _mgmt_unknown = True
            diligence_items.append(["management_quality_unknown:diligence_required"])

    # Collect missing diligence items
    flat_diligence = list(dict.fromkeys(
        item for sublist in diligence_items for item in sublist
    ))

    # -------------------------------------------------------------------
    # Priority routing
    # -------------------------------------------------------------------

    # 1. PASS thesis or BLOCKING conflict → no action
    if (thesis.underwrite_thesis == UnderwriteThesis.PASS
            or thesis.conflict_level == ConflictLevel.BLOCKING):
        structure = RecommendedStructure.NO_ACTION
        rationale = (
            f"Buyer thesis is {thesis.underwrite_thesis.value} "
            f"(conflict={thesis.conflict_level.value}). No action recommended."
        )
        return DealStructureRationale(
            recommended_structure=structure,
            rationale_text=rationale,
            overall_confidence=_compute_confidence(thesis, realism),
            caveats=caveats,
            diligence_items=flat_diligence,
            thesis_tier=thesis.underwrite_thesis.value,
            realism_label=realism.realism_label,
            management_risk_band=mgmt_risk_band,
            management_gate=mgmt_gate,
        )

    # 2. Very low overall confidence → diligence first
    overall_conf = _compute_confidence(thesis, realism)
    if overall_conf < 0.30 and realism.is_diligence_required:
        structure = RecommendedStructure.DILIGENCE_FIRST
        rationale = (
            "Overall confidence too low for structural recommendation. "
            "Diligence-first approach required before proceeding."
        )
        return DealStructureRationale(
            recommended_structure=structure,
            rationale_text=rationale,
            overall_confidence=overall_conf,
            caveats=caveats,
            diligence_items=flat_diligence,
            thesis_tier=thesis.underwrite_thesis.value,
            realism_label=realism.realism_label,
            management_risk_band=mgmt_risk_band,
            management_gate=mgmt_gate,
        )

    # 3. Route by thesis + realism combination
    t = thesis.underwrite_thesis
    r = realism.realism_label

    if t == UnderwriteThesis.STRONG_BUY:
        if r in {"HIGH", "MODERATE_HIGH"}:
            if rofr_friction or _mgmt_weak_trial_design or _mgmt_poor_capital_allocation:
                structure = RecommendedStructure.STRUCTURED_ACQUISITION_WITH_MILESTONES
                if rofr_friction:
                    caveats.append("rofr_redirected_from_full_to_structured")
            else:
                structure = RecommendedStructure.FULL_ACQUISITION
        elif r in {"MODERATE"}:
            structure = RecommendedStructure.STRUCTURED_ACQUISITION_WITH_MILESTONES
        else:
            structure = RecommendedStructure.OPTION_TO_ACQUIRE

    elif t == UnderwriteThesis.BUY:
        if r in {"HIGH", "MODERATE_HIGH"}:
            if rofr_friction or _mgmt_weak_trial_design or _mgmt_poor_capital_allocation:
                structure = RecommendedStructure.STRUCTURED_ACQUISITION_WITH_MILESTONES
                if rofr_friction:
                    caveats.append("rofr_redirected_from_full_to_structured")
            else:
                structure = RecommendedStructure.FULL_ACQUISITION
        elif r == "MODERATE":
            structure = RecommendedStructure.STRUCTURED_ACQUISITION_WITH_MILESTONES
        else:
            structure = RecommendedStructure.OPTION_TO_ACQUIRE

    elif t == UnderwriteThesis.MONITOR:
        structure = RecommendedStructure.MONITOR_ONLY

    else:
        # Fallback: diligence first
        structure = RecommendedStructure.DILIGENCE_FIRST

    # Add diligence flag if realism calls for it
    if realism.is_diligence_required:
        caveats.append("transaction_realism_diligence_required")

    return DealStructureRationale(
        recommended_structure=structure,
        rationale_text=_build_rationale(structure, thesis, realism),
        overall_confidence=overall_conf,
        caveats=list(dict.fromkeys(caveats)),
        diligence_items=flat_diligence,
        thesis_tier=thesis.underwrite_thesis.value,
        realism_label=realism.realism_label,
        management_risk_band=mgmt_risk_band,
        management_gate=mgmt_gate,
    )
