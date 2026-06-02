"""
bve-ledger-manifest — generate or verify a ledger integrity manifest.

Generate mode (default): computes SHA-256 + record stats and writes
  outputs/intelligence/ledger_manifest.json

Verify mode (--verify): compares the current file hash against a previously
  saved manifest; exits 1 on mismatch.

Usage::

    # Generate
    bve-ledger-manifest \\
      --ledger outputs/intelligence/evidence_ledger.jsonl \\
      --run-id daily-2026-06-02 \\
      --as-of 2026-06-02 \\
      --output outputs/intelligence/ledger_manifest.json

    # Verify
    bve-ledger-manifest --verify \\
      --ledger outputs/intelligence/evidence_ledger.jsonl \\
      --manifest outputs/intelligence/ledger_manifest.json
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-ledger-manifest",
        description="Generate or verify a ledger integrity manifest.",
    )
    parser.add_argument(
        "--ledger",
        default="outputs/intelligence/evidence_ledger.jsonl",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Run identifier (e.g. daily-2026-06-02). Defaults to daily-<today>.",
    )
    parser.add_argument("--as-of", default=None)
    parser.add_argument(
        "--output",
        default="outputs/intelligence/ledger_manifest.json",
        help="Path to write the manifest JSON (generate mode).",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        default=False,
        help="Verify mode: compare current file against stored manifest.",
    )
    parser.add_argument(
        "--manifest",
        default="outputs/intelligence/ledger_manifest.json",
        help="Manifest file to verify against (verify mode).",
    )
    args = parser.parse_args(argv)

    ledger_path = Path(args.ledger)
    as_of = args.as_of or date.today().isoformat()
    run_id = args.run_id or f"daily-{as_of}"

    # ── Verify mode ────────────────────────────────────────────────────────
    if args.verify:
        manifest_path = Path(args.manifest)
        if not manifest_path.exists():
            print(f"bve-ledger-manifest: manifest not found at {manifest_path}")
            return 1
        if not ledger_path.exists():
            print(f"bve-ledger-manifest: ledger not found at {ledger_path}")
            return 1

        from bve.ingestion.ledger_manifest import verify_manifest

        ok, msg = verify_manifest(ledger_path, manifest_path)
        print(f"Ledger integrity check: {msg}")
        return 0 if ok else 1

    # ── Generate mode ──────────────────────────────────────────────────────
    if not ledger_path.exists() or ledger_path.stat().st_size == 0:
        print(f"bve-ledger-manifest: {ledger_path} is empty or missing — manifest will show 0 records")

    from bve.ingestion.ledger_manifest import generate_manifest

    manifest = generate_manifest(
        ledger_path=ledger_path,
        run_id=run_id,
        as_of_date=as_of,
    )

    output_path = Path(args.output)
    manifest.save(output_path)

    sep = "─" * 50
    print(f"\nLedger manifest — {as_of}")
    print(sep)
    print(f"  run_id:          {manifest.run_id}")
    print(f"  ledger:          {manifest.ledger_path}")
    print(f"  sha256:          {manifest.sha256[:24]}…")
    print(f"  file_size:       {manifest.file_size_bytes / 1024:.1f} KB")
    print(f"  total_records:   {manifest.total_records:,}")
    if manifest.oldest_record:
        print(f"  oldest_record:   {manifest.oldest_record}")
    if manifest.newest_record:
        print(f"  newest_record:   {manifest.newest_record}")
    print(f"  manifest_path:   {output_path}")
    print()

    top_sources = list(manifest.records_by_source.items())[:5]
    if top_sources:
        print("  Sources (top 5)")
        for src, cnt in top_sources:
            print(f"    {src:<28} {cnt:>6,}")

    top_tickers = list(manifest.records_by_ticker.items())[:10]
    if top_tickers:
        print("\n  Tickers (top 10)")
        for t, cnt in top_tickers:
            print(f"    {t:<12} {cnt:>6,}")
    print()
    return 0
