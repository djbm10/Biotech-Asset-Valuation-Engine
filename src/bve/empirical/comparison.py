"""
Cross-mode POS evaluation — compare heuristic, empirical_base, empirical_heuristic,
and empirical_fitted POS predictions on the same outcome dataset.

Four modes evaluated on each test record:
    heuristic_only       — pos_model.compute_pos() with adjusters from record fields
    empirical_base_only  — phase-level Laplace-smoothed rate; no adjusters
    empirical_heuristic  — empirical base + hand-tuned log-odds adjusters
    empirical_fitted     — empirical base + fitted logistic overlay (optional)

Usage
-----
from bve.empirical.comparison import compare_all_modes

result = compare_all_modes(
    engine,
    records,
    cutoff_year=2019,
    overlay_artifact=artifact,
)
print(result.summary())
print("Fitted beats heuristic (Brier):", result.fitted_beats_heuristic())
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from bve.empirical.engine import EmpiricalPOSEngine
    from bve.empirical.overlay_model import OverlayArtifact
    from bve.empirical.pos_outcome import POSOutcomeRecord

logger = logging.getLogger(__name__)

_MODE_HEURISTIC = "heuristic_only"
_MODE_BASE = "empirical_base_only"
_MODE_HEURISTIC_EMP = "empirical_heuristic"
_MODE_FITTED = "empirical_fitted"


# ---------------------------------------------------------------------------
# Metric helpers (local; mirror evaluator.py without circular imports)
# ---------------------------------------------------------------------------

def _brier(preds: list[float], outcomes: list[bool]) -> float:
    if not preds:
        return 0.0
    return round(sum((p - float(y)) ** 2 for p, y in zip(preds, outcomes)) / len(preds), 4)


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
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ModeEvalResult:
    """Evaluation metrics for one POS mode on the test fold."""
    mode: str
    brier: float
    auc: Optional[float]
    ece: float
    n_samples: int
    mean_pred: float       # mean predicted probability (calibration sanity check)
    mean_outcome: float    # empirical success rate on the test fold

    def __str__(self) -> str:
        auc_str = f"{self.auc:.4f}" if self.auc is not None else "  n/a"
        return (
            f"{self.mode:<28}  Brier={self.brier:.4f}  AUC={auc_str}"
            f"  ECE={self.ece:.4f}  n={self.n_samples}"
            f"  mean_pred={self.mean_pred:.3f}"
        )


@dataclass
class POSModeComparison:
    """
    Side-by-side evaluation of all POS modes on the test fold.

    Attributes
    ----------
    modes:          Evaluation results for each mode (in evaluation order).
    cutoff_year:    Train/test cutoff year, or None (in-sample evaluation).
    n_train:        Number of training records (informational).
    n_test:         Number of test records evaluated.
    best_mode_by_brier: Mode with lowest Brier score on test set.
    best_mode_by_auc:   Mode with highest AUC (None when AUC not computable).
    empirical_success_rate: Observed success rate on test fold.
    """
    modes: list[ModeEvalResult]
    cutoff_year: Optional[int]
    n_train: int
    n_test: int
    best_mode_by_brier: str
    best_mode_by_auc: Optional[str]
    empirical_success_rate: float

    def get(self, mode_name: str) -> Optional[ModeEvalResult]:
        """Return ModeEvalResult for a specific mode name, or None."""
        for m in self.modes:
            if m.mode == mode_name:
                return m
        return None

    def fitted_beats_heuristic(self) -> Optional[bool]:
        """
        True if empirical_fitted has lower Brier than heuristic_only.
        None if either mode is absent.
        """
        fitted = self.get(_MODE_FITTED)
        heuristic = self.get(_MODE_HEURISTIC)
        if fitted is None or heuristic is None:
            return None
        return fitted.brier < heuristic.brier

    def fitted_beats_empirical_heuristic(self) -> Optional[bool]:
        """True if empirical_fitted beats empirical_heuristic on Brier."""
        fitted = self.get(_MODE_FITTED)
        emp_h = self.get(_MODE_HEURISTIC_EMP)
        if fitted is None or emp_h is None:
            return None
        return fitted.brier < emp_h.brier

    def summary(self) -> str:
        split_desc = f"cutoff_year={self.cutoff_year}" if self.cutoff_year else "in-sample"
        lines = [
            f"=== POS Mode Comparison ({split_desc}) ===",
            f"  Train records : {self.n_train}",
            f"  Test records  : {self.n_test}",
            f"  Test success rate: {self.empirical_success_rate:.1%}",
            "",
            f"  {'Mode':<28}  {'Brier':>6}  {'AUC':>6}  {'ECE':>6}  n",
            f"  {'-'*28}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*4}",
        ]
        best_brier = min(self.modes, key=lambda m: m.brier).brier if self.modes else None
        best_auc = (
            max((m.auc for m in self.modes if m.auc is not None), default=None)
        )
        for m in self.modes:
            auc_str = f"{m.auc:.4f}" if m.auc is not None else "   n/a"
            b_flag = " ✓" if m.brier == best_brier else "  "
            a_flag = " ✓" if m.auc is not None and m.auc == best_auc else "  "
            lines.append(
                f"  {m.mode:<28}  {m.brier:.4f}{b_flag}  {auc_str}{a_flag}"
                f"  {m.ece:.4f}  {m.n_samples}"
            )

        fb = self.fitted_beats_heuristic()
        fbe = self.fitted_beats_empirical_heuristic()
        lines += [
            "",
            f"  Best by Brier : {self.best_mode_by_brier}",
            f"  Best by AUC   : {self.best_mode_by_auc or 'n/a'}",
            f"  Fitted > Heuristic (Brier): {fb}",
            f"  Fitted > EmpHeuristic (Brier): {fbe}",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main comparison function
# ---------------------------------------------------------------------------

def compare_all_modes(
    engine: "EmpiricalPOSEngine",
    records: list["POSOutcomeRecord"],
    cutoff_year: Optional[int] = None,
    overlay_artifact: Optional["OverlayArtifact"] = None,
) -> POSModeComparison:
    """
    Evaluate all POS modes on the held-out test fold.

    Parameters
    ----------
    engine:
        Fitted EmpiricalPOSEngine (used for empirical base rate and heuristic
        overlay computations).
    records:
        All outcome records (censored excluded). Split internally by cutoff_year.
    cutoff_year:
        Integer year. Records with outcome_date > cutoff_year are used as test.
        If None, all records are evaluated in-sample (train = test = all).
    overlay_artifact:
        Optional fitted OverlayArtifact for the empirical_fitted mode.
        When None, that mode is skipped.

    Returns
    -------
    POSModeComparison
    """
    from bve.empirical.features import (
        build_feature_vector,
        record_to_adjusters,
    )
    from bve.models.pos_model import compute_pos
    from bve.entities.asset import TherapeuticArea
    from bve.entities.trial import TrialPhase

    # Split records
    if cutoff_year is None:
        train_records = records
        test_records = records
    else:
        train_records, test_records = [], []
        for rec in records:
            try:
                yr = int(str(rec.outcome_date)[:4]) if rec.outcome_date else None
            except (ValueError, TypeError):
                yr = None
            if yr is None or yr <= cutoff_year:
                train_records.append(rec)
            else:
                test_records.append(rec)

    n_train = len(train_records)
    n_test = len(test_records)

    if n_test == 0:
        logger.warning(
            "compare_all_modes: no test records for cutoff_year=%s. "
            "Returning empty comparison.",
            cutoff_year,
        )
        return POSModeComparison(
            modes=[],
            cutoff_year=cutoff_year,
            n_train=n_train,
            n_test=0,
            best_mode_by_brier="n/a",
            best_mode_by_auc=None,
            empirical_success_rate=0.0,
        )

    outcomes: list[bool] = [rec.success for rec in test_records]
    emp_success_rate = round(sum(outcomes) / len(outcomes), 4) if outcomes else 0.0

    # --- Compute per-record predictions in each mode ---
    h_preds: list[float] = []
    base_preds: list[float] = []
    emp_h_preds: list[float] = []
    fitted_preds: list[float] = []

    _CLIP = 1e-7
    ta = TherapeuticArea.ONCOLOGY  # default for bundled oncology dataset

    for rec in test_records:
        phase_str = rec.phase_at_entry
        try:
            phase_enum = TrialPhase(phase_str)
        except ValueError:
            phase_enum = TrialPhase.PHASE_2  # safe fallback for unrecognized phases
        adj = record_to_adjusters(rec)

        # Mode 1: heuristic_only
        h_pos = compute_pos(phase_enum, ta, adj)
        h_preds.append(h_pos)

        # Mode 2: empirical_base_only (phase-only rate, no adjusters)
        base_rate = engine._table.get(phase_str)
        base_preds.append(base_rate)

        # Mode 3: empirical_heuristic (empirical base + heuristic adjusters)
        emp_h_pos = engine.compute_pos_with_adjusters(phase_str, ta, adj)
        emp_h_preds.append(emp_h_pos)

        # Mode 4: empirical_fitted (empirical base + fitted overlay)
        if overlay_artifact is not None:
            fv = build_feature_vector(rec)
            p_base = base_rate
            p_base = max(_CLIP, min(1.0 - _CLIP, p_base))
            base_lo = math.log(p_base / (1.0 - p_base))
            fitted_pos = overlay_artifact.apply(fv, base_lo)
            fitted_preds.append(fitted_pos)

    # --- Compute metrics ---
    def _eval(mode_name: str, preds: list[float]) -> ModeEvalResult:
        return ModeEvalResult(
            mode=mode_name,
            brier=_brier(preds, outcomes),
            auc=_auc(preds, outcomes),
            ece=_ece(preds, outcomes),
            n_samples=len(preds),
            mean_pred=round(sum(preds) / len(preds), 4) if preds else 0.0,
            mean_outcome=emp_success_rate,
        )

    mode_results = [
        _eval(_MODE_HEURISTIC, h_preds),
        _eval(_MODE_BASE, base_preds),
        _eval(_MODE_HEURISTIC_EMP, emp_h_preds),
    ]
    if fitted_preds:
        mode_results.append(_eval(_MODE_FITTED, fitted_preds))

    # Best mode by each metric
    best_brier = min(mode_results, key=lambda m: m.brier).mode
    aucs = [(m.mode, m.auc) for m in mode_results if m.auc is not None]
    best_auc = max(aucs, key=lambda x: x[1])[0] if aucs else None

    return POSModeComparison(
        modes=mode_results,
        cutoff_year=cutoff_year,
        n_train=n_train,
        n_test=n_test,
        best_mode_by_brier=best_brier,
        best_mode_by_auc=best_auc,
        empirical_success_rate=emp_success_rate,
    )
