"""
Trading-day calendar utilities.

Uses numpy.busday_offset for Mon–Fri business day arithmetic.  This is a
deliberate simplification: US market holidays (~10/year) are not accounted for.
For T+30 / T+90 / T+180 windows the distortion is at most 1–2 days — acceptable
for event reaction studies.  Upgrade to pandas_market_calendars when precision
matters (e.g., day-of-event intraday studies).

Usage
-----
    from bve.utils.trading_calendar import trading_days_after, is_resolved

    settle_date = trading_days_after(signal_date, 5)   # T+5 trading days
    if is_resolved(signal_date, 30, as_of=today):      # T+30 elapsed?
        backfill_price(...)
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

import numpy as np


# Standard event-reaction windows (in trading days).
WINDOWS_TD: tuple[int, ...] = (1, 5, 30, 90, 180)


def trading_days_after(start: date | datetime, n_trading_days: int) -> date:
    """
    Return the date that is *n_trading_days* Mon–Fri business days after *start*.

    Parameters
    ----------
    start:
        Reference date or UTC datetime.  If a datetime is passed its date
        component is used.
    n_trading_days:
        Number of business days to advance.  Must be ≥ 0.

    Returns
    -------
    date
        Calendar date of the target trading day.

    Examples
    --------
    >>> from datetime import date
    >>> trading_days_after(date(2024, 6, 3), 5)  # Monday + 5 bd = next Monday
    datetime.date(2024, 6, 10)
    """
    if isinstance(start, datetime):
        start = start.date()
    if n_trading_days < 0:
        raise ValueError(f"n_trading_days must be ≥ 0, got {n_trading_days}")
    if n_trading_days == 0:
        # numpy.busday_offset with roll='forward' may jump if start is a weekend.
        result = np.busday_offset(start.isoformat(), 0, roll="forward")
    else:
        result = np.busday_offset(start.isoformat(), n_trading_days, roll="forward")
    return date.fromisoformat(str(result))


def is_trading_day_elapsed(
    signal_date: date | datetime,
    n_trading_days: int,
    as_of: Optional[date | datetime] = None,
) -> bool:
    """
    Return True if at least *n_trading_days* have elapsed since *signal_date*.

    Parameters
    ----------
    signal_date:
        The reference event date.
    n_trading_days:
        Window to check (e.g., 5 for T+5).
    as_of:
        Date to check against.  Defaults to today (UTC).
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc).date()
    if isinstance(as_of, datetime):
        as_of = as_of.date()
    target = trading_days_after(signal_date, n_trading_days)
    return as_of >= target


def count_trading_days_between(start: date | datetime, end: date | datetime) -> int:
    """Return the number of Mon–Fri business days in (start, end] inclusive."""
    if isinstance(start, datetime):
        start = start.date()
    if isinstance(end, datetime):
        end = end.date()
    return int(np.busday_count(start.isoformat(), end.isoformat()))


def resolution_targets(signal_date: date | datetime) -> dict[int, date]:
    """
    Return a mapping of {trading_day_window: target_date} for all standard windows.

    Useful for pre-computing the resolution schedule for an event outcome.

    Returns
    -------
    dict mapping each window in WINDOWS_TD to its calendar settlement date.
    """
    return {w: trading_days_after(signal_date, w) for w in WINDOWS_TD}
