"""
Standardized table builders — returns formatted strings or DataFrames.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from bve.valuation.outputs import ValuationOutput


def valuation_summary_table(output: "ValuationOutput") -> pd.DataFrame:
    """Single-row summary table for the lead asset."""
    d = output.summary_dict
    return pd.DataFrame([{
        "Asset": d["asset_name"],
        "Indication": d["indication"],
        "Stage": d["stage"].replace("_", " ").upper(),
        "P(Approval)": d["prob_approval_pct"],
        "Peak Sales ($M)": f"${d['peak_sales_millions']:,.0f}",
        "rNPV ($M)": f"${d['rnpv_millions']:,.0f}",
        "NAV ($M)": f"${d['nav_millions']:,.0f}",
        "NAV/Share": f"${d['nav_per_share']:.2f}",
        "Yrs to Launch": f"{d['years_to_launch']:.1f}",
        "WACC": d["discount_rate_pct"],
    }])


def scenario_table(output: "ValuationOutput") -> pd.DataFrame:
    rows = []
    for s in output.scenarios.as_list:
        rows.append({
            "Scenario": s.label,
            "rNPV ($M)": f"${s.rnpv_millions:,.0f}",
            "NAV ($M)": f"${s.nav_millions:,.0f}",
            "NAV/Share": f"${s.nav_per_share:.2f}",
            "P(Approval)": f"{s.cumulative_success_probability:.1%}",
            "Peak Sales ($M)": f"${s.peak_sales_millions:,.0f}",
            "Yrs to Launch": f"{s.years_to_launch:.1f}",
        })
    return pd.DataFrame(rows)


def monte_carlo_table(output: "ValuationOutput") -> pd.DataFrame:
    mc = output.monte_carlo
    return pd.DataFrame([
        {"Metric": "Mean rNPV", "Value ($M)": f"${mc.mean_millions:,.0f}"},
        {"Metric": "Median (P50)", "Value ($M)": f"${mc.median_millions:,.0f}"},
        {"Metric": "Std Dev", "Value ($M)": f"${mc.std_millions:,.0f}"},
        {"Metric": "P5", "Value ($M)": f"${mc.percentile_5_millions:,.0f}"},
        {"Metric": "P10", "Value ($M)": f"${mc.percentile_10_millions:,.0f}"},
        {"Metric": "P25", "Value ($M)": f"${mc.percentile_25_millions:,.0f}"},
        {"Metric": "P75", "Value ($M)": f"${mc.percentile_75_millions:,.0f}"},
        {"Metric": "P90", "Value ($M)": f"${mc.percentile_90_millions:,.0f}"},
        {"Metric": "P95", "Value ($M)": f"${mc.percentile_95_millions:,.0f}"},
        {"Metric": "P(Positive Value)", "Value ($M)": f"{mc.probability_positive:.1%}"},
        {"Metric": "P(> $500M)", "Value ($M)": f"{mc.probability_above_500m:.1%}"},
        {"Metric": "P(> $1B)", "Value ($M)": f"{mc.probability_above_1b:.1%}"},
    ])


def tornado_table(output: "ValuationOutput") -> pd.DataFrame:
    base = output.rnpv.rnpv_millions
    rows = []
    for s in output.sensitivities:
        rows.append({
            "Driver": s.parameter,
            "Bear Case rNPV ($M)": f"${s.low_rnpv:,.0f}",
            "Base Case rNPV ($M)": f"${base:,.0f}",
            "Bull Case rNPV ($M)": f"${s.high_rnpv:,.0f}",
            "|Swing| ($M)": f"${abs(s.swing):,.0f}",
        })
    return pd.DataFrame(rows)


def phase_breakdown_table(output: "ValuationOutput") -> pd.DataFrame:
    rows = []
    for pb in output.rnpv.phase_breakdown:
        trial = next((t for t in output.trials if t.phase.value == pb.phase), None)
        rows.append({
            "Phase": pb.phase.upper().replace("_", " "),
            "P(Reaching)": f"{pb.prob_reaching:.1%}",
            "P(Success)": f"{pb.success_probability:.1%}",
            "Duration (yrs)": pb.duration_years,
            "Cost ($M)": f"${trial.cost_millions:,.0f}" if trial else "—",
            "Weighted PV Cost ($M)": f"${pb.pv_cost_weighted:,.1f}",
        })
    return pd.DataFrame(rows)


def pipeline_table(trials: list, assets: list | None = None) -> pd.DataFrame:
    """Aggregate multi-asset pipeline summary."""
    rows = []
    for t in trials:
        rows.append({
            "Asset ID": t.asset_id,
            "Phase": t.phase.value.upper().replace("_", " "),
            "P(Success)": f"{t.success_probability:.0%}",
            "Duration (yrs)": t.duration_years,
            "NCT ID": t.nct_id or "—",
            "Status": t.status.value if t.status else "—",
            "Enrollment": t.enrollment or "—",
            "Primary Endpoint": (t.primary_endpoint or "")[:60],
        })
    return pd.DataFrame(rows)
