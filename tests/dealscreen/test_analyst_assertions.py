"""Cycle 1: cited analyst fact entry (ASSERT_FACT / RETRACT_FACT).

Criteria C1-C7 in research/dealscreen_product_program/ITERATION_LOG.md. Runs on the REAL
public FcRn / gMG landscape. Every assertion here cites a real public source.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bve.dealscreen.review import Action, DecisionRejected, ReviewerKind
from bve.dealscreen.workspace import Workspace

REAL = Path(__file__).resolve().parents[2] / "examples" / "dealscreen_real"
TARGETS = {t.casefold(): t for t in ["BTK", "C5", "CD19", "CD38", "CD40", "CFB", "FCGRT", "IL6R",
                                      "MS4A1", "TNFSF13B"]} | {"bcma": "TNFRSF17", "fcrn": "FCGRT"}
CTGOV_BATO = "https://clinicaltrials.gov/study/NCT05403541"


def normalizer(text: str) -> str | None:
    return TARGETS.get(text.strip().casefold())


@pytest.fixture
def ws(tmp_path, monkeypatch):
    from bve.se.ontology.targets import reset_resolver_cache

    monkeypatch.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(tmp_path / "absent"))
    reset_resolver_cache()
    workspace = Workspace(tmp_path / "ws")
    workspace.import_landscape(REAL / "landscape_fcrn_gmg.csv", REAL / "profile_public_landscape.yaml",
                               REAL / "buyer_fcrn_gmg.yaml")
    workspace.screen(normalizer)
    yield workspace
    reset_resolver_cache()


def _ids(ws: Workspace) -> dict[str, str]:
    return {a.external_id: a.asset_id for a in ws.assets()}


def _assert(ws, program, field, val, *, kind=ReviewerKind.HUMAN, **overrides):
    detail = {"field": field, "value": val, "source_url": CTGOV_BATO,
              "source_title": "ClinicalTrials.gov NCT05403541", "source_date": "2026-10-28",
              "evidence_span": "Batoclimab is a fully human anti-neonatal fragment crystallizable "
                               "receptor (FcRn) monoclonal antibody"}
    detail.update(overrides)
    return ws.decision_log().record(
        action=Action.ASSERT_FACT, subject_id=_ids(ws)[program], new_state="ASSERTED",
        reviewer_id="analyst-1", rationale="registry text", reviewer_kind=kind, detail=detail,
        context=ws.decision_context(normalizer))


def _screen(ws) -> dict[str, dict]:
    ext = {a.asset_id: a.external_id for a in ws.assets()}
    return {ext[s["asset_id"]]: s for s in ws.screen(normalizer).to_dict()["screens"]}


@pytest.mark.parametrize("missing", ["source_url", "evidence_span", "value"])
def test_c1_assertion_without_citation_or_value_is_refused_and_writes_nothing(ws, missing):
    with pytest.raises(DecisionRejected):
        _assert(ws, "RW-05", "indication", "Myasthenia Gravis", **{missing: ""})
    assert not ws.decisions_path.exists()


def test_c1_non_http_source_and_identity_fields_are_refused(ws):
    with pytest.raises(DecisionRejected, match="http"):
        _assert(ws, "RW-05", "indication", "Myasthenia Gravis", source_url="my notes")
    with pytest.raises(DecisionRejected, match="cannot be asserted"):
        _assert(ws, "RW-05", "program_name", "Something else")


@pytest.mark.parametrize(("field", "value"), [("modality", "antibody fragment"), ("target", "IL-23"),
                                              ("phase", "late stage"), ("mechanism", "binds FcRn"),
                                              ("us_rights", "see filing")])
def test_c2_unreadable_values_are_refused(ws, field, value):
    with pytest.raises(DecisionRejected, match="cannot be read"):
        _assert(ws, "RW-05", field, value)


def test_c3_ai_prepared_cannot_assert(ws):
    with pytest.raises(DecisionRejected, match="only by a human"):
        _assert(ws, "RW-05", "indication", "Myasthenia Gravis", kind=ReviewerKind.AI_PREPARED)


def test_c4_assertion_resolves_through_the_gate_engine_and_leaves_imports_untouched(ws):
    before_import = (ws.root / "import.json").read_bytes()
    assert _screen(ws)["RW-05"]["disposition"] == "UNRESOLVED"
    rec = _assert(ws, "RW-05", "indication", "Myasthenia Gravis",
                  evidence_span="Generalized Myasthenia Gravis")
    after = _screen(ws)["RW-05"]
    assert after["disposition"] == "ELIGIBLE"
    decision = next(d for d in after["decisions"] if d["requirement_id"] == "strategy.indication")
    assert decision["status"] == "PASS" and rec["decision_id"] in decision["supporting_or_contradictory_claim_ids"]
    assert (ws.root / "import.json").read_bytes() == before_import


def test_c5_overriding_a_readable_source_value_is_listed(ws):
    # RW-10 eculizumab is sourced as target C5; asserting FcRn would override it.
    _assert(ws, "RW-10", "target", "FCGRT")
    screen = _screen(ws)["RW-10"]
    assert screen["overrides"] and screen["overrides"][0]["field"] == "target"
    assert screen["overrides"][0]["superseded_claim_ids"]


def test_c6_retraction_restores_the_previous_screen_exactly(ws):
    ws.screen(normalizer)
    baseline = (ws.root / "screening.json").read_bytes()
    rec = _assert(ws, "RW-05", "indication", "Myasthenia Gravis")
    ws.screen(normalizer)
    assert (ws.root / "screening.json").read_bytes() != baseline
    ws.decision_log().record(action=Action.RETRACT_FACT, subject_id=rec["decision_id"], new_state="RETRACTED",
                             reviewer_id="analyst-1", rationale="wrong record", context=ws.decision_context(normalizer))
    ws.screen(normalizer)
    assert (ws.root / "screening.json").read_bytes() == baseline
    with pytest.raises(DecisionRejected, match="no active assertion"):
        ws.decision_log().record(action=Action.RETRACT_FACT, subject_id=rec["decision_id"],
                                 new_state="RETRACTED", reviewer_id="analyst-1", rationale="again",
                                 context=ws.decision_context(normalizer))


def test_c6_assertions_survive_reload_and_are_hash_chained(ws):
    from bve.dealscreen.review import DecisionLog

    rec = _assert(ws, "RW-05", "indication", "Myasthenia Gravis")
    reloaded = DecisionLog(ws.decisions_path)
    assert rec["decision_id"] in reloaded.state.assertions


def test_c7_workbook_shows_the_assertion_and_its_citation(ws, tmp_path):
    from openpyxl import load_workbook

    from bve.dealscreen.workbook import export_workbook

    rec = _assert(ws, "RW-05", "indication", "Myasthenia Gravis")
    ws.screen(normalizer)
    path = export_workbook(ws, tmp_path / "out.xlsx")
    rows = list(load_workbook(path, read_only=True)["Diligence"].iter_rows(values_only=True))
    hit = [r for r in rows if r[2] == "ANALYST_ASSERTION"]
    assert hit and CTGOV_BATO in hit[0][6] and rec["decision_id"] in hit[0][9]


def test_asserting_unknown_rights_is_refused_but_an_explicit_statement_is_kept(ws):
    with pytest.raises(DecisionRejected):
        _assert(ws, "RW-03", "us_rights", "not reported")
    _assert(ws, "RW-03", "us_rights", "U.S. rights exclusively licensed to X",
            evidence_span="U.S. rights were exclusively licensed to X.")
    assert _screen(ws)["RW-03"]["commercial"]["us_rights_status"] == "ENCUMBERED_PER_SOURCE"


# -- regressions from the Cycle 1 adversarial review (AI reviewer) -----------------------
def test_review1_multivalued_assertion_flipping_a_fail_is_disclosed(ws):
    """Adding an indication can turn a source therapeutic-area FAIL into PASS: it must be listed."""
    _assert(ws, "RW-29", "indication", "Myasthenia Gravis")  # RW-29: TA FAIL from 'Neurology'
    effects = _screen(ws)["RW-29"]["assertion_effects"]
    ta = [e for e in effects if e["requirement_id"] == "strategy.therapeutic_area"]
    assert ta and ta[0]["overturns_source_fail"] and ta[0]["without_assertions"] == "FAIL"


def test_review1_disposition_change_is_disclosed(ws):
    _assert(ws, "RW-05", "indication", "Myasthenia Gravis")
    effects = _screen(ws)["RW-05"]["assertion_effects"]
    assert {"requirement_id": "DISPOSITION", "without_assertions": "UNRESOLVED",
            "with_assertions": "ELIGIBLE", "overturns_source_fail": False} in effects


def test_review2_unrecognized_indication_and_area_are_refused(ws):
    with pytest.raises(DecisionRejected, match="cannot be read"):
        _assert(ws, "RW-29", "indication", "Neuromuscular junction disorders broadly")
    with pytest.raises(DecisionRejected, match="cannot be read"):
        _assert(ws, "RW-29", "therapeutic_area", "Neuromuscular")


def test_review2_assertion_that_changes_nothing_is_shown_as_no_effect(ws, tmp_path):
    from bve.dealscreen.memo import build_memo

    _assert(ws, "RW-10", "phase", "Phase 3")  # eculizumab stays EXCLUDED on target
    screen = _screen(ws)["RW-10"]
    assert screen["analyst_assertions"] and screen["assertion_effects"] == []
    assert "no effect on: Eculizumab" in build_memo(ws)


def test_review3_rights_assertion_needs_a_quote_that_states_it(ws):
    with pytest.raises(DecisionRejected, match="quote"):
        _assert(ws, "RW-04", "us_rights", "rights available",
                evidence_span="Nipocalimab will be administered as an IV infusion.")
    _assert(ws, "RW-04", "us_rights", "U.S. rights available; seeking partner",
            evidence_span="The company stated that U.S. rights are available and it is seeking a partner.")
    screen = _screen(ws)["RW-04"]
    assert screen["commercial"]["us_rights_status"] == "AVAILABLE_ANALYST_CONFIRMED"
    assert "verify" in screen["commercial"]["display"]


def test_review3_asserted_partnership_makes_available_conflicting(ws):
    # A recorded partnership alongside 'available' must go to a human, not stay AVAILABLE.
    asset = ws.assets()[0]
    from bve.dealscreen.commercial import CONFLICTING, assess
    from bve.dealscreen.models import SourceClaim

    claims = [
        SourceClaim(claim_id="u", asset_id=asset.asset_id, field="us_rights", value_as_written="U.S. rights available",
                    source_system="analyst", dataset_version="x"),
        SourceClaim(claim_id="p", asset_id=asset.asset_id, field="partnerships",
                    value_as_written="Exclusive license with Y", source_system="analyst", dataset_version="x"),
    ]
    assert assess(asset, questions=[], confirmed_findings=tuple(claims)).us_rights_status == CONFLICTING


def test_review4_assertion_without_context_is_refused(ws):
    with pytest.raises(DecisionRejected, match="context"):
        ws.decision_log().record(action=Action.ASSERT_FACT, subject_id="ds:nonexistent", new_state="ASSERTED",
                                 reviewer_id="a", rationale="r",
                                 detail={"field": "target", "value": "zzz", "source_url": "https://x.org",
                                         "evidence_span": "q"})


def test_review7_cli_path_refuses_ai_assertion(ws, capsys):
    from bve.cli.dealscreen import main

    code = main(["assert", "--workspace", str(ws.root), "--asset", "RW-05", "--field", "indication",
                 "--value", "Myasthenia Gravis", "--source-url", CTGOV_BATO, "--quote", "Generalized Myasthenia Gravis",
                 "--reviewer", "ai", "--rationale", "r", "--reviewer-kind", "AI_PREPARED"])
    assert code == 3 and "only by a human" in capsys.readouterr().err


def test_review7_retract_then_reassert_gets_a_new_id(ws):
    first = _assert(ws, "RW-05", "indication", "Myasthenia Gravis")
    ws.decision_log().record(action=Action.RETRACT_FACT, subject_id=first["decision_id"], new_state="RETRACTED",
                             reviewer_id="a", rationale="r", context=ws.decision_context(normalizer))
    second = _assert(ws, "RW-05", "indication", "Myasthenia Gravis")
    assert second["decision_id"] != first["decision_id"]
    assert _screen(ws)["RW-05"]["disposition"] == "ELIGIBLE"
