"""
CLI entry point: bve-compute-event-scores

Reads resolved event_outcomes from KnowledgeStore, computes EWM impact scores
stratified by (event_type, trial_phase, endpoint_type), and upserts results.

Usage
-----
    bve-compute-event-scores --db outputs/intelligence_phase2/knowledge.db
    bve-compute-event-scores --db knowledge.db --active-only
    bve-compute-event-scores --db knowledge.db --min-obs 10 --half-life 90
"""
from __future__ import annotations

import argparse

from bve.intelligence.event_impact_ledger import EventImpactLedger, MIN_OBSERVATIONS, HALF_LIFE_DAYS
from bve.intelligence.knowledge_layer import KnowledgeStore


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Compute EWM event impact scores from resolved outcomes"
    )
    p.add_argument(
        "--db",
        default="outputs/intelligence_phase2/knowledge.db",
        help="Path to KnowledgeStore SQLite database",
    )
    p.add_argument(
        "--min-obs",
        type=int,
        default=MIN_OBSERVATIONS,
        help=f"Minimum observations to activate a score (default: {MIN_OBSERVATIONS})",
    )
    p.add_argument(
        "--half-life",
        type=float,
        default=HALF_LIFE_DAYS,
        help=f"EWM half-life in calendar days (default: {HALF_LIFE_DAYS})",
    )
    p.add_argument(
        "--active-only",
        action="store_true",
        help="Print only scores with enough observations to be active",
    )
    return p


def _print_table(scores: list, active_only: bool) -> None:
    display = [s for s in scores if s.active] if active_only else scores
    if not display:
        print("No scores found" + (" (active_only=True)" if active_only else "") + ".")
        return

    header = (
        f"{'EventType':<30}  {'Phase':<10}  {'Endpoint':<10}  "
        f"{'N':>5}  {'Active':>6}  {'T30 Mean':>10}  {'T180 Mean':>10}"
    )
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)
    for s in sorted(display, key=lambda x: x.category.event_type):
        t30 = f"{s.mean_return_t30:+.4f}" if s.mean_return_t30 is not None else "n/a"
        t180 = f"{s.mean_return_t180:+.4f}" if s.mean_return_t180 is not None else "n/a"
        print(
            f"{s.category.event_type:<30}  "
            f"{(s.category.trial_phase or ''):<10}  "
            f"{(s.category.endpoint_type or ''):<10}  "
            f"{s.observation_count:>5}  "
            f"{'yes' if s.active else 'no':>6}  "
            f"{t30:>10}  "
            f"{t180:>10}"
        )
    print(sep)
    active_count = sum(1 for s in scores if s.active)
    print(
        f"\n{len(scores)} score(s) computed, {active_count} active "
        f"(≥ {scores[0].half_life_days if scores else HALF_LIFE_DAYS:.0f}d half-life)."
    )


def main() -> None:
    args = _build_parser().parse_args()
    store = KnowledgeStore(db_path=args.db)
    try:
        ledger = EventImpactLedger(
            min_observations=args.min_obs,
            half_life_days=args.half_life,
        )
        scores = ledger.run(store)
    finally:
        store.close()

    _print_table(scores, args.active_only)


if __name__ == "__main__":
    main()
