"""Multi-TA POS calibration — ECE, AUC, and Brier score stratified by therapeutic area.

Extends the oncology backtest (backtest.py) to handle multiple therapeutic areas
and produce calibration curves, time-split validation, and per-TA breakdowns.

Goal: demonstrate that the POS model is calibrated not just for oncology but
across all 6 TAs in the model's scope.

Therapeutic areas
-----------------
  oncology       — solid tumours, haematology (existing N=99 dataset)
  cns            — neurology, psychiatry, rare neurological diseases
  cardiovascular — atherosclerosis, heart failure, arrhythmia
  metabolic      — diabetes, obesity, NASH/MASH
  immunology     — autoimmune, inflammation, rare immune diseases
  rare_disease   — enzyme replacement, gene therapy, rare genetic

Calibration metrics per TA
--------------------------
  Brier Score  — mean squared error; baseline = 0.25 (always predict 0.5)
  AUC-ROC      — discrimination; baseline = 0.50 (random)
  ECE          — Expected Calibration Error (|pred_mean - actual_rate| weighted by N)
  Base rate    — actual success rate vs model mean prediction

Minimum N for reliable TA estimates: 20 observations per TA.

Usage
-----
    from bve.analysis.pos_calibration import POSCalibrationSuite, TACalibrationResult
    from bve.analysis.pos_calibration import run_pos_calibration_from_records

    records = [POSCalibrationRecord(ta="oncology", phase="phase_2",
                                    predicted_pos=0.42, actual_success=True), ...]
    suite = run_pos_calibration_from_records(records, time_split_year=2022)
    print(suite.summary())
    suite.save_json("outputs/pos_calibration.json")
"""
from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Supported TAs
# ---------------------------------------------------------------------------

SUPPORTED_TAS = [
    "oncology",
    "cns",
    "cardiovascular",
    "metabolic",
    "immunology",
    "rare_disease",
    "other",
]

MIN_N_FOR_RELIABLE_ESTIMATE = 20


def _build_base_rate_industry() -> dict[str, dict[str, float]]:
    """
    Build BASE_RATE_INDUSTRY from AssumptionsLoader so calibration uses the same
    base rates as the POS model.  Previously this was a hardcoded dict that diverged
    from industry_assumptions.yaml (e.g. oncology phase_2 was 0.40 vs model's 0.248),
    which made Brier/AUC scores appear better than they were.
    Block 34A fix.
    """
    import warnings as _w
    from bve.config.assumptions_loader import AssumptionsLoader as _AL
    loader = _AL.get()
    result: dict[str, dict[str, float]] = {}
    for ta in SUPPORTED_TAS:
        with _w.catch_warnings(record=True):
            _w.simplefilter("always")
            rates = loader.phase_success_rates_for(ta)
        result[ta] = {
            "phase_2": float(rates.get("phase_2", 0.40)),
            "phase_3": float(rates.get("phase_3", 0.60)),
        }
    return result


BASE_RATE_INDUSTRY: dict[str, dict[str, float]] = _build_base_rate_industry()


# ---------------------------------------------------------------------------
# Input record
# ---------------------------------------------------------------------------

@dataclass
class POSCalibrationRecord:
    """One trial outcome with model prediction.

    Used as input to the calibration suite.
    All fields required except year and notes.
    """
    therapeutic_area: str     # one of SUPPORTED_TAS
    phase: str                # "phase_2" | "phase_3"
    predicted_pos: float      # model output 0.0–1.0
    actual_success: bool      # True = advanced/approved; False = failed

    # Optional metadata
    drug: str = ""
    company: str = ""
    indication: str = ""
    year: Optional[int] = None
    notes: str = ""

    def __post_init__(self) -> None:
        ta = self.therapeutic_area.lower().strip()
        if ta not in SUPPORTED_TAS:
            self.therapeutic_area = "other"
        else:
            self.therapeutic_area = ta
        if self.predicted_pos < 0.0 or self.predicted_pos > 1.0:
            raise ValueError(f"predicted_pos must be 0–1; got {self.predicted_pos}")


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@dataclass
class CalibrationBucket:
    """One probability bin for calibration curve."""
    label: str
    predicted_low: float
    predicted_high: float
    n: int
    n_success: int
    predicted_mean: float

    @property
    def actual_rate(self) -> Optional[float]:
        return self.n_success / self.n if self.n > 0 else None

    @property
    def calibration_error(self) -> Optional[float]:
        """abs(predicted_mean - actual_rate), weighted by N in ECE computation."""
        if self.actual_rate is None:
            return None
        return abs(self.predicted_mean - self.actual_rate)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "n": self.n,
            "n_success": self.n_success,
            "predicted_mean": _r(self.predicted_mean),
            "actual_rate": _r(self.actual_rate),
            "calibration_error": _r(self.calibration_error),
        }


@dataclass
class ReliabilityBin:
    """One equal-width bin in a reliability diagram.

    Unlike CalibrationBucket (which uses fixed edges), ReliabilityBin bins are
    constructed for equal-width intervals of the predicted probability space.
    actual_rate and calibration_error are NaN when the bin is empty (n == 0).
    """
    bin_label: str          # e.g. "0.20–0.40"
    n: int
    n_success: int
    predicted_mean: float
    actual_rate: float      # NaN when n == 0
    calibration_error: float  # actual_rate - predicted_mean; NaN when n == 0


def build_reliability_diagram(
    records: list["POSCalibrationRecord"],
    n_bins: int = 5,
) -> list[ReliabilityBin]:
    """Build equal-width reliability diagram bins over [0, 1].

    Parameters
    ----------
    records : list[POSCalibrationRecord]
        Calibration records to bin.
    n_bins : int
        Number of equal-width bins.  Default 5 (every 20pp).

    Returns
    -------
    list[ReliabilityBin]
        n_bins bins; empty bins have n=0, actual_rate=NaN, calibration_error=NaN.
    """
    bin_width = 1.0 / n_bins
    bins: list[ReliabilityBin] = []

    for i in range(n_bins):
        lo = i * bin_width
        hi = (i + 1) * bin_width
        label = f"{lo:.2f}–{hi:.2f}"
        in_bin = [r for r in records if lo <= r.predicted_pos < hi]
        # Last bin includes 1.0 (for records exactly at 1.0)
        if i == n_bins - 1:
            in_bin = [r for r in records if lo <= r.predicted_pos <= hi]

        if not in_bin:
            bins.append(ReliabilityBin(
                bin_label=label,
                n=0,
                n_success=0,
                predicted_mean=float("nan"),
                actual_rate=float("nan"),
                calibration_error=float("nan"),
            ))
        else:
            pred_mean = sum(r.predicted_pos for r in in_bin) / len(in_bin)
            n_s = sum(1 for r in in_bin if r.actual_success)
            act_rate = n_s / len(in_bin)
            bins.append(ReliabilityBin(
                bin_label=label,
                n=len(in_bin),
                n_success=n_s,
                predicted_mean=round(pred_mean, 4),
                actual_rate=round(act_rate, 4),
                calibration_error=round(act_rate - pred_mean, 4),
            ))

    return bins


@dataclass
class TACalibrationResult:
    """Per-TA calibration metrics."""
    therapeutic_area: str
    phase: str
    n: int
    n_success: int
    actual_success_rate: Optional[float]
    model_mean_prediction: Optional[float]
    industry_base_rate: Optional[float]
    brier_score: Optional[float]         # lower is better; 0.25 = no-skill
    auc: Optional[float]                 # 0.50 = random
    ece: Optional[float]                 # Expected Calibration Error (lower = better)
    is_low_n: bool                       # N < MIN_N_FOR_RELIABLE_ESTIMATE
    calibration_buckets: list[CalibrationBucket] = field(default_factory=list)
    note: str = ""

    # --- Block 19 additions ---
    insufficient_data_warning: bool = False
    """True when n < MIN_N_FOR_RELIABLE_ESTIMATE.  Metrics are computed for
    reference but should not be used for calibration decisions."""
    insufficient_data_message: str = ""
    """Human-readable explanation when insufficient_data_warning is True."""
    reliability_diagram: list[ReliabilityBin] = field(default_factory=list)
    """Equal-width reliability bins (5 by default) for visual calibration check."""

    @property
    def brier_skill(self) -> Optional[float]:
        """Skill vs no-skill (positive = beats baseline)."""
        if self.brier_score is None:
            return None
        return round(0.25 - self.brier_score, 4)

    @property
    def calibration_direction(self) -> str:
        """'over' if model over-predicts, 'under' if under-predicts, 'calibrated'."""
        if self.model_mean_prediction is None or self.actual_success_rate is None:
            return "unknown"
        diff = self.model_mean_prediction - self.actual_success_rate
        if diff > 0.05:
            return "over"
        elif diff < -0.05:
            return "under"
        return "calibrated"

    def to_dict(self) -> dict:
        return {
            "therapeutic_area": self.therapeutic_area,
            "phase": self.phase,
            "n": self.n,
            "n_success": self.n_success,
            "actual_success_rate": _r(self.actual_success_rate),
            "model_mean_prediction": _r(self.model_mean_prediction),
            "industry_base_rate": _r(self.industry_base_rate),
            "brier_score": _r(self.brier_score),
            "brier_skill": _r(self.brier_skill),
            "auc": _r(self.auc),
            "ece": _r(self.ece),
            "is_low_n": self.is_low_n,
            "calibration_direction": self.calibration_direction,
            "calibration_buckets": [b.to_dict() for b in self.calibration_buckets],
            "note": self.note,
        }


# ---------------------------------------------------------------------------
# Aggregate suite
# ---------------------------------------------------------------------------

@dataclass
class POSCalibrationSuite:
    """Full calibration results across all TAs and phases.

    Attributes
    ----------
    all_records:
        Total input record count.
    time_split_year:
        Records before this year used for "in-sample" comparison;
        on/after used for "OOS" comparison (None = no split).
    in_sample:
        List of TACalibrationResult for the in-sample period.
    oos:
        List of TACalibrationResult for the OOS period (may be empty).
    overall:
        Single TACalibrationResult aggregating all TAs and phases.
    """
    model_name: str
    n_total_records: int
    time_split_year: Optional[int]
    in_sample: list[TACalibrationResult] = field(default_factory=list)
    oos: list[TACalibrationResult] = field(default_factory=list)
    overall: Optional[TACalibrationResult] = None

    @property
    def n_total(self) -> int:
        """Total number of input records (alias for n_total_records)."""
        return self.n_total_records

    @property
    def ta_results(self) -> list[TACalibrationResult]:
        """All in-sample TA calibration results."""
        return self.in_sample

    @property
    def n_tas_with_data(self) -> int:
        seen = {r.therapeutic_area for r in self.in_sample}
        return len(seen)

    @property
    def n_tas_passing_n_gate(self) -> int:
        return sum(1 for r in self.in_sample if not r.is_low_n)

    @property
    def mean_brier_in_sample(self) -> Optional[float]:
        scores = [r.brier_score for r in self.in_sample if r.brier_score is not None]
        return round(statistics.mean(scores), 4) if scores else None

    @property
    def mean_auc_in_sample(self) -> Optional[float]:
        vals = [r.auc for r in self.in_sample
                if r.auc is not None and not math.isnan(r.auc)]
        return round(statistics.mean(vals), 4) if vals else None

    def summary(self) -> str:
        lines = [
            "=" * 72,
            f"  POS CALIBRATION SUITE — {self.model_name}",
            "=" * 72,
            f"  Total records:     {self.n_total_records}",
            f"  TAs with data:     {self.n_tas_with_data}",
            f"  TAs N≥{MIN_N_FOR_RELIABLE_ESTIMATE}:          {self.n_tas_passing_n_gate}",
        ]
        if self.time_split_year:
            lines.append(f"  Time split:        < {self.time_split_year} in-sample")
        lines += ["", f"  {'TA':<16} {'Phase':<9} {'N':>5} {'Base':>6} {'Pred':>6} "
                  f"{'Actual':>7} {'Brier':>7} {'AUC':>7} {'ECE':>6} {'Dir':<12}",
                  "  " + "─" * 68]
        for r in sorted(self.in_sample, key=lambda x: (x.therapeutic_area, x.phase)):
            low_n = "*" if r.is_low_n else ""
            base = f"{r.industry_base_rate:.0%}" if r.industry_base_rate is not None else "n/a"
            pred = f"{r.model_mean_prediction:.0%}" if r.model_mean_prediction is not None else "n/a"
            act = f"{r.actual_success_rate:.0%}" if r.actual_success_rate is not None else "n/a"
            brier = f"{r.brier_score:.3f}" if r.brier_score is not None else "n/a"
            auc = f"{r.auc:.3f}" if (r.auc is not None and not math.isnan(r.auc or 0)) else "n/a"
            ece = f"{r.ece:.3f}" if r.ece is not None else "n/a"
            lines.append(
                f"  {r.therapeutic_area+low_n:<16} {r.phase:<9} {r.n:>5} "
                f"{base:>6} {pred:>6} {act:>7} {brier:>7} {auc:>7} {ece:>6} {r.calibration_direction:<12}"
            )
        lines.append("  * N < 20 — low confidence")
        if self.overall:
            lines += [
                "",
                f"  Overall Brier: {_fmt(self.overall.brier_score)} "
                f"(skill vs baseline: {_fmt_signed(self.overall.brier_skill)})",
                f"  Overall AUC:   {_fmt(self.overall.auc)}",
                f"  Overall ECE:   {_fmt(self.overall.ece)}",
            ]
        if self.oos:
            oos_briears = [r.brier_score for r in self.oos if r.brier_score is not None]
            if oos_briears:
                lines.append(
                    f"\n  OOS mean Brier: {statistics.mean(oos_briears):.4f} "
                    f"(N OOS records: {sum(r.n for r in self.oos)})"
                )
        lines.append("=" * 72)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "model_name": self.model_name,
            "n_total_records": self.n_total_records,
            "time_split_year": self.time_split_year,
            "n_tas_with_data": self.n_tas_with_data,
            "mean_brier_in_sample": self.mean_brier_in_sample,
            "mean_auc_in_sample": self.mean_auc_in_sample,
            "in_sample": [r.to_dict() for r in self.in_sample],
            "oos": [r.to_dict() for r in self.oos],
            "overall": self.overall.to_dict() if self.overall else None,
        }

    def save_json(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    def save_validation_report_md(self, path: str) -> None:
        """Write Markdown validation report."""
        lines = [
            "# POS Model Validation Report",
            "",
            f"**Model:** {self.model_name}  ",
            f"**Total records:** {self.n_total_records}  ",
            f"**TAs with data:** {self.n_tas_with_data} of {len(SUPPORTED_TAS)}  ",
            "",
            "## Summary metrics",
            "",
            "| Metric | Value | Baseline |",
            "|--------|-------|----------|",
        ]
        if self.overall:
            lines += [
                f"| Brier Score | {_fmt(self.overall.brier_score)} | 0.2500 (no skill) |",
                f"| Brier Skill | {_fmt_signed(self.overall.brier_skill)} | 0.0000 |",
                f"| AUC-ROC | {_fmt(self.overall.auc)} | 0.5000 (random) |",
                f"| ECE | {_fmt(self.overall.ece)} | — |",
            ]
        lines += [
            "",
            "## Per-TA calibration (in-sample)",
            "",
            "| TA | Phase | N | Base Rate | Model Mean | Actual Rate | Brier | AUC | ECE | Dir |",
            "|-------|-------|---|-----------|------------|-------------|-------|-----|-----|-----|",
        ]
        for r in sorted(self.in_sample, key=lambda x: (x.therapeutic_area, x.phase)):
            low_n = " *" if r.is_low_n else ""
            base = f"{r.industry_base_rate:.0%}" if r.industry_base_rate is not None else "—"
            pred = f"{r.model_mean_prediction:.0%}" if r.model_mean_prediction is not None else "—"
            act = f"{r.actual_success_rate:.0%}" if r.actual_success_rate is not None else "—"
            brier = f"{r.brier_score:.3f}" if r.brier_score is not None else "—"
            auc = f"{r.auc:.3f}" if (r.auc is not None and not math.isnan(r.auc or 0)) else "—"
            ece = f"{r.ece:.3f}" if r.ece is not None else "—"
            lines.append(
                f"| {r.therapeutic_area}{low_n} | {r.phase} | {r.n} | "
                f"{base} | {pred} | {act} | {brier} | {auc} | {ece} | {r.calibration_direction} |"
            )
        lines += [
            "",
            "_* N < 20: low-confidence estimate_",
            "",
            "## Interpretation",
            "",
            "Brier skill > 0 indicates the model outperforms the no-skill baseline. "
            "AUC > 0.55 indicates meaningful discrimination. "
            "ECE < 0.05 indicates well-calibrated probability estimates. "
            "Direction 'calibrated' = |predicted - actual| ≤ 5pp.",
        ]
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------

def _compute_ta_metrics(records: list[POSCalibrationRecord]) -> TACalibrationResult:
    """Compute metrics for a list of records (same TA and phase)."""
    if not records:
        ta = "unknown"
        phase = "unknown"
        return TACalibrationResult(
            therapeutic_area=ta, phase=phase, n=0, n_success=0,
            actual_success_rate=None, model_mean_prediction=None,
            industry_base_rate=None, brier_score=None, auc=None, ece=None,
            is_low_n=True, note="No records",
        )

    ta = records[0].therapeutic_area
    phase = records[0].phase
    n = len(records)
    n_success = sum(1 for r in records if r.actual_success)
    actual_rate = n_success / n
    pred_mean = statistics.mean(r.predicted_pos for r in records)

    # Industry base rate
    base = BASE_RATE_INDUSTRY.get(ta, BASE_RATE_INDUSTRY["other"]).get(phase)

    # Brier score
    brier = statistics.mean((r.predicted_pos - int(r.actual_success)) ** 2
                            for r in records)

    # AUC
    y_true = [r.actual_success for r in records]
    y_score = [r.predicted_pos for r in records]
    auc = _compute_auc(y_true, y_score)

    # ECE (5 buckets: 0-20, 20-40, 40-60, 60-80, 80-100)
    bucket_edges = [0.0, 0.20, 0.40, 0.60, 0.80, 1.01]
    buckets = []
    ece = 0.0
    for i in range(len(bucket_edges) - 1):
        lo, hi = bucket_edges[i], bucket_edges[i + 1]
        in_bucket = [r for r in records if lo <= r.predicted_pos < hi]
        if not in_bucket:
            buckets.append(CalibrationBucket(
                label=f"{lo:.0%}–{hi:.0%}", predicted_low=lo, predicted_high=hi,
                n=0, n_success=0, predicted_mean=float("nan"),
            ))
            continue
        b_pred = statistics.mean(r.predicted_pos for r in in_bucket)
        b_actual = sum(1 for r in in_bucket if r.actual_success) / len(in_bucket)
        ece += (len(in_bucket) / n) * abs(b_pred - b_actual)
        buckets.append(CalibrationBucket(
            label=f"{lo:.0%}–{min(hi, 1.0):.0%}",
            predicted_low=lo, predicted_high=hi,
            n=len(in_bucket),
            n_success=sum(1 for r in in_bucket if r.actual_success),
            predicted_mean=round(b_pred, 4),
        ))

    note = ""
    insufficient_data_warning = n < MIN_N_FOR_RELIABLE_ESTIMATE
    insufficient_data_message = ""
    if insufficient_data_warning:
        note = f"Low N={n}; estimates unreliable (need ≥{MIN_N_FOR_RELIABLE_ESTIMATE})"
        insufficient_data_message = (
            f"Insufficient data: N={n} < {MIN_N_FOR_RELIABLE_ESTIMATE}; "
            "metrics computed for reference only."
        )

    reliability_diagram = build_reliability_diagram(records)

    return TACalibrationResult(
        therapeutic_area=ta,
        phase=phase,
        n=n,
        n_success=n_success,
        actual_success_rate=round(actual_rate, 4),
        model_mean_prediction=round(pred_mean, 4),
        industry_base_rate=round(base, 4) if base is not None else None,
        brier_score=round(brier, 4),
        auc=round(auc, 4) if not math.isnan(auc) else None,
        ece=round(ece, 4),
        is_low_n=insufficient_data_warning,
        calibration_buckets=buckets,
        note=note,
        insufficient_data_warning=insufficient_data_warning,
        insufficient_data_message=insufficient_data_message,
        reliability_diagram=reliability_diagram,
    )


def _compute_auc(y_true: list[bool], y_score: list[float]) -> float:
    if len(set(y_true)) < 2:
        return float("nan")
    n_pos = sum(y_true)
    n_neg = len(y_true) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    pairs = sorted(zip(y_score, y_true), key=lambda x: -x[0])
    tp = fp = prev_tp = prev_fp = 0
    auc = 0.0
    for _s, label in pairs:
        if label:
            tp += 1
        else:
            fp += 1
        auc += (fp - prev_fp) * (tp + prev_tp) / 2.0
        prev_fp, prev_tp = fp, tp
    return auc / (n_pos * n_neg)


def run_pos_calibration_from_records(
    records: list[POSCalibrationRecord],
    *,
    model_name: str = "pos_model",
    time_split_year: Optional[int] = None,
) -> POSCalibrationSuite:
    """Run full calibration suite.

    Parameters
    ----------
    records:
        All calibration records (all TAs, all phases).
    model_name:
        Label for the suite.
    time_split_year:
        Year boundary for train/test split. Records with year < time_split_year
        go to in_sample; ≥ go to oos. If None, all records are in_sample.
    """
    if time_split_year is not None:
        in_recs = [r for r in records if r.year is not None and r.year < time_split_year]
        oos_recs = [r for r in records if r.year is not None and r.year >= time_split_year]
        no_year = [r for r in records if r.year is None]
        in_recs = in_recs + no_year   # undated records count as in-sample
    else:
        in_recs = records
        oos_recs = []

    def _build_results(recs: list[POSCalibrationRecord]) -> list[TACalibrationResult]:
        # Group by (ta, phase)
        groups: dict[tuple[str, str], list[POSCalibrationRecord]] = {}
        for r in recs:
            groups.setdefault((r.therapeutic_area, r.phase), []).append(r)
        return [_compute_ta_metrics(group) for group in sorted(groups.values(),
                key=lambda g: (g[0].therapeutic_area, g[0].phase))]

    in_sample = _build_results(in_recs)
    oos = _build_results(oos_recs)

    # Overall metrics (all records, all TAs flattened)
    overall_result = None
    if in_recs:
        overall_recs_flat = [
            POSCalibrationRecord(
                therapeutic_area="all",
                phase=r.phase,
                predicted_pos=r.predicted_pos,
                actual_success=r.actual_success,
                year=r.year,
            )
            for r in in_recs
        ]
        overall_result = _compute_ta_metrics(overall_recs_flat)

    return POSCalibrationSuite(
        model_name=model_name,
        n_total_records=len(records),
        time_split_year=time_split_year,
        in_sample=in_sample,
        oos=oos,
        overall=overall_result,
    )


def load_from_backtest_csv(
    csv_path: str,
    *,
    ta_column: str = "therapeutic_area",
    ta_from_indication: bool = True,
) -> list[POSCalibrationRecord]:
    """Load calibration records from a backtest CSV.

    Adds TA mapping by indication name when ta_column is absent.

    Parameters
    ----------
    csv_path:
        Path to a CSV with columns: drug, company, indication, phase_start,
        outcome, year, moa_precedent, biomarker_enriched, safety_profile,
        competitive_pressure, endpoint_type.
    ta_column:
        Column name for TA (may be absent in existing CSVs).
    ta_from_indication:
        If True and ta_column absent, infer TA from indication string via
        ``infer_ta_from_indication()``.
    """
    import csv as _csv

    records = []
    with open(csv_path, newline="") as f:
        reader = _csv.DictReader(f)
        for row in reader:
            phase = row.get("phase_start", "").strip()
            if phase not in ("phase_2", "phase_3"):
                continue
            outcome = row.get("outcome", "").strip()
            success = outcome in ("approved", "advanced", "success")
            indication = row.get("indication", "")

            if ta_column in row and row[ta_column].strip():
                ta = row[ta_column].strip().lower()
            elif ta_from_indication:
                ta = infer_ta_from_indication(indication)
            else:
                ta = "other"

            # Use a simple heuristic POS as the "model prediction" when we don't
            # have stored model outputs. This is a placeholder — in production,
            # replace with stored model scores from BacktestResult.
            predicted = _heuristic_pos_from_row(row, phase)

            year_str = row.get("year", "")
            year = int(year_str) if year_str.strip().isdigit() else None

            records.append(POSCalibrationRecord(
                therapeutic_area=ta,
                phase=phase,
                predicted_pos=predicted,
                actual_success=success,
                drug=row.get("drug", "").strip(),
                company=row.get("company", "").strip(),
                indication=indication,
                year=year,
                notes=row.get("notes", ""),
            ))
    return records


def infer_ta_from_indication(indication: str) -> str:
    """Heuristic TA inference from indication text."""
    ind = indication.lower()
    oncology_kw = [
        "cancer", "carcinoma", "lymphoma", "leukemia", "melanoma", "nsclc",
        "sclc", "glioma", "sarcoma", "myeloma", "oma", "tumour", "tumor",
        "aml", "cll", "crc", "mbc", "ovarian", "prostate", "breast",
        "colorectal", "pancreatic", "gastric", "renal",
    ]
    cns_kw = [
        "alzheimer", "parkinson", "als", "ms ", "multiple sclerosis", "epilepsy",
        "migraine", "depression", "schizophrenia", "bipolar", "huntington",
        "sma", "duchenne", "neuropathy", "psychiatric", "neurological",
    ]
    cv_kw = [
        "heart failure", "atherosclerosis", "arrhythmia", "afib", "lipid",
        "cholesterol", "statin", "myocardial", "hfpef", "hfref", "coronary",
        "cardiac",
    ]
    metabolic_kw = [
        "diabetes", "obesity", "nafld", "nash", "mash", "metabolic",
        "insulin", "glucose", "lipase", "obesity", "overweight",
    ]
    immunology_kw = [
        "lupus", "rheumatoid", "psoriasis", "crohn", "ibd", "uc ", "ulcerative",
        "autoimmune", "inflammation", "immune", "il-", "jak", "atopic",
    ]
    rare_kw = [
        "rare", "orphan", "huntington", "fabry", "gaucher", "pompe",
        "lysosomal", "gene therapy", "enzyme replacement", "duchenne", "sma",
        "haemophilia", "hemophilia", "thalassemia", "pku",
    ]
    for kw in oncology_kw:
        if kw in ind:
            return "oncology"
    for kw in rare_kw:
        if kw in ind:
            return "rare_disease"
    for kw in cns_kw:
        if kw in ind:
            return "cns"
    for kw in immunology_kw:
        if kw in ind:
            return "immunology"
    for kw in metabolic_kw:
        if kw in ind:
            return "metabolic"
    for kw in cv_kw:
        if kw in ind:
            return "cardiovascular"
    return "other"


def _heuristic_pos_from_row(row: dict, phase: str) -> float:
    """Estimate POS from feature set for CSV-loaded records without stored model outputs."""
    import warnings

    warnings.warn(
        "_heuristic_pos_from_row() reconstructs a simplified proxy of model predictions. "
        "Use BacktestReport.to_calibration_records() for actual model scores. "
        "Calibration metrics computed via this path do not reflect true model performance.",
        DeprecationWarning,
        stacklevel=2,
    )
    from bve.config.assumptions_loader import AssumptionsLoader
    ta_str = row.get("therapeutic_area", "other") or "other"
    try:
        rates = AssumptionsLoader().phase_success_rates(ta_str.lower())
        base = rates.get(phase, 0.40)
    except Exception:
        base = 0.40 if phase == "phase_2" else 0.62

    # Simple log-odds adjusters to approximate the model
    import math as _math
    lo = _math.log(base / (1 - base))

    moa = row.get("moa_precedent", "partial").lower()
    if moa == "validated":
        lo += 0.20
    elif moa == "novel":
        lo -= 0.15

    if str(row.get("biomarker_enriched", "")).lower() == "true":
        lo += 0.30

    safety = row.get("safety_profile", "minor").lower()
    if safety in ("serious", "concerning"):
        lo -= 0.25

    ep = row.get("endpoint_type", "surrogate_validated").lower()
    if "hard" in ep:
        lo += 0.10
    elif "composite" in ep:
        lo -= 0.05

    p = 1 / (1 + _math.exp(-lo))
    return round(max(0.05, min(0.95, p)), 4)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _r(v: Optional[float], d: int = 4) -> Optional[float]:
    return round(v, d) if v is not None else None


def _fmt(v: Optional[float]) -> str:
    return f"{v:.4f}" if v is not None else "n/a"


def _fmt_signed(v: Optional[float]) -> str:
    return f"{v:+.4f}" if v is not None else "n/a"
