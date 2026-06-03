"""Structured bear case model."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class BearCaseType(str, Enum):
    CLINICAL = "clinical"
    COMMERCIAL = "commercial"
    REGULATORY = "regulatory"
    COMPETITIVE = "competitive"
    FINANCING = "financing"
    MNA = "mna"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Probability(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class BearCase(BaseModel):
    """A structured bear case / disconfirming thesis for an asset."""

    bear_case_type: BearCaseType
    claim: str = Field(description="The specific bear case claim")
    evidence: str | None = Field(default=None, description="Supporting evidence for the bear case")
    severity: Severity
    probability: Probability
    what_would_confirm: str = Field(description="What data / event would confirm this bear case")
    what_would_refute: str = Field(description="What data / event would refute this bear case")
    rnpv_impact_pct: float = Field(
        description="Estimated rNPV impact if bear case materialises (negative = downside)"
    )
    mna_score_impact: float = Field(
        default=0.0, description="Estimated M&A score impact (negative = reduces score)"
    )

    @property
    def is_critical(self) -> bool:
        return self.severity == Severity.CRITICAL

    @property
    def expected_impact(self) -> float:
        """Probability-weighted rNPV impact."""
        p_map = {Probability.LOW: 0.15, Probability.MEDIUM: 0.35, Probability.HIGH: 0.60}
        return self.rnpv_impact_pct * p_map[self.probability]

    def to_dict(self) -> dict:
        return {
            "type": self.bear_case_type.value,
            "claim": self.claim,
            "severity": self.severity.value,
            "probability": self.probability.value,
            "rnpv_impact_pct": self.rnpv_impact_pct,
            "expected_impact_pct": round(self.expected_impact, 1),
            "confirm": self.what_would_confirm,
            "refute": self.what_would_refute,
        }
