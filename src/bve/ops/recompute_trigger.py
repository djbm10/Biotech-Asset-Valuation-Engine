"""
Recompute trigger — Sprint 15 Task 15.2.

Checks KnowledgeStore for new material events since the last screen date
and returns the tickers that warrant a fresh valuation run.

Usage
-----
    from bve.ops.recompute_trigger import check_and_trigger
    from bve.intelligence.knowledge_layer import KnowledgeStore
    from datetime import date

    store = KnowledgeStore("outputs/intelligence/ops.db")
    pending = check_and_trigger(store, as_of=date.today())
    store.close()
    print(f"Tickers to recompute: {pending}")
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

_LOG = logging.getLogger("bve.ops.recompute_trigger")


def check_and_trigger(
    store: "KnowledgeStore",  # type: ignore[name-defined]  # noqa: F821
    as_of: date,
    *,
    lookback_days: int = 7,
    require_recompute_flag: bool = True,
) -> list[str]:
    """
    Return tickers that have new material detected_events since last_screen_date.

    Parameters
    ----------
    store               : open KnowledgeStore instance
    as_of               : reference date (usually date.today())
    lookback_days       : how far back to search for events (default 7)
    require_recompute_flag : only return tickers whose requires_recompute=True (default True)

    Returns
    -------
    Sorted list of ticker strings that should be recomputed.
    """
    from datetime import timedelta

    since_str = (datetime.combine(as_of, datetime.min.time()).replace(tzinfo=timezone.utc)
                 - timedelta(days=lookback_days)).isoformat()

    events = store.get_detected_events(since=since_str, requires_recompute=require_recompute_flag)

    tickers: set[str] = set()
    for ev in events:
        tickers.add(ev["ticker"])

    result = sorted(tickers)
    if result:
        _LOG.info("Recompute triggered for %d tickers: %s", len(result), result)
    return result


def pending_trigger_count(
    store: "KnowledgeStore",  # type: ignore[name-defined]  # noqa: F821
    as_of: date,
    lookback_days: int = 7,
) -> int:
    """Return the count of pending recompute triggers (convenience wrapper)."""
    return len(check_and_trigger(store, as_of, lookback_days=lookback_days))
