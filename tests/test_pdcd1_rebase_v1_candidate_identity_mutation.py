"""Named mutation tests for Milestone 5 candidate-identity validation."""
from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path

import pytest

WT = Path(__file__).resolve().parents[1]
SCRIPTS = WT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import validate_pdcd1_rebase_v1_candidate_identity as val  # noqa: E402

STAGE_ROOT = WT / "artifacts" / "pipeline" / "pdcd1_rebase_v1" / "stages" / "05_candidate_identity_adjudication"
M4_DIR = (
    WT
    / "artifacts"
    / "pipeline"
    / "pdcd1_rebase_v1"
    / "stages"
    / "04_external_product_authority"
    / "d933fec9aaeecd2df64884b6"
)


def _find_snapshot() -> Path:
    if not STAGE_ROOT.is_dir():
        pytest.skip("M5 stage has not been built yet")
    for path in sorted(STAGE_ROOT.iterdir()):
        manifest = path / "manifest.json"
        if manifest.is_file() and json.loads(manifest.read_text()).get("stage_status") == "FINALIZED":
            return path
    pytest.skip("no finalized M5 snapshot present")


@pytest.fixture()
def snapshot_copy(tmp_path):
    dst = tmp_path / "snapshot"
    shutil.copytree(_find_snapshot(), dst)
    return dst


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def run_validator(snapshot_dir: Path) -> dict:
    return val.validate(snapshot_dir, M4_DIR)


def test_baseline_snapshot_passes(snapshot_copy):
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is True, report["failed_checks"]


def _force_bad_alias(snapshot_copy: Path, basis: str) -> None:
    path = snapshot_copy / "subjects" / "subject_candidate_mapping_ledger.jsonl"
    rows = load_jsonl(path)
    rows[0]["identity_outcome"] = "VERIFIED_ALIAS_OF_CANDIDATE"
    rows[0]["candidate_id"] = "cand_bad_context_merge"
    rows[0]["adjudication_basis"] = basis
    rows[0]["supporting_assertions"] = []
    write_jsonl(path, rows)


def test_mutation_01_fuzzy_name_merging(snapshot_copy):
    _force_bad_alias(snapshot_copy, "auto-merged by fuzzy name similarity")
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "no_fuzzy_same_sponsor_or_same_target_merges" in report["failed_checks"]


def test_mutation_02_same_sponsor_merging(snapshot_copy):
    _force_bad_alias(snapshot_copy, "auto-merged by shared sponsor/trial")
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "no_fuzzy_same_sponsor_or_same_target_merges" in report["failed_checks"]


def test_mutation_03_same_target_merging(snapshot_copy):
    _force_bad_alias(snapshot_copy, "auto-merged by shared PD-1 target")
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "no_fuzzy_same_sponsor_or_same_target_merges" in report["failed_checks"]


def test_mutation_04_adc_backbone_collapse(snapshot_copy):
    path = snapshot_copy / "boundaries" / "identity_boundary_ledger.jsonl"
    rows = load_jsonl(path)
    if not rows:
        pytest.skip("baseline has no boundary rows")
    rows[0]["boundary_type"] = "ADC_DISTINCT_FROM_BACKBONE"
    rows[0]["kept_distinct_from"] = {"merged_with": "naked antibody backbone"}
    write_jsonl(path, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "no_adc_or_biosimilar_or_combination_collapse" in report["failed_checks"]


def test_mutation_05_biosimilar_reference_collapse(snapshot_copy):
    path = snapshot_copy / "boundaries" / "identity_boundary_ledger.jsonl"
    rows = load_jsonl(path)
    if not rows:
        pytest.skip("baseline has no boundary rows")
    rows[0]["boundary_type"] = "BIOSIMILAR_DISTINCT_PRODUCT"
    rows[0]["kept_distinct_from"] = {"same_as": "reference product"}
    write_jsonl(path, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "no_adc_or_biosimilar_or_combination_collapse" in report["failed_checks"]


def test_mutation_06_unsupported_alias(snapshot_copy):
    path = snapshot_copy / "aliases" / "alias_development_code_ledger.jsonl"
    rows = load_jsonl(path)
    if not rows:
        pytest.skip("baseline has no aliases")
    rows[0]["supporting_assertions"] = []
    write_jsonl(path, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "aliases_have_citable_qualifying_assertions" in report["failed_checks"]


def test_mutation_07_conflict_silently_dropped(snapshot_copy):
    path = snapshot_copy / "conflicts" / "conflict_resolution_ledger.jsonl"
    rows = load_jsonl(path)
    rows.pop()
    write_jsonl(path, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "all_76_m4_conflicts_covered_once" in report["failed_checks"]


def test_mutation_08_conflict_without_real_marker(snapshot_copy):
    path = snapshot_copy / "conflicts" / "conflict_resolution_ledger.jsonl"
    rows = load_jsonl(path)
    rows[0]["resolution_marker"] = ""
    rows[0]["reasoning"] = ""
    write_jsonl(path, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "conflicts_have_real_resolution_or_unresolved_marker" in report["failed_checks"]


def test_mutation_09_candidate_created_without_evidence(snapshot_copy):
    path = snapshot_copy / "candidates" / "canonical_candidate_ledger.jsonl"
    rows = load_jsonl(path)
    bad = copy.deepcopy(rows[0])
    bad["candidate_id"] = "cand_without_evidence"
    bad["supporting_assertions"] = []
    rows.append(bad)
    write_jsonl(path, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "canonical_candidates_have_supporting_identity_assertions" in report["failed_checks"]
