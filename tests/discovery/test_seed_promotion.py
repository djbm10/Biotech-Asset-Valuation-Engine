"""Tests for promoting an approved proposed_seed into seeds_auto.yaml."""
from __future__ import annotations

import yaml

from bve.discovery.exclusion_ledger import ExclusionLedger
from bve.discovery.seed_promotion import (
    STATUS_DUPLICATE,
    STATUS_EXCLUDED,
    STATUS_NOT_FOUND,
    STATUS_PROMOTED,
    load_proposed_entries,
    promote_seed,
)
from bve.pipeline.universe_registry import load_universe_registry


def _proposals_file(tmp_path):
    doc = {
        "generated_at": "2026-06-15T00:00:00+00:00",
        "proposals": [{
            "ticker": "VKTX", "company_name": "Viking Therapeutics, Inc.",
            "asset_id": "asset-vktx-vk2735", "drug_name": "VK2735",
            "indication": "Obesity", "therapeutic_area": "metabolic",
            "stage": "phase_3", "modality": "peptide", "nct_id": "NCT07",
            "_meta": {"disposition": "high_confidence", "tier": "high",
                      "score": 1.7, "generated_at": "2026-06-15T00:00:00+00:00"},
        }],
        "review": [{
            "ticker": "MRUS", "company_name": "Merus", "asset_id": "asset-mrus-peto",
            "drug_name": "Petosemtamab", "indication": "Head and Neck Cancer",
            "therapeutic_area": "oncology", "stage": "phase_3", "modality": "biologic",
            "nct_id": "NCT08", "_meta": {"disposition": "approved_vs_active_pivotal"},
        }],
        "auto_added": [],
    }
    p = tmp_path / "proposed_seeds.yaml"
    p.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return p


def _registry_file(tmp_path, tickers=()):
    rows = [{
        "ticker": t, "company_name": f"{t} Inc", "asset_id": f"a-{t.lower()}",
        "drug_name": "X", "indication": "Cancer", "therapeutic_area": "oncology",
        "stage": "phase_2", "modality": "small_molecule",
    } for t in tickers]
    p = tmp_path / "universe_registry.yaml"
    p.write_text(yaml.safe_dump(rows, sort_keys=False), encoding="utf-8")
    return p


def test_load_proposed_entries_flattens_sections(tmp_path):
    entries = load_proposed_entries(_proposals_file(tmp_path))
    assert set(entries) == {"VKTX", "MRUS"}


def test_promote_writes_seed_with_provenance(tmp_path):
    proposals = _proposals_file(tmp_path)
    registry = _registry_file(tmp_path)
    seeds_auto = tmp_path / "seeds_auto.yaml"
    res = promote_seed(
        "VKTX", proposals_path=proposals, seeds_auto_path=seeds_auto,
        registry_path=registry, exclusion_path=tmp_path / "ex.yaml",
        reviewer="doug", rationale="confirmed lead",
    )
    assert res.status == STATUS_PROMOTED
    doc = yaml.safe_load(seeds_auto.read_text())
    entry = doc["assets"][0]
    assert entry["ticker"] == "VKTX"
    assert entry["drug_name"] == "VK2735"
    assert entry["provenance"]["source"] == "bve-discover"
    assert entry["provenance"]["approved_by"] == "doug"
    assert entry["provenance"]["proposed_at"] == "2026-06-15T00:00:00+00:00"
    # The staged file is loadable as a registry (provenance ignored).
    assert load_universe_registry(seeds_auto)[0].ticker == "VKTX"


def test_promote_unknown_ticker_is_not_found(tmp_path):
    res = promote_seed(
        "NOPE", proposals_path=_proposals_file(tmp_path),
        seeds_auto_path=tmp_path / "s.yaml", registry_path=_registry_file(tmp_path),
        exclusion_path=tmp_path / "ex.yaml",
    )
    assert res.status == STATUS_NOT_FOUND


def test_promote_rejects_curated_duplicate(tmp_path):
    res = promote_seed(
        "VKTX", proposals_path=_proposals_file(tmp_path),
        seeds_auto_path=tmp_path / "s.yaml",
        registry_path=_registry_file(tmp_path, tickers=["VKTX"]),
        exclusion_path=tmp_path / "ex.yaml",
    )
    assert res.status == STATUS_DUPLICATE


def test_promote_rejects_seeds_auto_duplicate(tmp_path):
    proposals = _proposals_file(tmp_path)
    registry = _registry_file(tmp_path)
    seeds_auto = tmp_path / "seeds_auto.yaml"
    ex = tmp_path / "ex.yaml"
    first = promote_seed("VKTX", proposals_path=proposals, seeds_auto_path=seeds_auto,
                         registry_path=registry, exclusion_path=ex)
    assert first.status == STATUS_PROMOTED
    second = promote_seed("VKTX", proposals_path=proposals, seeds_auto_path=seeds_auto,
                          registry_path=registry, exclusion_path=ex)
    assert second.status == STATUS_DUPLICATE


def test_promote_refuses_excluded(tmp_path):
    ex_path = tmp_path / "ex.yaml"
    led = ExclusionLedger(ex_path)
    led.add("VKTX", "rejected")
    led.save()
    res = promote_seed(
        "VKTX", proposals_path=_proposals_file(tmp_path),
        seeds_auto_path=tmp_path / "s.yaml", registry_path=_registry_file(tmp_path),
        exclusion_path=ex_path,
    )
    assert res.status == STATUS_EXCLUDED
