"""
Tests for P4.2 — Weekly refresh & monitoring: change detection and alerts.

Verifies:
- WeeklyMonitor.run() returns WeeklyRefreshResult
- WeeklyRefreshResult has alerts, changed_assets, n_assets_checked, run_date
- Alert has asset_id, alert_type, message, severity
- Severity is one of: "high", "medium", "low"
- alert_type is one of known types (price_move, thesis_change, catalyst_approaching,
  runway_warning, pos_shift, new_filing)
- WeeklyMonitor detects price move > threshold → alert
- WeeklyMonitor detects runway < 12 months → runway_warning alert
- WeeklyMonitor with no changes produces empty alerts
- WeeklyRefreshResult is frozen
- WeeklyRefreshResult.n_alerts property
- WeeklyRefreshResult.high_severity_alerts filters by severity
- WeeklyRefreshResult.alerts_for_asset returns alerts for one asset
- alert_summary_dict has expected keys
- MonitoredAsset stores ticker, thresholds, and asset_id
- WeeklyMonitor.run_on_snapshot accepts pre-built snapshots (no live fetch)
- Empty universe returns result with n_assets_checked=0
- WeeklyRefreshResult.run_date is a date
- Price move below threshold does NOT generate alert
- Multiple alerts for same asset are all returned
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import pytest

from bve.ops.weekly_monitor import (
    Alert,
    AlertSeverity,
    AlertType,
    AssetSnapshot,
    MonitoredAsset,
    WeeklyMonitor,
    WeeklyRefreshResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _asset(asset_id: str = "rlay-001", ticker: str = "RLAY") -> MonitoredAsset:
    return MonitoredAsset(
        asset_id=asset_id,
        ticker=ticker,
        price_move_threshold_pct=10.0,
        runway_warning_months=12,
    )


def _snapshot(
    asset_id: str = "rlay-001",
    price: float = 20.0,
    prev_price: float = 20.0,
    runway_months: Optional[float] = 24.0,
    nav_per_share: Optional[float] = 25.0,
) -> AssetSnapshot:
    return AssetSnapshot(
        asset_id=asset_id,
        current_price=price,
        prev_price=prev_price,
        runway_months=runway_months,
        nav_per_share=nav_per_share,
        catalyst_days_out=None,
    )


# ---------------------------------------------------------------------------
# Alert
# ---------------------------------------------------------------------------

class TestAlert:
    def test_has_required_fields(self):
        a = Alert(
            asset_id="rlay-001",
            alert_type=AlertType.PRICE_MOVE,
            message="Price moved 15%",
            severity=AlertSeverity.HIGH,
        )
        assert a.asset_id == "rlay-001"
        assert a.alert_type == AlertType.PRICE_MOVE
        assert len(a.message) > 0
        assert a.severity == AlertSeverity.HIGH

    def test_severity_values(self):
        assert AlertSeverity.HIGH.value == "high"
        assert AlertSeverity.MEDIUM.value == "medium"
        assert AlertSeverity.LOW.value == "low"

    def test_alert_type_values(self):
        assert AlertType.PRICE_MOVE.value == "price_move"
        assert AlertType.RUNWAY_WARNING.value == "runway_warning"
        assert AlertType.CATALYST_APPROACHING.value == "catalyst_approaching"


# ---------------------------------------------------------------------------
# MonitoredAsset
# ---------------------------------------------------------------------------

class TestMonitoredAsset:
    def test_stores_asset_id(self):
        a = _asset()
        assert a.asset_id == "rlay-001"

    def test_stores_ticker(self):
        a = _asset()
        assert a.ticker == "RLAY"

    def test_default_threshold(self):
        a = MonitoredAsset(asset_id="x")
        assert a.price_move_threshold_pct > 0

    def test_default_runway_warning(self):
        a = MonitoredAsset(asset_id="x")
        assert a.runway_warning_months > 0


# ---------------------------------------------------------------------------
# WeeklyRefreshResult
# ---------------------------------------------------------------------------

class TestWeeklyRefreshResult:
    def _make_result(self, alerts=None):
        return WeeklyRefreshResult(
            alerts=alerts or [],
            changed_assets=[],
            n_assets_checked=3,
            run_date=date.today(),
        )

    def test_n_alerts_zero(self):
        r = self._make_result()
        assert r.n_alerts == 0

    def test_n_alerts_nonzero(self):
        alert = Alert(
            asset_id="x", alert_type=AlertType.PRICE_MOVE,
            message="Big move", severity=AlertSeverity.HIGH,
        )
        r = self._make_result(alerts=[alert])
        assert r.n_alerts == 1

    def test_high_severity_alerts_filters(self):
        high = Alert(asset_id="x", alert_type=AlertType.PRICE_MOVE,
                     message="Big", severity=AlertSeverity.HIGH)
        low = Alert(asset_id="y", alert_type=AlertType.RUNWAY_WARNING,
                    message="Low", severity=AlertSeverity.LOW)
        r = self._make_result(alerts=[high, low])
        assert len(r.high_severity_alerts) == 1
        assert r.high_severity_alerts[0].severity == AlertSeverity.HIGH

    def test_alerts_for_asset(self):
        a1 = Alert(asset_id="rlay", alert_type=AlertType.PRICE_MOVE,
                   message="m1", severity=AlertSeverity.HIGH)
        a2 = Alert(asset_id="other", alert_type=AlertType.PRICE_MOVE,
                   message="m2", severity=AlertSeverity.MEDIUM)
        r = self._make_result(alerts=[a1, a2])
        assert len(r.alerts_for_asset("rlay")) == 1
        assert r.alerts_for_asset("rlay")[0].asset_id == "rlay"

    def test_run_date_is_date(self):
        r = self._make_result()
        assert isinstance(r.run_date, date)

    def test_is_frozen(self):
        r = self._make_result()
        with pytest.raises((AttributeError, TypeError)):
            r.n_assets_checked = 99  # type: ignore[misc]

    def test_summary_dict_has_keys(self):
        r = self._make_result()
        sd = r.summary_dict()
        for key in ["n_alerts", "n_assets_checked", "n_high", "run_date", "n_changed"]:
            assert key in sd


# ---------------------------------------------------------------------------
# WeeklyMonitor — run_on_snapshot
# ---------------------------------------------------------------------------

class TestRunOnSnapshot:
    def test_returns_weekly_refresh_result(self):
        monitor = WeeklyMonitor(assets=[_asset()])
        result = monitor.run_on_snapshot(
            snapshots=[_snapshot()]
        )
        assert isinstance(result, WeeklyRefreshResult)

    def test_n_assets_checked(self):
        monitor = WeeklyMonitor(assets=[_asset("a"), _asset("b")])
        result = monitor.run_on_snapshot(
            snapshots=[_snapshot("a"), _snapshot("b")]
        )
        assert result.n_assets_checked == 2

    def test_no_changes_no_alerts(self):
        monitor = WeeklyMonitor(assets=[_asset()])
        result = monitor.run_on_snapshot(
            snapshots=[_snapshot(price=20.0, prev_price=20.0)]
        )
        assert result.n_alerts == 0

    def test_large_price_drop_generates_alert(self):
        monitor = WeeklyMonitor(assets=[_asset()])
        snap = _snapshot(price=15.0, prev_price=20.0)  # -25% drop
        result = monitor.run_on_snapshot(snapshots=[snap])
        assert result.n_alerts >= 1
        assert any(a.alert_type == AlertType.PRICE_MOVE for a in result.alerts)

    def test_large_price_rise_generates_alert(self):
        monitor = WeeklyMonitor(assets=[_asset()])
        snap = _snapshot(price=25.0, prev_price=20.0)  # +25% rise
        result = monitor.run_on_snapshot(snapshots=[snap])
        assert any(a.alert_type == AlertType.PRICE_MOVE for a in result.alerts)

    def test_small_price_move_no_alert(self):
        monitor = WeeklyMonitor(assets=[_asset()])
        snap = _snapshot(price=20.5, prev_price=20.0)  # +2.5% — below 10% threshold
        result = monitor.run_on_snapshot(snapshots=[snap])
        price_alerts = [a for a in result.alerts if a.alert_type == AlertType.PRICE_MOVE]
        assert len(price_alerts) == 0

    def test_low_runway_generates_warning(self):
        monitor = WeeklyMonitor(assets=[_asset()])
        snap = _snapshot(runway_months=8.0)  # below 12-month threshold
        result = monitor.run_on_snapshot(snapshots=[snap])
        assert any(a.alert_type == AlertType.RUNWAY_WARNING for a in result.alerts)

    def test_sufficient_runway_no_warning(self):
        monitor = WeeklyMonitor(assets=[_asset()])
        snap = _snapshot(runway_months=24.0)
        result = monitor.run_on_snapshot(snapshots=[snap])
        runway_alerts = [a for a in result.alerts if a.alert_type == AlertType.RUNWAY_WARNING]
        assert len(runway_alerts) == 0

    def test_catalyst_approaching_alert(self):
        monitor = WeeklyMonitor(assets=[_asset()])
        snap = _snapshot()
        snap = AssetSnapshot(
            asset_id="rlay-001",
            current_price=20.0,
            prev_price=20.0,
            runway_months=24.0,
            nav_per_share=25.0,
            catalyst_days_out=5,  # within 7-day window
        )
        result = monitor.run_on_snapshot(snapshots=[snap])
        assert any(a.alert_type == AlertType.CATALYST_APPROACHING for a in result.alerts)

    def test_multiple_alerts_same_asset(self):
        monitor = WeeklyMonitor(assets=[_asset()])
        snap = AssetSnapshot(
            asset_id="rlay-001",
            current_price=14.0,   # -30% move
            prev_price=20.0,
            runway_months=6.0,    # low runway too
            nav_per_share=25.0,
            catalyst_days_out=None,
        )
        result = monitor.run_on_snapshot(snapshots=[snap])
        assert len(result.alerts) >= 2

    def test_empty_universe(self):
        monitor = WeeklyMonitor(assets=[])
        result = monitor.run_on_snapshot(snapshots=[])
        assert result.n_assets_checked == 0
        assert result.n_alerts == 0

    def test_price_alert_contains_asset_id(self):
        monitor = WeeklyMonitor(assets=[_asset(asset_id="rlay-001")])
        snap = _snapshot(asset_id="rlay-001", price=14.0, prev_price=20.0)
        result = monitor.run_on_snapshot(snapshots=[snap])
        price_alerts = [a for a in result.alerts if a.alert_type == AlertType.PRICE_MOVE]
        assert all(a.asset_id == "rlay-001" for a in price_alerts)

    def test_high_price_drop_is_high_severity(self):
        monitor = WeeklyMonitor(assets=[_asset()])
        snap = _snapshot(price=10.0, prev_price=20.0)  # -50%
        result = monitor.run_on_snapshot(snapshots=[snap])
        price_alerts = [a for a in result.alerts if a.alert_type == AlertType.PRICE_MOVE]
        assert any(a.severity == AlertSeverity.HIGH for a in price_alerts)
