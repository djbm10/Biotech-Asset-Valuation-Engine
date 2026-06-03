from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import yaml

from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, EndpointType, TrialPhase
from bve.intelligence.acquirer_fit import AcquirerFitEngine, AcquirerFitIntegrationConfig
from bve.intelligence.acquisition_memo import AcquisitionMemoGenerator
from bve.models.market_model import MarketModel
from bve.pipeline.watchlist_runner import AssetValuationContext, WatchlistAsset


def test_acquisition_memo_generator_reuses_bd_memo_and_appends_addendum(tmp_path: Path):
    generator, watchlist = _build_generator(tmp_path)

    memos = generator.generate_for_watchlist(
        watchlist,
        acquirer_id="regeneron",
        snapshot_date=date(2026, 3, 24),
        top_n=1,
    )

    assert len(memos) == 1
    memo = memos[0]
    assert "# RetinaAsset: BD Acquisition Analysis" in memo.rendered_markdown
    assert "## 9. Acquirer Fit Addendum" in memo.rendered_markdown
    assert "Regeneron Pharmaceuticals" in memo.rendered_markdown
    assert "Indicative Deal Structure" in memo.rendered_markdown
    assert memo.present_value_of_terms_millions > 0
    assert memo.to_memo_record().memo_type == "acquisition_memo"


def test_acquisition_memo_terms_plan_for_phase_2_is_milestone_weighted(tmp_path: Path):
    generator, watchlist = _build_generator(tmp_path)
    fit_result = generator.fit_engine.screen_watchlist(
        watchlist,
        acquirer_id="regeneron",
        snapshot_date=date(2026, 3, 24),
        top_n=2,
    )
    phase_2_row = next(row for row in fit_result.rows if row.asset_id == "asset-onc-1")

    terms = generator.plan_terms(phase_2_row)

    assert terms.structure_type == "structured_acquisition_with_development_milestones"
    assert terms.upfront_millions < terms.reference_enterprise_value_millions
    assert terms.milestone_total_millions > 0
    assert any(m.trigger == "phase_success" for m in terms.milestones)


def test_acquisition_memo_generator_supports_curated_pfizer_profile(tmp_path: Path):
    comps_path = _write_comps(tmp_path)
    contexts = {
        "asset-onc-adc": _make_context(
            asset_id="asset-onc-adc",
            company_id="co-onc-adc",
            asset_name="BreastADC",
            company_name="OncoCo",
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.ADC,
            cash_millions=100.0,
            market_cap_millions=9000.0,
        ),
    }
    watchlist = [
        _watchlist_asset("asset-onc-adc", "co-onc-adc", "ADC1", 9000.0, "breast cancer"),
    ]
    fit_engine = AcquirerFitEngine(
        context_provider=_StubProvider(contexts),
        integration_config=AcquirerFitIntegrationConfig(
            acquirer_profiles_path="examples/research/acquirer_profiles/pfizer.yaml",
            comparable_deals_path=str(comps_path),
            top_n=10,
            require_acquisition_readiness=False,
        ),
    )
    fit_engine.acquisition_screener._run_rnpv = lambda context: _stub_pfizer_rnpv(context.asset.id)
    generator = AcquisitionMemoGenerator(fit_engine=fit_engine)

    memos = generator.generate_for_watchlist(
        watchlist,
        acquirer_id="pfizer",
        snapshot_date=date(2026, 4, 5),
        top_n=1,
    )

    assert len(memos) == 1
    memo = memos[0]
    assert "Pfizer" in memo.rendered_markdown
    assert "oncology:breast_cancer" in memo.rendered_markdown
    assert "Indicative Deal Structure" in memo.rendered_markdown
    assert memo.fit_score == 1.0


class _StubProvider:
    def __init__(self, contexts: dict[str, AssetValuationContext]) -> None:
        self._contexts = contexts

    def get_context(self, asset: WatchlistAsset) -> AssetValuationContext:
        return self._contexts[asset.asset_id]


def _build_generator(tmp_path: Path):
    comps_path = _write_comps(tmp_path)
    contexts = {
        "asset-eye-1": _make_context(
            asset_id="asset-eye-1",
            company_id="co-eye-1",
            asset_name="RetinaAsset",
            company_name="RetinaCo",
            therapeutic_area=TherapeuticArea.OPHTHALMOLOGY,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.BIOLOGIC,
            cash_millions=50.0,
            market_cap_millions=500.0,
        ),
        "asset-onc-1": _make_context(
            asset_id="asset-onc-1",
            company_id="co-onc-1",
            asset_name="OncoAsset",
            company_name="OncoCo",
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            stage=DevelopmentStage.PHASE_2,
            modality=Modality.SMALL_MOLECULE,
            cash_millions=40.0,
            market_cap_millions=600.0,
        ),
    }
    watchlist = [
        _watchlist_asset("asset-eye-1", "co-eye-1", "EYE1", 500.0, "wet AMD"),
        _watchlist_asset("asset-onc-1", "co-onc-1", "ONC1", 600.0, "solid tumors"),
    ]
    fit_engine = AcquirerFitEngine(
        context_provider=_StubProvider(contexts),
        integration_config=AcquirerFitIntegrationConfig(
            acquirer_profiles_path="research/mna/pipeline_gaps.yaml",
            comparable_deals_path=str(comps_path),
            top_n=10,
            require_acquisition_readiness=True,
        ),
    )
    fit_engine.acquisition_screener._run_rnpv = lambda context: _stub_rnpv(context.asset.id)
    generator = AcquisitionMemoGenerator(fit_engine=fit_engine)
    return generator, watchlist


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
    asset_name: str,
    company_name: str,
    therapeutic_area: TherapeuticArea,
    stage: DevelopmentStage,
    modality: Modality,
    cash_millions: float,
    market_cap_millions: float,
) -> AssetValuationContext:
    asset = Asset(
        id=asset_id,
        name=asset_name,
        indication="Indication X",
        therapeutic_area=therapeutic_area,
        stage=stage,
        modality=modality,
        discount_rate=0.12,
    )
    company = Company(
        id=company_id,
        name=company_name,
        ticker=company_name[:4].upper(),
        cash_millions=cash_millions,
        debt_millions=0.0,
        shares_outstanding_millions=10.0,
        current_price=market_cap_millions / 10.0,
        market_cap_millions=market_cap_millions,
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
        total_addressable_market_millions=1200.0,
        peak_penetration=0.18,
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
        "asset-onc-1": SimpleNamespace(
            rnpv_millions=500.0,
            cumulative_success_probability=0.35,
            peak_sales_millions=400.0,
        ),
    }
    return payload[asset_id]


def _stub_pfizer_rnpv(asset_id: str):
    payload = {
        "asset-onc-adc": SimpleNamespace(
            rnpv_millions=12000.0,
            cumulative_success_probability=0.60,
            peak_sales_millions=5000.0,
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
                        "target_name": "Onco Deal",
                        "indication": "solid tumors",
                        "therapeutic_area": "oncology",
                        "phase_at_acquisition": "phase_2",
                        "acquirer": "Large Pharma",
                        "deal_date": "2025-02-01",
                        "ev_to_peak_sales": 1.25,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return path
