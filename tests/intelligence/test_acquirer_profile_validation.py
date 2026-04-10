from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, EndpointType, TrialPhase
from bve.intelligence.acquirer_profile_validation import AcquirerProfileDealValidator
from bve.models.market_model import MarketModel
from bve.pipeline.watchlist_runner import AssetValuationContext


def test_profile_validator_ranks_actual_acquirer_top1_with_watchlist_backed_context(tmp_path: Path):
    profiles_dir = _write_profiles(tmp_path)
    deals_path = _write_deals(
        tmp_path,
        [
            {
                "target_name": "Morphic",
                "target_ticker": "MORF",
                "acquirer": "Buyer A",
                "announcement_date": "2024-07-08",
                "headline_value_millions": 3200,
                "lead_asset": "MORF-057",
                "indication": "ulcerative colitis",
                "therapeutic_area": "immunology",
                "phase_at_acquisition": "phase_2",
                "notes": "Classic oral immunology small molecule takeout.",
            }
        ],
    )
    watchlist_path = _write_watchlist(
        tmp_path,
        [
            {
                "company_id": "co-morf",
                "asset_id": "asset-morf",
                "drug_name": "MORF-057",
                "indication": "ulcerative colitis",
                "ticker": "MORF",
                "valuation_config": "/tmp/asset-morf.yaml",
                "market_cap_millions": 2100.0,
            }
        ],
    )
    contexts = {
        "asset-morf": _make_context(
            asset_id="asset-morf",
            company_id="co-morf",
            name="Morphic",
            therapeutic_area=TherapeuticArea.IMMUNOLOGY,
            stage=DevelopmentStage.PHASE_2,
            modality=Modality.SMALL_MOLECULE,
            mechanism_of_action="oral small molecule integrin inhibitor",
        )
    }

    validator = AcquirerProfileDealValidator(
        profiles_path=profiles_dir,
        deal_universe_path=deals_path,
        comparable_deals_path=_write_comps(tmp_path),
        watchlist_path=watchlist_path,
        context_provider=_StubProvider(contexts),
    )
    validator.fit_engine.acquisition_screener._run_rnpv = lambda context: SimpleNamespace(
        rnpv_millions=4200.0,
        cumulative_success_probability=0.55,
        peak_sales_millions=1800.0,
    )

    result = validator.validate()

    assert result.n_scored_deals == 1
    assert result.n_watchlist_backed == 1
    assert result.top1_hits == 1
    assert result.top1_rate == pytest.approx(1.0, abs=1e-9)
    row = result.rows[0]
    assert row.candidate_source == "watchlist_config"
    assert row.actual_acquirer_name == "Buyer A"
    assert row.actual_acquirer_rank == 1
    assert row.top1_hit is True
    assert row.actual_acquirer_matched_gap == "immunology:oral_immunology"
    assert row.modality == "oral_small_molecule"


def test_profile_validator_uses_deal_fallback_when_watchlist_target_missing(tmp_path: Path):
    profiles_dir = _write_profiles(tmp_path)
    deals_path = _write_deals(
        tmp_path,
        [
            {
                "target_name": "ADC Target",
                "target_ticker": "ADCT",
                "acquirer": "Buyer B",
                "announcement_date": "2024-01-08",
                "headline_value_millions": 2000,
                "lead_asset": "ADC-101",
                "indication": "solid tumors",
                "therapeutic_area": "oncology",
                "phase_at_acquisition": "phase_1",
                "notes": "Clinical-stage antibody-drug conjugate platform.",
            }
        ],
    )

    validator = AcquirerProfileDealValidator(
        profiles_path=profiles_dir,
        deal_universe_path=deals_path,
        comparable_deals_path=_write_comps(tmp_path),
    )

    result = validator.validate()

    assert result.n_scored_deals == 1
    assert result.n_fallback_only == 1
    row = result.rows[0]
    assert row.candidate_source == "deal_universe_fallback"
    assert row.modality == "adc"
    assert row.actual_acquirer_name == "Buyer B"
    assert row.actual_acquirer_rank == 1
    assert row.top1_hit is True
    assert row.predicted_acquirer_name == "Buyer B"


def test_profile_validator_refines_generic_watchlist_therapeutic_area_from_deal(tmp_path: Path):
    profiles_dir = _write_profiles(tmp_path)
    deals_path = _write_deals(
        tmp_path,
        [
            {
                "target_name": "Kidney Target",
                "target_ticker": "KDNY",
                "acquirer": "Buyer C",
                "announcement_date": "2024-06-01",
                "headline_value_millions": 3500,
                "lead_asset": "KD-001",
                "indication": "IgA nephropathy",
                "therapeutic_area": "nephrology",
                "phase_at_acquisition": "phase_3",
                "notes": "Late-stage kidney disease takeout.",
            }
        ],
    )
    watchlist_path = _write_watchlist(
        tmp_path,
        [
            {
                "company_id": "co-kdny",
                "asset_id": "asset-kdny",
                "drug_name": "KD-001",
                "indication": "IgA nephropathy",
                "ticker": "KDNY",
                "valuation_config": "/tmp/asset-kdny.yaml",
                "market_cap_millions": 2800.0,
            }
        ],
    )
    contexts = {
        "asset-kdny": _make_context(
            asset_id="asset-kdny",
            company_id="co-kdny",
            name="Kidney Target",
            therapeutic_area=TherapeuticArea.OTHER,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.BIOLOGIC,
            mechanism_of_action="complement inhibitor",
        )
    }

    validator = AcquirerProfileDealValidator(
        profiles_path=profiles_dir,
        deal_universe_path=deals_path,
        comparable_deals_path=_write_comps(tmp_path),
        watchlist_path=watchlist_path,
        context_provider=_StubProvider(contexts),
    )
    validator.fit_engine.acquisition_screener._run_rnpv = lambda context: SimpleNamespace(
        rnpv_millions=4200.0,
        cumulative_success_probability=0.65,
        peak_sales_millions=2200.0,
    )

    result = validator.validate()

    assert result.top1_hits == 1
    row = result.rows[0]
    assert row.candidate_source == "watchlist_config"
    assert row.actual_acquirer_name == "Buyer C"
    assert row.actual_acquirer_rank == 1
    assert row.therapeutic_area == "kidney_disease"
    assert "fallback_therapeutic_area_inference" in row.notes


def test_profile_validator_refines_watchlist_small_molecule_to_adc(tmp_path: Path):
    profiles_dir = _write_profiles(tmp_path)
    deals_path = _write_deals(
        tmp_path,
        [
            {
                "target_name": "ADC Oncology",
                "target_ticker": "ADCO",
                "acquirer": "Buyer B",
                "announcement_date": "2024-05-10",
                "headline_value_millions": 2700,
                "lead_asset": "ADC-201",
                "indication": "solid tumors",
                "therapeutic_area": "oncology",
                "phase_at_acquisition": "phase_2",
                "notes": "Clinical-stage antibody-drug conjugate oncology platform.",
            }
        ],
    )
    watchlist_path = _write_watchlist(
        tmp_path,
        [
            {
                "company_id": "co-adco",
                "asset_id": "asset-adco",
                "drug_name": "ADC-201",
                "indication": "solid tumors",
                "ticker": "ADCO",
                "valuation_config": "/tmp/asset-adco.yaml",
                "market_cap_millions": 1800.0,
            }
        ],
    )
    contexts = {
        "asset-adco": _make_context(
            asset_id="asset-adco",
            company_id="co-adco",
            name="ADC Oncology",
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            stage=DevelopmentStage.PHASE_2,
            modality=Modality.SMALL_MOLECULE,
            mechanism_of_action="topoisomerase inhibitor payload",
        )
    }

    validator = AcquirerProfileDealValidator(
        profiles_path=profiles_dir,
        deal_universe_path=deals_path,
        comparable_deals_path=_write_comps(tmp_path),
        watchlist_path=watchlist_path,
        context_provider=_StubProvider(contexts),
    )
    validator.fit_engine.acquisition_screener._run_rnpv = lambda context: SimpleNamespace(
        rnpv_millions=3100.0,
        cumulative_success_probability=0.45,
        peak_sales_millions=1500.0,
    )

    result = validator.validate()

    assert result.top1_hits == 1
    row = result.rows[0]
    assert row.candidate_source == "watchlist_config"
    assert row.actual_acquirer_name == "Buyer B"
    assert row.actual_acquirer_rank == 1
    assert row.modality == "adc"
    assert "fallback_modality_inference" in row.notes


class _StubProvider:
    def __init__(self, contexts: dict[str, AssetValuationContext]) -> None:
        self._contexts = contexts

    def get_context(self, asset) -> AssetValuationContext:
        return self._contexts[asset.asset_id]


def _write_profiles(tmp_path: Path) -> Path:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "buyer_a.yaml").write_text(
        yaml.safe_dump(
            {
                "company": "Buyer A",
                "ticker": "BYRA",
                "pipeline_gaps": [
                    {
                        "therapeutic_area": "immunology",
                        "sub_area": "oral_immunology",
                        "gap_type": "bolt_on_expansion",
                        "urgency": "high",
                        "preferred_modality": ["small_molecule", "oral_small_molecule"],
                        "budget_ceiling_millions": 5000,
                    }
                ],
                "recent_deals": [
                    {
                        "target": "Morphic",
                        "date": "2024-07-08",
                        "value_billions": 3.2,
                        "therapeutic_area": "immunology",
                        "modality": "small_molecule",
                    }
                ],
                "stated_priorities": ["Oral immunology remains a priority."],
            }
        ),
        encoding="utf-8",
    )
    (profiles_dir / "buyer_b.yaml").write_text(
        yaml.safe_dump(
            {
                "company": "Buyer B",
                "ticker": "BYRB",
                "pipeline_gaps": [
                    {
                        "therapeutic_area": "oncology",
                        "sub_area": "adc_expansion",
                        "gap_type": "platform_buildout",
                        "urgency": "high",
                        "preferred_modality": ["adc", "biologic"],
                        "budget_ceiling_millions": 8000,
                    }
                ],
                "recent_deals": [
                    {
                        "target": "ADC Target",
                        "date": "2024-01-08",
                        "value_billions": 2.0,
                        "therapeutic_area": "oncology",
                        "modality": "adc",
                    }
                ],
                "stated_priorities": ["ADC expansion remains core."],
            }
        ),
        encoding="utf-8",
    )
    (profiles_dir / "buyer_c.yaml").write_text(
        yaml.safe_dump(
            {
                "company": "Buyer C",
                "ticker": "BYRC",
                "pipeline_gaps": [
                    {
                        "therapeutic_area": "kidney_disease",
                        "sub_area": "iga_nephropathy",
                        "gap_type": "late_stage_buildout",
                        "urgency": "high",
                        "preferred_modality": ["biologic", "small_molecule"],
                        "budget_ceiling_millions": 7000,
                    }
                ],
                "recent_deals": [
                    {
                        "target": "Kidney Target",
                        "date": "2024-06-01",
                        "value_billions": 3.5,
                        "therapeutic_area": "kidney_disease",
                        "modality": "biologic",
                    }
                ],
                "stated_priorities": ["Kidney disease remains a priority."],
            }
        ),
        encoding="utf-8",
    )
    return profiles_dir


def _write_deals(tmp_path: Path, deals: list[dict[str, object]]) -> Path:
    path = tmp_path / "deal_universe.yaml"
    path.write_text(
        yaml.safe_dump({"as_of_date": "2026-04-06", "deals": deals}),
        encoding="utf-8",
    )
    return path


def _write_watchlist(tmp_path: Path, assets: list[dict[str, object]]) -> Path:
    path = tmp_path / "watchlist.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "watchlist": assets,
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_comps(tmp_path: Path) -> Path:
    path = tmp_path / "comparable_deals.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "deals": [
                    {
                        "target_name": "Example I&I Deal",
                        "indication": "ulcerative colitis",
                        "therapeutic_area": "immunology",
                        "phase_at_acquisition": "phase_2",
                        "acquirer": "Buyer A",
                        "deal_date": "2024-07-08",
                        "ev_to_peak_sales": 1.5,
                    },
                    {
                        "target_name": "Example ADC Deal",
                        "indication": "solid tumors",
                        "therapeutic_area": "oncology",
                        "phase_at_acquisition": "phase_1",
                        "acquirer": "Buyer B",
                        "deal_date": "2024-01-08",
                        "ev_to_peak_sales": 1.2,
                    },
                    {
                        "target_name": "Example Kidney Deal",
                        "indication": "IgA nephropathy",
                        "therapeutic_area": "kidney_disease",
                        "phase_at_acquisition": "phase_3",
                        "acquirer": "Buyer C",
                        "deal_date": "2024-06-01",
                        "ev_to_peak_sales": 1.8,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def _make_context(
    *,
    asset_id: str,
    company_id: str,
    name: str,
    therapeutic_area: TherapeuticArea,
    stage: DevelopmentStage,
    modality: Modality,
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
        cash_millions=100.0,
        debt_millions=0.0,
        shares_outstanding_millions=10.0,
        current_price=10.0,
    )
    trials = [
        ClinicalTrial(
            asset_id=asset_id,
            phase=TrialPhase.PHASE_2,
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
