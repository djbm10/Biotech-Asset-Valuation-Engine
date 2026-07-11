"""CLI for generic source acquisition and corpus-coverage measurement.

Acquisition is generic (target/modality only). Coverage is measured separately against the
benchmark reference universe; asset names never re-enter the acquisition queries.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from bve.se.acquisition.runner import run_acquisition
from bve.se.evaluation.corpus_coverage import (
    attribute_required_evidence,
    evaluate_corpus_coverage,
)
from bve.se.evaluation.holdout import predict_holdout, predictions_json
from bve.se.schemas.contracts import BuyerProblemV2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bve-se-acquire",
        description="Populate and measure a generic public-evidence corpus for one BuyerProblem v2.",
    )
    parser.add_argument("--problem", required=True, help="BuyerProblem v2 YAML")
    parser.add_argument("--corpus-dir", required=True, help="Corpus store root directory")
    parser.add_argument(
        "--acquire",
        action="store_true",
        help="Run live connectors into the corpus (omit to only measure an existing corpus)",
    )
    parser.add_argument(
        "--reference-universe",
        help="Benchmark reference universe CSV for coverage measurement (evaluation only)",
    )
    parser.add_argument(
        "--source-index-out",
        help="Optional path to export a discovery --source-index YAML from the corpus",
    )
    parser.add_argument(
        "--declared-source-manifest",
        help="Versioned source-location URL manifest for company/conference disclosures",
    )
    parser.add_argument("--output", help="Write the JSON report to this path")
    parser.add_argument(
        "--holdout-data",
        help="Unlabeled case-level holdout JSONL; emits one disposition prediction per case",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    problem = BuyerProblemV2.model_validate(yaml.safe_load(Path(args.problem).read_text()))
    corpus_dir = Path(args.corpus_dir)

    report: dict[str, object] = {"corpus_dir": str(corpus_dir)}
    health = None
    if args.acquire:
        health = run_acquisition(
            problem,
            corpus_dir,
            declared_source_manifest=(
                Path(args.declared_source_manifest) if args.declared_source_manifest else None
            ),
        )

    if args.reference_universe:
        coverage = evaluate_corpus_coverage(corpus_dir, Path(args.reference_universe))
        if health is not None:
            health = attribute_required_evidence(coverage, health)
        report["coverage"] = {
            "gold": f"{coverage.gold_covered}/{coverage.gold_total}",
            "silver": f"{coverage.silver_covered}/{coverage.silver_total}",
            "total": f"{coverage.total_covered}/{coverage.total_assets}",
            "meets_release_thresholds": coverage.meets_release_thresholds(),
            "assets": [a.model_dump(mode="json") for a in coverage.assets],
        }

    if health is not None:
        report["source_health"] = {
            "stage_summary": health.stage_summary(),
            "sources": [s.model_dump(mode="json") for s in health.sources],
        }

    if args.source_index_out:
        from bve.se.acquisition.corpus_store import CorpusStore

        CorpusStore(corpus_dir).export_source_index(Path(args.source_index_out))
        report["source_index_out"] = args.source_index_out

    if args.holdout_data:
        predictions = predict_holdout(Path(args.holdout_data))
        report["predictions"] = predictions_json(predictions)
        report["prediction_count"] = len(predictions)

    rendered = json.dumps(report, indent=2)
    if args.output:
        Path(args.output).write_text(rendered + "\n")
    else:
        sys.stdout.write(rendered + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
