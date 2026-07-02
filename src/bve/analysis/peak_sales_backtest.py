"""Backtest predicted peak sales against realized sales for approved drugs.

This is the commercial counterpart to the POS backtest: it validates the other
large multiplicative input to rNPV without changing the valuation model. The
seed dataset is intentionally small and should be treated as a measurement
surface, not a calibration basis.
"""

from __future__ import annotations

import csv
import math
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_PEAK_SALES_BACKTEST_CSV = Path("research/data/peak_sales_backtest.csv")
MIN_N_FOR_RELIABLE_ESTIMATE = 20


@dataclass(frozen=True)
class PeakSalesCase:
    """One historical peak-sales prediction and realized outcome."""

    program_id: str
    drug: str
    company: str
    indication: str
    therapeutic_area: str
    prediction_year: int
    predicted_peak_sales_millions: float
    realized_peak_sales_millions: float
    realized_peak_sales_year: int
    actual_sales_basis: str = ""
    source: str = ""
    notes: str = ""

    @property
    def ratio_predicted_to_actual(self) -> float:
        return self.predicted_peak_sales_millions / self.realized_peak_sales_millions

    @property
    def error_millions(self) -> float:
        return self.predicted_peak_sales_millions - self.realized_peak_sales_millions

    @property
    def pct_error(self) -> float:
        return self.error_millions / self.realized_peak_sales_millions

    @property
    def abs_pct_error(self) -> float:
        return abs(self.pct_error)

    @property
    def fold_error(self) -> float:
        ratio = self.ratio_predicted_to_actual
        return max(ratio, 1.0 / ratio)


@dataclass(frozen=True)
class PeakSalesBacktestReport:
    """Aggregate commercial-forecast error metrics."""

    n_total: int
    mean_actual_peak_sales_millions: float
    mean_predicted_peak_sales_millions: float
    mean_error_millions: float
    mae_millions: float
    rmse_millions: float
    mean_abs_pct_error: float
    median_abs_pct_error: float
    mean_log_error: float
    within_25pct: float
    within_50pct: float
    within_2x: float
    is_low_n: bool
    cases: list[PeakSalesCase] = field(default_factory=list)

    @property
    def bias_direction(self) -> str:
        if self.mean_error_millions > 0:
            return "over-forecast"
        if self.mean_error_millions < 0:
            return "under-forecast"
        return "neutral"

    def to_dict(self) -> dict:
        return {
            "n_total": self.n_total,
            "mean_actual_peak_sales_millions": round(self.mean_actual_peak_sales_millions, 2),
            "mean_predicted_peak_sales_millions": round(
                self.mean_predicted_peak_sales_millions, 2
            ),
            "mean_error_millions": round(self.mean_error_millions, 2),
            "mae_millions": round(self.mae_millions, 2),
            "rmse_millions": round(self.rmse_millions, 2),
            "mean_abs_pct_error": round(self.mean_abs_pct_error, 4),
            "median_abs_pct_error": round(self.median_abs_pct_error, 4),
            "mean_log_error": round(self.mean_log_error, 4),
            "within_25pct": round(self.within_25pct, 4),
            "within_50pct": round(self.within_50pct, 4),
            "within_2x": round(self.within_2x, 4),
            "bias_direction": self.bias_direction,
            "is_low_n": self.is_low_n,
        }


def _required_float(row: dict[str, str], key: str) -> float:
    value = row.get(key, "").strip()
    if value == "":
        raise ValueError(f"missing required numeric column {key!r}")
    parsed = float(value)
    if parsed <= 0:
        raise ValueError(f"{key!r} must be positive; got {parsed}")
    return parsed


def _required_int(row: dict[str, str], key: str) -> int:
    value = row.get(key, "").strip()
    if value == "":
        raise ValueError(f"missing required integer column {key!r}")
    return int(value)


def load_peak_sales_cases(csv_path: str | Path = DEFAULT_PEAK_SALES_BACKTEST_CSV) -> list[PeakSalesCase]:
    """Load curated historical peak-sales cases from CSV."""

    path = Path(csv_path)
    cases: list[PeakSalesCase] = []
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cases.append(
                PeakSalesCase(
                    program_id=row["program_id"].strip(),
                    drug=row["drug"].strip(),
                    company=row["company"].strip(),
                    indication=row["indication"].strip(),
                    therapeutic_area=row["therapeutic_area"].strip().lower(),
                    prediction_year=_required_int(row, "prediction_year"),
                    predicted_peak_sales_millions=_required_float(
                        row, "predicted_peak_sales_millions"
                    ),
                    realized_peak_sales_millions=_required_float(
                        row, "realized_peak_sales_millions"
                    ),
                    realized_peak_sales_year=_required_int(row, "realized_peak_sales_year"),
                    actual_sales_basis=row.get("actual_sales_basis", "").strip(),
                    source=row.get("source", "").strip(),
                    notes=row.get("notes", "").strip(),
                )
            )
    return cases


def run_peak_sales_backtest(
    cases: list[PeakSalesCase] | None = None,
    *,
    csv_path: str | Path = DEFAULT_PEAK_SALES_BACKTEST_CSV,
) -> PeakSalesBacktestReport:
    """Compute peak-sales forecast error metrics.

    This function is measurement-only: it does not refit or alter revenue model
    assumptions.
    """

    if cases is None:
        cases = load_peak_sales_cases(csv_path)
    if not cases:
        raise ValueError("No peak-sales cases to backtest.")

    predicted = [c.predicted_peak_sales_millions for c in cases]
    actual = [c.realized_peak_sales_millions for c in cases]
    errors = [c.error_millions for c in cases]
    abs_errors = [abs(e) for e in errors]
    squared_errors = [e * e for e in errors]
    abs_pct_errors = [c.abs_pct_error for c in cases]
    log_errors = [math.log(c.ratio_predicted_to_actual) for c in cases]

    return PeakSalesBacktestReport(
        n_total=len(cases),
        mean_actual_peak_sales_millions=sum(actual) / len(actual),
        mean_predicted_peak_sales_millions=sum(predicted) / len(predicted),
        mean_error_millions=sum(errors) / len(errors),
        mae_millions=sum(abs_errors) / len(abs_errors),
        rmse_millions=math.sqrt(sum(squared_errors) / len(squared_errors)),
        mean_abs_pct_error=sum(abs_pct_errors) / len(abs_pct_errors),
        median_abs_pct_error=statistics.median(abs_pct_errors),
        mean_log_error=sum(log_errors) / len(log_errors),
        within_25pct=sum(1 for e in abs_pct_errors if e <= 0.25) / len(cases),
        within_50pct=sum(1 for e in abs_pct_errors if e <= 0.50) / len(cases),
        within_2x=sum(1 for c in cases if c.fold_error <= 2.0) / len(cases),
        is_low_n=len(cases) < MIN_N_FOR_RELIABLE_ESTIMATE,
        cases=list(cases),
    )


def print_peak_sales_report(report: PeakSalesBacktestReport) -> str:
    """Render a human-readable peak-sales backtest report."""

    lines = [
        "=" * 65,
        " BVE Peak-Sales Backtest Report",
        f" Dataset: {report.n_total} approved-drug commercial forecasts",
        " Scope: measurement only; no revenue model assumptions changed",
        "=" * 65,
        "",
    ]
    if report.is_low_n:
        lines.extend(
            [
                "LOW-N WARNING",
                f"  N={report.n_total}; need >= {MIN_N_FOR_RELIABLE_ESTIMATE} cases before",
                "  using these metrics for calibration or model-selection decisions.",
                "",
            ]
        )

    lines.extend(
        [
            "Aggregate error",
            f"  Mean predicted peak sales: ${report.mean_predicted_peak_sales_millions:,.0f}M",
            f"  Mean realized peak sales:  ${report.mean_actual_peak_sales_millions:,.0f}M",
            f"  Mean error:                ${report.mean_error_millions:,.0f}M "
            f"({report.bias_direction})",
            f"  MAE:                       ${report.mae_millions:,.0f}M",
            f"  RMSE:                      ${report.rmse_millions:,.0f}M",
            f"  MAPE:                      {report.mean_abs_pct_error:.1%}",
            f"  Median APE:                {report.median_abs_pct_error:.1%}",
            f"  Within 25%:                {report.within_25pct:.1%}",
            f"  Within 50%:                {report.within_50pct:.1%}",
            f"  Within 2x:                 {report.within_2x:.1%}",
            "",
            "Cases",
        ]
    )
    for case in report.cases:
        lines.append(
            f"  {case.program_id}: predicted ${case.predicted_peak_sales_millions:,.0f}M, "
            f"realized ${case.realized_peak_sales_millions:,.0f}M, "
            f"APE {case.abs_pct_error:.1%}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    csv_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PEAK_SALES_BACKTEST_CSV
    print(print_peak_sales_report(run_peak_sales_backtest(csv_path=csv_arg)))
