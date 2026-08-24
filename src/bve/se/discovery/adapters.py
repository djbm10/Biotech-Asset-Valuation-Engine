"""Source adapters that normalize live/frozen discovery results into ``CandidateHit`` records."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import lru_cache
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from bve.se.discovery.orchestrator import AdapterResult
from bve.se.ontology.modality import (
    known_modalities,
    modality_aliases,
    modality_gate_terms,
    modality_query_terms,
    normalize_modality,
)
from bve.se.ontology.records import normalize_lookup_key
from bve.se.ontology.targets import known_targets, target_aliases
from bve.se.universe.provenance import describe_universe
from bve.se.universe.provider import (
    PayloadKind,
    TrialQuery,
    TrialUniverseProvider,
)
from bve.se.schemas.contracts import (
    CandidateHit,
    CompiledQuery,
    SearchOutcome,
    SourceDocument,
    SourceTier,
    TrialUniverseProvenance,
)

TrialSearch = Callable[..., list[dict[str, Any]]]
PubMedSearch = Callable[[str, int], list[dict[str, Any]]]
UrlFetch = Callable[[str], dict[str, Any]]

_ASSET_CODE_RE = re.compile(r"\b[A-Z]{2,8}(?:[- ]?\d{2,8}[A-Z]?)\b")
_BIOLOGIC_NAME_RE = re.compile(
    r"\b[a-z][a-z-]{4,40}(?:mab|cept|parib|tinib|lisib|nib)(?:-[a-z]{3,5})?\b",
    re.IGNORECASE,
)
_NON_ASSET_CODES = {
    "BCMA",
    "CD3",
    "CD3E",
    "CD19",
    "CD20",
    "CD269",
    "TNFRSF17",
}
_NON_ASSET_CODE_PREFIXES = {
    "ASH",
    "CD",
    "CFR",
    "CI",
    "COVID",
    "CRD",
    "CYP",
    "EFS",
    "EULAR",
    "EUR",
    "FORM",
    "GSE",
    "HLA",
    "HPV",
    "IL",
    "ORR",
    "OS",
    "PFS",
    "PROSPERO",
    "Q",
    "SECTION",
    "TP",
    "USD",
}
_GENERIC_ASSET_PHRASES = (
    "biospecimen",
    "bone marrow",
    "computed tomography",
    "magnetic resonance",
    "placebo",
    "sample collection",
    "standard of care",
)


def _digest(prefix: str, value: str) -> str:
    return f"{prefix}:{hashlib.sha256(value.encode()).hexdigest()[:20]}"


def _normalized_lookup(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _plausible_asset_name(value: str) -> bool:
    stripped = " ".join(value.split()).strip(" ,.;:()[]{}")
    if len(stripped) < 3 or len(stripped) > 120:
        return False
    lowered = stripped.casefold()
    if any(phrase in lowered for phrase in _GENERIC_ASSET_PHRASES):
        return False
    normalized = _normalized_lookup(stripped).upper()
    if normalized in _NON_ASSET_CODES or normalized.startswith(("NCT", "PMID")):
        return False
    prefix_match = re.match(r"[A-Z]+", normalized)
    if prefix_match and prefix_match.group(0) in _NON_ASSET_CODE_PREFIXES:
        return False
    return True


def extract_observed_asset_names(*texts: str) -> list[str]:
    """Extract source-observed program names without falling back to a document title.

    The deliberately conservative extractor recognizes development codes and common drug-name
    suffixes. Documents without an observed program name remain evidence documents; they do not
    manufacture a ``CanonicalAsset`` from a publication or URL title.
    """

    combined = "\n".join(text for text in texts if text)[:100_000]
    candidates = [
        *[match.group(0) for match in _ASSET_CODE_RE.finditer(combined)],
        *[match.group(0) for match in _BIOLOGIC_NAME_RE.finditer(combined)],
    ]
    return list(
        dict.fromkeys(
            " ".join(candidate.split())
            for candidate in candidates
            if _plausible_asset_name(candidate)
        )
    )


def _matches_follow_up(query: CompiledQuery, text: str) -> bool:
    if query.expansion_depth == 0:
        return True
    haystack = _normalized_lookup(text)
    terms = [query.query, *query.aliases]
    return any(
        normalized and normalized in haystack
        for normalized in (_normalized_lookup(term) for term in terms)
    )


def _protocol_text(protocol: dict[str, Any]) -> str:
    return json.dumps(protocol, sort_keys=True, separators=(",", ":"))


def _extract_interventions(protocol: dict[str, Any]) -> list[dict[str, Any]]:
    module = protocol.get("armsInterventionsModule", {})
    return [
        intervention
        for intervention in module.get("interventions", [])
        if intervention.get("name", "").strip()
    ]


#: A query that names nothing, used to build the modality half of the indexing vocabulary.
_EMPTY_QUERY = CompiledQuery(query_id="vocabulary", query="")


def _fold(text: str) -> str:
    """Fold text into the ontology's lookup spelling before substring matching.

    Sources write ``T-cell engager``, ``T cell engager`` and ``t_cell_engager`` for one
    thing. The deleted hardcoded term lists absorbed that by enumerating spellings, which
    does not survive contact with a term nobody enumerated. Folding both sides handles it
    once, for every term the ontology supplies.
    """

    return normalize_lookup_key(text)


@lru_cache(maxsize=512)
def _word_boundary_pattern(terms: tuple[str, ...]) -> re.Pattern[str]:
    """One compiled alternation for a term set, instead of a regex per term per record.

    ``re.search(rf"\\b{re.escape(term)}\\b", ...)`` re-escapes and re-formats the pattern
    on every call and relies on re's internal cache to undo the damage; at corpus scale
    that was 14% of total CPU. Matching stays word-bounded, so a gate term as short as
    ``cd3`` still cannot admit CD30 or CD33.
    """

    if not terms:
        # Matches nothing, so an empty vocabulary keeps its "no modality requested"
        # behaviour at the call site rather than accidentally matching everything.
        return re.compile(r"(?!x)x")
    return re.compile(r"\b(?:" + "|".join(re.escape(term) for term in terms) + r")\b")


@dataclass(frozen=True)
class QueryVocabulary:
    """The search vocabulary for one compiled query, derived from the ontology.

    Discovery must not carry its own target or modality word lists. A hardcoded list is
    the previous benchmark leaking into retrieval: it makes the pipeline look accurate on
    the targets it was written for and silently un-discoverable for every other one.
    Terms come from :mod:`bve.se.ontology` so a new target is discoverable as soon as the
    ontology snapshot knows it, with no change here.
    """

    #: ``(canonical_id, casefolded terms)`` for each target the query asked for.
    targets: tuple[tuple[str, tuple[str, ...]], ...] = ()
    #: Same for modalities, query-requested ones first so they win a label tie.
    modalities: tuple[tuple[str, tuple[str, ...]], ...] = ()
    #: The subset of ``modalities`` the query actually asked for. Labelling scans every
    #: known modality, but eligibility may only be gated on what was requested.
    requested_modalities: frozenset[str] = frozenset()

    @classmethod
    def for_query(cls, query: CompiledQuery) -> "QueryVocabulary":
        targets: list[tuple[str, tuple[str, ...]]] = []
        for canonical in query.target_ids:
            terms = {_fold(canonical)}
            terms.update(_fold(alias) for alias in target_aliases(canonical))
            # Query-supplied aliases are query-wide, not per-target, so they can only be
            # attributed to a specific target when the query names exactly one. With more
            # than one, attributing them to each would let an alias of A match B.
            if len(query.target_ids) == 1:
                terms.update(_fold(alias) for alias in query.aliases)
            targets.append((canonical, tuple(sorted(terms))))

        requested = [normalize_modality(value) or value for value in query.modality_ids]
        ordered = [*dict.fromkeys(requested)]
        ordered += [name for name in known_modalities() if name not in ordered]
        modalities = [
            (
                canonical,
                tuple(sorted(
                    {_fold(alias) for alias in modality_aliases(canonical)},
                    # Longest first: "bispecific t cell engager" must beat "antibody".
                    key=lambda term: (-len(term), term),
                )),
            )
            for canonical in ordered
            if modality_aliases(canonical)
        ]
        return cls(
            targets=tuple(targets),
            modalities=tuple(modalities),
            requested_modalities=frozenset(
                canonical for canonical in requested if modality_aliases(canonical)
            ),
        )

    @staticmethod
    @lru_cache(maxsize=1)
    def for_ontology() -> "QueryVocabulary":
        """Whole-snapshot vocabulary, for labelling that happens before a query exists.

        Memoized. This is per-run state -- a pure function of the pinned snapshot -- but
        extraction called it once per hit, rebuilding and case-folding every target alias
        in the ontology for each record. That was ~6 hours of a single run's extraction
        stage. :func:`bve.se.ontology.targets.reset_resolver_cache` invalidates it.

        Corpus indexing runs ahead of any query. Without a snapshot this yields no targets
        and the indexer labels none, which is the intended abstention: search may abstain
        without a snapshot, it may not fall back to a benchmark-shaped word list.
        """

        targets = tuple(
            (canonical, tuple(sorted({_fold(canonical), *(_fold(a) for a in aliases)})))
            for canonical, aliases in known_targets()
        )
        return QueryVocabulary(
            targets=targets, modalities=QueryVocabulary.for_query(_EMPTY_QUERY).modalities
        )

    def targets_in(self, text: str) -> set[str]:
        lowered = _fold(text)
        return {
            canonical
            for canonical, terms in self.targets
            if any(term in lowered for term in terms)
        }

    def modality_in(self, text: str) -> str | None:
        """Label text with its most specific supported modality.

        Scored by longest matching alias rather than iteration order, so "BiTE bispecific"
        resolves to T_CELL_ENGAGER instead of the broader BISPECIFIC_ANTIBODY that a
        shorter alias would otherwise claim. A modality the query asked for outranks one
        it did not, since that is the distinction the caller cares about.
        """

        lowered = _fold(text)
        best: tuple[int, int, str] | None = None
        for canonical, terms in self.modalities:
            matched = max((len(term) for term in terms if term in lowered), default=0)
            if not matched:
                continue
            score = (1 if canonical in self.requested_modalities else 0, matched, canonical)
            if best is None or score > best:
                best = score
        return best[2] if best else None

    def requested_modality_terms(self) -> tuple[str, ...]:
        """Folded terms for the query's modalities only, for eligibility gating.

        Gating on every known modality would admit any trial at all, so this is
        deliberately narrower than the vocabulary used for labelling — and, in the other
        direction, wider than that vocabulary's aliases, because evidence that a construct
        *is* the requested modality is not limited to the names it is called by.
        """

        return tuple(
            dict.fromkeys(
                _fold(term)
                for canonical in sorted(self.requested_modalities)
                for term in modality_gate_terms(canonical)
            )
        )

    def matches_requested_modality(self, text: str) -> bool:
        """True when no modality was requested, or the text supports one that was.

        Matched on word boundaries rather than as a substring: a gate term as short as
        ``cd3`` would otherwise admit every CD30 and CD33 programme ever written down.
        """

        if not self.requested_modalities:
            return True
        pattern = _word_boundary_pattern(tuple(self.requested_modality_terms()))
        return pattern.search(_fold(text)) is not None

    def query_terms(self) -> tuple[str, ...]:
        """Retrieval terms for the upstream registry: target aliases plus modality expansion.

        Replaces a hardcoded ``CD3 CD3E T-cell engager BiTE bispecific trispecific`` suffix
        that was appended to every query regardless of what was asked.
        """

        terms: list[str] = []
        for canonical, _ in self.targets:
            terms.extend(target_aliases(canonical) or (canonical,))
        for canonical in sorted(self.requested_modalities):
            terms.extend(modality_query_terms(canonical))
        # Canonical IDs are internal identifiers (``T_CELL_ENGAGER``); sending them to a
        # registry matches nothing and only dilutes the query.
        return tuple(dict.fromkeys(term for term in terms if term and "_" not in term))

    def query_facets(self) -> tuple[tuple[str, ...], ...]:
        """The same vocabulary, kept as separate AND-ed facets.

        ``query_terms`` flattens targets and modalities into one bag, which discards the
        fact that they are different questions: any spelling of the target, AND any
        spelling of the modality. Retrieval needs the structure -- flattened, a PDCD1
        vaccine query matched every trial containing the word "vaccine".
        """

        def _clean(terms: list[str]) -> tuple[str, ...]:
            return tuple(dict.fromkeys(t for t in terms if t and "_" not in t))

        target_terms: list[str] = []
        for canonical, _ in self.targets:
            target_terms.extend(target_aliases(canonical) or (canonical,))
        modality_terms: list[str] = []
        for canonical in sorted(self.requested_modalities):
            modality_terms.extend(modality_query_terms(canonical))
        return tuple(f for f in (_clean(target_terms), _clean(modality_terms)) if f)


def _candidate_interventions(
    protocol: dict[str, Any],
    vocabulary: QueryVocabulary,
    serialized: str | None = None,
) -> list[tuple[str, set[str], str | None]]:
    """Exclude obvious concomitant/supportive interventions while retaining near-match candidates.

    Modality eligibility remains an evidence-backed gate; discovery may intentionally retain a
    named combination partner as a near-match, but should not turn every background drug into an
    apparent development program.
    """

    identification = protocol.get("identificationModule", {})
    description = protocol.get("descriptionModule", {})
    title_context = " ".join(
        [
            identification.get("briefTitle", ""),
            identification.get("officialTitle", ""),
            description.get("briefSummary", ""),
        ]
    ).casefold()
    # Callers that have already serialized the protocol pass it in. Re-deriving it here
    # cost six ``json.dumps`` passes per protocol per query, which is the same corpus x
    # query quadratic the search loop's memoization removes.
    serialized = _protocol_text(protocol) if serialized is None else serialized
    protocol_targets = vocabulary.targets_in(serialized)
    protocol_modality = vocabulary.modality_in(serialized)
    selected: list[tuple[str, set[str], str | None]] = []
    all_interventions = _extract_interventions(protocol)
    for intervention in all_interventions:
        name = intervention.get("name", "").strip()
        other_names = intervention.get("otherNames", []) or []
        other_names_text = " ".join(other_names) if isinstance(other_names, list) else str(other_names)
        intervention_context = " ".join(
            [name, intervention.get("description", ""), other_names_text]
        ).casefold()
        primary_names = extract_observed_asset_names(name)
        observed_names = extract_observed_asset_names(name, other_names_text)
        observed_in_title = any(
            _normalized_lookup(observed) in _normalized_lookup(title_context)
            for observed in observed_names
        )
        if (
            name.casefold() in title_context
            or observed_in_title
            or vocabulary.matches_requested_modality(intervention_context)
        ):
            intervention_targets = vocabulary.targets_in(intervention_context)
            intervention_modality = vocabulary.modality_in(intervention_context)
            # Protocol-level target/modality text is safe only when there is one named
            # intervention. In combination studies, assigning it to every background drug creates
            # false candidate programs (e.g. supportive agents and combination partners).
            if len(all_interventions) == 1:
                intervention_targets = intervention_targets or protocol_targets
                intervention_modality = intervention_modality or protocol_modality
            canonical_name = primary_names[0] if len(primary_names) == 1 else name
            selected.append(
                (
                    canonical_name,
                    intervention_targets,
                    intervention_modality,
                )
            )
    if len(selected) == 1 and selected[0][2] is None and protocol_modality:
        name, targets, _ = selected[0]
        selected[0] = (name, targets, protocol_modality)
    elif len(selected) > 1 and protocol_modality:
        normalized_names = [_normalized_lookup(name) for name, _, _ in selected]
        if len(set(normalized_names)) == 1:
            selected = [
                (
                    name,
                    targets or protocol_targets,
                    modality or protocol_modality,
                )
                for name, targets, modality in selected
            ]
    return selected


#: The parser applied to acquired payloads, recorded separately from the backend that
#: supplied them: the same records reached through AACT would need a different one.
CTGOV_EXTRACTOR = "clinicaltrials_v2"
CTGOV_EXTRACTOR_VERSION = "1"


class ClinicalTrialsGovAdapter:
    """Discover trial programs and sponsors from a trial universe provider.

    Acquisition belongs to the provider; this adapter opens the CT.gov-shaped envelopes it
    is entitled to and extracts from them exactly as before.
    """

    source_name = "clinicaltrials_gov"
    mandatory = True

    def __init__(
        self,
        search_fn: TrialSearch | None = None,
        *,
        provider: "TrialUniverseProvider | None" = None,
        page_size: int = 250,
        max_records: int | None = None,
        snapshot_root: Path | None = None,
    ) -> None:
        if provider is not None and search_fn is not None:
            raise ValueError("pass either a trial universe provider or a search_fn, not both")
        self.provider = provider
        if provider is None and search_fn is None:
            from bve.ingestion.clinicaltrials_gov import search_studies

            search_fn = search_studies
        self.search_fn = search_fn
        self.page_size = page_size
        #: How much of the universe to keep, as a policy choice. ``None`` sweeps it all.
        #: This used to be ``page_size``, which quietly made an HTTP paging default into
        #: a recall ceiling -- the first PDCD1 baseline scored against 250 of 403 trials.
        self.max_records = max_records
        self.snapshot_root = snapshot_root
        #: nctId -> (serialized, digest, snapshot path, folded text). The corpus is
        #: retrieved by many queries but is the same corpus each time; this keeps the
        #: per-protocol serialize/hash/snapshot cost proportional to the corpus rather
        #: than to corpus x queries.
        self._materialized: dict[str, tuple[str, str, str | None, str]] = {}
        #: Provenance of the last provider fetch, for the run manifest. Stays ``None`` on
        #: the legacy ``search_fn`` path, which acquires its own records and so cannot
        #: state which universe it saw — an absence the manifest records rather than hides.
        self.trial_universe: TrialUniverseProvenance | None = None

    def _acquire(
        self, vocabulary: QueryVocabulary, query: CompiledQuery, as_of_date: date
    ) -> list[dict[str, Any]]:
        """Obtain CT.gov protocol payloads, via the provider when one is configured.

        The adapter no longer performs acquisition when a provider is present: it asks for
        a universe and opens the envelopes it is entitled to. Extraction below is
        deliberately unchanged — moving CT.gov parsing behind a backend-neutral extractor
        is a separate concern, and doing it here would turn an integration seam into a
        rewrite of code that already works.
        """

        facets = vocabulary.query_facets() or (
            tuple(query.aliases or query.target_ids),
        )
        terms = tuple(t for facet in facets for t in facet)
        if self.provider is None:
            # CT.gov intervention search is the broad retrieval layer; explicit canonical
            # checks below prevent the query string from becoming an eligibility assertion.
            return self.search_fn(
                intervention=" ".join(terms),
                page_size=self.page_size,
                max_records=self.max_records,
            )

        trial_query = TrialQuery(
            # Both: ``term_groups`` carries the semantics, ``terms`` keeps the flat list
            # legible in run provenance. ``facets()`` reads the groups, so they cannot
            # disagree about what was actually searched.
            terms=list(terms),
            term_groups=[list(facet) for facet in facets],
            as_of_date=as_of_date,
            max_records=self.max_records,
        )
        started_at = datetime.now(timezone.utc)
        result = self.provider.fetch(trial_query)
        self.trial_universe = describe_universe(
            result,
            trial_query,
            retrieval_started_at=started_at,
            retrieval_completed_at=datetime.now(timezone.utc),
            extractor=CTGOV_EXTRACTOR,
            extractor_version=CTGOV_EXTRACTOR_VERSION,
        )
        if result.outcome is SearchOutcome.FAILED:
            raise RuntimeError(result.error or f"{result.backend} fetch failed")
        payloads: list[dict[str, Any]] = []
        for record in result.records:
            kind = record.snapshot.payload_kind if record.snapshot else None
            if kind is not PayloadKind.CTGOV_PROTOCOL_JSON:
                # Refuse rather than guess: this extractor reads CT.gov protocol JSON, and
                # an AACT relational row silently mis-parsed would look like an empty trial.
                raise ValueError(
                    f"{record.trial_id}: cannot parse payload kind {kind} as CT.gov protocol JSON"
                )
            if isinstance(record.raw_payload, dict):
                payloads.append(record.raw_payload)
        return payloads

    def _materialize(
        self, protocol: dict[str, Any]
    ) -> tuple[str, str, str | None, str]:
        """Serialize, hash, snapshot and case-fold one protocol -- at most once per run.

        Every query that retrieves a trial used to redo all of this for it: two full
        ``json.dumps`` passes, a SHA-256, a ``stat``, and a case-fold, before anything
        had decided the trial was even relevant. With the record cap removed the corpus
        also feeds the query frontier, so the work multiplied against itself: 5h26m of
        CPU and 2GB resident without producing a scoreable run.

        Memoizing preserves the evidence record exactly -- every protocol examined still
        yields its snapshot id -- rather than the cheaper and wrong fix of snapshotting
        only what survives the filters. Keyed by NCT id, which is the trial's identity;
        a protocol without one is not cached, since it has no stable key.
        """

        nct_id = (protocol.get("identificationModule") or {}).get("nctId")
        if nct_id is not None:
            cached = self._materialized.get(nct_id)
            if cached is not None:
                return cached

        serialized = _protocol_text(protocol)
        snapshot_content = json.dumps(protocol, indent=2, sort_keys=True) + "\n"
        snapshot_digest = hashlib.sha256(snapshot_content.encode()).hexdigest()
        snapshot_path_value: str | None = None
        if self.snapshot_root is not None:
            self.snapshot_root.mkdir(parents=True, exist_ok=True)
            snapshot_path = self.snapshot_root / f"{snapshot_digest}.json"
            if not snapshot_path.exists():
                snapshot_path.write_text(snapshot_content)
            snapshot_path_value = str(snapshot_path)
        entry = (
            serialized,
            snapshot_digest,
            snapshot_path_value,
            serialized.casefold().replace("_", " "),
        )
        if nct_id is not None:
            self._materialized[nct_id] = entry
        return entry

    def search(self, query: CompiledQuery, *, as_of_date: date) -> AdapterResult:
        vocabulary = QueryVocabulary.for_query(query)
        try:
            protocols = self._acquire(vocabulary, query, as_of_date)
        except Exception as exc:
            return AdapterResult(outcome=SearchOutcome.FAILED, error=str(exc))

        hits: list[CandidateHit] = []
        snapshots: list[str] = []
        source_documents: list[SourceDocument] = []
        aliases: set[str] = set()
        follow_ups: set[str] = set()
        for protocol in protocols:
            serialized, snapshot_digest, snapshot_path_value, lower = self._materialize(
                protocol
            )
            snapshot_id = f"snapshot:{snapshot_digest}"
            snapshots.append(snapshot_id)
            if not _matches_follow_up(query, serialized):
                continue
            protocol_targets = vocabulary.targets_in(lower)
            if query.target_ids and not set(query.target_ids).issubset(protocol_targets):
                continue
            if not vocabulary.matches_requested_modality(lower):
                continue
            identification = protocol.get("identificationModule", {})
            sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
            status_module = protocol.get("statusModule", {})
            nct_id = identification.get("nctId")
            document_id = _digest("document", snapshot_digest)
            source_documents.append(
                SourceDocument(
                    document_id=document_id,
                    source_url=(
                        f"https://clinicaltrials.gov/study/{nct_id}"
                        if nct_id
                        else "https://clinicaltrials.gov/"
                    ),
                    publisher="ClinicalTrials.gov",
                    document_type="trial_registry_record",
                    publication_date=None,
                    retrieval_date=datetime.now(timezone.utc),
                    content_hash=snapshot_digest,
                    snapshot_path=snapshot_path_value,
                    source_tier=SourceTier.REGISTRY,
                )
            )
            sponsor = sponsor_module.get("leadSponsor", {}).get("name")
            interventions = _candidate_interventions(protocol, vocabulary, serialized)
            if not interventions:
                fallback_name = identification.get("briefTitle") or nct_id or "unnamed program"
                interventions = [(fallback_name, protocol_targets, vocabulary.modality_in(lower))]
            last_update = status_module.get("lastUpdatePostDateStruct", {}).get("date")
            if last_update:
                try:
                    if date.fromisoformat(last_update[:10]) > as_of_date:
                        continue
                except ValueError:
                    pass
            for intervention, intervention_targets, intervention_modality in interventions:
                if query.target_ids and not set(query.target_ids).issubset(intervention_targets):
                    continue
                identity_key = f"{sponsor or ''}|{intervention}|{nct_id or ''}".casefold()
                hit_id = _digest("hit", f"{snapshot_id}|{identity_key}")
                hits.append(
                    CandidateHit(
                        hit_id=hit_id,
                        source=self.source_name,
                        source_document_id=document_id,
                        query=query.query,
                        asset_name=intervention,
                        company_name=sponsor,
                        trial_id=nct_id,
                        target_terms=sorted(intervention_targets),
                        modality_terms=[intervention_modality] if intervention_modality else [],
                        aliases=[],
                        snippet=identification.get("briefTitle", ""),
                        provisional_identity_key=identity_key,
                        retrieved_at=datetime.now(timezone.utc),
                        applicable_as_of_date=as_of_date,
                    )
                )
                aliases.add(intervention)
                if query.expansion_depth < 1:
                    # Intervention names are leads: a drug seen here may appear in trials
                    # the target/modality query never reached. The trial's own NCT id is
                    # not -- searching it returns the trial already in hand. On a 2,908
                    # trial corpus that queued 2,908 guaranteed-zero-yield queries, over
                    # half the orchestrator's 5,000-query budget.
                    follow_ups.add(intervention)
            if sponsor:
                aliases.add(sponsor)
        outcome = SearchOutcome.SUCCESS if protocols else SearchOutcome.NO_EVIDENCE_FOUND
        return AdapterResult(
            hits=hits,
            outcome=outcome,
            snapshot_ids=list(dict.fromkeys(snapshots)),
            discovered_aliases=sorted(aliases),
            follow_up_queries=sorted(follow_ups),
            source_documents=list({doc.document_id: doc for doc in source_documents}.values()),
        )


class FrozenCandidateAdapter:
    """Replay saved candidate hits through the same orchestration contract used by live sources."""

    def __init__(
        self,
        source_name: str,
        hits_by_query: dict[str, Iterable[CandidateHit]],
        *,
        mandatory: bool = True,
    ) -> None:
        self.source_name = source_name
        self.mandatory = mandatory
        self.hits_by_query = {query: list(hits) for query, hits in hits_by_query.items()}

    def search(self, query: CompiledQuery, *, as_of_date: date) -> AdapterResult:
        hits = [
            hit
            for hit in self.hits_by_query.get(query.query, [])
            if hit.applicable_as_of_date <= as_of_date
        ]
        return AdapterResult(
            hits=hits,
            outcome=SearchOutcome.SUCCESS if hits else SearchOutcome.NO_EVIDENCE_FOUND,
            snapshot_ids=sorted({hit.source_document_id for hit in hits}),
        )


class PubMedDiscoveryAdapter:
    """Search PubMed abstracts for target/modality evidence with immutable snapshots."""

    source_name = "pubmed"
    mandatory = False

    def __init__(self, search_fn: PubMedSearch | None = None, *, snapshot_root: Path | None = None) -> None:
        self.search_fn = search_fn or self._live_search
        self.snapshot_root = snapshot_root

    @staticmethod
    def _live_search(query: str, limit: int) -> list[dict[str, Any]]:
        import requests  # type: ignore[import-untyped]
        from xml.etree import ElementTree

        search = requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={"db": "pubmed", "term": query, "retmode": "json", "retmax": limit},
            timeout=30,
        )
        search.raise_for_status()
        ids = search.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []
        fetch = requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
            timeout=30,
        )
        fetch.raise_for_status()
        root = ElementTree.fromstring(fetch.text)
        records: list[dict[str, Any]] = []
        for article in root.findall(".//PubmedArticle"):
            pmid = article.findtext(".//PMID") or ""
            title_node = article.find(".//ArticleTitle")
            title = " ".join("".join(title_node.itertext()).split()) if title_node is not None else ""
            abstract = " ".join(
                " ".join(node.itertext())
                for node in article.findall(".//AbstractText")
            ).strip()
            year = article.findtext(".//PubDate/Year") or article.findtext(".//PubDate/MedlineDate") or ""
            records.append({"pmid": pmid, "title": title, "abstract": abstract, "publication_date": year})
        return records

    def search(self, query: CompiledQuery, *, as_of_date: date) -> AdapterResult:
        vocabulary = QueryVocabulary.for_query(query)
        try:
            records = self.search_fn(query.query, 50)
        except Exception as exc:
            return AdapterResult(outcome=SearchOutcome.FAILED, error=str(exc))
        hits: list[CandidateHit] = []
        documents: list[SourceDocument] = []
        snapshots: list[str] = []
        for record in records:
            serialized = json.dumps(record, sort_keys=True)
            snapshot_content = json.dumps(record, indent=2, sort_keys=True) + "\n"
            digest = hashlib.sha256(snapshot_content.encode()).hexdigest()
            snapshot_id = f"snapshot:{digest}"
            snapshots.append(snapshot_id)
            path_value: str | None = None
            if self.snapshot_root is not None:
                self.snapshot_root.mkdir(parents=True, exist_ok=True)
                path = self.snapshot_root / f"{digest}.json"
                if not path.exists():
                    path.write_text(snapshot_content)
                path_value = str(path)
            pmid = str(record.get("pmid", ""))
            title = str(record.get("title", ""))
            abstract = str(record.get("abstract", ""))
            text = f"{title} {abstract}".casefold()
            if not all(target.casefold() in text for target in query.target_ids):
                continue
            if not vocabulary.matches_requested_modality(text):
                continue
            document_id = _digest("document", digest)
            documents.append(
                SourceDocument(
                    document_id=document_id,
                    source_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    publisher="PubMed",
                    document_type="publication_abstract",
                    retrieval_date=datetime.now(timezone.utc),
                    content_hash=digest,
                    snapshot_path=path_value,
                    source_tier=SourceTier.PRIMARY,
                )
            )
            if not _matches_follow_up(query, f"{title} {abstract}"):
                continue
            observed_targets = sorted(vocabulary.targets_in(text))
            observed_modality = vocabulary.modality_in(text)
            for asset in extract_observed_asset_names(title, abstract):
                hits.append(
                    CandidateHit(
                        hit_id=_digest("hit", f"{serialized}|{asset}"),
                        source=self.source_name,
                        source_document_id=document_id,
                        query=query.query,
                        asset_name=asset,
                        target_terms=observed_targets,
                        modality_terms=[observed_modality] if observed_modality else [],
                        aliases=[title],
                        snippet=abstract[:500],
                        provisional_identity_key=f"pubmed:{asset.casefold()}",
                        retrieved_at=datetime.now(timezone.utc),
                        applicable_as_of_date=as_of_date,
                    )
                )
        return AdapterResult(
            hits=hits,
            outcome=SearchOutcome.SUCCESS if records else SearchOutcome.NO_EVIDENCE_FOUND,
            snapshot_ids=list(dict.fromkeys(snapshots)),
            source_documents=list({doc.document_id: doc for doc in documents}.values()),
        )


class UnavailableSourceAdapter:
    """Explicitly represent a declared source family that has no configured connector."""

    mandatory = True

    def __init__(self, source_name: str, reason: str = "connector not configured") -> None:
        self.source_name = source_name
        self.reason = reason

    def search(self, query: CompiledQuery, *, as_of_date: date) -> AdapterResult:
        return AdapterResult(outcome=SearchOutcome.FAILED, error=self.reason)


class IndexedDocumentAdapter:
    """Search a declared corpus of company, press, SEC, or conference documents.

    The corpus is intentionally a source index, not an asset universe. It contains documents and
    optional source-provided candidate mentions; the query still filters documents by normalized
    target/modality text and every result retains its document snapshot.
    """

    def __init__(
        self,
        source_name: str,
        documents: Iterable[dict[str, Any]],
        *,
        snapshot_root: Path | None = None,
        mandatory: bool = True,
    ) -> None:
        self.source_name = source_name
        self.mandatory = mandatory
        self.documents = list(documents)
        self.snapshot_root = snapshot_root

    def search(self, query: CompiledQuery, *, as_of_date: date) -> AdapterResult:
        vocabulary = QueryVocabulary.for_query(query)
        hits: list[CandidateHit] = []
        source_documents: list[SourceDocument] = []
        snapshots: list[str] = []
        for record in self.documents:
            text = str(record.get("text", ""))
            title = str(record.get("title", ""))
            observed_targets = vocabulary.targets_in(text)
            if query.target_ids and not set(query.target_ids).issubset(observed_targets):
                continue
            observed_modality = vocabulary.modality_in(text)
            if query.modality_ids and observed_modality not in set(query.modality_ids):
                continue
            if not _matches_follow_up(query, f"{title} {text}"):
                continue
            published = record.get("publication_date")
            if published and str(published)[:10] > as_of_date.isoformat():
                continue
            payload = json.dumps(record, sort_keys=True)
            snapshot_content = json.dumps(record, indent=2, sort_keys=True) + "\n"
            digest = hashlib.sha256(snapshot_content.encode()).hexdigest()
            snapshots.append(f"snapshot:{digest}")
            path_value: str | None = None
            if self.snapshot_root is not None:
                self.snapshot_root.mkdir(parents=True, exist_ok=True)
                path = self.snapshot_root / f"{digest}.json"
                if not path.exists():
                    path.write_text(snapshot_content)
                path_value = str(path)
            document_id = _digest("document", digest)
            source_documents.append(
                SourceDocument(
                    document_id=document_id,
                    source_url=str(record.get("url", "")),
                    publisher=str(record.get("publisher", self.source_name)),
                    document_type=str(record.get("document_type", self.source_name)),
                    retrieval_date=datetime.now(timezone.utc),
                    content_hash=digest,
                    snapshot_path=path_value,
                    source_tier=(
                        SourceTier.PRIMARY
                        if self.source_name in {"sec_edgar", "conference_ash", "conference_asco", "conference_aacr", "conference_eha"}
                        else SourceTier.COMPANY_AUTHORED
                    ),
                )
            )
            mentions = record.get("candidates") or [
                {"asset_name": asset_name}
                for asset_name in extract_observed_asset_names(title, text)
            ]
            for mention in mentions:
                asset_name = str(mention.get("asset_name", "")).strip()
                if (
                    not _plausible_asset_name(asset_name)
                    or _normalized_lookup(asset_name)
                    not in _normalized_lookup(f"{title} {text}")
                ):
                    continue
                hits.append(
                    CandidateHit(
                        hit_id=_digest("hit", f"{payload}|{asset_name}"),
                        source=self.source_name,
                        source_document_id=document_id,
                        query=query.query,
                        asset_name=asset_name,
                        company_name=mention.get("company_name") or record.get("publisher"),
                        trial_id=mention.get("trial_id"),
                        target_terms=sorted(observed_targets),
                        modality_terms=[observed_modality] if observed_modality else [],
                        aliases=list(mention.get("aliases") or []),
                        snippet=text[:500],
                        provisional_identity_key=f"{self.source_name}:{asset_name.casefold()}",
                        retrieved_at=datetime.now(timezone.utc),
                        applicable_as_of_date=as_of_date,
                    )
                )
        return AdapterResult(
            hits=hits,
            outcome=SearchOutcome.SUCCESS if source_documents else SearchOutcome.NO_EVIDENCE_FOUND,
            snapshot_ids=list(dict.fromkeys(snapshots)),
            source_documents=list({doc.document_id: doc for doc in source_documents}.values()),
        )


class UrlDocumentAdapter:
    """Fetch a declared public URL corpus and normalize matching pages into candidate hits."""

    def __init__(
        self,
        source_name: str,
        urls: Iterable[str],
        *,
        fetch_fn: UrlFetch | None = None,
        snapshot_root: Path | None = None,
        mandatory: bool = True,
    ) -> None:
        self.source_name = source_name
        self.urls = list(dict.fromkeys(urls))
        self.fetch_fn = fetch_fn or self._live_fetch
        self.snapshot_root = snapshot_root
        self.mandatory = mandatory

    @staticmethod
    def _live_fetch(url: str) -> dict[str, Any]:
        import requests

        response = requests.get(
            url,
            headers={"User-Agent": "bve-se-search/1.0 research@bve.local"},
            timeout=30,
        )
        response.raise_for_status()
        # Source-specific parsers can replace this generic text extraction later. Keeping the raw
        # response text here preserves the evidence boundary and makes failure visible.
        return {"url": url, "title": url, "text": response.text}

    def search(self, query: CompiledQuery, *, as_of_date: date) -> AdapterResult:
        records: list[dict[str, Any]] = []
        errors: list[str] = []
        for url in self.urls:
            try:
                record = self.fetch_fn(url)
                record.setdefault("url", url)
                records.append(record)
            except Exception as exc:
                errors.append(f"{url}: {exc}")
        indexed = IndexedDocumentAdapter(
            self.source_name,
            records,
            snapshot_root=self.snapshot_root,
            mandatory=self.mandatory,
        )
        result = indexed.search(query, as_of_date=as_of_date)
        if errors:
            result = result.model_copy(
                update={
                    "outcome": SearchOutcome.PARTIAL if result.source_documents else SearchOutcome.FAILED,
                    "error": "; ".join(errors),
                }
            )
        return result
