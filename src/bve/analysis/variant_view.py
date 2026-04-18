"""Variant view analysis — where the model differs from consensus and why."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class ThesisEvidence(BaseModel):
    """A single piece of evidence supporting or refuting the model's view."""

    evidence_id: str
    source: str
    description: str
    supports_model_view: bool
    confidence: float = Field(ge=0.0, le=1.0)
    date_observed: date


class KillCriterion(BaseModel):
    """A falsifiable criterion that, if triggered, breaks the thesis."""

    criterion_id: str
    description: str
    dimension: str
    threshold_description: str
    observable_by: Optional[date] = None
    is_triggered: bool = False


class ConsensusAssumption(BaseModel):
    """What the market/consensus assumes on a given dimension."""

    dimension: str
    consensus_value: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: str


class ModelAssumption(BaseModel):
    """What the model assumes on a given dimension."""

    dimension: str
    model_value: str
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


class VariantDelta(BaseModel):
    """The gap between consensus and model on a single dimension."""

    dimension: str
    consensus_assumption: ConsensusAssumption
    model_assumption: ModelAssumption
    delta_summary: str
    magnitude: float = Field(ge=-1.0, le=1.0)
    supporting_evidence: list[ThesisEvidence] = Field(default_factory=list)
    kill_criteria: list[KillCriterion] = Field(default_factory=list)
    time_to_resolution_days: Optional[int] = None
    falsifier: str


class VariantThesis(BaseModel):
    """Full variant view thesis for a single asset."""

    asset_id: str
    ticker: str
    created_at: datetime
    updated_at: datetime
    what_market_believes: str
    what_model_thinks: str
    why_gap_exists: str
    catalysts_to_resolve: list[str] = Field(default_factory=list)
    confidence_score: float = Field(ge=0.0, le=1.0)
    deltas: list[VariantDelta] = Field(default_factory=list)
    overall_conviction: str  # "high" | "medium" | "low"
