"""BD screening brief (BD_SEARCH_EVALUATION_DEMO v1).

The brief recomposes a finished run for a BD reader; it changes no decision. These tests pin
its honesty rather than its layout: discovery context is never shown as supported, legacy
prose human-PoC is never shown as proof, a missing fact is shown as unknown, and an empty or
broken run is displayed as a failure instead of a clean shortlist.
"""

from __future__ import annotations

import json

import yaml

from bve.cli.se_bd_brief import main
from bve.se.reporting.bd_brief import (
    EvidenceStatus,
    build_bd_brief,
    render_html,
    render_markdown,
    usefulness_checks,
)


def _problem(modalities=("CELL_THERAPY",), human_poc_required=False):
    return {
        "problem_id": "nlq_test",
        "strategic_gap": {
            "therapeutic_areas": ["ONCOLOGY"],
            "indications": ["INDICATION:B_CELL_LYMPHOMA"],
            "target_expression": {
                "operator": "ANY",
                "targets": [{"canonical_id": "CD19", "label": "CD19"}],
            },
            "modalities": list(modalities),
            "capability_constraints": {"manufacturing": []},
            "evidence_floor": {
                "minimum_stage": "PHASE_1",
                "human_poc_required": human_poc_required,
            },
            "clinical_effect_bar": {"endpoint": None},
            "acceptable_deal_routes": [],
        },
    }


def _citation(native="NCT00000001", field="development_stage_order", origin="SOURCE_DOCUMENT"):
    return {
        "origin": origin,
        "source_family": "ClinicalTrials.gov",
        "native_id": native,
        "url": f"https://clinicaltrials.gov/study/{native}",
        "structured_field": field,
        "evidence_span": None,
        "effective_date": None,
    }


def _entry(
    asset_id="asset:a",
    name="Example-cel",
    *,
    disposition="UNRESOLVED",
    target_status="CONFIRMED_TARGET",
    authority_modality="CELL_THERAPY",
    discovery_modality="CAR_T",
    phase="PHASE_2",
    company="Example Bio",
    review_reasons=(),
):
    target_citations = (
        [
            {
                "origin": "STRUCTURED_AUTHORITY",
                "source_family": "chembl",
                "native_id": "7686",
                "url": None,
                "structured_field": "DIRECT_TARGET -> TARGET:CD80"
                if target_status == "CONFIRMED_OTHER_TARGET"
                else "DIRECT_TARGET -> TARGET:CD19",
                "effective_date": "ChEMBL_37",
            }
        ]
        if target_status != "UNRESOLVED"
        else []
    )
    return {
        "asset_id": asset_id,
        "name": name,
        "position": 1,
        "disposition": disposition,
        "target_id": "TARGET:CD19",
        "target_status": target_status,
        "review_reasons": list(review_reasons),
        "why": ["found while searching CD19; named in 3 source documents"],
        "facts": [
            {
                "label": "Company",
                "value": company,
                "citations": [_citation(field="lead_sponsor")] if company else [],
            },
            {
                "label": "Modality",
                "value": discovery_modality,
                "citations": [],
                "note": "trial text",
            },
            {
                "label": "Authority modality",
                "value": authority_modality,
                "citations": [],
                "note": "ChEMBL_37 molecule type of DRUG:EXAMPLE (CHEMBL1: Cell)"
                if authority_modality
                else "UNKNOWN",
            },
            {"label": "Phase", "value": phase, "citations": [_citation()] if phase else []},
            {"label": "Target", "value": None, "citations": target_citations},
        ],
    }


def _run(entries, *, excluded=(), result=None, problem=None, deferred=()):
    return {
        "problem": problem or _problem(),
        "shortlist": {
            "problem_id": "nlq_test",
            "run_id": "se:test",
            "as_of_date": "2026-09-24",
            "run_status": "INCOMPLETE",
            "blind_spots": ["mandatory source 'sec_edgar' has no configured connector"],
            "counts": {
                "total_candidates": len(entries),
                "eligible": 0,
                "review": len(entries),
                "excluded": len(excluded),
            },
            "entries": list(entries),
            "excluded": list(excluded),
            "deferred": list(deferred),
        },
        "result": result,
    }


def _result(asset_id="asset:a", *, contradicting=(), gates=()):
    return {
        "gates": {
            asset_id: {
                "subject_id": asset_id,
                "decisions": [
                    {
                        "requirement_id": r,
                        "status": s,
                        "rationale": f"{r} {s}",
                        "analyst_override": None,
                    }
                    for r, s in gates
                ],
            }
        },
        "poc_facts": [
            {
                "subject_id": asset_id,
                "fact_type": "human_poc_present",
                "value": True,
                "supporting_claim_ids": ["claim:1"],
                "contradicting_claim_ids": list(contradicting),
            }
        ],
        "claims": {
            "claim:1": {
                "claim_id": "claim:1",
                "source_document_id": "document:1",
                "locator": "abstract",
                "supporting_passage": '"abstract": "ORR was 80% in 20 patients.",',
            }
        },
        "documents": {
            "document:1": {
                "publisher": "PubMed",
                "source_url": "https://pubmed.ncbi.nlm.nih.gov/1/",
            }
        },
    }


def test_authority_supported_card_and_discovery_modality_is_only_a_hint():
    brief = build_bd_brief(_run([_entry()]))
    card = brief.candidates[0]
    assert card.target.status is EvidenceStatus.SUPPORTED
    assert card.modality.status is EvidenceStatus.SUPPORTED
    assert card.discovery_modality == "CAR_T"
    assert card.company.status is EvidenceStatus.UNVERIFIED  # sponsors are not owners
    assert brief.review_first == ("Example-cel",)
    assert "not evidence" in render_markdown(brief)


def test_discovery_context_target_is_never_supported():
    card = build_bd_brief(_run([_entry(target_status="UNRESOLVED")])).candidates[0]
    assert card.target.status is EvidenceStatus.UNKNOWN
    assert card.target.value is None
    assert card.questions[0].area == "Biology / target"


def test_target_gate_pass_without_authority_is_disclosed_not_promoted():
    result = _result(gates=[("target.expression", "PASS")])
    card = build_bd_brief(_run([_entry(target_status="UNRESOLVED")], result=result)).candidates[0]
    assert card.target.status is EvidenceStatus.UNKNOWN
    assert "nevertheless PASSED" in card.target.basis


def test_other_target_and_wrong_modality_are_contradictory():
    entry = _entry(target_status="CONFIRMED_OTHER_TARGET", authority_modality="SMALL_MOLECULE")
    card = build_bd_brief(_run([entry])).candidates[0]
    assert card.target.status is EvidenceStatus.CONTRADICTORY
    assert card.target.value == "TARGET:CD80"
    assert card.modality.status is EvidenceStatus.CONTRADICTORY


def test_unrequested_modality_is_not_contradictory():
    run = _run([_entry(authority_modality="PROTEIN")], problem=_problem(modalities=()))
    assert build_bd_brief(run).candidates[0].modality.status is EvidenceStatus.SUPPORTED


def test_missing_facts_are_unknown_not_omitted():
    entry = _entry(authority_modality=None, phase=None, company=None, target_status="UNRESOLVED")
    card = build_bd_brief(_run([entry])).candidates[0]
    for fact in (card.target, card.modality, card.stage, card.company, card.human_efficacy):
        assert fact.status is EvidenceStatus.UNKNOWN
    assert "result.json not available" in card.human_efficacy.basis


def test_legacy_human_poc_is_unverified_with_passage():
    brief = build_bd_brief(_run([_entry()], result=_result()))
    poc = brief.candidates[0].human_efficacy
    assert poc.status is EvidenceStatus.UNVERIFIED
    assert poc.sources[0].passage == "ORR was 80% in 20 patients."
    assert poc.sources[0].url == "https://pubmed.ncbi.nlm.nih.gov/1/"
    md = render_markdown(brief)
    assert "not established clinical proof" in md


def test_conflicting_human_poc_is_contradictory():
    poc = (
        build_bd_brief(_run([_entry()], result=_result(contradicting=["claim:2"])))
        .candidates[0]
        .human_efficacy
    )
    assert poc.status is EvidenceStatus.CONTRADICTORY


def test_engine_eligible_resting_on_unverified_poc_is_labelled():
    result = _result(gates=[("target.expression", "PASS"), ("evidence.human_poc", "PASS")])
    brief = build_bd_brief(_run([_entry(disposition="ELIGIBLE")], result=result))
    assert brief.candidates[0].eligibility.startswith("Engine gates pass; human-PoC unverified")
    assert brief.engine_eligible == ("Example-cel",)


def test_excluded_candidates_name_the_failed_requirement():
    excluded = _entry(
        "asset:x",
        "abatacept",
        disposition="EXCLUDED",
        target_status="CONFIRMED_OTHER_TARGET",
        review_reasons=["target.expression FAIL: Canonical construct targets do not satisfy."],
    )
    brief = build_bd_brief(_run([_entry()], excluded=[excluded]))
    assert brief.excluded[0].eligibility == "Fails"
    assert brief.excluded[0].failed_requirements[0].startswith("target.expression")


def test_unknown_gate_drives_next_action_and_change_triggers():
    result = _result(gates=[("modality.required", "UNKNOWN")])
    brief = build_bd_brief(_run([_entry()], result=result))
    assert "modality.required" in brief.next_action
    assert any("modality.required" in t for t in brief.candidates[0].change_triggers)


def test_duplicate_authority_records_are_flagged_not_merged():
    brief = build_bd_brief(
        _run([_entry("asset:a", "Kymriah"), _entry("asset:b", "tisagenlecleucel")])
    )
    assert len(brief.candidates) == 2
    assert brief.candidates[0].duplicate_of == ("tisagenlecleucel",)


def test_cell_therapy_gets_manufacturing_and_safety_questions_only_when_relevant():
    cell = build_bd_brief(_run([_entry()])).candidates[0]
    small = build_bd_brief(
        _run(
            [_entry(authority_modality="SMALL_MOLECULE", discovery_modality=None)],
            problem=_problem(modalities=()),
        )
    ).candidates[0]
    assert {"Manufacturing / scale-up", "Safety / dosing"} <= {q.area for q in cell.questions}
    assert "Manufacturing / scale-up" not in {q.area for q in small.questions}


def test_empty_run_is_shown_as_failure():
    brief = build_bd_brief(_run([]))
    assert "cannot answer" in brief.next_action
    assert usefulness_checks(brief)["2_candidates_named"] is False


def test_unenforced_requirements_are_listed():
    gap = build_bd_brief(
        _run([_entry()]), context={"unenforced_requirements": ["allogeneic only"]}
    ).gap
    assert gap.not_enforced[0] == "allogeneic only"
    assert any("clinical effect bar" in x for x in gap.not_enforced)


def test_usefulness_checks_pass_on_a_well_formed_brief():
    checks = usefulness_checks(build_bd_brief(_run([_entry()], result=_result())))
    assert all(checks.values()), checks


def test_html_escapes_source_text():
    brief = build_bd_brief(_run([_entry(name="<script>x</script>")]))
    page = render_html(brief)
    assert "<script>x" not in page
    assert "&lt;script&gt;" in page


def test_cli_writes_brief_and_rejects_non_run_dir(tmp_path):
    run = _run([_entry()])
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "problem.yaml").write_text(yaml.safe_dump(run["problem"]))
    (run_dir / "shortlist.json").write_text(json.dumps(run["shortlist"]))
    out = tmp_path / "out"
    assert main(["--run-dir", str(run_dir), "--output-dir", str(out)]) == 0
    assert (out / "brief.html").exists() and (out / "brief.md").exists()
    assert all(json.loads((out / "checks.json").read_text()).values())
    assert main(["--run-dir", str(tmp_path), "--output-dir", str(out)]) == 2


def test_gate_and_display_disagreement_is_flagged_both_ways():
    result = _result(gates=[("target.expression", "PASS"), ("modality.required", "UNKNOWN")])
    card = build_bd_brief(_run([_entry(target_status="UNRESOLVED")], result=result)).candidates[0]
    assert "Target: shown UNKNOWN, engine gate PASS" in card.conflicts
    assert "Modality: shown SUPPORTED, engine gate UNKNOWN" in card.conflicts
    assert "Engine disagreement" in render_markdown(
        build_bd_brief(_run([_entry(target_status="UNRESOLVED")], result=result))
    )


def test_human_poc_requirement_is_listed_as_enforced_with_caveat():
    gap = build_bd_brief(_run([_entry()], problem=_problem(human_poc_required=True))).gap
    assert any("human proof-of-concept required" in x for x in gap.enforced)
    assert not any("not required" in x for x in gap.not_enforced)


def test_field_header_is_stripped_from_displayed_name():
    card = build_bd_brief(
        _run([_entry(name="Assigned Interventions CD19/BCMA CAR T-cells")])
    ).candidates[0]
    assert card.name == "CD19/BCMA CAR T-cells"


def test_summary_never_claims_confirmed_efficacy():
    brief = build_bd_brief(_run([_entry()], result=_result()))
    assert any("No human efficacy is confirmed" in x for x in brief.summary)
    assert "## Summary" in render_markdown(brief)


def test_stage_does_not_claim_requested_indication_is_verified():
    brief = build_bd_brief(_run([_entry()]))
    assert 'Indication-specific stage is UNVERIFIED' in brief.candidates[0].stage.basis
    assert 'Indication-specific stage is UNVERIFIED' in render_markdown(brief)
    assert 'Indication-specific stage is UNVERIFIED' in render_html(brief)
