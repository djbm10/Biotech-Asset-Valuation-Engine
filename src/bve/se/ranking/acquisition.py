"""Disposition-safe acquisition ranking, independent of valuation.

This module ranks only authoritative ``INCLUDE`` candidates.  ``UNKNOWN`` candidates
are returned as diligence work items and ``EXCLUDE`` candidates are never ranked.
All conclusions are explicitly public pre-diligence conclusions; no rNPV or valuation
field is accepted at this boundary.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Disposition = Literal["INCLUDE", "EXCLUDE", "UNKNOWN"]


class AcquisitionCandidate(BaseModel):
    """Evidence-backed ranking inputs, deliberately excluding valuation fields."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1)
    disposition: Disposition
    human_proof_of_concept: float = Field(ge=0.0, le=1.0)
    clinical_meaningfulness: float = Field(ge=0.0, le=1.0)
    evidence_quality: float = Field(ge=0.0, le=1.0)
    buyer_development_fit: float = Field(ge=0.0, le=1.0)
    differentiation: float = Field(ge=0.0, le=1.0)
    deal_feasibility: float = Field(ge=0.0, le=1.0)
    best_owner_rationale: str = Field(min_length=1)
    supporting_claim_ids: list[str] = Field(default_factory=list)
    public_only: bool = True


class DiligenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    route: Literal["DILIGENCE"] = "DILIGENCE"
    missing_or_conflicting_gate: str = Field(min_length=1)
    supporting_evidence: list[str] = Field(min_length=1)
    specific_diligence_question: str = Field(min_length=1)
    rationale: str
    required_checks: list[str] = Field(min_length=1)
    public_pre_diligence: bool = True


class RankedAcquisition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    rank: int = Field(ge=1)
    score: float = Field(ge=0.0, le=1.0)
    human_proof_of_concept: float
    clinical_meaningfulness: float
    evidence_quality: float
    buyer_development_fit: float
    differentiation: float
    deal_feasibility: float
    best_owner_rationale: str
    rationale: str
    public_pre_diligence: bool = True
    supporting_claim_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_public_cap(self) -> "RankedAcquisition":
        if not self.public_pre_diligence:
            raise ValueError("acquisition conclusions must remain public pre-diligence")
        return self


class AcquisitionRankingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ranked: list[RankedAcquisition] = Field(default_factory=list)
    diligence_queue: list[DiligenceItem] = Field(default_factory=list)
    excluded_asset_ids: list[str] = Field(default_factory=list)
    public_pre_diligence: bool = True

    @model_validator(mode="after")
    def enforce_disposition_partition(self) -> "AcquisitionRankingResult":
        ranked_ids = {item.asset_id for item in self.ranked}
        diligence_id_list = [item.asset_id for item in self.diligence_queue]
        diligence_ids = set(diligence_id_list)
        excluded_ids = set(self.excluded_asset_ids)
        if len(diligence_id_list) != len(diligence_ids):
            raise ValueError("an UNKNOWN asset must appear exactly once in diligence_queue")
        if ranked_ids & (diligence_ids | excluded_ids):
            raise ValueError("an asset cannot be both ranked and routed elsewhere")
        if diligence_ids & excluded_ids:
            raise ValueError("an asset cannot be both diligence-routed and excluded")
        return self

    @property
    def diligence(self) -> list[DiligenceItem]:
        """Backward-compatible access; serialized output uses ``diligence_queue``."""

        return self.diligence_queue


_DIMENSIONS = (
    "human_proof_of_concept",
    "clinical_meaningfulness",
    "evidence_quality",
    "buyer_development_fit",
    "differentiation",
    "deal_feasibility",
)


def _score(candidate: AcquisitionCandidate) -> float:
    """Equal-weight evidence score; valuation is intentionally not a dimension."""

    return sum(getattr(candidate, dimension) for dimension in _DIMENSIONS) / len(_DIMENSIONS)


def _diligence_item(candidate: AcquisitionCandidate) -> DiligenceItem:
    dimensions = {dimension: getattr(candidate, dimension) for dimension in _DIMENSIONS}
    missing_gate = min(dimensions, key=dimensions.__getitem__)
    evidence = list(dict.fromkeys(candidate.supporting_claim_ids))
    if not evidence:
        raise ValueError(f"UNKNOWN asset {candidate.asset_id} requires supporting evidence")
    return DiligenceItem(
        asset_id=candidate.asset_id,
        missing_or_conflicting_gate=missing_gate,
        supporting_evidence=evidence,
        specific_diligence_question=(
            f"What evidence would resolve the {missing_gate.replace('_', ' ')} gate for "
            f"{candidate.asset_id}, and does it support INCLUDE or EXCLUDE?"
        ),
        rationale=(
            "UNKNOWN disposition is not rankable; resolve the missing or conflicting evidence "
            "before acquisition comparison."
        ),
        required_checks=[
            "confirm target, modality, and human proof-of-concept linkage",
            "reconcile evidence quality and clinical meaningfulness",
            "confirm buyer-development fit, ownership, and deal feasibility",
        ],
    )


def rank_acquisition_candidates(
    candidates: Iterable[AcquisitionCandidate],
) -> AcquisitionRankingResult:
    """Rank INCLUDE candidates and route every non-INCLUDE disposition safely."""

    materialized = list(candidates)
    ids = [candidate.asset_id for candidate in materialized]
    if len(ids) != len(set(ids)):
        raise ValueError("asset_id values must be unique")

    includes = [candidate for candidate in materialized if candidate.disposition == "INCLUDE"]
    unknowns = [candidate for candidate in materialized if candidate.disposition == "UNKNOWN"]
    excludes = sorted(candidate.asset_id for candidate in materialized if candidate.disposition == "EXCLUDE")
    ordered = sorted(includes, key=lambda candidate: (-_score(candidate), candidate.asset_id))
    ranked = [
        RankedAcquisition(
            asset_id=candidate.asset_id,
            rank=rank,
            score=round(_score(candidate), 6),
            **{dimension: getattr(candidate, dimension) for dimension in _DIMENSIONS},
            best_owner_rationale=candidate.best_owner_rationale,
            rationale=(
                "INCLUDE-only acquisition ranking across human proof-of-concept, clinical "
                "meaningfulness, evidence quality, buyer-development fit, differentiation, "
                "and deal feasibility. Public evidence remains pre-diligence."
            ),
            supporting_claim_ids=candidate.supporting_claim_ids,
        )
        for rank, candidate in enumerate(ordered, start=1)
    ]
    result = AcquisitionRankingResult(
        ranked=ranked,
        diligence_queue=[_diligence_item(candidate) for candidate in unknowns],
        excluded_asset_ids=excludes,
    )
    unknown_ids = [candidate.asset_id for candidate in unknowns]
    queued_ids = [item.asset_id for item in result.diligence_queue]
    if sorted(unknown_ids) != sorted(queued_ids):
        raise ValueError("every UNKNOWN asset must appear exactly once in diligence_queue")
    if set(unknown_ids) & {item.asset_id for item in result.ranked}:
        raise ValueError("UNKNOWN assets must never be ranked")
    return result
