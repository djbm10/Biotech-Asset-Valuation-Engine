"""Cycle R1 revision 16: the inputs from adversarial re-review 14 (research/dealscreen_rights_v1/REREVIEW14.md).

A quote that marks words as left out ("...", ". . .", a brace) or points to a note ("*", "#") blocks (ELISION2,
FOOTNOTE). A quote must state the row: a grant, a retention with a place, an ending or the event itself; payments,
"all other rights" and press furniture alone block on every row type (NOTHING-READ, PAYONLY-CPO). A retention limited
to a use written after a comma blocks (RET-PARTIAL3). "Upon the termination" is a contract term, not an event, and
"its termination" names no deal (UPON-COND). The word after a kept dateline date opens the sentence (UQ1, UQ7).

Defaults as in ``test_rights_rereview10``. Parties are fictional; the tests assert no real-world facts."""

from __future__ import annotations

import pytest
from test_rights_rereview3 import CHINA, L, T, ev
from test_rights_rereview10 import AS_OF, DESCRIPTION, US, _named_run, _not_top, _quoted
from test_rights_rereview11 import ROWS

from bve.dealscreen.rights_quote import quote_problem

C = "Chinaco Pharma licenses NB-7 for mainland China"
DL = "BOSTON, Mass., March 3, 2025 /PRNewswire/ -- "
CPO = {"type": "CO_PROMOTION_OPTION", "grantor": "Origin Bio", "grantee": "Chinaco Pharma",
       "territory": "mainland China", "date": "2025-01-01"}


def read(row: str | dict, quote: str) -> str | None:
    e = row if isinstance(row, dict) else ROWS[row]
    return quote_problem(quote, e, "Origin Bio", AS_OF, US, names=["NB-7"], vocabulary=DESCRIPTION)


ATTACKS = [
    # RET-PARTIAL3: a retention limited to a use, written after a comma
    ("CN", C + "; Origin Bio retains U.S. rights to NB-7, for solid tumors"),                               # PU1
    ("CN", C + "; Origin Bio retains U.S. rights to NB-7, in solid tumors"),                                # PU2
    ("CN", C + "; Origin Bio retains rights to NB-7, for solid tumors, in the United States"),              # PU3
    ("CN", C + "; Origin Bio retains U.S. rights to NB-7, for first-line treatment"),                       # PU4
    ("CN", C + "; Origin Bio retains U.S. rights to NB-7, for gastric cancer"),                             # PU5
    ("CN", C + "; Origin Bio retains U.S. rights to NB-7, for patients with advanced solid tumors"),        # PU8
    ("CN", C + "; Origin Bio retains U.S. rights to NB-7 in solid tumors"),
    # UPON-COND: a contract term, and "its" naming no deal
    ("TERM", "Upon the termination, Origin Bio regains U.S. rights to NB-7"),                               # FT2
    ("TERM", "Upon the expiration of the license agreement, Alpha Bio returns U.S. rights to NB-7 to Origin Bio"),
    ("RET", "Upon the termination, Origin Bio regains U.S. rights to NB-7"),                                # FT6
    ("TERM", "Upon the termination of the agreement, Origin Bio regains U.S. rights to NB-7"),              # FT7
    ("TERM", "After its termination, Origin Bio regains U.S. rights to NB-7"),                              # FT5
    # ELISION2: omission marks other than brackets
    ("CN", "Origin Bio granted Chinaco Pharma exclusive rights to NB-7 in mainland China …"),               # EL8
    ("CN", "... Chinaco Pharma licenses NB-7 for mainland China"),                                          # EL9
    ("CN", C + " ... Chinaco Pharma will pay Origin Bio $20 million upfront"),                              # EL10
    ("CN", C + " . . . Origin Bio retains all other rights to NB-7"),                                       # EL11
    ("CN", "Origin Bio granted Chinaco Pharma exclusive rights to NB-7 {...} in mainland China"),           # EL13
    ("TERM", "Alpha Bio terminated the U.S. license with Origin Bio..."),                                   # EL15
    ("CN", "Origin Bio granted Chinaco Pharma exclusive rights to NB-7 <...> in mainland China"),
    # FOOTNOTE
    ("CN", C + "*"),                                                                                        # FN1
    ("CN", C + " #"),                                                                                       # FN3
    # NOTHING-READ: no grant, no placed retention, no ending
    ("CN", "Goldman Sachs advised Origin Bio on the transaction."),                                         # PO4
    ("CN", "Origin Bio retains all other rights to NB-7"),                                                  # PO3
    ("CN", "Chinaco Pharma paid Origin Bio $20 million; Origin Bio retains all other rights to NB-7"),      # PO2
    ("OPT", "Origin Bio retains all remaining rights to NB-7"),                                             # PO12
    ("OPT", "Chinaco Pharma paid Origin Bio $5 million; Origin Bio retains all remaining rights to NB-7"),  # PO9
    # PAYONLY-CPO
    (CPO, "Chinaco Pharma paid Origin Bio $5 million"),                                                     # PO1
]


@pytest.mark.parametrize(("row", "quote"), ATTACKS)
def test_every_rereview14_attack_blocks(row, quote):
    assert read(row, quote)


def test_ret_partial3_names_the_use():
    why = read("CN", C + "; Origin Bio retains U.S. rights to NB-7, for solid tumors")
    assert "only for solid tumors" in why


def test_ret_partial3_names_a_title_case_use_without_marks():
    why = read("CN", C + "; Origin Bio retains U.S. rights to NB-7 for Gastric Cancer")
    assert why and "^" not in why


def test_elision2_quotes_the_mark():
    assert "..." in read("CN", "Origin Bio granted Chinaco Pharma exclusive rights to NB-7 in mainland China …")


def test_footnote_names_the_mark():
    assert "'*'" in read("CN", C + "*")


def test_nothing_read_says_what_is_missing():
    why = read("CN", "Goldman Sachs advised Origin Bio on the transaction.")
    assert "states no grant" in why


def test_upon_is_not_read_as_an_ending():
    assert read("TERM", "Upon the termination, Origin Bio regains U.S. rights to NB-7")


CLEAN = [
    ("CN", DL + ("Under the terms of the agreement, Chinaco Pharma will receive exclusive rights to develop and "
                 "commercialize NB-7 in mainland China.")),                                                   # UQ1
    ("CN", DL + "The license agreement grants Chinaco Pharma exclusive rights to NB-7 in mainland China."),  # UQ7
    ("CN", ("Under the terms of the agreement, Chinaco Pharma will receive exclusive rights to develop and "
            "commercialize NB-7 in mainland China.")),                                                        # UQ1n
    ("TERM", DL + "Following the termination, Origin Bio regains U.S. rights to NB-7."),                    # UQ6
    ("RET", "Following the termination, Origin Bio regains U.S. rights to NB-7"),                           # UC54
    ("TERM", "Following the termination of the license agreement, Origin Bio regains U.S. rights to NB-7"),
    ("CN", C + "; Origin Bio retains all rights to NB-7 outside of mainland China"),
    ("CN", C + "; Origin Bio retains all other rights to NB-7"),          # beside a grant, "all other rights" is fine
    ("CN", C + "; Origin Bio retains all rights in the U.S. and the rest of the world"),
    ("CN", C + "; Origin Bio retains U.S. rights to NB-7"),
    ("CN", C + "; Chinaco Pharma paid Origin Bio $20 million"),
    (CPO, "Origin Bio granted Chinaco Pharma an option to co-promote NB-7 in mainland China"),
]


@pytest.mark.parametrize(("row", "quote"), CLEAN)
def test_clean_restatements_pass(row, quote):
    assert read(row, quote) is None


def test_end_to_end_an_adviser_line_is_not_top_tier():
    _not_top(_named_run([_quoted(ev(L, **CHINA), "Goldman Sachs advised Origin Bio on the transaction.")]))


def test_end_to_end_a_trailing_ellipsis_is_not_top_tier():
    _not_top(_named_run([_quoted(ev(L, **CHINA), "Origin Bio granted Chinaco Pharma exclusive rights to NB-7 in "
                                                 "mainland China …")]))


def test_end_to_end_a_retention_for_one_use_is_not_top_tier():
    _not_top(_named_run([_quoted(ev(L, **CHINA), C + "; Origin Bio retains U.S. rights to NB-7, for solid tumors")]))


def test_end_to_end_upon_termination_is_not_returned_top_tier():
    lic = ev(L, grantee="Alpha Bio", territory="United States", d="2024-03-01", deal="D1")
    end = _quoted(ev(T, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D1", deal="D9"),
                  "Upon the termination, Origin Bio regains U.S. rights to NB-7")
    _not_top(_named_run([lic, end]))
