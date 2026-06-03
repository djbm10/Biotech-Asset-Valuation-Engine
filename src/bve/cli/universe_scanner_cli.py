"""CLI: bve-scan-universe — discover public biotech companies from SEC EDGAR.

Usage::

    bve-scan-universe
    bve-scan-universe --output research/universe/biotech_tickers.yaml
    bve-scan-universe --rate 5 --quiet
    bve-scan-universe --show 20
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Scan SEC EDGAR for public biotech/pharma companies (SIC 2836/2835/2833/8731) "
            "on Nasdaq/NYSE and write a universe YAML."
        )
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output YAML path (default: research/universe/biotech_tickers.yaml)",
    )
    parser.add_argument(
        "--cache",
        default=None,
        help="SQLite SIC cache path (default: research/universe/.sic_cache.db)",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=8.0,
        help="EDGAR requests per second, max 10.0 (default: 8.0)",
    )
    parser.add_argument(
        "--show",
        type=int,
        default=10,
        metavar="N",
        help="Print first N entries to stdout (default: 10)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.rate > 10.0:
        print("ERROR: --rate must be ≤ 10.0 (EDGAR policy limit).", file=sys.stderr)
        sys.exit(1)

    try:
        from bve.ingestion.universe_scanner import (
            _DEFAULT_OUTPUT_PATH,
            scan_biotech_universe,
        )
    except ImportError as exc:
        print(f"ERROR: import failed — {exc}", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output).expanduser().resolve() if args.output else _DEFAULT_OUTPUT_PATH
    cache_path = Path(args.cache).expanduser().resolve() if args.cache else None

    entries = scan_biotech_universe(
        cache_path=cache_path,
        output_path=output_path,
        requests_per_second=args.rate,
        verbose=not args.quiet,
    )

    if not args.quiet:
        show_n = min(args.show, len(entries))
        if show_n > 0:
            print(f"\nFirst {show_n} of {len(entries)} entries:")
            for e in sorted(entries, key=lambda x: x.ticker)[:show_n]:
                print(f"  {e.ticker:8s}  {e.exchange:6s}  SIC:{e.sic}  {e.company_name}")
        print(f"\nTotal: {len(entries)} biotech companies. Written to {output_path}")


if __name__ == "__main__":
    main()
