"""Operational metrics dashboard and deterministic run-health checks."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel, Field

from bve.alerts.alert_model import AlertSeverity
from bve.intelligence.opportunity_snapshot import OpportunitySnapshotStore
from bve.ops.metrics import RunMetrics, RunMetricsStore

if TYPE_CHECKING:  # pragma: no cover
    from bve.alerts.alert_router import AlertRouter
    from bve.intelligence.knowledge_layer import KnowledgeStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DailyMetricPoint(BaseModel):
    """One daily aggregate count."""

    metric: str
    day: date
    count: int = Field(ge=0)


class TopOpportunitySummary(BaseModel):
    """Compact top-opportunity row for dashboard surfaces."""

    snapshot_date: date
    rank: int
    asset_id: Optional[str] = None
    ticker: Optional[str] = None
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    score: float
    mispricing: Optional[float] = None
    confidence: float
    event_type: Optional[str] = None
    days_since_event: Optional[int] = None
    source_mode: str = "opportunity_snapshot"
    action_policy: Optional[str] = None
    ranked_sotp_discount: Optional[float] = None
    enterprise_value_millions: Optional[float] = None
    sotp_equity_value_millions: Optional[float] = None
    modeled_asset_coverage_pct: Optional[float] = None
    balance_sheet_snapshot_date: Optional[date] = None


class RunHealthCheck(BaseModel):
    """One deterministic operational health check."""

    check_type: str
    asset_id: str
    passed: bool
    severity: str
    message: str
    threshold: str
    observed_value: Optional[float | int | str] = None
    checked_at: datetime = Field(default_factory=_utcnow)
    details: dict[str, Any] = Field(default_factory=dict)

    @property
    def dedup_key(self) -> str:
        return f"run_health:{self.asset_id}:{self.check_type}"


class RunHealthMonitorConfig(BaseModel):
    """Thresholds for operational health checks."""

    no_documents_window_hours: float = Field(default=24.0, gt=0.0)
    no_signals_window_days: int = Field(default=7, ge=1)
    connector_failure_rate_threshold: float = Field(default=0.20, ge=0.0, le=1.0)
    min_connector_runs_sampled: int = Field(default=5, ge=0)


class MetricsDashboardSnapshot(BaseModel):
    """Materialized dashboard payload for observability surfaces."""

    generated_at: datetime = Field(default_factory=_utcnow)
    as_of_date: date
    documents_per_day: list[DailyMetricPoint] = Field(default_factory=list)
    signals_per_day: list[DailyMetricPoint] = Field(default_factory=list)
    diffs_per_day: list[DailyMetricPoint] = Field(default_factory=list)
    alerts_per_day: list[DailyMetricPoint] = Field(default_factory=list)
    top_opportunities: list[TopOpportunitySummary] = Field(default_factory=list)
    top_opportunities_source_mode: str = "opportunity_snapshot"
    top_opportunities_reference_date: Optional[date] = None
    health_checks: list[RunHealthCheck] = Field(default_factory=list)


class RunHealthMonitor:
    """Evaluates pipeline liveness and connector degradation."""

    def __init__(
        self,
        knowledge_store: "KnowledgeStore",
        *,
        metrics_store: Optional[RunMetricsStore] = None,
        config: Optional[RunHealthMonitorConfig] = None,
    ) -> None:
        self.knowledge = knowledge_store
        self.metrics_store = metrics_store
        self.config = config or RunHealthMonitorConfig()

    def evaluate(
        self,
        *,
        reference_time: Optional[datetime] = None,
        latest_metrics: Optional[RunMetrics] = None,
    ) -> list[RunHealthCheck]:
        checked_at = self.knowledge._coerce_datetime(reference_time)
        checks = [
            self._check_documents(checked_at=checked_at),
            self._check_signals(checked_at=checked_at),
        ]
        checks.extend(
            self._check_connector_failure_rates(
                checked_at=checked_at,
                latest_metrics=latest_metrics,
            )
        )
        return checks

    def emit_alerts(
        self,
        *,
        router: Optional["AlertRouter"],
        run_id: str,
        reference_time: Optional[datetime] = None,
        latest_metrics: Optional[RunMetrics] = None,
    ) -> list[RunHealthCheck]:
        checks = self.evaluate(reference_time=reference_time, latest_metrics=latest_metrics)
        if router is None:
            return checks

        failed = [check for check in checks if not check.passed]
        if not failed:
            return checks

        for check in failed:
            router.enqueue_system_alert(
                key=check.dedup_key,
                message=check.message,
                detail={
                    "check_type": check.check_type,
                    "threshold": check.threshold,
                    "observed_value": check.observed_value,
                    "checked_at": check.checked_at.isoformat(),
                    **check.details,
                },
                run_id=run_id,
                severity=self._alert_severity(check),
                asset_id=check.asset_id,
                company_id="system",
            )
        router.flush_all(run_id=run_id)
        return checks

    def _check_documents(self, *, checked_at: datetime) -> RunHealthCheck:
        row = self.knowledge._conn.execute(
            "SELECT MAX(created_at) AS latest_created_at FROM raw_documents"
        ).fetchone()
        latest = row["latest_created_at"] if row is not None else None
        if latest is None:
            return RunHealthCheck(
                check_type="no_documents_ingested",
                asset_id="system:ingestion",
                passed=False,
                severity="high",
                message=(
                    "No documents ingested in the last "
                    f"{self.config.no_documents_window_hours:.0f}h."
                ),
                threshold=f"<= {self.config.no_documents_window_hours:.0f}h since last document",
                observed_value="never",
                checked_at=checked_at,
                details={"latest_created_at": None},
            )

        latest_dt = self.knowledge._coerce_datetime(latest)
        age_hours = (checked_at - latest_dt).total_seconds() / 3600.0
        passed = age_hours <= self.config.no_documents_window_hours
        return RunHealthCheck(
            check_type="no_documents_ingested",
            asset_id="system:ingestion",
            passed=passed,
            severity="info" if passed else "high",
            message=(
                "No documents ingested in the last "
                f"{self.config.no_documents_window_hours:.0f}h."
                if not passed
                else f"Documents healthy: latest ingestion {age_hours:.1f}h ago."
            ),
            threshold=f"<= {self.config.no_documents_window_hours:.0f}h since last document",
            observed_value=round(age_hours, 6),
            checked_at=checked_at,
            details={"latest_created_at": latest_dt.isoformat()},
        )

    def _check_signals(self, *, checked_at: datetime) -> RunHealthCheck:
        row = self.knowledge._conn.execute(
            "SELECT MAX(created_at) AS latest_created_at FROM structured_signals"
        ).fetchone()
        latest = row["latest_created_at"] if row is not None else None
        if latest is None:
            return RunHealthCheck(
                check_type="no_signals_created",
                asset_id="system:signals",
                passed=False,
                severity="medium",
                message=(
                    "No structured signals created in the last "
                    f"{self.config.no_signals_window_days}d."
                ),
                threshold=f"<= {self.config.no_signals_window_days}d since last signal",
                observed_value="never",
                checked_at=checked_at,
                details={"latest_created_at": None},
            )

        latest_dt = self.knowledge._coerce_datetime(latest)
        age_days = (checked_at - latest_dt).total_seconds() / 86400.0
        passed = age_days <= float(self.config.no_signals_window_days)
        return RunHealthCheck(
            check_type="no_signals_created",
            asset_id="system:signals",
            passed=passed,
            severity="info" if passed else "medium",
            message=(
                "No structured signals created in the last "
                f"{self.config.no_signals_window_days}d."
                if not passed
                else f"Signals healthy: latest signal {age_days:.1f}d ago."
            ),
            threshold=f"<= {self.config.no_signals_window_days}d since last signal",
            observed_value=round(age_days, 6),
            checked_at=checked_at,
            details={"latest_created_at": latest_dt.isoformat()},
        )

    def _check_connector_failure_rates(
        self,
        *,
        checked_at: datetime,
        latest_metrics: Optional[RunMetrics] = None,
    ) -> list[RunHealthCheck]:
        metrics = latest_metrics
        if metrics is None and self.metrics_store is not None:
            metrics = self.metrics_store.latest()
        if metrics is None:
            return []

        checks: list[RunHealthCheck] = []
        for metric in metrics.connector_health:
            if metric.n_runs_sampled < self.config.min_connector_runs_sampled:
                continue
            passed = metric.error_rate <= self.config.connector_failure_rate_threshold
            checks.append(
                RunHealthCheck(
                    check_type="connector_failure_rate",
                    asset_id=f"connector:{metric.connector}",
                    passed=passed,
                    severity="info"
                    if passed
                    else ("high" if metric.error_rate >= 0.50 else "medium"),
                    message=(
                        f"Connector health degraded: {metric.connector} "
                        f"success_rate={metric.success_rate:.2f} "
                        f"error_rate={metric.error_rate:.2f} "
                        f"over last {metric.n_runs_sampled} runs"
                        if not passed
                        else (
                            f"Connector healthy: {metric.connector} "
                            f"error_rate={metric.error_rate:.2f}"
                        )
                    ),
                    threshold=f"<= {self.config.connector_failure_rate_threshold:.2f} error_rate",
                    observed_value=round(metric.error_rate, 6),
                    checked_at=checked_at,
                    details={
                        "connector": metric.connector,
                        "success_rate": metric.success_rate,
                        "error_rate": metric.error_rate,
                        "avg_latency_ms": metric.avg_latency_ms,
                        "n_runs_sampled": metric.n_runs_sampled,
                        "last_failure_at": (
                            metric.last_failure_at.isoformat()
                            if metric.last_failure_at is not None
                            else None
                        ),
                        "last_success_at": (
                            metric.last_success_at.isoformat()
                            if metric.last_success_at is not None
                            else None
                        ),
                    },
                )
            )
        return checks

    @staticmethod
    def _alert_severity(check: RunHealthCheck) -> AlertSeverity:
        severity = check.severity.lower().strip()
        if severity == "high":
            return AlertSeverity.HIGH
        if severity == "medium":
            return AlertSeverity.MEDIUM
        if severity == "critical":
            return AlertSeverity.CRITICAL
        return AlertSeverity.LOW


class MetricsDashboard:
    """Builds compact observability snapshots from stored data."""

    def __init__(
        self,
        knowledge_store: "KnowledgeStore",
        *,
        metrics_store: Optional[RunMetricsStore] = None,
        snapshot_store: Optional[OpportunitySnapshotStore] = None,
        health_monitor: Optional[RunHealthMonitor] = None,
    ) -> None:
        self.knowledge = knowledge_store
        self.metrics_store = metrics_store
        self.snapshot_store = snapshot_store or OpportunitySnapshotStore(knowledge_store)
        self.health_monitor = health_monitor or RunHealthMonitor(
            knowledge_store,
            metrics_store=metrics_store,
        )

    def build(
        self,
        *,
        days: int = 14,
        top_n: int = 10,
        as_of: Optional[date] = None,
        reference_time: Optional[datetime] = None,
        latest_metrics: Optional[RunMetrics] = None,
    ) -> MetricsDashboardSnapshot:
        as_of_date = as_of or (reference_time.date() if reference_time is not None else _utcnow().date())
        checked_at = self.knowledge._coerce_datetime(reference_time)
        top_source_mode, top_reference_date, top_rows = self._top_opportunities(
            as_of=as_of_date,
            top_n=top_n,
        )
        return MetricsDashboardSnapshot(
            generated_at=checked_at,
            as_of_date=as_of_date,
            documents_per_day=self._daily_counts(
                metric="documents",
                table="raw_documents",
                timestamp_column="created_at",
                days=days,
                as_of=as_of_date,
            ),
            signals_per_day=self._daily_counts(
                metric="signals",
                table="structured_signals",
                timestamp_column="created_at",
                days=days,
                as_of=as_of_date,
            ),
            diffs_per_day=self._daily_counts(
                metric="diffs",
                table="valuation_diffs",
                timestamp_column="created_at",
                days=days,
                as_of=as_of_date,
            ),
            alerts_per_day=self._daily_counts(
                metric="alerts",
                table="opportunity_alerts",
                timestamp_column="created_at",
                days=days,
                as_of=as_of_date,
            ),
            top_opportunities=top_rows,
            top_opportunities_source_mode=top_source_mode,
            top_opportunities_reference_date=top_reference_date,
            health_checks=self.health_monitor.evaluate(
                reference_time=checked_at,
                latest_metrics=latest_metrics,
            ),
        )

    def _daily_counts(
        self,
        *,
        metric: str,
        table: str,
        timestamp_column: str,
        days: int,
        as_of: date,
    ) -> list[DailyMetricPoint]:
        n_days = max(1, int(days))
        start = as_of - timedelta(days=n_days - 1)
        rows = self.knowledge._conn.execute(
            f"""
            SELECT DATE({timestamp_column}) AS day, COUNT(*) AS n_rows
            FROM {table}
            WHERE DATE({timestamp_column}) >= DATE(?)
              AND DATE({timestamp_column}) <= DATE(?)
            GROUP BY DATE({timestamp_column})
            """,
            (start.isoformat(), as_of.isoformat()),
        ).fetchall()
        counts = {
            date.fromisoformat(str(row["day"])): int(row["n_rows"] or 0)
            for row in rows
            if row["day"] is not None
        }
        return [
            DailyMetricPoint(
                metric=metric,
                day=start + timedelta(days=offset),
                count=counts.get(start + timedelta(days=offset), 0),
            )
            for offset in range(n_days)
        ]

    def _top_opportunities(
        self,
        *,
        as_of: date,
        top_n: int,
    ) -> tuple[str, Optional[date], list[TopOpportunitySummary]]:
        company_snapshot_date, company_rows = self.knowledge.get_company_sotp_snapshots_on_or_before(
            as_of,
            limit=max(50, int(top_n) * 5),
        )
        if company_snapshot_date is not None and company_rows:
            filtered = [
                row
                for row in company_rows
                if bool(row.get("balance_sheet_passes_recency_gate", False))
                and str(row.get("action_policy") or "") in {"buy", "watch"}
            ]
            filtered.sort(
                key=lambda row: (
                    -float(row.get("ranked_sotp_discount") or 0.0),
                    str(row.get("ticker") or ""),
                )
            )
            return (
                "company_sotp_snapshot",
                company_snapshot_date,
                [
                    TopOpportunitySummary(
                        snapshot_date=row["snapshot_date"],
                        rank=idx,
                        asset_id=(row.get("modeled_asset_ids") or [None])[0],
                        ticker=row.get("ticker"),
                        company_id=row.get("company_id"),
                        company_name=row.get("company_name"),
                        score=float(row.get("ranked_sotp_discount") or 0.0),
                        mispricing=(
                            round(float(row["ranked_sotp_discount"]) - 1.0, 6)
                            if row.get("ranked_sotp_discount") is not None
                            else None
                        ),
                        confidence=float(row.get("modeled_asset_confidence_min") or 0.0),
                        source_mode="company_sotp_snapshot",
                        action_policy=row.get("action_policy"),
                        ranked_sotp_discount=(
                            float(row["ranked_sotp_discount"])
                            if row.get("ranked_sotp_discount") is not None
                            else None
                        ),
                        enterprise_value_millions=(
                            float(row["enterprise_value_millions"])
                            if row.get("enterprise_value_millions") is not None
                            else None
                        ),
                        sotp_equity_value_millions=(
                            float(row["sotp_equity_value_millions"])
                            if row.get("sotp_equity_value_millions") is not None
                            else None
                        ),
                        modeled_asset_coverage_pct=(
                            float(row["modeled_asset_coverage_pct"])
                            if row.get("modeled_asset_coverage_pct") is not None
                            else None
                        ),
                        balance_sheet_snapshot_date=row.get("balance_sheet_snapshot_date"),
                    )
                    for idx, row in enumerate(filtered[: max(1, int(top_n))], start=1)
                ],
            )

        snapshot_date = self.snapshot_store.latest_snapshot_date_on_or_before(as_of)
        if snapshot_date is None:
            return "opportunity_snapshot", None, []
        rows = self.snapshot_store.get_snapshots(
            snapshot_date=snapshot_date,
            top_n=max(1, int(top_n)),
            limit=max(1, int(top_n)),
        )
        return (
            "opportunity_snapshot",
            snapshot_date,
            [
                TopOpportunitySummary(
                    snapshot_date=row.snapshot_date,
                    rank=row.rank,
                    asset_id=row.asset_id,
                    score=row.score,
                    mispricing=row.mispricing,
                    confidence=row.confidence,
                    event_type=row.event_type,
                    days_since_event=self._days_since_event(asset_id=row.asset_id, as_of=snapshot_date),
                    source_mode="opportunity_snapshot",
                )
                for row in rows
            ],
        )

    def _days_since_event(self, *, asset_id: str, as_of: date) -> Optional[int]:
        rows = self.knowledge.get_structured_signals(asset_id=asset_id, limit=1)
        if not rows:
            return None
        raw = rows[0].payload_json.get("signal_date")
        if raw is None:
            return None
        try:
            signal_date = date.fromisoformat(str(raw))
        except ValueError:
            return None
        return max(0, (as_of - signal_date).days)
