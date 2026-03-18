"""CLI for reporting latest asset-level data-quality status."""

from __future__ import annotations

import argparse
import json

from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.ops.data_quality import DataQualityMonitor, score_rows_to_json


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Report latest data-quality scores")
    p.add_argument(
        "--db",
        default="outputs/intelligence_phase2/knowledge.db",
        help="Path to knowledge store SQLite DB",
    )
    p.add_argument(
        "--asset",
        default=None,
        help="Optional asset_id; when omitted, returns latest score per asset",
    )
    p.add_argument(
        "--gated-only",
        action="store_true",
        help="Only show assets currently gated by quality threshold",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Maximum number of assets/rows to display",
    )
    return p


def _render_table(scores) -> None:
    print("asset_id\toverall_score\tgated\tfailing_checks\tgenerated_at")
    for score in scores:
        failing = ",".join(score.failing_checks) if score.failing_checks else "-"
        print(
            f"{score.asset_id}\t{score.overall_score:.4f}\t{int(score.gated)}\t"
            f"{failing}\t{score.generated_at.isoformat()}"
        )


def main() -> None:
    args = _build_parser().parse_args()
    store = KnowledgeStore(args.db)
    try:
        monitor = DataQualityMonitor(store)
        if args.asset:
            score = store.get_latest_data_quality(args.asset)
            if score is None:
                score = monitor.check_asset(args.asset)
            scores = [score]
        else:
            scores = store.list_latest_data_quality(limit=max(1, args.limit))
            if not scores:
                rows = store._conn.execute(
                    """
                    SELECT asset_id
                    FROM asset_registry
                    WHERE asset_id IS NOT NULL AND asset_id <> ''
                    ORDER BY asset_id ASC
                    LIMIT ?
                    """,
                    (max(1, args.limit),),
                ).fetchall()
                if rows:
                    scores = monitor.check_all([str(row["asset_id"]) for row in rows])

        if args.gated_only:
            scores = [score for score in scores if score.gated]

        scores.sort(key=lambda s: (s.gated is False, s.overall_score, s.asset_id))
        if args.json:
            print(json.dumps(score_rows_to_json(scores), ensure_ascii=True, indent=2))
            return

        if not scores:
            print("No data quality records found.")
            return
        _render_table(scores)
    finally:
        store.close()


if __name__ == "__main__":
    main()
