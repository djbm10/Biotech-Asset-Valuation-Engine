"""Security master — tracks listing status, delistings, corporate actions.

Ensures survivorship-bias-safe replay by requiring every ticker in the
universe to have a documented status (active, acquired, delisted, bankrupt).
No ticker may be silently excluded from return calculations.

Design rules
------------
1. Every ticker that disappears from yfinance must have a SecurityMasterEntry
   with ``delisting_reason`` populated.
2. Missing return data is NOT the same as zero return. Use
   ``conservative_delisting_return_pct`` (default -100 for bankruptcy,
   -50 for unknown) or ``acquisition_consideration_pct`` for M&A exits.
3. Sensitivity runs must test 0%, -50%, and -100% scenarios for
   ``missing_return_data`` entries.

Usage
-----
    from bve.validation.security_master import SecurityMaster, SecurityMasterEntry
    sm = SecurityMaster.load_from_yaml("research/data/security_master.yaml")
    entry = sm.get("SRPT")
    if entry and entry.is_delisted:
        return_pct = entry.conservative_delisting_return_pct
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Optional


class DelistingReason(str, Enum):
    ACQUISITION = "acquisition"
    BANKRUPTCY = "bankruptcy"
    REVERSE_MERGER = "reverse_merger"
    VOLUNTARY_DELISTING = "voluntary_delisting"
    REGULATORY = "regulatory"
    UNKNOWN = "unknown"


class SecurityStatus(str, Enum):
    ACTIVE = "active"           # still trading
    ACQUIRED = "acquired"       # acquired/merged; known consideration price
    DELISTED = "delisted"       # delisted for other reason
    BANKRUPT = "bankrupt"       # filed Chapter 7/11; equity likely worthless
    MISSING_DATA = "missing_data"  # no data; must not be silently excluded


@dataclass
class CorporateAction:
    """A single corporate event (split, spin-off, dividend, etc.)."""
    action_date: date
    action_type: str           # "split" | "reverse_split" | "spin_off" | "dividend"
    ratio: Optional[float] = None   # e.g. 2.0 for 2-for-1 split
    note: str = ""


@dataclass
class SecurityMasterEntry:
    """Full lifecycle record for one security."""

    ticker: str
    company_name: str = ""
    cusip: Optional[str] = None
    figi: Optional[str] = None

    # Listing dates
    listing_start: Optional[date] = None
    listing_end: Optional[date] = None

    # Current status
    status: SecurityStatus = SecurityStatus.ACTIVE
    delisting_reason: Optional[DelistingReason] = None

    # M&A exit (acquired)
    merger_date: Optional[date] = None
    acquirer: Optional[str] = None
    acquisition_consideration_pct: Optional[float] = None  # return vs pre-announcement price

    # Bankruptcy
    bankruptcy_date: Optional[date] = None
    bankruptcy_chapter: Optional[str] = None   # "7" | "11"
    estimated_equity_recovery_pct: float = 0.0

    # Return assignment for replay (used when live prices unavailable)
    conservative_delisting_return_pct: float = -100.0  # pessimistic default
    optimistic_delisting_return_pct: Optional[float] = None

    # Corporate actions (splits, reverse splits)
    corporate_actions: list[CorporateAction] = field(default_factory=list)

    # Data quality
    has_live_price_history: bool = True
    missing_return_data: bool = False
    notes: str = ""

    @property
    def is_delisted(self) -> bool:
        return self.status in (
            SecurityStatus.ACQUIRED,
            SecurityStatus.DELISTED,
            SecurityStatus.BANKRUPT,
        )

    @property
    def return_scenarios(self) -> dict[str, float]:
        """Return dict of {scenario_name: return_pct} for sensitivity analysis."""
        if self.status == SecurityStatus.ACQUIRED and self.acquisition_consideration_pct is not None:
            base = self.acquisition_consideration_pct
        elif self.status == SecurityStatus.BANKRUPT:
            base = self.estimated_equity_recovery_pct - 100.0
        else:
            base = self.conservative_delisting_return_pct

        return {
            "pessimistic": -100.0,
            "conservative": min(base, -50.0) if base < 0 else base,
            "base": base,
            "optimistic": self.optimistic_delisting_return_pct if self.optimistic_delisting_return_pct is not None else max(0.0, base),
        }


class SecurityMaster:
    """In-memory registry of all tracked securities."""

    def __init__(self, entries: list[SecurityMasterEntry] | None = None) -> None:
        self._entries: dict[str, SecurityMasterEntry] = {}
        for e in (entries or []):
            self._entries[e.ticker.upper()] = e

    def get(self, ticker: str) -> Optional[SecurityMasterEntry]:
        return self._entries.get(ticker.upper())

    def add(self, entry: SecurityMasterEntry) -> None:
        self._entries[entry.ticker.upper()] = entry

    def all_tickers(self) -> list[str]:
        return sorted(self._entries)

    def delisted(self) -> list[SecurityMasterEntry]:
        return [e for e in self._entries.values() if e.is_delisted]

    def missing_data(self) -> list[SecurityMasterEntry]:
        return [e for e in self._entries.values() if e.missing_return_data]

    def coverage_report(self) -> dict:
        """Return a dict summarising coverage status for audit."""
        total = len(self._entries)
        n_active = sum(1 for e in self._entries.values() if e.status == SecurityStatus.ACTIVE)
        n_acquired = sum(1 for e in self._entries.values() if e.status == SecurityStatus.ACQUIRED)
        n_delisted = sum(1 for e in self._entries.values() if e.status == SecurityStatus.DELISTED)
        n_bankrupt = sum(1 for e in self._entries.values() if e.status == SecurityStatus.BANKRUPT)
        n_missing = sum(1 for e in self._entries.values() if e.missing_return_data)
        return {
            "total": total,
            "active": n_active,
            "acquired": n_acquired,
            "delisted": n_delisted,
            "bankrupt": n_bankrupt,
            "missing_data": n_missing,
            "survivorship_bias_guard_satisfied": n_missing == 0,
            "note": (
                "survivorship_bias_guard_satisfied=True means every ticker "
                "with no live price data has an explicit return assignment."
            ),
        }

    @classmethod
    def load_from_yaml(cls, path: str | Path) -> "SecurityMaster":
        """Load from a YAML file. Returns empty master if file missing."""
        import yaml
        p = Path(path)
        if not p.exists():
            return cls()
        with open(p) as f:
            data = yaml.safe_load(f) or {}
        entries = []
        for ticker, info in data.get("securities", {}).items():
            entry = SecurityMasterEntry(
                ticker=ticker,
                company_name=info.get("company_name", ""),
                status=SecurityStatus(info.get("status", "active")),
                delisting_reason=(
                    DelistingReason(info["delisting_reason"])
                    if info.get("delisting_reason") else None
                ),
                listing_start=(
                    date.fromisoformat(info["listing_start"])
                    if info.get("listing_start") else None
                ),
                listing_end=(
                    date.fromisoformat(info["listing_end"])
                    if info.get("listing_end") else None
                ),
                merger_date=(
                    date.fromisoformat(info["merger_date"])
                    if info.get("merger_date") else None
                ),
                acquirer=info.get("acquirer"),
                acquisition_consideration_pct=info.get("acquisition_consideration_pct"),
                bankruptcy_date=(
                    date.fromisoformat(info["bankruptcy_date"])
                    if info.get("bankruptcy_date") else None
                ),
                conservative_delisting_return_pct=info.get(
                    "conservative_delisting_return_pct", -100.0
                ),
                optimistic_delisting_return_pct=info.get("optimistic_delisting_return_pct"),
                has_live_price_history=info.get("has_live_price_history", True),
                missing_return_data=info.get("missing_return_data", False),
                notes=info.get("notes", ""),
            )
            entries.append(entry)
        return cls(entries)

    def to_yaml_dict(self) -> dict:
        """Serialise to YAML-compatible dict."""
        result: dict = {"securities": {}}
        for ticker, e in sorted(self._entries.items()):
            d: dict = {"company_name": e.company_name, "status": e.status.value}
            if e.delisting_reason:
                d["delisting_reason"] = e.delisting_reason.value
            if e.listing_start:
                d["listing_start"] = e.listing_start.isoformat()
            if e.listing_end:
                d["listing_end"] = e.listing_end.isoformat()
            if e.merger_date:
                d["merger_date"] = e.merger_date.isoformat()
            if e.acquirer:
                d["acquirer"] = e.acquirer
            if e.acquisition_consideration_pct is not None:
                d["acquisition_consideration_pct"] = e.acquisition_consideration_pct
            if e.bankruptcy_date:
                d["bankruptcy_date"] = e.bankruptcy_date.isoformat()
            d["conservative_delisting_return_pct"] = e.conservative_delisting_return_pct
            if e.optimistic_delisting_return_pct is not None:
                d["optimistic_delisting_return_pct"] = e.optimistic_delisting_return_pct
            d["has_live_price_history"] = e.has_live_price_history
            d["missing_return_data"] = e.missing_return_data
            if e.notes:
                d["notes"] = e.notes
            result["securities"][ticker] = d
        return result
