"""
bve.intelligence — biotech intelligence-to-valuation platform (Phase 0 foundation).

Layer boundary
--------------
This package sits ABOVE the frozen v1.0 engine.  It may import from:
    bve.entities.*     (Asset, Company, ClinicalTrial enums)
    bve.models.*       (frozen; import for type references only)
    bve.valuation.*    (frozen; import for type references only)

The frozen packages NEVER import from bve.intelligence.

Public surface
--------------
    from bve.intelligence.taxonomy import EventType, ChangeMode
    from bve.intelligence.mapping import EVENT_PARAMETER_MAP, MappingRule, rules_for
    from bve.intelligence.schemas import (
        IntelligenceCompany, IntelligenceAsset, IntelligenceIndication,
        Event, StructuredSignal, AssumptionChangeProposal,
        ValuationRun, ReviewDecision, Thesis, KnowledgeArtifact,
    )
"""
from bve.intelligence.taxonomy import EventType, ChangeMode
from bve.intelligence.mapping import (
    EVENT_PARAMETER_MAP,
    LEGAL_PARAMETER_PATHS,
    MappingRule,
    rules_for,
    auto_rules,
    requires_review,
)
from bve.intelligence.schemas import (
    IntelligenceCompany,
    IntelligenceAsset,
    IntelligenceIndication,
    Event,
    StructuredSignal,
    AssumptionChangeProposal,
    ValuationRun,
    ReviewDecision,
    Thesis,
    KnowledgeArtifact,
)
from bve.intelligence.phase2 import (
    EventRoutingPolicy,
    MappingPolicy,
    MappingEngine,
    MappingBatchResult,
    MappingAuditEntry,
    MappingSkip,
    ReviewQueue,
    ReviewQueueItem,
    ReviewRoutingResult,
    ValuationSession,
    ValuationRunRecord,
    ValuationDiffLog,
    AssumptionFieldChange,
    ScenarioSnapshot,
    RollbackResult,
    SourceDocumentMetadata,
    ManualReviewAction,
    ManualReviewCase,
    ManualReviewStore,
    render_case,
)
from bve.intelligence.knowledge_layer import (
    SourceTrace,
    RawDocumentRecord,
    ExtractionResultRecord,
    StructuredSignalRecord,
    StoredValuationDiff,
    MemoRecord,
    DossierRecord,
    RecordWithTrace,
    KnowledgeStore,
)
from bve.intelligence.memo_generation import (
    WeeklyMemoInput,
    WeeklyMemoOutput,
    WeeklyMemoPromptBuilder,
    WeeklyMemoGenerator,
)

__all__ = [
    # Taxonomy
    "EventType",
    "ChangeMode",
    # Mapping
    "EVENT_PARAMETER_MAP",
    "LEGAL_PARAMETER_PATHS",
    "MappingRule",
    "rules_for",
    "auto_rules",
    "requires_review",
    # Schemas
    "IntelligenceCompany",
    "IntelligenceAsset",
    "IntelligenceIndication",
    "Event",
    "StructuredSignal",
    "AssumptionChangeProposal",
    "ValuationRun",
    "ReviewDecision",
    "Thesis",
    "KnowledgeArtifact",
    # Phase 2 services
    "EventRoutingPolicy",
    "MappingPolicy",
    "MappingEngine",
    "MappingBatchResult",
    "MappingAuditEntry",
    "MappingSkip",
    "ReviewQueue",
    "ReviewQueueItem",
    "ReviewRoutingResult",
    "ValuationSession",
    "ValuationRunRecord",
    "ValuationDiffLog",
    "AssumptionFieldChange",
    "ScenarioSnapshot",
    "RollbackResult",
    "SourceDocumentMetadata",
    "ManualReviewAction",
    "ManualReviewCase",
    "ManualReviewStore",
    "render_case",
    # Knowledge layer
    "SourceTrace",
    "RawDocumentRecord",
    "ExtractionResultRecord",
    "StructuredSignalRecord",
    "StoredValuationDiff",
    "MemoRecord",
    "DossierRecord",
    "RecordWithTrace",
    "KnowledgeStore",
    # Memo generation
    "WeeklyMemoInput",
    "WeeklyMemoOutput",
    "WeeklyMemoPromptBuilder",
    "WeeklyMemoGenerator",
]
