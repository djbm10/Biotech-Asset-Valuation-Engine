"""
Backtesting: validate POS model predictions against historical drug trial outcomes.

Loads the oncology dataset from research/data/oncology_phase_transitions.csv (and optional
multi-TA datasets), runs the heuristic and statistical POS models on each program's feature
set, and computes calibration metrics.

Key metrics
-----------
- Brier Score: mean squared error between predicted P and actual outcome (lower = better)
  - 0.0 = perfect; 0.25 = no-skill baseline (always predicting 0.5)
  - Published industry models typically achieve 0.18–0.22 on held-out data
- Calibration: within each predicted-P decile, actual success rate should match
- AUC: discrimination (ability to rank successes above failures), computed via scipy

Interpreting results
--------------------
With ~70 observations (realistic 48% base rate), SE(Brier) ≈ ±0.03 and AUC
confidence intervals span ±0.12. Use these metrics directionally, not as definitive
model assessments. Production validation requires 500+ programs with known outcomes.
The dataset targets ~40% Phase 2 and ~60% Phase 3 success rates (Biomedtracker priors).

Usage
-----
    from bve.analysis.backtest import run_backtest_from_csv, print_report
    report = run_backtest_from_csv("research/data/oncology_phase_transitions.csv")
    print(print_report(report))

    # Multi-TA combined backtest
    from bve.analysis.backtest import run_combined_backtest_from_files
    report = run_combined_backtest_from_files({
        "oncology": "research/data/oncology_phase_transitions.csv",
        "immunology": "research/data/immunology_phase_transitions.csv",
        "rare_disease": "research/data/rare_disease_phase_transitions.csv",
        "cns": "research/data/cns_phase_transitions.csv",
        "cardiovascular": "research/data/cardiovascular_phase_transitions.csv",
    })
    print(print_report(report))

    # Or run as a script (single TA)
    python -m bve.analysis.backtest research/data/oncology_phase_transitions.csv
    # Combined multi-TA run
    python -m bve.analysis.backtest --multi-ta
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class BacktestCase:
    """A single historical trial program with features and known outcome."""
    drug: str
    company: str
    indication: str
    phase: str                 # "phase_2" | "phase_3"
    outcome: str               # "approved" | "advanced" | "failed"
    year: int
    endpoint_type: str         # "hard_clinical" | "surrogate_validated" | ...
    moa_precedent: str         # "validated" | "partial" | "novel"
    biomarker_enriched: bool
    safety_profile: str        # "clean" | "minor" | "concerning" | "serious"
    competitive_pressure: str  # "low" | "moderate" | "high"
    therapeutic_area: str = "oncology"  # TA for POS base rate lookup
    notes: str = ""

    @property
    def success(self) -> bool:
        """True if the program advanced past this phase (approved or accelerated)."""
        return self.outcome.lower() in ("approved", "advanced")


@dataclass
class BacktestResult:
    """Prediction result for a single program."""
    case: BacktestCase
    heuristic_pos: float
    statistical_pos: float

    @property
    def heuristic_error(self) -> float:
        return self.heuristic_pos - float(self.case.success)

    @property
    def statistical_error(self) -> float:
        return self.statistical_pos - float(self.case.success)

    @property
    def heuristic_brier(self) -> float:
        return (self.heuristic_pos - float(self.case.success)) ** 2

    @property
    def statistical_brier(self) -> float:
        return (self.statistical_pos - float(self.case.success)) ** 2


@dataclass
class CalibrationBucket:
    """Actual success rate within a predicted-probability bucket."""
    label: str         # e.g. "20–40%"
    n: int
    n_success: int
    predicted_mean: float

    @property
    def actual_rate(self) -> float:
        return self.n_success / self.n if self.n > 0 else float("nan")


@dataclass
class BacktestReport:
    """Aggregate metrics from backtesting POS model predictions."""
    n_total: int
    n_phase2: int
    n_phase3: int
    n_success: int

    heuristic_brier_score: float
    statistical_brier_score: float
    no_skill_brier_score: float  # baseline: always predict base rate

    heuristic_auc: float         # AUC-ROC via trapezoid rule
    statistical_auc: float

    # Per-phase breakdown
    heuristic_brier_phase2: float
    heuristic_brier_phase3: float
    statistical_brier_phase2: float
    statistical_brier_phase3: float

    # Calibration buckets (predicted P deciles)
    calibration_heuristic: list[CalibrationBucket] = field(default_factory=list)
    calibration_statistical: list[CalibrationBucket] = field(default_factory=list)

    # Raw results for downstream analysis
    results: list[BacktestResult] = field(default_factory=list)
    calibration_suite: Optional[object] = None

    @property
    def heuristic_lift_over_noskill(self) -> float:
        """Brier skill score vs. no-skill baseline (higher = better)."""
        if self.no_skill_brier_score == 0:
            return 0.0
        return 1.0 - self.heuristic_brier_score / self.no_skill_brier_score

    @property
    def statistical_lift_over_noskill(self) -> float:
        if self.no_skill_brier_score == 0:
            return 0.0
        return 1.0 - self.statistical_brier_score / self.no_skill_brier_score

    def to_calibration_records(self):
        """Convert results to calibration records using actual heuristic scores."""
        from bve.analysis.pos_calibration import POSCalibrationRecord

        return [
            POSCalibrationRecord(
                therapeutic_area=r.case.therapeutic_area,
                phase=r.case.phase,
                predicted_pos=r.heuristic_pos,
                actual_success=r.case.success,
                drug=r.case.drug,
                company=r.case.company,
                indication=r.case.indication,
                year=r.case.year,
                notes=r.case.notes,
            )
            for r in self.results
        ]

    def to_calibration_records_statistical(self):
        """Convert results to calibration records using actual statistical scores."""
        from bve.analysis.pos_calibration import POSCalibrationRecord

        return [
            POSCalibrationRecord(
                therapeutic_area=r.case.therapeutic_area,
                phase=r.case.phase,
                predicted_pos=r.statistical_pos,
                actual_success=r.case.success,
                drug=r.case.drug,
                company=r.case.company,
                indication=r.case.indication,
                year=r.case.year,
                notes=r.case.notes,
            )
            for r in self.results
        ]


# ---------------------------------------------------------------------------
# AUC computation (no sklearn dependency)
# ---------------------------------------------------------------------------

def _compute_auc(y_true: list[bool], y_score: list[float]) -> float:
    """Area under ROC curve via trapezoidal rule."""
    if len(set(y_true)) < 2:
        return float("nan")  # only one class

    pairs = sorted(zip(y_score, y_true), key=lambda x: -x[0])
    n_pos = sum(y_true)
    n_neg = len(y_true) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")

    tp = fp = 0
    auc = 0.0
    prev_fp = 0
    prev_tp = 0
    for _score, label in pairs:
        if label:
            tp += 1
        else:
            fp += 1
        # Trapezoidal increment
        auc += (fp - prev_fp) * (tp + prev_tp) / 2.0
        prev_fp = fp
        prev_tp = tp

    return auc / (n_pos * n_neg)


# ---------------------------------------------------------------------------
# Calibration buckets
# ---------------------------------------------------------------------------

def _build_calibration(results: list[BacktestResult], use_statistical: bool) -> list[CalibrationBucket]:
    """Group results into four predicted-probability buckets and compute actual rates."""
    buckets: dict[str, list[tuple[float, bool]]] = {
        "0–25%": [],
        "25–50%": [],
        "50–75%": [],
        "75–100%": [],
    }
    for r in results:
        p = r.statistical_pos if use_statistical else r.heuristic_pos
        success = r.case.success
        if p < 0.25:
            buckets["0–25%"].append((p, success))
        elif p < 0.50:
            buckets["25–50%"].append((p, success))
        elif p < 0.75:
            buckets["50–75%"].append((p, success))
        else:
            buckets["75–100%"].append((p, success))

    out = []
    for label, items in buckets.items():
        if not items:
            out.append(CalibrationBucket(label=label, n=0, n_success=0, predicted_mean=float("nan")))
        else:
            probs, successes = zip(*items)
            out.append(CalibrationBucket(
                label=label,
                n=len(items),
                n_success=sum(successes),
                predicted_mean=float(np.mean(probs)),
            ))
    return out


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

def load_cases_from_csv(csv_path: str | Path, therapeutic_area: str = "oncology") -> list[BacktestCase]:
    """
    Load BacktestCase list from a phase_transitions.csv file.

    Expected columns: drug, company, indication, phase_start, outcome, year,
    moa_precedent, biomarker_enriched, safety_profile, competitive_pressure,
    endpoint_type, notes

    Args:
        csv_path: Path to the CSV file.
        therapeutic_area: TA string for POS base rate lookup (e.g. "oncology",
            "immunology", "rare_disease", "cns", "cardiovascular"). Defaults
            to "oncology" for backward compatibility.
    """
    import csv

    cases = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            phase = row.get("phase_start", "").strip()
            if phase not in ("phase_2", "phase_3"):
                continue  # skip NDA-stage entries and blank rows
            cases.append(BacktestCase(
                drug=row["drug"].strip(),
                company=row.get("company", "").strip(),
                indication=row.get("indication", "").strip(),
                phase=phase,
                outcome=row.get("outcome", "").strip(),
                year=int(row.get("year", 2020)),
                endpoint_type=row.get("endpoint_type", "surrogate_validated").strip(),
                moa_precedent=row.get("moa_precedent", "partial").strip(),
                biomarker_enriched=row.get("biomarker_enriched", "false").strip().lower() == "true",
                safety_profile=row.get("safety_profile", "minor").strip(),
                competitive_pressure=row.get("competitive_pressure", "moderate").strip(),
                therapeutic_area=therapeutic_area,
                notes=row.get("notes", "").strip(),
            ))
    return cases


# ---------------------------------------------------------------------------
# Core backtest
# ---------------------------------------------------------------------------

def run_backtest(cases: list[BacktestCase]) -> BacktestReport:
    """Run backtest on a list of BacktestCase objects."""
    from bve.entities.asset import TherapeuticArea
    from bve.entities.trial import EndpointType, TrialPhase
    from bve.models.pos_model import (
        CompetitivePressure, MoAPrecedent, POSAdjusters, SafetyProfile, compute_pos
    )
    from bve.models.pos_statistical import compute_pos_statistical

    phase_map = {
        "phase_2": TrialPhase.PHASE_2,
        "phase_3": TrialPhase.PHASE_3,
    }
    endpoint_map = {e.value: e for e in EndpointType}
    moa_map = {m.value: m for m in MoAPrecedent}
    safety_map = {s.value: s for s in SafetyProfile}
    competition_map = {c.value: c for c in CompetitivePressure}
    ta_map = {e.value: e for e in TherapeuticArea}

    results = []
    for case in cases:
        if case.phase not in phase_map:
            continue
        phase_enum = phase_map[case.phase]
        adj = POSAdjusters(
            endpoint_type=endpoint_map.get(case.endpoint_type, EndpointType.SURROGATE_VALIDATED),
            moa_precedent=moa_map.get(case.moa_precedent, MoAPrecedent.PARTIAL),
            safety_profile=safety_map.get(case.safety_profile, SafetyProfile.MINOR),
            competitive_pressure=competition_map.get(case.competitive_pressure, CompetitivePressure.MODERATE),
            biomarker_selected_population=case.biomarker_enriched,
        )
        ta = ta_map.get(case.therapeutic_area, TherapeuticArea.OTHER)

        h_pos = compute_pos(phase_enum, ta, adj)
        s_pos = compute_pos_statistical(phase_enum, ta, adj)
        results.append(BacktestResult(case=case, heuristic_pos=h_pos, statistical_pos=s_pos))

    if not results:
        raise ValueError("No valid cases to backtest.")

    # Aggregate metrics
    y_true = [r.case.success for r in results]
    h_scores = [r.heuristic_pos for r in results]
    s_scores = [r.statistical_pos for r in results]

    h_brier = float(np.mean([r.heuristic_brier for r in results]))
    s_brier = float(np.mean([r.statistical_brier for r in results]))

    base_rate = float(np.mean(y_true))
    no_skill_brier = float(np.mean([(base_rate - float(y)) ** 2 for y in y_true]))

    phase2_results = [r for r in results if r.case.phase == "phase_2"]
    phase3_results = [r for r in results if r.case.phase == "phase_3"]

    def _safe_brier(rs: list[BacktestResult], use_stat: bool) -> float:
        if not rs:
            return float("nan")
        values = [r.statistical_brier if use_stat else r.heuristic_brier for r in rs]
        return float(np.mean(values))

    return BacktestReport(
        n_total=len(results),
        n_phase2=len(phase2_results),
        n_phase3=len(phase3_results),
        n_success=sum(y_true),
        heuristic_brier_score=round(h_brier, 4),
        statistical_brier_score=round(s_brier, 4),
        no_skill_brier_score=round(no_skill_brier, 4),
        heuristic_auc=round(_compute_auc(y_true, h_scores), 4),
        statistical_auc=round(_compute_auc(y_true, s_scores), 4),
        heuristic_brier_phase2=round(_safe_brier(phase2_results, False), 4),
        heuristic_brier_phase3=round(_safe_brier(phase3_results, False), 4),
        statistical_brier_phase2=round(_safe_brier(phase2_results, True), 4),
        statistical_brier_phase3=round(_safe_brier(phase3_results, True), 4),
        calibration_heuristic=_build_calibration(results, use_statistical=False),
        calibration_statistical=_build_calibration(results, use_statistical=True),
        results=results,
    )


def run_backtest_from_csv(csv_path: str | Path, therapeutic_area: str = "oncology") -> BacktestReport:
    """Load CSV and run full backtest. Convenience wrapper."""
    cases = load_cases_from_csv(csv_path, therapeutic_area=therapeutic_area)
    report = run_backtest(cases)
    from bve.analysis.pos_calibration import run_pos_calibration_from_records

    report.calibration_suite = run_pos_calibration_from_records(
        report.to_calibration_records(),
        model_name=f"heuristic_{therapeutic_area}",
        time_split_year=2020,
    )
    return report


# Default multi-TA file map relative to project root
_DEFAULT_TA_CSV_MAP: dict[str, str] = {
    "oncology": "research/data/oncology_phase_transitions.csv",
    "immunology": "research/data/immunology_phase_transitions.csv",
    "rare_disease": "research/data/rare_disease_phase_transitions.csv",
    "cns": "research/data/cns_phase_transitions.csv",
    "cardiovascular": "research/data/cardiovascular_phase_transitions.csv",
    "metabolic": "research/data/metabolic_phase_transitions.csv",
    "hematology": "research/data/hematology_phase_transitions.csv",
    "infectious_disease": "research/data/infectious_disease_phase_transitions.csv",
}


def run_combined_backtest_from_files(
    ta_csv_map: dict[str, str] | None = None,
) -> tuple[BacktestReport, dict[str, BacktestReport]]:
    """
    Run POS backtest across multiple therapeutic areas and return combined + per-TA reports.

    Args:
        ta_csv_map: Mapping of TA name → CSV path. Defaults to all 5 standard TA files.

    Returns:
        Tuple of (combined_report, per_ta_reports) where combined_report pools all cases
        and per_ta_reports maps TA name → individual BacktestReport.

    Missing files are skipped with a warning.
    """
    import warnings

    if ta_csv_map is None:
        ta_csv_map = _DEFAULT_TA_CSV_MAP

    all_cases: list[BacktestCase] = []
    per_ta: dict[str, BacktestReport] = {}

    for ta, csv_path in ta_csv_map.items():
        path = Path(csv_path)
        if not path.exists():
            warnings.warn(f"Skipping {ta}: file not found at {csv_path}", stacklevel=2)
            continue
        cases = load_cases_from_csv(path, therapeutic_area=ta)
        if not cases:
            warnings.warn(f"Skipping {ta}: no valid cases loaded from {csv_path}", stacklevel=2)
            continue
        per_ta[ta] = run_backtest(cases)
        all_cases.extend(cases)

    if not all_cases:
        raise ValueError("No valid cases loaded from any TA file.")

    combined = run_backtest(all_cases)
    return combined, per_ta


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_report(report: BacktestReport) -> str:
    """Format a BacktestReport as a human-readable string.

    Always prepends the hard validation disclaimer. This output is
    RESEARCH_GRADE for oncology (N=99) and UNVALIDATED for all other TAs.
    """
    from bve.validation.model_grade import (
        BacktestValidationStatus,
        validation_disclaimer,
    )
    disclaimer = validation_disclaimer(BacktestValidationStatus.RESEARCH_GRADE)
    # Derive label from TA mix in results
    ta_set = {r.case.therapeutic_area for r in report.results} if report.results else {"oncology"}
    ta_label = "/".join(sorted(ta_set)) if len(ta_set) > 1 else next(iter(ta_set))

    lines = [
        disclaimer,
        "=" * 65,
        "  BVE POS Model Backtest Report",
        f"  Dataset: {report.n_total} {ta_label} programs ({report.n_phase2} Phase 2, "
        f"{report.n_phase3} Phase 3)",
        f"  Base rate (actual success): {report.n_success}/{report.n_total} = "
        f"{report.n_success/report.n_total:.1%}",
        "=" * 65,
        "",
        "  Brier Score (lower = better; 0.25 = no-skill)",
        f"  {'Model':<22} {'Overall':>8}  {'Phase 2':>8}  {'Phase 3':>8}",
        "  " + "─" * 48,
        f"  {'No-skill baseline':<22} {report.no_skill_brier_score:>8.4f}",
        f"  {'Heuristic (log-odds)':<22} {report.heuristic_brier_score:>8.4f}  "
        f"{report.heuristic_brier_phase2:>8.4f}  {report.heuristic_brier_phase3:>8.4f}",
        f"  {'Statistical (logit)':<22} {report.statistical_brier_score:>8.4f}  "
        f"{report.statistical_brier_phase2:>8.4f}  {report.statistical_brier_phase3:>8.4f}",
        "",
        "  AUC-ROC (higher = better; 0.5 = chance)",
        f"  {'Heuristic':<22} {report.heuristic_auc:>8.4f}",
        f"  {'Statistical':<22} {report.statistical_auc:>8.4f}",
        "",
        "  Brier Skill Score (heuristic vs. no-skill, higher = better)",
        f"  {'Heuristic':<22} {report.heuristic_lift_over_noskill:>+8.1%}",
        f"  {'Statistical':<22} {report.statistical_lift_over_noskill:>+8.1%}",
        "",
    ]

    # Calibration table
    lines.append("  Calibration (heuristic) — predicted vs. actual success rate")
    lines.append(f"  {'Bucket':<12} {'N':>4}  {'Pred':>6}  {'Actual':>6}")
    lines.append("  " + "─" * 32)
    for bkt in report.calibration_heuristic:
        actual_str = f"{bkt.actual_rate:.0%}" if bkt.n > 0 else "  —"
        pred_str = f"{bkt.predicted_mean:.0%}" if bkt.n > 0 else "  —"
        lines.append(f"  {bkt.label:<12} {bkt.n:>4}  {pred_str:>6}  {actual_str:>6}")

    lines.append("")

    # Per-program detail
    lines.append("  Per-program predictions")
    lines.append(f"  {'Drug':<22} {'Ph':>4}  {'Actual':>7}  {'Heur':>6}  {'Stat':>6}  {'Err':>6}")
    lines.append("  " + "─" * 60)
    for r in sorted(report.results, key=lambda x: x.case.phase + x.case.drug):
        actual = "SUCCESS" if r.case.success else "FAIL   "
        err_str = f"{r.heuristic_error:>+.2f}"
        lines.append(
            f"  {r.case.drug:<22} {r.case.phase.replace('phase_', 'P'):>4}  "
            f"{actual:>7}  {r.heuristic_pos:>6.1%}  {r.statistical_pos:>6.1%}  {err_str}"
        )

    lines.extend([
        "",
        f"  Note: N={report.n_total} yields SE(Brier) ≈ ±0.03, SE(AUC) ≈ ±0.12.",
        "  Use these metrics directionally; 500+ programs required for reliable calibration.",
        "=" * 65,
        "",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--multi-ta" in sys.argv:
        # Run combined 5-TA backtest
        try:
            combined, per_ta = run_combined_backtest_from_files()
            # Per-TA summary
            print("=" * 65)
            print("  Per-TA Backtest Summary")
            print(f"  {'TA':<20} {'N':>5}  {'Base%':>6}  {'H-Brier':>8}  {'H-AUC':>7}  {'Lift':>7}")
            print("  " + "─" * 56)
            for ta_name, rpt in sorted(per_ta.items()):
                base = rpt.n_success / rpt.n_total if rpt.n_total else 0
                lift = rpt.heuristic_lift_over_noskill
                print(
                    f"  {ta_name:<20} {rpt.n_total:>5}  {base:>6.1%}  "
                    f"{rpt.heuristic_brier_score:>8.4f}  {rpt.heuristic_auc:>7.4f}  {lift:>+7.1%}"
                )
            print()
            print(print_report(combined))
        except (FileNotFoundError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        csv_path = sys.argv[1] if len(sys.argv) > 1 else "research/data/oncology_phase_transitions.csv"
        # Infer TA from filename
        _fname = Path(csv_path).stem
        _ta = "oncology"
        for _candidate in ("immunology", "rare_disease", "cns", "cardiovascular"):
            if _candidate in _fname:
                _ta = _candidate
                break
        try:
            report = run_backtest_from_csv(csv_path, therapeutic_area=_ta)
            print(print_report(report))
        except FileNotFoundError:
            print(f"ERROR: CSV file not found: {csv_path}", file=sys.stderr)
            print("Run from the project root: python -m bve.analysis.backtest research/data/oncology_phase_transitions.csv")
            print("Or run: python -m bve.analysis.backtest --multi-ta")
            sys.exit(1)
