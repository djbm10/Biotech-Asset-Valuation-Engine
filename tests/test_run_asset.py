from __future__ import annotations

from pathlib import Path

from bve.cli.run_asset import _build_pos_adjusters, _validate_config


def _base_config() -> dict:
    return {
        "asset": {
            "id": "asset-1",
            "name": "Drug X",
            "indication": "Indication Y",
            "therapeutic_area": "oncology",
            "stage": "phase_2",
            "modality": "small_molecule",
        },
        "company": {
            "id": "co-1",
            "name": "Company 1",
            "cash_millions": 100.0,
            "shares_outstanding_millions": 10.0,
        },
        "trials": [
            {
                "phase": "phase_2",
                "success_probability": 0.45,
                "duration_years": 2.0,
                "cost_millions": 20.0,
                "endpoint_type": "surrogate_validated",
            }
        ],
        "market_model": {
            "total_addressable_market_millions": 500.0,
            "peak_penetration": 0.10,
        },
        "pos_adjusters": {
            "apply_pos_model": True,
            "phase_2": {
                "endpoint_type": "surrogate_validated",
                "moa_precedent": "validated",
                "sample_size_adequacy": "large",
                "safety_profile": "clean",
                "competitive_pressure": "low",
                "biomarker_selected_population": False,
                "strong_prior_phase_data": True,
                "has_breakthrough_designation": False,
            }
        },
    }


def test_validate_config_accepts_legacy_large_sample_size_alias(tmp_path: Path) -> None:
    cfg = _base_config()
    _validate_config(cfg, tmp_path / "legacy_alias.yaml")


def test_build_pos_adjusters_normalizes_legacy_large_sample_size_alias() -> None:
    cfg = _base_config()
    adjusters, apply_pos = _build_pos_adjusters(cfg)

    assert apply_pos is True
    assert adjusters is not None
    phase_2_adjuster = next(iter(adjusters.values()))
    assert phase_2_adjuster.sample_size_adequacy.value == "well_powered"
