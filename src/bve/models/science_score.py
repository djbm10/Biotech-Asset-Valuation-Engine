"""Science score — structured assessment of scientific quality and risk."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from bve.models.analog_matcher import AnalogMatchResult
    from bve.models.endpoint_validity import EndpointValidityScoreV2
    from bve.models.safety_context import SafetyContextV2, SafetySignalV2
    from bve.models.trial_design_score import TrialDesignQualityScore


class ScienceScoreComponent(BaseModel):
    """A single dimension of the science score."""

    name: str
    score: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0)
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)


class ScienceScore(BaseModel):
    """Composite science quality score for a drug asset."""

    asset_id: str
    scored_at: datetime
    components: list[ScienceScoreComponent] = Field(default_factory=list)
    composite_score: float = Field(ge=0.0, le=1.0)
    confidence_band_low: float = Field(ge=0.0, le=1.0)
    confidence_band_high: float = Field(ge=0.0, le=1.0)
    top_positives: list[str] = Field(default_factory=list)
    top_risks: list[str] = Field(default_factory=list)
    plain_english_summary: str

    @property
    def weighted_score(self) -> float:
        """Weighted average score across all components."""
        if not self.components:
            return 0.0
        total_weight = sum(c.weight for c in self.components)
        if total_weight == 0.0:
            return 0.0
        return sum(c.score * c.weight for c in self.components) / total_weight


# ---------------------------------------------------------------------------
# Step 6: Structured science diligence types
# ---------------------------------------------------------------------------


class ScienceSubScore(BaseModel):
    """One named sub-score within a ScienceDiligenceResult."""

    model_config = {"frozen": True}

    name: str
    score: float
    confidence: float
    top_positives: list[str]
    top_risks: list[str]
    rationale: str


class ScienceDiligenceResult(BaseModel):
    """Full Step 6 science diligence result — deterministic, no LLM."""

    model_config = {"frozen": True}

    asset_id: str
    overall_score: float
    confidence: float
    sub_scores: dict[str, ScienceSubScore]
    top_positives: list[str]
    top_risks: list[str]
    rationale: str
    endpoint_validity: "EndpointValidityScoreV2 | None"
    trial_design: "TrialDesignQualityScore | None"
    analog_result: "AnalogMatchResult | None"
    safety: "SafetyContextV2 | None"


def compute_science_score(
    asset_id: str,
    mechanism: str | None = None,
    indication: str | None = None,
    primary_endpoint: str | None = None,
    phase: str = "phase2",
    is_randomized: bool = True,
    is_blinded: bool = False,
    has_active_comparator: bool = False,
    enrollment: int | None = None,
    has_biomarker_enrichment: bool = False,
    safety_signals: "list[SafetySignalV2] | None" = None,
) -> ScienceDiligenceResult:
    """Compute a deterministic ScienceDiligenceResult from structured inputs."""
    # Import here to avoid circular imports at module load time
    from bve.models.analog_matcher import find_analogs
    from bve.models.endpoint_validity import score_endpoint
    from bve.models.safety_context import compute_safety_context
    from bve.models.trial_design_score import score_trial_design

    sub_scores: dict[str, ScienceSubScore] = {}

    # --- 1. Endpoint validity ---
    ep_validity: EndpointValidityScoreV2 | None = None
    if primary_endpoint:
        ep_result = score_endpoint(primary_endpoint, is_primary=True)
        ep_validity = ep_result
        ep_sub = ScienceSubScore(
            name="endpoint_validity",
            score=ep_result.validity_score,
            confidence=0.85,
            top_positives=[f"Endpoint '{primary_endpoint}' has {ep_result.regulatory_weight.value} regulatory weight"]
            if ep_result.matched_profile
            else [],
            top_risks=[]
            if ep_result.validity_score >= 0.70
            else [f"Endpoint '{primary_endpoint}' is EXPLORATORY or BRONZE — limited approval support"],
            rationale=ep_result.rationale,
        )
    else:
        ep_sub = ScienceSubScore(
            name="endpoint_validity",
            score=0.5,
            confidence=0.3,
            top_positives=[],
            top_risks=["Primary endpoint not specified"],
            rationale="No primary endpoint provided; neutral score assigned.",
        )
    sub_scores["endpoint_validity"] = ep_sub

    # --- 2. Trial design ---
    td_result = score_trial_design(
        phase=phase,
        is_randomized=is_randomized,
        is_blinded=is_blinded,
        has_active_comparator=has_active_comparator,
        enrollment=enrollment,
        primary_endpoint=primary_endpoint,
        has_biomarker_enrichment=has_biomarker_enrichment,
    )
    td_sub = ScienceSubScore(
        name="trial_design",
        score=td_result.overall_score,
        confidence=0.80,
        top_positives=[f"Strong: {s}" for s in td_result.key_strengths],
        top_risks=[f"Concern: {c}" for c in td_result.key_concerns],
        rationale=f"Trial design quality: {td_result.quality_tier} (score={td_result.overall_score:.2f}).",
    )
    sub_scores["trial_design"] = td_sub

    # --- 3. Analog matching ---
    analog_result = None
    if mechanism and indication:
        analog_result = find_analogs(mechanism=mechanism, indication=indication)
        analog_sub = ScienceSubScore(
            name="analog",
            score=analog_result.analog_score,
            confidence=0.70 if analog_result.matched_analogs else 0.20,
            top_positives=[f"Analog success rate {analog_result.success_rate:.0%}"]
            if analog_result.success_rate >= 0.6
            else [],
            top_risks=[f"Analog failure rate {analog_result.failure_rate:.0%}"]
            if analog_result.failure_rate >= 0.4
            else [],
            rationale=analog_result.summary,
        )
        sub_scores["analog"] = analog_sub

    # --- 4. Safety ---
    sig_list = safety_signals or []
    safety_ctx: SafetyContextV2 = compute_safety_context(asset_id=asset_id, signals=sig_list)
    safety_sub = ScienceSubScore(
        name="safety",
        score=safety_ctx.overall_safety_score,
        confidence=0.75 if sig_list else 0.40,
        top_positives=["Clean safety profile"] if not sig_list else [],
        top_risks=[f"Safety concern: {s.signal_type.value}" for s in sig_list if not s.manageable],
        rationale=safety_ctx.rationale,
    )
    sub_scores["safety"] = safety_sub

    # --- Weighted overall score (only include sub-scores with confidence > 0.2) ---
    weights = {
        "endpoint_validity": 0.30,
        "trial_design": 0.30,
        "analog": 0.20,
        "safety": 0.20,
    }

    total_w = 0.0
    weighted_sum = 0.0
    for name, sub in sub_scores.items():
        if sub.confidence > 0.2:
            w = weights.get(name, 0.0)
            weighted_sum += sub.score * w
            total_w += w

    overall_score = weighted_sum / total_w if total_w > 0 else 0.5
    avg_confidence = sum(s.confidence for s in sub_scores.values()) / len(sub_scores)

    # Merge top positives and risks
    all_positives: list[str] = []
    all_risks: list[str] = []
    for sub in sub_scores.values():
        all_positives.extend(sub.top_positives)
        all_risks.extend(sub.top_risks)

    # Deduplicate preserving order
    seen: set[str] = set()
    deduped_positives: list[str] = []
    for p in all_positives:
        if p not in seen:
            seen.add(p)
            deduped_positives.append(p)

    seen = set()
    deduped_risks: list[str] = []
    for r in all_risks:
        if r not in seen:
            seen.add(r)
            deduped_risks.append(r)

    rationale = (
        f"Science diligence for asset '{asset_id}': "
        f"overall_score={overall_score:.2f}, confidence={avg_confidence:.2f}. "
        f"Sub-scores: {', '.join(f'{k}={v.score:.2f}' for k, v in sub_scores.items())}."
    )

    return ScienceDiligenceResult(
        asset_id=asset_id,
        overall_score=round(overall_score, 4),
        confidence=round(avg_confidence, 4),
        sub_scores=sub_scores,
        top_positives=deduped_positives[:3],
        top_risks=deduped_risks[:3],
        rationale=rationale,
        endpoint_validity=ep_validity,
        trial_design=td_result,
        analog_result=analog_result,
        safety=safety_ctx,
    )


# Resolve forward references after all modules are importable
def _rebuild_models() -> None:
    from bve.models.analog_matcher import AnalogMatchResult  # noqa: F401
    from bve.models.endpoint_validity import EndpointValidityScoreV2  # noqa: F401
    from bve.models.safety_context import SafetyContextV2  # noqa: F401
    from bve.models.trial_design_score import TrialDesignQualityScore  # noqa: F401

    ScienceDiligenceResult.model_rebuild()


_rebuild_models()
