"""Trial design score — structured assessment of clinical trial design quality."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TrialDesignScoreComponent(BaseModel):
    """A single dimension of the trial design score."""

    name: str
    score: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0)
    rationale: str


class TrialDesignScore(BaseModel):
    """Composite trial design quality score for a clinical trial."""

    asset_id: str
    trial_id: Optional[str] = None
    scored_at: datetime
    components: list[TrialDesignScoreComponent] = Field(default_factory=list)
    composite_score: float = Field(ge=0.0, le=1.0)
    endpoint_score: float = Field(ge=0.0, le=1.0)
    power_score: float = Field(ge=0.0, le=1.0)
    design_score: float = Field(ge=0.0, le=1.0)
    biomarker_score: float = Field(ge=0.0, le=1.0)
    regulatory_alignment_score: float = Field(ge=0.0, le=1.0)
    plain_english_summary: str
