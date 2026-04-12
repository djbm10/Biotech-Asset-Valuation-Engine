"""
bve-daily-brief CLI — Unified daily opportunity brief (Sprint 19).

Usage
-----
    bve-daily-brief                        # screen all universe names (offline)
    bve-daily-brief --live                 # fetch live market data
    bve-daily-brief --top 15               # show top 15 (default: 10)
    bve-daily-brief --format json          # JSON output instead of markdown
    bve-daily-brief --db PATH              # custom KnowledgeStore path
    bve-daily-brief --as-of 2026-03-01    # time-frozen analysis
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path


def _parse_date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date '{s}' — expected YYYY-MM-DD")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bve-daily-brief",
        description="Unified daily opportunity brief: spread + calibration + expert notes + events.",
    )
    p.add_argument(
        "--live",
        action="store_true",
        help="Fetch live market data from yfinance (default: offline/parametric)",
    )
    p.add_argument("--top", type=int, default=10, metavar="N", help="Top N rows to display")
    p.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    p.add_argument(
        "--db",
        default=None,
        metavar="PATH",
        help="KnowledgeStore SQLite path (default: outputs/intelligence/ops.db)",
    )
    p.add_argument(
        "--as-of",
        dest="as_of",
        default=None,
        type=_parse_date,
        metavar="YYYY-MM-DD",
        help="Time-frozen date for analysis (default: today)",
    )
    p.add_argument(
        "--expert-note-days",
        type=int,
        default=30,
        metavar="N",
        help="Look-back window for expert notes in days (default: 30)",
    )
    p.add_argument(
        "--event-days",
        type=int,
        default=7,
        metavar="N",
        help="Look-back window for detected events in days (default: 7)",
    )
    p.add_argument(
        "--out",
        default=None,
        metavar="PATH",
        help="Write output to file instead of stdout",
    )
    p.add_argument(
        "--no-persist-policy-snapshots",
        action="store_true",
        help="Do not persist Step 5 equity-policy audit rows for this brief run",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Resolve DB path
    if args.db:
        db_path = Path(args.db)
    else:
        try:
            from bve.ops.weekly_runner import DB_PATH
            db_path = DB_PATH
        except Exception:
            db_path = Path("outputs/intelligence/ops.db")

    from bve.intelligence.knowledge_layer import KnowledgeStore
    from bve.ops.daily_brief import build_daily_brief, render_brief
    from bve.ops.weekly_runner import UNIVERSE

    store = KnowledgeStore(db_path)
    try:
        brief = build_daily_brief(
            store,
            UNIVERSE,
            as_of=args.as_of,
            fetch_live=args.live,
            expert_note_days=args.expert_note_days,
            event_days=args.event_days,
            persist_policy_snapshots=not args.no_persist_policy_snapshots,
        )

        if args.format == "json":
            output = _brief_to_json(brief, top_n=args.top)
        else:
            output = render_brief(brief, top_n=args.top)

        if args.out:
            Path(args.out).write_text(output)
            print(f"Written to {args.out}")
        else:
            print(output)
    finally:
        store.close()


def _brief_to_json(brief, top_n: int) -> str:
    def _row_dict(row) -> dict:
        d = {
            "ticker": row.ticker,
            "program_label": row.program_label,
            "stage": row.stage,
            "ta": row.ta,
            "model_pos": row.model_pos,
            "implied_pos": row.implied_pos,
            "spread_pp": row.spread_pp,
            "rnpv_millions": row.rnpv_millions,
            "ev_millions": row.ev_millions,
            "calibrated_base_rate": row.calibrated_base_rate,
            "calibrated_pos_delta": row.calibrated_pos_delta,
            "next_catalyst": row.next_catalyst,
            "days_to_catalyst": row.days_to_catalyst,
            "expert_note_count": row.expert_note_count,
            "expert_signal_types": sorted(row.expert_signal_types),
            "recent_event_count": row.recent_event_count,
            "requires_recompute": row.requires_recompute,
            "composite_score": row.composite_score,
            "company_ranked_discount": row.company_ranked_discount,
            "company_action_policy": row.company_action_policy,
            "company_action_reason": row.company_action_reason,
            "equity_policy_action": row.equity_policy_action,
            "equity_policy_size_pct": row.equity_policy_size_pct,
            "equity_policy_rationale": row.equity_policy_rationale,
            "company_snapshot_date": (
                row.company_snapshot_date.isoformat()
                if row.company_snapshot_date is not None
                else None
            ),
        }
        return d

    payload = {
        "as_of": brief.as_of.isoformat(),
        "generated_at": brief.generated_at.isoformat(),
        "source_mode": brief.source_mode,
        "reference_snapshot_date": (
            brief.reference_snapshot_date.isoformat()
            if brief.reference_snapshot_date is not None
            else None
        ),
        "n_universe": brief.n_universe,
        "n_with_spread": brief.n_with_spread,
        "n_expert_notes": brief.n_expert_notes,
        "n_recent_events": brief.n_recent_events,
        "n_requires_recompute": brief.n_requires_recompute,
        "calibration": {
            "n_outcomes": brief.calibration.n_outcomes,
            "n_bins_calibrated": brief.calibration.n_bins_calibrated,
            "is_live": brief.calibration.is_live,
        },
        "rows": [_row_dict(r) for r in brief.rows[:top_n]],
    }
    return json.dumps(payload, indent=2)


if __name__ == "__main__":
    main()
