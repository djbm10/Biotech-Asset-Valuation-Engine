"""Automated watchlist runner for the intelligence-to-valuation pipeline."""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
import logging
import math
import random
import re
import time
import uuid
from difflib import SequenceMatcher
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Optional, Protocol

import yaml
from pydantic import BaseModel, Field

from bve.alerts.alert_model import AlertSeverity, AlertTrigger
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
from bve.intelligence.extraction.prompt_builder import PromptBuilder
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument
from bve.intelligence.extraction.result import ExtractionResult, ExtractionStatus
from bve.intelligence.competitor_discovery import CompetitorDiscoveryEngine
from bve.intelligence.knowledge_graph import KGNode, NodeType
from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace, StoredValuationDiff
from bve.intelligence.memo_generation import WeeklyMemoGenerator, WeeklyMemoInput
from bve.intelligence.phase2 import MappingEngine, ReviewQueue, ValuationSession
from bve.intelligence.schemas.proposals import AssumptionChangeProposal
from bve.intelligence.schemas.runs import ReviewDecision
from bve.intelligence.schemas.signals import Event, StructuredSignal
from bve.models.market_model import MarketModel
from bve.ops.cost_guard import CostGuard
from bve.ops.metrics import ConnectorHealthMetrics, StageLatencyMetrics
from bve.pipeline.change_detector import MaterialChangeDetector, MaterialityRule
from bve.pipeline.pipeline_state import PipelineStateStore
from bve.services.rate_limiter import ServiceRateLimiter


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Connector retry helpers
# ---------------------------------------------------------------------------

_PERMANENT_ERROR_PATTERNS: tuple[str, ...] = (
    "url keyword argument is required",
    "ticker is required",
    "nct_id or drug_name",
    "drug_name is required",
    "cik not found",
    "cik resolution failed",
    "404",
    "403",
    "not found for ticker",
    "import error",
)


def _is_all_permanent(errors: list[str]) -> bool:
    """Return True when every error string looks like a permanent/config failure."""
    if not errors:
        return False
    for err in errors:
        lower = err.lower()
        if not any(pat in lower for pat in _PERMANENT_ERROR_PATTERNS):
            return False
    return True


@dataclasses.dataclass
class _CircuitState:
    failures: int = 0
    opened_at: Optional[float] = None  # time.monotonic() when tripped

    def is_open(self, cooldown_seconds: float) -> bool:
        if self.opened_at is None:
            return False
        return (time.monotonic() - self.opened_at) < cooldown_seconds

    def is_half_open(self, cooldown_seconds: float) -> bool:
        if self.opened_at is None:
            return False
        return (time.monotonic() - self.opened_at) >= cooldown_seconds

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def record_failure(self, threshold: int) -> None:
        self.failures += 1
        if self.failures >= threshold:
            self.opened_at = time.monotonic()


class ConnectorRuntimeConfig(BaseModel):
    """Runtime settings for one connector."""

    enabled: bool = True
    limit: int = Field(default=20, ge=1)
    options: dict[str, Any] = Field(default_factory=dict)
    # Retry policy for transient connector failures.
    max_retries: int = Field(default=3, ge=0)
    retry_backoff_seconds: float = Field(default=2.0, ge=0.0)
    # Circuit breaker: trip after this many consecutive transient failures.
    circuit_failure_threshold: int = Field(default=5, ge=1)
    # Seconds to keep circuit OPEN before allowing a half-open probe.
    circuit_cooldown_seconds: float = Field(default=300.0, ge=0.0)


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
    max_docs_per_asset: int = Field(default=10, ge=1)
    llm_daily_cost_limit_usd: float = Field(default=2.50, ge=0.0)
    llm_daily_cost_path: str = "outputs/watchlist/daily_llm_cost.json"
    llm_estimated_input_cost_per_1k_tokens: float = Field(default=0.003, ge=0.0)
    llm_estimated_output_cost_per_1k_tokens: float = Field(default=0.015, ge=0.0)

    # Confidence gating — prevents low-quality extractions from touching the model.
    # Below discard_threshold: signal stored for audit but discarded from pipeline.
    # Below review_threshold (but ≥ discard): stored + flagged for manual review;
    # does NOT proceed to mapping or valuation.
    confidence_discard_threshold: float = Field(default=0.3, ge=0.0, le=1.0)
    confidence_review_threshold: float = Field(default=0.5, ge=0.0, le=1.0)


class ValuationTriggerConfig(BaseModel):
    """Cheap gating rules for deciding whether a stored signal should hit valuation."""

    enabled: bool = True
    min_confidence_score: float = Field(default=0.60, ge=0.0, le=1.0)
    event_types: tuple[str, ...] = ("trial_readout", "fda_decision", "safety_signal")


class PipelineScheduleConfig(BaseModel):
    """Optional daily/weekly cadence used by the service layer."""

    enabled: bool = False
    daily_ingestion_interval_hours: int = Field(default=24, ge=1)
    weekly_maintenance_weekday: int = Field(default=6, ge=0, le=6)
    weekly_replay_since: str = "7d"


class WatchlistRunnerConfig(BaseModel):
    """Top-level watchlist runner configuration."""

    polling_interval_seconds: int = Field(default=3600, ge=1)
    state_path: str = "outputs/watchlist/pipeline_state.json"
    knowledge_db_path: str = "outputs/intelligence_phase2/knowledge.db"
    valuation_output_dir: str = "outputs/intelligence_phase2/watchlist"
    materiality: MaterialityRule = Field(default_factory=MaterialityRule)
    extraction: ExtractionRuntimeConfig = Field(default_factory=ExtractionRuntimeConfig)
    valuation_trigger: ValuationTriggerConfig = Field(default_factory=ValuationTriggerConfig)
    schedule: PipelineScheduleConfig = Field(default_factory=PipelineScheduleConfig)
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
    stage_timings_ms: dict[str, float] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class WatchlistRunSummary(BaseModel):
    """Summary of one full watchlist cycle."""

    run_id: Optional[str] = None
    started_at: datetime
    finished_at: datetime
    assets: list[AssetRunSummary] = Field(default_factory=list)
    stage_logs: list[PipelineStageLog] = Field(default_factory=list)
    stage_latencies: list[StageLatencyMetrics] = Field(default_factory=list)
    connector_health: list[ConnectorHealthMetrics] = Field(default_factory=list)


class AssetValuationContext(BaseModel):
    """Valuation inputs for one asset."""

    asset: Asset
    company: Company
    trials: list[ClinicalTrial]
    market_model: MarketModel


class AssetContextProvider(Protocol):
    """Protocol for obtaining valuation context per tracked asset."""

    def get_context(self, asset: WatchlistAsset) -> AssetValuationContext: ...


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
    ) -> Optional[StoredValuationDiff]: ...


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
            # Persist the tracked watchlist asset key so downstream ranking and
            # memo joins stay aligned even when the underlying valuation config
            # uses a different engine-level asset identifier.
            asset_id=asset_id,
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
        rate_limiter: Optional[ServiceRateLimiter] = None,
        cost_guard: Optional[CostGuard] = None,
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
        if self.alert_router is not None and getattr(self.alert_router, "knowledge_store", None) is None:
            setattr(self.alert_router, "knowledge_store", self.knowledge)
        self.rate_limiter = rate_limiter or ServiceRateLimiter()
        self.cost_guard = cost_guard or CostGuard(
            state_path=config.extraction.llm_daily_cost_path,
            daily_limit_usd=config.extraction.llm_daily_cost_limit_usd,
        )
        self._llm_cost_guard_enabled = config.extraction.backend != "fake"
        self._cost_prompt_builder = PromptBuilder()
        # Lazy-init; created on first run_once() call.
        self._price_tracker: Optional[Any] = None
        # Per-(source_name, asset_id) circuit breaker state.
        self._circuit_states: dict[tuple[str, str], _CircuitState] = {}

    def _price_tracker_instance(self) -> Any:
        """Lazy singleton for PriceReactionTracker (avoids circular imports at module load)."""
        if self._price_tracker is None:
            from bve.intelligence.price_reaction import PriceReactionTracker

            self._price_tracker = PriceReactionTracker(self.knowledge, logger=self.logger)
        return self._price_tracker

    def close(self) -> None:
        self.knowledge.close()

    def _refresh_market_prices(self) -> int:
        """
        Pull latest prices for all tickers in the watchlist and upsert into market_prices.
        Returns number of records written.  Failures are logged, not raised.
        """
        tickers = [a.ticker for a in self.config.watchlist if a.ticker]
        if not tickers:
            return 0
        try:
            from bve.connectors.market_prices import MarketPriceConnector

            connector = MarketPriceConnector(logger=self.logger)
            records = connector.fetch(tickers, period="5d")
            n = self.knowledge.upsert_market_prices(records)
            self.logger.info("market_prices_refreshed tickers=%d rows=%d", len(tickers), n)
            return n
        except Exception as exc:
            self.logger.warning("market_price_refresh_failed: %s", exc)
            return 0

    def run_once(
        self,
        *,
        run_id: Optional[str] = None,
        enable_valuation: bool = True,
        enable_memos: bool = True,
        refresh_market_prices: bool = True,
    ) -> WatchlistRunSummary:
        run_id = run_id or str(uuid.uuid4())
        started = _utcnow()
        stage_logs: list[PipelineStageLog] = []
        results: list[AssetRunSummary] = []

        # Refresh market prices before processing assets (needed for event outcome recording).
        if refresh_market_prices:
            self._refresh_market_prices()

        # Resolve pending price reaction windows using updated prices.
        if refresh_market_prices:
            try:
                self._price_tracker_instance().resolve_pending()
            except Exception as exc:
                self.logger.warning("price_reaction_resolve_failed: %s", exc)

        # Wave A: resolve any forecast_records that now have closed price windows.
        try:
            from bve.intelligence.forecast_tracker import resolve_forecasts
            n_resolved = resolve_forecasts(self.knowledge)
            if n_resolved:
                self.logger.info("forecast_records_resolved count=%d", n_resolved)
        except Exception as exc:
            self.logger.warning("forecast_resolve_failed: %s", exc)

        for asset in self.config.watchlist:
            results.append(
                self._run_asset(
                    asset,
                    stage_logs=stage_logs,
                    run_id=run_id,
                    enable_valuation=enable_valuation,
                    enable_memos=enable_memos,
                )
            )
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
        stage_latencies = self._aggregate_stage_latencies(results)
        connector_health = self._compute_connector_health()
        return WatchlistRunSummary(
            run_id=run_id,
            started_at=started,
            finished_at=finished,
            assets=results,
            stage_logs=stage_logs,
            stage_latencies=stage_latencies,
            connector_health=connector_health,
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
        enable_valuation: bool,
        enable_memos: bool,
    ) -> AssetRunSummary:
        summary = AssetRunSummary(
            run_id=run_id,
            company_id=asset_cfg.company_id,
            asset_id=asset_cfg.asset_id,
            status="success",
            stage_timings_ms={
                "ingestion": 0.0,
                "extraction": 0.0,
                "valuation": 0.0,
                "alerts": 0.0,
            },
        )

        self.state.mark_run_started(asset_cfg.company_id, asset_cfg.asset_id)
        run_started = _utcnow()
        self.knowledge.mark_run_state_started(
            run_id=run_id,
            stage="asset_run",
            asset_id=asset_cfg.asset_id,
            started_at=run_started,
            checkpoint_json={
                "company_id": asset_cfg.company_id,
                "asset_id": asset_cfg.asset_id,
            },
        )

        try:
            context: Optional[AssetValuationContext] = None
            if enable_valuation:
                context = self._run_stage(
                    stage_logs,
                    asset_cfg,
                    run_id=run_id,
                    stage="prepare_context",
                    checkpoint_json={"valuation_config": asset_cfg.valuation_config},
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
            llm_extractions_attempted = 0

            for source_name in self._asset_connectors(asset_cfg):
                connector = self.connectors[source_name]
                source_cfg = self.config.connectors[source_name]
                since = self.state.get_since(asset_cfg.company_id, asset_cfg.asset_id, source_name)

                fetch_started = time.perf_counter()
                try:
                    fetch_result = self._run_stage(
                        stage_logs,
                        asset_cfg,
                        run_id=run_id,
                        stage=f"fetch:{source_name}",
                        checkpoint_json={
                            "source": source_name,
                            "since": since.isoformat() if since is not None else None,
                            "limit": source_cfg.limit,
                        },
                        fn=lambda c=connector, sn=source_name, s=since, lim=source_cfg.limit, o=source_cfg.options, h=hints, mr=source_cfg.max_retries, rb=source_cfg.retry_backoff_seconds, cft=source_cfg.circuit_failure_threshold, ccs=source_cfg.circuit_cooldown_seconds, aid=asset_cfg.asset_id: (
                            self._fetch_connector(
                                connector=c,
                                source_name=sn,
                                asset_id=aid,
                                entity_hints=h,
                                since=s,
                                limit=lim,
                                options=o,
                                max_retries=mr,
                                retry_backoff_seconds=rb,
                                circuit_failure_threshold=cft,
                                circuit_cooldown_seconds=ccs,
                            )
                        ),
                    )
                finally:
                    summary.stage_timings_ms["ingestion"] += (
                        time.perf_counter() - fetch_started
                    ) * 1000.0
                assert isinstance(fetch_result, FetchResult)
                summary.documents_fetched += len(fetch_result.documents)
                normalized_documents = self._prepare_documents_for_extraction(
                    asset_cfg=asset_cfg,
                    stage_logs=stage_logs,
                    run_id=run_id,
                    hints=hints,
                    documents=fetch_result.documents,
                )

                for normalized in normalized_documents:
                    event_id = self._event_id_for_document(
                        company_id=asset_cfg.company_id,
                        asset_id=asset_cfg.asset_id,
                        document=normalized,
                    )
                    event_already_exists = self.state.seen_event(
                        asset_cfg.company_id, asset_cfg.asset_id, event_id
                    ) or self.knowledge.event_exists(event_id)
                    if event_already_exists:
                        self.state.mark_document_processed(
                            asset_cfg.company_id, asset_cfg.asset_id, normalized.id
                        )
                        self.state.mark_event_processed(
                            asset_cfg.company_id, asset_cfg.asset_id, event_id
                        )
                        # Resume-safe behavior: if prior run crashed before valuation,
                        # continue from persisted signal without re-extracting.
                        if not self.knowledge.valuation_diff_exists_for_event(event_id):
                            resumed_signal = self.knowledge.get_structured_signal_by_event_id(
                                event_id
                            )
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
                            checkpoint_json={
                                "event_id": event_id,
                                "document_id": normalized.id,
                            },
                        )
                        continue

                    if self.state.seen_document(
                        asset_cfg.company_id, asset_cfg.asset_id, normalized.id
                    ):
                        self._log_stage(
                            stage_logs,
                            asset_cfg,
                            run_id=run_id,
                            stage="dedupe_document",
                            status="skipped",
                            started_at=run_started,
                            finished_at=_utcnow(),
                            message=f"duplicate document {normalized.id}",
                            checkpoint_json={
                                "document_id": normalized.id,
                            },
                        )
                        continue

                    if normalized.document_hash and self.knowledge.processed_document_hash_exists(
                        source=normalized.source,
                        document_hash=normalized.document_hash,
                    ):
                        self.state.mark_document_processed(
                            asset_cfg.company_id, asset_cfg.asset_id, normalized.id
                        )
                        self._log_stage(
                            stage_logs,
                            asset_cfg,
                            run_id=run_id,
                            stage="dedupe_document_hash",
                            status="skipped",
                            started_at=run_started,
                            finished_at=_utcnow(),
                            message=f"duplicate processed hash {normalized.document_hash}",
                            checkpoint_json={
                                "document_id": normalized.id,
                                "document_hash": normalized.document_hash,
                            },
                        )
                        continue

                    self.knowledge.add_raw_document(
                        normalized,
                        SourceTrace(
                            source_type=normalized.source,
                            source_ref=normalized.source_url or normalized.id,
                        ),
                    )

                    recent_title = self._find_recent_similar_processed_title(
                        asset_id=asset_cfg.asset_id,
                        title=normalized.title,
                        reference_time=fetch_result.fetched_at,
                    )
                    if recent_title is not None:
                        self._log_stage(
                            stage_logs,
                            asset_cfg,
                            run_id=run_id,
                            stage="dedupe_similar_title",
                            status="skipped",
                            started_at=run_started,
                            finished_at=_utcnow(),
                            message=f"similar recent title matched {recent_title!r}",
                            checkpoint_json={
                                "document_id": normalized.id,
                                "title": normalized.title,
                                "matched_title": recent_title,
                                "window_hours": 24,
                            },
                        )
                        continue

                    if llm_extractions_attempted >= self.config.extraction.max_docs_per_asset:
                        self._log_stage(
                            stage_logs,
                            asset_cfg,
                            run_id=run_id,
                            stage="extraction_limit",
                            status="skipped",
                            started_at=run_started,
                            finished_at=_utcnow(),
                            message=(
                                "max_docs_per_asset reached "
                                f"({self.config.extraction.max_docs_per_asset})"
                            ),
                            checkpoint_json={
                                "document_id": normalized.id,
                                "event_id": event_id,
                                "max_docs_per_asset": self.config.extraction.max_docs_per_asset,
                            },
                        )
                        continue

                    if self._llm_cost_guard_enabled and not self.cost_guard.allow_llm_call():
                        self._log_stage(
                            stage_logs,
                            asset_cfg,
                            run_id=run_id,
                            stage="extract",
                            status="skipped",
                            started_at=run_started,
                            finished_at=_utcnow(),
                            message="LLM extraction skipped due to daily cost limit",
                            checkpoint_json={
                                "document_id": normalized.id,
                                "event_id": event_id,
                                "daily_cost_total_usd": self.cost_guard.current_total_usd,
                                "daily_cost_limit_usd": (
                                    self.config.extraction.llm_daily_cost_limit_usd
                                ),
                                "daily_cost_utc_date": (
                                    self.cost_guard.current_utc_date.isoformat()
                                ),
                            },
                        )
                        self._emit_llm_cost_limit_alert(run_id=run_id)
                        continue

                    extract_started = time.perf_counter()
                    llm_extractions_attempted += 1
                    try:
                        extraction = self._run_stage(
                            stage_logs,
                            asset_cfg,
                            run_id=run_id,
                            stage="extract",
                            checkpoint_json={
                                "document_id": normalized.id,
                                "event_id": event_id,
                            },
                            fn=lambda d=normalized, e=event_id: self.extractor.extract(
                                d, event_id=e
                            ),
                        )
                    finally:
                        summary.stage_timings_ms["extraction"] += (
                            time.perf_counter() - extract_started
                        ) * 1000.0
                    assert isinstance(extraction, ExtractionResult)
                    if self._llm_cost_guard_enabled:
                        estimated_cost = self._estimate_llm_extraction_cost(
                            document=normalized,
                            extraction=extraction,
                        )
                        self.cost_guard.record_llm_cost(estimated_cost)
                        if self.cost_guard.cap_reached_on_last_record:
                            self._emit_llm_cost_limit_alert(run_id=run_id)
                    extraction_record = self.knowledge.add_extraction_result(
                        extraction,
                        SourceTrace(
                            source_type="extraction",
                            source_ref=f"document:{normalized.id}",
                        ),
                        raw_document_id=normalized.id,
                    )

                    self.state.mark_document_processed(
                        asset_cfg.company_id, asset_cfg.asset_id, normalized.id
                    )
                    summary.documents_processed += 1

                    if extraction.status != ExtractionStatus.SUCCESS or extraction.signal is None:
                        continue

                    signal = extraction.signal
                    conf = extraction.extraction_confidence
                    ext_cfg = self.config.extraction

                    # Confidence gate 1: discard — signal stored for audit but not processed.
                    if conf < ext_cfg.confidence_discard_threshold:
                        self.logger.warning(
                            "signal_discarded_low_confidence asset=%s conf=%.3f "
                            "threshold=%.2f document=%s",
                            asset_cfg.asset_id,
                            conf,
                            ext_cfg.confidence_discard_threshold,
                            normalized.id,
                        )
                        continue

                    # Confidence gate 2: review-only — stored + flagged but NOT sent to valuation.
                    if conf < ext_cfg.confidence_review_threshold:
                        ambiguous_signal_ids.append(signal.id)
                        self.logger.info(
                            "signal_routed_review_only asset=%s conf=%.3f "
                            "threshold=%.2f event_type=%s",
                            asset_cfg.asset_id,
                            conf,
                            ext_cfg.confidence_review_threshold,
                            signal.event_type.value,
                        )
                        # Store signal in knowledge store for human review but do not queue.
                        self.knowledge.add_structured_signal(
                            signal,
                            SourceTrace(
                                source_type="structured_signal",
                                source_ref=f"extraction:{extraction_record.id}",
                            ),
                            extraction_result_id=extraction_record.id,
                        )
                        continue

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

                    self.state.mark_event_processed(
                        asset_cfg.company_id, asset_cfg.asset_id, event.id
                    )
                    summary.events_created += 1
                    summary.signals_created += 1
                    self._queue_signal(
                        signal,
                        created_signals=created_signals,
                        created_signal_ids=created_signal_ids,
                    )
                    # Alert condition 1 (safety) + condition 3 (low-conf/high-severity).
                    if self.alert_router is not None:
                        alert_started = time.perf_counter()
                        try:
                            self.alert_router.enqueue_signal_alerts(
                                signal=signal,
                                extraction=extraction,
                                run_id=run_id,
                                headline=normalized.title,
                                source_url=normalized.source_url,
                            )
                        finally:
                            summary.stage_timings_ms["alerts"] += (
                                time.perf_counter() - alert_started
                            ) * 1000.0

                self.state.set_last_fetch(
                    asset_cfg.company_id,
                    asset_cfg.asset_id,
                    source_name,
                    fetch_result.fetched_at,
                )

            if enable_valuation and asset_cfg.indication:
                self._run_competitor_discovery(asset_cfg, run_id=run_id, stage_logs=stage_logs)

            # Stage 5/6: map + valuation integration
            if not enable_valuation:
                created_signals = []
            for signal in created_signals:
                if not self._should_trigger_valuation(signal):
                    self._log_stage(
                        stage_logs,
                        asset_cfg,
                        run_id=run_id,
                        stage="valuation_gate",
                        status="skipped",
                        started_at=run_started,
                        finished_at=_utcnow(),
                        message=(
                            f"signal {signal.id} skipped "
                            f"(confidence={signal.extraction_confidence:.2f}, "
                            f"event_type={signal.event_type.value})"
                        ),
                        checkpoint_json={
                            "signal_id": signal.id,
                            "event_id": signal.event_id,
                            "confidence": signal.extraction_confidence,
                            "event_type": signal.event_type.value,
                        },
                    )
                    continue

                valuation_started = time.perf_counter()
                try:
                    current_session_context = self._current_context_for_mapping(
                        company_id=asset_cfg.company_id,
                        asset_id=asset_cfg.asset_id,
                        fallback=context if context is not None else self.context_provider.get_context(asset_cfg),
                    )
                    mapping_batch = self._run_stage(
                        stage_logs,
                        asset_cfg,
                        run_id=run_id,
                        stage="map_signal",
                        checkpoint_json={
                            "signal_id": signal.id,
                            "event_id": signal.event_id,
                        },
                        fn=lambda s=signal, ctx=current_session_context: (
                            self.mapping_engine.map_signal(
                                s,
                                engine_asset_id=ctx.asset.id,
                                asset=ctx.asset,
                                trials=ctx.trials,
                                market_model=ctx.market_model,
                            )
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

                    # Record event outcome for later price reaction resolution.
                    try:
                        self._price_tracker_instance().record(
                            saved_diff,
                            signal,
                            ticker=asset_cfg.ticker,
                        )
                    except Exception as exc:
                        self.logger.warning(
                            "event_outcome_record_failed event=%s: %s",
                            saved_diff.event_id,
                            exc,
                        )

                    # Wave A: record model prediction at signal-extraction time.
                    try:
                        from bve.intelligence.forecast_tracker import record_forecast
                        record_forecast(signal, saved_diff, self.knowledge)
                    except Exception as exc:
                        self.logger.warning(
                            "forecast_record_failed event=%s: %s",
                            saved_diff.event_id,
                            exc,
                        )

                    # Alert condition 2: material valuation change (dual gate: abs + relative).
                    if self.alert_router is not None:
                        alert_started = time.perf_counter()
                        try:
                            self.alert_router.enqueue_diff_alerts(
                                diff=saved_diff,
                                signal=signal,
                                run_id=run_id,
                            )
                        finally:
                            summary.stage_timings_ms["alerts"] += (
                                time.perf_counter() - alert_started
                            ) * 1000.0
                finally:
                    summary.stage_timings_ms["valuation"] += (
                        time.perf_counter() - valuation_started
                    ) * 1000.0

            # Stage 8: update dossier
            if enable_valuation:
                valuation_started = time.perf_counter()
                dossier = self._run_stage(
                    stage_logs,
                    asset_cfg,
                    run_id=run_id,
                    stage="update_dossier",
                    checkpoint_json={
                        "company_id": asset_cfg.company_id,
                        "asset_id": asset_cfg.asset_id,
                    },
                    fn=lambda: self.knowledge.generate_dossier(
                        company_id=asset_cfg.company_id,
                        asset_id=asset_cfg.asset_id,
                        persist=True,
                    ),
                )
                summary.stage_timings_ms["valuation"] += (
                    time.perf_counter() - valuation_started
                ) * 1000.0
                summary.dossier_id = dossier.id
            else:
                dossier = None

            # Stage 9: memo if material changes
            if (
                enable_valuation
                and enable_memos
                and dossier is not None
                and self.change_detector.should_generate_weekly_memo(valuation_diffs)
            ):
                valuation_started = time.perf_counter()
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
                summary.stage_timings_ms["valuation"] += (
                    time.perf_counter() - valuation_started
                ) * 1000.0

            # Flush all enqueued alerts for this asset (batched per-asset).
            if self.alert_router is not None:
                alert_started = time.perf_counter()
                fired = self.alert_router.flush(asset_cfg.asset_id, run_id=run_id)
                summary.stage_timings_ms["alerts"] += (time.perf_counter() - alert_started) * 1000.0
                summary.alerts_fired = len(fired)

            self.state.mark_run_succeeded(asset_cfg.company_id, asset_cfg.asset_id)
            self._log_stage(
                stage_logs,
                asset_cfg,
                run_id=run_id,
                stage="asset_run",
                status="success",
                started_at=run_started,
                finished_at=_utcnow(),
                checkpoint_json={
                    "documents_fetched": summary.documents_fetched,
                    "signals_created": summary.signals_created,
                    "events_created": summary.events_created,
                    "valuation_diffs_persisted": summary.valuation_diffs_persisted,
                    "memo_generated": summary.memo_generated,
                },
            )
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
                error_json={"error": str(exc)},
            )
            self._log_asset_summary(summary=summary, run_started=run_started)
            return summary

    def _should_run_competitor_discovery(self, asset_id: str) -> bool:
        if self.knowledge.count_competitor_programs(asset_id) == 0:
            return True
        entry = self.knowledge.get_asset_registry_entry(asset_id)
        if entry is None or entry.last_competitor_discovery_at is None:
            return True
        return (_utcnow() - entry.last_competitor_discovery_at) > timedelta(days=7)

    def _run_competitor_discovery(
        self,
        asset_cfg: WatchlistAsset,
        *,
        run_id: str,
        stage_logs: list[PipelineStageLog],
    ) -> None:
        started = _utcnow()
        stage = "competitor_discovery"

        if not self._should_run_competitor_discovery(asset_cfg.asset_id):
            self._log_stage(
                stage_logs,
                asset_cfg,
                run_id=run_id,
                stage=stage,
                status="skipped",
                started_at=started,
                finished_at=_utcnow(),
                message="skipped, competitor discovery within 7-day window",
                checkpoint_json={"asset_id": asset_cfg.asset_id},
            )
            return

        try:
            asset_node = self.knowledge.find_node_by_external_id(NodeType.ASSET, asset_cfg.asset_id)
            if asset_node is None:
                asset_node = self.knowledge.upsert_node(
                    KGNode(
                        node_type=NodeType.ASSET,
                        name=asset_cfg.drug_name or asset_cfg.asset_id,
                        external_id=asset_cfg.asset_id,
                        properties={
                            "company_id": asset_cfg.company_id,
                            "ticker": asset_cfg.ticker,
                            "indication": asset_cfg.indication,
                        },
                    )
                )

            self.rate_limiter.wait("clinicaltrials_gov")
            engine = CompetitorDiscoveryEngine(store=self.knowledge, request_delay_seconds=0.0)
            result = engine.discover(
                asset_cfg.asset_id,
                asset_node.node_id,
                asset_cfg.indication or "",
            )

            if not result.errors:
                self.knowledge.update_competitor_discovery_timestamp(asset_cfg.asset_id, _utcnow())

            self._log_stage(
                stage_logs,
                asset_cfg,
                run_id=run_id,
                stage=stage,
                status="success",
                started_at=started,
                finished_at=_utcnow(),
                message=(
                    f"programs_found={len(result.programs_found)} "
                    f"kg_edges_added={result.kg_edges_added} errors={len(result.errors)}"
                ),
                checkpoint_json={
                    "programs_found": len(result.programs_found),
                    "kg_edges_added": result.kg_edges_added,
                    "errors": result.errors,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive failure isolation
            self._log_stage(
                stage_logs,
                asset_cfg,
                run_id=run_id,
                stage=stage,
                status="failure",
                started_at=started,
                finished_at=_utcnow(),
                message=f"competitor discovery failed: {exc}",
                checkpoint_json={"asset_id": asset_cfg.asset_id},
                error_json={"error": str(exc)},
            )

    def _asset_connectors(self, asset_cfg: WatchlistAsset) -> list[str]:
        if asset_cfg.connectors:
            return [
                name
                for name in asset_cfg.connectors
                if name in self.connectors
                and self.config.connectors.get(name, ConnectorRuntimeConfig()).enabled
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
        source_name: str,
        asset_id: str,
        entity_hints: EntityHints,
        since: Optional[datetime],
        limit: int,
        options: dict[str, Any],
        max_retries: int = 3,
        retry_backoff_seconds: float = 2.0,
        circuit_failure_threshold: int = 5,
        circuit_cooldown_seconds: float = 300.0,
    ) -> FetchResult:
        circuit_key = (source_name, asset_id)
        circuit = self._circuit_states.setdefault(circuit_key, _CircuitState())

        # Reject immediately if circuit is OPEN (not yet cooled down).
        if circuit.is_open(circuit_cooldown_seconds):
            return FetchResult(
                source=source_name,
                fetch_errors=[
                    f"circuit_open source={source_name} asset={asset_id}: "
                    f"too many consecutive failures; cooling down"
                ],
            )

        # If HALF-OPEN, allow a single probe request through.
        is_probe = circuit.is_half_open(circuit_cooldown_seconds)

        sig = inspect.signature(connector.fetch)
        kwargs: dict[str, Any] = {
            "entity_hints": entity_hints,
            "since": since,
            "limit": limit,
        }
        for key, value in options.items():
            if key in sig.parameters:
                kwargs[key] = value

        last_result: Optional[FetchResult] = None
        for attempt in range(max_retries + 1):
            try:
                self.rate_limiter.wait(source_name)
                result = connector.fetch(**kwargs)
            except Exception as exc:
                # Unexpected exception from a connector (should not happen per protocol).
                circuit.record_failure(circuit_failure_threshold)
                if attempt < max_retries and not is_probe:
                    jitter = random.uniform(0.0, retry_backoff_seconds * 0.25)
                    wait = retry_backoff_seconds * (2**attempt) + jitter
                    self.logger.warning(
                        "connector_exception connector=%s attempt=%d/%d wait=%.1fs: %s",
                        type(connector).__name__,
                        attempt + 1,
                        max_retries,
                        wait,
                        exc,
                    )
                    time.sleep(wait)
                    continue
                return FetchResult(
                    source=source_name,
                    fetch_errors=[f"unexpected connector exception: {exc}"],
                )

            # Check FetchResult errors for retryability.
            if result.fetch_errors and not result.documents:
                if _is_all_permanent(result.fetch_errors):
                    # Permanent config/auth error — no retry, no circuit trip.
                    return result

                # Transient error — count against circuit and potentially retry.
                circuit.record_failure(circuit_failure_threshold)
                last_result = result
                if attempt < max_retries and not is_probe:
                    jitter = random.uniform(0.0, retry_backoff_seconds * 0.25)
                    wait = retry_backoff_seconds * (2**attempt) + jitter
                    self.logger.warning(
                        "connector_transient_retry connector=%s attempt=%d/%d wait=%.1fs: %s",
                        type(connector).__name__,
                        attempt + 1,
                        max_retries,
                        wait,
                        result.fetch_errors,
                    )
                    time.sleep(wait)
                    continue

            # Success (documents returned or no errors).
            circuit.record_success()
            return result

        # All retries exhausted — return the last transient error result.
        return last_result or FetchResult(source=source_name, fetch_errors=["all retries exhausted"])

    def _prepare_documents_for_extraction(
        self,
        *,
        asset_cfg: WatchlistAsset,
        stage_logs: list[PipelineStageLog],
        run_id: str,
        hints: EntityHints,
        documents: list[RawDocument],
    ) -> list[RawDocument]:
        normalized_documents = [
            self._normalize_document(raw_document, hints) for raw_document in documents
        ]
        normalized_documents.sort(key=self._document_priority_key, reverse=True)

        out: list[RawDocument] = []
        seen_hashes: set[str] = set()
        for document in normalized_documents:
            if document.document_hash in seen_hashes:
                self._log_stage(
                    stage_logs,
                    asset_cfg,
                    run_id=run_id,
                    stage="dedupe_document_hash",
                    status="skipped",
                    started_at=_utcnow(),
                    finished_at=_utcnow(),
                    message=f"duplicate fetched hash {document.document_hash}",
                    checkpoint_json={
                        "document_id": document.id,
                        "document_hash": document.document_hash,
                    },
                )
                continue
            seen_hashes.add(document.document_hash)
            out.append(document)
        return out

    @staticmethod
    def _document_priority_key(document: RawDocument) -> tuple[datetime, datetime, str, str]:
        published_at = WatchlistPipelineRunner._coerce_document_datetime(document.published_at)
        retrieved_at = WatchlistPipelineRunner._coerce_document_datetime(document.retrieved_at)
        return (
            published_at if document.published_at is not None else retrieved_at,
            retrieved_at,
            document.source_url or "",
            document.id,
        )

    @staticmethod
    def _coerce_document_datetime(value: Optional[datetime]) -> datetime:
        if value is None:
            return datetime.min.replace(tzinfo=timezone.utc)
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _find_recent_similar_processed_title(
        self,
        *,
        asset_id: str,
        title: str,
        reference_time: datetime,
        window_hours: int = 24,
        similarity_threshold: float = 0.88,
        limit: int = 50,
    ) -> Optional[str]:
        normalized_title = self._normalize_title_for_dedupe(title)
        if not normalized_title:
            return None

        cutoff = self._coerce_document_datetime(reference_time) - timedelta(hours=window_hours)
        rows = self.knowledge._conn.execute(
            """
            SELECT DISTINCT json_extract(d.payload_json, '$.title') AS title
            FROM extraction_results er
            JOIN raw_documents d
              ON d.id = er.raw_document_id
            WHERE er.asset_id = ?
              AND julianday(er.created_at) >= julianday(?)
            ORDER BY er.created_at DESC
            LIMIT ?
            """,
            (asset_id, cutoff.isoformat(), limit),
        ).fetchall()
        for row in rows:
            recent_title = str(row["title"] or "").strip()
            recent_normalized = self._normalize_title_for_dedupe(recent_title)
            if not recent_normalized:
                continue
            if recent_normalized == normalized_title:
                return recent_title
            if (
                SequenceMatcher(None, normalized_title, recent_normalized).ratio()
                >= similarity_threshold
            ):
                return recent_title
        return None

    @staticmethod
    def _normalize_title_for_dedupe(title: str) -> str:
        return " ".join(re.sub(r"[^a-z0-9]+", " ", title.lower()).split())

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
        checkpoint_json: Optional[dict[str, Any]] = None,
        fn,
    ):
        started = _utcnow()
        self.knowledge.mark_run_state_started(
            run_id=run_id,
            stage=stage,
            asset_id=asset.asset_id,
            started_at=started,
            checkpoint_json=checkpoint_json or {},
        )
        try:
            value = fn()
            effective_checkpoint = dict(checkpoint_json or {})
            if isinstance(value, FetchResult):
                effective_checkpoint.update(
                    {
                        "documents_fetched": len(value.documents),
                        "fetch_errors": len(value.fetch_errors),
                    }
                )
            finished = _utcnow()
            self._log_stage(
                stage_logs,
                asset,
                run_id=run_id,
                stage=stage,
                status="success",
                started_at=started,
                finished_at=finished,
                checkpoint_json=effective_checkpoint,
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
                checkpoint_json=checkpoint_json,
                error_json={"error": str(exc)},
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
        checkpoint_json: Optional[dict[str, Any]] = None,
        error_json: Optional[dict[str, Any]] = None,
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
        self.knowledge.mark_run_state_finished(
            run_id=run_id,
            stage=stage,
            asset_id=asset.asset_id,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            checkpoint_json=checkpoint_json or {},
            error_json=error_json or {},
        )
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

    @staticmethod
    def _percentile(values: list[float], q: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        if len(ordered) == 1:
            return ordered[0]
        idx = (len(ordered) - 1) * q
        lo = int(math.floor(idx))
        hi = int(math.ceil(idx))
        if lo == hi:
            return ordered[lo]
        return ordered[lo] + (ordered[hi] - ordered[lo]) * (idx - lo)

    def _aggregate_stage_latencies(
        self, assets: list[AssetRunSummary]
    ) -> list[StageLatencyMetrics]:
        stages = ("ingestion", "extraction", "valuation", "alerts")
        out: list[StageLatencyMetrics] = []
        for stage in stages:
            values = [
                float(asset.stage_timings_ms.get(stage, 0.0))
                for asset in assets
                if stage in asset.stage_timings_ms
            ]
            n = len(values)
            if n == 0:
                continue
            avg = sum(values) / n
            p50 = self._percentile(values, 0.50)
            p95 = max(values) if n < 20 else self._percentile(values, 0.95)
            p99 = max(values) if n < 20 else self._percentile(values, 0.99)
            out.append(
                StageLatencyMetrics(
                    stage=stage,
                    avg_ms=round(avg, 6),
                    p50_ms=round(p50, 6),
                    p95_ms=round(p95, 6),
                    p99_ms=round(p99, 6),
                    n_observations=n,
                )
            )
        return out

    def _should_trigger_valuation(self, signal: StructuredSignal) -> bool:
        cfg = self.config.valuation_trigger
        if not cfg.enabled:
            return True
        if signal.extraction_confidence < cfg.min_confidence_score:
            return False

        allowed = {value.strip().lower() for value in cfg.event_types if value.strip()}
        event_type = signal.event_type.value.lower()
        if event_type in allowed:
            return True
        if "fda_decision" in allowed and event_type in {"fda_approval", "fda_rejection"}:
            return True
        return False

    def _compute_connector_health(self) -> list[ConnectorHealthMetrics]:
        rows = []
        for connector_name in sorted(self.connectors.keys()):
            stage = f"fetch:{connector_name}"
            run_rows = self.knowledge._conn.execute(
                """
                SELECT
                    run_id,
                    MAX(started_at) AS started_at,
                    MAX(finished_at) AS finished_at,
                    SUM(CASE WHEN status = 'failure' THEN 1 ELSE 0 END) AS failures,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS successes,
                    SUM(
                        COALESCE(
                            CAST(json_extract(checkpoint_json, '$.fetch_errors') AS INTEGER),
                            0
                        )
                    ) AS fetch_errors,
                    AVG(
                        COALESCE(
                            CAST(json_extract(checkpoint_json, '$.documents_fetched') AS REAL),
                            0.0
                        )
                    ) AS avg_documents_fetched,
                    AVG(
                        CASE
                            WHEN finished_at IS NULL THEN NULL
                            ELSE (julianday(finished_at) - julianday(started_at)) * 86400000.0
                        END
                    ) AS avg_latency_ms
                FROM run_state
                WHERE stage = ?
                GROUP BY run_id
                ORDER BY started_at DESC
                LIMIT 20
                """,
                (stage,),
            ).fetchall()
            total_runs = len(run_rows)
            if total_runs == 0:
                rows.append(
                    ConnectorHealthMetrics(
                        connector=connector_name,
                        success_rate=1.0,
                        error_rate=0.0,
                        avg_latency_ms=0.0,
                        n_runs_sampled=0,
                        last_failure_at=None,
                        last_success_at=None,
                        healthy=True,
                    )
                )
                continue

            success_points = 0.0
            last_failure_at: Optional[datetime] = None
            last_success_at: Optional[datetime] = None
            latencies_ms: list[float] = []
            for row in run_rows:
                failures = int(row["failures"] or 0)
                successes = int(row["successes"] or 0)
                fetch_errors = int(row["fetch_errors"] or 0)
                avg_documents = float(row["avg_documents_fetched"] or 0.0)
                latency_ms = row["avg_latency_ms"]
                if latency_ms is not None:
                    latencies_ms.append(max(0.0, float(latency_ms)))
                finished_at = (
                    self.knowledge._coerce_datetime(row["finished_at"])
                    if row["finished_at"] is not None
                    else None
                )
                hard_success = failures == 0 and successes > 0 and fetch_errors == 0
                if hard_success and avg_documents > 0.0:
                    success_points += 1.0
                    if last_success_at is None:
                        last_success_at = finished_at
                elif hard_success and avg_documents <= 0.0:
                    # No hard error, but connector returned no usable documents.
                    # Count as partial health to avoid overstating success.
                    success_points += 0.5
                    if last_failure_at is None:
                        last_failure_at = finished_at
                else:
                    if last_failure_at is None:
                        last_failure_at = finished_at
            success_rate = success_points / total_runs
            error_rate = 1.0 - success_rate
            avg_latency = sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0.0
            threshold = 0.80
            rows.append(
                ConnectorHealthMetrics(
                    connector=connector_name,
                    success_rate=round(success_rate, 6),
                    error_rate=round(error_rate, 6),
                    avg_latency_ms=round(avg_latency, 6),
                    n_runs_sampled=total_runs,
                    last_failure_at=last_failure_at,
                    last_success_at=last_success_at,
                    health_threshold=threshold,
                    healthy=success_rate >= threshold,
                )
            )
        return rows

    def _estimate_llm_extraction_cost(
        self,
        *,
        document: RawDocument,
        extraction: ExtractionResult,
    ) -> float:
        system_prompt = self._cost_prompt_builder.build_system_prompt()
        user_prompt = self._cost_prompt_builder.build_user_prompt(document)
        input_tokens = math.ceil((len(system_prompt) + len(user_prompt)) / 4.0)
        output_tokens = math.ceil(len(extraction.raw_llm_response or "") / 4.0)
        cfg = self.config.extraction
        estimated_cost = (
            (input_tokens / 1000.0) * cfg.llm_estimated_input_cost_per_1k_tokens
            + (output_tokens / 1000.0) * cfg.llm_estimated_output_cost_per_1k_tokens
        )
        return round(max(estimated_cost, 0.0), 6)

    def _emit_llm_cost_limit_alert(self, *, run_id: str) -> None:
        router = self.alert_router
        if router is None:
            return
        system_asset_id = "system"
        router.enqueue_system_alert(
            key=f"llm_daily_cost_limit:{self.cost_guard.current_utc_date.isoformat()}",
            message=(
                "Daily LLM extraction cost limit reached; further extraction calls "
                "will be skipped until the next UTC day."
            ),
            detail={
                "daily_cost_total_usd": self.cost_guard.current_total_usd,
                "daily_cost_limit_usd": self.config.extraction.llm_daily_cost_limit_usd,
                "daily_cost_utc_date": self.cost_guard.current_utc_date.isoformat(),
            },
            run_id=run_id,
            severity=AlertSeverity.LOW,
            trigger=AlertTrigger.SYSTEM_COST_LIMIT_REACHED,
            asset_id=system_asset_id,
        )
        router.flush(system_asset_id, run_id=run_id)


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
        elif name == "pubmed":
            import os
            from bve.connectors.pubmed import PubMedConnector

            api_key = options.pop("api_key", None) or os.getenv("NCBI_API_KEY")
            topic_keywords = options.pop("topic_keywords", None)
            if topic_keywords:
                topic_keywords = tuple(topic_keywords)
            built[name] = PubMedConnector(api_key=api_key, topic_keywords=topic_keywords, **options)
        else:
            raise ValueError(f"Unsupported connector name: {name!r}")

    return built


def load_watchlist_config(path: str | Path) -> WatchlistRunnerConfig:
    cfg_path = Path(path)
    if cfg_path.is_dir():
        files = sorted(cfg_path.glob("watchlist_*.yaml"))
        if not files:
            raise FileNotFoundError(f"No watchlist_*.yaml files found in {cfg_path}")

        base: dict[str, Any] | None = None
        merged_watchlist: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        logger = logging.getLogger("bve.watchlist")

        for file_path in files:
            raw = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
            if not isinstance(raw, dict):
                raise ValueError(f"Invalid watchlist config in {file_path}: expected mapping")

            if base is None:
                base = {k: v for k, v in raw.items() if k != "watchlist"}

            watchlist = raw.get("watchlist") or []
            if not isinstance(watchlist, list):
                raise ValueError(f"Invalid watchlist in {file_path}: expected list")
            for item in watchlist:
                if not isinstance(item, dict):
                    raise ValueError(f"Invalid watchlist entry in {file_path}: expected mapping")
                ticker = item.get("ticker")
                asset_id = item.get("asset_id")
                key = str(ticker).upper() if ticker else str(asset_id or "")
                if key and key in seen_keys:
                    logger.warning(
                        "duplicate watchlist entry in dir; keeping first occurrence key=%s file=%s",
                        key,
                        file_path,
                    )
                    continue
                if key:
                    seen_keys.add(key)
                merged_watchlist.append(item)

        assert base is not None
        base["watchlist"] = merged_watchlist
        return WatchlistRunnerConfig.model_validate(base)

    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    return WatchlistRunnerConfig.model_validate(raw)
