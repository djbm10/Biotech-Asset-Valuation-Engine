"""
Human review system utilities (Block 2L).

Provides tools for:
  1. Exporting a pending_events.csv so a reviewer can see what needs attention
  2. Loading reviewer decisions from a YAML file (review_decisions.yaml)
  3. Applying those decisions to a ReviewGate

review_decisions.yaml format
────────────────────────────
::

    decisions:
      - event_hash: abc0000000000001
        status: approved
        reviewer_id: djmann
        notes: "Confirmed Phase 3 positive — endpoint met"

      - event_hash: def0000000000002
        status: rejected
        notes: "Press release duplicate; already in SEC filing"

      - event_hash: ghi0000000000003
        status: downgraded
        downgrade_factor: 0.5
        reviewed_at: "2026-06-02"
        notes: "Conference abstract — low-confidence source"

pending_events.csv columns
──────────────────────────
event_hash, ticker, event_date, event_type, direction, confidence,
source_type, source_url, raw_text_preview

Usage::

    from bve.ingestion.review_apply import (
        load_review_decisions_yaml,
        build_pending_events_rows,
        write_pending_events_csv,
        apply_decisions_to_gate,
    )
    from bve.ingestion.review_gate import ReviewGate

    decisions = load_review_decisions_yaml("review_decisions.yaml")
    gate = ReviewGate()
    apply_decisions_to_gate(decisions, gate)

    # Export pending events for review
    rows = build_pending_events_rows(ledger, gate, as_of_date="2026-06-02")
    write_pending_events_csv(rows, "outputs/daily/2026-06-02/pending_events.csv")
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

from bve.ingestion.review_gate import ReviewDecision, ReviewGate, ReviewStatus


# ---------------------------------------------------------------------------
# Load decisions from YAML
# ---------------------------------------------------------------------------


def load_review_decisions_yaml(path: str | Path) -> list[ReviewDecision]:
    """
    Load reviewer decisions from a YAML file.

    Returns an empty list if the file does not exist (safe default for first run).
    """
    p = Path(path)
    if not p.exists():
        return []

    import yaml  # type: ignore[import-untyped]

    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not raw or "decisions" not in raw:
        return []

    decisions: list[ReviewDecision] = []
    for item in raw.get("decisions", []):
        if not isinstance(item, dict):
            continue
        event_hash = item.get("event_hash", "").strip()
        if not event_hash:
            continue
        status_str = item.get("status", "pending").lower()
        try:
            status = ReviewStatus(status_str)
        except ValueError:
            continue

        downgrade_factor = float(item.get("downgrade_factor", 1.0))
        # When status is DOWNGRADED but downgrade_factor is exactly 1.0, clamp to 0.9
        # to satisfy the ReviewDecision invariant (DOWNGRADED requires factor < 1.0).
        if status == ReviewStatus.DOWNGRADED and downgrade_factor >= 1.0:
            downgrade_factor = 0.9

        decisions.append(
            ReviewDecision(
                event_hash=event_hash,
                status=status,
                downgrade_factor=downgrade_factor,
                reviewer_id=item.get("reviewer_id"),
                notes=item.get("notes"),
                reviewed_at=item.get("reviewed_at"),
            )
        )
    return decisions


# ---------------------------------------------------------------------------
# Apply decisions to gate
# ---------------------------------------------------------------------------


def apply_decisions_to_gate(decisions: list[ReviewDecision], gate: ReviewGate) -> int:
    """
    Load a list of ReviewDecisions into a ReviewGate.

    Returns the number of decisions applied.
    """
    for d in decisions:
        gate.record_decision(d)
    return len(decisions)


# ---------------------------------------------------------------------------
# Build / write pending events CSV
# ---------------------------------------------------------------------------

_PENDING_CSV_FIELDS = [
    "event_hash",
    "ticker",
    "event_date",
    "event_type",
    "direction",
    "confidence",
    "source_type",
    "source_url",
    "raw_text_preview",
    "review_status",
]

_RAW_TEXT_PREVIEW_LEN = 120


def build_pending_events_rows(
    ledger,  # EvidenceLedger — avoid circular import with string annotation
    gate: ReviewGate,
    as_of_date: Optional[str] = None,
    pending_only: bool = True,
) -> list[dict]:
    """
    Build rows for the pending_events.csv review sheet.

    Parameters
    ----------
    ledger:
        EvidenceLedger to read all records from.
    gate:
        ReviewGate for looking up current review status.
    as_of_date:
        If provided, only include records with event_date ≤ as_of_date.
    pending_only:
        If True (default), only include PENDING records (no decision yet or
        explicitly PENDING status). Set False to export all records.
    """
    all_records = ledger.get_records()
    rows: list[dict] = []

    for rec in all_records:
        if as_of_date and rec.event_date > as_of_date:
            continue

        status = gate.get_status(rec.event_hash)

        if pending_only and status != ReviewStatus.PENDING:
            continue

        raw_preview = (rec.raw_text or "")[:_RAW_TEXT_PREVIEW_LEN]
        if len(rec.raw_text or "") > _RAW_TEXT_PREVIEW_LEN:
            raw_preview += "…"

        rows.append(
            {
                "event_hash": rec.event_hash,
                "ticker": rec.ticker,
                "event_date": rec.event_date,
                "event_type": rec.event_type,
                "direction": rec.direction,
                "confidence": f"{rec.confidence:.2f}",
                "source_type": rec.source_type,
                "source_url": rec.source_url,
                "raw_text_preview": raw_preview,
                "review_status": status.value,
            }
        )

    # Sort by ticker, then event_date
    rows.sort(key=lambda r: (r["ticker"], r["event_date"]))
    return rows


def write_pending_events_csv(rows: list[dict], path: str | Path) -> None:
    """Write pending event rows to a CSV file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_PENDING_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
