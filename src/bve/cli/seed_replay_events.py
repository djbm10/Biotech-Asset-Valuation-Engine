"""
cli/seed_replay_events.py — CLI wrapper for TrialEventBackfiller.

Entry point: ``bve-seed-replay-events``

Examples
--------
    # Dry-run: show what would be seeded
    bve-seed-replay-events --dry-run

    # Live seed into the default replay store
    bve-seed-replay-events

    # Use a custom events file and database
    bve-seed-replay-events --events research/replay/events_2024.yaml --db /tmp/test.sqlite
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bve.ops.historical_replay import REPLAY_STORE_PATH
from bve.ops.trial_event_backfiller import TrialEventBackfiller


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seed historical trial readout events into the replay store."
    )
    parser.add_argument(
        "--events",
        metavar="PATH",
        default=None,
        help="Path to events YAML (default: research/replay/events_2021_2023.yaml)",
    )
    parser.add_argument(
        "--db",
        metavar="PATH",
        default=str(REPLAY_STORE_PATH),
        help="Path to replay SQLite database",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Parse and validate without writing to the database",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()

    events_path = Path(args.events) if args.events else None
    backfiller = TrialEventBackfiller(
        events_path=events_path,
        replay_db_path=args.db,
    )

    # Load and print a preview
    rows = backfiller.load()
    if not rows:
        print("No valid events found — nothing to seed.")
        sys.exit(0)

    _print_preview(rows, dry_run=args.dry_run)

    if args.dry_run:
        print(f"\nDry-run complete — {len(rows)} event(s) would be seeded.")
        return

    result = backfiller.backfill(dry_run=False)

    print("\nBackfill complete:")
    print(f"  Inserted : {result.inserted}")
    print(f"  Skipped  : {result.skipped}")
    if result.errors:
        print("  Errors:")
        for e in result.errors:
            print(f"    - {e}")


def _print_preview(rows: list[dict], *, dry_run: bool) -> None:
    label = "[DRY-RUN] " if dry_run else ""
    print(f"{label}Trial events to seed ({len(rows)} total):\n")
    header = f"{'TICKER':<8}  {'DATE':<12}  {'TYPE':<22}  {'OUTCOME':<10}  HEADLINE"
    print(header)
    print("-" * len(header))
    for row in rows:
        headline_short = row["headline"][:60] + "…" if len(row["headline"]) > 60 else row["headline"]
        print(
            f"{row['ticker']:<8}  {row['announced_at']:<12}  "
            f"{row['event_type']:<22}  {row['outcome_label']:<10}  {headline_short}"
        )


if __name__ == "__main__":
    main()
