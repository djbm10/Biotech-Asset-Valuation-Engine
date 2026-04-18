"""Implied market expectations vs model — market snapshot and back-solved assumptions."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class MarketSnapshot(BaseModel):
    """Point-in-time market data for an asset."""

    asset_id: str
    ticker: str
    snapshot_date: date
    market_cap_millions: float
    ev_millions: float
    share_price: float
    shares_outstanding_millions: float
    cash_millions: float
    debt_millions: float


class ConsensusEstimate(BaseModel):
    """Sell-side or external consensus estimate for an asset."""

    asset_id: str
    ticker: str
    estimate_date: date
    source: str
    model_pos: float = Field(ge=0.0, le=1.0)
    model_peak_sales_millions: float
    analyst_count: int = Field(ge=0)
    consensus_rnpv_millions: float


class ImpliedExpectationsRecord(BaseModel):
    """Single back-solved implied expectations observation."""

    asset_id: str
    ticker: str
    snapshot_date: date
    implied_pos: float
    implied_peak_sales_millions: float
    implied_dilution_pct: float
    implied_timeline_years: float
    model_pos: float = Field(ge=0.0, le=1.0)
    model_peak_sales_millions: float
    model_rnpv_millions: float
    current_ev_millions: float
    upside_pct: float
    downside_pct: float
    valuation_gap_millions: float
    methodology: str = "nav_backsolve"


class ImpliedExpectations(BaseModel):
    """Collection of implied expectations records for a single asset."""

    asset_id: str
    records: list[ImpliedExpectationsRecord] = Field(default_factory=list)
    latest: Optional[ImpliedExpectationsRecord] = None
