"""Tests for review workflow and approval policy."""

import pytest

from bve.workflow.review_state import OutputType, ReviewState
from bve.workflow.review_policy import ReviewPolicy, ReviewRequirement, DEFAULT_REVIEW_POLICY
from bve.workflow.approval_log import ApprovalLog


class TestReviewRequirement:
    def test_satisfied_when_all_required_roles_approved(self):
        req = ReviewRequirement(
            output_type=OutputType.HF_TRADE,
            required_roles=["analyst", "pm"],
            min_approvers=2,
        )
        assert req.is_satisfied({"analyst", "pm"})

    def test_not_satisfied_when_too_few_approvers(self):
        req = ReviewRequirement(
            output_type=OutputType.HF_TRADE,
            required_roles=["analyst", "pm", "risk"],
            min_approvers=2,
        )
        assert not req.is_satisfied({"analyst"})

    def test_missing_roles_returned(self):
        req = ReviewRequirement(
            output_type=OutputType.BD_MEMO,
            required_roles=["clinical", "commercial", "bd"],
            min_approvers=2,
        )
        missing = req.missing_roles({"clinical"})
        assert "commercial" in missing
        assert "bd" in missing
        assert "clinical" not in missing


class TestReviewPolicy:
    def setup_method(self):
        self.policy = ReviewPolicy()

    def test_bd_memo_requires_min_3_approvers(self):
        req = self.policy.requirement(OutputType.BD_MEMO)
        assert req.min_approvers == 3

    def test_hf_trade_requires_min_2_approvers(self):
        req = self.policy.requirement(OutputType.HF_TRADE)
        assert req.min_approvers == 2

    def test_ic_ready_hf_trade_with_correct_roles(self):
        approved = {"analyst", "pm", "risk"}
        assert self.policy.is_ic_ready(OutputType.HF_TRADE, approved)

    def test_not_ic_ready_with_wrong_roles(self):
        approved = {"quant", "data_science"}
        assert not self.policy.is_ic_ready(OutputType.HF_TRADE, approved)

    def test_pos_override_requires_clinical_and_quant(self):
        req = self.policy.requirement(OutputType.POS_OVERRIDE)
        assert "clinical" in req.required_roles
        assert "quant" in req.required_roles


class TestApprovalLog:
    def setup_method(self):
        self.log = ApprovalLog()

    def test_register_creates_draft_status(self):
        status = self.log.register("memo-001", OutputType.BD_MEMO)
        assert status.current_state == ReviewState.DRAFT

    def test_single_approve_moves_to_analyst_reviewed(self):
        self.log.register("memo-001", OutputType.BD_MEMO)
        record = self.log.submit_review("memo-001", "clinical", "approve")
        assert record.state_after == ReviewState.ANALYST_REVIEWED

    def test_reject_moves_to_rejected(self):
        self.log.register("memo-001", OutputType.HF_TRADE)
        record = self.log.submit_review("memo-001", "risk", "reject")
        assert record.state_after == ReviewState.REJECTED

    def test_not_ic_ready_after_single_approve(self):
        self.log.register("trade-001", OutputType.HF_TRADE)
        self.log.submit_review("trade-001", "analyst", "approve")
        assert not self.log.is_ic_ready("trade-001")

    def test_ic_ready_after_sufficient_approvals(self):
        self.log.register("trade-001", OutputType.HF_TRADE)
        self.log.submit_review("trade-001", "analyst", "approve")
        self.log.submit_review("trade-001", "pm", "approve")
        assert self.log.is_ic_ready("trade-001")

    def test_ic_ready_is_false_for_unregistered(self):
        assert not self.log.is_ic_ready("nonexistent")

    def test_missing_approvals_listed(self):
        self.log.register("memo-001", OutputType.HF_TRADE)
        self.log.submit_review("memo-001", "analyst", "approve")
        missing = self.log.missing_approvals("memo-001")
        assert "pm" in missing or "risk" in missing

    def test_audit_trail_records_reviews(self):
        self.log.register("trade-001", OutputType.HF_TRADE)
        self.log.submit_review("trade-001", "analyst", "approve", reviewer_name="Alice")
        trail = self.log.audit_trail("trade-001")
        assert len(trail) == 1
        assert trail[0]["reviewer_role"] == "analyst"
        assert trail[0]["reviewer_name"] == "Alice"

    def test_unknown_output_id_raises(self):
        with pytest.raises(KeyError):
            self.log.submit_review("nonexistent", "analyst", "approve")

    def test_bd_memo_requires_three_of_four_roles(self):
        self.log.register("memo-bd", OutputType.BD_MEMO)
        self.log.submit_review("memo-bd", "clinical", "approve")
        self.log.submit_review("memo-bd", "commercial", "approve")
        assert not self.log.is_ic_ready("memo-bd")  # need 3 minimum
        self.log.submit_review("memo-bd", "bd", "approve")
        assert self.log.is_ic_ready("memo-bd")

    def test_reviewer_name_optional(self):
        self.log.register("trade-001", OutputType.HF_TRADE)
        record = self.log.submit_review("trade-001", "analyst", "approve")
        assert record.reviewer_name is None
