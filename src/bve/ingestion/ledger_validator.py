"""
Evidence ledger validator (Block 2I).

Validates every record in an evidence_ledger.jsonl file against a set of
structural, semantic, and integrity rules without modifying the file.

Rules checked
─────────────
File-level
  F1  File exists and is non-empty
  F2  Every line is valid JSON (no parse errors)
  F3  No blank lines that would disrupt line-count health checks

Record-level (required fields)
  R1  All required fields present: ticker, event_date, event_type, direction,
      source_type, source_url, raw_text, confidence, score_deltas, event_hash,
      published_date, ledger_version
  R2  ticker is a non-empty string
  R3  direction ∈ {positive, negative, mixed, neutral, unknown}
  R4  confidence ∈ [0.0, 1.0]
  R5  event_date is a valid ISO date (YYYY-MM-DD)
  R6  published_date is a valid ISO date (YYYY-MM-DD) when present

Temporal rules (require as_of_date)
  T1  event_date ≤ as_of_date  (no future events)
  T2  published_date ≤ as_of_date when present

Score delta rules
  S1  Each delta key is a recognised feature name
  S2  Each delta value abs ≤ MAX_SINGLE_EVENT_DELTA for that feature

Integrity rules
  I1  event_hash is non-empty
  I2  No duplicate event_hash values within the file

Universe rules (require known_tickers)
  U1  ticker is in the known_tickers set

Usage::

    from bve.ingestion.ledger_validator import LedgerValidator

    result = LedgerValidator(
        path="outputs/intelligence/evidence_ledger.jsonl",
        as_of_date="2026-06-02",
        known_tickers={"RVMD", "BEAM", "NTLA"},
    ).validate()

    if not result.is_valid:
        for e in result.errors:
            print(e)
        sys.exit(1)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from bve.ingestion.event_classifier import MAX_SINGLE_EVENT_DELTA

_REQUIRED_FIELDS = frozenset(
    [
        "ticker",
        "event_date",
        "event_type",
        "direction",
        "source_type",
        "source_url",
        "raw_text",
        "confidence",
        "score_deltas",
        "event_hash",
        "ledger_version",
    ]
)

_VALID_DIRECTIONS = frozenset(["positive", "negative", "mixed", "neutral", "unknown"])

_KNOWN_DELTA_KEYS = frozenset(MAX_SINGLE_EVENT_DELTA.keys())


@dataclass
class LedgerValidationResult:
    """Outcome of a ledger validation run."""

    path: str
    total_lines: int = 0
    valid_records: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)


class LedgerValidator:
    """
    Validates an evidence ledger JSONL file.

    Parameters
    ----------
    path:
        Path to the JSONL file.
    as_of_date:
        ISO date string (YYYY-MM-DD). When provided, records with
        event_date or published_date beyond this date are flagged as errors.
    known_tickers:
        If provided, records with tickers not in this set are flagged as warnings
        (not errors — new tickers may legitimately appear during ingestion).
    strict_delta_keys:
        If True (default), unknown delta keys are flagged as warnings.
        Set False if you allow custom feature keys.
    """

    def __init__(
        self,
        path: str | Path,
        as_of_date: Optional[str] = None,
        known_tickers: Optional[set[str]] = None,
        strict_delta_keys: bool = True,
    ) -> None:
        self._path = Path(path)
        self._as_of: Optional[date] = None
        if as_of_date:
            self._as_of = date.fromisoformat(as_of_date)
        self._known_tickers = known_tickers
        self._strict_delta_keys = strict_delta_keys

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self) -> LedgerValidationResult:
        result = LedgerValidationResult(path=str(self._path))

        # F1 — file exists and non-empty
        if not self._path.exists():
            result.errors.append(f"F1: File not found: {self._path}")
            return result
        if self._path.stat().st_size == 0:
            result.warnings.append(f"F1: File is empty: {self._path}")
            return result

        seen_hashes: dict[str, int] = {}  # hash → first line number

        with self._path.open(encoding="utf-8") as fh:
            for lineno, raw_line in enumerate(fh, start=1):
                result.total_lines += 1

                # F3 — blank lines
                if not raw_line.strip():
                    result.warnings.append(f"F3 line {lineno}: blank line")
                    continue

                # F2 — valid JSON
                try:
                    rec = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    result.errors.append(f"F2 line {lineno}: JSON parse error: {exc}")
                    continue

                if not isinstance(rec, dict):
                    result.errors.append(f"F2 line {lineno}: expected JSON object, got {type(rec).__name__}")
                    continue

                self._validate_record(rec, lineno, seen_hashes, result)

        return result

    # ------------------------------------------------------------------
    # Per-record validation
    # ------------------------------------------------------------------

    def _validate_record(
        self,
        rec: dict,
        lineno: int,
        seen_hashes: dict[str, int],
        result: LedgerValidationResult,
    ) -> None:
        pfx = f"line {lineno}"
        had_error = False

        def err(msg: str) -> None:
            nonlocal had_error
            had_error = True
            result.errors.append(f"{pfx}: {msg}")

        def warn(msg: str) -> None:
            result.warnings.append(f"{pfx}: {msg}")

        # R1 — required fields
        missing = _REQUIRED_FIELDS - rec.keys()
        if missing:
            err(f"R1: missing required fields: {sorted(missing)}")

        # R2 — ticker
        ticker = rec.get("ticker", "")
        if not isinstance(ticker, str) or not ticker.strip():
            err("R2: ticker must be a non-empty string")

        # R3 — direction
        direction = rec.get("direction", "")
        if direction not in _VALID_DIRECTIONS:
            err(f"R3: direction '{direction}' not in {sorted(_VALID_DIRECTIONS)}")

        # R4 — confidence
        confidence = rec.get("confidence")
        if confidence is None:
            pass  # covered by R1
        elif not isinstance(confidence, (int, float)) or not (0.0 <= float(confidence) <= 1.0):
            err(f"R4: confidence {confidence!r} must be a float in [0.0, 1.0]")

        # R5 — event_date
        event_date_str = rec.get("event_date", "")
        event_date = _parse_iso_date(event_date_str)
        if event_date is None:
            err(f"R5: event_date '{event_date_str}' is not a valid ISO date")

        # R6 — published_date (optional field, but validate if present)
        pub_date_str = rec.get("published_date")
        pub_date = None
        if pub_date_str:
            pub_date = _parse_iso_date(pub_date_str)
            if pub_date is None:
                err(f"R6: published_date '{pub_date_str}' is not a valid ISO date")

        # T1 — event_date ≤ as_of
        if self._as_of and event_date and event_date > self._as_of:
            err(f"T1: event_date {event_date} is after as_of_date {self._as_of}")

        # T2 — published_date ≤ as_of
        if self._as_of and pub_date and pub_date > self._as_of:
            err(f"T2: published_date {pub_date} is after as_of_date {self._as_of}")

        # S1/S2 — score deltas
        deltas = rec.get("score_deltas")
        if isinstance(deltas, dict):
            for key, val in deltas.items():
                if self._strict_delta_keys and key not in _KNOWN_DELTA_KEYS:
                    warn(f"S1: unknown delta key '{key}'")
                cap = MAX_SINGLE_EVENT_DELTA.get(key, 0.20)
                if isinstance(val, (int, float)) and abs(float(val)) > cap + 1e-9:
                    err(f"S2: delta '{key}'={val} exceeds cap {cap}")
        elif deltas is not None:
            err(f"S1: score_deltas must be a dict, got {type(deltas).__name__}")

        # I1 — event_hash non-empty
        evt_hash = rec.get("event_hash", "")
        if not isinstance(evt_hash, str) or not evt_hash.strip():
            err("I1: event_hash is empty or missing")
        else:
            # I2 — duplicate hash
            if evt_hash in seen_hashes:
                err(f"I2: duplicate event_hash '{evt_hash}' (first seen at line {seen_hashes[evt_hash]})")
            else:
                seen_hashes[evt_hash] = lineno

        # U1 — known tickers
        if self._known_tickers and ticker and ticker not in self._known_tickers:
            warn(f"U1: ticker '{ticker}' not in known_tickers universe")

        if not had_error:
            result.valid_records += 1


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------


def _parse_iso_date(value: str) -> Optional[date]:
    """Parse YYYY-MM-DD; return None on failure."""
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None
