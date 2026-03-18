"""
CLI entry point: bve-literature-review

Generate a deterministic literature review for one asset from ingested
documents in KnowledgeStore.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a literature review for one asset from KnowledgeStore data"
    )
    parser.add_argument(
        "--db",
        default="outputs/intelligence_phase2/knowledge.db",
        help="Path to KnowledgeStore SQLite database",
    )
    parser.add_argument("--asset-id", required=True, help="Asset ID to review")
    parser.add_argument("--company-id", default=None, help="Optional company ID filter")
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist the generated review into KnowledgeStore",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output JSON instead of plain-text section view",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Write output to a file instead of stdout",
    )
    return parser


def _render_text(review) -> str:
    lines = [
        f"Literature Review: asset={review.asset_id} company={review.company_id or '-'}",
        f"generated_at={review.generated_at.isoformat()}",
        "",
        "## Efficacy",
        review.efficacy_summary,
        "",
        "## Safety",
        review.safety_summary,
        "",
        "## Mechanism",
        review.mechanism_summary,
        "",
        "## Biomarkers",
        review.biomarker_summary,
        "",
        "## Trial Outcomes",
        review.trial_outcomes_summary,
        "",
        "## Knowledge Gaps",
    ]
    if review.knowledge_gaps:
        lines.extend([f"- {gap}" for gap in review.knowledge_gaps])
    else:
        lines.append("- none")
    return "\n".join(lines)


def main() -> None:
    args = _build_parser().parse_args()

    from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace
    from bve.intelligence.literature_review_agent import LiteratureReviewAgent

    store = KnowledgeStore(db_path=args.db)
    try:
        agent = LiteratureReviewAgent()
        review = agent.generate(
            store,
            asset_id=args.asset_id,
            company_id=args.company_id,
        )
        if args.persist:
            store.add_literature_review(
                review,
                source_trace=SourceTrace(
                    source_type="cli",
                    source_ref="bve-literature-review",
                ),
            )
    finally:
        store.close()

    output = review.model_dump_json(indent=2) if args.as_json else _render_text(review)
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"Literature review written to {args.out}")
    else:
        print(output)


if __name__ == "__main__":
    main()
