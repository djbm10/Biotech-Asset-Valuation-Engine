"""
AlertChannel Protocol and FakeChannel test double.

Channels filter by min_severity before sending. send_batch() is used by the
router when multiple alerts fire for the same asset in one pipeline run —
aggregation-capable channels (Slack, Telegram, email) send one message instead
of N. LocalFileChannel delegates send_batch() to individual send() calls.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from bve.alerts.alert_model import Alert, AlertSeverity, severity_gte


@runtime_checkable
class AlertChannel(Protocol):
    """Structural protocol for alert delivery channels."""

    @property
    def name(self) -> str: ...

    @property
    def min_severity(self) -> AlertSeverity: ...

    def send(self, alert: Alert) -> None: ...

    def send_batch(self, alerts: list[Alert], asset_id: str) -> None: ...


class FakeChannel:
    """
    Test double — captures all alerts in memory, never raises.

    ``sent`` contains every individual alert that passed the severity filter.
    ``batches`` contains (alerts, asset_id) tuples from send_batch() calls.
    """

    def __init__(self, min_severity: AlertSeverity = AlertSeverity.LOW) -> None:
        self._min_severity = min_severity
        self.sent: list[Alert] = []
        self.batches: list[tuple[list[Alert], str]] = []

    @property
    def name(self) -> str:
        return "fake"

    @property
    def min_severity(self) -> AlertSeverity:
        return self._min_severity

    def send(self, alert: Alert) -> None:
        if severity_gte(alert.severity, self._min_severity):
            self.sent.append(alert)

    def send_batch(self, alerts: list[Alert], asset_id: str) -> None:
        filtered = [a for a in alerts if severity_gte(a.severity, self._min_severity)]
        if filtered:
            self.batches.append((filtered, asset_id))
            for a in filtered:
                if a not in self.sent:
                    self.sent.append(a)

    def reset(self) -> None:
        self.sent.clear()
        self.batches.clear()
