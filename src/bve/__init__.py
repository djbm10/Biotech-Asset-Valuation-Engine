"""
Biotech Asset Valuation Engine (BVE)

Canonical imports — everything you need for a full valuation:

    from bve import (
        Asset, Company, ClinicalTrial, Indication,
        MarketModel, POSAdjusters, compute_pos,
        compute_rnpv, run_monte_carlo, MonteCarloParams,
        ValuationEngine, ValuationOutput,
        generate_memo, save_all_charts,
    )
"""

# Entities
from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea, Catalyst
from bve.entities.company import Company, Partnership
from bve.entities.indication import Indication
from bve.entities.trial import ClinicalTrial, EndpointType, TrialPhase, TrialStatus

# Models
from bve.models.pos_model import (
    POSAdjusters, compute_pos, apply_pos_to_trials,
    MoAPrecedent, MoAExceptionFlag, SafetyProfile, CompetitivePressure,
    BiomarkerSelectionStrength, PriorPhaseDataStrength,
)
from bve.models.sample_size_scorer import SampleSizeParams, SampleSizeTrialDesign, SampleSizeScoringResult, score_sample_size
from bve.models.safety_scorer import SafetyParams, SafetyScoringResult, score_safety
from bve.models.market_model import MarketModel, UptakeCurve
from bve.models.rnpv_model import RNPVResult, compute_rnpv
from bve.models.monte_carlo import MonteCarloParams, MonteCarloResult, PhaseSuccessDistribution, run_monte_carlo
from bve.models.correlations import CorrelationSpec, DEFAULT_CORRELATION

# Valuation
from bve.valuation.valuation_engine import ValuationEngine
from bve.valuation.outputs import ValuationOutput, SensitivityPoint
from bve.valuation.scenario import ScenarioSet, ScenarioResult, build_scenarios

# Reporting
from bve.reporting.memo_generator import generate_memo, save_memo
from bve.reporting.charts import save_all_charts
from bve.reporting.export import export_full_package

__all__ = [
    # Entities
    "Asset", "DevelopmentStage", "Modality", "TherapeuticArea", "Catalyst",
    "Company", "Partnership",
    "Indication",
    "ClinicalTrial", "EndpointType", "TrialPhase", "TrialStatus",
    # Models
    "POSAdjusters", "compute_pos", "apply_pos_to_trials",
    "MoAPrecedent", "MoAExceptionFlag", "SafetyProfile", "CompetitivePressure",
    "BiomarkerSelectionStrength", "PriorPhaseDataStrength",
    "SampleSizeParams", "SampleSizeTrialDesign", "SampleSizeScoringResult", "score_sample_size",
    "SafetyParams", "SafetyScoringResult", "score_safety",
    "MarketModel", "UptakeCurve",
    "RNPVResult", "compute_rnpv",
    "MonteCarloParams", "MonteCarloResult", "PhaseSuccessDistribution", "run_monte_carlo",
    "CorrelationSpec", "DEFAULT_CORRELATION",
    # Valuation
    "ValuationEngine", "ValuationOutput", "SensitivityPoint",
    "ScenarioSet", "ScenarioResult", "build_scenarios",
    # Reporting
    "generate_memo", "save_memo", "save_all_charts", "export_full_package",
]
