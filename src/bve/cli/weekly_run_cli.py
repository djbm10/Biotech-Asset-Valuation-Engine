"""
bve-weekly-run — full weekly M&A screen pipeline.

Orchestrates:
  1. Load universe (targets + acquirers + overrides)
  2. Enrich profiles (ProfileEnricher)
  3. Run M&A screen (WeeklyMAScreen)
  4. Write report files (WeeklyReportGenerator)
  5. Write screen_result.json

Output dir receives all seven files:
  screen_result.json
  ranked_targets.csv
  top_acquirer_pairs.csv
  suppressed_targets.csv
  score_changes.csv
  audit_report.md
  validation_snapshot.json

Usage::

    bve-weekly-run \\
      --targets research/universe/targets.yaml \\
      --acquirers research/universe/acquirers.yaml \\
      --overrides research/universe/manual_overrides.yaml \\
      --ledger outputs/intelligence/evidence_ledger.jsonl \\
      --as-of 2026-06-01 \\
      --score-mode provisional \\
      --output outputs/weekly/2026-06-01 \\
      --dry-run
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional


def main(
    argv: list[str] | None = None,
    _sec_fetcher: Optional[Callable[[str], dict[str, Any]]] = None,
    _ledger_score_fetcher: Optional[Callable[[str], dict[str, float]]] = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-weekly-run",
        description="Full weekly M&A screen pipeline: enrich → screen → report.",
    )
    parser.add_argument("--targets",    default="research/universe/targets.yaml")
    parser.add_argument("--acquirers",  default="research/universe/acquirers.yaml")
    parser.add_argument("--overrides",  default="research/universe/manual_overrides.yaml")
    parser.add_argument("--ledger",     default="outputs/intelligence/evidence_ledger.jsonl")
    parser.add_argument("--as-of",      default=None)
    parser.add_argument("--score-mode", default="provisional",
                        choices=["approved_only", "provisional", "all_auto"])
    parser.add_argument("--output",     default=None)
    parser.add_argument("--prev-output", default=None,
                        help="Previous run output dir (for score change diff)")
    parser.add_argument("--min-coverage", type=float, default=0.20)
    parser.add_argument("--dry-run",    action="store_true")
    args = parser.parse_args(argv)

    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    output_dir = Path(args.output) if args.output else Path("outputs/weekly") / as_of.isoformat()

    targets_path = Path(args.targets)
    acquirers_path = Path(args.acquirers)
    overrides_path = Path(args.overrides)
    ledger_path = Path(args.ledger)

    for label, p in [("targets", targets_path), ("acquirers", acquirers_path)]:
        if not p.exists():
            print(f"ERROR: {label} file not found: {p}", file=sys.stderr)
            return 1

    # ── Step 1: Load universe ──────────────────────────────────────────────
    from bve.ingestion.universe_loader import (
        load_acquirers,
        load_manual_overrides,
        load_targets,
        validate_universe,
    )

    targets = load_targets(targets_path)
    acquirers = load_acquirers(acquirers_path)
    overrides = load_manual_overrides(overrides_path) if overrides_path.exists() else {}

    validation = validate_universe(targets, acquirers)
    if not validation.valid:
        print("ERROR: Universe validation failed:", file=sys.stderr)
        for err in validation.errors:
            print(f"  [{err.ticker}] {err.field}: {err.message}", file=sys.stderr)
        return 1

    # ── Step 2: Enrich profiles ────────────────────────────────────────────
    from bve.ingestion.profile_enricher import ProfileEnricher

    if _ledger_score_fetcher is None and ledger_path.exists():
        from bve.ingestion.evidence_ledger import EvidenceLedger as _EL
        _el = _EL(path=ledger_path)
        _ledger_score_fetcher = _el.compute_score_state

    if _ledger_score_fetcher is None:
        def _ledger_score_fetcher(ticker: str) -> dict[str, float]:  # type: ignore[misc]
            return {}

    if _sec_fetcher is None:
        def _sec_fetcher(ticker: str) -> dict[str, Any]:  # type: ignore[misc]
            return {}

    enricher = ProfileEnricher(
        targets,
        acquirers,
        overrides,
        sec_fetcher=_sec_fetcher,
        ledger_score_fetcher=_ledger_score_fetcher,
    )
    target_profiles = enricher.enrich_targets()
    acquirer_profiles = enricher.enrich_acquirers()

    # ── Step 3: Run screen ─────────────────────────────────────────────────
    from bve.ingestion.evidence_ledger import EvidenceLedger
    from bve.ingestion.review_gate import ScoreMode
    from bve.intelligence.weekly_ma_screen import WeeklyMAScreen

    ledger = EvidenceLedger(path=ledger_path)
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

    # ── Load previous result for diff ─────────────────────────────────────
    prev_result = None
    if args.prev_output:
        prev_screen_path = Path(args.prev_output) / "screen_result.json"
        if prev_screen_path.exists():
            from bve.cli._serde import screen_result_from_json
            try:
                prev_result = screen_result_from_json(
                    prev_screen_path.read_text(encoding="utf-8")
                )
            except Exception as exc:
                print(f"WARNING: could not load prev result: {exc}", file=sys.stderr)

    # ── Summary ───────────────────────────────────────────────────────────
    ranked = result.ranked_targets
    print(f"As-of date:              {as_of}")
    print(f"Score mode:              {result.score_mode}")
    print(f"Targets loaded:          {len(targets)}")
    print(f"Acquirers loaded:        {len(acquirers)}")
    print(f"Targets ranked:          {len(ranked)}")
    print(f"Targets suppressed:      {len(result.suppressed_targets)}")
    print(f"Acquirer pairs scored:   {result.diagnostics.get('n_pair_scores', '?')}")
    if ranked:
        top = ranked[0]
        print(f"Top target:              {top.ticker} ({top.ma_probability:.1%})")

    if args.dry_run:
        print("Dry run successful. No files written.")
        return 0

    # ── Step 4: Write outputs ─────────────────────────────────────────────
    output_dir.mkdir(parents=True, exist_ok=True)

    from bve.cli._serde import screen_result_to_json
    from bve.reporting.weekly_report import WeeklyReportGenerator

    screen_result_path = output_dir / "screen_result.json"
    screen_result_path.write_text(screen_result_to_json(result), encoding="utf-8")

    gen = WeeklyReportGenerator()
    report_paths = gen.write_outputs(result, output_dir, prev_result=prev_result)

    print(f"Output written to:       {output_dir}")
    all_paths = [screen_result_path] + report_paths
    for p in all_paths:
        print(f"  {p.name}")
    return 0
