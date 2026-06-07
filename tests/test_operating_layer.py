from __future__ import annotations

import tempfile
from datetime import date, datetime, timezone

from bve.intelligence.knowledge_layer import AssetRegistryEntry, KnowledgeStore, SourceTrace
from bve.intelligence.operating_layer import OperatingLayerEngine, OperatingLayerValue
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument
from bve.ops.data_quality import DataQualityCheck, DataQualityScore
from bve.ops.metrics_dashboard import MetricsDashboardSnapshot


def _store() -> KnowledgeStore:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    return KnowledgeStore(tmp.name)


def test_phase_o_builds_auditable_operating_surface() -> None:
    store = _store()
    try:
        store.upsert_asset_registry_entry(
            AssetRegistryEntry(
                asset_id="asset-1",
                ticker="AAA",
                company_id="co-1",
                therapeutic_area="oncology",
                modality="small_molecule",
                stage="phase_2",
                source="unit_test",
            )
        )
        raw = RawDocument.from_text(
            id="doc-1",
            source="press_release",
            title="Asset update",
            raw_text="payload",
            source_url="https://example.org/doc-1",
            retrieved_at=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
            published_at=datetime(2026, 4, 18, 11, 0, tzinfo=timezone.utc),
            entity_hints=EntityHints(asset_id="asset-1", company_id="co-1"),
        )
        store.add_raw_document(raw, SourceTrace(source_type="unit_test", source_ref="doc-1"))
        store.log_data_quality(
            DataQualityScore(
                asset_id="asset-1",
                overall_score=0.40,
                checks=[
                    DataQualityCheck(
                        check_type="doc_freshness",
                        asset_id="asset-1",
                        value=5.0,
                        threshold="<=3d",
                        passed=False,
                        severity="warning",
                        reason="stale_source_documents",
                    )
                ],
                failing_checks=["doc_freshness"],
                gated=True,
                generated_at=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
            ),
            run_id="run-1",
        )
        store._append_audit_log(
            event_type="review_decision",
            entity_type="proposal",
            entity_id="prop-1",
            actor_id="analyst@test",
            action="accepted",
            payload_json='{"status":"accepted"}',
            assumption_field="override_value",
            evidence_signal_id="sig-1",
            review_decision_id="review-1",
        )

        assessment = OperatingLayerEngine().build(
            store=store,
            dashboard_snapshot=MetricsDashboardSnapshot(
                as_of_date=date(2026, 4, 18),
                generated_at=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
                health_checks=[],
            ),
            provenance_record_type="raw_documents",
            provenance_record_id="doc-1",
            previous_scenario={"pos": 0.40, "peak_sales": 900.0},
            current_scenario={"pos": 0.52, "peak_sales": 1100.0},
            freshness=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        )
        value = OperatingLayerValue.model_validate(assessment.output.value)

        assert value.model_registry
        assert value.stale_input_dashboard
        assert value.alert_audit_log
        assert value.provenance_viewer is not None
        assert value.provenance_viewer["record_type"] == "raw_documents"
        assert len(value.scenario_diff_viewer) == 2
        pos_diff = next(item for item in value.scenario_diff_viewer if item.field == "pos")
        assert pos_diff.delta == 0.12
        assert value.asset_registry_summary[0]["asset_id"] == "asset-1"
        assert assessment.output.confidence >= 0.55
    finally:
        store.close()


def test_phase_o_handles_empty_optional_surfaces() -> None:
    store = _store()
    try:
        assessment = OperatingLayerEngine().build(
            store=store,
            dashboard_snapshot=MetricsDashboardSnapshot(
                as_of_date=date(2026, 4, 18),
                generated_at=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
                health_checks=[],
            ),
            provenance_record_type=None,
            provenance_record_id=None,
            previous_scenario=None,
            current_scenario=None,
            freshness=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        )
        value = OperatingLayerValue.model_validate(assessment.output.value)
        assert value.provenance_viewer is None
        assert value.scenario_diff_viewer == []
        assert assessment.plain_english_summary
    finally:
        store.close()
