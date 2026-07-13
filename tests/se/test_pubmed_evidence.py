from __future__ import annotations

import json
from datetime import date, datetime, timezone

from bve.se.evidence.pubmed import PubMedEvidenceExtractor
from bve.se.schemas.contracts import CandidateHit, SourceDocument, SourceTier


def test_pubmed_extractor_only_asserts_publication_relevance(tmp_path) -> None:
    path = tmp_path / "pubmed.json"
    path.write_text(json.dumps({"pmid": "1", "title": "CLN-978 CD19 study", "abstract": "A study."}))
    document = SourceDocument(
        document_id="doc:1",
        source_url="https://pubmed.ncbi.nlm.nih.gov/1/",
        publisher="PubMed",
        document_type="publication_abstract",
        retrieval_date=datetime.now(timezone.utc),
        content_hash=__import__("hashlib").sha256(path.read_bytes()).hexdigest(),
        snapshot_path=str(path),
        source_tier=SourceTier.PRIMARY,
    )
    hit = CandidateHit(
        hit_id="hit:1",
        source="pubmed",
        source_document_id="doc:1",
        query="CD19",
        asset_name="CLN-978",
        provisional_identity_key="pubmed:1",
        retrieved_at=datetime.now(timezone.utc),
        applicable_as_of_date=date(2026, 7, 10),
    )
    bundle = PubMedEvidenceExtractor().extract(hit, document)
    assert bundle.facts[0].fact_type == "publication_relevance"
    assert bundle.facts[0].value is True
    assert "effect_size" not in {fact.fact_type for fact in bundle.facts}
