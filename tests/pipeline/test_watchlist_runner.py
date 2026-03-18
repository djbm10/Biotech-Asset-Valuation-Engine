from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import yaml
from bve.alerts.alert_config import AlertThresholdsConfig, AlertsConfig
from bve.alerts.alert_router import AlertRouter
from bve.alerts.channels.base import FakeChannel
from bve.connectors.base import FetchResult
from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, EndpointType, TrialPhase
from bve.intelligence.competitor_discovery import CompetitorDiscoveryResult, CompetitorProgram
from bve.intelligence.knowledge_graph import EdgeType, KGEdge, KGNode, NodeType
from bve.intelligence.knowledge_layer import AssetRegistryEntry, SourceTrace
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument
from bve.intelligence.extraction.result import ExtractionResult, ExtractionStatus
from bve.intelligence.knowledge_layer import StoredValuationDiff
from bve.intelligence.phase2.mapping_engine import MappingBatchResult
from bve.intelligence.phase2.policy import MappingPolicy
from bve.intelligence.schemas.proposals import AssumptionChangeProposal
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import ChangeMode, EventType
from bve.models.market_model import MarketModel
from bve.ops.cost_guard import CostGuard
from bve.pipeline.change_detector import MaterialChangeDetector, MaterialityRule
from bve.pipeline.watchlist_runner import (
    AssetValuationContext,
    ConnectorRuntimeConfig,
    ExtractionRuntimeConfig,
    Phase2SessionValuationExecutor,
    WatchlistAsset,
    WatchlistPipelineRunner,
    WatchlistRunnerConfig,
    load_watchlist_config,
)

_NOW = datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)


class FakeConnector:
    source_type = "press_release"

    def __init__(self) -> None:
        self.calls: list[tuple[str, Optional[datetime]]] = []

    def fetch(
        self,
        entity_hints: EntityHints,
        since: Optional[datetime] = None,
        limit: int = 50,
    ) -> FetchResult:
        self.calls.append((entity_hints.asset_id, since))
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
        return FetchResult(
            documents=[doc],
            source=self.source_type,
            fetched_at=_NOW,
        )


class FakeExtractor:
    def __init__(self, *, fail_asset_ids: Optional[set[str]] = None) -> None:
        self.fail_asset_ids = fail_asset_ids or set()
        self.calls = 0

    def extract(self, document: RawDocument, event_id: Optional[str] = None) -> ExtractionResult:
        self.calls += 1
        if document.entity_hints.asset_id in self.fail_asset_ids:
            raise RuntimeError(f"forced extraction failure for {document.entity_hints.asset_id}")

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


class FakeMappingEngine:
    def __init__(self) -> None:
        self.policy = MappingPolicy.default()

    def map_signal(
        self,
        signal: StructuredSignal,
        *,
        engine_asset_id: str,
        asset: Asset,
        trials: list[ClinicalTrial],
        market_model: MarketModel,
    ) -> MappingBatchResult:
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
        return MappingBatchResult(
            signal_id=signal.id,
            proposals=[proposal],
            audit_log=[],
            skipped=[],
        )


class FakeContextProvider:
    def get_context(self, asset: WatchlistAsset) -> AssetValuationContext:
        return AssetValuationContext(
            asset=Asset(
                id=asset.asset_id,
                name=asset.asset_id,
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
                addressable_patients_annual=10000,
                net_price_per_patient_usd=120000.0,
                peak_penetration=0.20,
                years_to_peak=5,
                patent_life_years=10,
            ),
        )


class FakeValuationExecutor:
    def __init__(self, *, delta_npv: float) -> None:
        self.delta_npv = delta_npv
        self.calls = 0

    def apply(
        self,
        *,
        company_id: str,
        asset_id: str,
        context: AssetValuationContext,
        signal: StructuredSignal,
        proposals: list[AssumptionChangeProposal],
        effective_values: dict[str, float],
        run_at: datetime,
    ) -> Optional[StoredValuationDiff]:
        if not effective_values:
            return None
        self.calls += 1
        return StoredValuationDiff(
            run_id=f"run-{signal.id}",
            event_id=signal.event_id,
            asset_id=asset_id,
            valuation_before={"rnpv_millions": 100.0, "nav_per_share": 4.0},
            valuation_after={
                "rnpv_millions": 100.0 + self.delta_npv,
                "nav_per_share": 4.0 + (self.delta_npv / 100.0),
            },
            delta_npv=self.delta_npv,
            created_at=run_at,
            valuation_delta={"delta_npv": self.delta_npv},
            assumptions_changed=[
                {
                    "field": "trials[*].success_probability",
                    "old_value": 0.50,
                    "new_value": 0.52,
                    "delta": 0.02,
                }
            ],
            applied_overrides={"trials[*].success_probability": 0.52},
        )


def _config(
    tmp_path: Path,
    watchlist: list[WatchlistAsset],
    *,
    max_docs_per_asset: int = 5,
    backend: str = "fake",
    llm_daily_cost_limit_usd: float = 2.50,
) -> WatchlistRunnerConfig:
    return WatchlistRunnerConfig(
        polling_interval_seconds=60,
        state_path=str(tmp_path / "state.json"),
        knowledge_db_path=str(tmp_path / "knowledge.db"),
        valuation_output_dir=str(tmp_path / "valuation"),
        extraction=ExtractionRuntimeConfig(
            backend=backend,
            max_docs_per_asset=max_docs_per_asset,
            llm_daily_cost_limit_usd=llm_daily_cost_limit_usd,
            llm_daily_cost_path=str(tmp_path / "daily_llm_cost.json"),
        ),
        connectors={
            "press_release": ConnectorRuntimeConfig(enabled=True, limit=10),
        },
        watchlist=watchlist,
    )


def test_phase2_session_executor_persists_watchlist_asset_id(tmp_path: Path) -> None:
    run_at = _NOW
    context = AssetValuationContext(
        asset=Asset(
            id="engine-asset-1",
            name="Engine Asset",
            indication="test indication",
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            stage=DevelopmentStage.PHASE_2,
            modality=Modality.SMALL_MOLECULE,
            discount_rate=0.10,
        ),
        company=Company(
            id="company-1",
            name="Company 1",
            cash_millions=500.0,
            debt_millions=0.0,
            shares_outstanding_millions=100.0,
        ),
        trials=[
            ClinicalTrial(
                asset_id="engine-asset-1",
                phase=TrialPhase.PHASE_2,
                success_probability=0.50,
                duration_years=2.0,
                cost_millions=80.0,
                endpoint_type=EndpointType.SURROGATE_VALIDATED,
            )
        ],
        market_model=MarketModel(
            asset_id="engine-asset-1",
            addressable_patients_annual=10000,
            net_price_per_patient_usd=120000.0,
            peak_penetration=0.20,
            years_to_peak=5,
            patent_life_years=10,
        ),
    )
    signal = StructuredSignal(
        id="sig-1",
        event_id="evt-1",
        asset_id="watchlist-asset-1",
        company_id="company-1",
        event_type=EventType.TRIAL_READOUT,
        signal_date=run_at.date(),
        trial_phase=TrialPhase.PHASE_2,
        primary_endpoint_met=True,
        extraction_model="test-extractor",
        extraction_confidence=0.95,
        created_at=run_at,
    )
    proposal = AssumptionChangeProposal(
        id="prop-1",
        signal_id=signal.id,
        asset_id=signal.asset_id,
        engine_asset_id=context.asset.id,
        parameter_path="trials[*].success_probability",
        current_value=0.50,
        proposed_value=0.52,
        change_mode=ChangeMode.AUTO,
        bound_pct=10.0,
        event_type=signal.event_type,
        rationale="test proposal",
        created_at=run_at,
    )

    executor = Phase2SessionValuationExecutor(tmp_path / "valuation")
    diff = executor.apply(
        company_id="company-1",
        asset_id="watchlist-asset-1",
        context=context,
        signal=signal,
        proposals=[proposal],
        effective_values={proposal.id: 0.52},
        run_at=run_at,
    )

    assert diff is not None
    assert diff.asset_id == "watchlist-asset-1"
    assert diff.event_id == signal.event_id


def test_watchlist_runner_is_idempotent_for_duplicate_documents(tmp_path: Path):
    connector = FakeConnector()
    valuation = FakeValuationExecutor(delta_npv=5.0)
    runner = WatchlistPipelineRunner(
        _config(
            tmp_path,
            [
                WatchlistAsset(
                    company_id="company-1", asset_id="asset-1", connectors=["press_release"]
                )
            ],
        ),
        connectors={"press_release": connector},
        extractor=FakeExtractor(),
        mapping_engine=FakeMappingEngine(),
        context_provider=FakeContextProvider(),
        valuation_executor=valuation,
    )

    first = runner.run_once()
    second = runner.run_once()

    assert first.assets[0].status == "success"
    assert first.assets[0].events_created == 1
    assert second.assets[0].status == "success"
    assert second.assets[0].events_created == 0
    assert second.assets[0].documents_processed == 0
    assert valuation.calls == 1

    assert len(runner.knowledge.get_raw_documents(limit=10)) == 1
    assert len(runner.knowledge.get_extraction_results(limit=10)) == 1
    assert len(runner.knowledge.get_structured_signals(limit=10)) == 1
    assert (
        len(runner.knowledge.get_events(company_id="company-1", asset_id="asset-1", limit=10)) == 1
    )
    assert (
        len(
            runner.knowledge.get_valuation_diffs(
                company_id="company-1", asset_id="asset-1", limit=10
            )
        )
        == 1
    )
    assert any(log.stage == "dedupe_event" and log.status == "skipped" for log in second.stage_logs)
    runner.close()


def test_watchlist_runner_skips_already_processed_document_hash(tmp_path: Path):
    class HashChangingConnector(FakeConnector):
        def __init__(self) -> None:
            super().__init__()
            self._call_idx = 0

        def fetch(
            self,
            entity_hints: EntityHints,
            since: Optional[datetime] = None,
            limit: int = 50,
        ) -> FetchResult:
            self.calls.append((entity_hints.asset_id, since))
            self._call_idx += 1
            return FetchResult(
                documents=[
                    RawDocument.from_text(
                        id=f"raw-{entity_hints.asset_id}-{self._call_idx}",
                        source="press_release",
                        title=f"{entity_hints.asset_id} update {self._call_idx}",
                        raw_text="Same payload text across URLs",
                        source_url=f"https://example.org/{entity_hints.asset_id}/update/{self._call_idx}",
                        published_at=_NOW,
                        retrieved_at=_NOW,
                        entity_hints=entity_hints,
                    )
                ],
                source=self.source_type,
                fetched_at=_NOW,
            )

    connector = HashChangingConnector()
    extractor = FakeExtractor()
    runner = WatchlistPipelineRunner(
        _config(
            tmp_path,
            [
                WatchlistAsset(
                    company_id="company-1", asset_id="asset-1", connectors=["press_release"]
                )
            ],
        ),
        connectors={"press_release": connector},
        extractor=extractor,
        mapping_engine=FakeMappingEngine(),
        context_provider=FakeContextProvider(),
        valuation_executor=FakeValuationExecutor(delta_npv=5.0),
    )

    hints = EntityHints(asset_id="asset-1", company_id="company-1")
    seeded_doc = RawDocument.from_text(
        id="seed-doc",
        source="press_release",
        title="seeded doc",
        raw_text="Same payload text across URLs",
        source_url="https://example.org/seed",
        published_at=_NOW,
        retrieved_at=_NOW,
        entity_hints=hints,
    )
    normalized = WatchlistPipelineRunner._normalize_document(seeded_doc, hints)
    runner.knowledge.add_raw_document(
        normalized,
        SourceTrace(source_type=normalized.source, source_ref=normalized.source_url or normalized.id),
    )
    extraction = extractor.extract(
        normalized,
        event_id=WatchlistPipelineRunner._event_id_for_document(
            company_id="company-1",
            asset_id="asset-1",
            document=normalized,
        ),
    )
    runner.knowledge.add_extraction_result(
        extraction,
        SourceTrace(source_type="extraction", source_ref=f"document:{normalized.id}"),
        raw_document_id=normalized.id,
    )
    extractor.calls = 0

    summary = runner.run_once()

    assert summary.assets[0].documents_processed == 0
    assert extractor.calls == 0
    assert any(log.stage == "dedupe_document_hash" for log in summary.stage_logs)
    runner.close()


def test_watchlist_runner_limits_extraction_to_newest_five_documents(tmp_path: Path):
    class ManyDocsConnector(FakeConnector):
        def fetch(
            self,
            entity_hints: EntityHints,
            since: Optional[datetime] = None,
            limit: int = 50,
        ) -> FetchResult:
            self.calls.append((entity_hints.asset_id, since))
            published_minutes = [2, 0, 6, 1, 5, 4, 3]
            title_by_minute = {
                0: "asset-1 financing update",
                1: "asset-1 enrollment progress",
                2: "asset-1 safety follow-up",
                3: "asset-1 biomarker readout",
                4: "asset-1 manufacturing note",
                5: "asset-1 regulatory meeting",
                6: "asset-1 efficacy data",
            }
            docs = [
                RawDocument.from_text(
                    id=f"raw-{entity_hints.asset_id}-{minute}",
                    source="press_release",
                    title=title_by_minute[minute],
                    raw_text=f"Unique payload {minute}",
                    source_url=f"https://example.org/{entity_hints.asset_id}/update/{minute}",
                    published_at=_NOW.replace(minute=minute),
                    retrieved_at=_NOW,
                    entity_hints=entity_hints,
                )
                for minute in published_minutes
            ]
            return FetchResult(documents=docs[:limit], source=self.source_type, fetched_at=_NOW)

    class RecordingExtractor(FakeExtractor):
        def __init__(self) -> None:
            super().__init__()
            self.titles: list[str] = []

        def extract(self, document: RawDocument, event_id: Optional[str] = None) -> ExtractionResult:
            self.titles.append(document.title)
            return super().extract(document, event_id=event_id)

    extractor = RecordingExtractor()
    runner = WatchlistPipelineRunner(
        _config(
            tmp_path,
            [
                WatchlistAsset(
                    company_id="company-1",
                    asset_id="asset-1",
                    connectors=["press_release"],
                )
            ],
            max_docs_per_asset=5,
        ),
        connectors={"press_release": ManyDocsConnector()},
        extractor=extractor,
        mapping_engine=FakeMappingEngine(),
        context_provider=FakeContextProvider(),
        valuation_executor=FakeValuationExecutor(delta_npv=5.0),
    )

    summary = runner.run_once()

    assert summary.assets[0].documents_fetched == 7
    assert summary.assets[0].documents_processed == 5
    assert extractor.calls == 5
    assert extractor.titles == [
        "asset-1 efficacy data",
        "asset-1 regulatory meeting",
        "asset-1 manufacturing note",
        "asset-1 biomarker readout",
        "asset-1 safety follow-up",
    ]
    assert sum(1 for log in summary.stage_logs if log.stage == "extraction_limit") == 2
    runner.close()


def test_watchlist_runner_skips_similar_titles_processed_in_last_24h(tmp_path: Path):
    class SimilarTitleConnector(FakeConnector):
        def fetch(
            self,
            entity_hints: EntityHints,
            since: Optional[datetime] = None,
            limit: int = 50,
        ) -> FetchResult:
            self.calls.append((entity_hints.asset_id, since))
            return FetchResult(
                documents=[
                    RawDocument.from_text(
                        id="raw-similar",
                        source="press_release",
                        title="asset 1 announces phase-2 data!!",
                        raw_text="Fresh payload that differs from prior text.",
                        source_url="https://example.org/asset-1/fresh",
                        published_at=_NOW,
                        retrieved_at=_NOW,
                        entity_hints=entity_hints,
                    )
                ],
                source=self.source_type,
                fetched_at=_NOW,
            )

    extractor = FakeExtractor()
    runner = WatchlistPipelineRunner(
        _config(
            tmp_path,
            [
                WatchlistAsset(
                    company_id="company-1",
                    asset_id="asset-1",
                    connectors=["press_release"],
                )
            ],
        ),
        connectors={"press_release": SimilarTitleConnector()},
        extractor=extractor,
        mapping_engine=FakeMappingEngine(),
        context_provider=FakeContextProvider(),
        valuation_executor=FakeValuationExecutor(delta_npv=5.0),
    )

    hints = EntityHints(asset_id="asset-1", company_id="company-1")
    seeded_doc = RawDocument.from_text(
        id="seed-title",
        source="press_release",
        title="Asset-1 Announces Phase 2 Data",
        raw_text="Older processed payload",
        source_url="https://example.org/asset-1/old",
        published_at=_NOW - timedelta(hours=2),
        retrieved_at=_NOW - timedelta(hours=2),
        entity_hints=hints,
    )
    normalized = WatchlistPipelineRunner._normalize_document(seeded_doc, hints)
    runner.knowledge.add_raw_document(
        normalized,
        SourceTrace(source_type=normalized.source, source_ref=normalized.source_url or normalized.id),
    )
    runner.knowledge.add_extraction_result(
        {
            "id": "extract-seed-title",
            "asset_id": "asset-1",
            "created_at": (_NOW - timedelta(hours=1)).isoformat(),
        },
        SourceTrace(source_type="extraction", source_ref=f"document:{normalized.id}"),
        raw_document_id=normalized.id,
    )
    extractor.calls = 0

    summary = runner.run_once()

    assert summary.assets[0].documents_fetched == 1
    assert summary.assets[0].documents_processed == 0
    assert extractor.calls == 0
    assert any(log.stage == "dedupe_similar_title" for log in summary.stage_logs)
    assert len(runner.knowledge.get_raw_documents(limit=10)) == 2
    runner.close()


def test_watchlist_runner_stops_extraction_when_daily_cost_cap_reached(tmp_path: Path):
    class TwoDocsConnector(FakeConnector):
        def fetch(
            self,
            entity_hints: EntityHints,
            since: Optional[datetime] = None,
            limit: int = 50,
        ) -> FetchResult:
            self.calls.append((entity_hints.asset_id, since))
            docs = [
                RawDocument.from_text(
                    id=f"raw-{entity_hints.asset_id}-1",
                    source="press_release",
                    title=f"{entity_hints.asset_id} first update",
                    raw_text="Positive clinical update with endpoint details.",
                    source_url=f"https://example.org/{entity_hints.asset_id}/1",
                    published_at=_NOW,
                    retrieved_at=_NOW,
                    entity_hints=entity_hints,
                ),
                RawDocument.from_text(
                    id=f"raw-{entity_hints.asset_id}-2",
                    source="press_release",
                    title=f"{entity_hints.asset_id} second update",
                    raw_text="Another clinical update with endpoint details.",
                    source_url=f"https://example.org/{entity_hints.asset_id}/2",
                    published_at=_NOW - timedelta(minutes=1),
                    retrieved_at=_NOW - timedelta(minutes=1),
                    entity_hints=entity_hints,
                ),
            ]
            return FetchResult(documents=docs[:limit], source=self.source_type, fetched_at=_NOW)

    channel = FakeChannel()
    router = AlertRouter(
        config=AlertsConfig(
            thresholds=AlertThresholdsConfig(
                dedup_window_hours=0.0,
                dedup_state_path=str(tmp_path / "cost_guard_dedup.json"),
            )
        ),
        channels=[channel],
    )
    extractor = FakeExtractor()
    cost_guard = CostGuard(
        state_path=tmp_path / "daily_llm_cost.json",
        daily_limit_usd=0.0001,
        now_fn=lambda: _NOW,
    )
    runner = WatchlistPipelineRunner(
        _config(
            tmp_path,
            [
                WatchlistAsset(
                    company_id="company-1",
                    asset_id="asset-1",
                    connectors=["press_release"],
                )
            ],
            backend="anthropic",
            llm_daily_cost_limit_usd=0.0001,
        ),
        connectors={"press_release": TwoDocsConnector()},
        extractor=extractor,
        mapping_engine=FakeMappingEngine(),
        context_provider=FakeContextProvider(),
        valuation_executor=FakeValuationExecutor(delta_npv=5.0),
        alert_router=router,
        cost_guard=cost_guard,
    )

    summary = runner.run_once()

    assert summary.assets[0].status == "success"
    assert summary.assets[0].documents_fetched == 2
    assert summary.assets[0].documents_processed == 1
    assert extractor.calls == 1
    assert any(
        log.stage == "extract"
        and log.status == "skipped"
        and log.message == "LLM extraction skipped due to daily cost limit"
        for log in summary.stage_logs
    )
    assert cost_guard.current_total_usd >= 0.0001
    assert channel.sent
    assert any(
        "Daily LLM extraction cost limit reached" in alert.message for alert in channel.sent
    )
    assert channel.sent[0].severity.value == "low"
    runner.close()


def test_watchlist_runner_continues_across_assets_when_cost_guard_blocks_extraction(
    tmp_path: Path,
):
    extractor = FakeExtractor()
    cost_guard = CostGuard(
        state_path=tmp_path / "daily_llm_cost.json",
        daily_limit_usd=0.10,
        now_fn=lambda: _NOW,
    )
    cost_guard.record_llm_cost(0.10)
    runner = WatchlistPipelineRunner(
        _config(
            tmp_path,
            [
                WatchlistAsset(
                    company_id="company-1",
                    asset_id="asset-1",
                    connectors=["press_release"],
                ),
                WatchlistAsset(
                    company_id="company-2",
                    asset_id="asset-2",
                    connectors=["press_release"],
                ),
            ],
            backend="anthropic",
            llm_daily_cost_limit_usd=0.10,
        ),
        connectors={"press_release": FakeConnector()},
        extractor=extractor,
        mapping_engine=FakeMappingEngine(),
        context_provider=FakeContextProvider(),
        valuation_executor=FakeValuationExecutor(delta_npv=5.0),
        cost_guard=cost_guard,
    )

    summary = runner.run_once()
    by_asset = {asset.asset_id: asset for asset in summary.assets}

    assert extractor.calls == 0
    assert by_asset["asset-1"].status == "success"
    assert by_asset["asset-2"].status == "success"
    assert by_asset["asset-1"].documents_fetched == 1
    assert by_asset["asset-2"].documents_fetched == 1
    assert by_asset["asset-1"].documents_processed == 0
    assert by_asset["asset-2"].documents_processed == 0
    assert sum(
        1
        for log in summary.stage_logs
        if log.stage == "extract"
        and log.status == "skipped"
        and log.message == "LLM extraction skipped due to daily cost limit"
    ) == 2
    runner.close()


def test_watchlist_runner_isolates_failures_per_asset(tmp_path: Path):
    connector = FakeConnector()
    runner = WatchlistPipelineRunner(
        _config(
            tmp_path,
            [
                WatchlistAsset(
                    company_id="company-fail", asset_id="asset-fail", connectors=["press_release"]
                ),
                WatchlistAsset(
                    company_id="company-ok", asset_id="asset-ok", connectors=["press_release"]
                ),
            ],
        ),
        connectors={"press_release": connector},
        extractor=FakeExtractor(fail_asset_ids={"asset-fail"}),
        mapping_engine=FakeMappingEngine(),
        context_provider=FakeContextProvider(),
        valuation_executor=FakeValuationExecutor(delta_npv=5.0),
    )

    summary = runner.run_once()
    by_asset = {asset.asset_id: asset for asset in summary.assets}

    assert by_asset["asset-fail"].status == "failure"
    assert by_asset["asset-fail"].errors
    assert by_asset["asset-ok"].status == "success"
    assert by_asset["asset-ok"].events_created == 1
    assert any(
        log.asset_id == "asset-fail" and log.stage == "asset_run" and log.status == "failure"
        for log in summary.stage_logs
    )
    assert (
        len(runner.knowledge.get_events(company_id="company-ok", asset_id="asset-ok", limit=10))
        == 1
    )
    runner.close()


def test_watchlist_runner_generates_memo_on_material_change(tmp_path: Path):
    runner = WatchlistPipelineRunner(
        _config(
            tmp_path,
            [
                WatchlistAsset(
                    company_id="company-1", asset_id="asset-1", connectors=["press_release"]
                )
            ],
        ),
        connectors={"press_release": FakeConnector()},
        extractor=FakeExtractor(),
        mapping_engine=FakeMappingEngine(),
        context_provider=FakeContextProvider(),
        valuation_executor=FakeValuationExecutor(delta_npv=35.0),
        change_detector=MaterialChangeDetector(MaterialityRule(min_abs_delta_npv=20.0)),
    )

    summary = runner.run_once()
    asset_summary = summary.assets[0]

    assert asset_summary.status == "success"
    assert asset_summary.memo_generated is True
    assert asset_summary.memo_id is not None

    memos = runner.knowledge.get_memos(company_id="company-1", asset_id="asset-1", limit=10)
    assert len(memos) == 1
    assert memos[0].referenced_diff_ids
    runner.close()


def test_watchlist_runner_skips_valuation_for_non_material_signal(tmp_path: Path):
    class FinancingExtractor(FakeExtractor):
        def extract(
            self, document: RawDocument, event_id: Optional[str] = None
        ) -> ExtractionResult:
            result = super().extract(document, event_id=event_id)
            assert result.signal is not None
            updated_signal = result.signal.model_copy(
                update={
                    "event_type": EventType.FINANCING,
                    "extraction_confidence": 0.95,
                }
            )
            return result.model_copy(
                update={
                    "signal": updated_signal,
                    "event_type_detected": EventType.FINANCING.value,
                    "extraction_confidence": 0.95,
                }
            )

    valuation = FakeValuationExecutor(delta_npv=25.0)
    runner = WatchlistPipelineRunner(
        _config(
            tmp_path,
            [
                WatchlistAsset(
                    company_id="company-1", asset_id="asset-1", connectors=["press_release"]
                )
            ],
        ),
        connectors={"press_release": FakeConnector()},
        extractor=FinancingExtractor(),
        mapping_engine=FakeMappingEngine(),
        context_provider=FakeContextProvider(),
        valuation_executor=valuation,
    )

    summary = runner.run_once()

    assert summary.assets[0].signals_created == 1
    assert summary.assets[0].valuation_diffs_persisted == 0
    assert valuation.calls == 0
    assert any(log.stage == "valuation_gate" and log.status == "skipped" for log in summary.stage_logs)
    runner.close()


def test_watchlist_runner_skips_valuation_below_material_confidence(tmp_path: Path):
    class MediumConfidenceExtractor(FakeExtractor):
        def extract(
            self, document: RawDocument, event_id: Optional[str] = None
        ) -> ExtractionResult:
            result = super().extract(document, event_id=event_id)
            assert result.signal is not None
            updated_signal = result.signal.model_copy(update={"extraction_confidence": 0.55})
            return result.model_copy(
                update={
                    "signal": updated_signal,
                    "extraction_confidence": 0.55,
                }
            )

    valuation = FakeValuationExecutor(delta_npv=25.0)
    runner = WatchlistPipelineRunner(
        _config(
            tmp_path,
            [
                WatchlistAsset(
                    company_id="company-1", asset_id="asset-1", connectors=["press_release"]
                )
            ],
        ),
        connectors={"press_release": FakeConnector()},
        extractor=MediumConfidenceExtractor(),
        mapping_engine=FakeMappingEngine(),
        context_provider=FakeContextProvider(),
        valuation_executor=valuation,
    )

    summary = runner.run_once()

    assert summary.assets[0].signals_created == 1
    assert summary.assets[0].valuation_diffs_persisted == 0
    assert valuation.calls == 0
    assert any(log.stage == "valuation_gate" and log.status == "skipped" for log in summary.stage_logs)
    runner.close()


def test_event_deduplication_key_is_deterministic_from_document_hash():
    hints = EntityHints(asset_id="asset-1", company_id="company-1")
    raw_a = RawDocument.from_text(
        id="raw-a",
        source="press_release",
        title="First title",
        raw_text="Same payload text",
        source_url="https://example.org/doc/1",
        published_at=_NOW,
        retrieved_at=_NOW,
        entity_hints=hints,
    )
    raw_b = RawDocument.from_text(
        id="raw-b",
        source="press_release",
        title="Updated title",
        raw_text="Same payload text",
        source_url="https://example.org/doc/1",
        published_at=datetime(2026, 3, 9, tzinfo=timezone.utc),
        retrieved_at=_NOW,
        entity_hints=hints,
    )

    normalized_a = WatchlistPipelineRunner._normalize_document(raw_a, hints)
    normalized_b = WatchlistPipelineRunner._normalize_document(raw_b, hints)
    event_id_a = WatchlistPipelineRunner._event_id_for_document(
        company_id="company-1",
        asset_id="asset-1",
        document=normalized_a,
    )
    event_id_b = WatchlistPipelineRunner._event_id_for_document(
        company_id="company-1",
        asset_id="asset-1",
        document=normalized_b,
    )

    assert normalized_a.document_hash == normalized_b.document_hash
    assert normalized_a.id == normalized_b.id
    assert event_id_a == event_id_b


def test_runner_resumes_after_crash_between_extraction_and_valuation(tmp_path: Path):
    class FlakyValuationExecutor(FakeValuationExecutor):
        def __init__(self) -> None:
            super().__init__(delta_npv=20.0)
            self._failed = False

        def apply(self, **kwargs):  # type: ignore[override]
            if not self._failed:
                self._failed = True
                raise RuntimeError("forced valuation failure")
            return super().apply(**kwargs)

    connector = FakeConnector()
    extractor = FakeExtractor()
    valuation = FlakyValuationExecutor()
    runner = WatchlistPipelineRunner(
        _config(
            tmp_path,
            [
                WatchlistAsset(
                    company_id="company-1", asset_id="asset-1", connectors=["press_release"]
                )
            ],
        ),
        connectors={"press_release": connector},
        extractor=extractor,
        mapping_engine=FakeMappingEngine(),
        context_provider=FakeContextProvider(),
        valuation_executor=valuation,
    )

    first = runner.run_once()
    second = runner.run_once()

    assert first.assets[0].status == "failure"
    assert second.assets[0].status == "success"
    assert second.assets[0].valuation_diffs_persisted == 1
    # Resume path should reuse persisted signal; no second extraction call needed.
    assert extractor.calls == 1
    runner.close()


def test_runner_writes_run_state_for_stage_lifecycle(tmp_path: Path):
    runner = WatchlistPipelineRunner(
        _config(
            tmp_path,
            [
                WatchlistAsset(
                    company_id="company-1", asset_id="asset-1", connectors=["press_release"]
                )
            ],
        ),
        connectors={"press_release": FakeConnector()},
        extractor=FakeExtractor(),
        mapping_engine=FakeMappingEngine(),
        context_provider=FakeContextProvider(),
        valuation_executor=FakeValuationExecutor(delta_npv=12.0),
    )

    summary = runner.run_once()
    run_id = summary.run_id
    assert run_id is not None
    rows = runner.knowledge.get_run_states(run_id=run_id, asset_id="asset-1", limit=100)
    stages = {row.stage: row for row in rows}
    assert "prepare_context" in stages
    assert "extract" in stages
    assert "map_signal" in stages
    assert "update_dossier" in stages
    assert "asset_run" in stages
    assert stages["asset_run"].status == "success"
    assert stages["extract"].checkpoint_json.get("document_id")
    runner.close()


def test_load_watchlist_config_supports_directory_and_dedupes(tmp_path: Path) -> None:
    watchlist_dir = tmp_path / "watchlists"
    watchlist_dir.mkdir(parents=True, exist_ok=True)

    (watchlist_dir / "watchlist_a.yaml").write_text(
        yaml.safe_dump(
            {
                "polling_interval_seconds": 120,
                "state_path": "outputs/a.json",
                "knowledge_db_path": "outputs/a.db",
                "valuation_output_dir": "outputs/a",
                "watchlist": [
                    {"company_id": "c1", "asset_id": "asset-1", "ticker": "AAA"},
                    {"company_id": "c2", "asset_id": "asset-dup", "ticker": "DUP"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (watchlist_dir / "watchlist_b.yaml").write_text(
        yaml.safe_dump(
            {
                "polling_interval_seconds": 999,
                "watchlist": [
                    {"company_id": "c3", "asset_id": "asset-2", "ticker": "BBB"},
                    {"company_id": "c4", "asset_id": "asset-dup-2", "ticker": "DUP"},
                ],
            }
        ),
        encoding="utf-8",
    )

    cfg = load_watchlist_config(watchlist_dir)
    assert cfg.polling_interval_seconds == 120
    assert [a.asset_id for a in cfg.watchlist] == ["asset-1", "asset-dup", "asset-2"]
    assert [a.company_id for a in cfg.watchlist if a.ticker == "DUP"] == ["c2"]


def test_runner_competitor_discovery_runs_then_skips_within_seven_days(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeCompetitorDiscoveryEngine:
        calls = 0

        def __init__(self, store, request_delay_seconds: float = 0.0) -> None:  # noqa: ARG002
            self._store = store

        def discover(self, asset_id: str, asset_node_id: str, indication: str):
            FakeCompetitorDiscoveryEngine.calls += 1
            program = CompetitorProgram(
                asset_id=asset_id,
                company="CompCo",
                drug_name="CompDrug",
                nct_id=f"NCT-COMP-{FakeCompetitorDiscoveryEngine.calls}",
                indication=indication,
            )
            self._store.add_competitor_program(program)
            node = KGNode(
                node_type=NodeType.COMPETITOR_PROGRAM,
                name=program.drug_name,
                external_id=program.nct_id,
            )
            self._store.upsert_node(node)
            self._store.add_edge(
                KGEdge(
                    source_node_id=asset_node_id,
                    target_node_id=node.node_id,
                    edge_type=EdgeType.COMPETES_WITH,
                    confidence=1.0,
                )
            )
            return CompetitorDiscoveryResult(
                asset_id=asset_id,
                indication=indication,
                programs_found=[program],
                kg_edges_added=1,
                errors=[],
            )

    monkeypatch.setattr(
        "bve.pipeline.watchlist_runner.CompetitorDiscoveryEngine",
        FakeCompetitorDiscoveryEngine,
    )

    asset = WatchlistAsset(
        company_id="company-1",
        asset_id="asset-1",
        indication="NSCLC",
        drug_name="DrugA",
        connectors=["press_release"],
    )
    runner = WatchlistPipelineRunner(
        _config(tmp_path, [asset]),
        connectors={"press_release": FakeConnector()},
        extractor=FakeExtractor(),
        mapping_engine=FakeMappingEngine(),
        context_provider=FakeContextProvider(),
        valuation_executor=FakeValuationExecutor(delta_npv=10.0),
    )
    runner.knowledge.upsert_asset_registry_entry(
        AssetRegistryEntry(
            asset_id="asset-1",
            ticker="DRUG",
            company_id="company-1",
            drug_name="DrugA",
            indication="NSCLC",
            therapeutic_area="oncology",
            modality="small_molecule",
            stage="phase_2",
            source="test",
        )
    )

    first = runner.run_once()
    second = runner.run_once()

    assert first.assets[0].status == "success"
    assert second.assets[0].status == "success"
    assert FakeCompetitorDiscoveryEngine.calls == 1
    assert runner.knowledge.count_competitor_programs("asset-1") == 1
    asset_node = runner.knowledge.find_node_by_external_id(NodeType.ASSET, "asset-1")
    assert asset_node is not None
    assert runner.knowledge.find_competing_assets(asset_node.node_id)
    assert any(
        log.stage == "competitor_discovery" and log.status == "skipped" for log in second.stage_logs
    )
    runner.close()


def test_runner_competitor_discovery_errors_do_not_fail_asset_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FailingCompetitorDiscoveryEngine:
        def __init__(self, store, request_delay_seconds: float = 0.0) -> None:  # noqa: ARG002
            self._store = store

        def discover(self, asset_id: str, asset_node_id: str, indication: str):  # noqa: ARG002
            raise RuntimeError("discovery failed")

    monkeypatch.setattr(
        "bve.pipeline.watchlist_runner.CompetitorDiscoveryEngine",
        FailingCompetitorDiscoveryEngine,
    )

    runner = WatchlistPipelineRunner(
        _config(
            tmp_path,
            [
                WatchlistAsset(
                    company_id="company-1",
                    asset_id="asset-1",
                    indication="NSCLC",
                    connectors=["press_release"],
                )
            ],
        ),
        connectors={"press_release": FakeConnector()},
        extractor=FakeExtractor(),
        mapping_engine=FakeMappingEngine(),
        context_provider=FakeContextProvider(),
        valuation_executor=FakeValuationExecutor(delta_npv=8.0),
    )

    summary = runner.run_once()
    assert summary.assets[0].status == "success"
    assert any(
        log.stage == "competitor_discovery" and log.status == "failure"
        for log in summary.stage_logs
    )
    runner.close()


def test_runner_emits_stage_latency_and_connector_health_metrics(tmp_path: Path) -> None:
    runner = WatchlistPipelineRunner(
        _config(
            tmp_path,
            [
                WatchlistAsset(
                    company_id="company-1", asset_id="asset-1", connectors=["press_release"]
                )
            ],
        ),
        connectors={"press_release": FakeConnector()},
        extractor=FakeExtractor(),
        mapping_engine=FakeMappingEngine(),
        context_provider=FakeContextProvider(),
        valuation_executor=FakeValuationExecutor(delta_npv=8.0),
    )

    summary = runner.run_once()
    assert summary.stage_latencies
    stages = {metric.stage for metric in summary.stage_latencies}
    assert {"ingestion", "extraction", "valuation", "alerts"}.issubset(stages)
    assert summary.connector_health
    connector = [m for m in summary.connector_health if m.connector == "press_release"][0]
    assert connector.n_runs_sampled >= 1
    assert connector.success_rate == 1.0
    assert connector.healthy is True
    runner.close()
