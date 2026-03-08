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

from bve.pipeline.watchlist_runner import WatchlistPipelineRunner, load_watchlist_config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run automated watchlist pipeline")
    parser.add_argument(
        "--watchlist",
        required=True,
        help="Path to watchlist YAML config",
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


def main() -> None:
    args = _build_parser().parse_args()
    _configure_logging(args.verbose)

    config = load_watchlist_config(args.watchlist)
    if args.polling_interval_seconds is not None:
        config = config.model_copy(
            update={"polling_interval_seconds": args.polling_interval_seconds}
        )

    alert_router = None
    if config.alerts is not None and config.alerts.enabled:
        from bve.alerts.alert_router import AlertRouter
        alert_router = AlertRouter.from_config(config.alerts)

    runner = WatchlistPipelineRunner(config, alert_router=alert_router)
    try:
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
