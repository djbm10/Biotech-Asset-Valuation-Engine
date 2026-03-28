from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from bve.cli.acquisition_screen import _build_parser as build_acquisition_screen_parser
from bve.cli.acquisition_screen import main as acquisition_screen_main
from bve.connectors.market_prices import MarketPriceRecord
from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, EndpointType, TrialPhase
from bve.intelligence.acquisition_screen import (
    AcquisitionDiscountSnapshot,
    AcquisitionScreenConfig,
    AcquisitionScreenResult,
    AcquisitionScreenRow,
    AcquisitionScreener,
)
from bve.intelligence.comparable_deals import ComparableDeal
from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import EventType
from bve.models.market_model import MarketModel
from bve.pipeline.watchlist_runner import AssetValuationContext, WatchlistAsset


def _make_watchlist_asset(**overrides) -> WatchlistAsset:
    payload = {
        "company_id": "co-1",
        "asset_id": "asset-1",
        "drug_name": "Drug X",
        "indication": "Indication Y",
        "ticker": "TEST",
        "valuation_config": "/tmp/asset-1.yaml",
    }
    payload.update(overrides)
    return WatchlistAsset(**payload)


def _make_context(
    *,
    ticker: str = "TEST",
    cash_millions: float = 40.0,
    debt_millions: float = 10.0,
    shares_outstanding_millions: float = 10.0,
    current_price: float = 12.0,
) -> AssetValuationContext:
    asset = Asset(
        id="asset-1",
        name="Drug X",
        indication="Indication Y",
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        stage=DevelopmentStage.PHASE_2,
        modality=Modality.SMALL_MOLECULE,
        discount_rate=0.12,
    )
    company = Company(
        id="co-1",
        name="Company 1",
        ticker=ticker,
        cash_millions=cash_millions,
        debt_millions=debt_millions,
        shares_outstanding_millions=shares_outstanding_millions,
        current_price=current_price,
    )
    trials = [
        ClinicalTrial(
            asset_id="asset-1",
            phase=TrialPhase.PHASE_2,
            success_probability=0.45,
            duration_years=2.0,
            cost_millions=20.0,
            endpoint_type=EndpointType.SURROGATE_VALIDATED,
        )
    ]
    market_model = MarketModel(
        asset_id="asset-1",
        total_addressable_market_millions=1_000.0,
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


class _StubProvider:
    def __init__(self, context: AssetValuationContext) -> None:
        self._context = context

    def get_context(self, asset: WatchlistAsset) -> AssetValuationContext:
        assert asset.asset_id == "asset-1"
        return self._context


class _StubScreener(AcquisitionScreener):
    def __init__(
        self,
        *,
        rnpv_millions: float,
        model_pos: float,
        peak_sales_millions: float | None = None,
        knowledge_store: KnowledgeStore | None = None,
        context: AssetValuationContext | None = None,
        threshold: float = 1.5,
        require_acquisition_readiness: bool = False,
    ) -> None:
        super().__init__(
            AcquisitionScreenConfig(
                threshold=threshold,
                require_acquisition_readiness=require_acquisition_readiness,
            ),
            knowledge_store=knowledge_store,
            context_provider=_StubProvider(context or _make_context()),
        )
        self._stub_rnpv_millions = rnpv_millions
        self._stub_model_pos = model_pos
        self._stub_peak_sales_millions = peak_sales_millions

    def _run_rnpv(self, context: AssetValuationContext):
        return SimpleNamespace(
            rnpv_millions=self._stub_rnpv_millions,
            cumulative_success_probability=self._stub_model_pos,
            peak_sales_millions=self._stub_peak_sales_millions,
        )


def _store_phase2_signal(
    store: KnowledgeStore,
    *,
    asset_id: str = "asset-1",
    company_id: str = "co-1",
    primary_endpoint_met: bool = True,
    p_value: float = 0.01,
    randomization: str = "randomized",
    n_patients: int = 160,
    estimated_effect_size: float = 0.45,
    alpha_level: float = 0.05,
) -> None:
    store.add_structured_signal(
        StructuredSignal(
            id=f"sig-{asset_id}",
            event_id=f"evt-{asset_id}",
            asset_id=asset_id,
            company_id=company_id,
            event_type=EventType.TRIAL_READOUT,
            signal_date=date(2026, 3, 1),
            trial_phase=TrialPhase.PHASE_2,
            randomization=randomization,
            comparator_type="active_comparator" if randomization == "randomized" else "none",
            n_patients=n_patients,
            estimated_effect_size=estimated_effect_size,
            alpha_level=alpha_level,
            primary_endpoint_met=primary_endpoint_met,
            p_value=p_value,
            extraction_confidence=0.95,
            extraction_model="unit-test",
            created_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        ),
        SourceTrace(
            source_type="unit_test",
            source_ref="phase2-signal",
            ingested_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        ),
        extraction_result_id=f"ext-{asset_id}",
    )


def test_acquisition_discount_uses_rnpv_over_ev_without_double_counting_pos():
    asset = _make_watchlist_asset(market_cap_millions=100.0)
    context = _make_context(cash_millions=0.0, debt_millions=0.0)
    screener = _StubScreener(rnpv_millions=200.0, model_pos=0.5, context=context)

    result = screener.screen_watchlist([asset], snapshot_date=date(2026, 3, 21), persist=False)
    row = result.rows[0]

    assert row.acquisition_discount == pytest.approx(2.0, abs=1e-9)
    assert row.acquisition_discount != pytest.approx(1.0, abs=1e-9)


def test_acquisition_screen_defaults_to_1_5x_threshold():
    assert AcquisitionScreenConfig().threshold == pytest.approx(1.5)


def test_acquisition_screen_cli_defaults_to_1_5x_threshold():
    parser = build_acquisition_screen_parser()
    args = parser.parse_args(["--watchlist", "watchlist.yaml"])
    assert args.threshold == pytest.approx(1.5)


def test_acquisition_screen_prefers_latest_market_price_market_cap(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        store.upsert_market_price(
            MarketPriceRecord(
                ticker="TEST",
                price_date=date(2026, 3, 10),
                close_usd=9.0,
                adj_close_usd=9.0,
                volume=10_000,
                market_cap_millions=100.0,
            )
        )
        store.upsert_market_price(
            MarketPriceRecord(
                ticker="TEST",
                price_date=date(2026, 3, 20),
                close_usd=10.0,
                adj_close_usd=10.0,
                volume=12_000,
                market_cap_millions=120.0,
            )
        )

        asset = _make_watchlist_asset(market_cap_millions=80.0)
        context = _make_context(cash_millions=30.0, debt_millions=10.0, current_price=25.0)
        screener = _StubScreener(
            rnpv_millions=250.0,
            model_pos=0.45,
            knowledge_store=store,
            context=context,
        )

        result = screener.screen_watchlist([asset], snapshot_date=date(2026, 3, 21), persist=False)
        row = result.rows[0]

        assert row.market_cap_millions == pytest.approx(120.0, abs=1e-9)
        assert row.market_cap_as_of == date(2026, 3, 20)
        assert row.market_cap_source == "knowledge_store_price"
        assert row.enterprise_value_millions == pytest.approx(100.0, abs=1e-9)
        assert row.acquisition_discount == pytest.approx(2.5, abs=1e-9)
    finally:
        store.close()


def test_acquisition_screen_falls_back_to_watchlist_market_cap():
    asset = _make_watchlist_asset(market_cap_millions=150.0)
    context = _make_context(current_price=20.0, shares_outstanding_millions=10.0)
    screener = _StubScreener(rnpv_millions=180.0, model_pos=0.35, context=context)

    result = screener.screen_watchlist([asset], snapshot_date=date(2026, 3, 21), persist=False)
    row = result.rows[0]

    assert row.market_cap_millions == pytest.approx(150.0, abs=1e-9)
    assert row.market_cap_source == "watchlist_override"


def test_acquisition_screen_excludes_non_positive_enterprise_value():
    asset = _make_watchlist_asset(market_cap_millions=50.0)
    context = _make_context(cash_millions=100.0, debt_millions=0.0)
    screener = _StubScreener(rnpv_millions=180.0, model_pos=0.35, context=context)

    result = screener.screen_watchlist([asset], snapshot_date=date(2026, 3, 21), persist=False)
    row = result.rows[0]

    assert row.enterprise_value_millions == pytest.approx(-50.0, abs=1e-9)
    assert row.acquisition_discount is None
    assert row.exclusion_reason == "non_positive_enterprise_value"


def test_acquisition_screen_persists_snapshot_round_trip(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        asset = _make_watchlist_asset(market_cap_millions=100.0)
        context = _make_context(cash_millions=0.0, debt_millions=0.0)
        screener = _StubScreener(
            rnpv_millions=250.0,
            model_pos=0.40,
            knowledge_store=store,
            context=context,
        )

        screener.screen_watchlist([asset], snapshot_date=date(2026, 3, 21))

        latest = store.get_latest_acquisition_discount_snapshot("asset-1")
        assert latest is not None
        assert latest.acquisition_discount == pytest.approx(2.5, abs=1e-9)
        assert latest.passes_threshold is True

        rows = store.list_acquisition_discount_snapshots(asset_id="asset-1", passes_threshold=True)
        assert len(rows) == 1
        assert rows[0].formula_version == "rnpv_over_ev_v1"
    finally:
        store.close()


def test_acquisition_screen_loads_real_valuation_config_when_no_provider(tmp_path: Path):
    config_path = tmp_path / "asset-1.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "asset": {
                    "id": "asset-1",
                    "name": "Drug X",
                    "indication": "Indication Y",
                    "therapeutic_area": "oncology",
                    "stage": "phase_2",
                    "modality": "small_molecule",
                    "discount_rate": 0.12,
                },
                "company": {
                    "id": "co-1",
                    "name": "Company 1",
                    "ticker": "TEST",
                    "cash_millions": 20.0,
                    "debt_millions": 5.0,
                    "shares_outstanding_millions": 10.0,
                    "current_price": 12.0,
                },
                "trials": [
                    {
                        "phase": "phase_2",
                        "success_probability": 0.45,
                        "duration_years": 2.0,
                        "cost_millions": 20.0,
                        "endpoint_type": "surrogate_validated",
                    }
                ],
                "market_model": {
                    "total_addressable_market_millions": 1000.0,
                    "peak_penetration": 0.15,
                    "years_to_peak": 5,
                    "patent_life_years": 10,
                },
            }
        ),
        encoding="utf-8",
    )

    asset = _make_watchlist_asset(
        valuation_config=str(config_path),
        market_cap_millions=120.0,
    )
    screener = AcquisitionScreener(AcquisitionScreenConfig(threshold=0.1))

    result = screener.screen_watchlist([asset], snapshot_date=date(2026, 3, 21), persist=False)
    row = result.rows[0]

    assert row.exclusion_reason is None
    assert row.model_rnpv_millions is not None
    assert row.model_pos is not None
    assert row.market_cap_source == "watchlist_override"


def test_acquisition_screen_enriches_row_with_comparable_deals():
    asset = _make_watchlist_asset(market_cap_millions=180.0)
    context = _make_context(cash_millions=0.0, debt_millions=0.0)
    screener = _StubScreener(
        rnpv_millions=240.0,
        model_pos=0.45,
        peak_sales_millions=120.0,
        context=context,
    )
    comparable_deals = [
        ComparableDeal(
            target_name="Comp A",
            indication="Indication Y",
            therapeutic_area="oncology",
            phase_at_acquisition="phase_2",
            acquirer="Big Pharma",
            deal_date="2025-01-10",
            enterprise_value_millions=250.0,
            peak_sales_millions=100.0,
        ),
        ComparableDeal(
            target_name="Comp B",
            indication="Indication Y",
            therapeutic_area="oncology",
            phase_at_acquisition="phase_2",
            acquirer="Big Pharma",
            deal_date="2025-04-15",
            enterprise_value_millions=150.0,
            peak_sales_millions=100.0,
        ),
    ]

    result = screener.screen_watchlist(
        [asset],
        snapshot_date=date(2026, 3, 21),
        persist=False,
        comparable_deals=comparable_deals,
    )
    row = result.rows[0]

    assert row.ev_to_peak_sales == pytest.approx(1.5, abs=1e-9)
    assert row.comps_match_tier == "exact_indication_phase"
    assert row.comps_n == 2
    assert row.comps_percentile_vs_peers == pytest.approx(0.25, abs=1e-9)
    assert row.comps_peer_median_ev_to_peak_sales == pytest.approx(2.0, abs=1e-9)


def test_acquisition_screen_requires_phase2_poc_when_readiness_filter_enabled(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        asset = _make_watchlist_asset(market_cap_millions=180.0)
        context = _make_context(cash_millions=0.0, debt_millions=0.0)
        screener = _StubScreener(
            rnpv_millions=240.0,
            model_pos=0.45,
            peak_sales_millions=120.0,
            knowledge_store=store,
            context=context,
            threshold=0.5,
            require_acquisition_readiness=True,
        )

        no_signal_result = screener.screen_watchlist(
            [asset],
            snapshot_date=date(2026, 3, 21),
            persist=False,
        )
        excluded_row = no_signal_result.rows[0]
        assert excluded_row.exclusion_reason == "missing_phase_2_readout"
        assert excluded_row.acquisition_ready is False
        assert excluded_row.passes_threshold is False

        _store_phase2_signal(store)
        ready_result = screener.screen_watchlist(
            [asset],
            snapshot_date=date(2026, 3, 21),
            persist=False,
        )
        ready_row = ready_result.rows[0]
        assert ready_row.exclusion_reason is None
        assert ready_row.acquisition_ready is True
        assert ready_row.acquisition_readiness_bucket == "phase_2_poc"
        assert ready_row.passes_threshold is True
    finally:
        store.close()


def test_acquisition_screen_cli_prints_table(tmp_path: Path, monkeypatch, capsys):
    watchlist_path = tmp_path / "watchlist.yaml"
    watchlist_path.write_text(
        yaml.safe_dump(
            {
                "knowledge_db_path": str(tmp_path / "knowledge.db"),
                "watchlist": [
                    {
                        "company_id": "co-1",
                        "asset_id": "asset-1",
                        "ticker": "TEST",
                        "valuation_config": "/tmp/asset-1.yaml",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    def _fake_screen_watchlist(
        self,
        watchlist,
        *,
        snapshot_date=None,
        persist=None,
        comparable_deals=None,
    ):
        row = AcquisitionScreenRow(
            asset_id="asset-1",
            company_id="co-1",
            ticker="TEST",
            snapshot_date=date(2026, 3, 21),
            formula_version="rnpv_over_ev_v1",
            model_rnpv_millions=250.0,
            model_pos=0.40,
            market_cap_millions=120.0,
            market_cap_source="knowledge_store_price",
            enterprise_value_millions=100.0,
            net_cash_millions=20.0,
            acquisition_discount=2.5,
            passes_threshold=True,
        )
        return AcquisitionScreenResult(
            snapshot_date=date(2026, 3, 21),
            threshold=2.0,
            formula_version="rnpv_over_ev_v1",
            n_assets=1,
            n_candidates=1,
            n_excluded=0,
            rows=[row],
        )

    monkeypatch.setattr(
        "bve.cli.acquisition_screen.AcquisitionScreener.screen_watchlist",
        _fake_screen_watchlist,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "bve-acquisition-screen",
            "--watchlist",
            str(watchlist_path),
        ],
    )

    acquisition_screen_main()
    out = capsys.readouterr().out
    assert "asset-1" in out
    assert "2.50x" in out
    assert "candidate" in out


def test_acquisition_screen_cli_prints_comps_columns(tmp_path: Path, monkeypatch, capsys):
    watchlist_path = tmp_path / "watchlist.yaml"
    comps_path = tmp_path / "comps.yaml"
    watchlist_path.write_text(
        yaml.safe_dump(
            {
                "knowledge_db_path": str(tmp_path / "knowledge.db"),
                "watchlist": [
                    {
                        "company_id": "co-1",
                        "asset_id": "asset-1",
                        "ticker": "TEST",
                        "valuation_config": "/tmp/asset-1.yaml",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    comps_path.write_text("deals: []\n", encoding="utf-8")

    def _fake_screen_watchlist(
        self,
        watchlist,
        *,
        snapshot_date=None,
        persist=None,
        comparable_deals=None,
    ):
        assert comparable_deals == []
        row = AcquisitionScreenRow(
            asset_id="asset-1",
            company_id="co-1",
            ticker="TEST",
            snapshot_date=date(2026, 3, 21),
            formula_version="rnpv_over_ev_v1",
            model_rnpv_millions=250.0,
            model_pos=0.40,
            market_cap_millions=120.0,
            market_cap_source="knowledge_store_price",
            enterprise_value_millions=100.0,
            net_cash_millions=20.0,
            peak_sales_millions=50.0,
            ev_to_peak_sales=2.0,
            acquisition_discount=2.5,
            passes_threshold=True,
            comps_match_tier="phase_only",
            comps_n=4,
            comps_percentile_vs_peers=0.75,
            comps_peer_median_ev_to_peak_sales=1.8,
        )
        return AcquisitionScreenResult(
            snapshot_date=date(2026, 3, 21),
            threshold=2.0,
            formula_version="rnpv_over_ev_v1",
            n_assets=1,
            n_candidates=1,
            n_excluded=0,
            rows=[row],
        )

    monkeypatch.setattr(
        "bve.cli.acquisition_screen.AcquisitionScreener.screen_watchlist",
        _fake_screen_watchlist,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "bve-acquisition-screen",
            "--watchlist",
            str(watchlist_path),
            "--with-comps",
            "--comps-file",
            str(comps_path),
        ],
    )

    acquisition_screen_main()
    out = capsys.readouterr().out
    assert "EV/Peak" in out
    assert "Comp %" in out
    assert "75" in out
    assert "comps: tier=phase_only n=4 peer_median=1.80x" in out


def test_acquisition_screen_cli_prints_target_monitor(tmp_path: Path, monkeypatch, capsys):
    watchlist_path = tmp_path / "watchlist.yaml"
    targets_path = tmp_path / "targets.yaml"
    watchlist_path.write_text(
        yaml.safe_dump(
            {
                "knowledge_db_path": str(tmp_path / "knowledge.db"),
                "watchlist": [
                    {
                        "company_id": "co-1",
                        "asset_id": "asset-1",
                        "ticker": "TEST",
                        "valuation_config": "/tmp/asset-1.yaml",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    targets_path.write_text(
        yaml.safe_dump(
            {
                "as_of_date": "2026-03-22",
                "targets": [
                    {
                        "company_name": "Revolution Medicines",
                        "ticker": "RVMD",
                        "status": "independent_public_target",
                        "therapeutic_area": "oncology",
                        "lead_assets": "daraxonrasib / elironrasib",
                        "stage": "late_stage",
                        "source_url": "https://example.com/rvmd",
                        "notes": "Independent public target.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    def _fake_screen_watchlist(
        self,
        watchlist,
        *,
        snapshot_date=None,
        persist=None,
        comparable_deals=None,
    ):
        row = AcquisitionScreenRow(
            asset_id="asset-1",
            company_id="co-1",
            ticker="TEST",
            snapshot_date=date(2026, 3, 21),
            formula_version="rnpv_over_ev_v1",
            model_rnpv_millions=250.0,
            model_pos=0.40,
            market_cap_millions=120.0,
            market_cap_source="knowledge_store_price",
            enterprise_value_millions=100.0,
            net_cash_millions=20.0,
            acquisition_discount=2.5,
            passes_threshold=True,
        )
        return AcquisitionScreenResult(
            snapshot_date=date(2026, 3, 21),
            threshold=2.0,
            formula_version="rnpv_over_ev_v1",
            n_assets=1,
            n_candidates=1,
            n_excluded=0,
            rows=[row],
        )

    monkeypatch.setattr(
        "bve.cli.acquisition_screen.AcquisitionScreener.screen_watchlist",
        _fake_screen_watchlist,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "bve-acquisition-screen",
            "--watchlist",
            str(watchlist_path),
            "--show-target-monitor",
            "--targets-file",
            str(targets_path),
        ],
    )

    acquisition_screen_main()
    out = capsys.readouterr().out
    assert "Target monitor as of 2026-03-22" in out
    assert "Revolution Medicines" in out
    assert "independent_public_target" in out


def test_acquisition_snapshot_model_can_be_constructed_directly():
    snapshot = AcquisitionDiscountSnapshot(
        asset_id="asset-1",
        ticker="TEST",
        snapshot_date=date(2026, 3, 21),
        model_rnpv_millions=220.0,
        model_pos=0.33,
        market_cap_millions=110.0,
        enterprise_value_millions=90.0,
        net_cash_millions=20.0,
        acquisition_discount=2.444444,
    )
    assert snapshot.asset_id == "asset-1"
    assert snapshot.formula_version == "rnpv_over_ev_v1"
