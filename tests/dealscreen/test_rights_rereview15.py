"""Cycle R1 revision 17: the inputs from adversarial re-review 15 (research/dealscreen_rights_v1/REREVIEW15.md).

A retention or an ending limited to a use blocks whatever the use's length, with or without a comma (RET-PARTIAL4,
PARTIAL-RETURN). A quote that ends in ",", ":", ";" or "-", or holds a dash between words, looks cut (CUT). "+", "=",
"@", "&" (outside a known name) and "%" (not after a number) are marks DealScreen does not read (FOOTNOTE2); "~"
before an amount is read (RM1). A bare "<place> rights" states no grant (BARE-RIGHTS).

Defaults as in ``test_rights_rereview10``. Parties are fictional; the tests assert no real-world facts."""

from __future__ import annotations

import pytest
from test_rights_rereview3 import CHINA, L, T, ev
from test_rights_rereview10 import _named_run, _not_top, _quoted
from test_rights_rereview14 import DL, C, read

G = "Origin Bio granted Chinaco Pharma exclusive rights to NB-7 in mainland China"
USE = "locally advanced unresectable or metastatic solid tumors"

ATTACKS = [
    # RET-PARTIAL4: a long use after a comma
    ("CN", C + "; Origin Bio retains U.S. rights to NB-7, for " + USE),                                     # RU1
    ("CN", C + "; Origin Bio retains U.S. rights to NB-7, for the treatment of " + USE),                    # RU2
    ("CN", C + "; Origin Bio retains U.S. rights to NB-7, for first-line locally advanced unresectable or "
           "metastatic gastric cancer"),                                                                     # RU7
    ("CN", "Origin Bio retains U.S. rights to NB-7, for " + USE),                                           # RU17
    # PARTIAL-RETURN: an ending or a return limited to a use
    ("RET", "Origin Bio regains U.S. rights to NB-7 for solid tumors"),                                     # PE1
    ("RET", "Alpha Bio returned U.S. rights to NB-7 for solid tumors to Origin Bio"),                       # PE2
    ("RET", "Origin Bio regained U.S. rights to NB-7, for gastric cancer"),                                 # PE3
    ("TERM", "Alpha Bio terminated the U.S. license with Origin Bio for NB-7 for solid tumors"),            # PE5
    ("RET", "Alpha Bio returned U.S. rights to NB-7 for first-line treatment to Origin Bio"),               # PE8
    # CUT
    ("CN", G + ","),                                                                                        # OM1
    ("CN", G + " --"),                                                                                      # OM3
    ("CN", G + ":"),                                                                                        # OM4
    ("CN", G + ";"),                                                                                        # OM12
    ("CN", G + " -"),
    ("CN", "Origin Bio granted Chinaco Pharma -- exclusive rights to NB-7 in mainland China"),              # OM11
    # FOOTNOTE2
    ("CN", G + "+"),                                                                                        # OM6
    ("CN", G + " ="),                                                                                       # OM7
    ("CN", G + " @"),                                                                                       # OM8
    ("CN", G + " &"),                                                                                       # OM9
    ("CN", G + " %"),                                                                                       # OM10
    ("CN", G + " !"),
    ("CN", G + " _"),
    ("CN", C + "; Chinaco Pharma will pay Origin Bio ~ about $20 million upfront"),
    # BARE-RIGHTS
    ("CN", "mainland China rights"),                                                                        # SR1
    ("CN", "China rights"),
]


@pytest.mark.parametrize(("row", "quote"), ATTACKS)
def test_every_rereview15_attack_blocks(row, quote):
    assert read(row, quote)


def test_ret_partial4_names_the_whole_use():
    assert "only for " + USE in read("CN", C + "; Origin Bio retains U.S. rights to NB-7, for " + USE)


def test_partial_return_says_another_party_may_hold_other_uses():
    why = read("RET", "Origin Bio regains U.S. rights to NB-7 for solid tumors")
    assert "ended or returned only for solid tumors" in why


def test_cut_quotes_the_end():
    assert "looks cut off" in read("CN", G + ",")


def test_a_mark_is_quoted_with_the_names_in_place():
    why = read("CN", G + "+")
    assert "'+'" in why and "NB-7 in mainland China+" in why


def test_bare_rights_says_it_states_no_grant():
    assert "bare" in read("CN", "mainland China rights")


CLEAN = [
    ("CN", C + "; Chinaco Pharma will pay Origin Bio ~$20 million upfront"),                                # RM1
    ("CN", C + "; Origin Bio retains rights to NB-7 in the rest of the world"),                             # RU8
    ("CN", G),
    ("CN", G + "."),
    ("CN", DL + G + "."),
    ("CN", "Origin Bio granted Chinaco Pharma exclusive rights to NB-7 for gastric cancer in mainland China"),
    ("RET", DL + "After the termination, Origin Bio regains U.S. rights to NB-7"),                          # DO4
    ("RET", "Origin Bio regains U.S. rights to NB-7"),
    ("TERM", "Alpha Bio terminated the U.S. license with Origin Bio for NB-7"),
    ("CN", "Chinaco Pharma licenses China rights; Origin Bio retains all rights outside China"),
]


@pytest.mark.parametrize(("row", "quote"), CLEAN)
def test_clean_restatements_pass(row, quote):
    assert read(row, quote) is None


def test_an_ampersand_inside_a_party_name_is_read():
    row = {"type": "LICENSE", "grantor": "Origin Bio", "grantee": "Chen & Wu Pharma", "territory": "mainland China",
           "date": "2025-01-01"}
    assert read(row, "Origin Bio granted Chen & Wu Pharma exclusive rights to NB-7 in mainland China") is None


def test_end_to_end_a_long_partial_retention_is_not_top_tier():
    _not_top(_named_run([_quoted(ev(L, **CHINA), C + "; Origin Bio retains U.S. rights to NB-7, for " + USE)]))


def test_end_to_end_a_cut_quote_is_not_top_tier():
    _not_top(_named_run([_quoted(ev(L, **CHINA), G + ",")]))


def test_end_to_end_a_bare_rights_quote_is_not_top_tier():
    _not_top(_named_run([_quoted(ev(L, **CHINA), "mainland China rights")]))


def test_end_to_end_a_partial_ending_is_not_returned_top_tier():
    lic = ev(L, grantee="Alpha Bio", territory="United States", d="2024-03-01", deal="D1")
    end = _quoted(ev(T, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D1", deal="D9"),
                  "Alpha Bio terminated the U.S. license with Origin Bio for NB-7 for solid tumors")
    _not_top(_named_run([lic, end]))
