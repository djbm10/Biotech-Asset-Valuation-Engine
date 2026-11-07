# Response to the R1 adversarial re-review 10 (REREVIEW10.md): revision 12

Revision 12 is R1 on top of revision 11 (7a62efd), on `dealscreen-mvp`, as of 2026-11-02. Nobody has reviewed it
yet. This file is the implementer's account, not a review: every claim below should be checked by running code. The
reviewer and the implementer are both AI. Neither is a human approval, and nothing here is validation. AC14 is not
claimed.

## 1. The highest-value fix: fixed sentence templates, or a human confirmation

REREVIEW10 §8: "Stop letting a word list decide that a quote restates its row … a quote should pass only if each
clause matches one of a few fixed templates for its row type, read as a whole clause … and the analyst clears it
with one recorded confirmation of the row." Revision 12 does this. `rights_vocab` (the word lists) is deleted.

**Templates (`rights_template`).** Beside a clear position, each clause of every applied rights row's quote is
turned into slots and must match one of a few sentences for the row's type:
- the row's parties, in their own roles: grantor (G), grantee (E). A party is masked only as the same legal
  entity: legal words ("Co., Ltd.", "Inc") and business words ("Pharma", "Bio") may follow it; "Holdings", "Group",
  "International", "Development", "Research" and place words never do (SUFFIX);
- the program (P), by one of its own names or ids. An initials acronym counts only after the quote defines it in
  parentheses, and the program is masked first, so "NB" inside "NB-7" is never a party (CODE2). A description of
  the program ("P, an anti-CLDN18.2 ADC for gastric cancer", "the Claudin18.2 antibody P", "P for gastric cancer")
  folds into P only when every word is a drug-development word or a lower-case or symbol word from the program's
  own target, mechanism, modality, therapeutic area and indication fields. A capitalised word is never a
  description word, and a field cannot add a connective, a place or a rights word ("from", "outside", "rights")
  (VOCAB);
- a verb for that type only. Grants: past or present. Endings and returns (TERMINATION and RIGHTS_RETURNED share
  one set): "terminated", "returned", "reverted", "regained", present or past. Lapses: "lapsed (unexercised)",
  "declined to exercise", "did not exercise", "let … lapse". Acquisitions: completed only ("acquired", "completed
  its acquisition of", "completed its tender offer for"). No modal ("may", "will", "could"), no "has" as a holding
  verb (only as an auxiliary), no "not" outside the lapse sentences, no sale or transfer, no condition ("after",
  "following", "upon", "subject to", "pending") (LOWER2, WIDER4, HEDGE4, MAY, LAPSE-NEG, SALE, ACQ-PENDING,
  MINORITY);
- an optional place, read with `parse_territory`, that must lie inside the row's own territory; "all" rights only
  when the row covers the buyer territory (WIDER4);
- an optional date. A date needs a year; months are matched only when capitalised, so "may" is never a month;
  ordinals ("January 10th, 2025") are read. A date passes if its period ends on or before the as-of date, or if
  the period holds the row's own date and that date is on or before the as-of date ("in 2025" for a row dated
  2025-01-15, as-of 2025-06-01) (MAY, UNDATED; usefulness E22, E23). There is no notice sentence: a notice blocks
  (NOTICE);
- an optional amount, and the press frames "X announced that …", "Under the agreement, …".

Before reading, only these are removed: a dateline (a city in capitals, at most two place parts, a full date, a
known wire, a dash; or the "CITY--(BUSINESS WIRE)--" form) (HEADLINE); an exchange note made only of
"(EXCHANGE: TICKER)" (NOTE); a speaker attribution whose title is "of <known party>"; an adviser clause of a known
party; a closing "<Name> has learned". A headline in title case or all capitals is read with template words
lower-cased; any other capitalised word stays a name.

Anything else blocks, quoting the clause: "has the clause '…', which is not one of the sentences DealScreen reads as
restating the row", or "names X, which is not a party to the row …".

**Confirmation (`review`, `rights_gate`).** The block's question names the row's event id. A human analyst who has
read the source can record `CONFIRM_RIGHTS_ROW` (state `CONFIRMED`, or `WITHDRAWN` to take it back) with `decide`.
The decision log refuses it from an AI-prepared or synthetic reviewer, for an event the workspace does not hold, or
without the workspace context. The record stores `row_sha256`, a hash of the row's type, parties, territory, dates,
status, exclusivity, source and quote. At screening, a confirmed row whose hash still matches is not read again, and
its reason says who confirmed it and in which decision ("confirmed as restating the row by jdoe (dec:00003, …); it
is not read again"). If the row has changed since, the confirmation does not apply and the block says "a
confirmation was recorded for an earlier version of this row". No AI can clear a block.

**Ledger.** OWNER-KEY2: an acquisition counts for the owner only when the acquired party is `_one_entity` with a
party to a recorded grant or with the company ("Origin Bio Holdings" and "Origin Bio Group" are other entities).
ACQ-TWO: two different acquirers of one party make both rows contested: neither is applied, an "uncontested:"
blocker cites both, and a question asks which is right. One acquirer written two ways ("Omega Holdings",
"Omega Holdings, Inc.") is one acquirer.

**Labels.** LBL-OWNER: a holder named only by the landscape (an FDA labeler) is shown as "U.S. rights holder or
labeler named by the landscape … (not shown by a rights row to hold or own the program; verify)", not "per
evidence". LBL-DATE: the unapplied position reads "rights rows recorded, none gives a position on the as-of date";
its reason says each row's own reason gives why (dated after it, not linked to a recorded deal, or naming another
party).

## 2. Each finding

| Id | Revision 12 | Tests (`test_rights_rereview10.py`, 156 cases) |
|---|---|---|
| LOWER2 (High) | No holding "has", no pronoun subject other than "it/they" after "announced that"; a clause must be a template | E1, E2, E7, E8, E9, LP3, L3, L5 |
| WIDER4 (High) | "all"/"full" rights only when the row covers the buyer territory; every place inside the row's territory | L1, L2, L13, plus 3 place variants |
| HEDGE4 (High) | No condition words in any template | E3, E4, E5 |
| MAY (High) | Months capitalised only; no modal in any template | E10, E11, LP4, LP5, A7 |
| UNDATED (High) | A date needs a year; "December 1", "Q4", "H2", "Friday", "December '26" match nothing | E12–E15, E20 |
| NOTICE (High) | No notice sentence | E16, E17 |
| LAPSE-NEG (High) | "not" only in the lapse sentences that mean no exercise | LP1, LP2, LP6 |
| SALE (High) | No sale or transfer verb | L4, L7, A1, A2, A4 |
| SUFFIX (High) | Holdings/Group/International are other entities | L10, L11, E6 |
| CODE2 (High) | A lone code-shaped token is a name unless it is the program's own | E18, L15 |
| NOTE (High) | Only "(EXCHANGE: TICKER)" is removed | L16, L17, plus 1 variant |
| HEADLINE (High) | A dateline needs a city in capitals, a full date and a known wire | L18, plus 3 headline variants |
| VOCAB (High) | Field words are description words only, lower-case or symbols, never connectives, places or rights words | V2, V3, V4; `descriptor_words` test |
| ACQ-PENDING, MINORITY (Medium) | Completed acquisitions only; no "percent of the shares" sentence | A3, A5, A6 |
| OWNER-KEY2 (Medium) | `_one_entity` for the acquired party | O1, O2 (parametrised) |
| ACQ-TWO (Medium) | Two acquirers are contested | O4; control: one acquirer written two ways |
| LBL-OWNER, LBL-DATE (Low) | Wording above | 1 test; rereview8 wording test updated |
| L14 (disclosed) | "Advanced Medicine" is a capitalised name and blocks | L14 |
| Confirmation | HUMAN only, hash-bound, withdrawable, unknown rows refused | 4 tests; CLI checked by hand (below) |

Also 31 close variants (roles reversed, a year after the as-of date, an undefined acronym, a name or a place inside a
description, "its" meaning the grantee's) block, and 38 clean restatements pass.

## 3. Measured result

| Check | Result |
|---|---|
| Tests | `tests/dealscreen`: 1,575 pass (1,436 at revision 11). `ruff` and `mypy` clean. The rest of the repository: 16,602 pass, 13 fail and 2 do not import (`httpx` missing); none of those files imports DealScreen (§4.7) |
| CLDN18.2 science | 0 of 62 scientific fields changed against the frozen baseline |
| CLDN18.2 transaction | 2 of 62 rows differ from `after_v11`, both in wording only: Zolbetuximab's reason now says the U.S. labeler is "named by the landscape … (not shown by a rights row to hold or own the program; verify)" (LBL-OWNER), and the memo's unapplied label for Zolbetuximab and IMAB362 reads "none gives a position on the as-of date" (LBL-DATE). No position or tier changed; 0 top-tier programs |
| Cross-version | 0 of 312 programs' science records differ |
| Cycle-4 equivalence | byte-identical, 4 of 4 |
| U1 | 38 of 38 CLDN18.2 open gates carry a diagnostic, as before |
| Reviewer's attack probes (`rr11/a/p11.py`, unchanged) | 5 of 75 top-tier, all controls or usefulness cases (E0, L0, A0, E22, E23); revision 11: 67. Every attack blocks |
| Earlier probes (`rr10/a`) | p10 0 of 75, p10b 0 of 5, d10 0 of 30 |
| Reviewer's end-to-end workspaces | ws_l 0 top-tier (revision 11: 7, ATG-022 at tier 0); ws_j2 0. ws_h2 3 and ws_i2 2: SKB315 (a China license with no quote), TORL-2-307-ADC in ws_h2 ("… TORL Biotherapeutics retains rights in the rest of the world", which REREVIEW10 called correct) and ATG-022 (the company's own dated availability statement, beside a China license with no quote). Each is a clean control |
| Confirmation, end to end | On a copy of ws_i2: `decide --reviewer-kind AI_PREPARED` refused ("an AI-prepared record cannot CONFIRM_RIGHTS_ROW"); an unknown event refused; a human confirmation of TORL's row 28 recorded; after `screen`, the row is tier 1 with the reason "confirmed as restating the row by jdoe (dec:00003, …)", and the memo repeats it |

### Usefulness

| Measure | Revision 11 | Revision 12 |
|---|---|---|
| Reviewer's 43 clean cases (`u10`, no placeholder) | 11 | 3 (UC1 dateline, UC9 exchange ticker, UC25 "China mainland") |
| Real CLDN18.2 quotes, through the gate, each row alone | 3 of 17 block | 4 of 17 block (all 4 rows that give a clear position alone) |
| Real CLDN18.2 quotes read directly | 13 of 17 block | 16 of 17 block |
| Implementer's harness (REREVIEW10-style) | — | 82 of 82 attacks block; 32 of 32 clean restatements pass |
| Usefulness against general Claude (15 deal programs) | 8/6/1 against 14/1/0 | unchanged: no CLDN18.2 position changed. No advantage is shown |

Revision 12 is stricter than revision 11. Read directly, the 16 real blocks are:
- 7 because the quote describes a different deal or more than the row: a co-promotion option in China beside an
  ex-China option (row 9, and row 10 the other way round), a joint partnership (row 12), a trial in China (row 16),
  another product (row 5, IBI363), the code TPX-4589 that the program's record does not hold (rows 6, 7);
- 2 acquisitions announced, not completed ("will pay EUR 422 million to acquire", rows 1, 2), as ACQ-PENDING asks;
- 7 on press wording no template covers: company boilerplate ("a clinical stage biopharmaceutical company focused
  on …", rows 13, 14, 17), "meanwhile, previously had a licensing agreement" (row 8), the typo "Inc i" (rows 3, 4)
  and one other sentence shape (row 15).

Each block quotes the clause and asks for one recorded confirmation. That is the intended path: the top tier now
depends on a template or on a human, never on a word list. The cost is analyst work, about one confirmation per
real rights row whose program would otherwise reach a top tier.

Two generic template changes were made after running the real quotes and the reviewer's clean cases, before
committing: a description may sit before the program after "the/a/an" ("the Claudin18.2 antibody NB-7"), and an
indication may follow the place ("for mainland China for gastric cancer"). Neither names a company or program.
"G licensed its P to E" is accepted ("its" is the grantor's); "E licensed its P to G" is not.

**Earlier clean cases that now block** (tested in `REV12_BLOCKED`; usefulness costs, no safety effect): "will pay"
and "will acquire" (modals); present-tense "acquires" (a pending deal reads the same); "transferred"; "after/
following a portfolio review"; a parent named after a party ("…, a subsidiary of Chinaco Group"); a place wider than
the row ("mainland China, Hong Kong and Macau" on a mainland-China row); "its third China deal"; "has Breakthrough
Therapy Designation"; "announced the end of the U.S. license"; an adviser named after the acquisition; "all rights …
revert" on a termination of one territory.

## 4. Costs and open issues

1. **Almost every real quote needs a human confirmation (16 of 17 read directly).** A clear position is now rare
   without analyst work. Nothing is dropped: every block names its clause and the event to confirm.
2. **Templates are DealScreen's own.** A wrong template would let a sentence through; a missing one only blocks.
   The templates are 34 distinct regular expressions over slots (49 by row type, since endings share theirs), so
   they can be read and attacked one by one.
3. **Confirmation is only as good as the analyst.** The record names the reviewer and is hash-bound to the row; the
   system cannot check that the source was read. DealScreen has no identity check on `--reviewer`.
4. **Rows with no quote still pass unread** (REREVIEW10 §2l, NOQ). The structured fields decide; a sparser export
   scores better than a richer one.
5. **Judgement calls kept:** partial-scope returns (H7, H8). "<party>, a subsidiary of <Name>" now blocks (P20).
6. **Recall is still capped by the rights file** (LM-302's and SKB315's returns are not in the frozen library), and
   no real vendor deals export has been tested.
7. **Repository tests outside DealScreen.** 13 fail (buyer-thesis tiers, API knowledge fallback, the architecture
   contract's unmapped `bve.se` module, PDCD1 population-capture receipts, the S&E release check) and `test_api.py`,
   `test_ui_pages.py` need `httpx`. None imports DealScreen, and revision 12 changes only `src/bve/dealscreen` and
   the DealScreen CLI.
8. AC14 stays open until a fresh adversarial review of revision 12.
