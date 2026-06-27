"""
CLI entry point for running the watchlist pipeline.

Usage
-----
    bve-watchlist-run --watchlist examples/configs/watchlist.yaml
    bve-watchlist-run --watchlist watchlist.yaml --forever
    bve-watchlist-run --watchlist watchlist.yaml --forever --max-cycles 3
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from bve.pipeline.history_replay import HistoryReplayRunner
from bve.pipeline.watchlist_runner import WatchlistPipelineRunner, load_watchlist_config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run automated watchlist pipeline")
    parser.add_argument(
        "watchlist_path",
        nargs="?",
        help="Positional watchlist YAML path (backward-compatible shorthand)",
    )
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "--watchlist",
        help="Path to watchlist YAML config",
    )
    group.add_argument(
        "--watchlist-dir",
        help="Path to directory of watchlist_*.yaml files",
    )
    parser.add_argument(
        "--forever",
        action="store_true",
        help="Run continuously using polling_interval_seconds from config",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="Maximum cycles when --forever is enabled",
    )
    parser.add_argument(
        "--polling-interval-seconds",
        type=int,
        default=None,
        help="Optional override for config polling_interval_seconds",
    )
    parser.add_argument(
        "--summary-json",
        default=None,
        help="Optional path to write one-cycle summary JSON",
    )
    parser.add_argument(
        "--science-thesis",
        action="store_true",
        help="Add read-only Science Thesis fields to watchlist summaries",
    )
    parser.add_argument(
        "--buyer-problem",
        help="Path to buyer problem YAML config; requires --science-thesis",
    )
    parser.add_argument(
        "--buyer-problem-id",
        help="Problem ID to select from buyer problem config",
    )
    parser.add_argument(
        "--reprocess-documents",
        action="store_true",
        help="Replay stored raw_documents through extraction, mapping, and valuation",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Replay only documents from the last N hours/days/weeks (e.g. 24h, 7d, 2w)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )



def _load_selected_buyer_problem(path: str | None, problem_id: str | None):
    if not path:
        return None
    from bve.intelligence.buyer_problem_library import BuyerProblemLibrary

    try:
        library = BuyerProblemLibrary.from_yaml(path)
    except Exception as exc:
        raise SystemExit(f"ERROR: Failed to load buyer problem config: {exc}") from exc
    problems = library.problems
    if not problems:
        raise SystemExit("ERROR: Buyer problem config contains no problems")
    if problem_id is None:
        if len(problems) > 1:
            raise SystemExit("ERROR: --buyer-problem-id required when config has multiple problems")
        return problems[0]
    for problem in problems:
        if getattr(problem, "problem_id", None) == problem_id:
            return problem
    raise SystemExit(f"ERROR: buyer problem id not found: {problem_id}")

def main() -> None:
    args = _build_parser().parse_args()
    _configure_logging(args.verbose)

    provided = [
        bool(args.watchlist_path),
        bool(args.watchlist),
        bool(args.watchlist_dir),
    ]
    if sum(provided) != 1:
        raise SystemExit(
            "Provide exactly one watchlist input: positional path, --watchlist, or --watchlist-dir"
        )

    if args.buyer_problem and not args.science_thesis:
        raise SystemExit("ERROR: --buyer-problem requires --science-thesis")
    if args.buyer_problem_id and not args.buyer_problem:
        raise SystemExit("ERROR: --buyer-problem-id requires --buyer-problem")

    watchlist_input = args.watchlist_dir or args.watchlist or args.watchlist_path
    config = load_watchlist_config(watchlist_input)
    if args.polling_interval_seconds is not None:
        config = config.model_copy(
            update={"polling_interval_seconds": args.polling_interval_seconds}
        )

    if args.reprocess_documents and args.forever:
        raise SystemExit("--reprocess-documents cannot be combined with --forever")

    alert_router = None
    if not args.reprocess_documents and config.alerts is not None and config.alerts.enabled:
        from bve.alerts.alert_router import AlertRouter
        alert_router = AlertRouter.from_config(config.alerts)

    buyer_problem = _load_selected_buyer_problem(args.buyer_problem, args.buyer_problem_id)

    if args.reprocess_documents:
        if args.science_thesis:
            raise SystemExit("ERROR: --science-thesis is not supported with --reprocess-documents")
        runner = HistoryReplayRunner(config)
    else:
        runner = WatchlistPipelineRunner(
            config,
            alert_router=alert_router,
            enable_science_thesis=args.science_thesis,
            buyer_problem=buyer_problem,
            buyer_problem_id=args.buyer_problem_id,
        )
    try:
        if args.reprocess_documents:
            summary = runner.replay(since=args.since)
            failures = sum(1 for asset in summary.assets if asset.status == "failure")
            print(
                f"history replay completed: assets={len(summary.assets)} "
                f"failures={failures} documents={summary.documents_replayed} "
                f"signals={summary.structured_signals_persisted} "
                f"diffs={summary.valuation_diffs_persisted} memos={summary.memos_persisted}"
            )
            for asset in summary.assets:
                print(
                    f"{asset.company_id}/{asset.asset_id}\tstatus={asset.status}\t"
                    f"docs={asset.documents_fetched}\tprocessed={asset.documents_processed}\t"
                    f"signals={asset.signals_created}\tdiffs={asset.valuation_diffs_persisted}\t"
                    f"memo={asset.memo_generated}"
                )
            if args.summary_json:
                out_path = Path(args.summary_json)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
            return

        if args.forever:
            runner.run_forever(max_cycles=args.max_cycles)
            return

        summary = runner.run_once()
        failures = sum(1 for asset in summary.assets if asset.status == "failure")
        print(
            f"watchlist run completed: assets={len(summary.assets)} "
            f"failures={failures} started_at={summary.started_at.isoformat()} "
            f"finished_at={summary.finished_at.isoformat()}"
        )
        for asset in summary.assets:
            print(
                f"{asset.company_id}/{asset.asset_id}\tstatus={asset.status}\t"
                f"fetched={asset.documents_fetched}\tprocessed={asset.documents_processed}\t"
                f"events={asset.events_created}\tdiffs={asset.valuation_diffs_persisted}\t"
                f"memo={asset.memo_generated}"
            )

        if args.summary_json:
            out_path = Path(args.summary_json)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    finally:
        runner.close()


if __name__ == "__main__":
    main()
