"""CLI: bve-catalyst-calendar — ranked catalyst edge screen.

Combines model POS, market-implied POS, upcoming catalyst dates, and binary
event volatility to rank where BVE disagrees with the market ahead of a
near-term event.

Usage
-----
    bve-catalyst-calendar
    bve-catalyst-calendar --tickers SRPT VKTX ALNY
    bve-catalyst-calendar --days 90
    bve-catalyst-calendar --min-edge 0.10
    bve-catalyst-calendar --output outputs/calendar_2026-05-26.md
    bve-catalyst-calendar --json
    bve-catalyst-calendar --skip-refresh       # offline / test mode

Output columns
--------------
    Ticker | Event | Date | Days | Model P | Mkt P | Gap | Mkt Cap | Move% | Edge | Conf
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="bve-catalyst-calendar",
        description=(
            "Display upcoming catalyst events ranked by edge score "
            "(POS gap × event materiality × confidence × timing)."
        ),
    )
    parser.add_argument(
        "--tickers", nargs="+", metavar="TICKER", default=None,
        help="Restrict to these tickers. Default: full tracked universe.",
    )
    parser.add_argument(
        "--days", type=int, default=180, metavar="N",
        help="Only include events within N days (default 180).",
    )
    parser.add_argument(
        "--min-edge", type=float, default=0.0, dest="min_edge", metavar="FLOAT",
        help="Hide rows with edge_score < FLOAT (default 0.0 = show all).",
    )
    parser.add_argument(
        "--output", default=None, metavar="PATH",
        help="Write Markdown output to PATH (default: stdout).",
    )
    parser.add_argument(
        "--json", action="store_true", dest="emit_json",
        help="Emit JSON array instead of Markdown.",
    )
    parser.add_argument(
        "--skip-refresh", action="store_true", dest="skip_refresh",
        help="Skip live market/financial fetch (offline / test mode).",
    )
    parser.add_argument(
        "--ops-db", default=None, dest="ops_db", metavar="PATH",
        help="Path to intelligence ops.db (default: outputs/intelligence/ops.db).",
    )
    parser.add_argument(
        "--outputs-dir", default=None, dest="outputs_dir", metavar="PATH",
        help="Root outputs directory (default: outputs/).",
    )
    args = parser.parse_args(argv)

    root = Path("outputs")
    ops_db = Path(args.ops_db) if args.ops_db else (root / "intelligence" / "ops.db")
    outputs_dir = Path(args.outputs_dir) if args.outputs_dir else root

    from bve.intelligence.catalyst_edge_calendar import CatalystEdgeCalendar

    calendar = CatalystEdgeCalendar(
        ops_db=ops_db,
        outputs_dir=outputs_dir,
        max_days_forward=args.days,
        skip_market_refresh=args.skip_refresh,
    )

    records = calendar.build(tickers=args.tickers)

    # Apply min-edge filter
    if args.min_edge > 0:
        records = [r for r in records if (r.edge_score or 0.0) >= args.min_edge]

    # Format output
    if args.emit_json:
        output = json.dumps([r.to_dict() for r in records], indent=2, default=str)
    else:
        output = calendar.render_markdown(records)
        if records:
            output += (
                f"\n*{len(records)} event(s) shown"
                f" | window: {args.days}d"
                f" | min-edge: {args.min_edge:.2f}*\n"
            )

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"[bve-catalyst-calendar] Written to {args.output}", file=sys.stderr)
    else:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
