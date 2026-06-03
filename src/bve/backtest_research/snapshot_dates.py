"""
snapshot_dates — compute pre-announcement snapshot windows.

For a deal announced on `announcement_date`, generate snapshot dates at
-365, -180, -90, and -30 days.  The snapshot date is the date at which
all features must be frozen (no data after this date may be used).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Sequence


# ---------------------------------------------------------------------------
# Default lookback windows (days before announcement)
# ---------------------------------------------------------------------------

DEFAULT_LOOKBACK_DAYS: tuple[int, ...] = (365, 180, 90, 30)


# ---------------------------------------------------------------------------
# SnapshotDate
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SnapshotDate:
    """
    A single frozen point-in-time for backtest evaluation.

    Fields
    ------
    snapshot_date       : the feature freeze date (all data must be <= this)
    announcement_date   : the actual deal announcement date (label only)
    days_before         : how many calendar days before announcement
    deal_id             : optional identifier for the associated deal
    acquirer_ticker     : optional acquirer identifier
    target_ticker       : optional target identifier
    """

    snapshot_date: date
    announcement_date: date
    days_before: int
    deal_id: str = ""
    acquirer_ticker: str = ""
    target_ticker: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "snapshot_date": self.snapshot_date.isoformat(),
            "announcement_date": self.announcement_date.isoformat(),
            "days_before": self.days_before,
            "deal_id": self.deal_id,
            "acquirer_ticker": self.acquirer_ticker,
            "target_ticker": self.target_ticker,
        }


# ---------------------------------------------------------------------------
# compute_snapshot_dates
# ---------------------------------------------------------------------------

def compute_snapshot_dates(
    announcement_date: date,
    lookback_days: Sequence[int] = DEFAULT_LOOKBACK_DAYS,
    *,
    deal_id: str = "",
    acquirer_ticker: str = "",
    target_ticker: str = "",
    min_date: date | None = None,
) -> list[SnapshotDate]:
    """
    Return one SnapshotDate per lookback window.

    Snapshot dates before `min_date` (e.g. 2010-01-01) are omitted
    because data may not be available before that point.

    Parameters
    ----------
    announcement_date : deal announcement date
    lookback_days     : windows to compute (default: 365, 180, 90, 30)
    deal_id           : optional deal identifier propagated to each snapshot
    acquirer_ticker   : optional acquirer identifier
    target_ticker     : optional target identifier
    min_date          : earliest allowed snapshot_date (omitted if before this)

    Returns
    -------
    List of SnapshotDate, sorted ascending by days_before.
    """
    results: list[SnapshotDate] = []
    for days in sorted(lookback_days, reverse=True):
        snap = announcement_date - timedelta(days=days)
        if min_date is not None and snap < min_date:
            continue
        results.append(
            SnapshotDate(
                snapshot_date=snap,
                announcement_date=announcement_date,
                days_before=days,
                deal_id=deal_id,
                acquirer_ticker=acquirer_ticker,
                target_ticker=target_ticker,
            )
        )
    return results


# ---------------------------------------------------------------------------
# compute_all_snapshot_dates
# ---------------------------------------------------------------------------

def compute_all_snapshot_dates(
    deals: list[dict[str, object]],
    lookback_days: Sequence[int] = DEFAULT_LOOKBACK_DAYS,
    min_date: date | None = None,
) -> list[SnapshotDate]:
    """
    Given a list of deal dicts (each with 'announced_date', optionally
    'deal_id', 'acquirer_ticker', 'target_ticker'), return all snapshots.

    The 'announced_date' field must be an ISO-format string or a date object.
    """
    all_snapshots: list[SnapshotDate] = []
    for deal in deals:
        raw = deal.get("announced_date") or deal.get("announcement_date")
        if raw is None:
            continue
        if isinstance(raw, str):
            ann_date = date.fromisoformat(raw)
        elif isinstance(raw, date):
            ann_date = raw
        else:
            continue
        snaps = compute_snapshot_dates(
            ann_date,
            lookback_days=lookback_days,
            deal_id=str(deal.get("deal_id", "")),
            acquirer_ticker=str(deal.get("acquirer_ticker", "")),
            target_ticker=str(deal.get("target_ticker", "")),
            min_date=min_date,
        )
        all_snapshots.extend(snaps)
    return all_snapshots
