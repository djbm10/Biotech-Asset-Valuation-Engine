"""Cycle R1 revision 4: the inputs from adversarial re-review 2 (research/dealscreen_rights_v1/REREVIEW2.md).

Every definite input in sections 2 and 3, and the judgement calls revision 4 decided, with fictional parties.
Defaults as in the review: buyer territory US, as-of 2025-06-01, maximum evidence age 730 days, encumbered rights
deprioritized, licensor "Origin Bio" unless stated. Each test is tagged with its review id. They test logic only and
assert no real-world facts."""

from __future__ import annotations

import csv
import shutil
from datetime import date
from types import SimpleNamespace

import pytest
import yaml

from bve.dealscreen import commercial as c
from bve.dealscreen import rights as r
from bve.dealscreen import rights_position as rp
from bve.dealscreen.rights_territory import parse_territory, same_company
from bve.dealscreen.rights_words import POSITION_WORDS
from bve.dealscreen.screening import _reconcile_with_field
from bve.dealscreen.transaction import (
    TransactionPreferences,
    assess_transaction,
    position_from_field,
)

US = frozenset({"US"})
JP = frozenset({"JP"})
TOP = frozenset({"AVAILABILITY_STATED_UNVERIFIED", "NO_THIRD_PARTY_GRANT_IN_EVIDENCE"})
PREFS = TransactionPreferences(encumbered_rights="deprioritize")
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
        event_id=f"rx:r2:{n}", deal_id=deal or f"D{n}", external_id="P1", event_type=kind, exclusivity=excl,
        grantee=grantee, grantor=grantor, territory_as_written=territory,
        territory=sorted(regions) if regions is not None else None,
        event_date=when, event_date_precision=precision, status=status, related_deal_id=related,
        source_system="TEST", dataset_version="TEST:x", row_number=n, source_reference=f"https://example.test/{n}",
        evidence_quote=f"quote {n}", source_date=source, source_date_precision=source_precision)


def pos(events, territory=US, as_of: date | None = date(2025, 6, 1), max_age=730, company: str | None = "Origin Bio"):
    """``company``: the landscape company (revision 5: a clear position must rest on it)."""
    return rp.rights_position(events, territory=territory, as_of=as_of, max_age_days=max_age, first_contact=company)


def view(p, prefs=PREFS, guard=None):
    return assess_transaction(prefs, market_status=None, rights_status="UNKNOWN", rights_holder=None,
                              company="Origin Bio", identity_twins=[], position=p, guard=guard)


def tier(p, **kw) -> str:
    return view(p, **kw).tier


def blocked(p, check: str, words: str = "") -> bool:
    return any(b.startswith(f"{check}:") and words in b for b in p.top_tier_blockers)


# -- 2a: introduced by revision 3 ----------------------------------------------------------------------------
def test_n1a_a_license_that_names_no_licensee_is_held_by_an_unnamed_licensee():
    p = pos([ev(r.LICENSE, grantee=None, territory="United States")])
    assert p.position == rp.P_LICENSED and p.holder == rp.UNNAMED and tier(p) == "DEPRIORITIZED"
    assert any("The record names no licensee" in q for q in p.questions)
    assert not any("do not cover" in x for x in p.reasons)


@pytest.mark.parametrize(("kind", "expected"), [(r.OPTION, rp.P_OPTION), (r.CO_DEVELOPMENT, rp.P_SHARED)])
def test_n1b_n1c_an_option_or_co_development_naming_one_party_still_covers_the_territory(kind, expected):
    p = pos([ev(kind, grantee=None, territory="worldwide")])
    assert p.position == expected and tier(p) not in TOP


def test_n1d_an_intra_group_license_is_worded_as_one_company():
    p = pos([ev(r.LICENSE, grantee="Origin Bio Inc", grantor="Origin Bio Ltd", territory="United States")])
    assert p.position == rp.P_OWNER_ACQUIRED and tier(p) == "NO_THIRD_PARTY_GRANT_IN_EVIDENCE"  # judgement kept
    assert any("within one company as written" in x for x in p.reasons)
    assert not any("do not cover" in x for x in p.reasons)


def test_n3a_an_acquisition_limited_to_another_territory_does_not_end_a_us_license():
    p = pos([ev(r.LICENSE, grantee="Alpha Bio", territory="worldwide", d="2021-01-01"),
             ev(r.ACQUISITION, grantee="Origin Bio", grantor="Alpha Bio", territory="Greater China", d="2024-06-01")])
    assert p.position == rp.P_LICENSED and p.holder == "Alpha Bio" and tier(p) == "DEPRIORITIZED"
    assert any("covers Greater China only; not applied for US" in x for x in p.reasons)
    assert len(p.evidence) == 2  # the acquisition that was not applied is still cited


@pytest.mark.parametrize("lapse", [{"d": "2023-03-01"}, {"d": None, "src": "2023-03"}], ids=["R1", "R1b"])
def test_r1_an_option_dated_only_by_its_report_is_not_cleared_by_an_earlier_lapse(lapse):
    p = pos([ev(r.OPTION, grantee="Alpha Bio", territory="worldwide", d=None, src="2024-06"),
             ev(r.OPTION_LAPSED, grantee="Alpha Bio", **lapse)])
    assert p.position in {rp.P_OPTION, rp.P_CONFLICTING} and tier(p) not in TOP


# -- 2b: claimed fixed, close variants -----------------------------------------------------------------------
def _screen(status: str = c.UNKNOWN, holder: str | None = None, basis=(), holder_basis=()) -> SimpleNamespace:
    return SimpleNamespace(commercial=SimpleNamespace(
        us_rights_status=status, us_rights_holder=holder, us_rights_holder_conflict=[],
        us_rights_basis=list(basis), us_rights_holder_basis=list(holder_basis)))


ANALYST = {"claim_id": "a1", "origin": "ANALYST_ASSERTED", "source": "https://example.test/assert1",
           "source_date": "2025-04-01"}


def test_e2_holder_an_analyst_naming_a_third_party_us_holder_contests_a_clear_position():
    china = [ev(r.LICENSE, grantee="Chinaco", territory="mainland China", d="2025-02-01")]
    p = pos(china)
    assert p.position == rp.P_NOT_ENCUMBERED
    _reconcile_with_field(p, _screen(holder="BigPharma Inc.", holder_basis=[ANALYST | {"value": "BigPharma Inc."}]), US)
    assert p.position == rp.P_CONFLICTING and tier(p) not in TOP
    assert any(x.startswith("an analyst assertion names BigPharma Inc. as the U.S. rights holder") for x in p.reasons)
    assert any("Does BigPharma Inc. hold U.S. rights" in q for q in p.questions)
    assert any(e["type"] == "FIELD_STATEMENT" and e["source"] == ANALYST["source"] for e in p.evidence)
    owner = pos(china)  # naming the owner itself contests nothing
    _reconcile_with_field(owner, _screen(holder="Origin Bio"), US)
    assert owner.position == rp.P_NOT_ENCUMBERED


LABELER = "Acme Pharma US, Inc. (U.S. labeler per FDA label; not a rights statement)"


@pytest.mark.parametrize(("a", "b", "same"), [
    ("Acme", LABELER, True), ("Acme Bio Ltd", "acme bio inc", True), ("Acme", "Acme KGaA", False),
    ("Acme", "Acme Development Partners", False), ("Ono", "Sonoma Ono", False), ("Acme", None, False),
])
def test_e2_holder_a_near_namesake_is_not_read_as_the_same_company(a, b, same):
    assert same_company(a, b) is same and same_company(b, a) is same


def test_e2_holder_a_near_namesake_of_the_owner_contests_a_clear_position_and_a_subsidiary_does_not():
    china = [ev(r.LICENSE, grantee="Chinaco", grantor="Acme", territory="mainland China", d="2025-02-01")]
    namesake = pos(china)
    assert namesake.position == rp.P_NOT_ENCUMBERED and namesake.owner == "Acme"
    _reconcile_with_field(namesake, _screen(holder="Acme KGaA"), US)
    assert namesake.position == rp.P_CONFLICTING and tier(namesake) not in TOP
    subsidiary = pos(china)
    _reconcile_with_field(subsidiary, _screen(holder=LABELER), US)
    assert subsidiary.position == rp.P_NOT_ENCUMBERED


@pytest.mark.parametrize(("text", "expected"), [
    ("Available for licensing: no", c.NOT_AVAILABLE), ("Available? No.", c.NOT_AVAILABLE),
    ("Available, but not in the U.S.", c.UNKNOWN), ("Ex-U.S. rights available", c.UNKNOWN),
    ("China rights available", c.UNKNOWN), ("Rights outside the United States are available", c.UNKNOWN),
    ("Was available until 2021", c.UNKNOWN), ("Previously available", c.UNKNOWN),
    ("available only in the U.S.", c.AVAILABLE), ("U.S. rights available; seeking a partner", c.AVAILABLE),
])
def test_f1_analyst_text_is_read_with_negation_place_and_tense(text, expected):
    assert c.rights_status(text) == expected


@pytest.mark.parametrize(("source_date", "counted"), [("2025-03-01", True), ("2015-01-01", False), (None, False)])
def test_f1_an_analyst_availability_statement_counts_only_when_dated_current_and_cited(source_date, counted):
    basis = [{"claim_id": "a1", "value": "U.S. rights available; seeking a partner", "origin": "ANALYST_ASSERTED",
              "source": "https://example.test/a1", "source_date": source_date, "quote": "U.S. rights are available"}]
    p = position_from_field(c.AVAILABLE_CONFIRMED, None, "Origin Bio", basis=basis, as_of=date(2025, 6, 1),
                            max_age_days=730)
    assert p.evidence and p.evidence[0]["source"] == "https://example.test/a1"  # cited either way
    if counted:
        assert p.position == rp.P_AVAILABILITY and tier(p) == "AVAILABILITY_STATED_UNVERIFIED"
    else:
        assert p.position == rp.P_NONE and tier(p) == "RIGHTS_UNRESOLVED"
        assert any("not counted" in x for x in p.reasons)


def test_n6_an_undated_statement_is_not_counted_beside_another_statement():
    unreadable = pos([ev(r.AVAILABILITY_STATED, grantor="Origin Bio", d=None),
                      ev(r.AVAILABILITY_STATED, grantor="Origin Bio", territory="Europe and Latin America",
                         d="2025-03-01")])
    assert unreadable.position == rp.P_NONE and tier(unreadable) not in TOP  # N6a
    completed = pos([ev(r.AVAILABILITY_STATED, grantor="Origin Bio", d=None),
                     ev(r.AVAILABILITY_STATED, grantor="Origin Bio", d="2025-03-01", status="COMPLETED")])
    assert completed.position == rp.P_NONE and tier(completed) not in TOP  # N6b
    superseded = pos([ev(r.AVAILABILITY_STATED, grantor="Origin Bio", d=None),
                      ev(r.AVAILABILITY_STATED, grantor="Origin Bio", d="2024-01-01"),
                      ev(r.LICENSE, grantee="Alpha Bio", territory="United States", d="2024-03-01"),
                      ev(r.TERMINATION, grantee="Alpha Bio", d="2025-01-01")])
    assert superseded.position == rp.P_RETURNED  # N6c: the A3 rule


@pytest.mark.parametrize("acquired", ["Origin Bio", "Alpha Bio"], ids=["N7b", "N7c"])
def test_n7b_n7c_an_unrelated_later_acquisition_does_not_refresh_an_old_return(acquired):
    p = pos([ev(r.LICENSE, grantee="Alpha Bio", territory="worldwide", d="2012-01-01"),
             ev(r.RIGHTS_RETURNED, grantee="Alpha Bio", d="2014-01-01"),
             ev(r.ACQUISITION, grantee="Gamma Corp", grantor=acquired, d="2025-01-01")])
    assert p.position == rp.P_RETURNED and p.stale and tier(p) == "RIGHTS_UNRESOLVED"
    assert blocked(p, "current", "(2014-01-01)")


def test_n8_a_co_development_ended_by_one_partner_is_not_clear():
    two = pos([ev(r.CO_DEVELOPMENT, grantee="Alpha Bio", grantor="Beta Bio", territory="worldwide", d="2024-01-01"),
               ev(r.TERMINATION, grantee="Beta Bio", grantor=None)])
    assert two.position == rp.P_SHARED and tier(two) not in TOP
    origin = pos([ev(r.CO_DEVELOPMENT, grantee="Alpha Bio", territory="worldwide", d="2024-01-01"),
                  ev(r.TERMINATION, grantee=None, grantor="Origin Bio")])
    assert origin.position == rp.P_SHARED and tier(origin) not in TOP
    assert any("Does Alpha Bio hold all US rights after Origin Bio's exit" in q for q in origin.questions)


# -- 2c: older paths -----------------------------------------------------------------------------------------
EXERCISE = {"grantee": "Beta Pharma", "territory": "United States", "d": "2025-02-01"}


def test_n2_h1_an_exercise_with_no_recorded_option_is_evidence_of_a_us_license():
    china = pos([ev(r.LICENSE, grantee="Alpha Bio", territory="mainland China", d="2024-01-01"),
                 ev(r.OPTION_EXERCISED, **EXERCISE)])
    assert china.position == rp.P_CONFLICTING and "Beta Pharma" in china.holders and tier(china) not in TOP  # N2a
    assert any("matches no recorded option; Beta Pharma may hold US rights" in x for x in china.reasons)
    stated = pos([ev(r.AVAILABILITY_STATED, grantor="Origin Bio", d="2024-06-01"), ev(r.OPTION_EXERCISED, **EXERCISE)])
    assert stated.position == rp.P_CONFLICTING and tier(stated) not in TOP  # N2b
    ended = pos([ev(r.TERMINATION, grantee="Alpha Bio", d="2024-06-01"), ev(r.OPTION_EXERCISED, **EXERCISE)])
    assert ended.position == rp.P_CONFLICTING and tier(ended) not in TOP  # H1


def test_n7a_a_statement_is_judged_on_its_own_date_not_on_a_later_report():
    p = pos([ev(r.AVAILABILITY_STATED, grantor="Origin Bio", territory="worldwide", d="2015-03-01", src="2025-03-01")])
    assert p.position == rp.P_NONE and tier(p) not in TOP


def test_n10_records_dated_after_the_as_of_date_are_not_applied():
    p = pos([ev(r.LICENSE, grantee="Alpha Bio", territory="United States", d="2023-01-01"),
             ev(r.TERMINATION, grantee="Alpha Bio", d="2026-01-15")])
    assert p.position == rp.P_LICENSED
    assert any("not applied, dated after the as-of date 2025-06-01" in x for x in p.reasons)
    assert len(p.evidence) == 2


# -- 2d: judgement calls decided by revision 4 ---------------------------------------------------------------
@pytest.mark.parametrize(("grantee", "grantor", "check", "words"), [
    ("Delta Bio", "Origin Bio", "specific", "states no territory"),  # N4a
    (None, "Origin Bio", "specific", "does not name both parties"),  # N4b
    ("Delta Bio", None, "specific", "does not name both parties"),  # N4c
])
def test_n4_a_return_recorded_without_its_grant_needs_both_parties_and_a_territory(grantee, grantor, check, words):
    p = pos([ev(r.TERMINATION, grantee=grantee, grantor=grantor)])
    assert p.position == rp.P_RETURNED and tier(p) == "RIGHTS_UNRESOLVED" and blocked(p, check, words)
    assert any("What record would make this rights evidence specific" in q for q in view(p).questions)


def _company(events, company: str | None, territory=US):
    return rp.rights_position(events, territory=territory, as_of=date(2025, 6, 1), max_age_days=730,
                              first_contact=company)


def test_n4d_a_return_without_its_grant_counts_only_when_it_returns_the_rights_to_the_programs_company():
    returned = [ev(r.RIGHTS_RETURNED, grantee="Delta Bio", grantor="Kappa Pharma", territory="United States")]
    other = _company(returned, "Origin Bio")  # Kappa may be a head licensee of Origin Bio
    v = view(other)
    assert other.position == rp.P_RETURNED and other.owner is None and v.tier == "RIGHTS_UNRESOLVED"
    assert blocked(other, "specific", "but the landscape names Origin Bio as the program's company")
    assert any("Does Kappa Pharma own this program, or hold it under a license from Origin Bio?" in q
               for q in other.questions)
    assert "rights returned per source to Kappa Pharma (not a statement of availability)" in v.notes
    assert not any("originator" in n for n in v.notes)
    unknown = _company(returned, None)
    assert tier(unknown) == "RIGHTS_UNRESOLVED" and blocked(unknown, "specific", "no program company is named")
    own = _company(returned, "Kappa Pharma, Inc.")  # the recipient is the program's company
    assert own.owner == "Kappa Pharma" and tier(own) == "NO_THIRD_PARTY_GRANT_IN_EVIDENCE"
    part = _company(returned, "Kappa Pharma", territory=frozenset({"US", "JP"}))
    assert blocked(part, "specific", "covers only part of JP/US")


@pytest.mark.parametrize("events", [
    pytest.param(lambda: [ev(r.TERMINATION, grantee="Alpha Bio", territory="worldwide", d=None)], id="N4f"),
    pytest.param(lambda: [ev(r.LICENSE, grantee="Alpha Bio", territory="worldwide", d=None),
                          ev(r.TERMINATION, grantee="Alpha Bio", d=None)], id="N5a"),
    pytest.param(lambda: [ev(r.LICENSE, grantee="Chinaco", territory="mainland China", d=None)], id="N5b"),
    pytest.param(lambda: [ev(r.OPTION, grantee="Alpha Bio", territory="worldwide", d=None),
                          ev(r.OPTION_LAPSED, grantee="Alpha Bio")], id="N5c"),
    pytest.param(lambda: [ev(r.LICENSE, grantee="Alpha Bio", territory="worldwide", d="2024-03"),
                          ev(r.TERMINATION, grantee="Alpha Bio", d=None)], id="N9a"),
    pytest.param(lambda: [ev(r.LICENSE, grantee="Alpha Bio", territory="worldwide", d=None),
                          ev(r.TERMINATION, grantee="Alpha Bio")], id="N9b"),
])
def test_n4f_n5_n9_undated_clearing_evidence_never_reaches_the_top_tiers(events):
    p = pos(events())
    assert p.position in rp.CLEAR_POSITIONS and tier(p) == "RIGHTS_UNRESOLVED" and blocked(p, "current")


def test_n3c_an_acquisition_alone_says_nothing_about_licenses():
    p = pos([ev(r.ACQUISITION, grantee="Gamma Corp", grantor="Origin Bio")])
    assert p.position == rp.P_OWNER_ACQUIRED and tier(p) == "RIGHTS_UNRESOLVED"
    assert blocked(p, "complete", "only an acquisition is recorded")


def test_n9c_an_ending_naming_only_the_licensor_must_be_linked_to_its_deal():
    loose = pos([ev(r.LICENSE, grantee="Alpha Bio", territory="United States", d="2024-03"),
                 ev(r.TERMINATION, grantee=None, grantor="Origin Bio", d="2025-01")])
    assert loose.position == rp.P_RETURNED and tier(loose) == "RIGHTS_UNRESOLVED"
    assert blocked(loose, "specific", "names only the licensor")
    linked = pos([ev(r.LICENSE, grantee="Alpha Bio", territory="United States", d="2024-03", deal="DL"),
                  ev(r.TERMINATION, grantee=None, grantor="Origin Bio", d="2025-01", related="DL")])
    assert linked.position == rp.P_RETURNED and tier(linked) == "NO_THIRD_PARTY_GRANT_IN_EVIDENCE"


def test_n11_without_an_as_of_date_a_clear_position_is_not_counted():
    p = pos([ev(r.LICENSE, grantee="Alpha Bio", territory="worldwide", d="2009-01-01"),
             ev(r.RIGHTS_RETURNED, grantee="Alpha Bio", d="2010-01-01")], as_of=None)
    assert p.position == rp.P_RETURNED and tier(p) == "RIGHTS_UNRESOLVED" and blocked(p, "current", "no as-of date")


def test_a_returned_co_development_with_no_owner_is_not_specific():
    p = pos([ev(r.CO_DEVELOPMENT, grantee="Alpha Bio", grantor="Beta Bio", territory="worldwide", d="2024-01-01",
                deal="DC"), ev(r.TERMINATION, grantee=None, grantor=None, related="DC")])
    assert p.position == rp.P_RETURNED and blocked(p, "specific", "who holds the US rights now is not established")


# -- 3: false encumbrance, holder, owner and labels -------------------------------------------------------------
def _option_then(*outcomes: r.RightsEvent) -> list[r.RightsEvent]:
    return [ev(r.OPTION, grantee="Alpha Bio", territory="worldwide", d="2023-01-01", deal="DX"), *outcomes]


def test_p1_a_later_lapse_ends_the_rest_of_a_partly_exercised_option():
    e2 = _option_then(ev(r.OPTION_EXERCISED, grantee="Alpha Bio", territory="Japan", d="2024-06-01"),
                      ev(r.OPTION_LAPSED, grantee="Alpha Bio"))
    assert pos(e2).position == rp.P_NOT_ENCUMBERED and tier(pos(e2)) == "NO_THIRD_PARTY_GRANT_IN_EVIDENCE"
    assert pos(e2, territory=JP).position == rp.P_LICENSED  # the license split off for Japan is kept
    e8 = _option_then(ev(r.OPTION_EXERCISED, grantee="Alpha Bio", territory="United States", d="2024-03-01"),
                      ev(r.OPTION_LAPSED, grantee="Alpha Bio", territory="worldwide excluding the U.S."))
    assert pos(e8, territory=JP).position == rp.P_NOT_ENCUMBERED and pos(e8).position == rp.P_LICENSED
    e1 = _option_then(ev(r.OPTION_EXERCISED, grantee="Alpha Bio", territory="United States", d="2024-03-01"),
                      ev(r.OPTION_LAPSED, grantee="Alpha Bio"))
    assert pos(e1, territory=JP).position == rp.P_NOT_ENCUMBERED
    e3 = _option_then(ev(r.OPTION_EXERCISED, grantee="Alpha Bio", territory="United States", d="2024-03-01"),
                      ev(r.OPTION_EXERCISED, grantee="Alpha Bio", territory="Japan"))
    assert pos(e3, territory=JP).position == rp.P_LICENSED


def test_p1_e7_a_termination_linked_to_the_option_deal_ends_the_license_split_from_it():
    p = pos(_option_then(ev(r.OPTION_EXERCISED, grantee="Alpha Bio", territory="United States", d="2024-03-01",
                            related="DX"),
                         ev(r.TERMINATION, grantee="Alpha Bio", related="DX")))
    assert p.position == rp.P_RETURNED and tier(p) == "NO_THIRD_PARTY_GRANT_IN_EVIDENCE"


def test_n3b_an_acquisition_outside_the_buyer_territory_does_not_change_the_us_owner():
    p = pos([ev(r.ACQUISITION, grantee="Gamma Corp", grantor="Origin Bio", territory="worldwide excluding the U.S.")])
    assert p.position == rp.P_NONE and p.owner is None
    prefs = TransactionPreferences(encumbered_rights="deprioritize", deprioritized_holders=["Gamma Corp"])
    assert tier(p, prefs=prefs) == "RIGHTS_UNRESOLVED"


@pytest.mark.parametrize("text", ["Not licensed", "Not licensed in the U.S.", "Never partnered", "Not optioned"])
def test_negated_grant_words_are_not_an_encumbrance(text):
    assert c.rights_status(text) == c.UNKNOWN
    p = pos([ev(r.LICENSE, grantee="Chinaco", territory="mainland China", d="2025-02-01")])
    _reconcile_with_field(p, _screen(status=c.rights_status(text)), US)
    assert p.position == rp.P_NOT_ENCUMBERED
    assert c.rights_status("Not partnered; available") != c.ENCUMBERED


def test_na_label_not_available_reads_as_not_available_never_as_licensed():
    p = position_from_field(c.NOT_AVAILABLE, None, "Origin Bio")
    assert p.position == rp.P_NOT_AVAILABLE and POSITION_WORDS[p.position] == "not available per source"
    assert tier(p) == "DEPRIORITIZED"  # governed by the buyer's encumbered_rights
    assert not any("_" in x for x in p.reasons)  # words, not codes


def test_w1_a_fresh_re_license_is_current_and_the_older_one_is_not_flagged():
    p = pos([ev(r.LICENSE, grantee="Alpha Bio", territory="United States", d="2015-01-01"),
             ev(r.LICENSE, grantee="Alpha Bio", territory="United States", d="2025-01-01")])
    assert p.position == rp.P_LICENSED and not p.stale
    assert not any("may have ended" in x for x in p.reasons)


def test_n7e_an_acquisition_does_not_make_an_old_license_current():
    p = pos([ev(r.LICENSE, grantee="Alpha Bio", territory="United States", d="2015-01-01"),
             ev(r.ACQUISITION, grantee="Gamma Corp", grantor="Origin Bio")])
    assert p.position == rp.P_LICENSED and p.stale


def test_h6_every_acquisition_in_the_chain_is_named():
    p = pos([ev(r.LICENSE, grantee="Alpha Bio", territory="United States", d="2023-01-01"),
             ev(r.ACQUISITION, grantee="Gamma Corp", grantor="Alpha Bio", d="2024-01-01"),
             ev(r.ACQUISITION, grantee="Origin Bio", grantor="Gamma Corp")])
    assert p.position == rp.P_OWNER_ACQUIRED and tier(p) == "NO_THIRD_PARTY_GRANT_IN_EVIDENCE"
    assert any("Gamma Corp acquired Alpha Bio (2024-01-01); Origin Bio acquired Gamma Corp (2025-01-01)" in x
               for x in p.reasons)


def test_h5_an_expired_option_is_worded_as_a_lapse():
    p = pos([ev(r.OPTION, grantee="Alpha Bio", territory="worldwide", d="2024-01-01", status="EXPIRED")])
    assert p.position == rp.P_NOT_ENCUMBERED and any("option to Alpha Bio lapsed in US" in x for x in p.reasons)


def test_h3_an_ended_grant_names_its_holder_as_recorded_and_its_successor():
    p = pos([ev(r.LICENSE, grantee="Alpha Bio", territory="United States", d="2024-01-01"),
             ev(r.TERMINATION, grantee="Alpha Bio", d="2024-06-01"),
             ev(r.ACQUISITION, grantee="Gamma Corp", grantor="Alpha Bio")])
    assert p.position == rp.P_RETURNED
    assert any("grant to Alpha Bio (now Gamma Corp) ended in US" in x for x in p.reasons)


# -- E3-ids, F1-analyst and section 4 through the workspace (synthetic landscape) ------------------------------
RIGHTS_PROFILE = {
    "name": "rr2", "source_system": "VENDOR_X", "license_status": "licensed", "allowed_use": "internal_only",
    "columns": {"deal_id": "Deal", "external_id": "Drug ID", "event_type": "Type", "grantee": "Licensee",
                "grantor": "Licensor", "territory": "Territory", "event_date": "Date", "status": "Status",
                "source_reference": "URL", "evidence_quote": "Quote"},
    "event_type_map": {"licensing": "LICENSE"},
    "status_map": {"active": "ACTIVE"},
}


def _workspace(tmp_path, demo_dir, rows: list[list[str]]):
    from bve.dealscreen.workspace import Workspace

    buyer = tmp_path / "buyer.yaml"
    shutil.copyfile(demo_dir / "buyer_tl1a_ibd.yaml", buyer)
    with buyer.open("a", encoding="utf-8") as f:
        f.write("\ntransaction:\n  encumbered_rights: deprioritize\n")
    ws = Workspace(tmp_path / "ws")
    ws.import_landscape(demo_dir / "landscape_200.csv", demo_dir / "profile_synthetic_vendor.yaml", buyer)
    rights = tmp_path / "deals.csv"
    with rights.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(list(RIGHTS_PROFILE["columns"].values()))
        w.writerows(rows)
    profile = tmp_path / "rights_profile.yaml"
    profile.write_text(yaml.safe_dump(RIGHTS_PROFILE), encoding="utf-8")
    ws.import_rights(rights, profile)
    return ws


#: The originator the synthetic landscape names for each program used here. Since revision 5 a clear position must
#: rest on the program's own company, so a row's licensor defaults to it; pass ``licensor`` to test another party.
_ORIGINATOR = {"SYN-0051": "Corvane Bio", "SYN-0154": "Pellucid Pharma"}


def _row(n: int, program: str, licensee: str, territory: str, licensor: str | None = None) -> list[str]:
    grantor = licensor or _ORIGINATOR.get(program.strip().upper(), "Originco")
    return [f"R{n}", program, "Licensing", licensee, grantor, territory, "2026-03-01", "Active",
            f"https://x.test/{n}", f"{territory} rights"]


def test_e3_ids_rows_match_ids_without_case_and_unattached_rows_are_reported(tmp_path, demo_dir, normalizer):
    from bve.dealscreen.memo import build_memo
    from bve.dealscreen.workbook import export_workbook

    ws = _workspace(tmp_path, demo_dir, [
        _row(1, "SYN-0051", "Chinaco", "mainland China"),
        _row(2, "syn-0051 ", "Bigco", "United States"),  # E3-ids (a): case and spaces differ
        _row(3, "SYN-9999", "Otherco", "United States"),  # matches no program in the landscape
        _row(4, "SYN-0154", "Chinaco", "mainland China"),
    ])
    ws.screen(normalizer)
    ids = {a.external_id: a.asset_id for a in ws.assets()}
    screening = ws.screening()
    screens = {s["asset_id"]: s for s in screening["screens"]}
    assert screens[ids["SYN-0051"]]["transaction"]["rights_position"] == rp.P_LICENSED
    assert screens[ids["SYN-0154"]]["transaction"]["tier"] == "NO_THIRD_PARTY_GRANT_IN_EVIDENCE"
    assert [u["program_id"] for u in screening["rights_import_issues"]["unlinked_rows"]] == ["SYN-9999"]
    assert "Rights rows attached to no program." in build_memo(ws) and "row 3 ('SYN-9999'" in build_memo(ws)
    import openpyxl

    sheet = openpyxl.load_workbook(export_workbook(ws, tmp_path / "out.xlsx"))["Diligence"]
    assert any(row[2] == "RIGHTS_ROW_NOT_ATTACHED" and row[3] == "SYN-9999" for row in sheet.iter_rows(values_only=True))


def test_e3_ids_a_rejected_row_naming_no_program_keeps_every_program_out_of_the_top_tiers(tmp_path, demo_dir,
                                                                                          normalizer):
    from bve.dealscreen.memo import build_memo

    ws = _workspace(tmp_path, demo_dir, [
        _row(1, "SYN-0154", "Chinaco", "mainland China"),
        _row(2, "", "Bigco", "United States"),  # E3-ids (b): no program id, rejected at import
    ])
    ws.screen(normalizer)
    ids = {a.external_id: a.asset_id for a in ws.assets()}
    screening = ws.screening()
    t = {s["asset_id"]: s for s in screening["screens"]}[ids["SYN-0154"]]["transaction"]
    assert t["rights_position"] == rp.P_NOT_ENCUMBERED and t["tier"] == "RIGHTS_UNRESOLVED"
    assert any("names no program and was rejected at import" in x for x in t["reasons"])
    assert screening["rights_import_issues"]["unattributed_rejected_rows"][0]["row"] == 2
    assert "Rejected rights rows not attached to any program." in build_memo(ws)
    assert not {s["transaction"]["tier"] for s in screening["screens"]} & TOP


def _assert_rights(ws, normalizer, external: str, value: str, source_date: str, field: str = "us_rights") -> None:
    from bve.dealscreen.review import Action, ReviewerKind

    asset_id = {a.external_id: a.asset_id for a in ws.assets()}[external]
    ws.decision_log().record(
        action=Action.ASSERT_FACT, subject_id=asset_id, new_state="ASSERTED", reviewer_id="analyst-1",
        rationale="press release", reviewer_kind=ReviewerKind.HUMAN,
        detail={"field": field, "value": value, "source_url": "https://x.test/pr", "source_date": source_date,
                "evidence_span": f"The company stated: {value}."},
        context=ws.decision_context(normalizer))


def test_f1_analyst_availability_is_cited_dated_and_the_memo_says_what_it_fed(tmp_path, demo_dir, normalizer):
    from bve.dealscreen.memo import build_memo

    ws = _workspace(tmp_path, demo_dir, [])
    ws.screen(normalizer)  # an assertion is recorded against a screened workspace
    _assert_rights(ws, normalizer, "SYN-0051", "U.S. rights available; seeking a partner", "2026-04-01")
    _assert_rights(ws, normalizer, "SYN-0154", "U.S. rights available; seeking a partner", "2015-01-01")
    ws.screen(normalizer)
    ids = {a.external_id: a.asset_id for a in ws.assets()}
    screens = {s["asset_id"]: s for s in ws.screening()["screens"]}
    fresh, old = (screens[ids[x]]["transaction"] for x in ("SYN-0051", "SYN-0154"))
    assert fresh["tier"] == "AVAILABILITY_STATED_UNVERIFIED"
    assert fresh["evidence"] and fresh["evidence"][0]["source"] == "https://x.test/pr"
    assert old["tier"] == "RIGHTS_UNRESOLVED" and any("not counted" in x for x in old["reasons"])
    memo = build_memo(ws)
    fresh_name, old_name = (screens[ids[x]]["program_name"] for x in ("SYN-0051", "SYN-0154"))
    assert f"{fresh_name} (" in memo and "newest evidence 2026-04-01" in memo and "[analyst assertion]" in memo
    assert ("an analyst statement of availability ('U.S. rights available; seeking a partner') is dated 2015-01-01, "
            "more than 730 days before") in memo and "so it is not counted" in memo
    assert "rights assertions changed no gate; the transaction view reads them" in memo
    assert f"{old_name} (asserted: U.S. rights; transaction view now: rights unresolved)" in memo
    assert f"{fresh_name} (asserted: U.S. rights; transaction view now: availability stated, unverified)" in memo


def test_ac10_the_memo_summary_line_gives_the_reason_for_the_position_not_a_preference_match():
    from bve.dealscreen.memo import _other_line

    v = view(pos([ev(r.LICENSE, grantee="Alpha Bio", territory="United States")]),
             prefs=TransactionPreferences(deprioritized_holders=["Alpha Bio"]))
    assert v.reasons[0].startswith("rights holder or owner per evidence 'Alpha Bio' matches declared")
    assert v.position_reasons and not v.position_reasons[0].startswith("rights holder or owner")
    t = {"rights_position": v.position, "rights_holder_per_evidence": v.holder, "stale": v.stale, "evidence": [],
         "reasons": v.reasons, "position_reasons": v.position_reasons}
    line = _other_line({"program_name": "PZ-1", "disposition": "UNRESOLVED", "transaction": t})
    assert f"({v.position_reasons[0]})" in line and "matches declared" not in line


def test_h7_a_holding_company_suffix_does_not_make_a_second_company():
    """Judgement kept: "Holdings" is a corporate suffix, so the acquisition merges licensor and licensee."""
    p = pos([ev(r.LICENSE, grantee="Alpha Bio Holdings", territory="United States", d="2024-01-01"),
             ev(r.ACQUISITION, grantee="Origin Bio", grantor="Alpha Bio Inc")])
    assert p.position == rp.P_OWNER_ACQUIRED and tier(p) == "NO_THIRD_PARTY_GRANT_IN_EVIDENCE"


def test_e2_holder_end_to_end_an_analyst_holder_assertion_contests_a_clear_program(tmp_path, demo_dir, normalizer):
    ws = _workspace(tmp_path, demo_dir, [_row(1, "SYN-0154", "Chinaco", "mainland China")])
    ws.screen(normalizer)
    ids = {a.external_id: a.asset_id for a in ws.assets()}

    def txn() -> dict:
        return {s["asset_id"]: s for s in ws.screening()["screens"]}[ids["SYN-0154"]]["transaction"]

    assert txn()["tier"] == "NO_THIRD_PARTY_GRANT_IN_EVIDENCE"
    _assert_rights(ws, normalizer, "SYN-0154", "BigPharma Inc.", "2026-04-01", field="us_rights_holder")
    ws.screen(normalizer)
    t = txn()
    assert t["rights_position"] == rp.P_CONFLICTING and t["tier"] == "RIGHTS_UNRESOLVED"
    assert any(x.startswith("an analyst assertion names BigPharma Inc. as the U.S. rights holder") for x in t["reasons"])
    assert any("Does BigPharma Inc. hold U.S. rights" in q for q in t["diligence_questions"])
    assert any(e["type"] == "FIELD_STATEMENT" and e["source"] == "https://x.test/pr" for e in t["evidence"])


def test_k3_rights_returned_to_the_company_then_offered_reaches_availability_stated():
    """A return recorded without its grant, then a fresh owner statement: the most useful BD pattern. The return is
    explained when it meets the return-only standard; otherwise it still holds the program back."""
    returned = ev(r.RIGHTS_RETURNED, grantee="Bigco", grantor="Origin Bio", territory="worldwide", d="2024-08-01")
    offered = ev(r.AVAILABILITY_STATED, grantor="Origin Bio", territory="ex-China", d="2025-01-01")
    p = _company([returned, offered], "Origin Bio, Inc.")
    assert p.position == rp.P_AVAILABILITY and tier(p) == "AVAILABILITY_STATED_UNVERIFIED"
    assert any("returned the rights covering US to Origin Bio, the program's company" in x for x in p.reasons)
    assert {e["row"] for e in p.evidence} == {returned.row_number, offered.row_number}
    elsewhere = _company([returned, offered], "Kappa Pharma")  # returned to a company the landscape does not name
    assert tier(elsewhere) == "RIGHTS_UNRESOLVED" and blocked(elsewhere, "complete", "matches no recorded grant")
    no_territory = ev(r.TERMINATION, grantee="Bigco", grantor="Origin Bio", d="2024-06-01")  # REREVIEW H2
    assert tier(_company([no_territory, offered], "Origin Bio")) == "RIGHTS_UNRESOLVED"
