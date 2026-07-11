from __future__ import annotations

import json

import pytest

from bve.se.evaluation.holdout import (
    HoldoutPrediction,
    load_holdout_cases,
    predict_holdout,
    validate_predictions,
)


def test_eight_holdout_cases_produce_eight_scoreable_predictions(tmp_path) -> None:
    path = tmp_path / "holdout_data.jsonl"
    path.write_text(
        "\n".join(
            json.dumps(
                {
                    "case_id": f"HO-{index:03d}",
                    "target": "CD19" if index % 2 else "BCMA",
                    "modality": "T-cell engager",
                    "source_text": (
                        "incomplete ownership information" if index > 4 else "public evidence"
                    ),
                }
            )
            for index in range(1, 9)
        )
        + "\n"
    )

    predictions = predict_holdout(path)

    assert len(predictions) == 8
    assert [prediction.case_id for prediction in predictions] == [
        f"HO-{i:03d}" for i in range(1, 9)
    ]
    assert all(
        prediction.disposition in {"INCLUDE", "EXCLUDE", "UNKNOWN"}
        for prediction in predictions
    )


def test_holdout_loader_rejects_labels(tmp_path) -> None:
    path = tmp_path / "holdout_data.jsonl"
    path.write_text(
        json.dumps(
            {
                "case_id": "HO-001",
                "target": "CD19",
                "modality": "T-cell engager",
                "source_text": "public evidence",
                "expected_disposition": "INCLUDE",
            }
        )
        + "\n"
    )

    with pytest.raises(ValueError, match="extra_forbidden"):
        load_holdout_cases(path)


def test_prediction_validation_detects_duplicate_and_missing_cases() -> None:
    prediction = HoldoutPrediction(case_id="A", disposition="INCLUDE")
    with pytest.raises(ValueError, match="duplicate"):
        validate_predictions(["A", "B"], [prediction, prediction])
    with pytest.raises(ValueError, match="missing"):
        validate_predictions(["A", "B"], [prediction])


def test_prediction_validation_rejects_invalid_disposition() -> None:
    with pytest.raises(ValueError):
        validate_predictions(["A"], [{"case_id": "A", "disposition": "MAYBE"}])


def test_prediction_output_is_deterministic_and_canonical(tmp_path) -> None:
    records = [
        {"case_id": "B", "target": "BCMA", "modality": "TCE", "source_text": "public evidence"},
        {"case_id": "A", "target": "CD19", "modality": "TCE", "source_text": "incomplete"},
    ]
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    first.write_text("\n".join(json.dumps(record) for record in records) + "\n")
    second.write_text("\n".join(json.dumps(record) for record in reversed(records)) + "\n")

    assert [item.model_dump() for item in predict_holdout(first)] == [
        item.model_dump() for item in predict_holdout(second)
    ]
