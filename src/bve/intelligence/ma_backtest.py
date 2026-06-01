"""M&A Backtest and Calibration Fitting — Block 7.

Evaluates historical M&A scores against 12-month acquisition outcomes,
fits logistic calibration parameters (slope + midpoint), and provides
base-rate adjustment for deployment-time prior shifts.

Design principles
-----------------
- Pure-Python; no scipy or sklearn dependency.
- All metric functions are self-contained and unit-testable.
- ``fit_logistic_calibration`` uses Platt scaling (gradient descent) to fit
  P = sigmoid(slope * (score - midpoint)).
- Calibration params are persisted to JSON with full metadata so every
  fitted model is traceable.
- ``load_calibration_params`` falls back to the hard-coded defaults in
  ma_layer5_calibration.py if no fitted file exists, but emits a warning
  so the caller knows the constants are un-validated.
- ``adjust_for_base_rate`` corrects for the difference between training set
  base rate and deployment-time base rate using the standard log-odds
  prior-shift formula.

Usage
-----
    from bve.intelligence.ma_backtest import (
        MABacktestRecord,
        run_backtest,
        fit_logistic_calibration,
        save_calibration_params,
        load_calibration_params,
        build_backtest_records_from_deal_universe,
        adjust_for_base_rate,
    )

    records = build_backtest_records_from_deal_universe()
    result = run_backtest(records)
    params = fit_logistic_calibration(records)
    save_calibration_params(params, "ma_calibration_params.json")
    slope, midpoint = load_calibration_params("ma_calibration_params.json")
"""
from __future__ import annotations

import json
import math
import warnings
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Default fallback constants (same as ma_layer5_calibration.py)
# ---------------------------------------------------------------------------

_DEFAULT_SLOPE: float = 8.0
_DEFAULT_MIDPOINT: float = 0.68

_DEFAULT_PARAMS_PATH = (
    Path(__file__).parent.parent / "config" / "ma_calibration_params.json"
)

# Minimum samples required to fit calibration
_MIN_FIT_SAMPLES: int = 10
_MIN_FIT_POSITIVES: int = 3
_MIN_FIT_NEGATIVES: int = 3

# Score buckets for calibration table (5 equal-width bins over [0, 1])
_N_CALIBRATION_BUCKETS: int = 5

# Phase-to-heuristic-score mapping for deal universe records
_PHASE_SCORE: dict[str, float] = {
    "approved": 0.80,
    "nda_bla": 0.76,
    "pdufa_pending": 0.76,
    "phase_3": 0.70,
    "phase_2/3": 0.65,
    "phase_2": 0.60,
    "phase_1/2": 0.55,
    "phase_1": 0.50,
    "preclinical": 0.42,
    "discovery": 0.38,
}
_PHASE_SCORE_DEFAULT: float = 0.58


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class MABacktestRecord:
    """A single labeled observation for backtest evaluation.

    Parameters
    ----------
    score:
        Model M&A probability score at prediction_date (0–1).
    label:
        1 = acquired (positive outcome within 12 months), 0 = not acquired.
    ticker:
        Optional stock ticker for traceability.
    prediction_date:
        Date the score was generated (no-lookahead constraint).
    outcome_type:
        Optional outcome category string for audit purposes.
    """

    score: float
    label: int  # 1 = acquired within 12m, 0 = not acquired
    ticker: Optional[str] = None
    prediction_date: Optional[date] = None
    outcome_type: Optional[str] = None


@dataclass
class MABacktestBucket:
    """Calibration bucket for one score band.

    Measures whether model-assigned probabilities correspond to observed
    acquisition rates in that score range.
    """

    bucket_lower: float
    bucket_upper: float
    count: int
    n_acquired: int
    mean_score: float
    acquisition_rate: float   # n_acquired / count


@dataclass
class MABacktestResult:
    """Aggregated backtest metrics for a labeled dataset.

    See module docstring for metric definitions.
    """

    n: int
    n_positive: int
    n_negative: int
    base_rate: float             # n_positive / n

    auc: Optional[float]         # None when only one class present
    brier_score: float
    precision_at_k: dict         # {k: precision}  e.g. {5: 0.60, 10: 0.50}
    recall_at_k: dict            # {k: recall}
    mean_acquired_score: Optional[float]
    mean_non_acquired_score: Optional[float]
    score_separation: Optional[float]   # mean_acquired - mean_non_acquired

    calibration_buckets: list[MABacktestBucket] = field(default_factory=list)

    # Metadata
    training_window: Optional[str] = None  # e.g. "2015-01-01 to 2026-03-22"
    notes: list[str] = field(default_factory=list)


@dataclass
class CalibrationParams:
    """Fitted logistic calibration parameters + metadata."""

    slope: float
    midpoint: float
    n_positive: int
    n_negative: int
    base_rate: float
    auc: Optional[float]
    brier_score: float
    training_window: Optional[str]
    created_at: str
    source: str = "fitted"   # "fitted" | "hardcoded_fallback"


# ---------------------------------------------------------------------------
# Pure-Python metric helpers
# ---------------------------------------------------------------------------

def _expit(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def _logit(p: float) -> float:
    p = max(1e-9, min(1 - 1e-9, p))
    return math.log(p / (1.0 - p))


def _binary_auc(labels: list[int], scores: list[float]) -> Optional[float]:
    """Wilcoxon-Mann-Whitney AUC (exact, O(N²))."""
    pos = [s for s, y in zip(scores, labels) if y == 1]
    neg = [s for s, y in zip(scores, labels) if y == 0]
    if not pos or not neg:
        return None
    concordant = sum(1 for p in pos for n in neg if p > n)
    ties = sum(0.5 for p in pos for n in neg if p == n)
    return (concordant + ties) / (len(pos) * len(neg))


def _brier_score(labels: list[int], probs: list[float]) -> float:
    if not labels:
        return float("nan")
    return sum((p - y) ** 2 for p, y in zip(probs, labels)) / len(labels)


def _precision_at_k(labels: list[int], scores: list[float], k: int) -> Optional[float]:
    """Precision @ k: fraction of top-k scored items that are positive."""
    if k <= 0 or not labels:
        return None
    paired = sorted(zip(scores, labels), reverse=True)
    top_k = paired[:k]
    return sum(y for _, y in top_k) / k


def _recall_at_k(labels: list[int], scores: list[float], k: int) -> Optional[float]:
    """Recall @ k: fraction of all positives captured in top-k."""
    if k <= 0 or not labels:
        return None
    n_pos = sum(labels)
    if n_pos == 0:
        return None
    paired = sorted(zip(scores, labels), reverse=True)
    top_k = paired[:k]
    return sum(y for _, y in top_k) / n_pos


def _calibration_buckets(
    labels: list[int],
    scores: list[float],
    n_buckets: int = _N_CALIBRATION_BUCKETS,
) -> list[MABacktestBucket]:
    """Partition [0, 1] into equal-width buckets; compute acquisition rate per bucket."""
    width = 1.0 / n_buckets
    buckets: list[MABacktestBucket] = []
    for i in range(n_buckets):
        lo = i * width
        hi = lo + width
        items = [
            (s, y) for s, y in zip(scores, labels)
            if lo <= s < hi or (hi == 1.0 and s == 1.0)
        ]
        if not items:
            continue
        n = len(items)
        n_acq = sum(y for _, y in items)
        mean_s = sum(s for s, _ in items) / n
        buckets.append(MABacktestBucket(
            bucket_lower=round(lo, 4),
            bucket_upper=round(hi, 4),
            count=n,
            n_acquired=n_acq,
            mean_score=round(mean_s, 4),
            acquisition_rate=round(n_acq / n, 4),
        ))
    return buckets


# ---------------------------------------------------------------------------
# Core backtest function
# ---------------------------------------------------------------------------

def run_backtest(
    records: list[MABacktestRecord],
    *,
    k_values: tuple[int, ...] = (5, 10, 20),
    training_window: Optional[str] = None,
) -> MABacktestResult:
    """Evaluate a set of labeled M&A records and return backtest metrics.

    Parameters
    ----------
    records:
        List of MABacktestRecord with (score, label) pairs.
    k_values:
        Values of k for precision@k and recall@k.
    training_window:
        Human-readable date range for metadata (e.g. "2015-01-01 to 2026-03-22").

    Returns
    -------
    MABacktestResult
    """
    if not records:
        raise ValueError("records is empty — nothing to evaluate")

    scores = [r.score for r in records]
    labels = [r.label for r in records]

    n = len(records)
    n_pos = sum(labels)
    n_neg = n - n_pos
    base_rate = n_pos / n if n > 0 else 0.0

    auc = _binary_auc(labels, scores)
    brier = _brier_score(labels, scores)

    precision_k: dict = {}
    recall_k: dict = {}
    for k in k_values:
        p = _precision_at_k(labels, scores, k)
        r = _recall_at_k(labels, scores, k)
        if p is not None:
            precision_k[k] = round(p, 4)
        if r is not None:
            recall_k[k] = round(r, 4)

    acq_scores = [r.score for r in records if r.label == 1]
    non_scores = [r.score for r in records if r.label == 0]
    mean_acq = sum(acq_scores) / len(acq_scores) if acq_scores else None
    mean_non = sum(non_scores) / len(non_scores) if non_scores else None
    separation = (
        round(mean_acq - mean_non, 4)
        if mean_acq is not None and mean_non is not None
        else None
    )

    buckets = _calibration_buckets(labels, scores)

    notes: list[str] = []
    if n_pos < 5:
        notes.append(f"WARNING: only {n_pos} positive examples — metrics are unreliable")
    if n_neg < 5:
        notes.append(f"WARNING: only {n_neg} negative examples — metrics are unreliable")
    if auc is None:
        notes.append("AUC undefined — only one class present in labels")

    return MABacktestResult(
        n=n,
        n_positive=n_pos,
        n_negative=n_neg,
        base_rate=round(base_rate, 4),
        auc=round(auc, 4) if auc is not None else None,
        brier_score=round(brier, 6),
        precision_at_k=precision_k,
        recall_at_k=recall_k,
        mean_acquired_score=round(mean_acq, 4) if mean_acq is not None else None,
        mean_non_acquired_score=round(mean_non, 4) if mean_non is not None else None,
        score_separation=separation,
        calibration_buckets=buckets,
        training_window=training_window,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Logistic calibration fitting
# ---------------------------------------------------------------------------

def fit_logistic_calibration(
    records: list[MABacktestRecord],
    *,
    max_iter: int = 500,
    tol: float = 1e-8,
    l2: float = 1.0,
) -> CalibrationParams:
    """Fit logistic calibration parameters from labeled records.

    Uses Platt scaling: P = sigmoid(A * score + B).
    Converts to slope/midpoint: slope = A, midpoint = -B / A.

    Parameters
    ----------
    records:
        Labeled MABacktestRecord list.
    max_iter:
        Maximum gradient descent iterations.
    tol:
        Convergence tolerance on gradient norm.
    l2:
        L2 regularization on slope parameter A.

    Returns
    -------
    CalibrationParams with fitted slope, midpoint, and backtest metadata.

    Raises
    ------
    ValueError
        If records are too few or lack both classes.
    """
    if len(records) < _MIN_FIT_SAMPLES:
        raise ValueError(
            f"Need at least {_MIN_FIT_SAMPLES} records to fit calibration, "
            f"got {len(records)}"
        )
    n_pos = sum(r.label for r in records)
    n_neg = len(records) - n_pos
    if n_pos < _MIN_FIT_POSITIVES:
        raise ValueError(
            f"Need at least {_MIN_FIT_POSITIVES} positive examples, got {n_pos}"
        )
    if n_neg < _MIN_FIT_NEGATIVES:
        raise ValueError(
            f"Need at least {_MIN_FIT_NEGATIVES} negative examples, got {n_neg}"
        )

    scores = [r.score for r in records]
    labels = [r.label for r in records]
    n = len(records)

    # Gradient descent for Platt scaling: P = sigmoid(A*s + B)
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
        if math.sqrt(grad_A ** 2 + grad_B ** 2) < tol:
            break

    # Convert A, B → slope, midpoint
    if abs(A) < 1e-8:
        # Degenerate: no discriminative power, fall back to defaults
        warnings.warn(
            "Platt scaling converged to near-zero A; "
            "logistic slope is ill-defined. Returning fallback defaults.",
            UserWarning,
            stacklevel=2,
        )
        slope = _DEFAULT_SLOPE
        midpoint = _DEFAULT_MIDPOINT
    else:
        slope = A
        midpoint = -B / A

    # Compute backtest metrics on the fitted model
    fitted_probs = [_expit(A * s + B) for s in scores]
    auc = _binary_auc(labels, scores)
    brier = _brier_score(labels, fitted_probs)
    base_rate = n_pos / n

    training_window: Optional[str] = None
    dated = [r.prediction_date for r in records if r.prediction_date is not None]
    if dated:
        training_window = f"{min(dated).isoformat()} to {max(dated).isoformat()}"

    return CalibrationParams(
        slope=round(slope, 6),
        midpoint=round(midpoint, 6),
        n_positive=n_pos,
        n_negative=n_neg,
        base_rate=round(base_rate, 6),
        auc=round(auc, 4) if auc is not None else None,
        brier_score=round(brier, 6),
        training_window=training_window,
        created_at=datetime.now(timezone.utc).isoformat(),
        source="fitted",
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_calibration_params(
    params: CalibrationParams,
    path: Optional[str | Path] = None,
) -> Path:
    """Save calibration parameters to JSON.

    Parameters
    ----------
    params:
        Fitted CalibrationParams to persist.
    path:
        Destination path. Defaults to ``_DEFAULT_PARAMS_PATH``.

    Returns
    -------
    Path
        The path the file was written to.
    """
    dest = Path(path) if path is not None else _DEFAULT_PARAMS_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "slope": params.slope,
        "midpoint": params.midpoint,
        "n_positive": params.n_positive,
        "n_negative": params.n_negative,
        "base_rate": params.base_rate,
        "auc": params.auc,
        "brier_score": params.brier_score,
        "training_window": params.training_window,
        "created_at": params.created_at,
        "source": params.source,
    }
    dest.write_text(json.dumps(payload, indent=2))
    return dest


def load_calibration_params(
    path: Optional[str | Path] = None,
) -> tuple[float, float]:
    """Load (slope, midpoint) from JSON.

    Falls back to hard-coded defaults with a UserWarning if the file
    does not exist, cannot be parsed, or is missing required keys.

    Parameters
    ----------
    path:
        JSON file path. Defaults to ``_DEFAULT_PARAMS_PATH``.

    Returns
    -------
    tuple[float, float]
        (slope, midpoint)
    """
    dest = Path(path) if path is not None else _DEFAULT_PARAMS_PATH
    if not dest.exists():
        warnings.warn(
            f"No fitted calibration params found at {dest}. "
            "Using hard-coded defaults (slope=8.0, midpoint=0.68). "
            "Run fit_logistic_calibration() and save_calibration_params() "
            "to replace these un-validated constants.",
            UserWarning,
            stacklevel=2,
        )
        return _DEFAULT_SLOPE, _DEFAULT_MIDPOINT

    try:
        data = json.loads(dest.read_text())
        slope = float(data["slope"])
        midpoint = float(data["midpoint"])
        return slope, midpoint
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        warnings.warn(
            f"Failed to parse calibration params at {dest}: {exc}. "
            "Using hard-coded defaults (slope=8.0, midpoint=0.68).",
            UserWarning,
            stacklevel=2,
        )
        return _DEFAULT_SLOPE, _DEFAULT_MIDPOINT


# ---------------------------------------------------------------------------
# Base-rate adjustment
# ---------------------------------------------------------------------------

def adjust_for_base_rate(
    raw_prob: float,
    training_base_rate: float,
    target_base_rate: float,
) -> float:
    """Adjust a calibrated probability for a different deployment-time base rate.

    Uses the standard log-odds prior-shift formula:
        adjusted_log_odds = raw_log_odds
                          - logit(training_base_rate)
                          + logit(target_base_rate)

    This corrects for the difference between the positive fraction in the
    training set and the expected positive fraction at deployment time.
    Both extremes (0 and 1) are clamped to avoid undefined log-odds.

    Parameters
    ----------
    raw_prob:
        Calibrated probability from the model (0–1).
    training_base_rate:
        Fraction of positive examples in the training dataset.
    target_base_rate:
        Expected positive fraction in the deployment population.

    Returns
    -------
    float
        Adjusted probability in [0, 1].
    """
    if not (0.0 < training_base_rate < 1.0):
        raise ValueError(
            f"training_base_rate must be in (0, 1), got {training_base_rate}"
        )
    if not (0.0 < target_base_rate < 1.0):
        raise ValueError(
            f"target_base_rate must be in (0, 1), got {target_base_rate}"
        )
    raw_lo = _logit(raw_prob)
    train_lo = _logit(training_base_rate)
    target_lo = _logit(target_base_rate)
    adjusted_lo = raw_lo - train_lo + target_lo
    return round(_expit(adjusted_lo), 6)


# ---------------------------------------------------------------------------
# Deal-universe record builder
# ---------------------------------------------------------------------------

def _heuristic_score_from_phase(phase_str: Optional[str]) -> float:
    """Map a phase_at_acquisition string to a heuristic M&A score.

    This is a v1 approximation. It does not run the full scan pipeline.
    For validated calibration, replace with actual historical scan scores.
    """
    if phase_str is None:
        return _PHASE_SCORE_DEFAULT
    phase_lower = phase_str.lower()
    # Match longest prefix
    for key in sorted(_PHASE_SCORE, key=len, reverse=True):
        if key in phase_lower:
            return _PHASE_SCORE[key]
    return _PHASE_SCORE_DEFAULT


def _lcg_random(seed: int, n: int, lo: float = 0.20, hi: float = 0.60) -> list[float]:
    """Generate n pseudo-random floats in [lo, hi] using a simple LCG."""
    a, c, m = 1664525, 1013904223, 2 ** 32
    state = seed & 0xFFFFFFFF
    result = []
    for _ in range(n):
        state = (a * state + c) % m
        result.append(lo + (state / m) * (hi - lo))
    return result


def build_backtest_records_from_deal_universe(
    deal_universe_path: Optional[str | Path] = None,
    *,
    n_negatives_per_positive: int = 3,
    negative_score_lo: float = 0.20,
    negative_score_hi: float = 0.60,
    seed: int = 42,
) -> list[MABacktestRecord]:
    """Build labeled backtest records from the deal universe YAML.

    Positive examples (label=1):
        Each deal in the YAML is a positive example. The prediction_date
        is announcement_date - 365 days (12 months before announcement).
        The heuristic score is derived from ``phase_at_acquisition``.

    Negative examples (label=0):
        ``n_negatives_per_positive`` synthetic negatives per positive.
        Scores are pseudo-randomly drawn from [negative_score_lo, negative_score_hi].
        In v1 these represent "targets that were not acquired"; for production use,
        replace with actual historical scan outputs.

    Notes
    -----
    This is a v1 heuristic builder. Phase-derived scores are not equivalent
    to running the full scan pipeline at historical dates. They are intended
    for smoke-testing calibration logic, not live model validation.

    Parameters
    ----------
    deal_universe_path:
        Path to the YAML file. Defaults to the bundled
        ``research/mna/deal_universe_2020_2026.yaml``.
    n_negatives_per_positive:
        Number of negative examples to generate per positive.
    negative_score_lo, negative_score_hi:
        Score range for synthetic negatives.
    seed:
        Seed for the pseudo-random negative-score generator.

    Returns
    -------
    list[MABacktestRecord]
        Positive examples followed by negative examples.
    """
    try:
        import yaml  # type: ignore[import]
    except ImportError:
        raise ImportError(
            "PyYAML is required for build_backtest_records_from_deal_universe(). "
            "Install it with: pip install pyyaml"
        )

    default_yaml = (
        Path(__file__).parent.parent.parent.parent
        / "research" / "mna" / "deal_universe_2020_2026.yaml"
    )
    yaml_path = Path(deal_universe_path) if deal_universe_path is not None else default_yaml

    with open(yaml_path, "r") as fh:
        data = yaml.safe_load(fh)

    deals = data.get("deals", [])
    positives: list[MABacktestRecord] = []

    for deal in deals:
        ann_str = deal.get("announcement_date")
        if not ann_str:
            continue
        try:
            ann_date = date.fromisoformat(str(ann_str))
        except ValueError:
            continue
        # Prediction date = 12 months before announcement (no-lookahead)
        pred_year = ann_date.year - 1
        try:
            prediction_date = ann_date.replace(year=pred_year)
        except ValueError:
            # Feb 29 → Feb 28 in non-leap years
            prediction_date = ann_date.replace(year=pred_year, day=28)

        phase = deal.get("phase_at_acquisition")
        score = _heuristic_score_from_phase(phase)
        ticker = deal.get("target_ticker")

        positives.append(MABacktestRecord(
            score=score,
            label=1,
            ticker=ticker,
            prediction_date=prediction_date,
            outcome_type="full_acquisition_announced",
        ))

    # Generate synthetic negatives
    n_neg = len(positives) * n_negatives_per_positive
    neg_scores = _lcg_random(seed, n_neg, lo=negative_score_lo, hi=negative_score_hi)
    negatives = [
        MABacktestRecord(score=round(s, 4), label=0, outcome_type="remained_independent")
        for s in neg_scores
    ]

    return positives + negatives


# ---------------------------------------------------------------------------
# Calibration-cases record builder (Block D)
# ---------------------------------------------------------------------------

# Composite rank_score weights for the three YAML feature columns.
# These approximate Layer 3 signal contribution using available features:
#   asset_quality   ≈ target_quality (0.35)
#   acquirer_fit    ≈ buyer_mandate + strategic_fit (0.35)
#   seller_willing  ≈ seller_readiness (0.20)
#   stage_factor    ≈ deal_momentum + other residual (0.10)
_CALIB_WEIGHT_ASSET_QUALITY: float = 0.35
_CALIB_WEIGHT_ACQUIRER_FIT: float = 0.35
_CALIB_WEIGHT_SELLER_WILLINGNESS: float = 0.20
_CALIB_WEIGHT_STAGE: float = 0.10

_STAGE_FACTOR: dict[str, float] = {
    "approved":    0.90,
    "nda_bla":     0.80,
    "pdufa_pending": 0.80,
    "phase_3":     0.70,
    "phase_2/3":   0.65,
    "phase_2":     0.60,
    "phase_1/2":   0.55,
    "phase_1":     0.50,
    "preclinical": 0.40,
    "discovery":   0.35,
}
_STAGE_FACTOR_DEFAULT: float = 0.58


def _stage_factor(stage: Optional[str]) -> float:
    if not stage:
        return _STAGE_FACTOR_DEFAULT
    return _STAGE_FACTOR.get(stage.lower(), _STAGE_FACTOR_DEFAULT)


def _composite_score_from_yaml_features(
    asset_quality: float,
    acquirer_fit: float,
    seller_willingness: float,
    stage: Optional[str],
) -> float:
    """Compute a rank_score proxy from the three YAML feature columns.

    This is used for retroactive calibration where the full Layer 3 pipeline
    cannot be re-run. The weights approximate the relative contribution of
    each signal domain in Layer 3. The result is a bounded [0.0, 1.0] float.
    """
    raw = (
        _CALIB_WEIGHT_ASSET_QUALITY * asset_quality
        + _CALIB_WEIGHT_ACQUIRER_FIT * acquirer_fit
        + _CALIB_WEIGHT_SELLER_WILLINGNESS * seller_willingness
        + _CALIB_WEIGHT_STAGE * _stage_factor(stage)
    )
    return round(min(max(raw, 0.0), 1.0), 4)


_DEFAULT_CALIBRATION_CASES_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "research" / "mna" / "historical_calibration_cases.yaml"
)


def build_backtest_records_from_calibration_cases(
    calibration_cases_path: Optional[str | Path] = None,
) -> list[MABacktestRecord]:
    """Build labeled backtest records from historical_calibration_cases.yaml.

    Unlike ``build_backtest_records_from_deal_universe``, this builder uses
    real labeled data (both positives and negatives) with hand-estimated
    feature scores per observation, giving a genuine held-out dataset for
    logistic calibration fitting.

    Score proxy:
        rank_score ≈ 0.35 * asset_quality + 0.35 * acquirer_fit
                   + 0.20 * seller_willingness + 0.10 * stage_factor

    Parameters
    ----------
    calibration_cases_path:
        Path to the YAML. Defaults to
        ``research/mna/historical_calibration_cases.yaml``.

    Returns
    -------
    list[MABacktestRecord]
        One record per case in the YAML (positives + negatives combined).
    """
    try:
        import yaml  # type: ignore[import]
    except ImportError:
        raise ImportError(
            "PyYAML is required for build_backtest_records_from_calibration_cases(). "
            "Install it with: pip install pyyaml"
        )

    yaml_path = (
        Path(calibration_cases_path)
        if calibration_cases_path is not None
        else _DEFAULT_CALIBRATION_CASES_PATH
    )

    with open(yaml_path, "r") as fh:
        data = yaml.safe_load(fh)

    cases = data.get("cases", [])
    records: list[MABacktestRecord] = []

    for case in cases:
        asset_quality = float(case.get("asset_quality_score_as_of") or 0.5)
        acquirer_fit = float(case.get("acquirer_fit_score_as_of") or 0.5)
        seller_willingness = float(case.get("seller_willingness_as_of") or 0.5)
        stage = case.get("target_stage")
        label = 1 if case.get("outcome_12m") else 0

        score = _composite_score_from_yaml_features(
            asset_quality=asset_quality,
            acquirer_fit=acquirer_fit,
            seller_willingness=seller_willingness,
            stage=stage,
        )

        obs_date_str = case.get("observation_date")
        obs_date: Optional[date] = None
        if obs_date_str:
            try:
                obs_date = date.fromisoformat(str(obs_date_str))
            except ValueError:
                pass

        records.append(MABacktestRecord(
            score=score,
            label=label,
            ticker=case.get("ticker"),
            prediction_date=obs_date,
            outcome_type=case.get("outcome_type"),
        ))

    return records
