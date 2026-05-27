"""M&A Base-Rate Adjusted Calibration Report.

Computes segment-level base rates from the typed M&A backtest dataset and
produces a calibration report that distinguishes the five negative types.

Key design decisions
--------------------
* Bankruptcy/liquidation cases are EXCLUDED from the calibration denominator.
  They represent a third outcome class (financial distress → dissolution), not
  a true negative for strategic deal probability.  Including them would
  artificially deflate the calibration base rate.
* ``base_rate`` = n_positive / (n_positive + n_calibration_negatives)
  where n_calibration_negatives excludes BANKRUPTCY_OR_LIQUIDATION.
* ``base_rate_strict`` = n_positive / n_total (all negatives included — for
  disclosure and comparison purposes only).
* Wilson 80% confidence intervals — not 95%, to avoid false precision with
  small segment N.
* A calibration_warning is emitted when a segment base rate implies the model
  is likely overstating probability (e.g. historical rate < 5% but model
  routinely outputs 25%+).

Public API
----------
    from bve.analysis.ma_base_rate_report import (
        compute_base_rate_report,
        render_markdown,
        MABaseRateReport,
    )

    from bve.analysis.ma_backtest import MA_EXPANDED_DATASET
    report = compute_base_rate_report(MA_EXPANDED_DATASET)
    print(render_markdown(report))
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from bve.analysis.ma_backtest import MABacktestRecord

# ---------------------------------------------------------------------------
# Wilson confidence interval (80% by default)
# ---------------------------------------------------------------------------

_Z_80 = 1.2816  # z-score for 80% two-sided CI  (z_{0.90})


def wilson_ci(n: int, k: int, z: float = _Z_80) -> tuple[float, float]:
    """Wilson score interval for a proportion k/n.

    Returns (lower, upper) clipped to [0, 1].
    Returns (0.0, 1.0) when n == 0 (no data).
    """
    if n == 0:
        return 0.0, 1.0
    p_hat = k / n
    denom = 1 + z * z / n
    centre = (p_hat + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - margin), min(1.0, centre + margin)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BaseRateSegment:
    """Calibration statistics for one slice of the dataset.

    Attributes
    ----------
    segment_key:
        Human-readable slice label (e.g. "overall", "oncology", "phase_2").
    n_total:
        All records in this segment (positives + all negatives).
    n_positive:
        Acquisitions.
    n_calibration_negatives:
        Negatives excluding BANKRUPTCY_OR_LIQUIDATION.
    n_by_negative_type:
        Count by NegativeType.value within this segment.
    base_rate:
        n_positive / (n_positive + n_calibration_negatives).
        This is the recommended denominator for strategic M&A calibration.
    base_rate_strict:
        n_positive / n_total (includes bankruptcies — for disclosure only).
    ci_lower:
        Wilson 80% CI lower bound (on base_rate).
    ci_upper:
        Wilson 80% CI upper bound (on base_rate).
    calibration_warning:
        Non-None string when segment data suggests model may be overstating
        probability.
    """
    segment_key: str
    n_total: int
    n_positive: int
    n_calibration_negatives: int
    n_by_negative_type: dict[str, int]
    base_rate: float
    base_rate_strict: float
    ci_lower: float
    ci_upper: float
    calibration_warning: Optional[str] = None

    @property
    def n_calibration_total(self) -> int:
        """Denominator for base_rate: positives + calibration negatives."""
        return self.n_positive + self.n_calibration_negatives


@dataclass(frozen=True)
class MABaseRateReport:
    """Full base-rate calibration report over the M&A backtest dataset.

    Attributes
    ----------
    dataset_version:
        Label identifying the dataset snapshot.
    n_positives:
        Total acquisitions in the dataset.
    n_negatives_total:
        All negatives including bankruptcies.
    n_by_negative_type:
        Dataset-wide negative counts by NegativeType.value.
    overall:
        Aggregate BaseRateSegment across the whole dataset.
    by_therapeutic_area:
        Segments keyed by TA label ("oncology_rare", "other").
    by_stage:
        Segments keyed by phase bucket ("phase_1", "phase_2_3", "approved").
    by_cap_bucket:
        Segments keyed by cap size ("small", "mid", "large").
    bankruptcy_exclusion_note:
        Explanation of why bankruptcies are excluded from base_rate.
    model_implied_overstatement_warning:
        Warning when average model output likely exceeds historical rate by >2×.
    warnings:
        List of any segment-level warnings.
    """
    dataset_version: str
    n_positives: int
    n_negatives_total: int
    n_by_negative_type: dict[str, int]
    overall: BaseRateSegment
    by_therapeutic_area: dict[str, BaseRateSegment]
    by_stage: dict[str, BaseRateSegment]
    by_cap_bucket: dict[str, BaseRateSegment]
    bankruptcy_exclusion_note: str
    model_implied_overstatement_warning: Optional[str] = None
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Segmentation helpers
# ---------------------------------------------------------------------------

_BANKRUPTCY_TYPE = "bankruptcy_or_liquidation"

_STAGE_BUCKETS: dict[str, tuple[float, ...]] = {
    "phase_1":    (0.5,),
    "phase_2_3":  (1.0, 2.0),
    "approved":   (3.0,),
}


def _ta_label(record: MABacktestRecord) -> str:
    return "oncology_rare" if record.ta_oncology == 1 else "other"


def _stage_label(record: MABacktestRecord) -> str:
    ps = record.phase_score
    if ps <= 0.5:
        return "phase_1"
    if ps <= 2.0:
        return "phase_2_3"
    return "approved"


def _cap_label(record: MABacktestRecord) -> str:
    """Derive cap bucket from negative_type metadata or default to 'small'."""
    # The backtest dataset doesn't store market cap directly; use is_discounted
    # as a proxy and cap_bucket if populated through typed negatives.
    # For robustness, we default to 'small' (most records are small-cap biotechs).
    return "small"


def _build_segment(
    segment_key: str,
    records: list[MABacktestRecord],
) -> BaseRateSegment:
    """Compute a BaseRateSegment from a filtered record list."""
    n_total = len(records)
    n_pos = sum(1 for r in records if r.label == 1)
    n_neg_calib = sum(
        1 for r in records
        if r.label == 0 and not r.calibration_exclude
    )

    # Negative-type breakdown
    nbt: dict[str, int] = {}
    for r in records:
        if r.label == 0:
            key = r.negative_type or "untyped"
            nbt[key] = nbt.get(key, 0) + 1

    # Base rates
    calib_denom = n_pos + n_neg_calib
    base_rate = n_pos / calib_denom if calib_denom > 0 else 0.0
    base_rate_strict = n_pos / n_total if n_total > 0 else 0.0

    # Wilson 80% CI on base_rate
    ci_lo, ci_hi = wilson_ci(calib_denom, n_pos)

    # Calibration warning: if base_rate < 0.10 and segment has any positives,
    # note the risk of model overstatement.
    warning: Optional[str] = None
    if n_pos > 0 and base_rate < 0.10:
        warning = (
            f"Low base rate ({base_rate:.1%}) in segment '{segment_key}'. "
            "Any model that routinely outputs >20% for assets in this segment "
            "is likely overstating acquisition probability."
        )
    elif calib_denom < 10:
        warning = (
            f"Small sample (N={calib_denom}) in segment '{segment_key}'. "
            "Base rate estimate has wide uncertainty — do not use for calibration."
        )

    return BaseRateSegment(
        segment_key=segment_key,
        n_total=n_total,
        n_positive=n_pos,
        n_calibration_negatives=n_neg_calib,
        n_by_negative_type=nbt,
        base_rate=round(base_rate, 4),
        base_rate_strict=round(base_rate_strict, 4),
        ci_lower=round(ci_lo, 4),
        ci_upper=round(ci_hi, 4),
        calibration_warning=warning,
    )


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------

_BANKRUPTCY_EXCLUSION_NOTE = (
    "BANKRUPTCY_OR_LIQUIDATION cases are excluded from the base_rate denominator. "
    "They represent a third outcome class — financial distress leading to dissolution — "
    "not a true negative for strategic deal probability. Including them would compress "
    "the calibration base rate below the real strategic-deal rate, causing models to "
    "appear better-calibrated than they are for the target population. "
    "base_rate_strict (which includes bankruptcies) is shown for transparency."
)


def compute_base_rate_report(
    dataset: list[MABacktestRecord],
    dataset_version: str = "expanded_v1",
) -> MABaseRateReport:
    """Compute the full base-rate calibration report.

    Parameters
    ----------
    dataset:
        List of MABacktestRecord. Should be MA_EXPANDED_DATASET for the
        most representative results.
    dataset_version:
        Label to stamp on the report.

    Returns
    -------
    MABaseRateReport
    """
    overall = _build_segment("overall", dataset)

    # by_therapeutic_area
    by_ta: dict[str, BaseRateSegment] = {}
    for label in ("oncology_rare", "other"):
        subset = [r for r in dataset if _ta_label(r) == label]
        by_ta[label] = _build_segment(label, subset)

    # by_stage
    by_stage: dict[str, BaseRateSegment] = {}
    for label in ("phase_1", "phase_2_3", "approved"):
        subset = [r for r in dataset if _stage_label(r) == label]
        by_stage[label] = _build_segment(label, subset)

    # by_cap_bucket — most negatives in the typed set are small-cap;
    # populate from the record's cap_bucket if available via negative_type
    # metadata.  Since MABacktestRecord doesn't store cap_bucket directly,
    # we infer from negative_type where possible via the typed negative set.
    by_cap: dict[str, BaseRateSegment] = {}
    try:
        from bve.intelligence.ma_negative_set import TYPED_NEGATIVE_DATASET
        cap_map: dict[str, str] = {neg.company: neg.cap_bucket for neg in TYPED_NEGATIVE_DATASET}
    except ImportError:
        cap_map = {}

    for cap_label in ("small", "mid", "large"):
        subset: list[MABacktestRecord] = []
        for r in dataset:
            if r.label == 1:
                # Positives: use phase_score as proxy; large-cap acquirees tend to Phase3/approved
                inferred = "large" if r.phase_score >= 3.0 else ("mid" if r.phase_score >= 2.0 else "small")
            else:
                inferred = cap_map.get(r.company, "small")
            if inferred == cap_label:
                subset.append(r)
        by_cap[cap_label] = _build_segment(cap_label, subset)

    # Collect all segment warnings
    all_warnings: list[str] = []
    for seg in [overall, *by_ta.values(), *by_stage.values(), *by_cap.values()]:
        if seg.calibration_warning:
            all_warnings.append(seg.calibration_warning)

    # Overall overstatement warning
    overstatement: Optional[str] = None
    if overall.base_rate > 0 and overall.base_rate < 0.15:
        overstatement = (
            f"Overall calibration base rate is {overall.base_rate:.1%} "
            f"(calibration N={overall.n_calibration_total}). "
            "If model outputs routinely exceed 30%, probability estimates are "
            "likely overstated by >2×. Prefer rank-based outputs for this segment."
        )

    # Dataset-wide negative type counts
    n_by_nt: dict[str, int] = {}
    for r in dataset:
        if r.label == 0:
            key = r.negative_type or "untyped"
            n_by_nt[key] = n_by_nt.get(key, 0) + 1

    return MABaseRateReport(
        dataset_version=dataset_version,
        n_positives=overall.n_positive,
        n_negatives_total=overall.n_total - overall.n_positive,
        n_by_negative_type=n_by_nt,
        overall=overall,
        by_therapeutic_area=by_ta,
        by_stage=by_stage,
        by_cap_bucket=by_cap,
        bankruptcy_exclusion_note=_BANKRUPTCY_EXCLUSION_NOTE,
        model_implied_overstatement_warning=overstatement,
        warnings=all_warnings,
    )


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

def render_markdown(report: MABaseRateReport) -> str:
    """Render a MABaseRateReport as a Markdown string."""
    lines: list[str] = []

    lines.append("## M&A Base Rate Calibration Report")
    lines.append(f"\n**Dataset version:** {report.dataset_version}")
    lines.append(
        f"**N positives (acquisitions):** {report.n_positives}  |  "
        f"**N negatives (all):** {report.n_negatives_total}"
    )

    # Negative type breakdown
    lines.append("\n### Negative Type Breakdown\n")
    lines.append("| Negative Type | Count |")
    lines.append("|---|---|")
    for nt_val, count in sorted(report.n_by_negative_type.items()):
        lines.append(f"| {nt_val} | {count} |")

    # Overall segment
    lines.append("\n### Overall Base Rate\n")
    lines.append(_segment_table_header())
    lines.append(_segment_row(report.overall))

    # By therapeutic area
    lines.append("\n### By Therapeutic Area\n")
    lines.append(_segment_table_header())
    for seg in report.by_therapeutic_area.values():
        lines.append(_segment_row(seg))

    # By stage
    lines.append("\n### By Stage\n")
    lines.append(_segment_table_header())
    for seg in report.by_stage.values():
        lines.append(_segment_row(seg))

    # By cap bucket
    lines.append("\n### By Cap Bucket\n")
    lines.append(_segment_table_header())
    for seg in report.by_cap_bucket.values():
        lines.append(_segment_row(seg))

    # Bankruptcy note
    lines.append("\n### Bankruptcy Exclusion Note\n")
    lines.append(f"> {report.bankruptcy_exclusion_note}")

    # Overstatement warning
    if report.model_implied_overstatement_warning:
        lines.append("\n### Overstatement Warning\n")
        lines.append(f"> **WARNING:** {report.model_implied_overstatement_warning}")

    # Segment warnings
    if report.warnings:
        lines.append("\n### Segment Warnings\n")
        for w in report.warnings:
            lines.append(f"- {w}")

    return "\n".join(lines) + "\n"


def _segment_table_header() -> str:
    return (
        "| Segment | N+ | N- (calib) | Base Rate | Base Rate (strict) | 80% CI |\n"
        "|---|---|---|---|---|---|"
    )


def _segment_row(seg: BaseRateSegment) -> str:
    return (
        f"| {seg.segment_key} "
        f"| {seg.n_positive} "
        f"| {seg.n_calibration_negatives} "
        f"| {seg.base_rate:.1%} "
        f"| {seg.base_rate_strict:.1%} "
        f"| {seg.ci_lower:.1%}–{seg.ci_upper:.1%} |"
    )
