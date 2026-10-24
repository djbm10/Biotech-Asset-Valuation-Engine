"""Development-code retrieval safety, not validation of global alias identity."""

from __future__ import annotations

import pytest

from bve.se.acquisition.asset_history import (
    company_naming_leads,
    investigate_history,
    query_term,
    registry_naming_leads,
)


def study(nct="NCT00000001", name="examplemab", others=None, **status):
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct},
            "armsInterventionsModule": {
                "interventions": [
                    {
                        "name": name,
                        "type": "DRUG",
                        "otherNames": others or [],
                    }
                ]
            },
            "statusModule": {
                "overallStatus": "TERMINATED",
                "whyStopped": "Sponsor decision",
                **status,
            },
            "designModule": {
                "phases": ["PHASE1", "PHASE2"],
                "enrollmentInfo": {"count": 40, "type": "ACTUAL"},
            },
            "conditionsModule": {"conditions": ["Cancer"]},
        }
    }


def response(*studies):
    return {"studies": list(studies), "totalCount": len(studies)}


def test_generic_chain_recovers_terminated_history_without_seeding_old_code():
    calls = []

    def fetch(params):
        term = params["query.intr"].strip('"')
        calls.append(term)
        if term == "OLD-42":
            return response(study("NCT00000002", "OLD-42"))
        return response(study(others=["NEW101"]))

    docs = [
        {
            "url": "https://example.org/release",
            "text": "Our drug OLD-42 (NEW101) is in development.",
        }
    ]
    result = investigate_history("examplemab", docs, fetch=fetch)
    assert calls == ["examplemab", "NEW101", "OLD-42"]
    assert len(result["trials"]) == 2
    old = result["trials"][1]
    assert old["status"] == "TERMINATED" and old["enrollment"] == {"count": 40, "type": "ACTUAL"}
    assert old["why_stopped"] == "Sponsor decision" and old["conditions"] == ["Cancer"]
    assert old["attribution"] == "REQUIRES_IDENTITY_REVIEW"
    assert result["identity_merges"] == [] and result["asset_history_completeness"] == "UNKNOWN"
    assert all(l["source_sha256"] and l["pointer"] for l in result["naming_leads"])
    assert result == investigate_history("examplemab", docs, fetch=fetch)


def test_no_cointervention_or_multiple_alias_merge():
    raw = study(others=["AAA101", "BBB202"])
    raw["protocolSection"]["armsInterventionsModule"]["interventions"].append(
        {"type": "DRUG", "name": "OTHER303", "otherNames": []}
    )
    assert all(l.status == "REVIEW_REQUIRED" for l in registry_naming_leads(raw))
    result = investigate_history("examplemab", [], fetch=lambda p: response(raw))
    assert len(result["queries"]) == 1 and result["identity_merges"] == []


@pytest.mark.parametrize(
    "text",
    [
        "AAA101 and BBB202 are separate drugs.",
        "AAA101 is combined with BBB202.",
        "AAA101 is not BBB202.",
        "AAA101 (BBB202) is a combination regimen.",
        "AAA101 (BBB202) are distinct products.",
    ],
)
def test_negative_company_context_never_drives_expansion(text):
    leads = company_naming_leads(text, "https://example.org/primary")
    assert not any(l.status == "RETRIEVAL_LEAD_NOT_IDENTITY" for l in leads)


def test_explicit_former_code_and_exact_offsets():
    text = "examplemab, formerly OLD-99, is an investigational antibody."
    lead = company_naming_leads(text, "https://example.org/primary")[0]
    assert (lead.left, lead.right) == ("examplemab", "OLD-99")
    assert lead.passage in text and lead.pointer.startswith("text[")


def test_known_collision_is_quarantined_not_merged():
    result = investigate_history(
        "examplemab",
        [],
        fetch=lambda p: response(study(others=["SHR101"])),
        known_claimants={"SHR101": ["examplemab", "othermab"]},
    )
    assert len(result["queries"]) == 1
    assert result["blocked_terms"][0]["other_claimants"] == ["othermab"]
    assert not result["identity_merges"]


@pytest.mark.parametrize(
    "payload", [{}, {"totalCount": 2}, {"totalCount": -1}, {"studies": [{}], "totalCount": 1}]
)
def test_malformed_is_failure_not_zero(payload):
    assert query_term("examplemab", lambda p: payload)["status"] == "FAILED"


def test_failed_request_never_becomes_complete_zero():
    def fail(params):
        raise TimeoutError()

    result = query_term("examplemab", fail)
    assert result["status"] == "FAILED" and result["total_count"] is None
    assert query_term("examplemab", lambda p: {"totalCount": 0})["status"] == "QUERY_PAGES_COMPLETE"


def test_pagination_is_bounded_and_not_asset_completeness():
    calls = []

    def fetch(params):
        calls.append(params)
        return {
            "studies": [study(f"NCT0000000{len(calls)}")],
            "totalCount": 3,
            "nextPageToken": str(len(calls)),
        }

    result = query_term("examplemab", fetch)
    assert len(calls) == 2 and result["status"] == "TRUNCATED"
    assert calls[1]["pageToken"] == "1"


def test_count_mismatch_and_conflicting_duplicate_fail_closed():
    assert (
        query_term("examplemab", lambda p: {"totalCount": 2, "studies": [study()]})["status"]
        == "COUNT_MISMATCH"
    )
    raw = study()
    altered = study(overallStatus="RECRUITING")
    assert (
        query_term("examplemab", lambda p: {"totalCount": 1, "studies": [raw, altered]})["status"]
        == "FAILED"
    )


@pytest.mark.parametrize(
    "term", ['x" OR placebo', "example mab", "foo*", "placebo", "x/y", "abc\n"]
)
def test_query_injection_and_generic_names_rejected(term):
    with pytest.raises(ValueError):
        query_term(term)


def test_partial_name_hit_is_retained_but_unattributed():
    result = investigate_history("AAA101", [], fetch=lambda p: response(study(name="AAA101-B")))
    assert result["trials"][0]["attribution"] == "UNATTRIBUTED_QUERY_HIT"


def test_cycle_stops_and_budgets_hold():
    result = investigate_history(
        "AAA101", [], fetch=lambda p: response(study(name="AAA101", others=["BBB202"]))
    )
    assert len(result["queries"]) == 2
    docs = [{"url": "https://example.org", "text": f"AAA101 (CODE{i})"} for i in range(100, 110)]
    result = investigate_history("AAA101", docs, fetch=lambda p: response())
    assert len(result["queries"]) <= 6 and result["blocked_terms"]


def test_conflicting_snapshots_not_presented_as_attributed_history():
    def fetch(params):
        return response(
            study(
                others=["BBB202"],
                overallStatus=(
                    "RECRUITING" if params["query.intr"] == '"examplemab"' else "TERMINATED"
                ),
            )
        )

    result = investigate_history("examplemab", [], fetch=fetch)
    assert result["trials"][0]["attribution"] == "CONFLICTING_SNAPSHOTS"


@pytest.mark.parametrize("bad_names", [None, "ABC101", [None]])
def test_malformed_related_names_cannot_crash_or_bootstrap(bad_names):
    raw = study()
    raw["protocolSection"]["armsInterventionsModule"]["interventions"][0]["otherNames"] = bad_names
    result = investigate_history("examplemab", [], fetch=lambda p: response(raw))
    assert result["queries"][0]["status"] == "FAILED"
    assert result["trials"] == [] and len(result["queries"]) == 1
