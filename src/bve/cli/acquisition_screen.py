"""CLI entry point: bve-acquisition-screen."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from bve.intelligence.acquisition_screen import (
    AcquisitionScreenConfig,
    AcquisitionScreenResult,
    AcquisitionScreener,
)
from bve.intelligence.comparable_deals import ComparableDealLoader
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.target_monitor import TargetMonitorDataset, TargetMonitorLoader
from bve.pipeline.watchlist_runner import load_watchlist_config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Screen watchlist assets for acquisition discount (rNPV / enterprise value)"
    )
    parser.add_argument("--watchlist", required=True, help="Path to watchlist YAML or directory")
    parser.add_argument(
        "--db",
        default=None,
        help="Override KnowledgeStore SQLite path (defaults to watchlist knowledge_db_path)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=1.5,
        help="Candidate threshold; assets above this acquisition discount are flagged",
    )
    parser.add_argument(
        "--as-of",
        default=None,
        help="Use price data on or before YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--with-comps",
        action="store_true",
        help="Enrich output with EV/peak-sales comparable-deal statistics",
    )
    parser.add_argument(
        "--readiness-filter",
        choices=["strict", "off"],
        default="strict",
        help="Apply the Phase 2 POC-or-later acquisition-readiness gate",
    )
    parser.add_argument(
        "--comps-file",
        default="research/mna/comparable_deals.yaml",
        help="Comparable deal YAML path used when --with-comps is set",
    )
    parser.add_argument(
        "--show-target-monitor",
        action="store_true",
        help="Append the current public-target monitor to the screen output",
    )
    parser.add_argument(
        "--targets-file",
        default="research/mna/target_monitor.yaml",
        help="Target monitor YAML path used when --show-target-monitor is set",
    )
    parser.add_argument("--format", choices=["table", "json"], default="table")
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


def _format_millions(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}"


def _format_ratio(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}x"


def _format_pct(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _format_decile_pct(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.0f}"


def _format_yes_no(value: Optional[bool]) -> str:
    if value is None:
        return "n/a"
    return "yes" if value else "no"


def _format_table(result: AcquisitionScreenResult) -> str:
    if not result.rows:
        return "No assets found in watchlist."

    show_comps = any(row.comps_match_tier is not None for row in result.rows)
    widths = [4, 18, 8, 10, 10, 8, 8, 9, 7, 5, 22, 28]
    header = (
        f"{'Rank':<{widths[0]}}  "
        f"{'Asset':<{widths[1]}}  "
        f"{'Ticker':<{widths[2]}}  "
        f"{'rNPV':>{widths[3]}}  "
        f"{'EV':>{widths[4]}}  "
        f"{'Disc':>{widths[5]}}  "
        f"{'PoS':>{widths[6]}}  "
        f"{'EV/Peak':>{widths[7]}}  "
        f"{'Comp %':>{widths[8]}}  "
        f"{'Ready':<{widths[9]}}  "
        f"{'MktCap Source':<{widths[10]}}  "
        f"{'Status':<{widths[11]}}"
    )
    separator = "-" * len(header)
    lines = [
        f"Acquisition screen date: {result.snapshot_date.isoformat()}",
        f"Threshold: > {result.threshold:.2f}x | "
        f"Candidates: {result.n_candidates}/{result.n_assets} | "
        f"Excluded: {result.n_excluded}",
        separator,
        header,
        separator,
    ]
    for idx, row in enumerate(result.rows, start=1):
        status = "candidate" if row.passes_threshold else (row.exclusion_reason or "below_threshold")
        lines.append(
            f"{idx:<{widths[0]}}  "
            f"{row.asset_id:<{widths[1]}}  "
            f"{(row.ticker or 'n/a'):<{widths[2]}}  "
            f"{_format_millions(row.model_rnpv_millions):>{widths[3]}}  "
            f"{_format_millions(row.enterprise_value_millions):>{widths[4]}}  "
            f"{_format_ratio(row.acquisition_discount):>{widths[5]}}  "
            f"{_format_pct(row.model_pos):>{widths[6]}}  "
            f"{_format_ratio(row.ev_to_peak_sales):>{widths[7]}}  "
            f"{_format_decile_pct(row.comps_percentile_vs_peers):>{widths[8]}}  "
            f"{_format_yes_no(row.acquisition_ready):<{widths[9]}}  "
            f"{(row.market_cap_source or 'n/a'):<{widths[10]}}  "
            f"{status:<{widths[11]}}"
        )
        if (
            row.acquisition_readiness_source not in (None, "asset_stage")
            or (row.acquisition_ready is False)
        ):
            lines.append(
                "      readiness: "
                f"bucket={row.acquisition_readiness_bucket or 'n/a'} "
                f"source={row.acquisition_readiness_source or 'n/a'} "
                f"design={row.acquisition_readiness_design_tier or 'n/a'} "
                f"low_power={_format_yes_no(row.acquisition_readiness_low_power)}"
            )
        if show_comps and row.comps_match_tier is not None:
            lines.append(
                f"      comps: tier={row.comps_match_tier} n={row.comps_n} "
                f"peer_median={_format_ratio(row.comps_peer_median_ev_to_peak_sales)}"
            )
    return "\n".join(lines)


def _format_target_monitor_table(dataset: TargetMonitorDataset) -> str:
    if not dataset.targets:
        return f"Target monitor as of {dataset.as_of_date.isoformat()}\nNo targets found."

    widths = [24, 8, 26, 18, 28]
    header = (
        f"{'Company':<{widths[0]}}  "
        f"{'Ticker':<{widths[1]}}  "
        f"{'Status':<{widths[2]}}  "
        f"{'Stage':<{widths[3]}}  "
        f"{'Therapeutic Area':<{widths[4]}}"
    )
    separator = "-" * len(header)
    lines = [
        f"Target monitor as of {dataset.as_of_date.isoformat()}",
        separator,
        header,
        separator,
    ]
    for entry in dataset.targets:
        lines.append(
            f"{entry.company_name:<{widths[0]}}  "
            f"{entry.ticker:<{widths[1]}}  "
            f"{entry.status:<{widths[2]}}  "
            f"{entry.stage:<{widths[3]}}  "
            f"{entry.therapeutic_area:<{widths[4]}}"
        )
        lines.append(f"      assets: {entry.lead_assets}")
        if entry.notes:
            lines.append(f"      notes: {entry.notes}")
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
    comparable_deals = None
    if args.with_comps:
        comparable_deals = ComparableDealLoader.load(args.comps_file).deals
    target_monitor = None
    if args.show_target_monitor:
        target_monitor = TargetMonitorLoader.load(args.targets_file)
    knowledge = KnowledgeStore(db_path)
    try:
        screener = AcquisitionScreener(
            AcquisitionScreenConfig(
                threshold=args.threshold,
                require_acquisition_readiness=(args.readiness_filter == "strict"),
            ),
            knowledge_store=knowledge,
        )
        result = screener.screen_watchlist(
            config.watchlist,
            snapshot_date=as_of,
            comparable_deals=comparable_deals,
        )
    finally:
        knowledge.close()

    if args.format == "json":
        payload: object = result.model_dump(mode="json")
        if target_monitor is not None:
            payload = {
                "screen": payload,
                "target_monitor": target_monitor.model_dump(mode="json"),
            }
        output = json.dumps(payload, indent=2)
    else:
        output = _format_table(result)
        if target_monitor is not None:
            output = f"{output}\n\n{_format_target_monitor_table(target_monitor)}"
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"Acquisition screen written to {out_path}", file=sys.stderr)
        return
    print(output)


if __name__ == "__main__":
    main()
