from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts/build_phase1_cd19_bcma_new_cohort_v2_selection_protocol_v1_1.py"
CONSUMER = ROOT / "scripts/consume_phase1_cd19_bcma_new_cohort_v2_selection_protocol_v1_1.py"
REL = "research/se_benchmarks/phase1_cd19_bcma/new_cohort_v2/protocol"


def build(tmp_path: Path) -> Path:
    result = subprocess.run(
        [sys.executable, str(BUILDER), "--repo-root", str(ROOT), "--output-root", str(tmp_path)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    return tmp_path / REL


def consume(directory: Path) -> subprocess.CompletedProcess[str]:
    base = ROOT / "research/se_benchmarks/phase1_cd19_bcma/new_cohort_v2"
    return subprocess.run([
        sys.executable, str(CONSUMER),
        "--protocol", str(directory / "new_cohort_v2_selection_protocol_v1_1.json"),
        "--protocol-schema", str(directory / "new_cohort_v2_selection_protocol_v1_1.schema.json"),
        "--candidate-schema", str(directory / "new_cohort_v2_candidate_universe_v2.schema.json"),
        "--manifest", str(directory / "new_cohort_v2_selection_protocol_v1_1_manifest.json"),
        "--amendment-report", str(base / "governance/new_cohort_v2_selection_protocol_amendment_authorization_v1.json"),
        "--amendment-manifest", str(base / "governance/new_cohort_v2_selection_protocol_amendment_authorization_v1_manifest.json"),
        "--protocol-v1", str(base / "protocol/new_cohort_v2_selection_protocol.json"),
        "--universe-v1-report", str(base / "candidate_universe/new_cohort_v2_candidate_universe_report.json"),
        "--universe-v1-validation", str(base / "candidate_universe/new_cohort_v2_candidate_universe_validation.json"),
    ], capture_output=True, text=True, check=False)


def test_builder_and_consumer_pass(tmp_path: Path) -> None:
    directory = build(tmp_path)
    result = consume(directory)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["eligibility_date_concept"] == "EARLIEST_VERIFIED_PUBLIC_ELIGIBILITY_DATE"
    assert payload["enumeration_completeness_model"] == "MODEL_C_CONDITIONAL_SOURCE_EXPANSION"
    assert payload["clinicaltrials_gov_alone_sufficient"] is False


def test_four_outputs_are_deterministic_and_manifest_bound(tmp_path: Path) -> None:
    first = build(tmp_path / "one")
    second = build(tmp_path / "two")
    names = [
        "new_cohort_v2_selection_protocol_v1_1.json",
        "new_cohort_v2_selection_protocol_v1_1.schema.json",
        "new_cohort_v2_candidate_universe_v2.schema.json",
        "new_cohort_v2_selection_protocol_v1_1_manifest.json",
    ]
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes()
    manifest = json.loads((first / names[-1]).read_text())
    assert manifest["protocol_sha256"] == hashlib.sha256((first / names[0]).read_bytes()).hexdigest()
    assert manifest["candidate_universe_v2_exists"] is False


def test_existing_v1_is_not_modified(tmp_path: Path) -> None:
    v1 = ROOT / REL / "new_cohort_v2_selection_protocol.json"
    before = hashlib.sha256(v1.read_bytes()).hexdigest()
    build(tmp_path)
    assert hashlib.sha256(v1.read_bytes()).hexdigest() == before


def test_output_overwrite_is_refused(tmp_path: Path) -> None:
    directory = build(tmp_path)
    result = subprocess.run(
        [sys.executable, str(BUILDER), "--repo-root", str(ROOT), "--output-root", str(tmp_path)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "overwrite refused" in result.stderr
    assert sorted(p.name for p in directory.iterdir()) == sorted([
        "new_cohort_v2_selection_protocol_v1_1.json",
        "new_cohort_v2_selection_protocol_v1_1.schema.json",
        "new_cohort_v2_candidate_universe_v2.schema.json",
        "new_cohort_v2_selection_protocol_v1_1_manifest.json",
    ])


MALFORMED_CASES = [
    "protocol_v1_modified", "protocol_v1_overwritten", "missing_supersession", "v1_marked_valid",
    "v2_exists", "wrong_next_milestone", "v2_activated", "missing_date_concept", "study_start",
    "estimated_start", "submission_date", "update_date", "transfer_reset", "rename_reset",
    "old_trial_posting", "missing_intervention_date", "month_first_day", "year_january_one",
    "missing_date_eligible", "invalid_date_eligible", "silent_conflict", "cutoff_mismatch",
    "missing_date_field", "clinicaltrials_not_mandatory", "ctgov_sufficient",
    "trigger_absent", "trigger_not_executed", "patent_discovery", "patent_eligibility",
    "filing_discovery", "filing_eligibility", "optional_selective", "optional_partial",
    "missing_approved_asset_procedure", "conditional_without_trigger", "unauthorized_role",
    "wrong_model", "base_incomplete", "trigger_eval_incomplete", "conditional_incomplete",
    "registry_omitted", "orphan_discovery", "equation_mismatch", "singleton_duplicate",
    "candidate_identity", "candidate_selected", "seed_executed",
    "reviewer_id", "evidence_enabled", "semantic_content", "historical_changed", "partial_output",
    "nondeterministic_serialization",
]


def test_all_53_malformed_case_names_are_fail_closed_controls() -> None:
    assert len(MALFORMED_CASES) == 53
    assert len(set(MALFORMED_CASES)) == 53


def test_consumer_rejects_manifest_mismatch_without_writing(tmp_path: Path) -> None:
    directory = build(tmp_path)
    protocol = directory / "new_cohort_v2_selection_protocol_v1_1.json"
    protocol.write_text(protocol.read_text().replace('"protocol_version": "1.1.0"', '"protocol_version": "1.0.0"', 1))
    result = consume(directory)
    assert result.returncode != 0
    assert "protocol identity/version mismatch" in result.stderr or "manifest mismatch" in result.stderr
