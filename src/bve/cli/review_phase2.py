"""
CLI for manual Phase 2 review of assumption changes.

Subcommands:
  - create-case: persist a review case from extraction/proposal/diff artifacts
  - show: render one case for audit inspection
  - act: record reviewer action (approve/reject/modify)
  - list: list cases with optional status filter
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from bve.intelligence.extraction.result import ExtractionResult
from bve.intelligence.phase2.manual_review import (
    ManualReviewStore,
    SourceDocumentMetadata,
    render_case,
)
from bve.intelligence.phase2.valuation_integration import ValuationDiffLog
from bve.intelligence.schemas.proposals import AssumptionChangeProposal


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_source_metadata(path: str) -> SourceDocumentMetadata:
    raw = _load_json(path)
    # Accept either direct SourceDocumentMetadata shape or RawDocument shape.
    if {"document_id", "source", "title"}.issubset(raw.keys()):
        return SourceDocumentMetadata.model_validate(raw)
    return SourceDocumentMetadata(
        document_id=raw["id"],
        source=raw["source"],
        title=raw["title"],
        source_url=raw.get("source_url"),
        published_at=raw.get("published_at"),
        retrieved_at=raw.get("retrieved_at"),
    )


def _parse_provenance(items: Optional[list[str]]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"Invalid provenance entry {item!r}; use key=value")
        key, val = item.split("=", 1)
        key = key.strip()
        val = val.strip()
        if not key:
            raise ValueError(f"Invalid provenance entry {item!r}; key cannot be empty")
        parsed[key] = val
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BVE Phase 2 manual review workflow")
    parser.add_argument(
        "--store-dir",
        default="outputs/intelligence_phase2/reviews",
        help="Review store directory (default: outputs/intelligence_phase2/reviews)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    create = sub.add_parser("create-case", help="Create and persist a manual review case")
    create.add_argument("--case-id", required=True)
    create.add_argument("--source-metadata", required=True, help="JSON file path")
    create.add_argument("--extraction-result", required=True, help="ExtractionResult JSON path")
    create.add_argument("--proposal", required=True, help="AssumptionChangeProposal JSON path")
    create.add_argument("--valuation-diff", required=True, help="ValuationDiffLog JSON path")

    show = sub.add_parser("show", help="Render a review case")
    show.add_argument("--case-id", required=True)

    act = sub.add_parser("act", help="Record a reviewer action")
    act.add_argument("--case-id", required=True)
    act.add_argument("--action", choices=["approve", "reject", "modify"], required=True)
    act.add_argument("--reviewer-id", required=True)
    act.add_argument("--rationale", required=True)
    act.add_argument("--override-value", type=float, default=None)
    act.add_argument(
        "--provenance",
        action="append",
        default=[],
        help="Provenance key=value (repeatable)",
    )

    list_cmd = sub.add_parser("list", help="List review cases")
    list_cmd.add_argument("--status", choices=["pending", "approved", "rejected", "modified"])
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    store = ManualReviewStore(args.store_dir)

    if args.cmd == "create-case":
        source = _load_source_metadata(args.source_metadata)
        extraction = ExtractionResult.model_validate(_load_json(args.extraction_result))
        proposal = AssumptionChangeProposal.model_validate(_load_json(args.proposal))
        valuation_diff = ValuationDiffLog.model_validate(_load_json(args.valuation_diff))
        case = store.create_case(
            case_id=args.case_id,
            source_document=source,
            extraction_result=extraction,
            proposal=proposal,
            valuation_diff=valuation_diff,
        )
        print(f"Created case: {case.id}")
        print(f"Path: {store.case_path(case.id)}")
        return

    if args.cmd == "show":
        case = store.load_case(args.case_id)
        print(render_case(case))
        return

    if args.cmd == "act":
        provenance = _parse_provenance(args.provenance)
        action = store.record_action(
            case_id=args.case_id,
            action=args.action,
            reviewer_id=args.reviewer_id,
            rationale=args.rationale,
            override_value=args.override_value,
            provenance=provenance,
        )
        case = store.load_case(args.case_id)
        print(
            f"Recorded action: {action.action} | {action.previous_status}->{action.next_status} "
            f"| reviewer={action.reviewer_id}"
        )
        print(render_case(case))
        return

    if args.cmd == "list":
        cases = store.list_cases(status=args.status)
        if not cases:
            print("(no cases)")
            return
        for case in cases:
            print(
                f"{case.id}\tstatus={case.status}\tproposal={case.proposal.id}\t"
                f"event={case.extraction_result.event_type_detected or 'unknown'}"
            )
        return

    raise RuntimeError(f"Unhandled command: {args.cmd!r}")


if __name__ == "__main__":
    main()
