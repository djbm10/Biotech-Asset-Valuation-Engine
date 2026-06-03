"""
bve-validate-universe — validate targets.yaml and acquirers.yaml against Phase 2M schema.

Exits with code 1 if any validation errors are found (CI-safe).

Usage::

    bve-validate-universe \\
      --targets research/universe/targets.yaml \\
      --acquirers research/universe/acquirers.yaml \\
      --as-of 2026-06-02

    # Strict: fail on warnings too
    bve-validate-universe --targets ... --acquirers ... --strict

    # Show per-ticker quality scores
    bve-validate-universe --targets ... --acquirers ... --scores
"""
from __future__ import annotations

import argparse
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-validate-universe",
        description="Validate targets.yaml and acquirers.yaml against Phase 2M schema.",
    )
    parser.add_argument(
        "--targets",
        default="research/universe/targets.yaml",
        help="Path to targets.yaml",
    )
    parser.add_argument(
        "--acquirers",
        default="research/universe/acquirers.yaml",
        help="Path to acquirers.yaml",
    )
    parser.add_argument("--as-of", default=None, help="ISO date for staleness checks (default: today)")
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Exit 1 on warnings as well as errors.",
    )
    parser.add_argument(
        "--scores",
        action="store_true",
        default=False,
        help="Print per-ticker profile quality scores.",
    )
    args = parser.parse_args(argv)

    targets_path = Path(args.targets)
    acquirers_path = Path(args.acquirers)

    if not targets_path.exists():
        print(f"bve-validate-universe: targets file not found: {targets_path}")
        return 1
    if not acquirers_path.exists():
        print(f"bve-validate-universe: acquirers file not found: {acquirers_path}")
        return 1

    from bve.ingestion.universe_schema import load_and_validate

    result = load_and_validate(targets_path, acquirers_path, args.as_of)

    sep = "─" * 60
    print(f"\nUniverse validation — {args.as_of or 'today'}")
    print(sep)
    print(f"  targets file:   {targets_path}")
    print(f"  acquirers file: {acquirers_path}")
    print(f"  targets:        {result.target_count}")
    print(f"  acquirers:      {result.acquirer_count}")
    print(f"  errors:         {result.error_count}")
    print(f"  warnings:       {result.warning_count}")

    med = result.quality_score_median
    if med is not None:
        print(f"  quality median: {med:.2f}")

    missing_cik = result.missing_cik_count
    if missing_cik:
        print(f"  missing CIKs:   {missing_cik} (warnings)")

    # Print errors
    if result.errors:
        print("\n  Errors")
        for e in result.errors[:40]:
            print(f"    ERR   {e.rule}  [{e.ticker}]{('.' + e.field) if e.field else ''}  {e.message}")
        if len(result.errors) > 40:
            print(f"    … +{len(result.errors) - 40} more errors")

    # Print warnings
    if result.warnings:
        print("\n  Warnings")
        for w in result.warnings[:30]:
            print(f"    WARN  {w.rule}  [{w.ticker}]{('.' + w.field) if w.field else ''}  {w.message}")
        if len(result.warnings) > 30:
            print(f"    … +{len(result.warnings) - 30} more warnings")

    # Rule distribution summary
    if result.issues:
        dist = result.suppression_reason_distribution
        print("\n  Issue distribution")
        for rule, count in sorted(dist.items()):
            print(f"    {rule}: {count}")

    # Per-ticker quality scores
    if args.scores and result.target_quality_scores:
        print("\n  Target quality scores (sorted)")
        scores = sorted(result.target_quality_scores.items(), key=lambda x: x[1])
        for ticker, score in scores:
            bar = "#" * int(score * 10)
            print(f"    {ticker:8}  {score:.1f}  {bar}")

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
