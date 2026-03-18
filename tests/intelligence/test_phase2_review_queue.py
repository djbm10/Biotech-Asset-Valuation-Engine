from __future__ import annotations

from datetime import date, datetime, timezone

from bve.intelligence.phase2 import ReviewQueue
from bve.intelligence.schemas.proposals import AssumptionChangeProposal
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import ChangeMode, EventType

_NOW = datetime(2026, 1, 7, 9, 0, tzinfo=timezone.utc)


def _signal(confidence: float = 0.95) -> StructuredSignal:
    return StructuredSignal(
        id="sig-financing",
        event_id="evt-financing",
        asset_id="asset-1",
        company_id="company-1",
        event_type=EventType.FINANCING,
        signal_date=date(2026, 1, 7),
        extraction_confidence=confidence,
        extraction_model="test",
        created_at=_NOW,
    )


def _proposal(
    *,
    proposal_id: str,
    change_mode: ChangeMode,
    current_value: float,
    proposed_value: float,
    bound_pct: float | None,
) -> AssumptionChangeProposal:
    return AssumptionChangeProposal(
        id=proposal_id,
        signal_id="sig-financing",
        asset_id="asset-1",
        engine_asset_id="asset-1",
        parameter_path="asset.discount_rate",
        current_value=current_value,
        proposed_value=proposed_value,
        change_mode=change_mode,
        bound_pct=bound_pct,
        event_type=EventType.FINANCING,
        rationale="test",
        created_at=_NOW,
    )


def test_threshold_and_mode_routing():
    queue = ReviewQueue()
    signal = _signal(confidence=0.95)
    small_auto = _proposal(
        proposal_id="p-small",
        change_mode=ChangeMode.AUTO,
        current_value=100.0,
        proposed_value=104.0,  # +4%
        bound_pct=10.0,
    )
    large_auto = _proposal(
        proposal_id="p-large",
        change_mode=ChangeMode.AUTO,
        current_value=100.0,
        proposed_value=125.0,  # +25%
        bound_pct=30.0,
    )
    bounded = _proposal(
        proposal_id="p-bounded",
        change_mode=ChangeMode.BOUNDED,
        current_value=100.0,
        proposed_value=105.0,
        bound_pct=10.0,
    )

    routed = queue.route(signal, [small_auto, large_auto, bounded], queued_at=_NOW)

    auto_ids = {p.id for p in routed.auto_apply}
    queued_ids = {q.proposal_id for q in routed.queued}

    assert auto_ids == {"p-small"}
    assert queued_ids == {"p-large", "p-bounded"}


def test_reviewer_decision_logging_and_effective_overrides():
    queue = ReviewQueue()
    signal = _signal(confidence=0.95)
    auto_prop = _proposal(
        proposal_id="p-auto",
        change_mode=ChangeMode.AUTO,
        current_value=100.0,
        proposed_value=103.0,
        bound_pct=10.0,
    )
    review_prop = _proposal(
        proposal_id="p-review",
        change_mode=ChangeMode.BOUNDED,
        current_value=100.0,
        proposed_value=120.0,
        bound_pct=25.0,
    )
    routed = queue.route(signal, [auto_prop, review_prop], queued_at=_NOW)
    assert len(routed.queued) == 1

    item = routed.queued[0]
    decision = queue.record_decision(
        item_id=item.id,
        decision="accepted",
        reviewer_id="analyst-1",
        rationale="Accept with smaller override",
        override_value=110.0,
        reviewed_at=_NOW,
    )
    assert decision.decision == "accepted"
    assert decision.override_value == 110.0

    overrides = queue.effective_overrides([auto_prop, review_prop])
    assert overrides == {
        "p-auto": 103.0,
        "p-review": 110.0,
    }


def test_materiality_threshold_uses_absolute_relative_change():
    queue = ReviewQueue()
    signal = _signal(confidence=0.95)

    # 10 -> 11 is +10% relative change.
    at_threshold = AssumptionChangeProposal(
        id="p-threshold",
        signal_id="sig-financing",
        asset_id="asset-1",
        engine_asset_id="asset-1",
        parameter_path="asset.discount_rate",
        current_value=10.0,
        proposed_value=11.0,
        change_mode=ChangeMode.AUTO,
        bound_pct=10.0,
        event_type=EventType.FINANCING,
        rationale="test",
        created_at=_NOW,
    )
    # 10 -> 11.3 is +13% relative change.
    above_threshold = AssumptionChangeProposal(
        id="p-above",
        signal_id="sig-financing",
        asset_id="asset-1",
        engine_asset_id="asset-1",
        parameter_path="asset.discount_rate",
        current_value=10.0,
        proposed_value=11.3,
        change_mode=ChangeMode.AUTO,
        bound_pct=20.0,
        event_type=EventType.FINANCING,
        rationale="test",
        created_at=_NOW,
    )

    routed = queue.route(signal, [at_threshold, above_threshold], queued_at=_NOW)
    auto_ids = {p.id for p in routed.auto_apply}
    queued_ids = {q.proposal_id for q in routed.queued}

    assert "p-threshold" in auto_ids
    assert "p-above" in queued_ids
