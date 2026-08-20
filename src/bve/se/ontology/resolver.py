"""Target-agnostic biomedical entity resolution over a versioned ontology snapshot.

The resolver groups source records into canonical entities using cross-reference join
keys (never string similarity), elects a canonical symbol under a declared source
authority order, and reports every disagreement it had to work around rather than
hiding it. A lookup string that legitimately points at more than one entity resolves
to ``AMBIGUOUS`` instead of guessing.
"""

from __future__ import annotations

from collections import defaultdict
from enum import Enum

from pydantic import Field

from bve.se.ontology.records import (
    AliasType,
    EntityType,
    SourceAlias,
    SourceEntityRecord,
    normalize_lookup_key,
)
from bve.se.ontology.snapshot import OntologySnapshot
from bve.se.schemas.contracts import StrictModel

#: Cross-reference namespaces used to decide that two source records describe the
#: same real-world entity. Deliberately identifier-based: no name matching.
JOIN_NAMESPACES: dict[EntityType, tuple[str, ...]] = {
    EntityType.TARGET: ("uniprot", "ensembl", "hgnc"),
    EntityType.DRUG: ("chembl", "inchikey", "unii"),
    EntityType.DISEASE: ("efo", "mondo", "meddra"),
}

#: Which source's ``canonical_symbol`` wins when sources disagree. Disagreement is
#: still recorded as a conflict; this only decides what the normalized view shows.
SYMBOL_AUTHORITY: dict[EntityType, tuple[str, ...]] = {
    EntityType.TARGET: ("open_targets", "chembl"),
    EntityType.DRUG: ("chembl", "open_targets"),
    EntityType.DISEASE: ("open_targets",),
}

#: Alias specificity, most specific first. Used only to break lookup ties, never to
#: choose between sources.
_ALIAS_PRECEDENCE: tuple[AliasType, ...] = (
    AliasType.SYMBOL,
    AliasType.APPROVED_NAME,
    AliasType.DEVELOPMENT_CODE,
    AliasType.TRADE_NAME,
    AliasType.SYNONYM,
    AliasType.XREF,
    AliasType.DESCRIPTION,
)


class ResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"


class ConflictType(str, Enum):
    CANONICAL_SYMBOL_DISAGREEMENT = "CANONICAL_SYMBOL_DISAGREEMENT"
    ALIAS_SHARED_ACROSS_ENTITIES = "ALIAS_SHARED_ACROSS_ENTITIES"


class ConflictFlag(StrictModel):
    """A disagreement the resolver preserved instead of resolving silently."""

    conflict_type: ConflictType
    detail: str
    #: ``source:source_id`` keys of the records involved.
    record_keys: list[str] = Field(default_factory=list)
    values: list[str] = Field(default_factory=list)


class AliasWithProvenance(StrictModel):
    """An alias plus every source record that asserted it."""

    value: str
    alias_type: AliasType
    sources: list[str] = Field(default_factory=list)
    record_keys: list[str] = Field(default_factory=list)

    @property
    def is_queryable(self) -> bool:
        return SourceAlias(value=self.value, alias_type=self.alias_type).is_queryable


class ResolutionBasis(StrictModel):
    """Why a lookup string resolved to the entity it did.

    Answers "why did you interpret my query this way?" without the caller having to
    re-derive anything: the alias that matched, who asserted it, and the identifier
    edges that merged the underlying source records into one entity.
    """

    observed_query: str
    matched_alias: str
    matched_alias_type: AliasType
    #: Sources that asserted ``matched_alias`` for this entity.
    asserted_by: list[str] = Field(default_factory=list)
    asserting_record_keys: list[str] = Field(default_factory=list)
    #: ``namespace:value`` identifiers shared by two or more source records -- the
    #: edges that caused the merge. Empty when the entity came from a single record.
    identifier_edges: list[str] = Field(default_factory=list)
    rule: str

    def explain(self, canonical_symbol: str | None) -> str:
        """A one-line, human-readable derivation, e.g. for a shortlist footnote."""

        target = canonical_symbol or "?"
        steps = [
            f"{self.observed_query!r}",
            f"{self.matched_alias_type.value.lower()} alias {self.matched_alias!r}"
            + (f" asserted by {', '.join(self.asserted_by)}" if self.asserted_by else ""),
            target,
        ]
        if self.identifier_edges:
            steps.append("merged on " + ", ".join(self.identifier_edges))
        return " -> ".join(steps)


class CanonicalEntity(StrictModel):
    """The normalized view of one entity, with its source records kept underneath."""

    canonical_id: str
    entity_type: EntityType
    canonical_symbol: str | None = None
    label: str | None = None
    aliases: list[AliasWithProvenance] = Field(default_factory=list)
    source_records: list[SourceEntityRecord] = Field(default_factory=list)
    conflicts: list[ConflictFlag] = Field(default_factory=list)
    #: ``namespace:value`` identifiers shared by two or more source records.
    identifier_edges: list[str] = Field(default_factory=list)

    @property
    def contributing_sources(self) -> tuple[str, ...]:
        return tuple(sorted({record.source for record in self.source_records}))

    def queryable_aliases(self) -> tuple[str, ...]:
        """Alias strings specific enough to expand into a literal search query."""

        return tuple(alias.value for alias in self.aliases if alias.is_queryable)


class ResolutionResult(StrictModel):
    """The outcome of resolving one lookup string."""

    query: str
    status: ResolutionStatus
    entity: CanonicalEntity | None = None
    #: Populated when ``status`` is ``AMBIGUOUS``: every entity the string could mean.
    candidates: list[CanonicalEntity] = Field(default_factory=list)
    #: Which rule produced the outcome, for audit trails.
    rule: str | None = None
    #: Present whenever ``status`` is ``RESOLVED``: the full derivation.
    basis: ResolutionBasis | None = None
    ontology_version: str | None = None

    @property
    def canonical_id(self) -> str | None:
        return self.entity.canonical_id if self.entity else None

    @property
    def canonical_symbol(self) -> str | None:
        return self.entity.canonical_symbol if self.entity else None


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def add(self, key: str) -> None:
        self._parent.setdefault(key, key)

    def find(self, key: str) -> str:
        self.add(key)
        root = key
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[key] != root:
            self._parent[key], key = root, self._parent[key]
        return root

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            # Keep the lexicographically smaller root so grouping is deterministic.
            low, high = sorted((left_root, right_root))
            self._parent[high] = low


class BiomedicalEntityResolver:
    """Resolve free-text biomedical strings to canonical entities.

    Built from an :class:`~bve.se.ontology.snapshot.OntologySnapshot`; holds no
    hard-coded entity knowledge of its own, so it generalizes to any target present
    in the snapshot.
    """

    def __init__(self, snapshot: OntologySnapshot) -> None:
        self._snapshot = snapshot
        self._entities: dict[str, CanonicalEntity] = {}
        self._by_type: dict[EntityType, list[CanonicalEntity]] = defaultdict(list)
        self._lookup: dict[tuple[EntityType, str], list[tuple[AliasType, str]]] = defaultdict(list)
        self._build()

    # -- construction ---------------------------------------------------------

    def _build(self) -> None:
        for entity_type in EntityType:
            records = self._snapshot.records_for(entity_type)
            if not records:
                continue
            for group in self._group_records(records, entity_type):
                entity = self._build_entity(group, entity_type)
                self._entities[entity.canonical_id] = entity
                self._by_type[entity_type].append(entity)
                self._index(entity)
        self._flag_shared_aliases()

    def _group_records(
        self, records: tuple[SourceEntityRecord, ...], entity_type: EntityType
    ) -> list[list[SourceEntityRecord]]:
        """Cluster records that share at least one cross-reference identifier."""

        union = _UnionFind()
        by_key: dict[str, SourceEntityRecord] = {}
        for record in records:
            union.add(record.record_key)
            by_key[record.record_key] = record

        seen_join_keys: dict[str, str] = {}
        for record in records:
            for namespace in JOIN_NAMESPACES.get(entity_type, ()):
                for value in record.join_keys(namespace):
                    token = f"{namespace}:{value}"
                    if token in seen_join_keys:
                        union.union(seen_join_keys[token], record.record_key)
                    else:
                        seen_join_keys[token] = record.record_key

        grouped: dict[str, list[SourceEntityRecord]] = defaultdict(list)
        for key, record in by_key.items():
            grouped[union.find(key)].append(record)
        return [sorted(group, key=lambda item: item.record_key) for group in grouped.values()]

    def _build_entity(self, group: list[SourceEntityRecord], entity_type: EntityType) -> CanonicalEntity:
        conflicts: list[ConflictFlag] = []
        symbol = self._elect_symbol(group, entity_type, conflicts)
        label = next((record.label for record in group if record.label), None)

        merged: dict[tuple[str, AliasType], AliasWithProvenance] = {}
        for record in group:
            for alias in record.all_aliases():
                key = (alias.normalized, alias.alias_type)
                existing = merged.get(key)
                if existing is None:
                    merged[key] = AliasWithProvenance(
                        value=alias.value,
                        alias_type=alias.alias_type,
                        sources=[record.source],
                        record_keys=[record.record_key],
                    )
                    continue
                if record.source not in existing.sources:
                    existing.sources = [*existing.sources, record.source]
                existing.record_keys = [*existing.record_keys, record.record_key]

        canonical_id = self._canonical_id(symbol, group, entity_type)
        aliases = sorted(
            merged.values(),
            key=lambda alias: (_ALIAS_PRECEDENCE.index(alias.alias_type), alias.value.casefold()),
        )
        return CanonicalEntity(
            canonical_id=canonical_id,
            entity_type=entity_type,
            canonical_symbol=symbol,
            label=label,
            aliases=aliases,
            source_records=group,
            conflicts=conflicts,
            identifier_edges=self._identifier_edges(group, entity_type),
        )

    @staticmethod
    def _identifier_edges(group: list[SourceEntityRecord], entity_type: EntityType) -> list[str]:
        """The ``namespace:value`` identifiers that actually merged these records."""

        counts: dict[str, int] = defaultdict(int)
        for record in group:
            for namespace in JOIN_NAMESPACES.get(entity_type, ()):
                for value in record.join_keys(namespace):
                    counts[f"{namespace}:{value}"] += 1
        return sorted(token for token, count in counts.items() if count > 1)

    @staticmethod
    def _elect_symbol(
        group: list[SourceEntityRecord], entity_type: EntityType, conflicts: list[ConflictFlag]
    ) -> str | None:
        by_source: dict[str, str] = {}
        for record in group:
            if record.canonical_symbol and record.source not in by_source:
                by_source[record.source] = record.canonical_symbol
        if not by_source:
            return None

        distinct = {symbol.upper() for symbol in by_source.values()}
        if len(distinct) > 1:
            conflicts.append(
                ConflictFlag(
                    conflict_type=ConflictType.CANONICAL_SYMBOL_DISAGREEMENT,
                    detail=(
                        "sources disagree on the canonical symbol; the authority order "
                        f"{SYMBOL_AUTHORITY.get(entity_type, ())} decided the normalized value"
                    ),
                    record_keys=sorted(record.record_key for record in group),
                    values=sorted(distinct),
                )
            )

        for source in SYMBOL_AUTHORITY.get(entity_type, ()):
            if source in by_source:
                return by_source[source]
        return by_source[sorted(by_source)[0]]

    @staticmethod
    def _canonical_id(symbol: str | None, group: list[SourceEntityRecord], entity_type: EntityType) -> str:
        if symbol:
            return f"{entity_type.value}:{symbol.upper()}"
        for namespace in JOIN_NAMESPACES.get(entity_type, ()):
            for record in group:
                keys = record.join_keys(namespace)
                if keys:
                    return f"{entity_type.value}:{namespace}:{keys[0]}"
        return f"{entity_type.value}:{group[0].record_key}"

    def _index(self, entity: CanonicalEntity) -> None:
        for alias in entity.aliases:
            key = (entity.entity_type, normalize_lookup_key(alias.value))
            self._lookup[key].append((alias.alias_type, entity.canonical_id))
        # Canonical IDs are always directly addressable.
        self._lookup[(entity.entity_type, normalize_lookup_key(entity.canonical_id))].append(
            (AliasType.SYMBOL, entity.canonical_id)
        )

    def _flag_shared_aliases(self) -> None:
        """Record, on each affected entity, aliases that are not entity-unique."""

        # Bulk data shares some aliases very widely -- Open Targets gives "novel
        # transcript" to tens of thousands of genes. Sorting the id set once per
        # alias rather than once per sharer, and appending to a per-entity list
        # rather than rebuilding each entity's list, keeps this linear in the size
        # of the sharing group instead of quadratic.
        pending: dict[str, list[ConflictFlag]] = defaultdict(list)
        for (entity_type, key), hits in self._lookup.items():
            # Classification identifiers are shared by design -- every enzyme in a
            # class carries the same EC number -- so sharing one is not a conflict.
            entity_ids = {
                canonical_id
                for alias_type, canonical_id in hits
                if alias_type not in {AliasType.XREF, AliasType.DESCRIPTION}
            }
            if len(entity_ids) < 2:
                continue
            values = sorted(entity_ids)
            flag = ConflictFlag(
                conflict_type=ConflictType.ALIAS_SHARED_ACROSS_ENTITIES,
                detail=(
                    f"the {entity_type.value.lower()} alias {key!r} is also used by "
                    "another entity in this snapshot"
                ),
                values=values,
            )
            for canonical_id in values:
                pending[canonical_id].append(flag)

        for canonical_id, flags in pending.items():
            entity = self._entities[canonical_id]
            entity.conflicts = [*entity.conflicts, *flags]

    # -- public API -----------------------------------------------------------

    @property
    def ontology_version(self) -> str:
        return self._snapshot.ontology_version

    @property
    def snapshot(self) -> OntologySnapshot:
        return self._snapshot

    def entities_of_type(self, entity_type: EntityType) -> tuple[CanonicalEntity, ...]:
        """Every canonical entity of one type, for callers that must label without a query.

        Corpus indexing happens before any query exists, so it needs the whole vocabulary
        rather than one query's slice. Ordered by canonical id so indexing is deterministic.
        """

        return tuple(
            sorted(self._by_type.get(entity_type, ()), key=lambda entity: entity.canonical_id)
        )

    def resolve(self, query: str, entity_type: EntityType = EntityType.TARGET) -> ResolutionResult:
        """Resolve one lookup string, refusing to guess between real homonyms."""

        key = normalize_lookup_key(query)
        hits = self._lookup.get((entity_type, key), [])
        if not hits:
            return ResolutionResult(
                query=query,
                status=ResolutionStatus.UNRESOLVED,
                rule="no_alias_match",
                ontology_version=self.ontology_version,
            )

        entity_ids = {canonical_id for _, canonical_id in hits}
        if len(entity_ids) == 1:
            return self._resolved(query, next(iter(entity_ids)), key, "unique_alias_match")

        # Homonym: prefer the entity for which this string is the most specific kind
        # of alias, but only when that leaves exactly one candidate.
        best_rank = min(_ALIAS_PRECEDENCE.index(alias_type) for alias_type, _ in hits)
        best = {canonical_id for alias_type, canonical_id in hits if _ALIAS_PRECEDENCE.index(alias_type) == best_rank}
        if len(best) == 1:
            return self._resolved(
                query,
                next(iter(best)),
                key,
                f"alias_type_precedence:{_ALIAS_PRECEDENCE[best_rank].value}",
            )

        return ResolutionResult(
            query=query,
            status=ResolutionStatus.AMBIGUOUS,
            candidates=[self._entities[canonical_id] for canonical_id in sorted(entity_ids)],
            rule="homonym_requires_escalation",
            ontology_version=self.ontology_version,
        )

    def _resolved(self, query: str, canonical_id: str, lookup_key: str, rule: str) -> ResolutionResult:
        """Build a RESOLVED result carrying the derivation that produced it."""

        entity = self._entities[canonical_id]
        matched = next(
            (alias for alias in entity.aliases if normalize_lookup_key(alias.value) == lookup_key),
            None,
        )
        if matched is None:
            # The lookup key was the canonical ID itself, which is indexed directly.
            basis = ResolutionBasis(
                observed_query=query,
                matched_alias=entity.canonical_id,
                matched_alias_type=AliasType.SYMBOL,
                identifier_edges=entity.identifier_edges,
                rule=rule,
            )
        else:
            basis = ResolutionBasis(
                observed_query=query,
                matched_alias=matched.value,
                matched_alias_type=matched.alias_type,
                # Sorted so the derivation is stable regardless of record ordering.
                asserted_by=sorted(matched.sources),
                asserting_record_keys=sorted(dict.fromkeys(matched.record_keys)),
                identifier_edges=entity.identifier_edges,
                rule=rule,
            )
        return ResolutionResult(
            query=query,
            status=ResolutionStatus.RESOLVED,
            entity=entity,
            rule=rule,
            basis=basis,
            ontology_version=self.ontology_version,
        )

    def get(self, canonical_id: str, entity_type: EntityType = EntityType.TARGET) -> CanonicalEntity | None:
        """Fetch an entity by canonical ID, or by symbol as a convenience."""

        entity = self._entities.get(canonical_id)
        if entity is not None:
            return entity
        result = self.resolve(canonical_id, entity_type)
        return result.entity

    def aliases_for(self, canonical_id: str, entity_type: EntityType = EntityType.TARGET) -> tuple[str, ...]:
        """Queryable alias strings for an entity; empty when it is not in the snapshot.

        This is the seam the discovery query compiler and acquisition runner use, and
        it returns ``()`` rather than raising so an unknown target degrades to the
        caller's own declared aliases instead of failing the run.
        """

        entity = self.get(canonical_id, entity_type)
        return entity.queryable_aliases() if entity else ()

    def entities(self, entity_type: EntityType = EntityType.TARGET) -> tuple[CanonicalEntity, ...]:
        return tuple(sorted(self._by_type.get(entity_type, []), key=lambda item: item.canonical_id))
