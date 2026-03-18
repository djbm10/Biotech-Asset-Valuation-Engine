"""Replay stored raw documents through extraction, mapping, and valuation."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field

from bve.intelligence.extraction.raw_document import RawDocument
from bve.intelligence.extraction.result import ExtractionStatus
from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace, StoredValuationDiff
from bve.intelligence.memo_generation import WeeklyMemoGenerator, WeeklyMemoInput
from bve.intelligence.phase2 import MappingEngine, ReviewQueue
from bve.pipeline.change_detector import MaterialChangeDetector
from bve.pipeline.watchlist_runner import (
    AssetContextProvider,
    AssetRunSummary,
    AssetValuationContext,
    ConfigAssetContextProvider,
    Phase2SessionValuationExecutor,
    ValuationExecutor,
    WatchlistAsset,
    WatchlistPipelineRunner,
    WatchlistRunnerConfig,
    _build_extractor,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_since(value: str) -> timedelta:
    """Parse compact durations like '7d', '24h', or '2w'."""
    raw = value.strip().lower()
    if not raw:
        raise ValueError("Empty --since value")
    unit = raw[-1]
    try:
        amount = int(raw[:-1])
    except ValueError as exc:
        raise ValueError(f"Invalid --since value: {value!r}") from exc

    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    if unit == "w":
        return timedelta(weeks=amount)
    raise ValueError(f"Unknown time unit in --since: {value!r} (use h/d/w)")


class HistoryReplaySummary(BaseModel):
    """Aggregate output from a replay run."""

    run_id: str
    started_at: datetime
    finished_at: datetime
    documents_considered: int = 0
    documents_replayed: int = 0
    extraction_results_persisted: int = 0
    structured_signals_persisted: int = 0
    events_persisted: int = 0
    valuation_diffs_persisted: int = 0
    memos_persisted: int = 0
    assets: list[AssetRunSummary] = Field(default_factory=list)


class HistoryReplayRunner:
    """Reprocess already-stored raw documents without refetching connectors."""

    def __init__(
        self,
        config: WatchlistRunnerConfig,
        *,
        extractor=None,
        mapping_engine: Optional[MappingEngine] = None,
        context_provider: Optional[AssetContextProvider] = None,
        valuation_executor: Optional[ValuationExecutor] = None,
        knowledge_store: Optional[KnowledgeStore] = None,
        change_detector: Optional[MaterialChangeDetector] = None,
        memo_generator: Optional[WeeklyMemoGenerator] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.config = config
        self.logger = logger or logging.getLogger("bve.history_replay")
        self.extractor = extractor or _build_extractor(config.extraction)
        self.mapping_engine = mapping_engine or MappingEngine()
        self.context_provider = context_provider or ConfigAssetContextProvider()
        self.valuation_executor = valuation_executor or Phase2SessionValuationExecutor(
            config.valuation_output_dir
        )
        self.knowledge = knowledge_store or KnowledgeStore(config.knowledge_db_path)
        self.change_detector = change_detector or MaterialChangeDetector(config.materiality)
        self.memo_generator = memo_generator or WeeklyMemoGenerator()

    def close(self) -> None:
        self.knowledge.close()

    def replay(
        self,
        *,
        since: Optional[str | timedelta | datetime] = None,
        run_id: Optional[str] = None,
    ) -> HistoryReplaySummary:
        resolved_run_id = run_id or str(uuid.uuid4())
        started_at = _utcnow()
        cutoff = self._resolve_cutoff(since)
        docs_by_asset = self._load_documents_by_asset(cutoff=cutoff)
        asset_summaries: list[AssetRunSummary] = []
        replayed_docs = 0
        persisted_extractions = 0
        persisted_signals = 0
        persisted_events = 0
        persisted_diffs = 0
        persisted_memos = 0

        for asset_cfg in self.config.watchlist:
            docs = docs_by_asset.get(asset_cfg.asset_id, [])
            replayed_docs += len(docs)
            asset_summary = self._replay_asset(
                asset_cfg,
                docs=docs,
                run_id=resolved_run_id,
            )
            asset_summaries.append(asset_summary)
            persisted_extractions += asset_summary.documents_processed
            persisted_signals += asset_summary.signals_created
            persisted_events += asset_summary.events_created
            persisted_diffs += asset_summary.valuation_diffs_persisted
            persisted_memos += 1 if asset_summary.memo_generated else 0

        finished_at = _utcnow()
        return HistoryReplaySummary(
            run_id=resolved_run_id,
            started_at=started_at,
            finished_at=finished_at,
            documents_considered=sum(len(v) for v in docs_by_asset.values()),
            documents_replayed=replayed_docs,
            extraction_results_persisted=persisted_extractions,
            structured_signals_persisted=persisted_signals,
            events_persisted=persisted_events,
            valuation_diffs_persisted=persisted_diffs,
            memos_persisted=persisted_memos,
            assets=asset_summaries,
        )

    def _resolve_cutoff(
        self,
        since: Optional[str | timedelta | datetime],
    ) -> Optional[datetime]:
        if since is None:
            return None
        if isinstance(since, datetime):
            return since if since.tzinfo is not None else since.replace(tzinfo=timezone.utc)
        if isinstance(since, timedelta):
            return _utcnow() - since
        return _utcnow() - parse_since(since)

    def _load_documents_by_asset(
        self,
        *,
        cutoff: Optional[datetime],
    ) -> dict[str, list[RawDocument]]:
        asset_ids = {asset.asset_id for asset in self.config.watchlist}
        if not asset_ids:
            return {}

        placeholders = ", ".join("?" for _ in asset_ids)
        sql = (
            "SELECT payload_json, created_at "
            "FROM raw_documents "
            f"WHERE json_extract(payload_json, '$.entity_hints.asset_id') IN ({placeholders})"
        )
        params: list[object] = list(asset_ids)
        if cutoff is not None:
            sql += " AND created_at >= ?"
            params.append(cutoff.isoformat())
        sql += " ORDER BY created_at ASC"

        rows = self.knowledge._conn.execute(sql, params).fetchall()
        grouped: dict[str, list[RawDocument]] = {asset_id: [] for asset_id in asset_ids}
        for row in rows:
            payload = json.loads(row["payload_json"])
            document = RawDocument.model_validate(payload)
            grouped.setdefault(document.entity_hints.asset_id, []).append(document)

        for docs in grouped.values():
            docs.sort(
                key=lambda doc: (
                    doc.published_at or doc.retrieved_at,
                    doc.retrieved_at,
                    doc.id,
                )
            )
        return grouped

    def _replay_asset(
        self,
        asset_cfg: WatchlistAsset,
        *,
        docs: list[RawDocument],
        run_id: str,
    ) -> AssetRunSummary:
        summary = AssetRunSummary(
            run_id=run_id,
            company_id=asset_cfg.company_id,
            asset_id=asset_cfg.asset_id,
            status="success",
            documents_fetched=len(docs),
            stage_timings_ms={
                "ingestion": 0.0,
                "extraction": 0.0,
                "valuation": 0.0,
                "alerts": 0.0,
            },
        )

        try:
            context = self.context_provider.get_context(asset_cfg)
            created_signals = []
            ambiguous_signal_ids: list[str] = []
            valuation_diffs: list[StoredValuationDiff] = []

            for document in docs:
                event_id = WatchlistPipelineRunner._event_id_for_document(
                    company_id=asset_cfg.company_id,
                    asset_id=asset_cfg.asset_id,
                    document=document,
                )
                extraction = self.extractor.extract(document, event_id=event_id)
                extraction_record = self.knowledge.add_extraction_result(
                    extraction,
                    SourceTrace(
                        source_type="history_replay_extraction",
                        source_ref=f"raw_document:{document.id}",
                    ),
                    raw_document_id=document.id,
                )
                summary.documents_processed += 1

                if extraction.status != ExtractionStatus.SUCCESS or extraction.signal is None:
                    continue

                signal = self._stable_signal_for_event(extraction.signal)
                confidence = extraction.extraction_confidence
                ext_cfg = self.config.extraction

                if confidence < ext_cfg.confidence_discard_threshold:
                    self.logger.info(
                        "history_replay_discard_low_confidence asset=%s document=%s conf=%.3f",
                        asset_cfg.asset_id,
                        document.id,
                        confidence,
                    )
                    continue

                if confidence < ext_cfg.confidence_review_threshold:
                    ambiguous_signal_ids.append(signal.id)
                    self.knowledge.add_structured_signal(
                        signal,
                        SourceTrace(
                            source_type="history_replay_signal",
                            source_ref=f"extraction:{extraction_record.id}",
                        ),
                        extraction_result_id=extraction_record.id,
                    )
                    summary.signals_created += 1
                    continue

                if extraction.ambiguity_flag:
                    ambiguous_signal_ids.append(signal.id)

                self.knowledge.add_structured_signal(
                    signal,
                    SourceTrace(
                        source_type="history_replay_signal",
                        source_ref=f"extraction:{extraction_record.id}",
                    ),
                    extraction_result_id=extraction_record.id,
                )
                event = WatchlistPipelineRunner._event_from_extraction(
                    signal=signal,
                    document=document,
                    extraction=extraction,
                )
                self.knowledge.add_event(
                    event,
                    SourceTrace(
                        source_type="history_replay_event",
                        source_ref=f"signal:{signal.id}",
                    ),
                    signal_id=signal.id,
                )
                created_signals.append(signal)
                summary.signals_created += 1
                summary.events_created += 1

            for signal in created_signals:
                current_context = self._current_context_for_mapping(
                    company_id=asset_cfg.company_id,
                    asset_id=asset_cfg.asset_id,
                    fallback=context,
                )
                mapping_batch = self.mapping_engine.map_signal(
                    signal,
                    engine_asset_id=current_context.asset.id,
                    asset=current_context.asset,
                    trials=current_context.trials,
                    market_model=current_context.market_model,
                )
                summary.proposals_generated += len(mapping_batch.proposals)

                queue = ReviewQueue(policy=self.mapping_engine.policy)
                routing = queue.route(signal, mapping_batch.proposals)
                for item in routing.queued:
                    review = queue.record_decision(
                        item_id=item.id,
                        decision="deferred",
                        reviewer_id="history-replay",
                        rationale=item.route_reason,
                        notes="Queued during raw-document history replay",
                    )
                    self.knowledge.add_review_decision(
                        review,
                        company_id=asset_cfg.company_id,
                        asset_id=asset_cfg.asset_id,
                        source_trace=SourceTrace(
                            source_type="history_replay_review",
                            source_ref=f"proposal:{review.proposal_id}",
                        ),
                    )
                    summary.review_decisions_logged += 1

                effective_values = queue.effective_overrides(mapping_batch.proposals)
                stored_diff = self.valuation_executor.apply(
                    company_id=asset_cfg.company_id,
                    asset_id=asset_cfg.asset_id,
                    context=current_context,
                    signal=signal,
                    proposals=mapping_batch.proposals,
                    effective_values=effective_values,
                    run_at=_utcnow(),
                )
                if stored_diff is None:
                    continue

                existing_diff = self._existing_diff_for_event(signal.event_id)
                if existing_diff is not None:
                    stored_diff = stored_diff.model_copy(update={"run_id": existing_diff.run_id})

                saved_diff = self.knowledge.add_valuation_diff(
                    stored_diff,
                    company_id=asset_cfg.company_id,
                    source_trace=SourceTrace(
                        source_type="history_replay_valuation",
                        source_ref=f"event:{signal.event_id}",
                    ),
                    assumptions_snapshot=stored_diff.applied_overrides,
                    valuation_snapshot=stored_diff.valuation_after,
                )
                valuation_diffs.append(saved_diff)
                summary.valuation_runs += 1
                summary.valuation_diffs_persisted += 1

            dossier = self.knowledge.generate_dossier(
                company_id=asset_cfg.company_id,
                asset_id=asset_cfg.asset_id,
                persist=True,
            )
            summary.dossier_id = dossier.id

            if self.change_detector.should_generate_weekly_memo(valuation_diffs):
                period_end = _utcnow().date()
                period_start = period_end - timedelta(days=6)
                memo = self.memo_generator.generate(
                    WeeklyMemoInput(
                        dossier=dossier,
                        structured_events=created_signals,
                        valuation_diffs=valuation_diffs,
                        review_decisions=self.knowledge.get_review_decisions(
                            company_id=asset_cfg.company_id,
                            asset_id=asset_cfg.asset_id,
                            date_from=period_start,
                            date_to=period_end,
                            limit=500,
                        ),
                        ambiguous_signal_ids=sorted(set(ambiguous_signal_ids)),
                        generated_at=_utcnow(),
                    ),
                    memo_id=self._stable_memo_id(
                        company_id=asset_cfg.company_id,
                        asset_id=asset_cfg.asset_id,
                        period_end=period_end,
                    ),
                    period_start=period_start,
                    period_end=period_end,
                    week_ending=period_end,
                )
                self.knowledge.add_memo(
                    memo.to_memo_record(
                        SourceTrace(
                            source_type="history_replay_memo",
                            source_ref=f"asset:{asset_cfg.asset_id}",
                        )
                    )
                )
                summary.memo_generated = True
                summary.memo_id = memo.id

            return summary
        except Exception as exc:
            summary.status = "failure"
            summary.errors.append(str(exc))
            return summary

    def _stable_signal_for_event(self, signal):
        existing = self.knowledge.get_structured_signal_by_event_id(signal.event_id)
        if existing is None:
            return signal
        return signal.model_copy(update={"id": existing.id})

    def _existing_diff_for_event(self, event_id: str) -> Optional[StoredValuationDiff]:
        row = self.knowledge._conn.execute(
            """
            SELECT payload_json
            FROM valuation_diffs
            WHERE event_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (event_id,),
        ).fetchone()
        if row is None:
            return None
        return StoredValuationDiff.model_validate_json(row["payload_json"])

    def _current_context_for_mapping(
        self,
        *,
        company_id: str,
        asset_id: str,
        fallback: AssetValuationContext,
    ) -> AssetValuationContext:
        executor = self.valuation_executor
        if not isinstance(executor, Phase2SessionValuationExecutor):
            return fallback
        key = executor._session_key(company_id, asset_id)  # noqa: SLF001
        session = executor._sessions.get(key)  # noqa: SLF001
        if session is None:
            return fallback
        return AssetValuationContext(
            asset=session._asset,  # noqa: SLF001
            company=session._company,  # noqa: SLF001
            trials=list(session._trials),  # noqa: SLF001
            market_model=session._market_model,  # noqa: SLF001
        )

    @staticmethod
    def _stable_memo_id(*, company_id: str, asset_id: str, period_end) -> str:
        return str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"history-replay|{company_id}|{asset_id}|{period_end.isoformat()}",
            )
        )


__all__ = [
    "HistoryReplayRunner",
    "HistoryReplaySummary",
    "parse_since",
]
