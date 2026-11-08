"""Cycle R1 revision 13: the inputs from adversarial re-review 11 (research/dealscreen_rights_v1/REREVIEW11.md).

Revision 13 makes the fixed sentences of ``rights_template`` the only reader of a rights row's quote. The plain-form
reader no longer reads quotes, so "it", "we" and "the company" are never the program's company (PF-PRONOUN,
SUFFIX2); the one sentence that keeps rights with a party is "<grantor> retains rights ...". Every character is read:
typographic punctuation is written in ASCII and any other non-ASCII text blocks (NONLATIN). A dateline needs a city on
the first line and region parts that are places, and a stripped adviser, byline or speaker name holds no rights,
template or place word (HEADLINE2, STRIP-CAPS). A grant, an option or an exercise must name a place unless the row
covers the buyer territory, and "an option to acquire NB-7" is no option template (UNPLACED, ACQ-OPT). Field words
that carry a condition or a holder never describe the program (VOCAB2). Only a license ends a license (DEAL-KIND).
An acquisition of "The Origin Bio" moves the owner (OWNER-THE). A rights row confirmation states its reviewer kind,
is refused in an AI agent's shell, is keyed by the row's content and shows the kind (CONFIRM-KIND, CONFIRM-REIMPORT);
the memo question carries no action code or event id (MEMO-CODE).

Defaults as in ``test_rights_rereview10``. Parties are fictional; the tests assert no real-world facts."""

from __future__ import annotations

from datetime import date

import pytest
from test_rights_rereview3 import AQ, CHINA, OL, OX, TIER1, TOP, L, O, T, blocked, ev, run
from test_rights_rereview10 import AS_OF, DESCRIPTION, US, _named_run, _not_top, _quoted

from bve.cli import dealscreen as cli
from bve.dealscreen import rights_position as rp
from bve.dealscreen.review import (
    Action,
    DecisionContext,
    DecisionLog,
    DecisionRejected,
    ReviewerKind,
    agent_shell,
)
from bve.dealscreen.rights import RIGHTS_RETURNED
from bve.dealscreen.rights_model import cite_event, row_key, row_sha256
from bve.dealscreen.rights_quote import quote_problem
from bve.dealscreen.rights_template import descriptor_words

ROWS = {
    "CN": {"type": "LICENSE", "grantor": "Origin Bio", "grantee": "Chinaco Pharma", "territory": "mainland China",
           "date": "2025-01-01"},
    "TERM": {"type": "TERMINATION", "grantor": "Origin Bio", "grantee": "Alpha Bio", "territory": "United States",
             "date": "2025-01-15"},
    "RET": {"type": "RIGHTS_RETURNED", "grantor": "Origin Bio", "grantee": "Alpha Bio", "territory": "United States",
            "date": "2025-01-15"},
    "LAPSE": {"type": "OPTION_LAPSED", "grantor": "Origin Bio", "grantee": "Alpha Bio", "territory": "United States",
              "date": "2025-01-15"},
    "OPT": {"type": "OPTION", "grantor": "Origin Bio", "grantee": "Chinaco Pharma", "territory": "mainland China",
            "date": "2025-01-01"},
    "EXER": {"type": "OPTION_EXERCISED", "grantor": "Origin Bio", "grantee": "Chinaco Pharma",
             "territory": "mainland China", "date": "2025-02-01"},
    "GC": {"type": "LICENSE", "grantor": "Origin Bio", "grantee": "Chinaco Pharma", "territory": "Greater China",
           "date": "2025-01-01"},
}
C = "Chinaco Pharma licenses NB-7 for mainland China"


def read(row: str, quote: str, vocabulary: frozenset[str] = DESCRIPTION) -> str | None:
    return quote_problem(quote, ROWS[row], "Origin Bio", AS_OF, US, names=["NB-7"], vocabulary=vocabulary)


# -- §2a-2g: every REREVIEW11 attack blocks -------------------------------------------------------------------------
ATTACKS = [
    # PF-PRONOUN: a pronoun or "the company" is never the program's company
    ("CN", C + "; it holds all rights in the U.S."),                                                          # PF1
    ("CN", ("Chinaco Pharma obtained rights to NB-7 in mainland China from Origin Bio; it holds the rights in "
            "the US")),                                                                                       # PF2
    ("CN", C + "; we own all rights in the United States"),                                                   # PF3
    ("TERM", "Alpha Bio terminated the U.S. license with Origin Bio; it retains all rights"),                 # PF4
    ("TERM", "Alpha Bio terminated the U.S. license with Origin Bio; the company retains all rights in the U.S."),
    ("CN", C + "; the company holds all rights in the U.S."),                                                 # PF6
    ("TERM", "Alpha Bio terminated the U.S. license with Origin Bio; rights retained by it"),                 # PF10
    ("CN", C + "; it keeps all rights in the US and rest of world"),                                          # PF13
    ("CN", C + "; owned by it"),                                                                              # PF15
    ("LAPSE", "Alpha Bio let its option to NB-7 lapse; it retains all rights"),                               # LP9
    ("LAPSE", "the option on the U.S. rights to NB-7 lapsed; the company holds the rights in the US"),        # LP10
    ("CN", C + "; US rights: undisclosed"),                                                                   # PF9
    ("CN", C + "; US rights: TBD"),                                                                           # PF14
    # SUFFIX2: another entity named like the company
    ("CN", C + "; Origin Bio Holdings retains all rights in the U.S."),                                       # PF7
    ("CN", C + "; Origin Bio International owns the rights in the US"),                                       # PF8
    ("CN", C + "; Origin Bio Global holds all rights in the U.S."),                                           # PF12
    # NONLATIN
    ("CN", C + "，美国权利由第三方持有"),                                                                       # NL1
    ("CN", C + "。美国权利已授予第三方。"),                                                                       # NL2
    ("CN", C + " ＴＥＳＳＡＬＹ ＨＯＬＤＳ ＵＳ ＲＩＧＨＴＳ"),                                                    # NL3
    ("CN", C + "; 美国权利由第三方持有"),                                                                       # NL4
    ("RET", "Alpha Bio returns U.S. rights to NB-7 to Origin Bio，但阿尔法保留美国商业化权利"),                    # NL5
    ("CN", C + "; Tessaly Pharma holds U.S. rights\x01"),                                                     # a marker
    # HEADLINE2 and STRIP-CAPS
    ("CN", "BOSTON, Tessaly Holds Rights, March 3, 2025 -- " + C),                                           # HD1
    ("CN", "BOSTON, Tessaly Pharma Holds, All U.S. Rights, March 3, 2025 -- " + C),                          # HD2
    ("CN", "TESSALY HOLDS RIGHTS\nBOSTON, March 3, 2025 -- " + C),                                           # HD3
    ("CN", "TESSALY HOLDS US RIGHTS, March 3, 2025 -- " + C),                                                # HD4
    ("CN", C + ". Tessaly Holds US Rights advised Origin Bio"),                                              # HD6
    ("CN", C + ", Tessaly Holds US Rights has learned"),                                                     # HD7
    ("CN", C + ", said Tessaly Holds-US-Rights, Chief Executive Officer of Origin Bio"),                     # HD8
    # ACQ-OPT and UNPLACED
    ("OPT", "Origin Bio granted Chinaco Pharma an option to acquire NB-7"),                                  # AO1
    ("OPT", "Chinaco Pharma obtained an exclusive option to acquire NB-7 from Origin Bio"),                  # AO2
    ("EXER", "Chinaco Pharma exercised its option to acquire NB-7"),                                         # AO3
    ("OPT", "Chinaco Pharma obtained an exclusive option to in-license NB-7 from Origin Bio"),               # UN7
    ("CN", "Chinaco Pharma acquired the rights to NB-7 from Origin Bio"),                                    # UN1
    ("CN", "Origin Bio granted Chinaco Pharma the exclusive rights to NB-7"),                                # UN2
    ("CN", "Chinaco Pharma obtained the sole rights to develop, manufacture and commercialize NB-7"),       # UN6
    ("CN", C + "; Origin Bio licensed NB-7 to Chinaco Pharma"),                                              # UN5
    ("CN", "rights to NB-7"),                                                                                # UN10
    # DEAL-KIND
    ("TERM", "Origin Bio terminated the option agreement with Alpha Bio"),                                   # X5
    ("TERM", "Origin Bio and Alpha Bio terminated their co-development agreement"),                          # X4
    ("TERM", "Origin Bio terminated the partnership agreement with Alpha Bio"),
]


@pytest.mark.parametrize(("row", "quote"), ATTACKS)
def test_every_rereview11_attack_blocks(row, quote):
    assert read(row, quote) is not None


# VOCAB2: a field may not add a condition or a holder word to the program's description
CONDITION_FIELDS = descriptor_words(["gastric cancer following two prior lines of therapy, after progression",
                                     "co-owned antibody", "jointly-owned antibody", "licensee product antibody",
                                     "Claudin 18.2"])


@pytest.mark.parametrize(("row", "quote"), [
    ("RET", "Alpha Bio returns U.S. rights to NB-7, after phase 3, to Origin Bio"),                          # QC1
    ("RET", "Origin Bio regains U.S. rights to NB-7, after phase 3"),                                        # QC3
    ("TERM", "Alpha Bio terminates the U.S. license for NB-7, after progression"),                           # QC4
    ("RET", "Alpha Bio returns U.S. rights to the after phase 3 NB-7 to Origin Bio"),                        # QC5
    ("CN", "Origin Bio licensed NB-7, a co-owned antibody, for mainland China to Chinaco Pharma"),           # Q5
    ("CN", "Origin Bio licensed NB-7, a jointly-owned antibody, for mainland China to Chinaco Pharma"),      # Q6
    ("CN", "Origin Bio licensed NB-7, the licensee product, for mainland China to Chinaco Pharma"),          # Q9
])
def test_vocab2_condition_and_holder_words_never_describe_the_program(row, quote):
    assert read(row, quote, CONDITION_FIELDS) is not None


def test_vocab2_the_filter_reads_hyphen_parts():
    words = descriptor_words(["co-owned antibody", "jointly-owned", "after progression", "anti-CLDN18.2"])
    assert not {"co-owned", "jointly-owned", "after", "owned", "jointly"} & words
    assert {"antibody", "anti-cldn18.2"} <= words


def test_nonlatin_block_quotes_the_unread_text():
    why = read("CN", C + "，美国权利由第三方持有") or ""
    assert "cannot read" in why and "美国权利" in why


# -- clean restatements still pass -----------------------------------------------------------------------------------
CLEAN = [
    ("CN", C),                                                                                               # PF0
    ("CN", "BOSTON, March 3, 2025 /PRNewswire/ -- " + C),                                                    # HD5
    ("CN", "CAMBRIDGE, Mass., March 3, 2025 -- " + C),
    ("CN", "SOUTH SAN FRANCISCO, Calif. and SHANGHAI, China, March 3, 2025 /PRNewswire/ -- " + C),
    ("CN", "Chinaco Pharma licenses NB-7 for mainland\u00a0China"),  # NBSP
    ("CN", "Chinaco Pharma licenses NB-7\u00ae for mainland China"),  # a registered mark
    ("CN", "Origin Bio retains all rights to NB-7 outside mainland China"),                                  # UC6
    ("CN", C + "; Origin Bio retains rights in the rest of the world"),
    ("CN", C + "; Origin Bio retains all rights in the U.S."),
    ("CN", "Origin Bio licensed NB-7 to Chinaco Pharma for \u201cmainland China\u201d"),  # curly quotes
    ("CN", ("Origin Bio licensed NB-7 to Chinaco Pharma for mainland China for $20 million upfront and up to $200 "
            "million in milestones")),                                                                       # UC19
    ("CN", ("Under the terms of the agreement, Chinaco Pharma will receive exclusive rights to develop and "
            "commercialize NB-7 in mainland China")),                                                        # UC2
    ("GC", ("Origin Bio and Chinaco Pharma today announced an exclusive license agreement for NB-7 in Greater "
            "China")),                                                                                       # UC1
    ("OPT", "Origin Bio granted Chinaco Pharma an option on NB-7 in mainland China"),                       # UN3c
    ("EXER", "Chinaco Pharma exercised its option to license NB-7 in mainland China"),
    ("LAPSE", "Alpha Bio did not exercise its option to acquire NB-7"),                                      # LP11
    ("TERM", "Alpha Bio terminated the U.S. license with Origin Bio"),
    ("TERM", "Alpha Bio terminated the agreement with Origin Bio"),
    ("CN", C + ", said Jane Doe, Chief Executive Officer of Origin Bio"),
    ("CN", "Jane Doe Partners advised Origin Bio"),
]


@pytest.mark.parametrize(("row", "quote"), CLEAN)
def test_clean_restatements_pass(row, quote):
    assert read(row, quote) is None


def test_a_global_partnership_is_not_a_place():
    why = read("CN", C + " in a global partnership") or ""
    assert "which the row's own territory" not in why


# -- end to end: the review's ws_m shapes ------------------------------------------------------------------------------
@pytest.mark.parametrize("quote", [
    C.replace("NB-7", "Prog") + "; it holds all rights in the U.S.",
    "BOSTON, Tessaly Holds Rights, March 3, 2026 -- " + C.replace("NB-7", "Prog"),
    "Chinaco Pharma obtained the sole rights to develop, manufacture and commercialize Prog from Origin Bio",
])
def test_end_to_end_the_ws_m_shapes_are_not_top_tier(quote):
    _not_top(run([_quoted(ev(L, **CHINA), quote.replace("Chinaco Pharma", "ChinaCo"))]))


def test_end_to_end_option_to_acquire_is_not_top_tier():
    events = [_quoted(ev(O, **CHINA), "Origin Bio granted ChinaCo an option to acquire Prog")]
    _not_top(run(events))


# -- OWNER-THE ---------------------------------------------------------------------------------------------------------
def test_owner_the_an_acquisition_of_the_company_written_with_the_moves_the_owner():
    v = run([ev(L, **CHINA, grantor="The Origin Bio"),
             ev(AQ, grantee="Omega Holdings", grantor="The Origin Bio", territory="Worldwide", d="2025-02-01")])
    assert v.position == rp.P_OWNER_ACQUIRED
    assert v.owner == "Omega Holdings"


# -- CONFIRM-KIND, CONFIRM-REIMPORT, MEMO-CODE ---------------------------------------------------------------------------
QUOTE = "Alpha Bio and Origin Bio said U.S. rights went back to Origin Bio last quarter"


def _ending(event_id: str = "rx:aaaa0000:7", row: int = 7):
    lic = ev(L, grantee="Alpha Bio", territory="United States", d="2024-03-01", deal="D1")
    end = _quoted(ev(RIGHTS_RETURNED, grantee="Alpha Bio", territory="United States", d="2025-01-15",
                     related="D1", deal="D9"), QUOTE).model_copy(update={"event_id": event_id, "row_number": row})
    return [lic, end], end


def _context(event) -> DecisionContext:
    c = cite_event(event)
    return DecisionContext(dispositions={}, claim_ids=set(), finding_ids=set(), flag_ids=set(),
                           rights_row_hashes={event.event_id: row_sha256(c)},
                           rights_row_keys={event.event_id: row_key(c)})


def test_confirm_kind_the_kind_must_be_stated(tmp_path):
    _, end = _ending()
    log = DecisionLog(tmp_path / "decisions.jsonl")
    with pytest.raises(DecisionRejected, match="states its reviewer kind explicitly"):
        log.record(action=Action.CONFIRM_RIGHTS_ROW, subject_id=end.event_id, new_state="CONFIRMED",
                   reviewer_id="jdoe", rationale="read the release", context=_context(end))


def test_confirm_kind_other_actions_still_default_to_human(tmp_path):
    log = DecisionLog(tmp_path / "decisions.jsonl")
    ctx = DecisionContext(dispositions={"A1": "ELIGIBLE"}, claim_ids=set(), finding_ids=set(), flag_ids=set())
    rec = log.record(action=Action.REQUEST_DILIGENCE, subject_id="A1", new_state="REQUESTED", reviewer_id="jdoe",
                     rationale="ask", detail={"question": "Q?"}, context=ctx)
    assert rec["reviewer_kind"] == "HUMAN"


@pytest.mark.parametrize("var", ["CLAUDECODE", "CODEX_SANDBOX", "DEALSCREEN_AI_AGENT"])
def test_confirm_kind_an_agent_shell_is_named(var):
    assert agent_shell({var: "1"}) == var
    assert agent_shell({}) is None


def test_confirm_kind_the_cli_refuses_in_an_agent_shell(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDECODE", "1")
    with pytest.raises(DecisionRejected, match="run by an AI agent"):
        cli._decide(None, action="CONFIRM_RIGHTS_ROW", subject="rx:x:1",  # type: ignore[arg-type]
                    new_state="CONFIRMED", reviewer="jdoe", rationale="r", kind=ReviewerKind.HUMAN)


class _FakeWorkspace:
    def __init__(self, log: DecisionLog, context: DecisionContext) -> None:
        self.log, self.context = log, context

    def assets(self) -> list:
        return []

    def decision_log(self) -> DecisionLog:
        return self.log

    def decision_context(self, normalizer=None) -> DecisionContext:
        return self.context


def test_confirm_kind_the_cli_needs_the_kind_stated(monkeypatch, tmp_path):
    for var in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CODEX_SANDBOX", "CODEX_SANDBOX_NETWORK_DISABLED",
                "CURSOR_AGENT", "AIDER_MODEL", "GEMINI_CLI", "DEALSCREEN_AI_AGENT"):
        monkeypatch.delenv(var, raising=False)
    _, end = _ending()
    ws = _FakeWorkspace(DecisionLog(tmp_path / "decisions.jsonl"), _context(end))
    with pytest.raises(DecisionRejected, match="states its reviewer kind explicitly"):
        cli._decide(ws, action="CONFIRM_RIGHTS_ROW", subject=end.event_id,  # type: ignore[arg-type]
                    new_state="CONFIRMED", reviewer="jdoe", rationale="r", kind=None)
    rec = cli._decide(ws, action="CONFIRM_RIGHTS_ROW", subject=end.event_id,  # type: ignore[arg-type]
                      new_state="CONFIRMED", reviewer="jdoe", rationale="r", kind=ReviewerKind.HUMAN)
    assert rec["reviewer_kind"] == "HUMAN"


def test_confirm_reimport_an_unchanged_row_keeps_its_confirmation(tmp_path):
    events, end = _ending()
    log = DecisionLog(tmp_path / "decisions.jsonl")
    log.record(action=Action.CONFIRM_RIGHTS_ROW, subject_id=end.event_id, new_state="CONFIRMED", reviewer_id="jdoe",
               reviewer_kind=ReviewerKind.HUMAN, rationale="read the release", context=_context(end))
    confirmed = DecisionLog(tmp_path / "decisions.jsonl").state.review_inputs([]).confirmed_rights_rows
    # the rights file changed elsewhere: a new file hash and row number, the same row
    moved = end.model_copy(update={"event_id": "rx:bbbb1111:9", "row_number": 9})
    v = _named_run([events[0], moved], confirmed=confirmed)
    assert v.tier == TIER1, v.top_tier_blockers
    reason = next(r for r in v.reasons if "confirmed as restating the row" in r)
    assert "by jdoe, recorded as a human analyst (DealScreen cannot verify this" in reason
    # a withdrawal through the new event id removes it
    log.record(action=Action.CONFIRM_RIGHTS_ROW, subject_id=moved.event_id, new_state="WITHDRAWN",
               reviewer_id="jdoe", reviewer_kind=ReviewerKind.HUMAN, rationale="source corrected",
               context=_context(moved))
    assert not DecisionLog(tmp_path / "decisions.jsonl").state.review_inputs([]).confirmed_rights_rows


def test_confirm_reimport_a_changed_row_is_read_and_names_the_earlier_confirmation(tmp_path):
    events, end = _ending()
    log = DecisionLog(tmp_path / "decisions.jsonl")
    log.record(action=Action.CONFIRM_RIGHTS_ROW, subject_id=end.event_id, new_state="CONFIRMED", reviewer_id="jdoe",
               reviewer_kind=ReviewerKind.HUMAN, rationale="read the release", context=_context(end))
    confirmed = DecisionLog(tmp_path / "decisions.jsonl").state.review_inputs([]).confirmed_rights_rows
    changed = end.model_copy(update={"event_id": "rx:cccc2222:7",
                                     "evidence_quote": QUOTE + "; Tessaly Pharma holds U.S. rights"})
    v = _named_run([events[0], changed], confirmed=confirmed)
    _not_top(v)
    assert blocked(v, "a confirmation was recorded for an earlier version of this row")


def test_confirm_reimport_no_leak_to_another_program(tmp_path):
    events, end = _ending()
    log = DecisionLog(tmp_path / "decisions.jsonl")
    log.record(action=Action.CONFIRM_RIGHTS_ROW, subject_id=end.event_id, new_state="CONFIRMED", reviewer_id="jdoe",
               reviewer_kind=ReviewerKind.HUMAN, rationale="read the release", context=_context(end))
    confirmed = DecisionLog(tmp_path / "decisions.jsonl").state.review_inputs([]).confirmed_rights_rows
    other = end.model_copy(update={"external_id": "P2", "event_id": "rx:dddd:8"})
    assert row_sha256(cite_event(other)) not in confirmed
    _not_top(_named_run([events[0], other], confirmed=confirmed))


def test_memo_code_the_question_has_no_action_code_or_event_id():
    events, end = _ending()
    v = _named_run(events)
    text = " ".join(v.questions)
    assert "CONFIRM_RIGHTS_ROW" not in text and end.event_id not in text
    assert any("can confirm the row in DealScreen" in q for q in v.questions)


# -- unchanged controls ------------------------------------------------------------------------------------------------
def test_a_clean_china_license_stays_top_tier():
    v = run([_quoted(ev(L, **CHINA), "ChinaCo licenses Prog for mainland China")])
    assert v.tier in TOP, v.top_tier_blockers


def test_a_clean_lapse_and_exercise_rows_still_read():
    lapse = run([_quoted(ev(O, grantee="Alpha Bio", territory="United States", d="2024-03-01", deal="D2"),
                         "Origin Bio granted Alpha Bio an option on Prog in the U.S."),
                 _quoted(ev(OL, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D2"),
                         "Alpha Bio did not exercise its option to acquire Prog")])
    assert lapse.tier in TOP, lapse.top_tier_blockers
    exercise = run([_quoted(ev(O, **CHINA, deal="D3"), "Origin Bio granted ChinaCo an option on Prog in mainland China"),
                    _quoted(ev(OX, **{**CHINA, "d": "2025-02-01"}, related="D3"),
                            "ChinaCo exercised its option to license Prog in mainland China")])
    assert exercise.tier in TOP, exercise.top_tier_blockers


def test_terminations_still_end_licenses():
    v = run([ev(L, grantee="Alpha Bio", territory="United States", d="2024-03-01", deal="D1"),
             _quoted(ev(T, grantee="Alpha Bio", territory="United States", d="2025-01-15", related="D1"),
                     "Alpha Bio terminated the U.S. license with Origin Bio")])
    assert v.tier in TOP, v.top_tier_blockers
    assert date(2025, 1, 15) <= AS_OF
