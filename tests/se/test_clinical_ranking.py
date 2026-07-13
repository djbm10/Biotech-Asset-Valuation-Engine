from __future__ import annotations

from bve.se.clinical.cohorts import assign_cohort
from bve.se.clinical.meaningfulness import assess_meaningfulness
from bve.se.ranking.pairwise import compare_profiles
from bve.se.schemas.contracts import (
    AttractivenessTier,
    ClinicalEffectBar,
    ClinicalResult,
    CohortStatus,
    EvidenceConfidenceTier,
    MeaningfulnessStatus,
    PairwiseOutcome,
    PairwiseProfile,
)


def _result(subject_id: str = "asset:1", **overrides) -> ClinicalResult:
    values = dict(
        result_id=f"result:{subject_id}",
        subject_id=subject_id,
        indication="multiple myeloma",
        population="triple-class exposed",
        treatment_line="fourth line or later",
        development_stage="PHASE_2",
        endpoint="overall response rate",
        endpoint_family="response",
        effect_size=0.65,
        effect_unit="proportion",
        evaluable_patients=100,
        follow_up_days=365,
        comparator="single-arm historical context",
        uncontrolled=False,
        supporting_claim_ids=[f"claim:{subject_id}"],
    )
    values.update(overrides)
    return ClinicalResult(**values)


def _profile(subject_id: str, cohort_id: str = "cohort:1", **overrides) -> PairwiseProfile:
    values = dict(
        subject_id=subject_id,
        cohort_id=cohort_id,
        clinical_tier=AttractivenessTier.MODERATE,
        differentiation_tier=AttractivenessTier.MODERATE,
        durability_safety_tier=AttractivenessTier.MODERATE,
        development_maturity_tier=AttractivenessTier.MODERATE,
        operating_fit_tier=AttractivenessTier.MODERATE,
        buyer_advantage_tier=AttractivenessTier.MODERATE,
        transaction_path_tier=AttractivenessTier.MODERATE,
        diligence_burden_tier=AttractivenessTier.MODERATE,
        evidence_confidence=EvidenceConfidenceTier.MODERATE,
    )
    values.update(overrides)
    return PairwiseProfile(**values)


def test_cohort_assignment_separates_stage_and_indication_context() -> None:
    phase2 = assign_cohort(_result())
    phase1 = assign_cohort(_result(subject_id="asset:2", development_stage="PHASE_1"))
    lymphoma = assign_cohort(_result(subject_id="asset:3", indication="DLBCL"))
    assert phase2.status == CohortStatus.COMPARABLE
    assert phase2.cohort_id != phase1.cohort_id
    assert phase2.cohort_id != lymphoma.cohort_id


def test_missing_cohort_context_abstains() -> None:
    assignment = assign_cohort(_result(population=""))
    assert assignment.status == CohortStatus.COHORT_UNRESOLVED
    assert assignment.cohort_id is None


def test_meaningfulness_requires_matching_buyer_context() -> None:
    bar = ClinicalEffectBar(
        indication="multiple myeloma",
        population="triple-class exposed",
        endpoint="overall response rate",
        minimum_effect=0.6,
        effect_unit="proportion",
        durability_minimum_days=180,
    )
    meets = assess_meaningfulness(_result(), bar)
    mismatch = assess_meaningfulness(_result(indication="DLBCL"), bar)
    assert meets.status == MeaningfulnessStatus.MEETS
    assert mismatch.status == MeaningfulnessStatus.UNKNOWN


def test_statistical_result_without_durability_cannot_meet_bar() -> None:
    bar = ClinicalEffectBar(
        indication="multiple myeloma",
        population="triple-class exposed",
        endpoint="overall response rate",
        minimum_effect=0.6,
        durability_minimum_days=180,
    )
    assessment = assess_meaningfulness(_result(follow_up_days=30), bar)
    assert assessment.status == MeaningfulnessStatus.UNKNOWN


def test_pairwise_comparison_refuses_cross_cohort_rank() -> None:
    comparison = compare_profiles(_profile("left"), _profile("right", cohort_id="cohort:2"))
    assert comparison.outcome == PairwiseOutcome.NOT_COMPARABLE


def test_pairwise_dominance_is_rankable_without_fixed_weights() -> None:
    left = _profile("left", clinical_tier=AttractivenessTier.HIGH)
    right = _profile("right")
    comparison = compare_profiles(left, right)
    assert comparison.outcome == PairwiseOutcome.LEFT_PREFERRED
    assert comparison.decisive_dimensions == ["clinical_tier"]


def test_tradeoffs_abstain_instead_of_emitting_pseudo_precision() -> None:
    left = _profile("left", clinical_tier=AttractivenessTier.HIGH)
    right = _profile("right", differentiation_tier=AttractivenessTier.HIGH)
    comparison = compare_profiles(left, right)
    assert comparison.outcome == PairwiseOutcome.ABSTAIN
    assert comparison.sensitivity_warning


def test_insufficient_evidence_abstains() -> None:
    left = _profile("left", evidence_confidence=EvidenceConfidenceTier.INSUFFICIENT)
    comparison = compare_profiles(left, _profile("right"))
    assert comparison.outcome == PairwiseOutcome.ABSTAIN
