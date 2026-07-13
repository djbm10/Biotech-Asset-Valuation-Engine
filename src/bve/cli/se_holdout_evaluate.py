"""Single-shot case-level holdout evaluator.

This command accepts unlabeled holdout cases only. The independent custodian scores its sealed
prediction output after hashing it; labels are intentionally not an input to this process.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from bve.se.evaluation.holdout import (
    HoldoutProblem,
    load_holdout_cases,
    predict_holdout,
    predictions_json,
    validate_predictions,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bve-se-holdout-evaluate",
        description="Produce one label-free disposition prediction per holdout case.",
    )
    parser.add_argument("--problem", required=True, help="Holdout problem YAML")
    parser.add_argument("--holdout-data", required=True, help="Unlabeled holdout JSONL")
    parser.add_argument("--output", help="Write predictions JSON to this path")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the problem and unlabeled cases without running inference",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    problem = HoldoutProblem.model_validate(yaml.safe_load(Path(args.problem).read_text()))
    holdout_path = Path(args.holdout_data)
    cases = load_holdout_cases(holdout_path)
    if args.validate_only:
        report = {
            "problem_id": problem.problem_id,
            "validation_status": "PASS",
            "case_count": len(cases),
        }
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
        return 0
    predictions = validate_predictions(
        [case.case_id for case in cases], predict_holdout(holdout_path)
    )
    report = {
        "problem_id": problem.problem_id,
        "prediction_count": len(predictions),
        "predictions": predictions_json(predictions),
    }
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(rendered)
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
