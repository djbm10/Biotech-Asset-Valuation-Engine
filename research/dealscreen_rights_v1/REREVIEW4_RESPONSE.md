# Response to the R1 adversarial re-review 4 (REREVIEW4.md): revision 6

Revision 6 is the working tree on `dealscreen-mvp` as of 2026-11-01. Nobody has reviewed it yet. This file is the
implementer's account, not a review: every claim below should be checked by running code. The reviewer and the
implementer are both AI; neither is a human approval and nothing here is validation.

## 1. The highest-value fix: the gate's default is inverted

REREVIEW4 section 13 asked that every rights-bearing input prove it is consistent, or block. Revision 6 does this in
one module, `rights_allow.py`.

- **Plain forms** (`plain_form`). Beside a clear position, a rights text counts as consistent only if every clause is
  one of: a placeholder or bare no-grant phrase; an offer in plain present words (closed word list, no digits, no
  "to …", no party but the program's company, role nouns only as what is sought); the company keeping the rights
  ("rights retained", "wholly owned by X", "X retains all rights outside Greater China"); a return to the company,
  dated no later than the as-of date; a grant over named places other than the U.S. only. Anything else blocks,
  quoted and cited, with the question "What does … say about rights in the buyer territory, and who holds them?".
- **Every input is read** (`rights_gate.reconcile`): every landscape and analyst U.S.-rights statement and holder, as
  before, and now every Partnerships and Geographic Notes value (`CommercialAssessment.other_rights_all`). A
  Partnerships value that only names organisations (`is_rights_text` false) is not rights evidence and stays neutral.
  The gate now runs for every buyer territory, not only those containing the U.S.
- **Notes in names** block wherever they appear: the landscape company name, a rights row's grantor or grantee, a
  holder. A one-word place inside a legal name before the corporate form ("Acme Bio (Suzhou) Co., Ltd.") is not a
  note (`rights_territory.content_note`); one after the form ("Acme Bio, Inc. (Delaware)") still is, because a
  one-word party has the same shape (judgement, kept).

The two smaller fixes the review named:

- **Ledger dates** (`rights_ledger`, `rights_position`). A TERMINATED or EXPIRED status reported in a source dated
  after the as-of date is not applied, and is listed (E2). A status-only ending beside an availability statement
  blocks: the status gives the end no date of its own, so it cannot be ordered against the statement (E1, E3). An
  undated acquisition is not applied; it blocks with "has no date, so it cannot show who holds the rights now" and
  asks for a dated source (O1).
- **Field path territory** (`screening.program_transaction`). The landscape's U.S.-rights fields are read as a
  position only when the buyer territory is exactly {US}. For any other territory the program has no field position
  and the reason says why (TER-F, TER2).

The reader was tightened where its readings fed the old gate: date tokens ("2H26", "FY27", "post-2026") are no
longer program codes (R1); a role noun as subject or as the party rights are "available to" is never an offer by the
company (R2, R3); a party span is erased only if it does not start with a region, so "option to U.S. rights" is read
(R4); "rights retained by" is no longer NOT_AVAILABLE (RET); a clause split that leaves an unread part makes the whole
clause unread (FE4); RETURNED with AVAILABLE reads AVAILABLE (K2); "Ex-China rights available" reads as an offer
covering the U.S. (U1).

Rows (ROW, judgement taken): an unattached accepted row now guards a program when its id is close to the program's
(`rights_gate.ids_close`: near key equal, one id the other plus tokens such as "AB-24 (ADC)" or "LB4330-01", or same
numbers with letter groups that start each other) or, when its id is close to no program, when it names the
program's company as grantor or grantee. A transposed id ("CL-42" for "CL-24") still guards nothing unless it names
the company: the digits differ, and guarding on that would hold every program with a two-digit id.

## 2. The findings

Per-program cases run through `program_transaction` (the reviewer's own scripts, `rv_*.py`, re-run unchanged against
revision 6; tests in `test_rights_rereview4.py`).

| Id | Severity | Revision 6 | Tests |
|---|---|---|---|
| R1 dated offers | High | Not read ("Available 2H26" → UNKNOWN, not understood); no rights evidence on the field path; blocked beside a clear position | `test_r1_…` (8) |
| R2, R3 role nouns, offers to a party | High | Not a plain form; never a top tier. "Collaborator open to licensing U.S. rights" and "Rights available to collaborator" read ENCUMBERED (deprioritized) | `test_r2_r3_…` (10) |
| R4 U.S. grant erased as a party | High | Read: "option to U.S. rights" → OPTION held by a third party; the rest ENCUMBERED; beside a China license the position is CONFLICTING | `test_r4_…` (6) |
| R5 return to a third party | High | Not a plain form; blocks | `test_r5_…` (4) |
| P Partnerships, Geographic Notes | High | Read and blocked unless plain (P1–P7 all RIGHTS_UNRESOLVED); a names-only Partnerships value stays neutral | `test_p_…` (8) |
| N, CN notes in names | High | Block (N1–N4, CN1–CN3); N1 no longer sets the holder | `test_n_…`, `test_cn_…` |
| E1, E3 status-flag endings | High | Block, "stated only by the record's status" | `test_e1_e3_…` (2) |
| E2 status after the as-of date | High | Not applied; the license stays in force (LICENSED, deprioritized) | `test_e2_…` |
| O1 undated acquisition | High | Not applied; blocks; asks for its date | `test_o1_…` |
| TER-F, TER-G | High | Field path only for {US}; gate runs for every territory | `test_ter_f_…` (2), `test_ter_g_…` |
| TER2 | Medium | No longer an EU encumbrance | `test_ter2_…` |
| K2, FE4, RET | Medium | No false conflict or encumbrance; RET is a plain form ("rights kept by the company") | `test_k2_…`, `test_fe4_…`, `test_ret_…` (3) |
| U1 "Ex-China rights available" | Usefulness | Tier 0 again | `test_u1_…` |
| U2 company-retains wording | Usefulness | Tier 1 beside a China license, listed as consistent | `test_u2_…` (3) |
| U3 city in a legal name | Usefulness | "(Suzhou) Co., Ltd." tier 1; "Inc. (Delaware)" still blocks (judgement) | `test_u3_…` (2) |
| ROW | Judgement | Suffixed and letter-variant ids guard; company-party rows guard when the id points nowhere | `test_row_…` (11) |
| L1 availability sentence | Low | Says what DealScreen found and that it is not a check the statement is true | `test_l1_l2_l4_…` |
| L2 "feed the transaction view" | Low | Lists the fields asserted per program and the program's current tier; geographic notes included | `test_l1_l2_l4_…`, `test_rights_rereview2` (edited) |
| L3 `assert` note | Low | Says whether the gate accepts the text as a plain form; notes for Partnerships and Geographic Notes too | `test_l3_…`, `test_rights_rereview3` (edited) |
| L4 own rejected row hidden in the memo | Low | Shown in the program's line ("no rights record applied (rights row 18 for this program was rejected at import …)") | `test_l1_l2_l4_…` |
| L6 zolbetuximab note question | Low | Not changed: the note is still asked about. The program is excluded as marketed, so no tier depends on it | — |
| D1, D2 "Nerida Bio Inc., Tessaly, US" | Judgement | Kept: read as the company at an address | — |

Edited existing tests (each for a stated rule): `test_a1d` (an undated acquisition now blocks, so the A1d expectation
is stricter); the `rights_reading_note` test (the note now adds the gate's verdict); the memo L2 wording test.

## 3. Measured result

| Check | Result |
|---|---|
| Tests | `tests/dealscreen`: 743 pass (653 at revision 5; 90 new in `test_rights_rereview4.py`). `ruff` and `mypy` clean on `bve.dealscreen` and the CLI. |
| Reviewer's scripts, re-run | Every High and Medium case in REREVIEW4 sections 2–7 is out of tiers 0 and 1 or no longer a false conflict. Still in a top tier: the cases the reviewer marked correct (E4, E5, E6, K9, K12, O4, O5) and the acknowledged judgements D1, D2 and O3. The over-caution cases K1, K3, K4, K5, K13, FE3, O6 (company-retains wording, legal-name city) and K6 ("Ex-China rights available") now reach the top tier the reviewer expected. K8's company offer beside a China license is now listed and cited as consistent. |
| Reviewer's end-to-end workspaces, re-screened from copies | Flagged top-tier placements 18 → 0: ws_a 6 → 0, ws_b 6 → 0 (Spevatamig's licensor note, N, included), ws_c 6 → 0; ws_d had none. The one remaining top-tier program, Spevatamig in ws_a, is the reviewer's unflagged control (China license only). ws_d's SKB315 line now shows its own rejected row (L4). |
| CLDN18.2 (`after_v6/`) | No tier, position, rank, holder or blocker changed from revision 5: eligible 8 rights unresolved, 6 deprioritized; none in tier 0 or 1. Memo wording only ("no rights record applied"). |
| Science | 0 of 62 CLDN18.2 scientific fields changed against the frozen baseline (`compare.py`). Cross-version against revision 5's snapshot: 0 scientific and 0 tier changes on 312 assets (synthetic 192, FcRn v1 40, FcRn v2 40, C5 40). Cycle-4 equivalence: byte-identical, fast path, on all four. |
| Usefulness against general Claude (B) | Unchanged: no CLDN18.2 call changed. 10 right / 4 partial / 1 missed against B's 14 / 1 / 0 on the 15 deal programs. No advantage is demonstrated. |

## 4. Acceptance criteria, as the implementer reads them (not a review)

| AC | Revision 5 (REREVIEW4) | Revision 6, implementer's reading |
|---|---|---|
| AC1, AC8, AC9, AC12 | PASS (AC9 partial on territory) | AC9: the territory preference now applies on the field path and in the gate. AC12: no landscape name added to `src/` |
| AC2 | PARTIAL | R1 and R2 inputs no longer reach tier 0; the memo sentence no longer overclaims (L1) |
| AC3 | PARTIAL | R4, TER-F, TER-G, TER2 addressed |
| AC4 | PARTIAL | E1, E2, E3, R5, K2 addressed; LM-302 still not RETURNED (data) |
| AC6 | PARTIAL | P, R5, R2, R4, N addressed; RET and K2 false conflicts removed |
| AC10 | PARTIAL | Contrary text is cited as a blocker; O1's acquisition cited; L4 fixed |
| AC11 | PARTIAL | Blocked texts get a question naming the text; O1 asks for a date; L6 unchanged |
| AC13 | PARTIAL | unchanged: LM-302 CONFLICTING, not returned |
| AC14 no new errors | FAIL | cannot be self-certified: needs a fresh adversarial review |

## 5. Costs and open issues

1. **Over-caution grows.** Any rights text outside the plain forms now holds a program out of tiers 0 and 1, with a
   question. On CLDN18.2 this costs nothing (no program was in a top tier). On real vendor exports with free-text
   rights notes it will hold back clean programs; each is cited, so an analyst can retract or reword.
2. **The plain forms are word patterns.** A text in a plain form still says only what its source says. A reviewer
   should try phrasings that fit a form and mean something else.
3. **Rows**: a transposed id that names no company of the landscape guards nothing; a rejected row with an unmatched id
   still guards every program.
4. **Recall is capped by the rights file** (LM-302's successor, SKB315's return, EO-3021's discontinuation). This,
   not the gate, is why B still leads on usefulness.
