"""Formal assumption ownership — who set it, when, and when it expires."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class OwnerRole(str, Enum):
    CLINICAL = "clinical"
    COMMERCIAL = "commercial"
    REGULATORY = "regulatory"
    BD = "bd"
    FINANCE = "finance"
    MARKET_ACCESS = "market_access"
    QUANT = "quant"


class ApprovalStatus(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    EXPIRED = "expired"


# Material assumptions that must have documented ownership
MATERIAL_ASSUMPTIONS: frozenset[str] = frozenset(
    [
        "phase_success_probability",
        "endpoint_adjuster",
        "peak_penetration",
        "net_price",
        "addressable_patients",
        "competition_haircut",
        "trial_cost",
        "trial_duration",
        "discount_rate",
        "takeout_premium",
        "acquirer_fit_score",
    ]
)


class AssumptionOwner(BaseModel):
    """Documents ownership of a single model assumption."""

    field_path: str = Field(description="Dot-path to the assumption, e.g. 'market_model.peak_penetration'")
    owner_role: OwnerRole
    owner_name: str | None = None
    last_reviewed_at: date
    review_frequency_days: int = Field(gt=0)
    expiration_date: date
    approval_status: ApprovalStatus = ApprovalStatus.DRAFT
    source: str | None = Field(default=None, description="Data source or rationale for this value")
    confidence: str | None = Field(
        default=None, description="Confidence level: low | medium | high"
    )
    value_snapshot: Any = Field(default=None, description="The value at last review")

    @model_validator(mode="after")
    def _expiration_consistent(self) -> "AssumptionOwner":
        if self.expiration_date.toordinal() < self.last_reviewed_at.toordinal():
            raise ValueError("expiration_date must be >= last_reviewed_at")
        return self

    def is_expired(self, as_of: date | None = None) -> bool:
        check_date = as_of or date.today()
        return check_date > self.expiration_date

    def days_until_expiry(self, as_of: date | None = None) -> int:
        check_date = as_of or date.today()
        return (self.expiration_date - check_date).days

    def effective_status(self, as_of: date | None = None) -> ApprovalStatus:
        if self.is_expired(as_of):
            return ApprovalStatus.EXPIRED
        return self.approval_status

    def to_display_dict(self, as_of: date | None = None) -> dict:
        return {
            "field": self.field_path,
            "owner": f"{self.owner_role.value}" + (f" ({self.owner_name})" if self.owner_name else ""),
            "status": self.effective_status(as_of).value,
            "last_reviewed": self.last_reviewed_at.isoformat(),
            "expires": self.expiration_date.isoformat(),
            "days_remaining": self.days_until_expiry(as_of),
            "source": self.source or "unspecified",
            "confidence": self.confidence or "unspecified",
        }
