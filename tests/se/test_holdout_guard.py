from datetime import date, datetime, timezone

import pytest

from bve.se.evaluation.benchmark import evaluate_reference_landscape
from bve.se.pipeline import SESearchResult
from bve.se.schemas.contracts import RunManifest, RunStatus


def test_milestone_evaluator_does_not_open_sealed_holdout(tmp_path) -> None:
    benchmark = tmp_path / "holdout.yaml"
    benchmark.write_text("status: sealed_holdout\nrecords: []\n")
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
            status=RunStatus.CONVERGED,
        )
    )
    with pytest.raises(ValueError, match="sealed holdout"):
        evaluate_reference_landscape(benchmark, result, reference_set="holdout")
