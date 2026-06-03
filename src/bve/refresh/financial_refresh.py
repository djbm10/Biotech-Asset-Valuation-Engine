"""Financial data refresh — cash, debt, net_cash, shares, quarterly_burn, runway, filing_date.

Wraps the existing yfinance/SEC EDGAR ingestion layer and adds:
- Structured ``FinancialSnapshot`` with source, as_of, and confidence.
- Staleness evaluation based on age relative to configurable thresholds.
- Injectable ``fetcher`` parameter so every public function is unit-testable
  without network access.

Confidence levels
-----------------
``"high"``          — data from a recent quarter filing (age ≤ 90 days)
``"medium"``        — data 91–180 days old (one quarter stale)
``"low"``           — data 181–365 days old
``"stale"``         — data older than 365 days but available
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
# Staleness thresholds (days)
# ---------------------------------------------------------------------------

_FRESH_DAYS: int = 90      # ≤90 days → high (within one quarter)
_RECENT_DAYS: int = 180    # ≤180 days → medium
_ACCEPTABLE_DAYS: int = 365  # ≤365 days → low
# > 365 days → stale


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
class FinancialSnapshot:
    """Structured financial snapshot for one ticker.

    All numeric fields are ``None`` when unavailable. ``confidence`` reflects
    the freshness and reliability of the data; callers should lower downstream
    confidence when this is ``"low"`` or ``"stale"``.

    Parameters
    ----------
    ticker:
        Stock ticker.
    cash_millions:
        Cash and cash equivalents + marketable securities (millions).
    total_debt_millions:
        Total long-term and short-term debt (millions).
    net_cash_millions:
        cash_millions − total_debt_millions (millions). Derived when absent.
    shares_outstanding_millions:
        Shares outstanding (millions).
    quarterly_burn_millions:
        R&D + SG&A operating cash burn per quarter (millions). Positive = spending.
        Derived from annual R&D + operating costs when quarterly data is unavailable.
    runway_quarters:
        Net cash / quarterly_burn. None if either component is missing.
    filing_date:
        Date of the most recent quarterly or annual filing used.
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
    cash_millions: Optional[float] = None
    total_debt_millions: Optional[float] = None
    net_cash_millions: Optional[float] = None
    shares_outstanding_millions: Optional[float] = None
    quarterly_burn_millions: Optional[float] = None
    runway_quarters: Optional[float] = None
    filing_date: Optional[date] = None
    as_of: Optional[date] = None
    source: str = "not_available"
    confidence: str = "not_available"
    staleness_warning: Optional[str] = None
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialisable dict for reports."""
        return {
            "ticker": self.ticker,
            "cash_millions": self.cash_millions,
            "total_debt_millions": self.total_debt_millions,
            "net_cash_millions": self.net_cash_millions,
            "shares_outstanding_millions": self.shares_outstanding_millions,
            "quarterly_burn_millions": self.quarterly_burn_millions,
            "runway_quarters": self.runway_quarters,
            "filing_date": self.filing_date.isoformat() if self.filing_date else None,
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

def fetch_financial_snapshot(
    ticker: str,
    *,
    fetcher: Optional[Callable[[str], dict]] = None,
    yaml_override: Optional[dict] = None,
    reference_date: Optional[date] = None,
) -> FinancialSnapshot:
    """Fetch a fresh financial snapshot for ``ticker``.

    Parameters
    ----------
    ticker:
        Stock ticker (e.g. ``"SRPT"``).
    fetcher:
        Callable ``(ticker) → dict`` providing raw financial data. Defaults to
        the yfinance-backed ``_yfinance_fetcher``. Inject a fake for tests.
    yaml_override:
        Dict of YAML-config values (fallback when live fetch fails or
        for fields not available from yfinance).
    reference_date:
        Date for staleness evaluation; defaults to today.

    Returns
    -------
    FinancialSnapshot
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
    cash = _coerce_float(raw.get("cash_millions")) or _coerce_float(override.get("cash_millions"))
    debt = _coerce_float(raw.get("total_debt_millions")) or _coerce_float(
        override.get("total_debt_millions")
    )
    shares = _coerce_float(raw.get("shares_outstanding_millions")) or _coerce_float(
        override.get("shares_outstanding_millions")
    )

    # Derive net_cash
    net_cash = _coerce_float(override.get("net_cash_millions"))
    if net_cash is None and cash is not None and debt is not None:
        net_cash = round(cash - debt, 2)
    elif net_cash is None and cash is not None:
        net_cash = cash  # No debt information — treat as net_cash

    # Quarterly burn — from YAML or derived from annual figures
    q_burn = _coerce_float(override.get("quarterly_burn_millions"))
    if q_burn is None:
        annual_rd = _coerce_float(raw.get("research_development")) or _coerce_float(
            override.get("annual_rd_millions")
        )
        annual_ops = _coerce_float(raw.get("total_operating_expenses")) or _coerce_float(
            override.get("annual_operating_expenses_millions")
        )
        if annual_rd is not None:
            q_burn = round(annual_rd / 4.0, 2)
        elif annual_ops is not None:
            q_burn = round(annual_ops / 4.0, 2)

    # Runway
    runway: Optional[float] = None
    if net_cash is not None and q_burn is not None and q_burn > 0:
        runway = round(net_cash / q_burn, 1)

    # Filing date
    filing_date: Optional[date] = None
    filing_date_raw = override.get("filing_date") or override.get("balance_sheet_date")
    if filing_date_raw:
        filing_date = _parse_date(filing_date_raw)

    # Determine source + confidence
    if fetch_error or not raw:
        if override and (cash is not None or net_cash is not None):
            source = "yaml_manual"
            yaml_as_of_str = override.get("balance_sheet_as_of") or override.get("as_of")
            as_of = _parse_date(yaml_as_of_str) or ref
            age = (ref - as_of).days
            if age > _ACCEPTABLE_DAYS:
                confidence = "stale"
                stale_warn: Optional[str] = f"YAML financials are {age} days old (>{_ACCEPTABLE_DAYS}d threshold)"
            elif age > _RECENT_DAYS:
                confidence = "low"
                stale_warn = f"YAML financials are {age} days old (>{_RECENT_DAYS}d threshold)"
            elif age > _FRESH_DAYS:
                confidence = "medium"
                stale_warn = f"YAML financials are {age} days old (>{_FRESH_DAYS}d threshold)"
            else:
                confidence = "medium"  # YAML is always medium max
                stale_warn = None
        else:
            source = "not_available"
            confidence = "not_available"
            as_of = ref
            stale_warn = fetch_error or "No financial data available"
    else:
        source = "yfinance"
        as_of = ref
        age = 0
        confidence = _confidence_from_age(age)
        stale_warn = None

    return FinancialSnapshot(
        ticker=ticker.upper(),
        cash_millions=cash,
        total_debt_millions=debt,
        net_cash_millions=net_cash,
        shares_outstanding_millions=shares,
        quarterly_burn_millions=q_burn,
        runway_quarters=runway,
        filing_date=filing_date,
        as_of=as_of,
        source=source,
        confidence=confidence,
        staleness_warning=stale_warn,
        raw=raw,
    )


def render_financial_snapshot(snap: FinancialSnapshot) -> str:
    """Render a FinancialSnapshot as a compact Markdown table."""
    na = "Not available"

    def _f(v: Any, fmt: str = ".1f") -> str:
        return na if v is None else format(float(v), fmt)

    lines = [
        "### Financial Snapshot",
        "",
        f"**Ticker:** {snap.ticker}  |  **As of:** {snap.as_of or na}  |  "
        f"**Source:** {snap.source}  |  **Confidence:** {snap.confidence}",
    ]
    if snap.staleness_warning:
        lines.append(f"\n> ⚠ {snap.staleness_warning}")
    if snap.filing_date:
        lines.append(f"\n**Filing date:** {snap.filing_date.isoformat()}")
    lines += [
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Cash ($M) | {_f(snap.cash_millions)} |",
        f"| Total debt ($M) | {_f(snap.total_debt_millions)} |",
        f"| Net cash ($M) | {_f(snap.net_cash_millions)} |",
        f"| Shares outstanding (M) | {_f(snap.shares_outstanding_millions)} |",
        f"| Quarterly burn ($M) | {_f(snap.quarterly_burn_millions)} |",
        f"| Runway (quarters) | {_f(snap.runway_quarters)} |",
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
