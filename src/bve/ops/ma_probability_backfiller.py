"""Backfill dated M&A probability snapshots across a replay watchlist."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.ma_calibration import MACalibrationDatasetBuilder
from bve.intelligence.ma_probability import MAProbabilityConfig, MAProbabilityScanner
from bve.pipeline.watchlist_runner import load_watchlist_config


@dataclass(frozen=True)
class MABackfillSummary:
    watchlist_path: str
    knowledge_db_path: str
    dataset_mode: str
    snapshot_dates: int
    snapshot_start: date | None
    snapshot_end: date | None
    total_rows_written: int
    total_excluded_assets: int
    calibration_rows: int
    calibration_positive_rows: int
    calibration_positive_targets: int
    precision_at_k: float | None
    unique_target_recall_at_k: float | None
    median_lead_days_at_k: float | None
    dataset_csv_path: str
    metrics_json_path: str
    calibration_fit_path: str | None = None
    policy_comparison_json_path: str | None = None


def _parse_date(raw: str) -> date:
    return date.fromisoformat(raw.strip())


def _resolve_dates(
    store: KnowledgeStore,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[date]:
    dates = store.list_screen_snapshot_dates()
    if start_date is not None:
        dates = [item for item in dates if item >= start_date]
    if end_date is not None:
        dates = [item for item in dates if item <= end_date]
    return sorted(dates)


def _range_token(start_date: date | None, end_date: date | None) -> str:
    if start_date is None or end_date is None:
        return "unknown_range"
    return f"{start_date.isoformat()}_{end_date.isoformat()}"


def backfill_ma_probability_snapshots(
    *,
    watchlist_path: str | Path,
    knowledge_db_path: str | Path,
    start_date: date | None = None,
    end_date: date | None = None,
    score_version: str = "v1.2",
    dataset_mode: str = "canonical_predeal",
    anchor_days_before_announcement: int = 180,
    controls_per_positive: int = 2,
    profiles_file: str = "examples/research/acquirer_profiles",
    comps_file: str = "research/mna/comparable_deals.yaml",
    vulnerability_file: str = "research/mna/vulnerability_signals.yaml",
    deal_universe_path: str = "research/mna/deal_universe_2020_2026.yaml",
    readiness_filter: bool = True,
    top_k: int = 15,
    output_dir: str | Path = "outputs/analysis",
) -> MABackfillSummary:
    config = load_watchlist_config(watchlist_path)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    store = KnowledgeStore(knowledge_db_path)
    try:
        snapshot_dates = _resolve_dates(store, start_date=start_date, end_date=end_date)
        if not snapshot_dates:
            raise ValueError("No screen snapshot dates found for the requested range")

        scanner = MAProbabilityScanner(
            knowledge_store=store,
            config=MAProbabilityConfig(
                score_version=score_version,
                top_n=max(len(config.watchlist), top_k),
                persist_daily_snapshots=True,
                enable_monitor=False,
                use_stored_screen_context=True,
                vulnerability_signals_path=vulnerability_file,
                fit_integration_config={
                    "acquirer_profiles_path": profiles_file,
                    "comparable_deals_path": comps_file,
                    "top_n": max(len(config.watchlist), top_k),
                    "require_acquisition_readiness": readiness_filter,
                },
            ),
        )

        total_rows_written = 0
        total_excluded_assets = 0
        for snapshot_date in snapshot_dates:
            result = scanner.scan_from_watchlist_config(
                config,
                snapshot_date=snapshot_date,
                top_n=max(len(config.watchlist), top_k),
                run_id=f"ma-backfill:{snapshot_date.isoformat()}",
            )
            total_rows_written += result.snapshots_written
            total_excluded_assets += result.n_excluded

        builder = MACalibrationDatasetBuilder(
            knowledge_store=store,
            deal_universe_path=deal_universe_path,
        )
        if dataset_mode == "canonical_predeal":
            dataset = builder.build_canonical_dataset(
                lookahead_days=365,
                start_date=snapshot_dates[0],
                end_date=snapshot_dates[-1],
                anchor_days_before_announcement=anchor_days_before_announcement,
                controls_per_positive=controls_per_positive,
            )
        elif dataset_mode == "historical_snapshot":
            dataset = builder.build_dataset(
                lookahead_days=365,
                start_date=snapshot_dates[0],
                end_date=snapshot_dates[-1],
            )
        else:
            raise ValueError(f"Unsupported dataset_mode: {dataset_mode}")
        metrics = builder.evaluate(dataset, top_k=top_k)

        range_token = _range_token(snapshot_dates[0], snapshot_dates[-1])
        if dataset_mode == "canonical_predeal":
            range_token = (
                f"{range_token}_canonical_anchor{anchor_days_before_announcement}"
                f"_controls{controls_per_positive}"
            )
        else:
            range_token = f"{range_token}_historical_snapshot"
        dataset_csv = output_root / f"ma_calibration_dataset_{range_token}.csv"
        metrics_json = output_root / f"ma_calibration_metrics_{range_token}.json"
        dataset.write_csv(dataset_csv)
        metrics_json.write_text(
            json.dumps(metrics.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )

        # Fit logistic model and persist JSON for live scoring
        calibration_fit_path: str | None = None
        policy_comparison_json_path: str | None = None
        if dataset_mode == "canonical_predeal" and dataset.n_positive_rows >= 3:
            fit_result = builder.fit_logistic_model(dataset, top_k=top_k)
            fit_json = output_root / "ma_calibration_fit.json"
            fit_result.write_json(fit_json)
            calibration_fit_path = str(fit_json)
            # Evaluate three ranking policies against the fitted model
            policy_result = builder.compare_ranking_policies(
                dataset, fit_result, top_k=top_k
            )
            policy_json = output_root / f"ma_policy_comparison_{range_token}.json"
            policy_json.write_text(
                json.dumps(policy_result.model_dump(mode="json"), indent=2),
                encoding="utf-8",
            )
            policy_comparison_json_path = str(policy_json)

        return MABackfillSummary(
            watchlist_path=str(Path(watchlist_path)),
            knowledge_db_path=str(Path(knowledge_db_path)),
            dataset_mode=dataset_mode,
            snapshot_dates=len(snapshot_dates),
            snapshot_start=snapshot_dates[0],
            snapshot_end=snapshot_dates[-1],
            total_rows_written=total_rows_written,
            total_excluded_assets=total_excluded_assets,
            calibration_rows=dataset.n_rows,
            calibration_positive_rows=dataset.n_positive_rows,
            calibration_positive_targets=dataset.n_unique_targets,
            precision_at_k=metrics.precision_at_k,
            unique_target_recall_at_k=metrics.unique_target_recall_at_k,
            median_lead_days_at_k=metrics.median_lead_days_at_k,
            dataset_csv_path=str(dataset_csv),
            metrics_json_path=str(metrics_json),
            calibration_fit_path=calibration_fit_path,
            policy_comparison_json_path=policy_comparison_json_path,
        )
    finally:
        store.close()


def _render_summary(summary: MABackfillSummary) -> str:
    lines = [
        "M&A probability backfill complete",
        f"  Watchlist: {summary.watchlist_path}",
        f"  Knowledge DB: {summary.knowledge_db_path}",
        f"  Dataset mode: {summary.dataset_mode}",
        f"  Snapshot dates: {summary.snapshot_dates}",
        f"  Date range: {summary.snapshot_start} -> {summary.snapshot_end}",
        f"  Snapshot rows written: {summary.total_rows_written}",
        f"  Excluded assets: {summary.total_excluded_assets}",
        f"  Calibration rows: {summary.calibration_rows}",
        f"  Positive rows: {summary.calibration_positive_rows}",
        f"  Positive targets: {summary.calibration_positive_targets}",
        f"  Precision@15: {summary.precision_at_k}",
        f"  Recall@15: {summary.unique_target_recall_at_k}",
        f"  Median lead days@15: {summary.median_lead_days_at_k}",
        f"  Dataset CSV: {summary.dataset_csv_path}",
        f"  Metrics JSON: {summary.metrics_json_path}",
    ]
    if summary.calibration_fit_path:
        lines.append(f"  Calibration fit JSON: {summary.calibration_fit_path}")
    if summary.policy_comparison_json_path:
        lines.append(f"  Policy comparison JSON: {summary.policy_comparison_json_path}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historical M&A probability snapshots")
    parser.add_argument("--watchlist", required=True, help="Path to watchlist YAML")
    parser.add_argument("--db", required=True, help="KnowledgeStore SQLite path")
    parser.add_argument("--start", default=None, help="Optional YYYY-MM-DD start date")
    parser.add_argument("--end", default=None, help="Optional YYYY-MM-DD end date")
    parser.add_argument("--score-version", default="v1.2")
    parser.add_argument(
        "--dataset-mode",
        choices=["canonical_predeal", "historical_snapshot"],
        default="canonical_predeal",
    )
    parser.add_argument("--anchor-days-before-announcement", type=int, default=180)
    parser.add_argument("--controls-per-positive", type=int, default=2)
    parser.add_argument("--profiles-file", default="examples/research/acquirer_profiles")
    parser.add_argument("--comps-file", default="research/mna/comparable_deals.yaml")
    parser.add_argument("--vulnerability-file", default="research/mna/vulnerability_signals.yaml")
    parser.add_argument("--deal-universe", default="research/mna/deal_universe_2020_2026.yaml")
    parser.add_argument("--readiness-filter", choices=["strict", "off"], default="strict")
    parser.add_argument("--top-k", type=int, default=15)
    parser.add_argument("--output-dir", default="outputs/analysis")
    args = parser.parse_args()

    summary = backfill_ma_probability_snapshots(
        watchlist_path=args.watchlist,
        knowledge_db_path=args.db,
        start_date=_parse_date(args.start) if args.start else None,
        end_date=_parse_date(args.end) if args.end else None,
        score_version=args.score_version,
        dataset_mode=args.dataset_mode,
        anchor_days_before_announcement=args.anchor_days_before_announcement,
        controls_per_positive=args.controls_per_positive,
        profiles_file=args.profiles_file,
        comps_file=args.comps_file,
        vulnerability_file=args.vulnerability_file,
        deal_universe_path=args.deal_universe,
        readiness_filter=args.readiness_filter == "strict",
        top_k=args.top_k,
        output_dir=args.output_dir,
    )
    print(_render_summary(summary))


if __name__ == "__main__":
    main()
