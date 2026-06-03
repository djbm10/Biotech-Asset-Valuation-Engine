"""
Dossier layer public API.

The graph-backed imports (asset_graph, CanonicalAssetGraph, etc.) are NOT
re-exported here to avoid a circular import chain:
  bve.dossier.asset_graph → bve.intelligence → bve.models.probability_stack
  → bve.intelligence.science_engine → bve.dossier.asset_graph
Import those directly from bve.dossier.asset_graph when needed.
"""
from bve.dossier.builder import DossierBuilder
from bve.dossier.dossier import AssetDossier, DossierCompletenessReport, ProvenanceField, TrialSummary
from bve.dossier.evidence_builder import EvidenceDossierBuilder
from bve.dossier.asset_dossier import (
    AssetDossier as EvidenceAssetDossier,
    AssetIdentity,
    CatalystSnapshot,
    CompetitionSnapshot,
    FinancingState,
    MarketSnapshot,
    ScienceContext,
    ThesisState,
    TrialSnapshot,
)
from bve.dossier.acquirer_dossier import (
    AcquirerDossier,
    BDActivity,
    BalanceSheet,
    LOEExposure,
    PipelineGap,
    TherapeuticFocus,
)

__all__ = [
    "AcquirerDossier",
    "AssetDossier",
    "AssetIdentity",
    "BDActivity",
    "BalanceSheet",
    "CatalystSnapshot",
    "CompetitionSnapshot",
    "DossierBuilder",
    "DossierCompletenessReport",
    "EvidenceAssetDossier",
    "EvidenceDossierBuilder",
    "FinancingState",
    "LOEExposure",
    "MarketSnapshot",
    "PipelineGap",
    "ProvenanceField",
    "ScienceContext",
    "TherapeuticFocus",
    "ThesisState",
    "TrialSnapshot",
    "TrialSummary",
]
