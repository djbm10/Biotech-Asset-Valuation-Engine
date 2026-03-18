"""CLI entry point: bve-rank."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.ranking import AssetRankingEngine, RankingConfig, RankingResult
from bve.pipeline.watchlist_runner import load_watchlist_config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rank watchlist assets by opportunity score")
    parser.add_argument("--watchlist", required=True, help="Path to watchlist YAML")
    parser.add_argument("--top", type=int, default=None, help="Number of rows to show")
    parser.add_argument("--format", choices=["table", "json"], default="table")
    parser.add_argument("--output", default=None, help="Write output to file instead of stdout")
    parser.add_argument(
        "--since",
        default=None,
        help="Only consider diffs from the last N days/hours/weeks (for example 7d, 24h, 2w)",
    )
    parser.add_argument(
        "--no-market-cap",
        action="store_true",
        help="Disable market-cap normalization and fall back to delta-based valuation scoring",
    )
    return parser


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


def _parse_since(since_str: str) -> timedelta:
    s = since_str.strip().lower()
    if not s:
        raise ValueError("Empty --since value")
    unit = s[-1]
    try:
        value = int(s[:-1])
    except ValueError as exc:
        raise ValueError(f"Invalid --since value: {since_str!r}") from exc
    if unit == "d":
        return timedelta(days=value)
    if unit == "w":
        return timedelta(weeks=value)
    if unit == "h":
        return timedelta(hours=value)
    raise ValueError(f"Unknown time unit in --since: {since_str!r} (use d/h/w)")


def _format_table(result: RankingResult) -> str:
    if not result.opportunities:
        return (
            f"No ranked opportunities found "
            f"(assets_evaluated={result.assets_evaluated}, "
            f"assets_with_diffs={result.assets_with_diffs})."
        )

    widths = [4, 18, 18, 9, 11, 10, 6, 16]
    header = (
        f"{'Rank':<{widths[0]}}  "
        f"{'Asset':<{widths[1]}}  "
        f"{'Event':<{widths[2]}}  "
        f"{'Score':>{widths[3]}}  "
        f"{'Mispricing':>{widths[4]}}  "
        f"{'Conf':>{widths[5]}}  "
        f"{'Days':>{widths[6]}}  "
        f"{'EventType':<{widths[7]}}"
    )
    separator = "-" * len(header)
    lines = [
        f"Ranked at: {result.ranked_at.strftime('%Y-%m-%d %H:%M UTC')}",
        f"Assets evaluated: {result.assets_evaluated} | with diffs: {result.assets_with_diffs}",
        separator,
        header,
        separator,
    ]
    for opp in result.opportunities:
        mispricing = f"{(opp.mispricing or 0.0) * 100:+.1f}%" if opp.mispricing is not None else "n/a"
        lines.append(
            f"{opp.rank:<{widths[0]}}  "
            f"{opp.asset_id:<{widths[1]}}  "
            f"{opp.event_id:<{widths[2]}}  "
            f"{opp.score:>{widths[3]}.4f}  "
            f"{mispricing:>{widths[4]}}  "
            f"{opp.confidence:>{widths[5]}.2f}  "
            f"{opp.days_since_event:>{widths[6]}}  "
            f"{(opp.signal_event_type or 'unknown'):<{widths[7]}}"
        )
    lines.append(separator)
    lines.append("")
    lines.append(f"Top opportunity: {result.opportunities[0].explanation}")
    return "\n".join(lines)


def main() -> None:
    args = _build_parser().parse_args()
    watchlist_path = _resolve_watchlist_path(args.watchlist)
    config = load_watchlist_config(watchlist_path)

    ranking_cfg_dict: dict = {}
    if getattr(config, "ranking", None) is not None:
        raw = config.ranking
        if hasattr(raw, "model_dump"):
            ranking_cfg_dict = raw.model_dump()
        elif isinstance(raw, dict):
            ranking_cfg_dict = raw
    if args.top is not None:
        ranking_cfg_dict["top_n"] = args.top
    if args.no_market_cap:
        ranking_cfg_dict["use_market_cap_normalization"] = False
    ranking_cfg = RankingConfig(**ranking_cfg_dict)

    since: Optional[datetime] = None
    if args.since:
        try:
            since = datetime.now(timezone.utc) - _parse_since(args.since)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

    knowledge = KnowledgeStore(config.knowledge_db_path)
    try:
        result = AssetRankingEngine(ranking_cfg, knowledge_store=knowledge).rank_from_watchlist_config(
            config,
            since=since,
        )
    finally:
        knowledge.close()

    output = result.model_dump_json(indent=2) if args.format == "json" else _format_table(result)
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"Rankings written to {out_path}", file=sys.stderr)
        return
    print(output)


if __name__ == "__main__":
    main()
