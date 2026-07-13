"""Append-only evidence ledger with immutable documents, claims, and normalized facts."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from bve.se.schemas.contracts import (
    ExtractedClaim,
    NormalizedFact,
    SourceDocument,
    SourceTier,
    TemporalFact,
)


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class EvidenceLedger:
    """Keep raw documents, extracted claims, and normalized facts as separate append-only layers."""

    def __init__(self, *, snapshot_root: Path | None = None) -> None:
        self.snapshot_root = snapshot_root
        self.documents: dict[str, SourceDocument] = {}
        self.claims: dict[str, ExtractedClaim] = {}
        self.facts: dict[str, NormalizedFact] = {}
        self.claim_versions: dict[tuple[str, str], list[str]] = defaultdict(list)

    def add_document(
        self,
        *,
        document_id: str,
        content: bytes,
        source_url: str,
        publisher: str,
        document_type: str,
        source_tier: SourceTier,
        publication_date: date | None = None,
        retrieval_date: datetime | None = None,
    ) -> SourceDocument:
        digest = content_hash(content)
        existing = self.documents.get(document_id)
        if existing:
            if existing.content_hash != digest:
                raise ValueError("document IDs are immutable and cannot point to changed content")
            return existing
        snapshot_path: str | None = None
        if self.snapshot_root is not None:
            self.snapshot_root.mkdir(parents=True, exist_ok=True)
            path = self.snapshot_root / f"{digest}.bin"
            if not path.exists():
                path.write_bytes(content)
            snapshot_path = str(path)
        document = SourceDocument(
            document_id=document_id,
            source_url=source_url,
            publisher=publisher,
            document_type=document_type,
            publication_date=publication_date,
            retrieval_date=retrieval_date or datetime.now(timezone.utc),
            content_hash=digest,
            snapshot_path=snapshot_path,
            source_tier=source_tier,
        )
        self.documents[document_id] = document
        return document

    def register_document(self, document: SourceDocument) -> SourceDocument:
        """Register a discovery-produced source document after verifying its saved snapshot."""

        existing = self.documents.get(document.document_id)
        if existing and existing != document:
            raise ValueError("document IDs are immutable")
        if document.snapshot_path:
            path = Path(document.snapshot_path)
            if not path.exists():
                raise FileNotFoundError(path)
            if content_hash(path.read_bytes()) != document.content_hash:
                raise ValueError("saved snapshot does not match SourceDocument.content_hash")
        self.documents[document.document_id] = document
        return document

    def add_claim(self, claim: ExtractedClaim) -> ExtractedClaim:
        if claim.source_document_id not in self.documents:
            raise KeyError(f"unknown source document {claim.source_document_id!r}")
        existing = self.claims.get(claim.claim_id)
        if existing and existing != claim:
            raise ValueError("claims are immutable; re-extraction requires a new claim_id")
        self.claims[claim.claim_id] = claim
        self.claim_versions[(claim.subject_id, claim.predicate)].append(claim.claim_id)
        return claim

    def add_fact(self, fact: NormalizedFact) -> NormalizedFact:
        missing = [claim_id for claim_id in fact.supporting_claim_ids if claim_id not in self.claims]
        if missing:
            raise KeyError(f"fact references unknown supporting claims: {missing}")
        missing_conflicts = [
            claim_id for claim_id in fact.contradicting_claim_ids if claim_id not in self.claims
        ]
        if missing_conflicts:
            raise KeyError(f"fact references unknown contradicting claims: {missing_conflicts}")
        existing = self.facts.get(fact.fact_id)
        if existing and existing != fact:
            raise ValueError("facts are immutable; renormalization requires a new fact_id")
        self.facts[fact.fact_id] = fact
        return fact

    def normalize_fact(
        self,
        *,
        fact_id: str,
        subject_id: str,
        fact_type: str,
        value: Any,
        supporting_claim_ids: list[str],
        contradicting_claim_ids: list[str] | None = None,
        confidence: float,
        analyst_confirmed: bool = False,
    ) -> NormalizedFact:
        return self.add_fact(
            NormalizedFact(
                fact_id=fact_id,
                subject_id=subject_id,
                fact_type=fact_type,
                value=value,
                supporting_claim_ids=supporting_claim_ids,
                contradicting_claim_ids=contradicting_claim_ids or [],
                confidence=confidence,
                analyst_confirmed=analyst_confirmed,
            )
        )

    def temporal_fact(
        self,
        *,
        fact_id: str,
        subject_id: str,
        fact_type: str,
        value: Any,
        supporting_claim_ids: list[str],
        contradicting_claim_ids: list[str] | None = None,
        confidence: float,
        effective_from: date,
        effective_to: date | None,
        evaluated_as_of: date,
        freshness_days: int | None,
    ) -> TemporalFact:
        stale = False
        if freshness_days is not None:
            stale = evaluated_as_of > effective_from + timedelta(days=freshness_days)
        if effective_to is not None and evaluated_as_of > effective_to:
            stale = True
        fact = TemporalFact(
            fact_id=fact_id,
            subject_id=subject_id,
            fact_type=fact_type,
            value=value,
            supporting_claim_ids=supporting_claim_ids,
            contradicting_claim_ids=contradicting_claim_ids or [],
            confidence=confidence,
            effective_from=effective_from,
            effective_to=effective_to,
            freshness_days=freshness_days,
            evaluated_as_of=evaluated_as_of,
            is_stale=stale,
        )
        self.add_fact(fact)
        return fact

    def claims_for_fact(self, fact_id: str) -> list[ExtractedClaim]:
        fact = self.facts[fact_id]
        return [
            self.claims[claim_id]
            for claim_id in [*fact.supporting_claim_ids, *fact.contradicting_claim_ids]
        ]

    def reconstruct_fact_evidence(self, fact_id: str) -> list[tuple[ExtractedClaim, SourceDocument]]:
        return [
            (claim, self.documents[claim.source_document_id])
            for claim in self.claims_for_fact(fact_id)
        ]
