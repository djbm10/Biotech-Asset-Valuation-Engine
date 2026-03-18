"""
CLI: bve-catalyst-calendar — display upcoming catalyst events ranked by signal strength.

Usage
-----
    bve-catalyst-calendar
    bve-catalyst-calendar --asset MRTX
    bve-catalyst-calendar --days-ahead 90
    bve-catalyst-calendar --asset MRTX --days-ahead 180 --db outputs/intel/knowledge.db

Output columns
--------------
    date | asset | type | signal_strength | delta_ev ($M) | asymmetry | confidence
"""
from __future__ import annotations

import argparse
import sys


_CAP_RISK_WARN = {"high", "critical"}


def _extract_cap_risk(ev) -> str:
    """
    Extract capital_risk label from the event description tag if present.
    Returns a display string with a warning marker for HIGH/CRITICAL.
    """
    desc = getattr(ev, "description", "") or ""
    # Description tag format: "cap_risk=<level>" (set by pipeline when available)
    for part in desc.split("|"):
        part = part.strip()
        if part.startswith("cap_risk="):
            level = part.split("=", 1)[1].strip().lower()
            if level in _CAP_RISK_WARN:
                return f"⚠ {level}"
            return level
    return "—"


def _fmt_float(v, fmt=".2f") -> str:
    if v is None:
        return "—"
    if v == float("inf"):
        return "∞"
    return f"{v:{fmt}}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Display upcoming catalyst events ranked by signal strength."
    )
    parser.add_argument(
        "--asset",
        metavar="ASSET_ID",
        default=None,
        help="Filter to a specific asset_id (or ticker)",
    )
    parser.add_argument(
        "--days-ahead",
        type=int,
        default=90,
        metavar="N",
        help="Only show catalysts within N days (default 90)",
    )
    parser.add_argument(
        "--db",
        default="outputs/intelligence_phase2/knowledge.db",
        metavar="PATH",
        help="Path to the KnowledgeStore SQLite database",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="show_all",
        help="Include resolved / inactive catalysts",
    )
    args = parser.parse_args()

    from bve.intelligence.knowledge_layer import KnowledgeStore

    try:
        ks = KnowledgeStore(db_path=args.db)
    except Exception as exc:
        print(f"ERROR: could not open knowledge store at {args.db!r}: {exc}", file=sys.stderr)
        sys.exit(1)

    events = ks.get_catalyst_events(
        asset_id=args.asset,
        active_only=not args.show_all,
        days_ahead=args.days_ahead,
    )

    if not events:
        print("No catalyst events found.")
        return

    # Sort by signal_strength descending (None treated as 0)
    events_sorted = sorted(
        events,
        key=lambda e: (e.signal_strength or 0.0),
        reverse=True,
    )

    # Header
    col_w = [12, 16, 22, 16, 15, 12, 12, 10]
    headers = ["date", "asset", "type", "signal_strength", "delta_ev ($M)", "asymmetry", "confidence", "cap_risk"]
    row_fmt = "  ".join(f"{{:<{w}}}" for w in col_w)

    print()
    print(row_fmt.format(*headers))
    print("  ".join("─" * w for w in col_w))

    for ev in events_sorted:
        # Attempt to pull capital_risk from the event description metadata
        # (stored as a structured tag when capital_structure_assessment was run)
        cap_risk_label = _extract_cap_risk(ev)
        print(row_fmt.format(
            str(ev.expected_date),
            (ev.asset_id or "—")[:col_w[1]],
            ev.catalyst_type.value[:col_w[2]],
            _fmt_float(ev.signal_strength, ".4f"),
            _fmt_float(ev.delta_ev, ".1f"),
            _fmt_float(ev.asymmetry_ratio, ".2f"),
            ev.date_confidence,
            cap_risk_label,
        ))

    print()
    print(f"  {len(events_sorted)} catalysts shown  |  window: next {args.days_ahead} days")
    print()


if __name__ == "__main__":
    main()
