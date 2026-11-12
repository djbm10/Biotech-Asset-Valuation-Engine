"""Cycle U1: a concrete next action for every tool UNKNOWN (research/dealscreen_unknown_actions_v1/ACCEPTANCE.md).

Held-back cases: other therapy areas (liver, colorectal, ulcerative colitis) and fictional target symbols, plus
the adversarial cases named in U1-4. They test logic only and assert no real-world facts about programs."""

from __future__ import annotations

import pytest

from bve.dealscreen import diagnostics as dg
from bve.dealscreen import indication_relations as ir
from bve.se.schemas.contracts import TargetTerm

HCC = ["hepatocellular carcinoma"]
CRC = ["colorectal adenocarcinoma"]
UC = ["ulcerative colitis"]
GASTRIC = ["gastric adenocarcinoma", "gastroesophageal junction adenocarcinoma"]
SCOPE_WORDS = ("in scope", "out of scope", "in-scope", "out-of-scope", "exclude", "eligible", "not a fit")


def name_class(name: str, requested: list[str]) -> str:
    return ir.classify_name(name, ir.requested_codes(requested)).category


# -- indication classes (U1-4) ----------------------------------------------------------------------
@pytest.mark.parametrize("name, requested, expected", [
    ("Locally advanced unresectable or metastatic solid tumours", HCC, ir.BASKET),
    ("Solid Tumour, Adult", CRC, ir.BASKET),
    ("Chronic disease", UC, ir.BASKET),
    ("Moderate to Severe Ulcerative Colitis", UC, ir.READS_AS_REQUESTED),
    ("Hepatocellular Carcinoma (HCC)", HCC, ir.READS_AS_REQUESTED),
    ("Inflammatory Bowel Disease", UC, ir.BROADER_THAN_REQUESTED),
    ("Liver Neoplasm", HCC, ir.BROADER_THAN_REQUESTED),
    ("Colorectal Cancer", CRC, ir.AMBIGUOUS_NAME_ALL_BROADER),
    ("Rectal Cancer", CRC, ir.AMBIGUOUS_NAME),
    ("Liver Cancer", HCC, ir.AMBIGUOUS_NAME_ALL_BROADER),  # "Adult Liver Carcinoma" read without its population
    ("Colon Carcinoma", CRC, ir.OVERLAPS_REQUESTED),
    ("Colorectal and gastric tumours", CRC, ir.NAMES_REQUESTED_SITE),
    ("Liver Cancer, Adult", HCC, ir.NAMES_REQUESTED_SITE),
    ("Cholangiocarcinoma", HCC, ir.DIFFERENT_DISEASE),
    ("Crohn Disease", UC, ir.DIFFERENT_DISEASE),
    ("Hepatic and biliary tumours", HCC, ir.UNREADABLE),
])
def test_each_indication_class(name, requested, expected):
    assert name_class(name, requested) == expected


def test_a_different_site_sharing_a_histology_word_is_a_different_disease():
    assert name_class("pancreatic adenocarcinoma", GASTRIC) == ir.DIFFERENT_DISEASE
    assert name_class("Gastric Adenocarcinoma", CRC) == ir.DIFFERENT_DISEASE


@pytest.mark.parametrize("name, requested", [
    ("solid tumors other than gastric", GASTRIC), ("Non-liver solid tumours", HCC),
    ("Solid tumours excluding colorectal", CRC), ("All solid tumours except liver", HCC),
])
def test_a_requested_site_after_an_exclusion_does_not_count(name, requested):
    assert name_class(name, requested) != ir.NAMES_REQUESTED_SITE


@pytest.mark.parametrize("name, requested", [
    ("Fibrolamellar Carcinoma", HCC), ("Rectal Adenocarcinoma", CRC), ("Colon Adenocarcinoma", CRC),
])
def test_a_subtype_of_the_requested_concept_is_never_broader(name, requested):
    reading = ir.classify_name(name, ir.requested_codes(requested))
    assert reading.category == ir.READS_AS_REQUESTED
    assert all(rel == ir.REQUESTED for _, rel in reading.concepts)


@pytest.mark.parametrize("name, requested", [("Rectal Cancer", CRC)])
def test_an_ambiguous_name_with_a_non_broader_reading_is_ambiguous(name, requested):
    reading = ir.classify_name(name, ir.requested_codes(requested))
    assert reading.category == ir.AMBIGUOUS_NAME
    assert any(rel != ir.BROADER for _, rel in reading.concepts) and len(reading.concepts) > 1


def test_site_words_come_from_site_ancestors_never_histology_or_qualifiers():
    for code in ir.requested_codes(HCC + CRC):
        phrases = ir.site_phrases(code)
        assert phrases and not {"carcinoma", "adenocarcinoma", "primary", "adult", "advanced"} & {
            w for p in phrases for w in p.split()}
    assert ir.site_phrases(next(iter(ir.requested_codes(UC)))) == frozenset()


def test_overlap_is_not_reported_as_a_different_disease():
    d = dg.indication_diagnostic(["Colon Carcinoma"], CRC)
    assert d["class"] == ir.OVERLAPS_REQUESTED
    assert "shares subtypes" in d["action"] and "neither a requested indication" not in d["action"]


def test_the_program_class_is_the_first_name_class_in_order_and_every_name_is_kept():
    d = dg.indication_diagnostic(["Advanced Solid Tumours", "Cholangiocarcinoma", "Liver Neoplasm"], HCC)
    assert d["class"] == ir.BROADER_THAN_REQUESTED
    assert [n["class"] for n in d["names"]] == [ir.BASKET, ir.DIFFERENT_DISEASE, ir.BROADER_THAN_REQUESTED]
    assert d["action"].startswith("'Liver Neoplasm'") and "(and 2 other name(s) on record)" in d["action"]


def test_indication_actions_name_the_record_and_the_deciding_fact_without_scope_words():
    for names in ([], ["Advanced Solid Tumours"], ["Cholangiocarcinoma"], ["Liver Cancer"]):
        d = dg.indication_diagnostic(names, HCC)
        action = d["action"]
        assert ("No indication on record." in action) if not names else (f"'{names[0]}'" in action)
        assert "What would pass the gate: a cited source naming hepatocellular carcinoma" in action
        assert "never fails on this evidence" in action and d["closes"] == "pass"
        assert "assert --field indication" in action
        assert not any(w in action.casefold() for w in SCOPE_WORDS)
    assert dg.indication_diagnostic([], HCC)["class"] == ir.NO_RECORD


# -- target classes -----------------------------------------------------------------------------------
REQ = [TargetTerm(canonical_id="ABC1", label="Abcin 1.2")]
READ = {"XYZ": "XYZ", "QRS-7": "QRS7"}.get


@pytest.mark.parametrize("values, expected", [
    ([], dg.NO_RECORD),
    (["ABC1.2 x CD99"], dg.SOURCE_NAMES_REQUIRED_TARGET),       # pair notation
    (["Abcin-1.2; Mysterin"], dg.SOURCE_NAMES_REQUIRED_TARGET),  # label, unreadable partner
    (["PQ-1; XYZ"], dg.SOURCE_NAMES_OTHER_TARGETS),
    (["ABC1.1"], dg.SOURCE_NAMES_OTHER_TARGETS),                # another isoform of the gene is not the target
    (["ABC12"], dg.SOURCE_NAMES_OTHER_TARGETS),                 # a longer symbol is not the target
    (["Undisclosed"], dg.UNREADABLE),
])
def test_each_target_class(values, expected):
    assert dg.target_diagnostic(values, False, REQ, READ, ";")["class"] == expected


def test_other_targets_are_named_and_the_required_one_is_stated():
    d = dg.target_diagnostic(["PQ-1; QRS-7"], False, REQ, READ, ";")
    assert "The record names QRS-7 (QRS7); none is ABC1 (Abcin 1.2)." in d["action"]
    assert "It also names 'PQ-1', which the target authority does not read; it is not written as ABC1" in d["action"]
    assert "assert --field target" in d["action"]


def test_conflicting_target_values_are_shown():
    d = dg.target_diagnostic(["XYZ", "QRS-7"], True, REQ, READ, ";")
    assert d["class"] == dg.CONFLICTING and "'XYZ', 'QRS-7'" in d["action"] and "confirming the right claim" in d["action"]


def test_no_record_never_suggests_rejecting_a_claim():
    for d in (dg.target_diagnostic([], False, REQ, READ, ";"), dg.modality_diagnostic([], False, False, ["X"]),
              dg.phase_diagnostic([], False), dg.indication_diagnostic([], HCC)):
        assert "reject" not in d["action"] and d["observed"] == []


# -- modality, phase, other ------------------------------------------------------------------------------
def test_modality_classes():
    allowed = ["MONOCLONAL_ANTIBODY"]
    assert dg.modality_diagnostic([], False, False, allowed)["class"] == dg.NO_RECORD
    assert dg.modality_diagnostic(["Widget"], False, False, allowed)["class"] == dg.SOURCE_MODALITY_UNREADABLE
    assert dg.modality_diagnostic(["Antibody"], False, True, allowed)["class"] == dg.COMBINATION_PRODUCT
    d = dg.modality_diagnostic(["Antibody", "Peptide"], True, False, allowed)
    assert d["class"] == dg.CONFLICTING and "monoclonal antibody" in d["action"]


def test_phase_classes():
    assert dg.phase_diagnostic([], False)["class"] == dg.NO_RECORD
    assert dg.phase_diagnostic(["Stage gamma"], False)["class"] == dg.UNREADABLE
    assert dg.phase_diagnostic(["Phase 2", "Phase 1"], True)["class"] == dg.CONFLICTING


def test_other_gates_keep_the_generic_action_when_no_field_can_be_asserted():
    assert "assert --field mechanism" in dg.other_diagnostic([], "mechanism", "Research it.")["action"]
    d = dg.other_diagnostic(["x"], None, "Research fact type 'evaluable_patients'.")
    assert d["class"] == dg.OTHER and "S&E: Research fact type 'evaluable_patients'." in d["action"]


# -- through the workspace (synthetic landscape) ----------------------------------------------------------
CLASSES = {*ir.ORDER, dg.CONFLICTING, dg.UNREADABLE, dg.OTHER, dg.SOURCE_NAMES_REQUIRED_TARGET,
           dg.SOURCE_NAMES_OTHER_TARGETS, dg.SOURCE_MODALITY_UNREADABLE, dg.COMBINATION_PRODUCT}


def _unknown(screen: dict) -> set[str]:
    return {d["requirement_id"] for d in screen["decisions"] if (d["analyst_override"] or d["status"]) == "UNKNOWN"}


@pytest.fixture
def synthetic_ws(tmp_path, demo_dir, normalizer):
    from bve.dealscreen.workspace import Workspace

    ws = Workspace(tmp_path / "ws")
    ws.import_landscape(demo_dir / "landscape_200.csv", demo_dir / "profile_synthetic_vendor.yaml",
                        demo_dir / "buyer_tl1a_ibd.yaml")
    ws.screen(normalizer)
    return ws


def test_every_unknown_on_a_program_not_excluded_has_a_diagnostic(synthetic_ws):
    screens = synthetic_ws.screening()["screens"]
    open_screens = [s for s in screens if s["disposition"] != "EXCLUDED" and _unknown(s)]
    assert open_screens
    for s in screens:
        diagnostics = s["unknown_diagnostics"]
        if s["disposition"] == "EXCLUDED":
            assert diagnostics == {}
            continue
        assert set(diagnostics) == _unknown(s), s["program_name"]
        for d in diagnostics.values():
            assert d["class"] in CLASSES and isinstance(d["observed"], list) and d["policy"] == dg.POLICY
            assert any(lead in d["action"] for lead in ("What decides the gate", "What would pass the gate", "S&E:"))
            assert not any(w in d["action"].casefold() for w in SCOPE_WORDS)


def test_diagnostics_change_no_decision_disposition_rank_or_transaction(synthetic_ws, normalizer, monkeypatch):
    from bve.dealscreen import screening

    def strip(result: dict) -> dict:
        return {**result, "screens": [{k: v for k, v in s.items() if k != "unknown_diagnostics"}
                                      for s in result["screens"]]}

    with_diagnostics = strip(synthetic_ws.screen(normalizer).to_dict())
    monkeypatch.setattr(screening, "diagnose", lambda *a, **k: {})
    without = strip(synthetic_ws.screen(normalizer).to_dict())
    assert with_diagnostics == without


def test_entering_the_fact_an_indication_action_names_decides_the_gate(synthetic_ws, normalizer):
    from bve.dealscreen.review import Action, ReviewerKind

    spec = synthetic_ws.buyer()
    target = next(s for s in synthetic_ws.screening()["screens"] if "strategy.indication" in s["unknown_diagnostics"])
    action = target["unknown_diagnostics"]["strategy.indication"]["action"]
    wanted = spec.problem.strategic_gap.indications[0]
    assert wanted in action and "assert --field indication" in action
    synthetic_ws.decision_log().record(
        action=Action.ASSERT_FACT, subject_id=target["asset_id"], new_state="ASSERTED", reviewer_id="analyst-1",
        rationale="trial registry title", reviewer_kind=ReviewerKind.HUMAN,
        detail={"field": "indication", "value": wanted, "source_url": "https://x.test/trial",
                "evidence_span": f"patients with {wanted}"},
        context=synthetic_ws.decision_context(normalizer))
    synthetic_ws.screen(normalizer)
    after = {s["asset_id"]: s for s in synthetic_ws.screening()["screens"]}[target["asset_id"]]
    assert "strategy.indication" not in _unknown(after)
    assert "strategy.indication" not in after["unknown_diagnostics"]


def test_workbook_and_memo_show_the_actions(synthetic_ws, tmp_path):
    from openpyxl import load_workbook

    from bve.dealscreen.memo import build_memo
    from bve.dealscreen.workbook import export_workbook

    book = load_workbook(export_workbook(synthetic_ws, tmp_path / "out.xlsx"), read_only=True)
    gates = [r for r in book["Diligence"].iter_rows(values_only=True) if r[2] == "GATE_UNKNOWN"]
    assert gates and all(r[4] and " (S&E: " in r[5] and r[5].split(" (S&E: ")[0] for r in gates)
    rows = list(book["Screening"].iter_rows(values_only=True))
    header = next(r for r in rows if r and r[0] == "Asset id")
    column = header.index(next(h for h in header if h and h.startswith("Open gates: what the record holds")))
    classes = [r[column] for r in rows[rows.index(header) + 1:] if r[column]]
    assert classes and all(":" in c for c in classes)
    lines = build_memo(synthetic_ws).splitlines()
    head = next(i for i, line in enumerate(lines) if "have one open gate" in line)
    gate_lines = []
    for line in lines[head + 1:]:
        if not line.startswith("  - "):
            break
        gate_lines.append(line)
    assert gate_lines and not any(w in line.casefold() for line in [lines[head], *gate_lines] for w in SCOPE_WORDS)
    from bve.dealscreen.memo import _GATE_WORDS

    by_gate = {line[4:].split(" gate (")[0]: line for line in gate_lines}
    single = [s for s in synthetic_ws.screening()["screens"] if s["disposition"] == "UNRESOLVED" and len(_unknown(s)) == 1]
    assert single and f"- {len(single)} unresolved program(s) have one open gate" in lines[head]
    for s in single:
        (gate, diag), = s["unknown_diagnostics"].items()
        line = by_gate[_GATE_WORDS.get(gate, gate)]
        verb = "passed only by" if diag.get("closes") == "pass" else "decided by"
        assert f"{verb} {diag['fact']}" in line
        # Every record phrase is shown (review U1 N13); a name past the cap is counted as "(+N more)".
        assert diag["summary"] in line and (s["program_name"] in line or "(+" in line), (s["program_name"], line)


def _screen(i: int, gates: list[str], summary: str) -> dict:
    return {"program_name": f"Program {i}", "rank": None,
            "decisions": [{"requirement_id": g, "status": "UNKNOWN", "analyst_override": None} for g in gates]
            + [{"requirement_id": "evidence.passed", "status": "PASS", "analyst_override": None}],
            "unknown_diagnostics": {g: {"summary": summary, "fact": "a cited fact", "field": "f"} for g in gates}}


def test_the_memo_list_of_single_gate_programs_is_bounded_and_skips_programs_with_several_open_gates():
    from bve.dealscreen.memo import _one_gate_lines

    gates = [f"gate.{g}" for g in range(9)]

    def lines(n: int) -> list[str]:
        return _one_gate_lines([_screen(i, [gates[i % 9]], f"record class {i % 7}") for i in range(n)]
                               + [_screen(n + 1, gates[:2], "record class 0")])

    large, larger = lines(600), lines(6000)
    assert larger[0].startswith("- 6000 unresolved program(s) have one open gate")  # the multi-gate one is skipped
    assert len(larger) == len(large) <= 8 and "more on other gates" in larger[-1]
    # Every phrase is shown, so the size is bounded by gates x classes x names, not by the number of programs.
    assert len(" ".join(larger).split()) <= len(" ".join(large).split()) < 800
    assert _one_gate_lines([_screen(1, gates[:2], "x")]) == []


# -- revision 2: the adversarial review's findings, on held-out areas (REVIEW.md D1-D13, J1-J3) ---------------
FL, T2DM, HNSCC = ["follicular lymphoma"], ["type 2 diabetes mellitus"], ["head and neck squamous cell carcinoma"]


@pytest.mark.parametrize("requested", [["diffuse large b-cell lymphoma"], ["generalized myasthenia gravis"],
                                       ["glioblastoma"], ["breast cancer"]])
def test_a_request_that_is_not_one_concept_is_reported_and_no_name_is_compared(requested):
    d = dg.indication_diagnostic(["Some Disease", "Another Disease"], requested)
    assert d["class"] == ir.REQUEST_NOT_ONE_CONCEPT and d["field"] is None
    assert {n["class"] for n in d["names"]} == {ir.REQUEST_NOT_ONE_CONCEPT}
    assert "edit the buyer file" in d["action"] and "assert --field" not in d["action"]


@pytest.mark.parametrize("request_text", ["glioblastoma", "diffuse large b-cell lymphoma"])
def test_a_suggested_restatement_resolves_to_one_of_the_requested_concepts(request_text):
    name, concept = ir.restatement(request_text)
    code = ir.disease_code(name)
    assert code is not None and code in ir._index(request_text) and ir.label(code) == concept
    assert not set(ir.norm(concept).split()) & {"childhood", "adult", "pediatric"}


def test_a_partly_resolved_request_still_names_the_cited_fact_and_the_restatement():
    d = dg.indication_diagnostic(["Lung Cancer"], ["lung cancer", "lung non-small cell carcinoma"])
    assert d["class"] == ir.REQUEST_NOT_ONE_CONCEPT and d["field"] == "indication"
    assert "the gate itself still compares names with lung non-small cell carcinoma" in d["action"]
    assert "Or, for every program, the buyer's request restated" in d["action"]


def test_a_condition_rule_request_names_a_cited_source_the_rule_matches():
    d = dg.indication_diagnostic(["Some lymphoma"], ["INDICATION:B_CELL_LYMPHOMA"])
    assert d["class"] == ir.REQUEST_NOT_ONE_CONCEPT and d["field"] == "indication"
    assert "words the S&E rule INDICATION:B_CELL_LYMPHOMA matches" in d["action"]
    assert "restated" not in d["action"]


def test_the_cli_warns_once_about_an_unread_request(capsys):
    from types import SimpleNamespace

    from bve.cli.dealscreen import _warn_unread_request

    gap = SimpleNamespace(indications=["glioblastoma", "hepatocellular carcinoma"])
    ws = SimpleNamespace(buyer=lambda: SimpleNamespace(problem=SimpleNamespace(strategic_gap=gap)))
    _warn_unread_request(ws)
    err = capsys.readouterr().err
    assert err.count("WARNING") == 1 and "'glioblastoma' matches 3 NCIt concepts" in err and "'GBM'" in err


@pytest.mark.parametrize("name, requested", [
    ("Hodgkin Lymphoma", FL), ("Type 1 Diabetes Mellitus", T2DM), ("Hemophilia B", ["hemophilia a"]),
    ("Bladder Small Cell Carcinoma", ["small cell lung carcinoma"]),
    ("Acute Lymphocytic Leukemia", ["chronic lymphocytic leukemia"]),
])
def test_a_lineage_or_histology_word_is_not_a_requested_site(name, requested):
    reading = ir.classify_name(name, ir.requested_codes(requested))
    assert reading.category == ir.DIFFERENT_DISEASE and reading.sites == ()


def test_site_phrases_are_whole_sites_never_lineage_cell_type_or_a_word_of_a_longer_site():
    phrases = {q: ir.site_phrases(ir.disease_code(q)) for q in (*FL, *T2DM, *HNSCC, *HCC, "hemophilia a")}
    assert phrases["follicular lymphoma"] == phrases["type 2 diabetes mellitus"] == phrases["hemophilia a"] == set()
    assert phrases["head and neck squamous cell carcinoma"] == {"head and neck"}
    assert phrases["hepatocellular carcinoma"] == {"liver"}
    assert ir.classify_name("Adenocarcinoma of the Head of the Pancreas",
                            ir.requested_codes(HNSCC)).category != ir.NAMES_REQUESTED_SITE


def test_a_site_ncit_names_only_after_the_histology_is_found_with_its_abbreviation():
    phrases = ir.site_phrases(ir.disease_code("gastroesophageal junction adenocarcinoma"))
    assert {"gastroesophageal junction", "esophagogastric junction", "gej"} <= phrases
    d = dg.indication_diagnostic(["GEJ cancer"], GASTRIC)
    assert d["class"] == ir.NAMES_REQUESTED_SITE and "names GEJ (gastroesophageal junction)" in d["action"]


@pytest.mark.parametrize("name, requested", [
    ("Adenocarcinoma (PDAC)", GASTRIC), ("Lymphoma (DLBCL)", FL), ("Leukemia (AML)", ["chronic lymphocytic leukemia"]),
])
def test_a_parenthetical_that_does_not_abbreviate_the_words_before_it_is_kept(name, requested):
    reading = ir.classify_name(name, ir.requested_codes(requested))
    assert reading.category == ir.UNREADABLE and not reading.steps


def test_an_acronym_of_the_words_before_it_is_removed_and_shown():
    reading = ir.classify_name("Non-Small Cell Lung Cancer (NSCLC)", ir.requested_codes(["lung non-small cell carcinoma"]))
    assert reading.category == ir.READS_AS_REQUESTED and reading.steps


@pytest.mark.parametrize("name", ["Solid tumors excl. liver", "Solid tumours (liver cancer excluded)",
                                  "Solid tumors, no liver", "Solid tumors (ex-liver)", "Solid tumors w/o liver",
                                  "Solid tumours apart from liver", "Solid tumors besides liver"])
def test_every_exclusion_form_masks_the_site(name):
    assert name_class(name, HCC) != ir.NAMES_REQUESTED_SITE


def test_a_negation_scopes_over_one_word_only():
    assert name_class("HER2-negative, not previously treated liver cancer", HCC) == ir.NAMES_REQUESTED_SITE


@pytest.mark.parametrize("name, requested", [
    ("Colorectal cancer with liver metastases", HCC), ("Uveal melanoma metastatic to the liver", HCC),
    ("Gastric-type endocervical adenocarcinoma", GASTRIC),
])
def test_a_metastatic_or_type_role_is_not_the_disease_site(name, requested):
    assert name_class(name, requested) != ir.NAMES_REQUESTED_SITE


def test_exact_label_and_unstated_population_choices_are_shown():
    exact = ir.classify_name("Adenocarcinoma", ir.requested_codes(CRC))
    assert exact.category == ir.BROADER_THAN_REQUESTED and "label names exactly" in exact.notes[0]
    swapped = dg.indication_diagnostic(["Colorectal (Colon or Rectal) Cancer"], CRC)
    assert swapped["class"] == ir.BROADER_THAN_REQUESTED and "the record states no population" in swapped["action"]
    stated = ir.classify_name("Childhood Liver Cancer", ir.requested_codes(HCC))
    assert not stated.notes and stated.category == ir.OVERLAPS_REQUESTED


@pytest.mark.parametrize("name, requested", [("Oesophageal adenocarcinoma", ["esophageal adenocarcinoma"]),
                                             ("Haemophilia A", ["hemophilia a"]),
                                             ("Gastro-oesophageal junction adenocarcinoma", GASTRIC)])
def test_british_spelling_and_hyphens_read_as_a_clean_up_the_gate_does_not_apply(name, requested):
    d = dg.indication_diagnostic([name], requested)
    assert d["class"] == ir.READS_AS_REQUESTED and "a clean-up the gate does not apply" in d["action"]
    assert d["names"][0]["screen_applies_steps"] is False


def test_screen_readings_are_shown_without_claiming_the_gate_skips_them():
    d = dg.indication_diagnostic(["AChR+ generalized myasthenia gravis"], ["myasthenia gravis"])
    assert "biomarker subset 'AChR+' read as the disease" in d["action"]
    assert "the gate does not apply" not in d["action"]


def test_the_lead_name_is_the_first_of_its_class_in_record_order():
    first = dg.indication_diagnostic(["Liver Neoplasm", "Malignant Liver Neoplasm"], HCC)
    second = dg.indication_diagnostic(["Malignant Liver Neoplasm", "Liver Neoplasm"], HCC)
    assert first["action"].startswith("'Liver Neoplasm'") and second["action"].startswith("'Malignant Liver Neoplasm'")


def test_a_resolved_different_disease_at_a_requested_site_says_both():
    d = dg.indication_diagnostic(["Liver Abscess"], HCC)
    assert d["class"] == ir.DIFFERENT_DISEASE and "although it names liver, a requested site" in d["action"]


def test_a_gate_with_no_landscape_field_says_so():
    d = dg.other_diagnostic(["x"], None, "Research it.", "evaluable_patients")
    assert "DealScreen maps no landscape field to this gate's fact (evaluable_patients)." in d["action"]


def test_no_action_tells_the_analyst_to_reject_a_claim_unless_values_conflict():
    for d in (dg.target_diagnostic(["XYZ"], False, REQ, READ, ";"), dg.indication_diagnostic(["Crohn Disease"], UC),
              dg.modality_diagnostic(["Widget"], False, False, ["X"]), dg.phase_diagnostic(["Stage gamma"], False)):
        assert "reject" not in d["action"]


@pytest.mark.parametrize("values, expected", [
    (["ABC 1.2"], dg.SOURCE_NAMES_REQUIRED_TARGET), (["ABC-1.2"], dg.SOURCE_NAMES_REQUIRED_TARGET),
    (["ABC1 isoform 2"], dg.SOURCE_NAMES_REQUIRED_TARGET), (["ABC1's isoform 2"], dg.SOURCE_NAMES_REQUIRED_TARGET),
    (["ABC1.2xCD99"], dg.SOURCE_NAMES_REQUIRED_TARGET), (["ABC1.1xCD99"], dg.SOURCE_NAMES_OTHER_TARGETS),
    (["Undisclosed Target"], dg.UNREADABLE), (["Novel target"], dg.UNREADABLE), (["TAA"], dg.UNREADABLE),
    (["not ABC1.2"], dg.SOURCE_STATES_NOT_REQUIRED_TARGET),
    (["ABC1.2-negative"], dg.SOURCE_STATES_NOT_REQUIRED_TARGET),
    (["formerly ABC1.2"], dg.SOURCE_STATES_NOT_REQUIRED_TARGET), (["ABC1A2"], dg.SOURCE_MAY_NAME_REQUIRED_TARGET),
    (["Abcin 1 isoform A2"], dg.SOURCE_MAY_NAME_REQUIRED_TARGET),
])
def test_target_forms_from_the_review(values, expected):
    d = dg.target_diagnostic(values, False, REQ, READ, ";")
    assert d["class"] == expected, d["record"]
    assert "without stating isoform" not in d["record"] or values == ["ABC1"]


def test_another_isoform_is_never_called_not_written_as_the_symbol():
    d = dg.target_diagnostic(["ABC1.1xCD99"], False, REQ, READ, ";")
    assert "ABC1.1 (isoform 1 of ABC1, not isoform 2); none is ABC1 (Abcin 1.2)." in d["record"]
    assert "'CD99', which the target authority does not read" in d["record"]


# -- revision 3: the second adversarial review's findings (REVIEW2.md N1-N13), on held-out inputs ---------------
GAS = ["gastric adenocarcinoma", "gastroesophageal junction adenocarcinoma"]


@pytest.mark.parametrize("name", ["Stage IV gastric cancer", "Stage III gastric cancer"])
def test_n1_a_stage_concept_under_the_requests_parent_is_not_a_different_disease(name):
    d = dg.indication_diagnostic([name], GAS)
    assert d["class"] == ir.UNDER_REQUESTED_PARENT, d["record"]
    assert "the record states no edition" in d["record"] and "names gastric" in d["record"]
    assert ir.ORDER.index(ir.UNDER_REQUESTED_PARENT) < ir.ORDER.index(ir.BASKET)


def test_n1_a_sibling_naming_another_site_is_still_a_different_disease():
    assert dg.indication_diagnostic(["Pancreatic adenocarcinoma"], GAS)["class"] == ir.DIFFERENT_DISEASE


def test_n1_held_out_stage_concept_for_another_site():
    assert dg.indication_diagnostic(["Stage IV colorectal cancer"], ["colorectal adenocarcinoma"])["class"] \
        == ir.UNDER_REQUESTED_PARENT


@pytest.mark.parametrize("request_text", ["pnh", "astrocytoma", "mesothelioma", "endometrial cancer",
                                          "gastric cancer"])
def test_n2_no_restatement_unless_it_is_the_requests_exact_label_concept(request_text):
    found = ir.restatement(request_text)
    if found is not None:
        assert ir.norm(found[1]) == ir.norm(request_text)


def test_n2_unrelated_readings_are_listed_for_the_buyer_to_choose():
    d = dg.indication_diagnostic(["x"], ["pnh"])
    assert "the buyer chooses among Periventricular Nodular Heterotopia; Paroxysmal Nocturnal Hemoglobinuria" \
        in d["action"]
    assert "for example" not in d["action"]


def test_n2_the_cli_warning_lists_the_readings(capsys):
    from types import SimpleNamespace

    from bve.cli.dealscreen import _warn_unread_request

    gap = SimpleNamespace(indications=["pnh"])
    _warn_unread_request(SimpleNamespace(buyer=lambda: SimpleNamespace(problem=SimpleNamespace(strategic_gap=gap))))
    err = capsys.readouterr().err
    assert "Paroxysmal Nocturnal Hemoglobinuria" in err and "Periventricular Nodular Heterotopia" in err
    assert "choose one" in err


@pytest.mark.parametrize(("name", "site"), [("Gastroesophageal Junction Cancer", "gastroesophageal junction"),
                                            ("Gastro-esophageal Junction Cancer", "gastroesophageal junction"),
                                            ("Esophagogastric junction cancer", "esophagogastric junction")])
def test_n3_a_multi_word_site_is_reported(name, site):
    d = dg.indication_diagnostic([name], GAS)
    assert d["class"] == ir.NAMES_REQUESTED_SITE and f"names {site}" in d["record"]


def test_n3_held_out_multi_word_site():
    d = dg.indication_diagnostic(["Recurrent head and neck cancer, platinum-refractory"], HNSCC)
    assert d["class"] == ir.NAMES_REQUESTED_SITE


@pytest.mark.parametrize(("british", "american"), [("Gastroesophageal", "Gastroesophageal"),
                                                   ("tracheoesophageal", "tracheoesophageal"),
                                                   ("oesophageal", "esophageal"),
                                                   ("gastro-oesophageal", "gastro-esophageal")])
def test_n3_spelling_is_changed_only_at_a_word_start_or_after_o(british, american):
    assert ir.us_spelling(british) == american


@pytest.mark.parametrize("name", ["Relapsed/refractory ALL", "ALL", "Adult ALL", "ALL, children"])
def test_n4_an_acronym_the_authority_reads_is_not_a_basket(name):
    assert dg.indication_diagnostic([name], ["acute lymphoblastic leukemia"])["class"] != ir.BASKET


def test_n4_a_basket_in_lower_case_is_still_a_basket():
    assert dg.indication_diagnostic(["All solid tumors"], ["acute lymphoblastic leukemia"])["class"] == ir.BASKET


@pytest.mark.parametrize(("request_text", "name"), [
    ("Recurrent Endocrine Carcinoma", "Endocrine therapy-resistant breast cancer"),
    ("Metastatic Neuroendocrine Tumor", "Neuroendocrine prostate cancer"),
    ("neuroendocrine carcinoma", "Pancreatic Neuroendocrine Tumor"),
    ("Hematologic Neoplasm with Germline DDX41 Mutation", "Hematologic toxicity"),
    ("Toxemia of Pregnancy", "Pregnancy-associated breast cancer"),
    ("Immunodeficiency with Hyper-IgM Type 2", "Severe combined immunodeficiency"),
    ("Lymphoproliferative Disorder", "X-linked lymphoproliferative disease")])
def test_n5_lineage_state_and_therapy_words_are_not_sites(request_text, name):
    d = dg.indication_diagnostic([name], [request_text])
    assert "a requested site" not in d["record"], d["record"]


@pytest.mark.parametrize("site", ["gastric", "head and neck", "liver", "lung", "breast", "pancreatic", "ovarian",
                                  "prostate", "bladder", "esophageal"])
def test_n5_anatomical_sites_are_still_sites(site):
    assert site in ir._neoplasm_sites()


@pytest.mark.parametrize("word", ["pregnancy", "immunodeficiency", "lymphoproliferative", "aids related",
                                  "histiocytic", "peroxisome biogenesis", "von willebrand", "neuroendocrine",
                                  "myoepithelial", "sex cord stromal", "ambiguous lineage",
                                  "well differentiated neuroendocrine", "immunosuppression related"])
def test_n5_held_out_non_site_phrases_are_not_sites(word):
    # A site phrase must be named by a by-site neoplasm node and contain no lineage, state or function word.
    assert not (word in ir._neoplasm_sites() and ir._clean_site(word))


def test_n6_a_negated_mention_is_reported_and_the_other_target_still_listed():
    d = dg.target_diagnostic(["KLX9 (ABC1.2 negative)"], False, REQ, lambda p: "KLX9" if p == "KLX9" else None, ";")
    assert d["class"] == dg.SOURCE_NAMES_OTHER_TARGETS
    assert "KLX9" in d["record"] and "states it is not ABC1.2" in d["record"]


@pytest.mark.parametrize("value", ["ABC1.2-negative", "ABC1.2 non-expressing", "ABC1.2 (formerly)", "ABC1.2 knockout"])
def test_n6_n7_negations_after_the_symbol_are_not_the_required_target(value):
    d = dg.target_diagnostic([value], False, REQ, READ, ";")
    assert d["class"] == dg.SOURCE_STATES_NOT_REQUIRED_TARGET and d["summary"] == "states it is not the required target"
    assert f"'{value}' states it is not" in d["record"]


def test_n7_an_isoform_after_a_comma_is_read():
    d = dg.target_diagnostic(["ABC1, isoform 1"], False, REQ, READ, ";")
    assert d["class"] == dg.SOURCE_NAMES_OTHER_TARGETS and "isoform 1 of ABC1, not isoform 2" in d["record"]


def test_n7_an_annotation_suffix_is_at_most_may_name():
    assert dg.target_diagnostic(["ABC1-AS1"], False, REQ, READ, ";")["class"] == dg.SOURCE_MAY_NAME_REQUIRED_TARGET


def test_n7_a_descriptive_suffix_still_names_the_target():
    assert dg.target_diagnostic(["ABC1.2-positive"], False, REQ, READ, ";")["class"] \
        == dg.SOURCE_NAMES_REQUIRED_TARGET


@pytest.mark.parametrize("value", ["Novel ADC target", "Proprietary antigen X", "Target 1", "Unnamed candidate"])
def test_n8_placeholder_variants_are_not_other_targets(value):
    assert dg.target_diagnostic([value], False, REQ, READ, ";")["class"] == dg.UNREADABLE


@pytest.mark.parametrize(("value", "quoted"), [("ABC1.2 and/or CD99", "'ABC1.2'"), ("CD99/7", "'CD99/7'"),
                                               ("N/A", "'N/A'")])
def test_n9_values_are_quoted_as_written(value, quoted):
    d = dg.target_diagnostic([value], False, REQ, READ, ";")
    assert quoted in d["record"] and "'or " not in d["record"] and "' and'" not in d["record"]


def test_n10_metastases_of_names_the_primary():
    d = dg.indication_diagnostic(["Peritoneal metastases of gastric cancer"], GAS)
    assert d["class"] == ir.NAMES_REQUESTED_SITE


def test_n11_labels_are_not_repeated_and_restatements_are_not_index_keys():
    for request_text in ("glioblastoma", "burkitt lymphoma", "wilms tumor", "neuroblastoma", "medulloblastoma"):
        found = ir.restatement(request_text)
        if found:
            assert not any(len(t) == 1 for t in found[0].split()) and not found[0].endswith("s")
    d = dg.indication_diagnostic(["Lung Cancer"], ["lung cancer", "lung non-small cell carcinoma"])
    assert "This diagnostic classes no record name" in d["action"]


def test_n11_a_disease_state_step_is_written_in_words():
    reading = ir.classify_name("Relapsed AML", ir.read_request(["acute myeloid leukemia"]).codes)
    assert reading.steps == ("'relapsed' set aside as a disease-state word",)


def test_n12_an_empty_request_compares_nothing():
    d = dg.indication_diagnostic(["Gastric cancer"], [])
    assert d["class"] == dg.OTHER and "requests no indication" in d["record"] and d["field"] is None


def test_n13_no_record_phrase_is_hidden_behind_a_count():
    from bve.dealscreen.memo import _one_gate_lines

    screens = [_screen(i, ["gate.0"], f"record class {i % 9}") for i in range(30)]
    screens.append(_screen(99, ["gate.0"], "a disease neither requested nor a subtype of one"))
    line = _one_gate_lines(screens)[1]
    assert "a disease neither requested nor a subtype of one: Program 99" in line and not line.endswith(" more.")


# -- revision 4: the third adversarial review's findings (REVIEW3.md D1-D9), on held-out inputs -----------------
@pytest.mark.parametrize(("request_text", "name"), [
    (GAS, "Gallbladder adenocarcinoma, gastric foveolar type"), (["cutaneous melanoma"], "Mycosis fungoides"),
    (["cutaneous melanoma"], "Cutaneous T-cell lymphoma"), (["cutaneous melanoma"], "Non-melanoma skin cancer"),
    (["cholangiocarcinoma"], "Extrahepatic bile duct lymphoma"),
    (["cholangiocarcinoma"], "Extrahepatic bile duct Kaposi sarcoma"),
    (["renal cell carcinoma"], "Collecting duct carcinoma"), (["renal cell carcinoma"], "Stage IV renal pelvis cancer"),
    (["hepatocellular carcinoma"], "Mucoepidermoid intrahepatic cholangiocarcinoma"),
    (GAS, "Gastric squamous cell carcinoma"), (GAS, "Gastric neuroendocrine carcinoma"),
    (GAS, "Stage IV pancreatic cancer")])
def test_d1_only_a_stage_concept_naming_the_requested_site_is_under_the_requests_parent(request_text, name):
    assert dg.indication_diagnostic([name], list(request_text))["class"] != ir.UNDER_REQUESTED_PARENT


@pytest.mark.parametrize(("request_text", "name"), [
    (GAS, "Stage IV gastric cancer"), (["colorectal adenocarcinoma"], "Stage IV colorectal cancer"),
    (["pancreatic ductal adenocarcinoma"], "Stage IV pancreatic cancer")])
def test_d1_stage_concepts_naming_the_site_keep_the_class(request_text, name):
    d = dg.indication_diagnostic([name], list(request_text))
    assert d["class"] == ir.UNDER_REQUESTED_PARENT and "names " in d["record"]


def test_d1_a_liver_request_gains_no_bile_duct_site():
    phrases = set().union(*(ir.site_phrases(c) for c in ir.read_request(["hepatocellular carcinoma"]).codes))
    assert not any("bile duct" in p for p in phrases)


@pytest.mark.parametrize("value", ["ABC1.2-low", "ABC1.2 low-expressing", "ABC1.2 null-Fc", "ABC1.2 previously validated",
                                   "ABC1.2 loss-of-function", "ABC1.2 KO-resistant", "ABC1.2 deficient tumors",
                                   "low ABC1.2", "ABC1.2 (low expression)"])
def test_d2_expression_and_engineering_words_name_the_target(value):
    assert dg.target_diagnostic([value], False, REQ, READ, ";")["class"] == dg.SOURCE_NAMES_REQUIRED_TARGET


@pytest.mark.parametrize("name", ["Stage IV Solid Tumours", "STAGE IV SOLID TUMORS", "Stage III/IV solid tumors",
                                  "Solid Tumors (ALL COMERS)", "Advanced CANCER"])
def test_d3_roman_numerals_and_words_in_capitals_keep_a_basket(name):
    assert dg.indication_diagnostic([name], GAS)["class"] == ir.BASKET


@pytest.mark.parametrize("value", ["lacking ABC1.2 expression", "ABC1.2-independent"])
def test_d4_other_negation_wordings(value):
    assert dg.target_diagnostic([value], False, REQ, READ, ";")["class"] == dg.SOURCE_STATES_NOT_REQUIRED_TARGET


@pytest.mark.parametrize(("british", "american"), [("tracheooesophageal", "tracheoesophageal"),
                                                   ("hypoglycaemia", "hypoglycemia")])
def test_d5_british_spelling_after_o(british, american):
    assert ir.us_spelling(british) == american


@pytest.mark.parametrize("name", ["Gastro-oesophageal junction cancer",
                                  "Gastric cancer with gastric outlet obstruction"])
def test_d5_d6_the_site_is_named(name):
    assert dg.indication_diagnostic([name], GAS)["class"] == ir.NAMES_REQUESTED_SITE


def test_d7_transplant_states_are_not_sites():
    d = dg.indication_diagnostic(["Post-transplant lymphoproliferative disease, EBV+"],
                                 ["post-transplant lymphoproliferative disorder"])
    assert "a requested site" not in d["record"]


@pytest.mark.parametrize("request_text", ["lymphoma", "neuroblastoma", "burkitt lymphoma", "medulloblastoma"])
def test_d8_a_restatement_is_an_acronym_or_nothing(request_text):
    found = ir.restatement(request_text)
    assert found is None or (found[0].isupper() and " " not in found[0])


@pytest.mark.parametrize(("value", "partner"), [("ABC1.2/4-1BB", "4-1BB"), ("ABC1.2 x 4-1BB", "4-1BB"),
                                                ("ABC1.2 + CD99", "CD99"), ("ABC1.2 and CD99", "CD99"),
                                                ("ABC1.2, CD99", "CD99"), ("4-1BB/ABC1.2", "4-1BB")])
def test_d9_the_partner_target_is_listed(value, partner):
    d = dg.target_diagnostic([value], False, REQ, READ, ";")
    assert d["class"] == dg.SOURCE_NAMES_REQUIRED_TARGET and f"'{partner}'" in d["record"]


# -- U1 revision 5: REVIEW4 D1, D2, D4, D8, D9 -------------------------------------------------------------------------
ALL_ADULT = ["adult acute lymphoblastic leukemia"]


@pytest.mark.parametrize("name", ["RELAPSED ALL", "PEDIATRIC ALL", "ALL, RELAPSED", "ADULT ALL", "ADVANCED ALL",
                                  "RELAPSED/REFRACTORY ALL"])
def test_r5_d1_an_acronym_in_capitalised_text_is_not_a_basket(name):
    assert dg.indication_diagnostic([name], ALL_ADULT)["class"] != ir.BASKET


@pytest.mark.parametrize("name", ["ALL COMERS", "SOLID TUMORS (ALL COMERS)", "ALL SOLID TUMORS",
                                  "STAGE IV SOLID TUMORS"])
def test_r5_d1_all_before_a_basket_word_is_still_a_basket(name):
    assert ir.is_basket(name)


@pytest.mark.parametrize(("request_text", "name"), [
    (GASTRIC, "Stage IV gastric neuroendocrine tumor"),
    (GASTRIC, "Stage III Gastric Neuroendocrine Tumor AJCC v8"),
    (["pancreatic ductal adenocarcinoma"], "Stage IV pancreatic neuroendocrine tumor"),
    (["colorectal adenocarcinoma"], "Stage IV colorectal neuroendocrine tumor"),
    (["lung adenocarcinoma"], "Stage IV small cell lung cancer"),
    (["endometrial endometrioid adenocarcinoma"], "Stage IV uterine corpus leiomyosarcoma")])
def test_r5_d2_a_stage_concept_of_another_lineage_is_not_under_the_requests_parent(request_text, name):
    assert dg.indication_diagnostic([name], request_text)["class"] != ir.UNDER_REQUESTED_PARENT


@pytest.mark.parametrize("name", ["Advanced solid tumors (AST)", "Advanced Cancer (AC)",
                                  "Malignant solid tumor (MST)", "Advanced malignancies (AM)"])
def test_r5_d4_a_basket_with_its_own_acronym_is_a_basket(name):
    assert dg.indication_diagnostic([name], GASTRIC)["class"] == ir.BASKET


@pytest.mark.parametrize("name", ["Gastric cancer type: diffuse", "Gastric carcinoma type 2"])
def test_r5_d8_a_tumour_head_before_type_is_not_a_role(name):
    assert dg.indication_diagnostic([name], GASTRIC)["class"] != ir.UNREADABLE


def test_r5_d9_a_restatement_is_never_a_basket_word():
    restated = ir.restatement("Neoplasm")
    assert restated is None or restated[0].casefold() not in ir._BASKET_WORDS


@pytest.mark.parametrize("value", ["ABC1.2 negative or positive", "ABC1.2 neg/pos", "ABC1.2-negative and -positive"])
def test_r5_d3_a_target_stated_both_negative_and_positive_is_not_stated_absent(value):
    assert dg.target_diagnostic([value], False, REQ, READ, ";")["class"] != dg.SOURCE_STATES_NOT_REQUIRED_TARGET


def test_r5_d3_a_negated_target_beside_another_positive_target_stays_negated():
    d = dg.target_diagnostic(["ABC1.2 negative; XYZ positive"], False, REQ, READ, ";")
    assert "'ABC1.2 negative' states it is not ABC1.2" in d["record"]


# -- U1 revision 6: REVIEW5 N1, N2, N3 ---------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["Relapsed ALL in adults", "Relapsed or refractory ALL in adults", "ALL in children",
                                  "ALL RELAPSED", "ALL in adults", "ALL relapsed", "ALL patients", "ALL Adults",
                                  "ALL REFRACTORY", "ALL - RELAPSED", "ALL ADVANCED", "ALL PATIENTS"])
def test_r6_n1_all_before_a_qualifier_or_population_word_is_not_a_basket(name):
    assert not ir.is_basket(name)
    assert dg.indication_diagnostic([name], ALL_ADULT)["class"] != ir.BASKET


@pytest.mark.parametrize("value, other", [
    ("not ABC1.2; XYZ positive or negative", "XYZ"),
    ("ABC1.2 negative, positive for XYZ", "XYZ"),
    ("ABC1.2 negative; XYZ negative or positive", "XYZ"),
    ("ABC1.2-negative, XYZ neg/pos", "XYZ"),
    ("ABC1.2 negative (XYZ positive or negative)", "XYZ")])
def test_r6_n2_another_targets_both_states_do_not_cancel_the_required_targets_negation(value, other):
    d = dg.target_diagnostic([value], False, REQ, READ, ";")
    assert d["class"] == dg.SOURCE_NAMES_OTHER_TARGETS, d
    assert "states it is not ABC1" in d["record"] and other in d["record"]


@pytest.mark.parametrize("value", ["ABC1.2 negative or positive", "ABC1.2 neg/pos", "ABC1.2-negative and -positive",
                                   "ABC1.2 negative and positive cohorts", "ABC1.2 neg & pos"])
def test_r6_n2_the_required_target_stated_both_ways_is_still_not_absent(value):
    assert dg.target_diagnostic([value], False, REQ, READ, ";")["class"] != dg.SOURCE_STATES_NOT_REQUIRED_TARGET


def test_r6_n3_an_en_dash_before_negative_is_a_negation():
    d = dg.target_diagnostic(["ABC1.2–negative"], False, REQ, READ, ";")
    assert d["class"] == dg.SOURCE_STATES_NOT_REQUIRED_TARGET


def test_r6_the_may_name_sentence_lists_the_other_parts():
    d = dg.target_diagnostic(["ABC1L2; XYZ"], False, REQ, READ, ";")
    assert d["class"] == dg.SOURCE_MAY_NAME_REQUIRED_TARGET and "also on record: 'XYZ'" in d["record"]


# -- U1 revision 7: REVIEW6 E1-E7 --------------------------------------------------------------------------------------
@pytest.mark.parametrize("name, requested", [
    ("Ulcerative colitis or Crohn's disease", UC), ("Myasthenia gravis or CIDP", ["myasthenia gravis"]),
    ("Adult ALL or AML", ["adult acute lymphoblastic leukemia"]),
    ("Adult acute lymphoblastic leukemia or AML", ["adult acute lymphoblastic leukemia"]),
    ("HCC or cholangiocarcinoma", HCC), ("Gastric adenocarcinoma or NSCLC", GASTRIC),
    ("Gastric Adenocarcinoma or Pancreatic Ductal Adenocarcinoma", GASTRIC),
    ("Pancreatic, gastric or esophageal adenocarcinoma", GASTRIC)])
def test_r7_e1_each_name_of_an_or_list_is_read_so_a_requested_one_is_never_a_different_disease(name, requested):
    d = dg.indication_diagnostic([name], requested)
    assert d["class"] == ir.AMBIGUOUS_NAME, d
    assert "(requested or a subtype)" in d["record"] and "its 'or' list split" in d["record"]


def test_r7_e1_an_or_list_read_only_in_part_says_which_part_it_does_not_read():
    d = dg.indication_diagnostic(["UC or Crohn's disease"], UC)
    assert d["class"] == ir.UNREADABLE
    assert "it reads Crohn Disease (not requested) and does not read 'UC'" in d["record"]
    assert "neither a requested indication" not in d["record"]


@pytest.mark.parametrize("name", ["ALL or AML", "AML or ALL"])
def test_r7_e1_all_or_aml_names_both_readings(name):
    d = dg.indication_diagnostic([name], ["adult acute lymphoblastic leukemia"])
    assert d["class"] == ir.AMBIGUOUS_NAME and "Acute Myeloid Leukemia" in d["record"], d


@pytest.mark.parametrize("name", ["Locally advanced or metastatic gastric adenocarcinoma"])
def test_r7_e1_qualifier_lists_and_unread_lists_keep_their_reading(name):
    assert dg.indication_diagnostic([name], GASTRIC)["class"] in (ir.READS_AS_REQUESTED, ir.NAMES_REQUESTED_SITE)


def test_r8_f1_a_list_of_two_read_diseases_names_both():
    # revision 8 reads the record's own list on every path: the pancreatic half is named, not only the site
    d = dg.indication_diagnostic(["Gastric adenocarcinoma or pancreatic cancer"], GASTRIC)
    assert d["class"] == ir.AMBIGUOUS_NAME, d
    assert "(requested or a subtype)" in d["record"] and "(not requested)" in d["record"]


@pytest.mark.parametrize("value", ["ABC1.2 negative, positive XYZ expression", "ABC1.2 negative and positive XYZ",
                                   "ABC1.2 negative, positive (XYZ)", "ABC1.2 negative or positive for XYZ",
                                   "ABC1.2 negative / positive for XYZ", "ABC1.2 negative, pos. XYZ",
                                   "ABC1.2 negative XYZ9 neg/pos", "ABC1.2 negative XYZ9 positive or negative"])
def test_r7_e2_a_positive_before_another_target_is_that_targets_state(value):
    d = dg.target_diagnostic([value], False, REQ, READ, ";")
    assert d["class"] in (dg.SOURCE_NAMES_OTHER_TARGETS, dg.SOURCE_STATES_NOT_REQUIRED_TARGET), d
    assert "states it is not ABC1" in d["record"]


@pytest.mark.parametrize("value", ["ABC1.2 negative and/or positive", "ABC1.2 negative &/or positive",
                                   "ABC1.2 neg + pos", "ABC1.2 negative plus positive", "ABC1.2 negative|positive",
                                   "ABC1.2 negative – positive", "ABC1.2 neg–pos", "ABC1.2  neg/pos",
                                   "ABC1.2 (neg)/pos"])
def test_r7_e3_both_states_joined_any_way_are_not_a_negation(value):
    assert dg.target_diagnostic([value], False, REQ, READ, ";")["class"] != dg.SOURCE_STATES_NOT_REQUIRED_TARGET


@pytest.mark.parametrize("value", ["non–ABC1.2", "non—ABC1.2", "non‐ABC1.2", "not–ABC1.2", "ABC1.2‑negative",
                                   "ABC1.2‐negative", "ABC1.2−negative"])
def test_r7_e4_any_unicode_dash_reads_as_a_hyphen(value):
    assert dg.target_diagnostic([value], False, REQ, READ, ";")["class"] == dg.SOURCE_STATES_NOT_REQUIRED_TARGET


@pytest.mark.parametrize("name", ["Adult ALL disease", "ALL disease", "ALL Disease", "Relapsed ALL disease",
                                  "ALL disorder", "ALL malignancy", "ALL carcinoma", "ALL condition", "ALL-disease"])
def test_r7_e5_all_before_a_singular_head_is_the_acronym(name):
    assert not ir.is_basket(name)


@pytest.mark.parametrize("name", ["ALL cancers", "ALL solid tumors", "ALL COMERS", "ALL tumors"])
def test_r7_e5_all_before_a_plural_head_is_still_a_basket(name):
    assert ir.is_basket(name)


@pytest.mark.parametrize("value", ["ABC1.2 not expressed", "ABC1.2 expression absent", "absent ABC1.2"])
def test_r7_e6_absence_words_are_a_negation(value):
    assert dg.target_diagnostic([value], False, REQ, READ, ";")["class"] == dg.SOURCE_STATES_NOT_REQUIRED_TARGET


def test_r7_e6_negative_or_low_and_low_or_negative_read_alike():
    one = dg.target_diagnostic(["ABC1.2 negative or low"], False, REQ, READ, ";")["class"]
    two = dg.target_diagnostic(["ABC1.2 low or negative"], False, REQ, READ, ";")["class"]
    assert one == two != dg.SOURCE_STATES_NOT_REQUIRED_TARGET


@pytest.mark.parametrize("name", ["Gastric metastatic adenocarcinoma", "Gastric Metastatic Cancer",
                                  "Gastric refractory cancer", "Gastric treatment-refractory cancer",
                                  "Gastric resistant cancer"])
def test_r7_e7_a_state_word_before_a_tumour_head_keeps_the_site(name):
    assert dg.indication_diagnostic([name], GASTRIC)["class"] == ir.NAMES_REQUESTED_SITE


@pytest.mark.parametrize("name", ["Gastric therapy-resistant", "gastric outlet obstruction"])
def test_r7_e7_a_role_with_no_tumour_head_stays_a_role(name):
    assert dg.indication_diagnostic([name], GASTRIC)["class"] != ir.NAMES_REQUESTED_SITE


# -- revision 8: REVIEW7 F1-F5 ---------------------------------------------------------------------------------------
@pytest.mark.parametrize(("name", "request_"), [
    ("Locally advanced or metastatic gastric adenocarcinoma or NSCLC", GASTRIC),
    ("Gastric adenocarcinoma or oesophageal adenocarcinoma", GASTRIC),
    ("Gastric adenocarcinoma, metastatic, or NSCLC", GASTRIC),
    ("Gastric adenocarcinoma, stage IV, or NSCLC", GASTRIC),
    ("Relapsed or refractory gastric adenocarcinoma or NSCLC", GASTRIC),
    ("Moderate or severe ulcerative colitis or Crohn's disease", UC),
    ("Relapsed or refractory ulcerative colitis or Crohn's disease", UC),
    ("Ulcerative colitis, pouchitis or Crohn's disease", UC),
    ("IBD (ulcerative colitis or Crohn's disease)", UC),
    ("Relapsed or refractory myasthenia gravis or CIDP", ["myasthenia gravis"]),
])
def test_r8_f1_f3_a_list_naming_the_request_is_ambiguous_on_every_path(name, request_):
    d = dg.indication_diagnostic([name], request_)
    assert d["class"] == ir.AMBIGUOUS_NAME, d
    assert "(requested or a subtype)" in d["record"]
    assert "neither a requested indication" not in d["record"]


@pytest.mark.parametrize("name", ["Stage III or stage IV gastric cancer", "Stage IIIB or stage IV gastric cancer",
                                  "Stage IV or recurrent gastric cancer", "Stage III or IV gastric adenocarcinoma"])
def test_r8_f2_a_stage_piece_is_never_looked_up_alone(name):
    d = dg.indication_diagnostic([name], GASTRIC)
    assert d["class"] != ir.DIFFERENT_DISEASE, d
    for organ in ("Pancreatic", "Testicular", "Lung", "Renal", "Masaoka"):
        assert organ not in d["record"], d["record"]


def test_r8_f2_the_edition_note_is_given_once():
    d = dg.indication_diagnostic(["Stage III or stage IV gastric cancer"], GASTRIC)
    assert d["record"].count("the record states no edition") == 1


def test_r8_f3_a_partly_read_list_says_what_it_reads():
    d = dg.indication_diagnostic(["Gastric adenocarcinoma, China, or NSCLC"], GASTRIC)
    assert d["class"] == ir.AMBIGUOUS_NAME
    assert "is not a name the NCIt authority can read as a whole" in d["record"]
    assert "does not read 'China'" in d["record"]
    assert "matches several NCIt concepts" not in d["record"]


@pytest.mark.parametrize("piece", ["HER2+", "2L", "metastatic"])
def test_r8_f3_a_marker_or_modifier_piece_is_set_aside(piece):
    d = dg.indication_diagnostic([f"Gastric adenocarcinoma, {piece}, or NSCLC"], GASTRIC)
    assert d["class"] == ir.AMBIGUOUS_NAME
    assert f"'{piece}' set aside as a modifier, not a name" in d["record"]


def test_r8_f1_a_capital_acronym_is_a_name_not_the_word_all():
    d = dg.indication_diagnostic(["Relapsed or refractory ALL or AML"], ["acute myeloid leukemia"])
    assert d["class"] == ir.AMBIGUOUS_NAME, d


@pytest.mark.parametrize("value", ["XYZ9 absent ABC1.2 positive", "XYZ9-absent ABC1.2-high", "XYZ9 absent ABC1.2"])
def test_r8_f4_absent_after_another_target_does_not_negate_the_required_one(value):
    d = dg.target_diagnostic([value], False, REQ, READ, ";")
    assert d["class"] == dg.SOURCE_NAMES_REQUIRED_TARGET, d


def test_r8_f4_absent_at_the_start_still_negates():
    d = dg.target_diagnostic(["absent ABC1.2"], False, REQ, READ, ";")
    assert d["class"] == dg.SOURCE_STATES_NOT_REQUIRED_TARGET, d


@pytest.mark.parametrize("value", ["ABC1.2 negative or positive for XYZ9", "ABC1.2 negative / positive for XYZ9"])
def test_r8_f5_a_negated_part_with_another_symbol_never_says_no_other_target(value):
    d = dg.target_diagnostic([value], False, REQ, READ, ";")
    assert d["class"] == dg.SOURCE_STATES_NOT_REQUIRED_TARGET, d
    assert "names no other target" not in d["record"]
    assert "also names another target" in d["record"]


@pytest.mark.parametrize("name", ["Unresectable or Metastatic Gastric or Gastroesophageal Junction Adenocarcinoma",
                                  "Gastric adenocarcinoma or gastroesophageal junction adenocarcinoma"])
def test_r8_f1_a_list_whose_every_name_is_requested_reads_as_requested(name):
    d = dg.indication_diagnostic([name], GASTRIC)
    assert d["class"] == ir.READS_AS_REQUESTED, d


# -- revision 9 (REVIEW8) -------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("name", "requested", "wanted"), [
    ("Chronic or acute myeloid leukemia", ["chronic myeloid leukemia"], "Chronic Myeloid Leukemia"),          # D1
    ("Chronic or acute GVHD", ["chronic graft versus host disease"], "Chronic Graft Versus Host Disease"),
    ("Severe or non-severe aplastic anemia", ["severe aplastic anemia"], "Severe Aplastic Anemia"),
    ("Chronic or acute lymphocytic leukemia", ["chronic lymphocytic leukemia"], "Chronic Lymphocytic Leukemia"),
    ("Chronic or acute pancreatitis", ["chronic pancreatitis"], "Chronic Pancreatitis"),
    ("Chronic or acute hepatitis B", ["chronic hepatitis b"], "Chronic Hepatitis B"),
])
def test_r9_d1_a_leading_defining_word_is_its_own_disease(name, requested, wanted):
    d = dg.indication_diagnostic([name], requested)
    assert d["class"] == ir.AMBIGUOUS_NAME, d
    assert f"{wanted}" in d["record"] and "(requested or a subtype)" in d["record"]
    assert d["class"] != ir.DIFFERENT_DISEASE


@pytest.mark.parametrize("name", ["Chronic or acute GVHD", "Acute or chronic GVHD",
                                  "Acute or chronic graft versus host disease"])
def test_r9_d1_both_subtypes_of_the_request_read_as_requested(name):
    d = dg.indication_diagnostic([name], ["graft versus host disease"])
    assert d["class"] == ir.READS_AS_REQUESTED, d
    assert "Acute Graft Versus Host Disease" in d["record"] and "Chronic Graft Versus Host Disease" in d["record"]


@pytest.mark.parametrize("basket", ["other solid tumors", "all comers", "other cancers", "any solid tumour"])
def test_r9_d2_a_basket_piece_is_a_basket_not_a_modifier(basket):
    d = dg.indication_diagnostic([f"Gastric adenocarcinoma, gastroesophageal junction adenocarcinoma, or {basket}"],
                                 GASTRIC)
    assert d["class"] == ir.AMBIGUOUS_NAME, d
    assert f"reads '{basket}' as a basket of diseases" in d["record"]
    assert "set aside" not in d["record"]


def test_r9_d2_a_symptom_is_a_name():
    d = dg.indication_diagnostic(["Gastric adenocarcinoma or pain"], GASTRIC)
    assert d["class"] == ir.AMBIGUOUS_NAME and "set aside" not in d["record"]


@pytest.mark.parametrize(("name", "requested", "wanted"), [
    ("Myeloid leukemia, chronic, or ALL, or AML", ["chronic myeloid leukemia"], "Chronic Myeloid Leukemia"),   # D3
    ("Diabetes mellitus, type 2, or obesity", ["type 2 diabetes mellitus"], "Type 2 Diabetes Mellitus"),
    ("Hepatitis B, chronic, or hepatitis D", ["chronic hepatitis b"], "Chronic Hepatitis B"),
    ("Myeloid leukemia, acute, or MDS, or CMML", ["acute myeloid leukemia"], "Acute Myeloid Leukemia"),
])
def test_r9_d3_an_inverted_modifier_reads_with_its_name(name, requested, wanted):
    d = dg.indication_diagnostic([name], requested)
    assert d["class"] == ir.AMBIGUOUS_NAME, d
    assert f"{wanted}" in d["record"] and "broader than requested" not in d["record"]


def test_r9_d3_an_unread_defining_modifier_is_named_not_set_aside():
    d = dg.indication_diagnostic(["Gastric adenocarcinoma, adult, or NSCLC"], GASTRIC)
    assert "does not read 'adult'" in d["record"] and "set aside" not in d["record"]


@pytest.mark.parametrize(("name", "requested", "cls"), [
    ("STAGE III OR STAGE IV GASTRIC CANCER", GASTRIC, ir.UNDER_REQUESTED_PARENT),                              # D4
    ("MODERATE OR SEVERE ULCERATIVE COLITIS OR CROHN'S DISEASE", ["ulcerative colitis"], ir.AMBIGUOUS_NAME),
])
def test_r9_d4_modifier_words_in_capitals_are_words(name, requested, cls):
    d = dg.indication_diagnostic([name], requested)
    assert d["class"] == cls, d
    assert "COVID" not in d["record"] and "Head and Neck" not in d["record"] and "Masaoka" not in d["record"]


@pytest.mark.parametrize("lead", ["Patients with", "Adult", "Pediatric"])
def test_r9_d5_a_population_before_the_request_is_read(lead):
    d = dg.indication_diagnostic([f"{lead} ulcerative colitis or Crohn's disease"], ["ulcerative colitis"])
    assert d["class"] == ir.AMBIGUOUS_NAME, d
    assert "Ulcerative Colitis (requested or a subtype)" in d["record"]


@pytest.mark.parametrize(("name", "requested", "cls"), [
    ("Advanced high grade B-cell lymphoma with MYC and BCL2 or BCL6 rearrangements",                          # D6
     ["high grade b-cell lymphoma with myc and bcl2 or bcl6 rearrangements"], ir.READS_AS_REQUESTED),
    ("Advanced ampullary pancreaticobiliary or gastric type adenocarcinoma",
     ["ampulla of vater pancreaticobiliary or gastric type adenocarcinoma"], ir.READS_AS_REQUESTED),
    ("Advanced ampullary pancreaticobiliary or gastric type adenocarcinoma", GASTRIC, ir.DIFFERENT_DISEASE),
])
def test_r9_d6_or_inside_an_ncit_name_is_read_whole(name, requested, cls):
    d = dg.indication_diagnostic([name], requested)
    assert d["class"] == cls, d
    assert "split" not in d["record"]


def test_r9_d8_the_partly_read_sentence_shows_its_steps():
    d = dg.indication_diagnostic(["Gastric adenocarcinoma, metastatic, China, or NSCLC"], GASTRIC)
    assert "does not read 'China'" in d["record"] and "'metastatic' set aside as a modifier" in d["record"]


def test_r9_d9_a_line_list_is_one_name_and_either_is_dropped():
    d = dg.indication_diagnostic(["Gastric adenocarcinoma (first or second line)"], GASTRIC)
    assert d["class"] == ir.READS_AS_REQUESTED, d
    d = dg.indication_diagnostic(["Either gastric adenocarcinoma or NSCLC"], GASTRIC)
    assert "Either" not in d["record"].split("'", 2)[2]


def test_r9_controls_unchanged():
    assert dg.indication_diagnostic(["Locally advanced or metastatic gastric adenocarcinoma"],
                                    GASTRIC)["class"] == ir.READS_AS_REQUESTED
    assert dg.indication_diagnostic(["Stage III or stage IV gastric cancer"],
                                    GASTRIC)["class"] == ir.UNDER_REQUESTED_PARENT
    assert dg.indication_diagnostic(["Gastric adenocarcinoma, metastatic, or NSCLC"],
                                    GASTRIC)["class"] == ir.AMBIGUOUS_NAME


@pytest.mark.parametrize("value", ["ABC1.2 NEGATIVE", "NOT ABC1.2", "ABC1.2-negative by IHC", "ABC1.2 negative in GC"])
def test_r9_d7_a_state_word_assay_or_disease_acronym_is_not_another_target(value):
    d = dg.target_diagnostic([value], False, REQ, READ, ";")
    assert d["class"] == dg.SOURCE_STATES_NOT_REQUIRED_TARGET, d
    assert "also names another target" not in d["record"]
    assert "names no other target" in d["record"]


# -- revision 10 (REVIEW9) ------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("name", "requested", "wanted"), [
    ("Relapsing or progressive multiple sclerosis", ["relapsing multiple sclerosis"],
     "Relapsing Multiple Sclerosis (requested"),                                                          # N1
    ("Type 1 or 2 diabetes mellitus", ["type 2 diabetes mellitus"], "Type 2 Diabetes Mellitus (requested"),  # N3
    ("Grade 1 or 2 follicular lymphoma", ["grade 2 follicular lymphoma"], "Grade 2 Follicular Lymphoma (requested"),
    ("GVHD, acute or chronic, or AML", ["chronic graft versus host disease"],
     "Chronic Graft Versus Host Disease (requested"),                                                     # N5
    ("Diabetes mellitus, type 1 or type 2", ["type 2 diabetes mellitus"], "Type 2 Diabetes Mellitus (requested"),
])
def test_r10_the_record_names_the_requested_concept(name, requested, wanted):
    d = dg.indication_diagnostic([name], requested)
    assert d["class"] == ir.AMBIGUOUS_NAME, d
    assert wanted in d["record"], d["record"]


@pytest.mark.parametrize(("name", "requested", "never"), [
    ("Diffuse or follicular lymphoma", GASTRIC, "Gastric"),                                               # N2
    ("Intestinal or extraintestinal Behçet's disease", GASTRIC, "Gastric"),
    ("Mixed or pure germ cell tumor", GASTRIC, "Gastric"),
    ("Diffuse, follicular, or mantle cell lymphoma", GASTRIC, "Gastric"),
    ("Symptomatic or asymptomatic multiple myeloma", ["covid-19"], "COVID"),
])
def test_r10_n2_an_adjective_is_never_read_alone_as_another_concept(name, requested, never):
    d = dg.indication_diagnostic([name], requested)
    assert never not in d["record"].split("'", 2)[2], d["record"]


def test_r10_n2_a_one_word_disease_is_still_read():
    d = dg.indication_diagnostic(["Myeloma or lymphoma"], ["multiple myeloma"])
    assert "Multiple Myeloma (requested" in d["record"], d["record"]


@pytest.mark.parametrize(("name", "requested", "wanted"), [
    ("Children with ALL or AML", ["adult acute lymphoblastic leukemia"], "Childhood Acute Lymphoblastic Leukemia"),
    ("Adults with ALL or AML", ["childhood acute lymphoblastic leukemia"], "Adult Acute Lymphoblastic Leukemia"),
])
def test_r10_n4_a_stated_population_keeps_its_concept(name, requested, wanted):
    d = dg.indication_diagnostic([name], requested)
    assert wanted in d["record"] and "broader than requested" not in d["record"], d["record"]


def test_r10_n5_each_inverted_modifier_reads_with_the_same_name():
    d = dg.indication_diagnostic(["Leukemia, acute or chronic, or lymphoma"], ["acute lymphoblastic leukemia"])
    assert "Chronic Leukemia" in d["record"] and "does not read 'chronic'" not in d["record"], d["record"]


@pytest.mark.parametrize("name", ["ADVANCED NSCLC", "RELAPSED AML"])
def test_r10_n6_a_capitals_cell_the_gate_reads_is_the_gate_reading(name):
    d = dg.indication_diagnostic([name], GASTRIC)
    assert "gate does not apply" not in d["record"] and "capitals" not in d["record"], d["record"]


def test_r10_n7_a_capitals_cell_is_quoted_as_written():
    d = dg.indication_diagnostic(["HCC (CHILD-PUGH A OR B)"], GASTRIC)
    assert "'CHILD-PUGH A'" in d["record"] and "child-PUGH" not in d["record"], d["record"]


@pytest.mark.parametrize("value", ["ABC1.2 negative in G1/G2 tumours", "ABC1.2 NEGATIVE IN 2L"])
def test_r10_n8_a_grade_or_line_token_is_not_another_target(value):
    d = dg.target_diagnostic([value], False, REQ, READ, ";")
    assert "names no other target" in d["record"], d["record"]


def test_r10_n9_a_set_apart_modifier_is_not_called_a_name():
    d = dg.indication_diagnostic(["Crohn's disease or ulcerative colitis, severe"], ["ulcerative colitis"])
    assert "does not read 'severe' with the name before it" in d["record"], d["record"]


def test_r10_controls_unchanged():
    assert dg.indication_diagnostic(["Unresectable or Metastatic Gastric or Gastroesophageal Junction Adenocarcinoma"],
                                    GASTRIC)["class"] == ir.READS_AS_REQUESTED
    assert dg.indication_diagnostic(["Progressive or relapsing multiple sclerosis"],
                                    ["progressive multiple sclerosis"])["class"] == ir.AMBIGUOUS_NAME


# -- revision 11 (REVIEW10) ------------------------------------------------------------------------------------------


def _cases(name: str) -> list[str]:
    """The record name as written, in lower case and in capitals: letter case never decides what U1 reads (P1-P3)."""
    return list(dict.fromkeys([name, name.lower(), name.upper()]))


N2_ROWS = [
    ("Diffuse or follicular lymphoma", GASTRIC, "Gastric"),
    ("Intestinal or extraintestinal Behçet's disease", GASTRIC, "Gastric"),
    ("Mixed or pure germ cell tumor", GASTRIC, "Gastric"),
    ("Diffuse, follicular, or mantle cell lymphoma", GASTRIC, "Gastric"),
    ("Diffuse or follicular lymphoma or pain", GASTRIC, "Gastric"),
    ("Diffuse or follicular lymphoma", ["diffuse large b-cell lymphoma, not otherwise specified"], "Gastric"),
    ("Symptomatic or asymptomatic multiple myeloma", ["covid-19"], "COVID"),
]


@pytest.mark.parametrize(("name", "requested", "never"),
                         [(c, r, n) for name, r, n in N2_ROWS for c in _cases(name)])
def test_r11_p3_an_adjective_is_never_read_alone_in_any_case(name, requested, never):
    d = dg.indication_diagnostic([name], requested)
    assert never not in d["record"].split("'", 2)[2], d["record"]


ACRONYM_ROWS = [
    ("mCRPC or mHSPC", ["metastatic castration-resistant prostate carcinoma"],
     "Metastatic Castration-Resistant Prostate Carcinoma (requested"),
    ("mCRPC or nmCRPC", ["metastatic castration-resistant prostate carcinoma"],
     "Metastatic Castration-Resistant Prostate Carcinoma (requested"),
    ("HCC or iCCA", ["intrahepatic cholangiocarcinoma"], "Intrahepatic Cholangiocarcinoma (requested"),
    ("iCCA or eCCA", ["intrahepatic cholangiocarcinoma"], "Intrahepatic Cholangiocarcinoma (requested"),
    ("ccRCC or pRCC", ["clear cell renal cell carcinoma"], "Clear Cell Renal Cell Carcinoma (requested"),
    ("NSCLC or SCLC", ["lung non-small cell carcinoma"], "Lung Non-Small Cell Carcinoma (requested"),
    ("Hives or angioedema", ["urticaria"], "Urticaria (requested"),
    ("Myeloma or lymphoma", ["multiple myeloma"], "Multiple Myeloma (requested"),
]


@pytest.mark.parametrize(("name", "requested", "wanted"),
                         [(c, r, w) for name, r, w in ACRONYM_ROWS for c in _cases(name)])
def test_r11_p2_an_acronym_or_synonym_the_authority_reads_is_read_in_any_case(name, requested, wanted):
    d = dg.indication_diagnostic([name], requested)
    assert d["class"] == ir.AMBIGUOUS_NAME and wanted in d["record"], d["record"]


@pytest.mark.parametrize(("name", "unread"), [
    ("GASTRIC/GEJ ADENOCARCINOMA OR NSCLC", "GASTRIC/GEJ ADENOCARCINOMA"),
    ("GEJ OR NSCLC", "GEJ"),
    ("NSCLC OR PAIN", "PAIN"),
])
def test_r11_p1_a_capitals_list_never_drops_what_it_does_not_read(name, unread):
    d = dg.indication_diagnostic([name], GASTRIC)
    assert d["class"] != ir.DIFFERENT_DISEASE and f"does not read '{unread}'" in d["record"], d["record"]


@pytest.mark.parametrize(("name", "requested"), [
    ("CASTRATION-SENSITIVE OR CASTRATION-RESISTANT PROSTATE CANCER", ["castration-sensitive prostate carcinoma"]),
    ("CGVHD OR BRONCHIOLITIS OBLITERANS", ["chronic graft versus host disease"]),
    ("LIMITED OR EXTENSIVE STAGE SCLC", ["limited stage lung small cell carcinoma"]),
    ("ADOLESCENTS WITH ALL OR AML", ["childhood acute lymphoblastic leukemia"]),
])
def test_r11_p1_a_capitals_list_read_in_part_is_not_a_different_disease(name, requested):
    assert dg.indication_diagnostic([name], requested)["class"] != ir.DIFFERENT_DISEASE


@pytest.mark.parametrize("name", _cases("ADVANCED NSCLC") + _cases("RELAPSED AML"))
def test_r11_p1_a_whole_capitals_cell_still_takes_the_gate_reading(name):
    assert "capitals" not in dg.indication_diagnostic([name], GASTRIC)["record"]


@pytest.mark.parametrize(("name", "requested", "never"), [
    ("Metastatic or pancreatic neuroendocrine carcinoma", ["lung neuroendocrine carcinoma"], "shares subtypes"),
    ("Recurrent or pharyngeal squamous cell carcinoma", ["lung squamous cell carcinoma"], "shares subtypes"),
    ("Metastatic or pharyngeal squamous cell carcinoma", GASTRIC, "Metastatic Squamous Cell Carcinoma"),
])
def test_r11_p4_a_borrowed_ending_never_drops_a_site(name, requested, never):
    assert never not in dg.indication_diagnostic([name], requested)["record"]


def test_r11_p4_a_borrowed_ending_without_a_site_is_still_read():
    d = dg.indication_diagnostic(["Relapsing or progressive multiple sclerosis"], ["relapsing multiple sclerosis"])
    assert "Relapsing Multiple Sclerosis (requested" in d["record"], d["record"]


@pytest.mark.parametrize(("name", "requested", "wanted"), [
    (c, r, w) for name, r, w in [
        ("Diabetes mellitus, type 1 or 2", ["type 2 diabetes mellitus"], "Type 2 Diabetes Mellitus (requested"),
        ("Diabetes (type 1 or 2)", ["type 2 diabetes mellitus"], "Type 2 Diabetes Mellitus (requested"),
        ("Follicular lymphoma, grade 1 or 2", ["grade 2 follicular lymphoma"], "Grade 2 Follicular Lymphoma (requested"),
        ("Follicular lymphoma (grade 1 or 2)", ["grade 2 follicular lymphoma"],
         "Grade 2 Follicular Lymphoma (requested"),
    ] for c in _cases(name)])
def test_r11_p5_a_number_in_an_inverted_list_keeps_its_word(name, requested, wanted):
    assert wanted in dg.indication_diagnostic([name], requested)["record"]


def test_r11_p6_a_line_token_is_not_numbered():
    assert "Stage 2L" not in dg.indication_diagnostic(["Stage III or 2L gastric cancer"], GASTRIC)["record"]


def test_r11_p6_a_carried_prefix_is_quoted_as_written():
    d = dg.indication_diagnostic(["Grade 1 or 2 obesity or type 1 diabetes"], ["type 1 diabetes mellitus"])
    assert "'Grade 1 or 2 obesity'" in d["record"] and "Grade 1 or Grade 2" not in d["record"], d["record"]


def test_r11_p7_an_inverted_modifier_after_a_basket_has_no_name():
    d = dg.indication_diagnostic(["GVHD, acute, or other solid tumors, chronic"], ["chronic graft versus host disease"])
    assert "Chronic Graft Versus Host Disease (requested" not in d["record"], d["record"]
    assert "does not read 'chronic'" in d["record"], d["record"]


def test_r11_p8_a_nested_list_shows_its_own_steps():
    d = dg.indication_diagnostic(["Unresectable or Metastatic Gastric or Gastroesophageal Junction Adenocarcinoma"],
                                 GASTRIC)
    assert d["class"] == ir.READS_AS_REQUESTED
    assert "'Unresectable' read as 'Unresectable Gastric Adenocarcinoma'" in d["record"], d["record"]


# -- revision 12 (REVIEW11) ------------------------------------------------------------------------------------------
CDI = ["central diabetes insipidus"]
Q1_ROWS = [
    # an ordinary word's index synonym is never read alone; the record's own coordination is tried first (Q1)
    ("Central, nephrogenic or gestational diabetes insipidus", CDI, "Osteosarcoma"),
    ("Central or nephrogenic DI", CDI, "Osteosarcoma"),
    ("Diabetes insipidus, central or nephrogenic", CDI, "Osteosarcoma"),
    ("Central or nephrogenic diabetes insipidus, or polyuria", CDI, "Osteosarcoma"),
    ("Cold or warm autoimmune hemolytic anemia", ["cold agglutinin disease"], "Pulmonary"),
    ("Cold or warm autoimmune hemolytic anemia", ["chronic obstructive pulmonary disease"], "Pulmonary"),
    ("Sensitive or resistant gastric cancer", GASTRIC, "Hypersensitivity"),
    ("Sensitive or refractory small cell lung cancer", ["refractory lung small cell carcinoma"], "Hypersensitivity"),
    ("Sensitive or resistant nephrotic syndrome", ["nephrotic syndrome"], "Hypersensitivity"),
    ("Sensitive or resistant high grade serous ovarian cancer", ["ovarian high grade serous adenocarcinoma"],
     "Hypersensitivity"),
    ("Diagnosis or treatment of gastric adenocarcinoma", GASTRIC, "Disease or Disorder"),
    ("Recurrence or metastasis of gastric cancer", GASTRIC, "Recurrent"),
    ("Cold or hot tumors of the stomach", GASTRIC, "Pulmonary"),
    ("Central or peripheral nervous system metastases of gastric cancer", GASTRIC, "Osteosarcoma"),
]


@pytest.mark.parametrize(("name", "requested", "never"),
                         [(c, r, n) for name, r, n in Q1_ROWS for c in _cases(name)])
def test_r12_q1_an_ordinary_word_never_reads_an_unrelated_disease(name, requested, never):
    d = dg.indication_diagnostic([name], requested)
    assert never not in d["record"].split("'", 2)[2], d["record"]


@pytest.mark.parametrize("name", _cases("Central, nephrogenic or gestational diabetes insipidus"))
def test_r12_q1_the_record_coordination_reads_the_request(name):
    d = dg.indication_diagnostic([name], CDI)
    assert d["class"] == ir.AMBIGUOUS_NAME and "Neurogenic Diabetes Insipidus (requested" in d["record"], d["record"]


@pytest.mark.parametrize("name", _cases("Sensitive or resistant gastric cancer"))
def test_r12_q1_an_unread_word_is_named_and_the_site_kept(name):
    d = dg.indication_diagnostic([name], GASTRIC)
    assert d["class"] == ir.NAMES_REQUESTED_SITE and "does not read 'sensitive'" in d["record"].casefold(), d["record"]


SYNONYM_ROWS = [
    # words NCIt uses as heads as often as inside labels keep their synonym (the revision 10 cost stays gone)
    ("Sepsis, infection, or pneumonia", ["sepsis"], "Septicemia (requested"),
    ("Infection or sepsis", ["sepsis"], "Infectious Disorder"),
    ("Sepsis or septic shock", ["sepsis"], "Septicemia (requested"),
    ("Epilepsy or migraine", ["epilepsy"], "Seizure Disorder (requested"),
    ("Hives or angioedema", ["urticaria"], "Urticaria (requested"),
    ("AML or MDS", ["acute myeloid leukemia"], "Acute Myeloid Leukemia (requested"),
]


@pytest.mark.parametrize(("name", "requested", "wanted"),
                         [(c, r, w) for name, r, w in SYNONYM_ROWS for c in _cases(name)])
def test_r12_q1_a_disease_word_keeps_its_synonym(name, requested, wanted):
    assert wanted in dg.indication_diagnostic([name], requested)["record"]


STAGE_ROWS = [
    # a stage the authority does not read with the name is set aside; the name is still read (Q2)
    ("Gastric adenocarcinoma, stage III or IV", GASTRIC),
    ("Gastric adenocarcinoma (stage 3 or 4)", GASTRIC),
    ("Gastric adenocarcinoma (Stage III or IV)", GASTRIC),
    ("Gastric adenocarcinoma, stage 3 or 4", GASTRIC),
    ("Melanoma, stage 3 or 4", ["melanoma"]),
    ("Chronic kidney disease, stage 3 or 4", ["chronic kidney disease"]),
]


@pytest.mark.parametrize(("name", "requested"), [(c, r) for name, r in STAGE_ROWS for c in _cases(name)])
def test_r12_q2_a_trailing_stage_pair_keeps_the_name(name, requested):
    assert dg.indication_diagnostic([name], requested)["class"] == ir.READS_AS_REQUESTED


@pytest.mark.parametrize(("name", "requested"), [
    (c, r) for name, r in [("Breast cancer, stage 2 or 3", ["breast carcinoma"]),
                           ("Breast cancer (stage 2 or 3)", ["breast carcinoma"]),
                           ("Colorectal cancer, stage 3 or 4", ["colorectal carcinoma"])] for c in _cases(name)])
def test_r12_q2_a_staged_name_with_several_readings_names_the_request(name, requested):
    d = dg.indication_diagnostic([name], requested)
    assert d["class"] == ir.AMBIGUOUS_NAME and "(requested" in d["record"], d["record"]


@pytest.mark.parametrize(("name", "requested", "unread"), [
    (c, r, u) for name, r, u in [("Melanoma, grade 1 or 2", ["melanoma"], "grade 1"),
                                 ("Melanoma, type 1 or 2", ["melanoma"], "type 1")] for c in _cases(name)])
def test_r12_q2_a_grade_or_type_pair_that_does_not_invert_is_named_unread(name, requested, unread):
    d = dg.indication_diagnostic([name], requested)
    assert d["class"] == ir.AMBIGUOUS_NAME and "Melanoma (requested" in d["record"], d["record"]
    assert f"does not read '{unread}" in d["record"].casefold(), d["record"]


def test_r12_q2_a_stage_between_names_is_set_aside():
    d = dg.indication_diagnostic(["Gastric adenocarcinoma, stage IV, or NSCLC"], GASTRIC)
    assert "'stage IV' set aside" in d["record"], d["record"]


Q3_ROWS = [
    # a lineage or tissue word is not a site, so the borrowed ending is read (Q3)
    ("Metastatic or neuroendocrine prostate carcinoma", ["metastatic prostate carcinoma"],
     "Metastatic Prostate Carcinoma (requested"),
    ("Metastatic or neuroendocrine lung adenocarcinoma", ["metastatic lung adenocarcinoma"],
     "Metastatic Lung Adenocarcinoma (requested"),
    ("Metastatic or vascular colorectal carcinoma", ["metastatic colorectal carcinoma"],
     "Metastatic Colorectal Carcinoma (requested"),
    ("Relapsing or neural multiple sclerosis", ["relapsing multiple sclerosis"], "Relapsing Multiple Sclerosis (requested"),
]


@pytest.mark.parametrize(("name", "requested", "wanted"), [(c, r, w) for name, r, w in Q3_ROWS for c in _cases(name)])
def test_r12_q3_a_lineage_word_does_not_block_the_borrowed_ending(name, requested, wanted):
    d = dg.indication_diagnostic([name], requested)
    assert d["class"] == ir.AMBIGUOUS_NAME and wanted in d["record"], d["record"]


@pytest.mark.parametrize(("name", "requested", "never"), [
    (c, r, n) for name, r, n in [
        ("Metastatic or gastroesophageal junction signet ring cell carcinoma", GASTRIC,
         "Metastatic Signet Ring Cell Adenocarcinoma"),
        ("Metastatic or esophagogastric junction signet ring cell carcinoma", GASTRIC,
         "Metastatic Signet Ring Cell Adenocarcinoma"),
        ("Metastatic or extrahepatic bile duct carcinoma", ["intrahepatic cholangiocarcinoma"],
         "Metastatic Bile Duct Carcinoma"),
        ("Metastatic or pancreatic neuroendocrine carcinoma", ["lung neuroendocrine carcinoma"], "shares subtypes"),
    ] for c in _cases(name)])
def test_r12_q4_a_borrowed_ending_never_drops_a_junction_or_a_duct(name, requested, never):
    assert never not in dg.indication_diagnostic([name], requested)["record"]


@pytest.mark.parametrize(("name", "requested", "wanted"), [
    (c, r, w) for name, r, w in [
        ("Spinal muscular atrophy, type 1 or 2", ["spinal muscular atrophy type 2"], "Type 2 (requested"),
        ("Spinal muscular atrophy (type 1 or 2)", ["spinal muscular atrophy type 2"], "Type 2 (requested"),
        ("Neurofibromatosis, type 1 or 2", ["neurofibromatosis type 2"], "Type 2 (requested"),
        ("Glycogen storage disease, type I or III", ["glycogen storage disease type iii"], "Type III (requested"),
    ] for c in _cases(name)])
def test_r12_q5_a_number_after_the_name_is_read(name, requested, wanted):
    d = dg.indication_diagnostic([name], requested)
    assert wanted.casefold() in d["record"].casefold(), d["record"]


@pytest.mark.parametrize("name", _cases("Stage III or 1st line gastric cancer"))
def test_r12_q6_an_ordinal_is_not_numbered(name):
    assert "stage 1st" not in dg.indication_diagnostic([name], GASTRIC)["record"].casefold()


def test_r12_q7_a_label_two_codes_share_is_shown_with_its_codes():
    d = dg.indication_diagnostic(["ITP or TTP"], ["immune thrombocytopenic purpura"])
    record = d["record"]
    assert record.count("Primary Immune Thrombocytopenia (C") == 2, record


@pytest.mark.parametrize("name", _cases("Locally advanced or metastatic gastric adenocarcinoma")
                         + _cases("Diffuse or follicular lymphoma"))
def test_r12_controls_are_unchanged(name):
    d = dg.indication_diagnostic([name], GASTRIC)
    assert "Gastric Diffuse" not in d["record"]
    if "locally" in name.casefold():
        assert d["class"] == ir.READS_AS_REQUESTED
