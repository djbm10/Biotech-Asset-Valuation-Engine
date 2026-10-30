"""Cycle R1: rights-evidence ingestion and transaction classification.

Held-back fixtures: fictional parties and deal phrasings that do not appear in the CLDN18.2 rights file.
They test logic only and assert no real-world facts."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from bve.dealscreen import rights as r
from bve.dealscreen.transaction import TIER_ORDER, TransactionPreferences, assess_transaction

US = frozenset({"US"})
CN = frozenset({"CN"})
_N = iter(range(1, 10_000))


def ev(kind: str, *, grantee: str | None = None, grantor: str | None = "Origin Bio", territory: str | None = None,
       d: str | None = "2025-01-01", excl: str = "EXCLUSIVE", status: str = "UNKNOWN", deal: str | None = None,
       related: str | None = None) -> r.RightsEvent:
    n = next(_N)
    regions = r.parse_territory(territory)
    return r.RightsEvent(
        event_id=f"rx:t:{n}", deal_id=deal or f"D{n}", external_id="P1", event_type=kind, exclusivity=excl,
        grantee=grantee, grantor=grantor, territory_as_written=territory,
        territory=sorted(regions) if regions is not None else None,
        event_date=date.fromisoformat(d) if d else None, status=status, related_deal_id=related,
        source_system="TEST", dataset_version="TEST:x", row_number=n, source_reference=f"https://example.test/{n}",
        evidence_quote=f"quote {n}")


def pos(events, territory=US, as_of=date(2025, 6, 1), max_age=730):
    return r.rights_position(events, territory=territory, originator="Origin Bio", as_of=as_of,
                             max_age_days=max_age)


# -- AC3 territory ---------------------------------------------------------------------------------
@pytest.mark.parametrize(("text", "has_us", "has_cn"), [
    ("Rest of world excluding Japan", True, True),
    ("North America", True, False),
    ("Japan only", False, False),
    ("worldwide", True, True),
    ("all territories except the PRC, Hong Kong and Macau", True, False),
    ("United States and Canada", True, False),
    ("Greater China", False, True),
    ("ex-Greater China", True, False),
])
def test_territory_phrasings(text, has_us, has_cn):
    t = r.parse_territory(text)
    assert t is not None and ("US" in t) == has_us and ("CN" in t) == has_cn


@pytest.mark.parametrize("text", ["", "the Licensed Territory", "rest of world", "certain Asian markets except some"])
def test_unreadable_territory_is_none_never_worldwide(text):
    assert r.parse_territory(text) is None


def test_license_covering_buyer_territory_is_encumbered_with_holder():
    p = pos([ev(r.LICENSE, grantee="Alpha Pharma", territory="Rest of world excluding Japan")])
    assert p.position == r.P_LICENSED and p.holder == "Alpha Pharma" and p.event_ids
    assert p.evidence[0]["quote"] and p.evidence[0]["source"].startswith("https://")


def test_license_elsewhere_is_not_encumbered_and_not_available():
    p = pos([ev(r.LICENSE, grantee="Beta KK", territory="Japan only")])
    assert p.position == r.P_NOT_ENCUMBERED and "not a statement of availability" in p.reasons[0]
    assert pos([ev(r.LICENSE, grantee="Beta KK", territory="Japan only")], territory=frozenset({"JP"})).position \
        == r.P_LICENSED


def test_unstated_territory_is_a_possible_encumbrance_with_question():
    p = pos([ev(r.LICENSE, grantee="Gamma", territory="the Licensed Territory")])
    assert p.position == r.P_UNSTATED and any("Which territories" in q for q in p.questions)


def test_co_development_is_shared():
    p = pos([ev(r.CO_DEVELOPMENT, grantee="Delta Bio", territory="worldwide", excl="UNSTATED")])
    assert p.position == r.P_SHARED and any("consent" in q for q in p.questions)


def test_exclusivity_unstated_asks():
    p = pos([ev(r.LICENSE, grantee="Alpha", territory="North America", excl="UNSTATED")])
    assert any("exclusive" in q for q in p.questions)


# -- AC4 returned rights -----------------------------------------------------------------------------
def test_return_by_same_party_clears_and_is_not_availability():
    p = pos([ev(r.LICENSE, grantee="Alpha Pharma Inc.", territory="worldwide", d="2021-01-01"),
             ev(r.RIGHTS_RETURNED, grantee="Alpha Pharma", d=None)])
    assert p.position == r.P_RETURNED and "not a statement of availability" in p.reasons[0]


def test_later_relicense_re_encumbers():
    p = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide", d="2021-01-01"),
             ev(r.TERMINATION, grantee="Alpha", d="2022-01-01"),
             ev(r.LICENSE, grantee="Epsilon", territory="North America", d="2024-01-01")])
    assert p.position == r.P_LICENSED and p.holder == "Epsilon"


def test_termination_linked_by_deal_id_clears_regardless_of_name():
    p = pos([ev(r.LICENSE, grantee="Old Name Bio", territory="worldwide", deal="DX"),
             ev(r.TERMINATION, grantee="Renamed Corp", related="DX")])
    assert p.position == r.P_RETURNED


def test_return_naming_an_unknown_party_is_conflicting_not_cleared():
    p = pos([ev(r.LICENSE, grantee="Zeta Therapeutics", territory="worldwide"),
             ev(r.RIGHTS_RETURNED, grantee="Big Acquirer", d=None)])
    assert p.position == r.P_CONFLICTING and any("successor" in q for q in p.questions)


def test_recorded_acquisition_of_licensee_links_the_return():
    p = pos([ev(r.LICENSE, grantee="Zeta Therapeutics", territory="worldwide", d="2021-01-01"),
             ev(r.ACQUISITION, grantee="Big Acquirer", grantor="Zeta Therapeutics", d="2022-01-01"),
             ev(r.RIGHTS_RETURNED, grantee="Big Acquirer", d="2023-01-01")])
    assert p.position == r.P_RETURNED


def test_acquirer_inherits_licensee_territory_only():
    p = pos([ev(r.LICENSE, grantee="Small Licensee", territory="excluding China", d="2021-01-01"),
             ev(r.ACQUISITION, grantee="Acquirer Co", grantor="Small Licensee", d="2022-01-01")])
    assert p.position == r.P_LICENSED and p.holder == "Acquirer Co"
    assert pos(p and [ev(r.LICENSE, grantee="Small Licensee", territory="excluding China"),
                      ev(r.ACQUISITION, grantee="Acquirer Co", grantor="Small Licensee")],
               territory=CN).position == r.P_NOT_ENCUMBERED


def test_acquisition_of_originator_is_acquired():
    p = pos([ev(r.ACQUISITION, grantee="Acquirer Co", grantor="Origin Bio", territory=None)])
    assert p.position == r.P_ACQUIRED and p.holder == "Acquirer Co"


# -- AC5 options -------------------------------------------------------------------------------------
def test_option_states():
    opt = ev(r.OPTION, grantee="Eta AG", territory="ex-Greater China", d="2023-01-01")
    p = pos([opt])
    assert p.position == r.P_OPTION and any("exercised" in q for q in p.questions)
    assert pos([opt, ev(r.OPTION_EXERCISED, grantee="Eta AG", d="2024-01-01")]).position == r.P_LICENSED
    assert pos([opt, ev(r.OPTION_LAPSED, grantee="Eta AG", d="2024-01-01")]).position == r.P_RETURNED
    assert pos([ev(r.OPTION, grantee="Eta AG", territory="mainland China")]).position == r.P_NOT_ENCUMBERED


# -- AC6 conflicts -------------------------------------------------------------------------------------
def test_two_exclusive_holders_conflict():
    p = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide"),
             ev(r.LICENSE, grantee="Beta", territory="North America")])
    assert p.position == r.P_CONFLICTING and len(p.event_ids) == 2


def test_availability_plus_active_grant_conflicts():
    p = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide"),
             ev(r.AVAILABILITY_STATED, grantor="Origin Bio", territory="worldwide")])
    assert p.position == r.P_CONFLICTING


# -- AC7 stale -----------------------------------------------------------------------------------------
def test_stale_availability_is_not_counted():
    p = pos([ev(r.AVAILABILITY_STATED, grantor="Origin Bio", territory="worldwide", d="2019-01-01")])
    assert p.stale and p.position == r.P_NONE
    fresh = pos([ev(r.AVAILABILITY_STATED, grantor="Origin Bio", territory="worldwide", d="2025-03-01")])
    assert fresh.position == r.P_AVAILABILITY and not fresh.stale


def test_stale_license_flagged_with_question():
    p = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide", d="2018-01-01")])
    assert p.position == r.P_LICENSED and p.stale and any("current" in q for q in p.questions)


# -- AC2/AC9 tiers ---------------------------------------------------------------------------------------
PREFS = TransactionPreferences(encumbered_rights="deprioritize", returned_rights="prefer")


def view(p, prefs=PREFS, **kw):
    base = {"market_status": None, "rights_status": "UNKNOWN", "rights_holder": None, "company": "Origin Bio",
            "identity_twins": []}
    return assess_transaction(prefs, **(base | kw), position=p)


def test_no_open_tier_exists_and_no_evidence_is_unresolved():
    assert "OPEN" not in TIER_ORDER
    v = view(None)
    assert v.tier == "RIGHTS_UNRESOLVED" and v.position == r.P_NONE and v.questions
    assert "availability not evidenced" in v.reasons


def test_tiers_follow_evidence_and_preferences():
    lic = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide")])
    assert view(lic).tier == "DEPRIORITIZED"
    assert view(lic, TransactionPreferences(encumbered_rights="exclude")).tier == "EXCLUDED_BY_BUYER_PREFERENCE"
    assert view(lic, TransactionPreferences()).tier == "RIGHTS_UNRESOLVED"  # ignored, never promoted
    ret = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide"), ev(r.TERMINATION, grantee="Alpha", d=None)])
    v = view(ret)
    assert v.tier == "NO_OBSTACLE_IN_RIGHTS_EVIDENCE" and v.sort_bonus == 1
    assert "availability not evidenced" in v.reasons
    avail = pos([ev(r.AVAILABILITY_STATED, grantor="Origin Bio", territory="worldwide")])
    assert view(avail).tier == "AVAILABILITY_STATED_UNVERIFIED"


def test_holder_preference_uses_evidence_holder():
    lic = pos([ev(r.LICENSE, grantee="Theta Pharma", territory="worldwide")])
    v = view(lic, TransactionPreferences(deprioritized_holders=["Theta Pharma"]))
    assert v.tier == "DEPRIORITIZED" and "per cited evidence" in v.reasons[0]


# -- AC1 import ------------------------------------------------------------------------------------------
PROFILE = {
    "name": "t", "source_system": "VENDOR_X", "license_status": "licensed", "allowed_use": "internal_only",
    "columns": {"deal_id": "Deal", "external_id": "Drug ID", "event_type": "Type", "grantee": "Licensee",
                "grantor": "Licensor", "territory": "Territory", "event_date": "Date", "status": "Status",
                "source_reference": "URL", "evidence_quote": "Quote"},
    "event_type_map": {"licensing": "LICENSE", "option": "OPTION", "termination": "TERMINATION"},
    "status_map": {"active": "ACTIVE", "terminated": "TERMINATED"},
}


def test_import_keeps_provenance_and_rejects_unknown_labels(tmp_path: Path):
    f = tmp_path / "deals.csv"
    f.write_text("Deal,Drug ID,Type,Licensee,Licensor,Territory,Date,Status,URL,Quote\n"
                 "D1,P1,Licensing,Alpha,Origin,North America,2024-03,Active,https://x.test/1,\"licensed NA\"\n"
                 "D2,P1,Asset swap,Alpha,Origin,,2024-03,,https://x.test/2,q\n"
                 "D3,P1,Licensing,Alpha,Origin,,2024-03,Pending,https://x.test/3,q\n"
                 "D4,P2,Licensing,,,,,,https://x.test/4,q\n", encoding="utf-8")
    out = r.import_rights(f, r.RightsProfile(**PROFILE))
    assert len(out.events) == 1 and len(out.rejected) == 3
    e = out.events[0]
    assert e.source_system == "VENDOR_X" and e.row_number == 1 and e.evidence_quote == "licensed NA"
    assert e.event_date == date(2024, 3, 1) and e.territory == ["CA", "US"] and len(out.source_sha256) == 64
    reasons = " ".join(" ".join(x["reasons"]) for x in out.rejected)
    assert "not guessed" in reasons and "Pending" in reasons and "name a party" in reasons


def test_profile_rejects_unknown_canonical_values():
    with pytest.raises(ValueError):
        r.RightsProfile(**(PROFILE | {"event_type_map": {"licensing": "AVAILABLE"}}))


def test_party_key_keeps_distinct_companies_apart():
    assert r.party_key("Alpha Pharma, Inc.") == r.party_key("Alpha Pharma")
    assert r.party_key("Merck KGaA") != r.party_key("Merck & Co., Inc.")


def test_reasons_not_duplicated_when_deprioritized():
    lic = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide", d="2018-01-01")])
    v = view(lic)
    assert len(v.reasons) == len(set(v.reasons))


def test_workbook_rights_cells_show_evidence_and_questions():
    from bve.dealscreen.workbook import _rights_cells

    p = pos([ev(r.OPTION, grantee="Eta AG", territory="ex-Greater China", d="2024-01-01")])
    v = view(p)
    cells = _rights_cells({"rights_position": v.position, "rights_holder_per_evidence": v.holder,
                           "evidence": v.evidence, "stale": v.stale, "diligence_questions": v.questions})
    assert cells[0] == r.P_OPTION and cells[1] == "Eta AG"
    assert "https://example.test/" in cells[2] and "quote" in cells[2] and "exercised" in cells[4]
    assert _rights_cells({})[2] == "no rights record"
