"""Cycle A5: market status vs Phase 4, and approval statements (AI-SIMULATED analyst findings;
INTERNAL DEVELOPMENT). Criteria: analyst_simulation/PRIORITIZED_FIXES.md (K1, K2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bve.dealscreen.agent import US_MARKETED_VALUE, us_approval_stated
from bve.dealscreen.facts import market_status

REAL = Path(__file__).resolve().parents[2] / "examples" / "dealscreen_real"
TARGETS = {"fcgrt": "FCGRT", "c5": "C5", "fcrn": "FCGRT"}


def normalizer(text: str) -> str | None:
    return TARGETS.get(text.strip().casefold())


@pytest.mark.parametrize("statuses, phases, expected", [
    (["Marketed in U.S. (FDA label lists myasthenia gravis)"], ["Marketed"], "US_MARKETED"),
    (["Active trial in registry"], ["Phase 4"], "PHASE4_STUDY_ONLY"),
    (["Approved in China"], ["Phase 3"], "MARKETED_NO_US_STATEMENT"),
    (["Not approved; Phase 3 ongoing"], ["Phase 3"], None),
    (["Withdrawn from marketed use"], ["Phase 4"], "PHASE4_STUDY_ONLY"),
    ([US_MARKETED_VALUE], ["Phase 4"], "US_MARKETED"),
    ([], [], None),
])
def test_k1_market_status(statuses, phases, expected):
    assert market_status(statuses, phases) == expected


NAMES = ["Rozanolixizumab", "UCB7665"]


@pytest.mark.parametrize("sentence, expected", [
    ("RYSTIGGO (rozanolixizumab-noli) has been approved by the U.S. Food and Drug Administration (FDA)", True),
    ("The FDA approved rozanolixizumab for gMG.", True),
    ("Following FDA approval of eculizumab, rozanolixizumab entered Phase 3", False),
    ("Eculizumab was approved by the FDA in 2017, while rozanolixizumab is in Phase 3", False),
    ("The rozanolixizumab BLA has been accepted for review by the U.S. FDA", False),
    ("Rozanolixizumab was submitted to the FDA; if approved it would be the second", False),
    ("Rozanolixizumab is not approved by the FDA", False),
    ("Rozanolixizumab was approved by the European Commission", False),
])
def test_k2_us_approval_statement(sentence, expected):
    assert us_approval_stated(sentence, NAMES) is expected


@pytest.fixture
def ws(tmp_path, monkeypatch):
    from bve.dealscreen.workspace import Workspace
    from bve.se.ontology.targets import reset_resolver_cache

    monkeypatch.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(tmp_path / "absent"))
    reset_resolver_cache()
    w = Workspace(tmp_path / "ws")
    w.import_landscape(REAL / "landscape_fcrn_gmg_v2.csv", REAL / "profile_public_landscape_v2.yaml",
                       REAL / "buyer_fcrn_gmg.yaml")
    w.screen(normalizer)
    yield w
    reset_resolver_cache()


def test_k1_real_rozanolixizumab_is_a_phase4_study_not_marketed_until_evidenced(ws):
    from bve.dealscreen.memo import stage_label

    ext = {a.asset_id: a.external_id for a in ws.assets()}
    s = {ext[x["asset_id"]]: x for x in ws.screening()["screens"]}
    assert s["RW-03"]["market_status"] == "PHASE4_STUDY_ONLY"
    assert stage_label(s["RW-03"]) == "Phase 4 study (approval jurisdiction not stated)"
    assert s["RW-04"]["market_status"] == "US_MARKETED"


def test_k2_real_library_proposes_only_rozanolixizumab(ws):
    from bve.dealscreen.agent import OfflineEvidenceProvider, Question

    provider = OfflineEvidenceProvider(REAL / "evidence_library_public.json", normalizer)
    ids = [a.asset_id for a in ws.assets()]
    found = [f for f in ws.research(provider, ids, [Question.STAGE]) if f.field == "development_status"]
    ext = {a.asset_id: a.external_id for a in ws.assets()}
    assert {ext[f.asset_id] for f in found} == {"RW-03"}
    assert all(f.proposed_value == US_MARKETED_VALUE for f in found)


def test_k1_market_status_changes_no_gate_or_rank(ws):
    from bve.dealscreen import facts as facts_module

    before = ws.screening()
    original = facts_module.market_status
    try:
        facts_module.market_status = lambda *_a, **_k: None  # type: ignore[assignment]
        after = ws.screen(normalizer).to_dict()
    finally:
        facts_module.market_status = original
    strip = lambda d: [{k: v for k, v in x.items() if k != "market_status"} for x in d["screens"]]
    assert strip(before) == strip(after)


# -- regressions from the A5 code review (AI reviewer) ---------------------------------
@pytest.mark.parametrize("text, expected", [
    ("US-based company; approved in EU", "MARKETED_NO_US_STATEMENT"),
    ("FDA granted orphan designation; marketed in Japan", "MARKETED_NO_US_STATEMENT"),
    ("approved for IND by FDA", None),
    ("Marketed ex-US", "MARKETED_NO_US_STATEMENT"),
    ("let us know; approved", "MARKETED_NO_US_STATEMENT"),
    ("not marketed in US, approved in EU", "MARKETED_NO_US_STATEMENT"),
    ("IRB approved protocol", None),
    ("has not yet been approved", None),
])
def test_review_a5_1_market_status_clause_scoped(text, expected):
    assert market_status([text], []) == expected


@pytest.mark.parametrize("sentence, expected", [
    ("RYSTIGGO received FDA approval", True),
    ("U.S. approval of RYSTIGGO", True),
    ("RYSTIGGO is approved in the U.S.", True),
    ("RYSTIGGO was approved by the EMA and FDA", True),
    ("FDA approved RYSTIGGO for adults; sBLA would extend to pediatrics", True),
    ("FDA approval for RYSTIGGO is expected", False),
    ("FDA approved a supplemental indication of RYSTIGGO", False),
    ("RYSTIGGO is used with drug X, approved by the FDA", False),
])
def test_review_a5_3_approval_phrasings(sentence, expected):
    assert us_approval_stated(sentence, ["RYSTIGGO"]) is expected


def test_review_a5_5_confirmed_us_approval_sets_marketed_activity():
    from bve.dealscreen.facts import activity_status

    assert activity_status(US_MARKETED_VALUE) == "MARKETED"  # disclosed rank consequence


def test_review_a5_6_stage6_without_evidence_label():
    from bve.dealscreen.memo import stage_label

    assert stage_label({"stage_order": 6, "market_status": None}) == \
        "Phase 4 or marketed (no market evidence in source)"
