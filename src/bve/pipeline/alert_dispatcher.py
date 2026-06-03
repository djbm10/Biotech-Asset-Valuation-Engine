"""Dispatch material alerts when monitoring detects significant state changes."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class MonitoringAlertPayload(BaseModel):
    alert_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str
    ticker: str
    alert_type: str  # "thesis_broken" / "upside_gap_opened" / "financing_risk_increased" / "competitor_threat" / "confidence_drop" / "job_degraded"
    severity: str  # "critical" / "high" / "medium" / "low"
    headline: str
    detail: str
    source_event_id: Optional[str] = None
    triggered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DispatchResult(BaseModel):
    alert: MonitoringAlertPayload
    dispatched: bool
    channel: str  # "log" / "file" / "slack" (future)
    dispatched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error: Optional[str] = None


class AlertDispatcher:
    """Dispatch alerts via configured channels. Default channel: log."""

    def __init__(self, channel: str = "log", output_dir: Optional[str] = None) -> None:
        self._channel = channel
        self._output_dir = output_dir
        self._dispatched: list[DispatchResult] = []

    def dispatch(self, alert: MonitoringAlertPayload) -> DispatchResult:
        """
        Dispatch to channel:
        - "log": write to Python logging (INFO level)
        - "file": append JSON line to output_dir/alerts.jsonl
        - other: log warning, mark dispatched=False
        """
        result: DispatchResult

        if self._channel == "log":
            logger.info(
                "[ALERT][%s][%s] %s — %s",
                alert.severity.upper(),
                alert.ticker,
                alert.headline,
                alert.detail,
            )
            result = DispatchResult(
                alert=alert,
                dispatched=True,
                channel="log",
            )

        elif self._channel == "file":
            if not self._output_dir:
                result = DispatchResult(
                    alert=alert,
                    dispatched=False,
                    channel="file",
                    error="output_dir not set for file channel",
                )
            else:
                try:
                    output_path = Path(self._output_dir)
                    output_path.mkdir(parents=True, exist_ok=True)
                    alerts_file = output_path / "alerts.jsonl"
                    line = alert.model_dump_json() + "\n"
                    with alerts_file.open("a", encoding="utf-8") as fh:
                        fh.write(line)
                    result = DispatchResult(
                        alert=alert,
                        dispatched=True,
                        channel="file",
                    )
                except Exception as exc:
                    result = DispatchResult(
                        alert=alert,
                        dispatched=False,
                        channel="file",
                        error=str(exc),
                    )

        else:
            logger.warning(
                "AlertDispatcher: unknown channel %r — alert not dispatched (alert_id=%s)",
                self._channel,
                alert.alert_id,
            )
            result = DispatchResult(
                alert=alert,
                dispatched=False,
                channel=self._channel,
                error=f"unknown channel: {self._channel!r}",
            )

        self._dispatched.append(result)
        return result

    def dispatch_batch(self, alerts: list[MonitoringAlertPayload]) -> list[DispatchResult]:
        return [self.dispatch(a) for a in alerts]

    def dispatched_alerts(self) -> list[DispatchResult]:
        return list(self._dispatched)
