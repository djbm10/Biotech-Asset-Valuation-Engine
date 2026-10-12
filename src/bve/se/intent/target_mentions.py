"""Decision-neutral authority mentions. This module never emits target requirements.

The caller supplies the existing production intent. Geometry and observed production
roles are provenance, not independent role or ownership certificates.
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from itertools import combinations
from typing import Literal

from pydantic import Field

from bve.se.intent.intent import SearchIntent
from bve.se.intent.parser import _clean, _strip_target_affixes, _tokenize
from bve.se.ontology.records import AliasType, SourceAlias, normalize_lookup_key
from bve.se.ontology.resolver import BiomedicalEntityResolver
from bve.se.ontology.targets import get_resolver, ontology_version
from bve.se.schemas.contracts import StrictModel


class MentionRole(str, Enum):
    TARGET_CANDIDATE = "TARGET_CANDIDATE"
    TARGET_ROLE_CONFIRMED = "TARGET_ROLE_CONFIRMED"
    EMBEDDED_BIOLOGICAL_MENTION = "EMBEDDED_BIOLOGICAL_MENTION"
    CONTEXTUAL_BIOLOGICAL_MENTION = "CONTEXTUAL_BIOLOGICAL_MENTION"
    AMBIGUOUS_ROLE = "AMBIGUOUS_ROLE"
    NON_TARGET_ROLE = "NON_TARGET_ROLE"


class AliasAssertion(StrictModel):
    record_key: str
    value: str
    alias_type: str


class MentionAuthorityEvidence(StrictModel):
    entity_id: str
    matching_aliases: list[AliasAssertion]
    source_record_keys: list[str]
    canonical_symbols: list[str]
    ensembl_ids: list[str]
    identifier_edges: list[str]
    basis: Literal["SOURCE_ALIAS", "CANONICAL_ID"]


class ProductionSpanObservation(StrictModel):
    span_index: int
    start: int
    end: int
    kind: str
    lookup_text: str
    resolved_to: str | None
    entity_id: str | None
    rule: str
    candidates: list[str]


class TargetMentionRole(StrictModel):
    mention_id: str
    start: int
    end: int
    surface: str
    lookup_text: str
    lookup_origins: list[str]
    status: str
    canonical_id: str | None
    claimant_ids: list[str]
    candidates: list[str]
    resolver_rule: str
    authority_evidence: list[MentionAuthorityEvidence]
    identity_conflicts: list[str]
    ownership: Literal["UNADJUDICATED"] = "UNADJUDICATED"
    role: MentionRole = MentionRole.TARGET_CANDIDATE
    role_evidence: list[str] = Field(default_factory=list)
    containing_mentions: list[str] = Field(default_factory=list)
    decision_bindings: list[int] = Field(default_factory=list)
    currently_decision_bearing: bool = False


class MentionSpanRelation(StrictModel):
    left: str
    right: str
    kind: Literal["CONTAINS", "CONTAINED", "OVERLAPPING", "EQUIVALENT", "INDEPENDENT"]


class TargetMentionAnalysis(StrictModel):
    representation_version: str = "target_mention_role_v1"
    original_query: str
    intent_ontology_version: str
    ontology_version: str | None
    source_status: Literal["AVAILABLE", "UNAVAILABLE"]
    production_observations: list[ProductionSpanObservation]
    mentions: list[TargetMentionRole] = Field(default_factory=list)
    relations: list[MentionSpanRelation] = Field(default_factory=list)


def _observations(intent: SearchIntent) -> list[ProductionSpanObservation]:
    return [
        ProductionSpanObservation(
            span_index=i,
            start=s.start,
            end=s.end,
            kind=s.kind.value,
            lookup_text=s.text,
            resolved_to=s.resolved_to,
            entity_id=s.target_reference.entity_id if s.target_reference else None,
            rule=s.rule,
            candidates=sorted(s.candidates),
        )
        for i, s in enumerate(intent.spans)
    ]


def _intervals(query: str, observations: list[ProductionSpanObservation]):
    # No new character-substring heuristic: only original/adopted lexical boundaries.
    found: dict[tuple[int, int, str], dict[str, set[str]]] = {}

    def add(start: int, end: int, text: str, origin: str):
        if start >= end or not text.strip():
            return
        key = (start, end, normalize_lookup_key(text))
        entry = found.setdefault(key, {"texts": set(), "origins": set()})
        entry["texts"].add(text)
        entry["origins"].add(origin)

    for view_name, view in [
        ("original", query),
        ("adopted_affix_view", _strip_target_affixes(query)),
    ]:
        streams = [
            [(m.group(), m.start(), m.end()) for m in re.finditer(r"\S+", view)],
            _tokenize(view),
        ]
        for stream in streams:
            starts = set()
            ends = set()
            for token, start, end in stream:
                starts.add(start)
                ends.add(end)
                cleaned = _clean(token)
                if cleaned:
                    clean_start = start + token.find(cleaned)
                    starts.add(clean_start)
                    ends.add(clean_start + len(cleaned))
            for start in sorted(starts):
                for end in sorted(ends):
                    if start < end:
                        add(start, end, query[start:end], view_name)
    for s in observations:
        if s.kind in {"TARGET", "AMBIGUOUS_TARGET"}:
            add(s.start, s.end, s.lookup_text, "observed_production_lookup")
    for (start, end, _), values in sorted(found.items()):
        texts = sorted(values["texts"], key=lambda s: (s != query[start:end], s))
        yield start, end, texts[0], sorted(values["origins"])


def _evidence(
    resolver: BiomedicalEntityResolver, entity_id: str, text: str
) -> MentionAuthorityEvidence:
    entity = resolver.get(entity_id)
    assert entity is not None
    key = normalize_lookup_key(text)
    assertions: set[tuple[str, str, str]] = set()
    genes = set()
    for record in entity.source_records:
        aliases = list(record.aliases)
        if record.canonical_symbol:
            aliases.append(SourceAlias(value=record.canonical_symbol, alias_type=AliasType.SYMBOL))
        if record.label:
            aliases.append(SourceAlias(value=record.label, alias_type=AliasType.APPROVED_NAME))
        for alias in aliases:
            if normalize_lookup_key(alias.value) == key:
                assertions.add((record.record_key, alias.value, alias.alias_type.value))
        genes.update(record.xrefs.get("ensembl", []))
        if record.source == "open_targets" and record.source_id.startswith("ENSG"):
            genes.add(record.source_id)
    return MentionAuthorityEvidence(
        entity_id=entity_id,
        matching_aliases=[
            AliasAssertion(record_key=r, value=v, alias_type=t) for r, v, t in sorted(assertions)
        ],
        source_record_keys=sorted({r.record_key for r in entity.source_records}),
        canonical_symbols=sorted(
            {r.canonical_symbol for r in entity.source_records if r.canonical_symbol}
        ),
        ensembl_ids=sorted(genes),
        identifier_edges=sorted(entity.identifier_edges),
        basis="CANONICAL_ID" if key == normalize_lookup_key(entity_id) else "SOURCE_ALIAS",
    )


def _relation(a: TargetMentionRole, b: TargetMentionRole) -> str:
    if (a.start, a.end) == (b.start, b.end):
        return "EQUIVALENT"  # Same text extent only; no biological equivalence claim.
    if a.start <= b.start and b.end <= a.end:
        return "CONTAINS"
    if b.start <= a.start and a.end <= b.end:
        return "CONTAINED"
    if a.start < b.end and b.start < a.end:
        return "OVERLAPPING"
    return "INDEPENDENT"


def analyze_target_mentions(intent: SearchIntent) -> TargetMentionAnalysis:
    """Read-only sidecar. No returned mention is consumed by the production compiler.

    No role confirmations are synthesized from existing selections. The current
    production path alone determines ``currently_decision_bearing``.
    """
    observations = _observations(intent)
    resolver = get_resolver()
    result = TargetMentionAnalysis(
        original_query=intent.original_query,
        intent_ontology_version=intent.ontology_version,
        ontology_version=resolver.ontology_version if resolver else None,
        source_status="AVAILABLE" if resolver else "UNAVAILABLE",
        production_observations=observations,
    )
    if resolver is None:
        return result
    if intent.ontology_version != ontology_version():
        raise ValueError("intent snapshot differs from installed authority snapshot")
    cache = {}
    for start, end, text, origins in _intervals(intent.original_query, observations):
        lookup_key = normalize_lookup_key(text)
        if lookup_key not in cache:
            resolution = resolver.resolve(text)
            claimants = list(resolver.claimants_of(text))
            entity_ids = set(claimants) | {c.canonical_id for c in resolution.candidates}
            if resolution.canonical_id:
                entity_ids.add(resolution.canonical_id)
            evidence = [_evidence(resolver, e, text) for e in sorted(entity_ids)]
            cache[lookup_key] = (resolution, claimants, evidence)
        resolution, claimants, evidence = cache[lookup_key]
        if resolution.status.value == "UNRESOLVED" and not claimants:
            continue
        conflicts = []
        if resolution.status.value == "AMBIGUOUS":
            conflicts.append("ambiguous_authority_identity")
        for e in evidence:
            if len({s.casefold() for s in e.canonical_symbols}) > 1:
                conflicts.append("multiple_source_symbols:" + e.entity_id)
            if len(e.ensembl_ids) > 1:
                conflicts.append("multiple_source_genes:" + e.entity_id)
        identity = [intent.original_query, resolver.ontology_version, start, end, lookup_key]
        mention = TargetMentionRole(
            mention_id="mention_"
            + hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest(),
            start=start,
            end=end,
            surface=intent.original_query[start:end],
            lookup_text=text,
            lookup_origins=origins,
            status=resolution.status.value,
            canonical_id=resolution.canonical_id,
            claimant_ids=claimants,
            candidates=sorted(c.canonical_id for c in resolution.candidates),
            resolver_rule=resolution.rule,
            authority_evidence=[e.model_copy(deep=True) for e in evidence],
            identity_conflicts=sorted(conflicts),
        )
        for s in observations:
            if s.start == start and s.end == end and s.kind in {"TARGET", "AMBIGUOUS_TARGET"}:
                mention.decision_bindings.append(s.span_index)
                if s.kind == "TARGET" and resolution.canonical_id is not None:
                    # Older supplied intents may lack the additive identity reference.
                    selected_id = s.entity_id or (
                        "TARGET:" + s.resolved_to if s.resolved_to else None
                    )
                    if selected_id == resolution.canonical_id:
                        mention.currently_decision_bearing = True
        result.mentions.append(mention)
    crossing = set()
    by_id = {m.mention_id: m for m in result.mentions}
    for a, b in combinations(result.mentions, 2):
        relation = _relation(a, b)
        result.relations.append(
            MentionSpanRelation(left=a.mention_id, right=b.mention_id, kind=relation)
        )
        if relation == "CONTAINS":
            b.containing_mentions.append(a.mention_id)
        elif relation == "CONTAINED":
            a.containing_mentions.append(b.mention_id)
        elif relation == "OVERLAPPING":
            crossing.update((a.mention_id, b.mention_id))
    for m in result.mentions:
        m.containing_mentions.sort()
        contextual = [
            s.span_index
            for s in observations
            if s.kind not in {"TARGET", "AMBIGUOUS_TARGET", "RESIDUAL"}
            and s.start < m.end
            and m.start < s.end
        ]
        if m.containing_mentions:
            m.role = MentionRole.EMBEDDED_BIOLOGICAL_MENTION
            m.role_evidence = [
                "geometrically_contained; independent_role_unconfirmed"
            ] + m.containing_mentions
        elif m.mention_id in crossing:
            m.role = MentionRole.AMBIGUOUS_ROLE
            m.role_evidence = ["crossing_authority_intervals; ownership_unadjudicated"]
        elif contextual:
            m.role = MentionRole.CONTEXTUAL_BIOLOGICAL_MENTION
            m.role_evidence = ["observed_non_target_production_claim; not_a_role_certificate"] + [
                f"production_span:{i}" for i in contextual
            ]
        else:
            m.role_evidence = ["authority_candidate; therapeutic_role_unconfirmed"]
        assert all(parent in by_id for parent in m.containing_mentions)
    return result
