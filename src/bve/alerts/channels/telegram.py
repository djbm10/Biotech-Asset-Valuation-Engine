"""
TelegramChannel — sends alerts via Telegram Bot API.

Requires: requests (already in core dependencies).
"""
from __future__ import annotations

import logging

from bve.alerts.alert_config import TelegramChannelConfig
from bve.alerts.alert_model import Alert, AlertSeverity, severity_gte

_LOG = logging.getLogger("bve.alerts.telegram")

_API_URL = "https://api.telegram.org/bot{token}/sendMessage"

_SEVERITY_EMOJI: dict[AlertSeverity, str] = {
    AlertSeverity.CRITICAL: "\U0001f6a8",  # 🚨
    AlertSeverity.HIGH:     "\u26a0\ufe0f",  # ⚠️
    AlertSeverity.MEDIUM:   "\U0001f7e1",  # 🟡
    AlertSeverity.LOW:      "\u26aa",  # ⚪
}


class TelegramChannel:
    """Posts alert messages to a Telegram chat via Bot API."""

    def __init__(self, config: TelegramChannelConfig) -> None:
        self._token = config.bot_token
        self._chat_id = config.chat_id
        self._min_severity = AlertSeverity(config.min_severity)

    @property
    def name(self) -> str:
        return "telegram"

    @property
    def min_severity(self) -> AlertSeverity:
        return self._min_severity

    def send(self, alert: Alert) -> None:
        if not severity_gte(alert.severity, self._min_severity):
            return
        emoji = _SEVERITY_EMOJI.get(alert.severity, "")
        text = f"{emoji} BVE Alert [{alert.severity.value.upper()}] {alert.asset_id}\n{alert.message}"
        self._post(text)

    def send_batch(self, alerts: list[Alert], asset_id: str) -> None:
        filtered = [a for a in alerts if severity_gte(a.severity, self._min_severity)]
        if not filtered:
            return
        top_sev = max(filtered, key=lambda a: list(AlertSeverity).index(a.severity)).severity
        emoji = _SEVERITY_EMOJI.get(top_sev, "")
        lines = [f"{emoji} BVE Alerts for {asset_id} ({len(filtered)} event(s))"]
        for a in filtered:
            e = _SEVERITY_EMOJI.get(a.severity, "")
            lines.append(f"  {e} [{a.severity.value}] {a.message}")
        self._post("\n".join(lines))

    def _post(self, text: str) -> None:
        try:
            import requests  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "TelegramChannel requires the 'requests' package"
            ) from exc
        url = _API_URL.format(token=self._token)
        resp = requests.post(
            url, json={"chat_id": self._chat_id, "text": text}, timeout=10
        )
        if not resp.ok:
            _LOG.warning("Telegram API %s: %s", resp.status_code, resp.text[:200])
