"""CLI for auto-generating valuation configs from a universe registry."""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from bve.intelligence.knowledge_layer import AssetRegistryEntry, KnowledgeStore
from bve.pipeline.auto_config_generator import AutoConfigGenerator
from bve.pipeline.disk_cache import DiskCache
from bve.pipeline.universe_registry import UniverseRegistryEntry, load_universe_registry
from bve.services.rate_limiter import ServiceRateLimiter


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate auto valuation configs")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticker", help="Generate config for one ticker")
    group.add_argument("--asset", help="Alias of --ticker (backward-compatible)")
    group.add_argument("--batch", action="store_true", help="Generate for all registry entries")
    parser.add_argument(
        "--registry",
        default="examples/configs/universe_registry.yaml",
        help="Universe registry path",
    )
    parser.add_argument(
        "--out-dir",
        default="examples/configs/auto_generated",
        help="Output directory for generated YAML files",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Optional knowledge DB path; when set, upserts into asset_registry",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print output without writing files")
    return parser


def _select_entries(entries: list[UniverseRegistryEntry], ticker: str | None, batch: bool) -> list[UniverseRegistryEntry]:
    if batch:
        return entries
    assert ticker is not None
    wanted = ticker.upper()
    selected = [entry for entry in entries if entry.ticker.upper() == wanted]
    if not selected:
        raise SystemExit(f"Ticker {wanted} not found in registry")
    return selected


def _write_watchlist_block(entry: UniverseRegistryEntry, config_path: Path) -> str:
    payload = {
        "company_id": f"{entry.ticker.lower()}-auto",
        "asset_id": entry.asset_id,
        "drug_name": entry.drug_name,
        "indication": entry.indication,
        "ticker": entry.ticker,
        "valuation_config": str(config_path),
    }
    return yaml.safe_dump([payload], sort_keys=False).strip()


def _upsert_asset_registry(db_path: str, entry: UniverseRegistryEntry) -> None:
    store = KnowledgeStore(db_path)
    try:
        store.upsert_asset_registry_entry(
            AssetRegistryEntry(
                asset_id=entry.asset_id,
                ticker=entry.ticker,
                company_id=f"{entry.ticker.lower()}-auto",
                drug_name=entry.drug_name,
                indication=entry.indication,
                therapeutic_area=entry.therapeutic_area,
                modality=entry.modality,
                stage=entry.stage,
                nct_id=entry.nct_id,
                tam_millions=entry.tam_millions,
                source="auto_generated",
            )
        )
    finally:
        store.close()


def main() -> None:
    args = _build_parser().parse_args()
    registry_entries = load_universe_registry(Path(args.registry))
    ticker = args.ticker or args.asset
    targets = _select_entries(registry_entries, ticker, args.batch)

    out_dir = Path(args.out_dir)
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    generator = AutoConfigGenerator(cache=DiskCache(), rate_limiter=ServiceRateLimiter())
    results = generator.generate_batch(targets)

    for entry, config_dict, error in results:
        if error is not None:
            print(f"ERROR {entry.ticker}: {error}")
            continue

        filename = f"{entry.ticker.lower()}.yaml"
        out_path = out_dir / filename
        if args.dry_run:
            print(f"# {entry.ticker} (dry-run)")
            print(yaml.safe_dump(config_dict, sort_keys=False).strip())
        else:
            out_path.write_text(yaml.safe_dump(config_dict, sort_keys=False), encoding="utf-8")
            print(f"Wrote {out_path}")

        defaults = config_dict.get("_meta", {}).get("defaulted_fields", [])
        for field in defaults:
            print(f"WARNING {entry.ticker}: used default for {field}")

        watchlist_path = out_path if not args.dry_run else Path(f"{args.out_dir}/{filename}")
        print("watchlist block:")
        print(_write_watchlist_block(entry, watchlist_path))

        if args.db:
            _upsert_asset_registry(args.db, entry)


if __name__ == "__main__":
    main()
