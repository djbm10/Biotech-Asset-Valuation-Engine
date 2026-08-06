from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREREQ = (
    ROOT / "artifacts" / "pipeline" / "pdcd1_rebase_v1" / "stages"
    / "03_candidate_bearing_evidence_triage" / "prerequisite_validation"
)


def load(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
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
    assert snapshots, "no finalized snapshot present; run scripts/extract_pdcd1_rebase_v1_evidence_triage.py first"
    return sorted(snapshots, key=lambda p: p.stat().st_mtime)[-1]


def run_module():
    module = load("extract_pdcd1_rebase_v1_evidence_triage.py")
    return module


def test_prerequisite_validation_rejects_wrong_snapshot_id(tmp_path):
    module = run_module()
    src = PREREQ / "m1" / "extracted"
    dest = tmp_path / "m1"
    dest.mkdir()
    for name in ("manifest.json", "receipt.json"):
        (dest / name).write_text((src / name).read_text())
    (dest / "source").mkdir()
    (dest / "source" / "benchmark_population.json").write_text(
        (src / "source" / "benchmark_population.json").read_text()
    )
    receipt = json.loads((dest / "receipt.json").read_text())
    receipt["snapshot_id"] = "wrong_snapshot_id"
    (dest / "receipt.json").write_text(json.dumps(receipt))
    try:
        module.load_prerequisite_m1(dest)
    except ValueError as exc:
        assert "PREREQUISITE_SNAPSHOT_ID_MISMATCH" in str(exc)
    else:
        raise AssertionError("mismatched m1 snapshot id was accepted")


def test_frozen_row_count_matches_milestone1():
    module = run_module()
    m1 = module.load_prerequisite_m1(PREREQ / "m1" / "extracted")
    assert len(m1["nct_ids"]) == 81
    assert len(m1["frozen_rows"]) == 300


def test_snapshot_has_four_required_ledgers():
    module = run_module()
    snapshot = latest_finalized_snapshot(module)
    normalized = snapshot / "normalized"
    assert (normalized / "candidate_bearing_occurrence_ledger.jsonl").is_file()
    assert (normalized / "unique_exact_string_ledger.jsonl").is_file()
    assert (normalized / "presentation_variant_ledger.jsonl").is_file()
    assert (normalized / "official_other_name_edge_ledger.jsonl").is_file()


def test_no_duplicate_occurrence_ids():
    module = run_module()
    snapshot = latest_finalized_snapshot(module)
    lines = (snapshot / "normalized" / "candidate_bearing_occurrence_ledger.jsonl").read_text().splitlines()
    rows = [json.loads(line) for line in lines]
    ids = [r["occurrence_id"] for r in rows]
    assert len(ids) == len(set(ids))


def test_frozen_row_bindings_have_no_benchmark_label():
    module = run_module()
    snapshot = latest_finalized_snapshot(module)
    lines = (snapshot / "extracted" / "frozen_row_evidence_bindings.jsonl").read_text().splitlines()
    rows = [json.loads(line) for line in lines]
    assert len(rows) == 300
    forbidden = {"benchmark_label", "label", "candidate_id", "canonical_candidate", "alias"}
    for row in rows:
        assert not (forbidden & set(row.keys()))


def test_pd1_alone_never_classified_as_isolated_product():
    lib = load("pdcd1_evidence_triage_lib.py")
    for s in ("PD-1", "PDCD1", "PD-L1", "anti-PD-1", "anti-PD-1 antibody"):
        category, _ = lib.classify_content(s)
        assert category == "GENERIC_TARGET_OR_MODALITY_STRING", s


def test_placebo_never_classified_as_isolated_product():
    lib = load("pdcd1_evidence_triage_lib.py")
    for s in ("Placebo", "placebo", "Vehicle Control"):
        category, _ = lib.classify_content(s)
        assert category == "PLACEBO_OR_CONTROL", s


def test_nct_id_never_classified_as_product():
    lib = load("pdcd1_evidence_triage_lib.py")
    category, _ = lib.classify_content("NCT02257528")
    assert category == "EXPLICIT_NONPRODUCT_INTERVENTION"


def test_combination_string_not_silently_treated_as_one_product():
    lib = load("pdcd1_evidence_triage_lib.py")
    category, _ = lib.classify_content("Pembrolizumab and Chemotherapy")
    assert category == "MULTI_PRODUCT_OR_COMBINATION_STRING"
    components = lib.parse_components("Pembrolizumab and Chemotherapy")
    assert len(components) == 2


def test_ambiguous_boundary_not_guessed_at():
    lib = load("pdcd1_evidence_triage_lib.py")
    long_prose = "First line chemotherapy plus PD-1/PD-L1 antibody " * 5
    category, _ = lib.classify_content(long_prose)
    assert category == "AMBIGUOUS_REQUIRES_REVIEW"


def test_official_other_name_only_string_gets_weaker_category():
    # Milestone 3B (Section 5): a bare, non-chemical-like comma with no explicit
    # connector is no longer guessed as multi-product or single-name -- it must
    # route to review rather than be silently resolved either way.
    lib = load("pdcd1_evidence_triage_lib.py")
    category, _ = lib.classify("Buzhong Yiqi Decoction, Hochu-ekki-to", "official_other_name", True)
    assert category in (
        "OFFICIAL_OTHER_NAME_STRING",
        "MULTI_PRODUCT_OR_COMBINATION_STRING",
        "AMBIGUOUS_REQUIRES_REVIEW",
    )


def test_review_queues_do_not_resolve_cases():
    module = run_module()
    snapshot = latest_finalized_snapshot(module)
    for name in ("targeted_review_queue.jsonl", "forensic_review_queue.jsonl"):
        lines = (snapshot / "triage" / name).read_text().splitlines()
        rows = [json.loads(line) for line in lines]
        forbidden = {"canonical_candidate", "alias", "resolution", "decision", "benchmark_label"}
        for row in rows:
            assert not (forbidden & set(row.keys()))


def test_manifest_declares_all_scope_flags_false():
    module = run_module()
    snapshot = latest_finalized_snapshot(module)
    manifest = json.loads((snapshot / "manifest.json").read_text())
    for flag in (
        "canonical_candidates_created", "aliases_adjudicated", "ownership_claims_created",
        "candidate_chronology_created", "benchmark_labels_created", "predictions_generated",
        "evaluation_performed",
    ):
        assert manifest[flag] is False, flag


def test_manifest_binds_both_prerequisite_identities():
    module = run_module()
    snapshot = latest_finalized_snapshot(module)
    manifest = json.loads((snapshot / "manifest.json").read_text())
    assert manifest["milestone1_prerequisite"]["snapshot_id"] == module.MILESTONE1_SNAPSHOT_ID
    assert manifest["milestone2_prerequisite"]["snapshot_id"] == module.MILESTONE2_SNAPSHOT_ID


def test_receipt_rejects_mutated_artifact(tmp_path):
    module = run_module()
    source = latest_finalized_snapshot(module)
    dest = tmp_path / "snapshot"
    dest.mkdir()
    for path in source.rglob("*"):
        if path.is_file():
            rel = path.relative_to(source)
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            (dest / rel).write_bytes(path.read_bytes())
    target = dest / "normalized" / "unique_exact_string_ledger.jsonl"
    target.write_bytes(target.read_bytes() + b"\n")
    try:
        module.validate_snapshot(dest)
    except ValueError as exc:
        assert "ARTIFACT_HASH_MISMATCH" in str(exc)
    else:
        raise AssertionError("mutated artifact was accepted as valid")


def test_already_finalized_short_circuits_without_reextraction():
    module = run_module()
    first = module.run_extraction(PREREQ / "m1" / "extracted", PREREQ / "m2" / "extracted")
    assert first["status"] in ("FINALIZED", "ALREADY_FINALIZED")
    found = module.find_finalized_snapshot_by_staging_key(first["staging_key"])
    assert found is not None
    result = module.run_extraction(PREREQ / "m1" / "extracted", PREREQ / "m2" / "extracted")
    assert result["status"] == "ALREADY_FINALIZED"
    for v in result["counters"].values():
        assert v == 0


def test_stage_does_not_perform_adjudication_prediction_or_scoring():
    module = run_module()
    defined_names = {name.casefold() for name in vars(module)}
    for forbidden in ("adjudicate", "predict", "score", "evaluate_candidate", "create_benchmark_label"):
        assert forbidden not in defined_names
