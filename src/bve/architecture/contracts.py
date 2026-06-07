"""Helpers for the repo-wide architecture contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ALLOWED_SCORE_TYPES = frozenset(
    {
        "descriptive",
        "predictive",
        "decision",
        "calibration / QA",
    }
)

REQUIRED_OUTPUT_FIELDS = (
    "value",
    "confidence",
    "provenance",
    "freshness",
    "explainability",
    "downstream_dependencies",
)


def architecture_contract_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "architecture_contract.yaml"


def load_architecture_contract(path: Path | None = None) -> dict[str, Any]:
    contract_path = path or architecture_contract_path()
    payload = yaml.safe_load(contract_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise TypeError("Architecture contract must deserialize to a mapping.")
    return payload


def validate_architecture_contract(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    for key in ("six_question_contract", "top_level_module_map", "module_contracts", "score_registry"):
        if not isinstance(payload.get(key), list) or not payload[key]:
            errors.append(f"Missing or empty required list: {key}")

    mapped_names: set[str] = set()
    for entry in payload.get("top_level_module_map", []):
        name = entry.get("module")
        if not name:
            errors.append("top_level_module_map entry missing module")
            continue
        if name in mapped_names:
            errors.append(f"Duplicate module map entry: {name}")
        mapped_names.add(name)
        if not entry.get("primary_question"):
            errors.append(f"Module map entry missing primary_question: {name}")

    for entry in payload.get("module_contracts", []):
        contract_id = entry.get("contract_id", "<unknown>")
        output_contract = entry.get("output_contract") or {}
        if not isinstance(output_contract, dict):
            errors.append(f"{contract_id}: output_contract must be a mapping")
            continue
        for field in REQUIRED_OUTPUT_FIELDS:
            if field not in output_contract:
                errors.append(f"{contract_id}: output_contract missing {field}")
        if not entry.get("required_inputs"):
            errors.append(f"{contract_id}: required_inputs must not be empty")
        if not entry.get("recalculation_triggers"):
            errors.append(f"{contract_id}: recalculation_triggers must not be empty")

    for entry in payload.get("planned_module_contracts", []):
        contract_id = entry.get("contract_id", "<unknown>")
        if not entry.get("phase"):
            errors.append(f"{contract_id}: planned module missing phase")
        if not entry.get("required_inputs"):
            errors.append(f"{contract_id}: planned module missing required_inputs")
        output_contract = entry.get("output_contract") or {}
        for field in REQUIRED_OUTPUT_FIELDS:
            if field not in output_contract:
                errors.append(f"{contract_id}: planned output_contract missing {field}")

    for entry in payload.get("score_registry", []):
        score_name = entry.get("score_name", "<unknown>")
        score_type = entry.get("score_type")
        if score_type not in ALLOWED_SCORE_TYPES:
            errors.append(f"{score_name}: invalid score_type {score_type!r}")
        if not entry.get("owner_module"):
            errors.append(f"{score_name}: missing owner_module")

    return errors
