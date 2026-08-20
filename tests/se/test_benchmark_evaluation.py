from __future__ import annotations

from datetime import date, datetime, timezone
from bve.se.evaluation.benchmark import evaluate_reference_landscape
from bve.se.pipeline import SESearchResult
from bve.se.schemas.contracts import CanonicalAsset, RunManifest, RunStatus


def test_benchmark_evaluator_reports_recall_and_missing_reference_assets(tmp_path) -> None:
    benchmark = tmp_path / "reference.yaml"
    benchmark.write_text(
        """records:\n  - fixture_id: a\n    canonical_asset: Asset A\n    expected_candidate: true\n  - fixture_id: b\n    canonical_asset: Asset B\n    expected_candidate: true\n"""
    )
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
        ),
        candidates=[CanonicalAsset(asset_id="asset:a", canonical_name="Asset A")],
    )
    report = evaluate_reference_landscape(benchmark, result, reference_set="development")
    assert report.candidate_metrics.recall == 0.5
    assert report.failures[0].canonical_asset == "Asset B"
    assert report.precision_evaluable is False
    assert report.release_eligible is False
