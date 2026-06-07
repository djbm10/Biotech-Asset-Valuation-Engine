"""
0F — Distress Pressure Guard

Purpose:
    Flag how financially distressed a target company is.  Distress pressure
    is an informational signal for downstream layers — it does NOT directly
    cap or route M&A probability.

Core principle:
    Distress pressure only.  0F answers: "How badly does this company need
    a deal?"  It does NOT assess asset quality, strategic scarcity,
    salvageability, or opportunity vs trap.

Ownership:
    0F        = financial distress pressure only
    Layer 1   = asset quality + "distress without quality" value-trap caps
    POS / 0D  = asset control / encumbrance
    Layer 3   = buyer-specific fit
    Layer 4/5 = routing / probability language after combined signals

Architecture:
    distress_pressure_score  — 5-component composite (financing pressure,
                                runway, valuation distress, capital market
                                access risk, near-term funding need)
    distress_classification  — NOT_DISTRESSED | MILD_PRESSURE |
                               HIGH_DISTRESS | SEVERE_DISTRESS
    guardrail_applied        — NONE or FLAG_ONLY (informational only)
    mna_probability_cap      — always None (caps owned by Layer 1)
    route_to                 — always None (routing owned by 0B / Layer 4)

Deprecated (backward compat only, not used in scoring):
    distress_quality_score         — always None
    clinical_salvageability_score  — always None
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DistressClassification(str, Enum):
    NOT_DISTRESSED          = "not_distressed"          # pressure < 0.35
    MILD_PRESSURE           = "mild_pressure"           # 0.35–0.60
    HIGH_DISTRESS           = "high_distress"           # 0.60–0.80
    SEVERE_DISTRESS         = "severe_distress"         # > 0.80


class DistressGuardTreatment(str, Enum):
    NONE                        = "none"
    FLAG_ONLY                   = "flag_only"
    # Deprecated — no longer emitted by compute_distress_guard().
    # Retained for backward compatibility with code that may reference these values.
    ROUTE_DISTRESSED_OPTIONALITY = "route_distressed_optionality"
    CAP_025                     = "cap_0.25"
    CAP_015                     = "cap_0.15"


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class ClinicalSalvageabilityInput(BaseModel):
    """Sub-components for clinical salvageability assessment.

    No longer consumed by 0F scoring.  Retained for use by Layer 1 asset
    quality analysis and for backward compatibility with callers that build
    this model.
    """
    model_config = ConfigDict(frozen=True)

    # Primary failure characterisation
    # "underpowered" | "endpoint_miss" | "fatal_safety" | "mechanism_invalidated" | "unknown"
    failed_trial_reason: Optional[str] = None

    # Supporting evidence of possible rescue
    subgroup_signal: Optional[bool] = None
    dose_response_exists: Optional[bool] = None
    safety_reversibility: Optional[bool] = None
    alternative_indications_available: Optional[bool] = None
    regulatory_path_remaining: Optional[bool] = None
    mechanism_still_valid: Optional[bool] = None


class DistressGuardInput(BaseModel):
    """Inputs for the 0F Distress Pressure Guard.

    Only the five distress-pressure fields are used in scoring.
    Asset-quality fields are retained for backward compatibility but
    are not consumed by compute_distress_guard().
    """
    model_config = ConfigDict(frozen=True)

    # ── Distress pressure signals (0–1) — active ─────────────────────────
    financing_pressure: float = Field(default=0.0, ge=0.0, le=1.0,
        description="Cash/runway pressure (0=well-funded, 1=critical)")
    runway_pressure: float = Field(default=0.0, ge=0.0, le=1.0,
        description="Months of runway remaining → higher = shorter")
    valuation_distress: float = Field(default=0.0, ge=0.0, le=1.0,
        description="EV vs. cash ratio; deep discount signals distress")
    capital_market_access_risk: float = Field(default=0.0, ge=0.0, le=1.0,
        description="Ability to raise equity at acceptable dilution")
    near_term_funding_need: float = Field(default=0.0, ge=0.0, le=1.0,
        description="Must raise capital within 12 months to continue operations")

    # ── Deprecated asset-quality fields — retained for compat, not scored ─
    lead_asset_quality: Optional[float] = Field(default=None, ge=0.0, le=1.0,
        description="Deprecated: not used by 0F scoring. Asset quality owned by Layer 1.")
    platform_validation: Optional[float] = Field(default=None, ge=0.0, le=1.0,
        description="Deprecated: not used by 0F scoring. Asset quality owned by Layer 1.")
    clinical_salvageability: Optional[float] = Field(default=None, ge=0.0, le=1.0,
        description="Deprecated: not used by 0F scoring. Salvageability owned by Layer 1.")
    strategic_scarcity: Optional[float] = Field(default=None, ge=0.0, le=1.0,
        description="Deprecated: not used by 0F scoring. Strategic value owned by Layer 1.")
    asset_control_cleanliness: Optional[float] = Field(default=None, ge=0.0, le=1.0,
        description="Deprecated: not used by 0F scoring. Encumbrance owned by 0D/Layer 3B.")

    # Retained for compat — not consumed by compute_distress_guard()
    salvageability_components: Optional[ClinicalSalvageabilityInput] = None


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class DistressGuardResult(BaseModel):
    """Complete 0F Distress Pressure Guard output."""
    model_config = ConfigDict(frozen=True)

    distress_pressure_score: float = Field(..., ge=0.0, le=1.0)

    # Deprecated compat fields — always None in the new pressure-only contract.
    # Asset quality is owned by Layer 1; salvageability by Layer 1/POS.
    distress_quality_score: Optional[float] = None
    clinical_salvageability_score: Optional[float] = None

    distress_classification: DistressClassification
    guardrail_applied: DistressGuardTreatment

    # Backward-compatible fields
    guard_active: bool
    mna_probability_cap: Optional[float] = None  # always None — caps owned by Layer 1
    reason_code: Optional[str] = None

    # Routing — always None; routing owned by 0B / Layer 4
    route_to: Optional[str] = None

    rationale: list[str]
    data_gaps: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Composite score formula — pressure only
# ---------------------------------------------------------------------------

_PRESSURE_WEIGHTS = {
    "financing_pressure":        0.35,
    "runway_pressure":           0.25,
    "valuation_distress":        0.20,
    "capital_market_access_risk": 0.10,
    "near_term_funding_need":    0.10,
}
assert abs(sum(_PRESSURE_WEIGHTS.values()) - 1.0) < 1e-9


def _pressure_classification(score: float) -> DistressClassification:
    if score < 0.35:
        return DistressClassification.NOT_DISTRESSED
    if score < 0.60:
        return DistressClassification.MILD_PRESSURE
    if score <= 0.80:
        return DistressClassification.HIGH_DISTRESS
    return DistressClassification.SEVERE_DISTRESS


# ---------------------------------------------------------------------------
# Guardrail — informational only
# ---------------------------------------------------------------------------

def _apply_guardrail(
    classification: DistressClassification,
) -> tuple[DistressGuardTreatment, bool, Optional[str]]:
    """Return (treatment, guard_active, reason_code).

    0F is now pressure-only.  No cap or route is ever emitted here.
    guard_active=True signals high/severe pressure that downstream layers
    (Layer 1, Layer 4) should incorporate into their assessments.
    """
    if classification == DistressClassification.NOT_DISTRESSED:
        return DistressGuardTreatment.NONE, False, None

    if classification == DistressClassification.MILD_PRESSURE:
        return DistressGuardTreatment.FLAG_ONLY, False, "mild_pressure_flag"

    if classification == DistressClassification.HIGH_DISTRESS:
        return DistressGuardTreatment.FLAG_ONLY, True, "high_distress_pressure_flag"

    # SEVERE_DISTRESS
    return DistressGuardTreatment.FLAG_ONLY, True, "severe_distress_pressure_flag"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_distress_guard(inp: DistressGuardInput) -> DistressGuardResult:
    """Compute the 0F Distress Pressure Guard for a target.

    Returns a DistressGuardResult with:
      - distress_pressure_score (5-component weighted composite)
      - distress_classification (NOT_DISTRESSED / MILD_PRESSURE /
                                 HIGH_DISTRESS / SEVERE_DISTRESS)
      - guardrail_applied (NONE or FLAG_ONLY — informational only)
      - guard_active (True when pressure >= HIGH_DISTRESS)
      - mna_probability_cap = None always (caps owned by Layer 1)
      - route_to = None always (routing owned by 0B / Layer 4)
      - distress_quality_score = None (deprecated; owned by Layer 1)
      - clinical_salvageability_score = None (deprecated; owned by Layer 1)
    """
    # Distress pressure composite
    pressure = round(
        inp.financing_pressure        * _PRESSURE_WEIGHTS["financing_pressure"]
        + inp.runway_pressure         * _PRESSURE_WEIGHTS["runway_pressure"]
        + inp.valuation_distress      * _PRESSURE_WEIGHTS["valuation_distress"]
        + inp.capital_market_access_risk * _PRESSURE_WEIGHTS["capital_market_access_risk"]
        + inp.near_term_funding_need  * _PRESSURE_WEIGHTS["near_term_funding_need"],
        4,
    )

    classification = _pressure_classification(pressure)
    treatment, guard_active, reason_code = _apply_guardrail(classification)

    # Build rationale
    rationale: list[str] = [
        f"distress_pressure={pressure:.3f}  ({classification.value})",
        "0F is pressure-only; asset-quality trap/opportunity classification handled downstream (Layer 1).",
        f"guardrail={treatment.value}",
    ]
    if guard_active:
        rationale.append(
            f"Distress pressure flagged ({reason_code}). "
            "No cap applied here — Layer 1 applies value-trap caps using asset quality."
        )
    elif treatment == DistressGuardTreatment.FLAG_ONLY:
        rationale.append(f"Mild pressure noted ({reason_code}) — informational only.")
    else:
        rationale.append("No distress pressure detected.")

    return DistressGuardResult(
        distress_pressure_score=pressure,
        distress_quality_score=None,          # deprecated: owned by Layer 1
        clinical_salvageability_score=None,   # deprecated: owned by Layer 1
        distress_classification=classification,
        guardrail_applied=treatment,
        guard_active=guard_active,
        mna_probability_cap=None,             # always None: caps owned by Layer 1
        route_to=None,                        # always None: routing owned by 0B/Layer 4
        reason_code=reason_code,
        rationale=rationale,
        data_gaps=[],
    )


# ---------------------------------------------------------------------------
# Target adapter
# ---------------------------------------------------------------------------

def distress_guard_from_target(t: object) -> DistressGuardInput:
    """Map a TargetEligibilityInput (or compatible object) to DistressGuardInput.

    Only pressure signals are mapped.  Asset-quality fields (lead_asset_quality,
    platform_validation, etc.) are no longer populated here — they are handled
    by Layer 1, which owns the "distress without quality" value-trap assessment.

    Float pressure fields take precedence over legacy boolean signals.
    Missing float fields are inferred conservatively from financing_pressure.
    """
    def _g(attr: str, default):
        return getattr(t, attr, default)

    # ── Pressure signals ──────────────────────────────────────────────────
    fp_bool = _g("financing_pressure_high", False)
    fp = _g("financing_pressure", None)
    if fp is None:
        fp = 0.75 if fp_bool else 0.10

    rp = _g("runway_pressure", None)
    if rp is None:
        rp = round(min(1.0, fp * 0.90), 4)

    vd = _g("valuation_distress", None)
    if vd is None:
        vd = round(min(1.0, fp * 0.75), 4)

    cm = _g("capital_market_access_risk", None)
    if cm is None:
        cm = round(min(1.0, fp * 0.65), 4)

    nf = _g("near_term_funding_need", None)
    if nf is None:
        nf = round(min(1.0, fp * 0.85), 4)

    return DistressGuardInput(
        financing_pressure=fp,
        runway_pressure=rp,
        valuation_distress=vd,
        capital_market_access_risk=cm,
        near_term_funding_need=nf,
    )
