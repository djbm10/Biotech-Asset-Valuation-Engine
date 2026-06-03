"""
historical_market_data_client — point-in-time market data via yfinance.

Returns market cap, enterprise value, price, and basic fundamentals as of
snapshot_date using historical adjusted prices.

LIMITATIONS:
  - Survivorship bias: delisted tickers are not available.
  - Private companies (e.g. Semma Therapeutics): not available; returns None.
  - Split-adjusted prices: used for price history; market cap computed from
    price × shares outstanding (from most recent filing, may not be exact).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional


EXTRACTION_METHOD = "market_data_api"
SOURCE_URL_TEMPLATE = "https://finance.yahoo.com/quote/{ticker}/history"


def _make_provenance(
    ticker: str,
    data_date: str,
    confidence: float = 0.85,
) -> dict[str, Any]:
    return {
        "source_url": SOURCE_URL_TEMPLATE.format(ticker=ticker),
        "source_published_date": data_date,
        "data_as_of_date": data_date,
        "extraction_method": EXTRACTION_METHOD,
        "confidence": confidence,
    }


class HistoricalMarketDataClient:
    """
    Point-in-time market data for public companies.

    All methods return None for private companies or when data is unavailable.
    """

    def get_price_on_date(
        self,
        ticker: str,
        target_date: date,
    ) -> Optional[float]:
        """
        Return the adjusted closing price on or immediately before target_date.
        Returns None if unavailable (private, delisted, no data).
        """
        try:
            import yfinance as yf
        except ImportError:
            return None
        try:
            start = target_date - timedelta(days=5)
            end = target_date + timedelta(days=1)
            hist = yf.download(ticker, start=start.isoformat(), end=end.isoformat(),
                                auto_adjust=True, progress=False)
            if hist.empty:
                return None
            # Filter to rows on or before target_date
            hist = hist[hist.index.date <= target_date]  # type: ignore[attr-defined]
            if hist.empty:
                return None
            close = hist["Close"].iloc[-1]
            if hasattr(close, "item"):
                return float(close.item())
            return float(close)
        except Exception:
            return None

    def get_market_cap(
        self,
        ticker: str,
        snapshot_date: date,
    ) -> dict[str, Any]:
        """
        Return approximate market cap as of snapshot_date.

        Uses: adjusted closing price × shares_outstanding from most
        recent filing (from yfinance fast_info).

        Returns dict with market_cap_millions + provenance fields.
        Returns None for market_cap_millions if unavailable.
        """
        price = self.get_price_on_date(ticker, snapshot_date)
        shares: Optional[float] = None
        if price is not None:
            try:
                import yfinance as yf
                info = yf.Ticker(ticker).fast_info
                shares = getattr(info, "shares", None)
                if shares is None:
                    shares = getattr(info, "shares_outstanding", None)
            except Exception:
                shares = None

        market_cap: Optional[float] = None
        if price is not None and shares is not None and shares > 0:
            market_cap = round((price * shares) / 1_000_000, 2)

        data_date = snapshot_date.isoformat()
        prov = _make_provenance(ticker, data_date)
        return {
            "ticker": ticker,
            "snapshot_date": snapshot_date.isoformat(),
            "price_usd": price,
            "shares_outstanding": shares,
            "market_cap_millions": market_cap,
            **prov,
        }

    def get_enterprise_value(
        self,
        ticker: str,
        snapshot_date: date,
        cash_millions: Optional[float] = None,
        debt_millions: Optional[float] = None,
    ) -> dict[str, Any]:
        """
        Return approximate enterprise value = market_cap + debt - cash.

        If cash/debt not supplied, attempts to read from yfinance info.
        """
        mc_data = self.get_market_cap(ticker, snapshot_date)
        market_cap = mc_data.get("market_cap_millions")

        if cash_millions is None or debt_millions is None:
            try:
                import yfinance as yf
                info = yf.Ticker(ticker).info
                if cash_millions is None:
                    cash_raw = info.get("totalCash") or info.get("cash") or 0
                    cash_millions = round(cash_raw / 1_000_000, 2)
                if debt_millions is None:
                    debt_raw = info.get("totalDebt") or 0
                    debt_millions = round(debt_raw / 1_000_000, 2)
            except Exception:
                cash_millions = cash_millions or 0.0
                debt_millions = debt_millions or 0.0

        ev: Optional[float] = None
        if market_cap is not None:
            ev = round(market_cap + (debt_millions or 0.0) - (cash_millions or 0.0), 2)

        return {
            "ticker": ticker,
            "snapshot_date": snapshot_date.isoformat(),
            "market_cap_millions": market_cap,
            "cash_millions": cash_millions,
            "debt_millions": debt_millions,
            "enterprise_value_millions": ev,
            **mc_data,  # carries provenance
        }

    def is_publicly_traded(self, ticker: str, snapshot_date: date) -> bool:
        """Return True if the company appears to have been public at snapshot_date."""
        price = self.get_price_on_date(ticker, snapshot_date)
        return price is not None
