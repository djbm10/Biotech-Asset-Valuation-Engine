"""Survivorship-safe price loader for strict backtests.

Guarantees that no ticker is silently excluded from the backtest universe
due to missing yfinance data.  Every ticker receives a documented
:class:`TickerPriceStatus` entry.

Key invariant (``survivorship_bias_guard_satisfied``):

* Every ticker in the universe that has been acquired / delisted must either
  have price rows seeded (via deal-universe fallback) **or** carry an
  explicit ``reason_if_excluded`` that records *why* it has no coverage.
* No ticker is silently removed — a missing-price report must be produced
  and stored in :class:`~bve.ops.strict_backtest.StrictBacktestReport`.

Separation of concerns
----------------------
This module handles *reporting* and *coverage detection* only.  Actual
price seeding still happens via :meth:`HistoricalReplay.seed_prices` and
:meth:`ReplayStore.seed_acquisition_price`.  The price-fetching callbacks
in ``strict_backtest.py`` are unchanged — the acquisition-announcement
leakage guard embedded in :meth:`ReplayStore.get_price` already prevents
pre-announcement deal-price leakage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from bve.ops.historical_replay import ReplayStore, load_deal_fallback_prices


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TickerPriceStatus:
    """Price-coverage record for one ticker in the backtest universe."""

    ticker: str
    """Canonical uppercase ticker symbol."""

    status: Literal["active", "acquired", "unknown"]
    """
    * ``active``  — ticker is still trading (no acquisition record).
    * ``acquired`` — ticker appears in ``acquisition_announcements`` or the
      deal-universe YAML (has a consideration price).
    * ``unknown``  — no price data and not recognised as acquired.
    """

    price_coverage_start: Optional[date]
    """Earliest price row date inside the requested backtest window, or None."""

    price_coverage_end: Optional[date]
    """Latest price row date inside the requested backtest window, or None."""

    row_count: int
    """Number of price rows available inside the requested window."""

    missing_days_pct: float
    """Approximate share of calendar days in the window with no price row (0–100)."""

    source: Literal["yfinance", "deal_universe", "both", "none"]
    """
    * ``yfinance``      — real market data (varying prices, no acquisition record).
    * ``deal_universe`` — synthetic flat history seeded from consideration price.
    * ``both``          — both real and synthetic rows present.
    * ``none``          — no rows at all.
    """

    included_in_backtest: bool
    """True when at least one price row is available (ticker contributes returns)."""

    reason_if_excluded: Optional[str]
    """
    Non-None when ``included_in_backtest=False``.  Explains why the ticker
    was excluded so that exclusions are never silent.
    """


@dataclass(frozen=True)
class MissingPriceReport:
    """Full coverage audit for every ticker in the replay universe."""

    generated_at: datetime
    backtest_start: date
    backtest_end: date
    universe_size: int
    tickers: list[TickerPriceStatus] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Derived views
    # ------------------------------------------------------------------

    @property
    def excluded_tickers(self) -> list[TickerPriceStatus]:
        """All tickers that are *not* included in the backtest."""
        return [t for t in self.tickers if not t.included_in_backtest]

    @property
    def acquired_tickers(self) -> list[TickerPriceStatus]:
        """Tickers identified as acquired (regardless of inclusion status)."""
        return [t for t in self.tickers if t.status == "acquired"]

    @property
    def acquired_excluded(self) -> list[TickerPriceStatus]:
        """Acquired tickers that ended up *excluded* — a survivorship-bias risk."""
        return [t for t in self.acquired_tickers if not t.included_in_backtest]

    @property
    def silently_excluded(self) -> list[TickerPriceStatus]:
        """Excluded tickers with no documented reason — should always be empty."""
        return [t for t in self.excluded_tickers if not t.reason_if_excluded]

    @property
    def survivorship_bias_guard_satisfied(self) -> bool:
        """Return True iff:

        1. No ticker is silently excluded (every exclusion has a reason).
        2. No acquired ticker is excluded (they have seeded price data).

        Both conditions must hold for the guard flag to be set True in the
        :class:`~bve.ops.strict_backtest.LeakageAudit`.
        """
        return len(self.silently_excluded) == 0 and len(self.acquired_excluded) == 0

    def to_dict(self) -> dict:
        """Serialise to a JSON-safe dict for inclusion in backtest report."""
        return {
            "generated_at": self.generated_at.isoformat(),
            "backtest_start": self.backtest_start.isoformat(),
            "backtest_end": self.backtest_end.isoformat(),
            "universe_size": self.universe_size,
            "survivorship_bias_guard_satisfied": self.survivorship_bias_guard_satisfied,
            "included_count": sum(1 for t in self.tickers if t.included_in_backtest),
            "excluded_count": len(self.excluded_tickers),
            "acquired_excluded_count": len(self.acquired_excluded),
            "silently_excluded_count": len(self.silently_excluded),
            "tickers": [
                {
                    "ticker": t.ticker,
                    "status": t.status,
                    "price_coverage_start": t.price_coverage_start.isoformat()
                    if t.price_coverage_start
                    else None,
                    "price_coverage_end": t.price_coverage_end.isoformat()
                    if t.price_coverage_end
                    else None,
                    "row_count": t.row_count,
                    "missing_days_pct": round(t.missing_days_pct, 1),
                    "source": t.source,
                    "included_in_backtest": t.included_in_backtest,
                    "reason_if_excluded": t.reason_if_excluded,
                }
                for t in self.tickers
            ],
        }


# ---------------------------------------------------------------------------
# Report generator
# ---------------------------------------------------------------------------


def generate_missing_price_report(
    replay_db_path: str,
    universe_tickers: list[str],
    backtest_start: date,
    backtest_end: date,
    *,
    deal_universe_path: str | Path | None = None,
) -> MissingPriceReport:
    """Produce a :class:`MissingPriceReport` for every ticker in *universe_tickers*.

    Queries the replay store for actual price rows and the
    ``acquisition_announcements`` table (populated by
    :meth:`~bve.ops.historical_replay.ReplayStore.seed_acquisition_price`) to
    classify each ticker as active, acquired, or unknown.

    Parameters
    ----------
    replay_db_path:
        Path to the replay SQLite store (``replay_store.sqlite``).
    universe_tickers:
        Uppercase ticker symbols for every name in the backtest universe.
    backtest_start, backtest_end:
        Date range of the backtest — used to measure coverage within window.
    deal_universe_path:
        Optional override for the deal-universe YAML.  When None, the default
        path (``research/mna/deal_universe_2020_2026.yaml``) is used.

    Returns
    -------
    MissingPriceReport
        Full per-ticker coverage audit.

    Raises
    ------
    RuntimeError
        If any acquired ticker is found with no price data — callers must seed
        prices (via :meth:`HistoricalReplay.seed_prices`) before calling this
        function, or the strict backtest should fail fast.
    """
    store = ReplayStore(replay_db_path)
    deal_fb = load_deal_fallback_prices(deal_universe_path)

    # Build acquired-ticker set from two sources:
    #   1. acquisition_announcements table (set by seed_acquisition_price)
    #   2. deal-universe YAML (tickers that *should* be seeded)
    acquired_from_db: set[str] = {
        str(row["ticker"]).upper()
        for row in store._conn.execute(
            "SELECT ticker FROM acquisition_announcements"
        ).fetchall()
    }
    acquired_from_yaml: set[str] = {t.upper() for t in deal_fb}
    all_acquired: set[str] = acquired_from_db | acquired_from_yaml

    total_window_days = max(1, (backtest_end - backtest_start).days + 1)

    statuses: list[TickerPriceStatus] = []

    for ticker in [t.upper() for t in universe_tickers]:
        # Query price rows within the backtest window
        rows = store._conn.execute(
            """
            SELECT MIN(price_date) AS coverage_start,
                   MAX(price_date) AS coverage_end,
                   COUNT(*)        AS row_count
            FROM historical_prices
            WHERE ticker = ? AND price_date >= ? AND price_date <= ?
            """,
            (ticker, backtest_start.isoformat(), backtest_end.isoformat()),
        ).fetchone()

        row_count = int(rows["row_count"] or 0)
        coverage_start: Optional[date] = None
        coverage_end: Optional[date] = None
        if row_count > 0 and rows["coverage_start"]:
            coverage_start = date.fromisoformat(str(rows["coverage_start"])[:10])
        if row_count > 0 and rows["coverage_end"]:
            coverage_end = date.fromisoformat(str(rows["coverage_end"])[:10])

        missing_days_pct = max(0.0, 100.0 * (1.0 - row_count / total_window_days))

        is_acquired = ticker in all_acquired
        in_db_ann = ticker in acquired_from_db
        in_yaml = ticker in acquired_from_yaml

        # Determine source
        if row_count == 0:
            source: Literal["yfinance", "deal_universe", "both", "none"] = "none"
        elif in_db_ann:
            # All rows came from seed_acquisition_price (flat synthetic)
            source = "deal_universe"
        else:
            source = "yfinance"

        # Determine status
        if is_acquired:
            status: Literal["active", "acquired", "unknown"] = "acquired"
        elif row_count > 0:
            status = "active"
        else:
            status = "unknown"

        # Inclusion and reason
        included_in_backtest = row_count > 0
        reason_if_excluded: Optional[str] = None

        if not included_in_backtest:
            if is_acquired and in_yaml and not in_db_ann:
                reason_if_excluded = (
                    "acquired_ticker_not_seeded: consideration_per_share present in "
                    "deal_universe but seed_acquisition_price() was not called — "
                    "run HistoricalReplay.seed_prices() with deal_universe_path to fix"
                )
            elif is_acquired:
                reason_if_excluded = (
                    "acquired_ticker_no_data: ticker identified as acquired but no "
                    "price rows in replay store and no fallback available"
                )
            else:
                reason_if_excluded = (
                    "no_price_data: yfinance returned no data and ticker is not in "
                    "deal_universe — verify ticker symbol or add to deal_universe YAML"
                )

        statuses.append(
            TickerPriceStatus(
                ticker=ticker,
                status=status,
                price_coverage_start=coverage_start,
                price_coverage_end=coverage_end,
                row_count=row_count,
                missing_days_pct=missing_days_pct,
                source=source,
                included_in_backtest=included_in_backtest,
                reason_if_excluded=reason_if_excluded,
            )
        )

    store.close()

    report = MissingPriceReport(
        generated_at=datetime.now(timezone.utc),
        backtest_start=backtest_start,
        backtest_end=backtest_end,
        universe_size=len(universe_tickers),
        tickers=statuses,
    )

    # Hard fail if any acquired ticker has no seeded data — caller must fix
    unseeded_acquired = [
        t.ticker for t in report.acquired_excluded
        if t.status == "acquired" and t.source == "none"
    ]
    if unseeded_acquired:
        raise RuntimeError(
            f"Survivorship bias detected: {len(unseeded_acquired)} acquired ticker(s) "
            f"have no price data in the replay store — backtest would silently exclude "
            f"known acquired names, biasing results. "
            f"Tickers: {unseeded_acquired}. "
            f"Fix: run seed_prices() with deal_universe_path, or add "
            f"consideration_per_share to deal_universe_2020_2026.yaml."
        )

    return report
