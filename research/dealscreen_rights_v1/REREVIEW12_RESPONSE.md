# Response to the R1 adversarial re-review 12 (REREVIEW12.md): revision 14

Revision 14 is R1 on top of revision 13 (d6d2d7f), on `dealscreen-mvp`, as of 2026-11-08. Nobody has reviewed it
yet. This file is the implementer's account, not a review: every claim below should be checked by running code. The
reviewer and the implementer are both AI. Neither is a human approval, and nothing here is validation. AC14 is not
claimed.

No confirmation was recorded by the implementer for any measurement in this file. The reviewer recorded AI test
confirmations in its own scratch copies and reported them (REREVIEW12 Scope); none is used here.

## 1. The highest-value fix: the retention sentence is as strict as the grants

REREVIEW12 §9: accept a retention only when the grantor is the program's company and the row is not a sublicense;
require that its places cover the buyer territory; allow no place only with "all other rights"; check after the
places, not before. Revision 14 does this in `rights_template._read_retention`:

- **RET-GRANTOR.** `quote_problem` passes `grantor_owns`, true only when the row's grantor is one legal entity with
  the program's company (`_one_entity`). A sublicensing licensee is the sublicense row's grantor, so "Chinaco Pharma
  retains all rights to NB-7 in the United States" now blocks: "says a party other than the program's company keeps
  rights, so that party may hold rights the row does not show" (RG4, ws_n ATG-022).
- **RET-PLACE.** The union of the places a retention names must include the buyer territory: "retains rights
  outside the United States", "in Japan and Europe", "ex-US rights" and "in mainland China" block with "says the
  company keeps rights only in …, which does not include US" (RT1-RT3, RT7, RX3; ws_n QLS31905, Spevatamig). "The
  rest of the world" beside the row means everything the row does not grant, so "retains rights in the rest of the
  world" (UC36) and "retains all rights in the U.S. and the rest of the world" still pass.
- **No place** only with "all other rights" or "all remaining rights" (RX1 "retains all rights to NB-7" now blocks).
- **Partial and future retentions block** (RT4, RT5, RT12): "keeps only commercialization rights, so another party
  may hold the other rights"; "will retain" and "will keep" are no longer in the sentence.

Not changed (judgement, disclosed): RT6 "retained U.S. rights to NB-7 in 2019" (past tense with a past date), RT8
"retains worldwide rights" beside a China license (a contradiction in the company's favour, not a third-party
holder; a first version of revision 14 blocked it, which broke two earlier clean tests, so it was dropped), RT9/RT10
"Nerida Bio Oncology/Pharma retains …" (the revision-11 business-word rule).

## 2. The other findings

| Finding | Revision 14 |
|---|---|
| HEADLINE3 (High) | A dateline city of one word may be any name that passes `_name_ok`; a city of more than one word must be on `_MULTI_WORD_CITIES` (about 60 hubs, e.g. "South San Francisco", "Research Triangle Park"). "TESSALY BUYS NERIDA, U.S., …" is no longer stripped; its words block the quote. An unlisted multi-word city is a usefulness cost, never a pass. A region part may end in "Province" ("Zhejiang Province", UC35). |
| UNPLACED2 (Medium) | Signing sentences ("G and E entered into an exclusive license agreement to develop and commercialize P", "… for the development and commercialization of P", option-and-license agreements) moved to the sentences that need a place unless the row covers the buyer territory. SG1-SG4, SG6 and ws_n TORL-2-307-ADC block. Cost: X19 (a signing sentence with no place and no program), which REREVIEW11 accepted, now blocks too. |
| ACQ-TWO2 (Medium) | Rival acquirers are grouped by `_entity_key`, the key succession uses, so "Nerida Bio" and "The Nerida Bio" bought by two parties block "who owns it is not established" (AQ1, AQ2, ws_n SKB315). |
| SUBSID (Medium) | `_SUBSIDIARY` is removed only when the parent is the program's company. "Nerida Bio, a wholly owned subsidiary of Chinaco Pharma, licensed …" now blocks (SB1-SB3, ws_n JS107). "Sideco Bio, a wholly owned subsidiary of Origin Bio (the company), licensed …" still passes. |
| PUNCT (Low) | A "?" anywhere in a quote blocks: "asks a question (…), so it does not state who holds rights". Other punctuation is still not read; I found no realistic quote where it changes who holds rights. |
| ROW12-REASON (Low) | "worldwide rights, excluding Greater China and South Korea" is read as one place (`_world_first`). Real row 12 still blocks, now because "shares … rights equally with" is no sentence of the co-development row, not because of a misread place. |
| CONFIRM-API (Medium) | `DecisionLog.record` itself refuses a CONFIRMED rights row confirmation when an agent variable is set, for every caller (CLI, Python API). A variable set to an empty string counts as set. The tests remove the agent variables in an autouse fixture so they run the same in any shell; the refusal is tested with the variable set to "1" and to "". Limit, unchanged: an agent that unsets the variable or edits the log is not stopped; DealScreen cannot prove a person made a HUMAN record. |
| WITHDRAW-STALE (Medium) | A withdrawal removes every stored confirmation of the row: its content hash, its event id, or its program, deal and type (`row_key`). Its `old_state` is `CONFIRMED_EARLIER_VERSION` when only an earlier version was confirmed. A withdrawal with nothing to withdraw is refused. The reviewer's C8/C9 sequence (confirm, change, withdraw through the changed row, revert) now leaves the row blocked. |
| Usefulness UC33, UC34 | Payment and milestone sentences between the row's parties pass ("E will pay G an upfront payment of N", "G is eligible to receive up to N in … milestones", with "plus tiered royalties"). They state money, not who holds rights. |
| UC37, UC38 | Not changed: "has licensed NB-7 from Nerida Bio" with no place, and a defined "Territory", still block. |
| O4 | Not changed: the memo keeps the decision id in the confirmation sentence, so the analyst can find the record. |

Tests: `tests/dealscreen/test_rights_rereview12.py` (49 tests: every §2 attack, the end-to-end sublicense and
termination shapes, ACQ-TWO2 both ways, ROW12, 13 clean cases, CONFIRM-API with "1" and "", WITHDRAW-STALE).
`test_rights_rereview10.py` no longer expects the upfront-payment sentence to block.

## 3. Measured (implementer, 2026-11-08)

Script: `scratchpad/fin14/measure.sh` (revision 13's, plus REREVIEW12's probes, ws_n and the U1 REVIEW7 workspaces).

| Check | Revision 13 | Revision 14 |
|---|---|---|
| `tests/dealscreen` | 1,726 pass | 1,803 pass; ruff and mypy clean |
| CLDN18.2 science fields | 0 of 62 | 0 of 62 |
| CLDN18.2 `after_transaction.csv`, memo | — | byte-identical to revision 13 (memo apart from the generation line) |
| Cycle-4 equivalence | 4 of 4 | 4 of 4 byte-identical |
| REREVIEW12 p13 (top tier) | 27 of 41 | 11 of 41 |
| REREVIEW12 p13b | 11 of 13 | 2 of 13 |
| REREVIEW12 ws_n (programs in a top tier) | 7 | 0 |
| p12 / p12b / p12c / p12d | 27 / 10 / 6 / 0 | 26 / 10 / 6 / 0 (X19 now blocks) |
| p10 / p11 | 0 of 75 / 5 of 75 | unchanged |
| End to end ws_m, ws_h2, ws_i2, ws_j2, ws_l, ws_h, ws_i, ws_j | 0, 3, 2, 0, 0, 0, 0, 0 | unchanged (the h2/i2 rows are controls) |

### 3a. What still reaches a top tier in p13 and p13b

Controls: RT0 ("retains all rights outside mainland China"), DL4 (a real dateline), SG5 (a signing sentence with a
place), RX7 ("all other rights"). Usefulness rows the reviewer wanted to pass: DL5-DL9 (prefecture and province
datelines, "CAMBRIDGE, England", "SOUTH SAN FRANCISCO, Calif. and SHANGHAI"). Judgement rows, listed in §1: RT6,
RT8, RT9, RT10.

## 4. Usefulness

| Measure | Revision 13 | Revision 14 |
|---|---|---|
| REREVIEW10's 43 clean cases | 6 pass | 7 pass |
| REREVIEW11's 24 sentences | 15 pass | 16 pass (UC4, an upfront payment) |
| REREVIEW12's 8 clean sentences (u13) | 3 pass | 6 pass (UC33, UC34, UC35 now pass; UC37, UC38 block) |
| Real CLDN18.2 quotes read directly | 15 of 17 block | 15 of 17 block |
| Real CLDN18.2 quotes through the gate | 4 of 17 block | 4 of 17 block |

The real quotes still nearly all need an analyst confirmation: they are multi-sentence releases with company
descriptions, other programs and defined terms. Payment sentences no longer add to that.

## 5. Against the reference and general Claude

No CLDN18.2 rights position changed (the CSV is byte-identical), so REREVIEW12 §6 stands: 0 false unobstructed,
1 labelled wrong holder, 2 missed returns, 2 missed owners; usefulness 8 right / 6 partial / 1 missed against
general Claude's 14 / 1 / 0. No advantage is shown, and none is claimed.

## 6. Costs and limits

1. A multi-word dateline city off the list leaves the dateline in the quote, which then blocks.
2. Signing sentences with no place now block on rows that do not cover the buyer territory (X19).
3. The agent-shell refusal stops an agent that runs in a known agent shell and does not edit its environment. It
   does not prove a person made a HUMAN record.
4. Judgement rows RT6, RT8, RT9, RT10 still pass (§1).
5. Recall is capped by the rights file; no real vendor export has been tested.

## 7. The highest-value next issue

The same as revision 13's: recall and usefulness are now limited by the input, not the reader. The rights file
misses returns and owners (LM-302, SKB315), and 15 of 17 real quotes need one analyst confirmation each. The next
step that would change a BD analyst's answer is a real vendor export (licensed data), which needs the owner's
approval and cannot be done here.
