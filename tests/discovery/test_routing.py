"""Tests for bve-discover routing (slice 2) — conservative confidence routing."""
from __future__ import annotations

from tests.discovery.conftest import make_protocol

from bve.discovery.program_cluster import cluster_programs
from bve.discovery.lead_ranker import rank_leads
from bve.discovery.routing import (
    ACTION_AUTO_ADD,
    ACTION_EXCEPTION,
    ACTION_PROPOSE,
    ACTION_REVIEW,
    ACTION_SKIP_EXISTS,
    DISPOSITION_APPROVED_AMBIGUOUS,
    CandidateCompany,
    approved_alternative,
    route_company,
    run_routing,
)
from bve.discovery.sponsor_trials import parse_protocol


def _trials(company, protos):
    return [parse_protocol(p, company) for p in protos]


def _route(company, protos, *, ticker="AAA", existing=None, auto_add=False):
    progs = cluster_programs(_trials(company, protos))
    lead = rank_leads(progs)
    cand = CandidateCompany(ticker=ticker, company_name=company)
    return route_company(cand, progs, lead, existing_tickers=existing, auto_add_high=auto_add)


# ── Confidence tiers → actions ───────────────────────────────────────────────────

def _high_single(company="Acme Bio"):
    # One late-stage program where the company is lead sponsor → high tier.
    return [make_protocol(nct_id="N1", drug="ABC-100", phases=["PHASE3"],
                          enrollment=400, status="RECRUITING", lead_sponsor=company,
                          conditions=["Breast Cancer"])]


def test_high_confidence_proposes_by_default():
    d = _route("Acme Bio", _high_single())
    assert d.tier == "high"
    assert d.action == ACTION_PROPOSE  # default: propose, not auto-add


def test_high_confidence_auto_adds_only_with_flag():
    d = _route("Acme Bio", _high_single(), auto_add=True)
    assert d.action == ACTION_AUTO_ADD


def test_medium_confidence_routes_to_review():
    # Two Phase 2 programs separated only by corroboration → medium margin.
    company = "Beta Bio"
    protos = [
        make_protocol(nct_id="N1", drug="BET-100", phases=["PHASE2"], enrollment=50,
                      status="RECRUITING", lead_sponsor=company),
        make_protocol(nct_id="N2", drug="BET-100", phases=["PHASE2"], enrollment=50,
                      status="RECRUITING", lead_sponsor=company),
        make_protocol(nct_id="N3", drug="BET-100", phases=["PHASE2"], enrollment=50,
                      status="RECRUITING", lead_sponsor=company),
        make_protocol(nct_id="N4", drug="BET-200", phases=["PHASE2"], enrollment=50,
                      status="RECRUITING", lead_sponsor=company),
    ]
    d = _route(company, protos)
    assert d.tier == "medium"
    assert d.action == ACTION_REVIEW


def test_low_confidence_is_exception():
    # Two indistinguishable Phase 2 programs → zero margin → low.
    company = "Gamma Bio"
    protos = [
        make_protocol(nct_id="N1", drug="GAM-100", phases=["PHASE2"], enrollment=50,
                      status="RECRUITING", lead_sponsor=company),
        make_protocol(nct_id="N2", drug="GAM-200", phases=["PHASE2"], enrollment=50,
                      status="RECRUITING", lead_sponsor=company),
    ]
    d = _route(company, protos)
    assert d.tier == "low"
    assert d.action == ACTION_EXCEPTION


def test_no_lead_is_exception():
    d = _route("Empty Bio", [])
    assert d.action == ACTION_EXCEPTION
    assert d.drug is None


def test_already_seeded_high_is_skipped():
    d = _route("Acme Bio", _high_single(), ticker="AAA", existing={"AAA"})
    assert d.already_seeded is True
    assert d.action == ACTION_SKIP_EXISTS


# ── The MRUS rule: approved-vs-active-pivotal is never auto-added ─────────────────

def _mrus_like(company="Merus"):
    return [
        # Active Phase 3 flagship (the ranker's pick).
        make_protocol(nct_id="P1", drug="Petosemtamab", phases=["PHASE3"],
                      enrollment=600, status="RECRUITING", lead_sponsor=company,
                      conditions=["Head and Neck Cancer"]),
        make_protocol(nct_id="P2", drug="Petosemtamab", phases=["PHASE3"],
                      enrollment=700, status="RECRUITING", lead_sponsor=company,
                      conditions=["Head and Neck Cancer"]),
        # A different, already-approved asset.
        make_protocol(nct_id="Z1", drug="Zenocutuzumab", phases=["PHASE2"],
                      enrollment=105, status="COMPLETED", lead_sponsor=company,
                      conditions=["NRG1 Fusion Cancer"]),
        make_protocol(nct_id="Z2", drug="Zenocutuzumab", status="APPROVED_FOR_MARKETING",
                      lead_sponsor=company, conditions=["NRG1 Fusion Cancer"]),
    ]


def test_mrus_picks_active_pivotal_but_routes_to_review():
    d = _route("Merus", _mrus_like(), ticker="MRUS")
    assert d.drug == "Petosemtamab"            # ranker still picks the active Ph3
    assert d.disposition == DISPOSITION_APPROVED_AMBIGUOUS
    assert d.action == ACTION_REVIEW
    assert d.approved_alternative == "Zenocutuzumab"


def test_mrus_not_auto_added_even_with_flag():
    # The hard guarantee: an approved alternative blocks auto-add unconditionally.
    d = _route("Merus", _mrus_like(), ticker="MRUS", auto_add=True)
    assert d.action == ACTION_REVIEW
    assert d.action != ACTION_AUTO_ADD


def test_approved_alternative_none_when_pick_is_the_approved_asset():
    # If the lead itself is the approved asset, there is no ambiguity.
    company = "Solo Bio"
    protos = [make_protocol(nct_id="A1", drug="ONLY-1", status="APPROVED_FOR_MARKETING",
                            phases=["PHASE3"], enrollment=400, lead_sponsor=company)]
    progs = cluster_programs(_trials(company, protos))
    lead = rank_leads(progs)
    assert approved_alternative(progs, lead) is None


# ── Aggregation + artifacts ──────────────────────────────────────────────────────

def _fetch_from(mapping):
    def fetch(company):
        return _trials(company, mapping.get(company, []))
    return fetch


def test_run_routing_aggregates_and_excludes_ambiguous_from_proposals():
    candidates = [
        CandidateCompany(ticker="AAA", company_name="Acme Bio"),
        CandidateCompany(ticker="MRUS", company_name="Merus"),
        CandidateCompany(ticker="EMP", company_name="Empty Bio"),
    ]
    fetch = _fetch_from({"Acme Bio": _high_single("Acme Bio"), "Merus": _mrus_like("Merus")})
    result = run_routing(candidates, fetch_fn=fetch)

    actions = {d.ticker: d.action for d in result.decisions}
    assert actions == {"AAA": ACTION_PROPOSE, "MRUS": ACTION_REVIEW, "EMP": ACTION_EXCEPTION}
    # Only the clean high-confidence lead is a proposal; MRUS is never proposed.
    assert [d.ticker for d in result.proposals] == ["AAA"]
    assert result.auto_added == []


def test_ta_inference_uses_loader_vocabulary():
    from bve.discovery.routing import _infer_ta

    # Each maps to an assumptions-loader TA key (not a non-canonical synonym).
    cases = {
        "Stargardt Disease 1": "ophthalmology",
        "IgA Nephropathy": "renal",
        "Focal Segmental Glomerulosclerosis": "renal",
        "Prader-Willi Syndrome": "rare_disease",
        "Major Depressive Disorder": "psychiatry",
        "Facioscapulohumeral Muscular Dystrophy": "cns",
        "Hypertension": "cardiovascular",
        "Glioma": "oncology",
    }
    for indication, expected in cases.items():
        assert _infer_ta(indication) == expected, indication

    # Unmapped indications stay honest.
    assert _infer_ta("Some Bespoke Condition") == "unknown"


def test_device_company_routed_to_exception():
    from bve.discovery.routing import ACTION_EXCEPTION, DISPOSITION_NOT_DEVELOPER

    # Even with a clean-looking lead, a device/dx company is not a developer.
    protos = _high_single("Intuitive Surgical")
    progs = cluster_programs(_trials("Intuitive Surgical", protos))
    lead = rank_leads(progs)
    d = route_company(
        CandidateCompany(ticker="ISRG", company_name="Intuitive Surgical"),
        progs, lead,
    )
    assert d.action == ACTION_EXCEPTION
    assert d.disposition == DISPOSITION_NOT_DEVELOPER


def test_collaborator_only_lead_routes_to_review():
    from bve.discovery.routing import ACTION_REVIEW, DISPOSITION_UNCONFIRMED_ORIGINATOR

    # Company is NOT the lead sponsor → possible partner/comparator asset.
    protos = [make_protocol(nct_id="N1", drug="ABC-100", phases=["PHASE3"],
                            enrollment=400, status="RECRUITING",
                            lead_sponsor="Some Other Pharma")]
    progs = cluster_programs(_trials("Acme Bio", protos))
    lead = rank_leads(progs)
    d = route_company(CandidateCompany(ticker="ACME", company_name="Acme Bio"),
                      progs, lead)
    assert d.action == ACTION_REVIEW
    assert d.disposition == DISPOSITION_UNCONFIRMED_ORIGINATOR


def test_excluded_ticker_short_circuits_without_fetch():
    from bve.discovery.routing import ACTION_EXCLUDED

    calls = {"n": 0}

    def fetch(company):
        calls["n"] += 1
        return _trials(company, _high_single(company))

    candidates = [CandidateCompany(ticker="ZYME", company_name="Zymeworks")]
    result = run_routing(candidates, fetch_fn=fetch, excluded_tickers={"ZYME"})
    assert result.decisions[0].action == ACTION_EXCLUDED
    assert calls["n"] == 0  # no CT.gov fetch for an excluded name


def test_proposals_doc_shape_and_provenance():
    candidates = [CandidateCompany(ticker="AAA", company_name="Acme Bio")]
    fetch = _fetch_from({"Acme Bio": _high_single("Acme Bio")})
    doc = run_routing(candidates, fetch_fn=fetch, auto_add_high=True).proposals_doc()
    assert len(doc["auto_added"]) == 1
    entry = doc["auto_added"][0]
    assert entry["ticker"] == "AAA"
    assert entry["drug_name"] == "ABC-100"
    assert entry["stage"] == "phase_3"
    assert entry["_meta"]["source"] == "bve-discover"
    assert entry["_meta"]["auto_added"] is True


def test_seed_entry_skips_healthy_and_picks_disease_indication():
    company = "Health Bio"
    protos = [make_protocol(nct_id="H1", drug="HB-1", phases=["PHASE3"], enrollment=400,
                            status="RECRUITING", lead_sponsor=company,
                            conditions=["Healthy Volunteers", "Atopic Dermatitis"])]
    d = _route(company, protos)
    assert d.indication == "Atopic Dermatitis"
    assert d.therapeutic_area == "immunology"
    assert d.nct_id == "H1"


def test_audit_text_lists_every_decision():
    candidates = [
        CandidateCompany(ticker="AAA", company_name="Acme Bio"),
        CandidateCompany(ticker="MRUS", company_name="Merus"),
    ]
    fetch = _fetch_from({"Acme Bio": _high_single("Acme Bio"), "Merus": _mrus_like("Merus")})
    text = run_routing(candidates, fetch_fn=fetch).to_audit_text()
    assert "routing audit" in text
    assert "AAA" in text and "MRUS" in text
    assert "approved alternative" in text


def test_decision_is_frozen():
    d = _route("Acme Bio", _high_single())
    try:
        d.action = "mutated"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("RouteDecision must be immutable")
