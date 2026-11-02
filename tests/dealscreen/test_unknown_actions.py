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
