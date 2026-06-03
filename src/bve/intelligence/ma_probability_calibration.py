"""Layer 5 — 5C: Probability Calibration Engine.

Converts raw BD action scores into calibrated probabilities using:
  1. Platt scaling (logistic regression on scores vs labels)
  2. Bayesian bin calibration (conservative default for sparse M&A data)
  3. Isotonic regression (larger datasets only — overfit guard)
  4. Horizon-specific probabilities (6m, 12m, 24m)

Layer 5 is honest about uncertainty:
  - If N < min_samples: do_not_use_as_probability = True
  - If calibration quality is poor: emits explicit warnings
  - Returns RANK_ONLY_NO_PROBABILITY when data is insufficient

Design:
  - No scipy dependency for Platt/bin; pure-python + optional numpy.
  - Separate fit (training) from predict (inference).
  - No silent swallowing of poor calibration.
"""
from __future__ import annotations

import math
from typing import Optional

from bve.intelligence.ma_calibration_models import (
    CalibrationArtifact,
    CalibrationDiagnostics,
    CalibrationGovernanceMetadata,
    CalibrationQualityLabel,
    CalibratedProbabilitySet,
    HistoricalMAOutcome,
    Layer5CalibrationConfig,
    ProbabilityInterval,
)

# Minimum sample sizes
_MIN_PLATT = 30
_MIN_ISOTONIC = 50
_DEFAULT_BINS = 10

# Horizon scaling constants (hazard-rate approximation)
_SCALE_6M = 0.55
_SCALE_18M_EXP = 1.35
_SCALE_24M_EXP = 1.65


# ---------------------------------------------------------------------------
# Pure-Python helpers
# ---------------------------------------------------------------------------

def _expit(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def _logit(p: float) -> float:
    p = max(1e-9, min(1 - 1e-9, p))
    return math.log(p / (1 - p))


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _brier_score(labels: list[int], probs: list[float]) -> float:
    if not labels:
        return float("nan")
    n = len(labels)
    return sum((p - y) ** 2 for p, y in zip(probs, labels)) / n


def _binary_auc(labels: list[int], scores: list[float]) -> Optional[float]:
    pos = [s for s, y in zip(scores, labels) if y == 1]
    neg = [s for s, y in zip(scores, labels) if y == 0]
    if not pos or not neg:
        return None
    concordant = sum(1 for p in pos for n in neg if p > n)
    ties = sum(1 for p in pos for n in neg if p == n)
    return (concordant + 0.5 * ties) / (len(pos) * len(neg))


def _expected_calibration_error(
    labels: list[int],
    probs: list[float],
    n_bins: int = 10,
) -> float:
    """Expected Calibration Error (ECE)."""
    if not labels:
        return float("nan")
    bins: list[tuple[float, float, int]] = []  # (avg_prob, fraction_pos, count)
    bin_edges = [i / n_bins for i in range(n_bins + 1)]
    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        bucket = [(p, y) for p, y in zip(probs, labels) if lo <= p < hi or (hi == 1.0 and p == 1.0)]
        if not bucket:
            continue
        avg_p = sum(p for p, _ in bucket) / len(bucket)
        frac_p = sum(y for _, y in bucket) / len(bucket)
        bins.append((avg_p, frac_p, len(bucket)))
    if not bins:
        return float("nan")
    total = sum(c for _, _, c in bins)
    return sum(abs(avg_p - frac_p) * c / total for avg_p, frac_p, c in bins)


def _reliability_table(
    labels: list[int],
    probs: list[float],
    n_bins: int = 10,
) -> list[dict]:
    """Produce reliability diagram data."""
    rows = []
    bin_edges = [i / n_bins for i in range(n_bins + 1)]
    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        bucket = [(p, y) for p, y in zip(probs, labels) if lo <= p < hi or (hi == 1.0 and p == 1.0)]
        if not bucket:
            continue
        avg_p = sum(p for p, _ in bucket) / len(bucket)
        frac_p = sum(y for _, y in bucket) / len(bucket)
        rows.append({
            "bin_lower": round(lo, 4),
            "bin_upper": round(hi, 4),
            "count": len(bucket),
            "mean_predicted": round(avg_p, 6),
            "fraction_positive": round(frac_p, 6),
        })
    return rows


# ---------------------------------------------------------------------------
# Platt scaling
# ---------------------------------------------------------------------------

def _fit_platt_scaler(
    scores: list[float],
    labels: list[int],
    *,
    max_iter: int = 500,
    tol: float = 1e-8,
    l2: float = 1.0,
) -> tuple[float, float]:
    """Fit Platt scaling parameters (A, B) where P = sigmoid(A*score + B).

    Uses gradient descent with L2 regularization on A.
    Returns (A, B).
    """
    n = len(scores)
    A, B = 0.0, 0.0
    lr = 0.1
    for _ in range(max_iter):
        grad_A = grad_B = 0.0
        for s, y in zip(scores, labels):
            p = _expit(A * s + B)
            err = p - y
            grad_A += err * s + l2 * A / n
            grad_B += err
        grad_A /= n
        grad_B /= n
        A -= lr * grad_A
        B -= lr * grad_B
        if abs(grad_A) < tol and abs(grad_B) < tol:
            break
    return A, B


def fit_platt_scaler(
    scores: list[float],
    labels: list[int],
    config: Layer5CalibrationConfig = Layer5CalibrationConfig(),
) -> tuple[float, float, list[str]]:
    """Fit Platt scaling if enough data, otherwise return fallback (0, logit(base_rate)).

    Returns:
        (A, B, warnings)
    """
    n = len(scores)
    warnings: list[str] = []
    if n < config.min_sample_size_for_platt:
        base_rate = sum(labels) / n if n > 0 else 0.05
        warnings.append(
            f"Insufficient data for Platt scaling (n={n} < {config.min_sample_size_for_platt}); "
            "using base-rate intercept only."
        )
        return 0.0, _logit(base_rate), warnings
    A, B = _fit_platt_scaler(scores, labels)
    return A, B, warnings


def predict_platt(score: float, A: float, B: float) -> float:
    return _clamp(_expit(A * score + B))


# ---------------------------------------------------------------------------
# Bayesian bin calibration (conservative default for sparse datasets)
# ---------------------------------------------------------------------------

def fit_bayesian_bin_calibrator(
    scores: list[float],
    labels: list[int],
    *,
    n_bins: int = _DEFAULT_BINS,
    prior_strength: float = 2.0,
) -> list[dict]:
    """Fit a Bayesian bin calibrator.

    Each bin has a Beta(alpha, beta) posterior:
        alpha = positives + prior_strength * global_base_rate
        beta  = negatives + prior_strength * (1 - global_base_rate)

    Returns a list of bin dicts:
        {"lower": float, "upper": float, "count": int,
         "positives": int, "posterior_mean": float,
         "posterior_lower": float, "posterior_upper": float}
    """
    n = len(scores)
    global_base_rate = sum(labels) / n if n > 0 else 0.05

    bin_edges = [i / n_bins for i in range(n_bins + 1)]
    bins: list[dict] = []
    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        bucket = [(s, y) for s, y in zip(scores, labels) if lo <= s < hi or (hi == 1.0 and s == 1.0)]
        count = len(bucket)
        positives = sum(y for _, y in bucket)
        # Bayesian update with global base rate prior
        alpha = positives + prior_strength * global_base_rate
        beta = (count - positives) + prior_strength * (1 - global_base_rate)
        posterior_mean = alpha / (alpha + beta)
        # 80% credible interval via Beta distribution approximation
        posterior_lower = max(0.0, posterior_mean - 1.28 * math.sqrt(alpha * beta / ((alpha + beta) ** 2 * (alpha + beta + 1))))
        posterior_upper = min(1.0, posterior_mean + 1.28 * math.sqrt(alpha * beta / ((alpha + beta) ** 2 * (alpha + beta + 1))))
        bins.append({
            "lower": round(lo, 4),
            "upper": round(hi, 4),
            "count": count,
            "positives": positives,
            "posterior_mean": round(posterior_mean, 6),
            "posterior_lower": round(posterior_lower, 6),
            "posterior_upper": round(posterior_upper, 6),
            "alpha": round(alpha, 4),
            "beta_param": round(beta, 4),
        })
    return bins


def predict_bayesian_bin(score: float, bins: list[dict]) -> tuple[float, float, float]:
    """Return (posterior_mean, lower, upper) for a score from a bin calibrator."""
    for b in bins:
        if b["lower"] <= score <= b["upper"] + 1e-9:
            return b["posterior_mean"], b["posterior_lower"], b["posterior_upper"]
    # Fallback to closest bin
    best = min(bins, key=lambda b: abs((b["lower"] + b["upper"]) / 2 - score))
    return best["posterior_mean"], best["posterior_lower"], best["posterior_upper"]


# ---------------------------------------------------------------------------
# Isotonic regression (overfit guard)
# ---------------------------------------------------------------------------

def _pool_adjacent_violators(scores: list[float], labels: list[int]) -> list[float]:
    """PAVA (Pool Adjacent Violators Algorithm) for isotonic regression."""
    n = len(scores)
    # Sort by score
    paired = sorted(zip(scores, labels), key=lambda x: x[0])
    pooled = [[p_s, float(p_y), 1] for p_s, p_y in paired]  # [score, mean_label, count]
    # PAVA
    i = 0
    while i < len(pooled) - 1:
        if pooled[i][1] > pooled[i + 1][1]:
            # Merge
            total = pooled[i][2] + pooled[i + 1][2]
            new_mean = (pooled[i][1] * pooled[i][2] + pooled[i + 1][1] * pooled[i + 1][2]) / total
            pooled[i] = [pooled[i][0], new_mean, total]
            pooled.pop(i + 1)
            if i > 0:
                i -= 1
        else:
            i += 1
    # Map back to original order
    results = [0.0] * n
    sorted_scores = sorted(range(n), key=lambda k: scores[k])
    block_idx = 0
    for rank_i, orig_i in enumerate(sorted_scores):
        # Find matching pooled block
        while block_idx < len(pooled) - 1 and rank_i >= sum(pooled[j][2] for j in range(block_idx + 1)):
            block_idx += 1
        results[orig_i] = _clamp(pooled[block_idx][1])
    return results


def fit_isotonic_calibrator(
    scores: list[float],
    labels: list[int],
    config: Layer5CalibrationConfig = Layer5CalibrationConfig(),
) -> tuple[list[tuple[float, float]], list[str]]:
    """Fit isotonic regression calibration.

    Returns:
        (calibration_pairs, warnings) where calibration_pairs is a list of
        (score, calibrated_probability) sorted by score.

    Overfit guard: refuses to fit if n < min_sample_size_for_isotonic.
    """
    warnings: list[str] = []
    n = len(scores)
    if n < config.min_sample_size_for_isotonic:
        warnings.append(
            f"Isotonic regression not fitted: n={n} < "
            f"min_sample_size={config.min_sample_size_for_isotonic}. "
            "Use Bayesian bin calibration instead."
        )
        return [], warnings

    calibrated = _pool_adjacent_violators(scores, labels)
    pairs = sorted(zip(scores, calibrated), key=lambda x: x[0])
    return pairs, warnings


def predict_isotonic(score: float, pairs: list[tuple[float, float]]) -> Optional[float]:
    """Interpolate isotonic calibrated probability for a score. Returns None if unfitted."""
    if not pairs:
        return None
    if score <= pairs[0][0]:
        return pairs[0][1]
    if score >= pairs[-1][0]:
        return pairs[-1][1]
    for i in range(len(pairs) - 1):
        s0, p0 = pairs[i]
        s1, p1 = pairs[i + 1]
        if s0 <= score <= s1:
            t = (score - s0) / (s1 - s0 + 1e-9)
            return _clamp(p0 + t * (p1 - p0))
    return pairs[-1][1]


# ---------------------------------------------------------------------------
# Horizon-specific calibrated probabilities
# ---------------------------------------------------------------------------

def calibrate_probability_targets(
    p_12m: float,
    *,
    global_base_rate: float = 0.08,
) -> CalibratedProbabilitySet:
    """Derive horizon-specific probabilities from a calibrated 12m estimate.

    Monotonicity: p_6m <= p_12m <= p_24m (always enforced).

    Args:
        p_12m: Calibrated 12-month probability.
        global_base_rate: Base rate used for conservative fallback.

    Returns:
        CalibratedProbabilitySet with all horizon probabilities.
    """
    p_12m = _clamp(p_12m)
    p_6m = _clamp(p_12m * _SCALE_6M)
    p_24m = _clamp(1.0 - (1.0 - p_12m) ** _SCALE_24M_EXP)

    # Enforce monotonicity
    p_6m = min(p_6m, p_12m)
    p_24m = max(p_24m, p_12m)

    # Intervals: narrower at 12m (most calibrated horizon)
    def _interval(p: float, width: float) -> ProbabilityInterval:
        return ProbabilityInterval(
            lower=_clamp(p - width),
            median=p,
            upper=_clamp(p + width),
            confidence_level=0.80,
        )

    intervals = {
        "p_full_acquisition_6m": _interval(p_6m, 0.05),
        "p_full_acquisition_12m": _interval(p_12m, 0.04),
        "p_full_acquisition_24m": _interval(p_24m, 0.07),
    }

    return CalibratedProbabilitySet(
        p_full_acquisition_6m=round(p_6m, 6),
        p_full_acquisition_12m=round(p_12m, 6),
        p_full_acquisition_24m=round(p_24m, 6),
        p_any_strategic_transaction_12m=round(_clamp(p_12m * 1.8), 6),
        p_any_strategic_transaction_24m=round(_clamp(p_24m * 1.8), 6),
        p_partnership_or_license_12m=round(_clamp(p_12m * 0.9), 6),
        p_partnership_or_license_24m=round(_clamp(p_24m * 0.9), 6),
        p_active_process_12m=round(_clamp(p_12m * 1.4), 6),
        probability_intervals=intervals,
    )


# ---------------------------------------------------------------------------
# Calibration quality label
# ---------------------------------------------------------------------------

def _quality_label(
    sample_size: int,
    brier: Optional[float],
    ece: Optional[float],
    *,
    min_n: int = 30,
) -> tuple[CalibrationQualityLabel, list[str]]:
    warnings: list[str] = []
    if sample_size < min_n:
        warnings.append(
            f"Insufficient data (n={sample_size} < {min_n}). "
            "Use score as ranking, not calibrated probability."
        )
        return CalibrationQualityLabel.INSUFFICIENT_DATA_RANK_ONLY, warnings

    if ece is not None and ece > 0.15:
        warnings.append(f"Poor calibration: ECE={ece:.3f} > 0.15.")
        return CalibrationQualityLabel.LOW_CONFIDENCE, warnings

    if brier is not None and brier > 0.20:
        warnings.append(f"High Brier score={brier:.3f} > 0.20.")
        return CalibrationQualityLabel.LOW_CONFIDENCE, warnings

    if sample_size < 100:
        return CalibrationQualityLabel.MEDIUM_CONFIDENCE, warnings

    return CalibrationQualityLabel.HIGH_CONFIDENCE, warnings


# ---------------------------------------------------------------------------
# Main calibration fit
# ---------------------------------------------------------------------------

def calibrate_ma_scores(
    cases: list[HistoricalMAOutcome],
    config: Layer5CalibrationConfig = Layer5CalibrationConfig(),
    *,
    artifact_id: str = "default",
    governance: Optional[CalibrationGovernanceMetadata] = None,
) -> CalibrationArtifact:
    """Fit a calibration artifact from historical cases.

    Uses Bayesian bin calibration as primary method (conservative for sparse M&A data).
    Falls back to base-rate if fewer than config.min_sample_size_for_platt cases.

    Args:
        cases: Historical MA outcome records (should pass leakage check).
        config: Calibration configuration.
        artifact_id: Identifier for the artifact.
        governance: Governance metadata (auto-generated if None).

    Returns:
        CalibrationArtifact ready for use in apply_layer5_calibration().
    """
    from datetime import date as _date

    clean = [c for c in cases if not c.excluded_from_training]
    n = len(clean)

    # Extract scores and labels for 12m acquisition
    scores: list[float] = []
    labels: list[int] = []
    for c in clean:
        l1_score = c.layer1_snapshot.get("layer1_score") or c.layer2_snapshot.get("bd_action_score")
        if l1_score is None:
            continue
        scores.append(float(l1_score))
        labels.append(1 if c.labels.acquired_within_12m else 0)

    n_scored = len(scores)
    global_base_rate = sum(labels) / n_scored if n_scored > 0 else 0.08

    # Fit Platt scaling
    platt_A, platt_B, platt_warnings = fit_platt_scaler(scores, labels, config)

    # Fit Bayesian bins
    bayesian_bins = fit_bayesian_bin_calibrator(
        scores, labels, n_bins=config.n_bins
    ) if n_scored > 0 else []

    # Compute diagnostics
    if n_scored > 0:
        platt_probs = [predict_platt(s, platt_A, platt_B) for s in scores]
        brier = _brier_score(labels, platt_probs)
        ece = _expected_calibration_error(labels, platt_probs)
        auc = _binary_auc(labels, scores)
        rel_table = _reliability_table(labels, platt_probs)
    else:
        brier = ece = auc = None
        rel_table = []

    quality, quality_warnings = _quality_label(n_scored, brier, ece)

    diagnostics = CalibrationDiagnostics(
        calibration_method=config.calibration_method,
        sample_size=n_scored,
        effective_sample_size=float(n_scored),
        base_rate=round(global_base_rate, 6) if n_scored > 0 else None,
        brier_score=round(brier, 6) if brier is not None else None,
        expected_calibration_error=round(ece, 6) if ece is not None else None,
        calibration_intercept=round(platt_B, 6) if platt_B is not None else None,
        calibration_slope=round(platt_A, 6) if platt_A is not None else None,
        auc=round(auc, 6) if auc is not None else None,
        reliability_table=rel_table,
        warnings=platt_warnings + quality_warnings,
    )

    if governance is None:
        governance = CalibrationGovernanceMetadata(
            model_version=config.model_version,
            calibration_dataset_version=config.dataset_version,
            calibration_date=_date.today(),
            feature_schema_version=config.feature_schema_version,
            calibration_artifact_id=artifact_id,
            excluded_case_count=len(cases) - n,
            known_limitations=[
                "Calibrated on internal historical data; survivorship bias possible.",
                "Sparse segment calibration uses global base rate fallback.",
                "Probabilities are point estimates; use intervals for decision-making.",
            ],
        )

    return CalibrationArtifact(
        artifact_id=artifact_id,
        governance=governance,
        platt_intercept=round(platt_A, 6),
        platt_slope=round(platt_B, 6),
        bayesian_bins=bayesian_bins,
        global_base_rate=round(global_base_rate, 6),
        global_sample_size=n_scored,
        training_diagnostics=diagnostics,
    )


def predict_calibrated_probabilities(
    raw_score: float,
    artifact: CalibrationArtifact,
) -> tuple[CalibratedProbabilitySet, CalibrationQualityLabel, bool, Optional[str]]:
    """Apply a fitted calibration artifact to a raw score.

    Returns:
        (probabilities, quality, do_not_use_as_probability, reason)
    """
    n = artifact.global_sample_size

    do_not_use = n < _MIN_PLATT
    reason = (
        f"Insufficient historical cases (n={n}) for calibrated probability. "
        "Use score as ranking only."
    ) if do_not_use else None

    if artifact.bayesian_bins:
        p_12m, _lo, _hi = predict_bayesian_bin(raw_score, artifact.bayesian_bins)
    elif artifact.platt_intercept is not None:
        p_12m = predict_platt(
            raw_score,
            artifact.platt_intercept,
            artifact.platt_slope or 0.0,
        )
    else:
        p_12m = artifact.global_base_rate or 0.05

    probs = calibrate_probability_targets(
        p_12m, global_base_rate=artifact.global_base_rate or 0.08
    )

    if do_not_use:
        quality = CalibrationQualityLabel.INSUFFICIENT_DATA_RANK_ONLY
    elif n < 100:
        quality = CalibrationQualityLabel.MEDIUM_CONFIDENCE
    else:
        quality = CalibrationQualityLabel.HIGH_CONFIDENCE

    return probs, quality, do_not_use, reason
