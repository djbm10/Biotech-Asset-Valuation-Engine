"""
Fitted logistic regression overlay for empirical POS predictions.

Architecture
------------
    logit(p_final) = logit(p_base) [fixed offset] + intercept + X @ beta

Where:
    p_base      Laplace-smoothed phase-level base rate (fixed; not trained).
                Using phase-only rate keeps coefficients comparable to the
                heuristic log-odds values (+0.35 validated MoA, etc.).
    intercept   Global bias (not L2-regularized).
    X           11-dimensional binary feature vector from features.py.
    beta        L2-regularized coefficient vector (default alpha=1.0).

The model is fitted using scipy.optimize.minimize with L-BFGS-B — no sklearn
dependency. All parameters are stored in a JSON-serializable OverlayArtifact.

Interpretability
----------------
Coefficients are in log-odds space and directly comparable to the hand-tuned
heuristic values in pos_model.py. A coefficient of +0.30 for moa_validated
means the model learned +0.30 log-odds (vs heuristic +0.35 for validated MoA).
Intercept ≈ 0 indicates no global bias beyond the phase base rate.

Usage
-----
from bve.empirical.overlay_model import fit_overlay, fit_overlay_time_split

artifact = fit_overlay(records, base_rate_table, alpha=1.0)
p = artifact.apply(feature_vector, base_log_odds)
print(artifact.coefficient_summary())
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

from bve.empirical.features import (
    EXPECTED_SIGNS,
    FEATURE_NAMES,
    MIN_OVERLAY_RECORDS,
    build_feature_vector,
)

if TYPE_CHECKING:
    from bve.empirical.pos_outcome import POSOutcomeRecord
    from bve.empirical.base_rate_table import BaseRateTable

logger = logging.getLogger(__name__)

_CLIP = 1e-7   # clip probabilities away from 0/1 before logit


# ---------------------------------------------------------------------------
# Metric helpers (local; avoids circular imports with evaluator.py)
# ---------------------------------------------------------------------------

def _brier(preds: list[float], outcomes: list[bool]) -> float:
    if not preds:
        return 0.0
    return sum((p - float(y)) ** 2 for p, y in zip(preds, outcomes)) / len(preds)


def _ece(preds: list[float], outcomes: list[bool], n_bins: int = 10) -> float:
    if not preds:
        return 0.0
    n = len(preds)
    ece = 0.0
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        in_bin = [(p, float(y)) for p, y in zip(preds, outcomes)
                  if lo <= p < hi or (b == n_bins - 1 and p == 1.0)]
        if not in_bin:
            continue
        mean_p = sum(x[0] for x in in_bin) / len(in_bin)
        obs_r  = sum(x[1] for x in in_bin) / len(in_bin)
        ece += (len(in_bin) / n) * abs(mean_p - obs_r)
    return round(ece, 4)


def _auc(preds: list[float], outcomes: list[bool]) -> Optional[float]:
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
    return round(sum(
        (fpr[i] - fpr[i - 1]) * (tpr[i] + tpr[i - 1]) / 2
        for i in range(1, len(fpr))
    ), 4)


# ---------------------------------------------------------------------------
# Core logistic regression fitter
# ---------------------------------------------------------------------------

def _fit_logistic_l2(
    X: np.ndarray,           # (n_samples, n_features)
    y: np.ndarray,           # (n_samples,) binary float
    offsets: np.ndarray,     # (n_samples,) fixed log-odds offset (base rate)
    alpha: float = 1.0,      # L2 regularization strength (not applied to intercept)
) -> tuple[list[float], float, bool]:
    """
    Fit regularized logistic regression with a fixed offset.

    Objective:
        L(intercept, beta) = -∑ [y·log σ(z) + (1-y)·log(1-σ(z))]
                              + (alpha/2) · ||beta||²
        where z = offset + intercept + X @ beta

    Parameters
    ----------
    X:        Feature matrix (n × p).
    y:        Binary outcome array.
    offsets:  Fixed log-odds offset per sample (phase-level base rate logit).
    alpha:    L2 penalty on beta (not intercept).

    Returns
    -------
    (coefficients: list[float], intercept: float, converged: bool)
    """
    n, p = X.shape

    def obj_grad(params: np.ndarray):
        intercept = params[0]
        beta = params[1:]
        z = offsets + intercept + X @ beta
        p_hat = np.clip(expit(z), 1e-12, 1.0 - 1e-12)
        nll = -float(np.sum(y * np.log(p_hat) + (1.0 - y) * np.log(1.0 - p_hat)))
        reg = 0.5 * alpha * float(np.dot(beta, beta))
        # gradients
        residual = p_hat - y
        g_intercept = float(np.sum(residual))
        g_beta = X.T @ residual + alpha * beta
        grad = np.concatenate([[g_intercept], g_beta])
        return nll + reg, grad

    init = np.zeros(1 + p)
    result = minimize(
        obj_grad, init, jac=True,
        method="L-BFGS-B",
        options={"maxiter": 2000, "ftol": 1e-10},
    )
    intercept = round(float(result.x[0]), 6)
    coefficients = [round(float(c), 6) for c in result.x[1:]]
    return coefficients, intercept, bool(result.success)


# ---------------------------------------------------------------------------
# OverlayArtifact
# ---------------------------------------------------------------------------

@dataclass
class OverlayArtifact:
    """
    Fitted logistic regression overlay — interpretable, JSON-serializable.

    Coefficients are log-odds adjustments on top of the phase-level empirical
    base rate. Directly comparable to the heuristic values in pos_model.py.
    """
    feature_names: list[str]
    coefficients: list[float]          # one per feature; index mirrors feature_names
    intercept: float                   # global bias (not regularized)
    regularization_alpha: float
    n_train: int
    cutoff_year: Optional[int]
    n_feature_nonzero: dict[str, int]  # training records with each feature set
    converged: bool

    # Training metrics
    train_brier_base: float            # base-rate-only Brier (no overlay)
    train_brier_overlay: float         # with overlay applied
    train_auc_base: Optional[float]
    train_auc_overlay: Optional[float]
    train_ece_base: float
    train_ece_overlay: float

    # Test metrics (populated by fit_overlay_time_split)
    n_test: Optional[int] = None
    test_brier_base: Optional[float] = None
    test_brier_overlay: Optional[float] = None
    test_auc_base: Optional[float] = None
    test_auc_overlay: Optional[float] = None
    test_ece_base: Optional[float] = None
    test_ece_overlay: Optional[float] = None

    # Hardening guards (Sprint 9)
    # sparse_clamped: features zeroed because n_nonzero < min_feature_obs
    #   maps feature_name → n_nonzero_at_clamp_time
    # sign_violated: features zeroed because fitted sign != expected sign
    #   maps feature_name → raw_fitted_coefficient_before_zeroing
    sparse_clamped: dict[str, int] = field(default_factory=dict)
    sign_violated: dict[str, float] = field(default_factory=dict)
    min_feature_obs: int = 5

    def apply(self, feature_vector: list[float], base_log_odds: float) -> float:
        """
        Apply the overlay to produce a calibrated POS estimate.

        Parameters
        ----------
        feature_vector:
            11-dimensional binary feature vector (from build_feature_vector*).
        base_log_odds:
            log-odds of the phase-level empirical base rate (fixed offset).

        Returns
        -------
        float in (0, 1) — final POS estimate.
        """
        if len(feature_vector) != len(self.coefficients):
            raise ValueError(
                f"feature_vector length {len(feature_vector)} != "
                f"coefficients length {len(self.coefficients)}"
            )
        net = (
            base_log_odds
            + self.intercept
            + sum(fv * c for fv, c in zip(feature_vector, self.coefficients))
        )
        return round(float(expit(net)), 4)

    def feature_contributions(self, feature_vector: list[float]) -> dict[str, float]:
        """
        Return per-feature log-odds contribution for a given feature vector.

        Entries are zero when the feature is at its baseline (indicator=0).
        Useful for provenance decomposition.
        """
        return {
            name: round(fv * c, 6)
            for name, fv, c in zip(self.feature_names, feature_vector, self.coefficients)
        }

    def net_log_odds_delta(self, feature_vector: list[float]) -> float:
        """
        Return total log-odds shift from the overlay (intercept + features).
        """
        return round(
            self.intercept
            + sum(fv * c for fv, c in zip(feature_vector, self.coefficients)),
            6,
        )

    def coefficient_summary(self) -> str:
        """
        Human-readable coefficient table sorted by absolute magnitude.

        Example output:
            OverlayArtifact Coefficients (alpha=1.0, n_train=75, converged=True)
            Feature                    Coeff    Heuristic   N_nonzero
            --------------------------  ------  ---------   ---------
            moa_validated               +0.28     +0.35          18
            ...
        """
        from bve.models.pos_model import (
            _MOA_LOGODDS, _SAFETY_LOGODDS, _COMPETITION_LOGODDS, _ENDPOINT_LOGODDS,
            _BIOMARKER_SELECTION_BONUS, MoAPrecedent, SafetyProfile,
            CompetitivePressure,
        )
        from bve.entities.trial import EndpointType

        # Best-effort mapping from feature name to heuristic log-odds
        _heuristic: dict[str, float] = {
            "moa_validated": _MOA_LOGODDS.get(MoAPrecedent.VALIDATED, 0.0),
            "moa_novel": _MOA_LOGODDS.get(MoAPrecedent.NOVEL, 0.0),
            "biomarker_selected": _BIOMARKER_SELECTION_BONUS,
            "endpoint_hard_clinical": _ENDPOINT_LOGODDS.get(EndpointType.HARD_CLINICAL, 0.0),
            "endpoint_surrogate_novel": _ENDPOINT_LOGODDS.get(EndpointType.SURROGATE_NOVEL, 0.0),
            "endpoint_biomarker_only": _ENDPOINT_LOGODDS.get(EndpointType.BIOMARKER_ONLY, 0.0),
            "safety_clean": _SAFETY_LOGODDS.get(SafetyProfile.CLEAN, 0.0),
            "safety_concerning": _SAFETY_LOGODDS.get(SafetyProfile.CONCERNING, 0.0),
            "safety_serious": _SAFETY_LOGODDS.get(SafetyProfile.SERIOUS, 0.0),
            "competition_low": _COMPETITION_LOGODDS.get(CompetitivePressure.LOW, 0.0),
            "competition_high": _COMPETITION_LOGODDS.get(CompetitivePressure.HIGH, 0.0),
        }

        lines = [
            f"OverlayArtifact Coefficients"
            f" (alpha={self.regularization_alpha}, n_train={self.n_train},"
            f" converged={self.converged})",
            f"  intercept = {self.intercept:+.4f}",
            "",
            f"  {'Feature':<30} {'Fitted':>7}  {'Heuristic':>9}  {'N_nonzero':>9}",
            f"  {'-'*30}  {'-'*7}  {'-'*9}  {'-'*9}",
        ]
        # Sort by absolute coefficient
        paired = sorted(
            zip(self.feature_names, self.coefficients),
            key=lambda x: -abs(x[1]),
        )
        for name, coef in paired:
            h = _heuristic.get(name, float("nan"))
            n_nz = self.n_feature_nonzero.get(name, 0)
            h_str = f"{h:+.2f}" if not math.isnan(h) else "  n/a"
            lines.append(
                f"  {name:<30} {coef:+.4f}  {h_str:>9}  {n_nz:>9}"
            )
        lines.append("")
        lines.append(f"  Train Brier (base={self.train_brier_base:.4f},"
                     f" overlay={self.train_brier_overlay:.4f})")
        if self.test_brier_base is not None:
            lines.append(f"  Test  Brier (base={self.test_brier_base:.4f},"
                         f" overlay={self.test_brier_overlay:.4f})")
            if self.test_auc_overlay is not None:
                lines.append(f"  Test  AUC   (base={self.test_auc_base},"
                             f" overlay={self.test_auc_overlay})")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """JSON-serializable representation."""
        return {
            "feature_names": self.feature_names,
            "coefficients": self.coefficients,
            "intercept": self.intercept,
            "regularization_alpha": self.regularization_alpha,
            "n_train": self.n_train,
            "cutoff_year": self.cutoff_year,
            "n_feature_nonzero": self.n_feature_nonzero,
            "converged": self.converged,
            "train_brier_base": self.train_brier_base,
            "train_brier_overlay": self.train_brier_overlay,
            "train_auc_base": self.train_auc_base,
            "train_auc_overlay": self.train_auc_overlay,
            "train_ece_base": self.train_ece_base,
            "train_ece_overlay": self.train_ece_overlay,
            "n_test": self.n_test,
            "test_brier_base": self.test_brier_base,
            "test_brier_overlay": self.test_brier_overlay,
            "test_auc_base": self.test_auc_base,
            "test_auc_overlay": self.test_auc_overlay,
            "test_ece_base": self.test_ece_base,
            "test_ece_overlay": self.test_ece_overlay,
            "sparse_clamped": self.sparse_clamped,
            "sign_violated": self.sign_violated,
            "min_feature_obs": self.min_feature_obs,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "OverlayArtifact":
        """Reconstruct from to_dict() output."""
        return cls(
            feature_names=d["feature_names"],
            coefficients=d["coefficients"],
            intercept=d["intercept"],
            regularization_alpha=d["regularization_alpha"],
            n_train=d["n_train"],
            cutoff_year=d.get("cutoff_year"),
            n_feature_nonzero=d.get("n_feature_nonzero", {}),
            converged=d["converged"],
            train_brier_base=d["train_brier_base"],
            train_brier_overlay=d["train_brier_overlay"],
            train_auc_base=d.get("train_auc_base"),
            train_auc_overlay=d.get("train_auc_overlay"),
            train_ece_base=d["train_ece_base"],
            train_ece_overlay=d["train_ece_overlay"],
            n_test=d.get("n_test"),
            test_brier_base=d.get("test_brier_base"),
            test_brier_overlay=d.get("test_brier_overlay"),
            test_auc_base=d.get("test_auc_base"),
            test_auc_overlay=d.get("test_auc_overlay"),
            test_ece_base=d.get("test_ece_base"),
            test_ece_overlay=d.get("test_ece_overlay"),
            sparse_clamped=d.get("sparse_clamped", {}),
            sign_violated=d.get("sign_violated", {}),
            min_feature_obs=d.get("min_feature_obs", 5),
        )


# ---------------------------------------------------------------------------
# Internal helpers for building train/test arrays
# ---------------------------------------------------------------------------

def _build_arrays(
    records: list["POSOutcomeRecord"],
    base_rate_table: "BaseRateTable",
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[float]]:
    """
    Build (X, y, offsets, base_preds) arrays from records.

    X       : (n, N_FEATURES) float array
    y       : (n,) float array (1.0 = success, 0.0 = failure)
    offsets : (n,) float array — logit of phase-only base rate (fixed offset)
    base_preds : list[float] — sigmoid(offset) for each record (baseline predictions)
    """
    rows_X = []
    rows_y = []
    rows_off = []
    base_preds = []

    for rec in records:
        fv = build_feature_vector(rec)
        phase_str = rec.phase_at_entry
        p_base = base_rate_table.get(phase_str)   # phase-only (no moa/biomarker)
        p_base = max(_CLIP, min(1.0 - _CLIP, p_base))
        offset = math.log(p_base / (1.0 - p_base))

        rows_X.append(fv)
        rows_y.append(1.0 if rec.success else 0.0)
        rows_off.append(offset)
        base_preds.append(round(float(expit(offset)), 4))

    X = np.array(rows_X, dtype=float)
    y = np.array(rows_y, dtype=float)
    offsets = np.array(rows_off, dtype=float)
    return X, y, offsets, base_preds


def _nonzero_counts(records: list["POSOutcomeRecord"]) -> dict[str, int]:
    """Count records with each feature set to 1."""
    counts = {name: 0 for name in FEATURE_NAMES}
    for rec in records:
        fv = build_feature_vector(rec)
        for i, v in enumerate(fv):
            if v > 0.0:
                counts[FEATURE_NAMES[i]] += 1
    return counts


# ---------------------------------------------------------------------------
# Public fitting API
# ---------------------------------------------------------------------------

def fit_overlay(
    records: list["POSOutcomeRecord"],
    base_rate_table: "BaseRateTable",
    alpha: float = 1.0,
    cutoff_year: Optional[int] = None,
    test_records: Optional[list["POSOutcomeRecord"]] = None,
    min_feature_obs: int = 5,
    enforce_sign_gate: bool = True,
) -> OverlayArtifact:
    """
    Fit a logistic regression overlay on outcome records.

    Parameters
    ----------
    records:
        Training outcome records (censored excluded).
    base_rate_table:
        Fitted BaseRateTable (used for phase-only offset computation).
    alpha:
        L2 regularization strength. Higher → more shrinkage toward zero.
        Default 1.0 appropriate for ~100 records; increase for smaller datasets.
    cutoff_year:
        Informational only; stored in the artifact. Use fit_overlay_time_split
        for proper time-based train/test splitting.
    test_records:
        Optional held-out records for out-of-sample metric computation.
    min_feature_obs:
        Features with fewer than this many nonzero training records will have
        their coefficient forced to 0.0 (sparse guard). Default 5.
    enforce_sign_gate:
        When True, coefficients that violate EXPECTED_SIGNS are zeroed and
        recorded in the artifact's sign_violated dict. Default True.

    Returns
    -------
    OverlayArtifact
    """
    if len(records) < MIN_OVERLAY_RECORDS:
        raise ValueError(
            f"fit_overlay requires at least {MIN_OVERLAY_RECORDS} records, "
            f"got {len(records)}. With fewer records the regularized fit is "
            f"not identifiable."
        )

    X, y, offsets, base_preds = _build_arrays(records, base_rate_table)
    outcomes = [bool(v) for v in y]
    n_feature_nonzero = _nonzero_counts(records)

    coefficients, intercept, converged = _fit_logistic_l2(X, y, offsets, alpha=alpha)
    coefficients = list(coefficients)  # ensure mutable copy
    if not converged:
        logger.warning(
            "fit_overlay: L-BFGS-B did not converge on %d records. "
            "Coefficients may be unreliable; consider increasing alpha.",
            len(records),
        )

    # --- Guard 1: sparse clamp ---
    # Zero out coefficients for features with insufficient training observations.
    # Recorded in sparse_clamped for provenance; sign gate skips these features.
    sparse_clamped: dict[str, int] = {}
    for i, name in enumerate(FEATURE_NAMES):
        n_obs = n_feature_nonzero.get(name, 0)
        if n_obs < min_feature_obs:
            if coefficients[i] != 0.0:
                logger.warning(
                    "fit_overlay: sparse-clamping '%s' "
                    "(n_nonzero=%d < min=%d, raw_coeff=%.4f) → 0.0",
                    name, n_obs, min_feature_obs, coefficients[i],
                )
            sparse_clamped[name] = n_obs
            coefficients[i] = 0.0

    # --- Guard 2: sign gate ---
    # Zero out coefficients whose sign contradicts EXPECTED_SIGNS,
    # provided the feature was not already sparse-clamped.
    sign_violated: dict[str, float] = {}
    if enforce_sign_gate:
        for i, name in enumerate(FEATURE_NAMES):
            if name in sparse_clamped:
                continue
            expected = EXPECTED_SIGNS.get(name, 0)
            if expected == 0:
                continue
            coef = coefficients[i]
            if (expected == +1 and coef < 0.0) or (expected == -1 and coef > 0.0):
                logger.warning(
                    "fit_overlay: sign violation for '%s' "
                    "(expected=%+d, fitted=%.4f) → 0.0",
                    name, expected, coef,
                )
                sign_violated[name] = coef
                coefficients[i] = 0.0

    # Build a temporary artifact used for training-set predictions only.
    _tmp = OverlayArtifact(
        feature_names=FEATURE_NAMES,
        coefficients=coefficients,
        intercept=intercept,
        regularization_alpha=alpha,
        n_train=len(records),
        cutoff_year=cutoff_year,
        n_feature_nonzero=n_feature_nonzero,
        converged=converged,
        train_brier_base=0.0,
        train_brier_overlay=0.0,
        train_auc_base=None,
        train_auc_overlay=None,
        train_ece_base=0.0,
        train_ece_overlay=0.0,
        sparse_clamped=sparse_clamped,
        sign_violated=sign_violated,
        min_feature_obs=min_feature_obs,
    )

    overlay_preds = [
        _tmp.apply(build_feature_vector(rec), offsets[i])
        for i, rec in enumerate(records)
    ]

    train_brier_base = round(_brier(base_preds, outcomes), 4)
    train_brier_overlay = round(_brier(overlay_preds, outcomes), 4)
    train_auc_base = _auc(base_preds, outcomes)
    train_auc_overlay = _auc(overlay_preds, outcomes)
    train_ece_base = _ece(base_preds, outcomes)
    train_ece_overlay = _ece(overlay_preds, outcomes)

    # Test metrics
    n_test = None
    test_brier_base = test_brier_overlay = None
    test_auc_base = test_auc_overlay = None
    test_ece_base = test_ece_overlay = None

    if test_records:
        n_test = len(test_records)
        if n_test > 0:
            X_t, y_t, off_t, base_t = _build_arrays(test_records, base_rate_table)
            outcomes_t = [bool(v) for v in y_t]
            overlay_t = [
                _tmp.apply(build_feature_vector(rec), float(off_t[i]))
                for i, rec in enumerate(test_records)
            ]
            test_brier_base = round(_brier(list(base_t), outcomes_t), 4)
            test_brier_overlay = round(_brier(overlay_t, outcomes_t), 4)
            test_auc_base = _auc(list(base_t), outcomes_t)
            test_auc_overlay = _auc(overlay_t, outcomes_t)
            test_ece_base = _ece(list(base_t), outcomes_t)
            test_ece_overlay = _ece(overlay_t, outcomes_t)

    return OverlayArtifact(
        feature_names=FEATURE_NAMES,
        coefficients=coefficients,
        intercept=intercept,
        regularization_alpha=alpha,
        n_train=len(records),
        cutoff_year=cutoff_year,
        n_feature_nonzero=n_feature_nonzero,
        converged=converged,
        train_brier_base=train_brier_base,
        train_brier_overlay=train_brier_overlay,
        train_auc_base=train_auc_base,
        train_auc_overlay=train_auc_overlay,
        train_ece_base=train_ece_base,
        train_ece_overlay=train_ece_overlay,
        n_test=n_test,
        test_brier_base=test_brier_base,
        test_brier_overlay=test_brier_overlay,
        test_auc_base=test_auc_base,
        test_auc_overlay=test_auc_overlay,
        test_ece_base=test_ece_base,
        test_ece_overlay=test_ece_overlay,
        sparse_clamped=sparse_clamped,
        sign_violated=sign_violated,
        min_feature_obs=min_feature_obs,
    )


def fit_overlay_time_split(
    records: list["POSOutcomeRecord"],
    base_rate_table: "BaseRateTable",
    cutoff_year: int,
    alpha: float = 1.0,
    min_feature_obs: int = 5,
    enforce_sign_gate: bool = True,
) -> OverlayArtifact:
    """
    Fit overlay with an explicit temporal train/test split.

    Records with outcome_date <= cutoff_year (or outcome_date is None) go to
    the train fold. Records with outcome_date > cutoff_year go to test.

    Parameters
    ----------
    records:
        All outcome records (censored excluded).
    base_rate_table:
        Fitted BaseRateTable.
    cutoff_year:
        Integer year (e.g. 2018). Train: year <= cutoff; test: year > cutoff.
    alpha:
        L2 regularization strength.
    min_feature_obs:
        Passed through to fit_overlay. Default 5.
    enforce_sign_gate:
        Passed through to fit_overlay. Default True.

    Returns
    -------
    OverlayArtifact with test metrics populated from the held-out fold.

    Raises
    ------
    ValueError if fewer than MIN_OVERLAY_RECORDS training records exist.
    """
    train, test = [], []
    for rec in records:
        try:
            yr = int(str(rec.outcome_date)[:4]) if rec.outcome_date else None
        except (ValueError, TypeError):
            yr = None
        if yr is None or yr <= cutoff_year:
            train.append(rec)
        else:
            test.append(rec)

    if len(train) < MIN_OVERLAY_RECORDS:
        raise ValueError(
            f"fit_overlay_time_split: only {len(train)} training records "
            f"before cutoff_year={cutoff_year} "
            f"(need >= {MIN_OVERLAY_RECORDS})."
        )

    logger.info(
        "fit_overlay_time_split: cutoff=%d  train=%d  test=%d",
        cutoff_year, len(train), len(test),
    )

    return fit_overlay(
        records=train,
        base_rate_table=base_rate_table,
        alpha=alpha,
        cutoff_year=cutoff_year,
        test_records=test if test else None,
        min_feature_obs=min_feature_obs,
        enforce_sign_gate=enforce_sign_gate,
    )


# ---------------------------------------------------------------------------
# Alpha regularization sweep
# ---------------------------------------------------------------------------

@dataclass
class AlphaSweepEntry:
    """Result of fitting the overlay at one alpha value."""
    alpha: float
    train_brier: float
    test_brier: Optional[float]
    test_auc: Optional[float]
    test_ece: Optional[float]
    n_sparse_clamped: int
    n_sign_violated: int
    converged: bool


def sweep_alpha(
    records: list["POSOutcomeRecord"],
    base_rate_table: "BaseRateTable",
    alphas: Optional[list[float]] = None,
    cutoff_year: Optional[int] = None,
    test_records: Optional[list["POSOutcomeRecord"]] = None,
    min_feature_obs: int = 5,
    enforce_sign_gate: bool = True,
) -> list[AlphaSweepEntry]:
    """
    Fit the overlay at multiple alpha values and return per-alpha diagnostics.

    When cutoff_year is provided and test_records is None, splits records
    temporally via fit_overlay_time_split. When test_records is explicit,
    cutoff_year is informational only.

    Parameters
    ----------
    records:
        Outcome records (censored excluded).
    base_rate_table:
        Fitted BaseRateTable.
    alphas:
        L2 strengths to evaluate. Default [1.0, 3.0, 5.0, 10.0].
    cutoff_year:
        Temporal cutoff for automatic train/test split.
    test_records:
        Explicit held-out set (overrides temporal split).
    min_feature_obs:
        Sparse clamp threshold, forwarded to fit_overlay.
    enforce_sign_gate:
        Sign gate flag, forwarded to fit_overlay.

    Returns
    -------
    list[AlphaSweepEntry] — one entry per alpha value, in input order.
    """
    if alphas is None:
        alphas = [1.0, 3.0, 5.0, 10.0]

    results: list[AlphaSweepEntry] = []
    for a in alphas:
        if cutoff_year is not None and test_records is None:
            art = fit_overlay_time_split(
                records=records,
                base_rate_table=base_rate_table,
                cutoff_year=cutoff_year,
                alpha=a,
                min_feature_obs=min_feature_obs,
                enforce_sign_gate=enforce_sign_gate,
            )
        else:
            art = fit_overlay(
                records=records,
                base_rate_table=base_rate_table,
                alpha=a,
                cutoff_year=cutoff_year,
                test_records=test_records,
                min_feature_obs=min_feature_obs,
                enforce_sign_gate=enforce_sign_gate,
            )
        entry = AlphaSweepEntry(
            alpha=a,
            train_brier=art.train_brier_overlay,
            test_brier=art.test_brier_overlay,
            test_auc=art.test_auc_overlay,
            test_ece=art.test_ece_overlay,
            n_sparse_clamped=len(art.sparse_clamped),
            n_sign_violated=len(art.sign_violated),
            converged=art.converged,
        )
        results.append(entry)
        logger.info(
            "sweep_alpha: alpha=%.1f  train_brier=%.4f  test_brier=%s  "
            "sparse=%d  sign_violated=%d  converged=%s",
            a, art.train_brier_overlay,
            f"{art.test_brier_overlay:.4f}" if art.test_brier_overlay is not None else "n/a",
            len(art.sparse_clamped), len(art.sign_violated), art.converged,
        )
    return results
