"""Portfolio recommendation change tracker panel data."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

_RANK = {"add": 4, "hold": 3, "watchlist": 2, "avoid": 1, "reduce": 0}


class RecommendationChangeRow(BaseModel):
    asset_id: str
    ticker: str
    change_date: date
    previous_action: Optional[str] = None    # add / hold / reduce / avoid / watchlist / None (new)
    current_action: str
    previous_score: Optional[float] = None
    current_score: float
    score_delta: Optional[float] = None
    conviction: str
    headline_reason: str                     # one-line reason for the change
    is_new: bool = False                     # True if no previous recommendation


class RecommendationPanel(BaseModel):
    built_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    rows: list[RecommendationChangeRow]

    def new_adds(self) -> list[RecommendationChangeRow]:
        return [r for r in self.rows if r.current_action == "add" and r.is_new]

    def upgrades(self) -> list[RecommendationChangeRow]:
        return [
            r for r in self.rows
            if not r.is_new
            and r.previous_action is not None
            and _RANK.get(r.current_action, 0) > _RANK.get(r.previous_action, 0)
        ]

    def downgrades(self) -> list[RecommendationChangeRow]:
        return [
            r for r in self.rows
            if not r.is_new
            and r.previous_action is not None
            and _RANK.get(r.current_action, 0) < _RANK.get(r.previous_action, 0)
        ]
