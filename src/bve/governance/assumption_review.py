"""Assumption expiration enforcement and STALE_INPUT warnings."""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from datetime import date
from typing import Sequence

from .assumption_owner import AssumptionOwner, ApprovalStatus


class StaleInputWarning(UserWarning):
    """Raised when a valuation run uses expired assumptions."""


@dataclass
class AssumptionReviewReport:
    """Summary of assumption review status for a valuation run."""

    as_of: date
    owners: list[AssumptionOwner]
    expired: list[AssumptionOwner] = field(default_factory=list)
    expiring_soon: list[AssumptionOwner] = field(default_factory=list)
    unreviewed: list[AssumptionOwner] = field(default_factory=list)
    approved: list[AssumptionOwner] = field(default_factory=list)

    @property
    def has_stale_inputs(self) -> bool:
        return len(self.expired) > 0

    @property
    def max_allowed_mna_classification(self) -> str:
        """With any expired assumption, M&A classification is capped at catalyst_watch."""
        if self.has_stale_inputs:
            return "catalyst_watch"
        return "active_pursuit"

    @property
    def precise_probability_display_allowed(self) -> bool:
        return not self.has_stale_inputs

    def summary_lines(self) -> list[str]:
        lines = [f"Assumption Review as of {self.as_of.isoformat()}"]
        lines.append(f"  Total: {len(self.owners)}  Approved: {len(self.approved)}  "
                     f"Expired: {len(self.expired)}  Expiring soon: {len(self.expiring_soon)}")
        if self.expired:
            lines.append("  STALE INPUTS:")
            for o in self.expired:
                lines.append(f"    - {o.field_path} (expired {o.expiration_date})")
        return lines


class AssumptionReviewer:
    """Validates a set of AssumptionOwner records and emits warnings."""

    EXPIRING_SOON_DAYS = 14

    def review(
        self,
        owners: Sequence[AssumptionOwner],
        as_of: date | None = None,
        emit_warnings: bool = True,
    ) -> AssumptionReviewReport:
        check_date = as_of or date.today()
        expired = []
        expiring_soon = []
        unreviewed = []
        approved = []

        for o in owners:
            status = o.effective_status(check_date)
            if status == ApprovalStatus.EXPIRED:
                expired.append(o)
            elif o.days_until_expiry(check_date) <= self.EXPIRING_SOON_DAYS:
                expiring_soon.append(o)
            elif status in (ApprovalStatus.DRAFT, ApprovalStatus.REVIEWED):
                unreviewed.append(o)
            elif status == ApprovalStatus.APPROVED:
                approved.append(o)

        report = AssumptionReviewReport(
            as_of=check_date,
            owners=list(owners),
            expired=expired,
            expiring_soon=expiring_soon,
            unreviewed=unreviewed,
            approved=approved,
        )

        if emit_warnings and report.has_stale_inputs:
            fields = ", ".join(o.field_path for o in expired)
            warnings.warn(
                f"STALE_INPUT: {len(expired)} expired assumption(s): {fields}. "
                "Valuation can proceed but M&A classification is capped at catalyst_watch "
                "and precise probability display is disabled.",
                StaleInputWarning,
                stacklevel=2,
            )

        return report
