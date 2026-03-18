"""
LocalFileChannel — appends each alert as a JSON line to a local JSONL file.

Zero external dependencies. send_batch() delegates to individual send() calls
because per-line JSONL is already the correct storage format.
"""
from __future__ import annotations

import json
from pathlib import Path

from bve.alerts.alert_config import LocalChannelConfig
from bve.alerts.alert_model import Alert, AlertSeverity, severity_gte


class LocalFileChannel:
    """Appends each alert as a JSON line to *config.output_path*."""

    def __init__(self, config: LocalChannelConfig) -> None:
        self._path = Path(config.output_path)
        self._min_severity = AlertSeverity(config.min_severity)

    @property
    def name(self) -> str:
        return "local"

    @property
    def min_severity(self) -> AlertSeverity:
        return self._min_severity

    def send(self, alert: Alert) -> None:
        if not severity_gte(alert.severity, self._min_severity):
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(alert.model_dump(mode="json"), ensure_ascii=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def send_batch(self, alerts: list[Alert], asset_id: str) -> None:
        # JSONL is naturally per-record; no aggregation needed.
        for alert in alerts:
            self.send(alert)
