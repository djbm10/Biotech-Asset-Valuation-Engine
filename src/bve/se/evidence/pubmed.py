"""Conservative PubMed claim extraction; publication mention is evidence, not clinical proof."""

from __future__ import annotations

import hashlib

from bve.se.evidence import snapshot_cache
from bve.se.evidence.attribution import attributed_areas
from bve.se.evidence.clinicaltrials import ExtractionBundle
from bve.se.evidence.generic import _area_span
from bve.se.ontology.therapeutic_areas import classify_therapeutic_areas
from bve.se.schemas.contracts import CandidateHit, ExtractedClaim, NormalizedFact, SourceDocument


class PubMedEvidenceExtractor:
    version = "pubmed_v3"

    def extract(self, hit: CandidateHit, document: SourceDocument) -> ExtractionBundle:
        if not document.snapshot_path:
            raise ValueError("PubMed extraction requires a saved source snapshot")
        record = snapshot_cache.load_json(document.snapshot_path)
        passage = f"{record.get('title', '')} {record.get('abstract', '')}".strip()
        claim_id = f"claim:{hashlib.sha256(f'{hit.hit_id}|publication_relevance'.encode()).hexdigest()[:20]}"
        claim = ExtractedClaim(
            claim_id=claim_id,
            subject_id=hit.hit_id,
            predicate="publication_relevance",
            normalized_value=True,
            source_document_id=document.document_id,
            supporting_passage=passage,
            locator=f"PubMed:{record.get('pmid', '')}",
            direct_observation=True,
            extraction_method="pubmed_structured",
            extractor_version=self.version,
            extraction_confidence=0.9,
            applicable_as_of_date=hit.applicable_as_of_date,
        )
        fact = NormalizedFact(
            fact_id=f"fact:{hashlib.sha256(f'{hit.hit_id}|publication_relevance'.encode()).hexdigest()[:20]}",
            subject_id=hit.hit_id,
            fact_type="publication_relevance",
            value=True,
            supporting_claim_ids=[claim_id],
            confidence=0.9,
        )
        claims, facts = [claim], [fact]
        # evidence_attribution_v1. The abstract's areas are context (gi_area_evidence_v1 G2
        # made them asset facts, which gave every reagent in an oncology paper ONCOLOGY).
        # Only a sentence that ties this asset to an area is a fact about the asset.
        text = f"{record.get('title', '')}\n{record.get('abstract', '')}"
        emitted = [
            ("document_therapeutic_area", area, _area_span(passage, area))
            for area in classify_therapeutic_areas(passage)
        ] + [
            ("therapeutic_area", area, sentence)
            for area, sentence in attributed_areas(text, hit.asset_name or "")
        ]
        for fact_type, area, span in emitted:
            key = f"{hit.hit_id}|{fact_type}|{area}"
            area_claim = claim.model_copy(update={
                "claim_id": f"claim:{hashlib.sha256(key.encode()).hexdigest()[:20]}",
                "predicate": fact_type,
                "normalized_value": area,
                "supporting_passage": span,
            })
            claims.append(area_claim)
            facts.append(fact.model_copy(update={
                "fact_id": f"fact:{hashlib.sha256(key.encode()).hexdigest()[:20]}",
                "fact_type": fact_type,
                "value": area,
                "supporting_claim_ids": [area_claim.claim_id],
            }))
        return ExtractionBundle(claims=claims, facts=facts)
