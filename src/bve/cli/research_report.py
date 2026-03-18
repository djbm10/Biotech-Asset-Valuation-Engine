"""
CLI entry point: bve-research-report

Generate a deterministic research report for one asset.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a research report for one asset from KnowledgeStore data"
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
        help="Persist the generated report into KnowledgeStore",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output JSON instead of rendered markdown",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Write output to file path instead of stdout",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()

    from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace
    from bve.intelligence.research_report import ResearchReportGenerator

    store = KnowledgeStore(db_path=args.db)
    try:
        report = ResearchReportGenerator().generate(
            store,
            asset_id=args.asset_id,
            company_id=args.company_id,
            persist=args.persist,
            source_trace=SourceTrace(
                source_type="cli",
                source_ref="bve-research-report",
            ),
        )
    finally:
        store.close()

    output = report.model_dump_json(indent=2) if args.as_json else report.rendered_markdown
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"Research report written to {args.out}")
    else:
        print(output)


if __name__ == "__main__":
    main()
