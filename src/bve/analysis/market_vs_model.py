"""Market vs model comparison — gap analysis and learning records."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class MarketVsModelComparison(BaseModel):
    """Single comparison of market-implied vs model values."""

    asset_id: str
    ticker: str
    comparison_date: date
    model_pos: float = Field(ge=0.0, le=1.0)
    implied_pos: float
    pos_gap: float  # implied - model
    model_peak_sales_millions: float
    implied_peak_sales_millions: float
    peak_sales_gap_millions: float
    model_ev_millions: float
    market_ev_millions: float
    ev_gap_millions: float
    ev_gap_pct: float
    pos_direction: str  # "underpriced" | "overpriced" | "aligned"
    summary: str


class LearningRecord(BaseModel):
    """Post-hoc record linking predicted gap direction to realized outcome."""

    asset_id: str
    comparison_date: date
    catalyst_date: date
    realized_outcome: str
    predicted_gap_direction: str
    was_correct: bool
    return_30d: float
    return_90d: float


class MarketVsModel(BaseModel):
    """Aggregated market vs model comparisons and learning records for an asset."""

    asset_id: str
    comparisons: list[MarketVsModelComparison] = Field(default_factory=list)
    learning_records: list[LearningRecord] = Field(default_factory=list)
