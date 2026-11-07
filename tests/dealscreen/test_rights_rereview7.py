"""Cycle R1 revision 9: the inputs from adversarial re-review 7 (research/dealscreen_rights_v1/REREVIEW7.md).

Revision 9 reads every cited row's quote, whatever the row's own territory (COVER), blocks a quote clause that names a
company other than the row's parties and the program's company (QW2), refuses a party name that contains joining,
place or condition words in any letter case (PN-CASE, PN-WORD), keeps a grant reported before the as-of date but
effective after it as a blocker (FUT), and judges an availability statement dated only to a period by the end of that
period (DATE-AV). It also narrows the quote's wider-word list so ordinary press words pass (usefulness). Each test is
tagged with its review id.

Defaults as in ``test_rights_rereview3``: buyer territory US, as-of 2025-06-01, company and licensor "Origin Bio"
(the review's "Nerida Bio"). Parties are fictional; the tests assert no real-world facts."""

from __future__ import annotations

import pytest
from test_rights_rereview3 import (
    AQ,
    AV,
    CHINA,
    OL,
    RR,
    STATED,
    TIER0,
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

from bve.dealscreen.rights_allow import plain_form

EU = frozenset({"EU"})
US_LIC = {"grantee": "Alpha Bio", "territory": "United States", "d": "2024-03-01", "deal": "D1"}


def _quoted(event, quote: str):
    return event.model_copy(update={"evidence_quote": quote})


def _not_top(v) -> None:
    assert v.tier not in TOP, (v.tier, v.position, v.top_tier_blockers)


# -- PN-CASE, PN-WORD: a party name holds no joining, place or condition word, in any letter case --------------------
PN = ["LICENSED IN CHINA TO CHINACO PHARMA AND ELSEWHERE TO TESSALY PHARMA",
      "LICENSED IN CHINA TO CHINACO PHARMA AND THE REST TO TESSALY PHARMA",
      "Licensed In China To Chinaco Pharma And In California To Tessaly Pharma",
      "Licensed In China To Chinaco Pharma And In Puerto Rico To Tessaly Pharma",
      "Licensed In China To Chinaco Pharma And Stateside To Tessaly Pharma",
      "Licensed in China to Chinaco Pharma And Elsewhere To Tessaly Pharma",
      "Licensed in China to Chinaco Pharma, Tessaly Pharma Has ROFN",
      "Licensed in China to Chinaco Pharma, ROFN Tessaly Pharma",
      "Licensed in China to Chinaco Pharma, ROFR Holder Tessaly Pharma",
      "Licensed in China to Chinaco Pharma, Tessaly Pharma Has First Look",
      "Licensed in China to Chinaco Pharma, Tessaly Pharma Opt-In",
      "Licensed in China to Chinaco Pharma, Subject To Tessaly Pharma Approval",
      "Licensed in China to Chinaco Pharma, Pending Tessaly Pharma Consent",
      "Licensed in China to Chinaco Pharma & Tessaly Pharma",
      "Licensed in China to Chinaco Pharma & Tessaly Pharma Mexico"]


@pytest.mark.parametrize("text", PN)
def test_pn_a_capitalised_tail_is_not_a_party_name(text):
    assert plain_form(text, "Origin Bio") is None


@pytest.mark.parametrize("text", PN[:3] + PN[6:8])
def test_pn_the_text_as_a_cell_or_assertion_keeps_the_program_out_of_the_top_tiers(text):
    _not_top(run([ev(L, **CHINA)], landscape=(cell("geographic_rights", text, src="2025-04-01"),)))
    _not_top(run([ev(L, **CHINA)], analysts=(analyst("partnerships", text),)))


def test_pn_case_tier_0_path_is_closed():
    v = run([ev(L, **CHINA), ev(AV, grantor="Origin Bio", **STATED)],
            landscape=(cell("geographic_rights", PN[0], src="2025-04-01"),))
    _not_top(v)


@pytest.mark.parametrize("text", ["LICENSED IN CHINA TO CHINACO PHARMA AND IN GERMANY TO TESSALY PHARMA",
                                  "Licensed In China To Chinaco Pharma And In France To Tessaly Pharma"])
def test_pn_case_eu_buyer(text):
    assert plain_form(text, "Origin Bio", None, EU) is None


@pytest.mark.parametrize("text", ["Licensed in China to Chinaco Pharma", "Licensed in China to L & M Bio",
                                  "Licensed in China to Kappa & Kappa",
                                  "Licensed in China to Chinaco plc", "LICENSED IN CHINA TO CHINACO PHARMA"])
def test_pn_plain_grants_and_corporate_forms_still_pass(text):
    assert plain_form(text, "Origin Bio") == "a grant over other places only"


# -- COVER: a covering ending, lapse or acquisition is read for its quote --------------------------------------------
def test_cover_r1_a_return_quote_naming_a_third_party_option_blocks():
    end = _quoted(ev(T, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D1"),
                  "Alpha Bio returns U.S. rights to Origin Bio; Tessaly Pharma holds an option on U.S. rights")
    v = run([ev(L, **US_LIC), end])
    _not_top(v)
    assert blocked(v, "Tessaly Pharma")


def test_cover_r2_rights_re_licensed_on_return_block():
    end = _quoted(ev(RR, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D1"),
                  "U.S. rights revert to Origin Bio and are immediately re-licensed to Tessaly Pharma")
    _not_top(run([ev(L, **US_LIC), end]))


def test_cover_r3_an_ending_after_a_transition_blocks():
    end = _quoted(ev(T, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D1"),
                  "Termination effective only after a 12-month transition; Alpha Bio sells in the U.S. until 2026")
    v = run([ev(L, **US_LIC), end])
    _not_top(v)
    assert blocked(v, "the quote on rights row")  # wording changed in revision 10 (rights_quote)


def test_cover_r5_a_lapse_quote_naming_a_new_licensee_blocks():
    option = ev(O, grantee="Alpha Bio", territory="United States", d="2024-03-01", deal="D2")
    lapse = _quoted(ev(OL, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D2"),
                    "Alpha Bio let its option lapse; Tessaly Pharma has since licensed U.S. rights")
    _not_top(run([option, lapse]))


def test_cover_r7_a_partial_return_blocks():
    lic = ev(L, grantee="Alpha Bio", territory="Worldwide", d="2024-03-01", deal="D3")
    end = _quoted(ev(T, grantee="Alpha Bio", territory="Worldwide", d="2025-01-15", related="D3"),
                  "Alpha Bio returns all rights except U.S. co-promotion rights, which Alpha Bio keeps")
    _not_top(run([lic, end]))


def test_cover_r8_an_acquisition_quote_naming_a_licensee_blocks():
    buy = _quoted(ev(AQ, grantee="Omega Holdings", territory="Worldwide", d="2025-02-01"),
                  "Omega Holdings acquires Origin Bio; U.S. rights to NB-7 remain licensed to Tessaly Pharma")
    _not_top(run([ev(L, **CHINA), buy]))


def test_cover_r9_tier_0_path_is_closed():
    end = _quoted(ev(T, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D1"),
                  "Alpha Bio returns U.S. rights to Origin Bio; Tessaly Pharma holds an option on U.S. rights")
    _not_top(run([ev(L, **US_LIC), end, ev(AV, **STATED)]))


def test_cover_r10_eu_buyer():
    lic = ev(L, grantee="Alpha Bio", territory="Europe", d="2024-03-01", deal="D4")
    end = _quoted(ev(T, grantee="Alpha Bio", territory="Europe", d="2025-01-15", related="D4"),
                  "Alpha Bio returns European rights; Tessaly Pharma holds an option on EU rights")
    _not_top(run([lic, end], territory=EU))


def test_cover_a_plain_return_quote_still_clears():
    end = _quoted(ev(T, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D1"),
                  "Alpha Bio returns U.S. rights to Origin Bio")
    assert run([ev(L, **US_LIC), end]).tier == TIER1


# -- QW2: a clause naming another company, or a wider word, blocks ---------------------------------------------------
QW2 = ["Chinaco Pharma licenses China rights; Origin Bio also granted Tessaly Pharma a license to NB-7",
       "Chinaco Pharma licenses China rights; Tessaly Pharma holds co-commercialization rights to NB-7",
       "Chinaco Pharma licenses China rights; Tessaly Pharma has first right to negotiate any further license",
       "Chinaco Pharma licenses China rights; Tessaly Pharma holds a buy-out right over NB-7",
       "Chinaco Pharma licenses China rights; Tessaly Pharma acquired the remaining rights in 2024",
       "Chinaco Pharma licenses China rights; the rest of NB-7 was sold to Tessaly Pharma",
       "Chinaco Pharma licenses China rights; Tessaly Pharma holds the remaining territories",
       "Chinaco Pharma licenses China rights and an opt-in to the remaining territories",
       "Chinaco Pharma licenses China rights and all other markets",
       "Chinaco Pharma licenses rights in China and all other countries",
       "Chinaco Pharma licenses ex China rights",
       "Chinaco Pharma licenses China and non-China rights",
       "Chinaco Pharma licenses rights in China and beyond",
       "Chinaco Pharma licenses China rights and may expand to further territories",
       "Chinaco Pharma licenses China rights, with first refusal on any later deal",
       "Chinaco Pharma licenses China and Puerto Rico rights",
       "Chinaco Pharma licenses China rights; Tessaly Pharma licenses stateside rights",
       "Chinaco Pharma licenses China rights; Tessaly Pharma licenses California rights"]


@pytest.mark.parametrize("quote", QW2)
def test_qw2_a_third_party_or_wider_clause_blocks(quote):
    _not_top(run([_quoted(ev(L, **CHINA), quote)]))


# -- FUT: a grant reported before the as-of date but effective after it ---------------------------------------------
def test_fut_a_grant_announced_before_the_as_of_date_blocks():
    later = ev(L, grantee="Tessaly Pharma", territory="United States", d="2025-07-01", src="2025-05-20")
    v = run([ev(L, **CHINA), later])
    _not_top(v)
    assert blocked(v, "may have been agreed by the as-of date")  # wording since revision 10
    assert any("not shown to have been reported after it" in x for x in v.reasons)
    # Q-FUT: the question does not say every recorded deal covers other territories only.
    assert not any("Recorded deals cover other territories only" in q for q in v.questions)
    assert any("Recorded deals in force on the as-of date" in q for q in v.questions)


def test_fut_tier_0_path_is_closed():
    later = ev(L, grantee="Tessaly Pharma", territory="United States", d="2025-07-01", src="2025-05-20")
    _not_top(run([ev(L, **CHINA), later, ev(AV, **STATED)]))


def test_fut_after_a_return():
    lic = ev(L, **US_LIC)
    end = ev(T, grantee="Alpha Bio", territory="United States", d="2025-02-01", related="D1")
    later = ev(L, grantee="Tessaly Pharma", territory="United States", d="2025-06-15", src="2025-05-30")
    _not_top(run([lic, end, later]))


def test_fut_a_grant_reported_after_the_as_of_date_is_still_not_applied():
    later = ev(L, grantee="Tessaly Pharma", territory="United States", d="2025-07-01", src="2025-06-20")
    assert not blocked(run([ev(L, **CHINA), later]), "may have been agreed by the as-of date")


# -- DATE-AV: an availability statement dated only to the as-of year or month ---------------------------------------
@pytest.mark.parametrize("d, src", [("2025", None), ("2025-06", None), (None, "2025")])
def test_date_av_a_statement_dated_to_the_as_of_period_does_not_count(d, src):
    _not_top(run([ev(AV, territory="United States", d=d, src=src)]))


def test_date_av_a_statement_dated_to_an_earlier_period_counts():
    assert run([ev(AV, territory="United States", d="2025-03")]).tier == TIER0


# -- Usefulness: ordinary press words and kept rights pass ----------------------------------------------------------
CLEAN = ["Chinaco Pharma obtains exclusive China rights to NB-7, a potential new treatment option for gastric cancer",
         "Chinaco Pharma licenses China rights; Origin Bio retains rights in the rest of the world",
         "Chinaco Pharma licenses China rights; Origin Bio retains all rights in the U.S. and the rest of the world",
         "Chinaco Pharma licenses China rights; Origin Bio retains U.S. rights"]
# revision 12: "its third China deal in a row", "will pay royalties" and a place wider than the row block
# (test_rights_rereview10.py: REV12_BLOCKED)


@pytest.mark.parametrize("quote", CLEAN)
def test_usefulness_a_clean_china_licence_quote_stays_tier_1(quote):
    v = run([_quoted(ev(L, **CHINA), quote)])
    assert v.tier == TIER1, v.top_tier_blockers


def test_usefulness_the_company_keeping_global_rights_passes():
    quote = "Chinaco Pharma licenses China rights; Origin Bio retains global rights"
    assert run([_quoted(ev(L, **CHINA), quote)]).tier == TIER1


@pytest.mark.parametrize("quote", ["Chinaco Pharma licenses China rights with an option on U.S. rights",
                                   "Chinaco Pharma licenses China rights and ROW rights",
                                   "Chinaco Pharma licenses China rights with an option for further territories"])
def test_usefulness_the_narrowed_wider_list_still_blocks_real_reach(quote):
    _not_top(run([_quoted(ev(L, **CHINA), quote)]))


# -- Usefulness on real press wording (fictional parties): bylines, suffixes and subsidiaries are not holders -------
@pytest.mark.parametrize("quote", [
    "Alpha Bio terminated its deal with Origin Bio covering NB-7, Wirecast has learned"])
# revision 12: "announced the end of the U.S. license" blocks (an announcement may be of a later ending)
def test_usefulness_a_byline_suffix_or_parent_does_not_block(quote):
    end = _quoted(ev(T, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D1"), quote)
    assert run([ev(L, **US_LIC), end]).tier == TIER1


def test_a_parent_named_on_the_license_row_now_blocks():
    """Revision 11 read "<known party>, a subsidiary of <Name>" as describing the party (judgement P20). Revision 12
    has no slot for a parent: the parent may hold rights, so the quote blocks until an analyst confirms the row."""
    lic = _quoted(ev(L, **US_LIC), ("Alpha Bio entered into a license agreement with Origin Bio Co., Ltd, a subsidiary "
                                    "of Origin Holdings Group Limited, for U.S. rights to NB-7"))
    end = ev(T, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D1")
    v = run([lic, end])
    _not_top(v)
    assert blocked(v, "Holdings")


def test_a_byline_with_a_company_word_is_a_news_source():
    """Revision 9 disclosed this as a cost; revision 10 reads "X has learned" as a news source (review R1v9 §3)."""
    end = _quoted(ev(T, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D1"),
                  "Alpha Bio terminated its deal with Origin Bio covering NB-7, Biotech Wire has learned")
    assert run([ev(L, **US_LIC), end]).tier == TIER1


def test_a_holder_with_has_and_a_rights_word_still_blocks():
    v = run([_quoted(ev(L, **CHINA), "Chinaco Pharma licenses China rights; Tessaly has U.S. rights to NB-7")])
    _not_top(v)
