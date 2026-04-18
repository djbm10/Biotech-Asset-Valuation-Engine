"""Structured variant perception object: market view vs model view with explicit evidence and falsifiers."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    """A piece of evidence that supports or opposes the model view."""
    description: str
    supports_model: bool            # True = supports model view, False = supports consensus
    strength: str = "moderate"      # "strong" / "moderate" / "weak"
    source: Optional[str] = None
    date_observed: Optional[date] = None


class PerceptionDimension(BaseModel):
    """One axis of disagreement between market and model."""
    dimension: str                  # "pos" / "peak_sales" / "timing" / "label_breadth" /
                                    # "payer_access" / "competition" / "financing" / "management"
    market_view: str                # plain English: what the market believes
    model_view: str                 # plain English: what the model thinks
    gap_direction: str              # "bullish" / "bearish" / "neutral" (model vs market)
    gap_magnitude: str              # "large" / "moderate" / "small"
    supporting_evidence: list[EvidenceItem] = Field(default_factory=list)
    opposing_evidence: list[EvidenceItem] = Field(default_factory=list)
    falsifier: str                  # what single event would prove market right
    expected_resolution_days: Optional[int] = None


class VariantPerception(BaseModel):
    """
    The core variant perception object.

    Mandatory before any trade signal is generated.
    Forces explicit documentation of disagreement with the market.
    """
    asset_id: str
    ticker: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Summary thesis
    market_believes: str            # one-paragraph: what the market is pricing
    model_thinks: str               # one-paragraph: what the model believes
    why_gap_exists: str             # one-paragraph: reason for disagreement
    # Structured dimensions
    dimensions: list[PerceptionDimension] = Field(default_factory=list)
    # Trade gate
    is_documented: bool = True      # must be True before trade signal allowed
    conviction: str = "medium"      # "high" / "medium" / "low"
    # Resolution
    primary_catalyst: Optional[str] = None
    days_to_resolution: Optional[int] = None
    # Post-resolution
    was_correct: Optional[bool] = None
    resolution_note: Optional[str] = None
    resolved_at: Optional[datetime] = None

    def bullish_dimensions(self) -> list[PerceptionDimension]:
        return [d for d in self.dimensions if d.gap_direction == "bullish"]

    def bearish_dimensions(self) -> list[PerceptionDimension]:
        return [d for d in self.dimensions if d.gap_direction == "bearish"]

    def net_conviction_direction(self) -> str:
        """Returns 'bullish', 'bearish', or 'mixed' based on dimension balance."""
        bulls = len(self.bullish_dimensions())
        bears = len(self.bearish_dimensions())
        if bulls > bears:
            return "bullish"
        if bears > bulls:
            return "bearish"
        return "mixed"
