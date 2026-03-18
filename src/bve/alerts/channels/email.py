"""
SmtpEmailChannel — sends alert emails via smtplib (stdlib, no extra dep).

send_batch() aggregates all asset alerts into one email to avoid inbox flooding.
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from bve.alerts.alert_config import EmailChannelConfig
from bve.alerts.alert_model import Alert, AlertSeverity, severity_gte

_LOG = logging.getLogger("bve.alerts.email")


class SmtpEmailChannel:
    """Sends alert emails via SMTP. Uses stdlib smtplib — no extra dependency."""

    def __init__(self, config: EmailChannelConfig) -> None:
        self._config = config
        self._min_severity = AlertSeverity(config.min_severity)

    @property
    def name(self) -> str:
        return "email"

    @property
    def min_severity(self) -> AlertSeverity:
        return self._min_severity

    def send(self, alert: Alert) -> None:
        if not severity_gte(alert.severity, self._min_severity):
            return
        cfg = self._config
        subject = (
            f"{cfg.subject_prefix} [{alert.severity.value.upper()}] {alert.asset_id}"
        )
        self._send_smtp(subject, _format_body([alert]))

    def send_batch(self, alerts: list[Alert], asset_id: str) -> None:
        filtered = [a for a in alerts if severity_gte(a.severity, self._min_severity)]
        if not filtered:
            return
        cfg = self._config
        subject = f"{cfg.subject_prefix} {len(filtered)} alert(s) for {asset_id}"
        self._send_smtp(subject, _format_body(filtered))

    def _send_smtp(self, subject: str, body: str) -> None:
        cfg = self._config
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = cfg.from_addr
        msg["To"] = ", ".join(cfg.to_addrs)
        msg.set_content(body)
        try:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=15) as smtp:
                if cfg.use_tls:
                    smtp.starttls()
                smtp.login(cfg.username, cfg.password)
                smtp.send_message(msg)
        except Exception as exc:
            _LOG.error("Failed to send email alert: %s", exc)
            raise


def _format_body(alerts: list[Alert]) -> str:
    lines: list[str] = []
    for a in alerts:
        lines.append(f"[{a.severity.value.upper()}] {a.trigger.value}")
        lines.append(f"Asset:   {a.asset_id}")
        lines.append(f"Company: {a.company_id}")
        lines.append(f"Message: {a.message}")
        if a.valuation_delta_npv is not None:
            sign = "+" if a.valuation_delta_npv >= 0 else ""
            lines.append(f"NPV delta: {sign}${a.valuation_delta_npv:.1f}M")
        if a.extraction_confidence is not None:
            lines.append(f"Confidence: {a.extraction_confidence:.2f}")
        lines.append(f"Time: {a.created_at.isoformat()}")
        lines.append("-" * 40)
    return "\n".join(lines)
