"""
P4.2 — Weekly refresh & monitoring: change detection and alert generation.

WeeklyMonitor runs a weekly scan across a monitored asset universe, comparing
current snapshots against prior-period values to detect material changes. It
generates structured Alert objects for analyst review.

Alert types
-----------
PRICE_MOVE        — price moved more than the configured threshold
RUNWAY_WARNING    — cash runway fell below the warning threshold
CATALYST_APPROACHING — a catalyst event is within N days
POS_SHIFT         — model P(approval) changed materially (external update)
THESIS_CHANGE     — thesis claim resolved or new claim added
NEW_FILING        — new SEC/FDA filing detected

Severity rules
--------------
HIGH   — price move > 25%, runway < 6 months, catalyst < 3 days
MEDIUM — price move 10–25%, runway 6–12 months, catalyst 3–7 days
LOW    — minor changes, informational

Integration with the existing weekly runner
-------------------------------------------
WeeklyMonitor.run_on_snapshot() is the pure analytics path — it accepts
pre-built AssetSnapshot objects and requires no live data fetch. This keeps
the monitor testable and allows the weekly runner to pass snapshots built
from its existing KnowledgeStore, preserving all manual data flows.

Usage
-----
>>> from bve.ops.weekly_monitor import WeeklyMonitor, MonitoredAsset, AssetSnapshot
>>> monitor = WeeklyMonitor(assets=[
...     MonitoredAsset(asset_id="rlay-001", ticker="RLAY"),
... ])
>>> result = monitor.run_on_snapshot(snapshots=[
...     AssetSnapshot(asset_id="rlay-001", current_price=15.0, prev_price=20.0,
...                   runway_months=24.0, nav_per_share=25.0, catalyst_days_out=None),
... ])
>>> result.n_alerts
1
>>> result.alerts[0].alert_type
<AlertType.PRICE_MOVE: 'price_move'>
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AlertSeverity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AlertType(str, Enum):
    PRICE_MOVE = "price_move"
    RUNWAY_WARNING = "runway_warning"
    CATALYST_APPROACHING = "catalyst_approaching"
    POS_SHIFT = "pos_shift"
    THESIS_CHANGE = "thesis_change"
    NEW_FILING = "new_filing"


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Alert:
    """A single monitoring alert for one asset."""
    asset_id: str
    alert_type: AlertType
    message: str
    severity: AlertSeverity
    detail: Optional[str] = None


@dataclass(frozen=True)
class MonitoredAsset:
    """
    Configuration for monitoring a single asset.

    Parameters
    ----------
    asset_id : str
        Canonical asset identifier.
    ticker : Optional[str]
        Equity ticker for price monitoring.
    price_move_threshold_pct : float
        Absolute % price move to trigger an alert. Default 10%.
    runway_warning_months : float
        Cash runway threshold (months) below which a warning is raised. Default 12.
    catalyst_alert_days : int
        Days-to-catalyst threshold for a CATALYST_APPROACHING alert. Default 7.
    """
    asset_id: str
    ticker: Optional[str] = None
    price_move_threshold_pct: float = 10.0
    runway_warning_months: float = 12.0
    catalyst_alert_days: int = 7


@dataclass(frozen=True)
class AssetSnapshot:
    """
    Point-in-time snapshot of key asset monitoring metrics.

    Typically built from KnowledgeStore data or live market feeds.
    """
    asset_id: str
    current_price: Optional[float]
    prev_price: Optional[float]
    runway_months: Optional[float]
    nav_per_share: Optional[float]
    catalyst_days_out: Optional[int]
    model_pos: Optional[float] = None
    prev_model_pos: Optional[float] = None


@dataclass(frozen=True)
class WeeklyRefreshResult:
    """
    Result of a weekly monitoring run.

    Attributes
    ----------
    alerts : list[Alert]
        All generated alerts, across all assets.
    changed_assets : list[str]
        Asset IDs with at least one alert.
    n_assets_checked : int
        Number of assets evaluated.
    run_date : date
        The date the monitor ran.
    """
    alerts: list[Alert]
    changed_assets: list[str]
    n_assets_checked: int
    run_date: date

    @property
    def n_alerts(self) -> int:
        return len(self.alerts)

    @property
    def high_severity_alerts(self) -> list[Alert]:
        return [a for a in self.alerts if a.severity == AlertSeverity.HIGH]

    def alerts_for_asset(self, asset_id: str) -> list[Alert]:
        return [a for a in self.alerts if a.asset_id == asset_id]

    def summary_dict(self) -> dict:
        return {
            "n_alerts": self.n_alerts,
            "n_assets_checked": self.n_assets_checked,
            "n_changed": len(self.changed_assets),
            "n_high": len(self.high_severity_alerts),
            "n_medium": sum(1 for a in self.alerts if a.severity == AlertSeverity.MEDIUM),
            "n_low": sum(1 for a in self.alerts if a.severity == AlertSeverity.LOW),
            "run_date": self.run_date.isoformat(),
            "changed_assets": self.changed_assets,
        }


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------

class WeeklyMonitor:
    """
    Weekly change-detection and alert engine.

    Parameters
    ----------
    assets : list[MonitoredAsset]
        Configured asset universe to monitor.
    """

    def __init__(self, assets: Optional[list[MonitoredAsset]] = None) -> None:
        self._assets = assets or []
        self._asset_map = {a.asset_id: a for a in self._assets}

    def run_on_snapshot(
        self,
        snapshots: list[AssetSnapshot],
        run_date: Optional[date] = None,
    ) -> WeeklyRefreshResult:
        """
        Evaluate snapshots against configured thresholds and generate alerts.

        Parameters
        ----------
        snapshots : list[AssetSnapshot]
            Pre-built snapshots; one per asset to evaluate.
        run_date : Optional[date]
            Override the run date (default: today).

        Returns
        -------
        WeeklyRefreshResult
        """
        today = run_date or date.today()
        all_alerts: list[Alert] = []

        for snap in snapshots:
            cfg = self._asset_map.get(snap.asset_id) or MonitoredAsset(
                asset_id=snap.asset_id
            )
            alerts = self._check_snapshot(snap, cfg)
            all_alerts.extend(alerts)

        changed = list({a.asset_id for a in all_alerts})

        return WeeklyRefreshResult(
            alerts=all_alerts,
            changed_assets=changed,
            n_assets_checked=len(snapshots),
            run_date=today,
        )

    # ------------------------------------------------------------------ #
    # Per-asset checks                                                     #
    # ------------------------------------------------------------------ #

    def _check_snapshot(
        self, snap: AssetSnapshot, cfg: MonitoredAsset
    ) -> list[Alert]:
        alerts: list[Alert] = []
        alerts.extend(self._check_price_move(snap, cfg))
        alerts.extend(self._check_runway(snap, cfg))
        alerts.extend(self._check_catalyst(snap, cfg))
        alerts.extend(self._check_pos_shift(snap, cfg))
        return alerts

    def _check_price_move(
        self, snap: AssetSnapshot, cfg: MonitoredAsset
    ) -> list[Alert]:
        if snap.current_price is None or snap.prev_price is None or snap.prev_price == 0:
            return []
        pct_change = (snap.current_price - snap.prev_price) / snap.prev_price * 100
        if abs(pct_change) < cfg.price_move_threshold_pct:
            return []

        direction = "rose" if pct_change > 0 else "fell"
        if abs(pct_change) >= 25:
            severity = AlertSeverity.HIGH
        elif abs(pct_change) >= 15:
            severity = AlertSeverity.MEDIUM
        else:
            severity = AlertSeverity.LOW

        return [Alert(
            asset_id=snap.asset_id,
            alert_type=AlertType.PRICE_MOVE,
            message=(
                f"{snap.asset_id}: price {direction} {abs(pct_change):.1f}% "
                f"(${snap.prev_price:.2f} → ${snap.current_price:.2f})"
            ),
            severity=severity,
            detail=f"Threshold: {cfg.price_move_threshold_pct:.0f}%",
        )]

    def _check_runway(
        self, snap: AssetSnapshot, cfg: MonitoredAsset
    ) -> list[Alert]:
        if snap.runway_months is None or snap.runway_months >= cfg.runway_warning_months:
            return []
        if snap.runway_months < 6:
            severity = AlertSeverity.HIGH
        elif snap.runway_months < 9:
            severity = AlertSeverity.MEDIUM
        else:
            severity = AlertSeverity.LOW

        return [Alert(
            asset_id=snap.asset_id,
            alert_type=AlertType.RUNWAY_WARNING,
            message=(
                f"{snap.asset_id}: cash runway {snap.runway_months:.1f} months "
                f"(below {cfg.runway_warning_months:.0f}-month threshold)"
            ),
            severity=severity,
        )]

    def _check_catalyst(
        self, snap: AssetSnapshot, cfg: MonitoredAsset
    ) -> list[Alert]:
        if snap.catalyst_days_out is None or snap.catalyst_days_out > cfg.catalyst_alert_days:
            return []
        if snap.catalyst_days_out <= 3:
            severity = AlertSeverity.HIGH
        else:
            severity = AlertSeverity.MEDIUM

        return [Alert(
            asset_id=snap.asset_id,
            alert_type=AlertType.CATALYST_APPROACHING,
            message=(
                f"{snap.asset_id}: catalyst in {snap.catalyst_days_out} day(s)"
            ),
            severity=severity,
        )]

    def _check_pos_shift(
        self, snap: AssetSnapshot, cfg: MonitoredAsset
    ) -> list[Alert]:
        if snap.model_pos is None or snap.prev_model_pos is None:
            return []
        shift_pp = (snap.model_pos - snap.prev_model_pos) * 100
        if abs(shift_pp) < 5:
            return []
        direction = "increased" if shift_pp > 0 else "decreased"
        return [Alert(
            asset_id=snap.asset_id,
            alert_type=AlertType.POS_SHIFT,
            message=(
                f"{snap.asset_id}: model P(approval) {direction} "
                f"{abs(shift_pp):.1f}pp"
            ),
            severity=AlertSeverity.MEDIUM,
        )]
