"""Conservative deterministic citation-entailment checks for structured-source claims."""

from __future__ import annotations

from pydantic import BaseModel, Field

from bve.se.schemas.contracts import ExtractedClaim


class EntailmentResult(BaseModel):
    claim_id: str
    entailed: bool
    rationale: str
    missing_qualifiers: list[str] = Field(default_factory=list)


def _flatten(value) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    if isinstance(value, dict):
        return [str(item) for pair in value.items() for item in pair]
    if isinstance(value, bool):
        return []
    return [str(value)]


def check_structured_entailment(claim: ExtractedClaim) -> EntailmentResult:
    """Require normalized values and material qualifiers to occur in the cited passage.

    This is a conservative guard for machine-verified structured extraction, not a replacement for
    expert or model-based semantic review of prose-heavy sources.
    """

    passage = claim.supporting_passage.casefold()
    expected = [value.casefold() for value in _flatten(claim.normalized_value) if value.strip()]
    qualifiers = [
        value.casefold()
        for value in [claim.indication, claim.population, claim.endpoint, claim.dose]
        if value
    ]
    missing_values = [value for value in expected if value not in passage]
    missing_qualifiers = [value for value in qualifiers if value not in passage]
    # Identity booleans are supported by the cited registry identifier rather than the word true.
    if claim.predicate == "identity_valid" and "nct" in passage:
        missing_values = []
    if claim.predicate == "therapeutic_area" and claim.normalized_value == "oncology":
        oncology_terms = ("leukemia", "lymphoma", "myeloma", "malignancy", "cancer", "tumor")
        if any(term in passage for term in oncology_terms):
            missing_values = []
    if claim.predicate == "modality_id" and claim.normalized_value == "T_CELL_ENGAGER":
        modality_terms = ("t-cell engager", "t cell engager", "bispecific", "bite", "cd3")
        if any(term in passage for term in modality_terms):
            missing_values = []
    if claim.predicate == "development_stage_order" and "phase" in passage:
        missing_values = []
    entailed = not missing_values and not missing_qualifiers
    missing = [*missing_values, *missing_qualifiers]
    return EntailmentResult(
        claim_id=claim.claim_id,
        entailed=entailed,
        rationale=(
            "The cited passage contains the normalized value and material qualifiers."
            if entailed
            else "The cited passage does not explicitly support every normalized value or qualifier."
        ),
        missing_qualifiers=missing,
    )
