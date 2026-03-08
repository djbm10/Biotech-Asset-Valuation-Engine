"""
AlertRouter — evaluates trigger conditions and manages the enqueue/flush cycle.

Usage pattern per pipeline asset run:
    router.enqueue_signal_alerts(signal, extraction, ...)  # after each extraction
    router.enqueue_diff_alerts(diff, signal, ...)          # after each valuation diff
    sent = router.flush(asset_id, run_id)                  # end of asset run

Design decisions:
- Enqueue → flush (not immediate dispatch) prevents alert storms when multiple
  signals arrive for the same asset in one batch. Channels receive either a
  single send() or one send_batch() aggregated message per asset.
- Condition 2 requires BOTH an absolute NPV floor ($25M default) AND a relative
  threshold (15% default). This prevents noise from small-NPV programs where
  $5M → $7M = 40% change but is economically irrelevant.
- Condition 3 (low confidence on high-severity event) fires at MEDIUM severity,
  not LOW — the risk is model corruption, which demands review.
- Dedup: (asset_id, event_type, trigger) key with configurable window (default
  24h) persisted to disk so restarts do not re-send across cycles.
"""
from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from bve.alerts.alert_config import AlertsConfig
from bve.alerts.alert_model import Alert, AlertSeverity, AlertTrigger
from bve.alerts.channels.base import AlertChannel
from bve.intelligence.extraction.result import ExtractionResult
from bve.intelligence.knowledge_layer import StoredValuationDiff
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import EventType

_LOG = logging.getLogger("bve.alerts")


class AlertRouter:
    """
    Evaluates trigger conditions, deduplicates, and dispatches alerts via channels.

    Safe to construct with no channels (no-op mode for tests and dry runs).
    """

    def __init__(
        self,
        config: AlertsConfig,
        channels: Optional[list[AlertChannel]] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.config = config
        self.channels = channels or []
        self.logger = logger or _LOG
        # Per-run pending queue keyed by asset_id
        self._pending: dict[str, list[Alert]] = defaultdict(list)
        # Dedup state: dedup_key -> last_fired_at (persisted across restarts)
        self._dedup: dict[str, datetime] = self._load_dedup()

    @classmethod
    def from_config(cls, config: AlertsConfig) -> "AlertRouter":
        """Build channels from AlertsConfig, then construct the router."""
        return cls(config=config, channels=_build_channels(config))

    # ------------------------------------------------------------------
    # Enqueue (called during asset processing)
    # ------------------------------------------------------------------

    def enqueue_signal_alerts(
        self,
        *,
        signal: StructuredSignal,
        extraction: ExtractionResult,
        run_id: Optional[str] = None,
        headline: Optional[str] = None,
        source_url: Optional[str] = None,
    ) -> None:
        """
        Evaluate conditions 1 (safety signal) and 3 (low-confidence/high-severity).
        Append any triggered alerts to the pending queue for later flush.
        """
        if not self.config.enabled:
            return

        thr = self.config.thresholds

        # Condition 1 — safety signal detected (CRITICAL, always fires)
        if signal.event_type == EventType.SAFETY_SIGNAL:
            key = _dedup_key(
                signal.asset_id, signal.event_type.value, AlertTrigger.SAFETY_SIGNAL_DETECTED
            )
            if not self._is_deduped(key):
                self._pending[signal.asset_id].append(
                    Alert(
                        id=str(uuid.uuid4()),
                        severity=AlertSeverity.CRITICAL,
                        trigger=AlertTrigger.SAFETY_SIGNAL_DETECTED,
                        asset_id=signal.asset_id,
                        company_id=signal.company_id,
                        run_id=run_id,
                        message=(
                            f"Safety signal detected for {signal.asset_id}"
                            + (f": {headline}" if headline else "")
                        ),
                        detail={
                            "event_type": signal.event_type.value,
                            "signal_date": str(signal.signal_date),
                            "source_url": source_url,
                            "extraction_confidence": extraction.extraction_confidence,
                        },
                        signal_event_type=signal.event_type.value,
                        extraction_confidence=extraction.extraction_confidence,
                    )
                )
                self._mark_dedup(key)

        # Condition 3 — low confidence on a high-severity event type.
        # Severity is MEDIUM (not LOW) — model corruption risk requires review.
        high_sev_types = set(thr.high_severity_event_types)
        conf = extraction.extraction_confidence
        if (
            signal.event_type.value in high_sev_types
            and conf is not None
            and conf < thr.low_confidence_threshold
        ):
            key = _dedup_key(
                signal.asset_id,
                signal.event_type.value,
                AlertTrigger.LOW_CONFIDENCE_HIGH_SEVERITY,
            )
            if not self._is_deduped(key):
                self._pending[signal.asset_id].append(
                    Alert(
                        id=str(uuid.uuid4()),
                        severity=AlertSeverity.MEDIUM,
                        trigger=AlertTrigger.LOW_CONFIDENCE_HIGH_SEVERITY,
                        asset_id=signal.asset_id,
                        company_id=signal.company_id,
                        run_id=run_id,
                        message=(
                            f"Low-confidence extraction ({conf:.2f}) for "
                            f"{signal.event_type.value} event on {signal.asset_id}"
                            f" — manual review required"
                        ),
                        detail={
                            "event_type": signal.event_type.value,
                            "confidence": conf,
                            "threshold": thr.low_confidence_threshold,
                            "source_url": source_url,
                        },
                        signal_event_type=signal.event_type.value,
                        extraction_confidence=conf,
                    )
                )
                self._mark_dedup(key)

    def enqueue_diff_alerts(
        self,
        *,
        diff: StoredValuationDiff,
        signal: StructuredSignal,
        run_id: Optional[str] = None,
    ) -> None:
        """
        Evaluate condition 2 (material valuation change).

        Both gates must pass:
          abs(delta_npv) >= abs_floor  (prevents small-NPV noise)
          AND
          abs(delta_npv / before_npv) * 100 >= pct_threshold
        """
        if not self.config.enabled:
            return

        thr = self.config.thresholds
        abs_delta = abs(diff.delta_npv)

        # Gate 1: absolute floor
        if abs_delta < thr.material_change_abs_floor_millions:
            return

        # Gate 2: relative threshold
        before_npv = float(diff.valuation_before.get("rnpv_millions") or 0.0)
        if before_npv == 0:
            rel_pct = 100.0  # starting from zero → always material if abs floor passed
        else:
            rel_pct = abs_delta / abs(before_npv) * 100.0

        if rel_pct < thr.material_change_pct:
            return

        key = _dedup_key(
            diff.asset_id,
            signal.event_type.value,
            AlertTrigger.MATERIAL_VALUATION_CHANGE,
        )
        if self._is_deduped(key):
            return

        sign = "+" if diff.delta_npv >= 0 else ""
        self._pending[diff.asset_id].append(
            Alert(
                id=str(uuid.uuid4()),
                severity=AlertSeverity.MEDIUM,
                trigger=AlertTrigger.MATERIAL_VALUATION_CHANGE,
                asset_id=diff.asset_id,
                company_id=signal.company_id,
                run_id=run_id,
                message=(
                    f"Material valuation change for {diff.asset_id}: "
                    f"{sign}${diff.delta_npv:.1f}M rNPV ({sign}{rel_pct:.1f}%) "
                    f"triggered by {signal.event_type.value}"
                ),
                detail={
                    "event_type": signal.event_type.value,
                    "delta_npv": diff.delta_npv,
                    "before_npv": before_npv,
                    "after_npv": diff.valuation_after.get("rnpv_millions"),
                    "rel_pct": round(rel_pct, 2),
                    "abs_floor_millions": thr.material_change_abs_floor_millions,
                },
                signal_event_type=signal.event_type.value,
                valuation_delta_npv=diff.delta_npv,
            )
        )
        self._mark_dedup(key)

    # ------------------------------------------------------------------
    # Flush (called at end of asset run)
    # ------------------------------------------------------------------

    def flush(self, asset_id: str, run_id: Optional[str] = None) -> list[Alert]:
        """
        Dispatch all pending alerts for *asset_id* and clear the queue.

        When only one alert is pending, channels receive send().
        When multiple alerts are pending, channels receive send_batch() — this
        allows aggregation-capable channels (Slack, email, Telegram) to send
        one message instead of N.

        Saves dedup state to disk after dispatch.
        """
        pending = self._pending.pop(asset_id, [])
        if not pending:
            return []

        for channel in self.channels:
            try:
                if len(pending) == 1:
                    channel.send(pending[0])
                else:
                    channel.send_batch(pending, asset_id)
            except Exception as exc:
                self.logger.error(
                    "alert_channel_error channel=%s asset=%s: %s",
                    channel.name,
                    asset_id,
                    exc,
                )

        self._save_dedup()
        self.logger.info(
            "alerts_flushed asset=%s count=%d run_id=%s",
            asset_id,
            len(pending),
            run_id or "unknown",
        )
        return pending

    def flush_all(self, run_id: Optional[str] = None) -> list[Alert]:
        """Flush pending alerts for all assets. Call at end of run_once()."""
        sent: list[Alert] = []
        for asset_id in list(self._pending.keys()):
            sent.extend(self.flush(asset_id, run_id=run_id))
        return sent

    def reset(self) -> None:
        """Clear in-memory pending queue (not dedup). Useful for test isolation."""
        self._pending.clear()

    # ------------------------------------------------------------------
    # Dedup helpers
    # ------------------------------------------------------------------

    def _is_deduped(self, key: str) -> bool:
        last_fired = self._dedup.get(key)
        if last_fired is None:
            return False
        window = timedelta(hours=self.config.thresholds.dedup_window_hours)
        return (datetime.now(timezone.utc) - last_fired) < window

    def _mark_dedup(self, key: str) -> None:
        self._dedup[key] = datetime.now(timezone.utc)

    def _dedup_path(self) -> Path:
        return Path(self.config.thresholds.dedup_state_path)

    def _load_dedup(self) -> dict[str, datetime]:
        path = self._dedup_path()
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            result: dict[str, datetime] = {}
            for k, v in raw.items():
                try:
                    dt = datetime.fromisoformat(v)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    result[k] = dt
                except (ValueError, TypeError):
                    pass
            return result
        except Exception as exc:
            _LOG.warning("Failed to load alert dedup state from %s: %s", path, exc)
            return {}

    def _save_dedup(self) -> None:
        path = self._dedup_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {k: v.isoformat() for k, v in self._dedup.items()}
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            _LOG.warning("Failed to save alert dedup state: %s", exc)


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _dedup_key(asset_id: str, event_type_value: str, trigger: AlertTrigger) -> str:
    return f"{asset_id}::{event_type_value}::{trigger.value}"


def _build_channels(config: AlertsConfig) -> list[AlertChannel]:
    """Build channel instances from AlertsConfig. Only instantiates configured channels."""
    channels: list[AlertChannel] = []
    if config.local:
        from bve.alerts.channels.local import LocalFileChannel
        channels.append(LocalFileChannel(config.local))
    if config.slack:
        from bve.alerts.channels.slack import SlackWebhookChannel
        channels.append(SlackWebhookChannel(config.slack))
    if config.email:
        from bve.alerts.channels.email import SmtpEmailChannel
        channels.append(SmtpEmailChannel(config.email))
    if config.telegram:
        from bve.alerts.channels.telegram import TelegramChannel
        channels.append(TelegramChannel(config.telegram))
    return channels
