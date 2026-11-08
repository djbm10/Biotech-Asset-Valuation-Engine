"""Cycle R1 revision 14: the inputs from adversarial re-review 12 (research/dealscreen_rights_v1/REREVIEW12.md).

Revision 14 reads a retention ("<company> retains rights ...") only when the row's grantor is the program's company
and the places it names cover the buyer territory; it names no place only with "all other / remaining rights", and a
retention of development or commercial rights alone, or a future one, blocks (RET-GRANTOR, RET-PLACE). A dateline
city of more than one word must be a listed city (HEADLINE3). Signing sentences need a place unless the row covers
the buyer territory (UNPLACED2). Two acquirers of one company are rivals however the company is written (ACQ-TWO2).
A subsidiary clause is removed only when the parent is the program's company (SUBSID). A question mark blocks
(PUNCT). "worldwide rights, excluding X" is one place (ROW12-REASON). Payment and milestone sentences between the
row's parties pass (UC33, UC34), and a "Province" may follow a listed region in a dateline (UC35). A rights row
confirmation is refused in an AI agent's shell for every caller, also when the variable is empty (CONFIRM-API), and a
withdrawal removes every version of the row's confirmation (WITHDRAW-STALE).

Defaults as in ``test_rights_rereview10``. Parties are fictional; the tests assert no real-world facts."""

from __future__ import annotations

import pytest
from test_rights_rereview3 import AQ, CHINA, TIER1, L, T, blocked, ev, run
from test_rights_rereview10 import AS_OF, DESCRIPTION, US, _named_run, _not_top, _quoted
from test_rights_rereview11 import ROWS, _context, _ending

from bve.dealscreen import rights_position as rp
from bve.dealscreen.review import Action, DecisionLog, DecisionRejected, ReviewerKind, agent_shell
from bve.dealscreen.rights_quote import quote_problem
from bve.dealscreen.rights_template import mark_places

C = "Chinaco Pharma licenses NB-7 for mainland China"
SUB = {"type": "LICENSE", "grantor": "Chinaco Pharma", "grantee": "Sideco Bio", "territory": "mainland China",
       "date": "2025-02-01"}


def read(row: str | dict, quote: str) -> str | None:
    e = ROWS[row] if isinstance(row, str) else row
    return quote_problem(quote, e, "Origin Bio", AS_OF, US, names=["NB-7"], vocabulary=DESCRIPTION)


# -- §2a-2f: every REREVIEW12 path into a top tier blocks -------------------------------------------------------------
ATTACKS = [
    # RET-GRANTOR: a sublicensing licensee is the row's grantor, not the program's company
    (SUB, ("Chinaco Pharma licensed NB-7 to Sideco Bio for mainland China; Chinaco Pharma retains all rights to NB-7 "
          "in the United States")),                                                                            # RG4
    # RET-PLACE: a retention that names places without the buyer territory
    ("CN", C + "; Origin Bio retains rights to NB-7 outside the United States"),                             # RT1
    ("CN", C + "; Origin Bio retains rights to NB-7 in Japan and Europe"),                                   # RT2
    ("CN", C + "; Origin Bio retains rights to NB-7 in mainland China"),                                     # RT7
    ("TERM", ("Alpha Bio terminated the U.S. license with Origin Bio; Origin Bio retains rights to NB-7 outside the "
             "United States")),                                                                                # RX3
    # partial, future and unplaced retentions
    ("CN", C + "; Origin Bio retains U.S. commercialization rights"),                                        # RT4
    ("CN", C + "; Origin Bio retains U.S. development rights"),                                              # RT5
    ("CN", C + "; Origin Bio will retain all rights in the U.S."),                                           # RT12
    ("CN", C + "; Origin Bio will keep all rights in the U.S."),
    ("CN", "Origin Bio retains all rights to NB-7"),                                                         # RX1
    # HEADLINE3: a headline is not a dateline city
    ("CN", "TESSALY BUYS ORIGIN, U.S., March 3, 2025 -- " + C),                                             # DL1
    ("CN", "TESSALY BUYS NB, Mass., March 3, 2025 -- " + C),                                                # DL2
    ("CN", "TESSALY TAKES OVER -- (BUSINESS WIRE) -- " + C),                                                # DL3
    # UNPLACED2: signing sentences that state a scope
    ("CN", ("Origin Bio and Chinaco Pharma entered into an exclusive license agreement to develop and commercialize "
           "NB-7")),                                                                                             # SG1
    ("CN", ("Origin Bio entered into an exclusive license agreement with Chinaco Pharma for the development and "
           "commercialization of NB-7")),                                                                        # SG2
    ("CN", ("Chinaco Pharma entered into an exclusive license agreement with Origin Bio for the development and "
           "commercialization of NB-7")),                                                                        # SG3
    ("OPT", "Origin Bio and Chinaco Pharma entered into an exclusive option and license agreement for NB-7"),  # SG4
    ("CN", ("Origin Bio and Chinaco Pharma announced an exclusive license agreement for NB-7 for $20 million upfront "
           "and up to $200 million in milestones")),                                                             # SG6
    # SUBSID: a subsidiary of the licensee
    ("CN", ("Origin Bio, a wholly owned subsidiary of Chinaco Pharma, licensed NB-7 to Chinaco Pharma for mainland "
           "China")),                                                                                            # SB1
    ("CN", C + "; Origin Bio, a subsidiary of Chinaco Pharma, retains all rights in the U.S."),             # SB2
    # PUNCT
    ("CN", C + "?"),                                                                                         # PU1
]


@pytest.mark.parametrize(("row", "quote"), ATTACKS)
def test_every_rereview12_attack_blocks(row, quote):
    assert read(row, quote) is not None


def test_ret_place_names_the_missing_buyer_territory():
    why = read("CN", C + "; Origin Bio retains rights to NB-7 outside the United States") or ""
    assert "does not include US" in why


def test_ret_grantor_says_another_party_keeps_rights():
    why = read(SUB, "Chinaco Pharma retains all rights to NB-7 in the United States") or ""
    assert "other than the program's company" in why


def test_punct_quotes_the_question():
    assert "asks a question" in (read("CN", C + "?") or "")


# -- end to end through the production per-program path ---------------------------------------------------------------
def test_end_to_end_a_sublicensing_licensee_retaining_us_rights_is_not_top_tier():
    lic = ev(L, grantee="Chinaco Pharma", territory="mainland China", d="2025-01-01", deal="D1")
    sub = _quoted(ev(L, grantor="Chinaco Pharma", grantee="Sideco Bio", territory="mainland China", d="2025-02-01",
                     deal="D2"),
                  "Chinaco Pharma licensed NB-7 to Sideco Bio for mainland China; Chinaco Pharma retains all rights "
                  "to NB-7 in the United States")
    _not_top(_named_run([lic, sub]))


def test_end_to_end_a_termination_retaining_rights_outside_the_us_is_not_top_tier():
    lic = ev(L, grantee="Alpha Bio", territory="United States", d="2024-03-01", deal="D1")
    end = _quoted(ev(T, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D1", deal="D9"),
                  "Alpha Bio terminated the U.S. license with Origin Bio; Origin Bio retains rights to NB-7 outside "
                  "the United States")
    _not_top(_named_run([lic, end]))


# -- ACQ-TWO2 ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("first", "second"), [("Origin Bio", "The Origin Bio"), ("The Origin Bio", "Origin Bio")])
def test_acq_two2_two_acquirers_are_rivals_however_the_company_is_written(first, second):
    v = run([ev(L, **CHINA),
             ev(AQ, grantee="Omega Holdings", grantor=first, territory="Worldwide", d="2025-02-01"),
             ev(AQ, grantee="Sideco Bio", grantor=second, territory="Worldwide", d="2025-03-01")])
    _not_top(v)
    assert blocked(v, "who owns it is not established")


def test_owner_the_still_moves_the_owner_with_one_acquirer():
    v = run([ev(L, **CHINA, grantor="The Origin Bio"),
             ev(AQ, grantee="Omega Holdings", grantor="The Origin Bio", territory="Worldwide", d="2025-02-01")])
    assert v.position == rp.P_OWNER_ACQUIRED
    assert v.owner == "Omega Holdings"


# -- ROW12-REASON ---------------------------------------------------------------------------------------------------------
def test_worldwide_rights_excluding_a_region_is_one_place():
    _, regions = mark_places("shares worldwide rights, excluding Greater China and South Korea, equally with Beta")
    assert regions == [frozenset({"US", "CA", "EU", "UK", "JP", "ROW"})]


# -- clean cases: what revision 14 keeps passing ------------------------------------------------------------------------
CLEAN = [
    ("CN", "Origin Bio retains all rights to NB-7 outside mainland China"),                                  # UC6
    ("CN", C + "; Origin Bio retains rights in the rest of the world"),                                      # UC36
    ("CN", C + "; Origin Bio retains all rights in the U.S."),
    ("CN", C + "; Origin Bio retains all other rights"),
    ("CN", C + "; Origin Bio retains development and commercialization rights in the U.S."),
    ("CN", "Chinaco Pharma will pay Origin Bio an upfront payment of $20 million"),                          # UC33
    ("CN", "Origin Bio is eligible to receive up to $200 million in milestones"),                            # UC34
    ("CN", ("Origin Bio will receive $20 million upfront and up to $180 million in development and commercial "
           "milestones, plus tiered royalties")),
    ("CN", "HANGZHOU, Zhejiang Province, China, March 3, 2025 /PRNewswire/ -- " + C),                       # UC35
    ("CN", "SOUTH SAN FRANCISCO, Calif., March 3, 2025 /PRNewswire/ -- " + C),
    ("CN", "BOSTON, March 3, 2025 /PRNewswire/ -- " + C),
    ("CN", "Origin Bio and Chinaco Pharma entered into an exclusive license agreement for NB-7 in mainland China"),
    ("CN", "Sideco Bio, a wholly owned subsidiary of Origin Bio, licensed NB-7 to Chinaco Pharma for mainland China"),
]


@pytest.mark.parametrize(("row", "quote"), CLEAN)
def test_clean_restatements_pass(row, quote):
    e = dict(ROWS[row])
    if quote.startswith("Sideco Bio, a wholly"):
        e["grantor"] = "Sideco Bio"
    assert quote_problem(quote, e, "Origin Bio", AS_OF, US, names=["NB-7"], vocabulary=DESCRIPTION) is None


def test_a_clean_china_license_with_a_retention_stays_top_tier():
    v = run([_quoted(ev(L, **CHINA), "ChinaCo licenses China rights; Origin Bio retains all rights outside China")])
    assert v.tier == TIER1, v.top_tier_blockers


# -- CONFIRM-API, WITHDRAW-STALE --------------------------------------------------------------------------------------
@pytest.mark.parametrize("value", ["1", ""])
def test_confirm_api_record_refuses_in_an_agent_shell(monkeypatch, tmp_path, value):
    monkeypatch.setenv("CLAUDECODE", value)
    _, end = _ending()
    log = DecisionLog(tmp_path / "decisions.jsonl")
    with pytest.raises(DecisionRejected, match="run by an AI agent"):
        log.record(action=Action.CONFIRM_RIGHTS_ROW, subject_id=end.event_id, new_state="CONFIRMED",
                   reviewer_id="jdoe", reviewer_kind=ReviewerKind.HUMAN, rationale="r", context=_context(end))
    assert not log.records


def test_confirm_api_an_empty_variable_is_an_agent_shell():
    assert agent_shell({"CLAUDECODE": ""}) == "CLAUDECODE"


def test_withdraw_stale_a_withdrawal_after_a_change_removes_the_earlier_confirmation(tmp_path):
    events, end = _ending()
    log = DecisionLog(tmp_path / "decisions.jsonl")
    log.record(action=Action.CONFIRM_RIGHTS_ROW, subject_id=end.event_id, new_state="CONFIRMED", reviewer_id="jdoe",
               reviewer_kind=ReviewerKind.HUMAN, rationale="read the release", context=_context(end))
    changed = end.model_copy(update={"event_id": "rx:cccc2222:7",
                                     "evidence_quote": end.evidence_quote + "; Tessaly Pharma holds U.S. rights"})
    rec = log.record(action=Action.CONFIRM_RIGHTS_ROW, subject_id=changed.event_id, new_state="WITHDRAWN",
                     reviewer_id="jdoe", reviewer_kind=ReviewerKind.HUMAN, rationale="the row changed",
                     context=_context(changed))
    assert rec["old_state"] == "CONFIRMED_EARLIER_VERSION"
    confirmed = DecisionLog(tmp_path / "decisions.jsonl").state.review_inputs([]).confirmed_rights_rows
    assert not confirmed
    # the vendor reverts the row: the withdrawn confirmation does not come back
    _not_top(_named_run(events, confirmed=confirmed))


def test_withdraw_stale_a_withdrawal_with_nothing_to_withdraw_is_refused(tmp_path):
    _, end = _ending()
    log = DecisionLog(tmp_path / "decisions.jsonl")
    with pytest.raises(DecisionRejected, match="nothing to withdraw"):
        log.record(action=Action.CONFIRM_RIGHTS_ROW, subject_id=end.event_id, new_state="WITHDRAWN",
                   reviewer_id="jdoe", reviewer_kind=ReviewerKind.HUMAN, rationale="r", context=_context(end))
