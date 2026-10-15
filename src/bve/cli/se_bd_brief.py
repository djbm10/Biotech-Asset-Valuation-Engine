"""Render a BD screening brief (HTML + Markdown) from a finished S&E run directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

from bve.se.reporting.bd_brief import (
    DEFAULT_LIMIT,
    build_bd_brief,
    load_run,
    render_html,
    render_markdown,
    usefulness_checks,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bve-se-bd-brief",
        description="Compose a BD screening brief from an existing run's problem.yaml, shortlist.json "
        "and result.json. Reads only; changes no decision.",
    )
    parser.add_argument(
        "--run-dir", required=True, type=Path, help="Run directory written by bve-se-run"
    )
    parser.add_argument(
        "--context", type=Path, help="Optional analyst context YAML (question, rationale)"
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    return parser


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for name in ("problem.yaml", "shortlist.json"):
        if not (args.run_dir / name).exists():
            sys.stderr.write(f"not a run directory: {args.run_dir / name} is missing\n")
            return 2
    context = yaml.safe_load(args.context.read_text()) if args.context else {}
    inputs = {
        name: _sha(args.run_dir / name)
        for name in ("problem.yaml", "shortlist.json", "result.json")
        if (args.run_dir / name).exists()
    }
    if args.context:
        inputs[args.context.name] = _sha(args.context)
    brief = build_bd_brief(
        load_run(args.run_dir, limit=args.limit), context=context, limit=args.limit, inputs=inputs
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "brief.md").write_text(render_markdown(brief))
    (args.output_dir / "brief.html").write_text(render_html(brief))
    checks = usefulness_checks(brief)
    (args.output_dir / "checks.json").write_text(
        json.dumps(checks, indent=2, sort_keys=True) + "\n"
    )
    sys.stdout.write(
        f"wrote {args.output_dir / 'brief.html'} and brief.md; checks: "
        f"{sum(checks.values())}/{len(checks)} pass\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
