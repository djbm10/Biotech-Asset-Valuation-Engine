"""Financing risk assessment models — scenario-based capital runway risk."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class FinancingScenario(BaseModel):
    """A single financing scenario with probability and terms."""

    label: str  # "no_raise" | "bridge" | "follow_on" | "dilutive" | "partnership" | "distressed"
    probability: float = Field(ge=0.0, le=1.0)
    raise_size_millions: float = 0.0
    dilution_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    timing_months: float = 0.0


class FinancingRiskAssessment(BaseModel):
    """Point-in-time financing risk assessment for a company."""

    asset_id: str
    company_id: str
    assessment_date: date
    risk_score: float = Field(ge=0.0, le=1.0)
    risk_tier: str  # "low" | "medium" | "high" | "critical"
    scenarios: list[FinancingScenario] = Field(default_factory=list)
    primary_scenario: str
    distress_probability: float = Field(ge=0.0, le=1.0)
    commentary: str


class FinancingRisk(BaseModel):
    """Financing risk container with current assessment and historical records."""

    asset_id: str
    company_id: str
    current_assessment: Optional[FinancingRiskAssessment] = None
    history: list[FinancingRiskAssessment] = Field(default_factory=list)
