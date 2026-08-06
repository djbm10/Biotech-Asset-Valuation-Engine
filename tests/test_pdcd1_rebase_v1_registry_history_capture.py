from __future__ import annotations

import importlib.util
import json
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def latest_finalized_snapshot(module) -> Path:
    snapshots = [
        p
        for p in module.STAGE_ROOT.iterdir()
        if p.is_dir() and p.name != "_staging" and (p / "receipt.json").is_file()
    ]
    assert snapshots, "no finalized snapshot present; run scripts/capture_pdcd1_rebase_v1_registry_history.py first"
    return sorted(snapshots, key=lambda p: p.stat().st_mtime)[-1]


def prerequisite_dir(module) -> Path:
    return (
        ROOT
        / "artifacts"
        / "pipeline"
        / "pdcd1_rebase_v1"
        / "stages"
        / "01_population_capture"
        / "prerequisite_download"
        / "extracted"
    )


def test_prerequisite_validation_rejects_wrong_snapshot_id(tmp_path):
    module = load("capture_pdcd1_rebase_v1_registry_history.py")
    src = prerequisite_dir(module)
    dest = tmp_path / "prereq"
    dest.mkdir()
    for name in ("manifest.json", "receipt.json"):
        (dest / name).write_text((src / name).read_text())
    (dest / "source").mkdir()
    (dest / "source" / "benchmark_population.json").write_text(
        (src / "source" / "benchmark_population.json").read_text()
    )
    receipt = json.loads((dest / "receipt.json").read_text())
    receipt["snapshot_id"] = "not_the_real_snapshot_id"
    (dest / "receipt.json").write_text(json.dumps(receipt))
    try:
        module.load_prerequisite(dest)
    except ValueError as exc:
        assert "PREREQUISITE_SNAPSHOT_ID_MISMATCH" in str(exc)
    else:
        raise AssertionError("mismatched prerequisite snapshot id was accepted")


def test_frozen_study_set_matches_milestone1_population():
    module = load("capture_pdcd1_rebase_v1_registry_history.py")
    prereq = module.load_prerequisite(prerequisite_dir(module))
    snapshot = latest_finalized_snapshot(module)
    staging_manifest = json.loads((snapshot / "input" / "staging_manifest.json").read_text())
    assert staging_manifest["nct_ids"] == sorted(prereq["nct_ids"])
    assert staging_manifest["nct_ids_count"] == len(prereq["nct_ids"]) == 81


def test_history_index_ledger_has_one_row_per_study():
    module = load("capture_pdcd1_rebase_v1_registry_history.py")
    snapshot = latest_finalized_snapshot(module)
    lines = (snapshot / "normalized" / "history_index_ledger.jsonl").read_text().splitlines()
    rows = [json.loads(line) for line in lines]
    assert len(rows) == 81
    assert len({r["nct_id"] for r in rows}) == 81


def test_version_enumeration_matches_declared_changes_count():
    module = load("capture_pdcd1_rebase_v1_registry_history.py")
    snapshot = latest_finalized_snapshot(module)
    manifest = json.loads((snapshot / "manifest.json").read_text())
    checks = manifest["checks"]
    assert checks["versions_expected_vs_captured_delta"] == 0
    assert checks["versions_captured"] == checks["versions_expected_from_index"]


def test_current_record_captured_independently_of_history_versions():
    module = load("capture_pdcd1_rebase_v1_registry_history.py")
    snapshot = latest_finalized_snapshot(module)
    lines = (snapshot / "normalized" / "current_ledger.jsonl").read_text().splitlines()
    rows = [json.loads(line) for line in lines]
    assert len(rows) == 81
    for row in rows:
        assert row["status"] in {"CAPTURED", "NOT_AVAILABLE", "ACCESS_BLOCKED", "RETRYABLE_FAILURE", "TERMINAL_FAILURE"}


def test_no_duplicate_or_missing_versions_per_study():
    module = load("capture_pdcd1_rebase_v1_registry_history.py")
    snapshot = latest_finalized_snapshot(module)
    lines = (snapshot / "normalized" / "version_ledger.jsonl").read_text().splitlines()
    rows = [json.loads(line) for line in lines]
    seen = set()
    for row in rows:
        key = (row["nct_id"], row["version"])
        assert key not in seen, f"duplicate version row: {key}"
        seen.add(key)


def test_raw_bytes_hash_matches_receipt_bindings():
    module = load("capture_pdcd1_rebase_v1_registry_history.py")
    snapshot = latest_finalized_snapshot(module)
    result = module.validate_snapshot(snapshot)
    assert result["receipt"]["status"] == "FINALIZED"
    assert result["mismatches"] == []


def test_receipt_rejects_mutated_artifact(tmp_path):
    module = load("capture_pdcd1_rebase_v1_registry_history.py")
    source = latest_finalized_snapshot(module)
    dest = tmp_path / "snapshot"
    dest.mkdir()
    for path in source.rglob("*"):
        if path.is_file() and "export" not in path.relative_to(source).parts:
            rel = path.relative_to(source)
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            (dest / rel).write_bytes(path.read_bytes())
    target = dest / "normalized" / "version_ledger.jsonl"
    target.write_bytes(target.read_bytes() + b"\n")
    try:
        module.validate_snapshot(dest)
    except ValueError as exc:
        assert "ARTIFACT_HASH_MISMATCH" in str(exc)
    else:
        raise AssertionError("mutated artifact was accepted as valid")


def test_normalized_ledger_is_extraction_metadata_only():
    module = load("capture_pdcd1_rebase_v1_registry_history.py")
    snapshot = latest_finalized_snapshot(module)
    lines = (snapshot / "normalized" / "version_ledger.jsonl").read_text().splitlines()
    rows = [json.loads(line) for line in lines]
    forbidden_keys = {"candidate_id", "alias", "canonical_candidate", "owner", "label", "benchmark_label"}
    for row in rows:
        assert not (forbidden_keys & set(row.keys()))


def test_manifest_declares_capture_only_scope():
    module = load("capture_pdcd1_rebase_v1_registry_history.py")
    snapshot = latest_finalized_snapshot(module)
    manifest = json.loads((snapshot / "manifest.json").read_text())
    assert manifest["adjudication_performed"] is False
    assert manifest["candidate_identities_derived"] is False
    assert manifest["aliases_derived"] is False
    assert manifest["benchmark_labels_created"] is False
    assert manifest["predictions_generated"] is False
    assert manifest["evaluation_performed"] is False
    assert manifest["lineage"] == "REPRODUCIBLE_BIOTECH_PIPELINE_REBASE_V1"
    assert manifest["canonical_target"] == "PDCD1"


def test_manifest_binds_milestone1_prerequisite_identity():
    module = load("capture_pdcd1_rebase_v1_registry_history.py")
    snapshot = latest_finalized_snapshot(module)
    manifest = json.loads((snapshot / "manifest.json").read_text())
    prereq = manifest["milestone1_prerequisite"]
    assert prereq["snapshot_id"] == "47e9e791f48bb7aacc467e28"
    assert prereq["archive_sha256"] == "7a6b509d42de915a0e0e8e5dfc054c23ffab4e6a3cfa5409acda1a45fae00923"
    assert prereq["nct_ids_count"] == 81


def test_no_machine_specific_absolute_paths_in_manifest_or_ledgers():
    module = load("capture_pdcd1_rebase_v1_registry_history.py")
    snapshot = latest_finalized_snapshot(module)
    text = (snapshot / "manifest.json").read_text()
    text += (snapshot / "normalized" / "version_ledger.jsonl").read_text()
    assert "/tmp/" not in text
    assert str(ROOT) not in text


def test_already_finalized_short_circuits_without_network_access(monkeypatch):
    module = load("capture_pdcd1_rebase_v1_registry_history.py")
    monkeypatch.setattr(
        module.urllib.request,
        "urlopen",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("network access attempted during resumability check")),
    )
    snapshot = latest_finalized_snapshot(module)
    manifest = json.loads((snapshot / "manifest.json").read_text())
    found = module.find_finalized_snapshot_by_staging_key(manifest["staging_key"])
    assert found is not None
    result = module.validate_snapshot(found)
    assert result["receipt"]["status"] == "FINALIZED"


def test_export_archive_extracts_and_revalidates():
    module = load("capture_pdcd1_rebase_v1_registry_history.py")
    snapshot = latest_finalized_snapshot(module)
    export_dir = snapshot / "export"
    tar_paths = list(export_dir.glob("*.tar.gz"))
    assert len(tar_paths) == 1
    tar_path = tar_paths[0]
    checksum_file = tar_path.with_suffix(tar_path.suffix + ".sha256")
    expected_sha, _, name = checksum_file.read_text().strip().partition("  ")
    assert name == tar_path.name
    import hashlib

    assert hashlib.sha256(tar_path.read_bytes()).hexdigest() == expected_sha
    receipt = json.loads((snapshot / "receipt.json").read_text())
    result = module.revalidate_export(tar_path, receipt)
    assert result["revalidated"] is True
    assert result["mismatches"] == []


def test_export_archive_contains_no_export_directory_recursion():
    module = load("capture_pdcd1_rebase_v1_registry_history.py")
    snapshot = latest_finalized_snapshot(module)
    tar_path = next((snapshot / "export").glob("*.tar.gz"))
    with tarfile.open(tar_path, "r:gz") as tar:
        names = tar.getnames()
    assert not any(name.startswith("export/") for name in names)


def test_stage_does_not_perform_adjudication_prediction_or_scoring():
    module = load("capture_pdcd1_rebase_v1_registry_history.py")
    defined_names = {name.casefold() for name in vars(module)}
    for forbidden in ("adjudicate", "predict", "score", "evaluate_candidate", "create_benchmark_label"):
        assert forbidden not in defined_names
