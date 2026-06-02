"""
Tests for RunContext + capture_run_context (Block 2J).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bve.run.run_context import (
    RunContext,
    capture_run_context,
    compare_contexts,
)

_TODAY = "2026-06-02"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(**kwargs) -> RunContext:
    defaults = dict(
        started_at="2026-06-02T00:00:00+00:00",
        git_commit="abc1234",
        git_dirty=False,
        pipeline_versions={"classifier": "v2.1", "schema": "v1.2"},
        as_of_date="2026-06-02",
        score_mode="provisional",
        lookback_days=3,
        ingest_live=False,
        input_hashes={"targets": "deadbeef12345678"},
        python_version="3.12.0",
    )
    defaults.update(kwargs)
    return RunContext(**defaults)


# ---------------------------------------------------------------------------
# 1. capture_run_context
# ---------------------------------------------------------------------------

class TestCaptureRunContext:
    def test_returns_run_context(self):
        ctx = capture_run_context(as_of_date=_TODAY)
        assert isinstance(ctx, RunContext)

    def test_as_of_date_set(self):
        ctx = capture_run_context(as_of_date=_TODAY)
        assert ctx.as_of_date == _TODAY

    def test_score_mode_propagated(self):
        ctx = capture_run_context(as_of_date=_TODAY, score_mode="approved_only")
        assert ctx.score_mode == "approved_only"

    def test_lookback_days_propagated(self):
        ctx = capture_run_context(as_of_date=_TODAY, lookback_days=7)
        assert ctx.lookback_days == 7

    def test_ingest_live_propagated(self):
        ctx = capture_run_context(as_of_date=_TODAY, ingest_live=True)
        assert ctx.ingest_live is True

    def test_pipeline_versions_populated(self):
        ctx = capture_run_context(as_of_date=_TODAY)
        assert "classifier" in ctx.pipeline_versions
        assert "schema" in ctx.pipeline_versions

    def test_python_version_populated(self):
        ctx = capture_run_context(as_of_date=_TODAY)
        assert ctx.python_version.startswith("3.")

    def test_git_commit_non_empty(self):
        ctx = capture_run_context(as_of_date=_TODAY)
        assert ctx.git_commit  # may be "unknown" in CI but must be non-empty

    def test_started_at_is_iso_datetime(self):
        ctx = capture_run_context(as_of_date=_TODAY)
        assert "T" in ctx.started_at

    def test_missing_input_file_recorded_as_missing(self, tmp_path):
        ctx = capture_run_context(
            as_of_date=_TODAY,
            input_files={"targets": str(tmp_path / "nonexistent.yaml")},
        )
        assert ctx.input_hashes["targets"] == "missing"

    def test_existing_input_file_hashed(self, tmp_path):
        p = tmp_path / "targets.yaml"
        p.write_text("targets: []\n")
        ctx = capture_run_context(
            as_of_date=_TODAY,
            input_files={"targets": str(p)},
        )
        assert ctx.input_hashes["targets"] != "missing"
        assert len(ctx.input_hashes["targets"]) == 16  # first 16 hex chars

    def test_two_different_files_different_hashes(self, tmp_path):
        p1 = tmp_path / "a.yaml"
        p2 = tmp_path / "b.yaml"
        p1.write_text("content: A\n")
        p2.write_text("content: B\n")
        ctx = capture_run_context(
            as_of_date=_TODAY,
            input_files={"a": str(p1), "b": str(p2)},
        )
        assert ctx.input_hashes["a"] != ctx.input_hashes["b"]

    def test_same_file_same_hash(self, tmp_path):
        p = tmp_path / "targets.yaml"
        p.write_text("targets: []\n")
        ctx1 = capture_run_context(as_of_date=_TODAY, input_files={"t": str(p)})
        ctx2 = capture_run_context(as_of_date=_TODAY, input_files={"t": str(p)})
        assert ctx1.input_hashes["t"] == ctx2.input_hashes["t"]


# ---------------------------------------------------------------------------
# 2. mark_completed
# ---------------------------------------------------------------------------

class TestMarkCompleted:
    def test_completed_at_set(self):
        ctx = capture_run_context(as_of_date=_TODAY)
        assert ctx.completed_at is None
        completed = ctx.mark_completed()
        assert completed.completed_at is not None

    def test_mark_completed_does_not_mutate_original(self):
        ctx = capture_run_context(as_of_date=_TODAY)
        completed = ctx.mark_completed()
        assert ctx.completed_at is None
        assert completed.completed_at is not None

    def test_completed_at_is_iso_datetime(self):
        ctx = capture_run_context(as_of_date=_TODAY).mark_completed()
        assert "T" in ctx.completed_at


# ---------------------------------------------------------------------------
# 3. Save / load round-trip
# ---------------------------------------------------------------------------

class TestSaveLoad:
    def test_save_creates_file(self, tmp_path):
        ctx = capture_run_context(as_of_date=_TODAY)
        out = tmp_path / "run_context.json"
        ctx.save(out)
        assert out.exists()

    def test_load_round_trip_preserves_as_of(self, tmp_path):
        ctx = capture_run_context(as_of_date=_TODAY)
        out = tmp_path / "run_context.json"
        ctx.save(out)
        loaded = RunContext.load(out)
        assert loaded.as_of_date == ctx.as_of_date

    def test_load_round_trip_preserves_git_commit(self, tmp_path):
        ctx = capture_run_context(as_of_date=_TODAY)
        out = tmp_path / "run_context.json"
        ctx.save(out)
        loaded = RunContext.load(out)
        assert loaded.git_commit == ctx.git_commit

    def test_load_round_trip_preserves_pipeline_versions(self, tmp_path):
        ctx = capture_run_context(as_of_date=_TODAY)
        out = tmp_path / "run_context.json"
        ctx.save(out)
        loaded = RunContext.load(out)
        assert loaded.pipeline_versions == ctx.pipeline_versions

    def test_save_writes_valid_json(self, tmp_path):
        ctx = capture_run_context(as_of_date=_TODAY)
        out = tmp_path / "run_context.json"
        ctx.save(out)
        parsed = json.loads(out.read_text())
        assert "as_of_date" in parsed
        assert "pipeline_versions" in parsed

    def test_to_dict_serialisable(self):
        ctx = capture_run_context(as_of_date=_TODAY)
        d = ctx.to_dict()
        json.dumps(d)  # must not raise


# ---------------------------------------------------------------------------
# 4. compare_contexts
# ---------------------------------------------------------------------------

class TestCompareContexts:
    def test_identical_contexts_no_changes(self):
        ctx = _ctx()
        diff = compare_contexts(ctx, ctx)
        assert diff["changed"] == []

    def test_different_git_commit_flagged(self):
        a = _ctx(git_commit="aaa")
        b = _ctx(git_commit="bbb")
        diff = compare_contexts(a, b)
        assert "git_commit" in diff["changed"]

    def test_different_as_of_flagged(self):
        a = _ctx(as_of_date="2026-06-01")
        b = _ctx(as_of_date="2026-06-02")
        diff = compare_contexts(a, b)
        assert "as_of_date" in diff["changed"]

    def test_different_score_mode_flagged(self):
        a = _ctx(score_mode="approved_only")
        b = _ctx(score_mode="provisional")
        diff = compare_contexts(a, b)
        assert "score_mode" in diff["changed"]

    def test_different_pipeline_version_flagged(self):
        a = _ctx(pipeline_versions={"classifier": "v1.0"})
        b = _ctx(pipeline_versions={"classifier": "v2.0"})
        diff = compare_contexts(a, b)
        assert "pipeline_versions.classifier" in diff["changed"]

    def test_different_input_hash_flagged(self):
        a = _ctx(input_hashes={"targets": "aaaa"})
        b = _ctx(input_hashes={"targets": "bbbb"})
        diff = compare_contexts(a, b)
        assert "input_hashes.targets" in diff["changed"]

    def test_same_values_in_same_list(self):
        a = _ctx(score_mode="provisional")
        b = _ctx(score_mode="provisional")
        diff = compare_contexts(a, b)
        assert "score_mode" in diff["same"]
