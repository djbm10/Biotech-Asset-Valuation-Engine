"""
bve-ingest-live — run live ingestion pipeline (SEC 8-K + CT.gov + FDA).

Loads the universe, enriches profiles, fetches real events for the lookback
window, classifies them, and appends novel events to the evidence ledger.
Also writes new_events.csv to the output directory.

Usage::

    bve-ingest-live \\
      --targets research/universe/targets.yaml \\
      --acquirers research/universe/acquirers.yaml \\
      --ledger outputs/intelligence/evidence_ledger.jsonl \\
      --lookback-days 14 \\
      --output outputs/weekly/2026-06-02 \\
      --dry-run
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Callable, Optional


def main(
    argv: list[str] | None = None,
    _sec_source: Optional[Callable] = None,
    _ctgov_source: Optional[Callable] = None,
    _fda_source: Optional[Callable] = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-ingest-live",
        description="Run live ingestion: SEC 8-K + CT.gov + FDA → evidence ledger.",
    )
    parser.add_argument("--targets",       default="research/universe/targets.yaml")
    parser.add_argument("--acquirers",     default="research/universe/acquirers.yaml")
    parser.add_argument("--overrides",     default="research/universe/manual_overrides.yaml")
    parser.add_argument("--ledger",        default="outputs/intelligence/evidence_ledger.jsonl")
    parser.add_argument("--lookback-days", type=int, default=14)
    parser.add_argument("--as-of",         default=None)
    parser.add_argument("--output",        default=None)
    parser.add_argument("--dry-run",       action="store_true")
    args = parser.parse_args(argv)

    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    output_dir = (
        Path(args.output)
        if args.output
        else Path("outputs/weekly") / as_of.isoformat()
    )

    targets_path  = Path(args.targets)
    acquirers_path = Path(args.acquirers)
    overrides_path = Path(args.overrides)
    ledger_path    = Path(args.ledger)

    for label, p in [("targets", targets_path), ("acquirers", acquirers_path)]:
        if not p.exists():
            print(f"ERROR: {label} file not found: {p}", file=sys.stderr)
            return 1

    # ── Step 1: Load + validate universe ──────────────────────────────────
    from bve.ingestion.universe_loader import (
        load_acquirers,
        load_manual_overrides,
        load_targets,
        validate_universe,
    )

    targets_raw  = load_targets(targets_path)
    acquirers_raw = load_acquirers(acquirers_path)
    overrides    = load_manual_overrides(overrides_path) if overrides_path.exists() else {}

    validation = validate_universe(targets_raw, acquirers_raw)
    if not validation.valid:
        print("ERROR: Universe validation failed:", file=sys.stderr)
        for err in validation.errors:
            print(f"  [{err.ticker}] {err.field}: {err.message}", file=sys.stderr)
        return 1

    # ── Step 2: Enrich profiles ────────────────────────────────────────────
    from bve.ingestion.profile_enricher import ProfileEnricher

    enricher = ProfileEnricher(
        targets_raw,
        acquirers_raw,
        overrides,
        sec_fetcher=lambda t: {},         # no live SEC financials here
        ledger_score_fetcher=lambda t: {},
    )
    target_profiles  = enricher.enrich_targets()
    acquirer_profiles = enricher.enrich_acquirers()

    # ── Step 3: Load ledger ────────────────────────────────────────────────
    from bve.ingestion.evidence_ledger import EvidenceLedger

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger = EvidenceLedger(path=ledger_path)

    # ── Step 4: Run ingestion ──────────────────────────────────────────────
    from bve.ingestion.live_ingestion_runner import LiveIngestionRunner

    runner = LiveIngestionRunner(
        sec_source=_sec_source,
        ctgov_source=_ctgov_source,
        fda_source=_fda_source,
    )

    result = runner.run(
        targets=target_profiles,
        acquirers=acquirer_profiles,
        ledger=ledger,
        as_of_date=as_of,
        lookback_days=args.lookback_days,
        output_dir=output_dir if not args.dry_run else None,
        dry_run=args.dry_run,
    )

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"As-of date:              {as_of}")
    print(f"Lookback days:           {result.lookback_days}")
    print(f"Targets:                 {len(target_profiles)}")
    print(f"Acquirers:               {len(acquirer_profiles)}")
    print(f"Items seen:              {result.items_seen}")
    print(f"Items classified:        {result.items_classified}")
    print(f"Unclassified:            {result.unclassified_count}")
    print(f"Records appended:        {result.records_appended}")
    print(f"Duplicates skipped:      {result.duplicates_skipped}")
    for src, count in sorted(result.source_breakdown.items()):
        print(f"  {src}: {count}")

    if args.dry_run:
        print("Dry run — no files written.")
        return 0

    print(f"Output dir:              {output_dir}")
    for p in result.output_paths:
        print(f"  {Path(p).name}")
    return 0
