# Response to the R1 adversarial re-review 9 (REREVIEW9.md): revision 11

Revision 11 is R1 on top of revision 10 (d905ff0) and U1 revision 5 (b0388eb), on `dealscreen-mvp`, as of
2026-11-02. Nobody has reviewed it yet. This file is the implementer's account, not a review: every claim below
should be checked by running code. The reviewer and the implementer are both AI. Neither is a human approval, and
nothing here is validation. AC14 is not claimed.

## 1. The highest-value fix: every word is read, and every row is read

REREVIEW9 §8 asked for two things: pass a clause only if every word is on a short allow-list for its row type, and
read every row the program has, not only the cited ones. Revision 11 does both.

**Every word (`rights_vocab`, `rights_quote`).** Revision 10 checked capitalised names and words in signal classes;
any other lower-case word passed. Revision 11 reads every token. A clause of a rights row's quote passes only if each
word is one of these:
- a grammar word, a press verb, an amount, a date or an ordinal (`FUNCTION_WORDS`);
- a generic drug-development word (`GENERAL_WORDS`: "antibody", "trial", "patients", "designation");
- a word that restates the row's own type (`ROW_WORDS`):
  - a license may say "licenses", "royalties", "transferred" and "collaboration";
  - a termination or return may say "terminated", "returned", "revert" and "end", but not "licensed" or
    "licensee";
  - a lapse may say "did not exercise" and "declined to take up";
  - an acquisition may say "acquires", "shares", "per share" and "tender";
- a word from the program's own landscape record (its name, aliases, target, mechanism, modality, therapeutic area
  and indication), which screening passes in. So no disease or target name is written in the code. Agent proposals
  are not used.

The words that point at another holder, place or time are in no list: "another", "other", "any", "every",
"further", "additional", "new", "third", "party", "company", "licensee", "partner", "not". `NEVER` keeps them out of
the program's own words too. A word missing from the lists blocks the clause, with the word quoted.

**Names.** A capitalised run is placed only as:
- a row party or the program's company, with corporate words after it ("Chinaco Pharma Co., Ltd.") but never a place
  word (MASK: "Chinaco Pharma U.S.", "USA", "America" and "International" are no longer absorbed);
- the program itself, or a lone program code ("NB-7");
- a place;
- an agency, exchange, meeting or currency code written in capitals.

A capitalised corporate word ("Pharma", "Bio", "Therapeutics", "Inc") always makes its run a name, so "Grant
Therapeutics" is not read as two allowed words. One known root with two different business words in a quote ("Chinaco
Pharma" and "Chinaco Bio") blocks: they may be two companies (PC5).

Revision 10's placement rules by shape or neighbour are removed (PLACE): `_SAID`, `_TITLE`, `_ADVISER`, `_SOURCE`,
`_DEFINED`, the digit rule, the known-words subset rule and "star" as a non-holder. In their place, three kinds of
text are removed before reading, and only when anchored:
- a dateline at the start of the quote ("SAN DIEGO, March 3, 2025 /PRNewswire/ --");
- a speaker attribution whose title is "of <known party>" ("said Jane Doe, Chief Executive Officer of Nerida
  Bio");
- an adviser of a known party ("Harlow Partners LLC advised Nerida Bio") and a byline at the end of a clause
  ("Wirecast has learned").

"<known party>, a subsidiary of <Name>" is still read as describing the known party (judgement, P20; REREVIEW9 §7.9
lists it as a judgement call).

**Dates.** Every date in a clause (day, month or year) is compared with the as-of date; a later one blocks (HEDGE3
H1). Notice words ("notice", "effective", "provided notice") are allowed on an ending only when every date in the
clause is on or before the as-of date (usefulness UT1).

**Every row (UNCITED).** A clear position now cites every applied rights row of the program
(`rights_position.rights_position`: `used += ledger.events`), so the gate reads every quote, including a grant over
other territories beside an availability statement, a return or a lapse.

## 2. Each finding

| Id | Revision 11 | Tests (`test_rights_rereview9.py`) |
|---|---|---|
| LOWER (High) | Every word is read; endings and acquisitions may not use grant words; "another", "third", "party", "company", "newco" are in no list | P1–P4, P16, P18; Q1, Q2, Q4; PC8–PC10 |
| PLACE (High) | Placement by shape or neighbour removed; speaker, adviser and byline text removed only when anchored to a known party | P5–P9b, P11–P15, P17, P23; PC5–PC7 |
| MASK (High) | Place words are never corporate words after a known name | PC1–PC4 |
| WIDER3 (High) | "any", "every", "further", "additional", "matching", "states", "globe", "includes" are in no list; "worldwide pivotal trials" is no longer stripped | W1–W6, W12, W17, PC12 |
| HEDGE3 (High) | Every date is compared with the as-of date; "to return", "elected", "decided", "returning", "starting", "wind-down", "due", "year-end", "decision" are in no ending list | H1–H6, H9–H12 |
| FUT3 (High) | A future-dated option exercise is announced like a grant: not applied, and it blocks | E2, E3 |
| UNCITED (High) | Every applied row is cited beside a clear position | AV1, AV3, AV4, RT1, RT2; control: a clean China license beside a return stays tier 1 |
| PN4 (High, low realism) | A party name of more than one word needs a company or legal word (or "&") | 3 names; control |
| OWNER-KEY (Medium) | An acquisition counts for the owner only when the acquired party is a grant party, the acquirer of one, or the company itself, with only legal forms removed (`rights_ledger._one_entity`). "Nerida Bio US", "Nerida Holdings" and "Nerida Bio International" are other entities; the company buying someone else (F6) is not "owner acquired" | F6, three affiliates; control: "Origin Bio, Inc." |
| LBL-NONE2 (Low) | When rights rows exist but none gives a position, the position is `RIGHTS_ROWS_NOT_APPLIED` on every path, not `NO_RIGHTS_EVIDENCE` | one test; five older tests updated |
| Q-FUT3 (Low) | Follows FUT3: with the exercise announced, the question says "Recorded deals in force on the as-of date" | d10 E2 |
| L1f (Low) | Follows UNCITED: ATG-022's China row is now read, so the memo no longer says the word rules found nothing | ws_j memo |
| L3f (Low) | Follows PN4 | — |
| SHARE (usefulness defect) | The co-development pattern is "shared", "sharing", "co-sharing" and "-sharing"; "share" and "shares" are acquisition words | 2 tests (UA1, UA2) |

## 3. Measured result

| Check | Result |
|---|---|
| Tests | `tests/dealscreen`: 1,436 pass (1,327 at revision 10 with U1 revision 5; `test_rights_rereview9.py` 85 cases). `ruff` and `mypy` clean |
| CLDN18.2 science | 0 of 62 scientific fields changed against the frozen baseline |
| CLDN18.2 transaction | 2 of 62 programs changed, both by OWNER-KEY: Zolbetuximab and IMAB362 go from `OWNER_ACQUIRED_PER_EVIDENCE` to `RIGHTS_ROWS_NOT_APPLIED`. Their row says Astellas (the landscape company) acquired Ganymed, and Ganymed is in no recorded grant, so the row no longer shows who held this program. The question is now "What rights to this program did Ganymed hold when Astellas acquired it?". Neither tier changes (EXCLUDED_BY_BUYER_PREFERENCE and DEPRIORITIZED). This is a usefulness cost of the F6 fix: it cannot tell "the company bought the program's originator" from "the company bought someone else" without a grant row |
| Cross-version | 0 of 312 programs' science records differ from revision 10 |
| Cycle-4 equivalence | byte-identical, 4 of 4 |
| Reviewer's end-to-end workspaces (re-screened) | ws_h 0, ws_i 0, ws_j 0 top-tier placements (revision 10: 1, 0, 7) |
| Reviewer's attack probes (`rr10/a`, run unchanged) | p10 0 of 75 top-tier (revision 10: 60); p10b 0 of 5 (3); d10 0 of 30 (16) |
| The same probes with the harness's placeholder quote removed | p10 4 of 75: P20 (judgement), H7 and H8 (partial-scope judgement calls) and the Q5 control. d10 7 of 30: E9, E12, N4, F2, F4, F8 and F10, none of which REREVIEW9 lists as a defect. Every finding in §2 blocks |

**The placeholder.** The reviewer's harness gives every row without its own quote the quote "(test) record N".
Revision 11 reads every row beside a clear position, and "test" and "record" are in no list, so these rows block.
The unchanged-probe numbers above overstate safety for that reason, and the usefulness numbers below understate it.
Both are reported.

### Usefulness

| Measure | Revision 10 | Revision 11 |
|---|---|---|
| Reviewer's 43 clean cases (`u10`), harness unchanged | 14 | 5 |
| The same, placeholder removed | 14 | 11 |
| Real CLDN18.2 quotes, through the gate, each row alone (4 rows give a clear position alone) | 1 of 17 blocks (REREVIEW9: misleading) | 3 of 17 block; all 3 are among the 4 clear-alone rows |
| Real CLDN18.2 quotes read directly by the quote reader, whatever position the row gives | 5 of 17 would block (reviewer's count) | 13 of 17 block |

REREVIEW9 was right that "1 of 17" was misleading. It counted only the rows that reach a clear position on their
own, and most real rows are licenses, which never reach the reader. Read directly, 13 of the 17 real quotes block at
revision 11:
- 2 on news style ("meanwhile", "according to an ApexOnco report");
- 1 on "worldwide" (a co-promotion option over more than the row's territory, which is correct);
- 1 on "co-promote" on an option row;
- the rest on ordinary deal words not in the lists ("through", "region", "biotechnology", a capitalised "Company",
  a typo "i").

Two generic changes were made after reading these rows, and are disclosed as such:
- program words keep dotted numbers ("Claudin18.2");
- "collaboration" is a license word.

No other word was added for them.

Of the 43 clean cases, revision 11 passes:
- datelines (UC1, UC2, UT4), a defined "Greater China", an exchange ticker and "the PRC" (UC8, UC9, UC25);
- a notice effective before the as-of date (UT1), FDA wording (UT5) and termination for convenience (UT7);
- per-share and tender-offer acquisitions (UA1, UA2).

It no longer passes:
- UC4: "We" is an unplaced name;
- UC7: "plus";
- UC16: "file";
- UC19: an INN in brackets;
- UC24: "double-digit";
- UC27: "run";
- UT3: "prioritization";
- UT6: "neither";
- UA5, UA6: advisers named without a legal form.

Disease names (UC12, UC13) block in the probe because the harness passes no program record. In screening, the
program's own indication words are read.

Usefulness against general Claude is not re-measured; at revision 10 it was 10/4/1 against 14/1/0 on 15 deal
programs, so no advantage is shown.

## 4. Costs and open issues

1. **Most real quotes block when read directly (13 of 17).** The top tier is rarer for clean cases. Every block
   names its word and asks a question; nothing is dropped. A clear position is now held back by any unusual word in
   any of the program's rights rows, and real press wording carries many.
2. **OWNER-KEY's cost on real rows.** "The company acquired the originator" with no grant row is not applied
   (Zolbetuximab, IMAB362).
3. **Judgement calls kept**: "a subsidiary of <Name>" directly after a known party (P20), partial-scope returns (H7,
   H8).
4. **Names made only of allowed words** ("Novel Grant", with no corporate word) are read as words. A name with any
   corporate word, or any word outside the lists, is a name and must be placed.
5. **The lists are DealScreen's own.** A wrong entry would let a word through; a missing entry only blocks.
6. **Recall is still capped by the rights file** (LM-302's and SKB315's returns are not in the frozen library), and
   no real vendor deals export has been tested.
7. AC14 stays open until a fresh adversarial review of revision 11.
