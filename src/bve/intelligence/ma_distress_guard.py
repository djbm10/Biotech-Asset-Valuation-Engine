"""
0F — Distress Quality Guard

Purpose:
    Prevent distressed, cash-burning biotechs from ranking highly just because
    they are cheap or need money.  Capital pressure only helps the M&A thesis
    if the company still owns something strategically valuable.

Core principle:
    Distress ≠ deal thesis.
    High distress + viable asset  = possible opportunity (route to specialist model).
    High distress + weak asset    = value trap (cap).
    Severe distress + no asset    = broken case (hard cap).

Architecture:
    1. distress_pressure_score — how badly does the company need a deal?
    2. distress_quality_score  — does it still own something worth buying?
    3. clinical_salvageability — can a failed/struggling asset be rescued?
    4. Guardrail table         — maps (pressure, quality) to treatment.
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
    ROUTE_DISTRESSED_OPTIONALITY = "route_distressed_optionality"
    CAP_025                     = "cap_0.25"
    CAP_015                     = "cap_0.15"


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class ClinicalSalvageabilityInput(BaseModel):
    """Sub-components for computing clinical_salvageability when a direct score
    is not provided.

    Represents what is knowable about a failed or struggling asset.
    """
    model_config = ConfigDict(frozen=True)

    # Primary failure characterisation
    # "underpowered" | "endpoint_miss" | "fatal_safety" | "mechanism_invalidated" | "unknown"
    failed_trial_reason: Optional[str] = None

    # Supporting evidence of possible rescue
    subgroup_signal: Optional[bool] = None          # meaningful sub-population response
    dose_response_exists: Optional[bool] = None     # dose-response relationship observed
    safety_reversibility: Optional[bool] = None     # AEs reversible / manageable
    alternative_indications_available: Optional[bool] = None
    regulatory_path_remaining: Optional[bool] = None  # credible label still possible
    mechanism_still_valid: Optional[bool] = None    # biology not disproved


class DistressGuardInput(BaseModel):
    """All inputs needed for the 0F Distress Quality Guard."""
    model_config = ConfigDict(frozen=True)

    # ── Distress pressure signals (0–1) ───────────────────────────────────
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

    # ── Distress quality signals (0–1) ────────────────────────────────────
    lead_asset_quality: float = Field(default=0.50, ge=0.0, le=1.0,
        description="Clinical / regulatory quality of lead program")
    platform_validation: float = Field(default=0.0, ge=0.0, le=1.0,
        description="Evidence that the platform has validated value beyond the lead asset")
    # clinical_salvageability is either provided directly or computed from sub-components
    clinical_salvageability: Optional[float] = Field(default=None, ge=0.0, le=1.0,
        description="If provided, used directly; else computed from salvageability_components")
    strategic_scarcity: float = Field(default=0.50, ge=0.0, le=1.0,
        description="How few comparable assets exist; higher = scarcer = more valuable")
    asset_control_cleanliness: float = Field(default=0.70, ge=0.0, le=1.0,
        description="Degree of clean title and absence of blocking rights")

    # Optional sub-components for clinical_salvageability
    salvageability_components: Optional[ClinicalSalvageabilityInput] = None


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class DistressGuardResult(BaseModel):
    """Complete 0F Distress Quality Guard output."""
    model_config = ConfigDict(frozen=True)

    distress_pressure_score: float = Field(..., ge=0.0, le=1.0)
    distress_quality_score: float = Field(..., ge=0.0, le=1.0)
    clinical_salvageability_score: float = Field(..., ge=0.0, le=1.0)

    distress_classification: DistressClassification
    guardrail_applied: DistressGuardTreatment

    # Backward-compatible fields (old DistressGuard interface)
    guard_active: bool
    mna_probability_cap: Optional[float] = None
    reason_code: Optional[str] = None

    # Routing (ROUTE_DISTRESSED_OPTIONALITY treatment)
    route_to: Optional[str] = None

    rationale: list[str]
    data_gaps: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Clinical salvageability scoring
# ---------------------------------------------------------------------------

_BASE_SALVAGEABILITY: dict[str, float] = {
    "underpowered":          0.62,
    "endpoint_miss":         0.40,
    "fatal_safety":          0.15,
    "mechanism_invalidated": 0.10,
    "unknown":               0.45,
}

_SALVAGEABILITY_ADJUSTMENTS: list[tuple[str, bool | None, float]] = [
    # (label, value_that_triggers, delta)
    ("subgroup_signal",                    True,  +0.12),
    ("dose_response_exists",               True,  +0.12),
    ("safety_reversibility",               True,  +0.10),
    ("alternative_indications_available",  True,  +0.10),
    ("regulatory_path_remaining",          True,  +0.08),
    ("mechanism_still_valid",              True,  +0.12),
]


def _compute_clinical_salvageability(
    components: Optional[ClinicalSalvageabilityInput],
    direct: Optional[float],
    data_gaps: list[str],
) -> float:
    """Return a 0–1 clinical salvageability score.

    Priority:
    1. direct score if provided
    2. computed from ClinicalSalvageabilityInput
    3. conservative default (0.45) with data_gap noted
    """
    if direct is not None:
        return direct

    if components is None:
        data_gaps.append(
            "clinical_salvageability: not provided; defaulting to 0.45 (neutral-conservative)"
        )
        return 0.45

    reason = (components.failed_trial_reason or "unknown").lower()
    base = _BASE_SALVAGEABILITY.get(reason, _BASE_SALVAGEABILITY["unknown"])

    delta = 0.0
    for attr, trigger, adj in _SALVAGEABILITY_ADJUSTMENTS:
        val = getattr(components, attr, None)
        if val is trigger:
            delta += adj

    # Additional penalty: irreversible safety event on a drug with fatal_safety
    if (
        reason == "fatal_safety"
        and components.safety_reversibility is False
    ):
        delta -= 0.10

    score = min(1.0, max(0.0, base + delta))
    return round(score, 4)


# ---------------------------------------------------------------------------
# Composite score formulas
# ---------------------------------------------------------------------------

_PRESSURE_WEIGHTS = {
    "financing_pressure":        0.35,
    "runway_pressure":           0.25,
    "valuation_distress":        0.20,
    "capital_market_access_risk": 0.10,
    "near_term_funding_need":    0.10,
}
assert abs(sum(_PRESSURE_WEIGHTS.values()) - 1.0) < 1e-9

_QUALITY_WEIGHTS = {
    "lead_asset_quality":       0.35,
    "platform_validation":      0.20,
    "clinical_salvageability":  0.15,
    "strategic_scarcity":       0.15,
    "asset_control_cleanliness": 0.15,
}
assert abs(sum(_QUALITY_WEIGHTS.values()) - 1.0) < 1e-9


def _pressure_classification(score: float) -> DistressClassification:
    if score < 0.35:
        return DistressClassification.NOT_DISTRESSED
    if score < 0.60:
        return DistressClassification.MILD_PRESSURE
    if score <= 0.80:
        return DistressClassification.HIGH_DISTRESS
    return DistressClassification.SEVERE_DISTRESS


# ---------------------------------------------------------------------------
# Guardrail table
# ---------------------------------------------------------------------------

def _apply_guardrail(
    pressure: float,
    quality: float,
) -> tuple[DistressGuardTreatment, bool, Optional[float], Optional[str], Optional[str]]:
    """Return (treatment, guard_active, cap, route_to, reason_code)."""

    if pressure < 0.35:
        return DistressGuardTreatment.NONE, False, None, None, None

    # Severe + broken — evaluate before other high-distress rules
    if pressure >= 0.80 and quality < 0.25:
        return (
            DistressGuardTreatment.CAP_015,
            True,
            0.15,
            None,
            "broken_distress_case",
        )

    # High distress + viable asset — route to specialist model (no cap)
    if pressure >= 0.60 and quality >= 0.60:
        return (
            DistressGuardTreatment.ROUTE_DISTRESSED_OPTIONALITY,
            True,
            None,
            "distressed_optionality_model",
            "distress_with_viable_asset",
        )

    # High distress + weak asset — hard cap
    if pressure >= 0.60 and quality < 0.35:
        return (
            DistressGuardTreatment.CAP_025,
            True,
            0.25,
            None,
            "distress_without_strategic_asset",
        )

    # High distress + medium quality (0.35–0.60) — flag only, no cap
    if pressure >= 0.60:
        return (
            DistressGuardTreatment.FLAG_ONLY,
            False,
            None,
            None,
            "high_distress_medium_quality_flag",
        )

    # Mild pressure (0.35–0.60) — informational flag only
    return DistressGuardTreatment.FLAG_ONLY, False, None, None, "mild_pressure_flag"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_distress_guard(inp: DistressGuardInput) -> DistressGuardResult:
    """Compute the 0F Distress Quality Guard for a target.

    Returns a DistressGuardResult with:
      - distress_pressure_score (5-component composite)
      - distress_quality_score  (5-component composite)
      - clinical_salvageability_score
      - guardrail treatment (NONE / FLAG_ONLY / CAP_025 / CAP_015 /
                             ROUTE_DISTRESSED_OPTIONALITY)
      - guard_active, mna_probability_cap, reason_code (backward compat)
    """
    data_gaps: list[str] = []

    # Clinical salvageability (needed inside quality composite)
    cs_score = _compute_clinical_salvageability(
        inp.salvageability_components,
        inp.clinical_salvageability,
        data_gaps,
    )

    # Distress pressure composite
    pressure = round(
        inp.financing_pressure        * _PRESSURE_WEIGHTS["financing_pressure"]
        + inp.runway_pressure         * _PRESSURE_WEIGHTS["runway_pressure"]
        + inp.valuation_distress      * _PRESSURE_WEIGHTS["valuation_distress"]
        + inp.capital_market_access_risk * _PRESSURE_WEIGHTS["capital_market_access_risk"]
        + inp.near_term_funding_need  * _PRESSURE_WEIGHTS["near_term_funding_need"],
        4,
    )

    # Distress quality composite
    quality = round(
        inp.lead_asset_quality         * _QUALITY_WEIGHTS["lead_asset_quality"]
        + inp.platform_validation      * _QUALITY_WEIGHTS["platform_validation"]
        + cs_score                     * _QUALITY_WEIGHTS["clinical_salvageability"]
        + inp.strategic_scarcity       * _QUALITY_WEIGHTS["strategic_scarcity"]
        + inp.asset_control_cleanliness * _QUALITY_WEIGHTS["asset_control_cleanliness"],
        4,
    )

    classification = _pressure_classification(pressure)
    treatment, guard_active, cap, route_to, reason_code = _apply_guardrail(pressure, quality)

    # Build rationale
    rationale: list[str] = [
        f"distress_pressure={pressure:.3f}  ({classification.value})",
        f"distress_quality={quality:.3f}  clinical_salvageability={cs_score:.3f}",
        f"guardrail={treatment.value}",
    ]
    if guard_active and cap is not None:
        rationale.append(
            f"Capping M&A probability at {cap:.2f}: {reason_code}"
        )
    elif guard_active and route_to is not None:
        rationale.append(
            f"Routing to {route_to}: {reason_code}"
        )
    elif treatment == DistressGuardTreatment.FLAG_ONLY:
        rationale.append(f"Flagging: {reason_code} — no cap applied")
    elif treatment == DistressGuardTreatment.NONE:
        rationale.append("No distress guard triggered")

    return DistressGuardResult(
        distress_pressure_score=pressure,
        distress_quality_score=quality,
        clinical_salvageability_score=cs_score,
        distress_classification=classification,
        guardrail_applied=treatment,
        guard_active=guard_active,
        mna_probability_cap=cap,
        route_to=route_to,
        reason_code=reason_code,
        rationale=rationale,
        data_gaps=data_gaps,
    )


# ---------------------------------------------------------------------------
# Target adapter
# ---------------------------------------------------------------------------

def distress_guard_from_target(t: object) -> DistressGuardInput:
    """Map a TargetEligibilityInput (or compatible object) to DistressGuardInput.

    Float fields take precedence over legacy boolean signals.
    Missing float fields are inferred conservatively from boolean flags.
    """
    def _g(attr: str, default):
        return getattr(t, attr, default)

    # ── Pressure signals ──────────────────────────────────────────────────
    # financing_pressure: float override or infer from bool flag
    fp_bool = _g("financing_pressure_high", False)
    fp = _g("financing_pressure", None)
    if fp is None:
        fp = 0.75 if fp_bool else 0.10

    rp = _g("runway_pressure", None)
    if rp is None:
        # Infer from financing_pressure as conservative proxy
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

    # ── Quality signals ───────────────────────────────────────────────────
    lq_bool = _g("lead_asset_quality_low", False)
    lq = _g("lead_asset_quality", None)
    if lq is None:
        lq = 0.20 if lq_bool else 0.65

    # platform_validation: float override or infer from bool flags
    pv = _g("platform_validation_score", None)
    if pv is None:
        if _g("platform_validated", False):
            pv = 0.80
        elif _g("is_platform_company", False):
            pv = 0.40
        else:
            pv = 0.10

    cs_direct = _g("clinical_salvageability_score", None)

    ss = _g("strategic_scarcity", None)
    if ss is None:
        ss = 0.50  # neutral default — no strong prior

    ac = _g("asset_control_cleanliness_score", None)
    if ac is None:
        ac = 0.70  # moderate cleanliness default

    # Build clinical salvageability sub-components if any signal present
    cs_components: Optional[ClinicalSalvageabilityInput] = None
    if cs_direct is None:
        ftr = _g("failed_trial_reason", None)
        sub = _g("subgroup_signal", None)
        dre = _g("dose_response_exists", None)
        sfr = _g("safety_reversibility", None)
        aia = _g("alternative_indications_available", None)
        rpr = _g("regulatory_path_remaining", None)
        msv = _g("mechanism_still_valid", None)
        if any(v is not None for v in (ftr, sub, dre, sfr, aia, rpr, msv)):
            cs_components = ClinicalSalvageabilityInput(
                failed_trial_reason=ftr,
                subgroup_signal=sub,
                dose_response_exists=dre,
                safety_reversibility=sfr,
                alternative_indications_available=aia,
                regulatory_path_remaining=rpr,
                mechanism_still_valid=msv,
            )

    return DistressGuardInput(
        financing_pressure=fp,
        runway_pressure=rp,
        valuation_distress=vd,
        capital_market_access_risk=cm,
        near_term_funding_need=nf,
        lead_asset_quality=lq,
        platform_validation=pv,
        clinical_salvageability=cs_direct,
        strategic_scarcity=ss,
        asset_control_cleanliness=ac,
        salvageability_components=cs_components,
    )
