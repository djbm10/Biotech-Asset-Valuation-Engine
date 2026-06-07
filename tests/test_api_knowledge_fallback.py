from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.pool import StaticPool

from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, EndpointType, TrialPhase
from bve.intelligence.knowledge_layer import (
    AssetRegistryEntry,
    KnowledgeStore,
    OpportunityAlertRecord,
    StoredValuationDiff,
)
from bve.intelligence.phase2.mapping_engine import MappingBatchResult
from bve.intelligence.phase2.policy import MappingPolicy
from bve.intelligence.schemas.proposals import AssumptionChangeProposal
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import ChangeMode, EventType
from bve.models.market_model import MarketModel
from bve.persistence.db import Base
from bve.pipeline.watchlist_runner import (
    AssetValuationContext,
    ConnectorRuntimeConfig,
    ExtractionRuntimeConfig,
    WatchlistAsset,
    WatchlistPipelineRunner,
    WatchlistRunnerConfig,
)
from bve.services.intelligence_service import IntelligenceService, IntelligenceServiceConfig

_NOW = datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)


class _FakeConnector:
    source_type = "press_release"

    def fetch(self, entity_hints, since: Optional[datetime] = None, limit: int = 50):
        from bve.connectors.base import FetchResult
        from bve.intelligence.extraction.raw_document import RawDocument

        doc = RawDocument.from_text(
            id=f"raw-{entity_hints.asset_id}",
            source="press_release",
            title=f"{entity_hints.asset_id} update",
            raw_text="Positive clinical update with endpoint details.",
            source_url=f"https://example.org/{entity_hints.asset_id}/update",
            published_at=_NOW,
            retrieved_at=_NOW,
            entity_hints=entity_hints,
        )
        return FetchResult(documents=[doc], source=self.source_type, fetched_at=_NOW)


class _FakeExtractor:
    def extract(self, document, event_id: Optional[str] = None):
        from bve.intelligence.extraction.result import ExtractionResult, ExtractionStatus

        resolved_event_id = event_id or f"evt-{document.id}"
        signal = StructuredSignal(
            id=f"sig-{resolved_event_id}",
            event_id=resolved_event_id,
            asset_id=document.entity_hints.asset_id,
            company_id=document.entity_hints.company_id,
            event_type=EventType.TRIAL_READOUT,
            signal_date=date(2026, 3, 8),
            trial_phase=TrialPhase.PHASE_2,
            primary_endpoint_met=True,
            extraction_model="fake-extractor",
            extraction_confidence=0.95,
            created_at=_NOW,
        )
        return ExtractionResult(
            document_id=document.id,
            asset_id=signal.asset_id,
            company_id=signal.company_id,
            source_url=document.source_url,
            status=ExtractionStatus.SUCCESS,
            signal=signal,
            event_type_detected=signal.event_type.value,
            raw_llm_response='{"event_type":"trial_readout"}',
            raw_llm_json={"event_type": "trial_readout"},
            ambiguity_flag=False,
            extraction_confidence=signal.extraction_confidence,
            rationale="deterministic test extraction",
            extraction_model="fake-extractor",
            prompt_version="v1.0",
            latency_ms=5,
            extracted_at=_NOW,
        )


class _FakeMappingEngine:
    def __init__(self) -> None:
        self.policy = MappingPolicy.default()

    def map_signal(self, signal, *, engine_asset_id: str, asset, trials, market_model):
        proposal = AssumptionChangeProposal(
            id=f"prop-{signal.id}",
            signal_id=signal.id,
            asset_id=signal.asset_id,
            engine_asset_id=engine_asset_id,
            parameter_path="trials[*].success_probability",
            current_value=0.50,
            proposed_value=0.52,
            change_mode=ChangeMode.AUTO,
            bound_pct=10.0,
            event_type=signal.event_type,
            rationale="test proposal",
            created_at=signal.created_at,
        )
        return MappingBatchResult(signal_id=signal.id, proposals=[proposal], audit_log=[], skipped=[])


class _FakeContextProvider:
    def get_context(self, asset: WatchlistAsset) -> AssetValuationContext:
        return AssetValuationContext(
            asset=Asset(
                id=asset.asset_id,
                name=asset.drug_name or asset.asset_id,
                indication=asset.indication or "solid tumor",
                therapeutic_area=TherapeuticArea.ONCOLOGY,
                stage=DevelopmentStage.PHASE_2,
                modality=Modality.SMALL_MOLECULE,
                discount_rate=0.10,
            ),
            company=Company(
                id=asset.company_id,
                name=asset.company_id,
                cash_millions=500.0,
                debt_millions=0.0,
                shares_outstanding_millions=100.0,
            ),
            trials=[
                ClinicalTrial(
                    asset_id=asset.asset_id,
                    phase=TrialPhase.PHASE_2,
                    success_probability=0.50,
                    duration_years=2.0,
                    cost_millions=80.0,
                    endpoint_type=EndpointType.SURROGATE_VALIDATED,
                )
            ],
            market_model=MarketModel(
                asset_id=asset.asset_id,
                therapeutic_area="oncology",
                addressable_patients_annual=10000,
                net_price_per_patient_usd=120000.0,
                peak_penetration=0.20,
                years_to_peak=5,
                patent_life_years=10,
            ),
        )


class _FakeValuationExecutor:
    def apply(
        self,
        *,
        company_id: str,
        asset_id: str,
        context: AssetValuationContext,
        signal: StructuredSignal,
        proposals,
        effective_values,
        run_at: datetime,
    ) -> Optional[StoredValuationDiff]:
        if not effective_values:
            return None
        return StoredValuationDiff(
            run_id=f"run-{signal.id}",
            event_id=signal.event_id,
            asset_id=asset_id,
            valuation_before={"rnpv_millions": 100.0},
            valuation_after={"rnpv_millions": 120.0},
            delta_npv=20.0,
            created_at=run_at,
            valuation_delta={"delta_npv": 20.0},
            assumptions_changed=[],
            applied_overrides={"trials[*].success_probability": 0.52},
        )


def _make_runner(tmp_path: Path) -> WatchlistPipelineRunner:
    cfg = WatchlistRunnerConfig(
        polling_interval_seconds=60,
        state_path=str(tmp_path / "state.json"),
        knowledge_db_path=str(tmp_path / "knowledge.db"),
        valuation_output_dir=str(tmp_path / "valuation"),
        extraction=ExtractionRuntimeConfig(backend="fake", max_docs_per_asset=5),
        connectors={"press_release": ConnectorRuntimeConfig(enabled=True, limit=10)},
        watchlist=[
            WatchlistAsset(
                company_id="company-1",
                asset_id="asset-1",
                ticker="ABCD",
                drug_name="ABCD-101",
                indication="solid tumor",
            )
        ],
    )
    return WatchlistPipelineRunner(
        cfg,
        connectors={"press_release": _FakeConnector()},
        extractor=_FakeExtractor(),
        mapping_engine=_FakeMappingEngine(),
        context_provider=_FakeContextProvider(),
        valuation_executor=_FakeValuationExecutor(),
    )


def _make_session(monkeypatch, knowledge_db_path: str):
    monkeypatch.setenv("BVE_KNOWLEDGE_DB_PATH", knowledge_db_path)
    engine = sa.create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sa.orm.sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return Session()


def test_watchlist_runner_populates_api_from_knowledge_store(tmp_path: Path, monkeypatch) -> None:
    runner = _make_runner(tmp_path)
    try:
        summary = runner.run_once(refresh_market_prices=False, enable_memos=False)
        assert summary.assets[0].status == "success"
    finally:
        runner.close()

    from apps.api.routers.alerts import list_alerts
    from apps.api.routers.assets import list_assets
    from apps.api.routers.deals import list_deals

    db = _make_session(monkeypatch, str(tmp_path / "knowledge.db"))
    try:
        assert list_assets(db, ta=None, phase=None, ticker=None, has_catalyst=None, limit=50, offset=0)
        assert list_deals(db, acquirer=None, timing_bucket=None, min_fit_score=0.0, limit=50)
        assert list_alerts(db, source_type=None, min_materiality=0.5, limit=50)
    finally:
        db.close()


def test_service_cycle_populates_api_from_knowledge_store(tmp_path: Path, monkeypatch) -> None:
    watchlist_path = tmp_path / "watchlist.yaml"
    watchlist_path.write_text(
        "polling_interval_seconds: 60\nwatchlist:\n  - company_id: company-1\n    asset_id: asset-1\n",
        encoding="utf-8",
    )
    knowledge = KnowledgeStore(str(tmp_path / "service.db"))
    knowledge.upsert_asset_registry_entry(
        AssetRegistryEntry(
            asset_id="asset-1",
            ticker="ABCD",
            company_id="company-1",
            drug_name="ABCD-101",
            indication="solid tumor",
            therapeutic_area="oncology",
            modality="small_molecule",
            stage="phase_2",
            created_at=_NOW,
            source="test",
        )
    )
    knowledge.add_opportunity_alert(
        OpportunityAlertRecord(
            asset_id="asset-1",
            event_type="trial_readout",
            window="2026-03-08",
            run_id="run-123",
            created_at=_NOW,
            payload_json={"score": 0.8, "title": "ABCD trial readout"},
        )
    )
    knowledge.close()

    class _FakeRunner:
        def __init__(self, store: KnowledgeStore) -> None:
            self.knowledge = store
            self.alert_router = None

        def run_once(self, *args, **kwargs):
            from bve.pipeline.watchlist_runner import AssetRunSummary, WatchlistRunSummary

            return WatchlistRunSummary(
                run_id="run-123",
                started_at=_NOW,
                finished_at=_NOW,
                assets=[
                    AssetRunSummary(
                        run_id="run-123",
                        company_id="company-1",
                        asset_id="asset-1",
                        status="success",
                    )
                ],
                stage_logs=[],
            )

        def close(self) -> None:
            self.knowledge.close()

    class _FakeScanner:
        def __init__(self) -> None:
            from bve.intelligence.opportunity_scanner import OpportunityScannerConfig, OpportunityScanResult

            self.config = OpportunityScannerConfig()
            self._result_cls = OpportunityScanResult

        def scan_from_watchlist_config(self, watchlist_config, *, run_id: str, scanned_at: datetime):
            return self._result_cls(
                run_id=run_id,
                scanned_at=scanned_at,
                config=self.config,
                opportunities=[],
                alerts_emitted=[],
                alerts_suppressed_as_duplicate=0,
            )

    service = IntelligenceService(
        IntelligenceServiceConfig(
            watchlist_path=str(watchlist_path),
            dashboard_cache_path=str(tmp_path / "cache.json"),
            control_state_path=str(tmp_path / "control.json"),
            metrics_path=str(tmp_path / "run_metrics.json"),
        ),
        runner=_FakeRunner(KnowledgeStore(str(tmp_path / "service.db"))),
        scanner=_FakeScanner(),
    )
    try:
        out = service.run_cycle()
        assert out.run_id == "run-123"
    finally:
        service.close()

    from apps.api.routers.alerts import list_alerts
    from apps.api.routers.assets import list_assets
    from apps.api.routers.deals import list_deals

    db = _make_session(monkeypatch, str(tmp_path / "service.db"))
    try:
        assert list_assets(db, ta=None, phase=None, ticker=None, has_catalyst=None, limit=50, offset=0)
        assert list_deals(db, acquirer=None, timing_bucket=None, min_fit_score=0.0, limit=50)
        assert list_alerts(db, source_type=None, min_materiality=0.5, limit=50)
    finally:
        db.close()
