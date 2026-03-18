"""
Wave E — PoS Recalibration Loop.

Reads resolved forecast_records from KnowledgeStore, segments by
(trial_phase × indication), Bayesian-updates the industry prior PoS
base rates, and writes calibrated rates to a YAML file.

The calibration file is consumed by AssumptionsLoader so that future
valuations automatically use data-updated base rates rather than static
industry priors.

Flow
----
1. ``PoSRecalibrator(store).calibrate()`` — groups resolved forecasts by
   segment bucket (trial_phase, indication), computes empirical success
   rate from directional accuracy, Beta-updates the prior.

2. ``PoSRecalibrator.write_calibration(report, path)`` — serialises the
   report to YAML.

3. The ``IntelligenceService`` calls this on Sundays (same cadence as
   ``RankingCalibrator``), guarded by ``_last_pos_calibration_date``.

Beta-update rule
----------------
Prior: Beta(α, β) where α = prior × ESS, β = (1 − prior) × ESS
Observation: wins = n_correct, losses = n_incorrect
Posterior mean: (α + wins) / (α + wins + β + losses)

This shrinks aggressive updates when observations are few (ESS = 50
by default), and converges to empirical rate as n grows.

Minimum segment size: ``MIN_SEGMENT_OBS = 15`` (configurable).
Below this threshold the prior is preserved unchanged.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_SEGMENT_OBS: int = 15
PRIOR_ESS: float = 50.0          # effective sample size of the industry prior
DRIFT_ALERT_THRESHOLD: float = 0.10  # relative change that triggers a drift alert


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _default_calibration_path() -> Path:
    return Path(__file__).parent.parent / "config" / "pos_recalibration.yaml"


# ---------------------------------------------------------------------------
# Calibration record
# ---------------------------------------------------------------------------

class SegmentCalibration(BaseModel):
    """PoS calibration for one (trial_phase, indication) bucket."""

    trial_phase: str
    indication: str
    n_observations: int
    n_correct: int
    empirical_success_rate: Optional[float]  # n_correct / n_observations
    prior_rate: float
    updated_rate: float
    updated_from_data: bool   # False when n < MIN_SEGMENT_OBS (prior preserved)
    drift_pct: Optional[float]    # |updated − prior| / prior × 100


class PoSCalibrationReport(BaseModel):
    """Output of one PoS recalibration run."""

    run_date: str = Field(default_factory=lambda: _utcnow().date().isoformat())
    n_resolved_forecasts: int
    n_segments: int
    segments: list[SegmentCalibration] = Field(default_factory=list)
    drift_alerts: list[str] = Field(default_factory=list)
    min_segment_obs: int = MIN_SEGMENT_OBS
    prior_ess: float = PRIOR_ESS


# ---------------------------------------------------------------------------
# PoSRecalibrator
# ---------------------------------------------------------------------------

class PoSRecalibrator:
    """
    Recalibrates PoS base rates from resolved forecast_records.

    Parameters
    ----------
    store:
        A ``KnowledgeStore`` instance.
    min_segment_obs:
        Minimum resolved observations required per segment before updating.
    prior_ess:
        Effective sample size of the industry prior (Beta distribution weight).
    calibration_path:
        Path to write/read the calibration YAML.
    """

    def __init__(
        self,
        store: Any,
        *,
        min_segment_obs: int = MIN_SEGMENT_OBS,
        prior_ess: float = PRIOR_ESS,
        calibration_path: Optional[Path] = None,
    ) -> None:
        self.store = store
        self.min_segment_obs = min_segment_obs
        self.prior_ess = prior_ess
        self.calibration_path = calibration_path or _default_calibration_path()

    # ------------------------------------------------------------------
    # Main calibration entry point
    # ------------------------------------------------------------------

    def calibrate(self) -> PoSCalibrationReport:
        """
        Read resolved forecasts, update segment rates, return report.

        Returns
        -------
        PoSCalibrationReport
        """
        rows = self._fetch_rows()
        prior_map = self._load_priors()

        # Group by (trial_phase, indication)
        groups: dict[tuple[str, str], list[dict]] = {}
        for row in rows:
            phase = str(row.get("trial_phase") or "").strip().lower()
            indication = str(row.get("indication") or "all").strip().lower()
            if not phase:
                continue
            key = (phase, indication)
            groups.setdefault(key, []).append(row)

        segments: list[SegmentCalibration] = []
        drift_alerts: list[str] = []

        for (phase, indication), segment_rows in sorted(groups.items()):
            n = len(segment_rows)
            # Count correct directional predictions
            n_correct = sum(
                1 for r in segment_rows
                if r.get("outcome_correct") == 1
            )
            empirical = n_correct / n if n > 0 else None

            # Load prior from industry assumptions
            prior = self._resolve_prior(phase, indication, prior_map)

            if n < self.min_segment_obs:
                # Insufficient data — preserve prior
                seg = SegmentCalibration(
                    trial_phase=phase,
                    indication=indication,
                    n_observations=n,
                    n_correct=n_correct,
                    empirical_success_rate=empirical,
                    prior_rate=prior,
                    updated_rate=round(prior, 6),
                    updated_from_data=False,
                    drift_pct=None,
                )
            else:
                # Bayesian Beta update
                alpha = prior * self.prior_ess
                beta  = (1.0 - prior) * self.prior_ess
                updated = (alpha + n_correct) / (alpha + n_correct + beta + (n - n_correct))
                updated = round(max(0.01, min(0.99, updated)), 6)

                drift_pct = None
                if prior > 0:
                    drift_pct = round(abs(updated - prior) / prior * 100.0, 2)
                    if abs(updated - prior) / prior > DRIFT_ALERT_THRESHOLD:
                        drift_alerts.append(
                            f"{phase}/{indication}: PoS drift {drift_pct:.1f}% "
                            f"({prior:.3f} → {updated:.3f}, n={n})"
                        )

                seg = SegmentCalibration(
                    trial_phase=phase,
                    indication=indication,
                    n_observations=n,
                    n_correct=n_correct,
                    empirical_success_rate=empirical,
                    prior_rate=prior,
                    updated_rate=updated,
                    updated_from_data=True,
                    drift_pct=drift_pct,
                )
            segments.append(seg)

        return PoSCalibrationReport(
            n_resolved_forecasts=len(rows),
            n_segments=len(segments),
            segments=segments,
            drift_alerts=drift_alerts,
            min_segment_obs=self.min_segment_obs,
            prior_ess=self.prior_ess,
        )

    # ------------------------------------------------------------------
    # Write calibration
    # ------------------------------------------------------------------

    def write_calibration(self, report: PoSCalibrationReport) -> None:
        """Serialise the calibration report to YAML."""
        payload = {
            "run_date":             report.run_date,
            "n_resolved_forecasts": report.n_resolved_forecasts,
            "n_segments":           report.n_segments,
            "min_segment_obs":      report.min_segment_obs,
            "prior_ess":            float(report.prior_ess),
            "drift_alerts":         report.drift_alerts,
            "calibrations": [
                {
                    "trial_phase":            seg.trial_phase,
                    "indication":             seg.indication,
                    "n_observations":         seg.n_observations,
                    "n_correct":              seg.n_correct,
                    "empirical_success_rate": (
                        round(seg.empirical_success_rate, 6)
                        if seg.empirical_success_rate is not None
                        else None
                    ),
                    "prior_rate":             round(seg.prior_rate, 6),
                    "updated_rate":           round(seg.updated_rate, 6),
                    "updated_from_data":      seg.updated_from_data,
                    "drift_pct":              seg.drift_pct,
                }
                for seg in sorted(
                    report.segments,
                    key=lambda s: (s.trial_phase, s.indication),
                )
            ],
        }
        self.calibration_path.parent.mkdir(parents=True, exist_ok=True)
        self.calibration_path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_rows(self) -> list[dict]:
        """Fetch resolved forecast_records with bucket fields."""
        rows = self.store._conn.execute(
            """
            SELECT
                trial_phase,
                indication,
                outcome_correct,
                extraction_confidence,
                event_type
            FROM forecast_records
            WHERE resolved = 1
              AND outcome_correct IS NOT NULL
            ORDER BY created_at
            """
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _load_priors() -> dict[str, dict[str, float]]:
        """
        Load phase_success_rates from industry_assumptions.yaml.

        Returns a dict: {ta_name: {phase_name: rate}}.
        Falls back to empty dict if loading fails.
        """
        try:
            from bve.config.assumptions_loader import AssumptionsLoader
            data = AssumptionsLoader.get()._data
            rates = data.get("phase_success_rates", {})
            # Convert from MappingProxyType to plain dict
            return {
                ta: dict(phases)
                for ta, phases in rates.items()
            }
        except Exception:
            return {}

    @staticmethod
    def _resolve_prior(
        phase: str,
        indication: str,
        prior_map: dict[str, dict[str, float]],
    ) -> float:
        """
        Look up the prior PoS for (phase, indication).

        Resolution order:
        1. Exact indication match in prior_map
        2. "all" (catch-all) in prior_map
        3. Default fallback by phase
        """
        fallbacks = {
            "phase_1": 0.64,
            "phase_2": 0.37,
            "phase_3": 0.60,
            "nda_bla": 0.87,
        }

        # Map indication to a TA key (approximate)
        ta_candidates = [indication, "all"]
        for ta in ta_candidates:
            ta_rates = prior_map.get(ta, {})
            if phase in ta_rates:
                return float(ta_rates[phase])

        return fallbacks.get(phase, 0.40)
