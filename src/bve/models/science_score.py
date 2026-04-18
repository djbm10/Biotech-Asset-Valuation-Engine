"""Science score — structured assessment of scientific quality and risk."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ScienceScoreComponent(BaseModel):
    """A single dimension of the science score."""

    name: str
    score: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0)
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)


class ScienceScore(BaseModel):
    """Composite science quality score for a drug asset."""

    asset_id: str
    scored_at: datetime
    components: list[ScienceScoreComponent] = Field(default_factory=list)
    composite_score: float = Field(ge=0.0, le=1.0)
    confidence_band_low: float = Field(ge=0.0, le=1.0)
    confidence_band_high: float = Field(ge=0.0, le=1.0)
    top_positives: list[str] = Field(default_factory=list)
    top_risks: list[str] = Field(default_factory=list)
    plain_english_summary: str

    @property
    def weighted_score(self) -> float:
        """Weighted average score across all components."""
        if not self.components:
            return 0.0
        total_weight = sum(c.weight for c in self.components)
        if total_weight == 0.0:
            return 0.0
        return sum(c.score * c.weight for c in self.components) / total_weight
