"""Compile an executable buyer problem into explicit target/modality queries."""

from __future__ import annotations

import hashlib
import warnings

from bve.se.discovery.seeding import (
    DEFAULT_MAX_SEEDED_ASSETS,
    SeedProvenance,
    seeded_assets_for_target,
)
from bve.se.schemas.contracts import BuyerProblemV2, CompiledQuery, TargetOperator
from bve.se.ontology.modality import modality_query_terms
from bve.se.discovery.alias_admission import searchable_target_aliases
from bve.se.ontology.targets import resolve_target


class AmbiguousTargetError(ValueError):
    """A declared target names more than one entity, so the query needs clarification.

    Raised rather than warned. When the ontology abstains, searching the string anyway
    is the worst available option: it looks like a normal result while actually being an
    unexpanded literal match on a nickname. The first PDCD1 baseline did exactly that
    for "PD-1" -- one seed term instead of the 216 the canonical id expands to -- and
    reported 233 candidates without a word about the ambiguity.
    """

    def __init__(self, query: str, candidates: tuple[str, ...]) -> None:
        self.query = query
        self.candidates = candidates
        listed = ", ".join(candidates) if candidates else "several entities"
        super().__init__(
            f"target {query!r} is ambiguous in this ontology; it could mean {listed}. "
            "Declare the canonical id you mean -- an ambiguous target may not be "
            "searched literally."
        )


def _ontology_terms(canonical_id: str) -> tuple[str, ...]:
    """Alias spellings for a declared target, refusing when the ontology abstains.

    ``UNRESOLVED`` is allowed through as a literal search with a warning: a genuinely
    novel target has no entry yet, and blocking it would make the ontology a whitelist.
    ``AMBIGUOUS`` is different -- the ontology knows the string and knows it is not
    enough -- so it stops here.
    """

    from bve.se.ontology.resolver import ResolutionStatus

    resolution = resolve_target(canonical_id)
    if resolution is not None:
        if resolution.status is ResolutionStatus.AMBIGUOUS:
            raise AmbiguousTargetError(
                canonical_id,
                tuple(entity.canonical_id for entity in resolution.candidates),
            )
        if resolution.status is ResolutionStatus.UNRESOLVED:
            warnings.warn(
                f"target {canonical_id!r} is not present in the ontology; searching it "
                "literally, with no alias expansion",
                UserWarning,
                stacklevel=3,
            )
    # Aliases this target alone claims, plus any shared alias a probe admitted under the
    # frozen retrieval-admission policy. A shared alias does not automatically widen the
    # search -- it can redirect it, as "NET" did when it filled the SLC6A2 corpus with
    # neutrophil-extracellular-trap trials -- but refusing all of them would cost PDCD1
    # the name nearly every PDCD1 document uses. Which is which is measured, not declared.
    return searchable_target_aliases(canonical_id)


def _query_id(query: str) -> str:
    return f"query:{hashlib.sha256(query.encode()).hexdigest()[:16]}"


def compile_problem_queries(
    problem: BuyerProblemV2, *, max_seeded_assets: int = DEFAULT_MAX_SEEDED_ASSETS
) -> list[CompiledQuery]:
    """Build deterministic discovery queries without conflating presentation with eligibility.

    Emits three kinds of query, all from declared inputs and none target-specific:
    the target vocabulary alone, the target vocabulary AND each requested modality, and
    one query per asset the drug->target authority associates with a declared target.
    """

    expression = problem.strategic_gap.target_expression
    modalities = problem.strategic_gap.modalities
    target_alias_groups = [
        list(
            dict.fromkeys(
                [
                    target.canonical_id,
                    target.label,
                    *target.aliases,
                    *_ontology_terms(target.canonical_id),
                ]
            )
        )
        for target in expression.targets
    ]

    # Aliases are alternative spellings of one thing, so they belong in an OR group
    # inside a single query -- not in a query each. Emitting one query per alias
    # multiplied the PDCD1 plan to 255 searches that resolved to 17 distinct ones
    # repeated 15 times, because retrieval re-expands the canonical id to the same
    # alias set regardless of which spelling the query was named after. 240 of the
    # 255 contributed no trial the plan had not already seen.
    def _or(aliases: list[str]) -> str:
        return "(" + " OR ".join(f'"{alias}"' for alias in aliases) + ")"

    target_phrases: list[tuple[str, list[str], list[str]]]
    if expression.operator == TargetOperator.ANY:
        target_phrases = [
            (_or(aliases), [target.canonical_id], aliases)
            for target, aliases in zip(expression.targets, target_alias_groups, strict=True)
        ]
    else:
        # ALL means every target must appear, so the groups are AND-ed. The old
        # cartesian product over alias groups was the same redundancy raised to the
        # number of targets.
        target_phrases = [
            (
                " AND ".join(_or(aliases) for aliases in target_alias_groups),
                [target.canonical_id for target in expression.targets],
                [alias for aliases in target_alias_groups for alias in aliases],
            )
        ]

    queries: list[CompiledQuery] = []
    for target_phrase, target_ids, phrase_aliases in target_phrases:
        # The target vocabulary on its own, before any modality is AND-ed to it. The
        # conjunct used to be the only form issued, which made the modality vocabulary a
        # filter on retrieval rather than a preference over results: every one of the 17
        # modality queries in the SLC6A2 run returned zero records, because registry
        # entries for small molecules describe a drug and an indication and never say
        # "kinase inhibitor". A buyer who wants antibodies is expressing what they would
        # like to buy, not claiming that documents about other modalities do not exist.
        queries.append(
            CompiledQuery(
                query_id=_query_id(target_phrase),
                query=target_phrase,
                target_ids=target_ids,
                modality_ids=[],
                aliases=list(phrase_aliases),
                seed_provenance=SeedProvenance.TARGET_VOCABULARY,
            )
        )
        for modality in modalities:
            # Expansion terms are modality-specific: adding "CD3" to a small-molecule
            # query would drag in unrelated T-cell engagers.
            modality_terms = list(dict.fromkeys([modality, *modality_query_terms(modality)]))
            query = f'{target_phrase} AND ("' + '" OR "'.join(modality_terms) + '")'
            queries.append(
                CompiledQuery(
                    query_id=_query_id(query),
                    query=query,
                    target_ids=target_ids,
                    modality_ids=[modality],
                    aliases=list(phrase_aliases),
                    seed_provenance=SeedProvenance.TARGET_VOCABULARY,
                )
            )

    queries.extend(_seeded_asset_queries(expression, max_seeded_assets))
    return list({query.query: query for query in queries}.values())


def _seeded_asset_queries(expression, max_seeded_assets: int) -> list[CompiledQuery]:
    """One query per asset the drug->target authority associates with a declared target.

    This is the ``target -> known assets -> documents`` direction. It exists because the
    other direction silently requires documents about an asset to name the asset's
    target, which is a property of immuno-oncology rather than of biology.

    Each query searches only the drug's own names, so what comes back is evidence about
    that drug from the ordinary sources -- not the authority's claim restated. The
    ``seed_provenance`` stamp is what keeps the two distinguishable downstream.
    """

    queries: list[CompiledQuery] = []
    for target in expression.targets:
        seeds, _known = seeded_assets_for_target(
            target.canonical_id, limit=max_seeded_assets
        )
        for drug_id, names in seeds:
            query = "(" + " OR ".join(f'"{name}"' for name in names) + ")"
            queries.append(
                CompiledQuery(
                    query_id=_query_id(query),
                    query=query,
                    target_ids=[target.canonical_id],
                    modality_ids=[],
                    aliases=list(names),
                    seed_provenance=SeedProvenance.AUTHORITY_SEEDED_ASSET,
                    seed_drug_id=drug_id,
                )
            )
    return queries
