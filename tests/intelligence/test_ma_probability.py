from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, EndpointType, TrialPhase
from bve.intelligence.catalyst_calendar import CatalystEvent, CatalystType
from bve.intelligence.ma_calibration import (
    MALogisticCoefficient,
    MALogisticFitResult,
    MALogisticMetrics,
)
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.ma_probability import (
    MAProbabilityConfig,
    MAProbabilityScanner,
    TargetabilityFilter,
)
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
        assert result.n_above_alert_threshold == 2
        assert [row.asset_id for row in result.rows] == ["asset-eye-1", "asset-onc-1"]
        assert result.rows[0].best_acquirer_id == "regeneron"
        assert result.rows[0].cash_runway_risk_level == "high"
        assert result.rows[0].target_signal_ids == ["asset-eye-1_board_change"]
        assert result.rows[0].above_alert_threshold is True
        assert result.rows[1].best_acquirer_id == "oncobuyer"
        assert result.rows[1].above_alert_threshold is True
    finally:
        store.close()


def test_ma_probability_scanner_excludes_company_recency_gate_failures(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        _write_company_sotp_snapshot(
            store,
            ticker="EYE1",
            snapshot_date=date(2026, 3, 20),
            passes_gate=False,
            action_policy="needs_manual_review",
            action_reason="balance_sheet_recency_gate_failed",
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
        }
        watchlist = [
            _watchlist_asset("asset-eye-1", "co-eye-1", "EYE1", 500.0, "wet AMD"),
        ]
        scanner = MAProbabilityScanner(
            knowledge_store=store,
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
        scanner.fit_engine.acquisition_screener._run_rnpv = lambda context: _stub_rnpv(context.asset.id)

        result = scanner.scan_watchlist(
            watchlist,
            snapshot_date=date(2026, 3, 24),
        )

        assert result.rows == []
        assert result.n_assets == 0
        assert result.n_excluded == 1
        assert result.excluded_assets[0].reasons == ["company_recency_gate_failed:2026-03-20"]
    finally:
        store.close()


def test_ma_probability_scanner_attaches_company_snapshot_metadata(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        _write_company_sotp_snapshot(
            store,
            ticker="EYE1",
            snapshot_date=date(2026, 3, 20),
            passes_gate=True,
            action_policy="watch",
            action_reason="ranked_discount_above_watch_threshold:1.25x",
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
        }
        watchlist = [
            _watchlist_asset("asset-eye-1", "co-eye-1", "EYE1", 500.0, "wet AMD"),
        ]
        scanner = MAProbabilityScanner(
            knowledge_store=store,
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
        scanner.fit_engine.acquisition_screener._run_rnpv = lambda context: _stub_rnpv(context.asset.id)

        result = scanner.scan_watchlist(
            watchlist,
            snapshot_date=date(2026, 3, 24),
        )

        assert len(result.rows) == 1
        assert result.rows[0].company_action_policy == "watch"
        assert result.rows[0].company_action_reason == "ranked_discount_above_watch_threshold:1.25x"
        assert result.rows[0].company_snapshot_date == date(2026, 3, 20)
        assert result.rows[0].company_recency_gate_failed is False
    finally:
        store.close()


def test_ma_probability_scanner_inverts_valuation_discount_in_v11(tmp_path: Path):
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
            score_version="v1.1",
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
    assert by_asset["asset-cheap"].p_acquisition < by_asset["asset-rich"].p_acquisition


def test_ma_probability_scanner_default_v12_uses_strategic_fit_only(tmp_path: Path):
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
    }
    watchlist = [
        _watchlist_asset("asset-eye-1", "co-eye-1", "EYE1", 500.0, "wet AMD"),
    ]
    scanner = MAProbabilityScanner(
        context_provider=_StubProvider(contexts),
        config=MAProbabilityConfig(
            top_n=15,
            vulnerability_signals_path=str(vulnerability_path),
            fit_integration_config={
                "acquirer_profiles_path": str(profiles_path),
                "comparable_deals_path": str(comps_path),
                "top_n": 15,
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
    row = result.rows[0]

    expected = round(row.strategic_fit_score, 6)
    assert row.score_version == "v1.2"
    assert row.mna_probability_score == pytest.approx(expected, abs=1e-9)
    assert row.p_acquisition == pytest.approx(expected, abs=1e-9)


def test_ma_probability_scanner_v13_adds_scarcity_on_top_of_strategic_fit(tmp_path: Path):
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
            mechanism_of_action="VEGF inhibitor",
            cash_millions=80.0,
            burn_rate_millions_per_quarter=10.0,
        ),
    }
    watchlist = [
        _watchlist_asset("asset-eye-1", "co-eye-1", "EYE1", 500.0, "wet AMD"),
    ]
    scanner = MAProbabilityScanner(
        context_provider=_StubProvider(contexts),
        config=MAProbabilityConfig(
            score_version="v1.3",
            top_n=15,
            vulnerability_signals_path=str(vulnerability_path),
            fit_integration_config={
                "acquirer_profiles_path": str(profiles_path),
                "comparable_deals_path": str(comps_path),
                "top_n": 15,
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
    row = result.rows[0]

    expected = round((row.strategic_fit_score * 0.85) + (row.scarcity_score * 0.15), 6)
    assert row.score_version == "v1.3"
    assert row.scarcity_peer_count == 0
    assert row.scarcity_bucket == "very_high"
    assert row.mna_probability_score == pytest.approx(expected, abs=1e-9)


def test_ma_probability_scanner_v11_uses_inverted_valuation_formula(tmp_path: Path):
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
    }
    watchlist = [
        _watchlist_asset("asset-eye-1", "co-eye-1", "EYE1", 500.0, "wet AMD"),
    ]
    scanner = MAProbabilityScanner(
        context_provider=_StubProvider(contexts),
        config=MAProbabilityConfig(
            score_version="v1.1",
            top_n=15,
            vulnerability_signals_path=str(vulnerability_path),
            fit_integration_config={
                "acquirer_profiles_path": str(profiles_path),
                "comparable_deals_path": str(comps_path),
                "top_n": 15,
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
    row = result.rows[0]

    expected = round(
        ((1.0 - row.valuation_discount_score) * 0.30)
        + (row.strategic_fit_score * 0.30)
        + (row.de_risking_stage_score * 0.25)
        + (row.capital_vulnerability_score * 0.15),
        6,
    )
    assert row.score_version == "v1.1"
    assert row.mna_probability_score == pytest.approx(expected, abs=1e-9)


def test_ma_probability_scanner_scores_scarcity_from_same_indication_mechanism_peers(tmp_path: Path):
    profiles_path = _write_profiles(tmp_path, include_onco=False)
    comps_path = _write_comps(tmp_path)
    vulnerability_path = _write_vulnerability_signals(tmp_path, include_target_signals=False)
    contexts = {
        "asset-a": _make_context(
            asset_id="asset-a",
            company_id="co-a",
            name="WetAmdA",
            therapeutic_area=TherapeuticArea.OPHTHALMOLOGY,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.BIOLOGIC,
            mechanism_of_action="VEGF inhibitor",
            cash_millions=80.0,
            burn_rate_millions_per_quarter=10.0,
        ),
        "asset-b": _make_context(
            asset_id="asset-b",
            company_id="co-b",
            name="WetAmdB",
            therapeutic_area=TherapeuticArea.OPHTHALMOLOGY,
            stage=DevelopmentStage.PHASE_2,
            modality=Modality.BIOLOGIC,
            mechanism_of_action="VEGF inhibitor",
            cash_millions=80.0,
            burn_rate_millions_per_quarter=10.0,
        ),
        "asset-c": _make_context(
            asset_id="asset-c",
            company_id="co-c",
            name="WetAmdC",
            therapeutic_area=TherapeuticArea.OPHTHALMOLOGY,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.BIOLOGIC,
            mechanism_of_action="VEGF inhibitor",
            cash_millions=80.0,
            burn_rate_millions_per_quarter=10.0,
        ),
        "asset-d": _make_context(
            asset_id="asset-d",
            company_id="co-d",
            name="WetAmdD",
            therapeutic_area=TherapeuticArea.OPHTHALMOLOGY,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.BIOLOGIC,
            mechanism_of_action="Complement inhibitor",
            cash_millions=80.0,
            burn_rate_millions_per_quarter=10.0,
        ),
    }
    watchlist = [
        _watchlist_asset("asset-a", "co-a", "A", 500.0, "wet AMD"),
        _watchlist_asset("asset-b", "co-b", "B", 500.0, "wet AMD"),
        _watchlist_asset("asset-c", "co-c", "C", 500.0, "wet AMD"),
        _watchlist_asset("asset-d", "co-d", "D", 500.0, "wet AMD"),
    ]
    scanner = MAProbabilityScanner(
        context_provider=_StubProvider(contexts),
        config=MAProbabilityConfig(
            score_version="v1.3",
            top_n=15,
            vulnerability_signals_path=str(vulnerability_path),
            fit_integration_config={
                "acquirer_profiles_path": str(profiles_path),
                "comparable_deals_path": str(comps_path),
                "top_n": 15,
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

    assert by_asset["asset-a"].scarcity_peer_count == 2
    assert by_asset["asset-a"].scarcity_bucket == "high"
    assert by_asset["asset-a"].scarcity_score == pytest.approx(0.8, abs=1e-9)
    assert by_asset["asset-d"].scarcity_peer_count == 0
    assert by_asset["asset-d"].scarcity_bucket == "very_high"
    assert by_asset["asset-d"].scarcity_score == pytest.approx(1.0, abs=1e-9)


def test_ma_probability_scanner_preserves_legacy_v10_weighting_formula(tmp_path: Path):
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
    }
    watchlist = [
        _watchlist_asset("asset-eye-1", "co-eye-1", "EYE1", 500.0, "wet AMD"),
    ]
    scanner = MAProbabilityScanner(
        context_provider=_StubProvider(contexts),
        config=MAProbabilityConfig(
            score_version="v1.0",
            top_n=15,
            vulnerability_signals_path=str(vulnerability_path),
            fit_integration_config={
                "acquirer_profiles_path": str(profiles_path),
                "comparable_deals_path": str(comps_path),
                "top_n": 15,
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
    row = result.rows[0]

    expected = round(
        (row.valuation_discount_score * 0.30)
        + (row.strategic_fit_score * 0.30)
        + (row.de_risking_stage_score * 0.25)
        + (row.capital_vulnerability_score * 0.15),
        6,
    )
    assert row.score_version == "v1.0"
    assert row.mna_probability_score == pytest.approx(expected, abs=1e-9)


def test_ma_probability_scan_populates_estimated_deal_value_range(tmp_path: Path):
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
    }
    watchlist = [
        _watchlist_asset("asset-eye-1", "co-eye-1", "EYE1", 500.0, "wet AMD"),
    ]
    scanner = MAProbabilityScanner(
        context_provider=_StubProvider(contexts),
        config=MAProbabilityConfig(
            top_n=15,
            vulnerability_signals_path=str(vulnerability_path),
            fit_integration_config={
                "acquirer_profiles_path": str(profiles_path),
                "comparable_deals_path": str(comps_path),
                "top_n": 15,
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
    row = result.rows[0]

    assert row.estimated_deal_value_low_millions is not None
    assert row.estimated_deal_value_high_millions is not None
    assert row.estimated_deal_value_high_millions >= row.estimated_deal_value_low_millions
    assert row.estimated_deal_value_source in {"recent_deal_history", "comparable_deals", "ev_to_model_rnpv"}


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
        assert emitted_types == set()
        assert len(store.get_opportunity_alerts(limit=10)) == 0
        assert duplicate.alerts_emitted == []
        assert duplicate.alerts_suppressed_as_duplicate == 0
    finally:
        store.close()


def test_ma_probability_snapshot_write_replaces_stale_rows_for_same_date(tmp_path: Path):
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
            "asset-eye-2": _make_context(
                asset_id="asset-eye-2",
                company_id="co-eye-2",
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
            _watchlist_asset("asset-eye-2", "co-eye-2", "EYE2", 500.0, "wet AMD"),
        ]
        common_config = {
            "top_n": 10,
            "persist_daily_snapshots": True,
            "enable_monitor": False,
            "vulnerability_signals_path": str(vulnerability_path),
            "fit_integration_config": {
                "acquirer_profiles_path": str(profiles_path),
                "comparable_deals_path": str(comps_path),
                "top_n": 10,
                "require_acquisition_readiness": True,
            },
        }
        scanner = MAProbabilityScanner(
            knowledge_store=store,
            context_provider=_StubProvider(contexts),
            config=MAProbabilityConfig(**common_config),
        )
        scanner.fit_engine.acquisition_screener._run_rnpv = lambda context: SimpleNamespace(
            rnpv_millions=900.0,
            cumulative_success_probability=0.65,
            peak_sales_millions=600.0,
        )

        snapshot_date = date(2026, 3, 24)
        first = scanner.scan_watchlist(watchlist, snapshot_date=snapshot_date, run_id="scan-1")
        first_snapshots = scanner.snapshot_store.list_snapshots(
            start_date=snapshot_date,
            end_date=snapshot_date,
        )

        rules_path = _write_targetability_rules(tmp_path, excluded_tickers=["EYE2"])
        filtered_scanner = MAProbabilityScanner(
            knowledge_store=store,
            context_provider=_StubProvider(contexts),
            config=MAProbabilityConfig(
                **common_config,
                targetability_rules_path=str(rules_path),
            ),
        )
        filtered_scanner.fit_engine.acquisition_screener._run_rnpv = scanner.fit_engine.acquisition_screener._run_rnpv
        second = filtered_scanner.scan_watchlist(
            watchlist,
            snapshot_date=snapshot_date,
            run_id="scan-2",
        )
        second_snapshots = filtered_scanner.snapshot_store.list_snapshots(
            start_date=snapshot_date,
            end_date=snapshot_date,
        )

        assert first.snapshots_written == 2
        assert len(first_snapshots) == 2
        assert second.snapshots_written == 1
        assert second.n_excluded == 1
        assert [item.ticker for item in second_snapshots] == ["EYE1"]
    finally:
        store.close()


def test_ma_probability_scanner_uses_stored_screen_context_for_historical_snapshots(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        profiles_path = _write_profiles(tmp_path, include_onco=False)
        comps_path = _write_comps(tmp_path)
        vulnerability_path = _write_vulnerability_signals(tmp_path, include_target_signals=False)
        store.write_screen_snapshots(
            [
                SimpleNamespace(
                    ticker="EYE1",
                    data_date=date(2026, 3, 24),
                    program_label="Retina program",
                    stage="phase_2",
                    ta="ophthalmology",
                    model_pos=0.55,
                    implied_pos=0.33,
                    spread_pp=22.0,
                    rnpv_millions=900.0,
                    ev_millions=300.0,
                    acquisition_discount_pct=200.0,
                    next_catalyst="Stored catalyst",
                    catalyst_date=date(2026, 5, 8),
                    days_to_catalyst=45,
                    single_asset=True,
                    approximation_warning=None,
                    thesis_strength=0.7,
                    market_exceeds_model=False,
                    config_quality="gold",
                )
            ]
        )
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
        }
        watchlist = [
            _watchlist_asset("asset-eye-1", "co-eye-1", "EYE1", 1000.0, "wet AMD"),
        ]
        scanner = MAProbabilityScanner(
            knowledge_store=store,
            context_provider=_StubProvider(contexts),
            config=MAProbabilityConfig(
                top_n=10,
                use_stored_screen_context=True,
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
        row = result.rows[0]

        assert row.stage == "phase_2"
        assert row.enterprise_value_millions == pytest.approx(300.0, abs=1e-9)
        assert row.acquisition_discount == pytest.approx(3.0, abs=1e-9)
        assert row.valuation_discount_score == pytest.approx(1.0, abs=1e-9)
        assert row.days_to_catalyst == 45
        assert row.nearest_catalyst_date == date(2026, 5, 8)
    finally:
        store.close()


def test_ma_probability_scanner_excludes_mega_cap_non_targets(tmp_path: Path):
    profiles_path = _write_profiles(tmp_path, include_onco=False)
    comps_path = _write_comps(tmp_path)
    vulnerability_path = _write_vulnerability_signals(tmp_path, include_target_signals=False)
    contexts = {
        "asset-mega": _make_context(
            asset_id="asset-mega",
            company_id="co-mega",
            name="MegaCapTarget",
            therapeutic_area=TherapeuticArea.OPHTHALMOLOGY,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.BIOLOGIC,
            cash_millions=100.0,
            burn_rate_millions_per_quarter=10.0,
        ),
    }
    watchlist = [
        _watchlist_asset("asset-mega", "co-mega", "MEGA", 125000.0, "wet AMD"),
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
    assert result.rows == []
    assert result.n_assets == 0
    assert result.n_ranked == 0
    assert result.n_excluded == 1
    assert result.excluded_assets[0].ticker == "MEGA"
    assert "mega_cap:125.0B" in result.excluded_assets[0].reasons


def test_ma_probability_scanner_excludes_self_acquirers(tmp_path: Path):
    profiles_path = _write_profiles(tmp_path, include_onco=False)
    comps_path = _write_comps(tmp_path)
    vulnerability_path = _write_vulnerability_signals(tmp_path, include_target_signals=False)
    contexts = {
        "asset-self": _make_context(
            asset_id="asset-self",
            company_id="co-self",
            name="SelfBuyer",
            therapeutic_area=TherapeuticArea.OPHTHALMOLOGY,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.BIOLOGIC,
            cash_millions=80.0,
            burn_rate_millions_per_quarter=10.0,
        ),
    }
    watchlist = [
        _watchlist_asset("asset-self", "co-self", "REGE", 900.0, "wet AMD"),
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
    assert result.rows == []
    assert result.n_excluded == 1
    assert "self_acquirer:REGE" in result.excluded_assets[0].reasons


def test_ma_probability_scanner_applies_explicit_targetability_rules(tmp_path: Path):
    profiles_path = _write_profiles(tmp_path, include_onco=False)
    comps_path = _write_comps(tmp_path)
    vulnerability_path = _write_vulnerability_signals(tmp_path, include_target_signals=False)
    rules_path = _write_targetability_rules(
        tmp_path,
        [
            {
                "ticker": "VRTX",
                "reason": "established_large_cap_operator",
                "note": "Explicit non-target override for large-cap operators.",
            }
        ],
    )
    contexts = {
        "asset-vrtx": _make_context(
            asset_id="asset-vrtx",
            company_id="co-vrtx",
            name="Vertex-like",
            therapeutic_area=TherapeuticArea.RARE_DISEASE,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.SMALL_MOLECULE,
            cash_millions=100.0,
            burn_rate_millions_per_quarter=10.0,
        ),
    }
    watchlist = [
        _watchlist_asset("asset-vrtx", "co-vrtx", "VRTX", 2500.0, "cystic fibrosis"),
    ]
    scanner = MAProbabilityScanner(
        context_provider=_StubProvider(contexts),
        config=MAProbabilityConfig(
            top_n=10,
            targetability_rules_path=str(rules_path),
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
    assert result.rows == []
    assert result.n_excluded == 1
    assert "established_large_cap_operator" in result.excluded_assets[0].reasons
    assert (
        "Explicit non-target override for large-cap operators."
        in result.excluded_assets[0].reasons
    )


def test_ma_probability_scanner_excludes_approved_multi_franchise_targets(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        profiles_path = _write_profiles(tmp_path, include_onco=False)
        comps_path = _write_comps(tmp_path)
        vulnerability_path = _write_vulnerability_signals(tmp_path, include_target_signals=False)
        store.write_screen_snapshots(
            [
                SimpleNamespace(
                    ticker="COMM",
                    data_date=date(2026, 3, 24),
                    program_label="Commercial franchise",
                    stage="commercial",
                    ta="ophthalmology",
                    model_pos=1.0,
                    implied_pos=0.8,
                    spread_pp=20.0,
                    rnpv_millions=900.0,
                    ev_millions=4000.0,
                    acquisition_discount_pct=-77.5,
                    next_catalyst="None",
                    catalyst_date=None,
                    days_to_catalyst=None,
                    single_asset=False,
                    approximation_warning="multi_asset",
                    thesis_strength=0.5,
                    market_exceeds_model=False,
                    config_quality="screening_grade",
                )
            ]
        )
        contexts = {
            "asset-comm": _make_context(
                asset_id="asset-comm",
                company_id="co-comm",
                name="CommercialCo",
                therapeutic_area=TherapeuticArea.OPHTHALMOLOGY,
                stage=DevelopmentStage.PHASE_3,
                modality=Modality.BIOLOGIC,
                cash_millions=80.0,
                burn_rate_millions_per_quarter=10.0,
            ),
        }
        watchlist = [
            _watchlist_asset("asset-comm", "co-comm", "COMM", 4000.0, "wet AMD"),
        ]
        scanner = MAProbabilityScanner(
            knowledge_store=store,
            context_provider=_StubProvider(contexts),
            config=MAProbabilityConfig(
                top_n=10,
                use_stored_screen_context=True,
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
        assert result.rows == []
        assert result.n_excluded == 1
        assert "commercial_franchise:unknown_share" in result.excluded_assets[0].reasons
    finally:
        store.close()


def test_ma_probability_scanner_penalizes_large_multi_franchise_targets(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        profiles_path = _write_profiles(tmp_path, include_onco=False)
        comps_path = _write_comps(tmp_path)
        vulnerability_path = _write_vulnerability_signals(tmp_path, include_target_signals=False)
        store.write_screen_snapshots(
            [
                SimpleNamespace(
                    ticker="SING",
                    data_date=date(2026, 3, 24),
                    program_label="Single asset",
                    stage="phase_3",
                    ta="ophthalmology",
                    model_pos=0.6,
                    implied_pos=0.4,
                    spread_pp=20.0,
                    rnpv_millions=900.0,
                    ev_millions=8000.0,
                    acquisition_discount_pct=-88.75,
                    next_catalyst="Readout",
                    catalyst_date=date(2026, 5, 1),
                    days_to_catalyst=38,
                    single_asset=True,
                    approximation_warning=None,
                    thesis_strength=0.5,
                    market_exceeds_model=False,
                    config_quality="gold",
                ),
                SimpleNamespace(
                    ticker="MULT",
                    data_date=date(2026, 3, 24),
                    program_label="Multi asset",
                    stage="phase_3",
                    ta="ophthalmology",
                    model_pos=0.6,
                    implied_pos=0.4,
                    spread_pp=20.0,
                    rnpv_millions=900.0,
                    ev_millions=8000.0,
                    acquisition_discount_pct=-88.75,
                    next_catalyst="Readout",
                    catalyst_date=date(2026, 5, 1),
                    days_to_catalyst=38,
                    single_asset=False,
                    approximation_warning="multi_asset",
                    thesis_strength=0.5,
                    market_exceeds_model=False,
                    config_quality="screening_grade",
                ),
            ]
        )
        contexts = {
            "asset-sing": _make_context(
                asset_id="asset-sing",
                company_id="co-sing",
                name="SingleCo",
                therapeutic_area=TherapeuticArea.OPHTHALMOLOGY,
                stage=DevelopmentStage.PHASE_3,
                modality=Modality.BIOLOGIC,
                cash_millions=80.0,
                burn_rate_millions_per_quarter=10.0,
            ),
            "asset-mult": _make_context(
                asset_id="asset-mult",
                company_id="co-mult",
                name="MultiCo",
                therapeutic_area=TherapeuticArea.OPHTHALMOLOGY,
                stage=DevelopmentStage.PHASE_3,
                modality=Modality.BIOLOGIC,
                cash_millions=80.0,
                burn_rate_millions_per_quarter=10.0,
            ),
        }
        watchlist = [
            _watchlist_asset("asset-sing", "co-sing", "SING", 8000.0, "wet AMD"),
            _watchlist_asset("asset-mult", "co-mult", "MULT", 8000.0, "wet AMD"),
        ]
        scanner = MAProbabilityScanner(
            knowledge_store=store,
            context_provider=_StubProvider(contexts),
            config=MAProbabilityConfig(
                top_n=10,
                use_stored_screen_context=True,
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
        by_ticker = {row.ticker: row for row in result.rows}

        assert by_ticker["SING"].targetability_multiplier == pytest.approx(1.0, abs=1e-9)
        assert by_ticker["MULT"].targetability_multiplier == pytest.approx(0.5, abs=1e-9)
        assert "multi_product_commercial_penalty" in by_ticker["MULT"].targetability_reasons
        assert by_ticker["SING"].p_acquisition > by_ticker["MULT"].p_acquisition
    finally:
        store.close()


def test_targetability_filter_hard_fails_excluded_tickers(tmp_path: Path):
    rules_path = _write_targetability_rules(tmp_path, excluded_tickers=["VRTX"])
    targetability_filter = TargetabilityFilter(str(rules_path))

    result = targetability_filter.assess(
        asset_id="asset-vrtx",
        ticker="VRTX",
        market_cap_billions=40.0,
        approved_revenue_share=None,
        stage="phase_3",
        single_asset=False,
        is_known_acquirer=False,
    )

    assert result.passes_hard_filters is False
    assert "excluded_ticker:VRTX" in result.hard_fail_reasons


def test_targetability_filter_passes_small_mid_cap_biotech(tmp_path: Path):
    rules_path = _write_targetability_rules(tmp_path)
    targetability_filter = TargetabilityFilter(str(rules_path))

    result = targetability_filter.assess(
        asset_id="asset-small",
        ticker="SMAL",
        market_cap_billions=3.5,
        approved_revenue_share=None,
        stage="phase_2",
        single_asset=True,
        is_known_acquirer=False,
    )

    assert result.passes_hard_filters is True
    assert result.multiplier == pytest.approx(1.0, abs=1e-9)
    assert result.hard_fail_reasons == []


def test_targetability_filter_scales_market_cap_penalty_linearly(tmp_path: Path):
    rules_path = _write_targetability_rules(tmp_path)
    targetability_filter = TargetabilityFilter(str(rules_path))

    result = targetability_filter.assess(
        asset_id="asset-mid",
        ticker="MIDC",
        market_cap_billions=60.0,
        approved_revenue_share=None,
        stage="phase_3",
        single_asset=True,
        is_known_acquirer=False,
    )

    assert result.passes_hard_filters is True
    assert result.multiplier == pytest.approx(0.5, abs=1e-9)
    assert "market_cap_penalty:60.0B" in result.notes


def test_ma_probability_scanner_logs_excluded_assets(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    profiles_path = _write_profiles(tmp_path, include_onco=False)
    comps_path = _write_comps(tmp_path)
    vulnerability_path = _write_vulnerability_signals(tmp_path, include_target_signals=False)
    contexts = {
        "asset-vrtx": _make_context(
            asset_id="asset-vrtx",
            company_id="co-vrtx",
            name="Vertex-like",
            therapeutic_area=TherapeuticArea.RARE_DISEASE,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.SMALL_MOLECULE,
            cash_millions=100.0,
            burn_rate_millions_per_quarter=10.0,
        ),
    }
    watchlist = [
        _watchlist_asset("asset-vrtx", "co-vrtx", "VRTX", 2500.0, "cystic fibrosis"),
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

    with caplog.at_level("INFO", logger="bve.intelligence.ma_probability"):
        result = scanner.scan_watchlist(watchlist, snapshot_date=date(2026, 3, 24))

    assert result.n_excluded == 1
    assert "Excluded 1 assets from M&A scan:" in caplog.text
    assert "VRTX: excluded_ticker:VRTX" in caplog.text


def test_ma_probability_scanner_threshold_filter_uses_calibrated_probability(tmp_path: Path):
    profiles_path = _write_profiles(tmp_path, include_onco=False)
    comps_path = _write_comps(tmp_path)
    vulnerability_path = _write_vulnerability_signals(tmp_path, include_target_signals=False)
    fit_path = _write_calibration_fit(
        tmp_path,
        feature_names=["stored_probability", "log_enterprise_value"],
        intercept=-5.0,
        coefficients=[
            ("stored_probability", 0.0, 0.0, 1.0),
            ("log_enterprise_value", 1.0, 0.0, 1.0),
        ],
    )
    contexts = {
        "asset-a": _make_context(
            asset_id="asset-a",
            company_id="co-a",
            name="RetinaA",
            therapeutic_area=TherapeuticArea.OPHTHALMOLOGY,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.BIOLOGIC,
            cash_millions=80.0,
            burn_rate_millions_per_quarter=10.0,
        ),
        "asset-z": _make_context(
            asset_id="asset-z",
            company_id="co-z",
            name="RetinaZ",
            therapeutic_area=TherapeuticArea.OPHTHALMOLOGY,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.BIOLOGIC,
            cash_millions=80.0,
            burn_rate_millions_per_quarter=10.0,
        ),
    }
    watchlist = [
        _watchlist_asset("asset-a", "co-a", "AAAA", 100.0, "wet AMD"),
        _watchlist_asset("asset-z", "co-z", "ZZZZ", 1000.0, "wet AMD"),
    ]
    scanner = MAProbabilityScanner(
        context_provider=_StubProvider(contexts),
        config=MAProbabilityConfig(
            top_n=10,
            vulnerability_signals_path=str(vulnerability_path),
            calibration_model_path=str(fit_path),
            calibration_policy="threshold_filter",
            calibration_threshold=0.80,
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

    assert result.calibration_policy == "threshold_filter"
    assert result.calibration_threshold == pytest.approx(0.80)
    assert result.n_assets == 2
    assert result.n_ranked == 1
    assert [row.asset_id for row in result.rows] == ["asset-z"]
    assert result.rows[0].rank == 1
    assert result.rows[0].p_takeout_calibrated is not None
    assert result.rows[0].p_takeout_calibrated >= 0.80


def test_ma_probability_scanner_tie_breaker_uses_calibrated_probability(tmp_path: Path):
    profiles_path = _write_profiles(tmp_path, include_onco=False)
    comps_path = _write_comps(tmp_path)
    vulnerability_path = _write_vulnerability_signals(tmp_path, include_target_signals=False)
    fit_path = _write_calibration_fit(
        tmp_path,
        feature_names=["stored_probability", "log_enterprise_value"],
        intercept=-5.0,
        coefficients=[
            ("stored_probability", 0.0, 0.0, 1.0),
            ("log_enterprise_value", 1.0, 0.0, 1.0),
        ],
    )
    contexts = {
        "asset-a": _make_context(
            asset_id="asset-a",
            company_id="co-a",
            name="RetinaA",
            therapeutic_area=TherapeuticArea.OPHTHALMOLOGY,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.BIOLOGIC,
            cash_millions=80.0,
            burn_rate_millions_per_quarter=10.0,
        ),
        "asset-z": _make_context(
            asset_id="asset-z",
            company_id="co-z",
            name="RetinaZ",
            therapeutic_area=TherapeuticArea.OPHTHALMOLOGY,
            stage=DevelopmentStage.PHASE_3,
            modality=Modality.BIOLOGIC,
            cash_millions=80.0,
            burn_rate_millions_per_quarter=10.0,
        ),
    }
    watchlist = [
        _watchlist_asset("asset-a", "co-a", "AAAA", 100.0, "wet AMD"),
        _watchlist_asset("asset-z", "co-z", "ZZZZ", 1000.0, "wet AMD"),
    ]
    scanner = MAProbabilityScanner(
        context_provider=_StubProvider(contexts),
        config=MAProbabilityConfig(
            top_n=10,
            vulnerability_signals_path=str(vulnerability_path),
            calibration_model_path=str(fit_path),
            calibration_policy="tie_breaker",
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

    assert result.calibration_policy == "tie_breaker"
    assert result.n_ranked == 2
    assert [row.asset_id for row in result.rows] == ["asset-z", "asset-a"]
    assert result.rows[0].rank == 1
    assert result.rows[1].rank == 2


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
    mechanism_of_action: str | None = None,
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


def _write_targetability_rules(
    tmp_path: Path,
    rules: list[dict[str, object]] | None = None,
    *,
    excluded_tickers: list[str] | None = None,
    max_market_cap_billions: float = 100.0,
    max_approved_revenue_share: float = 0.50,
    multi_product_commercial_penalty: float = 0.50,
    market_cap_penalty_start_billions: float = 20.0,
    market_cap_penalty_end_billions: float = 100.0,
) -> Path:
    path = tmp_path / "mna_targetability_rules.yaml"
    payload: dict[str, object] = {
        "hard_fails": {
            "max_market_cap_billions": max_market_cap_billions,
            "excluded_tickers": excluded_tickers or [],
            "max_approved_revenue_share": max_approved_revenue_share,
        },
        "soft_penalties": {
            "multi_product_commercial_penalty": multi_product_commercial_penalty,
            "market_cap_penalty_start_billions": market_cap_penalty_start_billions,
            "market_cap_penalty_end_billions": market_cap_penalty_end_billions,
        },
    }
    if rules:
        payload["explicit_hard_fails"] = rules
    path.write_text(
        yaml.safe_dump(payload),
        encoding="utf-8",
    )
    return path


def _write_company_sotp_snapshot(
    store: KnowledgeStore,
    *,
    ticker: str,
    snapshot_date: date,
    passes_gate: bool,
    action_policy: str,
    action_reason: str,
) -> None:
    store.write_company_sotp_snapshots(
        [
            SimpleNamespace(
                ticker=ticker,
                company_id=f"co-{ticker.lower()}",
                company_name=f"Company {ticker}",
                snapshot_date=snapshot_date,
                rank=1,
                market_cap_millions=500.0,
                enterprise_value_millions=450.0,
                sotp_equity_value_millions=650.0,
                sotp_per_share=65.0,
                sotp_discount=1.3,
                ranked_sotp_discount=1.3,
                modeled_asset_coverage_pct=0.8,
                asset_count_modeled=1,
                modeled_asset_ids=[f"asset-{ticker.lower()}"],
                config_quality_summary="curated",
                modeled_asset_confidence_min=0.9,
                modeled_asset_confidence_avg=0.9,
                action_policy=action_policy,
                action_reason=action_reason,
                market_cap_source="unit_test",
                balance_sheet_source="sec_edgar_company_facts",
                balance_sheet_source_ref="unit-test",
                balance_sheet_snapshot_date=snapshot_date,
                balance_sheet_period_end_date=snapshot_date,
                balance_sheet_form_type="10-Q",
                balance_sheet_is_point_in_time=True,
                balance_sheet_age_days=4,
                balance_sheet_passes_recency_gate=passes_gate,
                balance_sheet_recency_penalty=1.0 if passes_gate else 0.25,
                buckets=[],
                limitations=[],
                notes=None,
            )
        ],
        snapshot_date=snapshot_date,
    )


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


def _minimal_logistic_metrics() -> MALogisticMetrics:
    return MALogisticMetrics(auc=0.70, brier_score=0.18)


def _write_calibration_fit(
    tmp_path: Path,
    *,
    feature_names: list[str],
    intercept: float,
    coefficients: list[tuple[str, float, float, float]],
) -> Path:
    payload = MALogisticFitResult(
        dataset_mode="canonical_predeal",
        feature_names=feature_names,
        l2_penalty=1.0,
        top_k=15,
        n_rows=10,
        n_positive_rows=3,
        n_control_rows=7,
        n_match_groups=3,
        fit_converged=True,
        cross_validated_groups_converged=3,
        intercept=intercept,
        coefficients=[
            MALogisticCoefficient(
                feature_name=name,
                coefficient=value,
                odds_ratio=1.0,
                mean=mean,
                std=std,
            )
            for name, value, mean, std in coefficients
        ],
        stored_probability_metrics=_minimal_logistic_metrics(),
        fitted_metrics=_minimal_logistic_metrics(),
        cross_validated_metrics=_minimal_logistic_metrics(),
        predictions=[],
    )
    path = tmp_path / "ma_fit.json"
    payload.write_json(path)
    return path


def _source_ref() -> dict[str, str]:
    return {
        "source_date": "2026-03-01",
        "source_type": "press_release",
        "source_title": "Example source",
        "source_url": "https://example.com/source",
        "note": "Example note",
    }
