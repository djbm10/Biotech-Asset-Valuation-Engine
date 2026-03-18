"""CLI entry point: bve-replay-documents."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from bve.pipeline.history_replay import HistoryReplayRunner
from bve.pipeline.watchlist_runner import load_watchlist_config


def _default_watchlist_input() -> str | None:
    candidates = (
        Path("examples/configs/watchlists/watchlist_stage1.yaml"),
        Path("examples/configs/watchlist.yaml"),
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay stored raw documents through extraction, mapping, and valuation"
    )
    parser.add_argument(
        "--watchlist",
        default=None,
        help="Path to watchlist YAML config (defaults to stage1 example when present)",
    )
    parser.add_argument(
        "--watchlist-dir",
        default=None,
        help="Directory containing watchlist_*.yaml files",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Optional knowledge DB override (defaults to the watchlist config value)",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Replay only documents stored in the last N hours/days/weeks (e.g. 24h, 7d, 2w)",
    )
    parser.add_argument(
        "--backend",
        choices=["anthropic", "openai", "fake"],
        default=None,
        help="Optional extraction backend override",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional extraction model override",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )


def _resolve_watchlist_input(args: argparse.Namespace) -> str:
    provided = [bool(args.watchlist), bool(args.watchlist_dir)]
    if sum(provided) > 1:
        raise SystemExit("Provide at most one of --watchlist or --watchlist-dir")

    if args.watchlist_dir:
        return args.watchlist_dir
    if args.watchlist:
        return args.watchlist

    default_watchlist = _default_watchlist_input()
    if default_watchlist is None:
        raise SystemExit("No default watchlist found; provide --watchlist or --watchlist-dir")
    return default_watchlist


def main() -> None:
    args = _build_parser().parse_args()
    _configure_logging(args.verbose)

    cfg = load_watchlist_config(_resolve_watchlist_input(args))
    if args.db is not None:
        cfg = cfg.model_copy(update={"knowledge_db_path": args.db})
    if args.backend is not None or args.model is not None:
        extraction = cfg.extraction.model_copy(
            update={
                "backend": args.backend or cfg.extraction.backend,
                "model": args.model if args.model is not None else cfg.extraction.model,
            }
        )
        cfg = cfg.model_copy(update={"extraction": extraction})

    runner = HistoryReplayRunner(cfg)
    try:
        summary = runner.replay(since=args.since)
    finally:
        runner.close()

    failures = sum(1 for asset in summary.assets if asset.status == "failure")
    print(
        f"history replay completed: assets={len(summary.assets)} failures={failures} "
        f"documents={summary.documents_replayed} signals={summary.structured_signals_persisted} "
        f"diffs={summary.valuation_diffs_persisted} memos={summary.memos_persisted}"
    )
    for asset in summary.assets:
        print(
            f"{asset.company_id}/{asset.asset_id}\tstatus={asset.status}\t"
            f"docs={asset.documents_fetched}\tprocessed={asset.documents_processed}\t"
            f"signals={asset.signals_created}\tdiffs={asset.valuation_diffs_persisted}\t"
            f"memo={asset.memo_generated}"
        )


if __name__ == "__main__":
    main()
