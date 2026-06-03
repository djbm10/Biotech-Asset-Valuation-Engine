"""Market data refresh — price, shares, market cap, EV, volume, as_of, source.

Wraps the existing yfinance-based ingestion layer and adds:
- Structured ``MarketDataSnapshot`` with source, as_of, and confidence.
- Staleness evaluation based on age relative to configurable thresholds.
- Injectable ``fetcher`` parameter so every public function is unit-testable
  without network access.

Confidence levels
-----------------
``"high"``          — fresh data (age ≤ 1 business day)
``"medium"``        — data up to 5 calendar days old (e.g. weekend delay)
``"low"``           — data 6–30 days old
``"stale"``         — data older than 30 days but available
``"not_available"`` — fetch failed or returned no data

YAML fallback
-------------
A ``yaml_override`` dict (from YAML config) can supply any field. YAML values
are always used if the live fetch fails. Fields supplied by YAML carry
``source="yaml_manual"`` and ``confidence="medium"`` unless the field also
has an ``as_of`` entry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Optional


# ---------------------------------------------------------------------------
# Staleness thresholds
# ---------------------------------------------------------------------------

_FRESH_DAYS: int = 1        # ≤1 day → high
_RECENT_DAYS: int = 5       # ≤5 days → medium
_ACCEPTABLE_DAYS: int = 30  # ≤30 days → low
# > 30 days → stale


def _confidence_from_age(age_days: int) -> str:
    if age_days <= _FRESH_DAYS:
        return "high"
    if age_days <= _RECENT_DAYS:
        return "medium"
    if age_days <= _ACCEPTABLE_DAYS:
        return "low"
    return "stale"


# ---------------------------------------------------------------------------
# Snapshot container
# ---------------------------------------------------------------------------

@dataclass
class MarketDataSnapshot:
    """Structured market data snapshot for one ticker.

    All numeric fields are ``None`` when unavailable. ``confidence`` reflects
    the freshness and reliability of the data; callers should lower downstream
    confidence when this is ``"low"`` or ``"stale"``.

    Parameters
    ----------
    ticker:
        Stock ticker.
    price:
        Last closing price.
    shares_outstanding_millions:
        Shares outstanding (millions).
    market_cap_millions:
        Market capitalisation (millions). Derived from price × shares if not
        provided directly.
    enterprise_value_millions:
        Enterprise value = market_cap − net_cash (millions). Requires
        net_cash_millions to compute; ``None`` when unavailable.
    volume_avg_30d:
        30-day average daily volume (shares). Proxy for liquidity.
    as_of:
        Date the data was fetched/verified.
    source:
        ``"yfinance"`` | ``"yaml_manual"`` | ``"not_available"``
    confidence:
        ``"high"`` | ``"medium"`` | ``"low"`` | ``"stale"`` | ``"not_available"``
    staleness_warning:
        Non-None when confidence is ``"low"`` or ``"stale"``.
    raw:
        Raw dict from the underlying fetcher for auditability.
    """

    ticker: str
    price: Optional[float] = None
    shares_outstanding_millions: Optional[float] = None
    market_cap_millions: Optional[float] = None
    enterprise_value_millions: Optional[float] = None
    volume_avg_30d: Optional[float] = None
    as_of: Optional[date] = None
    source: str = "not_available"
    confidence: str = "not_available"
    staleness_warning: Optional[str] = None
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialisable dict for reports."""
        return {
            "ticker": self.ticker,
            "price": self.price,
            "shares_outstanding_millions": self.shares_outstanding_millions,
            "market_cap_millions": self.market_cap_millions,
            "enterprise_value_millions": self.enterprise_value_millions,
            "volume_avg_30d": self.volume_avg_30d,
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "source": self.source,
            "confidence": self.confidence,
            "staleness_warning": self.staleness_warning,
        }


# ---------------------------------------------------------------------------
# Default fetcher (yfinance)
# ---------------------------------------------------------------------------

def _yfinance_fetcher(ticker: str) -> dict:
    """Default live fetcher using yfinance."""
    from bve.ingestion.market_data import get_fundamentals
    return get_fundamentals(ticker)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_market_snapshot(
    ticker: str,
    *,
    fetcher: Optional[Callable[[str], dict]] = None,
    yaml_override: Optional[dict] = None,
    reference_date: Optional[date] = None,
) -> MarketDataSnapshot:
    """Fetch a fresh market data snapshot for ``ticker``.

    Parameters
    ----------
    ticker:
        Stock ticker (e.g. ``"SRPT"``).
    fetcher:
        Callable ``(ticker) → dict`` providing raw market data. Defaults to
        the yfinance-backed ``_yfinance_fetcher``. Inject a fake for tests.
    yaml_override:
        Dict of YAML-config values (fallback when live fetch fails or
        for fields not available from yfinance).
    reference_date:
        Date for staleness evaluation; defaults to today.

    Returns
    -------
    MarketDataSnapshot
    """
    ref = reference_date or date.today()
    fn = fetcher or _yfinance_fetcher
    raw: dict = {}
    fetch_error: Optional[str] = None

    try:
        raw = fn(ticker) or {}
    except Exception as exc:
        fetch_error = str(exc)

    override = yaml_override or {}

    # Extract fields with YAML fallback
    price = _coerce_float(raw.get("current_price")) or _coerce_float(override.get("current_price"))
    shares = _coerce_float(raw.get("shares_outstanding_millions")) or _coerce_float(
        override.get("shares_outstanding_millions")
    )
    market_cap = _coerce_float(raw.get("market_cap_millions")) or _coerce_float(
        override.get("market_cap_millions")
    )
    # Derive market_cap if missing
    if market_cap is None and price is not None and shares is not None:
        market_cap = round(price * shares, 2)

    volume = _coerce_float(raw.get("avg_volume")) or _coerce_float(
        override.get("volume_avg_30d")
    )

    # EV requires net_cash (not in this snapshot; caller can compute)
    net_cash = _coerce_float(override.get("net_cash_millions"))
    ev: Optional[float] = None
    if market_cap is not None and net_cash is not None:
        ev = round(market_cap - net_cash, 2)

    # Determine source + confidence
    if fetch_error or not raw:
        if override and price is not None:
            source = "yaml_manual"
            confidence = "medium"
            stale_warn: Optional[str] = None
            yaml_as_of_str = override.get("price_as_of") or override.get("as_of")
            as_of = _parse_date(yaml_as_of_str) or ref
            age = (ref - as_of).days
            if age > _ACCEPTABLE_DAYS:
                confidence = "stale"
                stale_warn = f"YAML price is {age} days old (>{_ACCEPTABLE_DAYS}d threshold)"
            elif age > _RECENT_DAYS:
                confidence = "low"
                stale_warn = f"YAML price is {age} days old (>{_RECENT_DAYS}d threshold)"
        else:
            source = "not_available"
            confidence = "not_available"
            as_of = ref
            stale_warn = fetch_error or "No market data available"
    else:
        source = "yfinance"
        as_of = ref
        age = 0  # just fetched → same day
        confidence = _confidence_from_age(age)
        stale_warn = None

    return MarketDataSnapshot(
        ticker=ticker.upper(),
        price=price,
        shares_outstanding_millions=shares,
        market_cap_millions=market_cap,
        enterprise_value_millions=ev,
        volume_avg_30d=volume,
        as_of=as_of,
        source=source,
        confidence=confidence,
        staleness_warning=stale_warn,
        raw=raw,
    )


def render_market_snapshot(snap: MarketDataSnapshot) -> str:
    """Render a MarketDataSnapshot as a compact Markdown table."""
    na = "Not available"

    def _f(v: Any, fmt: str = ".2f") -> str:
        return na if v is None else format(float(v), fmt)

    lines = [
        "### Market Data Snapshot",
        "",
        f"**Ticker:** {snap.ticker}  |  **As of:** {snap.as_of or na}  |  "
        f"**Source:** {snap.source}  |  **Confidence:** {snap.confidence}",
    ]
    if snap.staleness_warning:
        lines.append(f"\n> ⚠ {snap.staleness_warning}")
    lines += [
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Price ($) | {_f(snap.price)} |",
        f"| Shares outstanding (M) | {_f(snap.shares_outstanding_millions)} |",
        f"| Market cap ($M) | {_f(snap.market_cap_millions, '.0f')} |",
        f"| Enterprise value ($M) | {_f(snap.enterprise_value_millions, '.0f')} |",
        f"| 30d avg volume | {_f(snap.volume_avg_30d, '.0f')} |",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _coerce_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f != 0.0 else None
    except (TypeError, ValueError):
        return None


def _parse_date(v: Any) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v).split("T")[0])
    except (ValueError, AttributeError):
        return None
