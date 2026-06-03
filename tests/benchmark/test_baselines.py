"""Tests for baseline models and BenchmarkRunner."""

import pytest

from bve.benchmark.baselines import (
    CatalystBaseline,
    MNABaseline,
    POSBaseline,
    ValuationBaseline,
)
from bve.benchmark.benchmark_runner import BenchmarkRunner
from bve.benchmark.reports import render_benchmark_report


class TestPOSBaseline:
    def test_known_ta_phase_returns_base_rate(self):
        bl = POSBaseline()
        rate = bl.predict("oncology", "phase_2")
        assert 0.30 <= rate <= 0.45

    def test_unknown_ta_falls_back_to_other(self):
        bl = POSBaseline()
        rate = bl.predict("rare_disease_xyz", "phase_2")
        assert 0.0 < rate <= 1.0

    def test_batch_predict_length_matches(self):
        bl = POSBaseline()
        records = [{"ta": "oncology", "phase": "phase_2"}] * 5
        preds = bl.predict_batch(records)
        assert len(preds) == 5

    def test_brier_score_perfect_predictions(self):
        bl = POSBaseline()
        preds = [1.0, 0.0, 1.0]
        outcomes = [1, 0, 1]
        assert bl.brier_score(preds, outcomes) == 0.0

    def test_brier_score_worst_predictions(self):
        bl = POSBaseline()
        preds = [0.0, 1.0, 0.0]
        outcomes = [1, 0, 1]
        assert abs(bl.brier_score(preds, outcomes) - 1.0) < 1e-10

    def test_no_skill_brier_equals_variance(self):
        bl = POSBaseline()
        outcomes = [1, 0, 1, 0]
        nsk = bl.no_skill_brier(outcomes)
        assert 0.0 < nsk <= 0.25

    def test_skill_improvement_positive_for_good_model(self):
        bl = POSBaseline()
        # Better than random
        preds = [0.8, 0.2, 0.7, 0.3]
        outcomes = [1, 0, 1, 0]
        improvement = bl.skill_improvement_pct(preds, outcomes)
        assert improvement > 0


class TestMNABaseline:
    def test_phase2_scores_higher_than_phase1(self):
        bl = MNABaseline()
        s2 = bl.score("phase_2", cash_runway_months=24, market_cap_usd=5e8)
        s1 = bl.score("phase_1", cash_runway_months=24, market_cap_usd=5e8)
        assert s2 > s1

    def test_rank_batch_sorted_descending(self):
        bl = MNABaseline()
        records = [
            {"ticker": "A", "phase": "phase_3", "cash_runway_months": 24, "market_cap_usd": 2e8},
            {"ticker": "B", "phase": "phase_1", "cash_runway_months": 6, "market_cap_usd": 5e9},
        ]
        ranked = bl.rank_batch(records)
        assert ranked[0][0] == "A"  # phase 3 + small cap should rank higher

    def test_score_in_range(self):
        bl = MNABaseline()
        s = bl.score("phase_2", 18, 1e8)
        assert 0.0 <= s <= 1.0


class TestValuationBaseline:
    def test_rnpv_positive(self):
        bl = ValuationBaseline()
        v = bl.compute_rnpv("oncology", "phase_2")
        assert v > 0

    def test_rnpv_higher_for_phase3(self):
        bl = ValuationBaseline()
        v2 = bl.compute_rnpv("oncology", "phase_2")
        v3 = bl.compute_rnpv("oncology", "phase_3")
        assert v3 > v2

    def test_ownership_scales_rnpv(self):
        bl = ValuationBaseline()
        full = bl.compute_rnpv("oncology", "phase_2", net_ownership=1.0)
        half = bl.compute_rnpv("oncology", "phase_2", net_ownership=0.5)
        assert abs(half - full * 0.5) < 0.01


class TestCatalystBaseline:
    def test_known_event_returns_magnitude(self):
        bl = CatalystBaseline()
        mag = bl.predict_magnitude("phase_3_topline")
        assert mag > 0

    def test_unknown_event_returns_default(self):
        bl = CatalystBaseline()
        mag = bl.predict_magnitude("unknown_event_type")
        assert mag > 0

    def test_direction_always_50_50(self):
        bl = CatalystBaseline()
        assert bl.predict_direction() == 0.5


class TestBenchmarkRunner:
    def test_pos_benchmark_returns_results(self):
        runner = BenchmarkRunner()
        records = [{"ta": "oncology", "phase": "phase_2"}] * 10
        # Simulate a better-than-baseline model: oncology phase 2 base rate = 0.35
        model_preds = [0.35] * 10
        outcomes = [1, 0, 1, 0, 1, 0, 1, 0, 1, 0]
        results = runner.run_pos_benchmark(model_preds, records, outcomes)
        assert len(results) == 3
        assert all(r.metric in ("brier_score", "auc_roc", "skill_improvement_pct") for r in results)

    def test_mna_benchmark_returns_precision(self):
        runner = BenchmarkRunner()
        records = [
            {"ticker": "A", "phase": "phase_3", "cash_runway_months": 24, "market_cap_usd": 2e8},
            {"ticker": "B", "phase": "phase_2", "cash_runway_months": 18, "market_cap_usd": 5e8},
        ]
        model_scores = [("A", 0.90), ("B", 0.50)]
        actual_deals = {"A"}
        results = runner.run_mna_benchmark(model_scores, records, actual_deals)
        assert len(results) == 1
        assert "precision" in results[0].metric

    def test_valuation_benchmark_returns_error_metric(self):
        runner = BenchmarkRunner()
        records = [{"ta": "oncology", "phase": "phase_2"}] * 5
        model_rnpvs = [400.0, 350.0, 450.0, 380.0, 420.0]
        actual_peak = [500.0, 400.0, 500.0, 400.0, 500.0]
        results = runner.run_valuation_benchmark(model_rnpvs, records, actual_peak)
        assert len(results) == 1
        assert results[0].metric == "median_abs_pct_error"

    def test_result_describe_contains_pass_fail(self):
        runner = BenchmarkRunner()
        records = [{"ta": "oncology", "phase": "phase_2"}] * 5
        model_preds = [0.35] * 5
        outcomes = [1, 0, 1, 0, 1]
        results = runner.run_pos_benchmark(model_preds, records, outcomes)
        for r in results:
            desc = r.describe()
            assert "PASS" in desc or "FAIL" in desc


class TestBenchmarkReport:
    def test_render_returns_markdown(self):
        runner = BenchmarkRunner()
        records = [{"ta": "oncology", "phase": "phase_2"}] * 5
        model_preds = [0.35] * 5
        outcomes = [1, 0, 1, 0, 1]
        pos_results = runner.run_pos_benchmark(model_preds, records, outcomes)
        report = render_benchmark_report({"pos": pos_results})
        assert "# Benchmark Report" in report
        assert "PASS" in report or "FAIL" in report
