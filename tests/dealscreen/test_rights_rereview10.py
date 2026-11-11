"""Cycle R1 revision 12: the inputs from adversarial re-review 10 (research/dealscreen_rights_v1/REREVIEW10.md).

Revision 12 replaces the word lists of revisions 9-11 with fixed sentence templates per row type
(``rights_template``): a clause of a cited quote passes only when it is one of a few sentences for its row's type,
with the row's own parties in their roles, the program, a place inside the row's territory, a date not after the
as-of date and an amount. Anything else blocks until a human analyst records ``CONFIRM_RIGHTS_ROW`` for the row; the
confirmation is tied to a hash of the row and stops applying when the row changes. The ledger now requires one legal
entity for an acquired party (OWNER-KEY2) and treats two acquirers of one party as contested (ACQ-TWO).

Defaults as in ``test_rights_rereview3``: buyer territory US, as-of 2025-06-01, company and licensor "Origin Bio"
(the review's "Nerida Bio"), program "NB-7". Parties are fictional; the tests assert no real-world facts."""

from __future__ import annotations

from datetime import date

import pytest
from test_rights_rereview3 import AQ, CHINA, OL, TIER1, TOP, L, O, T, blocked, ev, run

from bve.dealscreen import rights_position as rp
from bve.dealscreen.commercial import assess
from bve.dealscreen.models import LandscapeAsset
from bve.dealscreen.review import (
    Action,
    DecisionContext,
    DecisionLog,
    DecisionRejected,
    ReviewerKind,
)
from bve.dealscreen.rights import RIGHTS_RETURNED
from bve.dealscreen.rights_model import cite_event, row_sha256
from bve.dealscreen.rights_quote import quote_problem
from bve.dealscreen.rights_template import date_problem, descriptor_words, mark_dates
from bve.dealscreen.rights_words import POSITION_WORDS
from bve.dealscreen.screening import program_transaction
from bve.dealscreen.transaction import TransactionPreferences

AS_OF = date(2025, 6, 1)
US = frozenset({"US"})
ROWS = {
    "CN": {"type": "LICENSE", "grantor": "Origin Bio", "grantee": "Chinaco Pharma", "territory": "mainland China",
           "date": "2025-01-01"},
    "TERM": {"type": "TERMINATION", "grantor": "Origin Bio", "grantee": "Alpha Bio", "territory": "United States",
             "date": "2025-01-15"},
    "RET": {"type": "RIGHTS_RETURNED", "grantor": "Origin Bio", "grantee": "Alpha Bio", "territory": "United States",
            "date": "2025-01-15"},
    "LAPSE": {"type": "OPTION_LAPSED", "grantor": "Origin Bio", "grantee": "Alpha Bio", "territory": "United States",
              "date": "2025-01-15"},
    "ACQ": {"type": "ACQUISITION", "grantor": "Origin Bio", "grantee": "Omega Holdings", "territory": "Worldwide",
            "date": "2025-02-01"},
}
DESCRIPTION = descriptor_words(["Claudin 18.2", "anti-CLDN18.2 ADC from Tessaly", "antibody-drug conjugate",
                                "gastric cancer", "AJCC (American Joint Committee on Cancer) stage IV gastric cancer"])


def read(row: str, quote: str) -> str | None:
    return quote_problem(quote, ROWS[row], "Origin Bio", AS_OF, US, names=["NB-7"], vocabulary=DESCRIPTION)


def _quoted(event, quote: str):
    return event.model_copy(update={"evidence_quote": quote})


def _not_top(v) -> None:
    assert v.tier not in TOP, (v.tier, v.position, v.top_tier_blockers)


def _named_run(events, confirmed=None):
    asset = LandscapeAsset(asset_id="A1", source_system="T", external_id="P1", program_name="NB-7",
                           company="Origin Bio", row_numbers=[1], claims=[])
    return program_transaction(events, assess(asset, questions=["Q?"], confirmed_findings=()), company="Origin Bio",
                               territory=US, as_of=AS_OF, max_age_days=730,
                               prefs=TransactionPreferences(encumbered_rights="deprioritize"), program_names=["NB-7"],
                               confirmed_rows=confirmed)


# -- Every REREVIEW10 input blocks (§2a-2k) ------------------------------------------------------------------------
ATTACKS = [
    ("TERM", "Alpha Bio has the U.S. rights to NB-7"),                                                         # E1
    ("TERM", "Alpha Bio returns U.S. development rights to Origin Bio; Alpha Bio has the commercial rights"),  # E2
    ("RET", "Alpha Bio returns U.S. rights to Origin Bio; both have the U.S. rights"),                         # E7
    ("RET", "Alpha Bio returns U.S. development rights to Origin Bio; they own the commercial rights"),        # E8
    ("RET", "Alpha Bio returns U.S. rights to Origin Bio, which handed the rights back to Alpha Bio"),         # E9
    ("LAPSE", "Alpha Bio let the option lapse; Alpha Bio has the U.S. rights"),                                # LP3
    ("CN", "Chinaco Pharma licenses mainland China rights to NB-7; Chinaco Pharma will own all rights to NB-7"),  # L3
    ("CN", "Chinaco Pharma licenses mainland China rights to NB-7 and has all rights to NB-7"),                # L5
    ("CN", "Chinaco Pharma licenses mainland China rights to NB-7 and will receive all rights upon approval"),  # L1
    ("CN", "Chinaco Pharma receives full rights to NB-7"),                                                     # L2
    ("CN", "Chinaco Pharma licenses NB-7 for mainland China and receives all-territory rights"),               # L13
    ("RET", "Alpha Bio returns U.S. rights to Origin Bio after the phase 3 trial"),                            # E3
    ("RET", "Alpha Bio returns U.S. rights to Origin Bio following approval"),                                 # E4
    ("TERM", "Alpha Bio's U.S. license to NB-7 ends at the end of the term"),                                  # E5
    ("TERM", "Alpha Bio's U.S. rights to NB-7 may revert to Origin Bio"),                                      # E10 MAY
    ("TERM", "Alpha Bio may end the U.S. license to NB-7"),                                                    # E11
    ("LAPSE", "Alpha Bio may exercise the U.S. option"),                                                       # LP4
    ("LAPSE", "The U.S. option to NB-7 may lapse"),                                                            # LP5
    ("ACQ", "Omega Holdings may acquire Origin Bio for $5 per share"),                                         # A7
    ("TERM", "Alpha Bio terminated the U.S. license on December 1"),                                           # E12
    ("TERM", "Alpha Bio terminated the U.S. license in Q4"),                                                   # E13
    ("TERM", "Alpha Bio terminated the U.S. license in H2"),                                                   # E14
    ("TERM", "Alpha Bio terminated the U.S. license in December '26"),                                         # E15
    ("TERM", "Alpha Bio terminated the U.S. license on Friday"),                                               # E20
    ("TERM", "Alpha Bio gave notice of termination of the U.S. license on January 10, 2025"),                  # E16
    ("TERM", "Alpha Bio provided notice of termination on January 10, 2025, effective following approval"),    # E17
    ("LAPSE", "Alpha Bio did not let the U.S. option lapse"),                                                  # LP1
    ("LAPSE", "Alpha Bio did exercise the U.S. option"),                                                       # LP2
    ("LAPSE", "The option did not expire"),                                                                    # LP6
    ("CN", ("Chinaco Pharma licenses NB-7 for mainland China; Origin Bio announced the sale of all rights to NB-7 for "
           "$40 million in cash")),                                                                             # L4
    ("CN", ("Chinaco Pharma licenses NB-7 for mainland China; Origin Bio transferred all rights to NB-7 for $40 "
           "million")),                                                                                         # L7
    ("ACQ", "Omega Holdings acquires Origin Bio; NB-7 was sold for $50 million in cash"),                      # A1
    ("ACQ", "Omega Holdings acquires Origin Bio, which sold NB-7 prior to the merger"),                        # A2
    ("ACQ", "Omega Holdings acquires Origin Bio and sells NB-7"),                                              # A4
    ("CN", "Chinaco Pharma licenses NB-7 for mainland China; NB-7 is also licensed to Chinaco Holdings"),      # L10
    ("CN", "Chinaco Pharma licenses NB-7 for mainland China; NB-7 is also licensed to Chinaco Group"),         # L11
    ("RET", "Alpha Bio returns U.S. rights to Origin Bio; Alpha Holdings has the U.S. rights"),                # E6
    ("RET", "Alpha Bio returns U.S. rights to Origin Bio; X4 has the U.S. rights"),                            # E18
    ("CN", "Chinaco Pharma licenses NB-7 for mainland China; NB-7 is also licensed to C4"),                    # L15
    ("CN", "Chinaco Pharma licenses NB-7 for mainland China (Nasdaq-listed Tessaly Pharma holds U.S. rights)"),  # L16
    ("CN", "Chinaco Pharma licenses NB-7 for mainland China (U.S. rights: Tessaly Pharma, NYSE: TSLY)"),       # L17
    ("CN", ("Tessaly Pharma Holds Rights, BOSTON, March 3, 2025 -- Chinaco Pharma licenses NB-7 for mainland "
           "China")),                                                                                           # L18
    ("CN", "Chinaco Pharma licenses NB-7 for mainland China and receives American rights"),                    # V2
    ("CN", "Chinaco Pharma licenses NB-7 for mainland China; Tessaly has all rights to NB-7"),                 # V3
    ("RET", "Alpha Bio returns U.S. rights to Origin Bio; Tessaly has the U.S. rights"),                       # V4
    ("ACQ", "Omega Holdings will acquire Origin Bio, subject to closing conditions"),                          # A3
    ("ACQ", "Omega Holdings acquires Origin Bio for $5 per share, pending approval"),                          # A6
    ("ACQ", "Omega Holdings acquires 10 percent of the shares of Origin Bio"),                                 # A5
    ("CN", "Chinaco Pharma licenses NB-7 for mainland China; Origin Bio pays royalties on all sales of NB-7"),  # L8
    ("CN", "Chinaco Pharma licenses NB-7 for mainland China; NB-7 is also licensed to Chinaco Pharma"),        # L12
    ("CN", "Advanced Medicine has all rights to NB-7"),                                                        # L14
]


@pytest.mark.parametrize(("row", "quote"), ATTACKS)
def test_every_rereview10_quote_blocks(row, quote):
    assert read(row, quote) is not None


# -- Close variants of the same holes ----------------------------------------------------------------------------
VARIANTS = [
    ("CN", "Chinaco Pharma licenses NB-7 in Greater China"),                       # a place wider than the row
    ("CN", "Origin Bio licensed NB-7 to Chinaco Pharma in China and the U.S."),
    ("CN", "Origin Bio licensed NB-7 to Chinaco Pharma outside the United States"),
    ("RET", "Alpha Bio returned U.S. rights to Origin Bio in 2026"),               # a year after the as-of date
    ("RET", "Alpha Bio returned U.S. rights to Origin Bio effective 2026"),
    ("TERM", "Alpha Bio terminated the U.S. license effective December 1, 2025"),
    ("CN", "Chinaco Pharma licensed NB-7 from Origin Bio, a subsidiary of Sideco Bio"),
    ("CN", "Origin Bio licensed NB-7 to Chinaco Pharma; Sideco Bio advised Origin Bio and Alpha Bio holds U.S. rights"),
    ("CN", "Chinaco Pharma licensed NB-7 to Origin Bio in mainland China"),         # roles reversed
    ("RET", "Origin Bio returned U.S. rights to NB-7 to Alpha Bio"),               # roles reversed
    ("CN", "Origin Bio licensed NB-7 to Chinaco Pharma, Inc. and Chinaco Holdings"),
    ("ACQ", "Omega Holdings acquires Origin Bio for $5 per share"),                # present tense: a pending deal
    ("ACQ", "Omega Holdings announced the acquisition of Origin Bio"),
    ("ACQ", "Omega Holdings agreed to acquire Origin Bio"),
    ("CN", ("Origin Bio licensed NB-7 to Chinaco Pharma in mainland China and Origin Bio licensed NB-7 to Alpha Bio in "
           "the U.S.")),
    ("CN", "Origin Bio licensed NB-7, an ADC partnered with Tessaly, to Chinaco Pharma in mainland China"),
    ("CN", "Origin Bio licensed NB-7, a phase 3 candidate in the U.S., to Chinaco Pharma in mainland China"),
    ("CN", "Origin Bio licensed NB-7 to Chinaco Pharma in mainland China for $20 million and an option on U.S. rights"),
    ("LAPSE", "Alpha Bio's option to license NB-7 lapsed, and Alpha Bio acquired NB-7"),
    ("RET", "Alpha Bio returned U.S. rights to NB-7 to Origin Bio and Sideco Bio"),
    ("RET", "U.S. rights to NB-7 reverted to Origin Bio from Alpha Bio, which retains a royalty"),
    ("CN", "Origin Bio licensed NB-7 to Chinaco Pharma in mainland China; NB-7 is licensed to Alpha Bio"),
    ("CN", "Origin Bio licensed NB-7 to Chinaco Pharma in mainland China, Alpha Bio said"),
    ("CN", ("Origin Bio licensed NB-7 to Chinaco Pharma in mainland China, said Jane Doe, Chief Executive Officer of "
           "Tessaly Pharma")),
    ("CN", "Origin Bio licensed NB-7 to Chinaco Pharma in mainland China in December 2025"),
    ("CN", "Origin Bio licensed NB-7 to Chinaco Pharma in mainland China (NYSE: TSLY holds U.S. rights)"),
    ("CN", ("BOSTON, March 3, 2025 /Tessaly Pharma holds U.S. rights/ -- Origin Bio licensed NB-7 to Chinaco Pharma in "
           "mainland China")),
    ("CN", "Origin Bio licensed NB-7 to Chinaco Pharma (OB) in mainland China"),    # an undefined acronym
    ("RET", "Alpha Bio Returns U.S. Rights To NB-7 To Origin Bio; Tessaly Holds Rights"),  # a headline cannot hide one
    ("RET", "ALPHA BIO RETURNS U.S. RIGHTS TO ORIGIN BIO; TESSALY PHARMA HOLDS U.S. RIGHTS"),
    ("RET", "Alpha Bio Returns U.S. Rights To Origin Bio After Approval"),
    ("CN", "Chinaco Pharma licenses the Tessaly antibody NB-7 for mainland China"),       # a name inside a description
    ("CN", "Chinaco Pharma licenses the U.S. antibody NB-7 for mainland China"),          # a place inside one
    ("CN", "Chinaco Pharma licensed its anti-CLDN18.2 ADC NB-7 to Origin Bio in mainland China"),  # "its" is the grantee's
    ("CN", "Chinaco Pharma licenses NB-7 for mainland China for gastric cancer and the U.S."),
    ("CN", "Chinaco Pharma licenses NB-7 for mainland China for Tessaly"),
]


@pytest.mark.parametrize(("row", "quote"), VARIANTS)
def test_close_variants_block(row, quote):
    assert read(row, quote) is not None


# -- Clean restatements pass ----------------------------------------------------------------------------------------
CLEAN = [
    ("CN", "Origin Bio licensed NB-7 to Chinaco Pharma in mainland China"),
    ("CN", "Chinaco Pharma licenses mainland China rights to NB-7"),
    ("CN", "Chinaco Pharma licenses NB-7 for mainland China"),
    ("CN", "Origin Bio granted Chinaco Pharma an exclusive license to develop and commercialize NB-7 in mainland China"),
    ("CN", "Origin Bio and Chinaco Pharma entered into an exclusive license agreement for NB-7 in mainland China"),
    ("CN", ("Chinaco Pharma and Origin Bio announced that they have entered into an exclusive license agreement for "
           "NB-7 in mainland China")),
    ("CN", ("BOSTON, March 3, 2025 /PRNewswire/ -- Origin Bio (Nasdaq: ORGN) today announced that it has licensed "
           "NB-7, an anti-Claudin18.2 ADC, to Chinaco Pharma Co., Ltd. in mainland China")),
    ("CN", "CAMBRIDGE, Mass.--(BUSINESS WIRE)--Origin Bio licensed NB-7 to Chinaco Pharma in mainland China"),
    ("CN", ("Chinaco Pharma obtained exclusive rights to develop and commercialize NB-7 in mainland China from Origin "
           "Bio for $20 million upfront and up to $200 million in milestones")),
    ("CN", "On January 1, 2025, Origin Bio licensed NB-7 to Chinaco Pharma in mainland China"),
    ("CN", ("Origin Bio licensed NB-7 to Chinaco Pharma in mainland China, said Jane Doe, Chief Executive Officer of "
           "Origin Bio")),
    ("CN", "Origin Bio, a clinical-stage biotechnology company, licensed NB-7 to Chinaco Pharma in mainland China"),
    ("CN", ("Origin Bio licensed NB-7, an investigational anti-CLDN18.2 antibody-drug conjugate for gastric cancer, to "
           "Chinaco Pharma in Greater China excluding Hong Kong, Macau and Taiwan")),
    ("CN", "ORIGIN BIO LICENSES NB-7 TO CHINACO PHARMA IN MAINLAND CHINA"),
    ("CN", "Chinaco Pharma licenses China rights; Origin Bio retains all rights outside China"),  # a plain form
    ("RET", "Alpha Bio returned U.S. rights to NB-7 to Origin Bio"),
    ("RET", "Alpha Bio returns U.S. rights to Origin Bio"),
    ("RET", "Alpha Bio Returns U.S. Rights to NB-7 to Origin Bio"),
    ("RET", "Alpha Bio returned U.S. rights to Origin Bio in 2025"),            # the year holds the row's own date
    ("RET", "Alpha Bio returned U.S. rights to Origin Bio on January 10th, 2025"),
    ("RET", "U.S. rights to NB-7 reverted to Origin Bio"),
    ("RET", "Origin Bio regained all U.S. rights to NB-7 from Alpha Bio"),      # "all": the row covers the buyer
    ("TERM", "Alpha Bio terminated the license agreement with Origin Bio for NB-7"),
    ("TERM", "The license agreement between Origin Bio and Alpha Bio was terminated effective January 15, 2025"),
    ("TERM", "Alpha Bio terminated the U.S. license for convenience"),
    ("TERM", "Alpha Bio returns U.S. rights to Origin Bio"),                    # a termination and a return are one ending
    ("LAPSE", "Alpha Bio's option to license NB-7 lapsed unexercised"),
    ("LAPSE", "Alpha Bio declined to exercise its option"),
    ("LAPSE", "Alpha Bio did not exercise its option to license NB-7"),
    ("LAPSE", "The U.S. option to NB-7 lapsed"),
    ("ACQ", "Omega Holdings acquired Origin Bio for $5 per share in cash"),
    ("ACQ", "Omega Holdings completed its acquisition of Origin Bio"),
    ("ACQ", "Omega Holdings completes acquisition of Origin Bio"),
    ("ACQ", "Origin Bio was acquired by Omega Holdings"),
    ("ACQ", "Omega Holdings completed its tender offer for all outstanding shares of Origin Bio"),
    ("CN", "Chinaco Pharma licenses the Claudin18.2 antibody NB-7 for mainland China"),   # a description before P
    ("CN", "Origin Bio licensed its anti-CLDN18.2 ADC NB-7 to Chinaco Pharma in mainland China"),  # the grantor's own
    ("CN", "Chinaco Pharma licenses NB-7 for mainland China for gastric cancer"),        # an indication after R
]


@pytest.mark.parametrize(("row", "quote"), CLEAN)
def test_clean_restatements_pass(row, quote):
    assert read(row, quote) is None


# -- Clean cases of earlier reviews that now block (usefulness costs, disclosed in REREVIEW10_RESPONSE.md) ---------
REV12_BLOCKED = [
    # revision 14: the payment sentence passes again (review R1v13 UC33), see test_rights_rereview12.py
    ("CN", "Origin Bio transferred China rights to NB-7 to Chinaco Pharma"),                             # SALE
    ("CN", "Chinaco Pharma, a subsidiary of Chinaco Group, licenses NB-7 for mainland China"),           # a parent
    ("CN", "Chinaco Pharma obtains exclusive China rights to NB-7, its third China deal in a row"),
    ("CN", "Chinaco Pharma will pay royalties on net sales in mainland China"),
    ("CN", "Chinaco Pharma licenses rights in mainland China, Hong Kong and Macau"),                     # wider place
    ("CN", "Origin Bio licensed China rights to NB-7 to Chinaco Pharma; NB-7 has Breakthrough Therapy Designation"),
    ("TERM", "Alpha Bio terminated its license; all rights to NB-7 revert to Origin Bio"),                # "revert"
    ("TERM", "Following a portfolio review, Alpha Bio returned U.S. rights to NB-7 to Origin Bio"),
    ("TERM", "Alpha Bio returned U.S. rights to Origin Bio after a strategic review"),
    ("TERM", "Origin Bio regains full global rights to NB-7 after Alpha Bio exits"),
    ("TERM", "Alpha Bio, Inc., and Origin Bio announced the end of the U.S. license"),
    ("ACQ", "Omega Holdings acquires Origin Bio; Harlow Partners LLC is acting as financial advisor to Origin Bio"),
    ("ACQ", ("Under the agreement, Omega Holdings will pay EUR 422 million to acquire 100% of the equity in Origin "
            "Bio.")),
    ("ACQ", "Omega Holdings will acquire Origin Bio for $25.00 per share in cash"),
]


@pytest.mark.parametrize(("row", "quote"), REV12_BLOCKED)
def test_earlier_clean_cases_that_now_block(row, quote):
    assert read(row, quote) is not None


# -- Dates ------------------------------------------------------------------------------------------------------------
def test_may_in_lower_case_is_never_a_month():
    text, periods = mark_dates("Alpha Bio may end the license; signed May 3, 2025; in May 2025")
    assert "may end" in text and len(periods) == 2


def test_a_period_after_the_as_of_date_passes_only_when_it_holds_the_row_date():
    _, (year,) = mark_dates("in 2025")
    assert date_problem([year], AS_OF, date(2025, 1, 15)) is None
    assert date_problem([year], AS_OF, date(2025, 8, 1)) is not None   # the row itself is after the as-of date
    assert date_problem([year], AS_OF, None) is not None


def test_an_ordinal_day_is_a_date():
    _, (day,) = mark_dates("on January 10th, 2025")
    assert day.start == day.end == date(2025, 1, 10)


# -- Description words ---------------------------------------------------------------------------------------------
def test_description_words_never_include_a_capitalised_word_or_an_alias():
    words = descriptor_words(["AJCC (American Joint Committee on Cancer) stage IV gastric cancer",
                              "anti-CLDN18.2 ADC from Tessaly", "Claudin 18.2"])
    assert {"gastric", "cancer", "anti-cldn18.2", "adc", "claudin18.2"} <= words
    assert not {"american", "tessaly", "joint", "committee", "from", "on"} & words


# -- CONFIRM_RIGHTS_ROW: a human analyst confirms a row; nothing else can -------------------------------------------
def _ending(quote: str):
    lic = ev(L, grantee="Alpha Bio", territory="United States", d="2024-03-01", deal="D1")
    end = _quoted(ev(RIGHTS_RETURNED, grantee="Alpha Bio", territory="United States", d="2025-01-15",
                     related="D1"), quote)
    return [lic, end], end


QUOTE = "Alpha Bio and Origin Bio said U.S. rights went back to Origin Bio last quarter"


def test_a_confirmed_row_is_not_read_again_while_it_is_unchanged():
    events, end = _ending(QUOTE)
    _not_top(_named_run(events))
    record = {"row_sha256": row_sha256(cite_event(end)), "reviewer_id": "jdoe", "decision_id": "dec:00001",
              "timestamp": "2025-05-01T00:00:00+00:00"}
    # revision 13: confirmations are keyed by the row's content hash (review R1v12 CONFIRM-REIMPORT)
    v = _named_run(events, confirmed={record["row_sha256"]: record})
    assert v.tier == TIER1, v.top_tier_blockers
    assert any("confirmed as restating the row by jdoe, recorded as a human analyst" in r for r in v.reasons)


def test_a_confirmation_lapses_when_the_row_changes():
    events, end = _ending(QUOTE)
    record = {"row_sha256": row_sha256(cite_event(end)), "reviewer_id": "jdoe", "decision_id": "dec:00001",
              "timestamp": "2025-05-01", "event_id": end.event_id}
    changed = end.model_copy(update={"evidence_quote": QUOTE + "; Tessaly Pharma holds U.S. rights"})
    v = _named_run([events[0], changed], confirmed={record["row_sha256"]: record})
    _not_top(v)
    assert blocked(v, "a confirmation was recorded for an earlier version of this row")


def test_the_block_question_asks_for_a_confirmation():
    # revision 13: the memo prints the question, so it names no action code or event id (review R1v12 MEMO-CODE);
    # the workbook's rights evidence lists the event id
    events, end = _ending(QUOTE)
    v = _named_run(events)
    assert any("a human analyst who has read the source can confirm the row in DealScreen" in q for q in v.questions)
    assert not any(end.event_id in q for q in v.questions)


def _context(event) -> DecisionContext:
    return DecisionContext(dispositions={}, claim_ids=set(), finding_ids=set(), flag_ids=set(),
                           rights_row_hashes={event.event_id: row_sha256(cite_event(event))})


def test_only_a_human_can_confirm_a_rights_row(tmp_path):
    _, end = _ending(QUOTE)
    log = DecisionLog(tmp_path / "decisions.jsonl")
    for kind in (ReviewerKind.AI_PREPARED, ReviewerKind.SYNTHETIC_FIXTURE):
        with pytest.raises(DecisionRejected):
            log.record(action=Action.CONFIRM_RIGHTS_ROW, subject_id=end.event_id, new_state="CONFIRMED",
                       reviewer_id="bot", rationale="read it", reviewer_kind=kind, context=_context(end))
    with pytest.raises(DecisionRejected):  # an unknown row
        log.record(action=Action.CONFIRM_RIGHTS_ROW, subject_id="rx:none", new_state="CONFIRMED",
                   reviewer_id="jdoe", rationale="read it", reviewer_kind=ReviewerKind.HUMAN, context=_context(end))
    with pytest.raises(DecisionRejected):  # no workspace context
        log.record(action=Action.CONFIRM_RIGHTS_ROW, subject_id=end.event_id, new_state="CONFIRMED",
                   reviewer_id="jdoe", rationale="read it", reviewer_kind=ReviewerKind.HUMAN)
    rec = log.record(action=Action.CONFIRM_RIGHTS_ROW, subject_id=end.event_id, new_state="CONFIRMED",
                     reviewer_id="jdoe", rationale="read the release", reviewer_kind=ReviewerKind.HUMAN,
                     context=_context(end))
    assert rec["detail"]["row_sha256"] == row_sha256(cite_event(end))
    confirmed = DecisionLog(tmp_path / "decisions.jsonl").state.review_inputs([]).confirmed_rights_rows
    assert confirmed[row_sha256(cite_event(end))]["reviewer_id"] == "jdoe"
    log.record(action=Action.CONFIRM_RIGHTS_ROW, subject_id=end.event_id, new_state="WITHDRAWN",
               reviewer_id="jdoe", rationale="source corrected", reviewer_kind=ReviewerKind.HUMAN,
               context=_context(end))
    assert not DecisionLog(tmp_path / "decisions.jsonl").state.review_inputs([]).confirmed_rights_rows


# -- Ledger: OWNER-KEY2 and ACQ-TWO (§2k) ---------------------------------------------------------------------------
@pytest.mark.parametrize("acquired", ["Origin Bio Holdings", "Origin Bio Group"])
def test_owner_key2_a_holdings_or_group_entity_is_not_the_company(acquired):
    v = run([ev(L, **CHINA), ev(AQ, grantee="Omega Holdings", grantor=acquired, territory="Worldwide",
                                d="2025-02-01")])
    assert v.position != rp.P_OWNER_ACQUIRED
    _not_top(v)


def test_acq_two_two_acquirers_of_one_party_are_contested():
    v = run([ev(L, **CHINA),
             ev(AQ, grantee="Omega Holdings", grantor="Origin Bio", territory="Worldwide", d="2025-02-01"),
             ev(AQ, grantee="Sideco Bio", grantor="Origin Bio", territory="Worldwide", d="2025-03-01")])
    _not_top(v)
    assert blocked(v, "recorded as acquired by")
    assert v.owner not in ("Omega Holdings", "Sideco Bio")


def test_one_acquirer_with_two_spellings_is_not_contested():
    v = run([ev(L, **CHINA),
             ev(AQ, grantee="Omega Holdings", grantor="Origin Bio", territory="Worldwide", d="2025-02-01"),
             ev(AQ, grantee="Omega Holdings, Inc.", grantor="Origin Bio", territory="Worldwide", d="2025-02-01")])
    assert v.position == rp.P_OWNER_ACQUIRED


# -- Labels (§4) -----------------------------------------------------------------------------------------------------
def test_lbl_date_the_unapplied_label_does_not_blame_the_date():
    assert POSITION_WORDS[rp.P_NOT_APPLIED] == "rights rows recorded, none gives a position on the as-of date"
    v = run([ev(L, **CHINA), ev(AQ, grantee="Omega Holdings", grantor="Ganyco Bio", territory="Worldwide",
                                d="2025-02-01")])
    assert not any("none applies on the as-of date" in r for r in v.reasons)


def test_an_option_and_its_lapse_still_clear_with_a_clean_quote():
    option = ev(O, grantee="Alpha Bio", territory="United States", d="2024-03-01", deal="D2")
    end = _quoted(ev(OL, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D2"),
                  "Alpha Bio's option to license NB-7 lapsed unexercised")
    assert _named_run([option, end]).tier == TIER1


def test_a_termination_row_with_a_clean_return_quote_clears():
    lic = ev(L, grantee="Alpha Bio", territory="United States", d="2024-03-01", deal="D1")
    end = _quoted(ev(T, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D1"),
                  "Alpha Bio returns U.S. rights to Origin Bio")
    assert _named_run([lic, end]).tier == TIER1
