"""
CLI entry point: bve-competitive-landscape

Generate a deterministic competitive landscape from knowledge graph records.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a competitive landscape for one asset from KnowledgeStore data"
    )
    parser.add_argument(
        "--db",
        default="outputs/intelligence_phase2/knowledge.db",
        help="Path to KnowledgeStore SQLite database",
    )
    parser.add_argument("--asset-id", required=True, help="Asset ID to analyze")
    parser.add_argument("--company-id", default=None, help="Optional company ID filter")
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist the generated landscape into KnowledgeStore",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output JSON instead of text table",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Write output to a file path instead of stdout",
    )
    return parser


def _render_text(landscape) -> str:
    lines = [
        f"Competitive Landscape: asset={landscape.asset_id} company={landscape.company_id or '-'}",
        f"generated_at={landscape.generated_at.isoformat()}",
        "",
        "drug | company | phase | mechanism | risk_score",
        "-----|---------|-------|-----------|-----------",
    ]
    if not landscape.entries:
        lines.append("(none)")
        return "\n".join(lines)

    for entry in landscape.entries:
        lines.append(
            f"{entry.drug} | {entry.company or '-'} | {entry.phase or '-'} | "
            f"{entry.mechanism or '-'} | {entry.risk_score:.3f}"
        )
    return "\n".join(lines)


def main() -> None:
    args = _build_parser().parse_args()

    from bve.intelligence.competitive_landscape_agent import CompetitiveLandscapeAgent
    from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace

    store = KnowledgeStore(db_path=args.db)
    try:
        agent = CompetitiveLandscapeAgent()
        landscape = agent.generate(
            store,
            asset_id=args.asset_id,
            company_id=args.company_id,
        )
        if args.persist:
            store.add_competitive_landscape(
                landscape,
                source_trace=SourceTrace(
                    source_type="cli",
                    source_ref="bve-competitive-landscape",
                ),
            )
    finally:
        store.close()

    output = landscape.model_dump_json(indent=2) if args.as_json else _render_text(landscape)
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"Competitive landscape written to {args.out}")
    else:
        print(output)


if __name__ == "__main__":
    main()
