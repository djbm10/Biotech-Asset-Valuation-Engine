"""Compare a clinical result with an explicit buyer-defined effect bar."""

from __future__ import annotations

from bve.se.schemas.contracts import (
    ClinicalEffectBar,
    ClinicalMeaningfulness,
    ClinicalResult,
    EvidenceConfidenceTier,
    MeaningfulnessStatus,
)


def _confidence(result: ClinicalResult) -> tuple[EvidenceConfidenceTier, list[str]]:
    limitations: list[str] = []
    if result.uncontrolled:
        limitations.append("uncontrolled comparison")
    if result.selected_subgroup:
        limitations.append("selected subgroup")
    if result.endpoint_switched:
        limitations.append("endpoint switching")
    if result.incomplete_reporting:
        limitations.append("incomplete reporting")
    if result.evaluable_patients is None:
        limitations.append("evaluable-patient denominator missing")
    if result.follow_up_days is None:
        limitations.append("follow-up missing")
    count = len(limitations)
    if count == 0 and (result.evaluable_patients or 0) >= 50:
        return EvidenceConfidenceTier.HIGH, limitations
    if count <= 1 and (result.evaluable_patients or 0) >= 20:
        return EvidenceConfidenceTier.MODERATE, limitations
    if result.effect_size is not None and result.evaluable_patients is not None:
        return EvidenceConfidenceTier.LOW, limitations
    return EvidenceConfidenceTier.INSUFFICIENT, limitations


def assess_meaningfulness(
    result: ClinicalResult,
    bar: ClinicalEffectBar,
) -> ClinicalMeaningfulness:
    confidence, limitations = _confidence(result)
    minimum_effect = bar.minimum_effect
    if bar.indication is None or bar.population is None or bar.endpoint is None or minimum_effect is None:
        return ClinicalMeaningfulness(
            subject_id=result.subject_id,
            result_id=result.result_id,
            status=MeaningfulnessStatus.UNKNOWN,
            rationale="The buyer-defined clinical effect bar is incomplete.",
            limitations=[*limitations, "incomplete buyer effect bar"],
            evidence_confidence=confidence,
            supporting_claim_ids=result.supporting_claim_ids,
        )
    if (
        result.indication.casefold() != str(bar.indication).casefold()
        or result.population.casefold() != str(bar.population).casefold()
        or result.endpoint.casefold() != str(bar.endpoint).casefold()
    ):
        return ClinicalMeaningfulness(
            subject_id=result.subject_id,
            result_id=result.result_id,
            status=MeaningfulnessStatus.UNKNOWN,
            rationale="The result and buyer effect bar are not contextually comparable.",
            limitations=[*limitations, "non-comparable indication/population/endpoint"],
            evidence_confidence=confidence,
            supporting_claim_ids=result.supporting_claim_ids,
        )
    if result.effect_size is None:
        status = MeaningfulnessStatus.UNKNOWN
        rationale = "No normalized effect size is available."
    elif result.effect_size >= minimum_effect:
        status = MeaningfulnessStatus.MEETS
        rationale = "The reported effect meets or exceeds the configured buyer threshold."
    else:
        status = MeaningfulnessStatus.DOES_NOT_MEET
        rationale = "The reported effect is below the configured buyer threshold."
    if bar.durability_minimum_days and (
        result.follow_up_days is None or result.follow_up_days < bar.durability_minimum_days
    ):
        status = MeaningfulnessStatus.UNKNOWN
        limitations.append("durability threshold not established")
        rationale = "Effect size is reported, but the required durability is not established."
    if bar.safety_ceiling is not None and (
        result.safety_grade3plus_rate is None
        or result.safety_grade3plus_rate > bar.safety_ceiling
    ):
        status = (
            MeaningfulnessStatus.UNKNOWN
            if result.safety_grade3plus_rate is None
            else MeaningfulnessStatus.DOES_NOT_MEET
        )
        limitations.append("safety ceiling unresolved or exceeded")
        rationale = "The configured safety ceiling is unresolved or exceeded."
    return ClinicalMeaningfulness(
        subject_id=result.subject_id,
        result_id=result.result_id,
        status=status,
        rationale=rationale,
        limitations=limitations,
        evidence_confidence=confidence,
        supporting_claim_ids=result.supporting_claim_ids,
    )
