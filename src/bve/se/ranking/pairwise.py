"""Pairwise dominance comparison with ties and abstention."""

from __future__ import annotations

from bve.se.schemas.contracts import (
    AttractivenessTier,
    EvidenceConfidenceTier,
    PairwiseComparison,
    PairwiseOutcome,
    PairwiseProfile,
)

_TIER = {
    AttractivenessTier.UNRANKED: 0,
    AttractivenessTier.LOW: 1,
    AttractivenessTier.MODERATE: 2,
    AttractivenessTier.HIGH: 3,
}
_CONFIDENCE = {
    EvidenceConfidenceTier.INSUFFICIENT: 0,
    EvidenceConfidenceTier.LOW: 1,
    EvidenceConfidenceTier.MODERATE: 2,
    EvidenceConfidenceTier.HIGH: 3,
}
_DIMENSIONS = (
    "clinical_tier",
    "differentiation_tier",
    "durability_safety_tier",
    "development_maturity_tier",
    "operating_fit_tier",
    "buyer_advantage_tier",
    "transaction_path_tier",
    "diligence_burden_tier",
)


def compare_profiles(left: PairwiseProfile, right: PairwiseProfile) -> PairwiseComparison:
    if left.cohort_id != right.cohort_id:
        return PairwiseComparison(
            left_subject_id=left.subject_id,
            right_subject_id=right.subject_id,
            outcome=PairwiseOutcome.NOT_COMPARABLE,
            rationale="Assets belong to different clinical ranking cohorts.",
        )
    if min(_CONFIDENCE[left.evidence_confidence], _CONFIDENCE[right.evidence_confidence]) == 0:
        return PairwiseComparison(
            left_subject_id=left.subject_id,
            right_subject_id=right.subject_id,
            cohort_id=left.cohort_id,
            outcome=PairwiseOutcome.ABSTAIN,
            rationale="At least one asset has insufficient public evidence for comparison.",
        )
    left_better: list[str] = []
    right_better: list[str] = []
    for dimension in _DIMENSIONS:
        left_value = _TIER[getattr(left, dimension)]
        right_value = _TIER[getattr(right, dimension)]
        if left_value > right_value:
            left_better.append(dimension)
        elif right_value > left_value:
            right_better.append(dimension)
    if left_better and not right_better:
        outcome = PairwiseOutcome.LEFT_PREFERRED
        decisive = left_better
        rationale = "Left asset weakly dominates across all differing dimensions."
    elif right_better and not left_better:
        outcome = PairwiseOutcome.RIGHT_PREFERRED
        decisive = right_better
        rationale = "Right asset weakly dominates across all differing dimensions."
    elif not left_better and not right_better:
        outcome = PairwiseOutcome.TIE
        decisive = []
        rationale = "No structured dimension distinguishes the assets."
    else:
        outcome = PairwiseOutcome.ABSTAIN
        decisive = [*left_better, *right_better]
        rationale = "The assets trade off across dimensions; buyer preferences are required."
    return PairwiseComparison(
        left_subject_id=left.subject_id,
        right_subject_id=right.subject_id,
        cohort_id=left.cohort_id,
        outcome=outcome,
        rationale=rationale,
        decisive_dimensions=decisive,
        sensitivity_warning=(
            "A total rank would be preference-sensitive."
            if outcome == PairwiseOutcome.ABSTAIN and left_better and right_better
            else None
        ),
    )
