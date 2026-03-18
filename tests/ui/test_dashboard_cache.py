from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from bve.ui.dashboard.cache import DashboardCacheStore
from bve.ui.dashboard.dashboard_app import format_cache_metadata_text


def test_dashboard_cache_metadata_contract_round_trip(tmp_path: Path):
    store = DashboardCacheStore(tmp_path / "cache.json")
    generated_at = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    record = store.write(
        source_run_id="run-1",
        source_model_version="model-v1",
        generated_at=generated_at,
        payload={"x": 1},
    )
    loaded = store.read()
    assert loaded is not None
    assert loaded.metadata.cache_version == "1"
    assert loaded.metadata.source_run_id == "run-1"
    assert loaded.metadata.source_model_version == "model-v1"
    assert loaded.metadata.generated_at == generated_at

    text = format_cache_metadata_text(loaded.metadata)
    assert "cache_version=1" in text
    assert "source_run_id=run-1" in text
    assert "source_model_version=model-v1" in text
    assert "generated_at=2026-03-09T12:00:00+00:00" in text


def test_dashboard_cache_version_increments(tmp_path: Path):
    store = DashboardCacheStore(tmp_path / "cache.json")
    store.write(
        source_run_id="run-1",
        source_model_version="model-v1",
        payload={"a": 1},
    )
    rec2 = store.write(
        source_run_id="run-2",
        source_model_version="model-v1",
        payload={"a": 2},
    )
    assert rec2.metadata.cache_version == "2"
