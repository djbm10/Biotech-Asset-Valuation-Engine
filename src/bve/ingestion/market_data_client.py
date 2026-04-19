"""
Market data ingestion client.

Fetches price, EV, share count, and cash data for biotech names.
Returns typed RawEvent records instead of raw DataFrames.

Wraps yfinance for price data and supplements with SEC EDGAR for balance-sheet items.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import yfinance as yf

from bve.ingestion.raw_event import RawEvent

_YF_BASE_URL = "https://finance.yahoo.com/quote"


def _yf_url(ticker: str) -> str:
    return f"{_YF_BASE_URL}/{ticker}"


def fetch_price_snapshot(
    ticker: str,
    entity_ids: list[str] | None = None,
) -> list[RawEvent]:
    """
    Fetch current market price snapshot (last close + key stats).

    Returns one RawEvent with record_type="price_snapshot".
    """
    t = yf.Ticker(ticker)
    info = t.fast_info
    try:
        last_price = float(info.last_price)
    except Exception:
        last_price = None
    try:
        market_cap = float(info.market_cap)
    except Exception:
        market_cap = None
    try:
        shares = float(info.shares)
    except Exception:
        shares = None

    payload: dict[str, Any] = {
        "ticker": ticker,
        "as_of_date": date.today().isoformat(),
        "last_price": last_price,
        "market_cap_usd": market_cap,
        "shares_outstanding": shares,
        "currency": getattr(info, "currency", "USD"),
    }
    return [
        RawEvent(
            source="market_data",
            record_type="price_snapshot",
            source_url=_yf_url(ticker),
            fetched_at=datetime.now(timezone.utc),
            payload=payload,
            entity_ids=entity_ids or [],
        )
    ]


def fetch_price_history(
    ticker: str,
    start: str | None = None,
    end: str | None = None,
    lookback_days: int = 365,
    entity_ids: list[str] | None = None,
) -> list[RawEvent]:
    """
    Fetch daily OHLCV price history.

    Returns one RawEvent with record_type="price_history" containing a list
    of daily bars (not a DataFrame, to stay schema-safe).
    """
    if start is None:
        start = (date.today() - timedelta(days=lookback_days)).isoformat()
    if end is None:
        end = date.today().isoformat()

    import pandas as pd

    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if df.empty:
        return []
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.reset_index()

    bars = []
    for _, row in df.iterrows():
        dt = row.get("Date") or row.get("Datetime")
        bars.append(
            {
                "date": str(dt)[:10] if dt is not None else "",
                "open": float(row["Open"]) if pd.notna(row.get("Open")) else None,
                "high": float(row["High"]) if pd.notna(row.get("High")) else None,
                "low": float(row["Low"]) if pd.notna(row.get("Low")) else None,
                "close": float(row["Close"]) if pd.notna(row.get("Close")) else None,
                "volume": int(row["Volume"]) if pd.notna(row.get("Volume")) else None,
            }
        )

    payload: dict[str, Any] = {
        "ticker": ticker,
        "start": start,
        "end": end,
        "bars": bars,
        "n_bars": len(bars),
    }
    return [
        RawEvent(
            source="market_data",
            record_type="price_history",
            source_url=_yf_url(ticker),
            fetched_at=datetime.now(timezone.utc),
            payload=payload,
            entity_ids=entity_ids or [],
        )
    ]


def fetch_fundamentals(
    ticker: str,
    entity_ids: list[str] | None = None,
) -> list[RawEvent]:
    """
    Fetch fundamental data: cash, debt, shares, EV.

    Returns one RawEvent with record_type="fundamentals_snapshot".
    """
    t = yf.Ticker(ticker)
    info = t.info  # full info dict

    def _safe(key: str) -> Any:
        val = info.get(key)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return val

    payload: dict[str, Any] = {
        "ticker": ticker,
        "as_of_date": date.today().isoformat(),
        "enterprise_value_usd": _safe("enterpriseValue"),
        "market_cap_usd": _safe("marketCap"),
        "total_cash_usd": _safe("totalCash"),
        "total_debt_usd": _safe("totalDebt"),
        "shares_outstanding": _safe("sharesOutstanding"),
        "float_shares": _safe("floatShares"),
        "book_value_per_share": _safe("bookValue"),
        "price_to_book": _safe("priceToBook"),
        "beta": _safe("beta"),
        "52w_high": _safe("fiftyTwoWeekHigh"),
        "52w_low": _safe("fiftyTwoWeekLow"),
        "avg_volume_10d": _safe("averageVolume10days"),
        "revenue_ttm": _safe("totalRevenue"),
        "gross_profit_ttm": _safe("grossProfits"),
        "operating_cash_flow": _safe("operatingCashflow"),
        "free_cash_flow": _safe("freeCashflow"),
        "currency": info.get("currency", "USD"),
        "sector": info.get("sector", ""),
        "industry": info.get("industry", ""),
        "short_name": info.get("shortName", ""),
    }
    return [
        RawEvent(
            source="market_data",
            record_type="fundamentals_snapshot",
            source_url=_yf_url(ticker),
            fetched_at=datetime.now(timezone.utc),
            payload=payload,
            entity_ids=entity_ids or [],
        )
    ]


def fetch_ev_snapshot(
    ticker: str,
    entity_ids: list[str] | None = None,
) -> list[RawEvent]:
    """
    Compute enterprise value = market_cap + debt - cash.

    Returns one RawEvent with record_type="ev_snapshot".
    """
    events = fetch_fundamentals(ticker, entity_ids=entity_ids)
    if not events:
        return []
    f = events[0].payload
    market_cap = f.get("market_cap_usd")
    cash = f.get("total_cash_usd") or 0.0
    debt = f.get("total_debt_usd") or 0.0
    ev_computed = (market_cap + debt - cash) if market_cap is not None else None
    ev_reported = f.get("enterprise_value_usd")

    payload: dict[str, Any] = {
        "ticker": ticker,
        "as_of_date": f.get("as_of_date", date.today().isoformat()),
        "market_cap_usd": market_cap,
        "total_cash_usd": cash,
        "total_debt_usd": debt,
        "ev_computed_usd": ev_computed,
        "ev_reported_usd": ev_reported,
        "net_cash_usd": cash - debt,
        "shares_outstanding": f.get("shares_outstanding"),
    }
    return [
        RawEvent(
            source="market_data",
            record_type="ev_snapshot",
            source_url=_yf_url(ticker),
            fetched_at=datetime.now(timezone.utc),
            payload=payload,
            entity_ids=entity_ids or [],
        )
    ]
