"""Blinded production-validation metrics for acquisition ranking.

This evaluator is deliberately separate from acquisition inference. It consumes a frozen truth
package and independently collected reviewer ratings; it does not tune ranking weights or expose
truth labels to the ranker.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HoldoutQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_id: str = Field(min_length=1)
    buyer_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    modality: str = Field(min_length=1)
    evidence_profile: str = Field(min_length=1)
    relevance_by_asset: dict[str, int] = Field(min_length=1)
    dispositions_by_asset: dict[str, Literal["INCLUDE", "EXCLUDE", "UNKNOWN"]]
    required_citation_assets: list[str] = Field(default_factory=list)
    diligence_assets: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_truth_partition(self) -> "HoldoutQuery":
        if set(self.relevance_by_asset) != set(self.dispositions_by_asset):
            raise ValueError("relevance and disposition asset IDs must match")
        for asset_id, relevance in self.relevance_by_asset.items():
            if not 0 <= relevance <= 3:
                raise ValueError(f"relevance for {asset_id} must be between 0 and 3")
        return self


class HoldoutPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_id: str = Field(min_length=1)
    ranked_asset_ids: list[str] = Field(default_factory=list)
    citations_by_asset: dict[str, list[str]] = Field(default_factory=dict)
    rationale_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    diligence_question_usefulness: float | None = Field(default=None, ge=0.0, le=1.0)
    serialized_output: Mapping[str, object] = Field(default_factory=dict)


class HoldoutCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_count: int = Field(ge=0)
    buyer_count: int = Field(ge=0)
    target_count: int = Field(ge=0)
    modality_count: int = Field(ge=0)
    evidence_profile_count: int = Field(ge=0)
    adequate: bool


class RankingValidationMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_k: int = Field(ge=1)
    top_k_shortlist_recall: float = Field(ge=0.0, le=1.0)
    ndcg_at_k: float = Field(ge=0.0, le=1.0)
    citation_completeness: float = Field(ge=0.0, le=1.0)
    rationale_quality: float = Field(ge=0.0, le=1.0)
    diligence_question_usefulness: float = Field(ge=0.0, le=1.0)
    zero_gate_leakage: bool
    zero_valuation_leakage: bool


class ProductionValidationThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_k: int = Field(default=5, ge=1)
    top_k_shortlist_recall_min: float = Field(default=0.80, ge=0.0, le=1.0)
    ndcg_at_k_min: float = Field(default=0.75, ge=0.0, le=1.0)
    citation_completeness_min: float = Field(default=0.95, ge=0.0, le=1.0)
    rationale_quality_min: float = Field(default=0.80, ge=0.0, le=1.0)
    diligence_question_usefulness_min: float = Field(default=0.80, ge=0.0, le=1.0)
    min_queries: int = Field(default=24, ge=1)
    min_buyers: int = Field(default=3, ge=1)
    min_targets: int = Field(default=3, ge=1)
    min_modalities: int = Field(default=3, ge=1)
    min_evidence_profiles: int = Field(default=4, ge=1)


class ProductionValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["NOT_RUN", "FAIL", "PASS"]
    coverage: HoldoutCoverage
    metrics: RankingValidationMetrics | None = None
    thresholds: ProductionValidationThresholds
    release_eligible: bool = False
    failures: list[str] = Field(default_factory=list)


_LEAKAGE_TERMS = re.compile(r"(?:^|[_\-.])(gate|gates|valuation|rnpv|npv)(?:$|[_\-.])", re.I)


def _ndcg(relevances: Sequence[int], ideal: Sequence[int], k: int) -> float:
    def dcg(values: Sequence[int]) -> float:
        return sum((2**value - 1) / math.log2(index + 2) for index, value in enumerate(values[:k]))

    ideal_score = dcg(sorted(ideal, reverse=True))
    return dcg(relevances) / ideal_score if ideal_score else 1.0


def _coverage(queries: Sequence[HoldoutQuery], thresholds: ProductionValidationThresholds) -> HoldoutCoverage:
    coverage = HoldoutCoverage(
        query_count=len(queries),
        buyer_count=len({query.buyer_id for query in queries}),
        target_count=len({query.target for query in queries}),
        modality_count=len({query.modality for query in queries}),
        evidence_profile_count=len({query.evidence_profile for query in queries}),
        adequate=False,
    )
    return coverage.model_copy(
        update={
            "adequate": (
                coverage.query_count >= thresholds.min_queries
                and coverage.buyer_count >= thresholds.min_buyers
                and coverage.target_count >= thresholds.min_targets
                and coverage.modality_count >= thresholds.min_modalities
                and coverage.evidence_profile_count >= thresholds.min_evidence_profiles
            )
        }
    )


def _leakage_fields(value: object, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if _LEAKAGE_TERMS.search(str(key)):
                found.append(path)
            found.extend(_leakage_fields(child, path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, child in enumerate(value):
            found.extend(_leakage_fields(child, f"{prefix}[{index}]"))
    return found


def evaluate_ranking_holdout(
    queries: Sequence[HoldoutQuery],
    predictions: Sequence[HoldoutPrediction],
    *,
    thresholds: ProductionValidationThresholds | None = None,
    holdout_status: Literal["BLINDED", "OPEN"] = "BLINDED",
) -> ProductionValidationReport:
    """Score a frozen ranking holdout; production eligibility requires every gate."""

    config = thresholds or ProductionValidationThresholds()
    coverage = _coverage(queries, config)
    by_id = {query.query_id: query for query in queries}
    observed = {prediction.query_id: prediction for prediction in predictions}
    failures: list[str] = []
    if len(observed) != len(predictions) or len(observed) != len(queries):
        failures.append("prediction cardinality or query identity mismatch")
    if set(observed) != set(by_id):
        failures.append("missing or extra query IDs")
    if holdout_status != "OPEN":
        failures.append("holdout labels remain blinded; scoring is not release eligible")
    if not coverage.adequate:
        failures.append("holdout coverage is below the multi-buyer production minimum")

    recalls: list[float] = []
    ndcgs: list[float] = []
    citation_numerator = citation_denominator = 0
    rationale_scores: list[float] = []
    diligence_scores: list[float] = []
    zero_gate_leakage = zero_valuation_leakage = True
    for query_id, query in by_id.items():
        prediction = observed.get(query_id)
        if prediction is None:
            continue
        relevant = {asset for asset, grade in query.relevance_by_asset.items() if grade > 0}
        top_assets = prediction.ranked_asset_ids[: config.top_k]
        recalls.append(len(relevant & set(top_assets)) / len(relevant) if relevant else 1.0)
        ndcgs.append(
            _ndcg(
                [query.relevance_by_asset.get(asset, 0) for asset in top_assets],
                list(query.relevance_by_asset.values()),
                config.top_k,
            )
        )
        for asset in query.required_citation_assets:
            citation_denominator += 1
            citation_numerator += bool(prediction.citations_by_asset.get(asset))
        if prediction.rationale_quality is not None:
            rationale_scores.append(prediction.rationale_quality)
        if prediction.diligence_question_usefulness is not None:
            diligence_scores.append(prediction.diligence_question_usefulness)
        ranked_set = set(prediction.ranked_asset_ids)
        if any(query.dispositions_by_asset.get(asset) != "INCLUDE" for asset in ranked_set):
            failures.append(f"non-INCLUDE asset ranked in {query_id}")
        leakage = _leakage_fields(prediction.serialized_output)
        zero_gate_leakage &= not any("gate" in field.casefold() for field in leakage)
        zero_valuation_leakage &= not any(
            term in field.casefold() for field in leakage for term in ("valuation", "rnpv", "npv")
        )
    metrics = RankingValidationMetrics(
        top_k=config.top_k,
        top_k_shortlist_recall=sum(recalls) / len(recalls) if recalls else 0.0,
        ndcg_at_k=sum(ndcgs) / len(ndcgs) if ndcgs else 0.0,
        citation_completeness=citation_numerator / citation_denominator if citation_denominator else 0.0,
        rationale_quality=sum(rationale_scores) / len(rationale_scores) if rationale_scores else 0.0,
        diligence_question_usefulness=(
            sum(diligence_scores) / len(diligence_scores) if diligence_scores else 0.0
        ),
        zero_gate_leakage=zero_gate_leakage,
        zero_valuation_leakage=zero_valuation_leakage,
    )
    if not metrics.zero_gate_leakage:
        failures.append("gate leakage detected")
    if not metrics.zero_valuation_leakage:
        failures.append("valuation/rNPV leakage detected")
    failures.extend(
        reason
        for passed, reason in [
            (metrics.top_k_shortlist_recall >= config.top_k_shortlist_recall_min, "top-k shortlist recall below threshold"),
            (metrics.ndcg_at_k >= config.ndcg_at_k_min, "NDCG below threshold"),
            (metrics.citation_completeness >= config.citation_completeness_min, "citation completeness below threshold"),
            (metrics.rationale_quality >= config.rationale_quality_min, "rationale quality below threshold"),
            (metrics.diligence_question_usefulness >= config.diligence_question_usefulness_min, "diligence-question usefulness below threshold"),
        ]
        if not passed
    )
    release_eligible = not failures
    return ProductionValidationReport(
        status="PASS" if release_eligible else "FAIL",
        coverage=coverage,
        metrics=metrics,
        thresholds=config,
        release_eligible=release_eligible,
        failures=list(dict.fromkeys(failures)),
    )
