"""
bve-write-report — write weekly report files from a screen result JSON.

Loads a WeeklyMAScreenResult from JSON and writes:
  ranked_targets.csv
  top_acquirer_pairs.csv
  suppressed_targets.csv
  score_changes.csv
  audit_report.md
  validation_snapshot.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-write-report",
        description="Write weekly report files from a screen result JSON.",
    )
    parser.add_argument("--screen-result", required=True)
    parser.add_argument("--output",        required=True)
    parser.add_argument("--prev-result",   default=None)
    parser.add_argument("--dry-run",       action="store_true")
    args = parser.parse_args(argv)

    result_path = Path(args.screen_result)
    output_dir = Path(args.output)

    if not result_path.exists():
        print(f"ERROR: screen result file not found: {result_path}", file=sys.stderr)
        return 1

    prev_path = Path(args.prev_result) if args.prev_result else None
    if prev_path and not prev_path.exists():
        print(f"WARNING: prev-result not found, skipping diff: {prev_path}", file=sys.stderr)
        prev_path = None

    from bve.cli._serde import screen_result_from_json
    from bve.reporting.weekly_report import WeeklyReportGenerator

    result = screen_result_from_json(result_path.read_text(encoding="utf-8"))
    prev_result = (
        screen_result_from_json(prev_path.read_text(encoding="utf-8"))
        if prev_path else None
    )

    ranked = result.ranked_targets
    print(f"As-of date:              {result.as_of_date}")
    print(f"Ranked targets:          {len(ranked)}")
    print(f"Suppressed targets:      {len(result.suppressed_targets)}")
    print(f"Prev result available:   {'yes' if prev_result else 'no'}")
    if ranked:
        print(f"Top target:              {ranked[0].ticker} ({ranked[0].ma_probability:.1%})")

    if args.dry_run:
        print("Dry run successful. No files written.")
        return 0

    gen = WeeklyReportGenerator()
    paths = gen.write_outputs(result, output_dir, prev_result=prev_result)
    print(f"Report written to:       {output_dir}")
    print(f"Files written:           {len(paths)}")
    for p in paths:
        print(f"  {p.name}")
    return 0
