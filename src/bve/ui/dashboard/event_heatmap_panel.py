"""Event frequency and materiality heatmap panel data."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class EventHeatmapCell(BaseModel):
    asset_id: str
    ticker: str
    week_start: date
    event_count: int = 0
    max_materiality: float = 0.0
    dominant_event_type: Optional[str] = None
    heat_level: str = "none"        # "none" / "low" / "medium" / "high"


class EventHeatmapPanel(BaseModel):
    built_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cells: list[EventHeatmapCell]
    asset_ids: list[str]
    weeks: list[date]

    def hot_cells(self, threshold: float = 0.7) -> list[EventHeatmapCell]:
        return [c for c in self.cells if c.max_materiality >= threshold]

    def asset_event_counts(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for c in self.cells:
            result[c.asset_id] = result.get(c.asset_id, 0) + c.event_count
        return result
