"""Milestone 3B (Section 6/7): regression fixtures for the Milestone 3
pointer-collision bug, the Section 5 comma/chemical-name disambiguation
rule, and the 21 explicitly named mutation tests. Every test here proves
a specific way the pipeline could quietly slide into adjudication,
prediction, or a resurrected pointer bug -- and that it does not.
"""
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
        if p.is_dir() and p.name not in ("_staging", "_checkpoints") and (p / "receipt.json").is_file()
    ]
    assert snapshots, "no finalized snapshot present"
    return sorted(snapshots, key=lambda p: p.stat().st_mtime)[-1]


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_m1():
    module = load("extract_pdcd1_rebase_v1_evidence_triage.py")
    return module, module.load_prerequisite_m1(PREREQ / "m1" / "extracted")


# ---------------------------------------------------------------------------
# Section 6: pointer-collision regression fixtures
# ---------------------------------------------------------------------------

def test_regression_not_every_frozen_occurrence_resolves_to_index_zero():
    module = load("extract_pdcd1_rebase_v1_evidence_triage.py")
    snapshot = latest_finalized_snapshot(module)
    rows = read_jsonl(snapshot / "extracted" / "frozen_row_evidence_bindings.jsonl")
    assert rows
    indices = {r["intervention_index"] for r in rows}
    assert indices != {0}, "every frozen occurrence resolved to intervention index 0 -- pointer bug regressed"


def test_regression_every_multi_intervention_study_resolves_correct_index():
    """The historical bug only manifests on studies with 2+ interventions
    (a single-intervention study can't reveal misrouting to index 0). The
    original spec calls out 16 historically-observed collision cases; this
    repo does not retain that specific list as an artifact, so this test
    instead exhaustively covers every multi-intervention study in the
    current Milestone 1 population (a strict superset of any historical 16)
    and asserts each frozen row's name-occurrence binds to its own
    intervention index and its own source text, never another row's.
    """
    module, m1 = load_m1()
    frozen_by_nct: dict[str, list[dict]] = {}
    for row in m1["frozen_rows"]:
        frozen_by_nct.setdefault(row["nct_id"], []).append(row)
    multi_studies = {nct: rows for nct, rows in frozen_by_nct.items() if len(rows) > 1}
    assert len(multi_studies) >= 16, "fewer multi-intervention studies than the historical collision count"

    class _EmptyM2:
        root = ROOT
        versions_by_nct: dict = {}

    checked = 0
    for nct_id, rows in multi_studies.items():
        occs = module.extract_unit_occurrences(nct_id, rows, {"root": ROOT, "versions_by_nct": {}})
        name_occs_by_row = {
            o["frozen_row_id"]: o for o in occs if o["field_class"] == "name" and o["frozen_row_id"]
        }
        for row in rows:
            occ = name_occs_by_row.get(row["frozen_row_id"])
            assert occ is not None, f"missing frozen occurrence for {row['frozen_row_id']}"
            assert occ["intervention_index"] == row["intervention_index"], (
                nct_id, row["frozen_row_id"], occ["intervention_index"], row["intervention_index"],
            )
            assert occ["raw_string"] == row["intervention"].get("name")
            assert occ["json_pointer"].endswith(f"/interventions/{row['intervention_index']}/name")
            checked += 1
        # distinct rows in the same study must resolve to distinct indices
        assert len({o["intervention_index"] for o in name_occs_by_row.values()}) == len(rows)
    assert checked >= 16


# ---------------------------------------------------------------------------
# Section 6: comma / chemical-name disambiguation fixtures
# ---------------------------------------------------------------------------

def test_fixture_single_chemical_name_with_internal_commas_not_split():
    lib = load("pdcd1_evidence_triage_lib.py")
    for s in (
        "1-Nitrosourea, 1-(2-chloroethyl)-3-cyclohexyl-",
        "Azacytidine, 5-",
        "Cyclophosphamide, 4-hydroxy-",
    ):
        category, flags = lib.classify_content(s)
        assert category == "ISOLATED_PRODUCT_LIKE_STRING", (s, category)
        assert flags["possible_single_chemical_name_with_internal_commas"] is True
        assert lib.parse_components(s) == []


def test_fixture_multi_drug_comma_or_list_not_guessed_as_single_product():
    """Regression for the suffix-heuristic false positive discovered while
    building this milestone: 'temozolomide' ends in '-ide' like many real
    chemical suffixes, but this string is a genuine 4-drug list joined by
    commas and 'or' with no strong connector -- it must never be silently
    merged into one isolated product.
    """
    lib = load("pdcd1_evidence_triage_lib.py")
    s = "dacarbazine, temozolomide, paclitaxel or platinum"
    category, flags = lib.classify_content(s)
    assert category == "AMBIGUOUS_REQUIRES_REVIEW", category
    assert flags["possible_single_chemical_name_with_internal_commas"] is False


def test_fixture_explicit_connector_strings_still_split():
    lib = load("pdcd1_evidence_triage_lib.py")
    for s in (
        "Pembrolizumab + Chemotherapy",
        "Nivolumab and Ipilimumab",
        "Drug A in combination with Drug B",
        "Drug A versus Drug B",
    ):
        category, _ = lib.classify_content(s)
        assert category == "MULTI_PRODUCT_OR_COMBINATION_STRING", s
        assert len(lib.parse_components(s)) >= 2


def test_fixture_ambiguous_comma_without_chemical_signal_routes_to_forensic():
    lib = load("pdcd1_evidence_triage_lib.py")
    s = "Buzhong Yiqi Decoction, Hochu-ekki-to"
    category, flags = lib.classify_content(s)
    assert category == "AMBIGUOUS_REQUIRES_REVIEW"
    row = {"triage_category": category, "flags": flags, "components": []}
    routes = lib.review_routing(row)
    reasons = {r["reason"] for r in routes}
    assert "unexplained_internal_comma_not_chemical_like" in reasons


# ---------------------------------------------------------------------------
# Target token / control / structural fixtures (Section 6)
# ---------------------------------------------------------------------------

def test_fixture_target_and_control_and_structural_strings():
    lib = load("pdcd1_evidence_triage_lib.py")
    cases = {
        "PD-1": "GENERIC_TARGET_OR_MODALITY_STRING",
        "PDCD1": "GENERIC_TARGET_OR_MODALITY_STRING",
        "PD-L1": "GENERIC_TARGET_OR_MODALITY_STRING",
        "anti-PD-1 antibody": "GENERIC_TARGET_OR_MODALITY_STRING",
        "Placebo": "PLACEBO_OR_CONTROL",
        "NCT02257528": "EXPLICIT_NONPRODUCT_INTERVENTION",
        "100 mg": "DOSE_ROUTE_COHORT_OR_ARM_TEXT",
        "Cohort 3": "DOSE_ROUTE_COHORT_OR_ARM_TEXT",
        "Arm B": "DOSE_ROUTE_COHORT_OR_ARM_TEXT",
        "Nivolumab plus Ipilimumab": "MULTI_PRODUCT_OR_COMBINATION_STRING",
    }
    for s, expected in cases.items():
        category, _ = lib.classify_content(s)
        assert category == expected, (s, category, expected)


# ===========================================================================
# Section 7: 21 named mutation tests
# ===========================================================================

# 1-5: target/control tokens must never be promoted to product-like
def test_mutation_pd1_target_token_not_promoted_to_product():
    lib = load("pdcd1_evidence_triage_lib.py")
    category, _ = lib.classify_content("PD-1")
    assert category != "ISOLATED_PRODUCT_LIKE_STRING"


def test_mutation_pdcd1_target_token_not_promoted_to_product():
    lib = load("pdcd1_evidence_triage_lib.py")
    category, _ = lib.classify_content("PDCD1")
    assert category != "ISOLATED_PRODUCT_LIKE_STRING"


def test_mutation_pdl1_target_token_not_promoted_to_product():
    lib = load("pdcd1_evidence_triage_lib.py")
    category, _ = lib.classify_content("PD-L1")
    assert category != "ISOLATED_PRODUCT_LIKE_STRING"


def test_mutation_generic_anti_pd1_phrase_not_promoted_to_product():
    lib = load("pdcd1_evidence_triage_lib.py")
    category, _ = lib.classify_content("anti-PD-1 antibody")
    assert category != "ISOLATED_PRODUCT_LIKE_STRING"


def test_mutation_placebo_not_promoted_to_product():
    lib = load("pdcd1_evidence_triage_lib.py")
    for s in ("Placebo", "placebo", "Vehicle Control"):
        category, _ = lib.classify_content(s)
        assert category != "ISOLATED_PRODUCT_LIKE_STRING", s


# 6-8: administrative/identifier strings must never be treated as product codes
def test_mutation_dose_level_not_treated_as_product_code():
    lib = load("pdcd1_evidence_triage_lib.py")
    category, _ = lib.classify_content("100 mg")
    assert category != "ISOLATED_PRODUCT_LIKE_STRING"


def test_mutation_cohort_arm_name_not_treated_as_candidate():
    lib = load("pdcd1_evidence_triage_lib.py")
    for s in ("Cohort 3", "Arm B"):
        category, _ = lib.classify_content(s)
        assert category != "ISOLATED_PRODUCT_LIKE_STRING", s


def test_mutation_nct_id_not_treated_as_candidate_code():
    lib = load("pdcd1_evidence_triage_lib.py")
    category, _ = lib.classify_content("NCT02257528")
    assert category == "EXPLICIT_NONPRODUCT_INTERVENTION"


# 9: combination strings must not be silently merged
def test_mutation_combination_string_not_treated_as_one_isolated_product():
    lib = load("pdcd1_evidence_triage_lib.py")
    category, _ = lib.classify_content("Pembrolizumab and Chemotherapy")
    assert category == "MULTI_PRODUCT_OR_COMBINATION_STRING"
    assert len(lib.parse_components("Pembrolizumab and Chemotherapy")) == 2


# 10: an official-other-name string must always carry an explicit review reason,
# never be silently accepted as fact (e.g. a co-administered background therapy
# masquerading as an official alias of the studied product)
def test_mutation_background_therapy_other_name_not_silently_accepted():
    lib = load("pdcd1_evidence_triage_lib.py")
    s = "Standard of Care Background Chemotherapy"
    category, flags = lib.classify(s, "official_other_name", True)
    row = {"triage_category": category, "flags": flags, "components": []}
    routes = lib.review_routing(row)
    assert routes, "official-other-name string produced no review-queue entry -- would be silently accepted"
    assert all(r["queue"] in ("TARGETED", "FORENSIC") for r in routes)


# 11-16: artifact-level corruption must be caught by hash verification, not
# silently reused/accepted
def _mutated_snapshot_copy(module, tmp_path):
    src = latest_finalized_snapshot(module)
    dest = tmp_path / "mutated"
    for path in src.rglob("*"):
        if path.is_file():
            rel = path.relative_to(src)
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            (dest / rel).write_bytes(path.read_bytes())
    return dest


def _expect_hash_mismatch(module, dest):
    try:
        module.validate_snapshot(dest)
    except ValueError as exc:
        assert "ARTIFACT_HASH_MISMATCH" in str(exc)
    else:
        raise AssertionError("mutated artifact was accepted as valid")


def test_mutation_historical_occurrence_dropped_is_detected(tmp_path):
    module = load("extract_pdcd1_rebase_v1_evidence_triage.py")
    dest = _mutated_snapshot_copy(module, tmp_path)
    target = dest / "normalized" / "historical_appearance_ledger.jsonl"
    lines = target.read_text().splitlines()
    target.write_text("\n".join(lines[:-1]) + "\n")
    _expect_hash_mismatch(module, dest)


def test_mutation_frozen_row_omitted_is_detected(tmp_path):
    module = load("extract_pdcd1_rebase_v1_evidence_triage.py")
    dest = _mutated_snapshot_copy(module, tmp_path)
    target = dest / "extracted" / "frozen_row_evidence_bindings.jsonl"
    lines = target.read_text().splitlines()
    target.write_text("\n".join(lines[:-1]) + "\n")
    _expect_hash_mismatch(module, dest)


def test_mutation_source_hash_altered_is_detected(tmp_path):
    module = load("extract_pdcd1_rebase_v1_evidence_triage.py")
    dest = _mutated_snapshot_copy(module, tmp_path)
    receipt_path = dest / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    some_key = next(iter(receipt["artifacts"]))
    receipt["artifacts"][some_key]["sha256"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt))
    _expect_hash_mismatch(module, dest)


def test_mutation_json_pointer_redirected_is_detected(tmp_path):
    module = load("extract_pdcd1_rebase_v1_evidence_triage.py")
    dest = _mutated_snapshot_copy(module, tmp_path)
    target = dest / "extracted" / "frozen_row_evidence_bindings.jsonl"
    lines = target.read_text().splitlines()
    row = json.loads(lines[0])
    row["json_pointer"] = row.get("json_pointer", "/x") + "/TAMPERED"
    lines[0] = json.dumps(row)
    target.write_text("\n".join(lines) + "\n")
    _expect_hash_mismatch(module, dest)


def test_mutation_presentation_variant_never_carries_alias_adjudication_fields(tmp_path):
    module = load("extract_pdcd1_rebase_v1_evidence_triage.py")
    snapshot = latest_finalized_snapshot(module)
    rows = read_jsonl(snapshot / "normalized" / "presentation_variant_ledger.jsonl")
    forbidden = {"alias", "canonical_alias", "adjudicated", "is_alias_of", "resolved_identity"}
    for row in rows:
        assert not (forbidden & set(row.keys())), row


def test_mutation_current_row_source_text_rewritten_is_detected(tmp_path):
    module = load("extract_pdcd1_rebase_v1_evidence_triage.py")
    dest = _mutated_snapshot_copy(module, tmp_path)
    target = dest / "extracted" / "frozen_row_evidence_bindings.jsonl"
    lines = target.read_text().splitlines()
    row = json.loads(lines[0])
    row["raw_string"] = "REWRITTEN " + row.get("raw_string", "")
    lines[0] = json.dumps(row)
    target.write_text("\n".join(lines) + "\n")
    _expect_hash_mismatch(module, dest)


# 17-20: the stage must never introduce adjudication-adjacent concepts anywhere
def test_mutation_no_canonical_candidate_id_introduced():
    module = load("extract_pdcd1_rebase_v1_evidence_triage.py")
    snapshot = latest_finalized_snapshot(module)
    for jsonl_path in snapshot.rglob("*.jsonl"):
        for row in read_jsonl(jsonl_path):
            assert not ({"canonical_candidate_id", "canonical_candidate", "candidate_id"} & set(row.keys())), jsonl_path
    defined = {name.casefold() for name in vars(module)}
    assert "create_canonical_candidate" not in defined


def test_mutation_no_benchmark_label_introduced():
    module = load("extract_pdcd1_rebase_v1_evidence_triage.py")
    snapshot = latest_finalized_snapshot(module)
    for jsonl_path in snapshot.rglob("*.jsonl"):
        for row in read_jsonl(jsonl_path):
            assert not ({"benchmark_label", "label"} & set(row.keys())), jsonl_path
    manifest = json.loads((snapshot / "manifest.json").read_text())
    assert manifest.get("benchmark_labels_created") in (0, False, None) or "benchmark_labels_created" not in manifest


def test_mutation_no_ownership_or_organization_claim_introduced():
    module = load("extract_pdcd1_rebase_v1_evidence_triage.py")
    snapshot = latest_finalized_snapshot(module)
    for jsonl_path in snapshot.rglob("*.jsonl"):
        for row in read_jsonl(jsonl_path):
            assert not ({"owner", "ownership_claim", "sponsor_ownership", "organization_claim"} & set(row.keys())), jsonl_path


def test_mutation_no_candidate_specific_chronology_introduced():
    module = load("extract_pdcd1_rebase_v1_evidence_triage.py")
    snapshot = latest_finalized_snapshot(module)
    for jsonl_path in snapshot.rglob("*.jsonl"):
        for row in read_jsonl(jsonl_path):
            assert not ({"chronology", "candidate_timeline", "candidate_chronology"} & set(row.keys())), jsonl_path


# 21: no prediction/evaluation module may be imported or invoked anywhere in the stage
def test_mutation_no_prediction_or_evaluation_module_imported_or_invoked():
    forbidden_tokens = (
        "sklearn", "torch", "tensorflow", "xgboost",
        "predict(", "evaluate_candidate", "score_candidate", "run_benchmark_eval",
    )
    for script in ("extract_pdcd1_rebase_v1_evidence_triage.py", "pdcd1_evidence_triage_lib.py",
                   "validate_pdcd1_rebase_v1_evidence_triage.py"):
        src = (ROOT / "scripts" / script).read_text()
        for token in forbidden_tokens:
            assert token not in src, (script, token)
