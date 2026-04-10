"""CLI entry point: bve-screen."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.mispricing_screener import (
    MispricingScreenConfig,
    MispricingScreenResult,
    UnifiedMispricingScreener,
)
from bve.pipeline.watchlist_runner import load_watchlist_config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rank watchlist assets with a unified mispricing screen"
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
        help="Screen as of YYYY-MM-DD (default: today)",
    )
    parser.add_argument("--top", type=int, default=25, help="Number of rows to show")
    parser.add_argument(
        "--days-ahead",
        type=int,
        default=180,
        help="Catalyst look-ahead window in days",
    )
    parser.add_argument(
        "--output-format",
        choices=["report", "json"],
        default="report",
        help="Output format",
    )
    parser.add_argument(
        "--use-stored-screen-snapshots",
        action="store_true",
        help="Prefer the latest stored screen_snapshot on or before --as-of",
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
    return f"{value:+.1f}%"


def _fmt_pos_gap(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:+.1f}pp"


def _fmt_ratio(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}x"


def _fmt_stage(value: Optional[str]) -> str:
    if value is None:
        return "n/a"
    return value


def _fmt_catalyst(row) -> str:
    if row.catalyst_type is None:
        return "n/a"
    return row.catalyst_type


def _format_report(result: MispricingScreenResult) -> str:
    if not result.rows:
        return f"No screen rows found for {result.as_of_date.isoformat()}."

    widths = [4, 18, 8, 7, 11, 8, 9, 8, 8, 24, 4]
    header = (
        f"{'Rank':<{widths[0]}}  "
        f"{'Asset':<{widths[1]}}  "
        f"{'Ticker':<{widths[2]}}  "
        f"{'Score':>{widths[3]}}  "
        f"{'Misprc':>{widths[4]}}  "
        f"{'Disc':>{widths[5]}}  "
        f"{'Stage':<{widths[6]}}  "
        f"{'ModelPoS':>{widths[7]}}  "
        f"{'PoSGap':>{widths[8]}}  "
        f"{'NextCatalyst':<{widths[9]}}  "
        f"{'Days':>{widths[10]}}"
    )
    separator = "-" * len(header)
    lines = [
        f"Unified mispricing screen date: {result.as_of_date.isoformat()}",
        (
            f"Source mode: {result.source_mode} | "
            f"Reference snapshot: "
            f"{result.reference_snapshot_date.isoformat() if result.reference_snapshot_date else 'n/a'}"
        ),
        f"Score version: {result.score_version} | "
        f"Assets: {result.n_assets} | "
        f"With ranking: {result.n_with_ranking} | "
        f"With acquisition discount: {result.n_with_acquisition_discount} | "
        f"With catalyst: {result.n_with_catalyst} | "
        f"Excluded company gate: {result.n_excluded_company_gate}",
        separator,
        header,
        separator,
    ]
    for row in result.rows:
        model_pos = f"{row.model_pos * 100:.1f}%" if row.model_pos is not None else "n/a"
        lines.append(
            f"{row.rank:<{widths[0]}}  "
            f"{row.asset_id:<{widths[1]}}  "
            f"{(row.ticker or 'n/a'):<{widths[2]}}  "
            f"{row.unified_score:>{widths[3]}.3f}  "
            f"{_fmt_pct(row.mispricing_pct):>{widths[4]}}  "
            f"{_fmt_ratio(row.acquisition_discount):>{widths[5]}}  "
            f"{_fmt_stage(row.stage):<{widths[6]}}  "
            f"{model_pos:>{widths[7]}}  "
            f"{_fmt_pos_gap(row.pos_gap):>{widths[8]}}  "
            f"{_fmt_catalyst(row):<{widths[9]}}  "
            f"{(row.days_to_catalyst if row.days_to_catalyst is not None else 'n/a'):>{widths[10]}}"
        )
        lines.append(
            "      "
            f"rNPV={row.rnpv_millions if row.rnpv_millions is not None else 'n/a'}  "
            f"EV={row.enterprise_value_millions if row.enterprise_value_millions is not None else 'n/a'}  "
            f"implied_pos={f'{row.implied_pos * 100:.1f}%' if row.implied_pos is not None else 'n/a'}  "
            f"modifier={row.catalyst_modifier:.3f}"
        )
        if row.company_action_policy is not None:
            lines.append(
                "      "
                f"company_action={row.company_action_policy}  "
                f"company_snapshot={row.company_snapshot_date.isoformat() if row.company_snapshot_date is not None else 'n/a'}  "
                f"company_reason={row.company_action_reason or 'n/a'}"
            )
        if row.data_notes:
            lines.append(f"      notes: {', '.join(row.data_notes)}")
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
        screened_at = (
            datetime.combine(as_of, datetime.min.time(), tzinfo=timezone.utc)
            if as_of is not None
            else None
        )
        result = UnifiedMispricingScreener(
            knowledge_store=knowledge,
            config=MispricingScreenConfig(
                top_n=args.top,
                catalyst_days_ahead=args.days_ahead,
                prefer_stored_screen_snapshots=args.use_stored_screen_snapshots,
            ),
        ).screen_from_watchlist_config(
            config,
            screened_at=screened_at,
        )
    finally:
        knowledge.close()

    output = (
        result.model_dump_json(indent=2)
        if args.output_format == "json"
        else _format_report(result)
    )
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"Unified screen written to {out_path}", file=sys.stderr)
        return
    print(output)


if __name__ == "__main__":
    main()
