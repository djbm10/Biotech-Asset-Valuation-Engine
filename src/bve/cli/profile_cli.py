"""bve-profile — auto-profile pipeline CLI.

Commands
--------
  build      Build the canonical profile from public sources + heuristic priors,
             persist it (SQLite truth + YAML export). ``--ticker X`` or ``--all``.
  gen-config Generate a valuation config from the stored profile(s). ``--all``
             also emits a gap-fill watchlist for the M&A coverage map.
  show       Print the stored profile and its low-confidence (review) fields.

Seeds (identity: ticker, lead asset, indication, NCT) are read from the universe
registry; everything else (financials, trial facts, economics) is auto-derived.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from bve.pipeline.auto_watchlist import write_auto_watchlist
from bve.pipeline.profile_builder import ProfileBuilder
from bve.pipeline.profile_store import ProfileStore
from bve.pipeline.profile_to_config import write_config
from bve.pipeline.universe_registry import UniverseRegistryEntry, load_universe_registry

_DEFAULT_REGISTRY = "examples/configs/universe_registry.yaml"
_DEFAULT_DB = "outputs/intelligence/ops.db"
_DEFAULT_AUTO_DIR = "examples/configs/auto_generated"
_DEFAULT_PROFILES_DIR = "profiles"
_DEFAULT_AUTO_WATCHLIST = "examples/configs/watchlists/watchlist_auto_generated.yaml"


def _all_seeds(registry_path: Path) -> list[UniverseRegistryEntry]:
    return load_universe_registry(registry_path)


def _find_seed(registry_path: Path, ticker: str) -> UniverseRegistryEntry:
    wanted = ticker.upper()
    for entry in _all_seeds(registry_path):
        if entry.ticker.upper() == wanted:
            return entry
    raise SystemExit(f"Ticker {wanted} not found in {registry_path}")


def _build_one(store: ProfileStore, seed: UniverseRegistryEntry, profiles_dir: str) -> None:
    profile = ProfileBuilder().build(seed)
    store.upsert(profile)
    store.export_yaml(seed.ticker, out_dir=profiles_dir)
    asset = profile.lead_asset
    print(
        f"  {seed.ticker:6s} {asset.drug_name.value} ({asset.indication.value}) "
        f"PoS={asset.success_probability.value}"
    )


def _cmd_build(args: argparse.Namespace) -> None:
    registry = Path(args.registry)
    if args.all or args.missing:
        seeds = _all_seeds(registry)
        if args.missing:
            # Only names not already covered by the M&A map — never rebuild/clobber
            # curated or point-in-time configs the working screen depends on.
            from bve.ops.weekly_runner import _mna_config_map

            covered = set(_mna_config_map().keys())
            seeds = [s for s in seeds if s.ticker.upper() not in covered]
    else:
        seeds = [_find_seed(registry, args.ticker)]
    store = ProfileStore(db_path=args.db)
    ok = failed = 0
    try:
        for seed in seeds:
            try:
                _build_one(store, seed, args.profiles_dir)
                ok += 1
            except Exception as exc:  # one bad name must not abort a batch
                print(f"  {seed.ticker:6s} FAILED ({type(exc).__name__}: {str(exc)[:60]})")
                failed += 1
    finally:
        store.close()
    print(f"Built {ok} profile(s), {failed} failed; DB={args.db}")


def _cmd_gen_config(args: argparse.Namespace) -> None:
    store = ProfileStore(db_path=args.db)
    try:
        if args.all:
            tickers = store.list_tickers()
        else:
            tickers = [args.ticker.upper()]
        profiles = []
        for ticker in tickers:
            profile = store.get(ticker)
            if profile is None:
                raise SystemExit(
                    f"No stored profile for {ticker}; run `bve-profile build --ticker {ticker}` first"
                )
            out = write_config(profile, out_dir=args.out_dir)
            profiles.append(profile)
            print(f"  wrote {out}  (evidence_level={profile.evidence_level})")
    finally:
        store.close()

    if args.all:
        wl = write_auto_watchlist(profiles, args.out_dir, args.watchlist)
        print(f"Wrote watchlist: {wl}  ({len(profiles)} configs)")
    else:
        print(
            f"  add examples/configs/overrides/{tickers[0]}.yaml "
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


def _require_target(args: argparse.Namespace) -> None:
    if not args.all and not args.ticker and not getattr(args, "missing", False):
        raise SystemExit("Provide --ticker <T>, --all, or --missing")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="bve-profile", description="Auto-profile pipeline"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="Build + persist canonical profile(s)")
    p_build.add_argument("--ticker", help="Single ticker to build")
    p_build.add_argument("--all", action="store_true", help="Build every registry seed")
    p_build.add_argument(
        "--missing", action="store_true",
        help="Build only registry seeds not already covered by the M&A map",
    )
    p_build.add_argument("--registry", default=_DEFAULT_REGISTRY)
    p_build.add_argument("--db", default=_DEFAULT_DB)
    p_build.add_argument("--profiles-dir", default=_DEFAULT_PROFILES_DIR)

    p_gen = sub.add_parser("gen-config", help="Generate valuation config(s) from profile(s)")
    p_gen.add_argument("--ticker", help="Single ticker to generate")
    p_gen.add_argument("--all", action="store_true", help="Generate for all stored profiles + watchlist")
    p_gen.add_argument("--db", default=_DEFAULT_DB)
    p_gen.add_argument("--out-dir", default=_DEFAULT_AUTO_DIR)
    p_gen.add_argument("--watchlist", default=_DEFAULT_AUTO_WATCHLIST)

    p_show = sub.add_parser("show", help="Print a stored profile")
    p_show.add_argument("--ticker", required=True)
    p_show.add_argument("--db", default=_DEFAULT_DB)

    args = parser.parse_args(argv)
    if args.command in ("build", "gen-config"):
        _require_target(args)
    {"build": _cmd_build, "gen-config": _cmd_gen_config, "show": _cmd_show}[args.command](args)


if __name__ == "__main__":
    main()
