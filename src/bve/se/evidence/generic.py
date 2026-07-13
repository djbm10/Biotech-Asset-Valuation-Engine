"""Conservative extraction from source-observed public document mentions.

This extractor is intentionally narrow. It turns only identity, target, modality, and therapeutic-
area terms that were independently observed in a source document into cited facts. It does not
infer human proof of concept, deal access, ownership, clinical effect, or buyer fit from a query.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from bve.se.evidence.clinicaltrials import ExtractionBundle
from bve.se.schemas.contracts import (
    CandidateHit,
    ExtractedClaim,
    NormalizedFact,
    SourceDocument,
    VerificationStatus,
)

_ONCOLOGY_TERMS = (
    "cancer",
    "leukemia",
    "lymphoma",
    "malignancy",
    "myeloma",
    "oncology",
    "tumor",
)


def _id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:20]
    return f"{prefix}:{digest}"


def _snapshot_text(document: SourceDocument) -> str:
    if not document.snapshot_path:
        return ""
    path = Path(document.snapshot_path)
    if not path.exists():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8", errors="replace")


def _claim(
    hit: CandidateHit,
    document: SourceDocument,
    *,
    predicate: str,
    value: object,
    passage: str,
) -> ExtractedClaim:
    return ExtractedClaim(
        claim_id=_id("claim", hit.hit_id, predicate, repr(value)),
        subject_id=hit.hit_id,
        predicate=predicate,
        normalized_value=value,
        source_document_id=document.document_id,
        supporting_passage=passage,
        locator="source-observed public document passage",
        direct_observation=True,
        extraction_method="public_document_observed",
        extractor_version="public_document_v1",
        extraction_confidence=0.80,
        verification_status=VerificationStatus.MACHINE_VERIFIED,
        applicable_as_of_date=hit.applicable_as_of_date,
    )


def _fact(hit: CandidateHit, claim: ExtractedClaim, fact_type: str, value: object) -> NormalizedFact:
    return NormalizedFact(
        fact_id=_id("fact", hit.hit_id, fact_type, repr(value)),
        subject_id=hit.hit_id,
        fact_type=fact_type,
        value=value,
        supporting_claim_ids=[claim.claim_id],
        confidence=claim.extraction_confidence,
    )


class PublicDocumentEvidenceExtractor:
    """Extract only values already observed by the discovery adapter in source text."""

    version = "public_document_v1"

    def extract(self, hit: CandidateHit, document: SourceDocument) -> ExtractionBundle:
        raw_text = _snapshot_text(document)
        passage = (hit.snippet or raw_text)[:2_000]
        searchable = f"{passage}\n{raw_text}".casefold()
        claims: list[ExtractedClaim] = []
        facts: list[NormalizedFact] = []

        if hit.asset_name and hit.asset_name.casefold() in searchable:
            claim = _claim(
                hit,
                document,
                predicate="identity_valid",
                value=True,
                passage=passage,
            )
            claims.append(claim)
            facts.append(_fact(hit, claim, "identity_valid", True))

        observed_targets = [
            target for target in hit.target_terms if target.casefold() in searchable
        ]
        if observed_targets:
            claim = _claim(
                hit,
                document,
                predicate="construct_target_set",
                value=sorted(set(observed_targets)),
                passage=passage,
            )
            claims.append(claim)
            facts.append(
                _fact(
                    hit,
                    claim,
                    "construct_target_set",
                    sorted(set(observed_targets)),
                )
            )

        if len(hit.modality_terms) == 1:
            modality = hit.modality_terms[0]
            claim = _claim(
                hit,
                document,
                predicate="modality_id",
                value=modality,
                passage=passage,
            )
            claims.append(claim)
            facts.append(_fact(hit, claim, "modality_id", modality))

        if any(term in searchable for term in _ONCOLOGY_TERMS):
            claim = _claim(
                hit,
                document,
                predicate="therapeutic_area",
                value="oncology",
                passage=passage,
            )
            claims.append(claim)
            facts.append(_fact(hit, claim, "therapeutic_area", "oncology"))

        return ExtractionBundle(claims=claims, facts=facts)
