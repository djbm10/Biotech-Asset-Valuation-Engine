"""Grammatical role precedence; certificates covered by target-reference compatibility."""
from bve.se.intent import parser
from bve.se.intent.compiler import compile_intent, build_buyer_identity
from bve.se.intent.intent import SpanKind


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
