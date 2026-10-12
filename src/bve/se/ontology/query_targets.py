"""Authority-backed Greek spelling for queries, without new biological identity joins."""
from __future__ import annotations

import re
from functools import lru_cache

from bve.se.ontology.records import AliasType, EntityType, normalize_lookup_key
from bve.se.ontology.resolver import (
    AliasWithProvenance, BiomedicalEntityResolver, CanonicalEntity,
    ResolutionBasis, ResolutionResult, ResolutionStatus,
)
from bve.se.ontology.targets import get_resolver, resolve_target

RULE = 'target_query_greek_orthography_v2'
_GREEK = 'αβγδεζηθικλμνξοπρστυφχψω'
_NAMES = ('alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi '
          'omicron pi rho sigma tau upsilon phi chi psi omega').split()
_WORDS = dict(zip(_NAMES, _GREEK, strict=True))
_SUPPORTED = frozenset(_GREEK + _GREEK.upper())
_ENGLISH = re.compile(r'(?<![a-z])(' + '|'.join(_NAMES) + r')(?![a-z])')
_TYPES = frozenset({AliasType.SYMBOL, AliasType.APPROVED_NAME, AliasType.SYNONYM})


def _key(value: str) -> str:
    text = _ENGLISH.sub(lambda m: _WORDS[m.group()], normalize_lookup_key(value))
    return ' '.join(''.join(f' {c} ' if c in _GREEK else c for c in text).split())


def _single_gene(entity: CanonicalEntity) -> bool:
    symbols = {r.canonical_symbol.casefold() for r in entity.source_records if r.canonical_symbol}
    genes = {gene for r in entity.source_records for gene in r.xrefs.get('ensembl', [])}
    return (len(symbols) == len(genes) == 1
            and bool(entity.canonical_symbol)
            and symbols == {entity.canonical_symbol.casefold()}
            and any(r.source == 'open_targets' and r.source_id in genes
                    for r in entity.source_records))


@lru_cache(maxsize=4)
def _claims(resolver: BiomedicalEntityResolver) -> dict[str, tuple[tuple[str, AliasWithProvenance], ...]]:
    pending: dict[str, list[tuple[str, AliasWithProvenance]]] = {}
    for entity in resolver.entities_of_type(EntityType.TARGET):
        for alias in entity.aliases:
            if alias.alias_type not in _TYPES:
                continue
            key = _key(alias.value)
            if any(c in _GREEK for c in key):
                pending.setdefault(key, []).append((entity.canonical_id, alias))
    return {key: tuple(sorted(items, key=lambda pair: (
        pair[0], pair[1].alias_type.value, pair[1].value.casefold(), pair[1].value)))
        for key, items in pending.items()}


def resolve_query_target(value: str) -> ResolutionResult | None:
    """Preserve exact lookup, then certify a full authority spelling and one gene."""
    original = resolve_target(value)
    if original is None or original.status is not ResolutionStatus.UNRESOLVED:
        return original
    if not any(c in _SUPPORTED for c in value) or '/' in value or '×' in value:
        return original
    # A canonical Greek letter elsewhere must not enable a confusable/variant glyph.
    if any(c not in _SUPPORTED and c.casefold() in _GREEK for c in value):
        return original
    key = _key(value)
    if not re.search('[a-z]', key):
        return original
    resolver = get_resolver()
    assert resolver is not None  # The exact lookup above established this snapshot.
    claims = _claims(resolver).get(key, ())
    ids = sorted({entity_id for entity_id, _ in claims})
    if not ids:
        return original
    if len(ids) > 1:
        return ResolutionResult(query=value, status=ResolutionStatus.AMBIGUOUS,
                                candidates=[resolver.get(i, EntityType.TARGET) for i in ids],
                                rule=RULE + ':multiple_claimants',
                                ontology_version=resolver.ontology_version)
    entity = resolver.get(ids[0], EntityType.TARGET)
    if entity is None or not _single_gene(entity):
        return original.model_copy(update={'rule': RULE + ':uncertified_gene_identity'})
    for _, alias in claims:
        authority = resolver.resolve(alias.value, EntityType.TARGET)
        if authority.status is not ResolutionStatus.RESOLVED or authority.canonical_id != ids[0]:
            continue
        basis = ResolutionBasis(observed_query=value, matched_alias=alias.value,
                                matched_alias_type=alias.alias_type,
                                asserted_by=sorted(alias.sources),
                                asserting_record_keys=sorted(alias.record_keys),
                                identifier_edges=sorted(entity.identifier_edges), rule=RULE)
        return ResolutionResult(query=value, status=ResolutionStatus.RESOLVED, entity=entity,
                                rule=RULE, basis=basis, ontology_version=resolver.ontology_version)
    return original.model_copy(update={'rule': RULE + ':original_alias_not_certified'})
