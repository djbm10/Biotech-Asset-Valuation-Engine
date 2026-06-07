from __future__ import annotations

import warnings

import pytest

from bve.analysis.backtest import BacktestCase, BacktestReport, BacktestResult
from bve.analysis.friction_model import INSTITUTIONAL_FRICTIONS, RETAIL_FRICTIONS
from bve.analysis.pos_calibration import _heuristic_pos_from_row
from bve.analysis.regime_analysis import compute_regime_report
from bve.analysis.replay_significance import analyze, permutation_test
from bve.analysis.walk_forward import DEFAULT_POLICY_GRID, PolicyConfig, _apply_policy


def test_friction_model_net_return_less_than_gross() -> None:
    assert INSTITUTIONAL_FRICTIONS.round_trip_cost_bps > RETAIL_FRICTIONS.round_trip_cost_bps
    assert INSTITUTIONAL_FRICTIONS.net_return(10.0) < 10.0


def test_walk_forward_grid_does_not_vary_hold_days() -> None:
    assert len(DEFAULT_POLICY_GRID) == 6
    assert {p.max_hold_days for p in DEFAULT_POLICY_GRID} == {28}
    assert {p.require_catalyst_days for p in DEFAULT_POLICY_GRID} == {0, 90}


def test_require_catalyst_filter_requires_populated_days() -> None:
    decisions = [
        {"composite_score": 0.7, "days_to_catalyst": 30},
        {"composite_score": 0.7, "days_to_catalyst": 120},
        {"composite_score": 0.7},
    ]
    filtered = _apply_policy(decisions, PolicyConfig(min_model_score=0.5, require_catalyst_days=90))
    assert filtered == [decisions[0]]


def test_backtest_calibration_records_use_actual_scores() -> None:
    case = BacktestCase(
        drug="D",
        company="C",
        indication="solid tumor",
        phase="phase_2",
        outcome="advanced",
        year=2021,
        endpoint_type="hard_clinical",
        moa_precedent="validated",
        biomarker_enriched=True,
        safety_profile="clean",
        competitive_pressure="low",
    )
    report = BacktestReport(
        n_total=1,
        n_phase2=1,
        n_phase3=0,
        n_success=1,
        heuristic_brier_score=0.0,
        statistical_brier_score=0.0,
        no_skill_brier_score=0.0,
        heuristic_auc=0.0,
        statistical_auc=0.0,
        heuristic_brier_phase2=0.0,
        heuristic_brier_phase3=0.0,
        statistical_brier_phase2=0.0,
        statistical_brier_phase3=0.0,
        results=[BacktestResult(case=case, heuristic_pos=0.77, statistical_pos=0.66)],
    )
    assert report.to_calibration_records()[0].predicted_pos == 0.77
    assert report.to_calibration_records_statistical()[0].predicted_pos == 0.66


def test_heuristic_reconstruction_warns() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _heuristic_pos_from_row({}, "phase_2")
    assert any(item.category is DeprecationWarning for item in caught)


def test_replay_significance_asset_catalyst_clustering() -> None:
    decisions = [
        {"asset_id": "A", "catalyst_event_id": "1", "return_pct": 5.0},
        {"asset_id": "A", "catalyst_event_id": "2", "return_pct": 4.0},
        {"asset_id": "B", "catalyst_event_id": "3", "return_pct": 3.0},
    ]
    by_asset = analyze(decisions, bootstrap_samples=50, cluster_by="asset_id")
    by_event = analyze(decisions, bootstrap_samples=50, cluster_by="asset_catalyst")
    assert by_asset.n_clusters == 2
    assert by_event.n_clusters == 3


def test_permutation_detects_perfect_positive_ranking() -> None:
    decisions = [
        {"composite_score": i / 20, "return_pct": float(i)}
        for i in range(1, 21)
    ]
    result = permutation_test(decisions, n_permutations=200, seed=1)
    assert result.observed_score_return_corr == pytest.approx(1.0)
    assert result.skill_in_ranking is True


def test_regime_report_alpha_zero_when_returns_equal_xbi() -> None:
    decisions = [
        {
            "return_pct": float(i),
            "xbi_return_during_hold": float(i),
            "ibb_return_during_hold": float(i),
            "spy_return_during_hold": float(i),
            "xbi_above_20d_ma_at_entry": i % 2,
        }
        for i in range(1, 20)
    ]
    report = compute_regime_report(decisions)
    assert report.n_with_regime_data == 19
    assert report.xbi_adjusted_mean_return == pytest.approx(0.0)
