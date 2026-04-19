"""Structured postmortem analysis for closed positions and resolved catalysts."""

from __future__ import annotations

import uuid
from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ErrorCategory(str, Enum):
    """Classification of what the model got wrong (or right)."""

    POS_OVERESTIMATE = "pos_overestimate"  # model too bullish on P(success)
    POS_UNDERESTIMATE = "pos_underestimate"  # model too bearish
    TIMING_ERROR = "timing_error"  # right direction, wrong timing
    MARKET_EXPECTATIONS_GAP = "market_expectations_gap"  # right science, mis-read market
    LABEL_BREADTH_ERROR = "label_breadth_error"  # approved but narrow label
    COMPETITION_SURPRISE = "competition_surprise"
    FINANCING_SURPRISE = "financing_surprise"
    CORRECT = "correct"  # no error — positive outcome


class PostmortemEntry(BaseModel):
    """A complete postmortem record for one resolved catalyst event."""

    postmortem_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str
    ticker: Optional[str] = None
    catalyst_date: date
    created_date: date
    catalyst_type: str
    actual_result: str  # "success" | "failure" | "partial"
    model_pos_at_entry: float
    market_implied_pos_at_entry: Optional[float] = None
    price_change_pct: Optional[float] = None
    primary_error: ErrorCategory
    secondary_errors: list[ErrorCategory] = Field(default_factory=list)
    what_model_got_right: str = ""
    what_model_got_wrong: str = ""
    rule_changes_suggested: list[str] = Field(default_factory=list)
    lessons: str = ""


class PostmortemStore:
    """In-memory store for postmortem entries.

    Postmortems are manually authored narrative records; no SQLite persistence
    is required. Use ``add()`` to register entries and the query helpers to
    slice and aggregate them.
    """

    def __init__(self) -> None:
        self._entries: dict[str, PostmortemEntry] = {}

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def add(self, entry: PostmortemEntry) -> None:
        """Add a postmortem entry; silently overwrites if ID already exists."""
        self._entries[entry.postmortem_id] = entry

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get(self, postmortem_id: str) -> Optional[PostmortemEntry]:
        """Return the entry for the given ID, or None if not found."""
        return self._entries.get(postmortem_id)

    def list_all(self) -> list[PostmortemEntry]:
        """Return all entries, sorted by catalyst_date ascending."""
        return sorted(self._entries.values(), key=lambda e: e.catalyst_date)

    def by_error_category(self, category: ErrorCategory) -> list[PostmortemEntry]:
        """Return entries whose primary_error matches ``category``."""
        return [e for e in self._entries.values() if e.primary_error == category]

    def by_asset(self, asset_id: str) -> list[PostmortemEntry]:
        """Return all entries for a given asset_id."""
        return [e for e in self._entries.values() if e.asset_id == asset_id]

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    def error_distribution(self) -> dict[str, int]:
        """Return a mapping of ErrorCategory value → count of primary errors."""
        dist: dict[str, int] = {}
        for entry in self._entries.values():
            key = entry.primary_error.value
            dist[key] = dist.get(key, 0) + 1
        return dist

    def most_common_error(self) -> Optional[ErrorCategory]:
        """Return the most frequent primary ErrorCategory, or None if empty."""
        dist = self.error_distribution()
        if not dist:
            return None
        top_key = max(dist, key=lambda k: dist[k])
        return ErrorCategory(top_key)
