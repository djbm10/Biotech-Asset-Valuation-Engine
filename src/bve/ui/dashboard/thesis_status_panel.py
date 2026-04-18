"""Per-asset thesis health summary panel data."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class ThesisStatusRow(BaseModel):
    asset_id: str
    ticker: str
    as_of: date
    overall_conviction: str                  # "high" / "medium" / "low"
    confidence_score: float                  # 0-1
    active_kill_criteria: int = 0
    triggered_kill_criteria: int = 0
    open_deltas: int = 0                     # number of unresolved VariantDelta dimensions
    days_since_updated: Optional[int] = None
    thesis_health: str = "unknown"           # "healthy" / "watch" / "at_risk" / "broken"
    summary: str = ""

    @property
    def kill_criteria_triggered(self) -> bool:
        return self.triggered_kill_criteria > 0


class ThesisStatusPanel(BaseModel):
    built_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    rows: list[ThesisStatusRow]

    def at_risk(self) -> list[ThesisStatusRow]:
        return [r for r in self.rows if r.thesis_health in ("at_risk", "broken")]

    def healthy(self) -> list[ThesisStatusRow]:
        return [r for r in self.rows if r.thesis_health == "healthy"]
