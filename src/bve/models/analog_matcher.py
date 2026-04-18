"""Analog matcher — winning and failing historical analogues for POS and sales calibration."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Analog(BaseModel):
    """A historical drug program used as a comparison point."""

    analog_id: str
    name: str
    indication: str
    target: Optional[str] = None
    mechanism: Optional[str] = None
    modality: Optional[str] = None
    phase_at_comparison: str
    outcome: str  # "approved" | "failed" | "ongoing"
    peak_sales_millions: Optional[float] = None
    pos_at_phase: Optional[float] = None


class AnalogMatch(BaseModel):
    """A matched analogue with similarity scoring and lessons."""

    focal_asset_id: str
    analog: Analog
    similarity_score: float = Field(ge=0.0, le=1.0)
    is_winner: bool
    key_similarities: list[str] = Field(default_factory=list)
    key_differences: list[str] = Field(default_factory=list)
    lesson: str


class AnalogMatcher(BaseModel):
    """Aggregated analogue matching result for a focal asset."""

    asset_id: str
    matched_at: datetime
    winning_analogs: list[AnalogMatch] = Field(default_factory=list)
    failing_analogs: list[AnalogMatch] = Field(default_factory=list)
    pos_implied_by_analogs: Optional[float] = None
    analog_confidence: float = Field(ge=0.0, le=1.0)
    summary: str
