"""Tests for Phase 1.5: auto-generated watchlist + coverage-map gap-fill wiring."""
from __future__ import annotations

import yaml

from bve.cli import profile_cli
from bve.ops import weekly_runner as wr
from bve.pipeline.asset_profile import AssetProfile, CompanyProfile, pf
from bve.pipeline.auto_watchlist import build_watchlist_entries, write_auto_watchlist
from bve.pipeline.profile_store import ProfileStore


def _profile(ticker: str, asset_id: str) -> CompanyProfile:
    asset = AssetProfile(
        asset_id=asset_id,
        nct_id="NCT00000000",
        drug_name=pf(f"{ticker}-101", "seed", confidence="high"),
        indication=pf("NSCLC", "seed", confidence="high"),
        therapeutic_area=pf("oncology", "seed", confidence="high"),
        stage=pf("phase_2", "seed", confidence="high"),
        modality=pf("small_molecule", "seed", confidence="high"),
    )
    return CompanyProfile(
        ticker=ticker, name=f"{ticker} Bio", company_id=f"{ticker.lower()}-auto", assets=[asset]
    )


def test_build_watchlist_entries_format():
    entries = build_watchlist_entries(
        [_profile("ABC", "asset-abc-1")], "examples/configs/auto_generated"
    )
    e = entries[0]
    assert e["ticker"] == "ABC"
    assert e["valuation_config"] == "examples/configs/auto_generated/abc.yaml"
    assert e["asset_id"] == "asset-abc-1"
    assert e["drug_name"] == "ABC-101"


def test_write_auto_watchlist_is_loadable_shape(tmp_path):
    out = write_auto_watchlist(
        [_profile("ABC", "a-1"), _profile("XYZ", "a-2")],
        config_dir=tmp_path / "cfgs",
        out_path=tmp_path / "wl.yaml",
    )
    doc = yaml.safe_load(out.read_text())
    assert {e["ticker"] for e in doc["watchlist"]} == {"ABC", "XYZ"}
    # Every entry carries the two keys the coverage-map loader requires.
    for e in doc["watchlist"]:
        assert e["ticker"] and e["valuation_config"]


def test_gen_config_all_writes_configs_and_watchlist(tmp_path):
    db = tmp_path / "ops.db"
    store = ProfileStore(db_path=db)
    try:
        store.upsert(_profile("ABC", "a-1"))
        store.upsert(_profile("XYZ", "a-2"))
    finally:
        store.close()

    out_dir = tmp_path / "auto_generated"
    wl = tmp_path / "watchlist_auto_generated.yaml"
    profile_cli.main(
        ["gen-config", "--all", "--db", str(db), "--out-dir", str(out_dir), "--watchlist", str(wl)]
    )

    assert (out_dir / "abc.yaml").exists()
    assert (out_dir / "xyz.yaml").exists()
    doc = yaml.safe_load(wl.read_text())
    assert {e["ticker"] for e in doc["watchlist"]} == {"ABC", "XYZ"}


def test_mna_config_map_auto_generated_is_gap_fill(tmp_path, monkeypatch):
    # Base coverage from replay + provisional watchlists.
    base = wr._load_valuation_config_map()
    for tkr, path in _load_provisional(wr).items():
        base.setdefault(tkr, path)
    assert base, "expected some base coverage"
    existing_ticker = sorted(base)[0]
    existing_cfg = base[existing_ticker]

    # Auto watchlist points an already-covered ticker at a DIFFERENT config and
    # introduces a brand-new ticker — both via paths that exist on disk.
    other_cfg = next(p for t, p in base.items() if p != existing_cfg)
    auto_wl = tmp_path / "watchlist_auto_generated.yaml"
    auto_wl.write_text(
        yaml.safe_dump(
            {
                "watchlist": [
                    {"ticker": existing_ticker, "valuation_config": other_cfg},
                    {"ticker": "ZZZZTEST", "valuation_config": existing_cfg},
                ]
            }
        )
    )
    monkeypatch.setattr(wr, "_MNA_AUTO_GENERATED_WATCHLIST", str(auto_wl))

    merged = wr._mna_config_map()
    # Gap-fill: new ticker added...
    assert merged.get("ZZZZTEST") is not None
    # ...but an already-covered ticker is NOT overridden.
    assert merged[existing_ticker] == existing_cfg


def _load_provisional(wr_mod) -> dict[str, str]:
    return wr_mod._load_valuation_config_map(wr_mod._MNA_PROVISIONAL_WATCHLIST)
