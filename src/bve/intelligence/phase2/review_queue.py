"""
Phase 2 review queue and routing.

Routes proposals to auto-apply or manual review based on:
  - mapping rule mode (AUTO/BOUNDED/MANUAL)
  - signal confidence
  - materiality threshold
  - event-specific routing policy
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

from bve.intelligence.phase2.policy import MappingPolicy
from bve.intelligence.schemas.proposals import AssumptionChangeProposal
from bve.intelligence.schemas.runs import ReviewDecision
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import ChangeMode


class ReviewQueueItem(BaseModel):
    """Manual-review queue entry for one proposal."""

    id: str
    proposal_id: str
    signal_id: str
    route_reason: str
    queued_at: datetime
    status: Literal["pending", "accepted", "rejected", "deferred"] = "pending"


class ReviewRoutingResult(BaseModel):
    """Result of routing a proposal batch."""

    auto_apply: list[AssumptionChangeProposal] = Field(default_factory=list)
    queued: list[ReviewQueueItem] = Field(default_factory=list)


class ReviewQueue:
    """In-memory review queue with decision logging."""

    def __init__(self, policy: Optional[MappingPolicy] = None) -> None:
        self.policy = policy or MappingPolicy.default()
        self._items_by_id: dict[str, ReviewQueueItem] = {}
        self._proposal_to_item: dict[str, str] = {}
        self._decisions_by_proposal: dict[str, ReviewDecision] = {}
        self._auto_apply_ids: set[str] = set()

    @property
    def items(self) -> list[ReviewQueueItem]:
        return list(self._items_by_id.values())

    @property
    def decisions(self) -> list[ReviewDecision]:
        return list(self._decisions_by_proposal.values())

    def route(
        self,
        signal: StructuredSignal,
        proposals: list[AssumptionChangeProposal],
        *,
        queued_at: Optional[datetime] = None,
    ) -> ReviewRoutingResult:
        queued_at = queued_at or datetime.now(timezone.utc)
        event_policy = self.policy.for_event(signal.event_type)

        auto_apply: list[AssumptionChangeProposal] = []
        queued: list[ReviewQueueItem] = []

        for proposal in proposals:
            route_to_manual, reason = self._requires_manual_review(
                proposal=proposal,
                confidence=signal.extraction_confidence,
                min_confidence=event_policy.min_confidence_score,
                materiality_threshold=event_policy.materiality_threshold_pct,
                review_requirement=event_policy.review_requirement,
            )

            if route_to_manual:
                item = ReviewQueueItem(
                    id=str(uuid.uuid4()),
                    proposal_id=proposal.id,
                    signal_id=signal.id,
                    route_reason=reason,
                    queued_at=queued_at,
                    status="pending",
                )
                self._items_by_id[item.id] = item
                self._proposal_to_item[proposal.id] = item.id
                queued.append(item)
            else:
                self._auto_apply_ids.add(proposal.id)
                auto_apply.append(proposal)

        return ReviewRoutingResult(auto_apply=auto_apply, queued=queued)

    def record_decision(
        self,
        *,
        item_id: str,
        decision: Literal["accepted", "rejected", "deferred"],
        reviewer_id: str,
        rationale: str,
        override_value: Optional[float] = None,
        run_id: Optional[str] = None,
        reviewed_at: Optional[datetime] = None,
        notes: Optional[str] = None,
    ) -> ReviewDecision:
        reviewed_at = reviewed_at or datetime.now(timezone.utc)
        item = self._items_by_id[item_id]
        updated_item = item.model_copy(update={"status": decision})
        self._items_by_id[item_id] = updated_item

        review = ReviewDecision(
            id=str(uuid.uuid4()),
            proposal_id=item.proposal_id,
            run_id=run_id,
            decision=decision,
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
            override_value=override_value,
            rationale=rationale,
            notes=notes,
        )
        self._decisions_by_proposal[item.proposal_id] = review
        return review

    def effective_overrides(
        self,
        proposals: list[AssumptionChangeProposal],
    ) -> dict[str, float]:
        """
        Resolve proposal_id -> effective value for valuation application.

        Rules:
          - Auto-routed proposals are applied at ``proposal.proposed_value``.
          - Manually reviewed proposals are applied only if decision=accepted.
          - ``override_value`` supersedes ``proposal.proposed_value``.
        """
        by_id = {p.id: p for p in proposals}
        resolved: dict[str, float] = {}

        for proposal_id in self._auto_apply_ids:
            if proposal_id in by_id:
                resolved[proposal_id] = by_id[proposal_id].proposed_value

        for proposal_id, review in self._decisions_by_proposal.items():
            if proposal_id not in by_id:
                continue
            if review.decision != "accepted":
                continue
            proposal = by_id[proposal_id]
            resolved[proposal_id] = (
                review.override_value
                if review.override_value is not None
                else proposal.proposed_value
            )

        return resolved

    @staticmethod
    def _requires_manual_review(
        *,
        proposal: AssumptionChangeProposal,
        confidence: float,
        min_confidence: float,
        materiality_threshold: float,
        review_requirement: str,
    ) -> tuple[bool, str]:
        if review_requirement == "manual_only":
            return True, "Event policy enforces manual review"
        if proposal.change_mode in {ChangeMode.BOUNDED, ChangeMode.MANUAL}:
            return True, f"change_mode={proposal.change_mode.value} requires review"
        if confidence < min_confidence:
            return True, (
                f"Signal confidence {confidence:.2f} below minimum {min_confidence:.2f}"
            )
        if abs(proposal.proposed_delta_pct) > materiality_threshold:
            return True, (
                f"Delta {proposal.proposed_delta_pct:.2f}% exceeds "
                f"materiality threshold {materiality_threshold:.2f}%"
            )
        return False, "AUTO proposal within confidence/materiality limits"
