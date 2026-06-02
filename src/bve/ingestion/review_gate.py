"""
Human review gate and score mode control.

Review gate
-----------
High-materiality events above a configurable threshold are flagged for human
review before they propagate into live scores. A `ReviewDecision` encodes the
reviewer's disposition: APPROVE / REJECT / DOWNGRADE.

Score modes
-----------
Three modes control which events are counted in `EvidenceLedger.compute_score_state()`:

  approved_only   — only events with review_status=APPROVED count
                    (highest precision; requires staffed review pipeline)
  provisional     — APPROVED events count at full weight;
                    PENDING events count at 50% weight;
                    REJECTED events are excluded
                    (default for live operation)
  all_auto        — all non-rejected events count regardless of review status
                    (for rapid prototyping / backtests without a review queue)

ScoreMode is an enum; passing the wrong string raises ValueError at construction,
preventing silent misconfiguration.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Review status / decision
# ---------------------------------------------------------------------------


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DOWNGRADED = "downgraded"  # approved but at reduced weight


class ScoreMode(str, Enum):
    APPROVED_ONLY = "approved_only"
    PROVISIONAL = "provisional"
    ALL_AUTO = "all_auto"


# Default threshold above which events are auto-flagged for review
DEFAULT_REVIEW_THRESHOLD = 0.70  # materiality >= 0.70 → queued


@dataclass
class ReviewDecision:
    """
    A reviewer's disposition for one evidence record.

    Fields
    ------
    event_hash      : unique record identifier (from EvidenceRecord.event_hash)
    status          : the reviewer's final call
    downgrade_factor: multiplier on delta when status=DOWNGRADED (0..1)
    reviewer_id     : optional reviewer identifier for audit
    notes           : optional free-text rationale
    reviewed_at     : ISO date string
    """

    event_hash: str
    status: ReviewStatus
    downgrade_factor: float = 1.0   # only used when status=DOWNGRADED
    reviewer_id: Optional[str] = None
    notes: Optional[str] = None
    reviewed_at: Optional[str] = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.downgrade_factor <= 1.0:
            raise ValueError(
                f"downgrade_factor must be in [0, 1], got {self.downgrade_factor}"
            )
        if self.status == ReviewStatus.DOWNGRADED and self.downgrade_factor == 1.0:
            raise ValueError(
                "DOWNGRADED decision must set downgrade_factor < 1.0"
            )


# ---------------------------------------------------------------------------
# ReviewGate
# ---------------------------------------------------------------------------


class ReviewGate:
    """
    Flag evidence records that require human review and apply review decisions.

    Usage::

        gate = ReviewGate(threshold=0.65)
        needs_review = gate.needs_review(materiality=0.80)  # True

        decision = ReviewDecision(
            event_hash="abc123",
            status=ReviewStatus.APPROVED,
        )
        gate.record_decision(decision)

        factor = gate.weight_factor("abc123", ScoreMode.PROVISIONAL)
        # 1.0 if APPROVED, 0.5 if PENDING, 0.0 if REJECTED
    """

    def __init__(self, threshold: float = DEFAULT_REVIEW_THRESHOLD) -> None:
        self._threshold = threshold
        self._decisions: dict[str, ReviewDecision] = {}

    # ------------------------------------------------------------------
    # Flagging
    # ------------------------------------------------------------------

    def needs_review(self, materiality: float) -> bool:
        """Return True if materiality exceeds the review threshold."""
        return materiality >= self._threshold

    # ------------------------------------------------------------------
    # Decision management
    # ------------------------------------------------------------------

    def record_decision(self, decision: ReviewDecision) -> None:
        """Store a review decision; overwrites any previous decision for same hash."""
        self._decisions[decision.event_hash] = decision

    def get_decision(self, event_hash: str) -> Optional[ReviewDecision]:
        return self._decisions.get(event_hash)

    def get_status(self, event_hash: str) -> ReviewStatus:
        """Return the review status; PENDING if no decision recorded."""
        d = self._decisions.get(event_hash)
        return d.status if d else ReviewStatus.PENDING

    # ------------------------------------------------------------------
    # Weight factor per score mode
    # ------------------------------------------------------------------

    def weight_factor(self, event_hash: str, mode: ScoreMode) -> float:
        """
        Return the weight multiplier (0..1) for one event given the score mode.

        approved_only : APPROVED→1.0, DOWNGRADED→factor, PENDING→0.0, REJECTED→0.0
        provisional   : APPROVED→1.0, DOWNGRADED→factor, PENDING→0.5,  REJECTED→0.0
        all_auto      : APPROVED→1.0, DOWNGRADED→factor, PENDING→1.0,  REJECTED→0.0
        """
        decision = self._decisions.get(event_hash)
        status = decision.status if decision else ReviewStatus.PENDING

        if status == ReviewStatus.REJECTED:
            return 0.0
        if status == ReviewStatus.DOWNGRADED:
            return decision.downgrade_factor  # type: ignore[union-attr]
        if status == ReviewStatus.APPROVED:
            return 1.0

        # PENDING — depends on mode
        if mode == ScoreMode.APPROVED_ONLY:
            return 0.0
        if mode == ScoreMode.PROVISIONAL:
            return 0.5
        # ALL_AUTO
        return 1.0

    # ------------------------------------------------------------------
    # Bulk helpers
    # ------------------------------------------------------------------

    def pending_hashes(self) -> list[str]:
        """Return event_hashes that need review (no decision yet OR still PENDING)."""
        # Any hash we don't have a decision for is implicitly pending
        # (The caller must supply the full set of event hashes to identify all pending)
        return [
            h
            for h, d in self._decisions.items()
            if d.status == ReviewStatus.PENDING
        ]

    def summary(self) -> dict[str, int]:
        """Count decisions by status."""
        counts: dict[str, int] = {s.value: 0 for s in ReviewStatus}
        for d in self._decisions.values():
            counts[d.status.value] += 1
        return counts
