from __future__ import annotations

import hashlib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "research/se_benchmarks/cd19_bcma/development"


def test_development_reference_snapshots_exist_and_match_hashes() -> None:
    landscape = yaml.safe_load((BENCHMARK / "reference_landscape.yaml").read_text())
    assert landscape["records"]
    for record in landscape["records"]:
        snapshot = BENCHMARK / record["snapshot"]
        assert snapshot.exists(), record["fixture_id"]
        digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        assert digest == record["snapshot_sha256"]


def test_parallel_cd19_bcma_trial_is_not_labeled_dual_target_asset() -> None:
    records = yaml.safe_load((BENCHMARK / "reference_landscape.yaml").read_text())["records"]
    parallel = [record for record in records if record["trial_id"] == "NCT07689149"]
    assert {tuple(record["expected_target_ids"]) for record in parallel} == {("CD19",), ("BCMA",)}
    assert all(record["expected_dual_target_same_asset"] is False for record in parallel)
