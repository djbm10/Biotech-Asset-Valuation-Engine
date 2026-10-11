"""Grammatical role precedence and frozen compilation/preservation contracts."""
import importlib.util
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
    return module.score()


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
