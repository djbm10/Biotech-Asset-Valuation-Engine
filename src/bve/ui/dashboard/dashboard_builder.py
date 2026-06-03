"""Assemble all dashboard panels from available data sources."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from bve.ui.dashboard.model_vs_market_panel import ModelVsMarketPanel, ModelVsMarketRow
from bve.ui.dashboard.recommendation_panel import RecommendationChangeRow, RecommendationPanel
from bve.ui.dashboard.thesis_status_panel import ThesisStatusPanel, ThesisStatusRow
from bve.ui.dashboard.calibration_panel import CalibrationModuleRow, CalibrationPanel
from bve.ui.dashboard.event_heatmap_panel import EventHeatmapCell, EventHeatmapPanel


class DashboardSnapshot(BaseModel):
    built_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_vs_market: ModelVsMarketPanel
    recommendations: RecommendationPanel
    thesis_status: ThesisStatusPanel
    calibration: CalibrationPanel
    event_heatmap: EventHeatmapPanel
    asset_count: int
    alert_count: int = 0
    stale_asset_count: int = 0


class DashboardBuilder:
    """
    Assemble a DashboardSnapshot from pre-computed panel data.

    All panel inputs are optional — the builder creates empty panels when sources are absent.
    This keeps the build path always runnable even when only partial data exists.
    """

    def build(
        self,
        *,
        model_vs_market_rows: Optional[list[ModelVsMarketRow]] = None,
        recommendation_rows: Optional[list[RecommendationChangeRow]] = None,
        thesis_rows: Optional[list[ThesisStatusRow]] = None,
        calibration_rows: Optional[list[CalibrationModuleRow]] = None,
        calibration_bias_score: float = 0.0,
        calibration_recommendations: Optional[list[str]] = None,
        heatmap_cells: Optional[list[EventHeatmapCell]] = None,
        alert_count: int = 0,
        stale_asset_count: int = 0,
    ) -> DashboardSnapshot:
        mvm = ModelVsMarketPanel(rows=model_vs_market_rows or [])
        rec = RecommendationPanel(rows=recommendation_rows or [])
        thesis = ThesisStatusPanel(rows=thesis_rows or [])
        cal = CalibrationPanel(
            rows=calibration_rows or [],
            overall_bias_score=calibration_bias_score,
            recommendations=calibration_recommendations or [],
        )
        heatmap_asset_ids = list({c.asset_id for c in (heatmap_cells or [])})
        heatmap_weeks = sorted({c.week_start for c in (heatmap_cells or [])})
        heatmap = EventHeatmapPanel(
            cells=heatmap_cells or [],
            asset_ids=heatmap_asset_ids,
            weeks=heatmap_weeks,
        )
        asset_ids = list({r.asset_id for r in (model_vs_market_rows or [])})
        return DashboardSnapshot(
            model_vs_market=mvm,
            recommendations=rec,
            thesis_status=thesis,
            calibration=cal,
            event_heatmap=heatmap,
            asset_count=len(asset_ids),
            alert_count=alert_count,
            stale_asset_count=stale_asset_count,
        )
