"""Review policy — what roles must approve each output type."""

from __future__ import annotations

from dataclasses import dataclass

from .review_state import OutputType


@dataclass
class ReviewRequirement:
    """Minimum approvals required for an output type to be IC-ready."""

    output_type: OutputType
    required_roles: list[str]
    min_approvers: int = 2

    def is_satisfied(self, approved_roles: set[str]) -> bool:
        matched = {r for r in self.required_roles if r in approved_roles}
        return len(matched) >= self.min_approvers

    def missing_roles(self, approved_roles: set[str]) -> list[str]:
        return [r for r in self.required_roles if r not in approved_roles]


# Default policy — can be overridden in YAML
DEFAULT_REVIEW_POLICY: dict[OutputType, ReviewRequirement] = {
    OutputType.BD_MEMO: ReviewRequirement(
        output_type=OutputType.BD_MEMO,
        required_roles=["clinical", "commercial", "bd", "finance"],
        min_approvers=3,
    ),
    OutputType.HF_TRADE: ReviewRequirement(
        output_type=OutputType.HF_TRADE,
        required_roles=["analyst", "pm", "risk"],
        min_approvers=2,
    ),
    OutputType.MNA_PROBABILITY: ReviewRequirement(
        output_type=OutputType.MNA_PROBABILITY,
        required_roles=["bd", "corporate_strategy", "finance"],
        min_approvers=2,
    ),
    OutputType.POS_OVERRIDE: ReviewRequirement(
        output_type=OutputType.POS_OVERRIDE,
        required_roles=["clinical", "quant"],
        min_approvers=2,
    ),
    OutputType.VALUATION_OUTPUT: ReviewRequirement(
        output_type=OutputType.VALUATION_OUTPUT,
        required_roles=["quant", "finance"],
        min_approvers=1,
    ),
    OutputType.WATCHLIST_CLASSIFICATION: ReviewRequirement(
        output_type=OutputType.WATCHLIST_CLASSIFICATION,
        required_roles=["analyst", "quant"],
        min_approvers=1,
    ),
}


class ReviewPolicy:
    """Evaluates whether an output has sufficient approvals for IC-ready labelling."""

    def __init__(self, requirements: dict[OutputType, ReviewRequirement] | None = None) -> None:
        self._req = requirements or DEFAULT_REVIEW_POLICY

    def requirement(self, output_type: OutputType) -> ReviewRequirement:
        return self._req[output_type]

    def is_ic_ready(self, output_type: OutputType, approved_roles: set[str]) -> bool:
        req = self._req.get(output_type)
        if req is None:
            return False
        return req.is_satisfied(approved_roles)

    def missing_approvals(self, output_type: OutputType, approved_roles: set[str]) -> list[str]:
        req = self._req.get(output_type)
        if req is None:
            return []
        return req.missing_roles(approved_roles)
