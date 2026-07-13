"""Production CLI for the live public-data S&E acquisition-to-asset pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from bve.se.acquisition.policy import LiveSourcePolicy
from bve.se.live_run import LiveRunMode, SELivePipelineError, run_live_pipeline
from bve.se.release import LiveReleaseManifest
from bve.se.schemas.contracts import BuyerProblemV2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bve-se-run",
        description=(
            "Run fail-closed public-data acquisition, canonical asset discovery, gates, "
            "monitoring, audit, and immutable artifact promotion."
        ),
    )
    parser.add_argument("--problem", required=True, type=Path)
    parser.add_argument("--source-policy", required=True, type=Path)
    parser.add_argument("--output-root", default="outputs/se/production", type=Path)
    parser.add_argument("--repo-root", default=Path.cwd(), type=Path)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--live", action="store_true")
    modes.add_argument("--replay", type=Path, metavar="CORPUS_DIR")
    modes.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--release-manifest",
        type=Path,
        help=(
            "Required custody manifest for live and dry-run modes; verified before "
            "network access. Forbidden in replay mode."
        ),
    )
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        help=(
            "Logical acquisition date (live and dry-run modes only; live defaults to today)."
        ),
    )
    parser.add_argument("--run-id", help="Optional immutable run identifier")
    return parser


def _load_yaml(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        problem = BuyerProblemV2.model_validate(_load_yaml(args.problem))
        policy = LiveSourcePolicy.model_validate(_load_yaml(args.source_policy))
        release = (
            LiveReleaseManifest.model_validate(_load_yaml(args.release_manifest))
            if args.release_manifest
            else None
        )
        mode = (
            LiveRunMode.LIVE
            if args.live
            else LiveRunMode.REPLAY
            if args.replay
            else LiveRunMode.DRY_RUN
        )
        outcome = run_live_pipeline(
            problem,
            policy,
            mode=mode,
            output_root=args.output_root,
            repo_root=args.repo_root,
            release=release,
            replay_corpus=args.replay,
            as_of_date=args.as_of,
            run_id=args.run_id,
        )
    except SELivePipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.exit_code
    except Exception as exc:  # configuration/schema boundary
        print(f"ERROR: invalid S&E run configuration: {exc}", file=sys.stderr)
        return 2

    sys.stdout.write(
        json.dumps(
            {
                "run_id": outcome.receipt.run_id,
                "status": outcome.status,
                "run_dir": str(outcome.run_dir),
                "reused": outcome.reused,
                "execution_key": outcome.receipt.execution_key,
            },
            indent=2,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
