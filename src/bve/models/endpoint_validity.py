"""Endpoint validity — regulatory and clinical meaningfulness scoring for endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class EndpointValidityScore(BaseModel):
    """Validity assessment for a single clinical endpoint."""

    endpoint_name: str
    endpoint_type: str  # "primary" | "secondary" | "exploratory"
    clinical_meaningfulness: float = Field(ge=0.0, le=1.0)
    regulatory_acceptability: float = Field(ge=0.0, le=1.0)
    measurability: float = Field(ge=0.0, le=1.0)
    precedent_count: int = 0
    rationale: str


class EndpointValidity(BaseModel):
    """Full endpoint validity assessment for a trial."""

    asset_id: str
    trial_id: Optional[str] = None
    scored_at: datetime
    primary_endpoint_scores: list[EndpointValidityScore] = Field(default_factory=list)
    secondary_endpoint_scores: list[EndpointValidityScore] = Field(default_factory=list)
    overall_validity_score: float = Field(ge=0.0, le=1.0)
    regulatory_risk: str  # "low" | "medium" | "high"
    commentary: str
