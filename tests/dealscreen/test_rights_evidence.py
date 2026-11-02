"""Cycle R1: rights-evidence ingestion and transaction classification.

Held-back fixtures: fictional parties and deal phrasings that do not appear in the CLDN18.2 rights file.
They test logic only and assert no real-world facts. Cases tagged T*, L* and P* are the failing inputs
from the R1 adversarial review (research/dealscreen_rights_v1/REVIEW.md, section 3)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from bve.dealscreen import rights as r
from bve.dealscreen import rights_position as rp
from bve.dealscreen.rights_territory import REGIONS, name_matches, parse_territory, party_key
from bve.dealscreen.transaction import (
    TIER_ORDER,
    TransactionPreferences,
    assess_transaction,
    holder_ambiguities,
)

US = frozenset({"US"})
CN = frozenset({"CN"})
_N = iter(range(1, 10_000))


def ev(kind: str, *, grantee: str | None = None, grantor: str | None = "Origin Bio", territory: str | None = None,
       d: str | None = "2025-01-01", excl: str = "EXCLUSIVE", status: str = "UNKNOWN", deal: str | None = None,
       related: str | None = None, src: str | None = None) -> r.RightsEvent:
    """``d`` / ``src`` as written: "2024" is a year, "2024-05" a month, "2024-05-02" a day."""
    n = next(_N)
    regions = parse_territory(territory)
    when, precision = r.parse_date(d) if d else (None, "day")
    source, source_precision = r.parse_date(src) if src else (None, "day")
    return r.RightsEvent(
        event_id=f"rx:t:{n}", deal_id=deal or f"D{n}", external_id="P1", event_type=kind, exclusivity=excl,
        grantee=grantee, grantor=grantor, territory_as_written=territory,
        territory=sorted(regions) if regions is not None else None,
        event_date=when, event_date_precision=precision, status=status, related_deal_id=related,
        source_system="TEST", dataset_version="TEST:x", row_number=n, source_reference=f"https://example.test/{n}",
        evidence_quote=f"quote {n}", source_date=source, source_date_precision=source_precision)


def pos(events, territory=US, as_of=date(2025, 6, 1), max_age=730, company: str | None = "Origin Bio"):
    """``company``: the landscape company (revision 5: a clear position must rest on it)."""
    return rp.rights_position(events, territory=territory, as_of=as_of, max_age_days=max_age, first_contact=company)


def ALL(*minus: str) -> set[str]:
    return set(REGIONS) - set(minus)


# -- AC3 territory -----------------------------------------------------------------------------------
@pytest.mark.parametrize(("text", "expected"), [
    ("Rest of world excluding Japan", ALL("JP")),
    ("North America", {"US", "CA"}),
    ("Japan only", {"JP"}),
    ("worldwide", ALL()),
    ("all territories except the PRC, Hong Kong and Macau", ALL("CN", "HK", "MO")),
    ("United States and Canada", {"US", "CA"}),
    ("Greater China", {"CN", "HK", "MO", "TW"}),
    ("ex-Greater China", ALL("CN", "HK", "MO", "TW")),
    ("territories outside China", ALL("CN")),
    ("worldwide ex-US", ALL("US")),
    ("excluding the US and EU", ALL("US", "EU")),
    # review T3, T6, T8: an exclusion subtracts from its own base, never from the world
    ("worldwide, including the US but excluding China", ALL("CN")),
    ("Europe and Japan, excluding the UK", {"EU", "JP"}),
    ("United States (excluding its territories)", {"US"}),
    ("EU5", {"EU", "UK"}),
    ("European Union", {"EU"}),
    ("U.S.", {"US"}),
])
def test_territory_phrasings(text, expected):
    assert parse_territory(text) == frozenset(expected)


@pytest.mark.parametrize("text", [
    "", "the Licensed Territory", "rest of world", "ROW", "certain Asian markets except some",
    # review T1, T2, T4, T5, T7: unknown places or qualifiers make the text unreadable, never "not covered"
    "North America excluding Mexico", "US, excluding Puerto Rico",
    "Worldwide other than Japan; US co-promotion retained by licensor", "Asia ex-Japan",
    "rights for use by us in China", "Americas", "Asia-Pacific", "global except where held by partner",
    "co-exclusive worldwide", "Mexico",
])
def test_unreadable_territory_is_none(text):
    assert parse_territory(text) is None


def test_unreadable_territory_is_a_possible_encumbrance_not_no_obstacle():
    for text in ("North America excluding Mexico", "US, excluding Puerto Rico"):
        p = pos([ev(r.LICENSE, grantee="Alpha", territory=text)])
        assert p.position == rp.P_UNSTATED and any("Which territories" in q for q in p.questions)


def test_license_covering_buyer_territory_is_encumbered_with_holder():
    p = pos([ev(r.LICENSE, grantee="Alpha Pharma", territory="Rest of world excluding Japan")])
    assert p.position == rp.P_LICENSED and p.holder == "Alpha Pharma" and p.owner == "Origin Bio"
    assert p.evidence[0]["quote"] and str(p.evidence[0]["source"]).startswith("https://")


def test_license_elsewhere_is_not_encumbered_and_not_available():
    p = pos([ev(r.LICENSE, grantee="Beta KK", territory="Japan only")])
    assert p.position == rp.P_NOT_ENCUMBERED and "not a statement of availability" in p.reasons[0]
    assert pos([ev(r.LICENSE, grantee="Beta KK", territory="Japan only")], territory=frozenset({"JP"})).position \
        == rp.P_LICENSED


def test_co_development_names_both_partners():
    p = pos([ev(r.CO_DEVELOPMENT, grantee="Delta Bio", grantor="Lead Bio", territory="worldwide", excl="UNSTATED")])
    assert p.position == rp.P_SHARED and set(p.holders) == {"Delta Bio", "Lead Bio"}
    assert any("both" in q for q in p.questions)


def test_non_exclusive_license_is_shared_not_exclusive():
    p = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide", excl="NON_EXCLUSIVE")])
    assert p.position == rp.P_SHARED


def test_exclusivity_unstated_asks():
    p = pos([ev(r.LICENSE, grantee="Alpha", territory="North America", excl="UNSTATED")])
    assert any("exclusive" in q for q in p.questions)


# -- AC4 returned rights ---------------------------------------------------------------------------------
def test_return_by_same_party_clears_and_is_not_availability():
    p = pos([ev(r.LICENSE, grantee="Alpha Pharma Inc.", territory="worldwide", d="2021-01-01"),
             ev(r.RIGHTS_RETURNED, grantee="Alpha Pharma", d=None)])
    assert p.position == rp.P_RETURNED and "not a statement of availability" in p.reasons[0]
    assert p.holder == "Origin Bio"


def test_later_relicense_re_encumbers():
    p = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide", d="2021-01-01"),
             ev(r.TERMINATION, grantee="Alpha", d="2022-01-01"),
             ev(r.LICENSE, grantee="Epsilon", territory="North America", d="2024-01-01")])
    assert p.position == rp.P_LICENSED and p.holder == "Epsilon"


def test_l1_undated_termination_cannot_clear_two_grants_to_the_same_party():
    p = pos([ev(r.LICENSE, grantee="A", territory="worldwide", d="2020-01-01"),
             ev(r.TERMINATION, grantee="A", d=None),
             ev(r.LICENSE, grantee="A", territory="worldwide", d="2025-01-01")])
    assert p.position == rp.P_LICENSED and any("Which of the grants" in q for q in p.questions)


def test_l2_partial_territory_termination_keeps_the_rest():
    p = pos([ev(r.LICENSE, grantee="A", territory="worldwide", d="2022-01-01"),
             ev(r.TERMINATION, grantee="A", territory="Japan", d="2024-01-01")])
    assert p.position == rp.P_LICENSED
    us_return = pos([ev(r.LICENSE, grantee="A", territory="worldwide", d="2022-01-01"),
                     ev(r.RIGHTS_RETURNED, grantee="A", territory="United States", d="2024-01-01")])
    assert us_return.position == rp.P_RETURNED


def test_termination_linked_by_deal_id_clears_regardless_of_name():
    p = pos([ev(r.LICENSE, grantee="Old Name Bio", territory="worldwide", deal="DX"),
             ev(r.TERMINATION, grantee="Renamed Corp", related="DX")])
    assert p.position == rp.P_RETURNED


def test_return_naming_an_unknown_party_is_conflicting_not_cleared():
    p = pos([ev(r.LICENSE, grantee="Zeta Therapeutics", territory="worldwide"),
             ev(r.RIGHTS_RETURNED, grantee="Big Acquirer", d=None)])
    assert p.position == rp.P_CONFLICTING and any("successor" in q for q in p.questions)


def test_l7_termination_naming_only_the_licensor_clears_its_single_grant():
    p = pos([ev(r.LICENSE, grantee="A", territory="worldwide", d="2024-01-01"),
             ev(r.TERMINATION, grantee=None, grantor="Origin Bio", d="2025-01-01")])
    assert p.position == rp.P_RETURNED


def test_recorded_acquisition_of_licensee_links_the_return():
    p = pos([ev(r.LICENSE, grantee="Zeta Therapeutics", territory="worldwide", d="2021-01-01"),
             ev(r.ACQUISITION, grantee="Big Acquirer", grantor="Zeta Therapeutics", d="2022-01-01"),
             ev(r.RIGHTS_RETURNED, grantee="Big Acquirer", d="2023-01-01")])
    assert p.position == rp.P_RETURNED


def test_acquirer_inherits_licensee_territory_only():
    events = [ev(r.LICENSE, grantee="Small Licensee", territory="excluding China", d="2021-01-01"),
              ev(r.ACQUISITION, grantee="Acquirer Co", grantor="Small Licensee", d="2022-01-01")]
    p = pos(events)
    assert p.position == rp.P_LICENSED and p.holder == "Acquirer Co"
    assert any("acquired by Acquirer Co" in x for x in p.reasons)
    assert pos(events, territory=CN).position == rp.P_NOT_ENCUMBERED


def test_l4_undated_acquisition_of_china_only_licensee_does_not_encumber_us():
    p = pos([ev(r.LICENSE, grantee="ChinaCo", territory="Greater China", d="2024-01-01"),
             ev(r.ACQUISITION, grantee="BigCo", grantor="ChinaCo", d=None)])
    assert p.position == rp.P_NOT_ENCUMBERED


def test_acquisition_of_the_owner_changes_the_owner_and_is_not_a_third_party_grant():
    p = pos([ev(r.ACQUISITION, grantee="Acquirer Co", grantor="Origin Bio", territory=None)])
    assert p.position == rp.P_OWNER_ACQUIRED and p.holder == "Acquirer Co"


def test_l5_acquisition_of_the_licensor_keeps_the_license():
    p = pos([ev(r.LICENSE, grantee="A", territory="worldwide outside Greater China", d="2024-01-01"),
             ev(r.ACQUISITION, grantee="BigCo", grantor="Origin Bio", d="2025-01-01")])
    assert p.position == rp.P_LICENSED and p.holder == "A" and p.owner == "BigCo"


def test_returned_then_licensor_acquired_names_the_new_owner():
    p = pos([ev(r.LICENSE, grantee="A", territory="worldwide", d="2022-01-01"),
             ev(r.RIGHTS_RETURNED, grantee="A", d="2024-01-01"),
             ev(r.ACQUISITION, grantee="BigCo", grantor="Origin Bio", d="2025-01-01")])
    assert p.position == rp.P_RETURNED and p.holder == "BigCo"


def test_l6_sublicense_is_not_a_competing_grant():
    p = pos([ev(r.LICENSE, grantee="A", territory="worldwide", d="2022-01-01"),
             ev(r.LICENSE, grantee="B", grantor="A", territory="United States", d="2024-01-01")])
    assert p.position == rp.P_LICENSED and p.holder == "B" and any("sublicense" in x for x in p.reasons)


# -- AC5 options -------------------------------------------------------------------------------------------
def test_option_states():
    opt = ev(r.OPTION, grantee="Eta AG", territory="ex-Greater China", d="2023-01-01")
    p = pos([opt])
    assert p.position == rp.P_OPTION and any("exercised" in q for q in p.questions)
    assert pos([opt, ev(r.OPTION_EXERCISED, grantee="Eta AG", d="2024-01-01")]).position == rp.P_LICENSED
    lapsed = pos([opt, ev(r.OPTION_LAPSED, grantee="Eta AG", d="2024-01-01")])
    assert lapsed.position == rp.P_NOT_ENCUMBERED and "lapsed" in lapsed.reasons[0]
    assert pos([ev(r.OPTION, grantee="Eta AG", territory="mainland China")]).position == rp.P_NOT_ENCUMBERED


def test_l3_exercise_and_lapse_both_recorded_is_a_conflict():
    p = pos([ev(r.OPTION, grantee="A", territory="worldwide", d="2024-01-01"),
             ev(r.OPTION_EXERCISED, grantee="A", d=None),
             ev(r.OPTION_LAPSED, grantee="A", d="2025-01-01")])
    assert p.position == rp.P_CONFLICTING


def test_co_promotion_option_becomes_shared_when_exercised():
    o = ev(r.CO_PROMOTION_OPTION, grantee="Theta", territory="United States", d="2024-01-01")
    assert pos([o]).position == rp.P_OPTION
    assert pos([o, ev(r.OPTION_EXERCISED, grantee="Theta", d="2025-01-01")]).position == rp.P_SHARED


# -- AC6 conflicts ---------------------------------------------------------------------------------------
def test_two_exclusive_holders_conflict():
    p = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide"),
             ev(r.LICENSE, grantee="Beta", territory="North America")])
    assert p.position == rp.P_CONFLICTING and len(p.event_ids) == 2


def test_availability_plus_active_grant_conflicts():
    p = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide"),
             ev(r.AVAILABILITY_STATED, grantor="Origin Bio", territory="worldwide")])
    assert p.position == rp.P_CONFLICTING


# -- AC7 stale -------------------------------------------------------------------------------------------
def test_stale_and_undated_availability_are_not_counted():
    p = pos([ev(r.AVAILABILITY_STATED, grantor="Origin Bio", territory="worldwide", d="2019-01-01")])
    assert p.stale and p.position == rp.P_NOT_APPLIED
    fresh = pos([ev(r.AVAILABILITY_STATED, grantor="Origin Bio", territory="worldwide", d="2025-03-01")])
    assert fresh.position == rp.P_AVAILABILITY and not fresh.stale
    undated = pos([ev(r.AVAILABILITY_STATED, grantor="Origin Bio", territory="worldwide", d=None)])
    assert undated.position == rp.P_NOT_APPLIED


def test_stale_license_flagged_with_question():
    p = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide", d="2018-01-01")])
    assert p.position == rp.P_LICENSED and p.stale and any("current" in q for q in p.questions)


def test_staleness_is_measured_from_the_analysis_date():
    events = [ev(r.LICENSE, grantee="Alpha", territory="worldwide", d="2023-01-01")]
    assert not pos(events, as_of=date(2024, 1, 1)).stale
    assert pos(events, as_of=date(2026, 1, 1)).stale


# -- AC2/AC9 tiers ---------------------------------------------------------------------------------------
PREFS = TransactionPreferences(encumbered_rights="deprioritize", returned_rights="prefer")


def view(p, prefs=PREFS, **kw):
    base = {"market_status": None, "rights_status": "UNKNOWN", "rights_holder": None, "company": "Origin Bio",
            "identity_twins": []}
    return assess_transaction(prefs, **(base | kw), position=p)


def test_no_open_tier_exists_and_no_evidence_is_unresolved_with_first_contact():
    assert "OPEN" not in TIER_ORDER and not any("OBSTACLE" in t for t in TIER_ORDER)
    v = view(None)
    assert v.tier == "RIGHTS_UNRESOLVED" and v.position == rp.P_NONE
    assert "availability not evidenced" in v.reasons and "Origin Bio" in v.questions[0]
    assert "not evidence of ownership" in v.questions[0]


def test_tiers_follow_evidence_and_preferences():
    lic = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide")])
    assert view(lic).tier == "DEPRIORITIZED"
    assert view(lic, TransactionPreferences(encumbered_rights="exclude")).tier == "EXCLUDED_BY_BUYER_PREFERENCE"
    assert view(lic, TransactionPreferences()).tier == "RIGHTS_UNRESOLVED"  # ignored, never promoted
    # revision 4 (review R1v3 N4f): an undated ending is never current, so the termination carries a date
    ret = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide"),
               ev(r.TERMINATION, grantee="Alpha", d="2025-03-01")])
    v = view(ret)
    assert v.tier == "NO_THIRD_PARTY_GRANT_IN_EVIDENCE" and v.sort_bonus == 1
    assert "availability not evidenced" in v.reasons
    avail = pos([ev(r.AVAILABILITY_STATED, grantor="Origin Bio", territory="worldwide")])
    assert view(avail).tier == "AVAILABILITY_STATED_UNVERIFIED"


def test_shared_rights_follow_their_own_preference():
    shared = pos([ev(r.CO_DEVELOPMENT, grantee="Delta Bio", grantor="Lead Bio", territory="worldwide")])
    assert view(shared).tier == "RIGHTS_UNRESOLVED"  # encumbered_rights does not govern shared rights
    assert view(shared, TransactionPreferences(shared_rights="deprioritize")).tier == "DEPRIORITIZED"


def test_holder_preference_uses_evidence_holder_and_names_it():
    lic = pos([ev(r.LICENSE, grantee="Theta Pharma", territory="worldwide")])
    v = view(lic, TransactionPreferences(deprioritized_holders=["Theta Pharma"]))
    assert v.tier == "DEPRIORITIZED" and "per evidence 'Theta Pharma'" in v.reasons[0]


def test_reasons_not_duplicated_when_deprioritized():
    lic = pos([ev(r.LICENSE, grantee="Alpha", territory="worldwide", d="2018-01-01")])
    v = view(lic)
    assert len(v.reasons) == len(set(v.reasons))


# -- P1/P2 counterparty names ---------------------------------------------------------------------------
def test_p2_punctuation_and_suffixes_do_not_block_a_match():
    assert name_matches("Bristol-Myers Squibb", "Bristol Myers Squibb Company")
    assert name_matches("Alpha Pharma", "Alpha Pharma, Inc.")
    assert not name_matches("Ono", "Sonoma Biotherapeutics")


def test_p1_ambiguous_declared_counterparty_is_reported():
    prefs = TransactionPreferences(deprioritized_holders=["Kappa", "Astra"])
    names = ["Kappa KGaA, Darmstadt", "Kappa Sharp & Dohme LLC", "Astra Pharma US, Inc.",
             "Astra Pharma Global Development, Inc."]
    out = holder_ambiguities(prefs, names)
    assert set(out) == {"Kappa"} and len(out["Kappa"]) == 2


def test_party_key_keeps_distinct_companies_apart():
    assert party_key("Alpha Pharma, Inc.") == party_key("Alpha Pharma")
    assert party_key("Acme KGaA") != party_key("Acme & Co., Inc.")


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
    assert e.event_date_precision == "month" and e.event_date_text == "2024-03"
    reasons = " ".join(" ".join(x["reasons"]) for x in out.rejected)
    assert "not guessed" in reasons and "Pending" in reasons and "name a party" in reasons


def test_profile_rejects_unknown_canonical_values():
    with pytest.raises(ValueError):
        r.RightsProfile(**(PROFILE | {"event_type_map": {"licensing": "AVAILABLE"}}))


def test_workbook_rights_cells_show_evidence_owner_and_questions():
    from bve.dealscreen.workbook import _rights_cells

    p = pos([ev(r.OPTION, grantee="Eta AG", territory="ex-Greater China", d="2024-01-01")])
    v = view(p)
    cells = _rights_cells({"rights_position": v.position, "rights_holder_per_evidence": v.holder,
                           "owner_per_evidence": v.owner, "evidence": v.evidence, "stale": v.stale,
                           "diligence_questions": v.questions})
    assert cells[0] == rp.P_OPTION and cells[1] == "Eta AG" and cells[2] == "Origin Bio"
    assert "https://example.test/" in cells[3] and "quote" in cells[3] and "exercised" in cells[5]
    assert _rights_cells({})[3] == "no rights record"


def test_sponsor_is_never_an_input_to_the_position():
    import inspect

    assert "originator" not in inspect.signature(rp.rights_position).parameters


# -- R1 self-review: dates as written, event order, superseded statements, every grant named --------------
def test_coarse_dates_are_shown_as_written_not_as_the_first_day():
    p = pos([ev(r.LICENSE, grantee="A", territory="worldwide", d="2024")])
    assert p.evidence[0]["date"] == "2024"
    p = pos([ev(r.LICENSE, grantee="A", territory="worldwide", d="2024-05", src="2024-06-30")])
    assert p.evidence[0]["date"] == "2024-05" and p.evidence[0]["source_date"] == "2024-06-30"
    assert r.parse_date("2024") == (date(2024, 1, 1), "year")


@pytest.mark.parametrize(("grant_date", "end_date"), [("2024", "2024-03-01"), ("2024-06-01", "2024")])
def test_outcome_and_grant_in_the_same_period_cannot_be_ordered(grant_date, end_date):
    p = pos([ev(r.LICENSE, grantee="A", territory="worldwide", d=grant_date),
             ev(r.TERMINATION, grantee="A", d=end_date)], as_of=date(2025, 1, 1))
    assert p.position == rp.P_CONFLICTING
    assert any("cannot order" in q for q in p.questions)


def test_coarse_outcome_after_the_grant_period_still_clears():
    p = pos([ev(r.LICENSE, grantee="A", territory="worldwide", d="2022-05-04"),
             ev(r.RIGHTS_RETURNED, grantee="A", d="2024")], as_of=date(2025, 1, 1))
    assert p.position == rp.P_RETURNED


def test_outcome_dated_before_every_grant_to_that_party_ended_an_earlier_deal():
    p = pos([ev(r.TERMINATION, grantee="A", d="2020-01-01"),
             ev(r.LICENSE, grantee="A", territory="worldwide", d="2024-01-01")])
    assert p.position == rp.P_LICENSED and p.holder == "A"
    assert not any("successor" in q for q in p.questions)
    assert any("earlier deal" in x for x in p.reasons)


def test_outcome_linked_to_a_later_deal_is_a_conflict():
    p = pos([ev(r.TERMINATION, grantee="A", d="2020-01-01", related="DX"),
             ev(r.LICENSE, grantee="A", territory="worldwide", d="2024-01-01", deal="DX")])
    assert p.position == rp.P_CONFLICTING and any("Which date" in q for q in p.questions)


def test_availability_statement_superseded_by_a_later_grant():
    # revision 4: the statement must be current by its own date to count at all, so it is dated within the limit
    p = pos([ev(r.AVAILABILITY_STATED, grantor="Origin Bio", territory="worldwide", d="2024-01-01"),
             ev(r.LICENSE, grantee="A", territory="worldwide", d="2024-06-01")])
    assert p.position == rp.P_LICENSED and any("superseded" in x for x in p.reasons)
    later = pos([ev(r.LICENSE, grantee="A", territory="worldwide", d="2024-06-01"),
                 ev(r.AVAILABILITY_STATED, grantor="Origin Bio", territory="worldwide", d="2025-01-01")])
    assert later.position == rp.P_CONFLICTING


def test_availability_without_a_territory_asks_which():
    p = pos([ev(r.AVAILABILITY_STATED, grantor="Origin Bio", territory=None, d="2025-03-01")])
    assert p.position == rp.P_AVAILABILITY
    assert any("territory" in x for x in p.reasons) and any("Which territories" in q for q in p.questions)


def test_one_fresh_dated_statement_counts_even_with_an_undated_one():
    p = pos([ev(r.AVAILABILITY_STATED, grantor="Origin Bio", territory="worldwide", d="2025-03-01"),
             ev(r.AVAILABILITY_STATED, grantor="Origin Bio", territory="worldwide", d=None)])
    assert p.position == rp.P_AVAILABILITY


def test_every_grant_over_the_territory_is_reported():
    # AC6: an exclusive license and an exclusive option to different parties over one territory conflict (R1v3 G1)
    p = pos([ev(r.LICENSE, grantee="Small Bio", territory="United States", d="2024-01-01"),
             ev(r.OPTION, grantee="Big Pharma AG", territory="worldwide", d="2024-02-01")])
    assert p.position == rp.P_CONFLICTING and {"Small Bio", "Big Pharma AG"} <= set(p.holders)
    assert any("option to Big Pharma AG" in x and "license to Small Bio" in x for x in p.reasons)
    assert len(p.evidence) == 2
    assert view(p, TransactionPreferences(deprioritized_holders=["Big Pharma"])).tier == "DEPRIORITIZED"
    # a co-promotion option is not over the rights themselves: it is named, not a conflict
    co = pos([ev(r.LICENSE, grantee="Small Bio", territory="United States", d="2024-01-01"),
              ev(r.CO_PROMOTION_OPTION, grantee="Big Pharma AG", territory="worldwide", d="2024-02-01")])
    assert co.position == rp.P_LICENSED and "Big Pharma AG" in co.holders
    assert any("Big Pharma AG" in q and "exercised" in q for q in co.questions)


def test_option_questions_ask_about_the_outcome_not_a_sublicense():
    p = pos([ev(r.OPTION, grantee="Eta AG", territory="worldwide", d="2024-01-01")])
    assert any("exercised" in q for q in p.questions) and not any("sublicense" in q for q in p.questions)


def test_staleness_uses_the_source_date_when_given():
    assert not pos([ev(r.LICENSE, grantee="A", territory="worldwide", d="2018-01-01", src="2025-01-15")]).stale
    assert pos([ev(r.LICENSE, grantee="A", territory="worldwide", d="2018-01-01")]).stale


def test_reasons_use_words_not_codes():
    p = pos([ev(r.LICENSE, grantee="Zeta", territory="worldwide"),
             ev(r.RIGHTS_RETURNED, grantee="Big Acquirer", d=None)])
    text = " ".join(p.reasons + p.questions)
    assert "rights_returned" not in text and "rights return" in text
