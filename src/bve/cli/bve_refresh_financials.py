"""bve-refresh-financials CLI: fetch and display a live financial snapshot.

Usage
-----
    bve-refresh-financials TICKER
    bve-refresh-financials TICKER --output outputs/financials.md
    bve-refresh-financials TICKER --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-refresh-financials",
        description="Fetch a live financial snapshot for a ticker.",
    )
    parser.add_argument("ticker", help="Stock ticker (e.g. SRPT).")
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path. If omitted, prints to stdout.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output JSON instead of Markdown.",
    )
    parser.add_argument(
        "--yaml-override",
        default=None,
        dest="yaml_override",
        help="Path to YAML config file with financial fallback values.",
    )
    args = parser.parse_args(argv)

    print(f"[bve-refresh-financials] Fetching financials for {args.ticker.upper()}...", file=sys.stderr)

    yaml_override: dict | None = None
    if args.yaml_override:
        try:
            import yaml
            yaml_override = yaml.safe_load(Path(args.yaml_override).read_text())
        except Exception as exc:
            print(f"[bve-refresh-financials] Warning: could not load YAML override: {exc}", file=sys.stderr)

    from bve.refresh.financial_refresh import fetch_financial_snapshot, render_financial_snapshot

    snap = fetch_financial_snapshot(args.ticker, yaml_override=yaml_override)

    if snap.staleness_warning:
        print(f"[bve-refresh-financials] Warning: {snap.staleness_warning}", file=sys.stderr)

    if args.as_json:
        rendered = json.dumps(snap.to_dict(), indent=2, default=str)
    else:
        rendered = render_financial_snapshot(snap)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
        print(f"[bve-refresh-financials] Output written to {out_path}", file=sys.stderr)
    else:
        print(rendered)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
