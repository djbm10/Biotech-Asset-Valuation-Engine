"""End-to-end proof: seed → profile → config → override merge → valuation run.

This is the MVP acceptance test: one ticker goes the full loop, fully offline
(mocked source fetchers, no network), and the confidential override reaches the
engine objects while staying out of the public surface.
"""
from __future__ import annotations

import yaml

from bve.cli.run_asset import _build_objects, _load_config
from bve.pipeline.config_resolver import load_resolved_config
from bve.pipeline.profile_builder import ProfileBuilder
from bve.pipeline.profile_store import ProfileStore
from bve.pipeline.profile_to_config import write_config
from bve.pipeline.universe_registry import UniverseRegistryEntry


def _seed() -> UniverseRegistryEntry:
    return UniverseRegistryEntry(
        ticker="ABC",
        company_name="ABC Bio",
        asset_id="asset-abc-1",
        drug_name="ABC-101",
        indication="NSCLC",
        therapeutic_area="oncology",
        stage="phase_3",
        modality="small_molecule",
        nct_id="NCT12345678",
    )


def _builder() -> ProfileBuilder:
    return ProfileBuilder(
        sec_fetcher=lambda t: {
            "cash_millions": 800.0,
            "shares_outstanding_millions": 120.0,
            "long_term_debt_millions": 50.0,
            "rd_expense_millions": 400.0,
        },
        ctgov_fetcher=lambda n: {
            "phase": "PHASE3",
            "enrollment": 450,
            "primary_endpoint": "Overall survival",
            "estimated_completion_date": "2027-06-01",
        },
        market_fetcher=lambda t: {"current_price": 25.0, "market_cap_millions": 3000.0},
    )


def test_full_loop_profile_to_valuation(tmp_path):
    # 1. Build the canonical profile and persist it (DB + YAML export).
    profile = _builder().build(_seed())
    store = ProfileStore(db_path=tmp_path / "ops.db")
    try:
        store.upsert(profile)
        exported = store.export_yaml("ABC", out_dir=tmp_path / "profiles")
    finally:
        store.close()
    assert exported.exists()

    # 2. Generate the valuation config from the profile (coarse evidence).
    cfg_path = write_config(profile, out_dir=tmp_path / "auto_generated")
    base_cfg = yaml.safe_load(cfg_path.read_text())
    assert base_cfg["_meta"]["evidence_level"] == "coarse"

    # 3. Analyst adds a confidential override (value driver + private notes).
    override_dir = tmp_path / "overrides"
    override_dir.mkdir()
    (override_dir / "ABC.yaml").write_text(
        yaml.safe_dump(
            {
                "confidential_overrides": {"market_model": {"peak_penetration": 0.45}},
                "private": {"diligence_notes": "TOP SECRET deal chatter"},
            }
        )
    )

    # 4. Resolve (merge) and confirm the override reached the engine config and
    #    elevated evidence, while the private note never entered the config.
    resolved, prov = load_resolved_config(cfg_path, override_dir=override_dir)
    assert resolved["market_model"]["peak_penetration"] == 0.45
    assert resolved["_meta"]["evidence_level"] == "full"
    assert prov["private"]["diligence_notes"] == "TOP SECRET deal chatter"
    assert "TOP SECRET" not in yaml.safe_dump(resolved)

    # 5. The resolved config runs through the engine and yields a finite rNPV.
    from bve.models.monte_carlo import MonteCarloParams
    from bve.valuation.valuation_engine import ValuationEngine

    asset, company, trials, market_model = _build_objects(resolved)
    assert market_model.peak_penetration == 0.45  # override flowed into engine objects
    engine = ValuationEngine(
        asset, company, trials, market_model,
        mc_params=MonteCarloParams(n_simulations=50, random_seed=0),
    )
    output = engine.run()
    assert isinstance(output.rnpv.rnpv_millions, float)


def test_load_config_applies_overrides_for_bve_asset(tmp_path, monkeypatch):
    """`bve-asset`'s _load_config must transparently merge overrides + drop private."""
    profile = _builder().build(_seed())
    cfg_path = write_config(profile, out_dir=tmp_path / "auto_generated")
    override_dir = tmp_path / "overrides"
    override_dir.mkdir()
    (override_dir / "ABC.yaml").write_text(
        yaml.safe_dump(
            {
                "confidential_overrides": {"asset": {"discount_rate": 0.13}},
                "private": {"diligence_notes": "secret"},
            }
        )
    )
    # _load_config resolves overrides from the default dir; point it at our tmp dir.
    monkeypatch.setattr(
        "bve.pipeline.config_resolver._DEFAULT_OVERRIDE_DIR", str(override_dir)
    )
    cfg = _load_config(cfg_path)
    assert cfg["asset"]["discount_rate"] == 0.13
    assert "secret" not in yaml.safe_dump(cfg)
