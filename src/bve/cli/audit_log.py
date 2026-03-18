"""
CLI entry point: bve-audit-log

Queries the append-only audit_log table and prints entries in reverse
chronological order.  Useful for inspecting review decisions and tracing
the history of any proposal.

Usage
-----
    bve-audit-log --db outputs/intelligence_phase2/knowledge.db
    bve-audit-log --db knowledge.db --entity-type proposal
    bve-audit-log --db knowledge.db --actor-id analyst@firm.com --limit 20
    bve-audit-log --db knowledge.db --action accepted
"""
from __future__ import annotations

import argparse
import json

from bve.intelligence.knowledge_layer import KnowledgeStore


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Inspect the append-only audit log of review decisions"
    )
    p.add_argument(
        "--db",
        default="outputs/intelligence_phase2/knowledge.db",
        help="Path to KnowledgeStore SQLite database",
    )
    p.add_argument("--entity-type", default=None, help="Filter by entity_type (e.g. 'proposal')")
    p.add_argument("--entity-id",   default=None, help="Filter by entity_id (e.g. proposal UUID)")
    p.add_argument("--actor-id",    default=None, help="Filter by actor_id (reviewer identifier)")
    p.add_argument("--action",      default=None, help="Filter by action (accepted/rejected/deferred)")
    p.add_argument("--limit",       type=int, default=50, help="Maximum rows to display (default: 50)")
    p.add_argument("--json",        action="store_true", help="Output as JSON array instead of table")
    return p


def _print_table(rows: list[dict]) -> None:
    if not rows:
        print("No audit log entries found.")
        return
    sep = "-" * 100
    print(sep)
    print(
        f"  {'Timestamp':<24}  {'Action':<10}  {'Entity':<12}  "
        f"{'EntityID':<36}  {'Actor':<20}"
    )
    print(sep)
    for r in rows:
        ts = r["created_at"][:19].replace("T", " ")
        entity_id = r["entity_id"][:34] + ".." if len(r["entity_id"]) > 36 else r["entity_id"]
        actor = (r["actor_id"] or "")[:20]
        print(
            f"  {ts:<24}  {r['action']:<10}  {r['entity_type']:<12}  "
            f"{entity_id:<36}  {actor:<20}"
        )
        try:
            payload = json.loads(r["payload_json"])
            confidence = payload.get("reviewer_confidence")
            tags = payload.get("analyst_tags") or []
            quote = payload.get("supporting_quote")
            if confidence is not None:
                print(f"    confidence={confidence:.2f}", end="")
            if tags:
                print(f"  tags={tags}", end="")
            if quote:
                short = quote[:80] + "…" if len(quote) > 80 else quote
                print(f'\n    quote: "{short}"', end="")
            if confidence is not None or tags or quote:
                print()
        except (json.JSONDecodeError, KeyError):
            pass
    print(sep)
    print(f"  {len(rows)} entry/entries displayed.")
    print(sep)


def main() -> None:
    args = _build_parser().parse_args()
    store = KnowledgeStore(db_path=args.db)
    try:
        rows = store.query_audit_log(
            entity_type=args.entity_type,
            entity_id=args.entity_id,
            actor_id=args.actor_id,
            action=args.action,
            limit=args.limit,
        )
    finally:
        store.close()

    if args.json:
        print(json.dumps(rows, indent=2, default=str))
    else:
        _print_table(rows)


if __name__ == "__main__":
    main()
