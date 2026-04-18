"""Per-asset model-vs-market comparison panel data."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class ModelVsMarketRow(BaseModel):
    asset_id: str
    ticker: str
    as_of: date
    model_pos: Optional[float] = None
    implied_pos: Optional[float] = None
    pos_direction: str = "unknown"          # "underpriced" / "overpriced" / "aligned" / "unknown"
    pos_gap_pct: Optional[float] = None     # (model - implied) as fraction
    model_ev_millions: Optional[float] = None
    market_ev_millions: Optional[float] = None
    ev_gap_pct: Optional[float] = None      # (model - market) / market
    ev_direction: str = "unknown"
    financing_adjusted_ev_millions: Optional[float] = None
    upside_pct: Optional[float] = None
    downside_pct: Optional[float] = None
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ModelVsMarketPanel(BaseModel):
    built_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    rows: list[ModelVsMarketRow]

    def top_underpriced(self, n: int = 5) -> list[ModelVsMarketRow]:
        return sorted(
            [r for r in self.rows if r.ev_direction == "underpriced"],
            key=lambda r: r.ev_gap_pct or 0.0,
            reverse=True,
        )[:n]

    def top_overpriced(self, n: int = 5) -> list[ModelVsMarketRow]:
        return sorted(
            [r for r in self.rows if r.ev_direction == "overpriced"],
            key=lambda r: r.ev_gap_pct or 0.0,
        )[:n]
