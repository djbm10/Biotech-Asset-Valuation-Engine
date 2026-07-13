"""Explicit retrieval, classification, resolution, citation, and ranking metrics."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from pydantic import BaseModel, Field


class ClassificationMetrics(BaseModel):
    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)


class ResolutionMetrics(BaseModel):
    correct_merges: int = Field(ge=0)
    incorrect_merges: int = Field(ge=0)
    missed_merges: int = Field(ge=0)
    merge_precision: float = Field(ge=0.0, le=1.0)
    merge_recall: float = Field(ge=0.0, le=1.0)
    irreversible_merges: int = Field(ge=0)


class EvidenceMetrics(BaseModel):
    material_claims: int = Field(ge=0)
    claims_with_citations: int = Field(ge=0)
    entailed_citations: int = Field(ge=0)
    unsupported_claims: int = Field(ge=0)
    citation_coverage: float = Field(ge=0.0, le=1.0)
    citation_entailment: float = Field(ge=0.0, le=1.0)
    unsupported_claim_rate: float = Field(ge=0.0, le=1.0)


def _ratio(numerator: int, denominator: int, *, empty: float = 1.0) -> float:
    return numerator / denominator if denominator else empty


def evaluate_classification(expected: Iterable[str], observed: Iterable[str]) -> ClassificationMetrics:
    expected_set = set(expected)
    observed_set = set(observed)
    tp = len(expected_set & observed_set)
    fp = len(observed_set - expected_set)
    fn = len(expected_set - observed_set)
    return ClassificationMetrics(
        true_positive=tp,
        false_positive=fp,
        false_negative=fn,
        precision=_ratio(tp, tp + fp),
        recall=_ratio(tp, tp + fn),
    )


def evaluate_resolution(
    expected_pairs: Iterable[frozenset[str]],
    observed_pairs: Iterable[frozenset[str]],
    *,
    irreversible_merges: int,
) -> ResolutionMetrics:
    expected = set(expected_pairs)
    observed = set(observed_pairs)
    correct = len(expected & observed)
    incorrect = len(observed - expected)
    missed = len(expected - observed)
    return ResolutionMetrics(
        correct_merges=correct,
        incorrect_merges=incorrect,
        missed_merges=missed,
        merge_precision=_ratio(correct, correct + incorrect),
        merge_recall=_ratio(correct, correct + missed),
        irreversible_merges=irreversible_merges,
    )


def evaluate_evidence(
    material_claim_ids: Iterable[str],
    citations_by_claim: Mapping[str, list[str]],
    entailment_by_claim: Mapping[str, bool],
) -> EvidenceMetrics:
    claims = set(material_claim_ids)
    cited = {claim_id for claim_id in claims if citations_by_claim.get(claim_id)}
    entailed = {claim_id for claim_id in claims if entailment_by_claim.get(claim_id) is True}
    unsupported = claims - entailed
    return EvidenceMetrics(
        material_claims=len(claims),
        claims_with_citations=len(cited),
        entailed_citations=len(entailed),
        unsupported_claims=len(unsupported),
        citation_coverage=_ratio(len(cited), len(claims)),
        citation_entailment=_ratio(len(entailed), len(claims)),
        unsupported_claim_rate=_ratio(len(unsupported), len(claims), empty=0.0),
    )
