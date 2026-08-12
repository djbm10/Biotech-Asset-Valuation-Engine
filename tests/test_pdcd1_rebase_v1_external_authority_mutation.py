"""Section 17: 21 named mutation tests for the Milestone 4 independent
authority validator (validate_pdcd1_rebase_v1_external_authority.py).

Each test takes a working copy of the real, finalized, independently
validated Build A snapshot (which passes cleanly on its own -- see
test_baseline_snapshot_passes) and applies exactly one targeted mutation
that the spec explicitly requires be rejected, then asserts the validator
fails closed and names the offending check.
"""
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
import validate_pdcd1_rebase_v1_external_authority as val  # noqa: E402

STAGE_ROOT = WT / "artifacts" / "pipeline" / "pdcd1_rebase_v1" / "stages" / "04_external_product_authority"
M3_DIR = STAGE_ROOT / "prerequisite_validation" / "m3" / "extracted" / "f5dd19d08deb59a75232d3bc"


def _find_finalized_snapshot_dir() -> Path:
    candidates = [
        d for d in STAGE_ROOT.iterdir()
        if d.is_dir() and d.name != "prerequisite_validation" and (d / "manifest.json").is_file()
    ]
    for d in candidates:
        m = json.loads((d / "manifest.json").read_text())
        if m.get("stage_status") == "FINALIZED":
            return d
    pytest.skip("no finalized Build A snapshot present; run build_external_authority_stage.py first")


@pytest.fixture()
def snapshot_copy(tmp_path):
    src = _find_finalized_snapshot_dir()
    dst = tmp_path / "snapshot"
    shutil.copytree(src, dst)
    return dst


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")


def run_validator(snapshot_dir: Path) -> dict:
    return val.validate(snapshot_dir, M3_DIR)


def test_baseline_snapshot_passes(snapshot_copy):
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is True, report["failed_checks"]


# 1. Google/Bing/search-engine snippet treated as evidence.
def test_mutation_01_search_snippet_as_evidence(snapshot_copy):
    p = snapshot_copy / "source" / "source_evidence_ledger.jsonl"
    rows = load_jsonl(p)
    rows[0] = dict(rows[0], source_class="google_search_results", requested_url="https://www.google.com/search?q=x")
    write_jsonl(p, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "no_search_snippet_treated_as_authority" in report["failed_checks"]


# 2. Wikipedia treated as product authority.
def test_mutation_02_wikipedia_as_product_authority(snapshot_copy):
    p = snapshot_copy / "source" / "source_evidence_ledger.jsonl"
    rows = load_jsonl(p)
    rows[0] = dict(rows[0], source_class="wikipedia_article", requested_url="https://en.wikipedia.org/wiki/X")
    write_jsonl(p, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "no_wikipedia_treated_as_authority" in report["failed_checks"]


# 3. Open Targets alone used to prove an alias linkage.
def test_mutation_03_open_targets_alone_proves_alias(snapshot_copy):
    p = snapshot_copy / "assertions" / "normalized_assertion_ledger.jsonl"
    rows = load_jsonl(p)
    a = copy.deepcopy(rows[0])
    a["assertion_type"] = "OFFICIAL_ALIAS_EXPLICIT_LINK"
    a["authority_tier"] = "tier_d"
    a["detail"] = {"alias": "FAKE-ALIAS", "note": "Open Targets alone"}
    rows.append(a)
    write_jsonl(p, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "no_tier_d_secondary_database_alone_proves_linkage" in report["failed_checks"]


# 4. ChEMBL alone used to merge/link two products.
def test_mutation_04_chembl_alone_merges_products(snapshot_copy):
    p = snapshot_copy / "assertions" / "normalized_assertion_ledger.jsonl"
    rows = load_jsonl(p)
    a = copy.deepcopy(rows[0])
    a["assertion_type"] = "CODE_TO_NAME_EXPLICIT_LINK"
    a["authority_tier"] = "tier_d"
    a["detail"] = {"linked_name": "FAKE-PRODUCT", "note": "ChEMBL alone"}
    rows.append(a)
    write_jsonl(p, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "no_tier_d_secondary_database_alone_proves_linkage" in report["failed_checks"]


# 5. Sponsor string treated as an ownership decision.
def test_mutation_05_sponsor_string_as_ownership(snapshot_copy):
    p = snapshot_copy / "assertions" / "normalized_assertion_ledger.jsonl"
    rows = load_jsonl(p)
    a = copy.deepcopy(rows[0])
    a["detail"] = dict(a.get("detail", {}), ownership="Acme Pharma", owner_organization="Acme Pharma")
    rows[0] = a
    write_jsonl(p, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "no_out_of_scope_fields_present_anywhere_in_snapshot" in report["failed_checks"]


# 6. Same-target products auto-merged (conflict silently resolved with a winner).
def test_mutation_06_same_target_products_auto_merged(snapshot_copy):
    p = snapshot_copy / "conflicts" / "authority_conflict_ledger.jsonl"
    rows = load_jsonl(p)
    rows[0] = dict(rows[0], winner="subject_a_wins", resolution="auto-merged: same target")
    write_jsonl(p, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "conflicts_not_resolved_with_a_winner" in report["failed_checks"]


# 7. Fuzzy name match treated as an explicit alias.
def test_mutation_07_fuzzy_match_as_explicit_alias(snapshot_copy):
    p = snapshot_copy / "assertions" / "normalized_assertion_ledger.jsonl"
    rows = load_jsonl(p)
    for r in rows:
        if r["assertion_type"] == "OFFICIAL_ALIAS_EXPLICIT_LINK":
            r["confidence_class"] = "FUZZY_STRING_SIMILARITY_MATCH"
            write_jsonl(p, rows)
            break
    else:
        pytest.skip("no OFFICIAL_ALIAS_EXPLICIT_LINK assertion present in baseline")
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "no_fuzzy_match_treated_as_explicit_linkage" in report["failed_checks"]


# 8. ADC merged with its antibody backbone.
def test_mutation_08_adc_merged_with_backbone(snapshot_copy):
    p = snapshot_copy / "assertions" / "normalized_assertion_ledger.jsonl"
    rows = load_jsonl(p)
    a = copy.deepcopy(rows[0])
    a["assertion_type"] = "ADC_DISTINCT_FROM_BACKBONE"
    a["detail"] = {"merged_with": "backbone-antibody-subject-id"}
    rows.append(a)
    write_jsonl(p, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "no_adc_or_biosimilar_merged_with_reference" in report["failed_checks"]


# 9. Biosimilar merged with its reference biologic.
def test_mutation_09_biosimilar_merged_with_reference(snapshot_copy):
    p = snapshot_copy / "assertions" / "normalized_assertion_ledger.jsonl"
    rows = load_jsonl(p)
    a = copy.deepcopy(rows[0])
    a["assertion_type"] = "BIOSIMILAR_DISTINCT_PRODUCT"
    a["detail"] = {"same_as": "reference-biologic-subject-id"}
    rows.append(a)
    write_jsonl(p, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "no_adc_or_biosimilar_merged_with_reference" in report["failed_checks"]


# 10. Company-hosted page treated as ownership proof.
def test_mutation_10_company_page_as_ownership_proof(snapshot_copy):
    p = snapshot_copy / "assertions" / "normalized_assertion_ledger.jsonl"
    rows = load_jsonl(p)
    a = copy.deepcopy(rows[0])
    a["authority_tier"] = "tier_b"
    a["detail"] = dict(a.get("detail", {}), ownership="Acme Pharma owns this asset")
    rows.append(a)
    write_jsonl(p, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "no_out_of_scope_fields_present_anywhere_in_snapshot" in report["failed_checks"]


# 11. Absence of an FDA match treated as proof of nonexistence.
def test_mutation_11_no_fda_match_as_nonexistence_proof(snapshot_copy):
    p = snapshot_copy / "assertions" / "normalized_assertion_ledger.jsonl"
    rows = load_jsonl(p)
    mutated = False
    for i, r in enumerate(rows):
        if r["assertion_type"] == "NO_EXACT_REGULATORY_MATCH":
            rows[i] = dict(
                r,
                assertion_type="PRODUCT_CONFIRMED_NOT_TO_EXIST",
                confidence_class="PROVEN_NONEXISTENT",
                detail={"note": "Product definitively does not exist"},
            )
            mutated = True
            break
    if not mutated:
        pytest.skip("no NO_EXACT_REGULATORY_MATCH assertion present in baseline")
    write_jsonl(p, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "every_assertion_type_is_schema_defined" in report["failed_checks"]


# 12. Secondary review article treated as primary linkage evidence.
def test_mutation_12_secondary_review_article_as_primary_linkage(snapshot_copy):
    p = snapshot_copy / "assertions" / "normalized_assertion_ledger.jsonl"
    se = snapshot_copy / "source" / "source_evidence_ledger.jsonl"
    a_rows = load_jsonl(p)
    e_rows = load_jsonl(se)
    a = copy.deepcopy(a_rows[0])
    a["assertion_type"] = "TRIAL_TO_PRODUCT_EXPLICIT_LINK"
    a["authority_tier"] = "tier_c"
    a["evidence_hash"] = "deadbeef" * 8
    a_rows.append(a)
    e = copy.deepcopy(e_rows[0])
    e["subject_id"] = a["subject_id"]
    e["source_class"] = "secondary_review_article"
    e["authority_tier"] = "tier_c"
    e["response_sha256"] = a["evidence_hash"]
    e_rows.append(e)
    write_jsonl(p, a_rows)
    write_jsonl(se, e_rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "tier_c_linkage_uses_primary_publication_source_class" in report["failed_checks"]


# 13. Publication mentioning the target (not the product) treated as identity evidence.
def test_mutation_13_target_mention_not_product_identity(snapshot_copy):
    p = snapshot_copy / "assertions" / "normalized_assertion_ledger.jsonl"
    se = snapshot_copy / "source" / "source_evidence_ledger.jsonl"
    a_rows = load_jsonl(p)
    e_rows = load_jsonl(se)
    a = copy.deepcopy(a_rows[0])
    a["assertion_type"] = "CODE_TO_NAME_EXPLICIT_LINK"
    a["authority_tier"] = "tier_c"
    a["evidence_hash"] = "cafebabe" * 8
    a_rows.append(a)
    e = copy.deepcopy(e_rows[0])
    e["subject_id"] = a["subject_id"]
    e["source_class"] = "target_biology_review_no_product_link"
    e["authority_tier"] = "tier_c"
    e["response_sha256"] = a["evidence_hash"]
    e_rows.append(e)
    write_jsonl(p, a_rows)
    write_jsonl(se, e_rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "tier_c_linkage_uses_primary_publication_source_class" in report["failed_checks"]


# 14. Altered exact evidence locator.
def test_mutation_14_altered_evidence_locator(snapshot_copy):
    p = snapshot_copy / "assertions" / "normalized_assertion_ledger.jsonl"
    rows = load_jsonl(p)
    mutated = False
    for i, r in enumerate(rows):
        non_exempt = r.get("authority_tier") in ("tier_b", "tier_c") or (
            r.get("authority_tier") == "tier_a"
            and r["assertion_type"] not in ("MODALITY_EXPLICIT", "GENERIC_DESCRIPTION_NOT_PRODUCT_NAME")
        )
        if non_exempt:
            rows[i] = dict(r, evidence_hash="0" * 64)
            mutated = True
            break
    if not mutated:
        pytest.skip("no evidence-hash-bound assertion present in baseline")
    write_jsonl(p, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "every_evidence_hash_resolves_to_a_captured_source" in report["failed_checks"]


# 15. Altered source hash.
def test_mutation_15_altered_source_hash(snapshot_copy):
    p = snapshot_copy / "source" / "source_evidence_ledger.jsonl"
    rows = load_jsonl(p)
    rows[0] = dict(rows[0], response_sha256="1" * 64)
    write_jsonl(p, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "every_evidence_hash_resolves_to_a_captured_source" in report["failed_checks"]


# 16. Unjustified authority-tier escalation.
def test_mutation_16_unjustified_tier_escalation(snapshot_copy):
    p = snapshot_copy / "assertions" / "normalized_assertion_ledger.jsonl"
    rows = load_jsonl(p)
    mutated = False
    for r in rows:
        if r["assertion_type"] not in ("MODALITY_EXPLICIT", "GENERIC_DESCRIPTION_NOT_PRODUCT_NAME") and r.get("authority_tier") == "tier_b":
            r["authority_tier"] = "tier_a"
            mutated = True
            break
    if not mutated:
        pytest.skip("no tier_b assertion present in baseline to escalate")
    write_jsonl(p, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "no_unjustified_authority_tier_escalation" in report["failed_checks"]


# 17. Subject outside the approved Milestone 3 review queue introduced.
def test_mutation_17_subject_outside_queue_introduced(snapshot_copy):
    p = snapshot_copy / "subjects" / "authority_research_subject_ledger.jsonl"
    rows = load_jsonl(p)
    fake = copy.deepcopy(rows[0])
    fake["subject_id"] = "0" * 24
    fake["source_strings"] = ["TOTALLY_FABRICATED_STRING_NOT_IN_M3"]
    rows.append(fake)
    write_jsonl(p, rows)
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "every_subject_originates_from_milestone3_queues" in report["failed_checks"]


# 18. Canonical candidate ID introduced.
def test_mutation_18_canonical_candidate_id_introduced(snapshot_copy):
    p = snapshot_copy / "manifest.json"
    m = json.loads(p.read_text())
    m["canonical_candidate_id"] = "CAND-0001"
    p.write_text(json.dumps(m, indent=2, sort_keys=True))
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "no_out_of_scope_fields_present_anywhere_in_snapshot" in report["failed_checks"]


# 19. Benchmark label introduced.
def test_mutation_19_benchmark_label_introduced(snapshot_copy):
    p = snapshot_copy / "manifest.json"
    m = json.loads(p.read_text())
    m["benchmark_label"] = "TRUE_POSITIVE"
    p.write_text(json.dumps(m, indent=2, sort_keys=True))
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "no_out_of_scope_fields_present_anywhere_in_snapshot" in report["failed_checks"]


# 20. Candidate-specific chronology introduced.
def test_mutation_20_candidate_chronology_introduced(snapshot_copy):
    p = snapshot_copy / "manifest.json"
    m = json.loads(p.read_text())
    m["candidate_chronology"] = [{"event": "IND filed", "date": "2020-01-01"}]
    p.write_text(json.dumps(m, indent=2, sort_keys=True))
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert "no_out_of_scope_fields_present_anywhere_in_snapshot" in report["failed_checks"]


# 21. Prediction/evaluation module invoked (evaluation_performed flag flipped).
def test_mutation_21_prediction_evaluation_module_invoked(snapshot_copy):
    p = snapshot_copy / "manifest.json"
    m = json.loads(p.read_text())
    m["evaluation_performed"] = True
    m["prediction"] = {"predicted_label": "LIKELY_APPROVED"}
    p.write_text(json.dumps(m, indent=2, sort_keys=True))
    report = run_validator(snapshot_copy)
    assert report["overall_pass"] is False
    assert (
        "manifest_scope_flags_correct" in report["failed_checks"]
        or "no_out_of_scope_fields_present_anywhere_in_snapshot" in report["failed_checks"]
    )
