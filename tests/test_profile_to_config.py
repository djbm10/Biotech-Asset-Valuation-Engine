"""Tests for profile → valuation config mapping."""
from __future__ import annotations

from bve.cli.run_asset import _build_objects
from bve.pipeline.profile_builder import ProfileBuilder
from bve.pipeline.profile_to_config import config_from_profile, write_config
from bve.pipeline.universe_registry import UniverseRegistryEntry


def _seed(**overrides) -> UniverseRegistryEntry:
    base = dict(
        ticker="ABC",
        company_name="ABC Bio",
        asset_id="asset-abc-1",
        drug_name="ABC-101",
        indication="NSCLC",
        therapeutic_area="oncology",
        stage="phase_2",
        modality="small_molecule",
        nct_id="NCT12345678",
    )
    base.update(overrides)
    return UniverseRegistryEntry(**base)


def _profile(**seed_overrides):
    builder = ProfileBuilder(
        sec_fetcher=lambda t: {
            "cash_millions": 800.0,
            "shares_outstanding_millions": 120.0,
            "rd_expense_millions": 400.0,
        },
        ctgov_fetcher=lambda n: {},
        market_fetcher=lambda t: {"current_price": 25.0, "market_cap_millions": 3000.0},
    )
    return builder.build(_seed(**seed_overrides))


def test_config_has_engine_schema_blocks():
    cfg = config_from_profile(_profile())
    assert set(cfg) == {"asset", "company", "trials", "market_model", "_meta"}
    assert cfg["asset"]["therapeutic_area"] == "oncology"
    assert cfg["asset"]["stage"] == "phase_2"
    assert cfg["company"]["cash_millions"] == 800.0
    assert cfg["trials"][0]["phase"] == "phase_2"
    assert cfg["trials"][0]["success_probability"] is not None


def test_meta_carries_coarse_evidence_level_and_review_fields():
    cfg = config_from_profile(_profile())
    meta = cfg["_meta"]
    assert meta["evidence_level"] == "coarse"
    # Heuristic economics are flagged for review.
    assert "peak_penetration" in meta["defaulted_fields"]
    assert "total_addressable_market_millions" in meta["defaulted_fields"]


def test_missing_required_company_field_is_coerced_and_flagged():
    builder = ProfileBuilder(
        sec_fetcher=lambda t: {},  # no cash / shares
        ctgov_fetcher=lambda n: {},
        market_fetcher=lambda t: {},
    )
    cfg = config_from_profile(builder.build(_seed()))
    assert cfg["company"]["cash_millions"] == 250.0  # coerced default
    assert "cash_millions" in cfg["_meta"]["defaulted_fields"]
    assert "shares_outstanding_millions" in cfg["_meta"]["defaulted_fields"]


def test_generated_config_runs_through_build_objects():
    # The whole point: the generated config must parse into engine objects.
    cfg = config_from_profile(_profile(tam_millions=12000.0, peak_penetration=0.35))
    asset, company, trials, market_model = _build_objects(cfg)
    assert asset.id == "asset-abc-1"
    assert company.cash_millions == 800.0
    assert trials[0].success_probability is not None
    assert market_model.total_addressable_market_millions == 12000.0


def test_write_config_emits_yaml(tmp_path):
    out = write_config(_profile(), out_dir=tmp_path)
    assert out.exists()
    assert out.name == "abc.yaml"
