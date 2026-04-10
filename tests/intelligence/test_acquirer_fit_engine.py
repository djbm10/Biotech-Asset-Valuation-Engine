from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, EndpointType, TrialPhase
from bve.intelligence.acquirer_fit import (
    AcquirerFitEngine,
    AcquirerFitIntegrationConfig,
)
from bve.models.market_model import MarketModel
from bve.pipeline.watchlist_runner import AssetValuationContext, WatchlistAsset


def test_acquirer_fit_engine_scores_and_ranks_watchlist(tmp_path: Path):
    comps_path = _write_comps(tmp_path)
    contexts = {
        "asset-eye-1": _make_context(
            asset_id="asset-eye-1",
            company_id="co-eye-1",
            name="RetinaCo",
            therapeutic_area=TherapeuticArea.OPHTHALMOLOGY,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.BIOLOGIC,
            cash_millions=50.0,
            mechanism_of_action=None,
        ),
        "asset-gene-1": _make_context(
            asset_id="asset-gene-1",
            company_id="co-gene-1",
            name="GeneRare",
            therapeutic_area=TherapeuticArea.RARE_DISEASE,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.GENE_THERAPY,
            cash_millions=120.0,
            mechanism_of_action=None,
        ),
        "asset-onc-1": _make_context(
            asset_id="asset-onc-1",
            company_id="co-onc-1",
            name="OncoCo",
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            stage=DevelopmentStage.PHASE_2,
            modality=Modality.SMALL_MOLECULE,
            cash_millions=40.0,
            mechanism_of_action=None,
        ),
    }
    watchlist = [
        _watchlist_asset("asset-eye-1", "co-eye-1", "EYE1", 500.0, "wet AMD"),
        _watchlist_asset("asset-gene-1", "co-gene-1", "GENE1", 1000.0, "hearing loss"),
        _watchlist_asset("asset-onc-1", "co-onc-1", "ONC1", 600.0, "solid tumors"),
    ]

    engine = AcquirerFitEngine(
        context_provider=_StubProvider(contexts),
        integration_config=AcquirerFitIntegrationConfig(
            acquirer_profiles_path="research/mna/pipeline_gaps.yaml",
            comparable_deals_path=str(comps_path),
            top_n=10,
            require_acquisition_readiness=True,
        ),
    )
    engine.acquisition_screener._run_rnpv = lambda context: _stub_rnpv(context.asset.id)

    result = engine.screen_watchlist(
        watchlist,
        acquirer_id="regeneron",
        snapshot_date=date(2026, 3, 24),
    )

    assert result.n_assets == 3
    assert result.n_passing_hard_filters == 2
    assert [row.asset_id for row in result.rows] == ["asset-eye-1", "asset-gene-1", "asset-onc-1"]
    assert result.rows[0].matched_therapeutic_gap == "ophthalmology"
    assert result.rows[0].matched_modality == "fully_human_antibody"
    assert result.rows[1].matched_therapeutic_gap == "genetic_medicines_rare_disease"
    assert "not_acquisition_ready" in result.rows[2].hard_fail_reasons
    assert result.rows[2].acquisition_ready is False


def test_acquirer_fit_engine_uses_stable_tie_breaker(tmp_path: Path):
    comps_path = _write_comps(tmp_path)
    contexts = {
        "asset-a": _make_context(
            asset_id="asset-a",
            company_id="co-a",
            name="RetinaA",
            therapeutic_area=TherapeuticArea.OPHTHALMOLOGY,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.BIOLOGIC,
            cash_millions=50.0,
            mechanism_of_action=None,
        ),
        "asset-b": _make_context(
            asset_id="asset-b",
            company_id="co-b",
            name="RetinaB",
            therapeutic_area=TherapeuticArea.OPHTHALMOLOGY,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.BIOLOGIC,
            cash_millions=50.0,
            mechanism_of_action=None,
        ),
    }
    watchlist = [
        _watchlist_asset("asset-b", "co-b", "BETA", 500.0, "wet AMD"),
        _watchlist_asset("asset-a", "co-a", "ALFA", 500.0, "wet AMD"),
    ]

    engine = AcquirerFitEngine(
        context_provider=_StubProvider(contexts),
        integration_config=AcquirerFitIntegrationConfig(
            acquirer_profiles_path="research/mna/pipeline_gaps.yaml",
            comparable_deals_path=str(comps_path),
            top_n=10,
            require_acquisition_readiness=True,
        ),
    )
    engine.acquisition_screener._run_rnpv = lambda context: _stub_rnpv("asset-eye-1")

    result = engine.screen_watchlist(
        watchlist,
        acquirer_id="regeneron",
        snapshot_date=date(2026, 3, 24),
    )

    assert [row.asset_id for row in result.rows] == ["asset-a", "asset-b"]


def test_acquirer_fit_engine_supports_curated_pfizer_profile(tmp_path: Path):
    comps_path = _write_comps(tmp_path)
    contexts = {
        "asset-onc-adc": _make_context(
            asset_id="asset-onc-adc",
            company_id="co-onc-adc",
            name="OncoADC",
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.ADC,
            cash_millions=100.0,
            mechanism_of_action="HER2 antibody-drug conjugate",
        ),
        "asset-ibd-sm": _make_context(
            asset_id="asset-ibd-sm",
            company_id="co-ibd-sm",
            name="IBDCo",
            therapeutic_area=TherapeuticArea.IMMUNOLOGY,
            stage=DevelopmentStage.PHASE_2,
            modality=Modality.SMALL_MOLECULE,
            cash_millions=80.0,
            mechanism_of_action="oral small molecule for inflammatory bowel disease",
        ),
    }
    watchlist = [
        _watchlist_asset("asset-ibd-sm", "co-ibd-sm", "IBD1", 7000.0, "ulcerative colitis"),
        _watchlist_asset("asset-onc-adc", "co-onc-adc", "ADC1", 9000.0, "breast cancer"),
    ]

    engine = AcquirerFitEngine(
        context_provider=_StubProvider(contexts),
        integration_config=AcquirerFitIntegrationConfig(
            acquirer_profiles_path="examples/research/acquirer_profiles/pfizer.yaml",
            comparable_deals_path=str(comps_path),
            top_n=10,
            require_acquisition_readiness=False,
        ),
    )
    engine.acquisition_screener._run_rnpv = lambda context: _stub_curated_pfizer_rnpv(context.asset.id)

    result = engine.screen_watchlist(
        watchlist,
        acquirer_id="pfizer",
        snapshot_date=date(2026, 4, 5),
    )

    assert [row.asset_id for row in result.rows] == ["asset-onc-adc", "asset-ibd-sm"]
    assert result.rows[0].matched_therapeutic_gap == "oncology:breast_cancer"
    assert result.rows[0].fit_score == pytest.approx(1.0, abs=1e-9)
    assert result.rows[1].matched_therapeutic_gap == "immunology:inflammatory_bowel_disease"
    assert result.rows[1].fit_score == pytest.approx(0.95, abs=1e-9)


def test_acquirer_fit_engine_supports_curated_directory_profiles(tmp_path: Path):
    comps_path = _write_comps(tmp_path)
    contexts = {
        "asset-oral-glp1": _make_context(
            asset_id="asset-oral-glp1",
            company_id="co-oral-glp1",
            name="MetaOral",
            therapeutic_area=TherapeuticArea.OTHER,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.SMALL_MOLECULE,
            cash_millions=100.0,
            mechanism_of_action="oral GLP-1 small molecule",
        ),
        "asset-cardio": _make_context(
            asset_id="asset-cardio",
            company_id="co-cardio",
            name="CardioCo",
            therapeutic_area=TherapeuticArea.CARDIOVASCULAR,
            stage=DevelopmentStage.PHASE_2,
            modality=Modality.SMALL_MOLECULE,
            cash_millions=60.0,
            mechanism_of_action="cardio-renal small molecule",
        ),
    }
    watchlist = [
        _watchlist_asset("asset-cardio", "co-cardio", "CARD", 7000.0, "cardio renal disease"),
        _watchlist_asset("asset-oral-glp1", "co-oral-glp1", "ORAL", 9000.0, "obesity"),
    ]

    engine = AcquirerFitEngine(
        context_provider=_StubProvider(contexts),
        integration_config=AcquirerFitIntegrationConfig(
            acquirer_profiles_path="examples/research/acquirer_profiles",
            comparable_deals_path=str(comps_path),
            top_n=10,
            require_acquisition_readiness=False,
        ),
    )
    engine.acquisition_screener._run_rnpv = lambda context: {
        "asset-oral-glp1": SimpleNamespace(
            rnpv_millions=18000.0,
            cumulative_success_probability=0.58,
            peak_sales_millions=7000.0,
        ),
        "asset-cardio": SimpleNamespace(
            rnpv_millions=9000.0,
            cumulative_success_probability=0.42,
            peak_sales_millions=4000.0,
        ),
    }[context.asset.id]

    result = engine.screen_watchlist(
        watchlist,
        acquirer_id="eli_lilly",
        snapshot_date=date(2026, 4, 5),
    )

    assert [row.asset_id for row in result.rows] == ["asset-oral-glp1", "asset-cardio"]
    assert result.rows[0].matched_therapeutic_gap == "obesity:oral_glp1"
    assert result.rows[0].fit_score == pytest.approx(1.0, abs=1e-9)


class _StubProvider:
    def __init__(self, contexts: dict[str, AssetValuationContext]) -> None:
        self._contexts = contexts

    def get_context(self, asset: WatchlistAsset) -> AssetValuationContext:
        return self._contexts[asset.asset_id]


def _watchlist_asset(
    asset_id: str,
    company_id: str,
    ticker: str,
    market_cap_millions: float,
    indication: str,
) -> WatchlistAsset:
    return WatchlistAsset(
        asset_id=asset_id,
        company_id=company_id,
        drug_name=asset_id,
        indication=indication,
        ticker=ticker,
        valuation_config=f"/tmp/{asset_id}.yaml",
        market_cap_millions=market_cap_millions,
    )


def _make_context(
    *,
    asset_id: str,
    company_id: str,
    name: str,
    therapeutic_area: TherapeuticArea,
    stage: DevelopmentStage,
    modality: Modality,
    cash_millions: float,
    mechanism_of_action: str | None,
) -> AssetValuationContext:
    asset = Asset(
        id=asset_id,
        name=name,
        indication=name,
        therapeutic_area=therapeutic_area,
        stage=stage,
        modality=modality,
        mechanism_of_action=mechanism_of_action,
        discount_rate=0.12,
    )
    company = Company(
        id=company_id,
        name=name,
        ticker=name[:4].upper(),
        cash_millions=cash_millions,
        debt_millions=0.0,
        shares_outstanding_millions=10.0,
        current_price=10.0,
    )
    trials = [
        ClinicalTrial(
            asset_id=asset_id,
            phase=TrialPhase.PHASE_3 if stage == DevelopmentStage.PHASE_3 else TrialPhase.PHASE_2,
            success_probability=0.55,
            duration_years=2.0,
            cost_millions=20.0,
            endpoint_type=EndpointType.SURROGATE_VALIDATED,
        )
    ]
    market_model = MarketModel(
        asset_id=asset_id,
        total_addressable_market_millions=1000.0,
        peak_penetration=0.15,
        years_to_peak=5,
        patent_life_years=10,
    )
    return AssetValuationContext(
        asset=asset,
        company=company,
        trials=trials,
        market_model=market_model,
    )


def _stub_rnpv(asset_id: str):
    payload = {
        "asset-eye-1": SimpleNamespace(
            rnpv_millions=900.0,
            cumulative_success_probability=0.65,
            peak_sales_millions=600.0,
        ),
        "asset-gene-1": SimpleNamespace(
            rnpv_millions=850.0,
            cumulative_success_probability=0.55,
            peak_sales_millions=600.0,
        ),
        "asset-onc-1": SimpleNamespace(
            rnpv_millions=500.0,
            cumulative_success_probability=0.35,
            peak_sales_millions=400.0,
        ),
    }
    return payload[asset_id]


def _stub_curated_pfizer_rnpv(asset_id: str):
    payload = {
        "asset-onc-adc": SimpleNamespace(
            rnpv_millions=12000.0,
            cumulative_success_probability=0.60,
            peak_sales_millions=5000.0,
        ),
        "asset-ibd-sm": SimpleNamespace(
            rnpv_millions=9000.0,
            cumulative_success_probability=0.42,
            peak_sales_millions=3500.0,
        ),
    }
    return payload[asset_id]


def _write_comps(tmp_path: Path) -> Path:
    path = tmp_path / "comparable_deals.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "deals": [
                    {
                        "target_name": "Eye Deal",
                        "indication": "wet AMD",
                        "therapeutic_area": "ophthalmology",
                        "phase_at_acquisition": "phase_3",
                        "acquirer": "Large Pharma",
                        "deal_date": "2025-01-01",
                        "ev_to_peak_sales": 1.50,
                    },
                    {
                        "target_name": "Rare Deal",
                        "indication": "hearing loss",
                        "therapeutic_area": "rare_disease",
                        "phase_at_acquisition": "phase_3",
                        "acquirer": "Large Pharma",
                        "deal_date": "2025-02-01",
                        "ev_to_peak_sales": 1.40,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return path
