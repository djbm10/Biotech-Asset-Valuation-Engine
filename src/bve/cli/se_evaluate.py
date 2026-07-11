"""Evaluate an S&E run against a declared frozen/development reference landscape."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bve.se.evaluation.benchmark import evaluate_reference_landscape
from bve.se.pipeline import SESearchResult


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bve-se-evaluate",
        description="Evaluate retrieval, citation, and UNKNOWN routing against a declared reference set.",
    )
    parser.add_argument("--benchmark", required=True, help="Reference landscape YAML")
    parser.add_argument("--result", required=True, help="bve-se-search JSON result")
    parser.add_argument("--reference-set", default="validation")
    parser.add_argument("--output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = SESearchResult.model_validate_json(Path(args.result).read_text())
    report = evaluate_reference_landscape(
        Path(args.benchmark), result, reference_set=args.reference_set
    )
    rendered = json.dumps(report.model_dump(mode="json"), indent=2)
    if args.output:
        Path(args.output).write_text(rendered + "\n")
    else:
        sys.stdout.write(rendered + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
