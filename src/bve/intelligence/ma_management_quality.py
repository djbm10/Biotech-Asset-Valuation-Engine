"""Block 6A–6D: Management Quality & Value Preservation.

Answers: "Can management turn the drug into value?"

Key design rules:
  - UNKNOWN inputs → no numeric penalty; lower confidence, route to diligence
  - Management gates cap confidence or structure — they do NOT hard-kill targets
  - POS multiplier is narrow: max swing ±15%, UNKNOWN = 1.0 (no effect)
  - Do NOT double-count clinical evidence, financing pressure, seller readiness,
    or buyer mandate — those live in Layers 1–3 already
  - Composite requires ≥ 4 of 7 components; fewer → UNKNOWN band
  - Source quality affects confidence only, never composite
  - Staleness (> 180 days) lowers confidence one level
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ManagementRiskBand(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    SEVERE = "severe"
    UNKNOWN = "unknown"


class ManagementConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT_DATA = "insufficient_data"


class ManagementGate(str, Enum):
    NONE = "none"
    DILIGENCE_REQUIRED = "diligence_required"
    CAP_CONFIDENCE = "cap_confidence"
    STRUCTURE_AROUND_MANAGEMENT_RISK = "structure_around_management_risk"
    CAP_ACTIVE_PURSUIT = "cap_active_pursuit"


class ManagementSignalSourceQuality(str, Enum):
    SEC_FILING = "sec_filing"
    EARNINGS_CALL = "earnings_call"
    INVESTOR_DECK = "investor_deck"
    CLINICALTRIALS_GOV = "clinicaltrials_gov"
    FDA_DOCUMENT = "fda_document"
    REPUTABLE_MEDIA = "reputable_media"
    ANALYST_NOTE = "analyst_note"
    COMPANY_PRESS_RELEASE = "company_press_release"
    MANAGEMENT_MEETING_NOTE = "management_meeting_note"
    MARKET_RUMOR = "market_rumor"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Gate priority ordering (higher index = more restrictive)
# ---------------------------------------------------------------------------

_GATE_PRIORITY: dict[ManagementGate, int] = {
    ManagementGate.NONE: 0,
    ManagementGate.DILIGENCE_REQUIRED: 1,
    ManagementGate.CAP_CONFIDENCE: 2,
    ManagementGate.STRUCTURE_AROUND_MANAGEMENT_RISK: 3,
    ManagementGate.CAP_ACTIVE_PURSUIT: 4,
}


def _most_restrictive_gate(*gates: ManagementGate) -> ManagementGate:
    return max(gates, key=lambda g: _GATE_PRIORITY[g])


# ---------------------------------------------------------------------------
# Composite formula weights
# ---------------------------------------------------------------------------

_WEIGHTS: dict[str, float] = {
    "clinical_execution_quality": 0.25,
    "trial_design_judgment": 0.20,
    "regulatory_execution": 0.15,
    "capital_allocation_discipline": 0.15,
    "bd_partnering_judgment": 0.10,
    "disclosure_transparency": 0.10,
    "governance_alignment": 0.05,
}
assert abs(sum(_WEIGHTS.values()) - 1.0) < 1e-9

# Minimum components required before producing a composite (and non-UNKNOWN band)
_MIN_COMPONENTS: int = 4

# Risk band thresholds
_LOW_THRESHOLD: float = 0.75
_MEDIUM_THRESHOLD: float = 0.55
_HIGH_THRESHOLD: float = 0.35

# Gate trigger thresholds (individual components)
_GATE_TRIGGER: float = 0.35

# Staleness threshold (days)
_STALENESS_DAYS: int = 180

# Source quality tiers (high-quality = higher confidence)
_HIGH_QUALITY_SOURCES: frozenset[ManagementSignalSourceQuality] = frozenset({
    ManagementSignalSourceQuality.SEC_FILING,
    ManagementSignalSourceQuality.FDA_DOCUMENT,
    ManagementSignalSourceQuality.CLINICALTRIALS_GOV,
    ManagementSignalSourceQuality.EARNINGS_CALL,
    ManagementSignalSourceQuality.MANAGEMENT_MEETING_NOTE,
})
_LOW_QUALITY_SOURCES: frozenset[ManagementSignalSourceQuality] = frozenset({
    ManagementSignalSourceQuality.MARKET_RUMOR,
    ManagementSignalSourceQuality.COMPANY_PRESS_RELEASE,
})


# ---------------------------------------------------------------------------
# POS multipliers by risk band
# ---------------------------------------------------------------------------

_POS_MULTIPLIERS: dict[ManagementRiskBand, float] = {
    ManagementRiskBand.LOW: 1.02,
    ManagementRiskBand.MEDIUM: 0.97,
    ManagementRiskBand.HIGH: 0.92,
    ManagementRiskBand.SEVERE: 0.87,
    ManagementRiskBand.UNKNOWN: 1.00,  # no effect
}


def management_execution_multiplier(band: ManagementRiskBand) -> float:
    """Return the narrow POS execution multiplier for a given risk band.

    UNKNOWN → 1.0 (no effect on POS).
    All other bands stay within [0.85, 1.05].
    """
    return _POS_MULTIPLIERS[band]


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class ManagementQualityInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_id: str

    # Scored sub-dimensions — None = not available
    clinical_execution_quality: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Enrollment track record, trial timelines, protocol amendments, data quality"
    )
    trial_design_judgment: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Endpoint quality, comparator, sample size, biomarker strategy, dose selection"
    )
    regulatory_execution: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="FDA/EMA alignment, SPA, CRL history, clinical holds, label strategy"
    )
    capital_allocation_discipline: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Cash runway, dilution history, financing timing, R&D prioritization"
    )
    bd_partnering_judgment: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Prior deal quality, timing, economics retained, strategic optionality"
    )
    disclosure_transparency: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Data completeness, filing consistency, safety event clarity, overpromotion risk"
    )
    governance_alignment: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Insider ownership, board quality, control provisions, shareholder alignment"
    )

    evidence_refs: list[str] = Field(default_factory=list)
    source_quality: ManagementSignalSourceQuality = ManagementSignalSourceQuality.UNKNOWN
    data_staleness_days: Optional[int] = None


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class ManagementQualityScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    composite: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Weighted composite (None when < 4 components available)"
    )
    risk_band: ManagementRiskBand
    confidence: ManagementConfidence
    gate: ManagementGate
    component_breakdown: dict[str, float] = Field(default_factory=dict)
    missing_components: list[str] = Field(default_factory=list)
    positive_drivers: list[str] = Field(default_factory=list)
    negative_drivers: list[str] = Field(default_factory=list)
    management_risk_summary: str = ""
    staleness_warning: bool = False
    evidence_refs: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _band_from_composite(composite: float) -> ManagementRiskBand:
    if composite >= _LOW_THRESHOLD:
        return ManagementRiskBand.LOW
    if composite >= _MEDIUM_THRESHOLD:
        return ManagementRiskBand.MEDIUM
    if composite >= _HIGH_THRESHOLD:
        return ManagementRiskBand.HIGH
    return ManagementRiskBand.SEVERE


def _base_confidence(
    n_available: int,
    source_quality: ManagementSignalSourceQuality,
) -> ManagementConfidence:
    """Derive base confidence from data completeness and source quality."""
    if n_available < _MIN_COMPONENTS:
        return ManagementConfidence.INSUFFICIENT_DATA
    # Source-quality adjustment
    if source_quality in _LOW_QUALITY_SOURCES:
        if n_available >= 6:
            return ManagementConfidence.LOW
        return ManagementConfidence.INSUFFICIENT_DATA
    if source_quality in _HIGH_QUALITY_SOURCES:
        if n_available == 7:
            return ManagementConfidence.HIGH
        if n_available >= 5:
            return ManagementConfidence.MEDIUM
        return ManagementConfidence.LOW
    # UNKNOWN or neutral source
    if n_available == 7:
        return ManagementConfidence.MEDIUM
    if n_available >= 5:
        return ManagementConfidence.LOW
    return ManagementConfidence.INSUFFICIENT_DATA


def _degrade_confidence(c: ManagementConfidence) -> ManagementConfidence:
    """Lower confidence one level."""
    order = [
        ManagementConfidence.INSUFFICIENT_DATA,
        ManagementConfidence.LOW,
        ManagementConfidence.MEDIUM,
        ManagementConfidence.HIGH,
    ]
    idx = order.index(c)
    return order[max(0, idx - 1)]


def _build_summary(band: ManagementRiskBand, negative_drivers: list[str]) -> str:
    if band == ManagementRiskBand.UNKNOWN:
        return "Management quality unknown — insufficient public data. Route to diligence; no score penalty applied."
    label = band.value.upper()
    if negative_drivers:
        issues = ", ".join(negative_drivers[:3])
        return f"{label} management risk. Key issues: {issues}."
    return f"{label} management risk. No specific red flags identified."


# ---------------------------------------------------------------------------
# Gate computation
# ---------------------------------------------------------------------------

def compute_management_gate(score: "ManagementQualityScore") -> ManagementGate:
    """Compute the most restrictive gate based on risk band and component scores.

    Rules (priority order, most restrictive wins):
      1. UNKNOWN band → DILIGENCE_REQUIRED
      2. trial_design_judgment < 0.35 → CAP_CONFIDENCE
      3. disclosure_transparency < 0.35 → CAP_CONFIDENCE
      4. capital_allocation_discipline < 0.35 → STRUCTURE_AROUND_MANAGEMENT_RISK
      5. bd_partnering_judgment < 0.35 → STRUCTURE_AROUND_MANAGEMENT_RISK
      6. governance_alignment < 0.35 → CAP_ACTIVE_PURSUIT
    """
    if score.risk_band == ManagementRiskBand.UNKNOWN:
        return ManagementGate.DILIGENCE_REQUIRED
    gates: list[ManagementGate] = [ManagementGate.NONE]
    bd = score.component_breakdown
    if bd.get("trial_design_judgment", 1.0) < _GATE_TRIGGER:
        gates.append(ManagementGate.CAP_CONFIDENCE)
    if bd.get("disclosure_transparency", 1.0) < _GATE_TRIGGER:
        gates.append(ManagementGate.CAP_CONFIDENCE)
    if bd.get("capital_allocation_discipline", 1.0) < _GATE_TRIGGER:
        gates.append(ManagementGate.STRUCTURE_AROUND_MANAGEMENT_RISK)
    if bd.get("bd_partnering_judgment", 1.0) < _GATE_TRIGGER:
        gates.append(ManagementGate.STRUCTURE_AROUND_MANAGEMENT_RISK)
    if bd.get("governance_alignment", 1.0) < _GATE_TRIGGER:
        gates.append(ManagementGate.CAP_ACTIVE_PURSUIT)
    return _most_restrictive_gate(*gates)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_management_quality_score(
    inputs: ManagementQualityInput,
) -> ManagementQualityScore:
    """Compute a ManagementQualityScore from structured inputs.

    Returns ManagementQualityScore with:
      - composite: weighted score (None if < 4 components available)
      - risk_band: LOW/MEDIUM/HIGH/SEVERE/UNKNOWN
      - confidence: adjusted for data completeness, source quality, staleness
      - gate: most restrictive gate triggered by individual components
      - component_breakdown: per-component values used in composite
      - missing_components: names of unavailable sub-dimensions
      - positive/negative_drivers: plain-English signals
    """
    _component_fields = list(_WEIGHTS.keys())

    # Resolve available components
    available: dict[str, float] = {}
    missing: list[str] = []
    for field in _component_fields:
        val = getattr(inputs, field)
        if val is not None:
            available[field] = float(val)
        else:
            missing.append(field)

    n_available = len(available)
    staleness_warning = (
        inputs.data_staleness_days is not None
        and inputs.data_staleness_days > _STALENESS_DAYS
    )

    # Compute composite only when enough data
    composite: Optional[float]
    if n_available < _MIN_COMPONENTS:
        composite = None
        risk_band = ManagementRiskBand.UNKNOWN
        gate = ManagementGate.DILIGENCE_REQUIRED
        component_breakdown: dict[str, float] = dict(available)
        positive_drivers: list[str] = []
        negative_drivers: list[str] = []
    else:
        # Weighted composite over available fields; re-normalise weights if any missing
        available_weights = {f: _WEIGHTS[f] for f in available}
        weight_sum = sum(available_weights.values())
        composite = sum(v * available_weights[f] / weight_sum for f, v in available.items())
        composite = round(max(0.0, min(1.0, composite)), 6)

        risk_band = _band_from_composite(composite)
        component_breakdown = dict(available)

        # Build positive/negative drivers
        positive_drivers = []
        negative_drivers = []

        if available.get("trial_design_judgment", 1.0) < _GATE_TRIGGER:
            negative_drivers.append("wrong_trial_risk")
        if available.get("disclosure_transparency", 1.0) < _GATE_TRIGGER:
            negative_drivers.append("low_disclosure_transparency")
        if available.get("capital_allocation_discipline", 1.0) < _GATE_TRIGGER:
            negative_drivers.append("financing_value_destruction_risk")
        if available.get("bd_partnering_judgment", 1.0) < _GATE_TRIGGER:
            negative_drivers.append("poor_partnering_history")
        if available.get("governance_alignment", 1.0) < _GATE_TRIGGER:
            negative_drivers.append("governance_alignment_risk")

        if available.get("clinical_execution_quality", 0.0) >= 0.75:
            positive_drivers.append("strong_clinical_execution")
        if available.get("bd_partnering_judgment", 0.0) >= 0.75:
            positive_drivers.append("strong_bd_partnering")
        if available.get("disclosure_transparency", 0.0) >= 0.75:
            positive_drivers.append("high_disclosure_quality")

        # Gate based on component-level triggers
        gate = compute_management_gate(ManagementQualityScore(
            composite=composite,
            risk_band=risk_band,
            confidence=ManagementConfidence.MEDIUM,  # placeholder for gate calc
            gate=ManagementGate.NONE,
            component_breakdown=component_breakdown,
            negative_drivers=negative_drivers,
        ))

    # Confidence
    confidence = _base_confidence(n_available, inputs.source_quality)
    if staleness_warning:
        confidence = _degrade_confidence(confidence)

    summary = _build_summary(risk_band, negative_drivers if n_available >= _MIN_COMPONENTS else [])

    return ManagementQualityScore(
        composite=composite,
        risk_band=risk_band,
        confidence=confidence,
        gate=gate,
        component_breakdown=component_breakdown if n_available >= _MIN_COMPONENTS else dict(available),
        missing_components=missing,
        positive_drivers=positive_drivers if n_available >= _MIN_COMPONENTS else [],
        negative_drivers=negative_drivers if n_available >= _MIN_COMPONENTS else [],
        management_risk_summary=summary,
        staleness_warning=staleness_warning,
        evidence_refs=list(inputs.evidence_refs),
    )
