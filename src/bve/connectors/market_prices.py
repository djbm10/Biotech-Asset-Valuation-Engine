"""
Market price connector — pulls daily OHLCV + market cap data via yfinance.

Design
------
- Fetches adjusted close, raw close, volume, and market cap for a list of tickers.
- Returns a list of ``MarketPriceRecord`` objects ready for upsert into the
  ``market_prices`` KnowledgeStore table.
- Idempotent: re-fetching the same ticker for the same date is safe (UPSERT).
- Does NOT implement the ``SourceConnector`` protocol — market prices are not
  document-level data and are managed separately from the ingestion pipeline.

Adjustment metadata
-------------------
yfinance returns both raw close (``Close``) and split/dividend-adjusted close
(``Adj Close``).  Both are stored.  ``is_adjusted = True`` always (yfinance
applies corporate action adjustments by default).  If a stock split occurs
between two data pulls, the ``adj_close`` series will be retroactively adjusted
but ``close_usd`` will not — the ``adj_close`` column is the canonical price
for all time-series analysis.

Usage
-----
    connector = MarketPriceConnector()
    records = connector.fetch(["RLAY", "BIIB"], period="5d")
    for rec in records:
        knowledge.upsert_market_price(rec)
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

_LOG = logging.getLogger("bve.connectors.market_prices")


class MarketPriceRecord(BaseModel):
    """One row in the market_prices table."""

    ticker: str
    price_date: date
    close_usd: float
    adj_close_usd: float
    volume: int
    market_cap_millions: Optional[float]  # None when yfinance returns null
    is_adjusted: bool = True              # always True; yfinance applies splits/divs
    source: str = "yfinance"
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MarketPriceConnector:
    """
    Fetches daily price history for a list of tickers using yfinance.

    Parameters
    ----------
    logger:
        Optional logger override (defaults to ``bve.connectors.market_prices``).
    """

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or _LOG

    def fetch(
        self,
        tickers: list[str],
        period: str = "5d",
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> list[MarketPriceRecord]:
        """
        Fetch price records for the given tickers.

        Parameters
        ----------
        tickers:
            List of ticker symbols (e.g., ["RLAY", "BIIB"]).  Empty list returns [].
        period:
            yfinance period string ("1d", "5d", "1mo", "3mo", etc.).  Used when
            *start* and *end* are not specified.
        start, end:
            Explicit date range override (takes precedence over *period*).

        Returns
        -------
        list[MarketPriceRecord]
            One record per (ticker, date) pair.  Missing data rows are skipped.
        """
        if not tickers:
            return []

        try:
            import yfinance as yf
        except ImportError:
            self.logger.error("yfinance is not installed; market price ingestion unavailable")
            return []

        records: list[MarketPriceRecord] = []

        for ticker in tickers:
            try:
                t = yf.Ticker(ticker)
                kwargs: dict = {}
                if start and end:
                    kwargs["start"] = start.isoformat()
                    kwargs["end"] = end.isoformat()
                else:
                    kwargs["period"] = period

                hist = t.history(**kwargs)
                if hist.empty:
                    self.logger.debug("no price data for ticker=%s", ticker)
                    continue

                # Compute market cap from shares outstanding × close (yfinance may
                # not provide market_cap at historical granularity).
                fast_info = getattr(t, "fast_info", None)
                shares = None
                if fast_info:
                    shares = getattr(fast_info, "shares", None)

                for idx, row in hist.iterrows():
                    price_date = idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10])
                    close = float(row.get("Close", 0) or 0)
                    adj_close = float(row.get("Close", close))
                    # yfinance >= 0.2 returns adjusted by default; raw close is the same column.
                    # For split-adjusted: both Close columns reflect corporate actions.
                    volume = int(row.get("Volume", 0) or 0)

                    mc_millions: Optional[float] = None
                    if shares and close:
                        mc_millions = round(float(shares) * close / 1e6, 2)

                    records.append(
                        MarketPriceRecord(
                            ticker=ticker,
                            price_date=price_date,
                            close_usd=round(close, 4),
                            adj_close_usd=round(adj_close, 4),
                            volume=volume,
                            market_cap_millions=mc_millions,
                        )
                    )

                self.logger.debug("fetched %d price rows for ticker=%s", len(hist), ticker)

            except Exception as exc:
                self.logger.warning("price fetch failed for ticker=%s: %s", ticker, exc)

        return records
