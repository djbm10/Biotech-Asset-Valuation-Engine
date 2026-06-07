"""
ReplaySignificance — statistical graduation tests for replay runs.

Computes cluster-robust standard errors (grouped by asset_id) and a
percentile bootstrap confidence interval to assess whether a replay
run's mean excess return is statistically distinguishable from zero.

Cameron–Miller (2015) cluster sandwich estimator for one-sample mean:

    V_CR = (G / (G-1)) * (1/n²) * Σ_g  (Σ_{i∈g} (r_i − r̄))²

where G = number of clusters, n = total observations, r_i = return on
trade i, r̄ = overall mean return.

Bootstrap uses cluster-level resampling: G clusters are drawn with
replacement in each of B iterations.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class SignificanceResult:
    """Full output of one significance analysis run."""

    run_id: str
    n: int                          # total closed decisions
    n_clusters: int                 # unique asset_ids (clusters)
    mean_return: float              # mean return % across all decisions
    std_return: float               # sample standard deviation of returns
    naive_se: float                 # std / sqrt(n)
    naive_t: float                  # mean / naive_se
    naive_p: float                  # two-sided p from N(0,1) approximation
    cluster_se: float               # Cameron-Miller cluster-robust SE
    cluster_t: float                # mean / cluster_se
    cluster_df: int                 # degrees of freedom = G - 1
    cluster_p: float                # two-sided p from t(G-1) distribution
    bootstrap_ci_90: tuple[float, float]    # (p5, p95)
    bootstrap_ci_95: tuple[float, float]    # (p2.5, p97.5)
    bootstrap_p: float              # fraction of bootstrap samples with mean ≤ 0
    alpha_survives_clustering: bool # cluster_t > 1.645 (one-sided p<0.10)
    bootstrap_ci_excludes_zero_90: bool    # lower bound of 90% CI > 0
    graduated: bool                 # both criteria pass
    cluster_by: str = "asset_id"    # asset_id | asset_catalyst


def analyze(
    decisions: list[dict],
    run_id: str = "",
    bootstrap_samples: int = 2000,
    seed: int = 42,
    cluster_by: str = "asset_id",
    return_field: str = "return_pct",
) -> SignificanceResult:
    """
    Run all graduation significance tests on a list of closed decisions.

    Parameters
    ----------
    decisions:
        List of dicts with at least ``asset_id`` and a return field. Only rows
        with a non-None return are used.
    run_id:
        Optional identifier included in the result for traceability.
    bootstrap_samples:
        Number of bootstrap iterations (default 2000).
    seed:
        RNG seed for reproducibility.

    Returns
    -------
    SignificanceResult
    """
    # Filter to rows with a return
    valid = [d for d in decisions if d.get(return_field) is not None]
    if not valid:
        raise ValueError(f"No decisions with {return_field} to analyze")

    n = len(valid)
    returns = [float(d[return_field]) for d in valid]
    cluster_ids = [_cluster_id(d, cluster_by) for d in valid]

    # ── Descriptive stats ──────────────────────────────────────────────
    mean_r = sum(returns) / n
    variance = sum((r - mean_r) ** 2 for r in returns) / (n - 1) if n > 1 else 0.0
    std_r = math.sqrt(variance) if variance > 0 else 0.0
    naive_se = std_r / math.sqrt(n)
    naive_t = mean_r / naive_se if naive_se > 0 else 0.0
    naive_p = _two_sided_normal_p(naive_t)

    # ── Cluster-robust SE (Cameron-Miller sandwich) ─────────────────────
    # Group residuals by requested cluster id
    clusters: dict[str, list[float]] = {}
    for cid, r in zip(cluster_ids, returns):
        clusters.setdefault(cid, []).append(r - mean_r)

    G = len(clusters)
    # B_hat = Σ_g (sum of residuals in cluster g)²
    b_hat = sum(
        (sum(resids)) ** 2 for resids in clusters.values()
    )
    # V_CR = (G/(G-1)) * (1/n²) * B_hat
    v_cr = (G / (G - 1)) * (1 / (n ** 2)) * b_hat if G > 1 else 0.0
    cluster_se = math.sqrt(v_cr) if v_cr > 0 else 0.0
    cluster_t = mean_r / cluster_se if cluster_se > 0 else 0.0
    cluster_df = max(G - 1, 0)
    cluster_p = _two_sided_t_p(cluster_t, df=cluster_df) if cluster_df > 0 else 1.0

    # ── Bootstrap (cluster-level resampling) ───────────────────────────
    rng = random.Random(seed)
    cluster_list = list(clusters.keys())
    # Map cluster → original returns (not residuals, raw returns)
    cluster_returns: dict[str, list[float]] = {}
    for cid, r in zip(cluster_ids, returns):
        cluster_returns.setdefault(cid, []).append(r)

    bootstrap_means: list[float] = []
    for _ in range(bootstrap_samples):
        # Draw G clusters with replacement
        drawn = [rng.choice(cluster_list) for _ in range(max(G, 1))]
        sample = []
        for cid in drawn:
            sample.extend(cluster_returns[cid])
        boot_mean = sum(sample) / len(sample) if sample else 0.0
        bootstrap_means.append(boot_mean)

    bootstrap_means.sort()
    b = len(bootstrap_means)
    ci_90 = (bootstrap_means[int(0.05 * b)], bootstrap_means[int(0.95 * b)])
    ci_95 = (bootstrap_means[int(0.025 * b)], bootstrap_means[int(0.975 * b)])
    boot_p = sum(1 for m in bootstrap_means if m <= 0) / b

    alpha_survives = cluster_t > 1.645
    ci_excludes_zero_90 = ci_90[0] > 0.0
    graduated = alpha_survives and ci_excludes_zero_90

    return SignificanceResult(
        run_id=run_id,
        n=n,
        n_clusters=G,
        cluster_by=cluster_by,
        mean_return=round(mean_r, 4),
        std_return=round(std_r, 4),
        naive_se=round(naive_se, 4),
        naive_t=round(naive_t, 4),
        naive_p=round(naive_p, 4),
        cluster_se=round(cluster_se, 4),
        cluster_t=round(cluster_t, 4),
        cluster_df=cluster_df,
        cluster_p=round(cluster_p, 4),
        bootstrap_ci_90=ci_90,
        bootstrap_ci_95=ci_95,
        bootstrap_p=round(boot_p, 4),
        alpha_survives_clustering=alpha_survives,
        bootstrap_ci_excludes_zero_90=ci_excludes_zero_90,
        graduated=graduated,
    )


def print_report(result: SignificanceResult) -> None:
    """Print a formatted significance report to stdout."""
    status = "✓ GRADUATED" if result.graduated else "✗ NOT YET"
    print("=" * 60)
    print(f"SIGNIFICANCE REPORT — run {result.run_id[:8]}...")
    print("=" * 60)
    print(f"  N decisions  : {result.n}")
    print(f"  N clusters   : {result.n_clusters} ({result.cluster_by})")
    print(f"  Mean return  : {result.mean_return:+.2f}%")
    print(f"  Std return   : {result.std_return:.2f}%")
    print()
    print("  ── Naive (no clustering) ──────────────────────────────")
    print(f"  SE           : {result.naive_se:.4f}%")
    print(f"  t-stat       : {result.naive_t:.2f}")
    print(f"  p (two-sided): {result.naive_p:.4f}")
    print()
    print("  ── Cluster-robust (Cameron-Miller, G={}) ────────────".format(
        result.n_clusters
    ))
    print(f"  SE           : {result.cluster_se:.4f}%")
    print(f"  t-stat       : {result.cluster_t:.2f}  (df={result.cluster_df})")
    print(f"  p (two-sided): {result.cluster_p:.4f}")
    print(f"  α survives   : {'YES ✓' if result.alpha_survives_clustering else 'NO ✗'}  "
          f"(cluster_t > 1.645)")
    print()
    print("  ── Bootstrap (cluster-level, B=2000) ─────────────────")
    ci90 = result.bootstrap_ci_90
    ci95 = result.bootstrap_ci_95
    print(f"  90% CI       : [{ci90[0]:+.2f}%, {ci90[1]:+.2f}%]")
    print(f"  95% CI       : [{ci95[0]:+.2f}%, {ci95[1]:+.2f}%]")
    print(f"  Bootstrap p  : {result.bootstrap_p:.4f}  (fraction ≤ 0)")
    print(f"  CI excl. 0   : {'YES ✓' if result.bootstrap_ci_excludes_zero_90 else 'NO ✗'}  "
          f"(90% lower > 0)")
    print()
    print(f"  Graduation   : {status}")
    print("=" * 60)


@dataclass
class PermutationResult:
    n: int
    observed_score_return_corr: float
    permutation_p: float
    n_permutations: int
    percentile_vs_random: float
    skill_in_ranking: bool


def permutation_test(
    decisions: list[dict],
    n_permutations: int = 5000,
    seed: int = 42,
) -> PermutationResult:
    """Test whether composite_score rank-orders returns better than random."""
    valid = [
        d for d in decisions
        if d.get("composite_score") is not None and d.get("return_pct") is not None
    ]
    if len(valid) < 15:
        raise ValueError("permutation_test requires at least 15 scored decisions")
    scores = [float(d["composite_score"]) for d in valid]
    returns = [float(d["return_pct"]) for d in valid]
    observed = _pearson(scores, returns)
    rng = random.Random(seed)
    permuted: list[float] = []
    shuffled = list(scores)
    for _ in range(n_permutations):
        rng.shuffle(shuffled)
        permuted.append(_pearson(shuffled, returns))
    extreme = sum(1 for value in permuted if abs(value) >= abs(observed))
    p_value = extreme / n_permutations
    percentile = sum(1 for value in permuted if value <= observed) / n_permutations
    return PermutationResult(
        n=len(valid),
        observed_score_return_corr=round(observed, 4),
        permutation_p=round(p_value, 4),
        n_permutations=n_permutations,
        percentile_vs_random=round(percentile, 4),
        skill_in_ranking=p_value < 0.10,
    )


def print_permutation_report(result: PermutationResult) -> None:
    print("=" * 60)
    print("PERMUTATION TEST — score/return ranking")
    print("=" * 60)
    print(f"  N decisions        : {result.n}")
    print(f"  Observed Pearson r : {result.observed_score_return_corr:+.3f}")
    print(f"  Permutation p      : {result.permutation_p:.4f}")
    print(f"  Percentile         : {result.percentile_vs_random:.1%}")
    print(f"  Ranking skill      : {'YES' if result.skill_in_ranking else 'NO'}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Statistical helpers (no external dependencies)
# ---------------------------------------------------------------------------

def _two_sided_normal_p(t: float) -> float:
    """Two-sided p-value from standard normal (large-sample approximation)."""
    # Rational approximation to erfc (Abramowitz & Stegun 7.1.26, max error 1.5e-7)
    a = abs(t) / math.sqrt(2)
    p = _erfc_approx(a)
    return min(2.0 * p, 1.0)


def _two_sided_t_p(t: float, df: int) -> float:
    """
    Two-sided p-value from Student's t distribution.

    Uses scipy if available; falls back to a normal approximation for large df.
    """
    try:
        from scipy.stats import t as t_dist
        return float(t_dist.sf(abs(t), df=df) * 2)
    except ImportError:
        # Fallback: for df ≥ 5, t approaches normal; use normal approx
        return _two_sided_normal_p(t)


def _cluster_id(decision: dict, cluster_by: str) -> str:
    asset_id = str(decision.get("asset_id") or decision.get("ticker") or "unknown")
    if cluster_by == "asset_catalyst":
        catalyst = decision.get("catalyst_event_id") or decision.get("decision_cluster_id")
        if catalyst:
            return f"{asset_id}:{catalyst}"
    return asset_id


def _pearson(xs: list[float], ys: list[float]) -> float:
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    cov = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    var_x = sum((x - x_mean) ** 2 for x in xs)
    var_y = sum((y - y_mean) ** 2 for y in ys)
    denom = math.sqrt(var_x * var_y)
    return cov / denom if denom > 0 else 0.0


def _erfc_approx(x: float) -> float:
    """Complementary error function approximation (erfc(x)/2 ≈ P(Z > x√2))."""
    # Using scipy if available for accuracy
    try:
        import math
        return math.erfc(x) / 2.0
    except Exception:
        # Horner form rational approximation
        t_ = 1.0 / (1.0 + 0.3275911 * x)
        poly = t_ * (0.254829592 + t_ * (-0.284496736 + t_ * (
            1.421413741 + t_ * (-1.453152027 + t_ * 1.061405429)
        )))
        return poly * math.exp(-(x * x))
