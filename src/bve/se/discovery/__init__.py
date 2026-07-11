"""Coverage-measured, iterative multi-source discovery."""

from bve.se.discovery.adapters import (
    ClinicalTrialsGovAdapter,
    FrozenCandidateAdapter,
    IndexedDocumentAdapter,
    PubMedDiscoveryAdapter,
    UrlDocumentAdapter,
    UnavailableSourceAdapter,
)
from bve.se.discovery.orchestrator import DiscoveryOrchestrator, DiscoveryResult, SourceAdapter
from bve.se.discovery.query import compile_problem_queries

__all__ = [
    "ClinicalTrialsGovAdapter",
    "DiscoveryOrchestrator",
    "DiscoveryResult",
    "FrozenCandidateAdapter",
    "IndexedDocumentAdapter",
    "PubMedDiscoveryAdapter",
    "SourceAdapter",
    "UnavailableSourceAdapter",
    "UrlDocumentAdapter",
    "compile_problem_queries",
]
