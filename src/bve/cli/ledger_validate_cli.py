"""
bve-ledger-validate — validate the evidence ledger before / after a run.

Exits with code 1 if any validation errors are found (CI-safe).

Usage::

    bve-ledger-validate \\
      --ledger outputs/intelligence/evidence_ledger.jsonl \\
      --as-of 2026-06-02 \\
      --known-tickers research/universe/targets.yaml

    # Strict: fail on warnings too
    bve-ledger-validate --ledger ... --strict
"""
from __future__ import annotations

import argparse
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-ledger-validate",
        description="Validate the evidence ledger and exit 1 on errors.",
    )
    parser.add_argument(
        "--ledger",
        default="outputs/intelligence/evidence_ledger.jsonl",
    )
    parser.add_argument("--as-of", default=None)
    parser.add_argument(
        "--known-tickers",
        default=None,
        help="Path to targets.yaml; tickers not in the universe emit warnings.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Exit 1 on warnings as well as errors.",
    )
    args = parser.parse_args(argv)

    ledger_path = Path(args.ledger)

    # Graceful pass on missing / empty — the create-if-missing step in the
    # workflow already handles this; we don't want to block the first run.
    if not ledger_path.exists() or ledger_path.stat().st_size == 0:
        print(f"bve-ledger-validate: {ledger_path} is empty or missing — skipping validation")
        return 0

    known_tickers: set[str] | None = None
    if args.known_tickers:
        known_tickers = _load_tickers_from_yaml(args.known_tickers)

    from bve.ingestion.ledger_validator import LedgerValidator

    result = LedgerValidator(
        path=ledger_path,
        as_of_date=args.as_of,
        known_tickers=known_tickers,
    ).validate()

    sep = "─" * 50
    print(f"\nLedger validation — {args.as_of or 'today'}")
    print(sep)
    print(f"  file:           {ledger_path}")
    print(f"  total_lines:    {result.total_lines:,}")
    print(f"  valid_records:  {result.valid_records:,}")
    print(f"  errors:         {result.error_count}")
    print(f"  warnings:       {result.warning_count}")

    if result.warnings:
        print("\n  Warnings")
        for w in result.warnings[:20]:
            print(f"    WARN  {w}")
        if len(result.warnings) > 20:
            print(f"    … +{len(result.warnings) - 20} more warnings")

    if result.errors:
        print("\n  Errors")
        for e in result.errors[:30]:
            print(f"    ERR   {e}")
        if len(result.errors) > 30:
            print(f"    … +{len(result.errors) - 30} more errors")

    print()
    if result.is_valid:
        print("  STATUS: PASS")
    else:
        print("  STATUS: FAIL")

    if not result.is_valid:
        return 1
    if args.strict and result.warning_count > 0:
        return 1
    return 0


def _load_tickers_from_yaml(path: str) -> set[str]:
    """Load ticker list from a targets.yaml file."""
    import yaml  # type: ignore[import-untyped]

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    tickers: set[str] = set()
    if isinstance(data, dict):
        for item in data.get("targets", []):
            if isinstance(item, dict) and "ticker" in item:
                tickers.add(str(item["ticker"]).upper())
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "ticker" in item:
                tickers.add(str(item["ticker"]).upper())
    return tickers
