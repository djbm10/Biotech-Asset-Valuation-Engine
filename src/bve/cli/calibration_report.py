"""
CLI entry point: bve-calibration-report

Reads resolved forecast_records from KnowledgeStore and prints calibration
metrics: directional accuracy, magnitude RMSE, Spearman correlation,
confidence calibration bins, and false positive rate.

Usage
-----
    bve-calibration-report --db outputs/intelligence_phase2/knowledge.db
    bve-calibration-report --db knowledge.db --min-resolved 10
"""
from __future__ import annotations

import argparse
import sys

from bve.intelligence.forecast_tracker import CalibrationReporter
from bve.intelligence.knowledge_layer import KnowledgeStore


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Print model calibration metrics from resolved forecast records"
    )
    p.add_argument(
        "--db",
        default="outputs/intelligence_phase2/knowledge.db",
        help="Path to KnowledgeStore SQLite database",
    )
    p.add_argument(
        "--min-resolved",
        type=int,
        default=5,
        help="Minimum resolved forecasts required to print metrics (default: 5)",
    )
    return p


def _print_report(report) -> None:
    sep = "-" * 60
    print(sep)
    print("  CALIBRATION REPORT")
    print(sep)
    print(f"  Total forecasts   : {report.n_total}")
    coverage_str = f"{report.coverage:.1%}" if report.coverage is not None else "n/a"
    print(f"  Resolved          : {report.n_resolved}  (coverage: {coverage_str})")

    if report.directional_accuracy is not None:
        print(f"  Directional acc.  : {report.directional_accuracy:.1%}")
    else:
        print("  Directional acc.  : n/a")

    if report.magnitude_rmse is not None:
        print(f"  Magnitude RMSE    : {report.magnitude_rmse:.2f}pp")
    else:
        print("  Magnitude RMSE    : n/a  (no paired predictions)")

    if report.spearman_correlation is not None:
        print(
            f"  Spearman ρ        : {report.spearman_correlation:+.3f}"
            f"  (p={report.spearman_p_value:.3f})"
        )
    else:
        print("  Spearman ρ        : n/a  (need ≥3 paired predictions or scipy)")

    if report.false_positive_rate is not None:
        print(f"  False positive rt : {report.false_positive_rate:.1%}  (pred=up, actual<0)")
    else:
        print("  False positive rt : n/a")

    print(sep)
    print("  Confidence calibration (by extraction_confidence decile):")
    print(f"  {'Bin':<15}  {'N':>5}  {'Dir. Acc':>8}")
    print(f"  {'-'*15}  {'-----':>5}  {'--------':>8}")
    for b in report.confidence_bins:
        if b.n_forecasts == 0:
            continue
        acc_str = f"{b.directional_accuracy:.1%}" if b.directional_accuracy is not None else "n/a"
        bin_label = f"[{b.bin_low:.1f}, {b.bin_high:.1f})"
        print(f"  {bin_label:<15}  {b.n_forecasts:>5}  {acc_str:>8}")
    print(sep)
    print(f"  Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M UTC')}")
    print(sep)


def main() -> None:
    args = _build_parser().parse_args()
    store = KnowledgeStore(db_path=args.db)
    try:
        reporter = CalibrationReporter()
        report = reporter.report(store)
    finally:
        store.close()

    if report.n_resolved < args.min_resolved:
        print(
            f"Only {report.n_resolved} resolved forecast(s) "
            f"(need ≥ {args.min_resolved}). Run more event resolutions first."
        )
        sys.exit(0)

    _print_report(report)


if __name__ == "__main__":
    main()
