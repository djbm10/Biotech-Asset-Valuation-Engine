"""Versioned, bulk-backed biomedical entity layer for the S&E pipeline."""

from bve.se.ontology.modality import (
    MODALITY_ONTOLOGY_VERSION,
    known_modalities,
    modality_aliases,
    modality_query_terms,
    normalize_modality,
)
from bve.se.ontology.records import (
    AliasType,
    EntityType,
    SourceAlias,
    SourceEntityRecord,
    SourceProvenance,
)
from bve.se.ontology.resolver import (
    BiomedicalEntityResolver,
    CanonicalEntity,
    ConflictFlag,
    ConflictType,
    ResolutionBasis,
    ResolutionResult,
    ResolutionStatus,
)
from bve.se.ontology.snapshot import RESOLVER_VERSION, OntologySnapshot
from bve.se.ontology.targets import (
    get_resolver,
    normalize_target,
    ontology_version,
    reset_resolver_cache,
    resolve_target,
    target_aliases,
)

__all__ = [
    "AliasType",
    "BiomedicalEntityResolver",
    "CanonicalEntity",
    "ConflictFlag",
    "ConflictType",
    "EntityType",
    "MODALITY_ONTOLOGY_VERSION",
    "OntologySnapshot",
    "RESOLVER_VERSION",
    "ResolutionBasis",
    "ResolutionResult",
    "ResolutionStatus",
    "SourceAlias",
    "SourceEntityRecord",
    "SourceProvenance",
    "get_resolver",
    "known_modalities",
    "modality_aliases",
    "modality_query_terms",
    "normalize_modality",
    "normalize_target",
    "ontology_version",
    "reset_resolver_cache",
    "resolve_target",
    "target_aliases",
]
