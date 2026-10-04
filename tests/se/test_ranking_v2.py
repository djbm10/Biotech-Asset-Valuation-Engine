"""RANKING_LEXICOGRAPHIC v2: a declared target's decision precedes efficacy and maturity.

Policy: ``docs/se_policies/ranking_lexicographic_v2.md``.
"""

from __future__ import annotations

from types import SimpleNamespace

from bve.se.reporting import shortlist as sl


def _gate(target: str | None, poc: str | None = None):
    decisions = []
    if target:
        decisions.append(SimpleNamespace(requirement_id=sl._TARGET_REQUIREMENT_ID, status=SimpleNamespace(value=target)))
    if poc:
        decisions.append(SimpleNamespace(requirement_id=sl._HUMAN_POC_REQUIREMENT_ID, status=SimpleNamespace(value=poc)))
    return SimpleNamespace(decisions=decisions)


def _asset(asset_id: str):
    return SimpleNamespace(asset_id=asset_id, canonical_name=asset_id, target_assertions=[], modality_match=None)


def _key(asset_id, target, poc, stage, declared):
    return sl._rank_key(
        _asset(asset_id), _gate(target, poc), eligible=False,
        stage={asset_id: stage}, human_poc=set(), target_declared=declared,
    )


def test_target_pass_outranks_unknown_with_stronger_evidence_when_declared() -> None:
    passing = _key("a", "PASS", None, 1, True)
    unknown = _key("b", "UNKNOWN", "PASS", 6, True)
    assert passing < unknown


def test_undeclared_keeps_v1_order() -> None:
    passing = _key("a", "PASS", None, 1, False)
    unknown = _key("b", "UNKNOWN", "PASS", 6, False)
    assert unknown < passing


def test_undeclared_key_is_v1_element_for_element() -> None:
    key = _key("a", "UNKNOWN", "PASS", 3, False)
    # eligibility, modality, efficacy, maturity, target decision, assertion, completeness, name, id
    # completeness is -1: the human-PoC decision is the one PASS decision.
    assert key == (1, 0, 0, -3, 1, len(sl._TARGET_PRECEDENCE), -1, "a", "a")


def test_declared_only_moves_the_target_decision() -> None:
    v1 = _key("a", "UNKNOWN", "PASS", 3, False)
    v2 = _key("a", "UNKNOWN", "PASS", 3, True)
    assert v2 == (v1[0], v1[1], v1[4], v1[2], v1[3], *v1[5:])


def test_within_a_target_status_efficacy_still_orders() -> None:
    assert _key("a", "PASS", "PASS", 2, True) < _key("b", "PASS", None, 6, True)
