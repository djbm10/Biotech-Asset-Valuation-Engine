"""Conservative extraction from source-observed public document mentions.

This extractor is intentionally narrow. It turns only identity, target, modality, and therapeutic-
area terms that were independently observed in a source document into cited facts. It does not
infer human proof of concept, deal access, ownership, clinical effect, or buyer fit from a query.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from bve.se.evidence import snapshot_cache
from bve.se.evidence.attribution import attributed_areas
from bve.se.evidence.clinicaltrials import ExtractionBundle
from bve.se.ontology.therapeutic_areas import area_terms, classify_therapeutic_areas
from bve.se.schemas.contracts import (
    CandidateHit,
    ExtractedClaim,
    NormalizedFact,
    SourceDocument,
    VerificationStatus,
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
    return snapshot_cache.load_text(path)


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


_AREA_SPAN_RADIUS = 300


def _area_span(text: str, area: str) -> str:
    """A window of ``text`` around the first occurrence of any of the area's terms."""

    folded = text.casefold()
    positions = [
        (index, len(term))
        for term in area_terms(area)
        if (index := folded.find(term)) >= 0
    ]
    start, length = min(positions)
    # Casefolding can change length (``ß`` -> ``ss``); cite the folded text then, so the
    # window still contains the term it was built around.
    source = text if len(folded) == len(text) else folded
    return source[max(0, start - _AREA_SPAN_RADIUS) : start + length + _AREA_SPAN_RADIUS]


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

        # Targets this document mentions alongside the asset. Context for review, never
        # construct attribution: a press release naming two programs mentions both their
        # targets, and co-occurrence in prose says nothing about what one molecule binds.
        observed_targets = [
            target for target in hit.target_terms if target.casefold() in searchable
        ]
        if observed_targets:
            claim = _claim(
                hit,
                document,
                predicate="document_target_context",
                value=sorted(set(observed_targets)),
                passage=passage,
            )
            claims.append(claim)
            facts.append(
                _fact(
                    hit,
                    claim,
                    "document_target_context",
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
        for modality in hit.context_modality_terms:
            claim = _claim(
                hit, document, predicate="document_modality_context", value=modality, passage=passage
            )
            claims.append(claim)
            facts.append(_fact(hit, claim, "document_modality_context", modality))

        # One fact per area, each cited to a span that names that area. The generic passage
        # is the document head, while areas are classified over the whole text, so an area
        # observed further down cannot be entailed by it; and a shared fact would let one
        # unentailed area delete another that is supported.
        #
        # evidence_attribution_v1: those document-wide areas are context. The asset's own
        # area needs a sentence that ties it to the area (R1), cited to that sentence.
        area_text = f"{passage}\n{raw_text}"
        for area in classify_therapeutic_areas(searchable):
            claim = _claim(
                hit,
                document,
                predicate="document_therapeutic_area",
                value=area,
                passage=_area_span(area_text, area),
            )
            claims.append(claim)
            facts.append(_fact(hit, claim, "document_therapeutic_area", area))
        for area, sentence in attributed_areas(raw_text or passage, hit.asset_name or ""):
            claim = _claim(hit, document, predicate="therapeutic_area", value=area, passage=sentence)
            claims.append(claim)
            facts.append(_fact(hit, claim, "therapeutic_area", area))

        return ExtractionBundle(claims=claims, facts=facts)
