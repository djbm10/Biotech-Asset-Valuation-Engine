"""Cycle R1 revision 18: the inputs from adversarial re-review 16 (research/dealscreen_rights_v1/REREVIEW16.md).

An ending or a lapse dated before the deal it ends blocks (DATE-BEFORE). A use after a closed description of the
program limits a retention or an ending (USE-AFTER-DESC), and a lapse limited to a use blocks (PARTIAL-LAPSE). A cut
hidden behind a closing mark, a cut at the start and an em dash between words block (CUT2, START-CUT, DASH-UNICODE).
"~" before a year, a mark inside a party's name and an unpaired mark block (TILDE-DATE, NAME-MARK, RESP-ASCII2).
"R&D" is read as "research and development".

Defaults as in ``test_rights_rereview10``. Parties are fictional; the tests assert no real-world facts."""

from __future__ import annotations

from datetime import date

import pytest
from test_rights_rereview3 import AS_OF, CHINA, OL, TOP, US, L, O, T, ev
from test_rights_rereview10 import _named_run, _not_top, _quoted
from test_rights_rereview11 import DESCRIPTION, ROWS
from test_rights_rereview14 import DL, C, read

from bve.dealscreen.rights_quote import quote_problem

G = "Origin Bio granted Chinaco Pharma exclusive rights to NB-7 in mainland China"
DEAL = date(2024, 3, 1)


def ended(row: str, quote: str, day: date | None = DEAL) -> str | None:
    return quote_problem(quote, ROWS[row], "Origin Bio", AS_OF, US, names=["NB-7"], vocabulary=DESCRIPTION, ended=day)


# -- DATE-BEFORE (High) ---------------------------------------------------------------------------------------------
BEFORE = [
    ("TERM", "Alpha Bio returned U.S. rights to NB-7 to Origin Bio in 2019"),                                    # DQ1
    ("TERM", "On January 15, 2023, Alpha Bio terminated the license agreement with Origin Bio for NB-7"),        # DQ2
    ("TERM", "Alpha Bio returned U.S. rights to NB-7 to Origin Bio in 2023"),                                    # DB1
    ("TERM", "In February 2024, Origin Bio regained U.S. rights to NB-7 from Alpha Bio"),                        # DB2
    ("RET", "In 2022, Alpha Bio returned U.S. rights to NB-7 to Origin Bio"),                                    # DB6
    ("LAPSE", "On June 1, 2023, Alpha Bio's option on NB-7 lapsed"),                                             # DB3
]


@pytest.mark.parametrize(("row", "quote"), BEFORE)
def test_an_ending_dated_before_its_deal_blocks(row, quote):
    why = ended(row, quote)
    assert why and "before the deal it ends (2024-03-01)" in why


@pytest.mark.parametrize("quote", [
    "On June 1, 2024, Alpha Bio terminated the license agreement with Origin Bio for NB-7",                     # DB4
    "In 2024, Alpha Bio returned U.S. rights to NB-7 to Origin Bio",
    "Alpha Bio terminated the U.S. license with Origin Bio for NB-7",
])
def test_an_ending_on_or_after_its_deal_passes(quote):
    assert ended("TERM", quote) is None


def test_without_the_deal_date_only_the_as_of_date_is_read():
    assert ended("TERM", "Alpha Bio returned U.S. rights to NB-7 to Origin Bio in 2019", day=None) is None


def test_a_grant_row_is_not_read_against_a_deal_date():
    assert ended("CN", G + " in 2019") is None


def _ending_run(kind, start_kind, quote, deal_day="2024-03-01"):
    start = ev(start_kind, grantee="Alpha Bio", territory="United States", d=deal_day, deal="D1")
    end = _quoted(ev(kind, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D1", deal="D9"),
                  quote)
    return _named_run([start, end])


def test_end_to_end_a_termination_dated_before_the_license_is_not_top_tier():
    _not_top(_ending_run(T, L, "On January 15, 2023, Alpha Bio terminated the license agreement with Origin Bio "
                               "for NB-7"))


def test_end_to_end_a_lapse_dated_before_the_option_is_not_top_tier():
    _not_top(_ending_run(OL, O, "On June 1, 2023, Alpha Bio's option on NB-7 lapsed"))


def test_end_to_end_the_reason_names_both_dates():
    v = _ending_run(T, L, "Alpha Bio returned U.S. rights to NB-7 to Origin Bio in 2019")
    assert any("before the deal it ends (2024-03-01)" in b for b in v.top_tier_blockers)


def test_end_to_end_a_termination_after_the_license_is_still_top_tier():
    v = _ending_run(T, L, "On June 1, 2024, Alpha Bio terminated the license agreement with Origin Bio for NB-7")
    assert v.tier in TOP, (v.tier, v.top_tier_blockers)


# -- USE-AFTER-DESC and PARTIAL-LAPSE (Medium) ----------------------------------------------------------------------
USES = [
    ("CN", C + "; Origin Bio retains U.S. rights to NB-7, an antibody, for solid tumors"),                       # RP1
    ("CN", "Origin Bio retains U.S. rights to NB-7, an antibody, for solid tumors"),                             # RP2
    ("CN", C + "; Origin Bio retains rights to NB-7, its lead ADC, for gastric cancer in the United States"),    # RQ1
    ("RET", "Origin Bio regains U.S. rights to NB-7, an antibody, for solid tumors"),                            # RP6
    ("RET", "Alpha Bio returned U.S. rights to NB-7, an antibody, for solid tumors, to Origin Bio"),             # RP7
    ("TERM", "Alpha Bio terminated the license with Origin Bio for NB-7, an antibody, for solid tumors"),        # RP9
    ("RET", ("Origin Bio regains U.S. rights to NB-7, a claudin18.2-directed antibody-drug conjugate, for gastric "
             "cancer")),                                                                                           # RQ2
    ("RET", "Origin Bio regains U.S. rights to NB-7, a novel antibody, for first-line solid tumors"),            # RP14
    ("LAPSE", "Alpha Bio did not exercise its option on NB-7 for solid tumors"),                                 # LP2
    ("LAPSE", "Alpha Bio declined to exercise its option on NB-7 for the treatment of solid tumors"),            # LP5
    ("LAPSE", "Alpha Bio did not exercise its option on NB-7 for gastric cancer"),                               # LQ1
    ("LAPSE", "Alpha Bio declined to exercise its option on NB-7 for first-line gastric cancer"),                # LQ2
    ("LAPSE", "Alpha Bio did not exercise its option on NB-7, an antibody, for solid tumors"),
]


@pytest.mark.parametrize(("row", "quote"), USES)
def test_a_use_limit_blocks(row, quote):
    assert read(row, quote)


def test_a_partial_lapse_says_the_holder_may_keep_an_option():
    assert "option lapsed only for solid tumors" in read("LAPSE", "Alpha Bio did not exercise its option on NB-7 for "
                                                                  "solid tumors")


def test_a_use_after_a_description_is_named():
    assert "only for solid tumors" in read("RET", "Origin Bio regains U.S. rights to NB-7, an antibody, for solid "
                                                  "tumors")


@pytest.mark.parametrize(("row", "quote"), [
    ("LAPSE", "Alpha Bio did not exercise its option on NB-7"),                                                  # LPc
    ("LAPSE", "Alpha Bio's option on NB-7 lapsed"),
    ("RET", "Origin Bio regains U.S. rights to NB-7, an antibody"),
    ("RET", "Origin Bio regains U.S. rights to NB-7"),
])
def test_an_ending_with_no_use_passes(row, quote):
    assert read(row, quote) is None


def test_end_to_end_a_partial_lapse_is_not_top_tier():
    _not_top(_ending_run(OL, O, "Alpha Bio did not exercise its option on NB-7 for solid tumors", "2025-01-01"))


def test_end_to_end_a_use_after_a_description_is_not_top_tier():
    _not_top(_ending_run(T, L, "Origin Bio regains U.S. rights to NB-7, an antibody, for solid tumors"))


# -- CUT2, START-CUT, DASH-UNICODE, marks (Low) ---------------------------------------------------------------------
LOW = [
    G + ',"', G + ",”", G + ",)", G + ", .", G + ' --"', G + " -.", G + ",'", '"' + G + ',"',            # CQ1-CQ9
    G + ",’", G + ' -"', G + ":)", G + ", /", G + ",$",                                                 # CU1-CU5
    ", " + G, "-- " + G, "; " + G, ": " + G, "- " + G, "— " + G,                                        # SC1-SC6
    "Origin Bio granted Chinaco Pharma—exclusive rights to NB-7 in mainland China",                     # DU1
    "Origin Bio granted Chinaco Pharma exclusive rights to NB-7—in mainland China",                     # DU2
    "Origin Bio granted Chinaco Pharma exclusive rights to NB-7–in mainland China",                     # DU3
    G + " $", G + "'", G + " /", G + " (", G + ")", G + ' "',                                               # MK10-MK14
    ". " + G, "/" + G, "$" + G,
    "Origin Bio granted Chinaco Pharma -exclusive rights to NB-7 in mainland China",                       # DU9
    "Origin Bio granted Chinaco Pharma- exclusive rights to NB-7 in mainland China",                       # DU10
    C + ",. " + G,                                                                                         # CU6
]


@pytest.mark.parametrize("quote", LOW)
def test_every_low_attack_blocks(quote):
    assert read("CN", quote)


@pytest.mark.parametrize("quote", ["Origin Bio regains—U.S. rights to NB-7",                           # DU8
                                   "Alpha Bio returned U.S. rights to NB-7 to Origin Bio in ~2024",           # MK1
                                   "Alpha Bio returned U.S. rights to NB-7 to Origin Bio in ~2025"])          # MK2
def test_low_attacks_on_an_ending_block(quote):
    assert read("RET", quote)


def test_a_start_cut_says_so():
    assert "cut off at the start" in read("CN", ", " + G)


def test_a_mark_inside_a_party_name_is_read():
    row = {"type": "LICENSE", "grantor": "Origin Bio", "grantee": "Chinaco Pharma*", "territory": "mainland China",
           "date": "2025-01-01"}
    assert "'*'" in read(row, "Origin Bio granted Chinaco Pharma* exclusive rights to NB-7 in mainland China")


CLEAN = [
    ("CN", G),
    ("CN", G + "."),
    ("CN", DL + G + "."),
    ("CN", '"' + G + '."'),
    ("CN", "“" + G + ".”"),                                                                       # UQ23
    ("CN", "'" + G + "'"),
    ("CN", "BOSTON, Mass., March 3, 2025 /PRNewswire/ — " + G + "."),
    ("CN", C + "; Chinaco Pharma will pay Origin Bio ~$20 million upfront"),                                # RM1
    ("CN", C + "; Chinaco Pharma will pay Origin Bio $20 million upfront"),
    ("CN", ("Origin Bio granted Chinaco Pharma exclusive R&D and commercialization rights to NB-7 in mainland "
            "China")),                                                                                         # UQ24
    ("CN", "Origin Bio granted Chinaco Pharma exclusive research and development rights to NB-7 in mainland China"),
    ("RET", "Origin Bio regains U.S. rights to NB-7"),
    ("CN", "Origin Bio granted Chinaco Pharma \"exclusive\" rights to NB-7 in mainland China"),           # MK11
]


@pytest.mark.parametrize(("row", "quote"), CLEAN)
def test_clean_quotes_pass(row, quote):
    assert read(row, quote) is None


def test_a_suspended_hyphen_is_not_a_cut():
    why = read("CN", "Origin Bio granted Chinaco Pharma exclusive rights to NB-7 for first- and second-line gastric "
                     "cancer in mainland China")
    assert "cut off" not in (why or "")


def test_an_ampersand_inside_a_party_name_is_still_read():
    row = {"type": "LICENSE", "grantor": "Origin Bio", "grantee": "Chen & Wu Pharma", "territory": "mainland China",
           "date": "2025-01-01"}
    assert read(row, "Origin Bio granted Chen & Wu Pharma exclusive rights to NB-7 in mainland China") is None


def test_an_ampersand_joining_places_still_blocks():
    assert "'&'" in read("CN", C + "; Origin Bio retains rights to NB-7 in the U.S. & Canada")              # UQ21


def test_a_retention_of_research_and_development_rights_only_blocks():
    assert read("CN", C + "; Origin Bio retains R&D rights to NB-7 in the United States")


def test_end_to_end_a_cut_behind_a_closing_mark_is_not_top_tier():
    _not_top(_named_run([_quoted(ev(L, **CHINA), G + ',"')]))


def test_end_to_end_an_em_dash_is_not_top_tier():
    _not_top(_named_run([_quoted(ev(L, **CHINA), "Origin Bio granted Chinaco Pharma—exclusive rights to NB-7 "
                                                 "in mainland China")]))
