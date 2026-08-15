"""Compile an executable buyer problem into explicit target/modality queries."""

from __future__ import annotations

import hashlib
from itertools import product

from bve.se.schemas.contracts import BuyerProblemV2, CompiledQuery, TargetOperator
from bve.se.ontology.modality import modality_query_terms
from bve.se.ontology.targets import target_aliases


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
                    *target_aliases(target.canonical_id),
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
