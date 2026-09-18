"""Evaluate an S&E run against a declared frozen/development reference landscape."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bve.se.evaluation.benchmark import evaluate_reference_landscape
from bve.se.evaluation.discovery_coverage import evaluate_discovery_coverage
from bve.se.evaluation.ontology_gate import OntologySnapshotRequired
from bve.se.pipeline import SESearchResult


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bve-se-evaluate",
        description="Evaluate retrieval, citation, and UNKNOWN routing against a declared reference set.",
    )
    reference = parser.add_mutually_exclusive_group(required=True)
    reference.add_argument("--benchmark", help="Reference landscape YAML")
    reference.add_argument(
        "--reference-universe",
        help="Development reference-universe CSV for post-run canonical discovery coverage",
    )
    parser.add_argument("--result", required=True, help="bve-se-search JSON result")
    parser.add_argument("--reference-set", default="validation")
    parser.add_argument("--output")
    parser.add_argument(
        "--require-release-thresholds",
        action="store_true",
        help="Exit 2 when discovery coverage misses the declared release threshold.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = SESearchResult.model_validate_json(Path(args.result).read_text())
    try:
        report = (
            evaluate_reference_landscape(
                Path(args.benchmark), result, reference_set=args.reference_set
            )
            if args.benchmark
            else evaluate_discovery_coverage(result, Path(args.reference_universe))
        )
    except OntologySnapshotRequired as exc:
        # Exit 3 is distinct from the threshold miss (2): nothing was scored at all.
        sys.stderr.write(f"refusing to score: {exc}\n")
        return 3
    rendered = json.dumps(report.model_dump(mode="json"), indent=2)
    if args.output:
        Path(args.output).write_text(rendered + "\n")
    else:
        sys.stdout.write(rendered + "\n")
    if (
        args.require_release_thresholds
        and hasattr(report, "meets_release_thresholds")
        and not report.meets_release_thresholds()
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
