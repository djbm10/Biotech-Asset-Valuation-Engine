"""Layer 5 — 5D: Segment / Hierarchical Calibration Engine.

Avoids pretending one global calibration curve applies equally to every
biotech M&A segment.

Hierarchical blending logic:
  - N >= 100: use segment calibration
  - 30 <= N < 100: blend = (N/100) * segment_prob + (1 - N/100) * global_prob
  - N < 30: use global calibration + sparse-segment warning

Segment dimensions:
  therapeutic_area, modality, stage, deal_type, market_cap_bucket,
  route_class, acquirer_type, distress_level, rights_encumbrance_level,
  catalyst_proximity_bucket, asset_quality_bucket
"""
from __future__ import annotations

from typing import Any, Optional

from bve.intelligence.ma_calibration_models import (
    CalibrationQualityLabel,
    HistoricalMAOutcome,
    SegmentDiagnostics,
)

# Sample-size thresholds
_N_SEGMENT_FULL = 100
_N_SEGMENT_BLEND = 30

# Segment dimension extractors
_SEGMENT_EXTRACTORS: dict[str, Any] = {
    "therapeutic_area": lambda c: c.target_features.therapeutic_area,
    "modality": lambda c: c.target_features.modality,
    "stage": lambda c: c.target_features.stage,
    "deal_type": lambda c: c.target_features.deal_type,
    "market_cap_bucket": lambda c: c.target_features.market_cap_bucket,
    "route_class": lambda c: c.target_features.route_class,
    "distress_level": lambda c: c.target_features.distress_level,
    "rights_encumbrance_level": lambda c: c.target_features.rights_encumbrance_level,
    "catalyst_proximity_bucket": lambda c: c.target_features.catalyst_proximity_bucket,
    "asset_quality_bucket": lambda c: c.target_features.asset_quality_bucket,
    "acquirer_type": lambda c: c.acquirer_features.acquirer_type if c.acquirer_features else None,
}


def _base_rate_and_size(cases: list[HistoricalMAOutcome]) -> tuple[float, int]:
    """Compute acquisition base rate and sample size from a list of cases."""
    n = len(cases)
    if n == 0:
        return 0.08, 0
    positives = sum(1 for c in cases if c.labels.acquired_within_12m)
    return positives / n, n


def hierarchical_segment_blend(
    segment_prob: float,
    global_prob: float,
    effective_n: float,
) -> float:
    """Blend segment and global calibration by effective sample size.

    segment_weight = min(1.0, effective_n / N_SEGMENT_FULL)
    """
    weight = min(1.0, effective_n / _N_SEGMENT_FULL)
    return round(weight * segment_prob + (1 - weight) * global_prob, 6)


def _reliability_label(n: int) -> CalibrationQualityLabel:
    if n >= _N_SEGMENT_FULL:
        return CalibrationQualityLabel.HIGH_CONFIDENCE
    if n >= _N_SEGMENT_BLEND:
        return CalibrationQualityLabel.MEDIUM_CONFIDENCE
    if n > 0:
        return CalibrationQualityLabel.LOW_CONFIDENCE
    return CalibrationQualityLabel.INSUFFICIENT_DATA_RANK_ONLY


def calibrate_by_segment(
    cases: list[HistoricalMAOutcome],
    segment_dimension: str,
    *,
    global_base_rate: Optional[float] = None,
) -> list[SegmentDiagnostics]:
    """Compute per-segment calibration diagnostics for one segment dimension.

    Args:
        cases: Historical outcome records.
        segment_dimension: One of the keys in _SEGMENT_EXTRACTORS.
        global_base_rate: Override global base rate (computed from cases if None).

    Returns:
        List of SegmentDiagnostics, one per observed segment value.
    """
    if segment_dimension not in _SEGMENT_EXTRACTORS:
        return []

    extractor = _SEGMENT_EXTRACTORS[segment_dimension]

    if global_base_rate is None:
        g_rate, g_n = _base_rate_and_size(cases)
    else:
        g_rate = global_base_rate

    # Group cases by segment value
    groups: dict[str, list[HistoricalMAOutcome]] = {}
    for case in cases:
        try:
            val = extractor(case)
        except Exception:
            val = None
        key = str(val) if val is not None else "_unknown_"
        groups.setdefault(key, []).append(case)

    results: list[SegmentDiagnostics] = []
    for seg_val, seg_cases in sorted(groups.items()):
        seg_rate, seg_n = _base_rate_and_size(seg_cases)
        effective_n = float(seg_n)

        blended = hierarchical_segment_blend(seg_rate, g_rate, effective_n)

        label = _reliability_label(seg_n)
        ood = seg_n == 0
        notes: list[str] = []

        if seg_n < _N_SEGMENT_BLEND:
            notes.append(
                f"Sparse segment (n={seg_n}); using global calibration blend "
                f"with weight={effective_n / _N_SEGMENT_FULL:.2f}. "
                "Use score as ranking only."
            )
        if seg_n == 0:
            notes.append("No historical cases in this segment — out of domain.")

        results.append(SegmentDiagnostics(
            segment_key=f"{segment_dimension}={seg_val}",
            segment_filters={segment_dimension: seg_val},
            sample_size=seg_n,
            effective_sample_size=effective_n,
            base_rate=round(seg_rate, 6) if seg_n > 0 else None,
            calibrated_rate=round(blended, 6),
            reliability_label=label,
            out_of_domain_warning=ood,
            notes=notes,
        ))

    return results


def compute_segment_diagnostics(
    cases: list[HistoricalMAOutcome],
    dimensions: Optional[list[str]] = None,
    *,
    global_base_rate: Optional[float] = None,
) -> list[SegmentDiagnostics]:
    """Compute segment diagnostics across multiple dimensions.

    Args:
        cases: Historical outcome records.
        dimensions: Segment dimensions to evaluate. Defaults to all known dimensions.
        global_base_rate: Override global base rate.

    Returns:
        Flat list of SegmentDiagnostics for all dimension/value combinations.
    """
    dims = dimensions or list(_SEGMENT_EXTRACTORS.keys())
    all_diags: list[SegmentDiagnostics] = []
    for dim in dims:
        all_diags.extend(
            calibrate_by_segment(cases, dim, global_base_rate=global_base_rate)
        )
    return all_diags


def get_segment_reliability(
    case: HistoricalMAOutcome,
    segment_diagnostics: list[SegmentDiagnostics],
) -> tuple[CalibrationQualityLabel, list[str]]:
    """Get the worst-case reliability label for a case given segment diagnostics.

    Args:
        case: The case to classify.
        segment_diagnostics: Pre-computed segment diagnostics.

    Returns:
        (quality_label, warnings)
    """
    warnings: list[str] = []
    worst_label = CalibrationQualityLabel.HIGH_CONFIDENCE
    _ORDER = [
        CalibrationQualityLabel.HIGH_CONFIDENCE,
        CalibrationQualityLabel.MEDIUM_CONFIDENCE,
        CalibrationQualityLabel.LOW_CONFIDENCE,
        CalibrationQualityLabel.INSUFFICIENT_DATA_RANK_ONLY,
        CalibrationQualityLabel.OUT_OF_DOMAIN,
    ]
    label_rank = {v: i for i, v in enumerate(_ORDER)}

    for dim, extractor in _SEGMENT_EXTRACTORS.items():
        try:
            val = extractor(case)
        except Exception:
            val = None
        if val is None:
            continue
        key = f"{dim}={val}"
        matched = [d for d in segment_diagnostics if d.segment_key == key]
        for diag in matched:
            if label_rank[diag.reliability_label] > label_rank[worst_label]:
                worst_label = diag.reliability_label
            warnings.extend(diag.notes)

    return worst_label, warnings


def detect_out_of_domain_segment(
    case: HistoricalMAOutcome,
    segment_diagnostics: list[SegmentDiagnostics],
) -> bool:
    """Return True if the case falls into any out-of-domain segment."""
    for dim, extractor in _SEGMENT_EXTRACTORS.items():
        try:
            val = extractor(case)
        except Exception:
            val = None
        if val is None:
            continue
        key = f"{dim}={val}"
        for diag in segment_diagnostics:
            if diag.segment_key == key and diag.out_of_domain_warning:
                return True
    return False
