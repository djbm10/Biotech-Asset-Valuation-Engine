"""CLI entry point: bve-opportunities."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from typing import Optional

from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.opportunity_snapshot import (
    OpportunitySnapshotRecord,
    OpportunitySnapshotStore,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Show latest top opportunity snapshots")
    parser.add_argument(
        "--db",
        default="outputs/intelligence_phase2/knowledge.db",
        help="Path to KnowledgeStore SQLite database",
    )
    parser.add_argument("--top", type=int, default=10, help="Number of rows to show")
    parser.add_argument(
        "--date",
        default=None,
        help="Snapshot date in YYYY-MM-DD format (default: latest available snapshot)",
    )
    parser.add_argument("--format", choices=["table", "json"], default="table")
    return parser


def _parse_snapshot_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid --date value: {raw!r}; expected YYYY-MM-DD") from exc


def _days_since_event(knowledge: KnowledgeStore, *, asset_id: str, as_of: date) -> Optional[int]:
    rows = knowledge.get_structured_signals(asset_id=asset_id, limit=1)
    if not rows:
        return None
    raw = rows[0].payload_json.get("signal_date")
    if raw is None:
        return None
    try:
        signal_date = date.fromisoformat(str(raw))
    except ValueError:
        return None
    return max(0, (as_of - signal_date).days)


def _format_table(
    knowledge: KnowledgeStore,
    snapshots: list[OpportunitySnapshotRecord],
    *,
    snapshot_date: date,
) -> str:
    if not snapshots:
        return f"No opportunity snapshots found for {snapshot_date.isoformat()}."

    widths = [4, 24, 7, 11, 10, 18, 6]
    header = (
        f"{'Rank':<{widths[0]}}  "
        f"{'Asset':<{widths[1]}}  "
        f"{'Score':>{widths[2]}}  "
        f"{'Mispricing':>{widths[3]}}  "
        f"{'Conf':>{widths[4]}}  "
        f"{'Event':<{widths[5]}}  "
        f"{'Days':>{widths[6]}}"
    )
    separator = "-" * len(header)
    lines = [
        f"Snapshot date: {snapshot_date.isoformat()}",
        separator,
        header,
        separator,
    ]
    for row in snapshots:
        mispricing = f"{row.mispricing:+.2f}" if row.mispricing is not None else "n/a"
        days = _days_since_event(knowledge, asset_id=row.asset_id, as_of=snapshot_date)
        lines.append(
            f"{row.rank:<{widths[0]}}  "
            f"{row.asset_id:<{widths[1]}}  "
            f"{row.score:>{widths[2]}.2f}  "
            f"{mispricing:>{widths[3]}}  "
            f"{row.confidence:>{widths[4]}.2f}  "
            f"{(row.event_type or 'unknown'):<{widths[5]}}  "
            f"{(days if days is not None else 'n/a'):>{widths[6]}}"
        )
    return "\n".join(lines)


def main() -> None:
    args = _build_parser().parse_args()
    knowledge = KnowledgeStore(args.db)
    snapshot_store = OpportunitySnapshotStore(knowledge)
    try:
        snapshot_date = (
            _parse_snapshot_date(args.date)
            if args.date
            else snapshot_store.latest_snapshot_date()
        )
        if snapshot_date is None:
            print("No opportunity snapshots found.", file=sys.stderr)
            raise SystemExit(1)
        snapshots = snapshot_store.get_snapshots(
            snapshot_date=snapshot_date,
            top_n=args.top,
            limit=args.top,
        )
        if args.format == "json":
            print(
                json.dumps(
                    {
                    "snapshot_date": snapshot_date.isoformat(),
                    "opportunities": [row.model_dump(mode="json") for row in snapshots],
                    },
                    ensure_ascii=True,
                    indent=2,
                )
            )
            return
        print(_format_table(knowledge, snapshots, snapshot_date=snapshot_date))
    finally:
        knowledge.close()


if __name__ == "__main__":
    main()
