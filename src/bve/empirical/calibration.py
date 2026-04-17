"""
Calibration for empirical POS predictions.

Two interpretable methods are provided; no black-box models are used:

Platt scaling (default)
    Fits sigmoid(a · logit(p) + b) on the training split.
    Two parameters: scale (a) and bias (b).
    a=1, b=0 is the identity function — any deviation is explicit and inspectable.
    Uses scipy.optimize.minimize; no sklearn dependency.

Isotonic regression
    Pool Adjacent Violators Algorithm (PAVA) — a non-parametric monotone fit.
    Produces a piecewise-constant step function stored as (x, y) breakpoints.
    Fully inspectable: the breakpoints are the calibration map.
    No sklearn dependency; pure Python implementation.

Both methods produce a CalibrationArtifact that:
    - is JSON-serializable (to_dict / from_dict)
    - has an apply(p) method for prediction-time use
    - stores pre- and post-calibration metrics (Brier, ECE, AUC)
    - records the train/test split used to fit it

Usage
-----
from bve.empirical.calibration import fit_calibration, CalibrationArtifact

artifact = fit_calibration(
    predictions_train=raw_pos_train,
    outcomes_train=binary_outcomes_train,
    method="platt",
    predictions_test=raw_pos_test,
    outcomes_test=binary_outcomes_test,
)
calibrated = artifact.apply(0.42)
"""
from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, logit as scipy_logit

logger = logging.getLogger(__name__)

# Clip probabilities away from 0/1 to avoid ±∞ in logit
_CLIP_LOW = 1e-6
_CLIP_HIGH = 1.0 - 1e-6


# ---------------------------------------------------------------------------
# Metric helpers (mirror evaluator.py — kept local to avoid circular import)
# ---------------------------------------------------------------------------

def _brier(preds: list[float], outcomes: list[bool]) -> float:
    if not preds:
        return 0.0
    return sum((p - float(y)) ** 2 for p, y in zip(preds, outcomes)) / len(preds)


def _ece_scalar(preds: list[float], outcomes: list[bool], n_bins: int = 10) -> float:
    if not preds:
        return 0.0
    total = len(preds)
    ece = 0.0
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        in_bin = [(p, float(y)) for p, y in zip(preds, outcomes)
                  if lo <= p < hi or (b == n_bins - 1 and p == 1.0)]
        if not in_bin:
            continue
        mean_p = sum(x[0] for x in in_bin) / len(in_bin)
        obs_r = sum(x[1] for x in in_bin) / len(in_bin)
        ece += (len(in_bin) / total) * abs(mean_p - obs_r)
    return round(ece, 4)


def _auc_scalar(preds: list[float], outcomes: list[bool]) -> Optional[float]:
    n_pos = sum(outcomes)
    n_neg = len(outcomes) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    paired = sorted(zip(preds, outcomes), key=lambda x: -x[0])
    tpr, fpr = [0.0], [0.0]
    tp = fp = 0
    for p, y in paired:
        if y:
            tp += 1
        else:
            fp += 1
        tpr.append(tp / n_pos)
        fpr.append(fp / n_neg)
    auc = sum(
        (fpr[i] - fpr[i - 1]) * (tpr[i] + tpr[i - 1]) / 2
        for i in range(1, len(fpr))
    )
    return round(auc, 4)


# ---------------------------------------------------------------------------
# Platt scaling
# ---------------------------------------------------------------------------

def _fit_platt(
    preds: list[float],
    outcomes: list[bool],
) -> tuple[float, float, bool]:
    """
    Fit Platt scaling: sigmoid(a · logit(p) + b).

    Returns (a, b, converged).
    a ≈ 1 and b ≈ 0 means the predictions are already well-calibrated.
    """
    x = np.array([float(np.clip(p, _CLIP_LOW, _CLIP_HIGH)) for p in preds])
    logit_x = np.log(x / (1.0 - x))
    y = np.array([float(v) for v in outcomes])

    def neg_ll(params: np.ndarray) -> float:
        a, b = params
        p_hat = expit(a * logit_x + b)
        p_hat = np.clip(p_hat, 1e-12, 1.0 - 1e-12)
        return -float(np.sum(y * np.log(p_hat) + (1.0 - y) * np.log(1.0 - p_hat)))

    result = minimize(neg_ll, np.array([1.0, 0.0]), method="BFGS",
                      options={"maxiter": 500})
    a, b = result.x[0], result.x[1]
    return round(float(a), 6), round(float(b), 6), result.success


# ---------------------------------------------------------------------------
# Isotonic regression (PAVA — Pool Adjacent Violators Algorithm)
# ---------------------------------------------------------------------------

def _pava(y: list[float], w: Optional[list[float]] = None) -> list[float]:
    """
    Weighted isotonic regression (increasing) via PAVA.

    Parameters
    ----------
    y: target values
    w: optional weights (uniform if None)

    Returns
    -------
    Isotonic-constrained fitted values (same length as y, non-decreasing).
    """
    n = len(y)
    if n == 0:
        return []
    if w is None:
        w = [1.0] * n

    # Work with blocks: each block = (sum_wy, sum_w) representing mean = sum_wy/sum_w
    blocks: list[tuple[float, float]] = [(y[i] * w[i], w[i]) for i in range(n)]

    changed = True
    while changed:
        changed = False
        i = 0
        new_blocks: list[tuple[float, float]] = []
        while i < len(blocks):
            if i + 1 < len(blocks):
                mean_i = blocks[i][0] / blocks[i][1]
                mean_next = blocks[i + 1][0] / blocks[i + 1][1]
                if mean_i > mean_next:
                    # Merge: weighted average must be non-decreasing
                    merged_wy = blocks[i][0] + blocks[i + 1][0]
                    merged_w = blocks[i][1] + blocks[i + 1][1]
                    new_blocks.append((merged_wy, merged_w))
                    i += 2
                    changed = True
                    continue
            new_blocks.append(blocks[i])
            i += 1
        blocks = new_blocks

    # Expand back to n values
    result: list[float] = []
    idx = 0
    w_remaining = list(w)
    for sum_wy, sum_w in blocks:
        block_mean = sum_wy / sum_w
        block_n = round(sum_w)  # works for integer weights
        for _ in range(block_n):
            result.append(block_mean)
    # Fallback: if rounding causes length mismatch, pad/trim
    while len(result) < n:
        result.append(result[-1] if result else 0.5)
    return result[:n]


def _fit_isotonic(
    preds: list[float],
    outcomes: list[bool],
) -> tuple[list[float], list[float]]:
    """
    Fit isotonic regression calibration.

    Returns (x_breaks, y_breaks) — breakpoints of the step function.
    x_breaks: sorted input probabilities at which calibrated output changes.
    y_breaks: calibrated output values at each breakpoint.

    To calibrate a new prediction p: find the nearest x_breaks value
    and return the corresponding y_breaks value.
    """
    # Sort by prediction
    sorted_pairs = sorted(zip(preds, outcomes), key=lambda x: x[0])
    sorted_preds = [x[0] for x in sorted_pairs]
    sorted_outcomes = [float(x[1]) for x in sorted_pairs]

    fitted = _pava(sorted_outcomes)

    # Deduplicate breakpoints (keep unique x → y mapping)
    x_breaks: list[float] = []
    y_breaks: list[float] = []
    prev_y = None
    for x, y in zip(sorted_preds, fitted):
        if y != prev_y:
            x_breaks.append(round(x, 6))
            y_breaks.append(round(y, 6))
            prev_y = y

    return x_breaks, y_breaks


def _apply_isotonic(p: float, x_breaks: list[float], y_breaks: list[float]) -> float:
    """
    Apply isotonic calibration to a single probability.

    Interpolates linearly between the two nearest breakpoints.
    Extrapolates flat beyond the ends.
    """
    if not x_breaks:
        return p
    if p <= x_breaks[0]:
        return y_breaks[0]
    if p >= x_breaks[-1]:
        return y_breaks[-1]
    # Binary search
    lo, hi = 0, len(x_breaks) - 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if x_breaks[mid] <= p:
            lo = mid
        else:
            hi = mid
    # Linear interpolation between lo and hi
    x0, x1 = x_breaks[lo], x_breaks[hi]
    y0, y1 = y_breaks[lo], y_breaks[hi]
    if x1 == x0:
        return y0
    t = (p - x0) / (x1 - x0)
    return round(y0 + t * (y1 - y0), 6)


# ---------------------------------------------------------------------------
# CalibrationArtifact
# ---------------------------------------------------------------------------

@dataclass
class CalibrationArtifact:
    """
    Inspectable calibration artifact for empirical POS predictions.

    All fields are plain Python scalars/lists — fully JSON-serializable
    via to_dict() / from_dict().

    Platt scaling: apply(p) = sigmoid(platt_a · logit(p) + platt_b)
    Isotonic:      apply(p) = piecewise-linear interpolation on breakpoints
    """
    method: str   # "platt" or "isotonic"

    # Training provenance
    n_train: int
    cutoff_year: Optional[int] = None  # when time-split was used

    # Platt parameters (None when method="isotonic")
    platt_a: Optional[float] = None
    platt_b: Optional[float] = None
    platt_converged: Optional[bool] = None

    # Isotonic breakpoints (None when method="platt")
    isotonic_x: Optional[list[float]] = None
    isotonic_y: Optional[list[float]] = None

    # Pre-calibration metrics (on training set)
    train_brier_raw: float = 0.0
    train_brier_calibrated: float = 0.0
    train_ece_raw: float = 0.0
    train_ece_calibrated: float = 0.0
    train_auc: Optional[float] = None

    # Post-calibration metrics (on held-out test set, if provided)
    n_test: Optional[int] = None
    test_brier_raw: Optional[float] = None
    test_brier_calibrated: Optional[float] = None
    test_ece_raw: Optional[float] = None
    test_ece_calibrated: Optional[float] = None
    test_auc: Optional[float] = None

    def apply(self, p: float) -> float:
        """Apply calibration to a single probability in (0, 1)."""
        p = float(np.clip(p, _CLIP_LOW, _CLIP_HIGH))
        if self.method == "platt":
            assert self.platt_a is not None and self.platt_b is not None
            logit_p = math.log(p / (1.0 - p))
            return round(float(expit(self.platt_a * logit_p + self.platt_b)), 6)
        elif self.method == "isotonic":
            assert self.isotonic_x is not None and self.isotonic_y is not None
            return _apply_isotonic(p, self.isotonic_x, self.isotonic_y)
        else:
            raise ValueError(f"Unknown calibration method: {self.method!r}")

    def calibration_summary(self) -> str:
        """Multi-line human-readable summary."""
        lines = [
            f"CalibrationArtifact — method={self.method}",
            f"  n_train={self.n_train}",
        ]
        if self.method == "platt":
            lines.append(f"  Platt: a={self.platt_a}, b={self.platt_b} (converged={self.platt_converged})")
        elif self.method == "isotonic":
            n_breaks = len(self.isotonic_x) if self.isotonic_x else 0
            lines.append(f"  Isotonic: {n_breaks} breakpoints")
        lines += [
            f"  Train Brier: {self.train_brier_raw:.4f} → {self.train_brier_calibrated:.4f}",
            f"  Train ECE  : {self.train_ece_raw:.4f} → {self.train_ece_calibrated:.4f}",
        ]
        if self.test_brier_raw is not None:
            lines += [
                f"  Test  Brier: {self.test_brier_raw:.4f} → {self.test_brier_calibrated:.4f}",
                f"  Test  ECE  : {self.test_ece_raw:.4f} → {self.test_ece_calibrated:.4f}",
            ]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """JSON-serializable representation."""
        return {
            "method": self.method,
            "n_train": self.n_train,
            "cutoff_year": self.cutoff_year,
            "platt_a": self.platt_a,
            "platt_b": self.platt_b,
            "platt_converged": self.platt_converged,
            "isotonic_x": self.isotonic_x,
            "isotonic_y": self.isotonic_y,
            "train_brier_raw": self.train_brier_raw,
            "train_brier_calibrated": self.train_brier_calibrated,
            "train_ece_raw": self.train_ece_raw,
            "train_ece_calibrated": self.train_ece_calibrated,
            "train_auc": self.train_auc,
            "n_test": self.n_test,
            "test_brier_raw": self.test_brier_raw,
            "test_brier_calibrated": self.test_brier_calibrated,
            "test_ece_raw": self.test_ece_raw,
            "test_ece_calibrated": self.test_ece_calibrated,
            "test_auc": self.test_auc,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CalibrationArtifact":
        """Reconstruct from a dict (e.g., loaded from JSON)."""
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Fitting function
# ---------------------------------------------------------------------------

def fit_calibration(
    predictions_train: list[float],
    outcomes_train: list[bool],
    method: str = "platt",
    predictions_test: Optional[list[float]] = None,
    outcomes_test: Optional[list[bool]] = None,
    cutoff_year: Optional[int] = None,
) -> CalibrationArtifact:
    """
    Fit a calibration model on training predictions and evaluate on test set.

    Parameters
    ----------
    predictions_train:
        Raw (pre-calibration) POS predictions for training records.
    outcomes_train:
        Binary outcomes for training records.
    method:
        "platt" (default) or "isotonic".
    predictions_test:
        Optional held-out predictions for evaluation.
    outcomes_test:
        Optional held-out outcomes for evaluation.
    cutoff_year:
        Year boundary used for the train/test split (for documentation only).

    Returns
    -------
    CalibrationArtifact

    Raises
    ------
    ValueError when there are fewer than 10 training examples or only one class.
    """
    if len(predictions_train) < 10:
        raise ValueError(
            f"Need at least 10 training samples for calibration, got {len(predictions_train)}. "
            "Use more records or reduce the train/test split cutoff."
        )
    n_pos = sum(outcomes_train)
    if n_pos == 0 or n_pos == len(outcomes_train):
        raise ValueError(
            "Training set has only one outcome class — calibration requires both success and failure examples."
        )

    # Pre-calibration metrics
    raw_brier_train = round(_brier(predictions_train, outcomes_train), 4)
    raw_ece_train = _ece_scalar(predictions_train, outcomes_train)
    raw_auc_train = _auc_scalar(predictions_train, outcomes_train)

    # Fit
    platt_a = platt_b = platt_converged = None
    isotonic_x = isotonic_y = None

    if method == "platt":
        platt_a, platt_b, platt_converged = _fit_platt(predictions_train, outcomes_train)
        calibrated_train = [
            float(expit(platt_a * math.log(max(_CLIP_LOW, min(_CLIP_HIGH, p)) /
                                           (1.0 - max(_CLIP_LOW, min(_CLIP_HIGH, p)))) + platt_b))
            for p in predictions_train
        ]
    elif method == "isotonic":
        isotonic_x, isotonic_y = _fit_isotonic(predictions_train, outcomes_train)
        calibrated_train = [_apply_isotonic(p, isotonic_x, isotonic_y) for p in predictions_train]
    else:
        raise ValueError(f"Unknown method {method!r}. Use 'platt' or 'isotonic'.")

    calib_brier_train = round(_brier(calibrated_train, outcomes_train), 4)
    calib_ece_train = _ece_scalar(calibrated_train, outcomes_train)

    # Build artifact
    artifact = CalibrationArtifact(
        method=method,
        n_train=len(predictions_train),
        cutoff_year=cutoff_year,
        platt_a=platt_a,
        platt_b=platt_b,
        platt_converged=platt_converged,
        isotonic_x=isotonic_x,
        isotonic_y=isotonic_y,
        train_brier_raw=raw_brier_train,
        train_brier_calibrated=calib_brier_train,
        train_ece_raw=raw_ece_train,
        train_ece_calibrated=calib_ece_train,
        train_auc=raw_auc_train,
    )

    # Evaluate on test set if provided
    if predictions_test is not None and outcomes_test is not None:
        if len(predictions_test) > 0:
            calibrated_test = [artifact.apply(p) for p in predictions_test]
            artifact.n_test = len(predictions_test)
            artifact.test_brier_raw = round(_brier(predictions_test, outcomes_test), 4)
            artifact.test_brier_calibrated = round(_brier(calibrated_test, outcomes_test), 4)
            artifact.test_ece_raw = _ece_scalar(predictions_test, outcomes_test)
            artifact.test_ece_calibrated = _ece_scalar(calibrated_test, outcomes_test)
            artifact.test_auc = _auc_scalar(predictions_test, outcomes_test)

    return artifact


def fit_calibration_time_split(
    engine,                   # EmpiricalPOSEngine
    records: list,            # list[POSOutcomeRecord]
    cutoff_year: int,
    method: str = "platt",
) -> CalibrationArtifact:
    """
    Convenience wrapper: fit calibration using a temporal train/test split.

    Records with outcome_date < cutoff_year → train.
    Records with outcome_date >= cutoff_year → test.

    Parameters
    ----------
    engine:
        EmpiricalPOSEngine used to generate raw predictions.
    records:
        All outcome records.
    cutoff_year:
        Year boundary for the split.
    method:
        "platt" or "isotonic".

    Returns
    -------
    CalibrationArtifact with train+test metrics.
    """
    train_recs, test_recs = [], []
    for rec in records:
        try:
            yr = int(rec.outcome_date) if rec.outcome_date else None
        except (ValueError, TypeError):
            yr = None
        (train_recs if yr is None or yr < cutoff_year else test_recs).append(rec)

    def _batch_predict(recs):
        return [
            engine.compute_pos_with_adjusters(
                phase=rec.phase_at_entry,
                adjusters=None,
            )
            for rec in recs
        ]

    train_preds = _batch_predict(train_recs)
    test_preds = _batch_predict(test_recs)
    train_outcomes = [r.success for r in train_recs]
    test_outcomes = [r.success for r in test_recs]

    return fit_calibration(
        predictions_train=train_preds,
        outcomes_train=train_outcomes,
        method=method,
        predictions_test=test_preds if test_recs else None,
        outcomes_test=test_outcomes if test_recs else None,
        cutoff_year=cutoff_year,
    )
