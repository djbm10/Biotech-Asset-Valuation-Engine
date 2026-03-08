"""
CLI entry point: bve-alert-test

Sends a synthetic test alert to all configured channels in the watchlist config.
Useful for verifying Slack/Telegram/email delivery before going live.

Usage
-----
    bve-alert-test --watchlist examples/configs/watchlist.yaml
    bve-alert-test --watchlist watchlist.yaml --severity critical
"""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone

from bve.alerts.alert_model import Alert, AlertSeverity, AlertTrigger
from bve.alerts.alert_router import AlertRouter, _build_channels
from bve.pipeline.watchlist_runner import load_watchlist_config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send a test alert to all configured channels"
    )
    parser.add_argument("--watchlist", required=True, help="Path to watchlist YAML")
    parser.add_argument(
        "--severity",
        choices=["low", "medium", "high", "critical"],
        default="medium",
        help="Severity of the test alert (default: medium)",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    config = load_watchlist_config(args.watchlist)

    if config.alerts is None or not config.alerts.enabled:
        print("No alerts config found or alerting is disabled.", file=sys.stderr)
        sys.exit(1)

    channels = _build_channels(config.alerts)
    if not channels:
        print(
            "No channels configured (slack/email/telegram/local all absent).",
            file=sys.stderr,
        )
        sys.exit(1)

    severity = AlertSeverity(args.severity)
    test_alert = Alert(
        id=str(uuid.uuid4()),
        severity=severity,
        trigger=AlertTrigger.MATERIAL_VALUATION_CHANGE,
        asset_id="test-asset",
        company_id="test-company",
        message=(
            f"[TEST] BVE alert channel verification — severity={severity.value}. "
            "If you see this, delivery is working correctly."
        ),
        detail={"test": True, "sent_at": datetime.now(timezone.utc).isoformat()},
        created_at=datetime.now(timezone.utc),
    )

    errors: list[str] = []
    for channel in channels:
        try:
            channel.send(test_alert)
            print(f"  ✓ {channel.name}: sent")
        except Exception as exc:
            errors.append(f"{channel.name}: {exc}")
            print(f"  ✗ {channel.name}: {exc}", file=sys.stderr)

    if errors:
        print(f"\n{len(errors)} channel(s) failed.", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"\nAll {len(channels)} channel(s) delivered successfully.")


if __name__ == "__main__":
    main()
