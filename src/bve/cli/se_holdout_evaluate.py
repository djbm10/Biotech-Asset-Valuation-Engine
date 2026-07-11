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
    load_holdout_cases,
    predict_holdout,
    predictions_json,
    validate_predictions,
)
from bve.se.schemas.contracts import BuyerProblemV2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bve-se-holdout-evaluate",
        description="Produce one label-free disposition prediction per holdout case.",
    )
    parser.add_argument("--problem", required=True, help="BuyerProblem v2 YAML")
    parser.add_argument("--holdout-data", required=True, help="Unlabeled holdout JSONL")
    parser.add_argument("--output", help="Write predictions JSON to this path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    problem = BuyerProblemV2.model_validate(yaml.safe_load(Path(args.problem).read_text()))
    holdout_path = Path(args.holdout_data)
    cases = load_holdout_cases(holdout_path)
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
