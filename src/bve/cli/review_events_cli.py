"""
bve-review-events — export pending events CSV and apply reviewer decisions.

Two modes:

  Export mode (default): writes pending_events.csv listing all records that
  have not yet been approved or rejected.

  Apply mode (--decisions): reads a review_decisions.yaml, applies the
  decisions to a ReviewGate, then optionally re-runs the screen to show
  the approved-only vs provisional delta.

Usage::

    # 1. Export pending events for human review
    bve-review-events \\
      --ledger outputs/intelligence/evidence_ledger.jsonl \\
      --output outputs/daily/2026-06-02/pending_events.csv

    # 2. Apply review decisions
    bve-review-events \\
      --ledger outputs/intelligence/evidence_ledger.jsonl \\
      --decisions review_decisions.yaml \\
      --show-delta

    # 3. Export ALL events (not just pending)
    bve-review-events --ledger ... --output ... --all
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-review-events",
        description="Export pending events for human review; apply review decisions.",
    )
    parser.add_argument("--ledger", default="outputs/intelligence/evidence_ledger.jsonl")
    parser.add_argument("--as-of", default=None)
    parser.add_argument(
        "--output",
        default=None,
        help="Path to write pending_events.csv (export mode).",
    )
    parser.add_argument(
        "--decisions",
        default=None,
        help="Path to review_decisions.yaml to apply.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Export all records, not just pending.",
    )
    parser.add_argument(
        "--show-delta",
        action="store_true",
        default=False,
        help="After applying decisions, print approved-only vs provisional delta.",
    )
    args = parser.parse_args(argv)

    ledger_path = Path(args.ledger)
    as_of = args.as_of or date.today().isoformat()

    if not ledger_path.exists() or ledger_path.stat().st_size == 0:
        print(f"bve-review-events: ledger is empty or missing: {ledger_path}")
        return 0

    from bve.ingestion.evidence_ledger import EvidenceLedger
    from bve.ingestion.review_apply import (
        apply_decisions_to_gate,
        build_pending_events_rows,
        load_review_decisions_yaml,
        write_pending_events_csv,
    )
    from bve.ingestion.review_gate import ReviewGate

    ledger = EvidenceLedger(path=ledger_path)
    gate = ReviewGate()

    # ── Apply decisions if provided ────────────────────────────────────────
    n_applied = 0
    if args.decisions:
        decisions = load_review_decisions_yaml(args.decisions)
        n_applied = apply_decisions_to_gate(decisions, gate)
        print(f"Applied {n_applied} review decisions from {args.decisions}")

    # ── Export pending events CSV ──────────────────────────────────────────
    rows = build_pending_events_rows(
        ledger=ledger,
        gate=gate,
        as_of_date=as_of,
        pending_only=not args.all,
    )

    output_path = args.output
    if output_path is None:
        # Default to same dir as ledger or cwd
        output_path = str(ledger_path.parent / "pending_events.csv")

    write_pending_events_csv(rows, output_path)

    sep = "─" * 50
    print(f"\nReview export — {as_of}")
    print(sep)
    print(f"  ledger:          {ledger_path}")
    print(f"  pending_events:  {output_path}")
    print(f"  rows exported:   {len(rows)}")
    if n_applied:
        summary = gate.summary()
        print(f"  decisions applied: {n_applied}")
        for status, count in summary.items():
            if count:
                print(f"    {status:<12} {count:>4}")

    # ── Show approved-only vs provisional delta ────────────────────────────
    if args.show_delta and n_applied > 0:
        _show_score_delta(ledger, gate, as_of)

    print()
    return 0


def _show_score_delta(ledger, gate, as_of: str) -> None:
    """Print per-ticker score diff between approved-only and provisional modes."""
    from bve.ingestion.review_gate import ScoreMode

    all_tickers = sorted({r.ticker for r in ledger.get_records()})
    if not all_tickers:
        return

    print("\n  Score delta: approved_only vs provisional")
    print(f"  {'Ticker':<10} {'Feature':<22} {'approved':>9} {'provisional':>12} {'delta':>7}")
    print("  " + "─" * 62)

    for ticker in all_tickers:
        scores_approved = ledger.compute_score_state(ticker, gate=gate, mode=ScoreMode.APPROVED_ONLY)
        scores_prov = ledger.compute_score_state(ticker, gate=gate, mode=ScoreMode.PROVISIONAL)

        for key in sorted(set(scores_approved) | set(scores_prov)):
            a = scores_approved.get(key, 0.0)
            p = scores_prov.get(key, 0.0)
            if abs(a - p) > 0.001:
                print(f"  {ticker:<10} {key:<22} {a:>9.3f} {p:>12.3f} {p-a:>+7.3f}")
