"""Biotech Asset Valuation Engine public API.

The public names remain available through ``from bve import ...`` but are loaded
on first access.  Keeping package initialization lightweight lets focused
operational entry points, including the public-data S&E runner, install only
their actual runtime dependencies.
"""

from __future__ import annotations

from importlib import import_module


_PUBLIC_EXPORTS: dict[str, str] = {
    # Entities
    "Asset": "bve.entities.asset",
    "DevelopmentStage": "bve.entities.asset",
    "Modality": "bve.entities.asset",
    "TherapeuticArea": "bve.entities.asset",
    "Catalyst": "bve.entities.asset",
    "Company": "bve.entities.company",
    "Partnership": "bve.entities.company",
    "Indication": "bve.entities.indication",
    "ClinicalTrial": "bve.entities.trial",
    "EndpointType": "bve.entities.trial",
    "TrialPhase": "bve.entities.trial",
    "TrialStatus": "bve.entities.trial",
    # Models
    "POSAdjusters": "bve.models.pos_model",
    "compute_pos": "bve.models.pos_model",
    "apply_pos_to_trials": "bve.models.pos_model",
    "MoAPrecedent": "bve.models.pos_model",
    "MoAExceptionFlag": "bve.models.pos_model",
    "SafetyProfile": "bve.models.pos_model",
    "CompetitivePressure": "bve.models.pos_model",
    "BiomarkerSelectionStrength": "bve.models.pos_model",
    "PriorPhaseDataStrength": "bve.models.pos_model",
    "SampleSizeParams": "bve.models.sample_size_scorer",
    "SampleSizeTrialDesign": "bve.models.sample_size_scorer",
    "SampleSizeScoringResult": "bve.models.sample_size_scorer",
    "score_sample_size": "bve.models.sample_size_scorer",
    "SafetyParams": "bve.models.safety_scorer",
    "SafetyScoringResult": "bve.models.safety_scorer",
    "score_safety": "bve.models.safety_scorer",
    "MarketModel": "bve.models.market_model",
    "UptakeCurve": "bve.models.market_model",
    "RNPVResult": "bve.models.rnpv_model",
    "compute_rnpv": "bve.models.rnpv_model",
    "MonteCarloParams": "bve.models.monte_carlo",
    "MonteCarloResult": "bve.models.monte_carlo",
    "PhaseSuccessDistribution": "bve.models.monte_carlo",
    "run_monte_carlo": "bve.models.monte_carlo",
    "CorrelationSpec": "bve.models.correlations",
    "DEFAULT_CORRELATION": "bve.models.correlations",
    # Valuation
    "ValuationEngine": "bve.valuation.valuation_engine",
    "ValuationOutput": "bve.valuation.outputs",
    "SensitivityPoint": "bve.valuation.outputs",
    "ScenarioSet": "bve.valuation.scenario",
    "ScenarioResult": "bve.valuation.scenario",
    "build_scenarios": "bve.valuation.scenario",
    # Reporting
    "generate_memo": "bve.reporting.memo_generator",
    "save_memo": "bve.reporting.memo_generator",
    "save_all_charts": "bve.reporting.charts",
    "export_full_package": "bve.reporting.export",
}

__all__ = list(_PUBLIC_EXPORTS)


def __getattr__(name: str) -> object:
    """Load one public export on demand and cache it in the package namespace."""

    module_name = _PUBLIC_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Expose lazy public names to interactive discovery tools."""

    return sorted({*globals(), *_PUBLIC_EXPORTS})
