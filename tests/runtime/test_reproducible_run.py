"""Tests for run context, artifact store, and observability."""

import json
import pytest
import tempfile
from datetime import datetime
from pathlib import Path

from bve.runtime.run_context import RunContext, RunMetadata, _dict_hash
from bve.runtime.artifact_store import ArtifactStore
from bve.runtime.observability import RunObserver


class TestRunMetadata:
    def test_run_id_is_unique(self):
        m1 = RunMetadata()
        m2 = RunMetadata()
        assert m1.run_id != m2.run_id

    def test_to_dict_has_required_keys(self):
        m = RunMetadata()
        d = m.to_dict()
        assert "run_id" in d
        assert "git_commit" in d
        assert "model_version" in d
        assert "started_at" in d

    def test_config_hash_deterministic(self):
        config = {"discount_rate": 0.10, "peak_penetration": 0.25}
        h1 = _dict_hash(config)
        h2 = _dict_hash(config)
        assert h1 == h2

    def test_config_hash_differs_for_different_config(self):
        c1 = {"discount_rate": 0.10}
        c2 = {"discount_rate": 0.12}
        assert _dict_hash(c1) != _dict_hash(c2)


class TestRunContext:
    def test_run_id_accessible(self):
        ctx = RunContext()
        assert len(ctx.run_id) > 0

    def test_record_failure(self):
        ctx = RunContext()
        ctx.record_failure("VKTX", "No price data available")
        obs = ctx.to_observation_dict()
        assert len(obs["failed_assets"]) == 1

    def test_record_stale_warning(self):
        ctx = RunContext()
        ctx.record_stale_warning("market_model.peak_penetration")
        obs = ctx.to_observation_dict()
        assert "market_model.peak_penetration" in obs["stale_data_warnings"]

    def test_record_score_delta(self):
        ctx = RunContext()
        ctx.record_score_delta("VKTX", 0.05)
        obs = ctx.to_observation_dict()
        assert obs["score_deltas"]["VKTX"] == 0.05

    def test_duration_computed_after_complete(self):
        ctx = RunContext()
        ctx.complete()
        assert ctx.duration_seconds is not None
        assert ctx.duration_seconds >= 0.0

    def test_duration_none_before_complete(self):
        ctx = RunContext()
        assert ctx.duration_seconds is None

    def test_config_hash_stored(self):
        config = {"discount_rate": 0.10}
        ctx = RunContext(config=config)
        assert ctx.metadata.config_hash is not None

    def test_user_id_propagated(self):
        ctx = RunContext(user_id="alice")
        assert ctx.metadata.user_id == "alice"

    def test_observation_dict_complete(self):
        ctx = RunContext()
        ctx.record_failure("ALNY", "config missing")
        ctx.complete()
        obs = ctx.to_observation_dict()
        assert "run_id" in obs
        assert "completed_at" in obs
        assert "failed_assets" in obs
        assert "duration_seconds" in obs


class TestArtifactStore:
    def test_save_and_load(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        ctx = RunContext()
        ctx.complete()
        output = {"rnpv": 250.0, "ticker": "VKTX"}
        run_dir = store.save(ctx, output)
        assert (run_dir / "output.json").exists()
        loaded = store.load(ctx.run_id)
        assert loaded["rnpv"] == 250.0

    def test_save_provenance(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        ctx = RunContext()
        ctx.complete()
        store.save(ctx, {})
        prov = store.load_provenance(ctx.run_id)
        assert prov is not None
        assert prov["run_id"] == ctx.run_id

    def test_save_extra_files(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        ctx = RunContext()
        ctx.complete()
        store.save(ctx, {}, extra_files={"memo.md": "# Memo"})
        memo_path = tmp_path / ctx.run_id / "memo.md"
        assert memo_path.exists()
        assert memo_path.read_text() == "# Memo"

    def test_exists_true_after_save(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        ctx = RunContext()
        ctx.complete()
        store.save(ctx, {})
        assert store.exists(ctx.run_id)

    def test_exists_false_for_unknown(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        assert not store.exists("nonexistent-run-id")

    def test_list_runs(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        for _ in range(3):
            ctx = RunContext()
            ctx.complete()
            store.save(ctx, {})
        assert len(store.list_runs()) == 3

    def test_load_returns_none_for_unknown(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        assert store.load("nonexistent") is None


class TestRunObserver:
    def test_observe_creates_observation(self):
        ctx = RunContext()
        ctx.record_failure("VKTX", "error")
        ctx.record_stale_warning("field")
        ctx.record_score_delta("ALNY", 0.05)
        ctx.record_score_delta("VKTX", -0.03)
        ctx.complete()
        observer = RunObserver()
        obs = observer.observe(ctx)
        assert obs.run_id == ctx.run_id
        assert obs.failed_count == 1
        assert obs.stale_warning_count == 1
        assert obs.asset_count == 2
        assert obs.score_delta_mean is not None

    def test_format_summary_contains_run_id(self):
        ctx = RunContext()
        ctx.complete()
        observer = RunObserver()
        obs = observer.observe(ctx)
        summary = observer.format_summary(obs)
        assert ctx.run_id in summary

    def test_duration_after_complete(self):
        ctx = RunContext()
        ctx.complete()
        observer = RunObserver()
        obs = observer.observe(ctx)
        assert obs.duration_seconds is not None
        assert obs.duration_seconds >= 0
