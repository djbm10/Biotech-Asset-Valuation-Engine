from __future__ import annotations

from datetime import datetime, timezone

from bve.intelligence.knowledge_layer import StoredValuationDiff
from bve.pipeline.change_detector import MaterialChangeDetector, MaterialityRule


def _diff(run_id: str, delta_npv: float, before_npv: float = 100.0) -> StoredValuationDiff:
    return StoredValuationDiff(
        run_id=run_id,
        event_id=f"evt-{run_id}",
        asset_id="asset-1",
        valuation_before={"rnpv_millions": before_npv},
        valuation_after={"rnpv_millions": before_npv + delta_npv},
        delta_npv=delta_npv,
        created_at=datetime(2026, 3, 8, tzinfo=timezone.utc),
    )


def test_material_change_detector_absolute_threshold():
    detector = MaterialChangeDetector(MaterialityRule(min_abs_delta_npv=20.0, min_diff_count=1))
    assert detector.is_material(_diff("run-a", 25.0))
    assert not detector.is_material(_diff("run-b", 5.0))


def test_material_change_detector_relative_threshold():
    detector = MaterialChangeDetector(
        MaterialityRule(
            min_abs_delta_npv=50.0,
            min_relative_delta_npv_pct=10.0,
            min_diff_count=1,
        )
    )
    assert detector.is_material(_diff("run-a", 12.0, before_npv=100.0))
    assert not detector.is_material(_diff("run-b", 5.0, before_npv=100.0))


def test_should_generate_weekly_memo_uses_material_diff_count():
    detector = MaterialChangeDetector(MaterialityRule(min_abs_delta_npv=10.0, min_diff_count=2))
    diffs = [_diff("run-a", 12.0), _diff("run-b", 9.0), _diff("run-c", -15.0)]
    assert detector.should_generate_weekly_memo(diffs)
