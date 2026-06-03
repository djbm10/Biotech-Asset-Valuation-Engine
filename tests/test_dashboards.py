"""Tests for Phase 6 dashboard panel data containers and builder."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from bve.ui.dashboard.calibration_panel import CalibrationModuleRow, CalibrationPanel
from bve.ui.dashboard.dashboard_builder import DashboardBuilder, DashboardSnapshot
from bve.ui.dashboard.event_heatmap_panel import EventHeatmapCell, EventHeatmapPanel
from bve.ui.dashboard.model_vs_market_panel import ModelVsMarketPanel, ModelVsMarketRow
from bve.ui.dashboard.recommendation_panel import RecommendationChangeRow, RecommendationPanel
from bve.ui.dashboard.thesis_status_panel import ThesisStatusPanel, ThesisStatusRow

TODAY = date(2026, 4, 18)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mvm_row(asset_id: str, ev_direction: str = "unknown", ev_gap_pct: float = 0.0) -> ModelVsMarketRow:
    return ModelVsMarketRow(
        asset_id=asset_id,
        ticker=asset_id.upper(),
        as_of=TODAY,
        ev_direction=ev_direction,
        ev_gap_pct=ev_gap_pct,
    )


def _rec_row(
    asset_id: str,
    current_action: str,
    previous_action: str | None = None,
    is_new: bool = False,
    current_score: float = 0.6,
    previous_score: float | None = None,
) -> RecommendationChangeRow:
    return RecommendationChangeRow(
        asset_id=asset_id,
        ticker=asset_id.upper(),
        change_date=TODAY,
        previous_action=previous_action,
        current_action=current_action,
        previous_score=previous_score,
        current_score=current_score,
        conviction="medium",
        headline_reason="test reason",
        is_new=is_new,
    )


def _thesis_row(asset_id: str, thesis_health: str = "healthy", triggered: int = 0) -> ThesisStatusRow:
    return ThesisStatusRow(
        asset_id=asset_id,
        ticker=asset_id.upper(),
        as_of=TODAY,
        overall_conviction="medium",
        confidence_score=0.6,
        triggered_kill_criteria=triggered,
        thesis_health=thesis_health,
    )


def _cal_row(module: str, status: str = "healthy") -> CalibrationModuleRow:
    return CalibrationModuleRow(
        module=module,
        n_resolved=10,
        mean_error=0.05,
        rmse=0.08,
        bias_direction="calibrated",
        bias_magnitude=0.1,
        status=status,
    )


def _heatmap_cell(asset_id: str, week: date, event_count: int = 1, max_materiality: float = 0.5) -> EventHeatmapCell:
    return EventHeatmapCell(
        asset_id=asset_id,
        ticker=asset_id.upper(),
        week_start=week,
        event_count=event_count,
        max_materiality=max_materiality,
    )


# ---------------------------------------------------------------------------
# 1. ModelVsMarketRow instantiation
# ---------------------------------------------------------------------------


def test_model_vs_market_row_instantiation() -> None:
    row = _mvm_row("asset_a", ev_direction="underpriced", ev_gap_pct=0.30)
    assert row.asset_id == "asset_a"
    assert row.ev_direction == "underpriced"
    assert row.ev_gap_pct == pytest.approx(0.30)
    assert isinstance(row.last_updated, datetime)


# ---------------------------------------------------------------------------
# 2. ModelVsMarketPanel.top_underpriced returns correct rows
# ---------------------------------------------------------------------------


def test_top_underpriced_returns_correct_rows() -> None:
    rows = [
        _mvm_row("a", "underpriced", 0.10),
        _mvm_row("b", "overpriced", -0.20),
        _mvm_row("c", "underpriced", 0.40),
    ]
    panel = ModelVsMarketPanel(rows=rows)
    result = panel.top_underpriced()
    assert len(result) == 2
    assert result[0].asset_id == "c"   # highest gap first
    assert result[1].asset_id == "a"


# ---------------------------------------------------------------------------
# 3. ModelVsMarketPanel.top_overpriced returns correct rows
# ---------------------------------------------------------------------------


def test_top_overpriced_returns_correct_rows() -> None:
    rows = [
        _mvm_row("a", "overpriced", -0.10),
        _mvm_row("b", "underpriced", 0.20),
        _mvm_row("c", "overpriced", -0.30),
    ]
    panel = ModelVsMarketPanel(rows=rows)
    result = panel.top_overpriced()
    assert len(result) == 2
    # sorted ascending by ev_gap_pct (most negative first)
    assert result[0].asset_id == "c"


# ---------------------------------------------------------------------------
# 4. ModelVsMarketPanel.top_underpriced with n=2 returns at most 2
# ---------------------------------------------------------------------------


def test_top_underpriced_respects_n() -> None:
    rows = [_mvm_row(f"a{i}", "underpriced", float(i) * 0.1) for i in range(6)]
    panel = ModelVsMarketPanel(rows=rows)
    assert len(panel.top_underpriced(n=2)) == 2


# ---------------------------------------------------------------------------
# 5. RecommendationChangeRow instantiation
# ---------------------------------------------------------------------------


def test_recommendation_change_row_instantiation() -> None:
    row = _rec_row("asset_b", "add", is_new=True, current_score=0.75)
    assert row.current_action == "add"
    assert row.is_new is True
    assert row.previous_action is None


# ---------------------------------------------------------------------------
# 6. RecommendationPanel.new_adds returns only new add rows
# ---------------------------------------------------------------------------


def test_new_adds_returns_only_new_adds() -> None:
    rows = [
        _rec_row("a", "add", is_new=True),
        _rec_row("b", "add", previous_action="hold", is_new=False),
        _rec_row("c", "hold", is_new=True),
    ]
    panel = RecommendationPanel(rows=rows)
    result = panel.new_adds()
    assert len(result) == 1
    assert result[0].asset_id == "a"


# ---------------------------------------------------------------------------
# 7. RecommendationPanel.upgrades returns only upgrades
# ---------------------------------------------------------------------------


def test_upgrades_returns_correct_rows() -> None:
    rows = [
        _rec_row("a", "add", previous_action="hold", is_new=False),   # upgrade
        _rec_row("b", "hold", previous_action="add", is_new=False),   # downgrade
        _rec_row("c", "add", is_new=True),                             # new — excluded
        _rec_row("d", "watchlist", previous_action="avoid", is_new=False),  # upgrade
    ]
    panel = RecommendationPanel(rows=rows)
    result = panel.upgrades()
    asset_ids = {r.asset_id for r in result}
    assert asset_ids == {"a", "d"}


# ---------------------------------------------------------------------------
# 8. RecommendationPanel.downgrades returns only downgrades
# ---------------------------------------------------------------------------


def test_downgrades_returns_correct_rows() -> None:
    rows = [
        _rec_row("a", "hold", previous_action="add", is_new=False),    # downgrade
        _rec_row("b", "add", previous_action="hold", is_new=False),    # upgrade
        _rec_row("c", "avoid", previous_action="hold", is_new=False),  # downgrade
    ]
    panel = RecommendationPanel(rows=rows)
    result = panel.downgrades()
    asset_ids = {r.asset_id for r in result}
    assert asset_ids == {"a", "c"}


# ---------------------------------------------------------------------------
# 9. ThesisStatusRow instantiation
# ---------------------------------------------------------------------------


def test_thesis_status_row_instantiation() -> None:
    row = _thesis_row("asset_c", thesis_health="watch")
    assert row.thesis_health == "watch"
    assert row.active_kill_criteria == 0
    assert row.summary == ""


# ---------------------------------------------------------------------------
# 10. ThesisStatusRow.kill_criteria_triggered property
# ---------------------------------------------------------------------------


def test_kill_criteria_triggered_property() -> None:
    not_triggered = _thesis_row("a", triggered=0)
    triggered = _thesis_row("b", triggered=2)
    assert not_triggered.kill_criteria_triggered is False
    assert triggered.kill_criteria_triggered is True


# ---------------------------------------------------------------------------
# 11. ThesisStatusPanel.at_risk returns at_risk and broken rows
# ---------------------------------------------------------------------------


def test_at_risk_includes_at_risk_and_broken() -> None:
    rows = [
        _thesis_row("a", "healthy"),
        _thesis_row("b", "at_risk"),
        _thesis_row("c", "broken"),
        _thesis_row("d", "watch"),
    ]
    panel = ThesisStatusPanel(rows=rows)
    result = panel.at_risk()
    asset_ids = {r.asset_id for r in result}
    assert asset_ids == {"b", "c"}


# ---------------------------------------------------------------------------
# 12. ThesisStatusPanel.healthy returns only healthy rows
# ---------------------------------------------------------------------------


def test_healthy_returns_only_healthy_rows() -> None:
    rows = [
        _thesis_row("a", "healthy"),
        _thesis_row("b", "at_risk"),
        _thesis_row("c", "healthy"),
    ]
    panel = ThesisStatusPanel(rows=rows)
    result = panel.healthy()
    assert all(r.thesis_health == "healthy" for r in result)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# 13. CalibrationModuleRow instantiation
# ---------------------------------------------------------------------------


def test_calibration_module_row_instantiation() -> None:
    row = _cal_row("pos_model", "degraded")
    assert row.module == "pos_model"
    assert row.status == "degraded"
    assert row.n_resolved == 10


# ---------------------------------------------------------------------------
# 14. CalibrationPanel.degraded_modules filter
# ---------------------------------------------------------------------------


def test_degraded_modules_filter() -> None:
    rows = [
        _cal_row("mod_a", "healthy"),
        _cal_row("mod_b", "degraded"),
        _cal_row("mod_c", "watch"),
        _cal_row("mod_d", "degraded"),
    ]
    panel = CalibrationPanel(rows=rows, overall_bias_score=0.3)
    result = panel.degraded_modules()
    assert {r.module for r in result} == {"mod_b", "mod_d"}


# ---------------------------------------------------------------------------
# 15. CalibrationPanel.well_calibrated_modules filter
# ---------------------------------------------------------------------------


def test_well_calibrated_modules_filter() -> None:
    rows = [
        _cal_row("mod_a", "healthy"),
        _cal_row("mod_b", "degraded"),
        _cal_row("mod_c", "healthy"),
    ]
    panel = CalibrationPanel(rows=rows, overall_bias_score=0.1)
    result = panel.well_calibrated_modules()
    assert all(r.status == "healthy" for r in result)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# 16. EventHeatmapCell instantiation
# ---------------------------------------------------------------------------


def test_event_heatmap_cell_instantiation() -> None:
    cell = _heatmap_cell("asset_x", TODAY, event_count=3, max_materiality=0.8)
    assert cell.asset_id == "asset_x"
    assert cell.event_count == 3
    assert cell.max_materiality == pytest.approx(0.8)
    assert cell.heat_level == "none"


# ---------------------------------------------------------------------------
# 17. EventHeatmapPanel.hot_cells threshold filter
# ---------------------------------------------------------------------------


def test_hot_cells_threshold_filter() -> None:
    week1 = date(2026, 4, 7)
    week2 = date(2026, 4, 14)
    cells = [
        _heatmap_cell("a", week1, max_materiality=0.9),
        _heatmap_cell("b", week1, max_materiality=0.5),
        _heatmap_cell("a", week2, max_materiality=0.7),
    ]
    panel = EventHeatmapPanel(cells=cells, asset_ids=["a", "b"], weeks=[week1, week2])
    hot = panel.hot_cells(threshold=0.7)
    assert len(hot) == 2
    mats = {c.max_materiality for c in hot}
    assert all(m >= 0.7 for m in mats)


# ---------------------------------------------------------------------------
# 18. EventHeatmapPanel.asset_event_counts aggregation
# ---------------------------------------------------------------------------


def test_asset_event_counts_aggregation() -> None:
    week1 = date(2026, 4, 7)
    week2 = date(2026, 4, 14)
    cells = [
        _heatmap_cell("a", week1, event_count=2),
        _heatmap_cell("a", week2, event_count=3),
        _heatmap_cell("b", week1, event_count=1),
    ]
    panel = EventHeatmapPanel(cells=cells, asset_ids=["a", "b"], weeks=[week1, week2])
    counts = panel.asset_event_counts()
    assert counts["a"] == 5
    assert counts["b"] == 1


# ---------------------------------------------------------------------------
# 19. DashboardBuilder.build — empty inputs → valid snapshot with zeros
# ---------------------------------------------------------------------------


def test_builder_empty_inputs_produces_valid_snapshot() -> None:
    builder = DashboardBuilder()
    snap = builder.build()
    assert isinstance(snap, DashboardSnapshot)
    assert snap.asset_count == 0
    assert snap.alert_count == 0
    assert snap.stale_asset_count == 0
    assert snap.model_vs_market.rows == []
    assert snap.recommendations.rows == []
    assert snap.thesis_status.rows == []
    assert snap.calibration.rows == []
    assert snap.event_heatmap.cells == []


# ---------------------------------------------------------------------------
# 20. DashboardBuilder.build — with full rows → correct counts
# ---------------------------------------------------------------------------


def test_builder_full_rows_correct_counts() -> None:
    mvm_rows = [_mvm_row("a"), _mvm_row("b")]
    rec_rows = [_rec_row("a", "add")]
    thesis_rows = [_thesis_row("a"), _thesis_row("b")]
    cal_rows = [_cal_row("mod_x")]
    builder = DashboardBuilder()
    snap = builder.build(
        model_vs_market_rows=mvm_rows,
        recommendation_rows=rec_rows,
        thesis_rows=thesis_rows,
        calibration_rows=cal_rows,
        alert_count=3,
        stale_asset_count=1,
    )
    assert snap.asset_count == 2
    assert snap.alert_count == 3
    assert snap.stale_asset_count == 1
    assert len(snap.model_vs_market.rows) == 2
    assert len(snap.recommendations.rows) == 1
    assert len(snap.thesis_status.rows) == 2
    assert len(snap.calibration.rows) == 1


# ---------------------------------------------------------------------------
# 21. DashboardSnapshot has all 5 panels
# ---------------------------------------------------------------------------


def test_dashboard_snapshot_has_all_five_panels() -> None:
    snap = DashboardBuilder().build()
    assert hasattr(snap, "model_vs_market")
    assert hasattr(snap, "recommendations")
    assert hasattr(snap, "thesis_status")
    assert hasattr(snap, "calibration")
    assert hasattr(snap, "event_heatmap")


# ---------------------------------------------------------------------------
# 22. DashboardSnapshot.asset_count correct
# ---------------------------------------------------------------------------


def test_dashboard_snapshot_asset_count_correct() -> None:
    # 3 distinct asset_ids in mvm rows
    mvm_rows = [_mvm_row("x"), _mvm_row("y"), _mvm_row("z")]
    snap = DashboardBuilder().build(model_vs_market_rows=mvm_rows)
    assert snap.asset_count == 3


# ---------------------------------------------------------------------------
# 23. DashboardBuilder.build — heatmap cells → correct asset_ids and weeks
# ---------------------------------------------------------------------------


def test_builder_heatmap_cells_correct_asset_ids_and_weeks() -> None:
    week1 = date(2026, 4, 7)
    week2 = date(2026, 4, 14)
    cells = [
        _heatmap_cell("asset_a", week1),
        _heatmap_cell("asset_b", week1),
        _heatmap_cell("asset_a", week2),
    ]
    snap = DashboardBuilder().build(heatmap_cells=cells)
    assert set(snap.event_heatmap.asset_ids) == {"asset_a", "asset_b"}
    assert sorted(snap.event_heatmap.weeks) == [week1, week2]


# ---------------------------------------------------------------------------
# 24. ModelVsMarketPanel.top_underpriced — empty panel → empty list
# ---------------------------------------------------------------------------


def test_top_underpriced_empty_panel_returns_empty_list() -> None:
    panel = ModelVsMarketPanel(rows=[])
    assert panel.top_underpriced() == []
