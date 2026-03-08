"""
Commercial calibration: compare engine predictions against historical asset revenue.

Purpose
-------
Demonstrates that the engine produces realistic commercial outcomes when given
calibrated inputs.  Designed to impress sophisticated readers by showing predicted
vs. actual revenue for well-known historical biotech assets.

Usage
-----
    from bve.analysis.commercial_calibration import run_calibration, print_calibration_report
    report = run_calibration("case_studies/ivacaftor_vertex/IVAC")
    print(print_calibration_report(report))

    # Or as a CLI:
    python -m bve.cli.calibrate case_studies/ivacaftor_vertex/IVAC

Inputs expected in <case_dir>/
------------------------------
  inputs.yaml       — standard BVE asset config (same format as bve-asset CLI)
  actual_revenue.yaml — historical revenue with schema:

    source: "Vertex annual reports 2012-2020"
    asset_name: "Ivacaftor (Kalydeco)"
    approval_year: 2012
    revenue_by_year:         # net product revenue, USD millions (calendar year)
      2012: 71
      2013: 382
      ...
    peak_year: 2014
    peak_revenue_millions: 498
    actual_pos_outcome: "approved"   # "approved" | "failed"
    notes: "G551D-positive CF only; later superseded by combination therapies"
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CalibrationReport:
    """Full comparison between engine predictions and historical outcomes."""
    asset_name: str
    case_dir: str

    # Historical ground truth
    source: str
    approval_year: int
    actual_pos_outcome: str          # "approved" | "failed"
    actual_revenue_by_year: dict[int, float]   # calendar year → net revenue ($M)
    actual_peak_year: int
    actual_peak_revenue_millions: float
    notes: str

    # Engine predictions (indexed from launch year = year 1)
    predicted_launch_year: int       # calendar year the engine predicts launch
    predicted_pos: float             # cumulative P(approval) from engine
    predicted_revenue_by_year: list[float]    # engine output: yr 1, yr 2, ...
    predicted_peak_revenue_millions: float

    # Derived comparisons (populated by run_calibration)
    year_by_year: list[dict] = field(default_factory=list)
    peak_error_pct: float = 0.0
    launch_year_1_error_pct: float = 0.0


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _load_actual(actual_path: Path) -> dict:
    with open(actual_path) as f:
        return yaml.safe_load(f)


def _run_engine(config_path: Path):
    """Load inputs.yaml and run ValuationEngine.  Returns ValuationOutput."""
    import yaml as _yaml
    from bve.cli.run_asset import _build_objects, _build_pos_adjusters, _build_design_adjusters
    from bve.models.drug_asset_program import DrugAssetProgram
    from bve.valuation.valuation_engine import ValuationEngine

    with open(config_path) as f:
        cfg = _yaml.safe_load(f)

    asset, company, trials, market_model = _build_objects(cfg)

    pos_adjusters, apply_pos = _build_pos_adjusters(cfg)
    design_adjusters, apply_design = _build_design_adjusters(cfg)

    program = DrugAssetProgram.build(
        asset=asset,
        trials=trials,
        market_model=market_model,
        pos_adjusters=pos_adjusters,
        design_features=design_adjusters,
    )

    engine = ValuationEngine.from_program(
        program,
        company,
        apply_pos_model=apply_pos,
        apply_design_model=apply_design,
    )
    return engine.run()


# ---------------------------------------------------------------------------
# Core comparison
# ---------------------------------------------------------------------------

def run_calibration(case_dir: str | Path) -> CalibrationReport:
    """
    Run the engine on inputs.yaml in case_dir and compare to actual_revenue.yaml.

    Parameters
    ----------
    case_dir : str or Path
        Directory containing inputs.yaml and actual_revenue.yaml.

    Returns
    -------
    CalibrationReport with year-by-year comparison and summary error metrics.
    """
    case_dir = Path(case_dir)
    inputs_path = case_dir / "inputs.yaml"
    actual_path = case_dir / "actual_revenue.yaml"

    for p in (inputs_path, actual_path):
        if not p.exists():
            raise FileNotFoundError(f"Required file not found: {p}")

    actual = _load_actual(actual_path)
    output = _run_engine(inputs_path)

    approval_year: int = actual["approval_year"]
    actual_rev: dict[int, float] = {
        int(k): float(v) for k, v in actual["revenue_by_year"].items()
    }
    actual_peak_year: int = actual["peak_year"]
    actual_peak_rev: float = float(actual["peak_revenue_millions"])

    predicted_rev: list[float] = (
        output.rnpv.revenue_stream.revenue_by_year
        if output.rnpv.revenue_stream is not None
        else []
    )
    predicted_pos: float = output.rnpv.cumulative_success_probability
    predicted_peak_rev: float = output.rnpv.peak_sales_millions

    # Align predicted revenue to calendar years (year 1 = approval_year)
    year_by_year = []
    for i, pred_rev in enumerate(predicted_rev):
        cal_year = approval_year + i
        act_rev = actual_rev.get(cal_year)
        error_pct = None
        if act_rev and act_rev > 0 and pred_rev is not None:
            error_pct = round((pred_rev - act_rev) / act_rev * 100, 1)
        year_by_year.append({
            "year": cal_year,
            "predicted_millions": round(pred_rev, 1) if pred_rev is not None else None,
            "actual_millions": act_rev,
            "error_pct": error_pct,
        })

    # Summary metrics
    actual_yr1 = actual_rev.get(approval_year, 0.0)
    pred_yr1 = predicted_rev[0] if predicted_rev else 0.0
    peak_error_pct = 0.0
    yr1_error_pct = 0.0
    if actual_peak_rev > 0:
        peak_error_pct = round((predicted_peak_rev - actual_peak_rev) / actual_peak_rev * 100, 1)
    if actual_yr1 > 0 and pred_yr1 > 0:
        yr1_error_pct = round((pred_yr1 - actual_yr1) / actual_yr1 * 100, 1)

    return CalibrationReport(
        asset_name=actual.get("asset_name", output.asset.name),
        case_dir=str(case_dir),
        source=actual.get("source", ""),
        approval_year=approval_year,
        actual_pos_outcome=actual.get("actual_pos_outcome", "approved"),
        actual_revenue_by_year=actual_rev,
        actual_peak_year=actual_peak_year,
        actual_peak_revenue_millions=actual_peak_rev,
        notes=actual.get("notes", ""),
        predicted_launch_year=approval_year,
        predicted_pos=round(predicted_pos, 3),
        predicted_revenue_by_year=predicted_rev,
        predicted_peak_revenue_millions=round(predicted_peak_rev, 1),
        year_by_year=year_by_year,
        peak_error_pct=peak_error_pct,
        launch_year_1_error_pct=yr1_error_pct,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_calibration_report(report: CalibrationReport) -> str:
    """Format a CalibrationReport as a human-readable string."""
    def _fmt(v) -> str:
        if v is None:
            return "    —"
        return f"{v:>6,.0f}"

    def _fmt_err(v) -> str:
        if v is None:
            return "     —"
        sign = "+" if v >= 0 else ""
        return f"{sign}{v:.1f}%"

    lines = [
        "",
        "=" * 72,
        f"  Commercial Calibration — {report.asset_name}",
        f"  Source: {report.source}",
        "=" * 72,
        "",
        "  Summary",
        "  ─────────────────────────────────────────────────────────",
        f"  {'Metric':<35} {'Predicted':>12}  {'Actual':>12}  {'Error':>8}",
        "  ─────────────────────────────────────────────────────────",
        f"  {'Approval year':<35} {report.predicted_launch_year:>12}  {report.approval_year:>12}",
        f"  {'P(approval) — predicted':<35} {report.predicted_pos:>11.1%}  "
        f"{'approved' if report.actual_pos_outcome == 'approved' else 'failed':>12}",
        f"  {'Peak revenue ($M)':<35} {report.predicted_peak_revenue_millions:>11,.0f}  "
        f"{report.actual_peak_revenue_millions:>11,.0f}  {_fmt_err(report.peak_error_pct):>8}",
        f"  {'Launch year 1 revenue ($M)':<35} "
        f"{(report.predicted_revenue_by_year[0] if report.predicted_revenue_by_year else 0):>11,.0f}  "
        f"{report.actual_revenue_by_year.get(report.approval_year, 0):>11,.0f}  "
        f"{_fmt_err(report.launch_year_1_error_pct):>8}",
        "",
        "  Year-by-Year Revenue ($M)",
        f"  {'Year':>6}  {'Predicted':>10}  {'Actual':>10}  {'Error':>8}",
        "  " + "─" * 40,
    ]

    for row in report.year_by_year:
        if row["predicted_millions"] is None and row["actual_millions"] is None:
            continue
        pred_str = f"{row['predicted_millions']:>10,.0f}" if row["predicted_millions"] is not None else "         —"
        act_str = f"{row['actual_millions']:>10,.0f}" if row["actual_millions"] is not None else "         —"
        err_str = _fmt_err(row["error_pct"]) if row["error_pct"] is not None else "     —"
        lines.append(f"  {row['year']:>6}  {pred_str}  {act_str}  {err_str:>8}")

    if report.notes:
        lines += ["", f"  Note: {report.notes}"]

    lines += ["", "=" * 72, ""]
    return "\n".join(lines)
