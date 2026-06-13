"""bve-profile — auto-profile pipeline CLI (MVP, single ticker).

Commands
--------
  build      Build the canonical profile from public sources + heuristic priors,
             persist it (SQLite truth + YAML export).
  gen-config Generate a valuation config from the stored profile.
  show       Print the stored profile and its low-confidence (review) fields.

Seeds (identity: ticker, lead asset, indication, NCT) are read from the universe
registry. Batch mode and screen wiring are intentionally out of scope for the MVP.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from bve.pipeline.profile_builder import ProfileBuilder
from bve.pipeline.profile_store import ProfileStore
from bve.pipeline.profile_to_config import write_config
from bve.pipeline.universe_registry import UniverseRegistryEntry, load_universe_registry

_DEFAULT_REGISTRY = "examples/configs/universe_registry.yaml"
_DEFAULT_DB = "outputs/intelligence/ops.db"
_DEFAULT_AUTO_DIR = "examples/configs/auto_generated"
_DEFAULT_PROFILES_DIR = "profiles"


def _find_seed(registry_path: Path, ticker: str) -> UniverseRegistryEntry:
    wanted = ticker.upper()
    for entry in load_universe_registry(registry_path):
        if entry.ticker.upper() == wanted:
            return entry
    raise SystemExit(f"Ticker {wanted} not found in {registry_path}")


def _cmd_build(args: argparse.Namespace) -> None:
    seed = _find_seed(Path(args.registry), args.ticker)
    profile = ProfileBuilder().build(seed)
    store = ProfileStore(db_path=args.db)
    try:
        store.upsert(profile)
        out = store.export_yaml(seed.ticker, out_dir=args.profiles_dir)
    finally:
        store.close()
    asset = profile.lead_asset
    print(f"Built profile {seed.ticker}: {asset.drug_name.value} ({asset.indication.value})")
    print(f"  evidence_level: {profile.evidence_level}")
    print(f"  review (low-confidence) fields: {', '.join(asset.low_confidence_fields()) or '-'}")
    print(f"  exported: {out}")


def _cmd_gen_config(args: argparse.Namespace) -> None:
    store = ProfileStore(db_path=args.db)
    try:
        profile = store.get(args.ticker)
    finally:
        store.close()
    if profile is None:
        raise SystemExit(
            f"No stored profile for {args.ticker.upper()}; "
            f"run `bve-profile build --ticker {args.ticker.upper()}` first"
        )
    out = write_config(profile, out_dir=args.out_dir)
    print(f"Wrote config: {out}  (evidence_level={profile.evidence_level})")
    print(
        f"  add examples/configs/overrides/{args.ticker.upper()}.yaml "
        f"with confidential_overrides to elevate to full"
    )


def _cmd_show(args: argparse.Namespace) -> None:
    store = ProfileStore(db_path=args.db)
    try:
        profile = store.get(args.ticker)
    finally:
        store.close()
    if profile is None:
        raise SystemExit(f"No stored profile for {args.ticker.upper()}")
    asset = profile.lead_asset
    print(f"{profile.ticker} — {profile.name}  [{profile.evidence_level}]")
    print(f"  lead asset: {asset.drug_name.value} | {asset.indication.value} | {asset.stage.value}")
    print("  low-confidence fields (analyst-review targets):")
    for name in asset.low_confidence_fields():
        field = getattr(asset, name)
        print(f"    - {name}: {field.value}  [{field.source}]")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="bve-profile", description="Auto-profile pipeline (MVP, single ticker)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="Build + persist a canonical profile")
    p_build.add_argument("--ticker", required=True)
    p_build.add_argument("--registry", default=_DEFAULT_REGISTRY)
    p_build.add_argument("--db", default=_DEFAULT_DB)
    p_build.add_argument("--profiles-dir", default=_DEFAULT_PROFILES_DIR)

    p_gen = sub.add_parser("gen-config", help="Generate a valuation config from a profile")
    p_gen.add_argument("--ticker", required=True)
    p_gen.add_argument("--db", default=_DEFAULT_DB)
    p_gen.add_argument("--out-dir", default=_DEFAULT_AUTO_DIR)

    p_show = sub.add_parser("show", help="Print a stored profile")
    p_show.add_argument("--ticker", required=True)
    p_show.add_argument("--db", default=_DEFAULT_DB)

    args = parser.parse_args(argv)
    {"build": _cmd_build, "gen-config": _cmd_gen_config, "show": _cmd_show}[args.command](args)


if __name__ == "__main__":
    main()
