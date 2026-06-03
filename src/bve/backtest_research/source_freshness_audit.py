"""
source_freshness_audit — per-feature source timing analysis.

For every feature row in the feature store, computes:
  - source_published_date
  - source_retrieved_at    (same as data_as_of_date — best available proxy)
  - data_as_of_date
  - snapshot_date
  - days_between_source_and_snapshot  (snapshot - source, negative = violation)
  - source_is_before_snapshot  (bool)

The audit CSV is written alongside the leakage audit and is referenced in
the source_audit.md report.
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Any, Optional


def _parse_date(value: Any) -> Optional[date]:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def build_freshness_rows(
    feature_rows: "list[dict[str, Any]]",
) -> list[dict[str, Any]]:
    """
    Given a list of feature store dicts, return freshness audit rows.

    Each output row corresponds to one feature store row.
    """
    result: list[dict[str, Any]] = []
    for row in feature_rows:
        snap = _parse_date(row.get("snapshot_date"))
        spd  = _parse_date(row.get("source_published_date"))
        dad  = _parse_date(row.get("data_as_of_date"))

        days_spd: Optional[int] = None
        days_dad: Optional[int] = None
        is_before_snapshot_spd: Optional[bool] = None
        is_before_snapshot_dad: Optional[bool] = None

        if snap and spd:
            days_spd = (snap - spd).days
            is_before_snapshot_spd = spd <= snap
        if snap and dad:
            days_dad = (snap - dad).days
            is_before_snapshot_dad = dad <= snap

        result.append({
            "deal_id": row.get("deal_id", ""),
            "acquirer_ticker": row.get("acquirer_ticker", ""),
            "target_ticker": row.get("target_ticker", ""),
            "snapshot_date": row.get("snapshot_date", ""),
            "days_before": row.get("days_before", ""),
            "is_actual_target": row.get("is_actual_target", ""),
            "extraction_method": row.get("extraction_method", ""),
            "source_url": row.get("source_url", ""),
            # Timing fields
            "source_published_date": row.get("source_published_date", ""),
            "source_retrieved_at": row.get("data_as_of_date", ""),  # best proxy
            "data_as_of_date": row.get("data_as_of_date", ""),
            "days_source_before_snapshot": days_spd,
            "days_data_before_snapshot": days_dad,
            "source_is_before_snapshot": is_before_snapshot_spd,
            "data_is_before_snapshot": is_before_snapshot_dad,
            "confidence": row.get("confidence", ""),
            "provenance_complete": row.get("provenance_complete", ""),
        })
    return result


def write_freshness_audit(
    feature_rows: "list[dict[str, Any]]",
    output_path: "str | Path",
) -> Path:
    """Build and write the source freshness audit CSV."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = build_freshness_rows(feature_rows)
    if not rows:
        output_path.write_text("", encoding="utf-8")
        return output_path
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def freshness_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Return summary stats over freshness audit rows."""
    total = len(rows)
    violations = sum(
        1 for r in rows
        if r.get("source_is_before_snapshot") is False
        or r.get("data_is_before_snapshot") is False
    )
    complete = sum(
        1 for r in rows
        if r.get("source_is_before_snapshot") is True
        and r.get("data_is_before_snapshot") is True
    )
    days_vals = [
        int(r["days_source_before_snapshot"])
        for r in rows
        if r.get("days_source_before_snapshot") is not None
    ]
    avg_days = sum(days_vals) / len(days_vals) if days_vals else None
    return {
        "total_rows": total,
        "violations": violations,
        "clean_rows": complete,
        "clean_pct": round(complete / max(total, 1) * 100, 1),
        "avg_days_source_before_snapshot": round(avg_days, 1) if avg_days else None,
    }
