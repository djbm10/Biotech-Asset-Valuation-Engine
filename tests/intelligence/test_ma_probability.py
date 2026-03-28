from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import yaml

from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, EndpointType, TrialPhase
from bve.intelligence.catalyst_calendar import CatalystEvent, CatalystType
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.ma_probability import MAProbabilityConfig, MAProbabilityScanner
from bve.models.market_model import MarketModel
from bve.pipeline.watchlist_runner import AssetValuationContext, WatchlistAsset


def test_ma_probability_scanner_scores_and_ranks_watchlist(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        store.upsert_catalyst_event(
            CatalystEvent(
                asset_id="asset-eye-1",
                company_id="co-eye-1",
                catalyst_type=CatalystType.TRIAL_READOUT,
                expected_date=date(2027, 1, 15),
                date_confidence="exact",
                source="unit_test",
                description="Retina readout",
                signal_strength=1.2,
            )
        )
        profiles_path = _write_profiles(tmp_path)
        comps_path = _write_comps(tmp_path)
        vulnerability_path = _write_vulnerability_signals(tmp_path)
        contexts = {
            "asset-eye-1": _make_context(
                asset_id="asset-eye-1",
                company_id="co-eye-1",
                name="RetinaCo",
                therapeutic_area=TherapeuticArea.OPHTHALMOLOGY,
                stage=DevelopmentStage.PHASE_3,
                modality=Modality.BIOLOGIC,
                cash_millions=20.0,
                burn_rate_millions_per_quarter=20.0,
            ),
            "asset-onc-1": _make_context(
                asset_id="asset-onc-1",
                company_id="co-onc-1",
                name="OncoCo",
                therapeutic_area=TherapeuticArea.ONCOLOGY,
                stage=DevelopmentStage.PHASE_3,
                modality=Modality.SMALL_MOLECULE,
                cash_millions=200.0,
                burn_rate_millions_per_quarter=10.0,
            ),
        }
        watchlist = [
            _watchlist_asset("asset-eye-1", "co-eye-1", "EYE1", 500.0, "wet AMD"),
            _watchlist_asset("asset-onc-1", "co-onc-1", "ONC1", 600.0, "solid tumors"),
        ]

        scanner = MAProbabilityScanner(
            knowledge_store=store,
            context_provider=_StubProvider(contexts),
            config=MAProbabilityConfig(
                top_n=10,
                alert_threshold=0.70,
                vulnerability_signals_path=str(vulnerability_path),
                fit_integration_config={
                    "acquirer_profiles_path": str(profiles_path),
                    "comparable_deals_path": str(comps_path),
                    "top_n": 10,
                    "require_acquisition_readiness": True,
                },
            ),
        )
        scanner.fit_engine.acquisition_screener._run_rnpv = lambda context: _stub_rnpv(context.asset.id)

        result = scanner.scan_watchlist(
            watchlist,
            snapshot_date=date(2026, 3, 24),
        )

        assert result.n_assets == 2
        assert result.n_above_alert_threshold == 1
        assert [row.asset_id for row in result.rows] == ["asset-eye-1", "asset-onc-1"]
        assert result.rows[0].best_acquirer_id == "regeneron"
        assert result.rows[0].cash_runway_risk_level == "high"
        assert result.rows[0].target_signal_ids == ["asset-eye-1_board_change"]
        assert result.rows[0].above_alert_threshold is True
        assert result.rows[1].best_acquirer_id == "oncobuyer"
        assert result.rows[1].above_alert_threshold is False
    finally:
        store.close()


def test_ma_probability_scanner_keeps_strategic_fit_separate_from_valuation(tmp_path: Path):
    profiles_path = _write_profiles(tmp_path, include_onco=False)
    comps_path = _write_comps(tmp_path)
    vulnerability_path = _write_vulnerability_signals(tmp_path, include_target_signals=False)
    contexts = {
        "asset-cheap": _make_context(
            asset_id="asset-cheap",
            company_id="co-cheap",
            name="RetinaCheap",
            therapeutic_area=TherapeuticArea.OPHTHALMOLOGY,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.BIOLOGIC,
            cash_millions=80.0,
            burn_rate_millions_per_quarter=10.0,
        ),
        "asset-rich": _make_context(
            asset_id="asset-rich",
            company_id="co-rich",
            name="RetinaRich",
            therapeutic_area=TherapeuticArea.OPHTHALMOLOGY,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.BIOLOGIC,
            cash_millions=80.0,
            burn_rate_millions_per_quarter=10.0,
        ),
    }
    watchlist = [
        _watchlist_asset("asset-cheap", "co-cheap", "CHEP", 500.0, "wet AMD"),
        _watchlist_asset("asset-rich", "co-rich", "RICH", 1000.0, "wet AMD"),
    ]
    scanner = MAProbabilityScanner(
        context_provider=_StubProvider(contexts),
        config=MAProbabilityConfig(
            top_n=10,
            vulnerability_signals_path=str(vulnerability_path),
            fit_integration_config={
                "acquirer_profiles_path": str(profiles_path),
                "comparable_deals_path": str(comps_path),
                "top_n": 10,
                "require_acquisition_readiness": True,
            },
        ),
    )
    scanner.fit_engine.acquisition_screener._run_rnpv = lambda context: SimpleNamespace(
        rnpv_millions=900.0,
        cumulative_success_probability=0.65,
        peak_sales_millions=600.0,
    )

    result = scanner.scan_watchlist(watchlist, snapshot_date=date(2026, 3, 24))
    by_asset = {row.asset_id: row for row in result.rows}

    assert by_asset["asset-cheap"].strategic_fit_score == by_asset["asset-rich"].strategic_fit_score
    assert (
        by_asset["asset-cheap"].valuation_discount_score
        > by_asset["asset-rich"].valuation_discount_score
    )
    assert by_asset["asset-cheap"].p_acquisition > by_asset["asset-rich"].p_acquisition


def test_ma_probability_scanner_persists_snapshots_and_emits_monitor_alerts(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        profiles_path = _write_profiles(tmp_path, include_onco=False)
        comps_path = _write_comps(tmp_path)
        vulnerability_path = _write_vulnerability_signals(tmp_path, include_target_signals=False)
        contexts = {
            "asset-eye-1": _make_context(
                asset_id="asset-eye-1",
                company_id="co-eye-1",
                name="RetinaCo",
                therapeutic_area=TherapeuticArea.OPHTHALMOLOGY,
                stage=DevelopmentStage.PHASE_3,
                modality=Modality.BIOLOGIC,
                cash_millions=80.0,
                burn_rate_millions_per_quarter=10.0,
            ),
            "asset-onc-1": _make_context(
                asset_id="asset-onc-1",
                company_id="co-onc-1",
                name="RetinaPeer",
                therapeutic_area=TherapeuticArea.OPHTHALMOLOGY,
                stage=DevelopmentStage.PHASE_3,
                modality=Modality.BIOLOGIC,
                cash_millions=80.0,
                burn_rate_millions_per_quarter=10.0,
            ),
        }
        watchlist = [
            _watchlist_asset("asset-eye-1", "co-eye-1", "EYE1", 900.0, "wet AMD"),
            _watchlist_asset("asset-onc-1", "co-onc-1", "EYE2", 500.0, "wet AMD"),
        ]
        scanner = MAProbabilityScanner(
            knowledge_store=store,
            context_provider=_StubProvider(contexts),
            config=MAProbabilityConfig(
                top_n=10,
                alert_threshold=0.70,
                persist_daily_snapshots=True,
                monitor={
                    "top_n": 1,
                    "alert_window_days": 1,
                },
                vulnerability_signals_path=str(vulnerability_path),
                fit_integration_config={
                    "acquirer_profiles_path": str(profiles_path),
                    "comparable_deals_path": str(comps_path),
                    "top_n": 10,
                    "require_acquisition_readiness": True,
                },
            ),
        )

        scanner.fit_engine.acquisition_screener._run_rnpv = lambda context: {
            "asset-eye-1": SimpleNamespace(
                rnpv_millions=500.0,
                cumulative_success_probability=0.65,
                peak_sales_millions=600.0,
            ),
            "asset-onc-1": SimpleNamespace(
                rnpv_millions=900.0,
                cumulative_success_probability=0.65,
                peak_sales_millions=600.0,
            ),
        }[context.asset.id]
        first = scanner.scan_watchlist(
            watchlist,
            snapshot_date=date(2026, 3, 24),
            run_id="scan-1",
        )

        scanner.fit_engine.acquisition_screener._run_rnpv = lambda context: {
            "asset-eye-1": SimpleNamespace(
                rnpv_millions=2500.0,
                cumulative_success_probability=0.65,
                peak_sales_millions=600.0,
            ),
            "asset-onc-1": SimpleNamespace(
                rnpv_millions=900.0,
                cumulative_success_probability=0.65,
                peak_sales_millions=600.0,
            ),
        }[context.asset.id]
        second = scanner.scan_watchlist(
            watchlist,
            snapshot_date=date(2026, 3, 25),
            run_id="scan-2",
        )
        duplicate = scanner.scan_watchlist(
            watchlist,
            snapshot_date=date(2026, 3, 25),
            run_id="scan-3",
        )

        emitted_types = {record.event_type for record in second.alerts_emitted}

        assert first.snapshots_written == 2
        assert first.alerts_emitted == []
        assert second.snapshots_written == 2
        assert second.reference_snapshot_date == "2026-03-24"
        assert second.rows[0].asset_id == "asset-eye-1"
        assert emitted_types == {
            "ma_probability_threshold_cross",
            "ma_probability_top_n_entry",
        }
        assert len(store.get_opportunity_alerts(limit=10)) == 2
        assert duplicate.alerts_emitted == []
        assert duplicate.alerts_suppressed_as_duplicate == 2
    finally:
        store.close()


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
    burn_rate_millions_per_quarter: float,
) -> AssetValuationContext:
    asset = Asset(
        id=asset_id,
        name=name,
        indication=name,
        therapeutic_area=therapeutic_area,
        stage=stage,
        modality=modality,
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
        burn_rate_millions_per_quarter=burn_rate_millions_per_quarter,
    )
    trials = [
        ClinicalTrial(
            asset_id=asset_id,
            phase=TrialPhase.PHASE_3,
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
        "asset-onc-1": SimpleNamespace(
            rnpv_millions=500.0,
            cumulative_success_probability=0.55,
            peak_sales_millions=400.0,
        ),
    }
    return payload[asset_id]


def _write_profiles(tmp_path: Path, *, include_onco: bool = True) -> Path:
    profiles = [_profile("regeneron", "ophthalmology", "fully_human_antibody", "Regeneron Pharmaceuticals")]
    if include_onco:
        profiles.append(_profile("oncobuyer", "oncology", "small_molecule", "Onco Buyer"))
    path = tmp_path / "pipeline_gaps.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "as_of_date": "2026-03-24",
                "acquirers": profiles,
            }
        ),
        encoding="utf-8",
    )
    return path


def _profile(acquirer_id: str, therapeutic_area: str, modality: str, company_name: str) -> dict[str, object]:
    return {
        "acquirer_id": acquirer_id,
        "company_name": company_name,
        "ticker": acquirer_id[:4].upper(),
        "profile_as_of": "2026-03-24",
        "source_notes": "Test profile",
        "therapeutic_area_gaps": [
            {
                "therapeutic_area": therapeutic_area,
                "exposure_type": "strategic_expansion",
                "exposure_level": "high",
                "rationale": "Test rationale",
                "source_refs": [_source_ref()],
            }
        ],
        "preferred_modalities": [
            {
                "modality": modality,
                "preference_strength": "high",
                "rationale": "Test rationale",
                "source_refs": [_source_ref()],
            }
        ],
        "strategic_priorities": [
            {
                "priority": therapeutic_area,
                "priority_strength": "high",
                "source_refs": [_source_ref()],
            }
        ],
        "recent_deal_history": [
            {
                "deal_name": "Example deal",
                "status": "announced",
                "announcement_date": "2025-06-01",
                "deal_type": "license",
                "therapeutic_area": therapeutic_area,
                "modality": modality,
                "stage_context": "phase_3",
                "upfront_millions": 100.0,
                "implied_value_band_millions_low": 100.0,
                "implied_value_band_millions_high": 500.0,
                "source_url": "https://example.com/deal",
            }
        ],
        "budget": {
            "as_of_date": "2025-12-31",
            "cash_and_marketable_securities_millions": 5000.0,
            "long_term_debt_millions": 0.0,
            "net_cash_millions": 5000.0,
            "capacity_notes": "ample budget",
            "source_refs": [_source_ref()],
        },
    }


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
                        "phase_at_acquisition": "phase_3",
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


def _write_vulnerability_signals(
    tmp_path: Path,
    *,
    include_target_signals: bool = True,
) -> Path:
    payload = {
        "as_of_date": "2026-03-24",
        "schema_version": "v1",
        "source_policy": {
            "computed_signals": [
                {
                    "signal_name": "cash_runway_pressure",
                    "source_module": "src/bve/intelligence/capital_structure.py",
                    "note": "Dynamic at scan time.",
                }
            ],
            "manual_signal_types": [
                "insider_activity",
                "board_changes",
                "same_space_external_deal",
            ],
            "staleness_windows_days": {
                "insider_activity": 90,
                "board_changes": 180,
                "same_space_external_deal": 180,
            },
        },
        "external_deal_activity": [
            {
                "signal_id": "ophth_same_space_deal",
                "signal_type": "same_space_external_deal",
                "deal_type": "licensing",
                "event_date": "2026-02-01",
                "therapeutic_area": "ophthalmology",
                "acquirer": "Regeneron Pharmaceuticals",
                "counterparty": "External Partner",
                "signal_strength": "medium",
                "rationale": "External ophthalmology deal pressure.",
                "source_refs": [_source_ref()],
            }
        ],
        "target_signals": [
            {
                "signal_id": "asset-eye-1_board_change",
                "signal_type": "board_changes",
                "asset_id": "asset-eye-1",
                "company_id": "co-eye-1",
                "ticker": "EYE1",
                "event_date": "2026-03-01",
                "signal_strength": "high",
                "signal_effect": "increase",
                "headline": "Board refresh",
                "rationale": "Board change can raise strategic optionality.",
                "source_refs": [_source_ref()],
            }
        ]
        if include_target_signals
        else [],
    }
    path = tmp_path / "vulnerability_signals.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def _source_ref() -> dict[str, str]:
    return {
        "source_date": "2026-03-01",
        "source_type": "press_release",
        "source_title": "Example source",
        "source_url": "https://example.com/source",
        "note": "Example note",
    }
