"""Market-regime controls for historical replay decisions."""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RegimeSubgroup:
    label: str
    n: int
    mean_return_pct: Optional[float]
    mean_xbi_return: Optional[float]
    xbi_adjusted_alpha: Optional[float]
    hit_rate: Optional[float]


@dataclass
class RegimeReport:
    n_with_regime_data: int
    raw_mean_return: Optional[float]
    overall_beta_to_xbi: Optional[float]
    xbi_adjusted_mean_return: Optional[float]
    ibb_adjusted_mean_return: Optional[float]
    spy_adjusted_mean_return: Optional[float]
    r_squared_xbi: Optional[float]
    alpha_survives_xbi_adjustment: bool
    subgroups: list[RegimeSubgroup] = field(default_factory=list)

    def summary(self) -> str:
        if self.n_with_regime_data < 15 or self.overall_beta_to_xbi is None:
            return (
                "Market regime analysis: insufficient XBI-matched decisions "
                f"(N={self.n_with_regime_data}, minimum 15)."
            )
        lines = [
            "=" * 70,
            "  MARKET REGIME ANALYSIS",
            "=" * 70,
            f"  N with XBI data       : {self.n_with_regime_data}",
            f"  Beta to XBI           : {self.overall_beta_to_xbi:.2f}",
            f"  R^2 vs XBI            : {self.r_squared_xbi:.2f}"
            if self.r_squared_xbi is not None else "  R^2 vs XBI            : n/a",
            f"  Raw mean return       : {_fmt_pct(self.raw_mean_return)}",
            f"  XBI-adjusted alpha    : {_fmt_pct(self.xbi_adjusted_mean_return)}",
            f"  IBB-adjusted mean     : {_fmt_pct(self.ibb_adjusted_mean_return)}",
            f"  SPY-adjusted mean     : {_fmt_pct(self.spy_adjusted_mean_return)}",
            "  Alpha survives XBI adj: "
            f"{'YES' if self.alpha_survives_xbi_adjustment else 'NO'}",
            "",
            "  Subgroups:",
        ]
        for subgroup in self.subgroups:
            lines.append(
                f"    {subgroup.label:<18} N={subgroup.n:<3} "
                f"mean={_fmt_pct(subgroup.mean_return_pct):>8} "
                f"XBI={_fmt_pct(subgroup.mean_xbi_return):>8} "
                f"hit={_fmt_rate(subgroup.hit_rate):>6}"
            )
        lines.append("=" * 70)
        return "\n".join(lines)


def compute_regime_report(decisions: list[dict]) -> RegimeReport:
    """Compute XBI-adjusted alpha and entry-regime subgroups."""
    valid = [
        d for d in decisions
        if d.get("return_pct") is not None and d.get("xbi_return_during_hold") is not None
    ]
    n = len(valid)
    raw_returns = [float(d["return_pct"]) for d in valid]
    xbi_returns = [float(d["xbi_return_during_hold"]) for d in valid]
    raw_mean = statistics.mean(raw_returns) if raw_returns else None

    beta = None
    alpha = None
    r2 = None
    if n >= 15:
        x_mean = statistics.mean(xbi_returns)
        y_mean = statistics.mean(raw_returns)
        var_x = sum((x - x_mean) ** 2 for x in xbi_returns)
        if var_x > 1e-12:
            cov_xy = sum((x - x_mean) * (y - y_mean) for x, y in zip(xbi_returns, raw_returns))
            beta = cov_xy / var_x
            alpha = y_mean - beta * x_mean
            fitted = [alpha + beta * x for x in xbi_returns]
            ss_tot = sum((y - y_mean) ** 2 for y in raw_returns)
            ss_res = sum((y - yh) ** 2 for y, yh in zip(raw_returns, fitted))
            r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else None

    ibb_adj = _mean_adjusted(valid, "ibb_return_during_hold")
    spy_adj = _mean_adjusted(valid, "spy_return_during_hold")
    subgroups = [
        _subgroup("XBI above 20d MA", [d for d in valid if d.get("xbi_above_20d_ma_at_entry") == 1]),
        _subgroup("XBI below 20d MA", [d for d in valid if d.get("xbi_above_20d_ma_at_entry") == 0]),
        _subgroup("XBI MA unknown", [d for d in valid if d.get("xbi_above_20d_ma_at_entry") is None]),
    ]
    return RegimeReport(
        n_with_regime_data=n,
        raw_mean_return=round(raw_mean, 4) if raw_mean is not None else None,
        overall_beta_to_xbi=round(beta, 4) if beta is not None else None,
        xbi_adjusted_mean_return=round(alpha, 4) if alpha is not None else None,
        ibb_adjusted_mean_return=ibb_adj,
        spy_adjusted_mean_return=spy_adj,
        r_squared_xbi=round(r2, 4) if r2 is not None else None,
        alpha_survives_xbi_adjustment=alpha is not None and alpha > 0,
        subgroups=[s for s in subgroups if s.n > 0],
    )


def _mean_adjusted(decisions: list[dict], benchmark_key: str) -> Optional[float]:
    pairs = [
        (float(d["return_pct"]), float(d[benchmark_key]))
        for d in decisions
        if d.get("return_pct") is not None and d.get(benchmark_key) is not None
    ]
    if not pairs:
        return None
    return round(statistics.mean(r - b for r, b in pairs), 4)


def _subgroup(label: str, decisions: list[dict]) -> RegimeSubgroup:
    returns = [float(d["return_pct"]) for d in decisions if d.get("return_pct") is not None]
    xbi = [
        float(d["xbi_return_during_hold"])
        for d in decisions
        if d.get("xbi_return_during_hold") is not None
    ]
    mean_r = statistics.mean(returns) if returns else None
    mean_xbi = statistics.mean(xbi) if xbi else None
    hit = sum(1 for r in returns if r > 0) / len(returns) if returns else None
    alpha = mean_r - mean_xbi if mean_r is not None and mean_xbi is not None else None
    return RegimeSubgroup(
        label=label,
        n=len(returns),
        mean_return_pct=round(mean_r, 4) if mean_r is not None else None,
        mean_xbi_return=round(mean_xbi, 4) if mean_xbi is not None else None,
        xbi_adjusted_alpha=round(alpha, 4) if alpha is not None else None,
        hit_rate=round(hit, 4) if hit is not None else None,
    )


def _fmt_pct(value: Optional[float]) -> str:
    return f"{value:+.2f}%" if value is not None else "n/a"


def _fmt_rate(value: Optional[float]) -> str:
    return f"{value:.0%}" if value is not None else "n/a"
