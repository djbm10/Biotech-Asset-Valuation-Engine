"""Recommendation engine — composite scoring and action generation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


class RecommendationInput(BaseModel):
    """All inputs required to generate a recommendation."""

    asset_id: str
    ticker: str
    valuation_gap_pct: float
    thesis_confidence: float = Field(ge=0.0, le=1.0)
    catalyst_expected_return_pct: float
    financing_risk_score: float = Field(ge=0.0, le=1.0)
    science_score: float = Field(ge=0.0, le=1.0)
    competition_risk_score: float = Field(ge=0.0, le=1.0)
    portfolio_context: Optional[Any] = None


class Recommendation(BaseModel):
    """Generated recommendation with action, rationale, and supporting detail."""

    asset_id: str
    ticker: str
    recommendation_date: datetime
    action: str  # "add" | "hold" | "reduce" | "avoid" | "watchlist"
    target_position_pct: float
    rationale: str
    top_risks: list[str] = Field(default_factory=list)
    top_catalysts: list[str] = Field(default_factory=list)
    conviction: str  # "high" | "medium" | "low"
    composite_score: float = Field(ge=0.0, le=1.0)


class RecommendationEngine:
    """Generates recommendations from structured inputs using a weighted formula.

    Formula:
      composite = (
          valuation_gap_normalised * 0.30
          + thesis_confidence        * 0.25
          + catalyst_return_norm     * 0.20
          + financing_quality        * 0.15
          + science_score            * 0.10
      )
      clipped to [0, 1].

    Action mapping:
      composite >= 0.65 → add
      composite >= 0.50 → hold
      composite >= 0.35 → watchlist
      otherwise         → avoid
    """

    def recommend(self, inputs: RecommendationInput) -> Recommendation:
        """Return a Recommendation derived from the provided inputs."""
        valuation_norm = max(0.0, min(1.0, (inputs.valuation_gap_pct + 100.0) / 200.0))
        catalyst_norm = max(0.0, min(1.0, (inputs.catalyst_expected_return_pct + 100.0) / 200.0))
        financing_quality = 1.0 - inputs.financing_risk_score

        composite = (
            valuation_norm * 0.30
            + inputs.thesis_confidence * 0.25
            + catalyst_norm * 0.20
            + financing_quality * 0.15
            + inputs.science_score * 0.10
        )
        composite = max(0.0, min(1.0, composite))

        if composite >= 0.65:
            action = "add"
            conviction = "high"
            target_pct = 0.10
        elif composite >= 0.50:
            action = "hold"
            conviction = "medium"
            target_pct = 0.05
        elif composite >= 0.35:
            action = "watchlist"
            conviction = "low"
            target_pct = 0.0
        else:
            action = "avoid"
            conviction = "low"
            target_pct = 0.0

        rationale = (
            f"Composite score {composite:.2f} driven by thesis_confidence={inputs.thesis_confidence:.2f}, "
            f"valuation_gap={inputs.valuation_gap_pct:.1f}%, "
            f"financing_quality={financing_quality:.2f}."
        )

        return Recommendation(
            asset_id=inputs.asset_id,
            ticker=inputs.ticker,
            recommendation_date=datetime.now(timezone.utc),
            action=action,
            target_position_pct=target_pct,
            rationale=rationale,
            top_risks=[],
            top_catalysts=[],
            conviction=conviction,
            composite_score=composite,
        )
