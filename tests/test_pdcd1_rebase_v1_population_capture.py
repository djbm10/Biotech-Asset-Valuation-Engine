from __future__ import annotations

import hashlib
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


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def latest_finalized_snapshot(module) -> Path:
    snapshots = [p for p in module.STAGE_ROOT.iterdir() if p.is_dir() and (p / "receipt.json").is_file()]
    assert snapshots, "no finalized snapshot present; run scripts/capture_pdcd1_rebase_v1_population.py first"
    return sorted(snapshots, key=lambda p: p.stat().st_mtime)[-1]


def test_manifest_declares_capture_only_scope():
    module = load("capture_pdcd1_rebase_v1_population.py")
    snapshot = latest_finalized_snapshot(module)
    manifest = json.loads((snapshot / "manifest.json").read_text())
    assert manifest["adjudication_performed"] is False
    assert manifest["predictions_generated"] is False
    assert manifest["evaluation_performed"] is False
    assert manifest["lineage"] == "REPRODUCIBLE_BIOTECH_PIPELINE_REBASE_V1"
    assert manifest["canonical_target"] == "PDCD1"


def test_receipt_hashes_match_files_on_disk():
    module = load("capture_pdcd1_rebase_v1_population.py")
    snapshot = latest_finalized_snapshot(module)
    result = module.validate_snapshot(snapshot)
    assert result["receipt"]["status"] == "FINALIZED"


def test_receipt_rejects_mutated_artifact(tmp_path):
    module = load("capture_pdcd1_rebase_v1_population.py")
    source = latest_finalized_snapshot(module)
    dest = tmp_path / "snapshot"
    dest.mkdir()
    for path in source.rglob("*"):
        if path.is_file():
            rel = path.relative_to(source)
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            (dest / rel).write_bytes(path.read_bytes())
    target = dest / "source" / "benchmark_population.json"
    target.write_bytes(target.read_bytes() + b" ")
    try:
        module.validate_snapshot(dest)
    except ValueError as exc:
        assert "ARTIFACT_HASH_MISMATCH" in str(exc)
    else:
        raise AssertionError("mutated artifact was accepted as valid")


def test_receipt_rejects_missing_artifact(tmp_path):
    module = load("capture_pdcd1_rebase_v1_population.py")
    source = latest_finalized_snapshot(module)
    dest = tmp_path / "snapshot"
    dest.mkdir()
    for path in source.rglob("*"):
        if path.is_file():
            rel = path.relative_to(source)
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            (dest / rel).write_bytes(path.read_bytes())
    (dest / "source" / "current_page_1.json").unlink()
    try:
        module.validate_snapshot(dest)
    except ValueError as exc:
        assert "MISSING_ARTIFACT" in str(exc)
    else:
        raise AssertionError("missing artifact was accepted as valid")


def test_no_duplicate_studies_or_intervention_rows():
    module = load("capture_pdcd1_rebase_v1_population.py")
    snapshot = latest_finalized_snapshot(module)
    manifest = json.loads((snapshot / "manifest.json").read_text())
    checks = manifest["checks"]
    assert checks["captured_page_duplicate_nct_ids"] == 0
    assert checks["selected_benchmark_duplicate_nct_ids"] == 0
    assert checks["selected_benchmark_duplicate_intervention_rows"] == 0


def test_pagination_gap_is_recorded_not_hidden():
    module = load("capture_pdcd1_rebase_v1_population.py")
    snapshot = latest_finalized_snapshot(module)
    manifest = json.loads((snapshot / "manifest.json").read_text())
    checks = manifest["checks"]
    assert checks["total_universe_studies"] >= checks["captured_page_studies"]
    if checks["total_universe_studies"] > checks["captured_page_studies"]:
        assert checks["additional_pages_beyond_captured_page"] is True


def test_http_retrieval_metadata_present():
    module = load("capture_pdcd1_rebase_v1_population.py")
    snapshot = latest_finalized_snapshot(module)
    manifest = json.loads((snapshot / "manifest.json").read_text())
    events = manifest["http_events"]
    assert len(events) == 1
    event = events[0]
    for key in ("requested_url", "final_url", "http_status", "timestamp"):
        assert event[key]


def test_already_finalized_short_circuits_without_writes(tmp_path, monkeypatch):
    module = load("capture_pdcd1_rebase_v1_population.py")
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("network access attempted during resumability check")))
    snapshot = latest_finalized_snapshot(module)
    today = snapshot.name and json.loads((snapshot / "manifest.json").read_text())["source_retrieval_date"]
    found = module.find_resumable_snapshot(today)
    assert found is not None
    result = module.validate_snapshot(found)
    assert result["receipt"]["status"] == "FINALIZED"


def test_export_archive_extracts_and_revalidates():
    module = load("capture_pdcd1_rebase_v1_population.py")
    snapshot = latest_finalized_snapshot(module)
    tar_path = snapshot / "export" / "snapshot.tar.gz"
    checksum_file = snapshot / "export" / "snapshot.tar.gz.sha256"
    assert tar_path.is_file() and checksum_file.is_file()
    expected_sha, _, name = checksum_file.read_text().strip().partition("  ")
    assert name == "snapshot.tar.gz"
    assert sha(tar_path) == expected_sha
    receipt = json.loads((snapshot / "receipt.json").read_text())
    result = module.revalidate_export(tar_path, receipt)
    assert result["revalidated"] is True
    assert result["mismatches"] == []


def test_export_archive_contains_no_export_directory_recursion():
    module = load("capture_pdcd1_rebase_v1_population.py")
    snapshot = latest_finalized_snapshot(module)
    tar_path = snapshot / "export" / "snapshot.tar.gz"
    with tarfile.open(tar_path, "r:gz") as tar:
        names = tar.getnames()
    assert not any(name.startswith("export/") for name in names)


def test_stage_does_not_perform_adjudication_prediction_or_scoring():
    module = load("capture_pdcd1_rebase_v1_population.py")
    defined_names = {name.casefold() for name in vars(module)}
    for forbidden in ("adjudicate", "predict", "score", "evaluate"):
        assert forbidden not in defined_names
    for other_stage_script in ("build_v4_fourth_target_benchmark", "run_v4_fourth_target_zero_shot",
                                "evaluate_v4_fourth_target_zero_shot"):
        assert not hasattr(module, other_stage_script)
