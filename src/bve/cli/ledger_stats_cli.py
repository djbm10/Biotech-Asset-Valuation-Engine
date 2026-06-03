"""
bve-ledger-stats — evidence ledger health check.

Prints a summary of the evidence ledger without modifying it:

  total_records
  records_last_7d / last_30d
  unique_tickers
  oldest / newest record date
  records_by_source_type
  records_by_event_type  (top 10)
  intra-ledger duplicate hashes  (integrity check)
  records_with_empty_deltas

Usage::

    bve-ledger-stats \\
      --ledger outputs/intelligence/evidence_ledger.jsonl \\
      --as-of 2026-06-02
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, timedelta
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-ledger-stats",
        description="Print evidence ledger health statistics.",
    )
    parser.add_argument(
        "--ledger",
        default="outputs/intelligence/evidence_ledger.jsonl",
    )
    parser.add_argument("--as-of", default=None)
    args = parser.parse_args(argv)

    ledger_path = Path(args.ledger)
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()

    if not ledger_path.exists() or ledger_path.stat().st_size == 0:
        print(f"Ledger: {ledger_path} (empty or not found)")
        return 0

    from bve.ingestion.evidence_ledger import EvidenceLedger

    ledger = EvidenceLedger(path=ledger_path)
    all_records = ledger.get_records()

    if not all_records:
        print(f"Ledger: {ledger_path}")
        print("total_records:            0")
        return 0

    total = len(all_records)
    cutoff_7d  = (as_of - timedelta(days=7)).isoformat()
    cutoff_30d = (as_of - timedelta(days=30)).isoformat()

    last_7d  = sum(1 for r in all_records if r.event_date >= cutoff_7d)
    last_30d = sum(1 for r in all_records if r.event_date >= cutoff_30d)

    tickers     = sorted({r.ticker for r in all_records})
    unique_tick = len(tickers)

    dates  = sorted(r.event_date for r in all_records)
    oldest = dates[0]
    newest = dates[-1]

    by_source = Counter(r.source_type for r in all_records)
    by_event  = Counter(r.event_type for r in all_records)

    # Integrity: check for duplicate event_hashes (should be zero)
    hashes = [r.event_hash for r in all_records if r.event_hash]
    dup_hashes = len(hashes) - len(set(hashes))

    empty_deltas = sum(1 for r in all_records if not r.score_deltas)

    # File size
    size_kb = ledger_path.stat().st_size / 1024

    # ── Print ─────────────────────────────────────────────────────────────
    sep = "─" * 48
    print(f"\nLedger health — {as_of}")
    print(sep)
    print(f"  file:                    {ledger_path}")
    print(f"  size:                    {size_kb:.1f} KB")
    print()
    print(f"  total_records:           {total:,}")
    print(f"  records_last_7d:         {last_7d:,}")
    print(f"  records_last_30d:        {last_30d:,}")
    print(f"  unique_tickers:          {unique_tick}")
    print(f"  oldest_record:           {oldest}")
    print(f"  newest_record:           {newest}")

    print()
    print("  Sources")
    for src, count in sorted(by_source.items(), key=lambda x: -x[1]):
        print(f"    {src:<28} {count:>6,}")

    print()
    print("  Event types (top 10)")
    for evt, count in by_event.most_common(10):
        print(f"    {evt:<28} {count:>6,}")

    print()
    print("  Integrity")
    dup_label = "ok" if dup_hashes == 0 else f"WARNING — {dup_hashes} duplicates"
    print(f"    intra-ledger duplicates: {dup_hashes}  ({dup_label})")
    print(f"    records_with_empty_deltas: {empty_deltas}")

    print()
    print(f"  Tickers tracked: {', '.join(tickers[:20])}", end="")
    if unique_tick > 20:
        print(f" … +{unique_tick - 20} more", end="")
    print()

    return 0
