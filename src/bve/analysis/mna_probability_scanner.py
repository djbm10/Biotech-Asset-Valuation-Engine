"""Utility CLI for evaluating historical M&A scanner label datasets."""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import median

from bve.intelligence.ma_calibration import (
    MACalibrationDataset,
    MACalibrationMetrics,
    MACalibrationRow,
)


def _normalize_row(raw: dict[str, str]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in raw.items():
        normalized[key] = None if value == "" else value
    return normalized


def _load_dataset(path: str | Path, *, lookahead_days: int = 365) -> MACalibrationDataset:
    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [
            MACalibrationRow.model_validate(_normalize_row(row))
            for row in reader
        ]

    if not rows:
        raise ValueError(f"No rows found in historical dataset: {csv_path}")

    dataset_mode = (
        "canonical_predeal"
        if any(row.match_group_id for row in rows)
        else "historical_snapshot"
    )
    positive_targets = {row.ticker for row in rows if row.label == 1}
    snapshot_dates = sorted({row.snapshot_date for row in rows})
    return MACalibrationDataset(
        start_date=snapshot_dates[0] if snapshot_dates else None,
        end_date=snapshot_dates[-1] if snapshot_dates else None,
        lookahead_days=lookahead_days,
        n_rows=len(rows),
        n_positive_rows=sum(1 for row in rows if row.label == 1),
        n_control_rows=sum(1 for row in rows if row.label == 0),
        n_unique_targets=len(positive_targets),
        dataset_mode=dataset_mode,
        rows=rows,
    )


def _evaluate(dataset: MACalibrationDataset, *, top_k: int = 15) -> MACalibrationMetrics:
    positive_targets = {row.ticker for row in dataset.rows if row.label == 1}
    positive_probabilities = [row.probability for row in dataset.rows if row.label == 1]
    control_probabilities = [row.probability for row in dataset.rows if row.label == 0]
    n_snapshot_dates = len({row.snapshot_date for row in dataset.rows})

    if dataset.dataset_mode == "canonical_predeal":
        top_rows = sorted(
            dataset.rows,
            key=lambda row: (-row.probability, row.rank, row.snapshot_date, row.ticker),
        )[:top_k]
        top_total = len(top_rows)
        top_hits = sum(1 for row in top_rows if row.label == 1)
        captured_targets = {row.ticker for row in top_rows if row.label == 1}
        best_lead_days = {
            row.ticker: row.days_to_announcement
            for row in top_rows
            if row.label == 1 and row.days_to_announcement is not None
        }
    else:
        rows_by_date: dict[date, list[MACalibrationRow]] = defaultdict(list)
        for row in dataset.rows:
            rows_by_date[row.snapshot_date].append(row)

        top_hits = 0
        top_total = 0
        captured_targets: set[str] = set()
        best_lead_days: dict[str, int] = {}
        for snapshot_date in sorted(rows_by_date):
            ranked = sorted(
                rows_by_date[snapshot_date],
                key=lambda row: (-row.probability, row.rank, row.ticker),
            )
            top_rows = ranked[:top_k]
            top_total += len(top_rows)
            top_hits += sum(1 for row in top_rows if row.label == 1)
            for row in top_rows:
                if row.label != 1 or row.days_to_announcement is None:
                    continue
                captured_targets.add(row.ticker)
                best_lead_days[row.ticker] = max(
                    best_lead_days.get(row.ticker, row.days_to_announcement),
                    row.days_to_announcement,
                )

    return MACalibrationMetrics(
        lookahead_days=dataset.lookahead_days,
        top_k=top_k,
        n_rows=dataset.n_rows,
        n_snapshot_dates=n_snapshot_dates,
        n_positive_rows=dataset.n_positive_rows,
        n_positive_targets=len(positive_targets),
        n_positive_targets_in_top_k=len(captured_targets),
        precision_at_k=round(top_hits / top_total, 6) if top_total > 0 else None,
        unique_target_recall_at_k=(
            round(len(captured_targets) / len(positive_targets), 6)
            if positive_targets
            else None
        ),
        median_lead_days_at_k=(
            float(median(best_lead_days.values()))
            if best_lead_days
            else None
        ),
        average_probability_positive=(
            round(sum(positive_probabilities) / len(positive_probabilities), 6)
            if positive_probabilities
            else None
        ),
        average_probability_control=(
            round(sum(control_probabilities) / len(control_probabilities), 6)
            if control_probabilities
            else None
        ),
    )


def _render_report(path: str | Path, metrics: MACalibrationMetrics) -> str:
    return "\n".join(
        [
            "M&A probability scanner evaluation",
            f"  Dataset: {Path(path)}",
            f"  Rows: {metrics.n_rows}",
            f"  Snapshot dates: {metrics.n_snapshot_dates}",
            f"  Positive rows: {metrics.n_positive_rows}",
            f"  Positive targets: {metrics.n_positive_targets}",
            f"  Precision@{metrics.top_k}: {metrics.precision_at_k}",
            f"  Recall@{metrics.top_k}: {metrics.unique_target_recall_at_k}",
            f"  Median lead days@{metrics.top_k}: {metrics.median_lead_days_at_k}",
            f"  Avg probability (positive): {metrics.average_probability_positive}",
            f"  Avg probability (control): {metrics.average_probability_control}",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate historical M&A scanner datasets")
    subparsers = parser.add_subparsers(dest="command", required=True)

    evaluate = subparsers.add_parser("evaluate", help="Evaluate one historical label CSV")
    evaluate.add_argument("--historical-dataset", required=True, help="Path to historical label CSV")
    evaluate.add_argument("--top-k", type=int, default=15)
    evaluate.add_argument("--lookahead-days", type=int, default=365)
    evaluate.add_argument("--output-format", choices=["report", "json"], default="report")

    args = parser.parse_args()
    if args.command != "evaluate":
        raise ValueError(f"Unsupported command: {args.command}")

    dataset = _load_dataset(args.historical_dataset, lookahead_days=args.lookahead_days)
    metrics = _evaluate(dataset, top_k=args.top_k)
    if args.output_format == "json":
        print(json.dumps(metrics.model_dump(mode="json"), indent=2))
        return
    print(_render_report(args.historical_dataset, metrics))


if __name__ == "__main__":
    main()
