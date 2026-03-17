from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, EndpointType, TrialPhase
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument
from bve.intelligence.extraction.result import ExtractionResult, ExtractionStatus
from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace, StoredValuationDiff
from bve.intelligence.phase2.mapping_engine import MappingBatchResult
from bve.intelligence.schemas.proposals import AssumptionChangeProposal
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import ChangeMode, EventType
from bve.models.market_model import MarketModel
from bve.pipeline.history_replay import HistoryReplayRunner
from bve.pipeline.watchlist_runner import (
    AssetValuationContext,
    WatchlistAsset,
    WatchlistRunnerConfig,
)

_NOW = datetime.now(timezone.utc)


class FakeExtractor:
    def __init__(self) -> None:
        self.calls = 0

    def extract(self, document: RawDocument, event_id: Optional[str] = None) -> ExtractionResult:
        self.calls += 1
        signal = StructuredSignal(
            id=f"sig-{document.id}-{self.calls}",
            event_id=event_id or f"evt-{document.id}",
            asset_id=document.entity_hints.asset_id,
            company_id=document.entity_hints.company_id,
            event_type=EventType.TRIAL_READOUT,
            signal_date=(document.published_at or _NOW).date(),
            trial_phase=TrialPhase.PHASE_2,
            primary_endpoint_met=True,
            extraction_model="fake-replay-extractor",
            extraction_confidence=0.95,
            created_at=_NOW + timedelta(minutes=self.calls),
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
            rationale="deterministic replay extraction",
            extraction_model="fake-replay-extractor",
            prompt_version="v1.0",
            latency_ms=1,
            extracted_at=signal.created_at,
        )


class FakeMappingEngine:
    def __init__(self) -> None:
        from bve.intelligence.phase2.policy import MappingPolicy

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
            id=f"proposal-{signal.id}",
            signal_id=signal.id,
            asset_id=signal.asset_id,
            engine_asset_id=engine_asset_id,
            parameter_path="trials[*].success_probability",
            current_value=0.50,
            proposed_value=0.52,
            change_mode=ChangeMode.AUTO,
            bound_pct=10.0,
            event_type=signal.event_type,
            rationale="test replay mapping",
            created_at=signal.created_at,
        )
        return MappingBatchResult(signal_id=signal.id, proposals=[proposal], audit_log=[], skipped=[])


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
    def __init__(self, delta_npv: float = 35.0) -> None:
        self.calls = 0
        self.delta_npv = delta_npv

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
            run_id=f"replay-run-{signal.event_id}-{self.calls}",
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


def _config(tmp_path: Path) -> WatchlistRunnerConfig:
    return WatchlistRunnerConfig(
        knowledge_db_path=str(tmp_path / "knowledge.db"),
        valuation_output_dir=str(tmp_path / "valuation"),
        watchlist=[
            WatchlistAsset(
                company_id="company-1",
                asset_id="asset-1",
                indication="test indication",
            )
        ],
    )


def _raw_document(*, doc_id: str, retrieved_at: datetime) -> RawDocument:
    return RawDocument.from_text(
        id=doc_id,
        source="press_release",
        title=f"{doc_id} title",
        raw_text=f"Positive clinical update with endpoint details for {doc_id}.",
        source_url=f"https://example.org/{doc_id}",
        published_at=retrieved_at,
        retrieved_at=retrieved_at,
        entity_hints=EntityHints(asset_id="asset-1", company_id="company-1"),
    )


def test_history_replay_creates_signals_diffs_and_memo(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    store = KnowledgeStore(cfg.knowledge_db_path)
    try:
        store.add_raw_document(
            _raw_document(doc_id="doc-1", retrieved_at=_NOW),
            SourceTrace(source_type="seed", source_ref="seed:doc-1"),
        )
    finally:
        store.close()

    runner = HistoryReplayRunner(
        cfg,
        extractor=FakeExtractor(),
        mapping_engine=FakeMappingEngine(),
        context_provider=FakeContextProvider(),
        valuation_executor=FakeValuationExecutor(delta_npv=35.0),
    )
    try:
        first = runner.replay()
        second = runner.replay()

        assert first.documents_replayed == 1
        assert first.structured_signals_persisted == 1
        assert first.valuation_diffs_persisted == 1
        assert first.memos_persisted == 1
        assert second.structured_signals_persisted == 1
        assert second.valuation_diffs_persisted == 1

        assert len(runner.knowledge.get_raw_documents(limit=10)) == 1
        assert len(runner.knowledge.get_structured_signals(limit=10)) == 1
        assert len(runner.knowledge.get_valuation_diffs(limit=10)) == 1
        assert len(runner.knowledge.get_memos(limit=10)) == 1
    finally:
        runner.close()


def test_history_replay_since_filter_limits_documents(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    store = KnowledgeStore(cfg.knowledge_db_path)
    try:
        store.add_raw_document(
            _raw_document(doc_id="doc-old", retrieved_at=_NOW - timedelta(days=10)),
            SourceTrace(source_type="seed", source_ref="seed:doc-old"),
        )
        store.add_raw_document(
            _raw_document(doc_id="doc-new", retrieved_at=_NOW - timedelta(days=1)),
            SourceTrace(source_type="seed", source_ref="seed:doc-new"),
        )
    finally:
        store.close()

    runner = HistoryReplayRunner(
        cfg,
        extractor=FakeExtractor(),
        mapping_engine=FakeMappingEngine(),
        context_provider=FakeContextProvider(),
        valuation_executor=FakeValuationExecutor(delta_npv=35.0),
    )
    try:
        summary = runner.replay(since="7d")
        assert summary.documents_replayed == 1
        assert len(runner.knowledge.get_structured_signals(limit=10)) == 1
    finally:
        runner.close()
