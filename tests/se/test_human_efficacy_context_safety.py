"""Frozen clinical-context controls; labels committed before behavior changed."""

from datetime import date
import json
from pathlib import Path

import pytest

from bve.se.evidence.human_poc import (
    efficacy_statements,
    human_poc_evidence,
    result_supports_human_poc,
)
from bve.se.schemas.contracts import ClinicalResult

PACKET = Path(__file__).resolve().parents[2] / "research/se_human_efficacy_context_safety_v1"


def _load(name):
    return json.loads((PACKET / name).read_text())


@pytest.mark.parametrize("control", _load("semantic_controls.json"), ids=lambda c: c["id"])
def test_frozen_clinical_context_control(control):
    statements = efficacy_statements(
        control["text"], asset_names=control["asset_names"], document_id="control"
    )
    assert bool(statements) is control["expected_pass"]
    if not statements:
        assert (
            human_poc_evidence(
                "asset:control", results=[], statements=[], as_of_date=date(2026, 10, 11)
            )
            is None
        )


@pytest.mark.parametrize("control", _load("structured_controls.json"), ids=lambda c: c["id"])
def test_frozen_structured_population_control(control):
    assert (
        result_supports_human_poc(ClinicalResult.model_validate(control["result"]))
        is control["expected_pass"]
    )


@pytest.mark.parametrize("call", _load("existing_test_population.json"), ids=lambda c: c["id"][:12])
def test_all_previous_reader_controls_are_preserved(call):
    if call["route"] == "prose":
        actual = bool(efficacy_statements(**call["inputs"]))
    else:
        actual = result_supports_human_poc(ClinicalResult.model_validate(call["inputs"]))
    assert actual is bool(call["baseline_outputs"])


@pytest.mark.parametrize("witness", _load("witness_adjudications.json"), ids=lambda w: str(w["id"]))
def test_frozen_adjudicated_benchmark_witness(witness):
    population = _load("benchmark_population.json")
    for row in witness["rows"]:
        asset = next(
            a
            for a in population
            if a["run"] == row["run"]
            and any(w["claim"]["claim_id"] == row["claim_id"] for w in a["witnesses"])
        )
        assert (
            bool(efficacy_statements(witness["passage"], asset_names=asset["asset_names"]))
            is witness["expected_pass"]
        )
