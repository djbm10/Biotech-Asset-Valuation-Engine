"""
CLI entry point: bve-claim-resolve

Manage thesis claims in the live KnowledgeStore (ops.db).

Subcommands
-----------
    list                    — list open (and optionally all) claims
    resolve CLAIM_ID        — resolve a claim to confirmed / refuted / expired
    expire-overdue          — expire all open claims whose resolution_date has passed

Usage
-----
    bve-claim-resolve list
    bve-claim-resolve list --asset a-alny
    bve-claim-resolve list --all

    bve-claim-resolve resolve <CLAIM_ID> --status confirmed --evidence "KARDIA-2 primary endpoint met"
    bve-claim-resolve resolve <CLAIM_ID> --status refuted   --evidence "Trial missed primary endpoint"

    bve-claim-resolve expire-overdue
    bve-claim-resolve expire-overdue --as-of 2026-04-01
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.thesis_tracker import ThesisTracker
from bve.ops.weekly_runner import DB_PATH


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_store(db_path: Path) -> KnowledgeStore:
    return KnowledgeStore(str(db_path))


def _claim_row(claim) -> str:
    """One-line display for a claim."""
    status_tag = f"[{claim.status.upper():<9}]"
    res_date = (
        f"  resolve_by={claim.resolution_date.isoformat()}"
        if claim.resolution_date else ""
    )
    weight_tag = f"  w={claim.weight:.2f}"
    return (
        f"{status_tag}  {claim.claim_id[:8]}  "
        f"{claim.asset_id:<12}  {claim.claim_type.value:<28}  "
        f"{claim.assertion[:60]}{res_date}{weight_tag}"
    )


# ---------------------------------------------------------------------------
# Subcommand: list
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> None:
    store = _get_store(args.db)
    tt = ThesisTracker(store)

    status_filter = None if args.all else "open"
    claims = tt.get_claims(
        asset_id=args.asset,
        status=status_filter,
        limit=500,
    )

    if not claims:
        status_label = "any" if args.all else "open"
        asset_label = f" for {args.asset}" if args.asset else ""
        print(f"No {status_label} claims{asset_label}.")
        store.close()
        return

    status_groups: dict[str, list] = {}
    for c in claims:
        status_groups.setdefault(c.status, []).append(c)

    for status_key in ("open", "confirmed", "refuted", "expired", "superseded"):
        group = status_groups.get(status_key, [])
        if not group:
            continue
        print(f"\n{status_key.upper()} ({len(group)})")
        print("─" * 100)
        for c in group:
            print(_claim_row(c))

    print(f"\nTotal: {len(claims)} claim(s)")
    store.close()


# ---------------------------------------------------------------------------
# Subcommand: resolve
# ---------------------------------------------------------------------------

def cmd_resolve(args: argparse.Namespace) -> None:
    store = _get_store(args.db)
    tt = ThesisTracker(store)

    claim = tt.get_claim(args.claim_id)
    if claim is None:
        print(f"Claim not found: {args.claim_id}", file=sys.stderr)
        store.close()
        sys.exit(1)

    if claim.status not in ("open",):
        print(
            f"Claim {args.claim_id[:8]} is already {claim.status!r}. "
            "Only open claims can be resolved.",
            file=sys.stderr,
        )
        store.close()
        sys.exit(1)

    updated = tt.resolve_claim(
        claim_id=args.claim_id,
        status=args.status,
        evidence=args.evidence or "",
    )
    if updated is None:
        print(f"Failed to resolve claim {args.claim_id}", file=sys.stderr)
        store.close()
        sys.exit(1)

    print(
        f"Resolved claim {args.claim_id[:8]}\n"
        f"  Asset:    {updated.asset_id}\n"
        f"  Claim:    {updated.assertion}\n"
        f"  Status:   {updated.status.upper()}\n"
        f"  Evidence: {updated.resolution_evidence or '(none)'}"
    )
    store.close()


# ---------------------------------------------------------------------------
# Subcommand: expire-overdue
# ---------------------------------------------------------------------------

def cmd_expire_overdue(args: argparse.Namespace) -> None:
    store = _get_store(args.db)
    tt = ThesisTracker(store)

    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    n = tt.expire_overdue_claims(as_of=as_of)

    as_of_label = as_of.isoformat() if as_of else date.today().isoformat()
    if n == 0:
        print(f"No overdue claims found (as_of={as_of_label}).")
    else:
        print(f"Expired {n} overdue claim(s) (as_of={as_of_label}).")

    store.close()


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bve-claim-resolve",
        description="Manage thesis claims in the live KnowledgeStore.",
    )
    p.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        metavar="PATH",
        help="Path to KnowledgeStore database (default: ops.db)",
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    # list
    list_p = sub.add_parser("list", help="List thesis claims")
    list_p.add_argument(
        "--asset",
        metavar="ASSET_ID",
        default=None,
        help="Filter to a specific asset (e.g. a-alny)",
    )
    list_p.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Show all claims (default: open only)",
    )

    # resolve
    resolve_p = sub.add_parser("resolve", help="Resolve a claim by ID")
    resolve_p.add_argument("claim_id", metavar="CLAIM_ID", help="Claim UUID to resolve")
    resolve_p.add_argument(
        "--status",
        choices=["confirmed", "refuted", "expired"],
        required=True,
        help="Resolution status",
    )
    resolve_p.add_argument(
        "--evidence",
        metavar="TEXT",
        default="",
        help="Short evidence description (e.g. trial headline)",
    )

    # expire-overdue
    expire_p = sub.add_parser(
        "expire-overdue",
        help="Expire open claims whose resolution_date has passed",
    )
    expire_p.add_argument(
        "--as-of",
        metavar="DATE",
        default=None,
        help="Expiry reference date YYYY-MM-DD (default: today)",
    )

    return p


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "resolve":
        cmd_resolve(args)
    elif args.cmd == "expire-overdue":
        cmd_expire_overdue(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
