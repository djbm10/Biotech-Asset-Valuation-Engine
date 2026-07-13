"""Tests for merging seeds_auto.yaml into bve-profile build."""
from __future__ import annotations

import yaml

from bve.cli.profile_cli import _merge_seeds_auto
from bve.pipeline.universe_registry import UniverseRegistryEntry, load_universe_registry


def _entry(ticker, drug="X"):
    return UniverseRegistryEntry(
        ticker=ticker, company_name=f"{ticker} Inc", asset_id=f"a-{ticker.lower()}",
        drug_name=drug, indication="Cancer", therapeutic_area="oncology",
        stage="phase_2", modality="small_molecule",
    )


def _write_seeds_auto(path, rows):
    path.write_text(yaml.safe_dump({"assets": rows}, sort_keys=False), encoding="utf-8")


def test_merge_appends_new_staged_seed(tmp_path):
    seeds_auto = tmp_path / "seeds_auto.yaml"
    _write_seeds_auto(seeds_auto, [{
        "ticker": "VKTX", "company_name": "Viking", "asset_id": "asset-vktx-vk2735",
        "drug_name": "VK2735", "indication": "Obesity", "therapeutic_area": "metabolic",
        "stage": "phase_3", "modality": "peptide", "provenance": {"source": "bve-discover"},
    }])
    merged = _merge_seeds_auto([_entry("BEAM")], seeds_auto)
    assert {e.ticker for e in merged} == {"BEAM", "VKTX"}


def test_curated_registry_wins_on_conflict(tmp_path):
    seeds_auto = tmp_path / "seeds_auto.yaml"
    _write_seeds_auto(seeds_auto, [{
        "ticker": "BEAM", "company_name": "Other", "asset_id": "asset-beam-dup",
        "drug_name": "DUP", "indication": "X", "therapeutic_area": "oncology",
        "stage": "phase_1", "modality": "small_molecule",
    }])
    merged = _merge_seeds_auto([_entry("BEAM", drug="CuratedDrug")], seeds_auto)
    assert len(merged) == 1
    assert merged[0].drug_name == "CuratedDrug"  # curated not overridden


def test_missing_seeds_auto_is_noop(tmp_path):
    merged = _merge_seeds_auto([_entry("BEAM")], tmp_path / "absent.yaml")
    assert [e.ticker for e in merged] == ["BEAM"]


def test_staged_seed_loads_with_provenance_ignored(tmp_path):
    seeds_auto = tmp_path / "seeds_auto.yaml"
    _write_seeds_auto(seeds_auto, [{
        "ticker": "VKTX", "company_name": "Viking", "asset_id": "asset-vktx-vk2735",
        "drug_name": "VK2735", "indication": "Obesity", "therapeutic_area": "metabolic",
        "stage": "phase_3", "modality": "peptide",
        "provenance": {"source": "bve-discover", "approved_by": "doug"},
    }])
    loaded = load_universe_registry(seeds_auto)
    assert loaded[0].ticker == "VKTX"  # extra provenance key tolerated
