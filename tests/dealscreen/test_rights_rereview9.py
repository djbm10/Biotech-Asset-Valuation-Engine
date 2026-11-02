"""Cycle R1 revision 11: the inputs from adversarial re-review 9 (research/dealscreen_rights_v1/REREVIEW9.md).

Revision 11 reads every word of a rights row's quote against a short allow-list for the row's type
(``rights_vocab``), not only its capitalised names (LOWER, WIDER3, HEDGE3). Names are placed only as a row party,
the program's company (with corporate words, never a place word: MASK), the program, a place or an agency code;
speaker, adviser and byline text is removed only when anchored to a known party (PLACE). Dates after the as-of date
block. A clear position cites every applied row, so every quote is read (UNCITED). A future option exercise is not
applied and blocks (FUT3). An acquisition counts as one of the owner only when the acquired party is a grant party or
the company itself (OWNER-KEY). Each test is tagged with its review id.

Defaults as in ``test_rights_rereview3``: buyer territory US, as-of 2025-06-01, company and licensor "Origin Bio"
(the review's "Nerida Bio"), program words "NB-7" and "gastric cancer". Parties are fictional; the tests assert no
real-world facts."""

from __future__ import annotations

import pytest
from test_rights_rereview3 import AQ, AV, CHINA, OL, TIER1, TOP, L, O, T, blocked, ev, run

from bve.dealscreen import rights_position as rp
from bve.dealscreen.rights import OPTION_EXERCISED
from bve.dealscreen.rights_allow import plain_form
from bve.dealscreen.rights_signals import right_kind

US_LIC = {"grantee": "Alpha Bio", "territory": "United States", "d": "2024-03-01", "deal": "D1"}
RETURN = "Alpha Bio returns U.S. rights to Origin Bio"


def _quoted(event, quote: str):
    return event.model_copy(update={"evidence_quote": quote})


def _not_top(v) -> None:
    assert v.tier not in TOP, (v.tier, v.position, v.top_tier_blockers)


def _term(quote: str):
    end = ev(T, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D1")
    return [ev(L, **US_LIC), _quoted(end, quote)]


def _china(quote: str):
    return [_quoted(ev(L, **CHINA), quote)]


def _acq(quote: str, grantor: str = "Origin Bio", grantee: str = "Omega Holdings"):
    buy = ev(AQ, grantee=grantee, grantor=grantor, territory="Worldwide", d="2025-02-01")
    return [ev(L, **CHINA), _quoted(buy, quote)]


# -- 2a LOWER: lower-case words that name another holder ------------------------------------------------------------
LOWER_TERM = [f"{RETURN}; U.S. rights then went to a third party",                                    # P1
              f"{RETURN}; the U.S. rights-holder is now another company",                             # P2
              f"{RETURN}, which has since licensed them to another company",                          # P3
              f"{RETURN}; Origin Bio has since granted an exclusive U.S. license to a new licensee",  # P4
              f"{RETURN}, which licensed them to a newco",                                            # P16
              f"{RETURN}, which licensed them to tessaly"]                                            # P18
LOWER_ACQ = ["Omega Holdings acquires Origin Bio, whose U.S. licensee is unaffected",                 # Q1
             "Omega Holdings acquires Origin Bio; NB-7 is licensed in the U.S. to a third party",     # Q2
             "Omega Holdings acquires Origin Bio, which granted another company an exclusive U.S. license to NB-7"]
LOWER_CHINA = ["Chinaco Pharma licenses NB-7 for mainland China; another company has all other rights",  # PC8
               "Chinaco Pharma licenses NB-7 for mainland China; NB-7 is also licensed to a third party",  # PC9
               "Chinaco Pharma licenses NB-7 for mainland China; a global pharmaceutical company has the other rights"]


@pytest.mark.parametrize("quote", LOWER_TERM)
def test_lower_a_return_quote_naming_a_new_holder_in_lower_case_blocks(quote):
    v = run(_term(quote))
    _not_top(v)
    assert blocked(v, "the quote on rights row")


@pytest.mark.parametrize("quote", LOWER_ACQ)
def test_lower_an_acquisition_quote_naming_a_licensee_blocks(quote):
    _not_top(run(_acq(quote)))


@pytest.mark.parametrize("quote", LOWER_CHINA)
def test_lower_a_china_license_quote_naming_other_holders_blocks(quote):
    _not_top(run(_china(quote)))


# -- 2b PLACE: names placed by shape or by a nearby word ------------------------------------------------------------
PLACE_TERM = [f"{RETURN}; Tessaly Pharma acts as the new U.S. licensee",                     # P5
              f"{RETURN}; Tessaly Pharma is acting as U.S. licensee",                        # P5b
              f"{RETURN}; Tessaly Pharma serves as exclusive U.S. licensee of NB-7",         # P6
              f"{RETURN}; Tessaly Pharma has confirmed its U.S. license to NB-7",            # P7
              f"{RETURN}; Tessaly Pharma reported an exclusive U.S. license to NB-7",        # P8
              f"{RETURN}, said Tessaly Pharma, the new U.S. licensee",                       # P9
              f"{RETURN}; the new U.S. licensee, analysts said, Tessaly Pharma",             # P9b
              f"{RETURN} and licensed them to a newly formed company (Tessco); Tessco now has U.S. rights",  # P15
              f"{RETURN}, which licensed them to New Co",                                    # P17
              f"{RETURN}; a New Licensee now has the U.S. rights",                           # P23
              f"{RETURN}; the new U.S. licensee is 3Tessaly",                                # P11
              f"{RETURN}; the new U.S. licensee is T7 Bio",                                  # P12
              f"{RETURN}; the new U.S. licensee is Alpha Origin",                            # P13
              f"{RETURN}; the new U.S. licensee is Star Bio"]                                # P14
PLACE_CHINA = ["Chinaco Pharma licenses NB-7 for mainland China; NB-7 is also licensed to Chinaco Bio",  # PC5
               "Chinaco Pharma licenses NB-7 for mainland China; NB-7 is also licensed to 3Tessaly",    # PC6
               "Chinaco Pharma licenses NB-7 for mainland China; NB-7 is also licensed to T7 Pharma"]   # PC7


@pytest.mark.parametrize("quote", PLACE_TERM)
def test_place_a_name_beside_a_title_source_or_digit_is_not_placed(quote):
    _not_top(run(_term(quote)))


@pytest.mark.parametrize("quote", PLACE_CHINA)
def test_place_china_license_naming_another_licensee_blocks(quote):
    _not_top(run(_china(quote)))


# -- 2c MASK: a place after a known name is a place, not a corporate word ----------------------------------------------
@pytest.mark.parametrize("tail", ["and Chinaco Pharma U.S. will commercialize NB-7",                  # PC1
                                  "; Chinaco Pharma USA will develop and commercialize NB-7",         # PC2
                                  "; Chinaco Pharma America will commercialize NB-7",                # PC3
                                  "; Chinaco Pharma International will commercialize NB-7"])         # PC4
def test_mask_a_known_name_with_a_place_word_is_not_the_known_party(tail):
    v = run(_china(f"Chinaco Pharma licenses NB-7 for mainland China, {tail}"))
    _not_top(v)


def test_mask_the_us_affiliate_is_named_as_a_place_in_the_buyer_territory():
    v = run(_china("Chinaco Pharma licenses NB-7 for mainland China, and Chinaco Pharma U.S. will commercialize NB-7"))
    assert blocked(v, "the quote on rights row")


# -- 2d WIDER3 ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("quote", [
    "Chinaco Pharma licenses NB-7 in mainland China and any other territory",                           # W1
    "Chinaco Pharma licenses NB-7 in mainland China and every other market",                            # W2
    "Chinaco Pharma licenses mainland China rights to NB-7 and will receive further rights upon approval",  # W3
    "Chinaco Pharma licenses mainland China rights to NB-7 and will obtain additional rights",          # W4
    "Chinaco Pharma licenses NB-7 in mainland China and all 50 states",                                 # W5
    "Chinaco Pharma licenses NB-7 in mainland China and across the globe",                              # W12
    "Chinaco Pharma licenses NB-7 in the Licensed Territory, which includes mainland China",            # W6
    "Chinaco Pharma licenses mainland China rights and receives a matching right",                      # W17
    "Chinaco Pharma licenses NB-7 for mainland China and will lead worldwide pivotal trials"])          # PC12
def test_wider3_reach_in_lower_case_words_blocks(quote):
    _not_top(run(_china(quote)))


# -- 2e HEDGE3 ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("quote", [
    "Alpha Bio returns U.S. rights to Origin Bio as of 1 December 2025",                                # H1
    "Alpha Bio returns U.S. rights to Origin Bio after a 180-day wind-down period",                     # H2
    "Alpha Bio to return U.S. rights to Origin Bio",                                                    # H3
    "Alpha Bio has elected to terminate the U.S. license",                                              # H4
    "Alpha Bio decided to terminate its U.S. license to NB-7",                                          # H5
    "Alpha Bio is returning U.S. rights to Origin Bio",                                                 # H6
    "Alpha Bio returns U.S. rights to Origin Bio starting in December",                                 # H9
    "Alpha Bio returns U.S. rights to Origin Bio by year-end",                                          # H10
    "Alpha Bio returns U.S. rights to Origin Bio in due course",                                        # H11
    "Alpha Bio announced its decision to return U.S. rights to Origin Bio"])                            # H12
def test_hedge3_an_ending_not_yet_in_effect_blocks(quote):
    _not_top(run(_term(quote)))


def test_hedge3_a_date_after_the_as_of_date_is_named():
    v = run(_term("Alpha Bio returns U.S. rights to Origin Bio as of 1 December 2025"))
    assert blocked(v, "after the as-of date")


def test_dated_notice_before_the_as_of_date_still_clears():
    """Usefulness (UT1): a notice effective before the as-of date is a completed ending."""
    v = run(_term("Alpha Bio provided notice of termination of the U.S. license, effective March 1, 2025"))
    assert v.tier == TIER1, v.top_tier_blockers


def test_a_notice_without_a_date_still_blocks():
    _not_top(run(_term("Alpha Bio provided notice of termination of the U.S. license")))


# -- 2f FUT3: a future option exercise -------------------------------------------------------------------------------
def test_fut3_e2_a_future_option_exercise_with_no_source_date_blocks():
    exercise = ev(OPTION_EXERCISED, grantee="Tessaly Pharma", territory="United States", d="2025-07-01")
    v = run([ev(L, **CHINA), exercise])
    _not_top(v)
    assert blocked(v, "takes effect after the as-of date")


def test_fut3_e3_linked_to_a_china_option():
    option = ev(O, grantee="Tessaly Pharma", territory="mainland China", d="2024-06-01", deal="D9")
    exercise = ev(OPTION_EXERCISED, grantee="Tessaly Pharma", territory="United States", d="2025-07-01",
                  related="D9")
    _not_top(run([ev(L, **CHINA), option, exercise]))


# -- 2g UNCITED: every row beside a clear position is read -----------------------------------------------------------
TESSALY_CHINA = "Chinaco Pharma licenses China rights; Tessaly Pharma holds U.S. rights"


@pytest.mark.parametrize("quote", [TESSALY_CHINA,                                                     # AV1
                                   "Chinaco Pharma licenses worldwide rights to NB-7",                # AV3
                                   "Chinaco Pharma licenses China rights and holds an option on U.S. rights"])  # AV4
def test_uncited_av_an_availability_statement_beside_a_china_license_reads_the_license(quote):
    statement = ev(AV, grantor="Origin Bio", territory="United States", d="2025-03-01")
    v = run([statement, *_china(quote)])
    _not_top(v)
    assert any(e.get("type") == L for e in v.evidence)


def test_uncited_rt1_a_return_beside_a_china_license_reads_the_license():
    end = ev(T, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D1")
    _not_top(run([ev(L, **US_LIC), end, *_china(TESSALY_CHINA)]))


def test_uncited_rt2_a_lapse_beside_a_china_license_reads_the_license():
    option = ev(O, grantee="Alpha Bio", territory="United States", d="2024-03-01", deal="D2")
    lapse = ev(OL, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D2")
    _not_top(run([option, lapse, *_china(TESSALY_CHINA)]))


def test_uncited_a_clean_china_license_beside_a_return_still_clears():
    end = ev(T, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D1")
    v = run([ev(L, **US_LIC), end, *_china("Origin Bio licensed China rights to NB-7 to Chinaco Pharma")])
    assert v.tier == TIER1, v.top_tier_blockers


# -- 2h PN4: a multi-word party name needs a company or legal word ------------------------------------------------------
@pytest.mark.parametrize("name", ["Tessaly Intercontinental", "Tessaly Transpacific", "Tessaly Exusa"])
def test_pn4_a_name_without_a_company_word_is_not_a_party(name):
    assert plain_form(f"Licensed in China to Chinaco, {name}", "Origin Bio", None, frozenset({"US"})) is None


def test_pn4_two_china_licensees_with_company_words_still_read():
    assert plain_form("Licensed in China to Chinaco Pharma, Tessaly Pharma", "Origin Bio", None,
                      frozenset({"US"})) is not None


# -- OWNER-KEY: the company buying someone else, or an affiliate being bought -------------------------------------------
def test_owner_key_f6_the_company_acquiring_another_party_is_not_owner_acquired():
    v = run(_acq("Origin Bio acquires Sideco Bio", grantor="Sideco Bio", grantee="Origin Bio"))
    _not_top(v)
    assert v.position != rp.P_OWNER_ACQUIRED


@pytest.mark.parametrize("acquired", ["Origin Bio US", "Origin Holdings", "Origin Bio International"])
def test_owner_key_an_affiliate_of_the_company_being_acquired_blocks(acquired):
    _not_top(run(_acq(f"Omega Holdings acquires {acquired}", grantor=acquired)))


def test_owner_key_the_company_itself_with_a_legal_form_is_still_the_owner():
    v = run(_acq("Omega Holdings acquires Origin Bio, Inc.", grantor="Origin Bio, Inc."))
    assert v.position == rp.P_OWNER_ACQUIRED and v.tier == TIER1, v.top_tier_blockers


# -- LBL-NONE2 ---------------------------------------------------------------------------------------------------------
def test_lbl_none2_unapplied_rows_are_not_no_rights_evidence():
    v = run([ev(AQ, grantee="Gamma Corp", grantor="Origin Bio", territory="worldwide excluding the U.S.",
                d="2025-02-01")])
    assert v.position == rp.P_NOT_APPLIED


# -- SHARE: "shares" is an acquisition word ------------------------------------------------------------------------------
def test_share_is_an_acquisition_word_and_shared_is_codevelopment():
    assert right_kind("shares") == "acquire" and right_kind("share") == "acquire"
    assert right_kind("shared") == "codev" and right_kind("cost-sharing") == "codev"


@pytest.mark.parametrize("quote", [
    "Omega Holdings will acquire Origin Bio for $25.00 per share in cash",                              # UA1
    "Omega Holdings completes tender offer for all outstanding shares of Origin Bio"])                  # UA2
def test_share_a_clean_acquisition_quote_reaches_tier_1(quote):
    v = run(_acq(quote))
    assert v.tier == TIER1, v.top_tier_blockers


# -- Usefulness: text that cannot hold rights is removed only when anchored ----------------------------------------------
@pytest.mark.parametrize("quote", [
    ("SAN DIEGO, March 3, 2025 /PRNewswire/ -- Origin Bio, Inc. (Nasdaq: ORGN) today announced an exclusive license "
     "agreement with Chinaco Pharma for NB-7 in mainland China"),                                       # UC1
    "BOSTON and SHANGHAI, March 3, 2025 -- Origin Bio licensed China rights to NB-7 to Chinaco Pharma",  # UC2
    ("Origin Bio licensed China rights to NB-7 to Chinaco Pharma, said Jane Doe, Chief Executive Officer of "
     "Origin Bio"),                                                                                     # UC3
    "Origin Bio licensed China rights to NB-7 for gastric cancer to Chinaco Pharma",                   # program words
    "Origin Bio licensed China rights to NB-7 to Chinaco Pharma; NB-7 has Breakthrough Therapy Designation"])
def test_usefulness_anchored_boilerplate_and_program_words_do_not_block(quote):
    v = run(_china(quote))
    assert v.tier == TIER1, v.top_tier_blockers


@pytest.mark.parametrize("quote", [
    # an attribution not anchored to a known party is not removed
    "Origin Bio licensed China rights to NB-7 to Chinaco Pharma, said Jane Doe, Chief Executive Officer of Tessaly",
    # a dateline anywhere but the start is not removed
    "Origin Bio licensed China rights to NB-7 to Chinaco Pharma -- BOSTON, March 3, 2025 -- Tessaly Pharma holds U.S. rights",
    # a disease word that is not the program's own
    "Origin Bio licensed China rights to NB-7 for lymphoma to Chinaco Pharma"])
def test_usefulness_unanchored_text_still_blocks(quote):
    _not_top(run(_china(quote)))
