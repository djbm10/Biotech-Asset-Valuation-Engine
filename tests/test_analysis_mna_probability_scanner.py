from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from bve.analysis.mna_probability_scanner import _evaluate, _load_dataset


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
        "stage",
        "therapeutic_area",
        "days_to_announcement",
        "announcement_date",
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
            "stage": "phase_3",
            "therapeutic_area": "oncology",
            "days_to_announcement": 120,
            "announcement_date": date(2026, 5, 1).isoformat(),
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
            "stage": "phase_3",
            "therapeutic_area": "oncology",
            "days_to_announcement": "",
            "announcement_date": "",
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
