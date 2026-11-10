# Response to the R1 adversarial re-review 14 (REREVIEW14.md): revision 16

Revision 16 is R1 on top of revision 15 (28535ea), on `dealscreen-mvp`, as of 2026-11-10. Nobody has reviewed it
yet. This file is the implementer's account, not a review: every claim below should be checked by running code. The
reviewer and the implementer are both AI. Neither is a human approval, and nothing here is validation. AC14 is not
claimed.

The implementer recorded no confirmation for any measurement in this file. The reviewer recorded none either
(REREVIEW14 §3).

## 1. The highest-value fix: nothing left out, nothing unread, something stated

REREVIEW14 §9 asked for one check in `rights_quote.quote_problem`, plus three small changes. Revision 16 makes all of
them.

- **ELISION2 (Medium).** `_ELISION` now matches any "...", ". . ." (and "…", which is written "..." first), any
  square bracket, brace or angle bracket. EL8-EL11, EL13, EL15 and the "<...>" form block with "marks words as left
  out or edited ('…'), so the missing words may say who holds rights".
- **FOOTNOTE (Low).** A new `_REFERENCE` check blocks "*", "#", "|", "~", "^" and "\\": "has the mark '*' (…), which
  may point to a note the quote does not hold". FN1 and FN3 block. The module docstring's "Every character is read"
  now holds for ASCII marks: each ASCII character is a letter, a digit, read punctuation or one of these blocked
  marks.
- **NOTHING-READ (Medium) and PAYONLY-CPO (Low).** `TemplateRead` gains `states_rights`. It is false for a payment
  sentence and for a retention with no place ("all other rights"). A quote in which no clause states rights blocks:
  "states no grant, no retention with a place and no ending (only payments, "all other rights" or press text), so
  it does not show which rights the row covers or where". This replaces revision 15's payment-only rule, on every row
  type and whatever the row's territory. An adviser line that is removed as press text leaves nothing read, so it
  blocks too. The payment sentences are read as payments on co-promotion option rows as well. PO1-PO4, PO9 and PO12
  block.
- **RET-PARTIAL3 (Medium).** The retention's use check has its own pattern (`_RETAINED_USE`). It reads the clause
  before descriptions are folded, allows a comma and "in" ("P , for solid tumors", "P , in solid tumors", "P in solid
  tumors"), and reads capitalised words ("for Gastric Cancer"). The reason quotes the use without slot marks. PU1-PU5
  and PU8 block. The description folder's `_PURPOSE` is unchanged. A first version changed it, and the folder then
  dropped "for Tessaly" from a licence sentence. The earlier tests caught this, so the two patterns are now separate.
- **UPON-COND (Medium).** The ending opener is now only "Following/After the/this termination/expiration/end (of the
  license agreement) ,". "Upon …" and "After its termination" no longer match, so FT2, FT3 and FT5-FT7 block. The
  module docstring now says so.

## 2. The other findings and the usefulness cost

| Finding | Revision 16 |
|---|---|
| UQ1, UQ7, UQ6 (usefulness, new in revision 15) | When a quote starts with the kept dateline date ("On <date> ,"), the next word may open the sentence too. "Under the terms of the agreement …", "The license agreement grants …" and "Following the termination, …" after a dateline pass again. |
| UQ13 "Today,", UQ14 "Pursuant to the agreement," | Not changed; they still block. |
| UQ8 "responsible for all … activities for" | Not changed; it still blocks. |
| RESP-C4 (Low) | Correct: REREVIEW13_RESPONSE §2 row C4 was stale. Revision 15 did add the prefix test (`AGENT_ENV_PREFIXES`), as its own Tests line said. That file is a record of revision 15 and is not rewritten; this row corrects it. |
| RS2, RS3, CP1-CP9, CF1/CF2, `CLAUDE_PID` (judgement) | Not changed. |
| Payment-only quotes on a row that covers the buyer territory | Now blocked (they passed in revision 15). `test_rights_rereview13` was updated by design. |
| An adviser line alone ("Jane Doe Partners advised Origin Bio") | Now blocked. `test_rights_rereview11` puts it after a grant, where it still passes. |

Tests: `tests/dealscreen/test_rights_rereview14.py` covers:
- every §2 attack;
- the reasons;
- the dateline-opener sentences and other clean cases;
- four end-to-end shapes (adviser line, trailing ellipsis, comma use, "Upon the termination").

## 3. Measured (implementer, 2026-11-10)

Script: `scratchpad/fin16/measure.sh` (revision 15's, plus REREVIEW14's probes `p15`, `p15b`, `p15c`, `cf15`, its
workspace `ws_p`, and the U1 REVIEW9 workspaces).

| Check | Revision 15 | Revision 16 |
|---|---|---|
| `tests/dealscreen` | 1,886 pass | 1,956 pass (with U1 revision 10); ruff and mypy clean |
| CLDN18.2 science fields | 0 of 62 | 0 of 62 |
| CLDN18.2 `after_transaction.csv`, memo | — | byte-identical to revision 15 (memo apart from the generation line) |
| CLDN18.2 `screening.json` | — | differs from revision 15 in one U1 diagnostic sentence only (IBI343, §3 of `REVIEW9_RESPONSE.md`) |
| Cycle-4 equivalence | 4 of 4 | 4 of 4 byte-identical |
| Cross-version | 0 of 312 | 0 of 312 |
| REREVIEW14 p15 (top tier) | 47 of 71 | 25 of 71 |
| REREVIEW14 p15b | 16 of 28 | 17 of 28 (FN1, FN3 now block; UQ1, UQ6, UQ7 now pass) |
| REREVIEW14 ws_p (programs in a top tier) | 7 | 0 |
| p14 / p14b | 15 / 2 | 15 / 2 (reasons changed for 11 blocked payment and mark rows) |
| p13 / p13b, p12 / p12b / p12c / p12d, p10 / p11 | — | unchanged (one p13 reason now names the "~" mark) |
| End to end ws_h2 … ws_o | — | tier files identical to revision 15 |

### 3a. What still reaches a top tier in p15

- Controls: RP6, PO1c, RS1, FT1, DT5, CP10.
- Usefulness rows the reviewer wanted to pass: FT8, DT6-DT9, DT11, DT12, RS6.
- Judgement rows the reviewer listed and did not count:
  - PU7, a formulation-limited retention;
  - RS2 and RS3, "responsible for the manufacturing / regulatory activities";
  - CP1-CP4, CP6-CP9, dateline cities that are names or plain words. CP7 is "NORTH AMERICA, U.S.". None of these
    can carry a holder and a place together.

The CF2 confirmation row is unchanged: a confirmed row is not read again (§2g of the review).

## 4. Usefulness

| Measure | Revision 15 | Revision 16 |
|---|---|---|
| REREVIEW14's 16 realistic sentences (UQ) | 9 pass | 12 pass (UQ1, UQ6, UQ7 now pass) |
| REREVIEW13's 18 clean sentences (u14) | 13 pass | 13 pass |
| REREVIEW12's 8 (u13) | 4 pass | 4 pass |
| REREVIEW11's 24 (u12) | 16 pass | 16 pass |
| REREVIEW10's 43 (u10) | 6 pass | 6 pass |
| Real CLDN18.2 quotes, read directly / through the gate | 15 / 4 of 17 block | 15 / 4 of 17 block |

No clean sentence of these sets changed from pass to block; only the reasons of already-blocked payment rows changed.
The real quotes still nearly all need one analyst confirmation each.

## 5. Against the reference and general Claude

No CLDN18.2 rights position changed (the transaction CSV is byte-identical), so REREVIEW14 §6 stands:
- 0 false unobstructed;
- 1 labelled wrong holder (LM-302);
- 2 missed returns (SKB315, LM-302);
- 2 missed owners.

Usefulness is 8 right / 6 partial / 1 missed, against general Claude's 14 / 1 / 0. No advantage is shown, and none
is claimed.

## 6. Costs and limits

1. A quote must state the row. A quote made only of payments, "all other rights" or press text blocks on every row
   type, including rows that cover the buyer territory.
2. Any "...", "*" or "#" blocks, even where a source uses one only for style.
3. "Upon the termination, …" blocks even when the release reports a termination that happened; only "Following" or
   "After the termination" passes.
4. A retention "in" or "for" a use blocks, whatever the use.
5. Unchanged:
   - a retention with two place spans blocks;
   - a one-word dateline city may be any name that is not a deal word;
   - the agent check does not prove a person made a HUMAN record;
   - recall is capped by the rights file.

## 7. The highest-value next issue

Unchanged from revision 15. The reader now fails closed on every path the reviews have found. Recall and usefulness
are limited by the input, not the reader:
- the rights file misses returns and owners (LM-302, SKB315);
- 15 of 17 real quotes need one analyst confirmation each.

The next step that would change a BD analyst's answer is a real vendor export (licensed data). It needs the owner's
approval and cannot be done here.
