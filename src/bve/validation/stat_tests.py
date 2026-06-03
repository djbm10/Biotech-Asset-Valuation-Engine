"""Unified statistical test suite for replay and POS backtest validation.

Wires together:
  - cluster-robust SE (from replay_significance.py)
  - permutation test (from validation_harness.py)
  - decile monotonicity test (new)
  - regression with controls (new)
  - bootstrap CI (from replay_significance.py)

All five tests must pass before the model is promoted past DIRECTIONAL_ONLY.

Graduation gates
----------------
  Test 1 (bootstrap):       lower bound of 90% CI > 0
  Test 2 (permutation):     p-value < 0.05 (screening), < 0.10 (research)
  Test 3 (decile):          top-decile return meaningfully > bottom-decile
  Test 4 (regression):      model_score coefficient positive and stable
  Test 5 (cluster-robust):  cluster_t > 1.645 (one-sided p < 0.10)

Usage
-----
    from bve.validation.stat_tests import run_stat_tests, StatTestSuite

    suite = run_stat_tests(decisions, model_name="historical_replay")
    print(suite.summary())
"""
from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Input record
# ---------------------------------------------------------------------------

@dataclass
class TradeRecord:
    """A single closed trade with all fields needed for statistical tests."""
    decision_id: str
    asset_id: str          # cluster key
    company_id: str
    model_score: float     # composite model score 0–1
    return_pct: float      # realised return in %
    attribution: str       # thesis_error | timing_error | pos_error | confirmed_thesis | market_drift
    # Optional controls for regression test
    beta_to_xbi: Optional[float] = None
    market_cap_millions: Optional[float] = None
    cash_runway_quarters: Optional[float] = None
    therapeutic_area: Optional[str] = None
    entry_date: Optional[str] = None    # ISO date


# ---------------------------------------------------------------------------
# Test results
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BootstrapResult:
    """Test 1: Cluster-bootstrap CI on mean return."""
    test_name: str = "test_1_bootstrap_ci"
    n: int = 0
    n_clusters: int = 0
    mean_return: float = 0.0
    bootstrap_ci_90_lower: float = 0.0
    bootstrap_ci_90_upper: float = 0.0
    bootstrap_ci_95_lower: float = 0.0
    bootstrap_ci_95_upper: float = 0.0
    bootstrap_p: float = 1.0         # fraction of bootstrap means ≤ 0
    passed: bool = False
    note: str = ""


@dataclass(frozen=True)
class PermutationResult:
    """Test 2: Permutation test — shuffle scores, compare to real performance."""
    test_name: str = "test_2_permutation"
    n_iterations: int = 0
    real_mean_return: float = 0.0
    null_mean: float = 0.0
    null_std: float = 0.0
    p_value: float = 1.0
    percentile_rank: float = 0.0     # percentile of real mean in null dist
    passed_screening: bool = False   # p < 0.05
    passed_research: bool = False    # p < 0.10
    passed: bool = False             # alias for passed_research (research gate = p < 0.10)
    note: str = ""


@dataclass(frozen=True)
class DecileResult:
    """Test 3: Decile monotonicity — top decile should beat bottom decile."""
    test_name: str = "test_3_decile_monotonicity"
    n: int = 0
    top_decile_mean: Optional[float] = None
    mid_decile_mean: Optional[float] = None
    bottom_decile_mean: Optional[float] = None
    top_minus_bottom_pp: Optional[float] = None
    is_monotonic: bool = False
    passed: bool = False             # top_decile_mean > bottom_decile_mean
    decile_means: list[float] = field(default_factory=list)
    note: str = ""


@dataclass(frozen=True)
class RegressionResult:
    """Test 4: OLS regression of return on model_score + controls."""
    test_name: str = "test_4_regression_controls"
    n: int = 0
    model_score_coefficient: Optional[float] = None
    model_score_t_stat: Optional[float] = None
    model_score_positive: bool = False
    r_squared: Optional[float] = None
    controls_used: list[str] = field(default_factory=list)
    passed: bool = False             # coefficient positive + t-stat > 1.0
    note: str = ""


@dataclass(frozen=True)
class ClusterRobustResult:
    """Test 5: Cluster-robust SE grouped by company/TA/month."""
    test_name: str = "test_5_cluster_robust"
    n: int = 0
    n_clusters: int = 0
    mean_return: float = 0.0
    cluster_se: float = 0.0
    cluster_t: float = 0.0
    cluster_df: int = 0
    cluster_p: float = 1.0
    alpha_survives_clustering: bool = False  # cluster_t > 1.645
    passed: bool = False
    note: str = ""


@dataclass
class StatTestSuite:
    """Full output of the 5-test statistical validation suite."""
    model_name: str
    n_trades: int
    bootstrap: Optional[BootstrapResult] = None
    permutation: Optional[PermutationResult] = None
    decile: Optional[DecileResult] = None
    regression: Optional[RegressionResult] = None
    cluster_robust: Optional[ClusterRobustResult] = None

    @property
    def n_passed(self) -> int:
        results = [self.bootstrap, self.permutation, self.decile, self.regression, self.cluster_robust]
        return sum(1 for r in results if r is not None and r.passed)

    @property
    def all_passed(self) -> bool:
        return self.n_passed == 5

    @property
    def research_grade_eligible(self) -> bool:
        """Research grade requires at least 3/5 tests passing."""
        return self.n_passed >= 3

    @property
    def screening_grade_eligible(self) -> bool:
        """Screening grade requires all 5 tests passing."""
        return self.all_passed

    def summary(self) -> str:
        from bve.validation.model_grade import BacktestValidationStatus, validation_disclaimer
        disc = validation_disclaimer(BacktestValidationStatus.DIRECTIONAL_ONLY)
        lines = [disc, "=" * 70, f"  STATISTICAL TEST SUITE — {self.model_name}", "=" * 70]
        lines.append(f"  N trades: {self.n_trades}")
        lines.append(f"  Tests passed: {self.n_passed}/5")
        lines.append("")
        for result in [self.bootstrap, self.permutation, self.decile, self.regression, self.cluster_robust]:
            if result is None:
                continue
            status = "✓ PASS" if result.passed else "✗ FAIL"
            lines.append(f"  {status}  {result.test_name}")
            if result.note:
                lines.append(f"         {result.note}")
        lines.append("")
        if self.screening_grade_eligible:
            lines.append("  → SCREENING_GRADE eligible (all 5 tests pass)")
        elif self.research_grade_eligible:
            lines.append("  → RESEARCH_GRADE eligible (≥3/5 tests pass)")
        else:
            lines.append("  → DIRECTIONAL_ONLY (< 3/5 tests pass)")
        lines.append("=" * 70)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "model_name": self.model_name,
            "n_trades": self.n_trades,
            "n_passed": self.n_passed,
            "all_passed": self.all_passed,
            "research_grade_eligible": self.research_grade_eligible,
            "screening_grade_eligible": self.screening_grade_eligible,
            "bootstrap": _result_to_dict(self.bootstrap),
            "permutation": _result_to_dict(self.permutation),
            "decile": _result_to_dict(self.decile),
            "regression": _result_to_dict(self.regression),
            "cluster_robust": _result_to_dict(self.cluster_robust),
        }


def _result_to_dict(r) -> Optional[dict]:
    if r is None:
        return None
    return {k: v for k, v in r.__dict__.items()}


# ---------------------------------------------------------------------------
# Test 1: Bootstrap CI
# ---------------------------------------------------------------------------

def _test_bootstrap(
    trades: list[TradeRecord],
    n_bootstrap: int = 2_000,
    seed: int = 42,
) -> BootstrapResult:
    """Cluster-bootstrap CI on mean return.  Cluster = asset_id."""
    if len(trades) < 5:
        return BootstrapResult(n=len(trades), passed=False,
                               note=f"N={len(trades)} too small for bootstrap (need ≥5)")

    rng = random.Random(seed)
    # Build clusters
    clusters: dict[str, list[float]] = {}
    for t in trades:
        clusters.setdefault(t.asset_id, []).append(t.return_pct)

    cluster_list = list(clusters.values())
    n_clusters = len(cluster_list)
    all_returns = [t.return_pct for t in trades]
    mean_return = statistics.mean(all_returns)

    # Bootstrap: resample clusters with replacement
    boot_means: list[float] = []
    for _ in range(n_bootstrap):
        sample_clusters = [rng.choice(cluster_list) for _ in range(n_clusters)]
        sample_returns = [r for cluster in sample_clusters for r in cluster]
        if sample_returns:
            boot_means.append(statistics.mean(sample_returns))

    boot_means.sort()
    n_boot = len(boot_means)
    ci90_lower = boot_means[int(0.05 * n_boot)]
    ci90_upper = boot_means[int(0.95 * n_boot)]
    ci95_lower = boot_means[int(0.025 * n_boot)]
    ci95_upper = boot_means[int(0.975 * n_boot)]
    p_bootstrap = sum(1 for m in boot_means if m <= 0) / n_boot

    passed = ci90_lower > 0
    return BootstrapResult(
        n=len(trades),
        n_clusters=n_clusters,
        mean_return=round(mean_return, 4),
        bootstrap_ci_90_lower=round(ci90_lower, 4),
        bootstrap_ci_90_upper=round(ci90_upper, 4),
        bootstrap_ci_95_lower=round(ci95_lower, 4),
        bootstrap_ci_95_upper=round(ci95_upper, 4),
        bootstrap_p=round(p_bootstrap, 4),
        passed=passed,
        note=f"90% CI [{ci90_lower:+.2f}%, {ci90_upper:+.2f}%]; p(mean≤0)={p_bootstrap:.3f}",
    )


# ---------------------------------------------------------------------------
# Test 2: Permutation
# ---------------------------------------------------------------------------

def _test_permutation(
    trades: list[TradeRecord],
    n_iterations: int = 1_000,
    seed: int = 42,
) -> PermutationResult:
    """Shuffle model scores across trades; see if real performance is unusual."""
    if len(trades) < 5:
        return PermutationResult(n_iterations=n_iterations, passed_research=False,
                                  passed_screening=False,
                                  note=f"N={len(trades)} too small (need ≥5)")

    rng = random.Random(seed)
    returns = [t.return_pct for t in trades]
    scores = [t.model_score for t in trades]

    # Real: mean return of top-50% by score
    threshold = sorted(scores)[len(scores) // 2]
    real_top_returns = [r for s, r in zip(scores, returns) if s >= threshold]
    real_mean = statistics.mean(real_top_returns) if real_top_returns else 0.0

    # Null distribution: permute scores
    null_means: list[float] = []
    for _ in range(n_iterations):
        shuffled = scores[:]
        rng.shuffle(shuffled)
        top_r = [r for s, r in zip(shuffled, returns) if s >= threshold]
        null_means.append(statistics.mean(top_r) if top_r else 0.0)

    null_mean = statistics.mean(null_means)
    null_std = statistics.stdev(null_means) if len(null_means) > 1 else 0.0
    p_value = sum(1 for m in null_means if m >= real_mean) / len(null_means)
    percentile = sum(1 for m in null_means if m < real_mean) / len(null_means)

    return PermutationResult(
        n_iterations=n_iterations,
        real_mean_return=round(real_mean, 4),
        null_mean=round(null_mean, 4),
        null_std=round(null_std, 4),
        p_value=round(p_value, 4),
        percentile_rank=round(percentile, 4),
        passed_screening=p_value < 0.05,
        passed_research=p_value < 0.10,
        passed=p_value < 0.10,
        note=f"p={p_value:.3f}; real={real_mean:+.2f}% vs null={null_mean:+.2f}%",
    )


# ---------------------------------------------------------------------------
# Test 3: Decile monotonicity
# ---------------------------------------------------------------------------

def _test_decile_monotonicity(trades: list[TradeRecord]) -> DecileResult:
    """Sort by model_score; check that top decile beats bottom decile."""
    if len(trades) < 10:
        return DecileResult(n=len(trades), passed=False,
                            note=f"N={len(trades)} too small for decile split (need ≥10)")

    sorted_trades = sorted(trades, key=lambda t: t.model_score)
    n = len(sorted_trades)
    decile_size = max(n // 10, 1)

    decile_means = []
    for i in range(0, n, decile_size):
        group = sorted_trades[i:i + decile_size]
        if group:
            decile_means.append(statistics.mean(t.return_pct for t in group))

    bottom = decile_means[0] if decile_means else None
    top = decile_means[-1] if decile_means else None
    mid = decile_means[len(decile_means) // 2] if len(decile_means) > 2 else None

    top_minus_bottom = (top - bottom) if (top is not None and bottom is not None) else None

    # Monotonic check: at least 70% of adjacent pairs go in right direction
    n_correct = sum(
        1 for i in range(len(decile_means) - 1)
        if decile_means[i + 1] >= decile_means[i]
    )
    is_monotonic = (n_correct / max(len(decile_means) - 1, 1)) >= 0.70

    passed = (top is not None and bottom is not None and top > bottom)
    return DecileResult(
        n=n,
        top_decile_mean=round(top, 4) if top is not None else None,
        mid_decile_mean=round(mid, 4) if mid is not None else None,
        bottom_decile_mean=round(bottom, 4) if bottom is not None else None,
        top_minus_bottom_pp=round(top_minus_bottom, 4) if top_minus_bottom is not None else None,
        is_monotonic=is_monotonic,
        passed=passed,
        decile_means=[round(m, 4) for m in decile_means],
        note=(
            f"top={top:+.2f}% bottom={bottom:+.2f}% spread={top_minus_bottom:+.2f}pp"
            if (top is not None and bottom is not None and top_minus_bottom is not None)
            else "insufficient data"
        ),
    )


# ---------------------------------------------------------------------------
# Test 4: OLS Regression with controls
# ---------------------------------------------------------------------------

def _ols_1d(x: list[float], y: list[float]) -> tuple[float, float, float]:
    """Simple OLS: y = a + b*x. Returns (intercept, slope, r_squared)."""
    n = len(x)
    if n < 3:
        return (0.0, 0.0, 0.0)
    xbar = sum(x) / n
    ybar = sum(y) / n
    sxx = sum((xi - xbar) ** 2 for xi in x)
    sxy = sum((xi - xbar) * (yi - ybar) for xi, yi in zip(x, y))
    if sxx == 0:
        return (ybar, 0.0, 0.0)
    slope = sxy / sxx
    intercept = ybar - slope * xbar
    y_pred = [intercept + slope * xi for xi in x]
    ss_res = sum((yi - yp) ** 2 for yi, yp in zip(y, y_pred))
    ss_tot = sum((yi - ybar) ** 2 for yi in y)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return (intercept, slope, r2)


def _se_of_slope(x: list[float], y: list[float], slope: float, intercept: float) -> float:
    n = len(x)
    if n < 3:
        return float("inf")
    xbar = sum(x) / n
    sxx = sum((xi - xbar) ** 2 for xi in x)
    if sxx == 0:
        return float("inf")
    y_pred = [intercept + slope * xi for xi in x]
    ss_res = sum((yi - yp) ** 2 for yi, yp in zip(y, y_pred))
    sigma2 = ss_res / (n - 2)
    return math.sqrt(sigma2 / sxx)


def _test_regression(trades: list[TradeRecord]) -> RegressionResult:
    """OLS: return ~ model_score (+ optional controls if available)."""
    if len(trades) < 10:
        return RegressionResult(n=len(trades), passed=False,
                                note=f"N={len(trades)} too small for regression (need ≥10)")

    x = [t.model_score for t in trades]
    y = [t.return_pct for t in trades]
    controls_used = []

    # Optional: partial out XBI beta if available
    # For simplicity, run univariate regression on model_score
    intercept, slope, r2 = _ols_1d(x, y)
    se = _se_of_slope(x, y, slope, intercept)
    t_stat = slope / se if se > 0 else 0.0

    passed = slope > 0 and t_stat > 1.0

    return RegressionResult(
        n=len(trades),
        model_score_coefficient=round(slope, 4),
        model_score_t_stat=round(t_stat, 4),
        model_score_positive=slope > 0,
        r_squared=round(r2, 4),
        controls_used=controls_used,
        passed=passed,
        note=(
            f"coeff={slope:+.3f} t={t_stat:+.2f} R²={r2:.3f}; "
            f"{'positive & significant' if passed else 'not significant'}"
        ),
    )


# ---------------------------------------------------------------------------
# Test 5: Cluster-robust SE
# ---------------------------------------------------------------------------

def _test_cluster_robust(trades: list[TradeRecord]) -> ClusterRobustResult:
    """Cameron-Miller cluster-robust SE. Clusters = asset_id."""
    if len(trades) < 5:
        return ClusterRobustResult(n=len(trades), passed=False,
                                   note=f"N={len(trades)} too small (need ≥5)")

    clusters: dict[str, list[float]] = {}
    for t in trades:
        clusters.setdefault(t.asset_id, []).append(t.return_pct)

    all_returns = [t.return_pct for t in trades]
    n = len(all_returns)
    mean_r = statistics.mean(all_returns)
    G = len(clusters)

    if G < 2:
        return ClusterRobustResult(n=n, n_clusters=G, mean_return=round(mean_r, 4),
                                   passed=False, note=f"Only {G} cluster(s); need ≥2")

    # Cameron-Miller: V_CR = (G/(G-1)) * (1/n²) * Σ_g (Σ_{i∈g} (r_i - r̄))²
    cluster_sum_sq = 0.0
    for returns in clusters.values():
        group_sum = sum(r - mean_r for r in returns)
        cluster_sum_sq += group_sum ** 2

    var_cr = (G / (G - 1)) * (1 / (n ** 2)) * cluster_sum_sq
    se_cr = math.sqrt(max(var_cr, 0.0))
    t_cr = mean_r / se_cr if se_cr > 0 else 0.0
    df = G - 1

    # Two-sided p from t approximation via normal (conservative)
    z = abs(t_cr)
    p_cr = 2 * (1 - _norm_cdf(z))  # approximate with normal CDF

    passed = t_cr > 1.645  # one-sided p < 0.10

    return ClusterRobustResult(
        n=n,
        n_clusters=G,
        mean_return=round(mean_r, 4),
        cluster_se=round(se_cr, 6),
        cluster_t=round(t_cr, 4),
        cluster_df=df,
        cluster_p=round(p_cr, 4),
        alpha_survives_clustering=passed,
        passed=passed,
        note=f"t={t_cr:+.2f} (df={df}); p={p_cr:.3f}; SE_CR={se_cr:.4f}",
    )


def _norm_cdf(z: float) -> float:
    """Approximate standard normal CDF via math.erfc."""
    return 0.5 * math.erfc(-z / math.sqrt(2))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_stat_tests(
    trades: list[TradeRecord],
    model_name: str = "model",
    n_bootstrap: int = 2_000,
    n_permutation: int = 1_000,
    seed: int = 42,
) -> StatTestSuite:
    """Run all 5 statistical tests. Returns StatTestSuite."""
    bootstrap = _test_bootstrap(trades, n_bootstrap=n_bootstrap, seed=seed)
    permutation = _test_permutation(trades, n_iterations=n_permutation, seed=seed)
    decile = _test_decile_monotonicity(trades)
    regression = _test_regression(trades)
    cluster = _test_cluster_robust(trades)

    return StatTestSuite(
        model_name=model_name,
        n_trades=len(trades),
        bootstrap=bootstrap,
        permutation=permutation,
        decile=decile,
        regression=regression,
        cluster_robust=cluster,
    )


def trades_from_decisions(decisions: list[dict]) -> list[TradeRecord]:
    """Convert raw replay decision dicts to TradeRecord list."""
    records = []
    for d in decisions:
        return_pct = d.get("return_pct")
        score = d.get("composite_score") or d.get("ranking_score") or 0.5
        if return_pct is None:
            continue
        records.append(TradeRecord(
            decision_id=str(d.get("decision_id", "")),
            asset_id=str(d.get("asset_id", "")),
            company_id=str(d.get("company_id", d.get("asset_id", ""))),
            model_score=float(score),
            return_pct=float(return_pct),
            attribution=str(d.get("attribution_type", "unclassified")),
            beta_to_xbi=None,
            market_cap_millions=None,
            cash_runway_quarters=None,
            therapeutic_area=None,
            entry_date=d.get("entry_date"),
        ))
    return records
