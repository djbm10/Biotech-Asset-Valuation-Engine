"""Tests for the review-first score-update gate (commit 2)."""
from __future__ import annotations

from bve.intelligence import score_update_policy as policy
from bve.intelligence.taxonomy import EventType


class TestDecide:
    def test_small_minor_event_auto_applies(self):
        decision, _ = policy.decide(0.02, (EventType.PAYER_COVERAGE.value,))
        assert decision == policy.DECISION_AUTO_APPLY

    def test_material_delta_forces_review(self):
        decision, reason = policy.decide(0.06, (EventType.PAYER_COVERAGE.value,))
        assert decision == policy.DECISION_REVIEW
        assert "delta" in reason

    def test_threshold_boundary_is_review(self):
        # exactly at threshold → review (>=)
        decision, _ = policy.decide(policy.AUTO_APPLY_THRESHOLD, (EventType.PAYER_COVERAGE.value,))
        assert decision == policy.DECISION_REVIEW

    def test_major_event_forces_review_even_when_tiny(self):
        decision, reason = policy.decide(0.001, (EventType.TRIAL_READOUT.value,))
        assert decision == policy.DECISION_REVIEW
        assert "major" in reason

    def test_fda_rejection_forces_review(self):
        decision, _ = policy.decide(0.0, (EventType.FDA_REJECTION.value,))
        assert decision == policy.DECISION_REVIEW

    def test_safety_signal_forces_review(self):
        decision, _ = policy.decide(0.01, (EventType.SAFETY_SIGNAL.value,))
        assert decision == policy.DECISION_REVIEW

    def test_negative_material_move_forces_review(self):
        decision, _ = policy.decide(-0.10, (EventType.PAYER_COVERAGE.value,))
        assert decision == policy.DECISION_REVIEW

    def test_no_events_small_delta_auto_applies(self):
        decision, _ = policy.decide(0.01, ())
        assert decision == policy.DECISION_AUTO_APPLY

    def test_unknown_event_type_does_not_crash(self):
        decision, _ = policy.decide(0.01, ("not_a_real_event",))
        assert decision == policy.DECISION_AUTO_APPLY
