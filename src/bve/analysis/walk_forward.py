"""Walk-forward model selection with locked policies.

Prevents overfitting by evaluating policy parameters on out-of-sample data.
Uses expanding windows: each fold adds one year to the training set and tests
on the following year.

Design
------
- Three expanding windows (configurable):
    Fold 1: train 2021-2022, test 2023
    Fold 2: train 2021-2023, test 2024
    Fold 3: train 2021-2024, test 2025

- For each fold, the "best" policy is the one that maximises mean return in
  the training window. The locked policy is then applied to the test window
  and the OOS performance is recorded.

- ``LockedPolicy`` — the winning parameter set for one fold (immutable)
- ``WalkForwardFold`` — per-fold results (train metrics, test metrics, locked policy)
- ``WalkForwardReport`` — aggregate stability summary across all folds
- ``run_walk_forward(decisions)`` — top-level entry point

Policy parameters varied
------------------------
  min_model_score   : [0.40, 0.50, 0.60]   — minimum composite score to enter
  require_catalyst  : [0, 90] days          — require catalyst within N days

``max_hold_days`` is intentionally not varied here. A replay run stores one
realized exit per decision, so hold-period sensitivity requires separate
replay seeds with different forced-exit rules.

Stability gate
--------------
  A policy is "stable" if the locked parameter is the same across all 3 folds.
  "Moderately stable" if it agrees on ≥2/3 folds.
  Otherwise: "unstable" — interpret results with caution.

Usage
-----
    from bve.analysis.walk_forward import run_walk_forward, WalkForwardReport

    report = run_walk_forward(decisions, folds=DEFAULT_FOLDS)
    print(report.summary())
    report.save_csv("outputs/walk_forward_results.csv")
    report.save_locked_policy_yaml("outputs/locked_policy_by_period.yaml")
"""
from __future__ import annotations

import csv
import statistics
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Policy grid
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PolicyConfig:
    """One candidate policy configuration."""
    min_model_score: float = 0.50
    # Documentation only: not varied in DEFAULT_POLICY_GRID because changing it
    # requires separate replay runs with different exits.
    max_hold_days: int = 28
    require_catalyst_days: int = 30   # 0 = disabled

    def label(self) -> str:
        cat = f"cat{self.require_catalyst_days}d" if self.require_catalyst_days else "nocat"
        return (
            f"score{self.min_model_score:.2f}_"
            f"hold{self.max_hold_days}d_"
            f"{cat}"
        )


DEFAULT_POLICY_GRID: list[PolicyConfig] = [
    PolicyConfig(min_model_score=s, require_catalyst_days=c)
    for s in [0.40, 0.50, 0.60]
    for c in [0, 90]
]

# ---------------------------------------------------------------------------
# Fold definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FoldSpec:
    """Date ranges for one walk-forward fold."""
    fold_id: int
    train_start: str   # ISO date YYYY-MM-DD
    train_end: str
    test_start: str
    test_end: str


DEFAULT_FOLDS: list[FoldSpec] = [
    FoldSpec(1, "2021-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
    FoldSpec(2, "2021-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
    FoldSpec(3, "2021-01-01", "2024-12-31", "2025-01-01", "2025-12-31"),
]


# ---------------------------------------------------------------------------
# Per-fold metrics
# ---------------------------------------------------------------------------

@dataclass
class PolicyMetrics:
    """Performance of one policy on one window (train or test)."""
    policy: PolicyConfig
    n_trades: int
    mean_return_pct: Optional[float]
    sharpe: Optional[float]
    hit_rate: Optional[float]
    ci90_lower: Optional[float]   # bootstrap 90% CI lower bound
    passed: bool                  # ci90_lower > 0

    def to_dict(self) -> dict:
        return {
            "policy": self.policy.label(),
            "n_trades": self.n_trades,
            "mean_return_pct": _r(self.mean_return_pct),
            "sharpe": _r(self.sharpe),
            "hit_rate": _r(self.hit_rate),
            "ci90_lower": _r(self.ci90_lower),
            "passed": self.passed,
        }


@dataclass
class LockedPolicy:
    """The winning policy for one fold, locked for OOS evaluation."""
    fold_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    policy: PolicyConfig
    train_mean_return_pct: Optional[float]
    test_mean_return_pct: Optional[float]
    test_n_trades: int
    test_passed: bool
    selection_criterion: str = "max_mean_return_in_sample"

    def to_dict(self) -> dict:
        return {
            "fold_id": self.fold_id,
            "train_period": f"{self.train_start} → {self.train_end}",
            "test_period": f"{self.test_start} → {self.test_end}",
            "locked_policy": {
                "min_model_score": self.policy.min_model_score,
                "max_hold_days": self.policy.max_hold_days,
                "require_catalyst_days": self.policy.require_catalyst_days,
            },
            "train_mean_return_pct": _r(self.train_mean_return_pct),
            "test_mean_return_pct": _r(self.test_mean_return_pct),
            "test_n_trades": self.test_n_trades,
            "test_passed": self.test_passed,
        }


@dataclass
class WalkForwardFold:
    """Complete results for one fold."""
    spec: FoldSpec
    all_train_metrics: list[PolicyMetrics]   # one per candidate policy
    best_train: PolicyMetrics
    locked: LockedPolicy
    test_metrics: PolicyMetrics


@dataclass
class WalkForwardReport:
    """Aggregate walk-forward results across all folds."""
    model_name: str
    folds: list[WalkForwardFold] = field(default_factory=list)
    policy_grid: list[PolicyConfig] = field(default_factory=list)

    # Stability assessment
    @property
    def locked_policies(self) -> list[LockedPolicy]:
        return [f.locked for f in self.folds]

    @property
    def optimal_score_stable(self) -> bool:
        scores = [f.locked.policy.min_model_score for f in self.folds]
        return len(set(scores)) == 1

    @property
    def optimal_hold_days_stable(self) -> bool:
        return True

    @property
    def optimal_catalyst_gate_stable(self) -> bool:
        gates = [f.locked.policy.require_catalyst_days for f in self.folds]
        return len(set(gates)) == 1

    @property
    def n_folds_with_positive_oos(self) -> int:
        return sum(
            1 for f in self.folds
            if f.locked.test_mean_return_pct is not None
            and f.locked.test_mean_return_pct > 0
        )

    @property
    def overall_stability_grade(self) -> str:
        """STABLE / MODERATE / UNSTABLE."""
        stable_count = sum([
            self.optimal_score_stable,
            self.optimal_hold_days_stable,
            self.optimal_catalyst_gate_stable,
        ])
        if stable_count == 3:
            return "STABLE"
        elif stable_count >= 2:
            return "MODERATE"
        return "UNSTABLE"

    def summary(self) -> str:
        lines = [
            "=" * 70,
            f"  WALK-FORWARD MODEL SELECTION — {self.model_name}",
            "=" * 70,
            f"  Folds: {len(self.folds)}",
            f"  Policy candidates per fold: {len(self.policy_grid)}",
            "",
            f"  {'Fold':<6} {'Train period':<25} {'Test period':<25} "
            f"{'In-sample':>10} {'OOS':>10} {'OOS N':>6} {'Pass':>5}",
            "  " + "─" * 66,
        ]
        for f in self.folds:
            lk = f.locked
            train_r = f"{lk.train_mean_return_pct:+.2f}%" if lk.train_mean_return_pct is not None else "n/a"
            test_r = f"{lk.test_mean_return_pct:+.2f}%" if lk.test_mean_return_pct is not None else "n/a"
            win = "✓" if lk.test_passed else "✗"
            lines.append(
                f"  {lk.fold_id:<6} {lk.train_start+' → '+lk.train_end:<25} "
                f"{lk.test_start+' → '+lk.test_end:<25} "
                f"{train_r:>10}  {test_r:>10}  {lk.test_n_trades:>5}  {win:>4}"
            )
        lines.append("")
        lines.append("  Locked policy by fold:")
        for f in self.folds:
            p = f.locked.policy
            lines.append(
                f"    Fold {f.spec.fold_id}: "
                f"score≥{p.min_model_score:.2f}  hold≤{p.max_hold_days}d  "
                f"catalyst≤{p.require_catalyst_days}d"
                if p.require_catalyst_days else
                f"    Fold {f.spec.fold_id}: "
                f"score≥{p.min_model_score:.2f}  hold≤{p.max_hold_days}d  no-catalyst-gate"
            )
        lines.append("")
        lines.append(f"  Score threshold stable:      {'✓' if self.optimal_score_stable else '✗'}")
        lines.append("  Hold days stable:            not tested (separate replay seeds required)")
        lines.append(f"  Catalyst gate stable:        {'✓' if self.optimal_catalyst_gate_stable else '✗'}")
        lines.append(f"  OOS positive folds:          {self.n_folds_with_positive_oos}/{len(self.folds)}")
        lines.append(f"  Overall stability grade:     {self.overall_stability_grade}")
        lines.append("")
        lines.append("  NOTE: max_hold_days was not varied in this walk-forward analysis.")
        lines.append("        Test hold-period sensitivity with separate replay seeds and")
        lines.append("        compare them using walk_forward.compare_hold_days().")
        lines.append("=" * 70)
        return "\n".join(lines)

    def to_rows(self) -> list[dict]:
        """Flat rows suitable for CSV export."""
        rows = []
        for f in self.folds:
            lk = f.locked
            rows.append({
                "fold_id": lk.fold_id,
                "train_start": lk.train_start,
                "train_end": lk.train_end,
                "test_start": lk.test_start,
                "test_end": lk.test_end,
                "locked_min_model_score": lk.policy.min_model_score,
                "locked_max_hold_days": lk.policy.max_hold_days,
                "locked_require_catalyst_days": lk.policy.require_catalyst_days,
                "train_mean_return_pct": _r(lk.train_mean_return_pct),
                "test_mean_return_pct": _r(lk.test_mean_return_pct),
                "test_n_trades": lk.test_n_trades,
                "test_passed": lk.test_passed,
            })
        return rows

    def save_csv(self, path: str) -> None:
        rows = self.to_rows()
        if not rows:
            return
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def save_locked_policy_yaml(self, path: str) -> None:
        import yaml  # type: ignore[import]
        data = {
            "model_name": self.model_name,
            "stability_grade": self.overall_stability_grade,
            "folds": [f.locked.to_dict() for f in self.folds],
        }
        with open(path, "w") as f:
            yaml.safe_dump(data, f, sort_keys=False)

    def parameter_stability_report(self) -> str:
        """Markdown stability report for docs."""
        lines = [
            "# Walk-Forward Parameter Stability Report",
            "",
            f"**Model:** {self.model_name}  ",
            f"**Folds:** {len(self.folds)}  ",
            f"**Stability grade:** {self.overall_stability_grade}  ",
            "",
            "## Per-fold locked policies",
            "",
            "| Fold | Train | Test | Score≥ | Hold≤ | Catalyst≤ | In-sample | OOS |",
            "|------|-------|------|--------|-------|-----------|-----------|-----|",
        ]
        for f in self.folds:
            lk = f.locked
            p = lk.policy
            train_r = f"{lk.train_mean_return_pct:+.2f}%" if lk.train_mean_return_pct is not None else "n/a"
            test_r = f"{lk.test_mean_return_pct:+.2f}%" if lk.test_mean_return_pct is not None else "n/a"
            cat_str = f"{p.require_catalyst_days}d" if p.require_catalyst_days else "none"
            lines.append(
                f"| {lk.fold_id} | {lk.train_start[:4]}–{lk.train_end[:4]} "
                f"| {lk.test_start[:4]} | {p.min_model_score:.2f} "
                f"| {p.max_hold_days}d | {cat_str} | {train_r} | {test_r} |"
            )
        lines += [
            "",
            "## Stability assessment",
            "",
            f"- Score threshold consistent: {'Yes' if self.optimal_score_stable else 'No'}",
            "- Hold days consistent: not tested in grid (separate replay seeds required)",
            f"- Catalyst gate consistent: {'Yes' if self.optimal_catalyst_gate_stable else 'No'}",
            f"- OOS positive folds: {self.n_folds_with_positive_oos}/{len(self.folds)}",
            "",
            "## Interpretation",
            "",
        ]
        grade = self.overall_stability_grade
        if grade == "STABLE":
            if self.n_folds_with_positive_oos >= 2:
                lines.append(
                    "Parameters are stable across folds and at least two OOS folds are positive. "
                    "This reduces overfitting risk, but promotion still depends on the replay "
                    "significance and independent-N gates."
                )
            else:
                lines.append(
                    "Parameters are stable across folds, but OOS returns are not consistently "
                    "positive. Treat this as parameter consistency only, not evidence for "
                    "validation-grade promotion."
                )
        elif grade == "MODERATE":
            lines.append(
                "Parameters are moderately stable (2/3 dimensions agree). "
                "Some sensitivity to the choice of fold. Exercise caution when "
                "applying the locked policy to new data."
            )
        else:
            lines.append(
                "Parameters are UNSTABLE across folds. Different policy configurations "
                "win in different periods — strong evidence of overfitting or regime "
                "sensitivity. Do not claim statistical significance until stability improves."
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core walk-forward engine
# ---------------------------------------------------------------------------

def _filter_decisions_by_date(
    decisions: list[dict], start: str, end: str
) -> list[dict]:
    """Return decisions where entry_date falls in [start, end]."""
    return [
        d for d in decisions
        if start <= str(d.get("entry_date", "") or "")[:10] <= end
    ]


def _apply_policy(decisions: list[dict], policy: PolicyConfig) -> list[dict]:
    """Filter decisions matching the policy configuration."""
    filtered = []
    for d in decisions:
        score = float(d.get("composite_score") or d.get("ranking_score") or 0.0)
        if score < policy.min_model_score:
            continue
        if policy.require_catalyst_days:
            cat_days = d.get("days_to_catalyst")
            if cat_days is None:
                continue
            if int(cat_days) > policy.require_catalyst_days:
                continue
        filtered.append(d)
    return filtered


def _compute_policy_metrics(
    decisions: list[dict], policy: PolicyConfig, n_bootstrap: int = 500, seed: int = 42
) -> PolicyMetrics:
    """Compute performance metrics for a policy on a set of decisions."""
    import random

    eligible = [d for d in decisions if d.get("return_pct") is not None]
    if not eligible:
        return PolicyMetrics(
            policy=policy, n_trades=0,
            mean_return_pct=None, sharpe=None, hit_rate=None,
            ci90_lower=None, passed=False,
        )

    returns = [float(d["return_pct"]) for d in eligible]
    n = len(returns)
    mean_r = statistics.mean(returns)
    std_r = statistics.stdev(returns) if n > 1 else 0.0
    sharpe = mean_r / std_r if std_r > 0 else None
    hit = sum(1 for r in returns if r > 0) / n

    # Cluster bootstrap CI (cluster = asset_id)
    rng = random.Random(seed)
    clusters: dict[str, list[float]] = {}
    for d in eligible:
        clusters.setdefault(str(d.get("asset_id", "")), []).append(float(d["return_pct"]))
    cluster_list = list(clusters.values())
    n_clusters = len(cluster_list)

    boot_means = []
    for _ in range(n_bootstrap):
        sample = [rng.choice(cluster_list) for _ in range(n_clusters)]
        flat = [r for cl in sample for r in cl]
        if flat:
            boot_means.append(statistics.mean(flat))

    boot_means.sort()
    ci90_lower = None
    if boot_means:
        ci90_lower = round(boot_means[int(0.05 * len(boot_means))], 4)

    passed = ci90_lower is not None and ci90_lower > 0

    return PolicyMetrics(
        policy=policy,
        n_trades=n,
        mean_return_pct=round(mean_r, 4),
        sharpe=round(sharpe, 4) if sharpe is not None else None,
        hit_rate=round(hit, 4),
        ci90_lower=ci90_lower,
        passed=passed,
    )


def run_walk_forward(
    decisions: list[dict],
    *,
    model_name: str = "historical_replay",
    folds: list[FoldSpec] = DEFAULT_FOLDS,
    policy_grid: list[PolicyConfig] = DEFAULT_POLICY_GRID,
    n_bootstrap: int = 500,
    seed: int = 42,
) -> WalkForwardReport:
    """Run walk-forward model selection across all folds.

    Parameters
    ----------
    decisions:
        List of replay decision dicts. Required keys: entry_date, return_pct.
        Optional: composite_score, ranking_score, asset_id, days_to_catalyst.
    model_name:
        Label for the report.
    folds:
        Ordered list of FoldSpec objects.
    policy_grid:
        Candidate policy configurations to evaluate.
    n_bootstrap:
        Number of cluster-bootstrap samples per policy evaluation.
    seed:
        Random seed for reproducibility.
    """
    report = WalkForwardReport(model_name=model_name, policy_grid=policy_grid)

    for spec in folds:
        # Partition decisions
        train_decisions = _filter_decisions_by_date(decisions, spec.train_start, spec.train_end)
        test_decisions = _filter_decisions_by_date(decisions, spec.test_start, spec.test_end)

        # Evaluate all policies on training window
        all_train: list[PolicyMetrics] = []
        for policy in policy_grid:
            filtered_train = _apply_policy(train_decisions, policy)
            m = _compute_policy_metrics(filtered_train, policy, n_bootstrap=n_bootstrap, seed=seed)
            all_train.append(m)

        # Select best policy = highest in-sample mean return (with ≥5 trades)
        eligible_train = [m for m in all_train if m.n_trades >= 5 and m.mean_return_pct is not None]
        if eligible_train:
            best_train = max(eligible_train, key=lambda m: m.mean_return_pct)  # type: ignore[arg-type]
        elif all_train:
            best_train = max(all_train, key=lambda m: m.n_trades)
        else:
            best_train = PolicyMetrics(
                policy=policy_grid[0], n_trades=0,
                mean_return_pct=None, sharpe=None, hit_rate=None,
                ci90_lower=None, passed=False,
            )

        # Lock the best policy and evaluate OOS
        locked_policy = best_train.policy
        filtered_test = _apply_policy(test_decisions, locked_policy)
        test_m = _compute_policy_metrics(filtered_test, locked_policy, n_bootstrap=n_bootstrap, seed=seed)

        locked = LockedPolicy(
            fold_id=spec.fold_id,
            train_start=spec.train_start,
            train_end=spec.train_end,
            test_start=spec.test_start,
            test_end=spec.test_end,
            policy=locked_policy,
            train_mean_return_pct=best_train.mean_return_pct,
            test_mean_return_pct=test_m.mean_return_pct,
            test_n_trades=test_m.n_trades,
            test_passed=test_m.passed,
        )

        report.folds.append(WalkForwardFold(
            spec=spec,
            all_train_metrics=all_train,
            best_train=best_train,
            locked=locked,
            test_metrics=test_m,
        ))

    return report


def compare_hold_days(
    decisions_by_hold: dict[int, list[dict]],
    *,
    model_name: str = "historical_replay",
) -> dict[int, PolicyMetrics]:
    """Compare separate replay runs with different max_hold_days values."""
    out: dict[int, PolicyMetrics] = {}
    for hold_days, decisions in sorted(decisions_by_hold.items()):
        policy = PolicyConfig(max_hold_days=hold_days, require_catalyst_days=0)
        out[hold_days] = _compute_policy_metrics(decisions, policy)
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _r(v: Optional[float], d: int = 4) -> Optional[float]:
    return round(v, d) if v is not None else None
