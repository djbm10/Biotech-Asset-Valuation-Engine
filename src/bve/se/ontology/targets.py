"""Snapshot-backed target normalization.

This module used to hold a hand-written CD19/BCMA alias table. It is now a thin
accessor over a versioned :class:`~bve.se.ontology.snapshot.OntologySnapshot` built
from bulk Open Targets and ChEMBL data, so it generalizes to any target present in
the snapshot rather than the two it was seeded with.

Degradation is deliberate and silent-free: when no snapshot is installed, lookups
return ``None``/``()`` and :func:`ontology_version` reports ``no_snapshot``. Callers
fall back to the aliases declared on the buyer problem, so a run without a snapshot
is narrower but never wrong — and the manifest records which case applied.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from bve.se.ontology.modality import MODALITY_ONTOLOGY_VERSION, normalize_modality
from bve.se.ontology.records import EntityType
from bve.se.ontology.resolver import BiomedicalEntityResolver, ResolutionStatus
from bve.se.ontology.snapshot import OntologySnapshot

#: Version reported when no snapshot is installed, so runs are still auditable.
NO_SNAPSHOT_VERSION = "no_snapshot"

_ENV_VAR = "BVE_SE_ONTOLOGY_SNAPSHOT"
_DEFAULT_SNAPSHOT_DIR = Path("data/se/ontology/current")


def default_snapshot_path() -> Path:
    """Where the resolver looks for its snapshot, overridable for tests and CI."""

    override = os.environ.get(_ENV_VAR)
    return Path(override) if override else _DEFAULT_SNAPSHOT_DIR


@lru_cache(maxsize=4)
def _load_resolver(path: str) -> BiomedicalEntityResolver | None:
    try:
        snapshot = OntologySnapshot.read(Path(path))
    except FileNotFoundError:
        return None
    return BiomedicalEntityResolver(snapshot)


def get_resolver(path: Path | None = None) -> BiomedicalEntityResolver | None:
    """The process-wide resolver, or ``None`` when no snapshot is installed."""

    return _load_resolver(str(path or default_snapshot_path()))


def reset_resolver_cache() -> None:
    """Drop the cached resolver; call after installing or replacing a snapshot."""

    _load_resolver.cache_clear()
    known_targets.cache_clear()
    # Imported here rather than at module scope: the discovery layer depends on this
    # module, so a top-level import would close a cycle.
    from bve.se.discovery.adapters import QueryVocabulary

    QueryVocabulary.for_ontology.cache_clear()


def ontology_version() -> str:
    """The pinned version token to stamp into a run manifest."""

    resolver = get_resolver()
    base = resolver.ontology_version if resolver else NO_SNAPSHOT_VERSION
    return f"{base}__{MODALITY_ONTOLOGY_VERSION}"


def normalize_target(value: str) -> str | None:
    """Return the canonical (HGNC approved) symbol, or ``None`` if not resolvable.

    Returns ``None`` for genuinely ambiguous strings rather than picking a side; use
    :func:`resolve_target` when the caller needs to distinguish "unknown" from
    "ambiguous" and escalate accordingly.
    """

    resolver = get_resolver()
    if resolver is None:
        return None
    result = resolver.resolve(value, EntityType.TARGET)
    return result.canonical_symbol if result.status is ResolutionStatus.RESOLVED else None


def resolve_target(value: str):
    """Full resolution result, including ambiguity candidates and conflict flags."""

    resolver = get_resolver()
    if resolver is None:
        return None
    return resolver.resolve(value, EntityType.TARGET)


def target_aliases(canonical_id: str) -> tuple[str, ...]:
    """Queryable alias spellings for a target; ``()`` when unavailable.

    This is the seam the discovery query compiler and the acquisition runner use in
    place of the former module-level alias dictionary.
    """

    resolver = get_resolver()
    if resolver is None:
        return ()
    return resolver.aliases_for(canonical_id, EntityType.TARGET)


@lru_cache(maxsize=1)
def known_targets() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Every target in the snapshot with its queryable aliases; ``()`` without one.

    Cached because it is a pure function of the pinned snapshot, and walking every
    target entity to collect its aliases is not something a caller should pay for per
    record. :func:`reset_resolver_cache` drops it along with the resolver, so installing
    a new snapshot never leaves a vocabulary describing the old one.

    Corpus indexing labels documents before a query exists, so it needs the whole target
    vocabulary. Returning ``()`` when no snapshot is loaded is deliberate: labelling
    against a hardcoded fallback list is what made discovery look accurate only on the
    targets it was written for.

    Keyed by approved symbol rather than internal canonical id, because that is what a
    compiled query names and what a label is compared against downstream. Entities with
    no elected symbol fall back to their id so they remain addressable.
    """

    resolver = get_resolver()
    if resolver is None:
        return ()
    return tuple(
        (entity.canonical_symbol or entity.canonical_id, entity.queryable_aliases())
        for entity in resolver.entities_of_type(EntityType.TARGET)
    )


__all__ = [
    "MODALITY_ONTOLOGY_VERSION",
    "NO_SNAPSHOT_VERSION",
    "default_snapshot_path",
    "get_resolver",
    "known_targets",
    "normalize_modality",
    "normalize_target",
    "ontology_version",
    "reset_resolver_cache",
    "resolve_target",
    "target_aliases",
]
