"""Review state machine for model outputs."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ReviewState(str, Enum):
    DRAFT = "draft"
    ANALYST_REVIEWED = "analyst_reviewed"
    CROSS_FUNCTIONAL_REVIEWED = "cross_functional_reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OutputType(str, Enum):
    BD_MEMO = "bd_memo"
    HF_TRADE = "hf_trade"
    MNA_PROBABILITY = "mna_probability"
    POS_OVERRIDE = "pos_override"
    VALUATION_OUTPUT = "valuation_output"
    WATCHLIST_CLASSIFICATION = "watchlist_classification"


class ReviewRecord(BaseModel):
    """Tracks one review action on an output."""

    output_id: str
    output_type: OutputType
    reviewer_role: str
    reviewer_name: str | None = None
    action: Literal["approve", "reject", "comment"]
    comment: str | None = None
    reviewed_at: datetime = Field(default_factory=datetime.utcnow)
    state_after: ReviewState


class OutputReviewStatus(BaseModel):
    """Current review status of a model output."""

    output_id: str
    output_type: OutputType
    current_state: ReviewState = ReviewState.DRAFT
    created_at: datetime = Field(default_factory=datetime.utcnow)
    reviews: list[ReviewRecord] = Field(default_factory=list)
    expires_at: date | None = None

    @property
    def is_ic_ready(self) -> bool:
        return self.current_state == ReviewState.APPROVED

    @property
    def approver_roles(self) -> set[str]:
        return {r.reviewer_role for r in self.reviews if r.action == "approve"}

    def add_review(self, record: ReviewRecord) -> None:
        self.reviews.append(record)
        self.current_state = record.state_after
