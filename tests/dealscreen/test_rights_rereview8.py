"""Cycle R1 revision 10: the inputs from adversarial re-review 8 (research/dealscreen_rights_v1/REREVIEW8.md).

Revision 10 replaces the quote reader's deny-lists with a fail-closed reader (``rights_quote``): every capitalised name
in a cited quote must be placed (a row party, the program's company, the program, a place, a person, an adviser or a
news source), and the clause may use only the rights words that restate its own row. Time and hedge words block an
ending; wide words and extra places block a row that does not cover the buyer territory (PARTY2, HEDGE2, WIDER2, WN).
Party names refuse place, area and signal words (PN3). A future-dated grant blocks unless its source shows it was
reported after the as-of date (FUT2). An acquisition of a party in no grant blocks (ACQ-X). Each test is tagged with
its review id.

Defaults as in ``test_rights_rereview3``: buyer territory US, as-of 2025-06-01, company and licensor "Origin Bio"
(the review's "Nerida Bio"). Parties are fictional; the tests assert no real-world facts."""

from __future__ import annotations

from datetime import date

import pytest
from test_rights_rereview3 import (
    AQ,
    AV,
    CHINA,
    OL,
    PREFS,
    STATED,
    TIER1,
    TOP,
    L,
    O,
    T,
    analyst,
    blocked,
    cell,
    ev,
    run,
)

from bve.dealscreen import rights_position as rp
from bve.dealscreen.commercial import assess
from bve.dealscreen.models import LandscapeAsset
from bve.dealscreen.rights_allow import plain_form
from bve.dealscreen.screening import program_transaction

US_LIC = {"grantee": "Alpha Bio", "territory": "United States", "d": "2024-03-01", "deal": "D1"}
TUS = {"grantee": "Tessaly Pharma", "territory": "United States"}


def _quoted(event, quote: str):
    return event.model_copy(update={"evidence_quote": quote})


def _not_top(v) -> None:
    assert v.tier not in TOP, (v.tier, v.position, v.top_tier_blockers)


def _term(quote: str, kind: str = T):
    end = ev(kind, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D1")
    return [ev(L, **US_LIC), _quoted(end, quote)]


def _china(quote: str):
    return [_quoted(ev(L, **CHINA), quote)]


def _lapse(quote: str):
    option = ev(O, grantee="Alpha Bio", territory="United States", d="2024-03-01", deal="D2")
    end = ev(OL, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D2")
    return [option, _quoted(end, quote)]


def _acq(quote: str, grantor: str = "Origin Bio"):
    buy = ev(AQ, grantee="Omega Holdings", grantor=grantor, territory="Worldwide", d="2025-02-01")
    return [ev(L, **CHINA), _quoted(buy, quote)]


def _run_at(events, as_of: date):
    asset = LandscapeAsset(asset_id="A1", source_system="T", external_id="P1", program_name="Prog",
                           company="Origin Bio", row_numbers=[1], claims=[])
    commercial = assess(asset, questions=["Q?"], confirmed_findings=())
    return program_transaction(events, commercial, company="Origin Bio", territory=frozenset({"US"}), as_of=as_of,
                               max_age_days=730, prefs=PREFS)


# -- PARTY2: every capitalised name in a cited quote must be placed --------------------------------------------------
RETURN = "Alpha Bio returns U.S. rights to Origin Bio"
PARTY2 = [f"{RETURN}; U.S. rights are now held by Tessaly",                                       # A1
          f"{RETURN}, which has since licensed them to a new partner",                            # A3
          f"{RETURN}; Tessaly will commercialize NB-7 in the U.S.",                               # A4
          f"{RETURN}; NB-7 is partnered with Tessaly in the U.S.",                                # A5
          f"{RETURN}; U.S. rights now belong to Tessaly",                                         # A6
          f"{RETURN}; U.S. rights are now held by a subsidiary of Tessaly Pharma",                # A8
          f"{RETURN}; an affiliate of Tessaly Pharma holds U.S. rights",                          # A9
          f"{RETURN}; Tessaly's U.S. license is unaffected",                                      # A10
          f"{RETURN}; Tessaly co-commercializes NB-7 in the U.S.",                                # A11
          f"{RETURN}; U.S. rights were acquired by Tessaly",                                      # A12
          f"{RETURN}; U.S. commercialization is led by Tessaly",                                  # A13
          f"{RETURN}; the U.S. licensee is TPC",                                                  # A14
          f"{RETURN}; U.S. licensee: Tessaly",                                                    # A15
          f"{RETURN}; Tessaly, which signed in 2024, keeps them",                                 # A16
          "U.S. rights revert to Origin Bio, which granted them to Tessaly in 2025",              # A17
          f"{RETURN}; the program is now in-licensed by Tessaly in the U.S.",                     # A18
          f"{RETURN}; Origin Bio signed a U.S. deal with Tessaly"]                                # A19


@pytest.mark.parametrize("quote", PARTY2)
def test_party2_a_return_quote_naming_any_other_holder_blocks(quote):
    v = run(_term(quote))
    _not_top(v)
    assert blocked(v, "the quote on rights row")


def test_party2_the_question_names_the_unplaced_party():
    v = run(_term(f"{RETURN}; U.S. rights are now held by Tessaly"))
    assert blocked(v, "Tessaly")


@pytest.mark.parametrize("quote", ["Chinaco Pharma licenses China rights; Tessaly's license to NB-7 is unaffected",
                                   "Chinaco Pharma licenses China rights; Origin Bio's other partner for NB-7 is Tessaly",
                                   ("Chinaco Pharma licenses China rights; an affiliate of Tessaly Pharma holds a "
                                    "license to NB-7"),
                                   "Chinaco Pharma licenses China rights; NB-7 is also partnered with Tessaly",
                                   "Chinaco Pharma licenses China rights; co-exclusive with kappa bio"])
def test_party2_w1_w4_w27_a_china_licence_naming_another_partner_blocks(quote):
    _not_top(run(_china(quote)))


def test_party2_b20_an_acquisition_quote_naming_a_holder_blocks():
    _not_top(run(_acq("Omega Holdings acquires Origin Bio; U.S. rights to NB-7 are held by Tessaly")))


# -- HEDGE2: an ending that is later, conditional, partial or disputed blocks -------------------------------------
HEDGE2 = ["Alpha Bio will return U.S. rights to Origin Bio on 1 January 2026",                     # B1
          "Alpha Bio gave notice to terminate; termination takes effect in 2026",                  # B2
          "Alpha Bio returns U.S. rights to Origin Bio, with the exception of co-promotion rights",  # B3
          "Alpha Bio returns U.S. rights to Origin Bio effective on 1 March 2026",                 # B4
          "Alpha Bio intends to return U.S. rights to Origin Bio",                                 # B5
          "Alpha Bio and Origin Bio are negotiating the return of U.S. rights",                    # B6
          "Alpha Bio returns most U.S. rights to Origin Bio",                                      # B7
          "Alpha Bio returns U.S. rights to Origin Bio, apart from co-promotion rights",           # B8
          "Alpha Bio returns U.S. rights to Origin Bio; Alpha Bio will still co-promote NB-7",     # B9
          "Alpha Bio returns U.S. rights to Origin Bio; the termination is disputed by Alpha Bio",  # B10
          "Alpha Bio may terminate the U.S. license",                                              # B11
          "Alpha Bio served a 180-day termination notice on the U.S. license",                     # B12
          "Alpha Bio returns U.S. rights to Origin Bio and will stay on as U.S. co-promotion partner",  # B13
          "Alpha Bio returns U.S. rights to Origin Bio; Alpha Bio has started arbitration over the termination"]  # B14


@pytest.mark.parametrize("quote", HEDGE2)
def test_hedge2_an_ending_not_yet_whole_or_in_effect_blocks(quote):
    _not_top(run(_term(quote)))


def test_hedge2_b15_an_extended_option_is_not_a_lapse():
    _not_top(run(_lapse("Alpha Bio's U.S. right was extended by twelve months")))


# -- WIDER2, WN: a China licence quote that reaches further blocks -------------------------------------------------
WIDER2 = ["Chinaco Pharma licenses China rights and also receives an exclusive option",            # W5 (WN)
          "Chinaco Pharma licenses China rights and holds a license in other major markets",       # W6
          "Chinaco Pharma licenses rights in China and in other countries",                        # W7
          "Chinaco Pharma licenses rights in China and other markets",                             # W8
          "Chinaco Pharma licenses China rights and may add additional territories",               # W9
          "Chinaco Pharma licenses rights in China and everywhere else",                           # W10
          "Chinaco Pharma licenses China rights with first negotiation on any other territory",    # W11
          "Chinaco Pharma licenses China rights and may opt into further countries",               # W12
          "Chinaco Pharma licenses China rights and international development and commercial rights",  # W14 (WN)
          "Chinaco Pharma licenses rights in mainland China and Puerto Rico",                      # W15
          "Chinaco Pharma licenses rights in mainland China and Guam",                             # W16
          "Chinaco Pharma licenses rights in China and NA",                                        # W17
          "Chinaco Pharma licenses China rights, with expansion rights",                           # W18
          "Chinaco Pharma licenses rights in all markets",                                         # W19
          "Chinaco Pharma licenses rights in China and the rest of the globe",                     # W20
          "Chinaco Pharma licenses rights in China; the remainder of the world goes to Chinaco Pharma in 2026",  # W21
          "Chinaco Pharma licenses China rights; tessaly pharma licenses the remaining rights",    # W22
          "Chinaco Pharma licenses China and Hawaii rights",                                       # W23
          "Chinaco Pharma licenses China rights and has an option to expand"]                      # W26 (WN)


@pytest.mark.parametrize("quote", WIDER2)
def test_wider2_a_china_licence_quote_reaching_further_blocks(quote):
    _not_top(run(_china(quote)))


# -- PN3: a party name holds no place, area or signal word -------------------------------------------------------
PN3 = [f"Licensed in China to Chinaco Pharma, Tessaly Pharma {tail}"
       for tail in ("Everywhere Else", "EVERYWHERE ELSE", "Otherwise", "Remainder", "Beyond", "North",
                    "Western Hemisphere", "ROTW", "WW", "Upon Exercise", "Thereafter", "Thereon", "Pre-Emption",
                    "Veto", "NA", "Delaware", "Inc., New Jersey", "TBD")]
PN3 += ["Licensed in China to Chinaco Pharma Plus Tessaly Pharma", "Licensed in China to Chinaco Pharma TBD"]


@pytest.mark.parametrize("text", PN3)
def test_pn3_a_place_area_or_signal_word_is_not_a_party_name(text):
    assert plain_form(text, "Origin Bio") is None


@pytest.mark.parametrize("text", PN3[:2] + PN3[9:10])
def test_pn3_the_text_as_a_cell_or_assertion_keeps_the_program_out_of_the_top_tiers(text):
    _not_top(run([ev(L, **CHINA)], landscape=(cell("geographic_rights", text, src="2025-04-01"),)))
    _not_top(run([ev(L, **CHINA)], analysts=(analyst("geographic_rights", text),)))


def test_pn3_tier_0_path_is_closed():
    _not_top(run([ev(L, **CHINA), ev(AV, **STATED)], analysts=(analyst("geographic_rights", PN3[0]),)))


@pytest.mark.parametrize("text", ["Licensed in China to Chinaco Pharma", "Licensed in China to Chinaco Pharma Group",
                                  "Licensed in China to Chinaco Pharma kk", "Licensed in mainland China to Chinaco Pharma"])
def test_pn3_plain_corporate_forms_still_pass(text):
    assert plain_form(text, "Origin Bio") == "a grant over other places only"


# -- FUT2: a grant effective after the as-of date blocks unless reported after it ------------------------------------
@pytest.mark.parametrize("src", [None, "2025", "2025-06"])
def test_fut2_a_future_grant_not_shown_reported_later_blocks(src):
    v = run([ev(L, **CHINA), ev(L, **TUS, d="2025-07-01", src=src)])
    _not_top(v)
    assert blocked(v, "may have been agreed by the as-of date")
    assert any("was it agreed by 2025-06-01" in q for q in v.questions)  # Q-FUT2


def test_fut2_e1b_tier_0_path_is_closed():
    _not_top(run([ev(L, **CHINA), ev(L, **TUS, d="2025-07-01"), ev(AV, **STATED)]))


def test_fut2_e7_live_use_a_future_deal_date_with_no_source_date_blocks():
    v = _run_at([ev(L, **{**CHINA, "d": "2026-01-01"}), ev(L, **TUS, d="2027-01-01")], date(2026, 11, 2))
    _not_top(v)


def test_fut2_e8_a_future_grant_outside_the_buyer_territory_does_not_block():
    later = ev(L, grantee="Kappa KK", territory="Japan", d="2025-07-01", src="2025-05-20")
    assert run([ev(L, **CHINA), later]).tier == TIER1


def test_fut2_a_grant_reported_after_the_as_of_date_still_does_not_block():
    v = run([ev(L, **CHINA), ev(L, **TUS, d="2025-07-01", src="2025-06-20")])
    assert not blocked(v, "may have been agreed by the as-of date")


# -- LBL-NONE: rows recorded, none applied --------------------------------------------------------------------------
def test_lbl_none_rows_recorded_but_none_applied_is_its_own_position():
    v = run([ev(L, **TUS, d="2025-07-01", src="2025-05-20")])
    _not_top(v)
    assert v.position == rp.P_NOT_APPLIED
    assert any("none applies on the as-of date" in x for x in v.reasons)


# -- ACQ-X: an acquisition of a party in no grant ---------------------------------------------------------------------
@pytest.mark.parametrize("quote", ["Omega Holdings acquires Sideco Bio, which holds U.S. rights to NB-7",
                                   "Omega Holdings acquires Sideco Bio"])
def test_acq_x_f1_an_acquired_party_in_no_grant_blocks_and_is_asked_about(quote):
    v = run(_acq(quote, grantor="Sideco Bio"))
    _not_top(v)
    assert blocked(v, "names neither the program's company nor a party to a recorded grant")
    assert any("What rights to this program did Sideco Bio hold" in q for q in v.questions)


def test_acq_x_f3_on_the_returned_path():
    buy = ev(AQ, grantee="Omega Holdings", grantor="Sideco Bio", territory="Worldwide", d="2025-02-01")
    _not_top(run(_term(RETURN) + [buy]))


# -- Usefulness: clean press wording stays in the top tiers --------------------------------------------------------
CLEAN_CHINA = ["Origin Bio granted Chinaco Pharma exclusive rights to NB-7 in mainland China",          # G1
               "Origin Bio licensed China rights to NB-7 to Chinaco Pharma",                            # G2
               ("Origin Bio, Inc. (Nasdaq: ORGN) today announced an exclusive license agreement with Chinaco Pharma "
                "Co., Ltd. for the development and commercialization of NB-7 in mainland China, Hong Kong, Macau "
                "and Taiwan"),                                                                           # G3
               "Under the agreement, Chinaco Pharma will pay Origin Bio an upfront payment of $20 million",  # G4
               "Chinaco Pharma obtains exclusive rights to develop and commercialize NB-7 in mainland China",  # G10
               "Origin Bio transferred China rights to NB-7 to Chinaco Pharma",                         # G11
               "Chinaco Pharma, a subsidiary of Chinaco Group, licenses NB-7 for mainland China",        # G13
               "NERIDA BIO LICENSES NB-7 TO CHINACO PHARMA IN MAINLAND CHINA".replace("NERIDA", "ORIGIN")]  # U3


@pytest.mark.parametrize("quote", CLEAN_CHINA)
def test_usefulness_a_clean_china_licence_quote_stays_tier_1(quote):
    v = run(_china(quote))
    assert v.tier == TIER1, v.top_tier_blockers


CLEAN_ENDS = ["Alpha Bio terminated its license; all rights to NB-7 revert to Origin Bio",                # C1
              "Following a portfolio review, Alpha Bio returned U.S. rights to NB-7 to Origin Bio",       # C2
              "Alpha Bio returned U.S. rights to Origin Bio after a strategic review",                    # C3
              "Origin Bio regains full global rights to NB-7 after Alpha Bio exits",                      # C4
              ("Alpha Bio terminated the agreement for convenience; U.S. rights reverted to Origin Bio on 15 "
               "January 2025"),                                                                           # C8
              "Alpha Bio Inc. returns U.S. rights to Origin Bio Co., Ltd.",                               # C11
              f"{RETURN}; Harlow Partners LLC advised Origin Bio",                                        # C13
              "Alpha Bio Returns U.S. Rights to NB-7 to Origin Bio"]                                      # U4


@pytest.mark.parametrize("quote", CLEAN_ENDS)
def test_usefulness_a_clean_ending_quote_stays_tier_1(quote):
    v = run(_term(quote))
    assert v.tier == TIER1, v.top_tier_blockers


@pytest.mark.parametrize("quote", ["Alpha Bio did not exercise its option on U.S. rights to NB-7",           # B16
                                   "Alpha Bio declined to take up U.S. rights to NB-7",                       # B17
                                   "Alpha Bio's option on U.S. rights to NB-7 expired unexercised"])         # U8
def test_usefulness_a_clean_lapse_quote_stays_tier_1(quote):
    v = run(_lapse(quote))
    assert v.tier == TIER1, v.top_tier_blockers


@pytest.mark.parametrize("quote", ["Omega Holdings completes acquisition of Origin Bio",                     # C15
                                   ("Omega Holdings acquires Origin Bio; Harlow Partners LLC is acting as financial "
                                    "advisor to Origin Bio"),                                                 # C18
                                   "Omega Holdings completes acquisition of Origin Bio, Inc. (Nasdaq: ORGN)",  # C19
                                   # real press shape (revision 10 measurement): a currency code, a future-tense deal
                                   ("Under the agreement, Omega Holdings will pay EUR 422 million to acquire 100% of "
                                    "the equity in Origin Bio.")])
def test_usefulness_a_clean_acquisition_quote_stays_tier_1(quote):
    v = run(_acq(quote))
    assert v.tier == TIER1, v.top_tier_blockers


def test_a_pending_acquisition_with_a_closing_expectation_still_blocks():
    """B19: announcement words a grant may use are allowed on an acquisition; other time words still block."""
    _not_top(run(_acq("Omega Holdings agreed to acquire Origin Bio; closing is expected in the third quarter")))


def test_pn3_a_signal_joined_by_a_hyphen_is_not_a_name_word():
    """REREVIEW7's pf8 input, still accepted at revision 10 before this fix: "NA" may mean North America."""
    assert plain_form("Licensed in China to Chinaco Pharma, NA-Tessaly Pharma", "Origin Bio") is None
    assert plain_form("Licensed in China to Chinaco-Pharma", "Origin Bio") == "a grant over other places only"
