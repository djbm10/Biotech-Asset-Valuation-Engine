from __future__ import annotations

import json

from bve.cli.se_holdout_evaluate import main


def test_holdout_cli_emits_one_prediction_per_case(tmp_path) -> None:
    problem = tmp_path / "problem.yaml"
    problem.write_text(
        """schema_version: se_buyer_problem_v2
problem_id: smoke
version: '1.0'
buyer:
  buyer_id: buyer
  name: Buyer
  as_of_date: '2026-07-11'
strategic_gap:
  therapeutic_areas: [oncology]
  target_expression:
    operator: ANY
    targets: [{canonical_id: CD19, label: CD19, aliases: []}]
  modalities: [T_CELL_ENGAGER]
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
