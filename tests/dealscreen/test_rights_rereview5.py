"""Cycle R1 revision 7: the inputs from adversarial re-review 5 (research/dealscreen_rights_v1/REREVIEW5.md).

Revision 7 makes the plain forms read what they accept, in the buyer's terms (REREVIEW5 section 11): places are read
on the text as written and compared with the buyer territory; a note in parentheses or brackets and a pronoun subject
in a multi-clause text are refused; a plain form never accepts a text the reader leaves unread, except the company
keeping its rights; ownership words and rights rows' quotes are read; a buyer territory that contains the U.S. keeps
the landscape's U.S.-rights field. Each test is tagged with its review id.

Defaults as in ``test_rights_rereview3``: buyer territory US, as-of 2025-06-01, company and licensor "Origin Bio".
Parties are fictional; the tests assert no real-world facts."""

from __future__ import annotations

import pytest
from test_rights_rereview3 import (
    AV,
    CHINA,
    STATED,
    TIER0,
    TIER1,
    TOP,
    UNRESOLVED,
    L,
    T,
    analyst,
    blocked,
    cell,
    ev,
    run,
)

from bve.dealscreen import rights as r
from bve.dealscreen import rights_position as rp
from bve.dealscreen.rights_allow import is_rights_text, plain_form
from bve.dealscreen.rights_gate import row_guards
from bve.dealscreen.rights_reader import AVAILABLE, rights_reading
from bve.dealscreen.rights_territory import content_note

OTHER = "Tessaly Pharma"
EU, JP, US_CA = frozenset({"EU"}), frozenset({"JP"}), frozenset({"US", "CA"})


def _quoted(event: r.RightsEvent, quote: str) -> r.RightsEvent:
    return event.model_copy(update={"evidence_quote": quote})


def _not_top(v) -> None:
    assert v.tier not in TOP, (v.tier, v.position, v.top_tier_blockers)


# PF1: "U.S." inside a party span or after a comma is a place, read as written.
PF1 = ["Licensed to Tessaly Pharma (U.S.) and to Chinaco Pharma in China",
       "China license to Chinaco Pharma, with Tessaly Pharma for the U.S.",
       "Licensed in China to Tessaly Pharma, also covering the U.S.",
       "Licensed in Greater China to Chinaco Pharma, which holds the U.S. too"]


@pytest.mark.parametrize("text", PF1)
def test_pf1_a_us_mention_after_the_party_is_never_a_grant_over_other_places(text):
    assert plain_form(text, "Origin Bio") is None


@pytest.mark.parametrize("text", PF1)
@pytest.mark.parametrize("field", ["us_rights", "geographic_rights", "partnerships"])
def test_pf1_the_text_keeps_a_china_license_out_of_the_top_tiers(text, field):
    _not_top(run([ev(L, **CHINA)], landscape=(cell(field, text, src="2025-04-01"),)))
    _not_top(run([ev(L, **CHINA)], analysts=(analyst(field, text),)))


# PF2: a pronoun or "the owner" is not the company.
@pytest.mark.parametrize("text", ["Licensed to Tessaly Pharma in Japan; it holds U.S. rights",
                                  "Japan license to Tessaly Pharma; it retains U.S. rights",
                                  "The owner holds U.S. rights", "Owner retains U.S. rights"])
def test_pf2_a_pronoun_or_role_subject_is_not_the_company(text):
    assert plain_form(text, "Origin Bio") is None
    for field in ("us_rights", "geographic_rights", "partnerships"):
        _not_top(run([ev(L, **CHINA)], landscape=(cell(field, text, src="2025-04-01"),)))


def test_pf2_a_single_clause_text_with_we_still_reads_as_the_company():
    assert plain_form("We retain all U.S. rights", "Origin Bio") == "rights kept by the company"


# PF3: a note inside the text is refused, not dropped.
@pytest.mark.parametrize("text", ["Rights retained by Origin Bio (Tessaly Pharma holds U.S.)",
                                  "U.S. rights were returned to Origin Bio (on behalf of Tessaly Pharma) in 2024",
                                  "Wholly owned by Origin Bio [U.S. sublicensed to Tessaly Pharma]",
                                  "U.S. rights were returned to Origin Bio Inc. (Tessaly) in 2024"])
def test_pf3_a_note_inside_the_text_is_not_a_plain_form(text):
    assert plain_form(text, "Origin Bio") is None
    for field in ("us_rights", "geographic_rights", "partnerships"):
        _not_top(run([ev(L, **CHINA)], landscape=(cell(field, text, src="2025-04-01"),)))


@pytest.mark.parametrize("text", ["Origin Bio retains all rights (ex-China)", "U.S. rights returned to Origin Bio (2024)",
                                  "Seeking partner(s) for U.S. rights"])
def test_pf3_a_year_an_excluded_place_or_a_plural_is_not_a_note(text):
    assert plain_form(text, "Origin Bio") is not None


# PF4: "other places" is read against the buyer territory, not against the U.S.
@pytest.mark.parametrize(("territory", "text"), [
    (EU, "Licensed in Europe to Tessaly Pharma"), (EU, "EU license to Tessaly Pharma"),
    (EU, "Ex-Europe rights available"), (US_CA, "Licensed in Canada to Tessaly Pharma"),
    (JP, "Licensed in Japan to Kappa Ltd")])
def test_pf4_a_grant_in_the_buyers_own_territory_is_not_other_places(territory, text):
    assert plain_form(text, "Origin Bio", territory=territory) is None
    _not_top(run([ev(L, **CHINA)], landscape=(cell("geographic_rights", text, src="2025-04-01"),),
                 territory=territory))


def test_pf4_the_same_grant_is_other_places_for_a_us_buyer():
    assert plain_form("Licensed in Europe to Tessaly Pharma", "Origin Bio") == "a grant over other places only"


def test_pf4_an_eu_availability_row_beside_an_eu_license_text_is_not_tier_0():
    v = run([ev(AV, territory="Europe", d="2025-03-01")],
            analysts=(analyst("us_rights", "Licensed in Europe to Tessaly Pharma"),), territory=EU)
    _not_top(v)


# The reader leaves a text unread: the plain form does not widen it (REREVIEW5 section 2a, last cause).
@pytest.mark.parametrize("text", ["China license to Chinaco Pharma, with Tessaly Pharma for the U.S.",
                                  "Licensed to Tessaly Pharma in Japan; it holds U.S. rights"])
def test_unread_landscape_us_rights_text_blocks_as_in_revision_5(text):
    v = run([ev(L, **CHINA)], landscape=(cell("us_rights", text, src="2025-04-01"),))
    assert v.tier == UNRESOLVED or v.position == rp.P_CONFLICTING


# OWN: ownership words are rights words.
@pytest.mark.parametrize("text", ["Owned by Tessaly Pharma", "Bought by Tessaly Pharma", "Tessaly Pharma (owner)",
                                  "Merged into Tessaly Pharma", "Spun out to Tessaly Pharma",
                                  "Subsidiary of Tessaly Pharma"])
def test_own_ownership_words_are_read_as_rights_evidence(text):
    assert is_rights_text(text)
    v = run([ev(L, **CHINA)], analysts=(analyst("partnerships", text),))
    _not_top(v)
    assert any(text in b for b in v.top_tier_blockers)


def test_own_a_names_only_partnerships_value_stays_neutral():
    assert not is_rights_text("Tessaly Pharma; Chinaco Pharma")
    assert run([ev(L, **CHINA)], analysts=(analyst("partnerships", "Tessaly Pharma; Chinaco Pharma"),)).tier == TIER1


# QUOTE: a rights row's own quote is read.
def test_quote_an_availability_rows_quote_naming_a_third_party_option_blocks():
    row = _quoted(ev(AV, **STATED), "(test) Origin Bio: U.S. rights available after Tessaly Pharma's option "
                                    "expires in 2027")
    v = run([row])
    _not_top(v)
    assert blocked(v, "the quote on rights row")
    assert any("quote" in q for q in v.questions)


def test_quote_a_china_licence_quote_naming_a_us_option_blocks():
    row = _quoted(ev(L, **CHINA), "(test) Chinaco Pharma licenses China rights and an option on U.S. rights")
    _not_top(run([row]))


def test_quote_a_plain_availability_quote_still_reaches_tier_0():
    row = _quoted(ev(AV, **STATED), "Origin Bio: U.S. rights available")
    assert run([row]).tier == TIER0


def test_quote_a_china_licence_quote_that_names_only_china_stays_tier_1():
    row = _quoted(ev(L, **CHINA), "Chinaco Pharma licenses rights in mainland China")
    assert run([row]).tier == TIER1


# TER-M: a buyer territory containing the U.S. keeps the U.S.-rights field's encumbrances.
def test_ter_m_a_us_license_cell_still_encumbers_a_us_and_ca_buyer():
    v = run([], landscape=(cell("us_rights", "Exclusive U.S. license to Tessaly Pharma (2024)", src="2025-04-01"),),
            territory=US_CA)
    _not_top(v)
    assert any("part of the buyer territory" in x for x in v.reasons) or v.position != rp.P_NONE


def test_ter_m_an_available_cell_is_not_a_clear_position_for_a_us_and_ca_buyer():
    v = run([], landscape=(cell("us_rights", "U.S. rights available", src="2025-04-01"),), territory=US_CA)
    _not_top(v)


# ORCD: "or" joins offers; "co-development" in an offer is not a grant.
def test_orcd_an_offer_with_or_is_read_as_an_offer():
    reading = rights_reading("Available for out-licensing or co-development")
    assert reading.status == AVAILABLE and reading.understood
    assert run([], analysts=(analyst("us_rights", "Available for out-licensing or co-development"),)).tier == TIER0


# S2: an ending stated only by a status, with no source date, is not placed before the as-of date.
def test_s2_a_terminated_status_with_no_source_date_blocks():
    row = ev(L, grantee="Alpha Bio", territory="United States", d="2025-03-01", status="TERMINATED")
    v = run([row])
    _not_top(v)
    assert blocked(v, "which no source date places before the as-of date")


def test_s2_a_terminated_status_with_a_source_date_before_as_of_is_applied():
    row = ev(L, grantee="Alpha Bio", territory="United States", d="2024-03-01", status="TERMINATED",
             src="2025-05-01")
    assert run([row]).tier == TIER1


# NH: a noted name is not printed as holder or owner.
def test_nh_a_noted_return_recipient_is_not_the_holder():
    rows = [ev(L, grantee="Alpha Bio", territory="United States", d="2024-03-01", deal="D1"),
            ev(RR_KIND, grantee="Origin Bio (on behalf of Tessaly Pharma)", grantor="Alpha Bio",
               territory="United States", d="2025-02-01", deal="D1")]
    v = run(rows)
    _not_top(v)
    assert "on behalf of" not in (v.holder or "")


RR_KIND = r.RIGHTS_RETURNED


# Hong Kong and other two-word places inside a legal name are not notes; a two-word partner is.
@pytest.mark.parametrize(("name", "note"), [("Origin Bio (Hong Kong) Limited", ""),
                                            ("Origin Bio (Suzhou) Co., Ltd.", ""),
                                            ("Origin Bio (Tessaly Pharma) Inc.", "Tessaly Pharma")])
def test_two_word_place_in_a_legal_name(name, note):
    assert content_note(name) == note


def test_hong_kong_company_statement_reaches_tier_0():
    assert run([ev(AV, grantor="Origin Bio (Hong Kong) Limited", **STATED)],
               company="Origin Bio (Hong Kong) Limited").tier == TIER0


# Usefulness: ordinary offers REREVIEW5 found held back.
@pytest.mark.parametrize("text", ["Partnered in China; U.S. rights available", "Worldwide rights (ex-China) available",
                                  "Seeking partner(s) for development and commercialization outside China",
                                  "Open to partnering discussions", "Open to co-promotion in the U.S."])
def test_usefulness_ordinary_offers_beside_a_china_license_reach_tier_1(text):
    assert plain_form(text, "Origin Bio") is not None
    assert run([ev(L, **CHINA)], landscape=(cell("us_rights", text, src="2025-04-01"),)).tier == TIER1


# R9: a company's unrelated deal guards its programs only if the deal may reach the buyer territory.
def _row(territory: str | None) -> r.RightsEvent:
    return ev(L, grantor="Big Pharma AB", grantee=OTHER, territory=territory).model_copy(
        update={"external_id": "AZ-904"})


def _guarded(guards, key: str = "P1") -> bool:
    return bool(guards.per_program.get(key))


def test_r9_a_company_deal_in_another_place_guards_nothing():
    guards = row_guards({"P1", "P2"}, [_row("mainland China")], [], {"P1": "Big Pharma AB", "P2": "Big Pharma AB"},
                        frozenset({"US"}))
    assert not _guarded(guards, "P1") and not _guarded(guards, "P2")


@pytest.mark.parametrize("territory", ["United States", None, "Worldwide"])
def test_r9_a_company_deal_that_may_reach_the_buyer_territory_guards_its_programs(territory):
    guards = row_guards({"P1"}, [_row(territory)], [], {"P1": "Big Pharma AB"}, frozenset({"US"}))
    assert _guarded(guards)


# L3b: the CLI note gives the gate's verdict in the buyer territory, and the unread rule.
def test_l3b_the_note_reads_the_buyer_territory():
    from bve.cli.dealscreen import rights_reading_note

    note = rights_reading_note("Licensed to Tessaly Pharma (U.S.) and to Chinaco Pharma in China", "Origin Bio",
                               "geographic_rights")
    assert "not one of the plain forms" in note
    eu = rights_reading_note("Licensed in Europe to Tessaly Pharma", "Origin Bio", "geographic_rights", EU)
    assert "not one of the plain forms" in eu and "(EU)" in eu
    assert "names of organisations only" not in rights_reading_note("Owned by Tessaly Pharma", "Origin Bio",
                                                                    "partnerships")


def test_l3b_an_unread_us_rights_text_with_a_plain_form_gets_the_gates_verdict():
    from bve.cli.dealscreen import rights_reading_note

    note = rights_reading_note("Licensed to Tessaly Pharma in Japan; it holds U.S. rights", "Origin Bio")
    assert "cannot read all of it" in note and "not one of the plain forms" in note


def test_termination_kind_is_still_imported():  # keeps the shared helper import honest
    assert T == r.TERMINATION


@pytest.mark.parametrize("label", [" (shared)", " (recorded; conflicting)"])
def test_nh_dealscreens_own_holder_labels_are_not_notes(label):
    from bve.dealscreen.rights_position import RightsPosition
    from bve.dealscreen.screening import _drop_noted_names

    position = RightsPosition(rp.P_SHARED, holder="Alpha Bio and Beta Bio" + label)
    _drop_noted_names(position)
    assert position.holder == "Alpha Bio and Beta Bio" + label
