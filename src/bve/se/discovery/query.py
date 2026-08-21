"""Compile an executable buyer problem into explicit target/modality queries."""

from __future__ import annotations

import hashlib
import warnings
from itertools import product

from bve.se.schemas.contracts import BuyerProblemV2, CompiledQuery, TargetOperator
from bve.se.ontology.modality import modality_query_terms
from bve.se.ontology.targets import resolve_target, target_aliases


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
    return target_aliases(canonical_id)


def _query_id(query: str) -> str:
    return f"query:{hashlib.sha256(query.encode()).hexdigest()[:16]}"


def compile_problem_queries(problem: BuyerProblemV2) -> list[CompiledQuery]:
    """Build deterministic discovery queries without conflating presentation with eligibility."""

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

    target_phrases: list[tuple[str, list[str]]]
    if expression.operator == TargetOperator.ANY:
        target_phrases = [
            (alias, [target.canonical_id])
            for target, aliases in zip(expression.targets, target_alias_groups, strict=True)
            for alias in aliases
        ]
    else:
        target_phrases = [
            (" AND ".join(combination), [target.canonical_id for target in expression.targets])
            for combination in product(*target_alias_groups)
        ]

    queries: list[CompiledQuery] = []
    for target_phrase, target_ids in target_phrases:
        for modality in modalities:
            # Expansion terms are modality-specific: adding "CD3" to a small-molecule
            # query would drag in unrelated T-cell engagers.
            modality_terms = list(dict.fromkeys([modality, *modality_query_terms(modality)]))
            query = f'({target_phrase}) AND ("' + '" OR "'.join(modality_terms) + '")'
            queries.append(
                CompiledQuery(
                    query_id=_query_id(query),
                    query=query,
                    target_ids=target_ids,
                    modality_ids=[modality],
                    aliases=[target_phrase],
                )
            )
    return list({query.query: query for query in queries}.values())
