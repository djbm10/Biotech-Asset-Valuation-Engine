from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from bve.connectors.base import FetchResult
from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, EndpointType, TrialPhase
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument
from bve.intelligence.extraction.result import ExtractionResult, ExtractionStatus
from bve.intelligence.knowledge_layer import StoredValuationDiff
from bve.intelligence.phase2.mapping_engine import MappingBatchResult
from bve.intelligence.phase2.policy import MappingPolicy
from bve.intelligence.schemas.proposals import AssumptionChangeProposal
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import ChangeMode, EventType
from bve.models.market_model import MarketModel
from bve.pipeline.change_detector import MaterialChangeDetector, MaterialityRule
from bve.pipeline.watchlist_runner import (
    AssetValuationContext,
    ConnectorRuntimeConfig,
    WatchlistAsset,
    WatchlistPipelineRunner,
    WatchlistRunnerConfig,
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


def _config(tmp_path: Path, watchlist: list[WatchlistAsset]) -> WatchlistRunnerConfig:
    return WatchlistRunnerConfig(
        polling_interval_seconds=60,
        state_path=str(tmp_path / "state.json"),
        knowledge_db_path=str(tmp_path / "knowledge.db"),
        valuation_output_dir=str(tmp_path / "valuation"),
        connectors={
            "press_release": ConnectorRuntimeConfig(enabled=True, limit=10),
        },
        watchlist=watchlist,
    )


def test_watchlist_runner_is_idempotent_for_duplicate_documents(tmp_path: Path):
    connector = FakeConnector()
    valuation = FakeValuationExecutor(delta_npv=5.0)
    runner = WatchlistPipelineRunner(
        _config(
            tmp_path,
            [WatchlistAsset(company_id="company-1", asset_id="asset-1", connectors=["press_release"])],
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
    assert len(runner.knowledge.get_events(company_id="company-1", asset_id="asset-1", limit=10)) == 1
    assert len(runner.knowledge.get_valuation_diffs(company_id="company-1", asset_id="asset-1", limit=10)) == 1
    assert any(log.stage == "dedupe_event" and log.status == "skipped" for log in second.stage_logs)
    runner.close()


def test_watchlist_runner_isolates_failures_per_asset(tmp_path: Path):
    connector = FakeConnector()
    runner = WatchlistPipelineRunner(
        _config(
            tmp_path,
            [
                WatchlistAsset(company_id="company-fail", asset_id="asset-fail", connectors=["press_release"]),
                WatchlistAsset(company_id="company-ok", asset_id="asset-ok", connectors=["press_release"]),
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
    assert len(runner.knowledge.get_events(company_id="company-ok", asset_id="asset-ok", limit=10)) == 1
    runner.close()


def test_watchlist_runner_generates_memo_on_material_change(tmp_path: Path):
    runner = WatchlistPipelineRunner(
        _config(
            tmp_path,
            [WatchlistAsset(company_id="company-1", asset_id="asset-1", connectors=["press_release"])],
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
            [WatchlistAsset(company_id="company-1", asset_id="asset-1", connectors=["press_release"])],
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
