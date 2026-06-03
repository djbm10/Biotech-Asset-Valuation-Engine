"""
Transaction Realism Score — Block 2.

Answers: "For this specific buyer-target pair, how realistic is the transaction
from a seller-side, price, and rights perspective?"

This is the FULL pair-level deal realism model, distinct from the simple
preliminary_transaction_friction (Block 1F) which only flags obvious barriers.

Key design rules:
  - activist_present RAISES seller openness (not lowers it)
  - strategic_review_announced is a STRONG POSITIVE timing signal
  - board_openness, price_expectation, management_language: UNKNOWN → neutral, no penalty
  - All UNKNOWN → is_diligence_required=True (route to diligence, not a hard block)
  - ROFR present → friction note, NOT a hard_fail
  - Never double-counts with Layer 3 pair_affordability (this covers seller readiness,
    price expectation, and rights clarity — not acquirer capacity)
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_NEUTRAL: float = 0.50

# Seller readiness weights
_SR_WEIGHTS: dict[str, float] = {
    "base_readiness": 0.50,   # board_openness + management_language blend
    "strategic_review": 0.25,
    "activist": 0.15,
    "rejection_penalty": 0.10,
}
assert abs(sum(_SR_WEIGHTS.values()) - 1.0) < 1e-9

# Transaction realism top-level weights
_TR_WEIGHTS: dict[str, float] = {
    "seller_readiness": 0.45,
    "price_alignment": 0.35,
    "rights_clarity": 0.20,
}
assert abs(sum(_TR_WEIGHTS.values()) - 1.0) < 1e-9

# Realism label thresholds
_HIGH_THRESHOLD: float = 0.72
_MOD_HIGH_THRESHOLD: float = 0.58
_MOD_THRESHOLD: float = 0.44
_MOD_LOW_THRESHOLD: float = 0.30

# Staleness cap for unknown confidence
_UNKNOWN_CONFIDENCE_CAP: float = 0.50


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class SellerReadinessScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    readiness_score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    is_diligence_required: bool = False
    strategic_review_uplift: float = Field(default=0.0, ge=0.0)
    activist_uplift: float = Field(default=0.0, ge=0.0)
    positive_drivers: list[str] = Field(default_factory=list)
    negative_drivers: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    rationale: str = ""


class PriceAlignmentScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    alignment_score: float = Field(..., ge=0.0, le=1.0)
    is_affordable: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    is_diligence_required: bool = False
    premium_gap_pct: float | None = None
    missing_data: list[str] = Field(default_factory=list)
    rationale: str = ""


class TransactionRealismScore(BaseModel):
    """Full pair-level transaction realism output."""
    model_config = ConfigDict(frozen=True)

    realism_score: float = Field(..., ge=0.0, le=1.0)
    realism_label: str  # HIGH | MODERATE_HIGH | MODERATE | MODERATE_LOW | LOW
    overall_confidence: float = Field(..., ge=0.0, le=1.0)
    is_hard_fail: bool = False  # reserved for true process-blockers; never from UNKNOWN
    is_diligence_required: bool

    # Sub-scores for transparency
    seller_readiness_score: float = Field(..., ge=0.0, le=1.0)
    price_alignment_score: float = Field(..., ge=0.0, le=1.0)
    rights_clarity_score: float = Field(..., ge=0.0, le=1.0)

    friction_notes: list[str] = Field(default_factory=list)
    diligence_items: list[str] = Field(default_factory=list)
    rationale: str = ""

    # Block 6F: optional management quality overlay
    # Does NOT double-count financing_pressure (already in Layer 1 transaction_setup)
    management_transaction_behavior_score: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Blended management BD/governance behavior signal from Block 6"
    )
    management_risk_band: Optional[str] = None
    management_risk_summary: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))


def _resolve_float(
    raw: Any,
    *,
    field_name: str,
    missing_list: list[str],
    default: float = _NEUTRAL,
) -> tuple[float, bool]:
    """UNKNOWN → neutral default (no penalty), track in missing_list."""
    if raw is None:
        missing_list.append(field_name)
        return default, False
    try:
        return _clamp(float(raw)), True
    except (TypeError, ValueError):
        missing_list.append(field_name)
        return default, False


def _resolve_bool(
    raw: Any,
    *,
    field_name: str,
    missing_list: list[str],
    default: bool = False,
) -> tuple[bool, bool]:
    if raw is None:
        missing_list.append(field_name)
        return default, False
    return bool(raw), True


def _compute_confidence(n_known: int, n_total: int, base: float = 0.75) -> float:
    if n_total == 0:
        return _UNKNOWN_CONFIDENCE_CAP
    frac = n_known / n_total
    return max(0.20, min(base, base * (0.35 + 0.65 * frac)))


def _classify_realism(score: float) -> str:
    if score >= _HIGH_THRESHOLD:
        return "HIGH"
    if score >= _MOD_HIGH_THRESHOLD:
        return "MODERATE_HIGH"
    if score >= _MOD_THRESHOLD:
        return "MODERATE"
    if score >= _MOD_LOW_THRESHOLD:
        return "MODERATE_LOW"
    return "LOW"


# ---------------------------------------------------------------------------
# SellerReadiness scorer
# ---------------------------------------------------------------------------

def compute_seller_readiness(inputs: dict[str, Any]) -> SellerReadinessScore:
    """
    Compute seller readiness from:
      - board_openness: float [0,1] | None
      - management_language: float [0,1] | None  (positive language about deal value)
      - strategic_review_announced: bool | None
      - activist_present: bool | None
      - prior_deal_rejections: int | None

    Design:
      - activist_present → RAISES openness (not lowers it)
      - strategic_review_announced → strong positive signal
      - UNKNOWN → neutral (no penalty), lower confidence
      - All UNKNOWN → is_diligence_required=True
    """
    missing_data: list[str] = []
    positive_drivers: list[str] = []
    negative_drivers: list[str] = []

    board_open, board_known = _resolve_float(
        inputs.get("board_openness"),
        field_name="board_openness",
        missing_list=missing_data,
    )
    mgmt_lang, mgmt_known = _resolve_float(
        inputs.get("management_language"),
        field_name="management_language",
        missing_list=missing_data,
    )
    strategic_review, sr_known = _resolve_bool(
        inputs.get("strategic_review_announced"),
        field_name="strategic_review_announced",
        missing_list=missing_data,
    )
    activist, act_known = _resolve_bool(
        inputs.get("activist_present"),
        field_name="activist_present",
        missing_list=missing_data,
    )

    raw_rejections = inputs.get("prior_deal_rejections")
    if raw_rejections is None:
        prior_rejections = 0
        rej_known = False
        missing_data.append("prior_deal_rejections")
    else:
        prior_rejections = int(raw_rejections)
        rej_known = True

    # Base readiness from board + management language blend
    base_readiness = (board_open * 0.60 + mgmt_lang * 0.40)

    # Strategic review uplift: +0.18 to base_readiness
    strategic_uplift = 0.18 if strategic_review else 0.0
    if strategic_review:
        positive_drivers.append("strategic_review_announced")

    # Activist uplift: +0.10 (activist increases deal pressure on board)
    activist_uplift = 0.10 if activist else 0.0
    if activist:
        positive_drivers.append("activist_present")

    # Rejection penalty: -0.12 per rejection, max 2
    rejection_penalty = min(prior_rejections, 2) * 0.12
    if prior_rejections > 0:
        negative_drivers.append(f"prior_deal_rejections:{prior_rejections}")

    # Track positive base drivers
    if board_known and board_open > 0.55:
        positive_drivers.append("board_openness")
    if mgmt_known and mgmt_lang > 0.55:
        positive_drivers.append("management_language")

    raw_score = _clamp(base_readiness + strategic_uplift + activist_uplift - rejection_penalty)

    n_known = sum([board_known, mgmt_known, sr_known, act_known, rej_known])
    confidence = _compute_confidence(n_known, 5)

    # All unknown → diligence required
    is_diligence_required = n_known == 0 or (not board_known and not mgmt_known)

    return SellerReadinessScore(
        readiness_score=round(raw_score, 6),
        confidence=round(confidence, 6),
        is_diligence_required=is_diligence_required,
        strategic_review_uplift=round(strategic_uplift, 6),
        activist_uplift=round(activist_uplift, 6),
        positive_drivers=positive_drivers,
        negative_drivers=negative_drivers,
        missing_data=missing_data,
        rationale=(
            f"base={base_readiness:.3f}; sr_uplift={strategic_uplift:.3f}; "
            f"act_uplift={activist_uplift:.3f}; rej_penalty={rejection_penalty:.3f}"
        ),
    )


# ---------------------------------------------------------------------------
# PriceAlignment scorer
# ---------------------------------------------------------------------------

def _resolve_pct(
    raw: Any,
    *,
    field_name: str,
    missing_list: list[str],
    default: float,
) -> tuple[float, bool]:
    """Resolve a premium percentage (0–200+, NOT clamped to [0,1])."""
    if raw is None:
        missing_list.append(field_name)
        return default, False
    try:
        return float(raw), True
    except (TypeError, ValueError):
        missing_list.append(field_name)
        return default, False


def compute_price_alignment(inputs: dict[str, Any]) -> PriceAlignmentScore:
    """
    Assess price expectation alignment.

    Inputs:
      - target_price_expectation_premium_pct: float | None  (% above current market)
      - market_implied_premium_pct: float | None
      - recent_comparable_premium_pct: float | None
      - acquirer_offer_capacity_premium_pct: float | None  (max the acquirer can pay)

    UNKNOWN target_price_expectation → neutral (no penalty).
    All unknown → is_diligence_required=True.
    """
    missing_data: list[str] = []

    target_exp, target_known = _resolve_pct(
        inputs.get("target_price_expectation_premium_pct"),
        field_name="target_price_expectation_premium_pct",
        missing_list=missing_data,
        default=35.0,  # neutral market assumption
    )
    market_impl, market_known = _resolve_pct(
        inputs.get("market_implied_premium_pct"),
        field_name="market_implied_premium_pct",
        missing_list=missing_data,
        default=35.0,
    )
    comp_prem, comp_known = _resolve_pct(
        inputs.get("recent_comparable_premium_pct"),
        field_name="recent_comparable_premium_pct",
        missing_list=missing_data,
        default=35.0,
    )
    capacity, cap_known = _resolve_pct(
        inputs.get("acquirer_offer_capacity_premium_pct"),
        field_name="acquirer_offer_capacity_premium_pct",
        missing_list=missing_data,
        default=50.0,
    )

    n_known = sum([target_known, market_known, comp_known, cap_known])
    confidence = _compute_confidence(n_known, 4)

    # Reference premium: average of market and comparables
    ref_premium = (market_impl * 0.55 + comp_prem * 0.45)

    # Gap: how much target expects vs reference
    premium_gap = target_exp - ref_premium

    # Is the target price within acquirer capacity?
    is_affordable = target_exp <= capacity

    # Alignment score: 1.0 if target matches reference exactly, decays with gap
    if premium_gap <= 0:
        # Target expects at or below market reference — very aligned
        alignment = _clamp(0.85 + (abs(premium_gap) / 100.0) * 0.10)
    else:
        # Target expects above reference — penalise proportionally
        # Gap of 20% premium pts → ~0.20 score decay
        alignment = _clamp(0.85 - (premium_gap / 100.0) * 1.0)

    # Affordability adjustment
    if not is_affordable:
        overshoot = target_exp - capacity
        alignment = _clamp(alignment - (overshoot / 100.0) * 0.50)

    is_diligence_required = n_known <= 1

    return PriceAlignmentScore(
        alignment_score=round(alignment, 6),
        is_affordable=is_affordable,
        confidence=round(confidence, 6),
        is_diligence_required=is_diligence_required,
        premium_gap_pct=round(premium_gap, 4),
        missing_data=missing_data,
        rationale=(
            f"target_exp={target_exp:.1f}; ref={ref_premium:.1f}; "
            f"capacity={capacity:.1f}; gap={premium_gap:.1f}; affordable={is_affordable}"
        ),
    )


# ---------------------------------------------------------------------------
# Rights clarity scorer
# ---------------------------------------------------------------------------

def _score_rights_clarity(rights: dict[str, Any]) -> tuple[float, float, list[str], list[str]]:
    """
    Returns (score, confidence, friction_notes, missing_data).
    ROFR = friction note, NOT hard fail.
    """
    missing_data: list[str] = []
    friction_notes: list[str] = []

    rofr_raw = rights.get("rofr_present")
    if rofr_raw is None:
        missing_data.append("rofr_present")
        rofr_score = 1.0  # benefit of doubt
        rofr_known = False
    else:
        rofr_present = bool(rofr_raw)
        rofr_score = 0.60 if rofr_present else 1.0  # friction, not block
        rofr_known = True
        if rofr_present:
            friction_notes.append("rofr_present:requires_legal_review")

    partner_raw = rights.get("partner_rights_issue")
    if partner_raw is None:
        partner_score = 1.0
        partner_known = False
        missing_data.append("partner_rights_issue")
    else:
        partner_score = _clamp(1.0 - float(partner_raw) * 0.50)  # partial friction
        partner_known = True
        if float(partner_raw) > 0.50:
            friction_notes.append("partner_rights_issue:elevated")

    ip_raw = rights.get("ip_licensing_barrier")
    if ip_raw is None:
        ip_score = 1.0
        ip_known = False
        missing_data.append("ip_licensing_barrier")
    else:
        ip_score = _clamp(1.0 - float(ip_raw) * 0.40)
        ip_known = True
        if float(ip_raw) > 0.50:
            friction_notes.append("ip_licensing_barrier:elevated")

    score = _clamp(rofr_score * 0.50 + partner_score * 0.30 + ip_score * 0.20)
    n_known = sum([rofr_known, partner_known, ip_known])
    confidence = _compute_confidence(n_known, 3)

    return score, confidence, friction_notes, missing_data


# ---------------------------------------------------------------------------
# TransactionRealismScore top-level
# ---------------------------------------------------------------------------

def compute_transaction_realism(
    inputs: dict[str, Any],
    *,
    management_quality: Optional[Any] = None,
) -> TransactionRealismScore:
    """
    Compute full transaction realism from seller readiness, price alignment,
    and rights clarity.

    Top-level input keys:
      - seller_readiness: dict  (see compute_seller_readiness inputs)
      - price_expectation: dict  (see compute_price_alignment inputs)
      - rights_clarity: dict  (rofr_present, partner_rights_issue, ip_licensing_barrier)

    Block 6F: optional management_quality (ManagementQualityScore) overlay.
      - Poor bd_partnering_judgment → lower confidence in seller readiness
      - Poor governance_alignment → cap active pursuit, but NOT cap licensing/partnership
      - UNKNOWN management → lower confidence only, no score penalty
      - Does NOT double-count financing_pressure (already in Layer 1 transaction_setup)

    UNKNOWN inputs at any level → neutral score, lower confidence, diligence flag.
    ROFR present → friction note, NOT hard_fail.
    """
    sr_raw = inputs.get("seller_readiness") or {}
    pe_raw = inputs.get("price_expectation") or {}
    rc_raw = inputs.get("rights_clarity") or {}

    # Score each sub-dimension
    sr = compute_seller_readiness(sr_raw)
    pa = compute_price_alignment(pe_raw)
    rc_score, rc_conf, friction_notes, rc_missing = _score_rights_clarity(rc_raw)

    # Weighted composite
    realism_score = _clamp(
        _TR_WEIGHTS["seller_readiness"] * sr.readiness_score
        + _TR_WEIGHTS["price_alignment"] * pa.alignment_score
        + _TR_WEIGHTS["rights_clarity"] * rc_score
    )

    # Overall confidence: weighted average (degrades proportionally when inputs unknown)
    overall_confidence = _clamp(
        _TR_WEIGHTS["seller_readiness"] * sr.confidence
        + _TR_WEIGHTS["price_alignment"] * pa.confidence
        + _TR_WEIGHTS["rights_clarity"] * rc_conf
    )

    # Diligence required if any sub-dimension needs it
    is_diligence_required = sr.is_diligence_required or pa.is_diligence_required or len(rc_missing) >= 2

    # Diligence items = all missing data fields
    diligence_items = list(dict.fromkeys(
        sr.missing_data + pa.missing_data + rc_missing
    ))
    friction_notes = list(friction_notes)

    # Block 6F: management quality overlay
    mgmt_behavior_score: Optional[float] = None
    mgmt_risk_band: Optional[str] = None
    mgmt_risk_summary: Optional[str] = None

    if management_quality is not None:
        mgmt_risk_band = (
            management_quality.risk_band.value
            if hasattr(management_quality.risk_band, "value")
            else str(management_quality.risk_band)
        )
        mgmt_risk_summary = getattr(management_quality, "management_risk_summary", None)
        bd = getattr(management_quality, "component_breakdown", {})

        # Derive a blended management transaction behavior signal
        bd_part = bd.get("bd_partnering_judgment")
        gov_part = bd.get("governance_alignment")
        if bd_part is not None or gov_part is not None:
            parts = [v for v in [bd_part, gov_part] if v is not None]
            mgmt_behavior_score = round(sum(parts) / len(parts), 6)

        # Poor bd_partnering_judgment → lower confidence (not a hard cap)
        if bd_part is not None and bd_part < 0.40:
            overall_confidence = _clamp(overall_confidence * 0.88)
            friction_notes.append(
                "management_bd_partnering_risk: poor BD judgment may affect seller engagement"
            )

        # Poor governance_alignment → flag active pursuit, but do NOT cap licensing
        if gov_part is not None and gov_part < 0.35:
            overall_confidence = _clamp(overall_confidence * 0.85)
            friction_notes.append(
                "management_governance_risk: governance concerns cap full acquisition confidence"
            )
            is_diligence_required = True

        # UNKNOWN management → lower confidence slightly, no other effect
        if mgmt_risk_band == "unknown":
            overall_confidence = _clamp(overall_confidence * 0.92)
            diligence_items = list(dict.fromkeys(
                diligence_items + ["management_quality_unknown: route to management diligence"]
            ))

    return TransactionRealismScore(
        realism_score=round(realism_score, 6),
        realism_label=_classify_realism(realism_score),
        overall_confidence=round(overall_confidence, 6),
        is_hard_fail=False,  # never set from UNKNOWN
        is_diligence_required=is_diligence_required,
        seller_readiness_score=sr.readiness_score,
        price_alignment_score=pa.alignment_score,
        rights_clarity_score=round(rc_score, 6),
        friction_notes=friction_notes,
        diligence_items=diligence_items,
        rationale=(
            f"label={_classify_realism(realism_score)}; "
            f"sr={sr.readiness_score:.3f}; pa={pa.alignment_score:.3f}; rc={rc_score:.3f}"
        ),
        management_transaction_behavior_score=mgmt_behavior_score,
        management_risk_band=mgmt_risk_band,
        management_risk_summary=mgmt_risk_summary,
    )
