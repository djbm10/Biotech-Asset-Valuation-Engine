"""
Tests for individual alert channels.

- LocalFileChannel: writes valid JSONL, respects min_severity.
- SlackWebhookChannel: mocks requests.post, checks payload shape.
- SmtpEmailChannel: mocks smtplib.SMTP, checks sendmail called.
- TelegramChannel: mocks requests.post, checks API URL and chat_id.
- FakeChannel: captures alerts correctly.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bve.alerts.alert_model import Alert, AlertSeverity, AlertTrigger
from bve.alerts.channels.base import FakeChannel


def _alert(severity: AlertSeverity = AlertSeverity.MEDIUM) -> Alert:
    return Alert(
        id=str(uuid.uuid4()),
        severity=severity,
        trigger=AlertTrigger.MATERIAL_VALUATION_CHANGE,
        asset_id="asset-test",
        company_id="company-test",
        message="Test alert message",
        created_at=datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        valuation_delta_npv=42.5,
    )


class TestFakeChannel:
    def test_send_captured(self):
        ch = FakeChannel()
        a = _alert()
        ch.send(a)
        assert len(ch.sent) == 1
        assert ch.sent[0] is a

    def test_min_severity_filters(self):
        ch = FakeChannel(min_severity=AlertSeverity.HIGH)
        ch.send(_alert(AlertSeverity.LOW))
        ch.send(_alert(AlertSeverity.MEDIUM))
        ch.send(_alert(AlertSeverity.HIGH))
        ch.send(_alert(AlertSeverity.CRITICAL))
        assert len(ch.sent) == 2

    def test_send_batch_captured(self):
        ch = FakeChannel()
        alerts = [_alert(), _alert(AlertSeverity.CRITICAL)]
        ch.send_batch(alerts, "asset-test")
        assert len(ch.batches) == 1
        assert len(ch.batches[0][0]) == 2
        assert ch.batches[0][1] == "asset-test"

    def test_reset_clears_all(self):
        ch = FakeChannel()
        ch.send(_alert())
        ch.send_batch([_alert()], "a")
        ch.reset()
        assert ch.sent == []
        assert ch.batches == []


class TestLocalFileChannel:
    def test_writes_valid_jsonl(self, tmp_path: Path):
        from bve.alerts.alert_config import LocalChannelConfig
        from bve.alerts.channels.local import LocalFileChannel

        cfg = LocalChannelConfig(output_path=str(tmp_path / "alerts.jsonl"))
        ch = LocalFileChannel(cfg)
        a = _alert()
        ch.send(a)

        lines = (tmp_path / "alerts.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["asset_id"] == "asset-test"
        assert data["severity"] == "medium"

    def test_appends_multiple_alerts(self, tmp_path: Path):
        from bve.alerts.alert_config import LocalChannelConfig
        from bve.alerts.channels.local import LocalFileChannel

        cfg = LocalChannelConfig(output_path=str(tmp_path / "alerts.jsonl"))
        ch = LocalFileChannel(cfg)
        ch.send(_alert())
        ch.send(_alert(AlertSeverity.CRITICAL))

        lines = (tmp_path / "alerts.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

    def test_min_severity_filters(self, tmp_path: Path):
        from bve.alerts.alert_config import LocalChannelConfig
        from bve.alerts.channels.local import LocalFileChannel

        cfg = LocalChannelConfig(
            output_path=str(tmp_path / "alerts.jsonl"), min_severity="high"
        )
        ch = LocalFileChannel(cfg)
        ch.send(_alert(AlertSeverity.LOW))     # filtered
        ch.send(_alert(AlertSeverity.MEDIUM))  # filtered
        ch.send(_alert(AlertSeverity.HIGH))    # passes

        out = tmp_path / "alerts.jsonl"
        lines = out.read_text().strip().splitlines() if out.exists() else []
        assert len(lines) == 1

    def test_send_batch_writes_each(self, tmp_path: Path):
        from bve.alerts.alert_config import LocalChannelConfig
        from bve.alerts.channels.local import LocalFileChannel

        cfg = LocalChannelConfig(output_path=str(tmp_path / "alerts.jsonl"))
        ch = LocalFileChannel(cfg)
        ch.send_batch([_alert(), _alert(AlertSeverity.CRITICAL)], "asset-test")

        lines = (tmp_path / "alerts.jsonl").read_text().strip().splitlines()
        assert len(lines) == 2


class TestSlackWebhookChannel:
    def test_send_posts_to_webhook(self):
        from bve.alerts.alert_config import SlackChannelConfig
        from bve.alerts.channels.slack import SlackWebhookChannel

        cfg = SlackChannelConfig(webhook_url="https://hooks.slack.com/test")
        ch = SlackWebhookChannel(cfg)

        mock_resp = MagicMock()
        mock_resp.ok = True
        with patch("requests.post", return_value=mock_resp) as mock_post:
            ch.send(_alert())
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert "text" in payload
        assert "asset-test" in payload["text"]

    def test_send_batch_one_request(self):
        from bve.alerts.alert_config import SlackChannelConfig
        from bve.alerts.channels.slack import SlackWebhookChannel

        cfg = SlackChannelConfig(webhook_url="https://hooks.slack.com/test")
        ch = SlackWebhookChannel(cfg)

        mock_resp = MagicMock()
        mock_resp.ok = True
        with patch("requests.post", return_value=mock_resp) as mock_post:
            ch.send_batch([_alert(), _alert(AlertSeverity.CRITICAL)], "asset-test")
        # Should send exactly one request (aggregated)
        assert mock_post.call_count == 1

    def test_min_severity_filters(self):
        from bve.alerts.alert_config import SlackChannelConfig
        from bve.alerts.channels.slack import SlackWebhookChannel

        cfg = SlackChannelConfig(webhook_url="https://hooks.slack.com/test", min_severity="high")
        ch = SlackWebhookChannel(cfg)

        with patch("requests.post") as mock_post:
            ch.send(_alert(AlertSeverity.LOW))
            ch.send(_alert(AlertSeverity.MEDIUM))
        assert mock_post.call_count == 0


class TestSmtpEmailChannel:
    def test_send_invokes_sendmail(self):
        from bve.alerts.alert_config import EmailChannelConfig
        from bve.alerts.channels.email import SmtpEmailChannel

        cfg = EmailChannelConfig(
            smtp_host="smtp.example.com",
            username="user",
            password="pass",
            from_addr="from@example.com",
            to_addrs=["to@example.com"],
        )
        ch = SmtpEmailChannel(cfg)

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = lambda s: mock_smtp
        mock_smtp.__exit__ = MagicMock(return_value=False)
        with patch("smtplib.SMTP", return_value=mock_smtp):
            ch.send(_alert())
        mock_smtp.send_message.assert_called_once()

    def test_send_batch_one_email(self):
        from bve.alerts.alert_config import EmailChannelConfig
        from bve.alerts.channels.email import SmtpEmailChannel

        cfg = EmailChannelConfig(
            smtp_host="smtp.example.com",
            username="user",
            password="pass",
            from_addr="from@example.com",
            to_addrs=["to@example.com"],
        )
        ch = SmtpEmailChannel(cfg)

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = lambda s: mock_smtp
        mock_smtp.__exit__ = MagicMock(return_value=False)
        with patch("smtplib.SMTP", return_value=mock_smtp):
            ch.send_batch([_alert(), _alert(AlertSeverity.CRITICAL)], "asset-test")
        # One aggregated email
        assert mock_smtp.send_message.call_count == 1


class TestTelegramChannel:
    def test_send_posts_to_api(self):
        from bve.alerts.alert_config import TelegramChannelConfig
        from bve.alerts.channels.telegram import TelegramChannel

        cfg = TelegramChannelConfig(bot_token="testtoken", chat_id="-123456")
        ch = TelegramChannel(cfg)

        mock_resp = MagicMock()
        mock_resp.ok = True
        with patch("requests.post", return_value=mock_resp) as mock_post:
            ch.send(_alert())
        mock_post.assert_called_once()
        call = mock_post.call_args
        url = call.args[0] if call.args else call.kwargs.get("url", "")
        kwargs = call.kwargs
        assert "testtoken" in url
        assert kwargs.get("json", {}).get("chat_id") == "-123456"

    def test_send_batch_one_message(self):
        from bve.alerts.alert_config import TelegramChannelConfig
        from bve.alerts.channels.telegram import TelegramChannel

        cfg = TelegramChannelConfig(bot_token="testtoken", chat_id="-123456")
        ch = TelegramChannel(cfg)

        mock_resp = MagicMock()
        mock_resp.ok = True
        with patch("requests.post", return_value=mock_resp) as mock_post:
            ch.send_batch([_alert(), _alert(AlertSeverity.CRITICAL)], "asset-test")
        assert mock_post.call_count == 1
