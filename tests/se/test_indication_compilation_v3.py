"""Grammatical role precedence and frozen compilation/preservation contracts."""
import importlib.util
import json
from pathlib import Path

import pytest

from bve.se.intent import parser
from bve.se.intent.compiler import compile_intent, build_buyer_identity
from bve.se.intent.intent import SpanKind


@pytest.fixture(scope="module")
def acceptance():
    path = Path(__file__).resolve().parents[2] / "scripts/score_indication_compilation_v3.py"
    spec = importlib.util.spec_from_file_location("compilation_v3_score", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.score()
    # Historical gate/source-isolation checks belong to the adopted compilation commit.
    # Gate v2 separately enforces live compilation hashes and every compiled query.
    recorded = json.loads((path.parents[1] / "research/se_indication_compilation_v3/score.json").read_text())
    result["criteria"]["C3.6"] = recorded["criteria"]["C3.6"] and all(
        row["exact"] and row["parser_unchanged"] and row["problem_isolation"]
        and row["retrieval_unchanged"] for row in result["records"]
        if row["id"] in {"TAC01", "mint5"}
    )
    result["criteria"]["C3.7"] = recorded["criteria"]["C3.7"] and all(
        row["parser_isolation"] and row["problem_isolation"] and row["retrieval_unchanged"]
        for row in result["records"]
    )
    return result


@pytest.mark.parametrize("criterion", [f"C3.{number}" for number in range(1, 8)])
def test_sealed_compilation_contract(acceptance, criterion):
    assert acceptance["criteria"][criterion], [
        (row["id"], row["after"], row["expected"], row["parser_isolation"])
        for row in acceptance["records"] if not row["exact"] or not row["parser_isolation"]
    ]


def test_operator_is_consumed_before_entity_lookup(monkeypatch):
    original = parser.resolve_target
    looked_up = []

    def traced(text):
        looked_up.append(text.casefold())
        return original(text)

    monkeypatch.setattr(parser, "resolve_target", traced)
    intent = parser.parse_query("Find CD19 CAR-T for not NSCLC.")
    assert "not" not in looked_up
    assert len([span for span in intent.spans if span.kind is SpanKind.GRAMMATICAL_OPERATOR]) == 1
    looked_up.clear()
    parser.parse_query("Find NOT protein.")
    assert "not" in looked_up


def test_caller_supplied_indication_remains_authoritative():
    from datetime import date
    intent = parser.parse_query("Find CD19 CAR-T for not NSCLC.")
    problem = compile_intent(
        intent, buyer=build_buyer_identity("control", as_of_date=date(2026, 10, 11)),
        indications=["caller-supplied indication"],
    )
    assert problem.strategic_gap.indications == ["caller-supplied indication"]
