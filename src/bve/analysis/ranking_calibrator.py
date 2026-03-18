"""Weekly ranking calibration from resolved forecast outcomes."""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.ranking import DEFAULT_EVENT_TYPE_SCORES


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _default_calibration_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "ranking_calibration.yaml"


class CalibrationReport(BaseModel):
    """Ranking feedback snapshot written by the weekly calibrator."""

    run_date: date
    n_resolved_forecasts: int
    event_type_weights: dict[str, float]
    event_type_weights_prior: dict[str, float]
    confidence_scaling_factor: float = Field(gt=0.0)
    brier_score: float
    calibration_curve: list[dict[str, float | int]] = Field(default_factory=list)
    drift_alerts: list[str] = Field(default_factory=list)


class RankingCalibrator:
    """Calibrates ranking weights from resolved forecast records."""

    def __init__(self, store: KnowledgeStore, calibration_path: Path | None = None) -> None:
        self._store = store
        self._calibration_path = calibration_path or _default_calibration_path()

    def _load_prior(self) -> tuple[dict[str, float], float]:
        prior = dict(DEFAULT_EVENT_TYPE_SCORES)
        scaling = 1.0
        path = self._calibration_path
        if not path.exists():
            return prior, scaling

        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return prior, scaling

        loaded = payload.get("event_type_weights") or {}
        if isinstance(loaded, dict):
            for key, value in loaded.items():
                try:
                    parsed = float(value)
                    if math.isfinite(parsed):
                        prior[str(key)] = max(parsed, 0.0)
                except (TypeError, ValueError):
                    continue

        raw_scaling = payload.get("confidence_scaling_factor")
        if raw_scaling is not None:
            try:
                s = float(raw_scaling)
                if s > 0:
                    scaling = s
            except (TypeError, ValueError):
                pass
        return prior, scaling

    def _resolved_forecasts(self) -> list[dict[str, Any]]:
        rows = self._store._conn.execute(  # noqa: SLF001 - internal analytics query
            """
            SELECT event_type, predicted_direction, extraction_confidence, actual_market_return_t30
            FROM forecast_records
            WHERE resolved = 1
              AND actual_market_return_t30 IS NOT NULL
            ORDER BY created_at
            """
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _f1(rows: list[dict[str, Any]]) -> float:
        tp = fp = fn = 0
        for row in rows:
            predicted_up = str(row.get("predicted_direction") or "").lower() == "up"
            actual_up = float(row.get("actual_market_return_t30") or 0.0) > 0.0
            if predicted_up and actual_up:
                tp += 1
            elif predicted_up and not actual_up:
                fp += 1
            elif (not predicted_up) and actual_up:
                fn += 1
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        if precision + recall == 0.0:
            return 0.0
        return 2.0 * precision * recall / (precision + recall)

    @staticmethod
    def _clip_conf(value: float) -> float:
        return max(1e-4, min(1.0 - 1e-4, value))

    @classmethod
    def _scaled_probability(cls, conf: float, scaling: float) -> float:
        conf = cls._clip_conf(conf)
        logit = math.log(conf / (1.0 - conf))
        z = scaling * logit
        return 1.0 / (1.0 + math.exp(-z))

    @classmethod
    def _fit_confidence_scaling_factor(cls, rows: list[dict[str, Any]]) -> float:
        if not rows:
            return 1.0

        observations: list[tuple[float, int]] = []
        for row in rows:
            conf_raw = row.get("extraction_confidence")
            if conf_raw is None:
                continue
            conf = cls._clip_conf(float(conf_raw))
            outcome = 1 if float(row.get("actual_market_return_t30") or 0.0) > 0.0 else 0
            observations.append((conf, outcome))

        if not observations:
            return 1.0

        best_scale = 1.0
        best_nll = float("inf")
        candidate = 0.25
        while candidate <= 2.5:
            nll = 0.0
            for conf, outcome in observations:
                p = cls._scaled_probability(conf, candidate)
                p = cls._clip_conf(p)
                if outcome == 1:
                    nll -= math.log(p)
                else:
                    nll -= math.log(1.0 - p)
            if nll < best_nll:
                best_nll = nll
                best_scale = candidate
            candidate = round(candidate + 0.05, 10)

        return round(best_scale, 6)

    @classmethod
    def _brier_score(cls, rows: list[dict[str, Any]], scaling: float) -> float:
        if not rows:
            return 0.0
        vals: list[float] = []
        for row in rows:
            conf = float(row.get("extraction_confidence") or 0.5)
            p = cls._scaled_probability(conf, scaling)
            outcome = 1.0 if float(row.get("actual_market_return_t30") or 0.0) > 0.0 else 0.0
            vals.append((p - outcome) ** 2)
        return round(sum(vals) / len(vals), 6)

    @classmethod
    def _calibration_curve(
        cls, rows: list[dict[str, Any]], scaling: float
    ) -> list[dict[str, float | int]]:
        out: list[dict[str, float | int]] = []
        if not rows:
            return out

        for idx in range(10):
            lo = idx / 10.0
            hi = (idx + 1) / 10.0
            in_bin: list[tuple[float, float]] = []
            for row in rows:
                conf = float(row.get("extraction_confidence") or 0.5)
                p = cls._scaled_probability(conf, scaling)
                if lo <= p < hi or (idx == 9 and p <= 1.0):
                    outcome = (
                        1.0 if float(row.get("actual_market_return_t30") or 0.0) > 0.0 else 0.0
                    )
                    in_bin.append((p, outcome))
            if not in_bin:
                continue
            mean_pred = sum(p for p, _ in in_bin) / len(in_bin)
            actual_rate = sum(o for _, o in in_bin) / len(in_bin)
            out.append(
                {
                    "bin_low": round(lo, 2),
                    "bin_high": round(hi, 2),
                    "n": len(in_bin),
                    "mean_pred": round(mean_pred, 6),
                    "actual_rate": round(actual_rate, 6),
                }
            )
        return out

    def calibrate(self) -> CalibrationReport:
        rows = self._resolved_forecasts()
        prior_weights, _prior_scaling = self._load_prior()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            evt = str(row.get("event_type") or "").strip()
            if not evt:
                continue
            grouped.setdefault(evt, []).append(row)

        event_type_weights = dict(prior_weights)
        drift_alerts: list[str] = []

        for event_type, sample in grouped.items():
            prior = float(
                prior_weights.get(event_type, DEFAULT_EVENT_TYPE_SCORES.get(event_type, 0.3))
            )
            prior = max(prior, 0.0)
            if len(sample) < 20:
                event_type_weights[event_type] = prior
                continue
            f1 = self._f1(sample)
            updated = 0.80 * prior + 0.20 * f1
            event_type_weights[event_type] = round(max(updated, 0.0), 6)
            if prior > 0:
                shift = abs(updated - prior) / prior
                if shift > 0.20:
                    drift_alerts.append(
                        f"{event_type}: weight drift {shift * 100:.1f}% ({prior:.3f} -> {updated:.3f})"
                    )

        scaling = self._fit_confidence_scaling_factor(rows)
        report = CalibrationReport(
            run_date=_utcnow().date(),
            n_resolved_forecasts=len(rows),
            event_type_weights=event_type_weights,
            event_type_weights_prior=prior_weights,
            confidence_scaling_factor=scaling,
            brier_score=self._brier_score(rows, scaling),
            calibration_curve=self._calibration_curve(rows, scaling),
            drift_alerts=drift_alerts,
        )
        return report

    def write_calibration(self, report: CalibrationReport) -> None:
        payload = {
            "run_date": report.run_date.isoformat(),
            "confidence_scaling_factor": float(report.confidence_scaling_factor),
            "event_type_weights": {
                key: float(value) for key, value in sorted(report.event_type_weights.items())
            },
            "drift_alerts": report.drift_alerts,
        }
        self._calibration_path.parent.mkdir(parents=True, exist_ok=True)
        self._calibration_path.write_text(
            yaml.safe_dump(payload, sort_keys=False),
            encoding="utf-8",
        )
