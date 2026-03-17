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
    RunStateRecord,
    OpportunityAlertRecord,
    LiteratureReviewRecord,
    CompetitiveLandscapeRecord,
    ResearchReportRecord,
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
from bve.intelligence.cross_asset_propagation import (
    PropagationType,
    PropagationGuardrails,
    PropagationObservation,
    PropagationCalibration,
    GeneratedPropagationProposal,
    PropagationRoutingResult,
    PropagationDatasetBuilder,
    PropagationCalibrator,
    CrossAssetPropagationEngine,
)
from bve.intelligence.moa_summary_agent import (
    MoASummary,
    MechanismOfActionSummaryAgent,
)
from bve.intelligence.literature_review_agent import (
    LiteratureTopic,
    LiteratureReviewSection,
    LiteratureReview,
    DocumentTopicGrouper,
    LiteratureReviewAgent,
)
from bve.intelligence.competitive_landscape_agent import (
    CompetitiveProgramEntry,
    CompetitiveLandscape,
    CompetitiveLandscapeAgent,
)
from bve.intelligence.research_report import (
    ResearchReport,
    ResearchReportContext,
    ResearchReportGenerator,
)
from bve.intelligence.opportunity_scanner import (
    OpportunityScannerConfig,
    OpportunityScanResult,
    OpportunityScanner,
)
from bve.intelligence.opportunity_snapshot import (
    OpportunitySnapshotRecord,
    OpportunitySnapshotStore,
)
from bve.intelligence.opportunity_monitor import (
    OpportunityMonitorConfig,
    OpportunityMonitorResult,
    OpportunityMonitor,
)
from bve.intelligence.investment_memo_agent import (
    InvestmentMemo,
    InvestmentMemoContext,
    InvestmentMemoAgent,
)
from bve.intelligence.trial_design_feature_extractor import (
    PreReadoutAssessment,
    TrialDesignFeatureExtractor,
)
from bve.intelligence.phase_correlation_updater import (
    PhaseCorrelationResult,
    PhaseCorrelationUpdater,
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
    "RunStateRecord",
    "OpportunityAlertRecord",
    "LiteratureReviewRecord",
    "CompetitiveLandscapeRecord",
    "ResearchReportRecord",
    "MemoRecord",
    "DossierRecord",
    "RecordWithTrace",
    "KnowledgeStore",
    # Memo generation
    "WeeklyMemoInput",
    "WeeklyMemoOutput",
    "WeeklyMemoPromptBuilder",
    "WeeklyMemoGenerator",
    # Wave 5 propagation
    "PropagationType",
    "PropagationGuardrails",
    "PropagationObservation",
    "PropagationCalibration",
    "GeneratedPropagationProposal",
    "PropagationRoutingResult",
    "PropagationDatasetBuilder",
    "PropagationCalibrator",
    "CrossAssetPropagationEngine",
    # Wave 6A MoA agent
    "MoASummary",
    "MechanismOfActionSummaryAgent",
    # Wave 6B literature review
    "LiteratureTopic",
    "LiteratureReviewSection",
    "LiteratureReview",
    "DocumentTopicGrouper",
    "LiteratureReviewAgent",
    # Wave 6C competitive landscape
    "CompetitiveProgramEntry",
    "CompetitiveLandscape",
    "CompetitiveLandscapeAgent",
    # Wave 6D research report
    "ResearchReport",
    "ResearchReportContext",
    "ResearchReportGenerator",
    # Wave 7 scanner + memo
    "OpportunityScannerConfig",
    "OpportunityScanResult",
    "OpportunityScanner",
    "OpportunitySnapshotRecord",
    "OpportunitySnapshotStore",
    "OpportunityMonitorConfig",
    "OpportunityMonitorResult",
    "OpportunityMonitor",
    "InvestmentMemo",
    "InvestmentMemoContext",
    "InvestmentMemoAgent",
    # Wave 4 pre-readout design scoring
    "PreReadoutAssessment",
    "TrialDesignFeatureExtractor",
    # Wave 5 phase correlation (Bayesian Ph2→Ph3 update)
    "PhaseCorrelationResult",
    "PhaseCorrelationUpdater",
]
