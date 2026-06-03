"""
P4.6 — ECE/Brier monitoring + governance + recalibration schedule.

Computes calibration metrics (Expected Calibration Error, Brier score) from a set of
(confidence, outcome) pairs, generates structured recalibration recommendations, and
maintains a governance log of model update events.

Calibration metrics
-------------------
**Brier score** — Mean squared error between confidence and binary outcome (0/1).
    BS = (1/N) × Σ (conf_i − outcome_i)²
    0 = perfect, 1 = worst possible.

**ECE (Expected Calibration Error)** — Weighted average of |avg_confidence − avg_accuracy|
per confidence bin.
    ECE = Σ_b (n_b / N) × |avg_conf_b − avg_outcome_b|
    0 = perfect calibration.

Recalibration thresholds
------------------------
ECE < 0.05 → no_action
ECE 0.05–0.10 → monitor
ECE 0.10–0.15 → recalibrate (medium urgency)
ECE > 0.15 → urgent_recalibrate (high urgency)

Usage
-----
>>> from bve.ops.calibration_monitor import CalibrationMonitor, RecalibrationSchedule
>>> monitor = CalibrationMonitor(n_bins=10)
>>> report = monitor.compute(confidences=[0.8, 0.6, 0.4], outcomes=[1.0, 1.0, 0.0])
>>> report.brier_score
0.12
>>> report.recommendation().action
'monitor'
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CalibrationBin:
    """One confidence bin in a reliability diagram."""
    lower: float
    upper: float
    avg_confidence: float
    avg_outcome: float
    n_samples: int
    gap: float  # |avg_confidence - avg_outcome|


@dataclass(frozen=True)
class RecalibrationRecommendation:
    """
    Governance recommendation based on calibration metrics.

    Attributes
    ----------
    action : str
        One of: "no_action", "monitor", "recalibrate", "urgent_recalibrate".
    urgency : str
        One of: "none", "low", "medium", "high".
    reason : str
        Human-readable explanation.
    """
    action: str
    urgency: str
    reason: str


@dataclass(frozen=True)
class CalibrationReport:
    """
    Full calibration report for one evaluation run.

    Attributes
    ----------
    brier_score : float
        Mean squared error of confidence vs. outcome.
    ece : float
        Expected Calibration Error.
    n_samples : int
        Number of (confidence, outcome) pairs evaluated.
    calibration_bins : list[CalibrationBin]
        Reliability diagram bins.
    min_samples : int
        Minimum samples threshold from the monitor config.
    """
    brier_score: float
    ece: float
    n_samples: int
    calibration_bins: list[CalibrationBin]
    min_samples: int

    def reliability_diagram_data(self) -> list[tuple[float, float]]:
        """
        List of (avg_confidence, avg_outcome) for non-empty bins.
        Suitable for plotting a reliability diagram.
        """
        return [
            (b.avg_confidence, b.avg_outcome)
            for b in self.calibration_bins
            if b.n_samples > 0
        ]

    def recommendation(self) -> RecalibrationRecommendation:
        """Generate a recalibration recommendation based on ECE and sample count."""
        if self.n_samples < self.min_samples:
            return RecalibrationRecommendation(
                action="monitor",
                urgency="low",
                reason=(
                    f"Insufficient data: {self.n_samples} samples "
                    f"(minimum {self.min_samples} required for reliable calibration)."
                ),
            )

        if self.ece < 0.05:
            return RecalibrationRecommendation(
                action="no_action",
                urgency="none",
                reason=f"ECE={self.ece:.3f} — model is well-calibrated. No action needed.",
            )
        if self.ece < 0.10:
            return RecalibrationRecommendation(
                action="monitor",
                urgency="low",
                reason=(
                    f"ECE={self.ece:.3f} — slight miscalibration. "
                    "Monitor over next 2–4 weeks; recalibrate if ECE persists above 0.10."
                ),
            )
        if self.ece < 0.15:
            return RecalibrationRecommendation(
                action="recalibrate",
                urgency="medium",
                reason=(
                    f"ECE={self.ece:.3f} (Brier={self.brier_score:.3f}) — "
                    "model confidence is materially mis-set. Recalibration recommended "
                    "within 2 weeks. Review confidence assignments for systematic bias."
                ),
            )
        return RecalibrationRecommendation(
            action="urgent_recalibrate",
            urgency="high",
            reason=(
                f"ECE={self.ece:.3f} (Brier={self.brier_score:.3f}) — "
                "severe miscalibration detected. Immediate recalibration required. "
                "Suspend confidence-weighted decisions until model is re-fitted."
            ),
        )


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------

class CalibrationMonitor:
    """
    Compute ECE and Brier score from (confidence, outcome) pairs.

    Parameters
    ----------
    n_bins : int
        Number of equal-width bins for ECE computation (default 10).
    min_samples : int
        Minimum sample count for reliable calibration assessment (default 20).
    """

    def __init__(self, n_bins: int = 10, min_samples: int = 20) -> None:
        self.n_bins = n_bins
        self.min_samples = min_samples

    def compute(
        self,
        confidences: list[float],
        outcomes: list[float],
    ) -> CalibrationReport:
        """
        Compute calibration metrics.

        Parameters
        ----------
        confidences : list[float]
            Predicted confidence / probability values in [0, 1].
        outcomes : list[float]
            Observed binary outcomes (0 or 1, or float for soft labels).
        """
        if not confidences:
            raise ValueError("confidences and outcomes must not be empty")
        if len(confidences) != len(outcomes):
            raise ValueError(
                f"confidences ({len(confidences)}) and outcomes ({len(outcomes)}) "
                "must have the same length"
            )

        n = len(confidences)

        # Brier score
        brier = round(
            sum((c - o) ** 2 for c, o in zip(confidences, outcomes)) / n, 6
        )

        # ECE via equal-width bins
        bins = self._build_bins(confidences, outcomes)
        ece = round(sum(b.n_samples / n * b.gap for b in bins), 6)

        return CalibrationReport(
            brier_score=brier,
            ece=ece,
            n_samples=n,
            calibration_bins=bins,
            min_samples=self.min_samples,
        )

    def _build_bins(
        self,
        confidences: list[float],
        outcomes: list[float],
    ) -> list[CalibrationBin]:
        bin_size = 1.0 / self.n_bins
        bins: list[CalibrationBin] = []

        for i in range(self.n_bins):
            lower = i * bin_size
            upper = lower + bin_size
            # Include upper boundary in last bin
            in_bin = [
                (c, o) for c, o in zip(confidences, outcomes)
                if lower <= c < upper or (i == self.n_bins - 1 and c == 1.0)
            ]
            if in_bin:
                avg_conf = sum(c for c, _ in in_bin) / len(in_bin)
                avg_out = sum(o for _, o in in_bin) / len(in_bin)
                gap = abs(avg_conf - avg_out)
            else:
                avg_conf = (lower + upper) / 2
                avg_out = 0.0
                gap = 0.0

            bins.append(CalibrationBin(
                lower=round(lower, 4),
                upper=round(upper, 4),
                avg_confidence=round(avg_conf, 4),
                avg_outcome=round(avg_out, 4),
                n_samples=len(in_bin),
                gap=round(gap, 4),
            ))

        return bins


# ---------------------------------------------------------------------------
# Governance log
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GovernanceLogEntry:
    """A single governance event record."""
    event: str
    detail: str
    logged_at: datetime


class GovernanceLog:
    """
    Append-only log of model governance events (recalibrations, reviews, etc.).

    Entries are stored in memory in insertion order.
    """

    def __init__(self) -> None:
        self._entries: list[GovernanceLogEntry] = []

    def record(self, event: str, detail: str) -> GovernanceLogEntry:
        """
        Record a governance event.

        Parameters
        ----------
        event : str
            Short event type label (e.g. "recalibration_run", "model_update").
        detail : str
            Human-readable detail about the event.
        """
        entry = GovernanceLogEntry(
            event=event,
            detail=detail,
            logged_at=datetime.now(timezone.utc),
        )
        self._entries.append(entry)
        return entry

    def entries(self) -> list[GovernanceLogEntry]:
        """All entries in insertion order."""
        return list(self._entries)


# ---------------------------------------------------------------------------
# Recalibration schedule
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RecalibrationSchedule:
    """
    Governs when recalibration checks are due.

    Parameters
    ----------
    cadence_days : int
        Number of days between scheduled recalibration runs (default 30).
    """
    cadence_days: int = 30

    def is_due(self, last_run: Optional[date]) -> bool:
        """Return True if a recalibration run is overdue."""
        if last_run is None:
            return True
        return (date.today() - last_run).days >= self.cadence_days

    def next_due(self, last_run: Optional[date]) -> date:
        """Return the next due date; today if last_run is None."""
        if last_run is None:
            return date.today()
        return last_run + timedelta(days=self.cadence_days)
