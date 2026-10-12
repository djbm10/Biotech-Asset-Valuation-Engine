"""Keep certified ontology identity separate from biological retrieval text."""
from __future__ import annotations

from collections.abc import Iterable

from bve.se.ontology.records import EntityType
from bve.se.ontology.resolver import CanonicalEntity, ResolutionResult, ResolutionStatus
from bve.se.ontology.targets import get_resolver
from bve.se.schemas.contracts import TargetReference, TargetTerm


class TargetReferenceError(ValueError):
    """A target reference cannot be used coherently under the installed snapshot."""


def reference_for(result: ResolutionResult) -> TargetReference | None:
    if (result.status is not ResolutionStatus.RESOLVED or result.entity is None
            or result.ontology_version is None):
        return None
    return TargetReference(entity_id=result.entity.canonical_id,
                           ontology_version=result.ontology_version)


def is_ontology_id(value: str) -> bool:
    return value.strip().casefold().startswith("target:")


def _entity(term: TargetTerm) -> CanonicalEntity | None:
    reference = term.target_reference
    if reference is None and not is_ontology_id(term.canonical_id):
        return None
    resolver = get_resolver()
    if resolver is None:
        raise TargetReferenceError("target reference requires its ontology snapshot")
    if reference is not None and reference.ontology_version != resolver.ontology_version:
        raise TargetReferenceError("target reference ontology version does not match the snapshot")
    entity_id = reference.entity_id if reference else term.canonical_id.strip()
    entity = resolver.get(entity_id, EntityType.TARGET)
    if (entity is None or entity.entity_type is not EntityType.TARGET
            or entity.canonical_id.casefold() != entity_id.casefold()):
        raise TargetReferenceError("target reference does not identify an exact TARGET entity")
    if not entity.canonical_symbol:
        raise TargetReferenceError("target entity has no approved biological symbol")
    if reference is not None:
        if entity.canonical_id != reference.entity_id:
            raise TargetReferenceError("target reference must use the exact canonical entity ID")
        allowed = {entity.canonical_id.casefold(), entity.canonical_symbol.casefold()}
        if term.canonical_id.strip().casefold() not in allowed:
            raise TargetReferenceError("target reference conflicts with the declared canonical target")
    return entity


def lookup_id(term: TargetTerm) -> str:
    """Authority identity; unreferenced legacy names retain their existing semantics."""
    entity = _entity(term)
    return entity.canonical_id if entity is not None else term.canonical_id


def surface_id(term: TargetTerm) -> str:
    """Biological text for source scope/retrieval, never a qualified ontology ID."""
    entity = _entity(term)
    return entity.canonical_symbol if entity is not None else term.canonical_id


def surface_terms(term: TargetTerm, values: Iterable[str]) -> list[str]:
    """Render only this target's own identifier, rejecting foreign metadata terms."""
    entity = _entity(term)
    terms = []
    for value in values:
        if is_ontology_id(value):
            if entity is None or value.strip().casefold() != entity.canonical_id.casefold():
                raise TargetReferenceError("foreign or uncertified ontology ID in retrieval terms")
            value = entity.canonical_symbol
        if value and value not in terms:
            terms.append(value)
    return terms
