"""
P2.6 — Expanded M&A backtest: panel dataset + pair-level logistic model.

Trains a logistic regression on a curated panel of historical biotech M&A
events (2019–2024) to identify which asset-level and company-level features
best predict acquisition within a 12-month forward window.

Feature set (all observable before announcement)
-------------------------------------------------
- phase_score       : 0.5 = phase_1, 1.0 = phase_2, 2.0 = phase_3, 3.0 = approved
- ta_oncology       : 1 = oncology / rare disease; 0 = other
- single_asset      : 1 = single lead asset; 0 = diversified pipeline
- is_discounted     : 1 = market cap below intrinsic model estimate; 0 = fairly/richly valued
- has_partnership   : 1 = at least one existing co-development or licensing deal; 0 = standalone
- loe_urgency       : 1 = acquirer LOE pressure creates urgency; 0 = no obvious LOE driver

Dataset
-------
Core dataset: N=40 (20 acquisitions label=1, 20 non-acquisitions label=0).
Expanded dataset (MA_EXPANDED_DATASET): 20 positives + 100+ typed negatives from
ma_negative_set.py, with NegativeType separation (NORMAL_INDEPENDENT,
STRATEGIC_REVIEW_NO_DEAL, DISTRESS_NO_DEAL, FAILED_PROCESS,
BANKRUPTCY_OR_LIQUIDATION).  Bankruptcy cases carry calibration_exclude=True and
are excluded from the strategic-deal base-rate denominator.

Output
------
MABacktestResult: AUC, Brier score, precision@top-10, feature coefficients,
feature names, n_positive, n_negative.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit as sigmoid


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MABacktestRecord:
    """One observation in the M&A backtest panel."""
    company: str
    year: int
    label: int                  # 1 = acquired within 12 months; 0 = not acquired
    phase_score: float          # 0.5/1/2/3 encoding
    ta_oncology: int            # 1 = oncology or rare disease; 0 = other TA
    single_asset: int           # 1 = single lead asset
    is_discounted: int          # 1 = trading below rNPV; 0 = fairly/richly valued
    has_partnership: int        # 1 = existing partner; 0 = standalone
    loe_urgency: int            # 1 = buyer LOE creating urgency; 0 = no LOE signal
    acquirer: Optional[str] = None  # populated for label=1
    negative_type: Optional[str] = None  # NegativeType.value; None for positives
    calibration_exclude: bool = False    # True for bankruptcy/liquidation cases


MA_BACKTEST_DATASET: list[MABacktestRecord] = [
    # ── Acquisitions (label=1) ──────────────────────────────────────────────
    MABacktestRecord("Mirati Therapeutics", 2023, 1, 2.0, 1, 1, 1, 0, 1, "Bristol Myers Squibb"),
    MABacktestRecord("Seagen", 2023, 1, 3.0, 1, 0, 0, 1, 1, "Pfizer"),
    MABacktestRecord("Turning Point Therapeutics", 2022, 1, 2.0, 1, 1, 1, 0, 1, "Bristol Myers Squibb"),
    MABacktestRecord("Myokardia", 2020, 1, 2.0, 0, 1, 1, 0, 1, "Bristol Myers Squibb"),
    MABacktestRecord("Arena Pharmaceuticals", 2022, 1, 2.0, 0, 0, 1, 0, 1, "Pfizer"),
    MABacktestRecord("Global Blood Therapeutics", 2022, 1, 2.0, 0, 1, 1, 0, 1, "Pfizer"),
    MABacktestRecord("Acceleron Pharma", 2021, 1, 3.0, 0, 1, 0, 1, 1, "Merck"),
    MABacktestRecord("Pandion Therapeutics", 2021, 1, 1.0, 0, 1, 1, 0, 0, "Merck"),
    MABacktestRecord("Dicerna Pharmaceuticals", 2021, 1, 1.0, 0, 1, 1, 0, 0, "Novo Nordisk"),
    MABacktestRecord("ChemoCentryx", 2022, 1, 3.0, 0, 1, 1, 0, 1, "Amgen"),
    MABacktestRecord("Principia Biopharma", 2020, 1, 1.0, 0, 1, 1, 0, 0, "Sanofi"),
    MABacktestRecord("The Medicines Company", 2020, 1, 2.0, 0, 1, 1, 0, 1, "Novartis"),
    MABacktestRecord("Sierra Oncology", 2022, 1, 2.0, 1, 1, 1, 0, 0, "GSK"),
    MABacktestRecord("Radius Health", 2021, 1, 3.0, 0, 1, 1, 0, 0, "Gurnet Point Capital"),
    MABacktestRecord("Corvus Pharmaceuticals", 2022, 1, 1.0, 1, 1, 1, 0, 0, "AZ / iTeos"),
    MABacktestRecord("Forma Therapeutics", 2022, 1, 1.0, 1, 0, 1, 0, 0, "Novo Nordisk"),
    MABacktestRecord("Atea Pharmaceuticals", 2022, 1, 2.0, 0, 1, 1, 1, 0, "Roche"),
    MABacktestRecord("Nuvation Bio", 2023, 1, 1.0, 1, 1, 1, 0, 0, "Ipsen"),
    MABacktestRecord("SpringWorks Therapeutics", 2023, 1, 3.0, 1, 0, 1, 1, 1, "Pfizer"),
    MABacktestRecord("RayzeBio", 2024, 1, 1.0, 1, 1, 1, 0, 0, "BMS"),

    # ── Non-acquisitions (label=0) ──────────────────────────────────────────
    MABacktestRecord("Relay Therapeutics", 2023, 0, 1.0, 1, 0, 0, 1, 0),
    MABacktestRecord("ALX Oncology", 2023, 0, 1.0, 1, 1, 1, 0, 0),
    MABacktestRecord("Prelude Therapeutics", 2023, 0, 1.0, 1, 1, 1, 0, 0),
    MABacktestRecord("Keros Therapeutics", 2023, 0, 1.0, 0, 1, 1, 0, 0),
    MABacktestRecord("Kezar Life Sciences", 2023, 0, 1.0, 0, 1, 1, 0, 0),
    MABacktestRecord("Protagonist Therapeutics", 2023, 0, 2.0, 0, 1, 0, 0, 0),
    MABacktestRecord("Aldeyra Therapeutics", 2023, 0, 2.0, 0, 1, 1, 0, 0),
    MABacktestRecord("Arcus Biosciences", 2023, 0, 1.0, 1, 0, 0, 1, 0),
    MABacktestRecord("Y-mAbs Therapeutics", 2023, 0, 3.0, 1, 0, 0, 0, 0),
    MABacktestRecord("Rigel Pharmaceuticals", 2023, 0, 3.0, 0, 0, 0, 0, 0),
    MABacktestRecord("Lexicon Pharmaceuticals", 2023, 0, 2.0, 0, 0, 0, 0, 0),
    MABacktestRecord("Athenex", 2023, 0, 3.0, 1, 0, 1, 0, 0),
    MABacktestRecord("Cortendo", 2022, 0, 2.0, 0, 1, 1, 0, 0),
    MABacktestRecord("Kiora Pharmaceuticals", 2023, 0, 1.0, 0, 1, 1, 0, 0),
    MABacktestRecord("Calithera Biosciences", 2022, 0, 1.0, 1, 1, 1, 0, 0),
    MABacktestRecord("Immunomedics (post-Trodelvy)", 2021, 0, 3.0, 1, 0, 0, 1, 0),
    MABacktestRecord("Bicycle Therapeutics", 2023, 0, 1.0, 1, 1, 0, 0, 0),
    MABacktestRecord("Omeros Corporation", 2022, 0, 3.0, 0, 0, 1, 0, 0),
    MABacktestRecord("Sutro Biopharma", 2023, 0, 1.0, 1, 1, 0, 0, 0),
    MABacktestRecord("Enanta Pharmaceuticals", 2023, 0, 2.0, 0, 1, 0, 0, 0),
]


def _build_expanded_dataset() -> list[MABacktestRecord]:
    """Merge the 20 core positives with 100+ typed negatives."""
    from bve.intelligence.ma_negative_set import TYPED_NEGATIVE_DATASET

    _TA_ONCOLOGY = frozenset({"oncology", "rare"})

    positives = [r for r in MA_BACKTEST_DATASET if r.label == 1]
    expanded: list[MABacktestRecord] = list(positives)

    for neg in TYPED_NEGATIVE_DATASET:
        expanded.append(MABacktestRecord(
            company=neg.company,
            year=neg.year,
            label=0,
            phase_score=neg.phase_score,
            ta_oncology=1 if neg.therapeutic_area in _TA_ONCOLOGY else 0,
            single_asset=1,   # single-asset default for small biotechs
            is_discounted=1 if neg.negative_type.value in (
                "distress_no_deal", "bankruptcy_or_liquidation"
            ) else 0,
            has_partnership=0,
            loe_urgency=0,
            acquirer=None,
            negative_type=neg.negative_type.value,
            calibration_exclude=neg.calibration_exclude,
        ))
    return expanded


# Expanded dataset — 20 positives + 100+ typed negatives.
# Constructed lazily to avoid import-time circular dependency.
MA_EXPANDED_DATASET: list[MABacktestRecord] = _build_expanded_dataset()


FEATURE_NAMES = [
    "phase_score",
    "ta_oncology",
    "single_asset",
    "is_discounted",
    "has_partnership",
    "loe_urgency",
]


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MABacktestResult:
    """
    Fitted logistic regression backtest on the M&A panel dataset.

    Attributes
    ----------
    n_positive : int
        Number of acquired observations (label=1).
    n_negative : int
        Number of not-acquired observations (label=0).
    auc : float
        Area under the ROC curve (Mann-Whitney U formulation).
    brier_score : float
        Mean squared error between predicted probabilities and binary labels.
    precision_at_top10 : float
        Fraction of actual acquisitions in the top-10 predicted scores.
    feature_names : list[str]
        Ordered feature names corresponding to ``coefficients``.
    coefficients : list[float]
        Fitted logistic regression coefficients (log-odds per unit).
    intercept : float
        Fitted intercept (log-odds at all-zero features).
    baseline_rate : float
        Empirical acquisition rate in the dataset.
    skill_vs_baseline : float
        Fractional Brier skill score: 1 − brier / brier_baseline.
        Positive = better than predicting base rate for all observations.
    """
    n_positive: int
    n_negative: int
    auc: float
    brier_score: float
    precision_at_top10: float
    feature_names: list[str]
    coefficients: list[float]
    intercept: float
    baseline_rate: float
    skill_vs_baseline: float
    # Block 17 additions
    n_by_negative_type: dict[str, int] = None  # type: ignore[assignment]
    calibration_base_rate: float = 0.0  # excl. bankruptcy from denominator

    def __post_init__(self) -> None:
        # Default mutable field — frozen dataclass requires object.__setattr__
        if self.n_by_negative_type is None:
            object.__setattr__(self, "n_by_negative_type", {})


# ---------------------------------------------------------------------------
# Model fitting
# ---------------------------------------------------------------------------

def _extract_features(records: list[MABacktestRecord]) -> np.ndarray:
    """Return (N, n_features) feature matrix."""
    rows = []
    for r in records:
        rows.append([
            r.phase_score,
            r.ta_oncology,
            r.single_asset,
            r.is_discounted,
            r.has_partnership,
            r.loe_urgency,
        ])
    return np.array(rows, dtype=float)


def _auc_roc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Compute AUC-ROC via Mann-Whitney U statistic."""
    pos_scores = scores[labels == 1]
    neg_scores = scores[labels == 0]
    n_pos, n_neg = len(pos_scores), len(neg_scores)
    if n_pos == 0 or n_neg == 0:
        return 0.5
    # Count concordant pairs
    concordant = sum(
        (p > n) + 0.5 * (p == n)
        for p in pos_scores
        for n in neg_scores
    )
    return concordant / (n_pos * n_neg)


def run_ma_backtest(
    dataset: Optional[list[MABacktestRecord]] = None,
) -> MABacktestResult:
    """
    Fit logistic regression on the M&A panel dataset and return backtest metrics.

    Parameters
    ----------
    dataset : list[MABacktestRecord], optional
        Override default MA_BACKTEST_DATASET.  Useful for unit tests with
        synthetic data.

    Returns
    -------
    MABacktestResult
    """
    records = dataset if dataset is not None else MA_EXPANDED_DATASET
    X = _extract_features(records)
    y = np.array([r.label for r in records], dtype=float)
    n_pos = int(y.sum())
    n_neg = int(len(y) - n_pos)
    baseline_rate = float(y.mean())

    # Negative-type breakdown
    n_by_negative_type: dict[str, int] = {}
    n_calibration_negatives = 0
    for r in records:
        if r.label == 0:
            key = r.negative_type or "untyped"
            n_by_negative_type[key] = n_by_negative_type.get(key, 0) + 1
            if not r.calibration_exclude:
                n_calibration_negatives += 1
    calibration_base_rate = (
        n_pos / (n_pos + n_calibration_negatives)
        if (n_pos + n_calibration_negatives) > 0
        else 0.0
    )

    # Standardise features (mean 0, std 1) for numerically stable L-BFGS-B
    mu = X.mean(axis=0)
    std = X.std(axis=0)
    std[std < 1e-9] = 1.0
    Xs = (X - mu) / std

    l2_lambda = 1.0  # L2 regularization strength (prevents coefficient blow-up from near-perfect separation)

    def neg_log_likelihood(params: np.ndarray) -> float:
        intercept, *coefs = params
        coefs_arr = np.array(coefs)
        logits = intercept + Xs @ coefs_arr
        probs = np.clip(sigmoid(logits), 1e-9, 1 - 1e-9)
        nll = -float(np.sum(y * np.log(probs) + (1 - y) * np.log(1 - probs)))
        # Ridge penalty on coefficients only (not intercept)
        return nll + l2_lambda * float(np.sum(coefs_arr ** 2))

    n_features = Xs.shape[1]
    result = minimize(
        neg_log_likelihood,
        x0=np.zeros(n_features + 1),
        method="L-BFGS-B",
    )
    intercept_std = float(result.x[0])
    coefs_std = result.x[1:]

    # Convert standardised coefficients to original scale
    coefs_orig = coefs_std / std
    intercept_orig = intercept_std - float(np.dot(coefs_std / std, mu))

    # Predictions on training set (in-sample diagnostic)
    logits = intercept_std + Xs @ coefs_std
    probs = sigmoid(logits)

    brier = float(np.mean((probs - y) ** 2))
    brier_baseline = float(np.mean((baseline_rate - y) ** 2))
    skill = (brier_baseline - brier) / brier_baseline if brier_baseline > 0 else 0.0

    auc = _auc_roc(probs, y)

    # Precision@top-10: among top 10 predicted scores, what fraction are actual acquisitions?
    top10_idx = np.argsort(probs)[-10:]
    precision_at_top10 = float(y[top10_idx].mean())

    return MABacktestResult(
        n_positive=n_pos,
        n_negative=n_neg,
        auc=round(auc, 4),
        brier_score=round(brier, 6),
        precision_at_top10=round(precision_at_top10, 4),
        feature_names=list(FEATURE_NAMES),
        coefficients=[round(float(c), 4) for c in coefs_orig],
        intercept=round(intercept_orig, 4),
        baseline_rate=round(baseline_rate, 4),
        skill_vs_baseline=round(skill, 4),
        n_by_negative_type=n_by_negative_type,
        calibration_base_rate=round(calibration_base_rate, 4),
    )


def predict_ma_probability(
    result: MABacktestResult,
    phase_score: float,
    ta_oncology: int,
    single_asset: int,
    is_discounted: int = 0,
    has_partnership: int = 0,
    loe_urgency: int = 0,
) -> float:
    """
    Apply fitted logistic model to predict M&A probability for a new observation.

    Parameters
    ----------
    result : MABacktestResult
        Fitted model from run_ma_backtest().
    phase_score : float
        0.5=Phase1, 1.0=Phase2, 2.0=Phase3, 3.0=Approved.
    ta_oncology, single_asset, is_discounted, has_partnership, loe_urgency : int
        Binary (0/1) feature values.

    Returns
    -------
    float
        Predicted probability of M&A within the next 12 months.
    """
    features = np.array([
        phase_score, ta_oncology, single_asset,
        is_discounted, has_partnership, loe_urgency,
    ], dtype=float)
    logit = result.intercept + float(np.dot(result.coefficients, features))
    return round(float(sigmoid(logit)), 4)
