"""
Historical calibration runner — Sprint E.

Loads historical_calibration_cases.yaml, computes raw ma_scores using the
same formula as the live weekly scorer, fits the Layer 5 calibration artifact,
and returns a structured report.

Usage::

    from pathlib import Path
    from bve.intelligence.calibration_runner import run_historical_calibration

    artifact, report = run_historical_calibration()
    print(report.summary())

Design
------
Raw ma_score formula (mirrors weekly_ma_screen._score_target):

    target_strength = 0.35 * asset_quality
                    + 0.25 * seller_willingness
                    + 0.20 * ma_attractiveness    (neutral=0.50 if missing)
                    + 0.20 * catalyst_timing       (derived from catalyst_days)

    raw_score = 0.65 * target_strength + 0.35 * acquirer_fit_score

    ma_score  = sigmoid(-2.0 + 4.0 * raw_score)

Catalyst timing conversion::

    catalyst_days is None  →  0.50 (neutral)
    0                      →  1.00 (catalyst imminent)
    30                     →  0.92
    90                     →  0.75
    180                    →  0.51
    365                    →  0.00

This is the same logistic decay used in the live scorer.

Calibration quality thresholds
-------------------------------
  N ≥ 30   — Platt scaling viable; Bayesian bins computed
  ECE ≤ 0.10  — acceptable calibration
  ECE ≤ 0.05  — good calibration
  AUC ≥ 0.65  — minimal discriminative skill
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Optional

import yaml

from bve.intelligence.ma_calibration_models import (
    CalibrationArtifact,
    HistoricalMAOutcome,
    HistoricalTargetFeatures,
    OutcomeLabels,
    OutcomeType,
)
from bve.intelligence.ma_probability_calibration import calibrate_ma_scores

# Default path (overridable via argument)
_DEFAULT_CASES_PATH = (
    Path(__file__).parents[3] / "research" / "mna" / "historical_calibration_cases.yaml"
)

# Calibration quality thresholds
_ECE_ACCEPTABLE = 0.10
_ECE_GOOD = 0.05
_AUC_MIN_SKILL = 0.65
_MIN_PLATT = 30


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def _catalyst_timing_score(catalyst_days: Optional[int]) -> float:
    """Convert catalyst_days_as_of → [0, 1] timing score."""
    if catalyst_days is None:
        return 0.50
    # Logistic decay: 0 days → 1.0, 365 days → ~0.0
    return max(0.0, min(1.0, 1.0 - catalyst_days / 365.0))


def _compute_raw_ma_score(
    asset_quality: float,
    seller_willingness: float,
    acquirer_fit: float,
    catalyst_days: Optional[int],
    ma_attractiveness: float = 0.50,
) -> float:
    """Compute raw ma_score using the live-scorer formula."""
    timing = _catalyst_timing_score(catalyst_days)
    target_strength = (
        0.35 * asset_quality
        + 0.25 * seller_willingness
        + 0.20 * ma_attractiveness
        + 0.20 * timing
    )
    raw_score = 0.65 * target_strength + 0.35 * acquirer_fit
    return round(_sigmoid(-2.0 + 4.0 * raw_score), 6)


def _parse_outcome_type(outcome_type_str: str) -> OutcomeType:
    """Map YAML outcome_type string → OutcomeType enum."""
    _MAP = {
        "acquisition": OutcomeType.FULL_ACQUISITION_CLOSED,
        "full_acquisition": OutcomeType.FULL_ACQUISITION_CLOSED,
        "asset_acquisition": OutcomeType.ASSET_ACQUISITION,
        "license": OutcomeType.GLOBAL_LICENSE,
        "partnership": OutcomeType.STRATEGIC_COLLABORATION,
        "no_deal": OutcomeType.REMAINED_INDEPENDENT_PERFORMED_WELL,
        "remained_independent": OutcomeType.REMAINED_INDEPENDENT_PERFORMED_WELL,
        "clinical_failure": OutcomeType.CLINICAL_FAILURE,
        "bankruptcy": OutcomeType.BANKRUPTCY_OR_WIND_DOWN,
        "distressed_financing": OutcomeType.DISTRESSED_FINANCING,
    }
    return _MAP.get(str(outcome_type_str).lower(), OutcomeType.UNKNOWN_OR_UNRESOLVED)


def _case_to_historical_outcome(case: dict[str, Any], idx: int) -> Optional[HistoricalMAOutcome]:
    """Convert one YAML case dict to a HistoricalMAOutcome."""
    try:
        ticker = str(case.get("ticker", f"UNKNOWN_{idx}"))
        obs_date_raw = case.get("observation_date")
        if obs_date_raw is None:
            return None
        obs_date = date.fromisoformat(str(obs_date_raw))

        outcome_date_raw = case.get("outcome_date")
        outcome_date = date.fromisoformat(str(outcome_date_raw)) if outcome_date_raw else None

        asset_quality = float(case.get("asset_quality_score_as_of", 0.50))
        seller_willingness = float(case.get("seller_willingness_as_of", 0.50))
        acquirer_fit = float(case.get("acquirer_fit_score_as_of", 0.50))
        catalyst_days_raw = case.get("catalyst_days_as_of")
        catalyst_days = int(catalyst_days_raw) if catalyst_days_raw is not None else None

        raw_score = _compute_raw_ma_score(
            asset_quality=asset_quality,
            seller_willingness=seller_willingness,
            acquirer_fit=acquirer_fit,
            catalyst_days=catalyst_days,
        )

        outcome_12m = bool(case.get("outcome_12m", False))
        outcome_type_str = str(case.get("outcome_type", "no_deal"))
        outcome_type = _parse_outcome_type(outcome_type_str)

        ta = str(case.get("therapeutic_area", "unknown"))
        stage = str(case.get("target_stage", "unknown"))
        modality = str(case.get("modality", "unknown"))

        return HistoricalMAOutcome(
            case_id=f"{ticker}_{obs_date.isoformat()}",
            target_id=ticker,
            prediction_date=obs_date,
            outcome_date=outcome_date,
            observation_window_months=12,
            as_of_date=obs_date,
            layer1_snapshot={"layer1_score": raw_score},
            layer2_snapshot={"bd_action_score": raw_score},
            target_features=HistoricalTargetFeatures(
                therapeutic_area=ta,
                stage=stage,
                modality=modality,
                cash_runway_months=float(case.get("cash_runway_months_as_of", 0)) or None,
            ),
            outcome_type=outcome_type,
            labels=OutcomeLabels(
                acquired_within_12m=outcome_12m,
                acquired_within_24m=outcome_12m,  # conservative: assume 12m ⊂ 24m window
                any_strategic_transaction_12m=outcome_12m,
                remained_independent_12m=not outcome_12m,
            ),
            source_refs=list(case.get("source_refs", [])),
            leakage_checks_passed=bool(case.get("lookahead_pass", True)),
            excluded_from_training=not bool(case.get("lookahead_pass", True)),
        )
    except Exception:
        return None


def load_cases(path: Optional[Path] = None) -> list[HistoricalMAOutcome]:
    """Load and parse historical calibration cases from YAML."""
    p = path or _DEFAULT_CASES_PATH
    with open(p, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    case_dicts = raw.get("cases", []) if isinstance(raw, dict) else raw
    outcomes: list[HistoricalMAOutcome] = []
    for idx, c in enumerate(case_dicts):
        obj = _case_to_historical_outcome(c, idx)
        if obj is not None:
            outcomes.append(obj)
    return outcomes


@dataclass
class CalibrationReport:
    """Human-readable summary of the calibration run."""

    n_cases: int
    n_positive: int
    n_negative: int
    n_excluded: int
    base_rate: Optional[float]
    brier_score: Optional[float]
    ece: Optional[float]
    auc: Optional[float]
    quality_label: str
    calibration_status: str  # "calibrated" | "insufficient_data" | "poor_quality"
    warnings: list[str]
    artifact_id: str

    def summary(self) -> str:
        lines = [
            f"Calibration Run — {self.artifact_id}",
            f"  N total:   {self.n_cases} ({self.n_positive} positive / {self.n_negative} negative)",
            f"  Excluded:  {self.n_excluded}",
            f"  Base rate: {self.base_rate:.1%}" if self.base_rate else "  Base rate: N/A",
            f"  Brier:     {self.brier_score:.4f}" if self.brier_score else "  Brier:     N/A",
            f"  ECE:       {self.ece:.4f}" if self.ece else "  ECE:       N/A",
            f"  AUC:       {self.auc:.4f}" if self.auc else "  AUC:       N/A",
            f"  Quality:   {self.quality_label}",
            f"  Status:    {self.calibration_status}",
        ]
        if self.warnings:
            lines.append("  Warnings:")
            for w in self.warnings:
                lines.append(f"    - {w}")
        return "\n".join(lines)


def run_historical_calibration(
    cases_path: Optional[Path] = None,
    artifact_id: str = "historical_cases_v1",
) -> tuple[CalibrationArtifact, CalibrationReport]:
    """
    Load historical cases, fit calibration, return (artifact, report).

    Parameters
    ----------
    cases_path:
        Path to historical_calibration_cases.yaml. Defaults to the
        canonical research/mna/ location.
    artifact_id:
        Identifier stamped on the CalibrationArtifact.

    Returns
    -------
    (CalibrationArtifact, CalibrationReport)
        Artifact can be passed directly to predict_calibrated_probabilities().
        Report.calibration_status is "calibrated" when N≥30 and ECE≤0.10.
    """
    cases = load_cases(cases_path)
    artifact = calibrate_ma_scores(cases, artifact_id=artifact_id)

    diag = artifact.training_diagnostics
    n = diag.sample_size
    n_total = len(cases)
    n_excluded = sum(1 for c in cases if c.excluded_from_training)
    n_positive = sum(
        1 for c in cases
        if not c.excluded_from_training and c.labels.acquired_within_12m
    )
    n_negative = n - n_positive

    warnings = list(diag.warnings)

    # Determine calibration status
    ece = diag.expected_calibration_error
    auc = diag.auc
    brier = diag.brier_score

    if n < _MIN_PLATT:
        cal_status = "insufficient_data"
        warnings.insert(0, f"N={n} < {_MIN_PLATT} required for Platt scaling")
    elif ece is not None and ece > _ECE_ACCEPTABLE:
        cal_status = "poor_quality"
        warnings.insert(0, f"ECE={ece:.4f} > {_ECE_ACCEPTABLE} threshold")
    else:
        cal_status = "calibrated"

    report = CalibrationReport(
        n_cases=n_total,
        n_positive=n_positive,
        n_negative=n_negative,
        n_excluded=n_excluded,
        base_rate=diag.base_rate,
        brier_score=brier,
        ece=ece,
        auc=auc,
        quality_label=artifact.training_diagnostics.calibration_method,
        calibration_status=cal_status,
        warnings=warnings,
        artifact_id=artifact_id,
    )
    return artifact, report
