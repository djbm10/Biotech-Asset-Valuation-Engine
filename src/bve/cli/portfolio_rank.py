"""
CLI entry point: bve-portfolio-rank

Ranks tracked assets into indication clusters, applies portfolio constraints,
and prints a table of top opportunities grouped by cluster.

Usage
-----
    bve-portfolio-rank --db outputs/intelligence_phase2/knowledge.db
    bve-portfolio-rank --db knowledge.db --min-confidence 0.7 --top-n 10
    bve-portfolio-rank --db knowledge.db --max-age-days 30 --min-delta 25 --json
"""
from __future__ import annotations

import argparse


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Rank and cluster portfolio opportunities from the KnowledgeStore"
    )
    p.add_argument(
        "--db",
        default="outputs/intelligence_phase2/knowledge.db",
        help="Path to KnowledgeStore SQLite database",
    )
    p.add_argument(
        "--min-confidence",
        type=float,
        default=0.0,
        help="Minimum extraction confidence (0.0–1.0, default: 0.0 = no filter)",
    )
    p.add_argument(
        "--max-age-days",
        type=int,
        default=None,
        help="Maximum diff age in calendar days (default: no filter)",
    )
    p.add_argument(
        "--min-delta",
        type=float,
        default=None,
        help="Minimum |ΔNPV| in $M (default: no filter)",
    )
    p.add_argument(
        "--accepted-only",
        action="store_true",
        help="Only include diffs with an accepted review_decision",
    )
    p.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Number of top clusters to display (default: 10)",
    )
    p.add_argument(
        "--cluster-edge",
        default="same_indication",
        help='KG edge type for clustering (default: "same_indication")',
    )
    p.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output raw JSON instead of a table",
    )
    return p


def _print_table(result) -> None:
    sep = "-" * 80
    print(sep)
    print(f"  PORTFOLIO RANKING   ranked at {result.ranked_at.strftime('%Y-%m-%d %H:%M UTC')}")
    print(sep)
    print(
        f"  Assets evaluated: {result.n_assets_evaluated}  |  "
        f"Filtered: conf={result.n_filtered_confidence} "
        f"age={result.n_filtered_age} "
        f"size={result.n_filtered_magnitude} "
        f"review={result.n_filtered_not_accepted}"
    )
    print(sep)

    if not result.clusters:
        print("  No clusters to display.")
        print(sep)
        return

    header = f"  {'#':<3}  {'Label':<28}  {'Assets':>6}  {'ΔNPV($M)':>10}  {'Adj ΔNPV':>10}  {'Pending':>7}  {'Top Asset'}"
    print(header)
    print(f"  {'-'*3}  {'-'*28}  {'-'*6}  {'-'*10}  {'-'*10}  {'-'*7}  {'-'*20}")

    for i, cl in enumerate(result.clusters, start=1):
        label = cl.cluster_label[:28]
        delta = f"{cl.combined_delta_npv_millions:+.1f}"
        adj   = f"{cl.combined_confidence_weighted_delta_npv_millions:+.1f}"
        print(
            f"  {i:<3}  {label:<28}  {cl.n_assets:>6}  {delta:>10}  {adj:>10}  "
            f"{cl.n_pending_review:>7}  {cl.top_asset_id or '—'}"
        )

    print(sep)


def main() -> None:
    args = _build_parser().parse_args()

    from bve.intelligence.knowledge_layer import KnowledgeStore
    from bve.intelligence.portfolio_ranking import PortfolioConstraints, PortfolioRankingEngine

    constraints = PortfolioConstraints(
        min_confidence=args.min_confidence,
        max_queue_age_days=args.max_age_days,
        min_abs_delta_npv_millions=args.min_delta,
        require_accepted_review=args.accepted_only,
        cluster_edge_type=args.cluster_edge,
        top_n=args.top_n,
    )

    store = KnowledgeStore(db_path=args.db)
    try:
        engine = PortfolioRankingEngine(constraints=constraints)
        result = engine.rank(store)
    finally:
        store.close()

    if args.as_json:
        print(result.model_dump_json(indent=2))
    else:
        _print_table(result)


if __name__ == "__main__":
    main()
