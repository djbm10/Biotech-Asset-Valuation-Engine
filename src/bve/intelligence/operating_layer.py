"""Phase O operating layer for auditability and operator views."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from bve.intelligence.knowledge_layer import AssetRegistryEntry, KnowledgeStore
from bve.ops.metrics_dashboard import MetricsDashboardSnapshot


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OperatingLayerModuleOutput(BaseModel):
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: list[str] = Field(default_factory=list)
    freshness: datetime
    explainability: str
    downstream_dependencies: list[str] = Field(default_factory=list)


class ModelRegistryEntryView(BaseModel):
    model_name: str
    version: str
    owner_module: str
    artifact_ref: Optional[str] = None
    updated_at: datetime


class ScenarioDiffValue(BaseModel):
    field: str
    previous: Optional[float] = None
    current: Optional[float] = None
    delta: Optional[float] = None


class OperatingLayerValue(BaseModel):
    model_registry: list[ModelRegistryEntryView] = Field(default_factory=list)
    dashboard_summary: dict[str, Any] = Field(default_factory=dict)
    stale_input_dashboard: list[dict[str, Any]] = Field(default_factory=list)
    alert_audit_log: list[dict[str, Any]] = Field(default_factory=list)
    provenance_viewer: Optional[dict[str, Any]] = None
    scenario_diff_viewer: list[ScenarioDiffValue] = Field(default_factory=list)
    asset_registry_summary: list[dict[str, Any]] = Field(default_factory=list)


class OperatingLayerAssessment(BaseModel):
    output: OperatingLayerModuleOutput
    plain_english_summary: str


class OperatingLayerEngine:
    """Aggregate audit and operator surfaces without requiring code inspection."""

    def build(
        self,
        *,
        store: KnowledgeStore,
        dashboard_snapshot: MetricsDashboardSnapshot,
        model_registry: Optional[list[ModelRegistryEntryView]] = None,
        provenance_record_type: Optional[str] = None,
        provenance_record_id: Optional[str] = None,
        current_scenario: Optional[dict[str, Any]] = None,
        previous_scenario: Optional[dict[str, Any]] = None,
        freshness: Optional[datetime] = None,
    ) -> OperatingLayerAssessment:
        freshness = freshness or _utcnow()
        registry = model_registry or self._default_registry(freshness)
        stale_dashboard = self._stale_input_dashboard(store)
        alert_audit = self._alert_audit_log(store)
        provenance_viewer = self._provenance_viewer(
            store=store,
            record_type=provenance_record_type,
            record_id=provenance_record_id,
        )
        scenario_diff = self._scenario_diff_viewer(previous_scenario, current_scenario)
        asset_registry = self._asset_registry_summary(store)
        dashboard_summary = {
            "as_of_date": dashboard_snapshot.as_of_date.isoformat(),
            "generated_at": dashboard_snapshot.generated_at.isoformat(),
            "top_opportunities_count": len(dashboard_snapshot.top_opportunities),
            "health_checks_failed": sum(1 for item in dashboard_snapshot.health_checks if not item.passed),
            "documents_points": len(dashboard_snapshot.documents_per_day),
            "signals_points": len(dashboard_snapshot.signals_per_day),
            "alerts_points": len(dashboard_snapshot.alerts_per_day),
        }

        value = OperatingLayerValue(
            model_registry=registry,
            dashboard_summary=dashboard_summary,
            stale_input_dashboard=stale_dashboard,
            alert_audit_log=alert_audit,
            provenance_viewer=provenance_viewer,
            scenario_diff_viewer=scenario_diff,
            asset_registry_summary=asset_registry,
        )
        output = OperatingLayerModuleOutput(
            value=value.model_dump(mode="json"),
            confidence=self._confidence(
                dashboard_snapshot=dashboard_snapshot,
                stale_dashboard=stale_dashboard,
                alert_audit=alert_audit,
                provenance_viewer=provenance_viewer,
            ),
            provenance=[
                f"dashboard:{dashboard_snapshot.as_of_date.isoformat()}",
                *(f"model_registry:{entry.model_name}:{entry.version}" for entry in registry),
                *(f"alert_audit:{row.get('audit_id')}" for row in alert_audit[:10]),
            ],
            freshness=freshness,
            explainability=(
                "Operating layer combines model registry, dashboard state, stale-input view, "
                "alert audit, provenance inspection, and scenario diffs into one reproducible "
                "operator surface."
            ),
            downstream_dependencies=[],
        )
        summary = (
            f"Operating layer built {len(registry)} registry entry view(s), "
            f"{len(alert_audit)} audit row(s), and {len(stale_dashboard)} stale-input row(s)."
        )
        return OperatingLayerAssessment(output=output, plain_english_summary=summary)

    @staticmethod
    def _default_registry(ts: datetime) -> list[ModelRegistryEntryView]:
        return [
            ModelRegistryEntryView(
                model_name="layered_probability_stack",
                version="phase-e-v1",
                owner_module="bve.models.probability_stack",
                artifact_ref="src/bve/models/probability_stack.py",
                updated_at=ts,
            ),
            ModelRegistryEntryView(
                model_name="catalyst_payoff_trees",
                version="phase-k-v1",
                owner_module="bve.intelligence.catalyst_payoff_trees",
                artifact_ref="src/bve/intelligence/catalyst_payoff_trees.py",
                updated_at=ts,
            ),
            ModelRegistryEntryView(
                model_name="portfolio_decision_engine",
                version="phase-l-v1",
                owner_module="bve.intelligence.portfolio_decision_engine",
                artifact_ref="src/bve/intelligence/portfolio_decision_engine.py",
                updated_at=ts,
            ),
        ]

    @staticmethod
    def _stale_input_dashboard(store: KnowledgeStore) -> list[dict[str, Any]]:
        rows = []
        for score in store.list_latest_data_quality(limit=1000):
            if not score.gated and "doc_freshness" not in set(score.failing_checks):
                continue
            rows.append(
                {
                    "asset_id": score.asset_id,
                    "overall_score": score.overall_score,
                    "gated": score.gated,
                    "failing_checks": list(score.failing_checks),
                    "generated_at": score.generated_at.isoformat(),
                }
            )
        return rows

    @staticmethod
    def _alert_audit_log(store: KnowledgeStore) -> list[dict[str, Any]]:
        rows = store.query_audit_log(limit=100)
        return [
            {
                "audit_id": row.get("audit_id"),
                "entity_type": row.get("entity_type"),
                "entity_id": row.get("entity_id"),
                "action": row.get("action"),
                "actor_id": row.get("actor_id"),
                "created_at": row.get("created_at"),
                "evidence_signal_id": row.get("evidence_signal_id"),
                "assumption_field": row.get("assumption_field"),
            }
            for row in rows
        ]

    @staticmethod
    def _provenance_viewer(
        *,
        store: KnowledgeStore,
        record_type: Optional[str],
        record_id: Optional[str],
    ) -> Optional[dict[str, Any]]:
        if not record_type or not record_id:
            return None
        traced = store.get_record_with_trace(record_type, record_id)
        return {
            "record_type": traced.record_type,
            "record_id": traced.record_id,
            "source_trace": traced.source_trace.model_dump(mode="json"),
            "provenance_chain": traced.provenance_chain,
        }

    @staticmethod
    def _scenario_diff_viewer(
        previous_scenario: Optional[dict[str, Any]],
        current_scenario: Optional[dict[str, Any]],
    ) -> list[ScenarioDiffValue]:
        if not previous_scenario and not current_scenario:
            return []
        keys = sorted(set((previous_scenario or {}).keys()) | set((current_scenario or {}).keys()))
        diffs: list[ScenarioDiffValue] = []
        for key in keys:
            prev_raw = (previous_scenario or {}).get(key)
            curr_raw = (current_scenario or {}).get(key)
            prev = float(prev_raw) if isinstance(prev_raw, (int, float)) else None
            curr = float(curr_raw) if isinstance(curr_raw, (int, float)) else None
            delta = None
            if prev is not None and curr is not None:
                delta = round(curr - prev, 6)
            diffs.append(ScenarioDiffValue(field=key, previous=prev, current=curr, delta=delta))
        return diffs

    @staticmethod
    def _asset_registry_summary(store: KnowledgeStore) -> list[dict[str, Any]]:
        rows: list[AssetRegistryEntry] = store.list_asset_registry()
        return [
            {
                "asset_id": row.asset_id,
                "ticker": row.ticker,
                "company_id": row.company_id,
                "therapeutic_area": row.therapeutic_area,
                "modality": row.modality,
                "stage": row.stage,
                "source": row.source,
            }
            for row in rows
        ]

    @staticmethod
    def _confidence(
        *,
        dashboard_snapshot: MetricsDashboardSnapshot,
        stale_dashboard: list[dict[str, Any]],
        alert_audit: list[dict[str, Any]],
        provenance_viewer: Optional[dict[str, Any]],
    ) -> float:
        confidence = 0.60
        failed_checks = sum(1 for item in dashboard_snapshot.health_checks if not item.passed)
        confidence -= min(0.15, failed_checks * 0.03)
        confidence -= min(0.10, len(stale_dashboard) * 0.02)
        if alert_audit:
            confidence += 0.05
        if provenance_viewer is not None:
            confidence += 0.05
        return round(max(0.40, min(0.95, confidence)), 4)
