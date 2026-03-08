"""
CLI entry point: bve-rebuild-dossiers

Rebuild dossiers for all assets listed in a watchlist config (or a specific
asset) from existing knowledge store data. This is non-destructive and
idempotent — it overwrites the stored dossier for each asset.

Useful after:
  - Schema migrations that change dossier structure
  - Bulk retroactive changes to underlying signals/reviews
  - Cold-start scenarios where dossiers were never built

Usage
-----
    bve-rebuild-dossiers --watchlist examples/configs/watchlist.yaml

    bve-rebuild-dossiers --watchlist watchlist.yaml \\
        --asset-id asset-001 --company-id co-001

    bve-rebuild-dossiers --watchlist watchlist.yaml --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rebuild dossiers for watchlist assets from knowledge store data"
    )
    parser.add_argument("--watchlist", required=True, help="Path to watchlist YAML config")
    parser.add_argument(
        "--asset-id",
        default=None,
        help="Rebuild only this asset (requires --company-id)",
    )
    parser.add_argument(
        "--company-id",
        default=None,
        help="Company ID for --asset-id filtering",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print which dossiers would be rebuilt without actually rebuilding",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> None:
    args = _build_parser().parse_args()

    import logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )
    log = logging.getLogger("bve.rebuild_dossiers")

    from bve.intelligence.knowledge_layer import KnowledgeStore
    from bve.pipeline.watchlist_runner import load_watchlist_config

    config = load_watchlist_config(args.watchlist)
    knowledge = KnowledgeStore(config.knowledge_db_path)

    # Determine target assets.
    assets = config.watchlist
    if args.asset_id:
        if not args.company_id:
            print("--company-id is required when --asset-id is specified", file=sys.stderr)
            sys.exit(1)
        assets = [
            a for a in assets
            if a.asset_id == args.asset_id and a.company_id == args.company_id
        ]
        if not assets:
            print(
                f"Asset {args.asset_id} / {args.company_id} not found in watchlist",
                file=sys.stderr,
            )
            sys.exit(1)

    total = len(assets)
    print(f"Rebuilding dossiers for {total} asset(s)...")

    succeeded = 0
    failed = 0
    for asset in assets:
        label = f"{asset.company_id}/{asset.asset_id}"
        if args.dry_run:
            print(f"  [dry-run] would rebuild: {label}")
            succeeded += 1
            continue
        try:
            dossier = knowledge.generate_dossier(
                company_id=asset.company_id,
                asset_id=asset.asset_id,
                persist=True,
            )
            log.info("rebuilt dossier %s → id=%s", label, dossier.id)
            print(f"  ✓ {label} → dossier_id={dossier.id}")
            succeeded += 1
        except Exception as exc:
            log.error("failed to rebuild dossier for %s: %s", label, exc)
            print(f"  ✗ {label}: {exc}", file=sys.stderr)
            failed += 1

    print(f"\nDone: {succeeded} succeeded, {failed} failed.")
    knowledge.close()

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
