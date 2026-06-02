"""
bve-build-profiles — enrich target and acquirer profiles.

Loads the universe YAML files and runs ProfileEnricher to produce:
  target_profiles.json
  acquirer_profiles.json
  profile_quality_report.json

External calls (SEC EDGAR, evidence ledger) can be injected for testing.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable, Optional


def main(
    argv: list[str] | None = None,
    _sec_fetcher: Optional[Callable[[str], dict[str, Any]]] = None,
    _ledger_score_fetcher: Optional[Callable[[str], dict[str, float]]] = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-build-profiles",
        description="Enrich target and acquirer profiles from universe YAMLs.",
    )
    parser.add_argument("--targets",   default="research/universe/targets.yaml")
    parser.add_argument("--acquirers", default="research/universe/acquirers.yaml")
    parser.add_argument("--overrides", default="research/universe/manual_overrides.yaml")
    parser.add_argument("--ledger",    default="outputs/intelligence/evidence_ledger.jsonl")
    parser.add_argument("--output",    default="outputs/profiles")
    parser.add_argument("--dry-run",   action="store_true")
    args = parser.parse_args(argv)

    targets_path = Path(args.targets)
    acquirers_path = Path(args.acquirers)
    overrides_path = Path(args.overrides)
    ledger_path = Path(args.ledger)
    output_dir = Path(args.output)

    # Validate required inputs
    for label, p in [("targets", targets_path), ("acquirers", acquirers_path)]:
        if not p.exists():
            print(f"ERROR: {label} file not found: {p}", file=sys.stderr)
            return 1

    # Lazy imports (keep startup fast)
    from bve.ingestion.universe_loader import (
        load_acquirers,
        load_manual_overrides,
        load_targets,
        validate_universe,
    )
    from bve.ingestion.profile_enricher import ProfileEnricher, write_profiles

    targets = load_targets(targets_path)
    acquirers = load_acquirers(acquirers_path)
    overrides = load_manual_overrides(overrides_path) if overrides_path.exists() else {}

    # Validate universe before enriching
    result = validate_universe(targets, acquirers)
    if not result.valid:
        print("ERROR: Universe validation failed:", file=sys.stderr)
        for err in result.errors:
            print(f"  [{err.ticker}] {err.field}: {err.message}", file=sys.stderr)
        return 1

    # Wire ledger score fetcher if ledger file exists
    if _ledger_score_fetcher is None and ledger_path.exists():
        from bve.ingestion.evidence_ledger import EvidenceLedger
        _ledger = EvidenceLedger(path=ledger_path)
        _ledger_score_fetcher = _ledger.compute_score_state

    if _ledger_score_fetcher is None:
        def _ledger_score_fetcher(ticker: str) -> dict[str, float]:  # type: ignore[misc]
            return {}

    # Default: skip live SEC calls (2C adds live ingestion)
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

    included = [p for p in target_profiles.values() if p.include_in_screen]
    high_q = sum(1 for p in included if p.quality_score >= 0.70)
    top = max(included, key=lambda p: p.quality_score, default=None)

    print(f"Targets loaded:          {len(targets)}")
    print(f"Acquirers loaded:        {len(acquirers)}")
    print(f"Targets included:        {len(included)}")
    print(f"High-quality (≥0.70):    {high_q}")
    if top:
        print(f"Best quality target:     {top.ticker} ({top.quality_score:.2f})")

    if args.dry_run:
        print("Dry run successful. No files written.")
        return 0

    write_profiles(target_profiles, acquirer_profiles, output_dir)
    print(f"Profiles written to:     {output_dir}")
    return 0
