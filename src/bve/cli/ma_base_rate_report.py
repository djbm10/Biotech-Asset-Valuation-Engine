"""CLI: bve-ma-base-rate-report — M&A base-rate calibration report.

Computes a base-rate adjusted calibration report from the typed M&A backtest
dataset and displays it as Markdown or JSON.

Usage
-----
    bve-ma-base-rate-report
    bve-ma-base-rate-report --dataset expanded
    bve-ma-base-rate-report --dataset core
    bve-ma-base-rate-report --json
    bve-ma-base-rate-report --output outputs/ma_base_rate_report.md

Notes
-----
* "expanded" (default): 20 positives + 100+ typed negatives (MA_EXPANDED_DATASET).
* "core": the original 40-record panel (MA_BACKTEST_DATASET, 20+20).
* Bankruptcy/liquidation cases are always excluded from the base_rate denominator
  regardless of dataset choice.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="bve-ma-base-rate-report",
        description=(
            "Generate a base-rate adjusted M&A calibration report with typed "
            "negative set breakdown."
        ),
    )
    parser.add_argument(
        "--dataset",
        choices=["expanded", "core"],
        default="expanded",
        help="Dataset to use: 'expanded' (default, 100+ negatives) or 'core' (N=40).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="emit_json",
        help="Emit JSON instead of Markdown.",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="PATH",
        help="Write output to PATH (default: stdout).",
    )
    args = parser.parse_args(argv)

    from bve.analysis.ma_backtest import MA_BACKTEST_DATASET, MA_EXPANDED_DATASET
    from bve.analysis.ma_base_rate_report import compute_base_rate_report, render_markdown

    dataset = MA_EXPANDED_DATASET if args.dataset == "expanded" else MA_BACKTEST_DATASET
    version = f"{args.dataset}_v1"
    report = compute_base_rate_report(dataset, dataset_version=version)

    if args.emit_json:
        payload = {
            "dataset_version": report.dataset_version,
            "n_positives": report.n_positives,
            "n_negatives_total": report.n_negatives_total,
            "n_by_negative_type": report.n_by_negative_type,
            "overall": _segment_to_dict(report.overall),
            "by_therapeutic_area": {
                k: _segment_to_dict(v) for k, v in report.by_therapeutic_area.items()
            },
            "by_stage": {
                k: _segment_to_dict(v) for k, v in report.by_stage.items()
            },
            "by_cap_bucket": {
                k: _segment_to_dict(v) for k, v in report.by_cap_bucket.items()
            },
            "bankruptcy_exclusion_note": report.bankruptcy_exclusion_note,
            "model_implied_overstatement_warning": report.model_implied_overstatement_warning,
            "warnings": report.warnings,
        }
        output = json.dumps(payload, indent=2)
    else:
        output = render_markdown(report)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"[bve-ma-base-rate-report] Written to {args.output}", file=sys.stderr)
    else:
        print(output)

    return 0


def _segment_to_dict(seg) -> dict:
    return {
        "segment_key": seg.segment_key,
        "n_total": seg.n_total,
        "n_positive": seg.n_positive,
        "n_calibration_negatives": seg.n_calibration_negatives,
        "n_by_negative_type": seg.n_by_negative_type,
        "base_rate": seg.base_rate,
        "base_rate_strict": seg.base_rate_strict,
        "ci_lower": seg.ci_lower,
        "ci_upper": seg.ci_upper,
        "calibration_warning": seg.calibration_warning,
    }


if __name__ == "__main__":
    raise SystemExit(main())
