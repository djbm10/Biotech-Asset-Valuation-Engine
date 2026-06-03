"""M&A Hard Exclusion / Routing Layer (Gate 0A replacement).

This package implements a structured 11-gate cascade that determines whether
a company is eligible for live M&A ranking, should be routed to a different
model, or should only be used in historical training/backtest.

Quick start
-----------
    from bve.intelligence.exclusions import (
        CompanyProfile,
        AcquirerProfile,
        ExclusionEngine,
        evaluate_company_exclusions,
        evaluate_pair_exclusions,
        apply_exclusion_assessment_to_score,
        ExclusionStatus,
        RoutingModel,
    )

    profile = CompanyProfile(
        company_id="INBX",
        ticker="INBX",
        corporate_status="acquired",          # → HISTORICAL_ONLY
    )
    assessment = evaluate_company_exclusions(profile)
    print(assessment.live_ranking_eligible)   # False
    print(assessment.historical_training_eligible)  # True

Gates
-----
    Gate 0  — Entity Validity
    Gate 1  — Standalone / Corporate Status
    Gate 2  — Buyer-Target Validity (pair-level; requires AcquirerProfile)
    Gate 3  — Asset Visibility
    Gate 4  — Asset Viability
    Gate 5  — Rights / IP / Ownership
    Gate 6  — Financial / Going-Concern
    Gate 7  — Market Data Quality
    Gate 8  — Legal / Integrity
    Gate 9  — Commercial Relevance
    Gate 10 — Model Routing
"""
from .enums import ExclusionStatus, GateName, RoutingModel, most_severe
from .models import (
    AcquirerProfile,
    CompanyProfile,
    ExclusionAssessment,
    GateResult,
)
from .engine import (
    ExclusionEngine,
    apply_exclusion_assessment_to_score,
    evaluate_company_exclusions,
    evaluate_pair_exclusions,
)
from .config_loader import ExclusionRuleConfigLoader, ExclusionRuleConfig

__all__ = [
    # Enums
    "ExclusionStatus",
    "GateName",
    "RoutingModel",
    "most_severe",
    # Models
    "AcquirerProfile",
    "CompanyProfile",
    "ExclusionAssessment",
    "GateResult",
    # Engine
    "ExclusionEngine",
    "apply_exclusion_assessment_to_score",
    "evaluate_company_exclusions",
    "evaluate_pair_exclusions",
    # Config
    "ExclusionRuleConfig",
    "ExclusionRuleConfigLoader",
]
