from __future__ import annotations

import hashlib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_validation_fixture_is_frozen_and_hashes_match() -> None:
    root = ROOT / "research/se_benchmarks/cd19_bcma/validation"
    landscape = yaml.safe_load((root / "reference_landscape.yaml").read_text())
    assert landscape["status"] == "frozen_fixture_incomplete_expert_universe"
    assert landscape["precision_evaluable"] is False
    assert landscape["records"]
    for record in landscape["records"]:
        snapshot = root / record["snapshot"]
        assert snapshot.exists(), record["fixture_id"]
        assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == record["snapshot_sha256"]
