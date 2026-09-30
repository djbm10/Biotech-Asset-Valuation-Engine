"""Fill a missing construct target set from CT.gov records fetched by the asset's own name.

``registry_target_lookup_v1.md``. The sealed corpus often holds nothing but abstracts for a
clinical-stage cell therapy, and no drug->target authority has a mechanism row for it -- yet
the sponsor has registered it, and the registry intervention says what it is: "ALLO-715:
BCMA-directed allogeneic CAR T". This route asks the registry for that record directly.

It adds a *retrieval*, never a reader. Every admitted intervention goes through
:func:`intervention_construct_targets` exactly as the intervention route uses it, because the
reader is the part that has already been shown to be precise; the free-text route failed on
reading, not on finding.

Everything fetched is pinned. A live run writes each query's answer into a lookup custody,
and a replay reads that custody and nothing else, so a measured result can be reproduced
without the registry having changed underneath it.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from bve.se.evidence.construct_targets import (
    ConstructTargetEvidence,
    intervention_construct_targets,
)
from bve.se.schemas.contracts import (
    ExtractedClaim,
    NormalizedFact,
    SourceDocument,
    SourceTier,
    VerificationStatus,
)

EXTRACTION_METHOD = "REGISTRY_TARGET_LOOKUP"
EXTRACTOR_VERSION = "registry_target_lookup_v1"

#: L7. Taken in ascending NCT-id order, so the same registry answers the same way however
#: the API happens to rank it.
MAX_STUDIES_PER_QUERY = 25

#: Below the authority's 0.95: a sponsor describing its own product is good evidence, and a
#: curated drug->target edge is better.
_CONFIDENCE = 0.8

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class LookupCustodyError(RuntimeError):
    """A replay asked for something the live run did not record, or the record changed."""


class LookupSource(Protocol):
    def studies(self, query: str) -> list[dict] | None:
        """The pinned studies for one query name, or ``None`` when the query failed."""


def _key(query: str) -> str:
    return hashlib.sha256(query.encode()).hexdigest()[:24]


def _digest(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _nct(study: dict) -> str:
    return str((study.get("identificationModule") or {}).get("nctId") or "")


class LiveLookup:
    """Query the registry and seal every answer, including failures, into ``custody``."""

    def __init__(
        self,
        custody: Path,
        *,
        search: Callable[[str], list[dict]],
        fetched_at: str | None = None,
    ) -> None:
        self.custody = Path(custody)
        self._search = search
        self._fetched_at = fetched_at
        (self.custody / "queries").mkdir(parents=True, exist_ok=True)
        self._memo: dict[str, list[dict] | None] = {}

    def studies(self, query: str) -> list[dict] | None:
        if query in self._memo:
            return self._memo[query]
        fetched_at = self._fetched_at or datetime.now(timezone.utc).isoformat()
        try:
            returned = self._search(query)
        except Exception as exc:  # the registry is an operational boundary
            payload = {
                "query": query,
                "status": "lookup_failed",
                "error": f"{type(exc).__name__}: {exc}",
                "fetched_at": fetched_at,
                "studies": None,
            }
        else:
            kept = sorted(
                (study for study in returned if _nct(study)), key=_nct
            )[:MAX_STUDIES_PER_QUERY]
            payload = {
                "query": query,
                "status": "ok",
                "returned": len(returned),
                "fetched_at": fetched_at,
                "studies": kept,
            }
        record = self.custody / "queries" / f"{_key(query)}.json"
        record.write_text(json.dumps(payload, sort_keys=True, indent=1))
        index_path = self.custody / "index.json"
        index = json.loads(index_path.read_text()) if index_path.exists() else {}
        index[query] = {"file": record.name, "sha256": _digest(payload)}
        index_path.write_text(json.dumps(index, sort_keys=True, indent=1))
        self._memo[query] = payload["studies"]
        return payload["studies"]


class PinnedLookup:
    """Read a lookup custody back. Never touches the network."""

    def __init__(self, custody: Path) -> None:
        self.custody = Path(custody)
        index_path = self.custody / "index.json"
        if not index_path.exists():
            raise LookupCustodyError(f"no lookup custody index at {index_path}")
        self._index = json.loads(index_path.read_text())

    def studies(self, query: str) -> list[dict] | None:
        entry = self._index.get(query)
        if entry is None:
            raise LookupCustodyError(
                f"query {query!r} was not recorded by the live lookup; the replay is not "
                "asking the question the live run asked"
            )
        payload = json.loads((self.custody / "queries" / entry["file"]).read_text())
        if _digest(payload) != entry["sha256"] or payload.get("query") != query:
            raise LookupCustodyError(f"lookup record for {query!r} does not match its seal")
        return payload["studies"]


def _tokens(text: str) -> list[str]:
    return [token for token in re.split(r"[^0-9a-z]+", text.casefold()) if token]


def name_in_intervention(name: str, intervention_name: str) -> bool:
    """L3: the query name appears as whole tokens in the intervention's own name."""

    wanted = _tokens(name)
    have = _tokens(intervention_name)
    if not wanted:
        return False
    width = len(wanted)
    return any(have[start : start + width] == wanted for start in range(len(have) - width + 1))


def _id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:20]
    return f"{prefix}:{digest}"


def _document(nct: str) -> SourceDocument:
    return SourceDocument(
        document_id=_id("doc", EXTRACTION_METHOD, nct),
        source_url=f"https://clinicaltrials.gov/study/{nct}",
        publisher="ClinicalTrials.gov",
        # Not ``trial_registry_record``: the record feeds this one fact and must not be
        # taken for a corpus document by any other reader.
        document_type="registry_target_lookup",
        retrieval_date=_EPOCH,
        content_hash=_id("hash", EXTRACTION_METHOD, nct),
        source_tier=SourceTier.REGISTRY,
        public_only=True,
    )


def lookup_eligible(
    qualified_asset_ids: list[str], facts_by_asset: dict[str, list[NormalizedFact]]
) -> list[str]:
    """L1: qualified assets with no construct target set from any stronger route."""

    return [
        asset_id
        for asset_id in qualified_asset_ids
        if not any(
            fact.fact_type == "construct_target_set"
            for fact in facts_by_asset.get(asset_id, [])
        )
    ]


def query_names_for(canonical_name: str, authority_names: tuple[str, ...]) -> list[str]:
    """L2: the asset's canonical name, then the authority's names for its drug."""

    return list(dict.fromkeys([canonical_name, *authority_names]))


def registry_target_evidence(
    asset_id: str,
    *,
    query_names: list[str],
    source: LookupSource,
    as_of_date: date,
) -> ConstructTargetEvidence | None:
    """The construct target set CT.gov states for the asset, or ``None``.

    ``None`` covers every way of not knowing -- no study, no admitted intervention, only
    empty readings, a failed query, or two readings that disagree -- and none of them is
    turned into a placeholder (L6).
    """

    names = list(dict.fromkeys(name for name in query_names if name and name.strip()))
    studies: dict[str, dict] = {}
    for name in names:
        found = source.studies(name)
        if found is None:
            # L7: fail closed. A name whose answer is unknown might have disagreed.
            return None
        for study in found:
            studies.setdefault(_nct(study), study)

    readings: list[tuple[str, str, list[str]]] = []
    for nct in sorted(studies):
        interventions = (
            (studies[nct].get("armsInterventionsModule") or {}).get("interventions") or []
        )
        for intervention in interventions:
            intervention_name = str(intervention.get("name", "") or "")
            if not any(name_in_intervention(name, intervention_name) for name in names):
                continue
            targets = intervention_construct_targets(
                intervention, intervention_type=intervention.get("type")
            )
            if targets:
                readings.append((nct, intervention_name, targets))
    if not readings:
        return None
    sets = {tuple(targets) for _, _, targets in readings}
    if len(sets) != 1:
        return None
    targets = list(next(iter(sets)))

    claims = [
        ExtractedClaim(
            claim_id=_id("claim", asset_id, EXTRACTION_METHOD, nct, intervention_name),
            subject_id=asset_id,
            predicate="construct_target_set",
            normalized_value=list(found),
            source_document_id=_document(nct).document_id,
            supporting_passage=json.dumps(
                {"nct_id": nct, "intervention": intervention_name, "query_names": names},
                sort_keys=True,
            ),
            locator=f"{nct}.armsInterventionsModule.interventions",
            direct_observation=True,
            extraction_method=EXTRACTION_METHOD,
            extractor_version=EXTRACTOR_VERSION,
            extraction_confidence=_CONFIDENCE,
            verification_status=VerificationStatus.EXTRACTED,
            applicable_as_of_date=as_of_date,
        )
        for nct, intervention_name, found in readings
    ]
    documents = {nct: _document(nct) for nct, _, _ in readings}
    fact = NormalizedFact(
        fact_id=_id("fact", asset_id, "construct_target_set", EXTRACTION_METHOD, *targets),
        subject_id=asset_id,
        fact_type="construct_target_set",
        value=targets,
        supporting_claim_ids=[claim.claim_id for claim in claims],
        confidence=_CONFIDENCE,
    )
    return ConstructTargetEvidence(
        documents=list(documents.values()), claims=claims, fact=fact
    )
