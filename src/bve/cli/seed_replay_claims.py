"""
CLI entry point: bve-seed-replay-claims

Seeds historical thesis claims (with accurate created_at / resolved_at dates)
into the replay KB so ThesisTracker.snapshot(as_of_date=...) reflects real
conviction state at each replay week.

Usage
-----
    bve-seed-replay-claims
    bve-seed-replay-claims --dry-run
    bve-seed-replay-claims --claims path/to/custom_claims.yaml
    bve-seed-replay-claims --db path/to/custom_replay_store.sqlite
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Seed historical thesis claims into the replay KB. "
            "Claims are inserted with accurate created_at / resolved_at dates "
            "so the no-lookahead thesis gate works correctly in replay runs."
        )
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and preview claims without writing to the database",
    )
    p.add_argument(
        "--claims",
        default=None,
        metavar="PATH",
        help=(
            "Path to thesis_claims_history.yaml "
            "(default: research/replay/thesis_claims_history.yaml)"
        ),
    )
    p.add_argument(
        "--db",
        default=None,
        metavar="PATH",
        help="Path to replay store SQLite database (default: auto-detected)",
    )
    return p


def main() -> None:
    args = _build_parser().parse_args()

    # Resolve DB path — claims live in the replay KNOWLEDGE store, not replay_store.sqlite
    if args.db:
        db_path = args.db
    else:
        from bve.ops.historical_replay import REPLAY_KNOWLEDGE_PATH
        db_path = str(REPLAY_KNOWLEDGE_PATH)

    # Resolve YAML path
    yaml_path = Path(args.claims) if args.claims else None

    from bve.ops.thesis_claims_backfiller import ThesisClaimsBackfiller

    backfiller = ThesisClaimsBackfiller(
        db_path,
        yaml_path=yaml_path,
        dry_run=args.dry_run,
    )

    try:
        claims = backfiller.load()
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error loading claims YAML: {exc}", file=sys.stderr)
        sys.exit(1)

    n_total = len(claims)
    print(
        f"{'[dry-run] ' if args.dry_run else ''}"
        f"Loaded {n_total} historical thesis claims from "
        f"{backfiller._yaml_path}"
    )

    result = backfiller.seed()

    if not args.dry_run:
        print(
            f"Done: {result['inserted']} inserted, "
            f"{result['skipped']} already present (skipped)."
        )
        if result["inserted"] > 0:
            print(
                "\nRe-run replay with --min-thesis-score 0.5 to use the "
                "thesis gate with real historical conviction data."
            )


if __name__ == "__main__":
    main()
