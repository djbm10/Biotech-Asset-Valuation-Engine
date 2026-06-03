"""
CLI: bve-seed-catalysts — Seed forward catalyst events into KnowledgeStore.

Usage
-----
    bve-seed-catalysts
    bve-seed-catalysts --dry-run
    bve-seed-catalysts --calendar research/catalyst_calendar_2026.yaml
    bve-seed-catalysts --db outputs/intelligence/ops.db --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


_DEFAULT_DB = "outputs/intelligence/ops.db"
_DEFAULT_CALENDAR = "research/catalyst_calendar_2026.yaml"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed forward catalyst events from a YAML calendar into KnowledgeStore."
    )
    parser.add_argument(
        "--db",
        default=_DEFAULT_DB,
        metavar="PATH",
        help=f"KnowledgeStore SQLite path (default: {_DEFAULT_DB})",
    )
    parser.add_argument(
        "--calendar",
        default=None,
        metavar="PATH",
        help=f"Catalyst calendar YAML path (default: {_DEFAULT_CALENDAR})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate without writing to the database",
    )
    args = parser.parse_args()

    from bve.ops.forward_calendar_seeder import ForwardCalendarSeeder
    from bve.intelligence.knowledge_layer import KnowledgeStore

    calendar_path = Path(args.calendar) if args.calendar else None

    try:
        seeder = ForwardCalendarSeeder(calendar_path=calendar_path)
    except Exception as exc:
        print(f"ERROR: could not load calendar: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        result = seeder.seed(None, dry_run=True)
        print(f"\n[dry-run] {result.seeded} events would be seeded\n")
        _print_entries(result)
        if result.errors:
            print(f"  {len(result.errors)} warning(s):")
            for e in result.errors:
                print(f"    - {e}")
        print()
        return

    try:
        store = KnowledgeStore(db_path=args.db)
    except Exception as exc:
        print(f"ERROR: could not open KnowledgeStore at {args.db!r}: {exc}", file=sys.stderr)
        sys.exit(1)

    result = seeder.seed(store, dry_run=False)

    print(f"\nbve-seed-catalysts: {result.seeded} seeded, {result.skipped} skipped\n")
    _print_entries(result)

    if result.errors:
        print(f"  {len(result.errors)} error(s):")
        for e in result.errors:
            print(f"    - {e}")

    print()


def _print_entries(result: object) -> None:
    from bve.ops.forward_calendar_seeder import SeedResult
    assert isinstance(result, SeedResult)
    if not result.entries:
        return
    col_w = [6, 12, 24, 10, 10]
    fmt = "  ".join(f"{{:<{w}}}" for w in col_w)
    print("  " + fmt.format("TICKER", "DATE", "TYPE", "CONF", "ID[:8]"))
    print("  " + "  ".join("─" * w for w in col_w))
    for e in result.entries:
        print("  " + fmt.format(
            e.ticker[:col_w[0]],
            str(e.expected_date),
            e.catalyst_type[:col_w[2]],
            e.date_confidence[:col_w[3]],
            e.event_id[:8],
        ))


if __name__ == "__main__":
    main()
