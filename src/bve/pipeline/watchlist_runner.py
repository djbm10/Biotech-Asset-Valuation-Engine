"""Automated watchlist runner for the intelligence-to-valuation pipeline."""
from __future__ import annotations

import hashlib
import inspect
import json
import logging
import time
import uuid
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Optional, Protocol

import yaml
from pydantic import BaseModel, Field

from bve.connectors import (
    ClinicalTrialsConnector,
    FDAConnector,
    PressReleaseConnector,
    SECEdgarConnector,
)
from bve.connectors.base import FetchResult, SourceConnector
from bve.entities.asset import Asset
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial
from bve.intelligence.extraction.extractor import SignalExtractor
from bve.intelligence.extraction.llm_client import AnthropicClient, FakeLLMClient, OpenAIClient
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument
from bve.intelligence.extraction.result import ExtractionResult, ExtractionStatus
from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace, StoredValuationDiff
from bve.intelligence.memo_generation import WeeklyMemoGenerator, WeeklyMemoInput
from bve.intelligence.phase2 import MappingEngine, ReviewQueue, ValuationSession
from bve.intelligence.schemas.proposals import AssumptionChangeProposal
from bve.intelligence.schemas.runs import ReviewDecision
from bve.intelligence.schemas.signals import Event, StructuredSignal
from bve.models.market_model import MarketModel
from bve.pipeline.change_detector import MaterialChangeDetector, MaterialityRule
from bve.pipeline.pipeline_state import PipelineStateStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConnectorRuntimeConfig(BaseModel):
    """Runtime settings for one connector."""

    enabled: bool = True
    limit: int = Field(default=20, ge=1)
    options: dict[str, Any] = Field(default_factory=dict)
    # Retry policy for transient connector failures.
    max_retries: int = Field(default=3, ge=0)
    retry_backoff_seconds: float = Field(default=2.0, ge=0.0)


class WatchlistAsset(BaseModel):
    """One tracked asset in the watchlist."""

    company_id: str
    asset_id: str
    drug_name: Optional[str] = None
    indication: Optional[str] = None
    ticker: Optional[str] = None
    nct_id: Optional[str] = None
    valuation_config: Optional[str] = None
    connectors: Optional[list[str]] = None
    # Optional market cap for ranking mispricing mode ($M). When None and ticker
    # is set, the ranking engine will attempt a yfinance lookup.
    market_cap_millions: Optional[float] = None
    # Per-asset overrides for RankingConfig fields (e.g. event_type_weight: 0.2).
    ranking_overrides: Optional[dict[str, float]] = None


class ExtractionRuntimeConfig(BaseModel):
    """Extractor backend settings."""

    backend: Literal["anthropic", "openai", "fake"] = "fake"
    model: Optional[str] = None
    api_key: Optional[str] = None


class WatchlistRunnerConfig(BaseModel):
    """Top-level watchlist runner configuration."""

    polling_interval_seconds: int = Field(default=3600, ge=1)
    state_path: str = "outputs/watchlist/pipeline_state.json"
    knowledge_db_path: str = "outputs/intelligence_phase2/knowledge.db"
    valuation_output_dir: str = "outputs/intelligence_phase2/watchlist"
    materiality: MaterialityRule = Field(default_factory=MaterialityRule)
    extraction: ExtractionRuntimeConfig = Field(default_factory=ExtractionRuntimeConfig)
    connectors: dict[str, ConnectorRuntimeConfig] = Field(default_factory=dict)
    watchlist: list[WatchlistAsset]
    # Optional alerting config. None = alerting disabled (default).
    alerts: Optional[Any] = None  # AlertsConfig at runtime; Any avoids circular import
    # Optional ranking config. Uses RankingConfig defaults when absent.
    ranking: Optional[Any] = None  # RankingConfig at runtime


class PipelineStageLog(BaseModel):
    """One stage log entry."""

    run_id: Optional[str] = None
    company_id: str
    asset_id: str
    stage: str
    status: Literal["success", "failure", "skipped"]
    started_at: datetime
    finished_at: datetime
    message: Optional[str] = None


class AssetRunSummary(BaseModel):
    """Summary for a single asset in one run cycle."""

    run_id: Optional[str] = None
    company_id: str
    asset_id: str
    status: Literal["success", "failure"]
    documents_fetched: int = 0
    documents_processed: int = 0
    events_created: int = 0
    signals_created: int = 0
    proposals_generated: int = 0
    valuation_runs: int = 0
    valuation_diffs_persisted: int = 0
    review_decisions_logged: int = 0
    memo_generated: bool = False
    memo_id: Optional[str] = None
    dossier_id: Optional[str] = None
    alerts_fired: int = 0
    errors: list[str] = Field(default_factory=list)


class WatchlistRunSummary(BaseModel):
    """Summary of one full watchlist cycle."""

    run_id: Optional[str] = None
    started_at: datetime
    finished_at: datetime
    assets: list[AssetRunSummary] = Field(default_factory=list)
    stage_logs: list[PipelineStageLog] = Field(default_factory=list)


class AssetValuationContext(BaseModel):
    """Valuation inputs for one asset."""

    asset: Asset
    company: Company
    trials: list[ClinicalTrial]
    market_model: MarketModel


class AssetContextProvider(Protocol):
    """Protocol for obtaining valuation context per tracked asset."""

    def get_context(self, asset: WatchlistAsset) -> AssetValuationContext:
        ...


class ConfigAssetContextProvider:
    """Builds valuation context from existing asset YAML config files."""

    def __init__(self) -> None:
        self._cache: dict[str, AssetValuationContext] = {}

    def get_context(self, asset: WatchlistAsset) -> AssetValuationContext:
        if not asset.valuation_config:
            raise ValueError(
                f"Asset {asset.asset_id} is missing valuation_config; required for mapping/valuation"
            )
        path = str(Path(asset.valuation_config).expanduser().resolve())
        cached = self._cache.get(path)
        if cached is not None:
            return cached

        # Reuse existing config object builders from the v1 CLI.
        from bve.cli.run_asset import _build_objects, _load_config

        cfg = _load_config(Path(path))
        built_asset, built_company, trials, market_model = _build_objects(cfg)
        ctx = AssetValuationContext(
            asset=built_asset,
            company=built_company,
            trials=trials,
            market_model=market_model,
        )
        self._cache[path] = ctx
        return ctx


class ValuationExecutor(Protocol):
    """Protocol for applying approved proposals and returning stored diff shape."""

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
        ...


class Phase2SessionValuationExecutor:
    """Valuation executor backed by `ValuationSession` per asset."""

    def __init__(self, output_root: str | Path) -> None:
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, ValuationSession] = {}

    @staticmethod
    def _session_key(company_id: str, asset_id: str) -> str:
        return f"{company_id}::{asset_id}"

    def _get_session(
        self,
        *,
        company_id: str,
        asset_id: str,
        context: AssetValuationContext,
    ) -> ValuationSession:
        key = self._session_key(company_id, asset_id)
        existing = self._sessions.get(key)
        if existing is not None:
            return existing
        session = ValuationSession(
            asset=context.asset,
            company=context.company,
            trials=context.trials,
            market_model=context.market_model,
            output_dir=self.output_root / asset_id,
        )
        self._sessions[key] = session
        return session

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

        session = self._get_session(
            company_id=company_id,
            asset_id=asset_id,
            context=context,
        )
        record = session.apply_proposals(
            proposals=proposals,
            effective_values=effective_values,
            signals_by_id={signal.id: signal},
            analyst_id="system-watchlist",
            notes="automated watchlist run",
            run_at=run_at,
        )
        diff = record.diff
        return StoredValuationDiff(
            run_id=diff.run_id,
            event_id=diff.event_id,
            asset_id=diff.asset_id,
            valuation_before=diff.valuation_before.model_dump(mode="json"),
            valuation_after=diff.valuation_after.model_dump(mode="json"),
            delta_npv=diff.delta_npv,
            created_at=diff.generated_at,
            valuation_delta={
                "delta_npv": diff.delta_npv,
                "delta_nav_per_share": diff.delta_nav_per_share,
                "delta_mc_mean_millions": diff.delta_mc_mean_millions,
                "delta_bull_rnpv_millions": diff.delta_bull_rnpv_millions,
                "delta_base_rnpv_millions": diff.delta_base_rnpv_millions,
                "delta_bear_rnpv_millions": diff.delta_bear_rnpv_millions,
            },
            assumptions_changed=[c.model_dump(mode="json") for c in diff.assumptions_changed],
            applied_overrides=diff.applied_overrides,
        )


class WatchlistPipelineRunner:
    """Runs the full intelligence-to-valuation pipeline for tracked assets."""

    def __init__(
        self,
        config: WatchlistRunnerConfig,
        *,
        connectors: Optional[dict[str, SourceConnector]] = None,
        extractor: Optional[SignalExtractor] = None,
        mapping_engine: Optional[MappingEngine] = None,
        context_provider: Optional[AssetContextProvider] = None,
        valuation_executor: Optional[ValuationExecutor] = None,
        knowledge_store: Optional[KnowledgeStore] = None,
        state_store: Optional[PipelineStateStore] = None,
        change_detector: Optional[MaterialChangeDetector] = None,
        memo_generator: Optional[WeeklyMemoGenerator] = None,
        alert_router: Optional[Any] = None,  # AlertRouter; Any avoids import at module level
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.config = config
        self.logger = logger or logging.getLogger("bve.watchlist")
        self.connectors = connectors or _build_connectors(config.connectors)
        self.extractor = extractor or _build_extractor(config.extraction)
        self.mapping_engine = mapping_engine or MappingEngine()
        self.context_provider = context_provider or ConfigAssetContextProvider()
        self.valuation_executor = valuation_executor or Phase2SessionValuationExecutor(
            config.valuation_output_dir
        )
        self.knowledge = knowledge_store or KnowledgeStore(config.knowledge_db_path)
        self.state = state_store or PipelineStateStore(config.state_path)
        self.change_detector = change_detector or MaterialChangeDetector(config.materiality)
        self.memo_generator = memo_generator or WeeklyMemoGenerator()
        self.alert_router = alert_router  # None = alerting disabled; never raises

    def close(self) -> None:
        self.knowledge.close()

    def run_once(self) -> WatchlistRunSummary:
        run_id = str(uuid.uuid4())
        started = _utcnow()
        stage_logs: list[PipelineStageLog] = []
        results: list[AssetRunSummary] = []

        for asset in self.config.watchlist:
            results.append(self._run_asset(asset, stage_logs=stage_logs, run_id=run_id))
            # Persist after each asset so retries do not repeat completed work.
            self.state.save()

        finished = _utcnow()
        duration_seconds = round((finished - started).total_seconds(), 3)
        self.logger.info(
            "watchlist_cycle_summary %s",
            json.dumps(
                {
                    "run_id": run_id,
                    "assets_total": len(results),
                    "assets_failed": sum(1 for a in results if a.status == "failure"),
                    "assets_succeeded": sum(1 for a in results if a.status == "success"),
                    "duration_seconds": duration_seconds,
                    "started_at": started.isoformat(),
                    "finished_at": finished.isoformat(),
                },
                ensure_ascii=True,
                sort_keys=True,
            ),
        )
        return WatchlistRunSummary(
            run_id=run_id,
            started_at=started,
            finished_at=finished,
            assets=results,
            stage_logs=stage_logs,
        )

    def run_forever(self, *, max_cycles: Optional[int] = None) -> None:
        cycle = 0
        while True:
            cycle += 1
            summary = self.run_once()
            self.logger.info(
                "watchlist cycle %s finished: assets=%s failures=%s",
                cycle,
                len(summary.assets),
                sum(1 for a in summary.assets if a.status == "failure"),
            )
            if max_cycles is not None and cycle >= max_cycles:
                return
            time.sleep(self.config.polling_interval_seconds)

    def _run_asset(
        self,
        asset_cfg: WatchlistAsset,
        *,
        stage_logs: list[PipelineStageLog],
        run_id: str,
    ) -> AssetRunSummary:
        summary = AssetRunSummary(
            run_id=run_id,
            company_id=asset_cfg.company_id,
            asset_id=asset_cfg.asset_id,
            status="success",
        )

        self.state.mark_run_started(asset_cfg.company_id, asset_cfg.asset_id)
        run_started = _utcnow()

        try:
            context = self._run_stage(
                stage_logs,
                asset_cfg,
                run_id=run_id,
                stage="prepare_context",
                fn=lambda: self.context_provider.get_context(asset_cfg),
            )

            hints = EntityHints(
                asset_id=asset_cfg.asset_id,
                company_id=asset_cfg.company_id,
                drug_name=asset_cfg.drug_name,
                indication=asset_cfg.indication,
                ticker=asset_cfg.ticker,
                nct_id=asset_cfg.nct_id,
            )

            created_signals: list[StructuredSignal] = []
            created_signal_ids: set[str] = set()
            review_decisions: list[ReviewDecision] = []
            valuation_diffs: list[StoredValuationDiff] = []
            ambiguous_signal_ids: list[str] = []

            for source_name in self._asset_connectors(asset_cfg):
                connector = self.connectors[source_name]
                source_cfg = self.config.connectors[source_name]
                since = self.state.get_since(asset_cfg.company_id, asset_cfg.asset_id, source_name)

                fetch_result = self._run_stage(
                    stage_logs,
                    asset_cfg,
                    run_id=run_id,
                    stage=f"fetch:{source_name}",
                    fn=lambda c=connector, s=since, l=source_cfg.limit, o=source_cfg.options, h=hints, mr=source_cfg.max_retries, rb=source_cfg.retry_backoff_seconds: self._fetch_connector(
                        connector=c,
                        entity_hints=h,
                        since=s,
                        limit=l,
                        options=o,
                        max_retries=mr,
                        retry_backoff_seconds=rb,
                    ),
                )
                assert isinstance(fetch_result, FetchResult)
                summary.documents_fetched += len(fetch_result.documents)

                for raw_doc in fetch_result.documents:
                    normalized = self._normalize_document(raw_doc, hints)
                    event_id = self._event_id_for_document(
                        company_id=asset_cfg.company_id,
                        asset_id=asset_cfg.asset_id,
                        document=normalized,
                    )
                    event_already_exists = (
                        self.state.seen_event(asset_cfg.company_id, asset_cfg.asset_id, event_id)
                        or self.knowledge.event_exists(event_id)
                    )
                    if event_already_exists:
                        self.state.mark_document_processed(asset_cfg.company_id, asset_cfg.asset_id, normalized.id)
                        self.state.mark_event_processed(asset_cfg.company_id, asset_cfg.asset_id, event_id)
                        # Resume-safe behavior: if prior run crashed before valuation,
                        # continue from persisted signal without re-extracting.
                        if not self.knowledge.valuation_diff_exists_for_event(event_id):
                            resumed_signal = self.knowledge.get_structured_signal_by_event_id(event_id)
                            if resumed_signal is not None:
                                self._queue_signal(
                                    resumed_signal,
                                    created_signals=created_signals,
                                    created_signal_ids=created_signal_ids,
                                )
                        self._log_stage(
                            stage_logs,
                            asset_cfg,
                            run_id=run_id,
                            stage="dedupe_event",
                            status="skipped",
                            started_at=run_started,
                            finished_at=_utcnow(),
                            message=f"duplicate event {event_id}",
                        )
                        continue

                    if self.state.seen_document(asset_cfg.company_id, asset_cfg.asset_id, normalized.id):
                        self._log_stage(
                            stage_logs,
                            asset_cfg,
                            run_id=run_id,
                            stage="dedupe_document",
                            status="skipped",
                            started_at=run_started,
                            finished_at=_utcnow(),
                            message=f"duplicate document {normalized.id}",
                        )
                        continue

                    self.knowledge.add_raw_document(
                        normalized,
                        SourceTrace(
                            source_type=normalized.source,
                            source_ref=normalized.source_url or normalized.id,
                        ),
                    )

                    extraction = self._run_stage(
                        stage_logs,
                        asset_cfg,
                        run_id=run_id,
                        stage="extract",
                        fn=lambda d=normalized, e=event_id: self.extractor.extract(d, event_id=e),
                    )
                    assert isinstance(extraction, ExtractionResult)
                    extraction_record = self.knowledge.add_extraction_result(
                        extraction,
                        SourceTrace(
                            source_type="extraction",
                            source_ref=f"document:{normalized.id}",
                        ),
                        raw_document_id=normalized.id,
                    )

                    self.state.mark_document_processed(asset_cfg.company_id, asset_cfg.asset_id, normalized.id)
                    summary.documents_processed += 1

                    if extraction.status != ExtractionStatus.SUCCESS or extraction.signal is None:
                        continue

                    signal = extraction.signal
                    if extraction.ambiguity_flag:
                        ambiguous_signal_ids.append(signal.id)

                    self.knowledge.add_structured_signal(
                        signal,
                        SourceTrace(
                            source_type="structured_signal",
                            source_ref=f"extraction:{extraction_record.id}",
                        ),
                        extraction_result_id=extraction_record.id,
                    )

                    event = self._event_from_extraction(
                        signal=signal,
                        document=normalized,
                        extraction=extraction,
                    )
                    self.knowledge.add_event(
                        event,
                        SourceTrace(
                            source_type="event",
                            source_ref=f"signal:{signal.id}",
                        ),
                        signal_id=signal.id,
                    )

                    self.state.mark_event_processed(asset_cfg.company_id, asset_cfg.asset_id, event.id)
                    summary.events_created += 1
                    summary.signals_created += 1
                    self._queue_signal(
                        signal,
                        created_signals=created_signals,
                        created_signal_ids=created_signal_ids,
                    )
                    # Alert condition 1 (safety) + condition 3 (low-conf/high-severity).
                    if self.alert_router is not None:
                        self.alert_router.enqueue_signal_alerts(
                            signal=signal,
                            extraction=extraction,
                            run_id=run_id,
                            headline=normalized.title,
                            source_url=normalized.source_url,
                        )

                self.state.set_last_fetch(
                    asset_cfg.company_id,
                    asset_cfg.asset_id,
                    source_name,
                    fetch_result.fetched_at,
                )

            # Stage 5/6: map + valuation integration
            for signal in created_signals:
                current_session_context = self._current_context_for_mapping(
                    company_id=asset_cfg.company_id,
                    asset_id=asset_cfg.asset_id,
                    fallback=context,
                )
                mapping_batch = self._run_stage(
                    stage_logs,
                    asset_cfg,
                    run_id=run_id,
                    stage="map_signal",
                    fn=lambda s=signal, ctx=current_session_context: self.mapping_engine.map_signal(
                        s,
                        engine_asset_id=ctx.asset.id,
                        asset=ctx.asset,
                        trials=ctx.trials,
                        market_model=ctx.market_model,
                    ),
                )
                summary.proposals_generated += len(mapping_batch.proposals)

                queue = ReviewQueue(policy=self.mapping_engine.policy)
                routing = queue.route(signal, mapping_batch.proposals)

                # Route non-auto proposals to deferred review automatically.
                for item in routing.queued:
                    review = queue.record_decision(
                        item_id=item.id,
                        decision="deferred",
                        reviewer_id="system-watchlist",
                        rationale=item.route_reason,
                        notes="Queued for manual review by automated watchlist runner",
                        reviewed_at=run_started,
                    )
                    self.knowledge.add_review_decision(
                        review,
                        company_id=asset_cfg.company_id,
                        asset_id=asset_cfg.asset_id,
                        source_trace=SourceTrace(
                            source_type="review_queue",
                            source_ref=f"proposal:{review.proposal_id}",
                        ),
                    )
                    summary.review_decisions_logged += 1
                    review_decisions.append(review)

                effective_values = queue.effective_overrides(mapping_batch.proposals)
                stored_diff = self.valuation_executor.apply(
                    company_id=asset_cfg.company_id,
                    asset_id=asset_cfg.asset_id,
                    context=current_session_context,
                    signal=signal,
                    proposals=mapping_batch.proposals,
                    effective_values=effective_values,
                    run_at=run_started,
                )
                if stored_diff is None:
                    continue

                # Snapshot market cap at diff time for historical mispricing analysis.
                stored_diff.market_cap_snapshot_millions = self._get_market_cap(asset_cfg)

                saved_diff = self.knowledge.add_valuation_diff(
                    stored_diff,
                    company_id=asset_cfg.company_id,
                    source_trace=SourceTrace(
                        source_type="valuation_integration",
                        source_ref=f"run:{stored_diff.run_id}",
                    ),
                    assumptions_snapshot=stored_diff.applied_overrides,
                    valuation_snapshot=stored_diff.valuation_after,
                )
                valuation_diffs.append(saved_diff)
                summary.valuation_runs += 1
                summary.valuation_diffs_persisted += 1
                # Alert condition 2: material valuation change (dual gate: abs + relative).
                if self.alert_router is not None:
                    self.alert_router.enqueue_diff_alerts(
                        diff=saved_diff,
                        signal=signal,
                        run_id=run_id,
                    )

            # Stage 8: update dossier
            dossier = self._run_stage(
                stage_logs,
                asset_cfg,
                run_id=run_id,
                stage="update_dossier",
                fn=lambda: self.knowledge.generate_dossier(
                    company_id=asset_cfg.company_id,
                    asset_id=asset_cfg.asset_id,
                    persist=True,
                ),
            )
            summary.dossier_id = dossier.id

            # Stage 9: memo if material changes
            if self.change_detector.should_generate_weekly_memo(valuation_diffs):
                period_end = run_started.date()
                period_start = period_end - timedelta(days=6)
                recent_reviews = self.knowledge.get_review_decisions(
                    company_id=asset_cfg.company_id,
                    asset_id=asset_cfg.asset_id,
                    date_from=period_start,
                    date_to=period_end,
                    limit=500,
                )
                memo = self.memo_generator.generate(
                    WeeklyMemoInput(
                        dossier=dossier,
                        structured_events=created_signals,
                        valuation_diffs=valuation_diffs,
                        review_decisions=recent_reviews,
                        ambiguous_signal_ids=sorted(set(ambiguous_signal_ids)),
                        generated_at=run_started,
                    ),
                    period_start=period_start,
                    period_end=period_end,
                    week_ending=period_end,
                )
                self.knowledge.add_memo(
                    memo.to_memo_record(
                        SourceTrace(
                            source_type="memo_generation",
                            source_ref=f"memo:{memo.id}",
                        )
                    )
                )
                summary.memo_generated = True
                summary.memo_id = memo.id

            # Flush all enqueued alerts for this asset (batched per-asset).
            if self.alert_router is not None:
                fired = self.alert_router.flush(asset_cfg.asset_id, run_id=run_id)
                summary.alerts_fired = len(fired)

            self.state.mark_run_succeeded(asset_cfg.company_id, asset_cfg.asset_id)
            self._log_asset_summary(summary=summary, run_started=run_started)
            return summary

        except Exception as exc:  # failure isolation per asset
            summary.status = "failure"
            summary.errors.append(str(exc))
            self.state.mark_run_failed(
                asset_cfg.company_id,
                asset_cfg.asset_id,
                error=str(exc),
            )
            self._log_stage(
                stage_logs,
                asset_cfg,
                run_id=run_id,
                stage="asset_run",
                status="failure",
                started_at=run_started,
                finished_at=_utcnow(),
                message=str(exc),
            )
            self._log_asset_summary(summary=summary, run_started=run_started)
            return summary

    def _asset_connectors(self, asset_cfg: WatchlistAsset) -> list[str]:
        if asset_cfg.connectors:
            return [
                name for name in asset_cfg.connectors
                if name in self.connectors and self.config.connectors.get(name, ConnectorRuntimeConfig()).enabled
            ]
        return [
            name
            for name, connector_cfg in self.config.connectors.items()
            if connector_cfg.enabled and name in self.connectors
        ]

    def _get_market_cap(self, asset_cfg: WatchlistAsset) -> Optional[float]:
        """Return market cap ($M) for an asset, preferring config value over yfinance."""
        if asset_cfg.market_cap_millions is not None:
            return asset_cfg.market_cap_millions
        if asset_cfg.ticker:
            try:
                import yfinance as yf  # optional dependency
                info = yf.Ticker(asset_cfg.ticker).fast_info
                mc = getattr(info, "market_cap", None)
                if mc:
                    return float(mc) / 1e6
            except Exception:
                pass
        return None

    def _fetch_connector(
        self,
        *,
        connector: SourceConnector,
        entity_hints: EntityHints,
        since: Optional[datetime],
        limit: int,
        options: dict[str, Any],
        max_retries: int = 3,
        retry_backoff_seconds: float = 2.0,
    ) -> FetchResult:
        sig = inspect.signature(connector.fetch)
        kwargs: dict[str, Any] = {
            "entity_hints": entity_hints,
            "since": since,
            "limit": limit,
        }
        for key, value in options.items():
            if key in sig.parameters:
                kwargs[key] = value

        last_exc: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                return connector.fetch(**kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt < max_retries:
                    wait = retry_backoff_seconds * (2 ** attempt)
                    self.logger.warning(
                        "connector_retry connector=%s attempt=%d/%d wait=%.1fs: %s",
                        type(connector).__name__,
                        attempt + 1,
                        max_retries,
                        wait,
                        exc,
                    )
                    time.sleep(wait)
        raise last_exc  # type: ignore[misc]

    @staticmethod
    def _normalize_document(raw: RawDocument, hints: EntityHints) -> RawDocument:
        text = " ".join(raw.raw_text.split())
        if not text:
            raise ValueError("Connector returned an empty document after normalization")

        document_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        # Deterministic document id for idempotent re-runs.
        base = "|".join(
            [
                raw.source,
                raw.source_url or "",
                hints.company_id,
                hints.asset_id,
                document_hash,
            ]
        )
        stable_id = str(uuid.uuid5(uuid.NAMESPACE_URL, base))

        return RawDocument.from_text(
            id=stable_id,
            source=raw.source,
            title=raw.title.strip() or "Untitled document",
            raw_text=text,
            entity_hints=EntityHints(
                asset_id=hints.asset_id,
                company_id=hints.company_id,
                drug_name=hints.drug_name or raw.entity_hints.drug_name,
                indication=hints.indication or raw.entity_hints.indication,
                ticker=hints.ticker or raw.entity_hints.ticker,
                nct_id=hints.nct_id or raw.entity_hints.nct_id,
            ),
            retrieved_at=raw.retrieved_at,
            source_url=raw.source_url,
            published_at=raw.published_at,
            document_hash=document_hash,
        )

    @staticmethod
    def _event_id_for_document(*, company_id: str, asset_id: str, document: RawDocument) -> str:
        key = f"{company_id}|{asset_id}|{document.document_hash}"
        return str(uuid.uuid5(uuid.NAMESPACE_URL, key))

    @staticmethod
    def _queue_signal(
        signal: StructuredSignal,
        *,
        created_signals: list[StructuredSignal],
        created_signal_ids: set[str],
    ) -> None:
        if signal.id in created_signal_ids:
            return
        created_signals.append(signal)
        created_signal_ids.add(signal.id)

    @staticmethod
    def _event_from_extraction(
        *,
        signal: StructuredSignal,
        document: RawDocument,
        extraction: ExtractionResult,
    ) -> Event:
        if document.published_at is not None:
            observed_at = document.published_at
        else:
            observed_at = datetime.combine(signal.signal_date, dtime.min, tzinfo=timezone.utc)

        confidence = max(extraction.extraction_confidence, signal.extraction_confidence)
        return Event(
            id=signal.event_id,
            event_type=signal.event_type,
            asset_id=signal.asset_id,
            company_id=signal.company_id,
            observed_at=observed_at,
            ingested_at=extraction.extracted_at,
            source_url=document.source_url,
            source_type=document.source,
            headline=document.title,
            raw_text=document.raw_text,
            confidence=confidence,
        )

    def _current_context_for_mapping(
        self,
        *,
        company_id: str,
        asset_id: str,
        fallback: AssetValuationContext,
    ) -> AssetValuationContext:
        # For the default session-based executor, valuation state lives in-session
        # and is advanced after every applied run. We expose that current state
        # to mapping through a best-effort adapter and otherwise fall back.
        executor = self.valuation_executor
        if not isinstance(executor, Phase2SessionValuationExecutor):
            return fallback
        key = executor._session_key(company_id, asset_id)  # noqa: SLF001 - internal adapter
        session = executor._sessions.get(key)  # noqa: SLF001 - internal adapter
        if session is None:
            return fallback
        return AssetValuationContext(
            asset=session._asset,  # noqa: SLF001 - internal adapter
            company=session._company,  # noqa: SLF001 - internal adapter
            trials=list(session._trials),  # noqa: SLF001 - internal adapter
            market_model=session._market_model,  # noqa: SLF001 - internal adapter
        )

    def _run_stage(
        self,
        stage_logs: list[PipelineStageLog],
        asset: WatchlistAsset,
        *,
        run_id: str,
        stage: str,
        fn,
    ):
        started = _utcnow()
        try:
            value = fn()
            finished = _utcnow()
            self._log_stage(
                stage_logs,
                asset,
                run_id=run_id,
                stage=stage,
                status="success",
                started_at=started,
                finished_at=finished,
            )
            return value
        except Exception as exc:
            finished = _utcnow()
            self._log_stage(
                stage_logs,
                asset,
                run_id=run_id,
                stage=stage,
                status="failure",
                started_at=started,
                finished_at=finished,
                message=str(exc),
            )
            raise

    def _log_stage(
        self,
        stage_logs: list[PipelineStageLog],
        asset: WatchlistAsset,
        *,
        run_id: str,
        stage: str,
        status: Literal["success", "failure", "skipped"],
        started_at: datetime,
        finished_at: datetime,
        message: Optional[str] = None,
    ) -> None:
        log = PipelineStageLog(
            run_id=run_id,
            company_id=asset.company_id,
            asset_id=asset.asset_id,
            stage=stage,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            message=message,
        )
        stage_logs.append(log)
        level = logging.INFO if status != "failure" else logging.ERROR
        self.logger.log(
            level,
            "run_id=%s asset=%s company=%s stage=%s status=%s msg=%s",
            run_id,
            asset.asset_id,
            asset.company_id,
            stage,
            status,
            message or "",
        )

    def _log_asset_summary(self, *, summary: AssetRunSummary, run_started: datetime) -> None:
        finished = _utcnow()
        duration_seconds = round((finished - run_started).total_seconds(), 3)
        payload = {
            "run_id": summary.run_id,
            "company_id": summary.company_id,
            "asset_id": summary.asset_id,
            "status": summary.status,
            "documents_fetched": summary.documents_fetched,
            "documents_processed": summary.documents_processed,
            "signals_extracted": summary.signals_created,
            "events_created": summary.events_created,
            "valuation_updates": summary.valuation_diffs_persisted,
            "memo_generated": summary.memo_generated,
            "duration_seconds": duration_seconds,
        }
        self.logger.info(
            "watchlist_asset_summary %s",
            json.dumps(payload, ensure_ascii=True, sort_keys=True),
        )


def _build_extractor(cfg: ExtractionRuntimeConfig) -> SignalExtractor:
    backend = cfg.backend
    model = cfg.model
    api_key = cfg.api_key

    if backend == "anthropic":
        llm = AnthropicClient(model=model or "claude-sonnet-4-6", api_key=api_key)
    elif backend == "openai":
        llm = OpenAIClient(model=model or "gpt-4o-2024-11-20", api_key=api_key)
    else:
        # Useful local default for dry runs/tests when API keys are not configured.
        llm = FakeLLMClient(
            default_response=(
                '{"event_type":"trial_readout","signal_date":"2026-01-01",'
                '"confidence":0.0,"ambiguity_flag":true,"rationale":"fake backend",'
                '"trial_phase":"phase_2","trial_nct_id":null,"primary_endpoint_met":null,'
                '"interim_flag":false,"hazard_ratio":null,"p_value":null,'
                '"response_rate":null,"safety_grade":null,"fda_action_type":null,'
                '"designation_type":null,"deal_value_millions":null,'
                '"deal_type":null,"payer_name":null}'
            ),
            model="fake-watchlist-llm",
        )
    return SignalExtractor(llm_client=llm)


def _build_connectors(configs: dict[str, ConnectorRuntimeConfig]) -> dict[str, SourceConnector]:
    if not configs:
        # Reasonable defaults if omitted.
        configs = {
            "clinicaltrials_gov": ConnectorRuntimeConfig(enabled=True, limit=20),
            "fda_website": ConnectorRuntimeConfig(enabled=True, limit=20),
            "sec_filing": ConnectorRuntimeConfig(enabled=True, limit=10),
        }

    built: dict[str, SourceConnector] = {}
    for name, cfg in configs.items():
        if not cfg.enabled:
            continue

        options = dict(cfg.options)
        if name == "clinicaltrials_gov":
            built[name] = ClinicalTrialsConnector(**options)
        elif name == "fda_website":
            built[name] = FDAConnector(**options)
        elif name == "sec_filing":
            built[name] = SECEdgarConnector(**options)
        elif name == "press_release":
            built[name] = PressReleaseConnector(**options)
        else:
            raise ValueError(f"Unsupported connector name: {name!r}")

    return built


def load_watchlist_config(path: str | Path) -> WatchlistRunnerConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return WatchlistRunnerConfig.model_validate(raw)
