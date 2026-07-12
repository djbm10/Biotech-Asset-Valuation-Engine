from __future__ import annotations

import json
from datetime import date

import pytest

from bve.se.acquisition.source_health import SourceHealth, SourceHealthReport
from bve.se.evaluation.production_inference import build_predictions
from bve.se.operations import (
    PRODUCTION_SCREEN_LABEL,
    RevalidationPolicy,
    SEAuditEvent,
    SEMonitoringBaseline,
    append_audit_event,
    build_monitoring_snapshot,
)


def _predictions():
    query = {
        "query_id": "Q1",
        "buyer_id": "B1",
        "strategic_priority": "fit",
        "candidate_ids": ["include", "unknown", "exclude"],
    }
    evidence = [
        {
            "query_id": "Q1",
            "candidate_id": asset,
            "evidence_id": f"E-{asset}",
            "observed_attributes": {
                "fit_signal": fit,
                "development_stage": stage,
                "evidence_completeness": completeness,
            },
        }
        for asset, fit, stage, completeness in (
            ("include", "strong-fit", "Phase 2", "high"),
            ("unknown", "uncertain", "preclinical", "low"),
            ("exclude", "disqualifying", "discontinued", "high"),
        )
    ]
    return build_predictions([query], evidence)


def test_production_label_and_monitoring_snapshot() -> None:
    assert PRODUCTION_SCREEN_LABEL == (
        "Production-validated public-data S&E screen; pre-diligence—not verified truth."
    )
    health = SourceHealthReport(
        sources=[
            SourceHealth(
                source_family="registry",
                connector_succeeded=True,
                query_returned_results=True,
                documents_indexed=3,
            )
        ]
    )
    snapshot = build_monitoring_snapshot(
        run_id="run-1",
        predictions=_predictions(),
        source_health=health,
        baseline=SEMonitoringBaseline(
            unknown_rate=1 / 3,
            citation_failure_rate=0,
            source_failure_rate=0,
        ),
    )
    assert snapshot.unknown_rate == pytest.approx(1 / 3)
    assert snapshot.citation_failure_rate == 0
    assert snapshot.source_failure_rate == 0
    assert snapshot.route_leakage_count == 0
    assert snapshot.performance_drift is False


def test_audit_log_is_append_only_jsonl(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    event = SEAuditEvent(
        event_id="event-1",
        run_id="run-1",
        event_type="screen_completed",
        occurred_at="2026-07-11T20:00:00Z",
        code_version="v6-release",
        evaluator_version="v6",
        specification_hash="a" * 64,
        source_configuration_hash="b" * 64,
    )
    append_audit_event(path, event)
    append_audit_event(path, event.model_copy(update={"event_id": "event-2"}))

    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row["event_id"] for row in rows] == ["event-1", "event-2"]


def test_revalidation_fails_closed_on_changes_or_elapsed_interval() -> None:
    policy = RevalidationPolicy(
        validated_code_hash="a" * 64,
        validated_rubric_hash="b" * 64,
        validated_source_configuration_hash="c" * 64,
        validated_on=date(2026, 7, 11),
        interval_days=180,
    )
    policy.require_current(
        current_code_hash="a" * 64,
        current_rubric_hash="b" * 64,
        current_source_configuration_hash="c" * 64,
        as_of=date(2026, 7, 12),
    )
    with pytest.raises(RuntimeError, match="material code hash changed"):
        policy.require_current(
            current_code_hash="d" * 64,
            current_rubric_hash="b" * 64,
            current_source_configuration_hash="c" * 64,
            as_of=date(2026, 7, 12),
        )
    with pytest.raises(RuntimeError, match="periodic public-source revalidation is due"):
        policy.require_current(
            current_code_hash="a" * 64,
            current_rubric_hash="b" * 64,
            current_source_configuration_hash="c" * 64,
            as_of=date(2027, 1, 7),
        )
