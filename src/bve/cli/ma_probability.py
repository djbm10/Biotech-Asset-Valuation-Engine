"""CLI entry point: bve-ma-probability."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.ma_probability import (
    MAProbabilityConfig,
    MAProbabilityResult,
    MAProbabilityScanner,
)
from bve.pipeline.watchlist_runner import load_watchlist_config


def _default_calibration_model_path() -> str | None:
    repo_root = Path(__file__).resolve().parents[3]
    candidates = [
        repo_root / "outputs" / "analysis" / "ma_calibration_fit_post_step2.json",
        repo_root / "outputs" / "analysis" / "ma_calibration_fit.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rank watchlist assets by acquisition likelihood across all configured acquirers"
    )
    parser.add_argument("--watchlist", required=True, help="Path to watchlist YAML")
    parser.add_argument(
        "--db",
        default=None,
        help="Override KnowledgeStore SQLite path (defaults to watchlist knowledge_db_path)",
    )
    parser.add_argument(
        "--as-of",
        default=None,
        help="Score as of YYYY-MM-DD (default: today)",
    )
    parser.add_argument("--top", type=int, default=15, help="Number of ranked rows to show")
    parser.add_argument(
        "--alert-threshold",
        type=float,
        default=0.70,
        help="Threshold used for above-alert highlighting and emitted alert checks",
    )
    parser.add_argument(
        "--profiles-file",
        default="examples/research/acquirer_profiles",
        help="Acquirer profile YAML file or directory path",
    )
    parser.add_argument(
        "--comps-file",
        default="research/mna/comparable_deals.yaml",
        help="Comparable deal YAML path",
    )
    parser.add_argument(
        "--vulnerability-file",
        default="research/mna/vulnerability_signals.yaml",
        help="Vulnerability signal YAML path",
    )
    parser.add_argument(
        "--readiness-filter",
        choices=["strict", "off"],
        default="strict",
        help="Apply the Phase 2 POC-or-later acquisition-readiness gate",
    )
    parser.add_argument(
        "--emit-alerts",
        action="store_true",
        help="Persist daily snapshots and emit idempotent threshold/top-entry alerts",
    )
    parser.add_argument(
        "--calibration-model",
        default=_default_calibration_model_path(),
        help="Optional MALogisticFitResult JSON used for calibrated takeout probabilities",
    )
    parser.add_argument(
        "--calibration-policy",
        choices=["display_only", "threshold_filter", "tie_breaker"],
        default="threshold_filter",
        help="How calibrated probability should affect the live ranked output",
    )
    parser.add_argument(
        "--calibration-threshold",
        type=float,
        default=0.10,
        help="Threshold used by the threshold_filter calibration policy",
    )
    parser.add_argument(
        "--output-format",
        choices=["report", "json"],
        default="report",
        help="Output format",
    )
    parser.add_argument("--output", default=None, help="Write output to file instead of stdout")
    return parser


def _parse_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid --as-of value: {raw!r}; expected YYYY-MM-DD") from exc


def _resolve_watchlist_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.exists():
        return path

    repo_root = Path(__file__).resolve().parents[3]
    candidates = [
        repo_root / "examples" / "configs" / "watchlists" / raw_path,
        repo_root / "examples" / "configs" / "watchlists" / Path(raw_path).name,
        repo_root / "examples" / "configs" / raw_path,
        repo_root / "examples" / "configs" / Path(raw_path).name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return path


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _fmt_ratio(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}x"


def _fmt_millions(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    if value >= 1000:
        return f"${value / 1000.0:.1f}B"
    return f"${value:,.0f}M"


def _fmt_deal_range(row) -> str:
    low = getattr(row, "estimated_deal_value_low_millions", None)
    high = getattr(row, "estimated_deal_value_high_millions", None)
    if low is None or high is None:
        return "n/a"
    return f"{_fmt_millions(low)}-{_fmt_millions(high)}"


def _fmt_score(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def _fmt_text(value: Optional[str], *, fallback: str = "n/a") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _fmt_flags(row) -> str:
    flags: list[str] = []
    if row.above_alert_threshold:
        flags.append("alert")
    flags.extend(row.hard_fail_reasons)
    return ",".join(flags) if flags else "none"


def _format_report(result: MAProbabilityResult) -> str:
    if not result.rows:
        return f"No M&A probability rows found for {result.as_of_date.isoformat()}."

    widths = [4, 18, 8, 8, 8, 14, 17, 8, 8, 8, 10, 18]
    header = (
        f"{'Rank':<{widths[0]}}  "
        f"{'Asset':<{widths[1]}}  "
        f"{'Ticker':<{widths[2]}}  "
        f"{'M&A':>{widths[3]}}  "
        f"{'Cal':>{widths[4]}}  "
        f"{'Acquirer':<{widths[5]}}  "
        f"{'Deal Range':<{widths[6]}}  "
        f"{'Disc':>{widths[7]}}  "
        f"{'Fit':>{widths[8]}}  "
        f"{'D-Risk':>{widths[9]}}  "
        f"{'CapV':>{widths[10]}}  "
        f"{'Flags':<{widths[11]}}"
    )
    separator = "-" * len(header)
    threshold_pct = int(round(result.alert_threshold * 100))
    lines = [
        f"WEEKLY M&A TARGETING SCAN — {result.as_of_date.isoformat()}",
        f"Score version: {result.score_version} | "
        f"Assets: {result.n_assets} | "
        f"Ranked: {result.n_ranked} | "
        f"Above {threshold_pct}%: {result.n_above_alert_threshold} | "
        f"Snapshots written: {result.snapshots_written} | "
        f"Alerts emitted: {len(result.alerts_emitted)}",
    ]
    if result.calibration_threshold is not None:
        lines.append(
            f"Calibration: {result.calibration_policy} | "
            f"Threshold: {result.calibration_threshold:.2f}"
        )
    if result.reference_snapshot_date is not None:
        lines.append(
            f"Reference snapshot: {result.reference_snapshot_date} | "
            f"Duplicate alerts suppressed: {result.alerts_suppressed_as_duplicate}"
        )
    lines.extend([separator, header, separator])
    for row in result.rows:
        lines.append(
            f"{row.rank:<{widths[0]}}  "
            f"{row.asset_id:<{widths[1]}}  "
            f"{_fmt_text(row.ticker):<{widths[2]}}  "
            f"{_fmt_pct(row.mna_probability_score):>{widths[3]}}  "
            f"{_fmt_pct(row.p_takeout_calibrated):>{widths[4]}}  "
            f"{row.best_acquirer_id:<{widths[5]}}  "
            f"{_fmt_deal_range(row):<{widths[6]}}  "
            f"{_fmt_ratio(row.acquisition_discount):>{widths[7]}}  "
            f"{_fmt_score(row.strategic_fit_score):>{widths[8]}}  "
            f"{_fmt_score(row.de_risking_stage_score):>{widths[9]}}  "
            f"{_fmt_score(row.capital_vulnerability_score):>{widths[10]}}  "
            f"{_fmt_flags(row):<{widths[11]}}"
        )
        lines.append(
            "      "
            f"runner_up={_fmt_text(row.runner_up_acquirer_id)}  "
            f"fit={row.best_acquirer_fit_score:.3f}  "
            f"source={_fmt_text(row.estimated_deal_value_source)}  "
            f"runway={_fmt_text(row.cash_runway_risk_level)}  "
            f"signals={','.join(row.target_signal_ids + row.external_deal_signal_ids) or 'none'}  "
            f"explanation={row.explanation}"
        )
    return "\n".join(lines)


def main() -> None:
    args = _build_parser().parse_args()
    watchlist_path = _resolve_watchlist_path(args.watchlist)
    config = load_watchlist_config(watchlist_path)

    as_of: Optional[date] = None
    if args.as_of:
        try:
            as_of = _parse_date(args.as_of)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1)

    db_path = args.db or config.knowledge_db_path
    knowledge = KnowledgeStore(db_path)
    try:
        result = MAProbabilityScanner(
            knowledge_store=knowledge,
            config=MAProbabilityConfig(
                top_n=args.top,
                alert_threshold=args.alert_threshold,
                vulnerability_signals_path=args.vulnerability_file,
                persist_daily_snapshots=args.emit_alerts,
                enable_monitor=args.emit_alerts,
                calibration_model_path=args.calibration_model,
                calibration_policy=args.calibration_policy,
                calibration_threshold=args.calibration_threshold,
                fit_integration_config={
                    "acquirer_profiles_path": args.profiles_file,
                    "comparable_deals_path": args.comps_file,
                    "top_n": args.top,
                    "require_acquisition_readiness": args.readiness_filter == "strict",
                },
            ),
        ).scan_from_watchlist_config(
            config,
            snapshot_date=as_of,
            top_n=args.top,
        )
    finally:
        knowledge.close()

    output = (
        json.dumps(result.model_dump(mode="json"), indent=2)
        if args.output_format == "json"
        else _format_report(result)
    )
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"M&A probability report written to {out_path}", file=sys.stderr)
        return
    print(output)


if __name__ == "__main__":
    main()
