"""Portfolio context — position sizing, concentration, and budget constraints."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class HoldingExposure(BaseModel):
    """Exposure detail for a single holding in the portfolio."""

    asset_id: str
    ticker: str
    position_size_pct: float = Field(ge=0.0, le=1.0)
    therapeutic_area: str
    modality: str
    catalyst_month: Optional[str] = None
    risk_bucket: str  # "early" | "late" | "commercial"
    market_cap_tier: str  # "micro" | "small" | "mid" | "large"


class PortfolioSnapshot(BaseModel):
    """Point-in-time snapshot of all portfolio holdings."""

    snapshot_date: date
    holdings: list[HoldingExposure] = Field(default_factory=list)
    gross_exposure_pct: float
    net_exposure_pct: float
    ta_concentration: dict[str, float] = Field(default_factory=dict)
    modality_concentration: dict[str, float] = Field(default_factory=dict)
    catalyst_month_concentration: dict[str, float] = Field(default_factory=dict)
    risk_bucket_concentration: dict[str, float] = Field(default_factory=dict)


class PortfolioContext(BaseModel):
    """Portfolio-level context for a single asset's sizing and constraints."""

    asset_id: str
    snapshot: PortfolioSnapshot
    current_position_pct: float
    ta_remaining_budget_pct: float
    modality_remaining_budget_pct: float
    catalyst_cluster_count: int
    liquidity_score: float = Field(ge=0.0, le=1.0)
    crowding_score: float = Field(ge=0.0, le=1.0)
