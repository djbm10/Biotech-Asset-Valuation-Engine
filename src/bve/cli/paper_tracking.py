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
_DEFAULT_ROLLING_HOLDOUT_REPORT = Path("outputs/analysis/rolling_holdout.json")


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


def _compute_paper_score(snap: object) -> tuple[Optional[float], str, list[str]]:
    """Compute a multi-signal paper tracking score from a BacktestSnapshot.

    Returns
    -------
    (score, recommendation, risk_flags)

    A high ``composite_score`` alone is not sufficient to produce an "add"
    recommendation.  At least one corroborating signal (valuation gap OR
    catalyst score OR science confidence) must be present.  When corroborating
    signals are absent the recommendation is capped at "watch" and a
    ``insufficient_data`` risk flag is added.

    Composite formula (when all signals present):
        0.45 × composite_score
      + 0.25 × valuation_gap_score    (mispricing_score clamped to [0,1])
      + 0.20 × catalyst_score         (clamped to [0,1])
      + 0.10 × science_confidence     (extraction_confidence clamped to [0,1])

    Absent signals are filled with the neutral value (0.5) and counted.
    If all three corroborating signals are absent, the score is overridden to
    ``None`` and recommendation is "watch/insufficient_data".
    """
    raw_model = getattr(snap, "composite_score", None)
    raw_valuation = getattr(snap, "mispricing_score", None)
    raw_catalyst = getattr(snap, "catalyst_score", None)
    raw_confidence = getattr(snap, "extraction_confidence", None)

    risk_flags: list[str] = []

    # Identify absent corroborating signals
    missing_signals: list[str] = []
    if raw_valuation is None:
        missing_signals.append("valuation_gap")
    if raw_catalyst is None:
        missing_signals.append("catalyst_score")
    if raw_confidence is None:
        missing_signals.append("science_confidence")

    # If model score is also absent — complete data gap
    if raw_model is None and len(missing_signals) == 3:
        return None, "watch", ["insufficient_data"]

    # If ALL three corroborating signals missing — cap at watch
    if len(missing_signals) == 3:
        risk_flags.append("insufficient_data")
        recommendation = _score_to_recommendation(raw_model)
        if recommendation == "add":
            recommendation = "watch"
        return raw_model, recommendation, risk_flags

    # At least one corroborating signal present — build composite
    def _clamp01(v: Optional[float], neutral: float = 0.5) -> float:
        if v is None:
            return neutral
        return max(0.0, min(1.0, float(v)))

    model_score = _clamp01(raw_model)
    valuation_gap = _clamp01(raw_valuation)
    catalyst = _clamp01(raw_catalyst)
    confidence = _clamp01(raw_confidence)

    composite = (
        0.45 * model_score
        + 0.25 * valuation_gap
        + 0.20 * catalyst
        + 0.10 * confidence
    )
    composite = round(composite, 6)

    if missing_signals:
        risk_flags.append(f"missing_signals:{','.join(missing_signals)}")

    if composite < 0.30:
        risk_flags.append("low_score")

    recommendation = _score_to_recommendation(composite)
    return composite, recommendation, risk_flags


# ---------------------------------------------------------------------------
# Sprint 23 Task 5 helpers
# ---------------------------------------------------------------------------


def _load_ece_gate_passes(report_path: Path) -> bool:
    """Return True only if a saved rolling holdout report shows all ECE gates pass.

    If the file does not exist or cannot be parsed, returns False (conservative).
    Do NOT call the calibrated score a probability unless this returns True.
    """
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
        return bool(data.get("calibration_gate_passes", False))
    except Exception:
        return False


def _extract_ma_snapshot_fields(
    conn,
    snap_date: date,
    asset_id: str,
) -> dict:
    """Query ma_probability_snapshots for Sprint 23 diagnostic fields.

    Returns a dict with keys: watchlist_type, calibrated_score,
    transaction_driver_count, gate_reason_codes (list[str]),
    top5_acquirers (list[str]).

    Returns empty dict if no snapshot found.
    """
    try:
        row = conn.execute(
            """
            SELECT watchlist_type, p_takeout_calibrated,
                   transaction_driver_count, acquirer_candidates_json
            FROM ma_probability_snapshots
            WHERE asset_id = ? AND snapshot_date <= ?
            ORDER BY snapshot_date DESC
            LIMIT 1
            """,
            (asset_id, snap_date.isoformat()),
        ).fetchone()
    except Exception:
        return {}

    if row is None:
        return {}

    result: dict = {}
    result["watchlist_type"] = row[0]  # watchlist_type
    result["calibrated_score"] = row[1]  # p_takeout_calibrated
    result["transaction_driver_count"] = row[2]  # transaction_driver_count

    # Extract gate_reason_codes and top5_acquirers from candidates JSON
    candidates_json = row[3]
    gate_codes: list[str] = []
    top5: list[str] = []
    if candidates_json:
        try:
            candidates = json.loads(candidates_json)
            for cand in candidates[:5]:
                name = cand.get("acquirer_name") or cand.get("acquirer_id", "")
                if name:
                    top5.append(name)
            # Gate reason codes from the best candidate (first in sorted order)
            if candidates:
                codes = candidates[0].get("transaction_gate_reason_codes") or []
                gate_codes = list(codes)
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass

    result["gate_reason_codes"] = gate_codes if gate_codes else None
    result["top5_acquirers"] = top5 if top5 else None
    return result


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
    parser.add_argument(
        "--holdout-report",
        default=str(_DEFAULT_ROLLING_HOLDOUT_REPORT),
        help=(
            "Path to rolling holdout JSON (default: outputs/analysis/rolling_holdout.json). "
            "Used to determine whether calibrated_score may be labelled as a probability. "
            "If the file is absent or calibration gate fails, score is labelled 'rank_score'."
        ),
    )
    args = parser.parse_args(argv)

    snap_date = date.fromisoformat(args.date) if args.date else date.today()
    since_date = snap_date - timedelta(days=args.lookback_days)

    # Determine calibration label: conservative default — only call it a
    # probability when the rolling ECE gate has been validated.
    ece_gate_passes = _load_ece_gate_passes(Path(args.holdout_report))
    calibrated_score_label = "probability_estimate" if ece_gate_passes else "rank_score"

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

        composite_score, recommendation, risk_flags = _compute_paper_score(snap)

        entry_id = str(uuid.uuid4())
        catalyst_type = getattr(snap, "catalyst_type", None)
        catalyst_date = getattr(snap, "catalyst_date", None)
        catalyst_str = f"{catalyst_type} {catalyst_date}" if catalyst_type else None

        # Sprint 23 Task 5: pull diagnostic fields from ma_probability_snapshots
        ma_fields = _extract_ma_snapshot_fields(store._conn, snap_date, asset_id)

        if args.dry_run:
            wt = ma_fields.get("watchlist_type") or "—"
            cal = ma_fields.get("calibrated_score")
            cal_str = f"{cal:.3f}" if cal is not None else "—"
            print(
                f"[DRY-RUN] {snap_date} | {asset_id} ({ticker or '—'}) | "
                f"{recommendation} | score={composite_score} | "
                f"watchlist={wt} | calibrated={cal_str}({calibrated_score_label})"
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
                composite_score=composite_score,
                catalyst=catalyst_str,
                risk_flags=risk_flags if risk_flags else None,
                watchlist_type=ma_fields.get("watchlist_type"),
                calibrated_score=ma_fields.get("calibrated_score"),
                calibrated_score_label=calibrated_score_label if ma_fields.get("calibrated_score") is not None else None,
                transaction_driver_count=ma_fields.get("transaction_driver_count"),
                gate_reason_codes=ma_fields.get("gate_reason_codes"),
                top5_acquirers=ma_fields.get("top5_acquirers"),
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
    col = (12, 14, 10, 8, 6, 7, 18, 7, 6, 24)
    header = (
        f"{'Date':<{col[0]}} {'AssetID':<{col[1]}} {'Ticker':<{col[2]}} "
        f"{'Rec':<{col[3]}} {'Score':>{col[4]}} {'MnA%':>{col[5]}} "
        f"{'Watchlist':<{col[6]}} {'Cal':>{col[7]}} {'Drvrs':>{col[8]}} "
        f"{'Catalyst':<{col[9]}}"
    )
    print(header)
    print("-" * len(header))
    for row in entries:
        score_str = f"{row['composite_score']:.2f}" if row.get("composite_score") is not None else "—"
        mna_str = f"{row['mna_likelihood']:.2f}" if row.get("mna_likelihood") is not None else "—"
        wt = (row.get("watchlist_type") or "—")[:col[6] - 1]
        cal_val = row.get("calibrated_score")
        cal_label = row.get("calibrated_score_label") or ""
        if cal_val is not None:
            prefix = "P" if cal_label == "probability_estimate" else "R"
            cal_str = f"{prefix}{cal_val:.3f}"
        else:
            cal_str = "—"
        drvrs = str(row["transaction_driver_count"]) if row.get("transaction_driver_count") is not None else "—"
        catalyst_str = (row.get("catalyst") or "")[:col[9] - 1]
        print(
            f"{row['snapshot_date']:<{col[0]}} "
            f"{(row['asset_id'] or '')[:col[1]-1]:<{col[1]}} "
            f"{(row['ticker'] or '—'):<{col[2]}} "
            f"{row['recommendation']:<{col[3]}} "
            f"{score_str:>{col[4]}} "
            f"{mna_str:>{col[5]}} "
            f"{wt:<{col[6]}} "
            f"{cal_str:>{col[7]}} "
            f"{drvrs:>{col[8]}} "
            f"{catalyst_str:<{col[9]}}"
        )

    print(f"\nTotal: {len(entries)} entries  (since {since})")
