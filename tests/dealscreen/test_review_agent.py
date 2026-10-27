"""Decision log integrity, approval rules, and the bounded diligence agent."""

from __future__ import annotations

import json
from datetime import date

import pytest

from bve.dealscreen.agent import ClinicalTrialsGovProvider, OfflineEvidenceProvider, Question
from bve.dealscreen.review import (
    Action,
    DecisionContext,
    DecisionLog,
    DecisionRejected,
    LogTampered,
    ReviewerKind,
    ReviewState,
)
from bve.dealscreen.workspace import Workspace


@pytest.fixture
def ws(tmp_path, demo_dir, normalizer) -> Workspace:
    workspace = Workspace(tmp_path / "ws")
    workspace.import_landscape(demo_dir / "landscape_200.csv", demo_dir / "profile_synthetic_vendor.yaml",
                               demo_dir / "buyer_tl1a_ibd.yaml")
    workspace.screen(normalizer)
    return workspace


def _by(ws: Workspace, disposition: str) -> list[str]:
    return [s["asset_id"] for s in ws.screening()["screens"] if s["disposition"] == disposition]


def _approve(ws, asset_id, state="APPROVED", log=None):
    log = log or ws.decision_log()
    return log.record(action=Action.APPROVE_FINALIST, subject_id=asset_id, new_state=state,
                      reviewer_id="analyst-1", rationale="fits", context=ws.decision_context())


def test_ranking_alone_creates_no_finalist(ws):
    assert ws.decision_log().state.finalists == {}
    top = [s for s in ws.screening()["screens"] if s["rank"] == 1 and s["disposition"] == "ELIGIBLE"]
    assert top and top[0]["machine_recommendation"] == "CANDIDATE_FOR_ANALYST_REVIEW"


def test_excluded_asset_cannot_be_approved(ws):
    with pytest.raises(DecisionRejected, match="EXCLUDED"):
        _approve(ws, _by(ws, "EXCLUDED")[0])
    assert not ws.decisions_path.exists()  # a refused decision writes nothing


def test_unresolved_asset_needs_explicit_open_question_acknowledgement(ws):
    asset = _by(ws, "UNRESOLVED")[0]
    with pytest.raises(DecisionRejected, match="APPROVED_WITH_OPEN_QUESTIONS"):
        _approve(ws, asset)
    assert _approve(ws, asset, "APPROVED_WITH_OPEN_QUESTIONS")["old_state"] == "NOT_A_FINALIST"


def test_limits_on_finalists_and_valuations(ws):
    eligible = _by(ws, "ELIGIBLE")
    log = ws.decision_log()
    for asset in eligible[:10]:
        _approve(ws, asset, log=log)
    with pytest.raises(DecisionRejected, match="limited to 10"):
        _approve(ws, eligible[10], log=log)
    ctx = ws.decision_context()
    with pytest.raises(DecisionRejected, match="finalist"):
        log.record(action=Action.SELECT_FOR_VALUATION, subject_id=eligible[10], new_state="SELECTED",
                   reviewer_id="a", rationale="r", context=ctx)
    for asset in eligible[:3]:
        log.record(action=Action.SELECT_FOR_VALUATION, subject_id=asset, new_state="SELECTED",
                   reviewer_id="a", rationale="r", context=ctx)
    with pytest.raises(DecisionRejected, match="at most 3"):
        log.record(action=Action.SELECT_FOR_VALUATION, subject_id=eligible[3], new_state="SELECTED",
                   reviewer_id="a", rationale="r", context=ctx)


def test_decisions_need_reviewer_and_rationale(ws):
    log = ws.decision_log()
    for reviewer, rationale in (("", "r"), ("a", " ")):
        with pytest.raises(DecisionRejected):
            log.record(action=Action.APPROVE_FINALIST, subject_id=_by(ws, "ELIGIBLE")[0],
                       new_state="APPROVED", reviewer_id=reviewer, rationale=rationale,
                       context=ws.decision_context())


def test_log_is_versioned_and_tamper_evident(ws):
    asset = _by(ws, "ELIGIBLE")[0]
    log = ws.decision_log()
    _approve(ws, asset, log=log)
    log.record(action=Action.WITHDRAW_FINALIST, subject_id=asset, new_state="WITHDRAWN",
               reviewer_id="analyst-2", rationale="rights encumbered", context=ws.decision_context())
    reloaded = DecisionLog(ws.decisions_path)
    assert [r["old_state"] for r in reloaded.records] == ["NOT_A_FINALIST", "APPROVED"]
    assert reloaded.state.finalists == {}
    lines = ws.decisions_path.read_text().splitlines()
    forged = json.loads(lines[0])
    forged["reviewer_id"] = "someone-else"
    ws.decisions_path.write_text("\n".join([json.dumps(forged, sort_keys=True), lines[1]]) + "\n")
    with pytest.raises(LogTampered):
        DecisionLog(ws.decisions_path)


def test_synthetic_fixture_decisions_are_labelled(ws):
    rec = ws.decision_log().record(
        action=Action.APPROVE_FINALIST, subject_id=_by(ws, "ELIGIBLE")[0], new_state="APPROVED",
        reviewer_id="synthetic-reviewer-01", rationale="demo", reviewer_kind=ReviewerKind.SYNTHETIC_FIXTURE,
        context=ws.decision_context())
    assert rec["reviewer_kind"] == "SYNTHETIC_FIXTURE"


def test_agent_findings_change_nothing_until_confirmed(ws, demo_dir, normalizer):
    truth = json.loads((demo_dir / "ground_truth.json").read_text())["programs"]
    by_ext = {a.external_id: a.asset_id for a in ws.assets()}
    target = by_ext[next(k for k, v in truth.items() if v["archetype"] == "missing_target_researchable")]
    provider = OfflineEvidenceProvider(demo_dir / "evidence_library.json", normalizer)
    findings = ws.research(provider, [target], [Question.TARGET])
    assert len(findings) == 1
    finding = findings[0]
    assert finding.proposed_value == "TNFSF15" and finding.source_url.startswith("https://example.org/")
    assert finding.document_date == date(2026, 6, 15) and "targeting TL1A" in finding.evidence_span
    assert finding.limitations
    before = {s["asset_id"]: s["disposition"] for s in ws.screen(normalizer).to_dict()["screens"]}
    assert before[target] == "UNRESOLVED"
    ws.decision_log().record(action=Action.CONFIRM_FINDING, subject_id=finding.finding_id,
                             new_state="CONFIRMED", reviewer_id="analyst-1", rationale="press release",
                             context=ws.decision_context())
    after = {s["asset_id"]: s for s in ws.screen(normalizer).to_dict()["screens"]}
    assert after[target]["disposition"] == "ELIGIBLE"
    fact = next(f for f in after[target]["facts"] if f["fact_type"] == "construct_target_set")
    assert fact["analyst_confirmed"] and fact["supporting_claim_ids"] == [finding.finding_id]


def test_rejecting_a_source_claim_removes_it_from_screening(ws, normalizer):
    asset_id = _by(ws, "ELIGIBLE")[0]
    claim = next(c for a in ws.assets() if a.asset_id == asset_id for c in a.claims_for("target"))
    ws.decision_log().record(action=Action.REJECT_CLAIM, subject_id=claim.claim_id, new_state="REJECTED",
                             reviewer_id="analyst-1", rationale="wrong target", context=ws.decision_context())
    screen = {s["asset_id"]: s for s in ws.screen(normalizer).to_dict()["screens"]}[asset_id]
    assert screen["disposition"] == "UNRESOLVED"


def test_rights_finding_contradiction_is_flagged(ws, demo_dir, normalizer):
    provider = OfflineEvidenceProvider(demo_dir / "evidence_library.json", normalizer)
    findings = ws.research(provider, _by(ws, "ELIGIBLE"), [Question.US_RIGHTS])
    assert len(findings) == 1  # "U.S." must not split the sentence
    assert findings[0].contradicts_claim_ids
    assert any("Contradicts" in limit for limit in findings[0].limitations)


def test_ctgov_provider_reads_only_registered_nct_ids(ws, normalizer):
    asset = ws.assets()[0]
    claim = asset.claims[0].model_copy(update={"claim_id": "t", "field": "trial_ids",
                                               "value_as_written": "NCT01234567; SYNTRIAL-00001"})
    asset = asset.model_copy(update={"claims": [*asset.claims, claim]})
    calls = []

    def fetch(nct):
        calls.append(nct)
        return {"identificationModule": {"nctId": nct, "briefTitle": f"Study of {asset.program_name}"},
                "designModule": {"phases": ["PHASE2"]},
                "armsInterventionsModule": {"interventions": [{"name": asset.program_name, "type": "DRUG"}]},
                "statusModule": {"lastUpdatePostDateStruct": {"date": "2026-05-01"}}}

    findings = ClinicalTrialsGovProvider(normalizer, fetch=fetch).investigate(asset, Question.STAGE)
    assert calls == ["NCT01234567"]
    assert findings and findings[0].proposed_value == "Phase 2"
    assert findings[0].source_url == "https://clinicaltrials.gov/study/NCT01234567"
    assert any("sponsor is not evidence of rights" in limit for limit in findings[0].limitations)


def test_context_rejects_unknown_subjects():
    ctx = DecisionContext(dispositions={}, claim_ids=set(), finding_ids=set(), flag_ids=set())
    with pytest.raises(DecisionRejected, match="unknown agent finding"):
        ctx.check(Action.CONFIRM_FINDING, "finding:nope", ReviewState())
