from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from bve.pipeline.pipeline_state import PipelineStateStore


def test_pipeline_state_round_trip(tmp_path: Path):
    state_path = tmp_path / "state.json"
    store = PipelineStateStore(state_path)

    company_id = "company-1"
    asset_id = "asset-1"
    fetched_at = datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)

    store.mark_run_started(company_id, asset_id)
    store.mark_document_processed(company_id, asset_id, "doc-1")
    store.mark_event_processed(company_id, asset_id, "evt-1")
    store.set_last_fetch(company_id, asset_id, "press_release", fetched_at)
    store.mark_run_succeeded(company_id, asset_id)
    store.save()

    loaded = PipelineStateStore(state_path)
    assert loaded.seen_document(company_id, asset_id, "doc-1")
    assert loaded.seen_event(company_id, asset_id, "evt-1")
    assert loaded.get_since(company_id, asset_id, "press_release") == fetched_at

    asset_state = loaded.get_asset_state(company_id, asset_id)
    assert asset_state.last_run_started_at is not None
    assert asset_state.last_run_completed_at is not None
    assert asset_state.last_error is None


def test_pipeline_state_records_failures(tmp_path: Path):
    store = PipelineStateStore(tmp_path / "state.json")
    company_id = "company-2"
    asset_id = "asset-2"

    store.mark_run_started(company_id, asset_id)
    store.mark_run_failed(company_id, asset_id, error="connector timeout")
    store.save()

    loaded = PipelineStateStore(tmp_path / "state.json")
    asset_state = loaded.get_asset_state(company_id, asset_id)
    assert asset_state.last_error == "connector timeout"
    assert asset_state.last_run_completed_at is not None
