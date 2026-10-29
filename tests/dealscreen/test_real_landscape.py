"""Regression on the REAL public FcRn / gMG landscape (INTERNAL DEVELOPMENT, not validation).

Pins what DealScreen does with 40 real programs today, so a later engine change that moves
any classification is visible. The reference was committed before screening.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from bve.dealscreen.review import Action, DecisionRejected, ReviewerKind
from bve.dealscreen.workspace import Workspace

REAL = Path(__file__).resolve().parents[2] / "examples" / "dealscreen_real"
#: The same symbols the S&E ontology resolves for this landscape (checked 2026-10-28).
TARGETS = {t.casefold(): t for t in ["BTK", "C5", "CD19", "CD38", "CD40", "CFB", "FCGRT", "IL6R",
                                      "MS4A1", "TNFSF13B"]} | {"bcma": "TNFRSF17"}


@pytest.fixture(scope="module")
def real_ws(tmp_path_factory):
    from bve.se.ontology.targets import reset_resolver_cache

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(tmp_path_factory.mktemp("none") / "absent"))
        reset_resolver_cache()
        ws = Workspace(tmp_path_factory.mktemp("real") / "ws")
        ws.import_landscape(REAL / "landscape_fcrn_gmg.csv", REAL / "profile_public_landscape.yaml",
                            REAL / "buyer_fcrn_gmg.yaml")
        ws.screen(lambda text: TARGETS.get(text.strip().casefold()))
        yield ws
    reset_resolver_cache()


def _by_program(ws: Workspace) -> dict[str, dict]:
    ext = {a.asset_id: a.external_id for a in ws.assets()}
    return {ext[s["asset_id"]]: s for s in ws.screening()["screens"]}


def test_every_cell_has_field_provenance():
    rows = list(csv.DictReader((REAL / "landscape_fcrn_gmg.csv").open()))
    prov = {(r["program_id"], r["field"]) for r in csv.DictReader((REAL / "field_provenance.csv").open())}
    for row in rows:
        for field in ("Target", "Mechanism", "Modality", "Therapeutic Area", "Indication", "Highest Phase",
                      "Status", "Status Date", "Company", "Partnerships", "Aliases"):
            if row[field]:
                assert (row["Program ID"], field) in prov, (row["Program ID"], field)
    assert all(not row["US Rights"] for row in rows)  # no source stated rights; nothing invented


def test_no_wrong_inclusion_or_exclusion_against_the_reference(real_ws):
    reference = {r["program_id"]: r["reference_scope"] for r in
                 csv.DictReader((REAL / "reference_manual_assessment.csv").open())}
    screens = _by_program(real_ws)
    for program, s in screens.items():
        if reference[program] == "IN":
            assert s["disposition"] != "EXCLUDED", program
        if reference[program] == "OUT":
            assert s["disposition"] != "ELIGIBLE", program


def test_pinned_real_result(real_ws):
    f = real_ws.screening()["funnel"]
    # 4/14/22 until cycle A1; RW-05 and RW-09 became ELIGIBLE when "Generalized Myasthenia Gravis"
    # was read (disclosed) as myasthenia gravis. The v1 research results are unchanged history.
    assert (f["eligible"], f["unresolved"], f["excluded"]) == (6, 12, 22)
    s = _by_program(real_ws)
    assert {p for p, x in s.items() if x["disposition"] == "ELIGIBLE"} == {
        "RW-03", "RW-04", "RW-05", "RW-06", "RW-07", "RW-09"}
    # The documented misses, each with its cause:
    gate = {p: {d["requirement_id"]: d["status"] for d in x["decisions"]} for p, x in s.items()}
    assert gate["RW-01"]["modality.required"] == "UNKNOWN"  # "Protein" is not a modality term
    assert gate["RW-05"]["strategy.indication"] == "PASS"  # via the disclosed qualifier reading
    assert s["RW-05"]["indication_readings"] == [{
        "observed": "Generalized Myasthenia Gravis", "read_as": "Myasthenia Gravis",
        "qualifier": "generalized", "rule": s["RW-05"]["indication_readings"][0]["rule"]}]
    assert gate["RW-08"]["target.expression"] == "UNKNOWN"  # no sourced target in the landscape


def test_ai_prepared_records_cannot_approve_or_confirm(real_ws):
    log = real_ws.decision_log()
    ctx = real_ws.decision_context()
    by_ext = {a.external_id: a.asset_id for a in real_ws.assets()}
    with pytest.raises(DecisionRejected, match="approval needs a human"):
        log.record(action=Action.APPROVE_FINALIST, subject_id=by_ext["RW-03"], new_state="APPROVED",
                   reviewer_id="ai", rationale="r", reviewer_kind=ReviewerKind.AI_PREPARED, context=ctx)
    with pytest.raises(DecisionRejected, match="only by a human"):
        log.record(action=Action.REJECT_CLAIM, subject_id="x", new_state="REJECTED",
                   reviewer_id="ai", rationale="r", reviewer_kind=ReviewerKind.AI_PREPARED, context=ctx)
    rec = log.record(action=Action.APPROVE_FINALIST, subject_id=by_ext["RW-03"],
                     new_state="CANDIDATE_NOT_APPROVED", reviewer_id="ai", rationale="r",
                     reviewer_kind=ReviewerKind.AI_PREPARED, context=ctx)
    assert rec["new_state"] == "CANDIDATE_NOT_APPROVED"


def test_memo_names_the_data_and_the_approver_honestly(real_ws, tmp_path):
    from bve.dealscreen.memo import build_memo

    by_ext = {a.external_id: a.asset_id for a in real_ws.assets()}
    log = real_ws.decision_log()
    if by_ext["RW-04"] not in log.state.finalists:
        log.record(action=Action.APPROVE_FINALIST, subject_id=by_ext["RW-04"],
                   new_state="CANDIDATE_NOT_APPROVED", reviewer_id="ai", rationale="r",
                   reviewer_kind=ReviewerKind.AI_PREPARED, context=real_ws.decision_context())
    text = build_memo(real_ws)
    assert "Synthetic landscape" not in text and "public sources" in text
    assert "NOT approved by a human analyst" in text
