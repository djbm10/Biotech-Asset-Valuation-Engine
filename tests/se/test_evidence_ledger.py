from __future__ import annotations

from datetime import date

import pytest

from bve.se.evidence.ledger import EvidenceLedger
from bve.se.schemas.contracts import ExtractedClaim, SourceTier


def _claim(claim_id: str = "claim:1", *, value: object = ["CD19"]) -> ExtractedClaim:
    return ExtractedClaim(
        claim_id=claim_id,
        subject_id="asset:1",
        predicate="construct_target_set",
        normalized_value=value,
        source_document_id="doc:1",
        supporting_passage="Asset A is a CD19-directed T-cell engager.",
        extraction_method="fixture",
        extractor_version="1",
        extraction_confidence=0.95,
        applicable_as_of_date=date(2026, 7, 10),
    )


def _ledger(tmp_path) -> EvidenceLedger:
    ledger = EvidenceLedger(snapshot_root=tmp_path / "snapshots")
    ledger.add_document(
        document_id="doc:1",
        content=b"Asset A is a CD19-directed T-cell engager.",
        source_url="https://example.test/doc",
        publisher="Example",
        document_type="pipeline_page",
        source_tier=SourceTier.COMPANY_AUTHORED,
    )
    return ledger


def test_document_snapshot_is_content_addressed_and_immutable(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    document = ledger.documents["doc:1"]
    assert document.snapshot_path
    assert (tmp_path / "snapshots" / f"{document.content_hash}.bin").exists()
    with pytest.raises(ValueError, match="immutable"):
        ledger.add_document(
            document_id="doc:1",
            content=b"changed",
            source_url="https://example.test/doc",
            publisher="Example",
            document_type="pipeline_page",
            source_tier=SourceTier.COMPANY_AUTHORED,
        )


def test_claim_and_fact_layers_are_separate_and_reconstructable(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    ledger.add_claim(_claim())
    fact = ledger.normalize_fact(
        fact_id="fact:1",
        subject_id="asset:1",
        fact_type="construct_target_set",
        value=["CD19"],
        supporting_claim_ids=["claim:1"],
        confidence=0.9,
    )
    evidence = ledger.reconstruct_fact_evidence(fact.fact_id)
    assert evidence[0][0].claim_id == "claim:1"
    assert evidence[0][1].document_id == "doc:1"


def test_reextraction_cannot_overwrite_claim(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    ledger.add_claim(_claim())
    with pytest.raises(ValueError, match="new claim_id"):
        ledger.add_claim(_claim(value=["BCMA"]))


def test_temporal_fact_computes_staleness(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    ledger.add_claim(_claim())
    fact = ledger.temporal_fact(
        fact_id="fact:status",
        subject_id="asset:1",
        fact_type="development_status",
        value="ACTIVE",
        supporting_claim_ids=["claim:1"],
        confidence=0.8,
        effective_from=date(2025, 1, 1),
        effective_to=None,
        evaluated_as_of=date(2026, 7, 10),
        freshness_days=180,
    )
    assert fact.is_stale is True
