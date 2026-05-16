"""Audit log of all review actions."""

from __future__ import annotations


from .review_state import OutputReviewStatus, OutputType, ReviewRecord, ReviewState
from .review_policy import ReviewPolicy


class ApprovalLog:
    """In-memory log of output reviews. Back with a database in production."""

    def __init__(self, policy: ReviewPolicy | None = None) -> None:
        self._outputs: dict[str, OutputReviewStatus] = {}
        self._policy = policy or ReviewPolicy()

    def register(self, output_id: str, output_type: OutputType) -> OutputReviewStatus:
        """Register a new output for review."""
        status = OutputReviewStatus(output_id=output_id, output_type=output_type)
        self._outputs[output_id] = status
        return status

    def submit_review(
        self,
        output_id: str,
        reviewer_role: str,
        action: str,
        reviewer_name: str | None = None,
        comment: str | None = None,
    ) -> ReviewRecord:
        status = self._get_or_raise(output_id)
        approved_roles_after = status.approver_roles | {reviewer_role} if action == "approve" else status.approver_roles

        if action == "reject":
            new_state = ReviewState.REJECTED
        elif self._policy.is_ic_ready(status.output_type, approved_roles_after):
            new_state = ReviewState.APPROVED
        elif len(approved_roles_after) >= 1:
            new_state = ReviewState.ANALYST_REVIEWED
        else:
            new_state = ReviewState.DRAFT

        record = ReviewRecord(
            output_id=output_id,
            output_type=status.output_type,
            reviewer_role=reviewer_role,
            reviewer_name=reviewer_name,
            action=action,
            comment=comment,
            state_after=new_state,
        )
        status.add_review(record)
        return record

    def get_status(self, output_id: str) -> OutputReviewStatus | None:
        return self._outputs.get(output_id)

    def is_ic_ready(self, output_id: str) -> bool:
        status = self._outputs.get(output_id)
        if status is None:
            return False
        return status.is_ic_ready

    def missing_approvals(self, output_id: str) -> list[str]:
        status = self._outputs.get(output_id)
        if status is None:
            return []
        return self._policy.missing_approvals(status.output_type, status.approver_roles)

    def audit_trail(self, output_id: str) -> list[dict]:
        status = self._outputs.get(output_id)
        if status is None:
            return []
        return [
            {
                "output_id": r.output_id,
                "reviewer_role": r.reviewer_role,
                "reviewer_name": r.reviewer_name,
                "action": r.action,
                "comment": r.comment,
                "reviewed_at": r.reviewed_at.isoformat(),
                "state_after": r.state_after.value,
            }
            for r in status.reviews
        ]

    def _get_or_raise(self, output_id: str) -> OutputReviewStatus:
        status = self._outputs.get(output_id)
        if status is None:
            raise KeyError(f"Output '{output_id}' not registered in approval log")
        return status
