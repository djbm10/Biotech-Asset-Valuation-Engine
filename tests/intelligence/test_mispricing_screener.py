from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from bve.connectors.market_prices import MarketPriceRecord
from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, EndpointType, TrialPhase
from bve.intelligence.catalyst_calendar import CatalystEvent, CatalystType
from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace, StoredValuationDiff
from bve.intelligence.mispricing_screener import (
    MispricingScreenConfig,
    UnifiedMispricingScreener,
    _NEUTRAL_ACQUISITION_SCORE,
    _catalyst_modifier,
    _resolve_pos_adjustment,
)
from bve.intelligence.schemas.signals import Event, StructuredSignal
from bve.intelligence.taxonomy import EventType
from bve.models.market_model import MarketModel
from bve.pipeline.watchlist_runner import AssetValuationContext, WatchlistAsset


def _event(*, asset_id: str, company_id: str, event_id: str, observed_at: datetime) -> Event:
    return Event(
        id=event_id,
        event_type=EventType.TRIAL_READOUT,
        asset_id=asset_id,
        company_id=company_id,
        observed_at=observed_at,
        ingested_at=observed_at,
        source_type="manual",
        headline=f"{asset_id} trial readout",
        confidence=0.95,
    )


def _signal(
    *,
    asset_id: str,
    company_id: str,
    event_id: str,
    signal_date: date,
    created_at: datetime,
    confidence: float,
    phase: TrialPhase,
) -> StructuredSignal:
    return StructuredSignal(
        id=f"sig-{asset_id}",
        event_id=event_id,
        asset_id=asset_id,
        company_id=company_id,
        event_type=EventType.TRIAL_READOUT,
        signal_date=signal_date,
        trial_phase=phase,
        primary_endpoint_met=True,
        extraction_model="unit-test",
        extraction_confidence=confidence,
        created_at=created_at,
    )


def _diff(
    *,
    asset_id: str,
    event_id: str,
    created_at: datetime,
    before_rnpv: float,
    after_rnpv: float,
    model_pos: float,
) -> StoredValuationDiff:
    return StoredValuationDiff(
        run_id=f"run-{asset_id}",
        event_id=event_id,
        asset_id=asset_id,
        valuation_before={"rnpv_millions": before_rnpv},
        valuation_after={
            "rnpv_millions": after_rnpv,
            "cumulative_success_probability": model_pos,
        },
        delta_npv=after_rnpv - before_rnpv,
        created_at=created_at,
        valuation_delta={"delta_npv": after_rnpv - before_rnpv},
    )


def _context(
    *,
    asset_id: str,
    company_id: str,
    ticker: str,
    stage: DevelopmentStage,
    phase: TrialPhase,
    market_cap_millions: float,
    current_price: float,
    cash_millions: float,
    debt_millions: float = 0.0,
    total_addressable_market_millions: float = 1_500.0,
    peak_penetration: float = 0.20,
    success_probability: float = 0.55,
) -> AssetValuationContext:
    shares_outstanding = market_cap_millions / current_price
    asset = Asset(
        id=asset_id,
        name=f"Drug {asset_id}",
        indication="Solid tumors",
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        stage=stage,
        modality=Modality.SMALL_MOLECULE,
        discount_rate=0.12,
    )
    company = Company(
        id=company_id,
        name=company_id,
        ticker=ticker,
        cash_millions=cash_millions,
        debt_millions=debt_millions,
        shares_outstanding_millions=shares_outstanding,
        current_price=current_price,
    )
    trials = [
        ClinicalTrial(
            asset_id=asset_id,
            phase=phase,
            success_probability=success_probability,
            duration_years=2.0,
            cost_millions=25.0,
            endpoint_type=EndpointType.SURROGATE_VALIDATED,
        )
    ]
    market_model = MarketModel(
        asset_id=asset_id,
        total_addressable_market_millions=total_addressable_market_millions,
        peak_penetration=peak_penetration,
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
    def __init__(self, contexts: dict[str, AssetValuationContext]) -> None:
        self._contexts = contexts

    def get_context(self, asset: WatchlistAsset) -> AssetValuationContext:
        return self._contexts[asset.asset_id]


def _watchlist_asset(
    *,
    asset_id: str,
    company_id: str,
    ticker: str,
    market_cap_millions: float,
) -> WatchlistAsset:
    return WatchlistAsset(
        company_id=company_id,
        asset_id=asset_id,
        ticker=ticker,
        valuation_config=f"/tmp/{asset_id}.yaml",
        market_cap_millions=market_cap_millions,
    )


def test_unified_screener_combines_existing_layers():
    store = KnowledgeStore(":memory:")
    screened_at = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
    signal_date = screened_at.date()
    trace = SourceTrace(source_type="test", source_ref="mispricing-screen")

    asset_a = _watchlist_asset(
        asset_id="asset-a",
        company_id="company-a",
        ticker="AAA",
        market_cap_millions=120.0,
    )
    asset_b = _watchlist_asset(
        asset_id="asset-b",
        company_id="company-b",
        ticker="BBB",
        market_cap_millions=160.0,
    )

    store.add_event(
        _event(
            asset_id="asset-a",
            company_id="company-a",
            event_id="evt-a",
            observed_at=screened_at,
        ),
        trace,
        signal_id="sig-asset-a",
    )
    store.add_structured_signal(
        _signal(
            asset_id="asset-a",
            company_id="company-a",
            event_id="evt-a",
            signal_date=signal_date,
            created_at=screened_at,
            confidence=0.90,
            phase=TrialPhase.PHASE_3,
        ),
        trace,
        extraction_result_id="extract-a",
    )
    store.add_valuation_diff(
        _diff(
            asset_id="asset-a",
            event_id="evt-a",
            created_at=screened_at,
            before_rnpv=160.0,
            after_rnpv=260.0,
            model_pos=0.65,
        ),
        company_id="company-a",
        source_trace=trace,
    )
    store.upsert_market_price(
        MarketPriceRecord(
            ticker="AAA",
            price_date=signal_date,
            close_usd=12.0,
            adj_close_usd=12.0,
            volume=100_000,
            market_cap_millions=120.0,
        )
    )
    store.upsert_market_price(
        MarketPriceRecord(
            ticker="BBB",
            price_date=signal_date,
            close_usd=16.0,
            adj_close_usd=16.0,
            volume=80_000,
            market_cap_millions=160.0,
        )
    )
    store.upsert_catalyst_event(
        CatalystEvent(
            asset_id="asset-a",
            company_id="company-a",
            catalyst_type=CatalystType.TRIAL_READOUT,
            expected_date=date(2026, 3, 20),
            date_confidence="exact",
            source="unit_test",
            description="near-term readout",
            signal_strength=1.4,
        )
    )

    contexts = {
        "asset-a": _context(
            asset_id="asset-a",
            company_id="company-a",
            ticker="AAA",
            stage=DevelopmentStage.PHASE_3,
            phase=TrialPhase.PHASE_3,
            market_cap_millions=120.0,
            current_price=12.0,
            cash_millions=20.0,
            total_addressable_market_millions=2_200.0,
            peak_penetration=0.24,
            success_probability=0.65,
        ),
        "asset-b": _context(
            asset_id="asset-b",
            company_id="company-b",
            ticker="BBB",
            stage=DevelopmentStage.PHASE_1,
            phase=TrialPhase.PHASE_1,
            market_cap_millions=160.0,
            current_price=16.0,
            cash_millions=10.0,
            total_addressable_market_millions=300.0,
            peak_penetration=0.08,
            success_probability=0.20,
        ),
    }
    cfg = SimpleNamespace(watchlist=[asset_a, asset_b], ranking={"top_n": 10})

    screener = UnifiedMispricingScreener(
        knowledge_store=store,
        config=MispricingScreenConfig(top_n=10, catalyst_days_ahead=60),
        context_provider=_StubProvider(contexts),
    )
    result = screener.screen_from_watchlist_config(cfg, screened_at=screened_at)
    store.close()

    assert result.n_assets == 2
    assert result.n_with_ranking == 1
    assert result.n_with_catalyst == 1
    assert len(result.rows) == 2

    top = result.rows[0]
    second = result.rows[1]
    assert top.asset_id == "asset-a"
    assert top.catalyst_type == "trial_readout"
    assert top.days_to_catalyst == 10
    assert top.acquisition_discount is not None
    assert top.catalyst_modifier > 1.0
    assert top.unified_score > second.unified_score

    assert second.asset_id == "asset-b"
    assert "missing_ranking_signal" in second.data_notes
    assert second.acquisition_exclusion_reason is not None


def test_pos_adjustment_uses_pos_gap_not_raw_model_pos():
    low_model = SimpleNamespace(pos_gap=-0.12, model_pos=0.20)
    high_model = SimpleNamespace(pos_gap=-0.12, model_pos=0.85)
    wider_gap = SimpleNamespace(pos_gap=-0.22, model_pos=0.85)

    low_score, low_value, low_source = _resolve_pos_adjustment(
        ranking=low_model,
        acquisition_row=None,
    )
    high_score, high_value, high_source = _resolve_pos_adjustment(
        ranking=high_model,
        acquisition_row=None,
    )
    wider_score, wider_value, wider_source = _resolve_pos_adjustment(
        ranking=wider_gap,
        acquisition_row=None,
    )

    assert low_source == "pos_gap"
    assert high_source == "pos_gap"
    assert low_value == high_value
    assert low_score == high_score
    assert wider_source == "pos_gap"
    assert wider_value > high_value
    assert wider_score > high_score


def test_catalyst_modifier_is_bounded():
    event = CatalystEvent(
        asset_id="asset-a",
        company_id="company-a",
        catalyst_type=CatalystType.TRIAL_READOUT,
        expected_date=date(2026, 3, 11),
        date_confidence="exact",
        source="unit_test",
        description="high-signal readout",
        signal_strength=10.0,
    )
    modifier = _catalyst_modifier(
        catalyst=event,
        as_of=date(2026, 3, 10),
        days_ahead=60,
        max_modifier_pct=0.10,
    )

    negative_event = event.model_copy(update={"signal_strength": -10.0})
    negative_modifier = _catalyst_modifier(
        catalyst=negative_event,
        as_of=date(2026, 3, 10),
        days_ahead=60,
        max_modifier_pct=0.10,
    )

    assert 1.0 < modifier <= 1.10
    assert 0.90 <= negative_modifier < 1.0


def test_missing_acquisition_discount_is_explicit_and_neutral():
    store = KnowledgeStore(":memory:")
    screener = UnifiedMispricingScreener(
        knowledge_store=store,
        config=MispricingScreenConfig(top_n=5),
    )
    asset = _watchlist_asset(
        asset_id="asset-missing",
        company_id="company-missing",
        ticker="MISS",
        market_cap_millions=100.0,
    )
    ranking = SimpleNamespace(
        rank=1,
        composite_score=0.72,
        ticker="MISS",
        after_rnpv_millions=180.0,
        market_cap_millions=100.0,
        mispricing=0.80,
        model_pos=0.50,
        implied_pos=0.28,
        pos_gap=-0.22,
        signal_trial_phase="phase_2",
    )
    acquisition_row = SimpleNamespace(
        stage="phase_2",
        ticker="MISS",
        drug_name="Drug M",
        indication="Solid tumors",
        model_rnpv_millions=180.0,
        market_cap_millions=100.0,
        enterprise_value_millions=90.0,
        acquisition_discount=None,
        exclusion_reason="missing_market_cap",
        acquisition_ready=None,
        market_cap_source="missing",
        acquisition_readiness_prior_pos=None,
        acquisition_readiness_posterior_pos=None,
        model_pos=0.50,
    )

    row = screener._build_row(
        asset=asset,
        ranking=ranking,
        acquisition_row=acquisition_row,
        as_of=date(2026, 3, 10),
    )
    store.close()

    assert row.acquisition_score == _NEUTRAL_ACQUISITION_SCORE
    assert "acquisition_discount_unavailable" in row.data_notes
    assert row.acquisition_exclusion_reason == "missing_market_cap"
