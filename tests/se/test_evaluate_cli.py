from __future__ import annotations

import json
from datetime import date, datetime, timezone

from bve.cli.se_evaluate import main
from bve.se.pipeline import SESearchResult
from bve.se.schemas.contracts import RunManifest, RunStatus


def test_evaluate_cli_writes_machine_readable_report(tmp_path) -> None:
    benchmark = tmp_path / "reference.yaml"
    benchmark.write_text(
        """records:\n  - fixture_id: a\n    canonical_asset: Asset A\n    expected_candidate: true\n"""
    )
    result_path = tmp_path / "result.json"
    result = SESearchResult(
        problem_id="p",
        run_manifest=RunManifest(
            run_id="r",
            problem_id="p",
            problem_version="1",
            as_of_date=date(2026, 7, 10),
            started_at=datetime.now(timezone.utc),
            code_version="test",
            normalization_version="test",
            ontology_version="chembl_36__open_targets_26.06__resolver_v1__modality_v2",
            status=RunStatus.CONVERGED,
        )
    )
    result_path.write_text(result.model_dump_json())
    output = tmp_path / "evaluation.json"
    assert main(
        [
            "--benchmark",
            str(benchmark),
            "--result",
            str(result_path),
            "--output",
            str(output),
        ]
    ) == 0
    report = json.loads(output.read_text())
    assert report["reference_set"] == "validation"
