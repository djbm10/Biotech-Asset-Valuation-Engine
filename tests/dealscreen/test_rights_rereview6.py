"""Cycle R1 revision 8: the inputs from adversarial re-review 6 (research/dealscreen_rights_v1/REREVIEW6.md).

Revision 8 reads a "grant over other places only" party as a name and nothing else (PLACE), keeps a quote's prefix
unless it is the row's grantor or the company speaking (SPK), reads a quote's options and wider territories clause by
clause (QW), requires an offer that names places to cover the buyer territory (QT), and judges an ending dated only to
a year or month by the end of that period (DATE). Each test is tagged with its review id.

Defaults as in ``test_rights_rereview3``: buyer territory US, as-of 2025-06-01, company and licensor "Origin Bio".
Parties are fictional; the tests assert no real-world facts."""

from __future__ import annotations

import pytest
from test_rights_rereview3 import (
    AQ,
    AV,
    CHINA,
    STATED,
    TIER0,
    TIER1,
    TOP,
    L,
    T,
    analyst,
    blocked,
    cell,
    ev,
    run,
)

from bve.dealscreen.rights_allow import plain_form

EU, JP, US_CA = frozenset({"EU"}), frozenset({"JP"}), frozenset({"US", "CA"})
US_LIC = {"grantee": "Alpha Bio", "territory": "United States", "d": "2024-03-01", "deal": "D1"}


def _quoted(event, quote: str):
    return event.model_copy(update={"evidence_quote": quote})


def _not_top(v) -> None:
    assert v.tier not in TOP, (v.tier, v.position, v.top_tier_blockers)


# PLACE: the party of a grant over other places is a name and nothing else.
PLACE = ["Licensed in China to Chinaco Pharma and in the Americas to Tessaly Pharma",
         "Licensed in China to Chinaco Pharma, which sells in the Americas",
         "Licensed in China to Chinaco Pharma and in the rest of the world to Tessaly Pharma",
         "Licensed in China to Chinaco Pharma and for ROW to Tessaly Pharma",
         "Licensed in China to Chinaco Pharma in California",
         "Licensed in China to Chinaco Pharma and elsewhere to Tessaly Pharma",
         "Licensed in China to Chinaco Pharma - Tessaly Pharma has the rest",
         "Licensed for China to Chinaco Pharma for sales in all of America",
         "Licensed in China to Chinaco Pharma Americas"]


@pytest.mark.parametrize("text", PLACE)
def test_place_more_text_after_the_party_is_not_a_grant_over_other_places(text):
    assert plain_form(text, "Origin Bio") is None


@pytest.mark.parametrize("text", PLACE[:4])
@pytest.mark.parametrize("field", ["us_rights", "geographic_rights", "partnerships"])
def test_place_texts_keep_a_china_license_out_of_the_top_tiers(text, field):
    _not_top(run([ev(L, **CHINA)], landscape=(cell(field, text, src="2025-04-01"),)))


def test_place_beside_an_availability_statement_is_not_tier_0():
    text = "Licensed in China to Chinaco Pharma and in the rest of the world to Tessaly Pharma"
    _not_top(run([], analysts=(analyst("us_rights", "U.S. rights available"),),
                 landscape=(cell("geographic_rights", text, src="2025-04-01"),)))
    _not_top(run([ev(AV, **STATED)], landscape=(cell("geographic_rights", text, src="2025-04-01"),)))


@pytest.mark.parametrize(("territory", "text"), [
    (EU, "Licensed in China to Chinaco Pharma and in France to Tessaly Pharma"), (EU, "Licensed in France to Tessaly"),
    (JP, "Licensed in Korea to Kappa Ltd and in Asia to Tessaly"), (JP, "Licensed in Asia to Kappa Ltd"),
    (US_CA, "Licensed in China to Chinaco Pharma and in Ontario to Tessaly Pharma")])
def test_place_unknown_places_for_other_buyers(territory, text):
    assert plain_form(text, "Origin Bio", territory=territory) is None
    _not_top(run([ev(L, **CHINA)], landscape=(cell("geographic_rights", text, src="2025-04-01"),),
                 territory=territory))


@pytest.mark.parametrize("text", ["Licensed in Greater China to Chinaco Pharma",
                                  "Exclusive China license to Chinaco Pharma Co., Ltd.",
                                  "Licensed to Chinaco Pharma for Japan", "Licensed in China to Chinaco Pharma only",
                                  "Licensed in China only"])
def test_place_a_plain_grant_over_other_places_still_passes(text):
    assert plain_form(text, "Origin Bio") == "a grant over other places only"


# SPK: only the row's grantor or the company may be stripped as a speaker.
@pytest.mark.parametrize("quote", ["Subject to Tessaly Pharma consent: U.S. rights available",
                                   "After Tessaly Pharma's U.S. option expires in 2027: U.S. rights available",
                                   "Tessaly Pharma: U.S. rights available"])
def test_spk_a_prefix_that_is_not_the_company_is_read(quote):
    v = run([_quoted(ev(AV, **STATED), quote)])
    _not_top(v)
    assert blocked(v, "the quote on rights row")


@pytest.mark.parametrize("quote", ["Origin Bio: U.S. rights available", "Origin Bio Inc.: U.S. rights available"])
def test_spk_the_company_speaking_is_still_stripped(quote):
    assert run([_quoted(ev(AV, **STATED), quote)]).tier == TIER0


# QW: options and wider territories in a non-availability row's quote.
@pytest.mark.parametrize("quote", ["Chinaco Pharma licenses China rights and an option on worldwide rights",
                                   "Chinaco Pharma licenses China rights and an option on North American rights",
                                   ("Chinaco Pharma licenses China rights and a right of first negotiation for the rest "
                                   "of the world"),
                                   "Chinaco Pharma licenses China rights; global rights to follow"])
def test_qw_an_option_or_wider_territory_in_a_quote_blocks(quote):
    v = run([_quoted(ev(L, **CHINA), quote)])
    _not_top(v)
    assert blocked(v, "the quote on rights row")


@pytest.mark.parametrize("quote", ["Chinaco Pharma licenses China rights; Origin Bio retains U.S. rights",
                                   "Chinaco Pharma licenses China rights; Origin Bio retains all rights outside China",
                                   "Chinaco Pharma licenses rights in mainland China, Hong Kong and Macau"])
def test_qw_a_quote_confirming_the_company_kept_its_rights_passes(quote):
    assert run([_quoted(ev(L, **CHINA), quote)]).tier == TIER1


def test_qw_a_row_whose_own_territory_covers_the_buyer_is_read_by_the_ledger_not_the_quote():
    v = run([_quoted(ev(L, **US_LIC), "Alpha Bio licenses U.S. rights with an option on global rights")])
    _not_top(v)


# QT: an offer that names places must cover the buyer territory.
def test_qt_a_us_offer_is_not_an_offer_to_an_eu_buyer():
    assert plain_form("U.S. rights available", "Origin Bio", territory=EU) is None
    row = _quoted(ev(AV, territory="Europe", d="2025-03-01"), "Origin Bio: U.S. rights available")
    _not_top(run([row], territory=EU))


def test_qt_a_us_offer_covers_only_part_of_a_us_and_ca_buyer():
    assert plain_form("U.S. rights available", "Origin Bio", territory=US_CA) is None


@pytest.mark.parametrize("text", ["U.S. rights available", "Ex-China rights available", "Seeking a partner",
                                  "Open to co-promotion in the U.S."])
def test_qt_offers_to_a_us_buyer_still_pass(text):
    assert plain_form(text, "Origin Bio") == "an offer"


# DATE: an ending dated only to a year or month that contains the as-of date may come after it.
@pytest.mark.parametrize("events", [
    [ev(L, **US_LIC), ev(T, grantee="Alpha Bio", d="2025", deal="D1")],
    [ev(L, **US_LIC), ev(T, grantee="Alpha Bio", d="2025-06", deal="D1")],
    [ev(L, grantee="Alpha Bio", territory="United States", d="2024-03-01", status="TERMINATED", src="2025")],
    [ev(L, grantee="Alpha Bio", territory="United States", d="2024-03-01", status="TERMINATED", src="2025-06")],
    [ev(AQ, grantor="Origin Bio", grantee="Omega Holdings", d="2025"), ev(L, **CHINA)],
])
def test_date_an_ending_dated_to_a_period_containing_the_as_of_date_does_not_clear(events):
    _not_top(run(events))


def test_date_the_straddling_record_is_reported_with_a_question():
    v = run([ev(L, **US_LIC), ev(T, grantee="Alpha Bio", d="2025", deal="D1")])
    assert any("period that contains the as-of date" in r for r in v.reasons)


@pytest.mark.parametrize("events", [
    [ev(L, **{**US_LIC, "d": "2023-03-01"}), ev(T, grantee="Alpha Bio", d="2024", deal="D1")],
    [ev(L, **US_LIC), ev(T, grantee="Alpha Bio", d="2025-05", deal="D1")],
    [ev(L, grantee="Alpha Bio", territory="United States", d="2024-03-01", status="TERMINATED", src="2025-05")],
])
def test_date_an_ending_whose_whole_period_is_before_the_as_of_date_still_clears(events):
    assert run(events).tier == TIER1
