"""Service control-plane CLI.

Commands:
  bve-service start --watchlist watchlist.yaml
  bve-service stop
  bve-service pause-stage ingestion
  bve-service resume-stage ingestion
  bve-service replay-run --watchlist watchlist.yaml --run-id <id>
  bve-service inspect-asset --db <knowledge.db> --asset-id <asset>
"""
from __future__ import annotations

import argparse
import logging

from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.ops.control_plane import ServiceControlPlane
from bve.pipeline.watchlist_runner import WatchlistPipelineRunner, load_watchlist_config
from bve.services.pipeline_scheduler import PipelineScheduler, PipelineSchedulerConfig


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Control BVE intelligence service")
    p.add_argument(
        "--control-state-path",
        default="outputs/watchlist/service_control.json",
    )
    p.add_argument("--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Start service loop")
    start_group = start.add_mutually_exclusive_group(required=True)
    start_group.add_argument("--watchlist")
    start_group.add_argument("--watchlist-dir")
    start.add_argument("--dashboard-cache", default="outputs/dashboard/cache.json")
    start.add_argument("--lock-path", default="outputs/watchlist/intelligence_service.lock")
    start.add_argument("--metrics-path", default="logs/run_metrics.json")
    start.add_argument("--once", action="store_true")
    start.add_argument("--max-cycles", type=int, default=None)

    sub.add_parser("stop", help="Request graceful service stop")

    pause = sub.add_parser("pause-stage", help="Pause a stage")
    pause.add_argument("stage")

    resume = sub.add_parser("resume-stage", help="Resume a stage")
    resume.add_argument("stage")

    replay = sub.add_parser("replay-run", help="Replay assets from a prior run_id")
    replay_group = replay.add_mutually_exclusive_group(required=True)
    replay_group.add_argument("--watchlist")
    replay_group.add_argument("--watchlist-dir")
    replay.add_argument("--db", default="outputs/intelligence_phase2/knowledge.db")
    replay.add_argument("--run-id", required=True)

    inspect = sub.add_parser("inspect-asset", help="Inspect run_state timeline for asset")
    inspect.add_argument("--db", default="outputs/intelligence_phase2/knowledge.db")
    inspect.add_argument("--asset-id", required=True)
    inspect.add_argument("--run-id", default=None)
    inspect.add_argument("--limit", type=int, default=200)

    return p


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )


def _cmd_start(args) -> None:
    scheduler = PipelineScheduler(
        PipelineSchedulerConfig(
            watchlist_path=args.watchlist,
            watchlist_dir=args.watchlist_dir,
            dashboard_cache_path=args.dashboard_cache,
            control_state_path=args.control_state_path,
            metrics_path=args.metrics_path,
            scheduler={"lock_path": args.lock_path},
        )
    )
    try:
        # Ensure stale stop signal does not block startup.
        scheduler.service.control_plane.clear_stop()
        if args.once:
            scheduler.run_once()
        else:
            scheduler.run_forever(max_cycles=args.max_cycles)
    finally:
        scheduler.close()


def _cmd_stop(args) -> None:
    state = ServiceControlPlane(args.control_state_path).request_stop()
    print(
        f"stop_requested={state.stop_requested} updated_at={state.updated_at.isoformat()} "
        f"paused_stages={','.join(state.paused_stages) if state.paused_stages else 'none'}"
    )


def _cmd_pause_stage(args) -> None:
    cp = ServiceControlPlane(args.control_state_path)
    state = cp.pause_stage(args.stage)
    print(f"paused_stages={','.join(state.paused_stages)}")


def _cmd_resume_stage(args) -> None:
    cp = ServiceControlPlane(args.control_state_path)
    state = cp.resume_stage(args.stage)
    print(
        f"paused_stages={','.join(state.paused_stages) if state.paused_stages else 'none'}"
    )


def _cmd_replay_run(args) -> None:
    cfg = load_watchlist_config(args.watchlist_dir or args.watchlist)
    store = KnowledgeStore(args.db)
    try:
        run_states = store.get_run_states(run_id=args.run_id, limit=5000)
    finally:
        store.close()

    replay_asset_ids = sorted({r.asset_id for r in run_states})
    if not replay_asset_ids:
        print(f"No run_state records found for run_id={args.run_id}")
        return

    replay_watchlist = [
        asset for asset in cfg.watchlist if asset.asset_id in set(replay_asset_ids)
    ]
    if not replay_watchlist:
        print(f"No watchlist assets matched run_state assets for run_id={args.run_id}")
        return

    replay_cfg = cfg.model_copy(update={"watchlist": replay_watchlist})
    runner = WatchlistPipelineRunner(replay_cfg)
    try:
        summary = runner.run_once()
    finally:
        runner.close()
    print(
        f"replay_complete original_run_id={args.run_id} "
        f"replay_run_id={summary.run_id} assets={len(summary.assets)}"
    )


def _cmd_inspect_asset(args) -> None:
    store = KnowledgeStore(args.db)
    try:
        rows = store.get_run_states(
            run_id=args.run_id,
            asset_id=args.asset_id,
            limit=args.limit,
        )
    finally:
        store.close()
    if not rows:
        print("No run_state rows found.")
        return
    for row in rows:
        finished = row.finished_at.isoformat() if row.finished_at else "n/a"
        print(
            f"{row.run_id}\t{row.asset_id}\t{row.stage}\t{row.status}\t"
            f"started={row.started_at.isoformat()}\tfinished={finished}\t"
            f"checkpoint={row.checkpoint_json}\terror={row.error_json}"
        )


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _configure_logging(args.verbose)

    if args.command == "start":
        _cmd_start(args)
    elif args.command == "stop":
        _cmd_stop(args)
    elif args.command == "pause-stage":
        _cmd_pause_stage(args)
    elif args.command == "resume-stage":
        _cmd_resume_stage(args)
    elif args.command == "replay-run":
        _cmd_replay_run(args)
    elif args.command == "inspect-asset":
        _cmd_inspect_asset(args)
    else:  # pragma: no cover
        parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
