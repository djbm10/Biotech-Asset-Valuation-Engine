"""Persistent exclusion ledger — names that must not be proposed again.

When an analyst rejects a discovered candidate (wrong lead, partner artifact), or a
name is acquired / delisted / not actually a drug developer, we record it here so
routing stops surfacing it on every enumeration. This is durable curation state, so
it lives under ``examples/configs/`` (committed), not ``outputs/`` (gitignored).

The ledger is keyed by ticker. Re-excluding a ticker updates the existing record
rather than duplicating it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

_DEFAULT_LEDGER = "examples/configs/discovery_exclusions.yaml"

# Why a name is excluded. Open vocabulary, but these are the expected reasons.
REASON_REJECTED = "rejected"        # analyst judged the proposed lead wrong / not useful
REASON_ACQUIRED = "acquired"        # company acquired / no longer independent
REASON_DELISTED = "delisted"        # delisted / inactive
REASON_NOT_DEVELOPER = "not_drug_developer"  # not actually a clinical-stage developer
REASON_BAD_DATA = "bad_data"        # CT.gov data too poor to seed reliably


@dataclass(frozen=True)
class ExclusionRecord:
    ticker: str
    reason: str
    note: Optional[str]
    reviewer: Optional[str]
    excluded_at: str


class ExclusionLedger:
    """Load / query / update the durable exclusion ledger (YAML-backed)."""

    def __init__(self, path: str | Path = _DEFAULT_LEDGER) -> None:
        self.path = Path(path)
        self._records: dict[str, ExclusionRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        for row in raw.get("exclusions", []) or []:
            tkr = str(row.get("ticker", "")).upper()
            if not tkr:
                continue
            self._records[tkr] = ExclusionRecord(
                ticker=tkr,
                reason=row.get("reason", REASON_REJECTED),
                note=row.get("note"),
                reviewer=row.get("reviewer"),
                excluded_at=row.get("excluded_at", ""),
            )

    def is_excluded(self, ticker: str) -> bool:
        return ticker.upper() in self._records

    def get(self, ticker: str) -> Optional[ExclusionRecord]:
        return self._records.get(ticker.upper())

    def excluded_tickers(self) -> set[str]:
        return set(self._records)

    def records(self) -> list[ExclusionRecord]:
        return sorted(self._records.values(), key=lambda r: r.ticker)

    def add(
        self,
        ticker: str,
        reason: str = REASON_REJECTED,
        *,
        note: Optional[str] = None,
        reviewer: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> ExclusionRecord:
        """Add or update an exclusion (in memory; call ``save`` to persist)."""
        rec = ExclusionRecord(
            ticker=ticker.upper(),
            reason=reason,
            note=note,
            reviewer=reviewer,
            excluded_at=(now or datetime.now(timezone.utc)).isoformat(),
        )
        self._records[rec.ticker] = rec
        return rec

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        doc = {
            "exclusions": [
                {
                    "ticker": r.ticker,
                    "reason": r.reason,
                    "note": r.note,
                    "reviewer": r.reviewer,
                    "excluded_at": r.excluded_at,
                }
                for r in self.records()
            ]
        }
        self.path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
        return self.path
