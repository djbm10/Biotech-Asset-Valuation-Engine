"""
Emits alerts when metric thresholds are crossed.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class AlertSeverity(str, Enum):
    CRITICAL = "critical"    # immediate action required
    HIGH = "high"            # same-day review
    MEDIUM = "medium"        # review in next cycle
    LOW = "low"              # informational


class AlertChannel(str, Enum):
    LOG = "log"              # always available
    SLACK = "slack"          # optional
    EMAIL = "email"          # optional


@dataclass(frozen=True)
class AlertRule:
    rule_id: str
    name: str
    metric: str              # e.g. "pos_delta", "financing_distress_tier", "kill_criterion"
    threshold: float         # numeric threshold value
    operator: str            # "gt", "lt", "gte", "lte", "eq"
    severity: AlertSeverity
    channels: list[AlertChannel]


@dataclass(frozen=True)
class Alert:
    alert_id: str            # UUID
    rule_id: str
    asset_id: str
    metric: str
    observed_value: float
    threshold: float
    severity: AlertSeverity
    message: str
    fired_at: datetime


def check_operator(observed: float, operator: str, threshold: float) -> bool:
    """Evaluate: 'gt', 'lt', 'gte', 'lte', 'eq'"""
    if operator == "gt":
        return observed > threshold
    elif operator == "lt":
        return observed < threshold
    elif operator == "gte":
        return observed >= threshold
    elif operator == "lte":
        return observed <= threshold
    elif operator == "eq":
        return observed == threshold
    else:
        raise ValueError(f"Unknown operator: {operator!r}")


class AlertDispatcher:
    """
    Evaluates metric readings against registered rules and fires alerts.
    Deduplicates: same (rule_id, asset_id) within cooldown_minutes doesn't re-fire.
    """

    def __init__(self, cooldown_minutes: int = 60) -> None:
        self._cooldown_minutes = cooldown_minutes
        self._rules: dict[str, AlertRule] = {}         # rule_id -> rule
        self._alerts: list[Alert] = []
        # Tracks last fire time for (rule_id, asset_id) pairs
        self._last_fired: dict[tuple[str, str], datetime] = {}

    def register_rule(self, rule: AlertRule) -> None:
        """Register an alert rule."""
        self._rules[rule.rule_id] = rule

    def evaluate(
        self,
        asset_id: str,
        metrics: dict[str, float],   # metric_name -> current value
    ) -> list[Alert]:
        """
        For each registered rule:
        - Check if metrics[rule.metric] satisfies rule.operator vs rule.threshold
        - Skip if (rule_id, asset_id) fired within cooldown_minutes
        - Create Alert, store, return
        """
        now = datetime.now(timezone.utc)
        fired: list[Alert] = []

        for rule in self._rules.values():
            # Skip if metric not in provided metrics
            if rule.metric not in metrics:
                continue

            observed = metrics[rule.metric]

            # Check threshold condition
            if not check_operator(observed, rule.operator, rule.threshold):
                continue

            # Check cooldown
            pair = (rule.rule_id, asset_id)
            last = self._last_fired.get(pair)
            if last is not None:
                elapsed_minutes = (now - last).total_seconds() / 60.0
                if elapsed_minutes < self._cooldown_minutes:
                    continue

            # Fire alert
            message = (
                f"Rule '{rule.name}': {rule.metric}={observed} "
                f"{rule.operator} {rule.threshold} for asset {asset_id}"
            )
            alert = Alert(
                alert_id=str(uuid.uuid4()),
                rule_id=rule.rule_id,
                asset_id=asset_id,
                metric=rule.metric,
                observed_value=observed,
                threshold=rule.threshold,
                severity=rule.severity,
                message=message,
                fired_at=now,
            )
            self._alerts.append(alert)
            self._last_fired[pair] = now
            fired.append(alert)

        return fired

    def fired_alerts(
        self,
        asset_id: str | None = None,
        severity: AlertSeverity | None = None,
    ) -> list[Alert]:
        """Return fired alerts, optionally filtered by asset_id and/or severity."""
        results = list(self._alerts)
        if asset_id is not None:
            results = [a for a in results if a.asset_id == asset_id]
        if severity is not None:
            results = [a for a in results if a.severity == severity]
        return results

    def alert_count(self) -> int:
        """Total number of fired alerts."""
        return len(self._alerts)

    def clear_alerts(self) -> None:
        """Empty the alert store."""
        self._alerts.clear()
        self._last_fired.clear()
