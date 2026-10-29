"""Cycle A2: AI proposals for human confirmation, identity resolution vocabulary and groups,
activity disclosure (AI-SIMULATED analyst findings; INTERNAL DEVELOPMENT).

Criteria: research/dealscreen_product_program/analyst_simulation/PRIORITIZED_FIXES.md (G1-G3).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bve.dealscreen.review import Action, DecisionRejected, ReviewerKind
from bve.dealscreen.workspace import Workspace

REAL = Path(__file__).resolve().parents[2] / "examples" / "dealscreen_real"
TARGETS = {t.casefold(): t for t in ["BTK", "C5", "CD19", "CD38", "CD40", "CFB", "FCGRT", "IL6R",
                                      "MS4A1", "TNFSF13B"]} | {"fcrn": "FCGRT"}
TENQ = "https://www.sec.gov/Archives/edgar/data/1764013/000176401326000011/imvt-20251231.htm"
QUOTE = "The Company is pursuing a broad anti-FcRn strategy based on its lead asset, IMVT-1402."


#: The ChEMBL synonyms the S&E authority resolves for these names (as in the Cycle 2 tests).
AUTHORITY = {"batoclimab": "DRUG:BATOCLIMAB", "hbm9161": "DRUG:BATOCLIMAB", "rvt-1401": "DRUG:BATOCLIMAB",
             "gefurulimab": "DRUG:GEFURULIMAB", "alxn1720": "DRUG:GEFURULIMAB"}


def normalizer(text: str) -> str | None:
    return TARGETS.get(text.strip().casefold())


@pytest.fixture
def ws(tmp_path, monkeypatch):
    from bve.se.ontology.targets import reset_resolver_cache

    monkeypatch.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(tmp_path / "absent"))
    reset_resolver_cache()
    workspace = Workspace(tmp_path / "ws")
    workspace.import_landscape(REAL / "landscape_fcrn_gmg_v2.csv", REAL / "profile_public_landscape_v2.yaml",
                               REAL / "buyer_fcrn_gmg.yaml",
                               drug_authority=lambda n: AUTHORITY.get(n.casefold()))
    workspace.screen(normalizer)
    yield workspace
    reset_resolver_cache()


def _ids(ws: Workspace) -> dict[str, str]:
    return {a.external_id: a.asset_id for a in ws.assets()}


def _propose(ws, program="RW-08", field="target", value="FCGRT", **over):
    detail = {"field": field, "value": value, "source_url": TENQ,
              "source_title": "Immunovant 10-Q (period ended 2025-12-31)", "source_date": "",
              "evidence_span": QUOTE} | over
    return ws.propose(_ids(ws)[program], detail, reviewer_id="ai-assistant",
                      target_normalizer=normalizer)


def _screen_bytes(ws) -> bytes:
    ws.screen(normalizer)
    return (ws.root / "screening.json").read_bytes()


# -- G1 ----------------------------------------------------------------------------------
def test_g1_proposal_is_stored_as_a_finding_and_changes_nothing(ws):
    before = _screen_bytes(ws)
    finding = _propose(ws)
    assert finding.provider == "ai_proposal:ai-assistant"
    assert finding.proposed_value == "FCGRT" and finding.evidence_span == QUOTE
    assert any("re-check the quote" in lim for lim in finding.limitations)
    assert finding.finding_id in {f.finding_id for f in ws.findings()}
    assert _screen_bytes(ws) == before


def test_g1_human_confirmation_applies_it_and_ai_confirmation_is_refused(ws):
    finding = _propose(ws)
    log = ws.decision_log()
    with pytest.raises(DecisionRejected):
        log.record(action=Action.CONFIRM_FINDING, subject_id=finding.finding_id, new_state="CONFIRMED",
                   reviewer_id="ai", rationale="r", reviewer_kind=ReviewerKind.AI_PREPARED,
                   context=ws.decision_context(normalizer))
    log.record(action=Action.CONFIRM_FINDING, subject_id=finding.finding_id, new_state="CONFIRMED",
               reviewer_id="analyst-1", rationale="checked the 10-Q", reviewer_kind=ReviewerKind.HUMAN,
               context=ws.decision_context(normalizer))
    screen = {s["asset_id"]: s for s in ws.screen(normalizer).to_dict()["screens"]}[_ids(ws)["RW-08"]]
    gate = next(d for d in screen["decisions"] if d["requirement_id"] == "target.expression")
    assert gate["status"] == "PASS"
    assert finding.finding_id in gate["supporting_or_contradictory_claim_ids"]


@pytest.mark.parametrize("over", [
    {"source_url": "my notes"},
    {"evidence_span": ""},
    {"value": ""},
    {"field": "program_name", "value": "x"},
    {"value": "IL-23"},                                        # unreadable target
    {"field": "us_rights", "value": "available"},               # quote does not state it
])
def test_g1_bad_proposals_are_refused_and_write_nothing(ws, over):
    with pytest.raises(DecisionRejected):
        _propose(ws, **over)
    assert not (ws.root / "findings.json").exists() or not [
        f for f in ws.findings() if f.provider.startswith("ai_proposal")]


def test_g1_same_proposal_twice_is_one_finding(ws):
    a, b = _propose(ws), _propose(ws)
    assert a.finding_id == b.finding_id
    assert sum(f.provider.startswith("ai_proposal") for f in ws.findings()) == 1


# -- G2 ----------------------------------------------------------------------------------
def _bato_flag(ws) -> str:
    ids = _ids(ws)
    return next(f.flag_id for f in ws.flags() if set(f.asset_ids) == {ids["RW-05"], ids["RW-07"]})


def _resolve(ws, flag_id, state, kind=ReviewerKind.HUMAN):
    return ws.decision_log().record(
        action=Action.RESOLVE_IDENTITY_FLAG, subject_id=flag_id, new_state=state, reviewer_id="analyst-1",
        rationale="RVT-1401 is Roivant's former code for batoclimab", reviewer_kind=kind,
        context=ws.decision_context(normalizer))


def test_g2_free_text_resolution_is_refused(ws):
    with pytest.raises(DecisionRejected, match="SAME_MOLECULE"):
        _resolve(ws, _bato_flag(ws), "merge them")


def test_g2_legacy_keep_separate_is_still_accepted(ws):
    rec = _resolve(ws, _bato_flag(ws), "KEEP_SEPARATE")
    assert rec["new_state"] == "KEEP_SEPARATE"


def test_g2_human_same_molecule_groups_without_changing_gates(ws):
    from bve.dealscreen.groups import identity_groups

    before = _screen_bytes(ws)
    _resolve(ws, _bato_flag(ws), "SAME_MOLECULE")
    assert _screen_bytes(ws) == before  # grouping never changes a gate or disposition
    groups = identity_groups(ws.flags(), ws.decision_log())
    ids = _ids(ws)
    assert groups[ids["RW-05"]] == groups[ids["RW-07"]]
    assert ids["RW-06"] not in groups  # its flags are unresolved


def test_g2_memo_counts_distinct_molecules_after_human_resolution(ws):
    from bve.dealscreen.memo import build_memo

    _resolve(ws, _bato_flag(ws), "SAME_MOLECULE")
    ws.screen(normalizer)
    text = build_memo(ws)
    assert "6 eligible records = at most 5 distinct molecules after human-confirmed identity" in text


# -- G3 ----------------------------------------------------------------------------------
def test_g3_candidate_line_discloses_stopped_development(ws):
    from bve.dealscreen.memo import build_memo

    ids = _ids(ws)
    ws.decision_log().record(action=Action.APPROVE_FINALIST, subject_id=ids["RW-09"],
                             new_state="CANDIDATE_NOT_APPROVED", reviewer_id="ai", rationale="r",
                             reviewer_kind=ReviewerKind.AI_PREPARED, context=ws.decision_context(normalizer))
    ws.screen(normalizer)
    line = next(x for x in build_memo(ws).splitlines() if x.startswith("- Orilanolimab"))
    assert "source status suggests development stopped (verify)" in line


# -- regressions from the A2 code review (AI reviewer) ---------------------------------
@pytest.mark.parametrize("bad", ["2025-13-45", "garbage", "25/01/2025"])
def test_review_a2_1_bad_dates_refused_for_proposals_and_assertions(ws, bad):
    with pytest.raises(DecisionRejected, match="YYYY-MM-DD"):
        _propose(ws, source_date=bad)
    with pytest.raises(DecisionRejected, match="YYYY-MM-DD"):
        ws.decision_log().record(
            action=Action.ASSERT_FACT, subject_id=_ids(ws)["RW-08"], new_state="ASSERTED",
            reviewer_id="analyst-1", rationale="r", reviewer_kind=ReviewerKind.HUMAN,
            detail={"field": "target", "value": "FCGRT", "source_url": TENQ, "evidence_span": QUOTE,
                    "source_date": bad},
            context=ws.decision_context(normalizer))
    assert not ws.decisions_path.exists()


def test_review_a2_2_proposer_cannot_confirm_its_own_proposal(ws):
    finding = _propose(ws)
    with pytest.raises(DecisionRejected, match="cannot confirm"):
        ws.decision_log().record(action=Action.CONFIRM_FINDING, subject_id=finding.finding_id,
                                 new_state="CONFIRMED", reviewer_id="ai-assistant", rationale="r",
                                 reviewer_kind=ReviewerKind.HUMAN, context=ws.decision_context(normalizer))


def test_review_a2_3_finding_edited_after_confirmation_is_not_applied(ws):
    import json

    finding = _propose(ws)
    rec = ws.decision_log().record(action=Action.CONFIRM_FINDING, subject_id=finding.finding_id,
                                   new_state="CONFIRMED", reviewer_id="analyst-1", rationale="checked",
                                   reviewer_kind=ReviewerKind.HUMAN, context=ws.decision_context(normalizer))
    assert rec["detail"]["finding_sha256"]
    path = ws.root / "findings.json"
    data = json.loads(path.read_text())
    for f in data:
        if f["finding_id"] == finding.finding_id:
            f["evidence_span"] = "edited after confirmation"
    path.write_text(json.dumps(data))
    screen = {s["asset_id"]: s for s in ws.screen(normalizer).to_dict()["screens"]}[_ids(ws)["RW-08"]]
    gate = next(d for d in screen["decisions"] if d["requirement_id"] == "target.expression")
    assert gate["status"] == "UNKNOWN"


def test_review_a2_4_activity_combination() -> None:
    from bve.dealscreen.facts import combine_activity

    assert combine_activity([]) == "UNKNOWN"
    assert combine_activity(["ACTIVE", "UNKNOWN"]) == "ACTIVE"
    assert combine_activity(["ACTIVE", "MARKETED"]) == "ACTIVE"
    assert combine_activity(["ACTIVE", "INACTIVE"]) == "CONFLICTING"
    assert combine_activity(["MARKETED", "INACTIVE"]) == "CONFLICTING"


def test_review_a2_5_groups_sharing_a_label_are_counted_separately() -> None:
    from types import SimpleNamespace

    from bve.dealscreen.groups import distinct_count, identity_groups
    from bve.dealscreen.models import IdentityFlag

    flags = [IdentityFlag(flag_id=f, asset_ids=ids, kind="PROPOSED_MERGE", relationship="IDENTITY_ALIAS",
                          shared_value="X", basis="t")
             for f, ids in (("f1", ["a", "b"]), ("f2", ["c", "d"]))]
    log = SimpleNamespace(state=SimpleNamespace(identity_resolutions={
        "f1": {"state": "SAME_MOLECULE", "reviewer_kind": "HUMAN"},
        "f2": {"state": "SAME_MOLECULE", "reviewer_kind": "HUMAN"}}))
    groups = identity_groups(flags, log)  # type: ignore[arg-type]
    assert distinct_count(["a", "b", "c", "d"], groups) == 2
    assert distinct_count(["a", "b", "X"], groups) == 2
