"""Named mutation tests for Milestone 6 row-identity mapping validation."""

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

import validate_pdcd1_rebase_v1_row_identity_mapping as val  # noqa: E402

STAGE_ROOT = WT / "artifacts" / "pipeline" / "pdcd1_rebase_v1" / "stages" / "06_frozen_row_identity_mapping"
M3_DIR = WT / "artifacts" / "pipeline" / "pdcd1_rebase_v1" / "stages" / "03_candidate_bearing_evidence_triage" / "f5dd19d08deb59a75232d3bc"
M5_DIR = WT / "artifacts" / "pipeline" / "pdcd1_rebase_v1" / "stages" / "05_candidate_identity_adjudication" / "f26fd47e34ab97badde4e2ae"


def _find_snapshot() -> Path:
    if not STAGE_ROOT.is_dir():
        pytest.skip("M6 stage has not been built yet")
    for path in sorted(STAGE_ROOT.iterdir()):
        manifest = path / "manifest.json"
        if manifest.is_file() and json.loads(manifest.read_text()).get("stage_status") == "FINALIZED":
            return path
    pytest.skip("no finalized M6 snapshot present")


@pytest.fixture()
def snapshot_copy(tmp_path: Path) -> Path:
    dst = tmp_path / "snapshot"
    shutil.copytree(_find_snapshot(), dst)
    return dst


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def run_validator(snapshot_dir: Path) -> dict:
    return val.validate(snapshot_dir, M3_DIR, M5_DIR)


def _candidate_mapping_rows(snapshot_dir: Path) -> list[dict]:
    return load_jsonl(snapshot_dir / "rows" / "row_candidate_mapping_ledger.jsonl")


def _rewrite_candidate_mapping(snapshot_dir: Path, rows: list[dict]) -> None:
    write_jsonl(snapshot_dir / "rows" / "row_candidate_mapping_ledger.jsonl", rows)


def test_mutation_01_fuzzy_mapping_no_real_assertion(snapshot_copy: Path) -> None:
    rows = _candidate_mapping_rows(snapshot_copy)
    for entry in rows[0]["binding_path"]:
        if entry.get("canonical_candidate_id"):
            entry["assertion_types"] = ["FUZZY_NAME_SIMILARITY"]
    _rewrite_candidate_mapping(snapshot_copy, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "no_candidate_row_derives_only_from_context_assertion_types" in report["failed_checks"]


def test_mutation_02_sponsor_mapping_context_only(snapshot_copy: Path) -> None:
    rows = _candidate_mapping_rows(snapshot_copy)
    for entry in rows[0]["binding_path"]:
        if entry.get("canonical_candidate_id"):
            entry["assertion_types"] = ["SPONSOR_ONLY"]
    _rewrite_candidate_mapping(snapshot_copy, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "no_candidate_row_derives_only_from_context_assertion_types" in report["failed_checks"]


def test_mutation_03_target_only_mapping_context_only(snapshot_copy: Path) -> None:
    rows = _candidate_mapping_rows(snapshot_copy)
    for entry in rows[0]["binding_path"]:
        if entry.get("canonical_candidate_id"):
            entry["assertion_types"] = ["TARGET_ONLY"]
    _rewrite_candidate_mapping(snapshot_copy, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "no_candidate_row_derives_only_from_context_assertion_types" in report["failed_checks"]


def test_mutation_04_alias_bypass_not_in_m5_alias_ledger(snapshot_copy: Path) -> None:
    rows = _candidate_mapping_rows(snapshot_copy)
    alias_row = next(
        row for row in rows for entry in row["binding_path"] if entry.get("m5_identity_outcome") == "VERIFIED_ALIAS_OF_CANDIDATE"
    )
    alias_row = copy.deepcopy(alias_row)
    for entry in alias_row["binding_path"]:
        if entry.get("m5_identity_outcome") == "VERIFIED_ALIAS_OF_CANDIDATE":
            entry["alias_ledger_binding"]["alias_string"] = "FABRICATED_ALIAS"
            break
    rows[rows.index(next(row for row in rows if row["frozen_row_id"] == alias_row["frozen_row_id"]))] = alias_row
    _rewrite_candidate_mapping(snapshot_copy, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "every_alias_bypass_mapping_exists_in_m5_alias_ledger_and_not_rejected" in report["failed_checks"]


def test_mutation_05_combination_collapse_discards_second_candidate(snapshot_copy: Path) -> None:
    outcomes = load_jsonl(snapshot_copy / "rows" / "row_outcome_ledger.jsonl")
    mappings = _candidate_mapping_rows(snapshot_copy)
    conflict = next(row for row in mappings if len(row.get("canonical_candidate_ids", [])) > 1)
    for row in outcomes:
        if row["frozen_row_id"] == conflict["frozen_row_id"]:
            row["outcome"] = "CANDIDATE_LINKED"
            row["canonical_candidate_id"] = conflict["canonical_candidate_ids"][0]
    conflict["canonical_candidate_ids"] = [conflict["canonical_candidate_ids"][0]]
    conflict["canonical_candidate_id"] = conflict["canonical_candidate_ids"][0]
    write_jsonl(snapshot_copy / "rows" / "row_outcome_ledger.jsonl", outcomes)
    _rewrite_candidate_mapping(snapshot_copy, mappings)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "combination_rows_preserve_all_distinct_candidate_components" in report["failed_checks"]


def test_mutation_06_multi_candidate_row_forced_single(snapshot_copy: Path) -> None:
    outcomes = load_jsonl(snapshot_copy / "rows" / "row_outcome_ledger.jsonl")
    mappings = _candidate_mapping_rows(snapshot_copy)
    conflict = next(row for row in mappings if len(row.get("canonical_candidate_ids", [])) > 1)
    for row in outcomes:
        if row["frozen_row_id"] == conflict["frozen_row_id"]:
            row["outcome"] = "CANDIDATE_LINKED"
            row["canonical_candidate_id"] = conflict["canonical_candidate_ids"][0]
    write_jsonl(snapshot_copy / "rows" / "row_outcome_ledger.jsonl", outcomes)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "multi_candidate_rows_are_not_collapsed_to_single_candidate" in report["failed_checks"]


def test_mutation_07_unresolved_conflict_forced_closed_without_boundary(snapshot_copy: Path) -> None:
    outcomes = load_jsonl(snapshot_copy / "rows" / "row_outcome_ledger.jsonl")
    conflict_row = next(row for row in outcomes if row["outcome"] == "IDENTITY_CONFLICT_UNRESOLVED")
    candidate_id = load_jsonl(M5_DIR / "candidates" / "canonical_candidate_ledger.jsonl")[0]["candidate_id"]
    for row in outcomes:
        if row["frozen_row_id"] == conflict_row["frozen_row_id"]:
            row["outcome"] = "CANDIDATE_LINKED"
            row["canonical_candidate_id"] = candidate_id
    write_jsonl(snapshot_copy / "rows" / "row_outcome_ledger.jsonl", outcomes)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "conflict_unresolved_subject_rows_remain_unresolved_without_escape_hatch" in report["failed_checks"]


def test_mutation_08_row_omission_and_duplication(snapshot_copy: Path) -> None:
    rows = load_jsonl(snapshot_copy / "rows" / "row_outcome_ledger.jsonl")
    rows.pop()
    rows.append(copy.deepcopy(rows[0]))
    write_jsonl(snapshot_copy / "rows" / "row_outcome_ledger.jsonl", rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "all_300_frozen_rows_present_exactly_once" in report["failed_checks"]
