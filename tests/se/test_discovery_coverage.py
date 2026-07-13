from __future__ import annotations

from pathlib import Path

from bve.se.evaluation.discovery_coverage import evaluate_discovery_coverage
from bve.se.pipeline import SESearchResult
from bve.se.schemas.contracts import CanonicalAsset, RunManifest, RunStatus


def _result() -> SESearchResult:
    return SESearchResult(
        problem_id="p",
        run_manifest=RunManifest(
            run_id="r",
            problem_id="p",
            problem_version="1",
            as_of_date="2026-07-12",
            started_at="2026-07-12T12:00:00Z",
            completed_at="2026-07-12T12:01:00Z",
            code_version="test",
            normalization_version="test",
            status=RunStatus.CONVERGED,
        ),
        candidates=[
            CanonicalAsset(
                asset_id="asset:1",
                canonical_name="TNB-383B",
                aliases=["ABBV 383", "TNB383B"],
            ),
            CanonicalAsset(asset_id="asset:2", canonical_name="CLN-978"),
        ],
    )


def test_reference_aliases_measure_output_without_entering_discovery(tmp_path: Path) -> None:
    reference = tmp_path / "reference.csv"
    reference.write_text(
        "benchmark_id,canonical_asset,aliases,reference_tier\n"
        "A,ABBV-383,TNB-383B|TNB383B,GOLD\n"
        "B,CLN-978,CLN978,SILVER\n"
        "C,Missing-1,MISSING1,SILVER\n"
    )

    report = evaluate_discovery_coverage(_result(), reference)

    assert report.total_covered == 2
    assert report.recall == 2 / 3
    assert report.gold_covered == 1
    assert report.assets[0].matched_asset_ids == ("asset:1",)
    assert report.meets_release_thresholds() is True
