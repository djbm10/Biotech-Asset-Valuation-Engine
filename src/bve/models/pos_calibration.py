"""
P2.3 — POS Calibration: Platt-scaling logistic regression on oncology outcomes.

Fits a calibration layer on top of the existing log-odds POS model:

    calibrated_pos = sigmoid(slope * logit(raw_pos) + intercept)

Trained on the N=99 oncology phase-transition dataset at:
    research/data/oncology_phase_transitions.csv

The calibration is diagnostic — it reveals systematic over/under-confidence
in raw model estimates. A slope > 1.0 means the model is under-confident
(outputs too close to 0.5); slope < 1.0 means over-confident (outputs too
extreme). Intercept captures net bias.

Workflow
--------
1. load_oncology_dataset()  → list of (raw_pos, binary_outcome) pairs
2. fit_calibration(raw_pos_list, outcomes)  → CalibrationResult
3. calibrate_pos(raw_pos, result)  → float (Platt-calibrated prediction)
4. POSCalibrationLayer.fit_on_oncology_dataset()  → convenience wrapper

References
----------
- Platt (1999) "Probabilistic outputs for SVMs"
- Niculescu-Mizil & Caruana (2005) "Predicting good probabilities with SVMs"
"""
from __future__ import annotations

import csv
import math
import pathlib
from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.special import expit as sigmoid  # pylint: disable=no-name-in-module

from bve.config.constants import PHASE_SUCCESS_RATES

# ---------------------------------------------------------------------------
# Calibration result
# ---------------------------------------------------------------------------

_DATASET_PATH = pathlib.Path(__file__).parent.parent.parent.parent / "research" / "data" / "oncology_phase_transitions.csv"


@dataclass(frozen=True)
class CalibrationResult:
    """
    Fitted Platt-scaling calibration layer.

    calibrated_pos = sigmoid(slope * logit(raw_pos) + intercept)

    Attributes
    ----------
    n_samples : int
        Number of observations used to fit.
    slope : float
        Logit-space multiplier. ~1.0 = well-calibrated; >1 = under-confident;
        <1 = over-confident.
    intercept : float
        Logit-space bias. >0 = optimistic bias; <0 = pessimistic bias.
    brier_score_raw : float
        Brier score of raw (uncalibrated) POS predictions on training set.
    brier_score_calibrated : float
        Brier score of Platt-calibrated predictions on training set (in-sample).
    ece_raw : float
        Expected calibration error of raw predictions (10 equal-width bins).
    ece_calibrated : float
        Expected calibration error after Platt scaling.
    mean_raw_pos : float
        Mean raw POS across dataset (diagnostic for overall bias).
    mean_outcome : float
        Empirical success rate in dataset.
    """
    n_samples: int
    slope: float
    intercept: float
    brier_score_raw: float
    brier_score_calibrated: float
    ece_raw: float
    ece_calibrated: float
    mean_raw_pos: float
    mean_outcome: float

    @property
    def calibration_improvement(self) -> float:
        """Fractional reduction in Brier score: (raw - cal) / raw."""
        if self.brier_score_raw <= 0:
            return 0.0
        return (self.brier_score_raw - self.brier_score_calibrated) / self.brier_score_raw

    @property
    def is_over_confident(self) -> bool:
        return self.slope < 0.90

    @property
    def is_under_confident(self) -> bool:
        return self.slope > 1.10

    @property
    def net_bias(self) -> str:
        if self.intercept > 0.10:
            return "optimistic"
        if self.intercept < -0.10:
            return "pessimistic"
        return "neutral"


# ---------------------------------------------------------------------------
# Feature-to-raw-POS mapping
# ---------------------------------------------------------------------------

# Map CSV column values to log-odds adjusters (same calibration as pos_model.py)
_MOA_LOGODDS: dict[str, float] = {
    "novel": -0.35,
    "partial": 0.00,
    "established": +0.35,
    "validated": +0.35,
}

_SAFETY_LOGODDS: dict[str, float] = {
    "clean": +0.15,
    "minor": 0.00,
    "moderate": -0.10,
    "concerning": -0.25,
    "serious": -0.40,
}

_COMPETITION_LOGODDS: dict[str, float] = {
    "low": +0.10,
    "moderate": 0.00,
    "high": -0.20,
}

_ENDPOINT_LOGODDS: dict[str, float] = {
    "surrogate_validated": +0.15,
    "hard_clinical": 0.00,
    "other": -0.10,
}

_PHASE_KEY_MAP: dict[str, str] = {
    "phase_1": "phase_1",
    "phase_2": "phase_2",
    "phase_3": "phase_3",
}


def _raw_pos_from_row(row: dict) -> float:
    """
    Compute raw POS from a CSV row using log-odds adjusters.

    Returns a float in (0, 1).
    """
    phase_key = _PHASE_KEY_MAP.get(row.get("phase_start", "phase_2"), "phase_2")
    # Use oncology base rate
    base_rate = PHASE_SUCCESS_RATES.get("oncology", {}).get(phase_key, 0.40)
    base_logodds = math.log(base_rate / (1 - base_rate))

    moa = row.get("moa_precedent", "partial").lower()
    safety = row.get("safety_profile", "minor").lower()
    competition = row.get("competitive_pressure", "moderate").lower()
    endpoint = row.get("endpoint_type", "hard_clinical").lower()
    biomarker = row.get("biomarker_enriched", "false").lower() in {"true", "1", "yes"}

    adj = (
        _MOA_LOGODDS.get(moa, 0.0)
        + _SAFETY_LOGODDS.get(safety, 0.0)
        + _COMPETITION_LOGODDS.get(competition, 0.0)
        + _ENDPOINT_LOGODDS.get(endpoint, 0.0)
        + (0.40 if biomarker else 0.0)
    )

    final_logodds = base_logodds + adj
    return float(sigmoid(final_logodds))


def _outcome_to_binary(outcome: str) -> int:
    """
    Map outcome string to binary success label.

    "approved" → 1 (full success)
    "advanced" → 1 (program advanced / accelerated approval)
    "failed"   → 0
    """
    return 1 if outcome.lower() in {"approved", "advanced"} else 0


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------

def load_oncology_dataset(
    path: Optional[pathlib.Path] = None,
) -> tuple[list[float], list[int]]:
    """
    Load the N=99 oncology phase-transition dataset and return (raw_pos, outcomes).

    Parameters
    ----------
    path : Path, optional
        Override default dataset path. Uses research/data/oncology_phase_transitions.csv
        by default.

    Returns
    -------
    raw_pos_list : list[float]
        Model-predicted POS for each program.
    outcomes : list[int]
        Binary success labels (1 = advanced/approved, 0 = failed).
    """
    csv_path = path or _DATASET_PATH
    raw_pos_list: list[float] = []
    outcomes: list[int] = []

    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            raw_pos_list.append(_raw_pos_from_row(row))
            outcomes.append(_outcome_to_binary(row.get("outcome", "failed")))

    return raw_pos_list, outcomes


# ---------------------------------------------------------------------------
# Calibration fitting
# ---------------------------------------------------------------------------

def _brier_score(probs: np.ndarray, outcomes: np.ndarray) -> float:
    return float(np.mean((probs - outcomes) ** 2))


def _ece(probs: np.ndarray, outcomes: np.ndarray, n_bins: int = 10) -> float:
    """Expected Calibration Error (equal-width bins)."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    total = len(probs)
    ece_val = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (probs >= lo) & (probs < hi)
        if mask.sum() == 0:
            continue
        frac = mask.sum() / total
        mean_conf = float(np.mean(probs[mask]))
        mean_acc = float(np.mean(outcomes[mask]))
        ece_val += frac * abs(mean_conf - mean_acc)
    return ece_val


def fit_calibration(
    raw_pos_list: list[float],
    outcomes: list[int],
) -> CalibrationResult:
    """
    Fit Platt scaling: logit-space linear regression of raw_pos on outcome.

    Minimises negative log-likelihood:
        -Σ [ y*log(σ(a*logit(p) + b)) + (1-y)*log(1-σ(a*logit(p) + b)) ]

    Uses scipy.optimize for the 2-parameter fit (slope, intercept).

    Parameters
    ----------
    raw_pos_list : list[float]
        Raw (uncalibrated) model predictions in (0, 1).
    outcomes : list[int]
        Binary labels (1 = success, 0 = failure).

    Returns
    -------
    CalibrationResult
    """
    raw = np.clip(np.array(raw_pos_list, dtype=float), 1e-6, 1 - 1e-6)
    y = np.array(outcomes, dtype=float)
    logit_raw = np.log(raw / (1 - raw))

    def neg_log_likelihood(params: np.ndarray) -> float:
        a, b = params
        p = sigmoid(a * logit_raw + b)
        p = np.clip(p, 1e-9, 1 - 1e-9)
        return -float(np.sum(y * np.log(p) + (1 - y) * np.log(1 - p)))

    from scipy.optimize import minimize
    result = minimize(
        neg_log_likelihood,
        x0=np.array([1.0, 0.0]),
        method="L-BFGS-B",
    )
    slope, intercept = float(result.x[0]), float(result.x[1])

    cal_probs = sigmoid(slope * logit_raw + intercept)
    brier_raw = _brier_score(raw, y)
    brier_cal = _brier_score(cal_probs, y)
    ece_raw = _ece(raw, y)
    ece_cal = _ece(cal_probs, y)

    return CalibrationResult(
        n_samples=len(raw_pos_list),
        slope=slope,
        intercept=intercept,
        brier_score_raw=round(brier_raw, 6),
        brier_score_calibrated=round(brier_cal, 6),
        ece_raw=round(ece_raw, 6),
        ece_calibrated=round(ece_cal, 6),
        mean_raw_pos=round(float(np.mean(raw)), 4),
        mean_outcome=round(float(np.mean(y)), 4),
    )


# ---------------------------------------------------------------------------
# Apply calibration
# ---------------------------------------------------------------------------

def calibrate_pos(raw_pos: float, result: CalibrationResult) -> float:
    """
    Apply Platt-scaling calibration to a raw POS prediction.

    Parameters
    ----------
    raw_pos : float
        Raw model prediction in (0, 1).
    result : CalibrationResult
        Fitted calibration parameters.

    Returns
    -------
    float
        Calibrated probability in (0, 1).
    """
    raw_clipped = max(1e-6, min(1 - 1e-6, raw_pos))
    logit_raw = math.log(raw_clipped / (1 - raw_clipped))
    cal_logit = result.slope * logit_raw + result.intercept
    return float(sigmoid(cal_logit))


# ---------------------------------------------------------------------------
# Convenience class
# ---------------------------------------------------------------------------

class POSCalibrationLayer:
    """
    Fits and applies Platt-scaling calibration using the oncology dataset.

    Usage
    -----
    >>> layer = POSCalibrationLayer()
    >>> cal = layer.fit_on_oncology_dataset()
    >>> calibrated = layer.calibrate(raw_pos=0.55)
    """

    def __init__(self, dataset_path: Optional[pathlib.Path] = None) -> None:
        self._path = dataset_path
        self._result: Optional[CalibrationResult] = None

    @property
    def is_fitted(self) -> bool:
        return self._result is not None

    @property
    def result(self) -> CalibrationResult:
        if self._result is None:
            raise RuntimeError("POSCalibrationLayer not fitted. Call fit_on_oncology_dataset() first.")
        return self._result

    def fit_on_oncology_dataset(self) -> CalibrationResult:
        """Load dataset and fit calibration. Returns CalibrationResult."""
        raw_pos_list, outcomes = load_oncology_dataset(self._path)
        self._result = fit_calibration(raw_pos_list, outcomes)
        return self._result

    def calibrate(self, raw_pos: float) -> float:
        """Calibrate a raw POS prediction. Raises RuntimeError if not fitted."""
        return calibrate_pos(raw_pos, self.result)
