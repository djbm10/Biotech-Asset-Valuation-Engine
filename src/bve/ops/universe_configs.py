"""
Parametric DrugAssetProgram builder for the 27-name UNIVERSE.

Builds screening-grade DrugAssetProgram + Company objects from
research/universe_params.yaml without requiring a full hand-written
asset YAML config per ticker.

ACCURACY TIER: SCREENING-GRADE
- Valuations use industry-average phase success rates (no asset-specific POS adjusters)
- Peak sales taken from universe_params.yaml conservative consensus estimates
- Company financials fetched live from yfinance at call time
- LOE tail suppressed (no_loe) for cross-universe consistency

Use ValuationEngine.from_program(program, company).run() on each output to
get a ValuationOutput suitable for compute_implied_market_assumptions().

Usage
-----
    from bve.ops.universe_configs import load_universe_programs

    programs = load_universe_programs()
    for ticker, (program, company) in programs.items():
        output = ValuationEngine.from_program(program, company).run()
        ...
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml

from bve.config.assumptions_loader import AssumptionsLoader
from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, EndpointType, TrialPhase, TrialStatus
from bve.models.drug_asset_program import CommercialPlan, DrugAssetProgram
from bve.models.market_model import MarketModel

_LOG = logging.getLogger("bve.ops.universe_configs")

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PARAMS_PATH = _REPO_ROOT / "research" / "universe_params.yaml"

# Phase chain: starting from a given phase, what phases remain?
_PHASE_CHAIN: dict[str, list[str]] = {
    "phase_1": ["phase_1", "phase_2", "phase_3", "nda_bla"],
    "phase_2": ["phase_2", "phase_3", "nda_bla"],
    "phase_3": ["phase_3", "nda_bla"],
    "nda_bla": ["nda_bla"],
    "approved": [],
}

_MODALITY_MAP: dict[str, Modality] = {
    "small_molecule": Modality.SMALL_MOLECULE,
    "biologic": Modality.BIOLOGIC,
    "gene_therapy": Modality.GENE_THERAPY,
    "cell_therapy": Modality.CELL_THERAPY,
    "adc": Modality.ADC,
    "rna_therapy": Modality.RNA_THERAPY,
    "other": Modality.OTHER,
}

_TA_MAP: dict[str, TherapeuticArea] = {
    "oncology": TherapeuticArea.ONCOLOGY,
    "rare_disease": TherapeuticArea.RARE_DISEASE,
    "cns": TherapeuticArea.CNS,
    "cardiovascular": TherapeuticArea.CARDIOVASCULAR,
    "immunology": TherapeuticArea.IMMUNOLOGY,
    "infectious_disease": TherapeuticArea.INFECTIOUS_DISEASE,
    "ophthalmology": TherapeuticArea.OPHTHALMOLOGY,
    "other": TherapeuticArea.OTHER,
}

_STAGE_MAP: dict[str, DevelopmentStage] = {
    "phase_1": DevelopmentStage.PHASE_1,
    "phase_2": DevelopmentStage.PHASE_2,
    "phase_3": DevelopmentStage.PHASE_3,
    "nda_bla": DevelopmentStage.NDA_BLA,
    "approved": DevelopmentStage.APPROVED,
}

_PHASE_ENUM_MAP: dict[str, TrialPhase] = {
    "phase_1": TrialPhase.PHASE_1,
    "phase_2": TrialPhase.PHASE_2,
    "phase_3": TrialPhase.PHASE_3,
    "nda_bla": TrialPhase.NDA_BLA,
}


def load_params(params_path: Optional[Path] = None) -> dict[str, dict]:
    """Load and return universe_params.yaml as a ticker → params dict."""
    path = params_path or _DEFAULT_PARAMS_PATH
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return {ticker: entry for ticker, entry in raw.get("universe", {}).items()}


def _build_trials(
    asset_id: str,
    ta: str,
    phase: str,
    loader: AssumptionsLoader,
) -> list[ClinicalTrial]:
    """
    Build a trial chain from current phase through NDA using industry base rates.
    Returns empty list for approved assets (no remaining trials).
    """
    chain = _PHASE_CHAIN.get(phase, [])
    if not chain:
        return []

    durations = loader.phase_durations_years
    costs = loader.phase_costs_millions
    rates = loader.phase_success_rates_for(ta)

    trials = []
    for phase_key in chain:
        phase_enum = _PHASE_ENUM_MAP[phase_key]
        pos = rates.get(phase_key, 0.50)
        trials.append(
            ClinicalTrial(
                asset_id=asset_id,
                phase=phase_enum,
                success_probability=pos,
                duration_years=durations.get(phase_key, 2.0),
                cost_millions=costs.get(phase_key, 75.0),
                cost_source="default",
                endpoint_type=EndpointType.SURROGATE_VALIDATED,
                status=TrialStatus.RECRUITING,
                data_source="parametric",
            )
        )
    return trials


def build_program(
    ticker: str,
    params: dict,
    company: Optional[Company] = None,
) -> tuple[DrugAssetProgram, Company]:
    """
    Build a screening-grade DrugAssetProgram and Company from universe_params.yaml entry.

    Parameters
    ----------
    ticker : stock ticker (e.g. "VKTX")
    params : entry from universe_params.yaml["universe"][ticker]
    company : pre-built Company; if None, a placeholder company with zeros is built
              (caller should inject live financials via fetch_company_snapshot)

    Returns
    -------
    (DrugAssetProgram, Company)
    """
    loader = AssumptionsLoader.get()

    asset_id = f"a-{ticker.lower()}"
    ta_key = params.get("ta", "other")
    phase = params.get("phase", "phase_2")
    modality_key = params.get("modality", "small_molecule")
    peak_sales = float(params.get("peak_sales_millions", 1000.0))
    patent_life = int(params.get("patent_life_years", 12))

    ta_enum = _TA_MAP.get(ta_key, TherapeuticArea.OTHER)
    stage_enum = _STAGE_MAP.get(phase, DevelopmentStage.PHASE_2)
    modality_enum = _MODALITY_MAP.get(modality_key, Modality.SMALL_MOLECULE)

    asset = Asset(
        id=asset_id,
        name=params.get("program_label", ticker),
        indication=params.get("program_label", ticker),
        therapeutic_area=ta_enum,
        stage=stage_enum,
        modality=modality_enum,
        discount_rate=0.10,
        royalty_rate=0.0,
    )

    trials = _build_trials(asset_id, ta_key, phase, loader)

    market_model = MarketModel(
        asset_id=asset_id,
        total_addressable_market_millions=peak_sales,
        peak_penetration=0.25,
        years_to_peak=5,
        patent_life_years=patent_life,
        cogs_rate=0.15,
        sgna_rate_launch=0.40,
        sgna_rate_mature=0.20,
    )

    commercial_plan = CommercialPlan.no_loe()

    program = DrugAssetProgram(
        asset=asset,
        trials=trials,
        market_model=market_model,
        commercial_plan=commercial_plan,
    )

    if company is None:
        company = Company(
            id=f"co-{ticker.lower()}",
            name=ticker,
            ticker=ticker,
            cash_millions=0.0,
            shares_outstanding_millions=1.0,
        )

    return program, company


def fetch_company_snapshot(ticker: str) -> Company:
    """
    Build a Company with live financials from yfinance.

    Returns a Company with zeros for financials if the yfinance call fails.
    Does not raise — missing market data is handled downstream by implied_pos_batch.
    """
    try:
        from bve.ingestion.market_data import get_fundamentals
        data = get_fundamentals(ticker)
        return Company(
            id=f"co-{ticker.lower()}",
            name=data.get("name") or ticker,
            ticker=ticker,
            cash_millions=float(data.get("cash_millions") or 0.0),
            debt_millions=float(data.get("total_debt_millions") or 0.0),
            shares_outstanding_millions=max(
                float(data.get("shares_outstanding_millions") or 1.0), 0.001
            ),
            current_price=data.get("current_price"),
            market_cap_millions=data.get("market_cap_millions"),
        )
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("yfinance fetch failed for %s: %s — using zero financials", ticker, exc)
        return Company(
            id=f"co-{ticker.lower()}",
            name=ticker,
            ticker=ticker,
            cash_millions=0.0,
            shares_outstanding_millions=1.0,
        )


def load_universe_programs(
    params_path: Optional[Path] = None,
    fetch_live: bool = True,
) -> dict[str, tuple[DrugAssetProgram, Company]]:
    """
    Load all 27 universe entries and build (DrugAssetProgram, Company) pairs.

    Parameters
    ----------
    params_path : override path to universe_params.yaml
    fetch_live  : if True, fetch live Company financials from yfinance (default True)
                  if False, return placeholder Company objects with zero financials
                  (useful for offline tests)

    Returns
    -------
    dict mapping ticker → (DrugAssetProgram, Company)
    """
    all_params = load_params(params_path)
    result = {}
    for ticker, params in all_params.items():
        company = fetch_company_snapshot(ticker) if fetch_live else None
        program, company = build_program(ticker, params, company)
        result[ticker] = (program, company)
    return result
