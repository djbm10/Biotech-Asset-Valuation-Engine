from __future__ import annotations

from datetime import date, datetime, timezone

from bve.se.pipeline import SESearchResult
from bve.se.reporting.memo import render_search_memo
from bve.se.schemas.contracts import CanonicalAsset, RunManifest, RunStatus, SearchOutcome


def test_memo_has_three_groups_coverage_and_pre_diligence_label() -> None:
    asset = CanonicalAsset(asset_id="asset:1", canonical_name="Asset A")
    result = SESearchResult(
        problem_id="problem:1",
        run_manifest=RunManifest(
            run_id="run:1",
            problem_id="problem:1",
            problem_version="1",
            as_of_date=date(2026, 7, 10),
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            code_version="test",
            normalization_version="test",
            source_status={"clinicaltrials_gov": SearchOutcome.SUCCESS},
            status=RunStatus.CONVERGED,
        ),
        candidates=[asset],
        unresolved_asset_ids=[asset.asset_id],
    )
    memo = render_search_memo(result)
    assert "Production-validated public-data S&E screen; pre-diligence—not verified truth." in memo
    assert "Eligible and ranked" in memo
    assert "Confirmed exclusions" in memo
    assert "Unresolved — analyst research required" in memo
    assert "clinicaltrials_gov" in memo
