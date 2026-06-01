"""CLI entry point: bve-ma-calibrate — fit logistic calibration from historical cases.

Loads research/mna/historical_calibration_cases.yaml (196 labeled observations:
73 positives + 123 negatives), computes a composite rank_score proxy for each
case, fits Platt-scaling calibration (slope + midpoint), saves the result to
src/bve/config/ma_calibration_params.json, and prints a calibration report.

After running this command the UserWarning about "no fitted calibration params"
will stop appearing in bve-ma-grade and Layer 5 output.

Usage::

    bve-ma-calibrate
    bve-ma-calibrate --cases research/mna/historical_calibration_cases.yaml
    bve-ma-calibrate --out src/bve/config/ma_calibration_params.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_cases_path() -> Path:
    return _repo_root() / "research" / "mna" / "historical_calibration_cases.yaml"


def _default_out_path() -> Path:
    return _repo_root() / "src" / "bve" / "config" / "ma_calibration_params.json"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fit M&A logistic calibration from historical labeled cases"
    )
    parser.add_argument(
        "--cases",
        default=None,
        help="Path to historical_calibration_cases.yaml (default: research/mna/...)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Destination for calibration params JSON (default: src/bve/config/...)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print calibration report but do not write the JSON file",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    cases_path = Path(args.cases) if args.cases else _default_cases_path()
    out_path = Path(args.out) if args.out else _default_out_path()

    if not cases_path.exists():
        print(
            f"ERROR: Calibration cases YAML not found at {cases_path}.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        from bve.intelligence.ma_backtest import (
            build_backtest_records_from_calibration_cases,
            fit_logistic_calibration,
            run_backtest,
            save_calibration_params,
        )
    except ImportError as exc:
        print(f"ERROR: import failed — {exc}", file=sys.stderr)
        sys.exit(1)

    records = build_backtest_records_from_calibration_cases(cases_path)
    n = len(records)
    n_pos = sum(r.label for r in records)
    n_neg = n - n_pos

    print()
    print("=" * 65)
    print("  BVE M&A Logistic Calibration Fitter")
    print("=" * 65)
    print(f"  Cases file  : {cases_path}")
    print(f"  Records     : {n} ({n_pos} positive / {n_neg} negative)")
    print(f"  Base rate   : {n_pos / n:.1%}")
    print()

    # Run raw-score backtest before calibration
    raw_result = run_backtest(records, training_window=None)
    print(f"  Raw score AUC     : {raw_result.auc:.4f}" if raw_result.auc is not None else "  Raw score AUC: n/a")
    print(f"  Raw score Brier   : {raw_result.brier_score:.4f}")
    sep = raw_result.score_separation
    print(f"  Score separation  : {sep:+.4f}" if sep is not None else "  Score separation: n/a")
    if raw_result.mean_acquired_score is not None:
        print(f"  Mean score (pos)  : {raw_result.mean_acquired_score:.4f}")
    if raw_result.mean_non_acquired_score is not None:
        print(f"  Mean score (neg)  : {raw_result.mean_non_acquired_score:.4f}")
    print()

    # Fit calibration
    try:
        params = fit_logistic_calibration(records)
    except ValueError as exc:
        print(f"ERROR: Calibration fitting failed — {exc}", file=sys.stderr)
        sys.exit(1)

    print("  Fitted calibration parameters:")
    print(f"    slope     = {params.slope:.6f}")
    print(f"    midpoint  = {params.midpoint:.6f}")
    print(f"    AUC       = {params.auc:.4f}" if params.auc is not None else "    AUC: n/a")
    print(f"    Brier     = {params.brier_score:.4f}")
    print(f"    Window    : {params.training_window or 'n/a'}")
    print()

    if args.dry_run:
        print("  (dry-run — params NOT saved)")
        print()
        return

    saved_path = save_calibration_params(params, out_path)
    print(f"  Saved to: {saved_path}")
    print()
    print("  Run 'bve-ma-grade' to grade logged M&A predictions using the")
    print("  new calibration parameters.")
    print()


if __name__ == "__main__":
    main()
