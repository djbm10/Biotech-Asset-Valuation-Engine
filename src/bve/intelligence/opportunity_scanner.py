"""
Continuous opportunity scanning on top of ranking outputs.

Deterministic contract:
  - identical watchlist + DB state + config => identical scanner outputs
  - idempotent alert insertion via key: (asset_id, event_type, window)
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from bve.intelligence.knowledge_layer import (
    BacktestSnapshot,
    KnowledgeStore,
    OpportunityAlertRecord,
)
from bve.intelligence.opportunity_monitor import OpportunityMonitor, OpportunityMonitorConfig
from bve.intelligence.opportunity_snapshot import OpportunitySnapshotStore
from bve.intelligence.ranking import AssetRankingEngine, RankedOpportunity, RankingConfig
from bve.models.catalyst_model import CatalystModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OpportunityScannerConfig(BaseModel):
    """Scanner thresholds and metadata."""

    min_composite_score: float = Field(default=0.30, ge=0.0, le=1.0)
    min_abs_mispricing_pct: float = Field(default=10.0, ge=0.0)
    alert_window_hours: int = Field(default=24, ge=1)
    top_n: int = Field(default=10, ge=1)
    model_version: str = "opportunity_scanner_v1"
    persist_daily_snapshots: bool = True
    monitor: OpportunityMonitorConfig = Field(default_factory=OpportunityMonitorConfig)


class OpportunityScanResult(BaseModel):
    """Result of one deterministic scan pass."""

    run_id: str
    scanned_at: datetime
    config: OpportunityScannerConfig
    opportunities: list[RankedOpportunity] = Field(default_factory=list)
    alerts_emitted: list[OpportunityAlertRecord] = Field(default_factory=list)
    alerts_suppressed_as_duplicate: int = 0
    monitor_alerts_emitted: list[OpportunityAlertRecord] = Field(default_factory=list)
    monitor_alerts_suppressed_as_duplicate: int = 0
    snapshots_written: int = 0
    # Wave D: cross-asset propagation proposals targeting watchlist assets.
    peer_dislocation_proposals: list[dict] = Field(default_factory=list)


class CatalystContext(BaseModel):
    """Upcoming catalyst metadata used in ranking adjustments."""

    catalyst_type: Optional[str] = None
    catalyst_date: Optional[date] = None
    days_to_catalyst: Optional[int] = None
    catalyst_importance: float = 1.0
    catalyst_weight: float = 1.0


class OpportunityScanner:
    """Deterministic, idempotent opportunity scanner."""

    def __init__(
        self,
        *,
        knowledge_store: KnowledgeStore,
        config: Optional[OpportunityScannerConfig] = None,
        catalyst_model: Optional[CatalystModel] = None,
        snapshot_store: Optional[OpportunitySnapshotStore] = None,
        monitor: Optional[OpportunityMonitor] = None,
    ) -> None:
        self.knowledge = knowledge_store
        self.config = config or OpportunityScannerConfig()
        self.catalyst_model = catalyst_model
        self.snapshot_store = snapshot_store or OpportunitySnapshotStore(knowledge_store)
        self.monitor = monitor or OpportunityMonitor(
            knowledge_store=knowledge_store,
            config=self.config.monitor,
            snapshot_store=self.snapshot_store,
        )

    def scan_from_watchlist_config(
        self,
        watchlist_config: Any,
        *,
        run_id: str,
        scanned_at: Optional[datetime] = None,
    ) -> OpportunityScanResult:
        scanned_at = scanned_at or _utcnow()
        ranking_cfg = self._resolve_ranking_config(watchlist_config)
        ranking = AssetRankingEngine(
            config=ranking_cfg,
            knowledge_store=self.knowledge,
        ).rank_from_watchlist_config(
            watchlist_config,
            ranked_at=scanned_at,
        )

        opportunities = list(ranking.opportunities)
        opportunities = self._apply_catalyst_awareness(
            opportunities,
            as_of=scanned_at.date(),
        )
        monitor_result = self.monitor.evaluate(
            opportunities,
            monitored_at=scanned_at,
            run_id=run_id,
        )
        snapshots_written = 0
        if self.config.persist_daily_snapshots:
            try:
                snapshots_written = self.snapshot_store.write_snapshots(
                    opportunities,
                    snapshot_date=scanned_at.date(),
                    run_id=run_id,
                    created_at=scanned_at,
                )
            except Exception:
                snapshots_written = 0
        alerts: list[OpportunityAlertRecord] = []
        suppressed = 0
        for opp in opportunities:
            record = self._to_alert_record(opp, run_id=run_id, scanned_at=scanned_at)
            if record is None:
                continue
            inserted = self.knowledge.add_opportunity_alert(record)
            if inserted:
                alerts.append(record)
                self._write_backtest_snapshot(
                    opp=opp,
                    record=record,
                    scanned_at=scanned_at,
                )
            else:
                suppressed += 1

        # Wave D: pull pending cross-asset propagation proposals for watchlist assets.
        watchlist_asset_ids = [
            asset.asset_id
            for asset in getattr(watchlist_config, "watchlist", [])
        ]
        peer_proposals: list[dict] = []
        if watchlist_asset_ids:
            try:
                peer_proposals = self.knowledge.get_pending_propagation_proposals(
                    watchlist_asset_ids
                )
            except Exception:
                peer_proposals = []

        return OpportunityScanResult(
            run_id=run_id,
            scanned_at=scanned_at,
            config=self.config,
            opportunities=opportunities,
            alerts_emitted=alerts,
            alerts_suppressed_as_duplicate=suppressed,
            monitor_alerts_emitted=monitor_result.alerts_emitted,
            monitor_alerts_suppressed_as_duplicate=(
                monitor_result.alerts_suppressed_as_duplicate
            ),
            snapshots_written=snapshots_written,
            peer_dislocation_proposals=peer_proposals,
        )

    def _to_alert_record(
        self,
        opp: RankedOpportunity,
        *,
        run_id: str,
        scanned_at: datetime,
    ) -> Optional[OpportunityAlertRecord]:
        if opp.composite_score < self.config.min_composite_score:
            return None

        mispricing_pct = (
            (opp.mispricing_score or 0.0) * 100.0 if opp.mispricing_score is not None else 0.0
        )
        if abs(mispricing_pct) < self.config.min_abs_mispricing_pct:
            return None

        event_type = opp.signal_event_type or "unknown"
        window = self._window_key(scanned_at, hours=self.config.alert_window_hours)
        payload = {
            "rank": opp.rank,
            "asset_id": opp.asset_id,
            "company_id": opp.company_id,
            "ticker": opp.ticker,
            "signal_id": opp.signal_id,
            "signal_timestamp": opp.last_diff_at.isoformat() if opp.last_diff_at else None,
            "composite_score": round(float(opp.composite_score), 6),
            "base_rank_score": (
                round(float(opp.base_rank_score), 6) if opp.base_rank_score is not None else None
            ),
            "final_rank_score": (
                round(float(opp.final_rank_score), 6) if opp.final_rank_score is not None else None
            ),
            "intrinsic_value_millions": opp.intrinsic_value_millions,
            "mispricing_pct": round(float(mispricing_pct), 4),
            "mispricing_score": opp.mispricing_score,
            "confidence": round(float(opp.extraction_confidence), 6),
            "delta_npv_millions": opp.delta_npv_millions,
            "event_type": event_type,
            "catalyst_type": opp.catalyst_type,
            "catalyst_date": opp.catalyst_date.isoformat() if opp.catalyst_date else None,
            "catalyst_score": opp.catalyst_score,
            "catalyst_boost_weight": opp.catalyst_boost_weight,
            "days_to_catalyst": opp.days_to_catalyst,
            "catalyst_importance": opp.catalyst_importance,
            "model_version": self.config.model_version,
        }
        return OpportunityAlertRecord(
            asset_id=opp.asset_id,
            event_type=event_type,
            window=window,
            run_id=run_id,
            created_at=scanned_at,
            payload_json=payload,
        )

    @staticmethod
    def _resolve_ranking_config(watchlist_config: Any) -> RankingConfig:
        base = getattr(watchlist_config, "ranking", None)
        if base is None:
            return RankingConfig()
        if isinstance(base, RankingConfig):
            return RankingConfig.model_validate(base.model_dump(mode="json"))
        if hasattr(base, "model_dump"):
            return RankingConfig.model_validate(base.model_dump(mode="json"))
        return RankingConfig.model_validate(base)

    def _apply_catalyst_awareness(
        self,
        opportunities: list[RankedOpportunity],
        *,
        as_of: date,
    ) -> list[RankedOpportunity]:
        if self.catalyst_model is None:
            return self._apply_heuristic_catalyst_awareness(opportunities, as_of=as_of)

        adjusted: list[RankedOpportunity] = []
        for opp in opportunities:
            catalyst = self._lookup_catalyst(asset_id=opp.asset_id, as_of=as_of)
            catalyst_event_type = catalyst.catalyst_type or opp.signal_event_type or "unknown"
            catalyst_valuation = self.catalyst_model.score_catalyst(
                catalyst_event_type,
                opp.signal_trial_phase,
                signal_id=opp.signal_id,
                event_key=opp.signal_id or f"{opp.asset_id}:{opp.rank}",
                asset_id=opp.asset_id,
                catalyst_date=catalyst.catalyst_date,
                days_to_catalyst=catalyst.days_to_catalyst,
            )
            boost_weight = self._catalyst_boost_weight(
                catalyst_valuation.expected_return_pct
            ) * self._design_confidence_weight(catalyst_valuation.design_quality_multiplier)
            boost_weight = max(0.5, min(1.5, boost_weight))
            base_score = float(
                opp.base_rank_score if opp.base_rank_score is not None else opp.composite_score
            )
            adjusted_score = min(1.0, max(0.0, base_score * boost_weight))
            adjusted.append(
                opp.model_copy(
                    update={
                        "composite_score": round(adjusted_score, 6),
                        "base_rank_score": round(base_score, 6),
                        "final_rank_score": round(adjusted_score, 6),
                        "catalyst_score": round(catalyst_valuation.expected_return_pct, 6),
                        "catalyst_boost_weight": round(boost_weight, 6),
                        "catalyst_type": catalyst.catalyst_type,
                        "catalyst_date": catalyst.catalyst_date,
                        "days_to_catalyst": catalyst.days_to_catalyst,
                        "catalyst_importance": catalyst.catalyst_importance,
                        "catalyst_valuation": catalyst_valuation,
                    }
                )
            )

        adjusted.sort(
            key=lambda o: (
                -float(o.composite_score),
                o.days_to_catalyst if o.days_to_catalyst is not None else 10_000,
                o.asset_id,
            )
        )
        return [opp.model_copy(update={"rank": i + 1}) for i, opp in enumerate(adjusted)]

    def _apply_heuristic_catalyst_awareness(
        self,
        opportunities: list[RankedOpportunity],
        *,
        as_of: date,
    ) -> list[RankedOpportunity]:
        adjusted: list[RankedOpportunity] = []
        for opp in opportunities:
            catalyst = self._lookup_catalyst(asset_id=opp.asset_id, as_of=as_of)
            base_score = float(
                opp.base_rank_score if opp.base_rank_score is not None else opp.composite_score
            )
            boost_weight = catalyst.catalyst_weight * catalyst.catalyst_importance
            adjusted_score = min(
                1.0,
                base_score * boost_weight,
            )
            adjusted.append(
                opp.model_copy(
                    update={
                        "composite_score": round(adjusted_score, 6),
                        "base_rank_score": round(base_score, 6),
                        "final_rank_score": round(adjusted_score, 6),
                        "catalyst_boost_weight": round(boost_weight, 6),
                        "catalyst_type": catalyst.catalyst_type,
                        "catalyst_date": catalyst.catalyst_date,
                        "days_to_catalyst": catalyst.days_to_catalyst,
                        "catalyst_importance": catalyst.catalyst_importance,
                    }
                )
            )

        adjusted.sort(
            key=lambda o: (
                -float(o.composite_score),
                o.days_to_catalyst if o.days_to_catalyst is not None else 10_000,
                o.asset_id,
            )
        )
        return [opp.model_copy(update={"rank": i + 1}) for i, opp in enumerate(adjusted)]

    @staticmethod
    def _catalyst_boost_weight(expected_return_pct: float) -> float:
        """
        Map expected catalyst return to a confidence-style multiplicative boost.

        Expected return of 0% -> 1.00x. Strongly negative -> downweight to 0.75x.
        Strongly positive -> upweight to 1.25x.
        """
        normalized = max(0.0, min(1.0, 0.5 + (expected_return_pct / 100.0)))
        return 0.75 + 0.5 * normalized

    @staticmethod
    def _design_confidence_weight(design_quality_multiplier: float) -> float:
        """Apply trial-design confidence as a bounded ranking-only multiplier."""
        return max(0.8, min(1.2, float(design_quality_multiplier)))

    def _write_backtest_snapshot(
        self,
        *,
        opp: RankedOpportunity,
        record: OpportunityAlertRecord,
        scanned_at: datetime,
    ) -> None:
        try:
            signal_date = (
                opp.last_diff_at.date() if opp.last_diff_at is not None else scanned_at.date()
            )
            alert_id = f"{record.asset_id}:{record.event_type}:{record.window}"
            self.knowledge.write_backtest_snapshot(
                BacktestSnapshot(
                    snapshot_id=str(uuid.uuid4()),
                    alert_id=alert_id,
                    asset_id=opp.asset_id,
                    signal_date=signal_date,
                    signal_id=opp.signal_id,
                    signal_timestamp=opp.last_diff_at,
                    composite_score=float(opp.composite_score),
                    extraction_confidence=float(opp.extraction_confidence),
                    delta_npv_millions=float(opp.delta_npv_millions),
                    intrinsic_value_millions=opp.intrinsic_value_millions,
                    mispricing_score=(
                        float(opp.mispricing_score) if opp.mispricing_score is not None else None
                    ),
                    catalyst_date=opp.catalyst_date,
                    catalyst_type=opp.catalyst_type,
                    catalyst_score=opp.catalyst_score,
                    rank_at_signal=opp.rank,
                    model_version=self.config.model_version,
                    created_at=scanned_at,
                )
            )
        except Exception:
            # Snapshotting is an observability/backtest side-effect and must not
            # block opportunity detection.
            return

    def _lookup_catalyst(self, *, asset_id: str, as_of: date) -> CatalystContext:
        # Source 1: explicit future events in events table.
        row = self.knowledge._conn.execute(
            """
            SELECT event_type, observed_at
            FROM events
            WHERE asset_id = ? AND DATE(observed_at) > DATE(?)
            ORDER BY observed_at ASC
            LIMIT 1
            """,
            (asset_id, as_of.isoformat()),
        ).fetchone()
        if row is not None:
            catalyst_date = date.fromisoformat(str(row["observed_at"])[:10])
            days = max(0, (catalyst_date - as_of).days)
            return self._catalyst_from_values(
                catalyst_type=str(row["event_type"]),
                catalyst_date=catalyst_date,
                days_to_catalyst=days,
            )

        # Source 2: inferred milestones from ClinicalTrials/FDA/news text.
        inferred = self._infer_catalyst_from_documents(asset_id=asset_id, as_of=as_of)
        if inferred is not None:
            return inferred

        return CatalystContext()

    def _infer_catalyst_from_documents(
        self,
        *,
        asset_id: str,
        as_of: date,
    ) -> Optional[CatalystContext]:
        rows = self.knowledge._conn.execute(
            """
            SELECT payload_json
            FROM raw_documents
            WHERE json_extract(payload_json, '$.entity_hints.asset_id') = ?
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (asset_id,),
        ).fetchall()
        for row in rows:
            payload = row["payload_json"]
            if isinstance(payload, str):
                try:
                    import json

                    payload_obj = json.loads(payload)
                except Exception:
                    continue
            else:
                payload_obj = payload
            text = str(payload_obj.get("raw_text") or "")
            source = str(payload_obj.get("source") or "")
            found = self._extract_catalyst_date(text=text, source=source)
            if found is None:
                continue
            catalyst_type, catalyst_date = found
            if catalyst_date < as_of:
                continue
            days = (catalyst_date - as_of).days
            return self._catalyst_from_values(
                catalyst_type=catalyst_type,
                catalyst_date=catalyst_date,
                days_to_catalyst=days,
            )
        return None

    @staticmethod
    def _extract_catalyst_date(*, text: str, source: str) -> Optional[tuple[str, date]]:
        patterns = [
            (
                r"(?:primary completion date|readout(?: date)?)[^\n:]*[:\-]\s*(\d{4}-\d{2}-\d{2})",
                "trial_readout",
            ),
            (r"(?:pdufa(?: date)?|action date)[^\n:]*[:\-]\s*(\d{4}-\d{2}-\d{2})", "fda_decision"),
            (
                r"(?:conference|presentation)[^\n:]*[:\-]\s*(\d{4}-\d{2}-\d{2})",
                "conference_presentation",
            ),
        ]
        normalized = " ".join(text.split())
        for pattern, typ in patterns:
            m = re.search(pattern, normalized, flags=re.IGNORECASE)
            if not m:
                continue
            try:
                return typ, date.fromisoformat(m.group(1))
            except ValueError:
                continue
        return None

    @staticmethod
    def _catalyst_from_values(
        *,
        catalyst_type: str,
        catalyst_date: date,
        days_to_catalyst: int,
    ) -> CatalystContext:
        if days_to_catalyst < 30:
            weight = 1.4
        elif days_to_catalyst < 90:
            weight = 1.2
        else:
            weight = 1.0
        importance = {
            "trial_readout": 1.1,
            "interim_analysis": 1.0,
            "fda_decision": 1.2,
            "fda_approval": 1.2,
            "fda_rejection": 1.2,
            "conference_presentation": 0.9,
            "publication": 0.9,
        }.get(catalyst_type, 1.0)
        return CatalystContext(
            catalyst_type=catalyst_type,
            catalyst_date=catalyst_date,
            days_to_catalyst=days_to_catalyst,
            catalyst_importance=importance,
            catalyst_weight=weight,
        )

    @staticmethod
    def _window_key(ts: datetime, *, hours: int) -> str:
        """Stable window bucket used in alert idempotency key."""
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        seconds = hours * 3600
        epoch = int(ts.timestamp())
        bucket_start = (epoch // seconds) * seconds
        start_dt = datetime.fromtimestamp(bucket_start, tz=timezone.utc)
        end_dt = start_dt + timedelta(hours=hours)
        return f"{start_dt.isoformat()}__{end_dt.isoformat()}"
