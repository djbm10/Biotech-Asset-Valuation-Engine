"""BenchmarkRunner — compare model outputs against baselines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .baselines import (
    MNABaseline,
    POSBaseline,
    ValuationBaseline,
)


@dataclass
class BenchmarkResult:
    """Comparison of model vs baseline on a specific metric."""

    model_name: str
    metric: str
    model_value: float
    baseline_value: float
    improvement_pct: float
    passed: bool
    n_samples: int
    note: str | None = None

    def describe(self) -> str:
        direction = "+" if self.improvement_pct >= 0 else ""
        status = "PASS" if self.passed else "FAIL"
        return (
            f"[{status}] {self.model_name} vs baseline | "
            f"{self.metric}: model={self.model_value:.4f} baseline={self.baseline_value:.4f} "
            f"({direction}{self.improvement_pct:.1f}%) | N={self.n_samples}"
        )


def _safe_improvement(model_val: float, baseline_val: float, higher_is_better: bool = True) -> float:
    if baseline_val == 0:
        return 0.0
    raw = (model_val - baseline_val) / abs(baseline_val) * 100
    return raw if higher_is_better else -raw


def _auc_roc(predictions: Sequence[float], outcomes: Sequence[int]) -> float:
    """Compute AUC-ROC via Mann-Whitney U statistic."""
    pos = [p for p, o in zip(predictions, outcomes) if o == 1]
    neg = [p for p, o in zip(predictions, outcomes) if o == 0]
    if not pos or not neg:
        return 0.5
    concordant = sum(1 for p in pos for n in neg if p > n)
    tied = sum(0.5 for p in pos for n in neg if p == n)
    return (concordant + tied) / (len(pos) * len(neg))


class BenchmarkRunner:
    """Runs benchmark comparisons for all major model types."""

    def run_pos_benchmark(
        self,
        model_predictions: Sequence[float],
        baseline_records: Sequence[dict],
        outcomes: Sequence[int],
        model_name: str = "pos_model",
    ) -> list[BenchmarkResult]:
        """Compare model vs TA/phase baseline on Brier and AUC."""
        results = []
        bl = POSBaseline()
        bl_preds = bl.predict_batch(baseline_records)

        n = len(outcomes)
        model_brier = bl.brier_score(model_predictions, outcomes)
        bl_brier = bl.brier_score(bl_preds, outcomes)

        results.append(
            BenchmarkResult(
                model_name=model_name,
                metric="brier_score",
                model_value=model_brier,
                baseline_value=bl_brier,
                improvement_pct=_safe_improvement(model_brier, bl_brier, higher_is_better=False),
                passed=model_brier <= bl_brier,
                n_samples=n,
                note="Lower Brier = better",
            )
        )

        model_auc = _auc_roc(model_predictions, outcomes)
        bl_auc = _auc_roc(bl_preds, outcomes)
        results.append(
            BenchmarkResult(
                model_name=model_name,
                metric="auc_roc",
                model_value=model_auc,
                baseline_value=bl_auc,
                improvement_pct=_safe_improvement(model_auc, bl_auc, higher_is_better=True),
                passed=model_auc >= bl_auc,
                n_samples=n,
            )
        )

        model_skill = bl.skill_improvement_pct(model_predictions, outcomes)
        bl_skill = bl.skill_improvement_pct(bl_preds, outcomes)
        results.append(
            BenchmarkResult(
                model_name=model_name,
                metric="skill_improvement_pct",
                model_value=model_skill,
                baseline_value=bl_skill,
                improvement_pct=model_skill - bl_skill,
                passed=model_skill >= bl_skill,
                n_samples=n,
            )
        )

        return results

    def run_mna_benchmark(
        self,
        model_scores: Sequence[tuple[str, float]],
        baseline_records: Sequence[dict],
        actual_deals: set[str],
        model_name: str = "mna_ranking",
    ) -> list[BenchmarkResult]:
        """Compare model vs M&A baseline on Precision@10."""
        bl = MNABaseline()
        bl_ranked = bl.rank_batch(baseline_records)

        def precision_at_k(ranked: list[tuple[str, float]], k: int, deals: set[str]) -> float:
            top_k = [ticker for ticker, _ in ranked[:k]]
            hits = sum(1 for t in top_k if t in deals)
            return hits / k if k > 0 else 0.0

        k = min(10, len(model_scores))
        model_sorted = sorted(model_scores, key=lambda x: x[1], reverse=True)
        model_p10 = precision_at_k(model_sorted, k, actual_deals)
        bl_p10 = precision_at_k(bl_ranked, k, actual_deals)

        return [
            BenchmarkResult(
                model_name=model_name,
                metric=f"precision_at_{k}",
                model_value=model_p10,
                baseline_value=bl_p10,
                improvement_pct=_safe_improvement(model_p10, bl_p10, higher_is_better=True),
                passed=model_p10 >= bl_p10,
                n_samples=len(model_scores),
            )
        ]

    def run_valuation_benchmark(
        self,
        model_rnpvs: Sequence[float],
        baseline_records: Sequence[dict],
        actual_peak_sales: Sequence[float],
        model_name: str = "valuation_model",
    ) -> list[BenchmarkResult]:
        """Compare median peak sales error: model vs fixed baseline."""
        bl = ValuationBaseline()

        def median_abs_pct_error(predicted: Sequence[float], actual: Sequence[float]) -> float:
            errors = [abs(p - a) / max(abs(a), 1) for p, a in zip(predicted, actual)]
            sorted_errors = sorted(errors)
            n = len(sorted_errors)
            if n == 0:
                return float("nan")
            mid = n // 2
            return sorted_errors[mid] if n % 2 else (sorted_errors[mid - 1] + sorted_errors[mid]) / 2

        bl_rnpvs = [
            bl.compute_rnpv(r.get("ta", "other"), r.get("phase", "phase_2"))
            for r in baseline_records
        ]
        model_err = median_abs_pct_error(model_rnpvs, actual_peak_sales)
        bl_err = median_abs_pct_error(bl_rnpvs, actual_peak_sales)

        return [
            BenchmarkResult(
                model_name=model_name,
                metric="median_abs_pct_error",
                model_value=model_err,
                baseline_value=bl_err,
                improvement_pct=_safe_improvement(model_err, bl_err, higher_is_better=False),
                passed=model_err <= bl_err,
                n_samples=len(model_rnpvs),
                note="Lower error = better",
            )
        ]

    def run_all(
        self,
        pos_data: dict | None = None,
        mna_data: dict | None = None,
        valuation_data: dict | None = None,
    ) -> dict[str, list[BenchmarkResult]]:
        results = {}
        if pos_data:
            results["pos"] = self.run_pos_benchmark(**pos_data)
        if mna_data:
            results["mna"] = self.run_mna_benchmark(**mna_data)
        if valuation_data:
            results["valuation"] = self.run_valuation_benchmark(**valuation_data)
        return results
