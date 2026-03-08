"""
CLI entry point: bve-rank

Ranks watchlist assets by composite opportunity score.

Usage
-----
    bve-rank --watchlist examples/configs/watchlist.yaml
    bve-rank --watchlist watchlist.yaml --top 5 --format table
    bve-rank --watchlist watchlist.yaml --since 7d --format json --output rankings.json

``--since`` accepts durations: Nd (days), Nh (hours), Nw (weeks).
  Example: --since 7d  filters to diffs from the last 7 days.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from bve.intelligence.ranking import AssetRankingEngine, RankingConfig, RankingResult
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.pipeline.watchlist_runner import load_watchlist_config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rank watchlist assets by composite opportunity score"
    )
    parser.add_argument("--watchlist", required=True, help="Path to watchlist YAML")
    parser.add_argument(
        "--top", type=int, default=None, help="Number of top opportunities to show"
    )
    parser.add_argument(
        "--format", choices=["table", "json"], default="table", help="Output format"
    )
    parser.add_argument(
        "--output", default=None, help="Write output to file instead of stdout"
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Only consider diffs from last N days/hours/weeks (e.g. 7d, 24h, 2w)",
    )
    parser.add_argument(
        "--no-market-cap",
        action="store_true",
        help="Disable market-cap normalization (use delta-only scoring)",
    )
    return parser


def _parse_since(since_str: str) -> timedelta:
    """Parse '7d', '2w', '24h' into a timedelta."""
    s = since_str.strip().lower()
    if not s:
        raise ValueError("Empty --since value")
    unit = s[-1]
    try:
        value = int(s[:-1])
    except ValueError:
        raise ValueError(f"Invalid --since value: {since_str!r}")
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
    col_widths = [4, 20, 20, 8, 12, 8, 16, 10, 9]
    header = (
        f"{'Rank':<{col_widths[0]}}  "
        f"{'Asset':<{col_widths[1]}}  "
        f"{'Company':<{col_widths[2]}}  "
        f"{'Score':>{col_widths[3]}}  "
        f"{'DeltaNPV($M)':>{col_widths[4]}}  "
        f"{'Conf':>{col_widths[5]}}  "
        f"{'EventType':<{col_widths[6]}}  "
        f"{'Mispricing':>{col_widths[7]}}  "
        f"{'PoS Gap':>{col_widths[8]}}"
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
        misprice = (
            f"{opp.mispricing_score * 100:+.0f}%"
            if opp.mispricing_score is not None
            else "n/a"
        )
        pos_gap_str = (
            f"{opp.pos_gap:+.2f}"
            if opp.pos_gap is not None
            else "n/a"
        )
        delta_sign = "+" if opp.delta_npv_millions >= 0 else ""
        lines.append(
            f"{opp.rank:<{col_widths[0]}}  "
            f"{opp.asset_id:<{col_widths[1]}}  "
            f"{opp.company_id:<{col_widths[2]}}  "
            f"{opp.composite_score:>{col_widths[3]}.4f}  "
            f"{delta_sign}{opp.delta_npv_millions:>{col_widths[4] - 1}.1f}  "
            f"{opp.extraction_confidence:>{col_widths[5]}.2f}  "
            f"{(opp.signal_event_type or 'unknown'):<{col_widths[6]}}  "
            f"{misprice:>{col_widths[7]}}  "
            f"{pos_gap_str:>{col_widths[8]}}"
        )
    lines.append(separator)
    # Explanation block
    lines.append("\nTop opportunity explanation:")
    lines.append(f"  {result.opportunities[0].explanation}")
    return "\n".join(lines)


def main() -> None:
    args = _build_parser().parse_args()
    config = load_watchlist_config(args.watchlist)

    # Build RankingConfig from watchlist config + CLI overrides.
    ranking_cfg_dict: dict = {}
    if hasattr(config, "ranking") and config.ranking is not None:
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
            delta = _parse_since(args.since)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        since = datetime.now(timezone.utc) - delta

    knowledge = KnowledgeStore(config.knowledge_db_path)
    try:
        engine = AssetRankingEngine(ranking_cfg, knowledge_store=knowledge)
        result = engine.rank_from_watchlist_config(config, since=since)
    finally:
        knowledge.close()

    if args.format == "json":
        output = result.model_dump_json(indent=2)
    else:
        output = _format_table(result)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"Rankings written to {out_path}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
