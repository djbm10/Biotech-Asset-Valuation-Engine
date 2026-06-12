"""
bve-weekly-run — full weekly M&A screen pipeline.

Orchestrates:
  1. Load universe (targets + acquirers + overrides)
  2. Enrich profiles (ProfileEnricher) — first pass for ingestion context
  3. Ingest live evidence (optional, --ingest-live)
     SEC 8-K + ClinicalTrials.gov + FDA → evidence_ledger.jsonl + new_events.csv
  4. Re-enrich profiles if ingestion appended new records (ledger is file-backed)
  5. Run M&A screen (WeeklyMAScreen)
  6. Write report files (WeeklyReportGenerator)
  7. Write screen_result.json

Output dir receives all output files:
  screen_result.json
  ranked_targets.csv
  top_acquirer_pairs.csv
  suppressed_targets.csv
  score_changes.csv
  audit_report.md
  validation_snapshot.json
  new_events.csv          (only when --ingest-live)

Usage::

    bve-weekly-run \\
      --targets research/universe/targets.yaml \\
      --acquirers research/universe/acquirers.yaml \\
      --overrides research/universe/manual_overrides.yaml \\
      --ledger outputs/intelligence/evidence_ledger.jsonl \\
      --as-of 2026-06-01 \\
      --score-mode provisional \\
      --lookback-days 14 \\
      --ingest-live \\
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
    # Injectable ingestion sources (None → real adapters)
    _ingest_sec_source: Optional[Callable] = None,
    _ingest_ctgov_source: Optional[Callable] = None,
    _ingest_fda_source: Optional[Callable] = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-weekly-run",
        description="Full weekly M&A screen pipeline: enrich → [ingest] → screen → report.",
    )
    parser.add_argument("--targets",      default="research/universe/targets.yaml")
    parser.add_argument("--acquirers",    default="research/universe/acquirers.yaml")
    parser.add_argument("--overrides",    default="research/universe/manual_overrides.yaml")
    parser.add_argument("--ledger",       default="outputs/intelligence/evidence_ledger.jsonl")
    parser.add_argument("--as-of",        default=None)
    parser.add_argument("--score-mode",   default="provisional",
                        choices=["approved_only", "provisional", "all_auto",
                                 "structural", "evidence_backed"])
    parser.add_argument("--output",       default=None)
    parser.add_argument("--prev-output",  default=None,
                        help="Previous run output dir (for score change diff)")
    parser.add_argument("--min-coverage", type=float, default=0.20)
    parser.add_argument("--ingest-live",  action="store_true",
                        help="Run live ingestion (SEC 8-K + CT.gov + FDA) before screening")
    parser.add_argument(
        "--ingest-sources",
        default=None,
        help=(
            "Comma-separated live ingestion sources. Defaults to sec,clinicaltrials,fda. "
            "Accepted: sec,clinicaltrials,fda,press_releases,earnings_calls."
        ),
    )
    parser.add_argument("--lookback-days", type=int, default=14,
                        help="Lookback window in days for live ingestion")
    parser.add_argument("--dry-run",      action="store_true")
    parser.add_argument(
        "--decisions",
        default=None,
        help="Path to review_decisions.yaml; activates approved-only vs provisional delta reporting.",
    )
    args = parser.parse_args(argv)

    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    output_dir = Path(args.output) if args.output else Path("outputs/weekly") / as_of.isoformat()

    targets_path  = Path(args.targets)
    acquirers_path = Path(args.acquirers)
    overrides_path = Path(args.overrides)
    ledger_path    = Path(args.ledger)

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

    targets  = load_targets(targets_path)
    acquirers = load_acquirers(acquirers_path)
    overrides = load_manual_overrides(overrides_path) if overrides_path.exists() else {}

    validation = validate_universe(targets, acquirers)
    if not validation.valid:
        print("ERROR: Universe validation failed:", file=sys.stderr)
        for err in validation.errors:
            print(f"  [{err.ticker}] {err.field}: {err.message}", file=sys.stderr)
        return 1

    # ── Step 2: First enrich — provides context for ingestion ──────────────
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

    def _make_enricher() -> ProfileEnricher:
        return ProfileEnricher(
            targets,
            acquirers,
            overrides,
            sec_fetcher=_sec_fetcher,
            ledger_score_fetcher=_ledger_score_fetcher,
        )

    enricher = _make_enricher()
    target_profiles  = enricher.enrich_targets()
    acquirer_profiles = enricher.enrich_acquirers()

    # ── Step 3: Live ingestion (optional) ─────────────────────────────────
    from bve.ingestion.evidence_ledger import EvidenceLedger
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger = EvidenceLedger(path=ledger_path)

    ingest_result = None
    if args.ingest_live:
        from bve.ingestion.live_ingestion_runner import LiveIngestionRunner

        ingest_sources = (
            [s.strip() for s in args.ingest_sources.split(",") if s.strip()]
            if args.ingest_sources
            else None
        )
        ingest_runner = LiveIngestionRunner(
            sec_source=_ingest_sec_source,
            ctgov_source=_ingest_ctgov_source,
            fda_source=_ingest_fda_source,
        )
        ingest_result = ingest_runner.run(
            targets=target_profiles,
            acquirers=acquirer_profiles,
            ledger=ledger,
            as_of_date=as_of,
            lookback_days=args.lookback_days,
            output_dir=output_dir if not args.dry_run else None,
            dry_run=args.dry_run,
            sources=ingest_sources,
        )
        print(
            "Ingestion — requested sources: "
            f"{', '.join(ingest_sources or ['sec', 'clinicaltrials', 'fda'])}"
        )
        print(f"Ingestion — items seen:      {ingest_result.items_seen}")
        print(f"Ingestion — classified:      {ingest_result.items_classified}")
        print(f"Ingestion — appended:        {ingest_result.records_appended}")
        print(f"Ingestion — duplicates:      {ingest_result.duplicates_skipped}")
        print(f"Ingestion — unclassified:    {ingest_result.unclassified_count}")
        print("Ingestion — source breakdown:")
        for source_name, count in sorted(ingest_result.source_breakdown.items()):
            print(f"  {source_name:<24} {count}")

        # ── Step 4: Re-enrich using updated ledger ─────────────────────────
        # EvidenceLedger is file-backed; compute_score_state re-reads the file,
        # so the same _ledger_score_fetcher closure sees the new records.
        if ingest_result.records_appended > 0:
            enricher2 = _make_enricher()
            target_profiles  = enricher2.enrich_targets()
            acquirer_profiles = enricher2.enrich_acquirers()

    # ── Step 5: Load review decisions (optional) ──────────────────────────
    from bve.ingestion.review_gate import ReviewGate, ScoreMode

    gate = ReviewGate()
    if args.decisions:
        from bve.ingestion.review_apply import apply_decisions_to_gate, load_review_decisions_yaml

        decisions = load_review_decisions_yaml(args.decisions)
        n = apply_decisions_to_gate(decisions, gate)
        print(f"Review decisions loaded:  {n} from {args.decisions}")

    # ── Step 6: Run screen ─────────────────────────────────────────────────
    from bve.intelligence.weekly_ma_screen import WeeklyMAScreen

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

    # ── Load previous result for score diff ───────────────────────────────
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

    # ── Approved-only vs provisional delta (when --decisions provided) ─────
    if args.decisions:
        result_approved = screen.run(
            as_of_date=as_of,
            targets=list(target_profiles.values()),
            acquirers=list(acquirer_profiles.values()),
            ledger=ledger,
            score_mode=ScoreMode.APPROVED_ONLY,
            min_coverage=args.min_coverage,
        )
        prov_scores = {r.ticker: r.ma_probability for r in result.ranked_targets}
        appr_scores = {r.ticker: r.ma_probability for r in result_approved.ranked_targets}
        print("\nApproved-only vs provisional delta (MA probability):")
        for ticker in sorted(prov_scores):
            prov = prov_scores[ticker]
            appr = appr_scores.get(ticker, 0.0)
            if abs(prov - appr) > 0.005:
                print(f"  {ticker:<10} approved={appr:.3f}  provisional={prov:.3f}  Δ={prov-appr:+.3f}")

    if args.dry_run:
        print("Dry run successful. No files written.")
        return 0

    # ── Step 6: Write outputs ─────────────────────────────────────────────
    output_dir.mkdir(parents=True, exist_ok=True)

    from bve.cli._serde import screen_result_to_json
    from bve.reporting.weekly_report import WeeklyReportGenerator

    screen_result_path = output_dir / "screen_result.json"
    screen_result_path.write_text(screen_result_to_json(result), encoding="utf-8")

    gen = WeeklyReportGenerator()
    report_paths = gen.write_outputs(result, output_dir, prev_result=prev_result)

    print(f"Output written to:       {output_dir}")
    all_paths = [screen_result_path] + report_paths

    # Include new_events.csv from ingestion if it was written
    if ingest_result:
        new_events_path = output_dir / "new_events.csv"
        if new_events_path.exists():
            all_paths.append(new_events_path)

    for p in all_paths:
        print(f"  {p.name}")

    # ── Step 7: Write run_context.json ────────────────────────────────────
    try:
        from bve.run.run_context import capture_run_context

        ctx = capture_run_context(
            as_of_date=as_of.isoformat(),
            score_mode=args.score_mode,
            lookback_days=args.lookback_days,
            ingest_live=args.ingest_live,
            input_files={
                "targets": str(targets_path),
                "acquirers": str(acquirers_path),
                "overrides": str(overrides_path),
                "ledger": str(ledger_path),
            },
        ).mark_completed()
        ctx.save(output_dir / "run_context.json")
        print("  run_context.json")
    except Exception as exc:  # pragma: no cover — defensive
        print(f"WARNING: could not write run_context.json: {exc}", file=sys.stderr)

    return 0
