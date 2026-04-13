"""Data models for structured scientific similarity scoring between assets."""
from __future__ import annotations

from pydantic import BaseModel, Field


class DimensionScore(BaseModel):
    """Score on a single similarity dimension."""

    score: float = Field(ge=0.0, le=1.0)
    reason: str
    weight: float = Field(gt=0.0)


class AssetSimilarityScore(BaseModel):
    """
    Five-dimension scientific similarity between two assets.

    Each dimension carries a score (0.0–1.0), a human-readable reason,
    and the weight used in the composite.  ``composite_score`` is the
    weighted sum.  ``confidence_flags`` lists normalization warnings that
    reduce trust in specific dimensions.
    """

    asset_a_id: str
    asset_b_id: str

    indication_overlap: DimensionScore
    target_overlap: DimensionScore
    moa_overlap: DimensionScore
    modality_overlap: DimensionScore
    stage_proximity: DimensionScore

    composite_score: float = Field(ge=0.0, le=1.0)
    confidence_flags: list[str] = Field(default_factory=list)
