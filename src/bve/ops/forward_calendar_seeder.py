"""
ops/forward_calendar_seeder.py — Seed catalyst_events from a curated YAML calendar.

Design
------
- Idempotent: each event gets a deterministic UUID derived from
  ``(ticker, catalyst_type, expected_date)`` via uuid5. Re-seeding the
  same YAML never creates duplicate rows.
- No EV fields populated here — CatalystEVCalculator can be run separately
  once asset configs are loaded. EV fields are optional on CatalystEvent.
- asset_id / company_id default to the ``"a-{ticker.lower()}"`` and
  ``"co-{ticker.lower()}"`` convention used throughout the ops layer.

Usage
-----
    from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
    from bve.intelligence.knowledge_layer import KnowledgeStore

    seeder = ForwardCalendarSeeder()          # uses default calendar path
    result = seeder.seed(store, dry_run=False)
    print(result.seeded, "events seeded")

CLI: see src/bve/cli/seed_catalysts.py / bve-seed-catalysts entry point.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional
import uuid
import warnings

import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_CALENDAR = (
    Path(__file__).resolve().parents[3]   # project root (ops → bve → src → root)
    / "research"
    / "catalyst_calendar_2026.yaml"
)

_CATALYST_TYPE_MAP: dict[str, str] = {
    "trial_readout":        "trial_readout",
    "pdufa_decision":       "pdufa_decision",
    "adcom_meeting":        "adcom_meeting",
    "enrollment_complete":  "enrollment_complete",
    "conference_abstract":  "conference_abstract",
    "competitor_readout":   "competitor_readout",
}

_DATE_CONFIDENCE_VALUES = frozenset({"exact", "quarter", "half_year", "estimate"})

_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # uuid.NAMESPACE_URL


def _deterministic_id(ticker: str, catalyst_type: str, expected_date: str) -> str:
    """Return a deterministic UUID string for (ticker, catalyst_type, expected_date)."""
    key = f"{ticker.upper()}:{catalyst_type.lower()}:{expected_date}"
    return str(uuid.uuid5(_NAMESPACE, key))


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class SeedEntry:
    """One successfully parsed calendar entry ready for insertion."""
    event_id: str
    ticker: str
    asset_id: str
    company_id: str
    catalyst_type: str
    description: str
    expected_date: date
    date_confidence: str
    source: str


@dataclass
class SeedResult:
    """Summary returned by ForwardCalendarSeeder.seed()."""
    seeded: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    entries: list[SeedEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Seeder
# ---------------------------------------------------------------------------

class ForwardCalendarSeeder:
    """
    Read a catalyst calendar YAML and seed KnowledgeStore.catalyst_events.

    Parameters
    ----------
    calendar_path:
        Path to a YAML file following the ``research/catalyst_calendar_2026.yaml``
        schema. Defaults to that file relative to the project root.
    """

    def __init__(self, calendar_path: Optional[Path] = None) -> None:
        self._path = Path(calendar_path) if calendar_path else _DEFAULT_CALENDAR

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> list[SeedEntry]:
        """
        Parse the calendar YAML and return validated SeedEntry objects.

        Invalid rows are skipped with a UserWarning. Rows that reference an
        unknown catalyst_type are also skipped.
        """
        raw = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        rows: list[dict] = raw.get("catalysts") or []
        entries: list[SeedEntry] = []

        for i, row in enumerate(rows):
            try:
                entry = self._parse_row(i, row)
            except (KeyError, ValueError) as exc:
                warnings.warn(
                    f"catalyst_calendar row {i}: skipped — {exc}",
                    UserWarning,
                    stacklevel=2,
                )
                continue
            if entry is not None:
                entries.append(entry)

        return entries

    def seed(
        self,
        store: object,
        *,
        dry_run: bool = False,
    ) -> SeedResult:
        """
        Seed catalyst events into *store*.

        Parameters
        ----------
        store:
            A ``KnowledgeStore`` instance.
        dry_run:
            When True, parse and validate entries but do not write to the
            database. Returns the full entry list in ``SeedResult.entries``.
        """
        from bve.intelligence.catalyst_calendar import CatalystEvent, CatalystType

        result = SeedResult()
        entries = self.load()

        for entry in entries:
            try:
                ct = CatalystType(entry.catalyst_type)
            except ValueError:
                result.skipped += 1
                result.errors.append(
                    f"{entry.ticker}: unknown catalyst_type {entry.catalyst_type!r}"
                )
                continue

            event = CatalystEvent(
                id=entry.event_id,
                asset_id=entry.asset_id,
                company_id=entry.company_id,
                catalyst_type=ct,
                expected_date=entry.expected_date,
                date_confidence=entry.date_confidence,  # type: ignore[arg-type]
                source=entry.source,
                description=entry.description,
                is_active=True,
                resolved=False,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

            result.entries.append(entry)

            if not dry_run:
                try:
                    store.upsert_catalyst_event(event)  # type: ignore[attr-defined]
                    result.seeded += 1
                except Exception as exc:
                    result.skipped += 1
                    result.errors.append(f"{entry.ticker}: upsert failed — {exc}")
            else:
                result.seeded += 1

        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _parse_row(self, index: int, row: dict) -> Optional[SeedEntry]:
        ticker = str(row["ticker"]).upper()
        raw_type = str(row["catalyst_type"]).lower()
        raw_date = str(row["expected_date"])
        description = str(row.get("description", "")).strip()
        source = str(row.get("source", "")).strip()
        date_confidence = str(row.get("date_confidence", "estimate")).lower()

        if raw_type not in _CATALYST_TYPE_MAP:
            warnings.warn(
                f"catalyst_calendar row {index} ({ticker}): "
                f"unknown catalyst_type {raw_type!r} — skipped",
                UserWarning,
                stacklevel=3,
            )
            return None

        if date_confidence not in _DATE_CONFIDENCE_VALUES:
            raise ValueError(
                f"invalid date_confidence {date_confidence!r}; "
                f"must be one of {sorted(_DATE_CONFIDENCE_VALUES)}"
            )

        expected_date = date.fromisoformat(raw_date)
        catalyst_type = _CATALYST_TYPE_MAP[raw_type]
        event_id = _deterministic_id(ticker, catalyst_type, raw_date)

        asset_id = str(row.get("asset_id") or f"a-{ticker.lower()}")
        company_id = str(row.get("company_id") or f"co-{ticker.lower()}")

        return SeedEntry(
            event_id=event_id,
            ticker=ticker,
            asset_id=asset_id,
            company_id=company_id,
            catalyst_type=catalyst_type,
            description=description,
            expected_date=expected_date,
            date_confidence=date_confidence,
            source=source,
        )
