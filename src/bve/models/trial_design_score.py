"""Trial design score — structured assessment of clinical trial design quality."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from bve.models.endpoint_validity import score_endpoint


class TrialDesignScoreComponent(BaseModel):
    """A single dimension of the trial design score."""

    name: str
    score: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0)
    rationale: str


class TrialDesignScore(BaseModel):
    """Composite trial design quality score for a clinical trial."""

    asset_id: str
    trial_id: Optional[str] = None
    scored_at: datetime
    components: list[TrialDesignScoreComponent] = Field(default_factory=list)
    composite_score: float = Field(ge=0.0, le=1.0)
    endpoint_score: float = Field(ge=0.0, le=1.0)
    power_score: float = Field(ge=0.0, le=1.0)
    design_score: float = Field(ge=0.0, le=1.0)
    biomarker_score: float = Field(ge=0.0, le=1.0)
    regulatory_alignment_score: float = Field(ge=0.0, le=1.0)
    plain_english_summary: str


# ---------------------------------------------------------------------------
# Step 6: Structured trial design quality scoring
# ---------------------------------------------------------------------------


class TrialDesignDimension(str, Enum):
    RANDOMIZATION = "RANDOMIZATION"
    BLINDING = "BLINDING"
    COMPARATOR = "COMPARATOR"
    SAMPLE_SIZE = "SAMPLE_SIZE"
    ENDPOINT_APPROPRIATENESS = "ENDPOINT_APPROPRIATENESS"
    POPULATION_SELECTION = "POPULATION_SELECTION"
    STATISTICAL_POWER = "STATISTICAL_POWER"
    DURATION = "DURATION"


class DesignDimensionScore(BaseModel):
    """Score for one dimension of trial design."""

    model_config = {"frozen": True}

    dimension: TrialDesignDimension
    score: float
    rationale: str
    deductions: list[str]


class TrialDesignQualityScore(BaseModel):
    """Overall trial design quality score computed by score_trial_design()."""

    model_config = {"frozen": True}

    nct_id: str | None
    phase: str
    overall_score: float
    dimension_scores: list[DesignDimensionScore]
    quality_tier: str  # "EXCELLENT" | "GOOD" | "ADEQUATE" | "WEAK"
    key_strengths: list[str]
    key_concerns: list[str]
    pos_multiplier: float


# Phase weights: dimension → weight
_PHASE_WEIGHTS: dict[str, dict[TrialDesignDimension, float]] = {
    "phase1": {
        TrialDesignDimension.RANDOMIZATION: 0.05,
        TrialDesignDimension.BLINDING: 0.05,
        TrialDesignDimension.COMPARATOR: 0.05,
        TrialDesignDimension.SAMPLE_SIZE: 0.15,
        TrialDesignDimension.ENDPOINT_APPROPRIATENESS: 0.30,
        TrialDesignDimension.POPULATION_SELECTION: 0.25,
        TrialDesignDimension.STATISTICAL_POWER: 0.10,
        TrialDesignDimension.DURATION: 0.05,
    },
    "phase2": {
        TrialDesignDimension.RANDOMIZATION: 0.15,
        TrialDesignDimension.BLINDING: 0.10,
        TrialDesignDimension.COMPARATOR: 0.15,
        TrialDesignDimension.SAMPLE_SIZE: 0.15,
        TrialDesignDimension.ENDPOINT_APPROPRIATENESS: 0.20,
        TrialDesignDimension.POPULATION_SELECTION: 0.10,
        TrialDesignDimension.STATISTICAL_POWER: 0.10,
        TrialDesignDimension.DURATION: 0.05,
    },
    "phase3": {
        TrialDesignDimension.RANDOMIZATION: 0.20,
        TrialDesignDimension.BLINDING: 0.10,
        TrialDesignDimension.COMPARATOR: 0.20,
        TrialDesignDimension.SAMPLE_SIZE: 0.15,
        TrialDesignDimension.ENDPOINT_APPROPRIATENESS: 0.15,
        TrialDesignDimension.POPULATION_SELECTION: 0.05,
        TrialDesignDimension.STATISTICAL_POWER: 0.10,
        TrialDesignDimension.DURATION: 0.05,
    },
}

_TIER_MULTIPLIER: dict[str, float] = {
    "EXCELLENT": 1.10,
    "GOOD": 1.00,
    "ADEQUATE": 0.90,
    "WEAK": 0.80,
}


def _sample_size_score(phase: str, enrollment: Optional[int]) -> tuple[float, str]:
    if enrollment is None:
        return 0.60, "Enrollment unknown; moderate score assigned."
    p = phase.lower()
    if "1" in p:
        return 0.90, f"Phase 1: enrollment={enrollment}; sample size not the key criterion."
    if "2" in p:
        if enrollment < 50:
            return 0.50, f"Phase 2: enrollment={enrollment} (<50) — underpowered."
        if enrollment < 100:
            return 0.70, f"Phase 2: enrollment={enrollment} (50-99) — modest."
        if enrollment <= 200:
            return 0.85, f"Phase 2: enrollment={enrollment} (100-200) — adequate."
        return 0.95, f"Phase 2: enrollment={enrollment} (>200) — well-powered."
    if "3" in p:
        if enrollment < 100:
            return 0.40, f"Phase 3: enrollment={enrollment} (<100) — underpowered."
        if enrollment < 300:
            return 0.60, f"Phase 3: enrollment={enrollment} (100-299) — modest."
        if enrollment <= 500:
            return 0.80, f"Phase 3: enrollment={enrollment} (300-500) — adequate."
        return 0.95, f"Phase 3: enrollment={enrollment} (>500) — well-powered."
    return 0.60, f"Phase unknown; enrollment={enrollment}."


def score_trial_design(
    phase: str,
    is_randomized: bool,
    is_blinded: bool,
    has_active_comparator: bool,
    enrollment: int | None,
    primary_endpoint: str | None,
    has_biomarker_enrichment: bool = False,
    has_adaptive_design: bool = False,
    nct_id: str | None = None,
) -> TrialDesignQualityScore:
    """Compute a deterministic TrialDesignQualityScore from trial design parameters."""

    # --- Individual dimension scores ---
    rand_score = 1.0 if is_randomized else 0.40
    rand_rationale = "Randomized design." if is_randomized else "Single-arm; lower evidential weight."
    rand_deductions = [] if is_randomized else ["Non-randomized design"]

    blind_score = 1.0 if is_blinded else 0.70
    blind_rationale = "Blinded design." if is_blinded else "Open-label; acceptable for some endpoints."
    blind_deductions = [] if is_blinded else ["Open-label design"]

    if has_active_comparator:
        comp_score = 1.0
        comp_rationale = "Active comparator provides head-to-head evidence."
        comp_deductions: list[str] = []
    elif is_randomized:
        comp_score = 0.75
        comp_rationale = "Randomized but placebo/no active comparator."
        comp_deductions = ["No active comparator"]
    else:
        comp_score = 0.40
        comp_rationale = "Single-arm, no comparator."
        comp_deductions = ["No comparator", "Single-arm"]

    ss_score, ss_rationale = _sample_size_score(phase, enrollment)
    ss_deductions = ["Small enrollment"] if ss_score < 0.60 else []

    if primary_endpoint:
        ep_result = score_endpoint(primary_endpoint, is_primary=True)
        ep_score = ep_result.validity_score
        ep_rationale = ep_result.rationale
        ep_deductions = [] if ep_score >= 0.70 else [f"Endpoint '{primary_endpoint}' has limited regulatory weight"]
    else:
        ep_score = 0.60
        ep_rationale = "Primary endpoint not specified; moderate score."
        ep_deductions = ["Endpoint not specified"]

    pop_score = 0.90 if has_biomarker_enrichment else 0.70
    pop_rationale = "Biomarker-enriched population." if has_biomarker_enrichment else "Unselected population."
    pop_deductions = [] if has_biomarker_enrichment else ["No biomarker enrichment"]

    power_score = 0.90
    power_rationale = "Statistical power assumed adequate."
    power_deductions: list[str] = []

    dur_score = 0.80
    dur_rationale = "Duration assumed adequate."
    dur_deductions: list[str] = []

    dimension_scores = [
        DesignDimensionScore(
            dimension=TrialDesignDimension.RANDOMIZATION,
            score=rand_score,
            rationale=rand_rationale,
            deductions=rand_deductions,
        ),
        DesignDimensionScore(
            dimension=TrialDesignDimension.BLINDING,
            score=blind_score,
            rationale=blind_rationale,
            deductions=blind_deductions,
        ),
        DesignDimensionScore(
            dimension=TrialDesignDimension.COMPARATOR,
            score=comp_score,
            rationale=comp_rationale,
            deductions=comp_deductions,
        ),
        DesignDimensionScore(
            dimension=TrialDesignDimension.SAMPLE_SIZE,
            score=ss_score,
            rationale=ss_rationale,
            deductions=ss_deductions,
        ),
        DesignDimensionScore(
            dimension=TrialDesignDimension.ENDPOINT_APPROPRIATENESS,
            score=ep_score,
            rationale=ep_rationale,
            deductions=ep_deductions,
        ),
        DesignDimensionScore(
            dimension=TrialDesignDimension.POPULATION_SELECTION,
            score=pop_score,
            rationale=pop_rationale,
            deductions=pop_deductions,
        ),
        DesignDimensionScore(
            dimension=TrialDesignDimension.STATISTICAL_POWER,
            score=power_score,
            rationale=power_rationale,
            deductions=power_deductions,
        ),
        DesignDimensionScore(
            dimension=TrialDesignDimension.DURATION,
            score=dur_score,
            rationale=dur_rationale,
            deductions=dur_deductions,
        ),
    ]

    # Determine weights for this phase
    phase_key = "phase2"  # default
    p = phase.lower()
    if "1" in p:
        phase_key = "phase1"
    elif "3" in p:
        phase_key = "phase3"
    weights = _PHASE_WEIGHTS[phase_key]

    dim_map = {ds.dimension: ds for ds in dimension_scores}
    overall_score = sum(dim_map[d].score * w for d, w in weights.items())

    if has_adaptive_design:
        overall_score = min(1.0, overall_score + 0.05)

    if overall_score >= 0.85:
        quality_tier = "EXCELLENT"
    elif overall_score >= 0.70:
        quality_tier = "GOOD"
    elif overall_score >= 0.55:
        quality_tier = "ADEQUATE"
    else:
        quality_tier = "WEAK"

    key_strengths = [ds.dimension.value for ds in dimension_scores if ds.score >= 0.85]
    key_concerns = [ds.dimension.value for ds in dimension_scores if ds.score < 0.60]
    pos_multiplier = _TIER_MULTIPLIER[quality_tier]

    return TrialDesignQualityScore(
        nct_id=nct_id,
        phase=phase,
        overall_score=round(overall_score, 4),
        dimension_scores=dimension_scores,
        quality_tier=quality_tier,
        key_strengths=key_strengths,
        key_concerns=key_concerns,
        pos_multiplier=pos_multiplier,
    )
