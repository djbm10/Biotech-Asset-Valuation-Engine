"""
Market data ingestion via yfinance.
Provides price history, benchmark series, and snapshot fundamentals.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf


def fetch_price_history(
    ticker: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    lookback_days: int = 365 * 3,
) -> pd.DataFrame:
    """
    Return daily OHLCV dataframe for ticker.

    Parameters
    ----------
    ticker: stock symbol
    start, end: ISO date strings. If omitted, uses lookback_days.
    lookback_days: days of history when start is not specified.

    Returns
    -------
    DataFrame with columns: Open, High, Low, Close, Volume, ticker
    Index: DatetimeIndex
    """
    if start is None:
        start = (date.today() - timedelta(days=lookback_days)).isoformat()
    if end is None:
        end = date.today().isoformat()

    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df["ticker"] = ticker
    return df


def fetch_returns(
    ticker: str,
    benchmark: str = "XBI",
    start: Optional[str] = None,
    lookback_days: int = 365 * 3,
) -> pd.DataFrame:
    """
    Return daily log-returns for ticker and benchmark aligned on the same dates.

    Columns: ret_{ticker}, ret_{benchmark}
    """
    if start is None:
        start = (date.today() - timedelta(days=lookback_days)).isoformat()

    tickers = list({ticker, benchmark})
    raw = yf.download(tickers, start=start, progress=False, auto_adjust=True)["Close"]

    if isinstance(raw, pd.Series):
        raw = raw.to_frame(name=tickers[0])

    rets = raw.pct_change().dropna()
    rets.columns = [f"ret_{c}" for c in rets.columns]
    return rets


def get_fundamentals(ticker: str) -> dict:
    """
    Pull snapshot fundamental data from yfinance info dict.

    Returns a cleaned subset relevant to biotech valuation.
    """
    t = yf.Ticker(ticker)
    info = t.info or {}

    return {
        "ticker": ticker,
        "name": info.get("longName") or info.get("shortName"),
        "market_cap_millions": round(info.get("marketCap", 0) / 1e6, 1),
        "cash_millions": round((info.get("totalCash") or 0) / 1e6, 1),
        "total_debt_millions": round((info.get("totalDebt") or 0) / 1e6, 1),
        "shares_outstanding_millions": round((info.get("sharesOutstanding") or 0) / 1e6, 2),
        "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "52w_high": info.get("fiftyTwoWeekHigh"),
        "52w_low": info.get("fiftyTwoWeekLow"),
        "beta": info.get("beta"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
    }


def fetch_benchmark(
    benchmark: str = "XBI",
    start: Optional[str] = None,
    lookback_days: int = 365 * 3,
) -> pd.DataFrame:
    """Return price history for a benchmark ETF (default: SPDR S&P Biotech ETF)."""
    return fetch_price_history(benchmark, start=start, lookback_days=lookback_days)
