"""
SlackWebhookChannel — posts to a Slack incoming webhook.

Requires: requests (already in core dependencies).
Batching: send_batch() sends one aggregated message per asset run instead of N.
"""
from __future__ import annotations

import logging

from bve.alerts.alert_config import SlackChannelConfig
from bve.alerts.alert_model import Alert, AlertSeverity, severity_gte

_LOG = logging.getLogger("bve.alerts.slack")

_SEVERITY_EMOJI: dict[AlertSeverity, str] = {
    AlertSeverity.CRITICAL: ":rotating_light:",
    AlertSeverity.HIGH:     ":warning:",
    AlertSeverity.MEDIUM:   ":large_yellow_circle:",
    AlertSeverity.LOW:      ":white_circle:",
}


class SlackWebhookChannel:
    """Posts alert messages to a Slack incoming webhook URL."""

    def __init__(self, config: SlackChannelConfig) -> None:
        self._url = config.webhook_url
        self._min_severity = AlertSeverity(config.min_severity)

    @property
    def name(self) -> str:
        return "slack"

    @property
    def min_severity(self) -> AlertSeverity:
        return self._min_severity

    def send(self, alert: Alert) -> None:
        if not severity_gte(alert.severity, self._min_severity):
            return
        self._post(_format_single(alert))

    def send_batch(self, alerts: list[Alert], asset_id: str) -> None:
        filtered = [a for a in alerts if severity_gte(a.severity, self._min_severity)]
        if not filtered:
            return
        self._post(_format_batch(filtered, asset_id))

    def _post(self, payload: dict) -> None:
        try:
            import requests  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "SlackWebhookChannel requires the 'requests' package"
            ) from exc
        resp = requests.post(self._url, json=payload, timeout=10)
        if not resp.ok:
            _LOG.warning("Slack webhook %s: %s", resp.status_code, resp.text[:200])


def _top_severity(alerts: list[Alert]) -> AlertSeverity:
    order = list(AlertSeverity)
    return max(alerts, key=lambda a: order.index(a.severity)).severity


def _format_single(alert: Alert) -> dict:
    emoji = _SEVERITY_EMOJI.get(alert.severity, "")
    text = (
        f"{emoji} *BVE Alert* [`{alert.severity.value.upper()}`] `{alert.asset_id}`\n"
        f"{alert.message}"
    )
    if alert.valuation_delta_npv is not None:
        sign = "+" if alert.valuation_delta_npv >= 0 else ""
        text += f"\n> NPV delta: {sign}${alert.valuation_delta_npv:.1f}M"
    return {"text": text}


def _format_batch(alerts: list[Alert], asset_id: str) -> dict:
    top = _top_severity(alerts)
    emoji = _SEVERITY_EMOJI.get(top, "")
    lines = [
        f"{emoji} *BVE Alerts* for `{asset_id}` — {len(alerts)} event(s) this cycle"
    ]
    for a in alerts:
        sev_emoji = _SEVERITY_EMOJI.get(a.severity, "")
        lines.append(f"  {sev_emoji} [{a.severity.value}] {a.message}")
    return {"text": "\n".join(lines)}
