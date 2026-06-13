"""
bve-score-audit — explain why a company's M&A feature scores are where they are.

Replays the evidence ledger for one ticker and prints (or writes) a per-feature
audit trail: every sourced event, the delta it applied, before/after, decay,
clamping, confidence, and reason. This is the "show someone exactly why a
company moved up or down" artifact.

Usage::

    bve-score-audit --ticker SRPT
    bve-score-audit --ticker SRPT --as-of 2026-06-01 --feature seller_willingness
    bve-score-audit --ticker SRPT --out outputs/audit/SRPT.md
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-score-audit",
        description="Render a source-level audit trail of a ticker's score changes.",
    )
    parser.add_argument("--ticker", required=True)
    parser.add_argument(
        "--ledger", default="outputs/intelligence/evidence_ledger.jsonl"
    )
    parser.add_argument("--as-of", default=None, help="ISO date; replay up to this date.")
    parser.add_argument(
        "--feature", default=None,
        help="Restrict the trail to a single feature (e.g. seller_willingness).",
    )
    parser.add_argument(
        "--apply-decay", action="store_true",
        help="Apply staleness decay (matches the screen's decay mode).",
    )
    parser.add_argument(
        "--use-published-date", action="store_true",
        help="Filter by published_date (no-lookahead) instead of event_date.",
    )
    parser.add_argument("--out", default=None, help="Write markdown to this path instead of stdout.")
    args = parser.parse_args(argv)

    ledger_path = Path(args.ledger)
    if not ledger_path.exists() or ledger_path.stat().st_size == 0:
        print(f"Ledger: {ledger_path} (empty or not found)")
        return 1

    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    ticker = args.ticker.upper()

    from bve.ingestion.evidence_ledger import EvidenceLedger
    from bve.reporting.score_audit import render_score_audit

    ledger = EvidenceLedger(path=ledger_path)
    scores, trail = ledger.compute_score_state_with_trail(
        ticker=ticker,
        as_of_date=as_of,
        use_published_date=args.use_published_date,
        apply_decay=args.apply_decay,
    )

    if args.feature:
        trail = [e for e in trail if e.feature == args.feature]

    md = render_score_audit(
        ticker, scores, trail, as_of=as_of.isoformat() if as_of else None
    )

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")
        print(f"Wrote {out_path}")
    else:
        print(md)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
