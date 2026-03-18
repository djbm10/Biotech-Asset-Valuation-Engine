"""Deterministic change detection on top of daily opportunity snapshots."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from bve.intelligence.knowledge_layer import OpportunityAlertRecord
from bve.intelligence.opportunity_snapshot import OpportunitySnapshotStore
from bve.intelligence.ranking import RankedOpportunity

if TYPE_CHECKING:
    from bve.intelligence.knowledge_layer import KnowledgeStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OpportunityMonitorConfig(BaseModel):
    """Thresholds for change-based opportunity alerts."""

    top_n: int = Field(default=10, ge=1)
    score_change_threshold_pct: float = Field(default=30.0, ge=0.0)
    mispricing_threshold_pct: float = Field(default=25.0, ge=0.0)
    alert_window_days: int = Field(default=1, ge=1)


class OpportunityMonitorResult(BaseModel):
    """Output from one monitor pass."""

    monitored_at: datetime
    reference_snapshot_date: Optional[str] = None
    alerts_emitted: list[OpportunityAlertRecord] = Field(default_factory=list)
    alerts_suppressed_as_duplicate: int = 0


class OpportunityMonitor:
    """Compares current rankings against the most recent prior daily snapshot."""

    def __init__(
        self,
        *,
        knowledge_store: "KnowledgeStore",
        config: Optional[OpportunityMonitorConfig] = None,
        snapshot_store: Optional[OpportunitySnapshotStore] = None,
    ) -> None:
        self.knowledge = knowledge_store
        self.config = config or OpportunityMonitorConfig()
        self.snapshot_store = snapshot_store or OpportunitySnapshotStore(knowledge_store)

    def evaluate(
        self,
        opportunities: list[RankedOpportunity],
        *,
        monitored_at: Optional[datetime] = None,
        run_id: Optional[str] = None,
    ) -> OpportunityMonitorResult:
        monitored_at = monitored_at or _utcnow()
        snapshot_date = monitored_at.date()
        previous_date = self.snapshot_store.latest_snapshot_date_before(snapshot_date)
        if previous_date is None:
            return OpportunityMonitorResult(monitored_at=monitored_at)

        previous = self.snapshot_store.get_snapshot_map(snapshot_date=previous_date)
        alerts: list[OpportunityAlertRecord] = []
        suppressed = 0
        current_top = sorted(opportunities, key=lambda opp: opp.rank)

        for opp in current_top:
            prev = previous.get(opp.asset_id)
            for record in self._alerts_for_opportunity(
                opp,
                previous_snapshot=prev,
                monitored_at=monitored_at,
                run_id=run_id,
            ):
                if self.knowledge.add_opportunity_alert(record):
                    alerts.append(record)
                else:
                    suppressed += 1

        return OpportunityMonitorResult(
            monitored_at=monitored_at,
            reference_snapshot_date=previous_date.isoformat(),
            alerts_emitted=alerts,
            alerts_suppressed_as_duplicate=suppressed,
        )

    def _alerts_for_opportunity(
        self,
        opp: RankedOpportunity,
        *,
        previous_snapshot,
        monitored_at: datetime,
        run_id: Optional[str],
    ) -> list[OpportunityAlertRecord]:
        records: list[OpportunityAlertRecord] = []
        window = self._window_key(monitored_at, days=self.config.alert_window_days)

        if opp.rank <= self.config.top_n and (
            previous_snapshot is None or previous_snapshot.rank > self.config.top_n
        ):
            records.append(
                self._record(
                    asset_id=opp.asset_id,
                    event_type="opportunity_top10_entry",
                    window=window,
                    monitored_at=monitored_at,
                    run_id=run_id,
                    payload={
                        "asset_id": opp.asset_id,
                        "current_rank": opp.rank,
                        "previous_rank": (
                            previous_snapshot.rank if previous_snapshot is not None else None
                        ),
                        "score": round(float(opp.composite_score), 6),
                        "mispricing": opp.mispricing,
                        "confidence": round(float(opp.extraction_confidence), 6),
                        "event_type": opp.signal_event_type,
                    },
                )
            )

        if previous_snapshot is not None:
            score_change_pct = self._score_change_pct(previous_snapshot.score, opp.composite_score)
            if score_change_pct is not None and score_change_pct > self.config.score_change_threshold_pct:
                records.append(
                    self._record(
                        asset_id=opp.asset_id,
                        event_type="opportunity_score_change",
                        window=window,
                        monitored_at=monitored_at,
                        run_id=run_id,
                        payload={
                            "asset_id": opp.asset_id,
                            "current_rank": opp.rank,
                            "previous_rank": previous_snapshot.rank,
                            "current_score": round(float(opp.composite_score), 6),
                            "previous_score": round(float(previous_snapshot.score), 6),
                            "score_change_pct": round(score_change_pct, 4),
                            "event_type": opp.signal_event_type,
                        },
                    )
                )

            crossing = self._mispricing_crossing(
                previous_snapshot.mispricing,
                opp.mispricing,
                threshold_pct=self.config.mispricing_threshold_pct,
            )
            if crossing is not None:
                records.append(
                    self._record(
                        asset_id=opp.asset_id,
                        event_type="opportunity_mispricing_cross",
                        window=window,
                        monitored_at=monitored_at,
                        run_id=run_id,
                        payload={
                            "asset_id": opp.asset_id,
                            "direction": crossing,
                            "threshold_pct": self.config.mispricing_threshold_pct,
                            "current_mispricing": opp.mispricing,
                            "previous_mispricing": previous_snapshot.mispricing,
                            "current_rank": opp.rank,
                            "previous_rank": previous_snapshot.rank,
                            "event_type": opp.signal_event_type,
                        },
                    )
                )

        return records

    @staticmethod
    def _record(
        *,
        asset_id: str,
        event_type: str,
        window: str,
        monitored_at: datetime,
        run_id: Optional[str],
        payload: dict[str, object],
    ) -> OpportunityAlertRecord:
        return OpportunityAlertRecord(
            asset_id=asset_id,
            event_type=event_type,
            window=window,
            run_id=run_id,
            created_at=monitored_at,
            payload_json=payload,
        )

    @staticmethod
    def _score_change_pct(previous_score: float, current_score: float) -> Optional[float]:
        prev = float(previous_score)
        curr = float(current_score)
        if math.isclose(prev, 0.0, abs_tol=1e-12):
            if math.isclose(curr, 0.0, abs_tol=1e-12):
                return 0.0
            return None
        return abs((curr - prev) / abs(prev)) * 100.0

    @staticmethod
    def _mispricing_crossing(
        previous_mispricing: Optional[float],
        current_mispricing: Optional[float],
        *,
        threshold_pct: float,
    ) -> Optional[str]:
        if previous_mispricing is None or current_mispricing is None:
            return None
        threshold = threshold_pct / 100.0
        prev_over = abs(float(previous_mispricing)) >= threshold
        curr_over = abs(float(current_mispricing)) >= threshold
        if prev_over == curr_over:
            return None
        return "entered" if curr_over else "exited"

    @staticmethod
    def _window_key(ts: datetime, *, days: int) -> str:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        start_dt = datetime(ts.year, ts.month, ts.day, tzinfo=timezone.utc)
        end_dt = start_dt + timedelta(days=days)
        return f"{start_dt.isoformat()}__{end_dt.isoformat()}"
