"""Safety context — structured safety signal assessment for drug assets."""

from __future__ import annotations

from datetime import datetime

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
