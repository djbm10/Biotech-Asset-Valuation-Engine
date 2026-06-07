"""Phase E approval scenario allocator."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ApprovalScenario(str, Enum):
    FULL_APPROVAL = "full_approval"
    NARROW_LABEL = "narrow_label"
    DELAYED_APPROVAL = "delayed_approval"
    CRL_MAJOR_SETBACK = "crl_major_setback"
    NON_APPROVAL = "non_approval"


class ApprovalScenarioInputs(BaseModel):
    technical_success_probability: float = Field(ge=0.0, le=1.0)
    regulatory_approval_probability: float = Field(ge=0.0, le=1.0)
    broad_label_probability: float = Field(ge=0.0, le=1.0)
    commercial_realization_probability: float = Field(ge=0.0, le=1.0)
    delay_probability: float = Field(ge=0.0, le=1.0)


class ApprovalScenarioWeight(BaseModel):
    scenario: ApprovalScenario
    probability: float = Field(ge=0.0, le=1.0)
    explanation: str


def build_approval_scenarios(inputs: ApprovalScenarioInputs) -> list[ApprovalScenarioWeight]:
    full = (
        inputs.technical_success_probability
        * inputs.regulatory_approval_probability
        * inputs.broad_label_probability
        * inputs.commercial_realization_probability
    )
    narrow = (
        inputs.technical_success_probability
        * inputs.regulatory_approval_probability
        * (1.0 - inputs.broad_label_probability)
        * max(0.4, inputs.commercial_realization_probability)
    )
    delayed = (
        inputs.technical_success_probability
        * inputs.regulatory_approval_probability
        * inputs.delay_probability
        * 0.8
    )
    crl = (
        inputs.technical_success_probability
        * (1.0 - inputs.regulatory_approval_probability)
        * 0.65
    )
    non_approval = max(0.0, 1.0 - (full + narrow + delayed + crl))

    raw = [
        (ApprovalScenario.FULL_APPROVAL, full, "Clean technical, regulatory, label, and commercial path."),
        (ApprovalScenario.NARROW_LABEL, narrow, "Approval is plausible, but label breadth looks constrained."),
        (ApprovalScenario.DELAYED_APPROVAL, delayed, "Program is approvable but timing risk remains material."),
        (ApprovalScenario.CRL_MAJOR_SETBACK, crl, "Regulatory failure or major setback remains plausible."),
        (ApprovalScenario.NON_APPROVAL, non_approval, "Stack implies outright failure remains possible."),
    ]
    total = sum(prob for _, prob, _ in raw) or 1.0
    return [
        ApprovalScenarioWeight(
            scenario=scenario,
            probability=round(max(0.0, min(1.0, prob / total)), 4),
            explanation=explanation,
        )
        for scenario, prob, explanation in raw
    ]
