"""CLI entry point: bve-ma-grade — grade logged M&A probability predictions.

Loads the ops.db snapshot store, joins logged predictions to known deal
outcomes, and prints a calibration report (P@K, precision, recall, lead days).

Usage::

    bve-ma-grade
    bve-ma-grade --from 2025-01-01 --to 2026-06-01
    bve-ma-grade --lookahead 180 --top-k 10
    bve-ma-grade --baselines   # also compare transparent feature baselines
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_db_path() -> Path:
    return _repo_root() / "outputs" / "intelligence" / "ops.db"


def _default_deal_universe_path() -> Path:
    return _repo_root() / "research" / "mna" / "deal_universe_2020_2026.yaml"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Grade logged M&A probability predictions against actual deal outcomes"
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Path to KnowledgeStore SQLite (default: outputs/intelligence/ops.db)",
    )
    parser.add_argument(
        "--deal-universe",
        default=None,
        help="Path to deal universe YAML (default: research/mna/deal_universe_2020_2026.yaml)",
    )
    parser.add_argument(
        "--from",
        dest="from_date",
        default=None,
        help="Start date for snapshot window YYYY-MM-DD (default: all history)",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        default=None,
        help="End date for snapshot window YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--lookahead",
        type=int,
        default=365,
        help="Lookahead days to match deal outcomes (default: 365)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=15,
        help="K for precision@K (default: 15)",
    )
    parser.add_argument(
        "--baselines",
        action="store_true",
        default=False,
        help="Also compare transparent feature baselines",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else _default_db_path()
    if not db_path.exists():
        print(
            f"ERROR: KnowledgeStore not found at {db_path}.\n"
            "Run 'python -m bve.ops.weekly_runner seed' first, then run the M&A scan.",
            file=sys.stderr,
        )
        sys.exit(1)

    deal_universe_path = (
        Path(args.deal_universe) if args.deal_universe else _default_deal_universe_path()
    )
    if not deal_universe_path.exists():
        print(
            f"ERROR: Deal universe YAML not found at {deal_universe_path}.",
            file=sys.stderr,
        )
        sys.exit(1)

    from_date = date.fromisoformat(args.from_date) if args.from_date else None
    to_date = date.fromisoformat(args.to_date) if args.to_date else None

    try:
        from bve.intelligence.knowledge_layer import KnowledgeStore
        from bve.intelligence.ma_calibration import MACalibrationDatasetBuilder
        from bve.intelligence.ma_probability import MAProbabilitySnapshotStore
    except ImportError as exc:
        print(f"ERROR: import failed — {exc}", file=sys.stderr)
        sys.exit(1)

    store = KnowledgeStore(str(db_path))
    snapshot_store = MAProbabilitySnapshotStore(store)

    # Check how many snapshots exist before building the dataset
    all_snapshots = snapshot_store.list_snapshots(start_date=from_date, end_date=to_date)
    n_snapshots = len(all_snapshots)
    n_dates = len({s.snapshot_date for s in all_snapshots})

    print()
    print("=" * 65)
    print("  BVE M&A Prediction Grade Report")
    print("=" * 65)
    print(f"  KnowledgeStore : {db_path}")
    print(f"  Deal universe  : {deal_universe_path}")
    date_range = (
        f"{from_date or 'all'} → {to_date or date.today()}"
    )
    print(f"  Window         : {date_range}")
    print(f"  Lookahead days : {args.lookahead}")
    print(f"  Top-K          : {args.top_k}")
    print()

    if n_snapshots == 0:
        print("  ⚠  No M&A probability snapshots found in the store.")
        print("  Run 'python -m bve.ops.weekly_runner mna' to log the first predictions.")
        print()
        store.close()
        return

    print(f"  Snapshots found: {n_snapshots} rows across {n_dates} scan date(s)")
    print()

    builder = MACalibrationDatasetBuilder(
        knowledge_store=store,
        deal_universe_path=str(deal_universe_path),
        snapshot_store=snapshot_store,
    )

    dataset = builder.build_dataset(
        lookahead_days=args.lookahead,
        start_date=from_date,
        end_date=to_date,
    )

    if dataset.n_rows == 0:
        print("  ⚠  Dataset is empty after joining snapshots to deal outcomes.")
        print("  This is expected when scanning has just started —")
        print("  predictions need time to resolve before grading is meaningful.")
        print()
        store.close()
        return

    metrics = builder.evaluate(dataset, top_k=args.top_k)

    # ── Core metrics ──────────────────────────────────────────────────────────
    print(f"  Dataset        : {metrics.n_rows} rows "
          f"({metrics.n_positive_rows} positive / "
          f"{metrics.n_rows - metrics.n_positive_rows} control)")
    print(f"  Scan dates     : {metrics.n_snapshot_dates}")
    print(f"  Unique targets : {metrics.n_positive_targets} confirmed deals")
    print()

    p_at_k = metrics.precision_at_k
    recall = metrics.unique_target_recall_at_k
    lead = metrics.median_lead_days_at_k
    avg_pos = getattr(metrics, "avg_positive_probability", None)
    avg_ctrl = getattr(metrics, "avg_control_probability", None)

    print(f"  P@{args.top_k:<3}           : "
          f"{f'{p_at_k:.1%}' if p_at_k is not None else 'n/a'}")
    print(f"  Recall@{args.top_k:<3}       : "
          f"{f'{recall:.1%}' if recall is not None else 'n/a'} "
          f"({metrics.n_positive_targets_in_top_k}/{metrics.n_positive_targets} "
          f"deals captured in top-{args.top_k})")
    print(f"  Median lead    : "
          f"{f'{lead:.0f} days before announcement' if lead is not None else 'n/a'}")
    if avg_pos is not None and avg_ctrl is not None:
        print(f"  Avg score (pos): {avg_pos:.3f}")
        print(f"  Avg score (ctrl): {avg_ctrl:.3f}")
        separation = avg_pos - avg_ctrl
        print(f"  Score separation: {separation:+.3f} "
              f"({'good' if separation > 0.10 else 'weak' if separation > 0 else 'inverted'})")
    print()

    # ── Baselines comparison ──────────────────────────────────────────────────
    if args.baselines:
        try:
            baseline_result = builder.compare_baselines(dataset, top_k=args.top_k)
            baselines = getattr(baseline_result, "baselines", [])
            if baselines:
                print(f"  Transparent baseline comparison (P@{args.top_k})")
                print(f"  {'Baseline':<44}  {'P@K':>6}  {'Recall':>7}")
                print("  " + "─" * 62)
                for b in baselines:
                    b_p = getattr(b, "precision_at_k", None)
                    b_r = getattr(b, "unique_target_recall_at_k", None)
                    b_label = getattr(b, "label", "?")
                    p_str = f"{b_p:.1%}" if b_p is not None else "n/a"
                    r_str = f"{b_r:.1%}" if b_r is not None else "n/a"
                    print(f"  {b_label:<44}  {p_str:>6}  {r_str:>7}")
                print()
        except Exception as exc:  # noqa: BLE001
            print(f"  (Baselines comparison failed: {exc})")
            print()

    # ── Grading threshold ─────────────────────────────────────────────────────
    if metrics.n_positive_rows < 10:
        print("  ⚠  GRADE: Too few resolved positives for meaningful grading.")
        print(f"     Need ≥10 resolved deals; have {metrics.n_positive_rows}.")
        print("     Continue logging predictions and check again in 6–12 months.")
    elif p_at_k is not None and p_at_k >= 0.25:
        print(f"  ✓  GRADE: P@{args.top_k} = {p_at_k:.1%} — above random baseline.")
    else:
        p_str = f"{p_at_k:.1%}" if p_at_k is not None else "n/a"
        print(f"  ✗  GRADE: P@{args.top_k} = {p_str} — at or below random baseline.")
        print("     Review scoring weights or expand the scan universe.")
    print()

    store.close()


if __name__ == "__main__":
    main()
