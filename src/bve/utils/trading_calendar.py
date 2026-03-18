"""
Trading-day calendar utilities.

Uses numpy.busdaycalendar with NYSE holiday list for accurate US market
day arithmetic.  The holiday list covers NYSE-observed holidays from 2010
through 2035.  This eliminates the ~10/year distortion from pure Mon–Fri
arithmetic (Thanksgiving, Christmas, New Year's, etc.).

For T+1 / T+5 windows holiday accuracy matters; for T+90 / T+180 the
effect is 1–2 days at most but is now correct at all windows.

Holiday source: NYSE market holiday schedule (Rule 51 and related).
Half-days are NOT excluded (the market is open; prices exist).

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


# ---------------------------------------------------------------------------
# NYSE observed holiday calendar (2010–2035)
# ---------------------------------------------------------------------------
# Rules:
#   New Year's Day        — Jan 1 (observed Mon if Sun, Fri if Sat)
#   Martin Luther King Jr — 3rd Monday of January
#   Presidents' Day       — 3rd Monday of February
#   Good Friday           — Friday before Easter
#   Memorial Day          — Last Monday of May
#   Juneteenth            — Jun 19 (observed; added 2022)
#   Independence Day      — Jul 4 (observed)
#   Labor Day             — 1st Monday of September
#   Thanksgiving          — 4th Thursday of November
#   Christmas Day         — Dec 25 (observed)
#
# Closures for national events (9/11 closures, Hurricane Sandy, etc.) are not
# included; those are rare ad-hoc closures unrelated to signal window math.

_NYSE_HOLIDAYS: list[str] = [
    # 2010
    "2010-01-01", "2010-01-18", "2010-02-15", "2010-04-02", "2010-05-31",
    "2010-07-05", "2010-09-06", "2010-11-25", "2010-12-24",
    # 2011
    "2011-01-17", "2011-02-21", "2011-04-22", "2011-05-30",
    "2011-07-04", "2011-09-05", "2011-11-24", "2011-12-26",
    # 2012
    "2012-01-02", "2012-01-16", "2012-02-20", "2012-04-06", "2012-05-28",
    "2012-07-04", "2012-09-03", "2012-11-22", "2012-12-25",
    # 2013
    "2013-01-01", "2013-01-21", "2013-02-18", "2013-03-29", "2013-05-27",
    "2013-07-04", "2013-09-02", "2013-11-28", "2013-12-25",
    # 2014
    "2014-01-01", "2014-01-20", "2014-02-17", "2014-04-18", "2014-05-26",
    "2014-07-04", "2014-09-01", "2014-11-27", "2014-12-25",
    # 2015
    "2015-01-01", "2015-01-19", "2015-02-16", "2015-04-03", "2015-05-25",
    "2015-07-03", "2015-09-07", "2015-11-26", "2015-12-25",
    # 2016
    "2016-01-01", "2016-01-18", "2016-02-15", "2016-03-25", "2016-05-30",
    "2016-07-04", "2016-09-05", "2016-11-24", "2016-12-26",
    # 2017
    "2017-01-02", "2017-01-16", "2017-02-20", "2017-04-14", "2017-05-29",
    "2017-07-04", "2017-09-04", "2017-11-23", "2017-12-25",
    # 2018
    "2018-01-01", "2018-01-15", "2018-02-19", "2018-03-30", "2018-05-28",
    "2018-07-04", "2018-09-03", "2018-11-22", "2018-12-05", "2018-12-25",
    # 2019
    "2019-01-01", "2019-01-21", "2019-02-18", "2019-04-19", "2019-05-27",
    "2019-07-04", "2019-09-02", "2019-11-28", "2019-12-25",
    # 2020
    "2020-01-01", "2020-01-20", "2020-02-17", "2020-04-10", "2020-05-25",
    "2020-07-03", "2020-09-07", "2020-11-26", "2020-12-25",
    # 2021
    "2021-01-01", "2021-01-18", "2021-02-15", "2021-04-02", "2021-05-31",
    "2021-07-05", "2021-09-06", "2021-11-25", "2021-12-24",
    # 2022
    "2022-01-17", "2022-02-21", "2022-04-15", "2022-05-30", "2022-06-20",
    "2022-07-04", "2022-09-05", "2022-11-24", "2022-12-26",
    # 2023
    "2023-01-02", "2023-01-16", "2023-02-20", "2023-04-07", "2023-05-29",
    "2023-06-19", "2023-07-04", "2023-09-04", "2023-11-23", "2023-12-25",
    # 2024
    "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27",
    "2024-06-19", "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
    # 2025
    "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18",
    "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27",
    "2025-12-25",
    # 2026
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    # 2027
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
    # 2028
    "2028-01-17", "2028-02-21", "2028-04-14", "2028-05-29", "2028-06-19",
    "2028-07-04", "2028-09-04", "2028-11-23", "2028-12-25",
    # 2029
    "2029-01-01", "2029-01-15", "2029-02-19", "2029-03-30", "2029-05-28",
    "2029-06-19", "2029-07-04", "2029-09-03", "2029-11-22", "2029-12-25",
    # 2030
    "2030-01-01", "2030-01-21", "2030-02-18", "2030-04-19", "2030-05-27",
    "2030-06-19", "2030-07-04", "2030-09-02", "2030-11-28", "2030-12-25",
    # 2031–2035 (projected)
    "2031-01-01", "2031-01-20", "2031-02-17", "2031-04-11", "2031-05-26",
    "2031-06-19", "2031-07-04", "2031-09-01", "2031-11-27", "2031-12-25",
    "2032-01-01", "2032-01-19", "2032-02-16", "2032-03-26", "2032-05-31",
    "2032-06-18", "2032-07-05", "2032-09-06", "2032-11-25", "2032-12-24",
    "2033-01-17", "2033-02-21", "2033-04-15", "2033-05-30", "2033-06-20",
    "2033-07-04", "2033-09-05", "2033-11-24", "2033-12-26",
    "2034-01-02", "2034-01-16", "2034-02-20", "2034-04-07", "2034-05-29",
    "2034-06-19", "2034-07-04", "2034-09-04", "2034-11-23", "2034-12-25",
    "2035-01-01", "2035-01-15", "2035-02-19", "2035-04-20", "2035-05-28",
    "2035-06-19", "2035-07-04", "2035-09-03", "2035-11-22", "2035-12-25",
]

# Build once at module load; numpy.busdaycalendar is immutable after creation.
_NYSE_CALENDAR: np.busdaycalendar = np.busdaycalendar(holidays=_NYSE_HOLIDAYS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Standard event-reaction windows (in trading days).
WINDOWS_TD: tuple[int, ...] = (1, 5, 30, 90, 180)


def trading_days_after(start: date | datetime, n_trading_days: int) -> date:
    """
    Return the date that is *n_trading_days* NYSE trading days after *start*.

    Accounts for NYSE-observed holidays (2010–2035) in addition to weekends.

    Parameters
    ----------
    start:
        Reference date or UTC datetime.  If a datetime is passed its date
        component is used.
    n_trading_days:
        Number of trading days to advance.  Must be ≥ 0.

    Returns
    -------
    date
        Calendar date of the target trading day.

    Examples
    --------
    >>> from datetime import date
    >>> trading_days_after(date(2024, 11, 28), 1)  # Thanksgiving + 1
    datetime.date(2024, 11, 29)
    """
    if isinstance(start, datetime):
        start = start.date()
    if n_trading_days < 0:
        raise ValueError(f"n_trading_days must be ≥ 0, got {n_trading_days}")
    result = np.busday_offset(
        start.isoformat(), n_trading_days, roll="forward", busdaycal=_NYSE_CALENDAR
    )
    return date.fromisoformat(str(result))


def is_trading_day_elapsed(
    signal_date: date | datetime,
    n_trading_days: int,
    as_of: Optional[date | datetime] = None,
) -> bool:
    """
    Return True if at least *n_trading_days* NYSE trading days have elapsed
    since *signal_date*.

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
    """Return the number of NYSE trading days in (start, end] inclusive."""
    if isinstance(start, datetime):
        start = start.date()
    if isinstance(end, datetime):
        end = end.date()
    return int(np.busday_count(start.isoformat(), end.isoformat(), busdaycal=_NYSE_CALENDAR))


def resolution_targets(signal_date: date | datetime) -> dict[int, date]:
    """
    Return a mapping of {trading_day_window: target_date} for all standard windows.

    Useful for pre-computing the resolution schedule for an event outcome.

    Returns
    -------
    dict mapping each window in WINDOWS_TD to its NYSE-adjusted settlement date.
    """
    return {w: trading_days_after(signal_date, w) for w in WINDOWS_TD}
