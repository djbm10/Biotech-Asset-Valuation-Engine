# Response to the R1 adversarial re-review 13 (REREVIEW13.md): revision 15

Revision 15 is R1 on top of revision 14 (624b2f0), on `dealscreen-mvp`, as of 2026-11-08. Nobody has reviewed it
yet. This file is the implementer's account, not a review: every claim below should be checked by running code. The
reviewer and the implementer are both AI. Neither is a human approval, and nothing here is validation. AC14 is not
claimed.

The implementer recorded no confirmation for any measurement in this file. The reviewer recorded one AI test
confirmation and its withdrawal in its own scratch copy and reported them (REREVIEW13 §3, C6); neither is used here.

## 1. The highest-value fix: a retention names one place, and keeps plain rights

REREVIEW13 §9: accept a retention with one place span at most, or none with "all other/remaining rights"; accept
only plain "rights" as its object; block a quote with an omission mark before reading it. Revision 15 does all three.

- **RET-PLACE2 (High).** `rights_template._read_retention` blocks a retention clause that names more than one place:
  "names more than one place for the rights the company keeps (worldwide; excluding the US), so DealScreen cannot
  tell where it keeps them; another party may hold rights in the buyer territory". RU1-RU5, RU18, RU19 and ROW1
  block. One span still reads as one territory, so "retains global rights outside of China" (UC44), "retains all
  rights in the U.S. and the rest of the world" and "retains all rights to NB-7 outside mainland China" pass.
- **RET-PARTIAL2 (Medium).** The retention's object is plain "rights" (`_retention`: the `_DEV_LIST` verbs are gone;
  "full" is allowed). "retains all rights to develop / commercialize NB-7", "the rights to market and sell" no longer
  match the retention sentence. A retention that "is for" a use ("U.S. rights to NB-7 for gastric cancer") blocks
  with "says the company keeps rights only for gastric cancer", whatever the case of the landscape's indication
  field (`_PURPOSE` is read on the clause before descriptions are folded).
- **RET-REASON (Low).** A clause that keeps rights in words the retention sentence does not read ("retains all rights
  to develop …", "will retain …", "kept …" with an unread object) now says "says a party keeps rights in words
  DealScreen does not read (only plain "retains rights to the program in one place"), so another party may hold the
  rest", not that a granted place is outside the row (`_KEEPS`).
- **ELISION (Medium).** `quote_problem` blocks any quote with a square bracket or a parenthesised ellipsis ("[...]",
  "[…]", "(...)", "[the Company]") before reading: "marks words as left out or edited ('…'), so the missing words may
  say who holds rights". EL1, EL2, EL4, EL7 and ws_o BL-M05D1 block.

## 2. The other findings

| Finding | Revision 15 |
|---|---|
| DATELINE-DATE (Low) | `_strip_dateline` keeps the dateline's date as "On <date>," before the text, so it is read against the as-of date like any other date. DT1 ("BOSTON, Mass., March 3, 2026 …" at as-of 2025-06-01) blocks: "gives the date 2026-03-03, which may be after the as-of date". |
| HEADLINE-1WORD (Low) | A dateline city may not hold a deal word (`_DEAL_WORD`: takeover, divest-, acqui-, merger, buy(s), sell(s), control-, own(s), licen-, option, return, regain, terminat-, partner, deal, transfer, spin, rights, exclusiv-, agreement, grant, hold, retain, keep, collaborat-). "TAKEOVER, Mass.", "DIVESTITURE, U.S.", "TESSALY-CONTROLLED, U.S." and "NORTH ACQUIRES, U.S." block. A one-word city that is not a deal word ("TESSALY, U.S.") still passes; that is a name, which holds no rights statement. |
| PAYONLY (judgement in the review) | A quote made only of payment sentences blocks unless the row covers the buyer territory, as a signing sentence with no place does: "states only payments between the parties, not which rights were granted or where". A payment beside a grant still passes. PY8, PY9 and ws_o TORL-2-307-ADC block. Cost: UC41 alone (two payment verbs, no grant) blocks for this reason. |
| UC41, UC42 | Two receive verbs ("will receive … and is eligible to receive …") and "as well as" join payments. Beside a grant they pass. |
| UC43 | "full rights" is a plain retention. |
| UC47 | "E will be responsible for the development and commercialization of P in R" is a licence sentence that needs a place unless the row covers the buyer territory. |
| UC49-UC51 | A two-word dateline city whose first word is a common city prefix (North, South, East, West, New, Fort, Port, Saint, St., San, Santa, Los, Las, Lake, Mount, Glen, Palm, Bay, Upper, Lower, Great) passes when neither word is a deal word. |
| UC54 | "Following/After/Upon the termination (of the license) ," may open an ending sentence; "Following", "After" and "Upon" may open a sentence in capitals. |
| C4 (judgement) | Not changed: the agent check reads the variables in its list (`AGENT_ENV_VARS`), two of them for this shell. A longer list or a prefix test would catch an agent that removes only those two; an agent that clears its environment is not stopped by any list; DealScreen cannot prove a person made a HUMAN record. |
| RU14, RU20, RT6, RT8-RT10 (judgement) | Not changed: past retentions ("kept U.S. rights") and the business-word variants still pass. |

Tests: `tests/dealscreen/test_rights_rereview13.py` (every §2 attack, the reasons, the clean cases, three end-to-end
shapes, the agent prefix). `test_rights_rereview12.py`: the payment sentences in its clean list now follow a grant.

## 3. Measured (implementer, 2026-11-08)

Script: `scratchpad/fin15/measure.sh` (revision 14's, plus REREVIEW13's probes `p14`, `p14b`, `u14`, its workspace
`ws_o`, and the U1 REVIEW8 workspaces).

| Check | Revision 14 | Revision 15 |
|---|---|---|
| `tests/dealscreen` | 1,803 pass | 1,886 pass (with U1 revision 9); ruff and mypy clean |
| CLDN18.2 science fields | 0 of 62 | 0 of 62 |
| CLDN18.2 `screening.json`, `after_transaction.csv`, memo | — | byte-identical to revision 14 (memo apart from the generation line) |
| Cycle-4 equivalence | 4 of 4 | 4 of 4 byte-identical |
| Cross-version | 0 of 312 | 0 of 312 |
| REREVIEW13 p14 (top tier) | 38 of 57 | 15 of 57 |
| REREVIEW13 p14b | 4 of 11 | 2 of 11 |
| REREVIEW13 ws_o (programs in a top tier) | 5 | 0 |
| p13 / p13b | 11 / 2 | 11 / 2 (reasons changed for three blocked rows) |
| p12 / p12b / p12c / p12d | 26 / 10 / 6 / 0 | unchanged (reasons changed for blocked retention rows) |
| p10 / p11 | 0 of 75 / 5 of 75 | unchanged |
| End to end ws_h2 … ws_n | — | tier files identical to revision 14 |

### 3a. What still reaches a top tier in p14 and p14b

- Controls: RU13, RU16, SG7, SG9, DL12, RW1.
- Usefulness rows the reviewer wanted to pass: DL13, DL14.
- Judgement rows the reviewer listed and did not count: RU14, RU20 (past retentions), SG8 (the place is on the
  royalties), EL5 (scare quotes), SB4 (the licensee is the company's subsidiary), SB5 (a self-referential subsidiary
  clause), RG7 (the landscape names the licensee as the company).
- DT4: a wire-form dateline with no date, so there is nothing to read against the as-of date.
- DL11: a one-word name as a dateline city ("TESSALY, U.S."). A name is not a deal word and holds no rights
  statement; this is disclosed, not fixed.

## 4. Usefulness

| Measure | Revision 14 | Revision 15 |
|---|---|---|
| REREVIEW13's 18 clean sentences (u14) | 8 pass | 13 pass (UC43, UC44, UC47, UC49-UC51, UC54 now pass; UC40 now blocks as payment-only) |
| REREVIEW12's 8 clean sentences (u13) | 6 pass | 4 pass (UC33, UC34 now block as payment-only) |
| REREVIEW11's 24 sentences (u12) | 16 pass | 16 pass (UC13 "responsible for" and UC24, a dateline with "Jan.", now pass; UC4, payment-only, blocks) |
| REREVIEW10's 43 clean cases | 7 pass | 6 pass (UC7, payment-only, blocks) |
| Real CLDN18.2 quotes, read directly / through the gate | 15 / 4 of 17 block | 15 / 4 of 17 block |

The payment-only rule (PAYONLY) costs 5 clean sentences across these sets: UC4, UC7, UC33, UC34 and UC40. Each
states only money. I chose to treat them as a signing sentence with no place is treated, because the review found the
two rules disagreed. The other choice, letting both pass, would reopen UNPLACED2. This is a judgement, and a reviewer
may weigh it the other way.

## 5. Against the reference and general Claude

No CLDN18.2 rights position changed (the transaction CSV is byte-identical), so REREVIEW13 §6 stands:
- 0 false unobstructed;
- 1 labelled wrong holder (LM-302);
- 2 missed returns (SKB315, LM-302);
- 2 missed owners.

Usefulness is 8 right / 6 partial / 1 missed, against general Claude's 14 / 1 / 0. No advantage is shown, and none
is claimed.

## 6. Costs and limits

1. A quote of payments alone blocks (§4).
2. A retention with two place spans blocks, even when both include the buyer territory ("retains U.S. rights to NB-7
   worldwide"); one span is read as written.
3. A one-word dateline city may be any name that is not a deal word.
4. The agent check stops an agent that runs in a known agent shell and does not clear its environment. It does not
   prove a person made a HUMAN record.
5. Recall is capped by the rights file; no real vendor export has been tested.

## 7. The highest-value next issue

Unchanged from revision 14. Recall and usefulness are limited by the input, not the reader:
- the rights file misses returns and owners (LM-302, SKB315);
- 15 of 17 real quotes need one analyst confirmation each.

The next step that would change a BD analyst's answer is a real vendor export (licensed data). It needs the owner's
approval and cannot be done here.
