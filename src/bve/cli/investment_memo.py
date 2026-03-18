"""CLI for deterministic investment memo generation."""
from __future__ import annotations

import argparse
from pathlib import Path

from bve.intelligence.investment_memo_agent import InvestmentMemoAgent
from bve.intelligence.knowledge_layer import KnowledgeStore


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate deterministic investment memo")
    p.add_argument("--db", default="outputs/intelligence_phase2/knowledge.db")
    p.add_argument("--asset", required=True)
    p.add_argument("--company", default=None)
    p.add_argument("--out", default=None, help="Optional markdown output path")
    p.add_argument(
        "--persist",
        action="store_true",
        help="Persist memo to knowledge store as memo_type=investment_memo",
    )
    return p


def main() -> None:
    args = _build_parser().parse_args()
    store = KnowledgeStore(args.db)
    try:
        memo = InvestmentMemoAgent().generate(
            store,
            asset_id=args.asset,
            company_id=args.company,
            persist=args.persist,
        )
        if args.out:
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(memo.rendered_markdown, encoding="utf-8")
        else:
            print(memo.rendered_markdown)
    finally:
        store.close()


if __name__ == "__main__":
    main()
