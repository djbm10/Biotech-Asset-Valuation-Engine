"""
CLI entry point: bve-weekly-brief

Generates a one-page Markdown executive summary of the past week's
intelligence activity: review throughput, top opportunities, accepted
changes, and open-queue snapshot.

Usage
-----
    bve-weekly-brief --db outputs/intelligence_phase2/knowledge.db
    bve-weekly-brief --db knowledge.db --days 14 --top-n 10 --out brief.md
    bve-weekly-brief --db knowledge.db --json
"""
from __future__ import annotations

import argparse
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generate a weekly opportunity brief from the KnowledgeStore"
    )
    p.add_argument(
        "--db",
        default="outputs/intelligence_phase2/knowledge.db",
        help="Path to KnowledgeStore SQLite database",
    )
    p.add_argument(
        "--days",
        type=int,
        default=7,
        help="Lookback window in calendar days (default: 7)",
    )
    p.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="Number of top opportunities to include (default: 5)",
    )
    p.add_argument(
        "--out",
        default=None,
        help="Write Markdown output to this file path (default: print to stdout)",
    )
    p.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output the brief as JSON instead of Markdown",
    )
    return p


def main() -> None:
    args = _build_parser().parse_args()

    from bve.intelligence.knowledge_layer import KnowledgeStore
    from bve.intelligence.weekly_brief import WeeklyBriefGenerator, WeeklyBriefRenderer

    store = KnowledgeStore(db_path=args.db)
    try:
        generator = WeeklyBriefGenerator(lookback_days=args.days, top_n=args.top_n)
        brief = generator.generate(store)
    finally:
        store.close()

    if args.as_json:
        output = brief.model_dump_json(indent=2)
    else:
        renderer = WeeklyBriefRenderer()
        output = renderer.render(brief)

    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"Brief written to {args.out}")
    else:
        print(output)


if __name__ == "__main__":
    main()
