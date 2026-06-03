from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from bve.analysis.mna_probability_scanner import _evaluate, _load_dataset
from bve.intelligence.ma_calibration import MACalibrationDataset, MACalibrationRow


def test_load_and_evaluate_historical_mna_dataset(tmp_path: Path):
    dataset_path = tmp_path / "historical_labels.csv"
    fieldnames = [
        "snapshot_date",
        "asset_id",
        "ticker",
        "label",
        "probability",
        "rank",
        "best_acquirer_id",
        "best_acquirer_name",
        "acquirer_candidate_ids",
        "acquirer_candidate_names",
        "stage",
        "therapeutic_area",
        "days_to_announcement",
        "announcement_date",
        "acquired_by",
        "match_group_id",
    ]
    rows = [
        {
            "snapshot_date": date(2026, 1, 1).isoformat(),
            "asset_id": "asset-pos",
            "ticker": "POS",
            "label": 1,
            "probability": 0.8,
            "rank": 1,
            "best_acquirer_id": "pfizer",
            "best_acquirer_name": "Pfizer",
            "acquirer_candidate_ids": '["pfizer","merck","roche"]',
            "acquirer_candidate_names": '["Pfizer","Merck","Roche"]',
            "stage": "phase_3",
            "therapeutic_area": "oncology",
            "days_to_announcement": 120,
            "announcement_date": date(2026, 5, 1).isoformat(),
            "acquired_by": "Pfizer",
            "match_group_id": "",
        },
        {
            "snapshot_date": date(2026, 1, 1).isoformat(),
            "asset_id": "asset-ctrl",
            "ticker": "CTRL",
            "label": 0,
            "probability": 0.2,
            "rank": 2,
            "best_acquirer_id": "pfizer",
            "best_acquirer_name": "Pfizer",
            "acquirer_candidate_ids": '["pfizer","merck","roche"]',
            "acquirer_candidate_names": '["Pfizer","Merck","Roche"]',
            "stage": "phase_3",
            "therapeutic_area": "oncology",
            "days_to_announcement": "",
            "announcement_date": "",
            "acquired_by": "",
            "match_group_id": "",
        },
    ]
    with dataset_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    dataset = _load_dataset(dataset_path)
    metrics = _evaluate(dataset, top_k=1)

    assert dataset.dataset_mode == "historical_snapshot"
    assert dataset.n_rows == 2
    assert metrics.precision_at_k == 1.0
    assert metrics.unique_target_recall_at_k == 1.0
    assert metrics.false_positive_rate_at_k == 0.0
    assert metrics.acquirer_top1_accuracy == 1.0
    assert metrics.acquirer_top3_accuracy == 1.0
    assert metrics.acquirer_top5_accuracy == 1.0
    assert metrics.acquirer_mrr == 1.0
    # Stage A metrics are None when stage_a_probability is not populated (CSV rows lack it)
    assert metrics.acquisition_likelihood_precision is None
    assert metrics.acquisition_likelihood_auc is None


def _make_row(
    ticker: str,
    label: int,
    probability: float,
    stage_a_probability: float | None = None,
    acquired_by: str | None = None,
    acquirer_names: list[str] | None = None,
) -> MACalibrationRow:
    return MACalibrationRow(
        snapshot_date=date(2026, 1, 1),
        asset_id=f"asset-{ticker.lower()}",
        ticker=ticker,
        label=label,
        probability=probability,
        rank=1,
        best_acquirer_id="pfizer",
        best_acquirer_name="Pfizer",
        acquirer_candidate_names=acquirer_names or [],
        stage_a_probability=stage_a_probability,
        acquired_by=acquired_by,
    )


def _make_dataset(rows: list[MACalibrationRow]) -> MACalibrationDataset:
    return MACalibrationDataset(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        lookahead_days=365,
        n_rows=len(rows),
        n_positive_rows=sum(1 for r in rows if r.label == 1),
        n_control_rows=sum(1 for r in rows if r.label == 0),
        n_unique_targets=len({r.ticker for r in rows if r.label == 1}),
        dataset_mode="historical_snapshot",
        rows=rows,
    )


def test_evaluate_reports_stage_a_metrics_when_populated():
    rows = [
        _make_row("POS", 1, 0.9, stage_a_probability=0.8, acquired_by="Pfizer",
                  acquirer_names=["Pfizer", "Merck"]),
        _make_row("CTRL1", 0, 0.3, stage_a_probability=0.2),
        _make_row("CTRL2", 0, 0.2, stage_a_probability=0.1),
    ]
    dataset = _make_dataset(rows)
    metrics = _evaluate(dataset, top_k=2)

    assert metrics.acquisition_likelihood_precision is not None
    assert metrics.acquisition_likelihood_recall is not None
    assert metrics.acquisition_likelihood_auc is not None
    assert metrics.stage_a_avg_positive is not None
    assert metrics.stage_a_avg_control is not None
    assert metrics.stage_a_avg_positive > metrics.stage_a_avg_control


def test_evaluate_stage_a_precision_is_separate_from_stage_b():
    """Stage A and Stage B precision can differ because they use different ranking scores."""
    rows = [
        # High stage_a score, low composite probability (would rank low in Stage B top-k)
        _make_row("POS", 1, 0.2, stage_a_probability=0.9, acquired_by="Pfizer",
                  acquirer_names=["Pfizer"]),
        _make_row("CTRL1", 0, 0.9, stage_a_probability=0.1),
        _make_row("CTRL2", 0, 0.8, stage_a_probability=0.05),
    ]
    dataset = _make_dataset(rows)
    metrics = _evaluate(dataset, top_k=1)

    # Stage B ranks by probability: CTRL1 (0.9) > CTRL2 (0.8) > POS (0.2) → precision=0
    assert metrics.precision_at_k == 0.0
    # Stage A ranks by stage_a_probability: POS (0.9) is top-1 → precision=1.0
    assert metrics.acquisition_likelihood_precision == 1.0


def test_evaluate_stage_b_acquirer_ranking_conditional_on_actual_deals():
    """Acquirer top-N is computed only over rows where acquired_by is known."""
    rows = [
        _make_row("ACQ1", 1, 0.9, acquired_by="Merck", acquirer_names=["Pfizer", "Merck"]),
        _make_row("ACQ2", 1, 0.8, acquired_by="Roche", acquirer_names=["Novartis"]),
        _make_row("CTRL", 0, 0.3),
    ]
    dataset = _make_dataset(rows)
    metrics = _evaluate(dataset, top_k=3)

    # ACQ1: Merck is at index 1 → hits top-2, top-5 but not top-1
    # ACQ2: Roche not in list → miss
    assert metrics.acquirer_top1_accuracy is not None
    assert metrics.acquirer_mrr is not None
    # MRR for ACQ1: rank=2 → 1/2; ACQ2: not found → 0; mean = 0.25
    assert abs(metrics.acquirer_mrr - 0.25) < 1e-5
