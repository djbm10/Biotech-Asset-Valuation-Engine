from __future__ import annotations

from pathlib import Path

from bve.architecture import (
    ALLOWED_SCORE_TYPES,
    REQUIRED_OUTPUT_FIELDS,
    load_architecture_contract,
    validate_architecture_contract,
)


def test_architecture_contract_is_valid() -> None:
    payload = load_architecture_contract()
    errors = validate_architecture_contract(payload)
    assert errors == []


def test_all_top_level_bve_modules_are_mapped() -> None:
    payload = load_architecture_contract()
    mapped = {entry["module"] for entry in payload["top_level_module_map"]}

    root = Path(__file__).resolve().parents[1] / "src" / "bve"
    expected = {
        path.name
        for path in root.iterdir()
        if (
            (path.is_dir() and path.name != "__pycache__")
            or (path.is_file() and path.suffix == ".py" and path.name != "__init__.py")
        )
    }

    assert expected <= mapped


def test_every_contract_output_has_required_fields() -> None:
    payload = load_architecture_contract()
    for entry in payload["module_contracts"] + payload["planned_module_contracts"]:
        output_contract = entry["output_contract"]
        assert set(REQUIRED_OUTPUT_FIELDS) <= set(output_contract)


def test_score_registry_uses_allowed_score_types() -> None:
    payload = load_architecture_contract()
    for entry in payload["score_registry"]:
        assert entry["score_type"] in ALLOWED_SCORE_TYPES
