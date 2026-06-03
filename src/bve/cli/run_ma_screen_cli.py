"""
bve-run-ma-screen — run the weekly M&A screen from enriched profiles.

Loads target/acquirer profile JSON files, runs WeeklyMAScreen, and writes
screen_result.json to the output path.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-run-ma-screen",
        description="Run the weekly M&A screen from enriched profile JSON files.",
    )
    parser.add_argument(
        "--target-profiles",
        default="outputs/profiles/target_profiles.json",
    )
    parser.add_argument(
        "--acquirer-profiles",
        default="outputs/profiles/acquirer_profiles.json",
    )
    parser.add_argument(
        "--ledger",
        default="outputs/intelligence/evidence_ledger.jsonl",
    )
    parser.add_argument("--as-of",      default=None)
    parser.add_argument("--score-mode", default="provisional",
                        choices=["approved_only", "provisional", "all_auto",
                                 "structural", "evidence_backed"])
    parser.add_argument("--output",     default="outputs/screen/screen_result.json")
    parser.add_argument("--min-coverage", type=float, default=0.20)
    parser.add_argument("--dry-run",    action="store_true")
    args = parser.parse_args(argv)

    targets_path = Path(args.target_profiles)
    acquirers_path = Path(args.acquirer_profiles)
    ledger_path = Path(args.ledger)
    output_path = Path(args.output)

    for label, p in [("target-profiles", targets_path),
                     ("acquirer-profiles", acquirers_path)]:
        if not p.exists():
            print(f"ERROR: {label} file not found: {p}", file=sys.stderr)
            return 1

    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()

    from bve.cli._serde import (
        acquirer_profiles_from_json,
        screen_result_to_json,
        target_profiles_from_json,
    )
    from bve.ingestion.evidence_ledger import EvidenceLedger
    from bve.ingestion.review_gate import ScoreMode
    from bve.intelligence.weekly_ma_screen import WeeklyMAScreen

    target_profiles = target_profiles_from_json(targets_path.read_text(encoding="utf-8"))
    acquirer_profiles = acquirer_profiles_from_json(acquirers_path.read_text(encoding="utf-8"))

    ledger = EvidenceLedger(path=ledger_path) if ledger_path.exists() else EvidenceLedger(path=ledger_path)

    score_mode = ScoreMode(args.score_mode)
    screen = WeeklyMAScreen()
    result = screen.run(
        as_of_date=as_of,
        targets=list(target_profiles.values()),
        acquirers=list(acquirer_profiles.values()),
        ledger=ledger,
        score_mode=score_mode,
        min_coverage=args.min_coverage,
    )

    ranked = result.ranked_targets
    print(f"As-of date:              {as_of}")
    print(f"Score mode:              {result.score_mode}")
    print(f"Targets screened:        {result.diagnostics.get('n_targets_screened', '?')}")
    print(f"Ranked targets:          {len(ranked)}")
    print(f"Suppressed targets:      {len(result.suppressed_targets)}")
    print(f"Acquirer pairs scored:   {result.diagnostics.get('n_pair_scores', '?')}")
    if ranked:
        top = ranked[0]
        print(f"Top target:              {top.ticker} ({top.ma_probability:.1%})")

    if args.dry_run:
        print("Dry run successful. No files written.")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(screen_result_to_json(result), encoding="utf-8")
    print(f"Screen result written to: {output_path}")
    return 0
