"""
ops/trial_event_backfiller.py — Seed replay-store historical trial readout events.

Design
------
- Reads ``research/replay/events_2021_2023.yaml`` (or a caller-supplied path).
- Builds a deterministic event_id: ``trial:{TICKER}:{announced_at}`` so that
  re-running the backfill never creates duplicate rows.
- Writes directly to the ``historical_events`` table in the replay SQLite via
  ``INSERT OR REPLACE`` keyed on ``event_id``.
- Returns a :class:`BackfillResult` with inserted / skipped / error counts.

Usage
-----
    from bve.ops.trial_event_backfiller import TrialEventBackfiller

    result = TrialEventBackfiller().backfill()
    print(result.inserted, "events inserted")

CLI: ``bve-seed-replay-events``
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

import yaml

from bve.ops.historical_replay import REPLAY_STORE_PATH, ReplayStore


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_EVENTS_FILE = (
    Path(__file__).resolve().parents[3]   # project root
    / "research"
    / "replay"
    / "events_2021_2023.yaml"
)

_VALID_OUTCOME_LABELS = frozenset({"positive", "negative", "mixed", "neutral"})

_VALID_EVENT_TYPES = frozenset({
    "trial_readout",
    "pdufa_decision",
    "adcom_meeting",
    "enrollment_complete",
    "conference_abstract",
    "competitor_readout",
})


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class BackfillResult:
    """Summary returned by :meth:`TrialEventBackfiller.backfill`."""
    inserted: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Backfiller
# ---------------------------------------------------------------------------

class TrialEventBackfiller:
    """
    Read a trial-readout events YAML and seed ``historical_events`` in the
    replay SQLite store.

    Parameters
    ----------
    events_path:
        Path to the YAML file.  Defaults to
        ``research/replay/events_2021_2023.yaml`` relative to the project root.
    replay_db_path:
        Path to the replay SQLite database.  Defaults to the standard
        ``REPLAY_STORE_PATH`` used by ``ReplayStore``.
    """

    def __init__(
        self,
        events_path: Optional[Path] = None,
        *,
        replay_db_path: str = str(REPLAY_STORE_PATH),
    ) -> None:
        self._events_path = Path(events_path) if events_path else _DEFAULT_EVENTS_FILE
        self._replay_db_path = replay_db_path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> list[dict]:
        """
        Parse the events YAML and return the raw list of validated event dicts.

        Invalid rows are skipped with a :class:`UserWarning`.
        """
        raw = yaml.safe_load(self._events_path.read_text(encoding="utf-8")) or {}
        rows: list[dict] = raw.get("events") or []
        validated: list[dict] = []

        for i, row in enumerate(rows):
            try:
                entry = self._validate_row(i, row)
            except (KeyError, ValueError) as exc:
                warnings.warn(
                    f"trial_events row {i}: skipped — {exc}",
                    UserWarning,
                    stacklevel=2,
                )
                continue
            if entry is not None:
                validated.append(entry)

        return validated

    def backfill(self, *, dry_run: bool = False) -> BackfillResult:
        """
        Seed trial events into the replay store.

        Parameters
        ----------
        dry_run:
            When True, parse and validate entries but do not write to the
            database.  Returns accurate ``inserted`` count (what *would* be
            written).
        """
        result = BackfillResult()
        rows = self.load()

        if dry_run:
            result.inserted = len(rows)
            return result

        store = ReplayStore(self._replay_db_path)
        try:
            for row in rows:
                event_id = f"trial:{row['ticker']}:{row['announced_at']}"
                try:
                    store._conn.execute(
                        """
                        INSERT OR REPLACE INTO historical_events
                            (event_id, asset_id, ticker, event_type, announced_at,
                             effective_date, outcome_label, headline)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event_id,
                            row["asset_id"],
                            row["ticker"],
                            row["event_type"],
                            row["announced_at"],
                            row["announced_at"],   # effective_date == announced_at
                            row["outcome_label"],
                            row["headline"],
                        ),
                    )
                    result.inserted += 1
                except Exception as exc:
                    result.skipped += 1
                    result.errors.append(
                        f"{row['ticker']} {row['announced_at']}: insert failed — {exc}"
                    )
            store._conn.commit()
        finally:
            store.close()

        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _validate_row(self, index: int, row: dict) -> Optional[dict]:
        asset_id = str(row["asset_id"]).strip()
        ticker = str(row["ticker"]).strip().upper()
        event_type = str(row["event_type"]).strip().lower()
        announced_at = str(row["announced_at"]).strip()
        outcome_label = str(row.get("outcome_label", "neutral")).strip().lower()
        headline = str(row.get("headline", "")).strip()

        # Validate date format
        date.fromisoformat(announced_at)   # raises ValueError if malformed

        if event_type not in _VALID_EVENT_TYPES:
            warnings.warn(
                f"trial_events row {index} ({ticker}): "
                f"unknown event_type {event_type!r} — skipped",
                UserWarning,
                stacklevel=4,
            )
            return None

        if outcome_label not in _VALID_OUTCOME_LABELS:
            raise ValueError(
                f"invalid outcome_label {outcome_label!r}; "
                f"must be one of {sorted(_VALID_OUTCOME_LABELS)}"
            )

        return {
            "asset_id": asset_id,
            "ticker": ticker,
            "event_type": event_type,
            "announced_at": announced_at,
            "outcome_label": outcome_label,
            "headline": headline,
        }
