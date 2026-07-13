from __future__ import annotations

import json

import pytest

from bve.cli.se_holdout_evaluate import main


def test_holdout_cli_emits_one_prediction_per_case(tmp_path) -> None:
    problem = tmp_path / "problem.yaml"
    problem.write_text(
        """schema_version: se_holdout_problem_v1
problem_id: smoke
version: '1.0'
title: Synthetic acquisition triage
task: Classify each standalone evidence item.
allowed_dispositions: [INCLUDE, EXCLUDE, UNKNOWN]
labeling_rubric:
  INCLUDE: Decision-relevant human or regulatory evidence.
  EXCLUDE: Irrelevant or non-human evidence.
  UNKNOWN: Evidence with critical missing context.
decision_rules:
  - Use only the supplied source text.
source_text_policy: Each record is a standalone synthetic excerpt.
"""
    )
    cases = tmp_path / "holdout.jsonl"
    cases.write_text(
        "\n".join(
            json.dumps(
                {
                    "case_id": f"CASE-{i}",
                    "target": "CD19",
                    "modality": "T-cell engager",
                    "source_text": "public evidence",
                }
            )
            for i in range(8)
        )
        + "\n"
    )
    output = tmp_path / "predictions.json"

    assert main(
        ["--problem", str(problem), "--holdout-data", str(cases), "--output", str(output)]
    ) == 0
    report = json.loads(output.read_text())
    assert report["prediction_count"] == 8
    assert len(report["predictions"]) == 8
    assert all(prediction["gates"] for prediction in report["predictions"])
    assert all(prediction["reason"] for prediction in report["predictions"])


def test_validate_only_parses_problem_and_cases_without_inference(tmp_path, monkeypatch, capsys) -> None:
    problem = tmp_path / "problem.yaml"
    problem.write_text(
        """schema_version: se_holdout_problem_v1
problem_id: validation-smoke
version: 1
title: Synthetic acquisition triage
task: Classify each standalone evidence item.
allowed_dispositions: [INCLUDE, EXCLUDE, UNKNOWN]
labeling_rubric:
  INCLUDE: Decision-relevant human or regulatory evidence.
  EXCLUDE: Irrelevant or non-human evidence.
  UNKNOWN: Evidence with critical missing context.
decision_rules:
  - Use only the supplied source text.
source_text_policy: Each record is a standalone synthetic excerpt.
"""
    )
    cases = tmp_path / "holdout.jsonl"
    cases.write_text(
        json.dumps(
            {
                "case_id": "SYN-001",
                "target": "TARGET-A",
                "modality": "MODALITY-A",
                "source_text": "Synthetic public evidence.",
            }
        )
        + "\n"
    )

    def fail_if_called(*_args, **_kwargs):
        pytest.fail("predict_holdout must not run during --validate-only")

    monkeypatch.setattr("bve.cli.se_holdout_evaluate.predict_holdout", fail_if_called)

    assert main(["--problem", str(problem), "--holdout-data", str(cases), "--validate-only"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report == {
        "problem_id": "validation-smoke",
        "validation_status": "PASS",
        "case_count": 1,
    }


def test_holdout_cli_rejects_buyer_problem_schema(tmp_path) -> None:
    problem = tmp_path / "problem.yaml"
    problem.write_text(
        """schema_version: se_buyer_problem_v2
problem_id: wrong-contract
version: '1.0'
"""
    )
    cases = tmp_path / "holdout.jsonl"
    cases.write_text(
        '{"case_id":"SYN-001","target":"T","modality":"M","source_text":"text"}\n'
    )

    with pytest.raises(ValueError, match="se_holdout_problem_v1"):
        main(["--problem", str(problem), "--holdout-data", str(cases), "--validate-only"])
