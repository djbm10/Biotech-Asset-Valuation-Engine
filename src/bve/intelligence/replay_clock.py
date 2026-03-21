"""Simulation clock abstraction. Production → live time. Replay → fixed date."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional


class ReplayClock:
    """
    Controls the notion of "now" for the replay system.

    In production mode (as_of_date=None) all calls delegate to the real
    system clock.  In replay mode a fixed date is frozen and advanced
    explicitly via ``advance()``.

    Parameters
    ----------
    as_of_date:
        The fixed date to freeze time at.  Pass ``None`` for live mode.
    """

    def __init__(self, as_of_date: Optional[date] = None) -> None:
        self._as_of = as_of_date

    def today(self) -> date:
        """Return the current (possibly frozen) date."""
        return self._as_of if self._as_of is not None else date.today()

    def now(self) -> datetime:
        """Return the current (possibly frozen) datetime (UTC)."""
        if self._as_of is not None:
            return datetime(
                self._as_of.year,
                self._as_of.month,
                self._as_of.day,
                tzinfo=timezone.utc,
            )
        return datetime.now(timezone.utc)

    @property
    def is_replay(self) -> bool:
        """True when the clock is frozen to a specific date."""
        return self._as_of is not None

    def advance(self, days: int) -> "ReplayClock":
        """Return a new ReplayClock advanced by *days* from the current date."""
        base = self._as_of or date.today()
        return ReplayClock(base + timedelta(days=days))

    def __repr__(self) -> str:
        if self._as_of:
            return f"ReplayClock(replay={self._as_of})"
        return "ReplayClock(live)"
