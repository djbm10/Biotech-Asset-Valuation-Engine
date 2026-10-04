"""Positively established target entities that can make a target query incompatible.

``target_compatibility_v1.md``. This never says an asset "does not bind X". It records the
target entity an authority positively identifies -- a complex or family as one entity, or a
non-gene antigen -- so the gate can say the product is *incompatible* with a query whose
targets are none of that entity's members. Members are carried for that membership test
only and are never emitted as target ids.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone

from bve.se.evidence.construct_targets import ConstructTargetEvidence
from bve.se.schemas.contracts import (
    ExtractedClaim,
    NormalizedFact,
    SourceDocument,
    SourceTier,
    VerificationStatus,
)

FACT_TYPE = "target_compatibility_evidence"
EXTRACTOR_VERSION = "target_compatibility_v1"
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

#: NCIt antigen classes whose antigen is not one human gene (ncit_target_sidecar_v1 §3.2).
NONGENE_CLASSES = ("C201172", "C201491")


def _id(prefix: str, *parts: str) -> str:
    return f"{prefix}:{hashlib.sha256('|'.join(parts).encode()).hexdigest()[:20]}"


def complex_entities(edges) -> list[dict] | None:
    """E1: complex/family entities, or ``None`` when E1 does not apply."""

    from bve.se.ontology.mechanisms import EdgeStatus, TargetRelationship

    usable = [edge for edge in edges if edge.status is EdgeStatus.USABLE]
    if not usable or any(
        edge.relationship_type is not TargetRelationship.FAMILY_OR_COMPLEX_ASSOCIATION
        for edge in usable
    ):
        return None
    grouped: dict[tuple[str, str], dict] = {}
    for edge in usable:
        key = (edge.source, edge.source_record_id)
        entry = grouped.setdefault(
            key,
            {
                "entity": f"COMPLEX:{edge.source}:{edge.source_record_id}",
                "source": edge.source,
                "source_release": edge.source_release,
                "members": set(),
            },
        )
        if edge.canonical_target_id:
            entry["members"].add(edge.canonical_target_id)
    return [
        {**entry, "members": sorted(entry["members"])}
        for _, entry in sorted(grouped.items())
    ]


def nongene_entities(classes: list[str]) -> list[dict] | None:
    """E2: non-gene antigen entities when the product sits only in non-gene classes."""

    if not classes or any(code not in NONGENE_CLASSES for code in classes):
        return None
    return [
        {"entity": f"NONGENE:{code}", "source": "ncit", "source_release": "26.08e", "members": []}
        for code in sorted(classes)
    ]


def compatibility_evidence(
    asset_id: str, entities: list[dict], *, basis: str, as_of_date: date
) -> ConstructTargetEvidence:
    payload = json.dumps(entities, sort_keys=True)
    document = SourceDocument(
        document_id=_id("doc", "compat", basis),
        source_url=f"urn:target-compatibility:{basis}",
        publisher=basis,
        document_type="ontology_snapshot",
        retrieval_date=_EPOCH,
        content_hash=_id("hash", basis),
        source_tier=SourceTier.REGISTRY,
        public_only=True,
    )
    value = [entity["entity"] for entity in entities]
    claim = ExtractedClaim(
        claim_id=_id("claim", asset_id, FACT_TYPE, payload),
        subject_id=asset_id,
        predicate=FACT_TYPE,
        normalized_value=value,
        source_document_id=document.document_id,
        supporting_passage=payload,
        locator=f"{basis}#established_entities",
        direct_observation=True,
        extraction_method=f"target_compatibility_{basis}",
        extractor_version=EXTRACTOR_VERSION,
        extraction_confidence=0.95,
        verification_status=VerificationStatus.MACHINE_VERIFIED,
        applicable_as_of_date=as_of_date,
    )
    fact = NormalizedFact(
        fact_id=_id("fact", asset_id, FACT_TYPE, payload),
        subject_id=asset_id,
        fact_type=FACT_TYPE,
        value=entities,
        supporting_claim_ids=[claim.claim_id],
        confidence=0.95,
    )
    return ConstructTargetEvidence(documents=[document], claims=[claim], fact=fact)
