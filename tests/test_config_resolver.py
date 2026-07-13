"""Tests for the confidential-override config resolver."""
from __future__ import annotations

import yaml

from bve.pipeline.config_resolver import load_resolved_config


def _base_config() -> dict:
    return {
        "asset": {"id": "a-1", "discount_rate": 0.10, "stage": "phase_2"},
        "company": {"id": "abc-auto", "ticker": "ABC", "cash_millions": 500.0},
        "trials": [{"phase": "phase_2", "success_probability": 0.35}],
        "market_model": {"peak_penetration": 0.10, "patent_life_years": 10},
        "_meta": {"evidence_level": "coarse"},
    }


def _write(tmp_path, base: dict | None = None, override: dict | None = None):
    cfg_path = tmp_path / "abc.yaml"
    cfg_path.write_text(yaml.safe_dump(base if base is not None else _base_config()))
    override_dir = tmp_path / "overrides"
    if override is not None:
        override_dir.mkdir(parents=True, exist_ok=True)
        (override_dir / "ABC.yaml").write_text(yaml.safe_dump(override))
    return cfg_path, override_dir


def test_no_override_file_is_clean_coarse_passthrough(tmp_path):
    cfg_path, override_dir = _write(tmp_path)
    resolved, prov = load_resolved_config(cfg_path, override_dir=override_dir)
    assert resolved["market_model"]["peak_penetration"] == 0.10
    assert resolved["_meta"]["evidence_level"] == "coarse"
    assert prov["overrides_applied"] == []
    assert prov["override_file"] is None


def test_deep_merge_overrides_leaf_values(tmp_path):
    override = {
        "confidential_overrides": {
            "market_model": {"peak_penetration": 0.30},
            "asset": {"discount_rate": 0.11},
        }
    }
    cfg_path, override_dir = _write(tmp_path, override=override)
    resolved, prov = load_resolved_config(cfg_path, override_dir=override_dir)
    assert resolved["market_model"]["peak_penetration"] == 0.30
    assert resolved["asset"]["discount_rate"] == 0.11
    # Untouched fields are preserved.
    assert resolved["market_model"]["patent_life_years"] == 10
    assert "market_model.peak_penetration" in prov["overrides_applied"]


def test_list_merge_by_index(tmp_path):
    override = {"confidential_overrides": {"trials": [{"success_probability": 0.42}]}}
    cfg_path, override_dir = _write(tmp_path, override=override)
    resolved, _ = load_resolved_config(cfg_path, override_dir=override_dir)
    assert resolved["trials"][0]["success_probability"] == 0.42
    # Other keys on the same element are preserved.
    assert resolved["trials"][0]["phase"] == "phase_2"


def test_value_driver_override_elevates_evidence_level(tmp_path):
    override = {"confidential_overrides": {"market_model": {"peak_penetration": 0.30}}}
    cfg_path, override_dir = _write(tmp_path, override=override)
    resolved, _ = load_resolved_config(cfg_path, override_dir=override_dir)
    assert resolved["_meta"]["evidence_level"] == "full"


def test_private_section_never_reaches_config(tmp_path):
    override = {
        "confidential_overrides": {"market_model": {"peak_penetration": 0.30}},
        "private": {"expected_partner_interest": "high", "diligence_notes": "secret"},
    }
    cfg_path, override_dir = _write(tmp_path, override=override)
    resolved, prov = load_resolved_config(cfg_path, override_dir=override_dir)
    # Confidential content is returned for downstream use...
    assert prov["private"]["expected_partner_interest"] == "high"
    # ...but NEVER merged into the engine config.
    assert "private" not in resolved
    assert "diligence_notes" not in yaml.safe_dump(resolved)


def test_no_meaningful_override_does_not_elevate(tmp_path):
    # Overriding the same value as the base → no leaf change → stays coarse.
    override = {"confidential_overrides": {"market_model": {"peak_penetration": 0.10}}}
    cfg_path, override_dir = _write(tmp_path, override=override)
    resolved, prov = load_resolved_config(cfg_path, override_dir=override_dir)
    assert resolved["_meta"]["evidence_level"] == "coarse"
    assert prov["overrides_applied"] == []
