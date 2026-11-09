"""Cycle R1 revision 15: the inputs from adversarial re-review 13 (research/dealscreen_rights_v1/REREVIEW13.md).

A retention names one place at most (RET-PLACE2), keeps plain "rights" to the program, never "rights to develop" it
or rights "for" one use (RET-PARTIAL2), and a retention DealScreen does not read says so (RET-REASON). A quote that
marks words as left out or edited blocks (ELISION). A dateline date is read against the as-of date (DATELINE-DATE),
and a deal word is never a dateline city (HEADLINE-1WORD). A quote made only of payments blocks unless the row
covers the buyer territory (PAYONLY). Clean wordings from the review now pass (UC41-UC51, UC54).

Defaults as in ``test_rights_rereview10``. Parties are fictional; the tests assert no real-world facts."""

from __future__ import annotations

import pytest
from test_rights_rereview3 import CHINA, L, T, ev
from test_rights_rereview10 import AS_OF, DESCRIPTION, US, _named_run, _not_top, _quoted
from test_rights_rereview11 import ROWS

from bve.dealscreen.rights_quote import quote_problem

C = "Chinaco Pharma licenses NB-7 for mainland China"


def read(row: str, quote: str) -> str | None:
    return quote_problem(quote, ROWS[row], "Origin Bio", AS_OF, US, names=["NB-7"], vocabulary=DESCRIPTION)


ATTACKS = [
    # RET-PLACE2: a scope and an exclusion are two places, never their union
    ("CN", C + "; Origin Bio retains worldwide rights to NB-7, excluding the United States"),               # RU1
    ("CN", C + "; Origin Bio retains global rights to NB-7 outside the United States"),                     # RU2
    ("CN", C + "; Origin Bio retains worldwide rights to NB-7 outside of the United States"),               # RU3
    ("CN", C + "; Origin Bio retains ex-U.S. rights to NB-7 worldwide"),                                    # RU4
    ("CN", C + "; Origin Bio retains worldwide rights to NB-7 except the U.S. and Canada"),                 # RU19
    ("CN", C + "; Origin Bio retains ROW rights excluding the U.S."),                                       # ROW1
    ("OPT", ("Origin Bio granted Chinaco Pharma an option on NB-7 in mainland China; Origin Bio retains global "
             "rights to NB-7, excluding the United States")),                                                 # RU18
    ("TERM", ("Alpha Bio terminated the U.S. license with Origin Bio; Origin Bio retains worldwide rights to NB-7, "
              "excluding the United States")),                                                                # RU5
    # RET-PARTIAL2
    ("CN", C + "; Origin Bio retains all rights to develop NB-7 in the United States"),                     # RU7
    ("CN", C + "; Origin Bio retains all rights to commercialize NB-7 in the United States"),               # RU8
    ("CN", C + "; Origin Bio retains the rights to market and sell NB-7 in the United States"),             # RU9
    ("CN", C + "; Origin Bio retains U.S. rights to NB-7 for gastric cancer"),                              # RU10
    # ELISION
    ("CN", "Origin Bio granted Chinaco Pharma exclusive rights to NB-7 [...] in mainland China"),          # EL1
    ("CN", "Origin Bio granted Chinaco Pharma exclusive rights to NB-7 (...) in mainland China"),          # EL2
    ("CN", "Origin Bio granted Chinaco Pharma exclusive rights to NB-7 […] in mainland China"),
    ("TERM", "Alpha Bio terminated the [...] license with Origin Bio"),                                     # EL4
    ("CN", C + "; Origin Bio retains [...] rights to NB-7 in the United States"),                           # EL7
    ("CN", "[Origin Bio] granted Chinaco Pharma exclusive rights to NB-7 in mainland China"),
    # HEADLINE-1WORD
    ("CN", "TAKEOVER, Mass., March 3, 2025 /PRNewswire/ -- " + C),                                         # DL16
    ("CN", "DIVESTITURE, U.S., March 3, 2025 /PRNewswire/ -- " + C),                                       # DL15
    ("CN", "TESSALY-CONTROLLED, U.S., March 3, 2025 /PRNewswire/ -- " + C),                                # DL10
    ("CN", "NORTH ACQUIRES, U.S., March 3, 2025 /PRNewswire/ -- " + C),
    # DATELINE-DATE: a dateline after the as-of date
    ("TERM", "BOSTON, Mass., March 3, 2026 /PRNewswire/ -- Alpha Bio terminated the U.S. license with Origin Bio"),
    # PAYONLY
    ("CN", "Chinaco Pharma paid Origin Bio $20 million"),                                                   # PY8
    ("OPT", "Chinaco Pharma paid Origin Bio $20 million"),                                                  # PY9
    ("CN", ("Origin Bio will receive an upfront payment of $20 million and is eligible to receive up to $200 million "
            "in milestone payments")),
]


@pytest.mark.parametrize(("row", "quote"), ATTACKS)
def test_every_rereview13_attack_blocks(row, quote):
    assert read(row, quote)


def test_ret_place2_names_both_places():
    why = read("CN", C + "; Origin Bio retains worldwide rights to NB-7, excluding the United States")
    assert "more than one place" in why and "worldwide" in why


def test_ret_partial2_names_the_use():
    assert "only for gastric cancer" in read("CN", C + "; Origin Bio retains U.S. rights to NB-7 for gastric cancer")


def test_ret_reason_a_retention_is_not_called_a_grant():
    why = read("CN", C + "; Origin Bio retains all rights to develop NB-7 in the United States")
    assert "keeps rights in words DealScreen does not read" in why
    assert "does not cover" not in why


def test_elision_quotes_the_mark():
    assert "[...]" in read("CN", "Origin Bio granted Chinaco Pharma exclusive rights to NB-7 [...] in mainland China")


def test_dateline_date_is_read_against_the_as_of_date():
    why = read("TERM", "BOSTON, Mass., March 3, 2026 /PRNewswire/ -- Alpha Bio terminated the U.S. license with "
                       "Origin Bio")
    assert "2026-03-03" in why and "as-of" in why


def test_payonly_says_what_is_missing():
    assert "only payments" in read("CN", "Chinaco Pharma paid Origin Bio $20 million")


def test_payonly_passes_when_the_row_covers_the_buyer_territory():
    row = dict(ROWS["CN"], territory="worldwide")
    assert quote_problem("Chinaco Pharma paid Origin Bio $20 million", row, "Origin Bio", AS_OF, US, names=["NB-7"],
                         vocabulary=DESCRIPTION) is None


CLEAN = [
    ("CN", (C + "; Origin Bio will receive an upfront payment of $20 million and is eligible to receive up to $200 "
            "million in milestone payments")),                                                                # UC41
    ("CN", (C + "; Origin Bio is eligible to receive up to $200 million in development and sales milestones, as "
            "well as tiered royalties on net sales")),                                                        # UC42
    ("GC", ("Chinaco Pharma obtains exclusive rights to NB-7 in Greater China; Origin Bio retains full rights to "
            "NB-7 outside of Greater China")),                                                                # UC43
    ("CN", "Chinaco Pharma will be responsible for the development and commercialization of NB-7 in mainland China"),
    ("CN", "NORTH WALES, Pa., March 3, 2025 /PRNewswire/ -- " + C),                                         # UC49
    ("CN", "SOUTH PLAINFIELD, N.J., March 3, 2025 /PRNewswire/ -- " + C),                                   # UC50
    ("CN", "WEST LAFAYETTE, Ind., March 3, 2025 /PRNewswire/ -- " + C),                                     # UC51
    ("RET", "Following the termination, Origin Bio regains U.S. rights to NB-7"),                           # UC54
    ("CN", C + "; Origin Bio retains global rights outside of China"),                                      # UC44
    ("CN", C + "; Origin Bio retains all rights in the U.S. and the rest of the world"),
    ("CN", "BOSTON, Mass., March 3, 2025 /PRNewswire/ -- " + C),
    ("CN", "BOSTON, Jan. 15, 2025 /PRNewswire/ -- " + C),                    # a dated dateline with "Jan."
    ("RET", "BOSTON, Jan. 15, 2025 /PRNewswire/ -- Alpha Bio returned U.S. rights to NB-7 to Origin Bio"),  # UC24
]


@pytest.mark.parametrize(("row", "quote"), CLEAN)
def test_clean_restatements_pass(row, quote):
    assert read(row, quote) is None


def test_end_to_end_a_retention_excluding_the_us_is_not_top_tier():
    v = _named_run([_quoted(ev(L, **CHINA), C + "; Origin Bio retains worldwide rights to NB-7, excluding the "
                                               "United States")])
    _not_top(v)


def test_end_to_end_a_termination_keeping_rights_outside_the_us_is_not_returned_top_tier():
    lic = ev(L, grantee="Alpha Bio", territory="United States", d="2024-03-01", deal="D1")
    end = _quoted(ev(T, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D1", deal="D9"),
                  "Alpha Bio terminated the U.S. license with Origin Bio; Origin Bio retains global rights to NB-7 "
                  "outside the United States")
    _not_top(_named_run([lic, end]))


def test_end_to_end_an_elided_quote_is_not_top_tier():
    _not_top(_named_run([_quoted(ev(L, **CHINA), "Origin Bio granted Chinaco Pharma exclusive rights to NB-7 [...] "
                                                 "in mainland China")]))


def test_c4_an_agent_variable_by_prefix_marks_the_shell():
    from bve.dealscreen.review import agent_shell

    assert agent_shell({"CLAUDE_CODE_SESSION_ID": "x"}) == "CLAUDE_CODE_SESSION_ID"
    assert agent_shell({"HOME": "/home/x"}) is None
