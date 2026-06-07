"""Phase E label-breadth model."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class LabelBreadthInputs(BaseModel):
    design_score: float = Field(ge=0.0, le=1.0)
    biomarker_logic_score: float = Field(ge=0.0, le=1.0)
    safety_score: float = Field(ge=0.0, le=1.0)
    regulatory_approval_probability: float = Field(ge=0.0, le=1.0)
    endpoint_strength_score: float = Field(ge=0.0, le=1.0)


class LabelBreadthResult(BaseModel):
    broad_label_probability: float = Field(ge=0.0, le=1.0)
    narrow_label_probability: float = Field(ge=0.0, le=1.0)
    rationale: str


def infer_label_breadth(inputs: LabelBreadthInputs) -> LabelBreadthResult:
    broad = (
        (inputs.design_score * 0.30)
        + (inputs.biomarker_logic_score * 0.20)
        + (inputs.safety_score * 0.15)
        + (inputs.regulatory_approval_probability * 0.20)
        + (inputs.endpoint_strength_score * 0.15)
    )
    broad = round(max(0.0, min(1.0, broad)), 4)
    narrow = round(max(0.0, min(1.0, 1.0 - broad)), 4)
    rationale = (
        "Broad-label probability rises with stronger design, cleaner safety, clearer biomarker logic, "
        "and better regulatory posture."
    )
    return LabelBreadthResult(
        broad_label_probability=broad,
        narrow_label_probability=narrow,
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# Step 7: LabelScope + LabelBreadthEstimate — new types, do not replace above
# ---------------------------------------------------------------------------


class LabelScope(str, Enum):
    """Scope of the approved drug label."""

    BROAD = "broad"
    STANDARD = "standard"
    RESTRICTED = "restricted"
    NARROW = "narrow"


_BREADTH_SCORE: dict[LabelScope, float] = {
    LabelScope.BROAD: 0.9,
    LabelScope.STANDARD: 0.7,
    LabelScope.RESTRICTED: 0.5,
    LabelScope.NARROW: 0.3,
}

_COMMERCIAL_MULTIPLIER: dict[LabelScope, float] = {
    LabelScope.BROAD: 1.3,
    LabelScope.STANDARD: 1.0,
    LabelScope.RESTRICTED: 0.7,
    LabelScope.NARROW: 0.4,
}


class LabelBreadthEstimate(BaseModel):
    """Step 7 label breadth estimate — frozen."""

    model_config = {"frozen": True}

    asset_id: str
    phase: str
    scope: LabelScope
    breadth_score: float
    p_broad_label: float
    p_restricted_label: float
    commercial_multiplier: float
    key_factors: list[str]
    rationale: str


def estimate_label_breadth(
    asset_id: str,
    phase: str,
    has_biomarker_selection: bool = False,
    is_rare_disease: bool = False,
    n_indications_in_pipeline: int = 1,
    has_companion_diagnostic: bool = False,
    indication_breadth: str = "single",
) -> LabelBreadthEstimate:
    """Estimate label breadth from pipeline and design characteristics."""
    scope = LabelScope.STANDARD
    p_broad = 0.30
    p_restricted = 0.35
    key_factors: list[str] = []

    if has_biomarker_selection:
        scope = LabelScope.RESTRICTED
        p_restricted += 0.20
        p_broad -= 0.15
        key_factors.append("biomarker_selection restricts label")

    if is_rare_disease:
        if n_indications_in_pipeline < 3:
            scope = LabelScope.NARROW
        p_restricted += 0.10
        key_factors.append("rare_disease narrows label")

    if n_indications_in_pipeline >= 3:
        scope = LabelScope.BROAD
        p_broad += 0.25
        key_factors.append(f"n_indications={n_indications_in_pipeline} broadens label")

    if indication_breadth == "multiple":
        p_broad += 0.15
        key_factors.append("multiple indications increases p_broad")
    elif indication_breadth == "platform":
        scope = LabelScope.BROAD
        p_broad += 0.30
        key_factors.append("platform indication supports broad label")

    if has_companion_diagnostic:
        p_restricted += 0.15
        key_factors.append("companion_diagnostic signals label restriction")

    p_broad = max(0.0, min(1.0, p_broad))
    p_restricted = max(0.0, min(1.0, p_restricted))

    if not key_factors:
        key_factors.append("standard single-indication profile")

    breadth_score = _BREADTH_SCORE[scope]
    commercial_multiplier = _COMMERCIAL_MULTIPLIER[scope]

    rationale = (
        f"Label scope estimated as {scope.value} for {asset_id} at {phase}. "
        f"p_broad={p_broad:.2f}, p_restricted={p_restricted:.2f}. "
        f"Factors: {'; '.join(key_factors)}."
    )

    return LabelBreadthEstimate(
        asset_id=asset_id,
        phase=phase,
        scope=scope,
        breadth_score=breadth_score,
        p_broad_label=p_broad,
        p_restricted_label=p_restricted,
        commercial_multiplier=commercial_multiplier,
        key_factors=key_factors,
        rationale=rationale,
    )
