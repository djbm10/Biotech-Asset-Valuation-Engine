"""Discovery adapters over an acquired :class:`~bve.se.acquisition.CorpusStore`.

The acquisition corpus already owns the immutable source snapshots.  This adapter indexes those
snapshots once, then serves every discovery pass without exporting YAML, rereading the corpus for
each query, or writing a second set of snapshots.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from bve.se.acquisition.corpus_store import CorpusDocument, CorpusStore, IndexStatus
from bve.se.discovery.adapters import (
    QueryVocabulary,
    _candidate_interventions,
    _matches_follow_up,
    _normalized_lookup,
    _protocol_text,
    extract_observed_asset_names,
)
from bve.se.discovery.orchestrator import AdapterResult
from bve.se.schemas.contracts import (
    CandidateHit,
    CompiledQuery,
    SearchOutcome,
    SourceDocument,
)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:20]
    return f"{prefix}:{digest}"


def _unique_names(values: Iterable[str]) -> tuple[str, ...]:
    observed: dict[str, str] = {}
    for value in values:
        cleaned = " ".join(value.split()).strip()
        normalized = _normalized_lookup(cleaned)
        if cleaned and normalized:
            observed.setdefault(normalized, cleaned)
    return tuple(observed.values())


def _string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return []


@dataclass(frozen=True)
class _ObservedCandidate:
    asset_name: str
    company_name: str | None
    trial_id: str | None
    target_ids: tuple[str, ...]
    modality_id: str | None
    aliases: tuple[str, ...] = ()

    def searchable_text(self) -> str:
        return " ".join(
            value
            for value in (
                self.asset_name,
                *self.aliases,
                self.company_name or "",
                self.trial_id or "",
            )
            if value
        )


@dataclass(frozen=True)
class _IndexedDocument:
    corpus_document: CorpusDocument
    source_document: SourceDocument
    snapshot_id: str
    searchable_text: str
    target_ids: tuple[str, ...]
    modality_id: str | None
    candidates: tuple[_ObservedCandidate, ...]


def _source_document(document: CorpusDocument, snapshot_bytes: bytes) -> tuple[SourceDocument, str]:
    digest = hashlib.sha256(snapshot_bytes).hexdigest()
    document_id = _stable_id(
        "document",
        document.source_family,
        document.document_id,
        digest,
    )
    return (
        SourceDocument(
            document_id=document_id,
            source_url=document.source_url,
            publisher=document.publisher,
            document_type=document.document_type,
            publication_date=document.publication_date,
            retrieval_date=document.retrieval_date,
            content_hash=digest,
            snapshot_path=document.snapshot_path,
            source_tier=document.source_tier,
        ),
        f"snapshot:{digest}",
    )


def _ctgov_candidates(
    payload: dict[str, Any], vocabulary: QueryVocabulary
) -> tuple[_ObservedCandidate, ...]:
    identification = payload.get("identificationModule", {})
    sponsor = (
        payload.get("sponsorCollaboratorsModule", {})
        .get("leadSponsor", {})
        .get("name")
    )
    nct_id = str(identification.get("nctId") or "") or None
    raw_interventions = payload.get("armsInterventionsModule", {}).get("interventions", [])
    aliases_by_name: dict[str, tuple[str, ...]] = {}
    for intervention in raw_interventions:
        name = str(intervention.get("name") or "").strip()
        if not name:
            continue
        aliases_by_name[_normalized_lookup(name)] = _unique_names(
            _string_values(intervention.get("otherNames"))
        )

    candidates: list[_ObservedCandidate] = []
    for name, targets, modality in _candidate_interventions(payload, vocabulary):
        candidates.append(
            _ObservedCandidate(
                asset_name=name,
                company_name=str(sponsor) if sponsor else None,
                trial_id=nct_id,
                target_ids=tuple(sorted(targets)),
                modality_id=modality,
                aliases=aliases_by_name.get(_normalized_lookup(name), ()),
            )
        )
    return tuple(candidates)



def _modality_passage_pattern(vocabulary: QueryVocabulary) -> str:
    """Alternation over every modality spelling the ontology knows.

    Long portfolio disclosures are scanned for local passages that carry modality evidence.
    The pattern is derived rather than written out so a disclosure about a modality this
    file was not authored around is still scanned.

    Terms arrive space-separated because the vocabulary folds separators away, but this
    pattern runs against the raw text (the match offsets locate the passage), so each gap
    is widened back out to accept the hyphenated spellings sources actually publish.
    """

    terms = sorted(
        {term for _, terms in vocabulary.modalities for term in terms},
        key=lambda term: (-len(term), term),
    )
    patterns = [r"[\s\-_/]+".join(re.escape(word) for word in term.split()) for term in terms]
    return "|".join(patterns) or r"(?!x)x"


def _generic_candidates(
    document: CorpusDocument,
    payload: Any,
    searchable_text: str,
    targets: tuple[str, ...],
    modality: str | None,
    vocabulary: QueryVocabulary,
) -> tuple[_ObservedCandidate, ...]:
    payload_title = ""
    if isinstance(payload, dict):
        payload_title = str(payload.get("title") or "")
    if document.source_family in {"fda_label", "pubmed"}:
        # Labels and publications have a bounded, source-authored title. Searching their full
        # bodies turns biomarkers, registry IDs, comparators, and cited programs into assets.
        evidence_passages = [document.title, payload_title]
    else:
        # Corporate/SEC documents can be long portfolio disclosures. Extract identities only from
        # local passages that independently contain both target and modality evidence.
        evidence_passages = []
        for match in re.finditer(
            _modality_passage_pattern(vocabulary),
            searchable_text,
            flags=re.IGNORECASE,
        ):
            start = max(0, match.start() - 350)
            end = min(len(searchable_text), match.end() + 350)
            passage = searchable_text[start:end]
            if vocabulary.targets_in(passage) and vocabulary.modality_in(passage):
                evidence_passages.append(passage)
    names = extract_observed_asset_names(*evidence_passages)
    generic_publishers = {
        document.source_family.casefold(),
        "pubmed",
        "sec edgar",
        "fda/dailymed",
    }
    company = (
        document.publisher
        if document.publisher.strip().casefold() not in generic_publishers
        else None
    )
    return tuple(
        _ObservedCandidate(
            asset_name=name,
            company_name=company,
            trial_id=None,
            target_ids=targets,
            modality_id=modality,
        )
        for name in names
        if _normalized_lookup(name) in _normalized_lookup(searchable_text)
    )


def _index_document(
    document: CorpusDocument, vocabulary: QueryVocabulary
) -> _IndexedDocument | None:
    if document.index_status is not IndexStatus.INDEXED:
        return None
    path = Path(document.snapshot_path)
    snapshot_bytes = path.read_bytes()
    try:
        payload: Any = json.loads(snapshot_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid corpus snapshot for {document.document_id}: {path}") from exc

    source_document, snapshot_id = _source_document(document, snapshot_bytes)
    if document.source_family == "clinicaltrials_gov":
        if not isinstance(payload, dict):
            raise ValueError(
                f"ClinicalTrials.gov snapshot is not an object: {document.document_id}"
            )
        structured_text = _protocol_text(payload)
        searchable_text = f"{document.title} {document.text} {structured_text}"
        targets = tuple(sorted(vocabulary.targets_in(structured_text)))
        modality = vocabulary.modality_in(structured_text)
        candidates = _ctgov_candidates(payload, vocabulary)
    else:
        payload_text = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        searchable_text = f"{document.title} {document.text} {payload_text}"
        targets = tuple(sorted(vocabulary.targets_in(searchable_text)))
        modality = vocabulary.modality_in(searchable_text)
        candidates = _generic_candidates(
            document,
            payload,
            searchable_text,
            targets,
            modality,
            vocabulary,
        )
    return _IndexedDocument(
        corpus_document=document,
        source_document=source_document,
        snapshot_id=snapshot_id,
        searchable_text=searchable_text,
        target_ids=targets,
        modality_id=modality,
        candidates=candidates,
    )


class CorpusDiscoveryAdapter:
    """Serve one acquired source family through the common discovery contract."""

    def __init__(
        self,
        source_name: str,
        documents: Iterable[CorpusDocument],
        *,
        mandatory: bool = False,
    ) -> None:
        if not source_name.strip():
            raise ValueError("source_name must be non-empty")
        materialized = list(documents)
        mismatched = sorted(
            {document.source_family for document in materialized}
            - {source_name}
        )
        if mismatched:
            raise ValueError(
                f"adapter {source_name!r} received documents from: {', '.join(mismatched)}"
            )
        self.source_name = source_name
        self.mandatory = mandatory
        # Indexing precedes any query, so it labels against the whole ontology vocabulary.
        vocabulary = QueryVocabulary.for_ontology()
        self._documents = tuple(
            indexed
            for document in materialized
            if (indexed := _index_document(document, vocabulary)) is not None
        )
        follow_up_index: dict[str, dict[str, _IndexedDocument]] = {}
        for indexed in self._documents:
            for candidate in indexed.candidates:
                for value in (
                    candidate.asset_name,
                    *candidate.aliases,
                    candidate.trial_id or "",
                ):
                    normalized = _normalized_lookup(value)
                    if normalized:
                        follow_up_index.setdefault(normalized, {})[
                            indexed.source_document.document_id
                        ] = indexed
        self._follow_up_index = {
            key: tuple(documents.values()) for key, documents in follow_up_index.items()
        }

    def search(self, query: CompiledQuery, *, as_of_date: date) -> AdapterResult:
        required_targets = {target.upper() for target in query.target_ids}
        required_modalities = {modality.upper() for modality in query.modality_ids}
        hits: list[CandidateHit] = []
        documents: list[SourceDocument] = []
        snapshot_ids: list[str] = []
        discovered_aliases: list[str] = []
        follow_ups: list[str] = []

        documents_to_search = self._documents
        if query.expansion_depth > 0:
            follow_up_keys = {
                normalized
                for normalized in (
                    _normalized_lookup(value) for value in [query.query, *query.aliases]
                )
                if normalized
            }
            selected: dict[str, _IndexedDocument] = {}
            for key in follow_up_keys:
                for indexed in self._follow_up_index.get(key, ()):
                    selected[indexed.source_document.document_id] = indexed
            documents_to_search = tuple(selected.values())

        for indexed in documents_to_search:
            corpus_document = indexed.corpus_document
            if (
                corpus_document.publication_date is not None
                and corpus_document.publication_date > as_of_date
            ):
                continue
            observed_targets = {target.upper() for target in indexed.target_ids}
            if required_targets and not required_targets.issubset(observed_targets):
                continue
            if required_modalities and (
                indexed.modality_id is None
                or indexed.modality_id.upper() not in required_modalities
            ):
                continue
            if not _matches_follow_up(query, indexed.searchable_text):
                continue

            documents.append(indexed.source_document)
            snapshot_ids.append(indexed.snapshot_id)
            for candidate in indexed.candidates:
                candidate_targets = {target.upper() for target in candidate.target_ids}
                if required_targets and not required_targets.issubset(candidate_targets):
                    continue
                if required_modalities and (
                    candidate.modality_id is None
                    or candidate.modality_id.upper() not in required_modalities
                ):
                    continue
                if not _matches_follow_up(query, candidate.searchable_text()):
                    continue
                identity = "|".join(
                    [
                        candidate.company_name or "",
                        candidate.asset_name,
                        candidate.trial_id or "",
                    ]
                ).casefold()
                hits.append(
                    CandidateHit(
                        hit_id=_stable_id(
                            "hit",
                            self.source_name,
                            indexed.source_document.document_id,
                            identity,
                        ),
                        source=self.source_name,
                        source_document_id=indexed.source_document.document_id,
                        query=query.query,
                        asset_name=candidate.asset_name,
                        company_name=candidate.company_name,
                        trial_id=candidate.trial_id,
                        target_terms=list(candidate.target_ids),
                        modality_terms=(
                            [candidate.modality_id] if candidate.modality_id else []
                        ),
                        aliases=list(candidate.aliases),
                        snippet=corpus_document.text[:500],
                        provisional_identity_key=identity,
                        retrieved_at=corpus_document.retrieval_date,
                        applicable_as_of_date=as_of_date,
                    )
                )
                discovered_aliases.extend(
                    [
                        candidate.asset_name,
                        *candidate.aliases,
                        candidate.company_name or "",
                    ]
                )
                if query.expansion_depth == 0:
                    follow_ups.extend(
                        [
                            candidate.asset_name,
                            *candidate.aliases,
                            candidate.trial_id or "",
                        ]
                    )

        unique_documents = {
            document.document_id: document for document in documents
        }
        return AdapterResult(
            hits=list({hit.hit_id: hit for hit in hits}.values()),
            outcome=(
                SearchOutcome.SUCCESS
                if unique_documents
                else SearchOutcome.NO_EVIDENCE_FOUND
            ),
            snapshot_ids=list(dict.fromkeys(snapshot_ids)),
            discovered_aliases=list(_unique_names(discovered_aliases)),
            follow_up_queries=list(_unique_names(follow_ups)),
            source_documents=list(unique_documents.values()),
        )


def adapters_from_corpus(
    store: CorpusStore,
    required_source_families: Sequence[str],
    *,
    proven_no_data_source_families: Sequence[str] = (),
) -> list[CorpusDiscoveryAdapter]:
    """Build one adapter per family, including required families proven to have no data.

    A required family is never inferred to be empty merely because it is absent from the corpus.
    The caller must explicitly supply families whose successful acquisition health verdict was
    ``NO_DATA``.  Those families receive empty mandatory adapters so discovery can record
    ``NO_EVIDENCE_FOUND`` without weakening mandatory-source configuration checks.
    """

    required = tuple(dict.fromkeys(required_source_families))
    if any(not source.strip() for source in required):
        raise ValueError("required source family names must be non-empty")
    proven_no_data = tuple(dict.fromkeys(proven_no_data_source_families))
    if any(not source.strip() for source in proven_no_data):
        raise ValueError("proven NO_DATA source family names must be non-empty")
    unexpected_no_data = sorted(set(proven_no_data) - set(required))
    if unexpected_no_data:
        raise ValueError(
            "proven NO_DATA families must be required source families: "
            + ", ".join(unexpected_no_data)
        )
    grouped = store.by_family()
    contradictory_no_data = sorted(set(proven_no_data) & set(grouped))
    if contradictory_no_data:
        raise ValueError(
            "proven NO_DATA families unexpectedly contain corpus documents: "
            + ", ".join(contradictory_no_data)
        )
    missing = sorted(set(required) - set(grouped) - set(proven_no_data))
    if missing:
        raise ValueError(
            "required source families absent from corpus: " + ", ".join(missing)
        )
    adapter_families = sorted(set(grouped) | set(proven_no_data))
    return [
        CorpusDiscoveryAdapter(
            source_name,
            grouped.get(source_name, ()),
            mandatory=source_name in set(required),
        )
        for source_name in adapter_families
    ]
