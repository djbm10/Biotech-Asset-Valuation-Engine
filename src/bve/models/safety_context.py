"""Safety context — structured safety signal assessment for drug assets."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SafetySignal(BaseModel):
    """A single observed or potential safety signal."""

    signal_id: str
    description: str
    severity: str  # "mild" | "moderate" | "severe" | "fatal"
    frequency: str  # "rare" | "uncommon" | "common"
    mechanism_plausibility: str  # "low" | "medium" | "high"
    regulatory_precedent: str  # "managed" | "boxed" | "hold" | "withdrawal"
    source: str


class SafetyContext(BaseModel):
    """Aggregated safety assessment for a drug asset."""

    asset_id: str
    assessed_at: datetime
    signals: list[SafetySignal] = Field(default_factory=list)
    overall_safety_score: float = Field(ge=0.0, le=1.0)  # 1 = safest
    safety_risk_tier: str  # "low" | "medium" | "high" | "critical"
    class_safety_profile: str
    regulatory_concern: bool
    pos_penalty: float = Field(ge=0.0, le=1.0)
    commentary: str


# ---------------------------------------------------------------------------
# Step 6: Structured safety scoring types
# ---------------------------------------------------------------------------


class SafetySignalType(str, Enum):
    BLACK_BOX_WARNING = "BLACK_BOX_WARNING"
    SERIOUS_ADVERSE_EVENT = "SERIOUS_ADVERSE_EVENT"
    DOSE_LIMITING_TOXICITY = "DOSE_LIMITING_TOXICITY"
    IMMUNE_MEDIATED = "IMMUNE_MEDIATED"
    CARDIAC = "CARDIAC"
    HEPATIC = "HEPATIC"
    RENAL = "RENAL"
    HEMATOLOGIC = "HEMATOLOGIC"
    DERMATOLOGIC = "DERMATOLOGIC"
    GI = "GI"
    CNS = "CNS"
    INFECTION_RISK = "INFECTION_RISK"
    OTHER = "OTHER"


class SafetySignalV2(BaseModel):
    """Step 6 structured safety signal."""

    model_config = {"frozen": True}

    signal_type: SafetySignalType
    description: str
    severity: str  # "mild" | "moderate" | "severe" | "life_threatening"
    frequency_pct: float | None = None
    manageable: bool
    notes: str | None = None


class SafetyContextV2(BaseModel):
    """Step 6 deterministic safety context — computed from SafetySignalV2 list."""

    model_config = {"frozen": True}

    asset_id: str
    signals: list[SafetySignalV2]
    overall_safety_score: float
    class_risk_level: str  # "low" | "medium" | "high" | "very_high"
    controversy_score: float
    manageable_fraction: float
    rationale: str


_SEVERITY_MULTIPLIER: dict[str, float] = {
    "mild": 0.5,
    "moderate": 1.0,
    "severe": 1.5,
    "life_threatening": 2.0,
}

_BASE_DEDUCTION: dict[SafetySignalType, float] = {
    SafetySignalType.BLACK_BOX_WARNING: 0.30,
    SafetySignalType.SERIOUS_ADVERSE_EVENT: 0.15,
    SafetySignalType.DOSE_LIMITING_TOXICITY: 0.10,
    SafetySignalType.IMMUNE_MEDIATED: 0.12,
    SafetySignalType.CARDIAC: 0.10,
    SafetySignalType.HEPATIC: 0.10,
    SafetySignalType.RENAL: 0.05,
    SafetySignalType.HEMATOLOGIC: 0.05,
    SafetySignalType.DERMATOLOGIC: 0.05,
    SafetySignalType.GI: 0.05,
    SafetySignalType.CNS: 0.05,
    SafetySignalType.INFECTION_RISK: 0.05,
    SafetySignalType.OTHER: 0.05,
}

_CONTROVERSIAL_TYPES = {SafetySignalType.BLACK_BOX_WARNING, SafetySignalType.IMMUNE_MEDIATED}


def compute_safety_context(
    asset_id: str,
    signals: list[SafetySignalV2],
    mechanism_class: str = "",
) -> SafetyContextV2:
    """Compute a deterministic SafetyContextV2 from a list of SafetySignalV2."""
    if not signals:
        return SafetyContextV2(
            asset_id=asset_id,
            signals=[],
            overall_safety_score=1.0,
            class_risk_level="low",
            controversy_score=0.0,
            manageable_fraction=1.0,
            rationale="No safety signals reported; clean profile assumed.",
        )

    base_score = 1.0
    for signal in signals:
        severity_mult = _SEVERITY_MULTIPLIER.get(signal.severity, 1.0)
        base_deduction = _BASE_DEDUCTION.get(signal.signal_type, 0.05)
        deduction = base_deduction * severity_mult
        if signal.manageable:
            deduction *= 0.5
        base_score -= deduction

    overall_safety_score = max(0.05, base_score)

    if overall_safety_score >= 0.80:
        class_risk_level = "low"
    elif overall_safety_score >= 0.60:
        class_risk_level = "medium"
    elif overall_safety_score >= 0.40:
        class_risk_level = "high"
    else:
        class_risk_level = "very_high"

    controversial_count = sum(1 for s in signals if s.signal_type in _CONTROVERSIAL_TYPES)
    controversy_score = controversial_count / len(signals)

    manageable_count = sum(1 for s in signals if s.manageable)
    manageable_fraction = manageable_count / len(signals)

    signal_labels = ", ".join(s.signal_type.value for s in signals)
    rationale = (
        f"Scored {len(signals)} signal(s) [{signal_labels}]. "
        f"Overall safety score: {overall_safety_score:.2f} ({class_risk_level} risk). "
        f"Manageable fraction: {manageable_fraction:.0%}. "
        f"Controversy score: {controversy_score:.2f}."
    )

    return SafetyContextV2(
        asset_id=asset_id,
        signals=signals,
        overall_safety_score=round(overall_safety_score, 4),
        class_risk_level=class_risk_level,
        controversy_score=round(controversy_score, 4),
        manageable_fraction=round(manageable_fraction, 4),
        rationale=rationale,
    )
