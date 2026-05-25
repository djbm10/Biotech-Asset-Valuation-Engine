"""Layer 5 — 5G: Drift Detection Engine.

Detects when the distribution of inputs, scores, or outcomes has shifted
away from the calibration window, indicating that re-calibration may be needed.

Detection methods:
  - Population Stability Index (PSI) for feature/score distributions
  - Chi-squared test for categorical feature drift
  - Base rate drift: rolling window vs historical window
  - Calibration drift: Brier score or ECE degradation over time
  - Regime flags: antitrust, financing, premium environment changes

All drift reports are advisory. The engine never silently updates model
parameters. Drift signals require human review before action.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any, Optional

from bve.intelligence.ma_calibration_models import (
    DriftReport,
    DriftType,
    HistoricalMAOutcome,
    LayerValidated,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# PSI thresholds
_PSI_NO_DRIFT = 0.10
_PSI_MODERATE_DRIFT = 0.20   # above this → significant drift
_PSI_SEVERE_DRIFT = 0.25     # above this → severe drift, re-calibrate

# Minimum samples to compute PSI
_MIN_PSI_SAMPLES = 10

# Default number of bins for PSI
_PSI_BINS = 10

# Base rate drift: flag if rolling rate differs from historical by more than this
_BASE_RATE_DRIFT_THRESHOLD = 0.05   # 5 percentage points

# Brier score / ECE degradation threshold
_BRIER_DEGRADATION_THRESHOLD = 0.05

# Rolling window size for recent observations (number of cases)
_DEFAULT_ROLLING_WINDOW = 50


# ---------------------------------------------------------------------------
# PSI helpers
# ---------------------------------------------------------------------------

def _compute_psi_bins(
    reference: list[float],
    current: list[float],
    n_bins: int = _PSI_BINS,
) -> tuple[float, list[dict]]:
    """Compute Population Stability Index between reference and current distributions.

    Args:
        reference: Reference distribution scores (calibration window).
        current: Current distribution scores (recent window).
        n_bins: Number of equal-width bins.

    Returns:
        (psi_total, bin_details) where bin_details is a list of per-bin dicts.
    """
    if not reference or not current:
        return 0.0, []

    all_vals = reference + current
    lo = min(all_vals)
    hi = max(all_vals)
    if hi == lo:
        return 0.0, []

    bin_width = (hi - lo) / n_bins
    ref_n = len(reference)
    cur_n = len(current)

    bin_details = []
    psi_total = 0.0

    for i in range(n_bins):
        bin_lo = lo + i * bin_width
        bin_hi = lo + (i + 1) * bin_width if i < n_bins - 1 else hi + 1e-9

        ref_count = sum(1 for v in reference if bin_lo <= v < bin_hi)
        cur_count = sum(1 for v in current if bin_lo <= v < bin_hi)

        # Laplace smoothing to avoid division by zero
        ref_pct = max(ref_count / ref_n, 1e-6)
        cur_pct = max(cur_count / cur_n, 1e-6)

        psi_bin = (cur_pct - ref_pct) * math.log(cur_pct / ref_pct)
        psi_total += psi_bin

        bin_details.append({
            "bin": i,
            "bin_lo": round(bin_lo, 4),
            "bin_hi": round(bin_hi, 4),
            "ref_pct": round(ref_pct, 6),
            "cur_pct": round(cur_pct, 6),
            "psi_bin": round(psi_bin, 6),
        })

    return round(psi_total, 6), bin_details


def _psi_severity(psi: float) -> str:
    if psi < _PSI_NO_DRIFT:
        return "no_drift"
    if psi < _PSI_MODERATE_DRIFT:
        return "minor_drift"
    if psi < _PSI_SEVERE_DRIFT:
        return "moderate_drift"
    return "severe_drift"


# ---------------------------------------------------------------------------
# Score distribution drift
# ---------------------------------------------------------------------------

def detect_score_distribution_drift(
    reference_scores: list[float],
    current_scores: list[float],
    *,
    score_name: str = "bd_action_score",
    n_bins: int = _PSI_BINS,
) -> dict[str, Any]:
    """Detect drift in a score distribution using PSI.

    Args:
        reference_scores: Scores from calibration window.
        current_scores: Scores from recent window.
        score_name: Human-readable label for the score.
        n_bins: Number of PSI bins.

    Returns:
        Dict with keys: psi, severity, drift_detected, score_name, bin_details, warnings.
    """
    warnings: list[str] = []

    if len(reference_scores) < _MIN_PSI_SAMPLES:
        warnings.append(
            f"Reference window too small (n={len(reference_scores)}); "
            "PSI may be unreliable."
        )
    if len(current_scores) < _MIN_PSI_SAMPLES:
        warnings.append(
            f"Current window too small (n={len(current_scores)}); "
            "PSI may be unreliable."
        )

    psi, bin_details = _compute_psi_bins(reference_scores, current_scores, n_bins)
    severity = _psi_severity(psi)

    return {
        "score_name": score_name,
        "psi": psi,
        "severity": severity,
        "drift_detected": psi >= _PSI_NO_DRIFT,
        "bin_details": bin_details,
        "reference_n": len(reference_scores),
        "current_n": len(current_scores),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Base rate drift
# ---------------------------------------------------------------------------

def detect_base_rate_drift(
    historical_cases: list[HistoricalMAOutcome],
    recent_cases: list[HistoricalMAOutcome],
    *,
    label_attr: str = "acquired_within_12m",
    threshold: float = _BASE_RATE_DRIFT_THRESHOLD,
) -> dict[str, Any]:
    """Detect drift in acquisition base rate between historical and recent windows.

    Args:
        historical_cases: Cases from calibration window.
        recent_cases: Cases from recent window.
        label_attr: Label attribute to compare (e.g. 'acquired_within_12m').
        threshold: Flag drift if abs(recent_rate - historical_rate) > threshold.

    Returns:
        Dict with keys: historical_rate, recent_rate, drift, drift_detected, severity.
    """
    def _rate(cases: list[HistoricalMAOutcome]) -> Optional[float]:
        if not cases:
            return None
        positives = sum(
            1 for c in cases if getattr(c.labels, label_attr, False)
        )
        return positives / len(cases)

    hist_rate = _rate(historical_cases)
    rec_rate = _rate(recent_cases)

    if hist_rate is None or rec_rate is None:
        return {
            "label_attr": label_attr,
            "historical_rate": hist_rate,
            "recent_rate": rec_rate,
            "drift": None,
            "drift_detected": False,
            "severity": "insufficient_data",
            "warnings": ["Insufficient data in one or both windows."],
        }

    drift = rec_rate - hist_rate
    drift_detected = abs(drift) > threshold
    if abs(drift) < threshold:
        severity = "no_drift"
    elif abs(drift) < 2 * threshold:
        severity = "moderate_drift"
    else:
        severity = "severe_drift"

    return {
        "label_attr": label_attr,
        "historical_rate": round(hist_rate, 6),
        "recent_rate": round(rec_rate, 6),
        "drift": round(drift, 6),
        "drift_detected": drift_detected,
        "severity": severity,
        "historical_n": len(historical_cases),
        "recent_n": len(recent_cases),
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# Calibration quality drift (Brier score comparison)
# ---------------------------------------------------------------------------

def detect_calibration_quality_drift(
    reference_scores: list[float],
    reference_labels: list[bool],
    current_scores: list[float],
    current_labels: list[bool],
    *,
    threshold: float = _BRIER_DEGRADATION_THRESHOLD,
) -> dict[str, Any]:
    """Detect degradation in calibration quality (Brier score) over time.

    Args:
        reference_scores: Predicted scores in calibration window.
        reference_labels: Actual outcomes in calibration window.
        current_scores: Predicted scores in recent window.
        current_labels: Actual outcomes in recent window.
        threshold: Flag if Brier score increases by more than this.

    Returns:
        Dict with keys: reference_brier, current_brier, brier_delta, drift_detected.
    """
    def _brier(scores: list[float], labels: list[bool]) -> Optional[float]:
        if len(scores) != len(labels) or not scores:
            return None
        return sum((s - (1.0 if lbl else 0.0)) ** 2 for s, lbl in zip(scores, labels)) / len(scores)

    ref_brier = _brier(reference_scores, reference_labels)
    cur_brier = _brier(current_scores, current_labels)

    if ref_brier is None or cur_brier is None:
        return {
            "reference_brier": ref_brier,
            "current_brier": cur_brier,
            "brier_delta": None,
            "drift_detected": False,
            "severity": "insufficient_data",
            "warnings": ["Insufficient data for Brier drift comparison."],
        }

    delta = cur_brier - ref_brier
    drift_detected = delta > threshold
    severity = "no_drift"
    if delta > threshold:
        severity = "moderate_drift"
    if delta > 2 * threshold:
        severity = "severe_drift"

    return {
        "reference_brier": round(ref_brier, 6),
        "current_brier": round(cur_brier, 6),
        "brier_delta": round(delta, 6),
        "drift_detected": drift_detected,
        "severity": severity,
        "reference_n": len(reference_scores),
        "current_n": len(current_scores),
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# Categorical feature drift (chi-squared proxy)
# ---------------------------------------------------------------------------

def detect_categorical_drift(
    reference_values: list[str],
    current_values: list[str],
    *,
    feature_name: str = "therapeutic_area",
) -> dict[str, Any]:
    """Detect drift in a categorical feature using simple distribution comparison.

    Uses a simplified chi-squared-like statistic (sum of squared relative
    frequency differences). This is advisory only — for low sample sizes
    the result is unreliable.

    Args:
        reference_values: Feature values in calibration window.
        current_values: Feature values in recent window.
        feature_name: Human-readable name of the feature.

    Returns:
        Dict with keys: drift_stat, drift_detected, severity, distribution_shifts.
    """
    warnings: list[str] = []

    if len(reference_values) < _MIN_PSI_SAMPLES or len(current_values) < _MIN_PSI_SAMPLES:
        warnings.append("Sample sizes too small for reliable categorical drift detection.")

    # Build frequency tables
    ref_counts: dict[str, int] = {}
    for v in reference_values:
        ref_counts[v] = ref_counts.get(v, 0) + 1

    cur_counts: dict[str, int] = {}
    for v in current_values:
        cur_counts[v] = cur_counts.get(v, 0) + 1

    all_cats = sorted(set(ref_counts) | set(cur_counts))
    ref_n = max(len(reference_values), 1)
    cur_n = max(len(current_values), 1)

    drift_stat = 0.0
    distribution_shifts = []
    for cat in all_cats:
        ref_f = ref_counts.get(cat, 0) / ref_n
        cur_f = cur_counts.get(cat, 0) / cur_n
        diff = abs(cur_f - ref_f)
        drift_stat += diff ** 2
        if diff > 0.05:
            distribution_shifts.append({
                "category": cat,
                "reference_freq": round(ref_f, 4),
                "current_freq": round(cur_f, 4),
                "abs_diff": round(diff, 4),
            })

    drift_stat = round(math.sqrt(drift_stat), 6)

    if drift_stat < 0.10:
        severity = "no_drift"
    elif drift_stat < 0.20:
        severity = "moderate_drift"
    else:
        severity = "severe_drift"

    return {
        "feature_name": feature_name,
        "drift_stat": drift_stat,
        "drift_detected": drift_stat >= 0.10,
        "severity": severity,
        "distribution_shifts": distribution_shifts,
        "reference_n": len(reference_values),
        "current_n": len(current_values),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Regime flags
# ---------------------------------------------------------------------------

def _extract_scores(
    cases: list[HistoricalMAOutcome],
    *,
    field: str = "bd_action_score",
    snap: str = "layer2_snapshot",
) -> list[float]:
    """Extract a numeric field from a layer snapshot for a list of cases."""
    out = []
    for c in cases:
        snapshot = getattr(c, snap, None) or {}
        val = snapshot.get(field)
        if val is not None:
            try:
                out.append(float(val))
            except (TypeError, ValueError):
                pass
    return out


def _extract_categorical(
    cases: list[HistoricalMAOutcome],
    attr_path: str,
) -> list[str]:
    """Extract a string attribute from target_features for a list of cases.

    attr_path can be a dotted path like 'target_features.therapeutic_area'.
    """
    out = []
    for c in cases:
        parts = attr_path.split(".")
        obj: Any = c
        for part in parts:
            obj = getattr(obj, part, None)
            if obj is None:
                break
        if obj is not None:
            out.append(str(obj))
    return out


# ---------------------------------------------------------------------------
# Full drift report
# ---------------------------------------------------------------------------

def run_drift_detection(
    historical_cases: list[HistoricalMAOutcome],
    recent_cases: list[HistoricalMAOutcome],
    *,
    report_date: Optional[date] = None,
    rolling_window: int = _DEFAULT_ROLLING_WINDOW,
) -> DriftReport:
    """Run full drift detection comparing historical and recent case windows.

    Checks:
      1. BD action score distribution (PSI)
      2. Layer 1 score distribution (PSI)
      3. Acquisition base rate drift
      4. Calibration quality drift (Brier)
      5. Therapeutic area distribution drift

    Args:
        historical_cases: Reference window cases (calibration period).
        recent_cases: Recent window cases (post-calibration period).
        report_date: Date for the report (defaults to today).
        rolling_window: Max recent cases to use (most recent N).

    Returns:
        DriftReport summarizing all detected drift signals.
    """
    # Limit recent window
    recent = recent_cases[-rolling_window:] if len(recent_cases) > rolling_window else recent_cases

    drift_types: list[DriftType] = []
    drift_details: dict[str, Any] = {}
    recommendations: list[str] = []
    severity_flags: list[str] = []

    # -----------------------------------------------------------------------
    # 1. BD action score PSI
    # -----------------------------------------------------------------------
    ref_bd = _extract_scores(historical_cases, field="bd_action_score", snap="layer2_snapshot")
    cur_bd = _extract_scores(recent, field="bd_action_score", snap="layer2_snapshot")
    if ref_bd and cur_bd:
        bd_psi_result = detect_score_distribution_drift(
            ref_bd, cur_bd, score_name="bd_action_score"
        )
        drift_details["bd_action_score_psi"] = bd_psi_result
        if bd_psi_result["drift_detected"]:
            drift_types.append(DriftType.FEATURE_DISTRIBUTION_DRIFT)
            severity_flags.append(f"bd_action_score:{bd_psi_result['severity']}")
            if bd_psi_result["psi"] >= _PSI_SEVERE_DRIFT:
                recommendations.append(
                    "BD action score distribution has shifted severely (PSI=%.3f). "
                    "Review recent deal activity and Layer 2 signal weights." % bd_psi_result["psi"]
                )

    # -----------------------------------------------------------------------
    # 2. Layer 1 score PSI
    # -----------------------------------------------------------------------
    ref_l1 = _extract_scores(historical_cases, field="layer1_score", snap="layer1_snapshot")
    cur_l1 = _extract_scores(recent, field="layer1_score", snap="layer1_snapshot")
    if ref_l1 and cur_l1:
        l1_psi_result = detect_score_distribution_drift(
            ref_l1, cur_l1, score_name="layer1_score"
        )
        drift_details["layer1_score_psi"] = l1_psi_result
        if l1_psi_result["drift_detected"]:
            if DriftType.FEATURE_DISTRIBUTION_DRIFT not in drift_types:
                drift_types.append(DriftType.FEATURE_DISTRIBUTION_DRIFT)
            severity_flags.append(f"layer1_score:{l1_psi_result['severity']}")

    # -----------------------------------------------------------------------
    # 3. Acquisition base rate drift
    # -----------------------------------------------------------------------
    base_rate_result = detect_base_rate_drift(historical_cases, recent)
    drift_details["base_rate_drift"] = base_rate_result
    if base_rate_result.get("drift_detected"):
        drift_types.append(DriftType.OUTCOME_BASE_RATE_DRIFT)
        severity_flags.append(f"base_rate:{base_rate_result['severity']}")
        rec_rate = base_rate_result.get("recent_rate", 0)
        hist_rate = base_rate_result.get("historical_rate", 0)
        direction = "higher" if (rec_rate or 0) > (hist_rate or 0) else "lower"
        recommendations.append(
            f"Acquisition base rate has drifted {direction} "
            f"(historical={hist_rate:.2%}, recent={rec_rate:.2%}). "
            "Consider updating global calibration prior."
        )

    # -----------------------------------------------------------------------
    # 4. Calibration quality drift (Brier score)
    # -----------------------------------------------------------------------
    ref_scores_flat = ref_bd or ref_l1
    rec_scores_flat = cur_bd or cur_l1
    ref_labels = [c.labels.acquired_within_12m for c in historical_cases]
    cur_labels = [c.labels.acquired_within_12m for c in recent]

    if ref_scores_flat and rec_scores_flat and ref_labels and cur_labels:
        min_len_ref = min(len(ref_scores_flat), len(ref_labels))
        min_len_cur = min(len(rec_scores_flat), len(cur_labels))
        brier_result = detect_calibration_quality_drift(
            ref_scores_flat[:min_len_ref],
            ref_labels[:min_len_ref],
            rec_scores_flat[:min_len_cur],
            cur_labels[:min_len_cur],
        )
        drift_details["calibration_quality_drift"] = brier_result
        if brier_result.get("drift_detected"):
            drift_types.append(DriftType.CALIBRATION_DRIFT)
            severity_flags.append(f"calibration_brier:{brier_result['severity']}")
            recommendations.append(
                "Calibration quality has degraded "
                f"(Brier delta=+{brier_result.get('brier_delta', 0):.4f}). "
                "Re-run calibration with recent data."
            )

    # -----------------------------------------------------------------------
    # 5. Therapeutic area distribution drift
    # -----------------------------------------------------------------------
    ref_ta = _extract_categorical(historical_cases, "target_features.therapeutic_area")
    cur_ta = _extract_categorical(recent, "target_features.therapeutic_area")
    if ref_ta and cur_ta:
        ta_result = detect_categorical_drift(ref_ta, cur_ta, feature_name="therapeutic_area")
        drift_details["therapeutic_area_drift"] = ta_result
        if ta_result.get("drift_detected"):
            drift_types.append(DriftType.MARKET_REGIME_DRIFT)
            severity_flags.append(f"therapeutic_area:{ta_result['severity']}")

    # -----------------------------------------------------------------------
    # Compose final report
    # -----------------------------------------------------------------------
    requires_recalibration = any(
        "severe_drift" in f for f in severity_flags
    ) or DriftType.CALIBRATION_DRIFT in drift_types

    overall_severity = "no_drift"
    if severity_flags:
        if any("severe" in f for f in severity_flags):
            overall_severity = "severe_drift"
        elif any("moderate" in f for f in severity_flags):
            overall_severity = "moderate_drift"
        else:
            overall_severity = "minor_drift"

    if not recommendations and drift_types:
        recommendations.append(
            "Drift signals detected. Monitor closely and consider re-calibration "
            "if drift persists over the next observation window."
        )

    # Map to DriftReport fields
    drift_status_map = {
        "no_drift": "none",
        "minor_drift": "mild",
        "moderate_drift": "moderate",
        "severe_drift": "severe",
    }
    drift_status = drift_status_map.get(overall_severity, "none")

    # Build evidence list from drift details
    evidence: list[str] = []
    for key, val in drift_details.items():
        if isinstance(val, dict) and val.get("drift_detected"):
            sev = val.get("severity", "unknown")
            evidence.append(f"{key}: {sev}")

    # Build affected layers from drift type signals
    affected: list = []
    if DriftType.FEATURE_DISTRIBUTION_DRIFT in drift_types:
        affected.extend([LayerValidated.LAYER_1, LayerValidated.LAYER_2])
    if DriftType.OUTCOME_BASE_RATE_DRIFT in drift_types:
        affected.append(LayerValidated.END_TO_END)
    if DriftType.CALIBRATION_DRIFT in drift_types:
        affected.extend([LayerValidated.LAYER_3, LayerValidated.LAYER_4])
    affected = list(dict.fromkeys(affected))  # dedup preserving order

    recommended_action = "; ".join(recommendations) if recommendations else "No action required."

    return DriftReport(
        drift_status=drift_status,
        drift_types=drift_types,
        affected_layers=affected,
        evidence=evidence,
        metric_changes=drift_details,
        recommended_action=recommended_action,
        requires_recalibration=requires_recalibration,
        temporary_weighting_caution=severity_flags,
    )
