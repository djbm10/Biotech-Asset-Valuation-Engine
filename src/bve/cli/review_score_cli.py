"""bve-review-score — resolve held scanner score-update movements.

Commit 3 of the live scanner score-update contract. The weekly gate holds material
or major-event score moves at the prior value and records a pending ``score_update``.
This CLI lets an analyst resolve them:

    bve-review-score list
    bve-review-score approve --id su-xxxx --reviewer doug --rationale "confirmed readout"
    bve-review-score reject  --ticker SRPT --reviewer doug --rationale "already priced in"

approve → the held new_score publishes on the next weekly run; reject → the prior
score is kept. Both log reviewer + rationale + timestamp and write an append-only
audit_log row linked by review_decision_id. Resolved movements are suppressed from
the pending queue; a NEW event for the same asset re-triggers a fresh pending item.

Scope: scanner composite-score updates only — does NOT touch the rNPV valuation
review flow (review_app / valuation_diffs) or ingestion.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

_DEFAULT_DB = Path(__file__).parent.parent.parent.parent / "outputs" / "intelligence" / "ops.db"


def _store(db: Optional[str]):
    from bve.intelligence.knowledge_layer import KnowledgeStore

    return KnowledgeStore(Path(db) if db else _DEFAULT_DB)


def _cmd_list(args: argparse.Namespace) -> int:
    store = _store(args.db)
    try:
        rows = store.get_score_updates(status="pending", asset_id=args.asset_id, limit=args.limit)
    finally:
        store.close()
    if not rows:
        print("No pending score updates.")
        return 0
    print(f"{len(rows)} pending score update(s):\n")
    for r in rows:
        print(f"  id={r.id}  asset={r.asset_id}  {r.prior_score}→{r.new_score} "
              f"({r.delta:+.3f})  events={','.join(r.contributing_event_ids) or '-'}")
    return 0


def _resolve(args: argparse.Namespace, action: str) -> int:
    store = _store(args.db)
    try:
        su_id = args.id
        if su_id is None:
            if not args.ticker and not args.asset_id:
                print("ERROR: provide --id, or --asset-id/--ticker to resolve the latest pending.")
                return 2
            pending = store.get_score_updates(status="pending", asset_id=args.asset_id, limit=50)
            if args.ticker and not args.asset_id:
                # asset_id unknown; match by the audit detail is not available here, so
                # require --asset-id when not using --id. Keep it explicit + safe.
                print("ERROR: resolving by ticker requires --asset-id (asset is the stored key).")
                return 2
            if not pending:
                print("No matching pending score update.")
                return 1
            su_id = pending[0].id

        result = store.resolve_score_update(
            su_id, action=action, reviewer=args.reviewer, rationale=args.rationale,
        )
        if result is None:
            print(f"No score update found with id={su_id}.")
            return 1
        verb = "APPROVED" if action == "approve" else "REJECTED"
        published = result.new_score if action == "approve" else result.prior_score
        print(f"{verb}: {result.asset_id} {result.prior_score}→{result.new_score} "
              f"({result.delta:+.3f}) — published score will be {published} on next run.")
        print(f"  review_decision_id={result.review_decision_id}  reviewer={result.reviewer}")
        return 0
    except ValueError as e:
        print(f"ERROR: {e}")
        return 2
    finally:
        store.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-review-score",
        description="Resolve held scanner score-update movements (approve/reject).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List pending score updates")
    p_list.add_argument("--asset-id", default=None)
    p_list.add_argument("--limit", type=int, default=100)
    p_list.add_argument("--db", default=None)

    for name in ("approve", "reject"):
        p = sub.add_parser(name, help=f"{name.capitalize()} a held score update")
        p.add_argument("--id", default=None, help="score_update id (preferred)")
        p.add_argument("--asset-id", default=None, help="resolve latest pending for this asset")
        p.add_argument("--ticker", default=None, help="(display only; use --asset-id to target)")
        p.add_argument("--reviewer", default=None)
        p.add_argument("--rationale", default=None)
        p.add_argument("--db", default=None)

    args = parser.parse_args(argv)
    if args.command == "list":
        return _cmd_list(args)
    return _resolve(args, args.command)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
