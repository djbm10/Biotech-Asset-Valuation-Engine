from __future__ import annotations

from pathlib import Path

from bve.ops.control_plane import ServiceControlPlane


def test_control_plane_pause_resume_and_stop(tmp_path: Path):
    cp = ServiceControlPlane(tmp_path / "control.json")
    state = cp.load()
    assert state.stop_requested is False
    assert state.paused_stages == []

    paused = cp.pause_stage("ingestion")
    assert "watchlist" in paused.paused_stages
    assert cp.is_stage_paused("watchlist")

    resumed = cp.resume_stage("ingestion")
    assert resumed.paused_stages == []
    assert not cp.is_stage_paused("watchlist")

    stopped = cp.request_stop()
    assert stopped.stop_requested is True
    cleared = cp.clear_stop()
    assert cleared.stop_requested is False
