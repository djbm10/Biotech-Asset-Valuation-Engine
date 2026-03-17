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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from bve.intelligence.capital_structure import CapitalStructureAssessment

from bve.alerts.alert_config import AlertsConfig
from bve.alerts.alert_model import Alert, AlertSeverity, AlertTrigger
from bve.alerts.channels.base import AlertChannel
from bve.intelligence.catalyst_calendar import CatalystEvent
from bve.intelligence.extraction.result import ExtractionResult
from bve.intelligence.knowledge_layer import BacktestSnapshot, KnowledgeStore, StoredValuationDiff
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
        knowledge_store: Optional[KnowledgeStore] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.config = config
        self.channels = channels or []
        self.knowledge_store = knowledge_store
        self.logger = logger or _LOG
        # Per-run pending queue keyed by asset_id
        self._pending: dict[str, list[Alert]] = defaultdict(list)
        # Dedup state: dedup_key -> last_fired_at (persisted across restarts)
        self._dedup: dict[str, datetime] = self._load_dedup()

    @classmethod
    def from_config(
        cls,
        config: AlertsConfig,
        *,
        knowledge_store: Optional[KnowledgeStore] = None,
    ) -> "AlertRouter":
        """Build channels from AlertsConfig, then construct the router."""
        return cls(
            config=config,
            channels=_build_channels(config),
            knowledge_store=knowledge_store,
        )

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
            if self._is_suppressed(
                signal.asset_id, signal.event_type.value, AlertTrigger.SAFETY_SIGNAL_DETECTED
            ):
                return
            key = _dedup_key(
                signal.asset_id,
                signal.event_type.value,
                AlertTrigger.SAFETY_SIGNAL_DETECTED,
                str(signal.signal_date),
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
            if self._is_suppressed(
                signal.asset_id, signal.event_type.value, AlertTrigger.LOW_CONFIDENCE_HIGH_SEVERITY
            ):
                return
            key = _dedup_key(
                signal.asset_id,
                signal.event_type.value,
                AlertTrigger.LOW_CONFIDENCE_HIGH_SEVERITY,
                str(signal.signal_date),
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

        if self._is_suppressed(
            diff.asset_id, signal.event_type.value, AlertTrigger.MATERIAL_VALUATION_CHANGE
        ):
            return

        key = _dedup_key(
            diff.asset_id,
            signal.event_type.value,
            AlertTrigger.MATERIAL_VALUATION_CHANGE,
            str(signal.signal_date),
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

    def enqueue_system_alert(
        self,
        *,
        key: str,
        message: str,
        detail: Optional[dict] = None,
        run_id: Optional[str] = None,
        severity: AlertSeverity = AlertSeverity.LOW,
        trigger: AlertTrigger = AlertTrigger.LOW_STATISTICAL_POWER,
        asset_id: str = "system",
        company_id: str = "system",
    ) -> None:
        """
        Queue a non-asset scientific/system alert through normal router channels.

        This keeps dispatch, severity filtering, and dedup behavior consistent
        with existing alert infrastructure.
        """
        if not self.config.enabled:
            return

        dedup = _dedup_key(asset_id, key, trigger, key)
        if self._is_deduped(dedup):
            return

        self._pending[asset_id].append(
            Alert(
                id=str(uuid.uuid4()),
                severity=severity,
                trigger=trigger,
                asset_id=asset_id,
                company_id=company_id,
                run_id=run_id,
                message=message,
                detail=detail or {},
            )
        )
        self._mark_dedup(dedup)

    def enqueue_catalyst_alerts(
        self,
        *,
        catalyst: "CatalystEvent",
        days_ahead: int = 30,
        min_delta_ev_abs: float = 100.0,
        run_id: Optional[str] = None,
    ) -> None:
        """
        Evaluate CATALYST_APPROACHING condition.

        Fires HIGH severity when:
          - catalyst.expected_date is within *days_ahead* calendar days of today
          - |catalyst.delta_ev| > *min_delta_ev_abs* millions

        Parameters
        ----------
        catalyst:
            The CatalystEvent to evaluate.
        days_ahead:
            Window in calendar days (default 30).
        min_delta_ev_abs:
            Absolute minimum |delta_ev| in $M required to fire (default $100M).
        run_id:
            Optional pipeline run ID for traceability.
        """
        if not self.config.enabled:
            return
        if catalyst.asset_id is None:
            return

        from datetime import date as _date
        today = _date.today()
        days_to = (catalyst.expected_date - today).days
        if days_to < 0 or days_to > days_ahead:
            return

        delta_ev = catalyst.delta_ev
        if delta_ev is None or abs(delta_ev) <= min_delta_ev_abs:
            return

        key = _dedup_key(
            catalyst.asset_id,
            catalyst.catalyst_type.value,
            AlertTrigger.CATALYST_APPROACHING,
            str(catalyst.expected_date),
        )
        if self._is_deduped(key):
            return

        sign = "+" if delta_ev >= 0 else ""
        self._pending[catalyst.asset_id].append(
            Alert(
                id=str(uuid.uuid4()),
                severity=AlertSeverity.HIGH,
                trigger=AlertTrigger.CATALYST_APPROACHING,
                asset_id=catalyst.asset_id,
                company_id=catalyst.company_id or "unknown",
                run_id=run_id,
                message=(
                    f"Catalyst approaching in {days_to}d for {catalyst.asset_id}: "
                    f"{catalyst.catalyst_type.value} on {catalyst.expected_date} "
                    f"(EV {sign}${delta_ev:.1f}M)"
                ),
                detail={
                    "catalyst_type":   catalyst.catalyst_type.value,
                    "expected_date":   str(catalyst.expected_date),
                    "days_to":         days_to,
                    "delta_ev":        delta_ev,
                    "signal_strength": catalyst.signal_strength,
                    "date_confidence": catalyst.date_confidence,
                },
            )
        )
        self._mark_dedup(key)

    def enqueue_capital_risk_alerts(
        self,
        *,
        assessment: "CapitalStructureAssessment",
        alert_window_months: float = 12.0,
        run_id: Optional[str] = None,
    ) -> None:
        """
        Evaluate CAPITAL_RISK_HIGH condition.

        Fires HIGH severity when:
          - capital_risk is HIGH or CRITICAL
          - months_to_catalyst is within *alert_window_months*

        Parameters
        ----------
        assessment:
            CapitalStructureAssessment produced by capital_structure_assessment().
        alert_window_months:
            Window in months (default 12).
        run_id:
            Optional pipeline run ID for traceability.
        """
        from bve.intelligence.capital_structure import CapitalRiskLevel

        if not self.config.enabled:
            return
        if not assessment.asset_id:
            return

        high_risk = assessment.capital_risk in (
            CapitalRiskLevel.HIGH, CapitalRiskLevel.CRITICAL
        )
        if not high_risk:
            return
        if assessment.months_to_catalyst > alert_window_months:
            return

        key = _dedup_key(
            assessment.asset_id,
            "capital_risk",
            AlertTrigger.CAPITAL_RISK_HIGH,
            assessment.catalyst_id,
        )
        if self._is_deduped(key):
            return

        diluted = assessment.diluted_delta_ev
        diluted_str = (
            f"  Diluted EV Δ ${diluted:.1f}M" if diluted is not None else ""
        )
        self._pending[assessment.asset_id].append(
            Alert(
                id=str(uuid.uuid4()),
                severity=AlertSeverity.HIGH,
                trigger=AlertTrigger.CAPITAL_RISK_HIGH,
                asset_id=assessment.asset_id,
                company_id="unknown",
                run_id=run_id,
                message=(
                    f"Capital risk {assessment.capital_risk.value.upper()} for "
                    f"{assessment.asset_id}: {assessment.gap_months:.1f}mo gap, "
                    f"raise ~${assessment.raise_amount_millions:.0f}M needed "
                    f"({assessment.n_offerings_required} offering(s), "
                    f"{assessment.dilution_pct*100:.1f}% dilution).{diluted_str}"
                ),
                detail={
                    "capital_risk":         assessment.capital_risk.value,
                    "gap_months":           assessment.gap_months,
                    "raise_amount_millions": assessment.raise_amount_millions,
                    "n_offerings":          assessment.n_offerings_required,
                    "dilution_pct":         assessment.dilution_pct,
                    "diluted_delta_ev":     diluted,
                    "liquidity_constrained": assessment.liquidity_constrained,
                },
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
        self._write_backtest_snapshots(pending)
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

    def _write_backtest_snapshots(self, alerts: list[Alert]) -> None:
        if self.knowledge_store is None:
            return
        for alert in alerts:
            detail = dict(alert.detail or {})
            has_snapshot_context = (
                any(key in detail for key in ("rank", "composite_score", "mispricing_score"))
                or alert.valuation_delta_npv is not None
            )
            if not has_snapshot_context:
                continue
            try:
                signal_date = self._parse_signal_date(
                    detail.get("signal_date"), alert.created_at.date()
                )
                signal_timestamp = self._parse_datetime(
                    detail.get("signal_timestamp"), alert.created_at
                )
                catalyst_date = self._parse_signal_date(detail.get("catalyst_date"), None)
                self.knowledge_store.write_backtest_snapshot(
                    BacktestSnapshot(
                        snapshot_id=str(uuid.uuid4()),
                        alert_id=alert.id,
                        asset_id=alert.asset_id,
                        signal_date=signal_date,
                        signal_id=self._to_str(detail.get("signal_id")),
                        signal_timestamp=signal_timestamp,
                        composite_score=self._to_float(detail.get("composite_score")),
                        extraction_confidence=(
                            self._to_float(detail.get("extraction_confidence"))
                            if detail.get("extraction_confidence") is not None
                            else self._to_float(detail.get("confidence"))
                            if detail.get("confidence") is not None
                            else alert.extraction_confidence
                        ),
                        delta_npv_millions=(
                            self._to_float(detail.get("delta_npv_millions"))
                            if detail.get("delta_npv_millions") is not None
                            else self._to_float(detail.get("delta_npv"))
                            if detail.get("delta_npv") is not None
                            else alert.valuation_delta_npv
                        ),
                        intrinsic_value_millions=self._to_float(
                            detail.get("intrinsic_value_millions")
                        ),
                        mispricing_score=self._to_float(detail.get("mispricing_score")),
                        catalyst_date=catalyst_date,
                        catalyst_type=self._to_str(detail.get("catalyst_type")),
                        catalyst_score=self._to_float(detail.get("catalyst_score")),
                        rank_at_signal=self._to_int(detail.get("rank")),
                        model_version=self._to_str(detail.get("model_version")),
                        created_at=alert.created_at,
                    )
                )
            except Exception as exc:
                self.logger.debug(
                    "backtest_snapshot_write_failed alert_id=%s err=%s", alert.id, exc
                )

    @staticmethod
    def _to_float(value: object) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int(value: object) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_str(value: object) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _parse_signal_date(raw: object, default: Optional[date]) -> Optional[date]:
        if raw is None:
            return default
        text = str(raw).strip()
        if not text:
            return default
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return default

    @staticmethod
    def _parse_datetime(raw: object, default: Optional[datetime]) -> Optional[datetime]:
        if raw is None:
            return default
        text = str(raw).strip()
        if not text:
            return default
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            return default

    def _is_suppressed(
        self,
        asset_id: str,
        event_type_value: Optional[str],
        trigger: AlertTrigger,
    ) -> bool:
        """Return True if any active suppression rule matches this alert."""
        now = datetime.now(timezone.utc)
        for rule in self.config.suppression_rules:
            if rule.until <= now:
                continue  # rule expired
            if rule.asset_id is not None and rule.asset_id != asset_id:
                continue
            if rule.event_type is not None and rule.event_type != event_type_value:
                continue
            if rule.trigger is not None and rule.trigger != trigger.value:
                continue
            self.logger.debug(
                "alert_suppressed asset=%s event_type=%s trigger=%s until=%s",
                asset_id,
                event_type_value,
                trigger.value,
                rule.until.isoformat(),
            )
            return True
        return False

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


def _dedup_key(
    asset_id: str,
    event_type_value: str,
    trigger: AlertTrigger,
    signal_date: Optional[str] = None,
) -> str:
    """
    Include signal_date so alerts from different events of the same type
    on different dates are not conflated under the same dedup window.
    E.g. two safety signals in separate months both get through.
    """
    date_part = signal_date or "unknown"
    return f"{asset_id}::{event_type_value}::{trigger.value}::{date_part}"


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
