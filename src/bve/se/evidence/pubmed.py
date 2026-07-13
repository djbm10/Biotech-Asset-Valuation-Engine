"""Conservative PubMed claim extraction; publication mention is evidence, not clinical proof."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from bve.se.evidence.clinicaltrials import ExtractionBundle
from bve.se.schemas.contracts import CandidateHit, ExtractedClaim, NormalizedFact, SourceDocument


class PubMedEvidenceExtractor:
    version = "pubmed_v1"

    def extract(self, hit: CandidateHit, document: SourceDocument) -> ExtractionBundle:
        if not document.snapshot_path:
            raise ValueError("PubMed extraction requires a saved source snapshot")
        record = json.loads(Path(document.snapshot_path).read_text())
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
        return ExtractionBundle(claims=[claim], facts=[fact])
