from __future__ import annotations

from pathlib import Path

import yaml

from bve.se.gates.engine import GateEngine
from bve.se.schemas.contracts import BuyerProblemV2, GateStatus, NormalizedFact, OverallDisposition


ROOT = Path(__file__).resolve().parents[2]


def _problem() -> BuyerProblemV2:
    return BuyerProblemV2.model_validate(
        yaml.safe_load(
            (ROOT / "examples/configs/se/benchmarks/cd19_or_bcma_tce.yaml").read_text()
        )
    )


def _fact(fact_id: str, fact_type: str, value) -> NormalizedFact:
    return NormalizedFact(
        fact_id=fact_id,
        subject_id="asset:1",
        fact_type=fact_type,
        value=value,
        supporting_claim_ids=[f"claim:{fact_id}"],
        confidence=0.9,
    )


def _eligible_facts() -> list[NormalizedFact]:
    return [
        _fact("identity", "identity_valid", True),
        _fact("targets", "construct_target_set", ["CD19"]),
        _fact("modality", "modality_id", "T_CELL_ENGAGER"),
        _fact("ta", "therapeutic_area", "oncology"),
        _fact("stage", "development_stage_order", 2),
        _fact("poc", "human_poc_present", True),
        _fact("access", "available_deal_routes", ["LICENSE"]),
    ]


def test_all_pass_asset_is_eligible() -> None:
    result = GateEngine().evaluate(_problem(), subject_id="asset:1", facts=_eligible_facts())
    assert result.disposition == OverallDisposition.ELIGIBLE
    assert result.review_items == []
    assert all(decision.status == GateStatus.PASS for decision in result.decisions)


def test_missing_fact_is_unresolved_and_always_routed_to_review() -> None:
    facts = [fact for fact in _eligible_facts() if fact.fact_type != "human_poc_present"]
    result = GateEngine().evaluate(_problem(), subject_id="asset:1", facts=facts)
    assert result.disposition == OverallDisposition.UNRESOLVED
    assert any(item.requirement_id == "evidence.human_poc" for item in result.review_items)
    assert len(result.review_items) == sum(
        decision.status == GateStatus.UNKNOWN for decision in result.decisions
    )


def test_confirmed_mismatch_excludes_even_with_other_unknowns() -> None:
    facts = [fact for fact in _eligible_facts() if fact.fact_type != "human_poc_present"]
    facts = [
        fact.model_copy(update={"value": "CELL_THERAPY"})
        if fact.fact_type == "modality_id"
        else fact
        for fact in facts
    ]
    result = GateEngine().evaluate(_problem(), subject_id="asset:1", facts=facts)
    assert result.disposition == OverallDisposition.EXCLUDED
    assert any(
        decision.gate_id == "modality_technology" and decision.status == GateStatus.FAIL
        for decision in result.decisions
    )
