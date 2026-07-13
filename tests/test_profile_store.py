"""Tests for ProfileStore (SQLite upsert/get + YAML export)."""
from __future__ import annotations

import yaml

from bve.pipeline.asset_profile import AssetProfile, CompanyProfile, pf
from bve.pipeline.profile_store import ProfileStore


def _sample_profile() -> CompanyProfile:
    asset = AssetProfile(
        asset_id="asset-abc-1",
        nct_id="NCT12345678",
        drug_name=pf("ABC-101", "seed", confidence="high"),
        indication=pf("NSCLC", "clinicaltrials_gov", confidence="high"),
        peak_penetration=pf(0.1, "heuristic_prior", confidence="low"),
    )
    return CompanyProfile(
        ticker="ABC",
        name="ABC Bio",
        company_id="abc-auto",
        cash_millions=pf(500.0, "sec_edgar", confidence="high"),
        assets=[asset],
    )


def test_upsert_and_get_round_trip(tmp_path):
    store = ProfileStore(db_path=tmp_path / "ops.db")
    try:
        store.upsert(_sample_profile())
        loaded = store.get("ABC")
        assert loaded is not None
        assert loaded.ticker == "ABC"
        assert loaded.lead_asset.asset_id == "asset-abc-1"
        assert loaded.lead_asset.drug_name.value == "ABC-101"
        assert loaded.cash_millions.value == 500.0
        # provenance survives the round-trip
        assert loaded.lead_asset.peak_penetration.confidence == "low"
    finally:
        store.close()


def test_get_is_case_insensitive_on_ticker(tmp_path):
    store = ProfileStore(db_path=tmp_path / "ops.db")
    try:
        store.upsert(_sample_profile())
        assert store.get("abc") is not None
        assert store.list_tickers() == ["ABC"]
    finally:
        store.close()


def test_get_missing_returns_none(tmp_path):
    store = ProfileStore(db_path=tmp_path / "ops.db")
    try:
        assert store.get("ZZZZ") is None
    finally:
        store.close()


def test_export_yaml_is_public_only(tmp_path):
    store = ProfileStore(db_path=tmp_path / "ops.db")
    try:
        store.upsert(_sample_profile())
        out = store.export_yaml("ABC", out_dir=tmp_path / "profiles")
        assert out.exists()
        data = yaml.safe_load(out.read_text())
        # Public facts + provenance present...
        assert data["ticker"] == "ABC"
        assert data["assets"][0]["drug_name"]["value"] == "ABC-101"
        # ...and NO confidential surface ever leaks into the public export.
        text = out.read_text().lower()
        assert "confidential_overrides" not in text
        assert "private" not in text
        assert "diligence_notes" not in text
    finally:
        store.close()
