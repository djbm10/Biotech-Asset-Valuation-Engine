"""
Deal premium estimation: predict EV/peak-sales range for a new acquisition target.

Uses comparables from research/mna/comparable_deals.yaml to find the K most
similar closed deals by phase, therapeutic area, and urgency tier, then reports
the median, P25, P75 of their EV/peak-sales multiples as a valuation anchor.

Also provides a simple OLS regression (log ev_to_peak_sales ~ phase_score +
ta_specificity + urgency_score) for a continuous point estimate.

Usage:
    from bve.analysis.deal_premium import DealPremiumEngine
    engine = DealPremiumEngine.from_default()
    est = engine.estimate(
        phase="phase_2",
        therapeutic_area="immunology",
        acquirer_fit_score=0.975,
        peak_sales_millions=2000,
    )
    print(est)
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

# ---------------------------------------------------------------------------
# Phase encoding
# ---------------------------------------------------------------------------

_PHASE_SCORE: dict[str, float] = {
    "phase_1": 0.5,
    "phase_1b": 0.5,
    "phase_1b_phase_2": 0.75,
    "phase_1_phase_2": 0.75,
    "phase_2": 1.0,
    "phase_2_phase_3": 1.5,
    "phase_2b": 1.0,
    "phase_2b_phase_3": 1.5,
    "phase_3": 2.0,
    "nda_bla": 2.5,
    "pivotal": 2.0,
    "approved": 3.0,
}

_TA_SPECIFICITY: dict[str, float] = {
    # How "proprietary / hard to replicate" the indication type is.
    # Higher → buyer has fewer alternatives → higher premium.
    "rare_disease": 0.9,
    "rare disease": 0.9,
    "ophthalmology": 0.85,
    "neuroscience": 0.80,
    "hematology": 0.75,
    "hepatology": 0.70,
    "cardiovascular": 0.65,
    "immunology": 0.60,
    "respiratory": 0.55,
    "oncology": 0.50,
    "nephrology": 0.70,
    "endocrinology": 0.55,
    "dermatology": 0.55,
    "metabolic": 0.50,
    "infectious disease": 0.45,
}

_DEFAULT_TA_SPECIFICITY = 0.55


def _ta_specificity(ta: str) -> float:
    return _TA_SPECIFICITY.get(ta.lower().strip(), _DEFAULT_TA_SPECIFICITY)


def _phase_score(phase: str) -> float:
    return _PHASE_SCORE.get(phase.lower().strip(), 1.0)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class ComparableDeal:
    """One deal record loaded from comparable_deals.yaml."""
    target_name: str
    indication: str
    therapeutic_area: str
    phase: str
    acquirer: str
    deal_date: str
    ev_to_peak_sales: float
    enterprise_value_millions: Optional[float]
    peak_sales_millions: Optional[float]
    data_quality: str
    deal_structure: str

    @property
    def phase_score(self) -> float:
        return _phase_score(self.phase)

    @property
    def ta_specificity(self) -> float:
        return _ta_specificity(self.therapeutic_area)


@dataclass
class DealPremiumEstimate:
    """EV/peak-sales range estimate for a target asset."""
    phase: str
    therapeutic_area: str
    acquirer_fit_score: float

    # Core output: EV/peak-sales multiples
    ev_to_peak_sales_p25: float
    ev_to_peak_sales_median: float
    ev_to_peak_sales_p75: float

    # Regression point estimate (log-linear model)
    ev_to_peak_sales_regression: float

    # Blended estimate = 0.5×median + 0.5×regression
    ev_to_peak_sales_blended: float

    # Implied EV range (when peak_sales_millions provided)
    implied_ev_p25_millions: Optional[float] = None
    implied_ev_median_millions: Optional[float] = None
    implied_ev_p75_millions: Optional[float] = None
    implied_ev_blended_millions: Optional[float] = None

    # Premium tier classification
    premium_tier: str = "market_rate"   # "strategic_premium" | "market_rate" | "below_market"

    # Most similar comparables used
    comparables: list[str] = field(default_factory=list)
    n_comparables: int = 0

    def __str__(self) -> str:
        lines = [
            f"DealPremiumEstimate({self.phase} / {self.therapeutic_area})",
            f"  EV/peak-sales: P25={self.ev_to_peak_sales_p25:.2f}x  "
            f"median={self.ev_to_peak_sales_median:.2f}x  "
            f"P75={self.ev_to_peak_sales_p75:.2f}x",
            f"  Regression est: {self.ev_to_peak_sales_regression:.2f}x  "
            f"Blended: {self.ev_to_peak_sales_blended:.2f}x",
            f"  Premium tier: {self.premium_tier}",
        ]
        if self.implied_ev_blended_millions is not None:
            lines.append(
                f"  Implied EV: ${self.implied_ev_blended_millions:.0f}M "
                f"(range ${self.implied_ev_p25_millions:.0f}M – ${self.implied_ev_p75_millions:.0f}M)"
            )
        if self.comparables:
            lines.append(f"  Comparables ({self.n_comparables}): {', '.join(self.comparables[:3])}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Regression model (OLS on log scale — trained on load)
# ---------------------------------------------------------------------------

def _fit_log_linear(deals: list[ComparableDeal]) -> tuple[float, float, float, float]:
    """
    Fit: log(ev_to_peak_sales) = b0 + b1*phase_score + b2*ta_specificity + b3*urgency_score
    urgency_score is not in the comparable deals, so we use a neutral 0.5.

    Returns (b0, b1, b2, b3) via closed-form OLS (no scipy/numpy required).
    Falls back to intercept-only if < 5 observations.
    """
    n = len(deals)
    if n < 5:
        mean_log = statistics.mean(math.log(d.ev_to_peak_sales) for d in deals if d.ev_to_peak_sales > 0)
        return (mean_log, 0.0, 0.0, 0.0)

    # Build design matrix [1, phase_score, ta_specificity] and log(y)
    # Solving via normal equations X^T X b = X^T y

    def dot(a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b))

    rows = []
    ys = []
    for d in deals:
        if d.ev_to_peak_sales <= 0:
            continue
        rows.append([1.0, d.phase_score, d.ta_specificity, 0.5])  # urgency=0.5 (neutral)
        ys.append(math.log(d.ev_to_peak_sales))

    n = len(rows)
    k = 4  # intercept + 3 features

    # X^T X (k×k)
    XtX = [[sum(rows[i][a] * rows[i][b] for i in range(n)) for b in range(k)] for a in range(k)]
    # X^T y (k×1)
    Xty = [sum(rows[i][a] * ys[i] for i in range(n)) for a in range(k)]

    # Gaussian elimination (no numpy needed)
    def _solve(A: list[list[float]], b: list[float]) -> list[float]:
        n = len(b)
        M = [row[:] + [b[i]] for i, row in enumerate(A)]
        for col in range(n):
            pivot = max(range(col, n), key=lambda r: abs(M[r][col]))
            M[col], M[pivot] = M[pivot], M[col]
            if abs(M[col][col]) < 1e-12:
                continue
            for row in range(n):
                if row != col:
                    factor = M[row][col] / M[col][col]
                    M[row] = [M[row][j] - factor * M[col][j] for j in range(n + 1)]
        return [M[i][n] / M[i][i] if abs(M[i][i]) > 1e-12 else 0.0 for i in range(n)]

    try:
        coeffs = _solve(XtX, Xty)
        return tuple(coeffs)  # type: ignore[return-value]
    except Exception:
        mean_log = statistics.mean(ys)
        return (mean_log, 0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class DealPremiumEngine:
    """Estimate EV/peak-sales multiple for a new acquisition target."""

    def __init__(self, deals: list[ComparableDeal]) -> None:
        self._deals = deals
        self._coeffs = _fit_log_linear(deals)

    @classmethod
    def from_file(cls, path: Path) -> "DealPremiumEngine":
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        deals = []
        for record in raw.get("deals", []):
            ev_ps = record.get("ev_to_peak_sales")
            ev = record.get("enterprise_value_millions")
            ps = record.get("peak_sales_millions")
            if ev_ps is None and ev is not None and ps and ps > 0:
                ev_ps = round(ev / ps, 4)
            if ev_ps is None or ev_ps <= 0:
                continue
            deals.append(ComparableDeal(
                target_name=record.get("target_name", ""),
                indication=record.get("indication", ""),
                therapeutic_area=record.get("therapeutic_area", ""),
                phase=record.get("phase_at_acquisition", ""),
                acquirer=record.get("acquirer", ""),
                deal_date=str(record.get("deal_date", "")),
                ev_to_peak_sales=ev_ps,
                enterprise_value_millions=ev,
                peak_sales_millions=ps,
                data_quality=record.get("data_quality", "medium"),
                deal_structure=record.get("deal_structure", ""),
            ))
        return cls(deals)

    @classmethod
    def from_default(cls) -> "DealPremiumEngine":
        """Load from the project-default comparable_deals.yaml."""
        default_path = Path("research/mna/comparable_deals.yaml")
        if not default_path.exists():
            # Try relative to package root
            default_path = Path(__file__).parents[3] / "research/mna/comparable_deals.yaml"
        return cls.from_file(default_path)

    # ── Regression point estimate ────────────────────────────────────────────

    def _regression_estimate(
        self,
        phase: str,
        therapeutic_area: str,
        acquirer_fit_score: float,
    ) -> float:
        b0, b1, b2, b3 = self._coeffs
        ps = _phase_score(phase)
        ta = _ta_specificity(therapeutic_area)
        # Map fit_score [0,1] → urgency_score [0,1]
        urgency = min(max(acquirer_fit_score, 0.0), 1.0)
        log_ev_ps = b0 + b1 * ps + b2 * ta + b3 * urgency
        return round(math.exp(log_ev_ps), 3)

    # ── Comparable-based quantile estimate ───────────────────────────────────

    def _find_comparables(
        self,
        phase: str,
        therapeutic_area: str,
        *,
        k: int = 15,
        min_data_quality: str = "medium",
    ) -> list[ComparableDeal]:
        """Score each deal by similarity and return top-K."""
        _DQ_RANK = {"high": 3, "medium": 2, "low": 1}
        min_rank = _DQ_RANK.get(min_data_quality, 1)
        query_ps = _phase_score(phase)
        query_ta = _ta_specificity(therapeutic_area)
        query_ta_str = therapeutic_area.lower().strip()

        scored = []
        for d in self._deals:
            if _DQ_RANK.get(d.data_quality, 1) < min_rank:
                continue
            # Phase distance (0 = exact match)
            phase_dist = abs(d.phase_score - query_ps)
            # TA match: exact=0, same specificity tier=0.1, otherwise proportional distance
            ta_dist = abs(d.ta_specificity - query_ta)
            exact_ta = 0.0 if d.therapeutic_area.lower().strip() == query_ta_str else 0.15
            similarity = -(phase_dist * 0.6 + ta_dist * 0.3 + exact_ta * 0.1)
            scored.append((similarity, d))

        scored.sort(key=lambda x: -x[0])
        return [d for _, d in scored[:k]]

    # ── Main entry point ─────────────────────────────────────────────────────

    def estimate(
        self,
        *,
        phase: str,
        therapeutic_area: str,
        acquirer_fit_score: float = 0.5,
        peak_sales_millions: Optional[float] = None,
        k_comparables: int = 15,
        min_data_quality: str = "medium",
    ) -> DealPremiumEstimate:
        """
        Estimate EV/peak-sales range for an acquisition target.

        Parameters
        ----------
        phase : str
            Phase at time of acquisition (e.g., "phase_2", "phase_3", "approved").
        therapeutic_area : str
            Target therapeutic area (e.g., "immunology", "oncology", "rare_disease").
        acquirer_fit_score : float
            Acquirer-fit model score [0, 1]. Higher → more strategic urgency → higher premium.
        peak_sales_millions : float, optional
            Consensus/model peak sales estimate ($M). If provided, implied EV is computed.
        k_comparables : int
            Number of comparable deals to use for quantile estimation (default 15).
        min_data_quality : str
            Minimum data quality of comparables to include ("low"/"medium"/"high").
        """
        comps = self._find_comparables(
            phase, therapeutic_area,
            k=k_comparables, min_data_quality=min_data_quality,
        )
        if not comps:
            # Fallback: use all deals
            comps = self._deals

        vals = sorted(d.ev_to_peak_sales for d in comps)
        n = len(vals)
        p25 = vals[max(0, int(n * 0.25))]
        median = vals[n // 2]
        p75 = vals[min(n - 1, int(n * 0.75))]

        regression = self._regression_estimate(phase, therapeutic_area, acquirer_fit_score)
        blended = round((median + regression) / 2.0, 3)

        # Premium tier: top quartile of our 90-deal dataset → strategic premium
        all_vals = sorted(d.ev_to_peak_sales for d in self._deals)
        all_p25 = all_vals[len(all_vals) // 4]
        all_p75 = all_vals[len(all_vals) * 3 // 4]
        if blended >= all_p75:
            premium_tier = "strategic_premium"
        elif blended <= all_p25:
            premium_tier = "below_market"
        else:
            premium_tier = "market_rate"

        comp_names = [d.target_name for d in comps[:5]]

        implied_p25 = implied_med = implied_p75 = implied_blended = None
        if peak_sales_millions is not None and peak_sales_millions > 0:
            implied_p25 = round(p25 * peak_sales_millions)
            implied_med = round(median * peak_sales_millions)
            implied_p75 = round(p75 * peak_sales_millions)
            implied_blended = round(blended * peak_sales_millions)

        return DealPremiumEstimate(
            phase=phase,
            therapeutic_area=therapeutic_area,
            acquirer_fit_score=acquirer_fit_score,
            ev_to_peak_sales_p25=round(p25, 3),
            ev_to_peak_sales_median=round(median, 3),
            ev_to_peak_sales_p75=round(p75, 3),
            ev_to_peak_sales_regression=regression,
            ev_to_peak_sales_blended=blended,
            implied_ev_p25_millions=float(implied_p25) if implied_p25 else None,
            implied_ev_median_millions=float(implied_med) if implied_med else None,
            implied_ev_p75_millions=float(implied_p75) if implied_p75 else None,
            implied_ev_blended_millions=float(implied_blended) if implied_blended else None,
            premium_tier=premium_tier,
            comparables=comp_names,
            n_comparables=len(comps),
        )

    def phase_summary(self) -> dict[str, dict]:
        """Return median, P25, P75 of EV/peak-sales by phase (for inspection)."""
        by_phase: dict[str, list[float]] = {}
        for d in self._deals:
            by_phase.setdefault(d.phase, []).append(d.ev_to_peak_sales)
        result = {}
        for phase, vals in sorted(by_phase.items()):
            s = sorted(vals)
            n = len(s)
            result[phase] = {
                "n": n,
                "p25": round(s[max(0, n // 4)], 3),
                "median": round(s[n // 2], 3),
                "p75": round(s[min(n - 1, n * 3 // 4)], 3),
            }
        return result
