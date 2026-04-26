"""Forward paper tracking log CLI.

Two entry points:

    bve-paper-snapshot  [--db PATH] [--date YYYY-MM-DD]
        Capture today's paper recommendations from the latest backtest
        snapshots and write them to the paper_tracking_log table.

    bve-paper-summary   [--db PATH] [--days N]
        Print a summary table of recent paper tracking entries.
"""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

_DEFAULT_DB = Path("outputs/intelligence/ops.db")


# ---------------------------------------------------------------------------
# Helper — score → recommendation label
# ---------------------------------------------------------------------------


def _score_to_recommendation(score: Optional[float]) -> str:
    """Map a composite score to a paper recommendation label."""
    if score is None:
        return "watch"
    if score >= 0.65:
        return "add"
    if score >= 0.45:
        return "hold"
    if score >= 0.25:
        return "watch"
    return "avoid"


# ---------------------------------------------------------------------------
# Snapshot command
# ---------------------------------------------------------------------------


def snapshot_main(argv: Optional[list[str]] = None) -> None:
    """Capture paper tracking snapshots from the latest knowledge store signals."""
    parser = argparse.ArgumentParser(
        prog="bve-paper-snapshot",
        description="Write paper tracking snapshot rows to paper_tracking_log.",
    )
    parser.add_argument(
        "--db",
        default=str(_DEFAULT_DB),
        help="Path to the knowledge store SQLite database (default: outputs/intelligence/ops.db).",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Snapshot date in YYYY-MM-DD format (default: today).",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=90,
        help="How many days back to pull signals from (default: 90).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without modifying the database.",
    )
    args = parser.parse_args(argv)

    snap_date = date.fromisoformat(args.date) if args.date else date.today()
    since_date = snap_date - timedelta(days=args.lookback_days)

    from bve.intelligence.knowledge_layer import KnowledgeStore

    store = KnowledgeStore(args.db)
    try:
        snapshots = store.get_backtest_snapshots(since=since_date)
    except Exception as exc:
        print(f"[ERROR] Failed to read backtest snapshots: {exc}")
        store.close()
        return

    if not snapshots:
        print(f"No backtest snapshots found since {since_date} in {args.db!r}.")
        store.close()
        return

    # Deduplicate: keep the highest-scoring snapshot per asset
    best: dict[str, object] = {}
    for snap in snapshots:
        prev = best.get(snap.asset_id)
        if prev is None or (snap.composite_score or 0.0) > (prev.composite_score or 0.0):  # type: ignore[attr-defined]
            best[snap.asset_id] = snap

    written = 0
    skipped = 0
    for asset_id, snap in sorted(best.items()):
        ticker_entry = store.get_asset_registry_entry(asset_id)
        ticker = getattr(ticker_entry, "ticker", None) if ticker_entry else None

        score = snap.composite_score  # type: ignore[attr-defined]
        recommendation = _score_to_recommendation(score)

        entry_id = str(uuid.uuid4())
        risk_flags: list[str] = []
        if score is not None and score < 0.30:
            risk_flags.append("low_score")
        catalyst_type = getattr(snap, "catalyst_type", None)
        catalyst_date = getattr(snap, "catalyst_date", None)
        catalyst_str = f"{catalyst_type} {catalyst_date}" if catalyst_type else None

        if args.dry_run:
            print(
                f"[DRY-RUN] {snap_date} | {asset_id} ({ticker or '—'}) | "  # type: ignore[attr-defined]
                f"{recommendation} | score={score}"
            )
            skipped += 1
            continue

        try:
            store.write_paper_tracking_entry(
                entry_id=entry_id,
                snapshot_date=snap_date,
                asset_id=asset_id,
                recommendation=recommendation,
                ticker=ticker,
                composite_score=score,
                catalyst=catalyst_str,
                risk_flags=risk_flags if risk_flags else None,
            )
            written += 1
        except Exception as exc:
            print(f"[WARN] Failed to write entry for {asset_id}: {exc}")

    store.close()

    if args.dry_run:
        print(f"Dry-run complete. Would have written {skipped} entries for {snap_date}.")
    else:
        print(f"Paper snapshot complete: {written} entries written for {snap_date}.")


# ---------------------------------------------------------------------------
# Summary command
# ---------------------------------------------------------------------------


def summary_main(argv: Optional[list[str]] = None) -> None:
    """Print a summary table of recent paper tracking entries."""
    parser = argparse.ArgumentParser(
        prog="bve-paper-summary",
        description="Display recent paper tracking log entries.",
    )
    parser.add_argument(
        "--db",
        default=str(_DEFAULT_DB),
        help="Path to the knowledge store SQLite database.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="How many days back to display (default: 30).",
    )
    parser.add_argument(
        "--asset",
        default=None,
        help="Filter to a specific asset_id.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Maximum rows to display (default: 200).",
    )
    args = parser.parse_args(argv)

    since = date.today() - timedelta(days=args.days)

    from bve.intelligence.knowledge_layer import KnowledgeStore

    store = KnowledgeStore(args.db)
    try:
        entries = store.get_paper_tracking_entries(
            since=since,
            asset_id=args.asset,
            limit=args.limit,
        )
    except Exception as exc:
        print(f"[ERROR] Failed to read paper tracking log: {exc}")
        store.close()
        return
    finally:
        store.close()

    if not entries:
        print(f"No paper tracking entries found since {since}.")
        return

    # Render table
    col = (12, 14, 14, 8, 6, 7, 8, 30)
    header = (
        f"{'Date':<{col[0]}} {'AssetID':<{col[1]}} {'Ticker':<{col[2]}} "
        f"{'Rec':<{col[3]}} {'Score':>{col[4]}} {'MnA%':>{col[5]}} "
        f"{'Flags':<{col[6]}} {'Catalyst':<{col[7]}}"
    )
    print(header)
    print("-" * len(header))
    for row in entries:
        flags = ""
        if row.get("risk_flags"):
            try:
                flags = ",".join(json.loads(row["risk_flags"]))
            except (json.JSONDecodeError, TypeError):
                flags = str(row["risk_flags"])[:8]
        score_str = f"{row['composite_score']:.2f}" if row.get("composite_score") is not None else "—"
        mna_str = f"{row['mna_likelihood']:.2f}" if row.get("mna_likelihood") is not None else "—"
        catalyst_str = (row.get("catalyst") or "")[:28]
        print(
            f"{row['snapshot_date']:<{col[0]}} "
            f"{(row['asset_id'] or '')[:col[1]-1]:<{col[1]}} "
            f"{(row['ticker'] or '—'):<{col[2]}} "
            f"{row['recommendation']:<{col[3]}} "
            f"{score_str:>{col[4]}} "
            f"{mna_str:>{col[5]}} "
            f"{flags:<{col[6]}} "
            f"{catalyst_str:<{col[7]}}"
        )

    print(f"\nTotal: {len(entries)} entries  (since {since})")
