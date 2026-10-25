"""A therapeutic area passed as a bare string must never compile into its letters.

Regression for pilot gucy2c_oncology_v1: ``compile_intent(..., therapeutic_areas="ONCOLOGY")``
produced ``[O, N, C, O, L, O, G, Y]``, which no evidence can satisfy, and the run looked normal.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from bve.se.intent.compiler import build_buyer_identity, compile_intent
from bve.se.intent.parser import parse_query
from bve.se.schemas.contracts import StrategicGap

BUYER = build_buyer_identity("t", as_of_date=date(2026, 10, 24))


@pytest.fixture(scope="module")
def intent():
    return parse_query("GUCY2C programs")


def test_list_compiles_to_one_area(intent) -> None:
    problem = compile_intent(intent, buyer=BUYER, therapeutic_areas=["ONCOLOGY"])
    assert problem.strategic_gap.therapeutic_areas == ["ONCOLOGY"]


@pytest.mark.parametrize("field", ["therapeutic_areas", "indications"])
def test_bare_string_is_refused_by_the_compiler(intent, field: str) -> None:
    with pytest.raises(TypeError, match="list of strings"):
        compile_intent(intent, buyer=BUYER, **{field: "ONCOLOGY"})


@pytest.mark.parametrize("field", ["therapeutic_areas", "indications"])
def test_schema_rejects_exploded_letters(intent, field: str) -> None:
    gap = compile_intent(intent, buyer=BUYER, therapeutic_areas=["ONCOLOGY"]).strategic_gap
    data = gap.model_dump() | {field: list("ONCOLOGY")}
    with pytest.raises(ValidationError, match="shorter than two characters"):
        StrategicGap.model_validate(data)


def test_schema_accepts_ordinary_areas(intent) -> None:
    gap = compile_intent(intent, buyer=BUYER, therapeutic_areas=["ONCOLOGY"]).strategic_gap
    data = gap.model_dump() | {
        "therapeutic_areas": ["ONCOLOGY", "AUTOIMMUNE"],
        "indications": ["colorectal cancer"],
    }
    assert StrategicGap.model_validate(data).therapeutic_areas == ["ONCOLOGY", "AUTOIMMUNE"]


def test_the_frozen_pilot_problem_no_longer_loads() -> None:
    from pathlib import Path

    import yaml  # type: ignore[import-untyped]

    from bve.se.schemas.contracts import BuyerProblemV2

    frozen = Path(__file__).resolve().parents[2] / (
        "research/se_blinded_pilot_v1/gucy2c_oncology_v1/engine_problem.yaml"
    )
    with pytest.raises(ValidationError, match="shorter than two characters"):
        BuyerProblemV2.model_validate(yaml.safe_load(frozen.read_text()))
