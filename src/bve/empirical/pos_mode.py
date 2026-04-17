"""
POSMode — flag controlling which POS layer ValuationEngine uses.

Three modes:
    HEURISTIC          : heuristic log-odds model (pos_model.py) — current default
    EMPIRICAL_RAW      : empirical base rates + heuristic adjusters (EmpiricalPOSEngine)
    EMPIRICAL_CALIBRATED : empirical + adjusters + calibration artifact

HeuristicVsEmpiricalComparison
    Side-by-side comparison of heuristic and empirical predictions for the same input.
    Useful for auditing how much the empirical layer shifts outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class POSMode(str, Enum):
    """
    Controls which probability-of-success layer is applied by ValuationEngine.

    HEURISTIC
        Use pos_model.compute_pos() with hand-calibrated log-odds adjusters
        and PHASE_SUCCESS_RATES base rates. Default; no empirical data required.

    EMPIRICAL_RAW
        Use EmpiricalPOSEngine.compute_pos_with_adjusters() — empirical base
        rates from real outcome data + heuristic log-odds adjusters.
        Requires empirical_pos_engine to be set on ValuationEngine.

    EMPIRICAL_CALIBRATED
        Like EMPIRICAL_RAW, then apply the CalibrationArtifact fitted on the
        training split. Requires empirical_pos_engine to be set AND the engine
        to have been fitted with a calibration artifact.

    EMPIRICAL_FITTED
        Empirical base rate (phase-only offset) + fitted logistic regression
        overlay (OverlayArtifact) trained on real outcome records. Replaces
        the heuristic adjuster layer with data-driven coefficients.
        Requires empirical_pos_engine to be set AND an OverlayArtifact to be
        attached via engine.attach_overlay(). Calibration may be layered on
        top via engine.attach_calibration().
    """
    HEURISTIC = "heuristic"
    EMPIRICAL_RAW = "empirical_raw"
    EMPIRICAL_CALIBRATED = "empirical_calibrated"
    EMPIRICAL_FITTED = "empirical_fitted"


@dataclass
class TrialPOSComparison:
    """Per-trial comparison of heuristic vs empirical POS estimates."""
    phase: str
    heuristic_pos: float
    empirical_raw_pos: float
    empirical_calibrated_pos: Optional[float]
    delta_heuristic_vs_raw: float      # empirical_raw - heuristic
    delta_heuristic_vs_calib: Optional[float]  # empirical_calibrated - heuristic
    agree_within_5pp: bool             # |empirical_raw - heuristic| < 0.05

    def __str__(self) -> str:
        calib_str = f"calib={self.empirical_calibrated_pos:.3f}" if self.empirical_calibrated_pos is not None else "calib=n/a"
        agree = "AGREE" if self.agree_within_5pp else "DIVERGE"
        return (
            f"Phase {self.phase}: "
            f"heuristic={self.heuristic_pos:.3f}  "
            f"empirical={self.empirical_raw_pos:.3f}  "
            f"{calib_str}  "
            f"Δ={self.delta_heuristic_vs_raw:+.3f}  [{agree}]"
        )


@dataclass
class HeuristicVsEmpiricalComparison:
    """
    Side-by-side comparison of heuristic and empirical POS for a set of trials.

    Produced by compare_pos_modes(); useful for auditing whether the empirical
    layer materially shifts valuation outcomes.
    """
    trials: list[TrialPOSComparison]
    cumulative_heuristic_pos: float
    cumulative_empirical_raw_pos: float
    cumulative_empirical_calibrated_pos: Optional[float]
    max_delta: float
    n_diverging: int   # trials with |empirical - heuristic| >= 0.05

    def summary(self) -> str:
        lines = [
            "=== Heuristic vs Empirical POS Comparison ===",
            f"  Cumulative heuristic        : {self.cumulative_heuristic_pos:.3f}",
            f"  Cumulative empirical (raw)  : {self.cumulative_empirical_raw_pos:.3f}",
        ]
        if self.cumulative_empirical_calibrated_pos is not None:
            lines.append(
                f"  Cumulative empirical (calib): {self.cumulative_empirical_calibrated_pos:.3f}"
            )
        lines += [
            f"  Max per-trial Δ            : {self.max_delta:+.3f}",
            f"  Diverging trials (≥5pp)    : {self.n_diverging}",
            "",
        ]
        for t in self.trials:
            lines.append(f"  {t}")
        return "\n".join(lines)


def compare_pos_modes(
    trials: list,          # list[ClinicalTrial]
    asset,                 # Asset
    empirical_engine,      # EmpiricalPOSEngine
    pos_adjusters: Optional[dict] = None,
) -> HeuristicVsEmpiricalComparison:
    """
    Compare heuristic and empirical POS estimates for each trial.

    Parameters
    ----------
    trials:
        ClinicalTrial objects to evaluate.
    asset:
        Asset entity (for therapeutic_area, approval_pathway).
    empirical_engine:
        Fitted EmpiricalPOSEngine.
    pos_adjusters:
        Per-phase POSAdjusters dict (optional).

    Returns
    -------
    HeuristicVsEmpiricalComparison
    """
    from bve.models.pos_model import POSAdjusters, compute_pos

    comparisons = []
    cum_h = 1.0
    cum_e_raw = 1.0
    cum_e_calib: Optional[float] = 1.0 if empirical_engine.calibration is not None else None

    for trial in trials:
        adj = (pos_adjusters or {}).get(trial.phase, POSAdjusters())

        # Heuristic
        h_pos = compute_pos(trial.phase, asset.therapeutic_area, adj,
                            approval_pathway=getattr(asset, "approval_pathway", None))

        # Empirical raw
        e_raw_pos = empirical_engine.compute_pos_with_adjusters(
            phase=trial.phase,
            therapeutic_area=asset.therapeutic_area,
            adjusters=adj,
        )

        # Empirical calibrated
        e_calib_pos = None
        if empirical_engine.calibration is not None:
            e_calib_pos = empirical_engine.compute_calibrated_pos(
                phase=trial.phase,
                therapeutic_area=asset.therapeutic_area,
                adjusters=adj,
            )

        delta = round(e_raw_pos - h_pos, 4)
        delta_calib = round(e_calib_pos - h_pos, 4) if e_calib_pos is not None else None

        comparisons.append(TrialPOSComparison(
            phase=trial.phase.value if hasattr(trial.phase, "value") else str(trial.phase),
            heuristic_pos=h_pos,
            empirical_raw_pos=e_raw_pos,
            empirical_calibrated_pos=e_calib_pos,
            delta_heuristic_vs_raw=delta,
            delta_heuristic_vs_calib=delta_calib,
            agree_within_5pp=abs(delta) < 0.05,
        ))

        cum_h *= h_pos
        cum_e_raw *= e_raw_pos
        if cum_e_calib is not None and e_calib_pos is not None:
            cum_e_calib *= e_calib_pos

    max_delta = max((abs(c.delta_heuristic_vs_raw) for c in comparisons), default=0.0)
    n_diverge = sum(1 for c in comparisons if not c.agree_within_5pp)

    return HeuristicVsEmpiricalComparison(
        trials=comparisons,
        cumulative_heuristic_pos=round(cum_h, 6),
        cumulative_empirical_raw_pos=round(cum_e_raw, 6),
        cumulative_empirical_calibrated_pos=round(cum_e_calib, 6) if cum_e_calib is not None else None,
        max_delta=round(max_delta, 4),
        n_diverging=n_diverge,
    )
