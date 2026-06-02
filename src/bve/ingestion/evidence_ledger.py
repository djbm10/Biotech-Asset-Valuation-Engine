"""
Append-only JSONL evidence ledger.

Every event that changes a score is persisted here with full provenance:
  - Source, date, event type, raw text that generated it
  - Confidence level and match reasons (why the classifier fired)
  - Score deltas actually applied (bounded, confidence-weighted)

This ledger enables:
  1. Full audit trail — every score delta has a dated, sourced reason
  2. Score replay — reconstruct score state at any historical date
  3. Evidence export — show the model's reasoning for any target score
  4. Drift detection — compare scores at t-1 and t-0

File: outputs/intelligence/evidence_ledger.jsonl
Format: one JSON object per line, append-only, never overwritten.

Usage::

    from bve.ingestion.evidence_ledger import EvidenceLedger, EvidenceRecord
    from bve.ingestion.event_classifier import classify_headline

    ledger = EvidenceLedger()
    ev = classify_headline("Phase 3 trial met primary endpoint", ticker="RVMD")
    rec = EvidenceRecord.from_classification(ev, event_date="2025-06-01", source_url="https://...")
    ledger.append(rec)

    # Current score state for a ticker
    scores = ledger.compute_score_state("RVMD")

    # Score history (one row per event, ordered by date)
    history = ledger.get_score_history("RVMD")
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from bve.ingestion.event_classifier import EventClassification

_DEFAULT_LEDGER_PATH = (
    Path(__file__).resolve().parents[3] / "outputs" / "intelligence" / "evidence_ledger.jsonl"
)

# Default starting scores when no evidence history exists for a ticker.
# These are neutral priors — not strong claims.
DEFAULT_SEED_SCORES: dict[str, float] = {
    "asset_quality":      0.40,
    "seller_willingness": 0.30,
    "acquirer_fit":       0.50,
    "catalyst_timing":    0.30,
}


# ---------------------------------------------------------------------------
# EvidenceRecord
# ---------------------------------------------------------------------------


@dataclass
class EvidenceRecord:
    """One persisted evidence event."""

    # Identity
    ticker: str
    event_date: str              # ISO date (YYYY-MM-DD) the event occurred

    # Classification
    event_type: str
    direction: str               # positive | negative | mixed | neutral | unknown
    phase_detected: Optional[str]

    # Source provenance
    source_type: str             # clinicaltrials_gov | sec_filing | press_release | ...
    source_url: str
    raw_text: str

    # Extraction quality
    confidence: float            # 0.0–1.0
    match_reasons: list[str]

    # Score impact — bounded deltas that were (or will be) applied
    score_deltas: dict[str, float]

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ledger_version: str = "1"

    @classmethod
    def from_classification(
        cls,
        classification: EventClassification,
        event_date: str,
        source_url: str,
    ) -> "EvidenceRecord":
        """Build an EvidenceRecord from an EventClassification."""
        return cls(
            ticker=classification.ticker,
            event_date=event_date,
            event_type=classification.event_type,
            direction=classification.direction,
            phase_detected=classification.phase_detected,
            source_type=classification.source_type,
            source_url=source_url,
            raw_text=classification.raw_text,
            confidence=classification.confidence,
            match_reasons=classification.match_reasons,
            score_deltas=classification.score_deltas,
        )

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_jsonl(cls, line: str) -> "EvidenceRecord":
        return cls(**json.loads(line))


# ---------------------------------------------------------------------------
# EvidenceLedger
# ---------------------------------------------------------------------------


class EvidenceLedger:
    """
    Append-only evidence ledger backed by a JSONL file.

    Thread-safety: append() uses line-at-a-time writes which are atomic on
    POSIX filesystems for lines shorter than PIPE_BUF (~4KB). Suitable for
    single-writer use. For concurrent writes, add an external file lock.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_LEDGER_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ── Write ──────────────────────────────────────────────────────────────

    def append(self, record: EvidenceRecord) -> None:
        """Append one evidence record to the ledger."""
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(record.to_jsonl() + "\n")

    # ── Read ───────────────────────────────────────────────────────────────

    def get_records(
        self,
        ticker: Optional[str] = None,
        since_date: Optional[date] = None,
        until_date: Optional[date] = None,
        event_types: Optional[list[str]] = None,
    ) -> list[EvidenceRecord]:
        """
        Read records matching the given filters.

        Parameters
        ----------
        ticker:
            Only records for this ticker. None = all tickers.
        since_date:
            Only records on or after this date (inclusive).
        until_date:
            Only records on or before this date (inclusive).
        event_types:
            Only records with one of these event_type values.
        """
        if not self._path.exists():
            return []

        since_str = str(since_date) if since_date else None
        until_str = str(until_date) if until_date else None

        results: list[EvidenceRecord] = []
        with self._path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if ticker and obj.get("ticker") != ticker:
                    continue

                edate = obj.get("event_date", "")
                if since_str and edate and edate < since_str:
                    continue
                if until_str and edate and edate > until_str:
                    continue

                if event_types and obj.get("event_type") not in event_types:
                    continue

                results.append(EvidenceRecord(**obj))

        return results

    # ── Score replay ───────────────────────────────────────────────────────

    def compute_score_state(
        self,
        ticker: str,
        as_of_date: Optional[date] = None,
        seed_scores: Optional[dict[str, float]] = None,
    ) -> dict[str, float]:
        """
        Replay the ledger for a ticker up to as_of_date to compute current scores.

        Each event's score_deltas are applied in chronological order.
        Scores are clamped to [0.0, 1.0] after each delta.

        Parameters
        ----------
        ticker:
            Target or acquirer ticker.
        as_of_date:
            Replay up to and including this date. None = all history.
        seed_scores:
            Starting score values. None = DEFAULT_SEED_SCORES.

        Returns
        -------
        dict of feature → score (0.0–1.0)
        """
        scores = dict(seed_scores if seed_scores is not None else DEFAULT_SEED_SCORES)
        records = self.get_records(ticker=ticker, until_date=as_of_date)
        records.sort(key=lambda r: r.event_date)

        for record in records:
            for feature, delta in record.score_deltas.items():
                if feature in scores:
                    scores[feature] = max(0.0, min(1.0, scores[feature] + delta))

        return scores

    def get_score_history(
        self,
        ticker: str,
        features: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Return a time series of score snapshots for a ticker, one entry per event.

        Each entry contains event_date, event_type, direction, confidence,
        plus the score for each requested feature after that event was applied.

        Returns
        -------
        list[dict] ordered by event_date ascending.
        """
        target_features = features or list(DEFAULT_SEED_SCORES.keys())
        records = self.get_records(ticker=ticker)
        records.sort(key=lambda r: r.event_date)

        scores = dict(DEFAULT_SEED_SCORES)
        history: list[dict] = []

        for record in records:
            for feature, delta in record.score_deltas.items():
                if feature in scores:
                    scores[feature] = max(0.0, min(1.0, scores[feature] + delta))

            entry: dict = {
                "event_date":  record.event_date,
                "event_type":  record.event_type,
                "direction":   record.direction,
                "confidence":  record.confidence,
                "source_type": record.source_type,
                "raw_text":    record.raw_text[:120],  # truncate for display
            }
            for f in target_features:
                entry[f] = round(scores.get(f, 0.0), 4)
            history.append(entry)

        return history

    # ── Summary helpers ────────────────────────────────────────────────────

    def ticker_summary(self, ticker: str) -> dict:
        """Return a brief summary dict for a ticker."""
        records = self.get_records(ticker=ticker)
        if not records:
            return {
                "ticker":    ticker,
                "n_events":  0,
                "scores":    {k: round(v, 4) for k, v in DEFAULT_SEED_SCORES.items()},
            }
        records_sorted = sorted(records, key=lambda r: r.event_date)
        scores = self.compute_score_state(ticker)
        return {
            "ticker":            ticker,
            "n_events":          len(records),
            "first_event_date":  records_sorted[0].event_date,
            "last_event_date":   records_sorted[-1].event_date,
            "scores":            {k: round(v, 4) for k, v in scores.items()},
        }

    def all_tickers(self) -> list[str]:
        """Return sorted list of all tickers that have at least one ledger entry."""
        if not self._path.exists():
            return []
        seen: set[str] = set()
        with self._path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    t = obj.get("ticker")
                    if t:
                        seen.add(t)
                except json.JSONDecodeError:
                    continue
        return sorted(seen)
