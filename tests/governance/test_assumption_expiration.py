"""Tests for assumption ownership and expiration enforcement."""

import warnings
from datetime import date, timedelta

import pytest

from bve.governance.assumption_owner import (
    ApprovalStatus,
    AssumptionOwner,
    OwnerRole,
)
from bve.governance.assumption_review import AssumptionReviewer, StaleInputWarning
from bve.reporting.assumption_status_table import render_assumption_status_table


def make_owner(
    field="peak_penetration",
    last_reviewed_days_ago=10,
    review_frequency_days=90,
    approval_status=ApprovalStatus.APPROVED,
    owner_name=None,
) -> AssumptionOwner:
    today = date.today()
    last_reviewed = today - timedelta(days=last_reviewed_days_ago)
    expiration = last_reviewed + timedelta(days=review_frequency_days)
    return AssumptionOwner(
        field_path=field,
        owner_role=OwnerRole.COMMERCIAL,
        owner_name=owner_name,
        last_reviewed_at=last_reviewed,
        review_frequency_days=review_frequency_days,
        expiration_date=expiration,
        approval_status=approval_status,
        source="analyst estimate",
        confidence="medium",
    )


def make_expired_owner(field="net_price") -> AssumptionOwner:
    today = date.today()
    last_reviewed = today - timedelta(days=100)
    expiration = last_reviewed + timedelta(days=90)  # expired 10 days ago
    return AssumptionOwner(
        field_path=field,
        owner_role=OwnerRole.COMMERCIAL,
        last_reviewed_at=last_reviewed,
        review_frequency_days=90,
        expiration_date=expiration,
        approval_status=ApprovalStatus.APPROVED,
    )


class TestAssumptionOwner:
    def test_not_expired_when_within_period(self):
        o = make_owner(last_reviewed_days_ago=10, review_frequency_days=90)
        assert not o.is_expired()

    def test_expired_when_past_expiration(self):
        o = make_expired_owner()
        assert o.is_expired()

    def test_effective_status_returns_expired(self):
        o = make_expired_owner()
        assert o.effective_status() == ApprovalStatus.EXPIRED

    def test_effective_status_returns_approved_when_fresh(self):
        o = make_owner(approval_status=ApprovalStatus.APPROVED)
        assert o.effective_status() == ApprovalStatus.APPROVED

    def test_days_until_expiry_positive_when_fresh(self):
        o = make_owner(last_reviewed_days_ago=0, review_frequency_days=90)
        assert o.days_until_expiry() > 0

    def test_days_until_expiry_negative_when_expired(self):
        o = make_expired_owner()
        assert o.days_until_expiry() < 0

    def test_display_dict_keys(self):
        o = make_owner()
        d = o.to_display_dict()
        assert "field" in d
        assert "owner" in d
        assert "status" in d
        assert "expires" in d

    def test_owner_name_in_display(self):
        o = make_owner(owner_name="Dr. Smith")
        d = o.to_display_dict()
        assert "Dr. Smith" in d["owner"]

    def test_expiration_date_must_be_after_last_reviewed(self):
        today = date.today()
        with pytest.raises(ValueError):
            AssumptionOwner(
                field_path="peak_penetration",
                owner_role=OwnerRole.COMMERCIAL,
                last_reviewed_at=today,
                review_frequency_days=90,
                expiration_date=today - timedelta(days=1),
                approval_status=ApprovalStatus.APPROVED,
            )


class TestAssumptionReviewer:
    def setup_method(self):
        self.reviewer = AssumptionReviewer()

    def test_no_warnings_when_all_approved_and_fresh(self):
        owners = [make_owner(field=f) for f in ["peak_penetration", "net_price"]]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            report = self.reviewer.review(owners)
        assert not report.has_stale_inputs
        assert len([x for x in w if issubclass(x.category, StaleInputWarning)]) == 0

    def test_stale_warning_emitted_for_expired(self):
        owners = [make_expired_owner()]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            report = self.reviewer.review(owners)
        assert report.has_stale_inputs
        stale_warnings = [x for x in w if issubclass(x.category, StaleInputWarning)]
        assert len(stale_warnings) == 1

    def test_no_warning_emitted_when_emit_warnings_false(self):
        owners = [make_expired_owner()]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            report = self.reviewer.review(owners, emit_warnings=False)
        assert report.has_stale_inputs
        stale_warnings = [x for x in w if issubclass(x.category, StaleInputWarning)]
        assert len(stale_warnings) == 0

    def test_mna_classification_capped_when_stale(self):
        owners = [make_expired_owner()]
        report = self.reviewer.review(owners, emit_warnings=False)
        assert report.max_allowed_mna_classification == "catalyst_watch"

    def test_mna_classification_unrestricted_when_fresh(self):
        owners = [make_owner()]
        report = self.reviewer.review(owners, emit_warnings=False)
        assert report.max_allowed_mna_classification == "active_pursuit"

    def test_precise_probability_disabled_when_stale(self):
        owners = [make_expired_owner()]
        report = self.reviewer.review(owners, emit_warnings=False)
        assert not report.precise_probability_display_allowed

    def test_expiring_soon_detected(self):
        today = date.today()
        last_reviewed = today - timedelta(days=85)
        expiration = last_reviewed + timedelta(days=90)  # expires in 5 days
        o = AssumptionOwner(
            field_path="discount_rate",
            owner_role=OwnerRole.FINANCE,
            last_reviewed_at=last_reviewed,
            review_frequency_days=90,
            expiration_date=expiration,
            approval_status=ApprovalStatus.APPROVED,
        )
        report = self.reviewer.review([o], emit_warnings=False)
        assert len(report.expiring_soon) == 1

    def test_mixed_report_counts_correctly(self):
        owners = [
            make_owner("peak_penetration"),
            make_expired_owner("net_price"),
            make_owner("discount_rate", approval_status=ApprovalStatus.DRAFT),
        ]
        report = self.reviewer.review(owners, emit_warnings=False)
        assert len(report.expired) == 1
        assert len(report.approved) == 1
        assert len(report.unreviewed) == 1

    def test_summary_lines_contains_stale_label(self):
        owners = [make_expired_owner()]
        report = self.reviewer.review(owners, emit_warnings=False)
        summary = "\n".join(report.summary_lines())
        assert "STALE" in summary


class TestAssumptionStatusTable:
    def test_renders_markdown_table(self):
        owners = [make_owner(), make_expired_owner()]
        table = render_assumption_status_table(owners, emit_warnings=False)
        assert "| Assumption |" in table
        assert "STALE_INPUT" in table

    def test_renders_without_expired(self):
        owners = [make_owner()]
        table = render_assumption_status_table(owners, emit_warnings=False)
        assert "STALE_INPUT" not in table
        assert "| Assumption |" in table
