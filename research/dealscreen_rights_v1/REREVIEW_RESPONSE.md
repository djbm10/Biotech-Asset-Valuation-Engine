# Response to the R1 adversarial re-review (REREVIEW.md): revision 3

INTERNAL DEVELOPMENT. Written by the implementer, not the reviewer. It claims nothing about whether the fixes are
adequate, and it is not validation. AI-simulated measurement only.

Revision 3 is on `dealscreen-mvp` after e805f0b. Every finding has a held-out test with fictional parties in
`tests/dealscreen/test_rights_rereview.py`, named by the re-review's case id. Outputs were regenerated in
`after_v3/`. The reviewer's own scripts (`adv2.py`–`adv5.py`) were re-run unchanged, except that a validation
error is recorded instead of aborting the run.

## 1. The ranked issues (REREVIEW §7)

| # | Finding | Response | Test |
|---|---|---|---|
| 1 | Weak inputs promote programs to the top tiers (D1, D2, U1, U2, A1, A2, A3) | **Fixed in the ledger, and guarded in the transaction view.** Only `CLEAR_POSITIONS` (returned, not encumbered, owner acquired, availability stated) can reach tiers 0/1. Ledger rules: an ending with no event date of its own (undated, or dated only by its report) counts ended grants as candidates, so a second record of one termination never clears a re-license (D1, D2, D3). An outcome whose territory is written but cannot be read changes nothing: the grant is kept and a question is asked (U1, U1b, U3). An outcome with a stated territory changes only that territory (U2). Availability statements count only with status ACTIVE or UNKNOWN (A2), and a readable territory that covers the buyer's or none written (A1). A statement is superseded by any later grant over the territory, active or since ended (A3). | `test_d1_…`, `test_d2_…`, `test_d3_…`, `test_u_…` (3 cases), `test_u2_…`, `test_a1_…` (2), `test_a2_…` (2), `test_a3_…` |
| 2 | The buyer territory is not validated (B1) | **Fixed at three levels.** `TransactionPreferences.territory` and `CommercialDiligence.required_market` refuse codes outside `REGIONS` (case and spaces normalised: `us ` → `US`; `USA`, `U.S.`, `UNITED STATES` → error naming the valid codes). `rights_position()` itself refuses an empty or unknown territory, so a direct caller cannot bypass the check. | `test_b1_…` (4) |
| 3 | The rights file overrides other rights evidence (E2, E3) | **Fixed.** A landscape or analyst U.S. encumbrance against a clear position → `CONFLICTING_EVIDENCE`, with the reason and "Which is current?" (E2). A rejected rights row now carries its program id; the program cannot enter tiers 0/1, the reason names the row, and the questions ask to correct and re-import it (E3). Tested end to end on the synthetic landscape through the workspace. | `test_e2_…`, `test_e3_…`, `test_rights_file_reaches_each_program_through_the_workspace` |
| 4 | Landscape "not currently available" lands in the availability tier (F1) | **Fixed.** "Not currently / no longer / never available" and "unavailable" read `NOT_AVAILABLE_PER_SOURCE`; "available only in China" (or outside, except, excluding, ex-) reads `UNKNOWN`. An undated landscape "available" cell is not counted at all; an analyst-asserted statement with a citation still is. | `test_f1_…` (5), workspace test |
| 5 | Uncited acquisitions and exercises (§3d) | **Fixed.** Acquisitions that move a grant, and exercises (whole or partial), are cited with the grant and count for staleness. FL-301 now cites rows 16 and 17 in the JSON, workbook and memo. | `test_g5_…`, `test_m1_…`, `test_m3_…`, `test_k5_…` |
| 6 | Holder logic (G4, G3, G2) | **Fixed.** An acquisition that makes licensor and licensee one company ends the grant: `OWNER_ACQUIRED` (G4). A sublicensee's head licensee is a named holder, with a consent question, and counts for the holder preference (G3). A grant with an unreadable territory is named beside the deciding grant, with a question (G2). | `test_g4_…`, `test_g3_…`, `test_g2_…` |
| 7 | Output gaps (§4) | **Fixed.** See section 3. | section 3 |
| 8 | Returns with no recorded grant read `NO_RIGHTS_EVIDENCE` (K1); linked outcomes give false conflicts (D5, D6) | **Fixed.** A return or termination recorded without its grant is read as it would be with its grant: no territory written ends the whole deal; a readable territory over the buyer's ends it there. Either is `RIGHTS_RETURNED`, with a question naming the parties and the missing grant (K1, K2). One for other territories, or an unreadable one, stays a question. Deal-id-linked outcomes and option outcomes follow their grant by definition (D5, D6). | `test_k1_…`, `test_k2_…` (3), `test_d5_d6_…` |
| 9 | LM-302 still CONFLICTING; recall capped by the library | **Not fixed.** Both depend on evidence the frozen library does not hold (see section 5). |  — |

The re-review's "single highest-value fix", a promotion guard, is `CLEAR_POSITIONS` plus the checks above: territory
readable or absent, live status, unambiguous match, valid buyer territory, no rejected row, no contradicting field.

## 2. Judgement calls (REREVIEW §3d) and AC6

| Case | Revision 2 | Revision 3 | Why |
|---|---|---|---|
| D4: license dated only by a 2025-03 filing; termination 2024-05 | LICENSED, "ending an earlier deal not in the evidence" | CONFLICTING: "may predate the grant (reported 2025-03): the dates cannot order them" | A report date bounds a grant from above only. A grant with no event date of its own now exists from the start of the replay; an ending before its report cannot be ordered. A deal-id-linked ending still applies, and an ending after the report still clears. |
| S1: 2015 return, as of 2025-06 | RETURNED, tier 1, stale | RETURNED, **tier `RIGHTS_UNRESOLVED`**, stale, reason "stale evidence does not show the current position" | AC7 already refuses a stale availability statement. The same rule now applies to every clear position. The buyer sets the age (`max_evidence_age_days`). |
| S2: license 2016, option 2025 over the US | LICENSED, stale=False | CONFLICTING (AC6). The 2016 license is named: "the newest evidence for the license to Alpha Bio is dated 2016-01-01 … it may have ended since", with "Is it still in force?" | Any active grant over the territory whose own evidence is old is named, in a conflict or beside a fresh deciding grant. The outcome that creates a conflict counts for the conflict's staleness. |
| G1 / AC6: exclusive license or option to different parties | option named beside the license | CONFLICTING | AC6's own example. A co-promotion option is not over the rights themselves, so it is named and asked about, not a conflict. |
| K6: co-development ended by one partner | "grant to Alpha Bio ended" | "co-development between Alpha Bio and Beta Bio ended", no holder claimed, "owner not established" | Both partners named; no owner invented. |

## 3. Output honesty (REREVIEW §4)

- **Quotes** are clipped with an ellipsis, never silently: up to 1,000 characters in the workbook, 200 in the memo.
  IBI343's cell now ends "...IBI363 and IBI343, worldwide outside of Greater China." (`test_quotes_are_clipped_…`)
- **Evidence ids.** Workbook evidence lines start with the rights row and end with the event id. Memo evidence
  bullets give the rights row and the quote, and say how many rows are not shown (`test_workbook_evidence_…`,
  `test_memo_says_how_many_…`).
- **Words, not codes, in memo prose.** Tiers and positions are written out ("rights unresolved; rights position:
  conflicting evidence"). Codes stay in the JSON and the workbook. The duplicated stale note is gone: the position
  says "(stale evidence)", the reason gives the date, and the question asks. The "also exists" line now gives
  each program's position in words, its stale flag and its rights rows (`test_memo_lines_…`).
- **Memo line 9** ("Nothing is shown as available without an explicit, dated statement") is now enforced by the F1
  and S1 rules, not only true of this run.
- **Screening column** renamed "U.S.-rights field in the landscape, as read (not rights evidence; independent of
  science)", so it no longer reads as a second rights answer.
- `rights_position.py` was split: wording helpers moved to `rights_words.py` (file limit 800 lines).

## 4. The reviewer's adversarial cases, re-run on revision 3

35 distinct cases from `adv2.py`–`adv5.py`. Each meets the reviewer's expected value. For the four judgement
cases (D4, D7, S1, K6), the conservative reading was taken. No case reaches a top tier that the reviewer said
should not.

| Group | Cases | Revision 3 |
|---|---|---|
| Dates (D1–D7) | 7 | D1–D3 LICENSED (not top tier); D4 CONFLICTING; D5 RETURNED; D6 NOT_ENCUMBERED (lapsed); D7 RETURNED, stale, so `RIGHTS_UNRESOLVED` |
| Outcome territories (U1, U1b, U2, U3) | 4 | LICENSED / LICENSED / OPTION_HELD / LICENSED, each with a territory question |
| Availability (A1, A1b, A2, A2b, A3) | 5 | none counted; A3 RETURNED |
| Holders (G1–G5, M2) | 6 | G1 CONFLICTING; G2 BigPharma named + question; G3 head licensee named, DEPRIORITIZED; G4 OWNER_ACQUIRED; G5 acquisition cited; M2 both named, DEPRIORITIZED |
| No grant recorded (K1, K2) | 2 | RETURNED, with the missing-grant question |
| Partial exercise (K5), exercise (M3), chain (M1) | 3 | option kept for the US, exercise cited, not stale; license cited, not stale; RETURNED, 4 rows cited |
| Staleness (S1, S2) | 2 | see section 2 |
| Buyer territory (B1 ×3) | 3 | validation error |
| Other (K3, K4, K6) | 3 | AVAILABILITY_STATED (accepted by reviewer); NOT_ENCUMBERED by design; K6 as section 2 |

## 5. Measured result on CLDN18.2

Revision 3 versus revision 2: **2 programs changed**, and neither tier changed. FL-301 now cites the acquisition
row behind its holder (rows 16 and 17). LM-302 gains "the newest evidence for the license to Turning Point
Therapeutics is dated 2022-08 … it may have ended since", with "Is it still in force?". Tiers among the 14 eligible
programs: rights unresolved 8, deprioritized 6 (unchanged).

| Error class (vs reference) | Baseline | R1 | Revision 2 | Revision 3 |
|---|---|---|---|---|
| False "unobstructed" (third-party U.S. rights shown OPEN or in a top tier) | 4 definite + zanidatamab | 0 | 0 | **0** |
| False encumbrance | 0 | 0 definite, 2 likely outdated | same | same (EO-3021, SYSA1801; stale-flagged) |
| Wrong holder | n/a | 3 | 1, labelled (LM-302) | 1, labelled (LM-302) |
| Wrong territory reading | n/a | 1 | 0 | 0 |
| Missed return | n/a | 1 (SKB315) | 1 | 1 |
| Re-review findings still failing (REREVIEW §3a–3d, judgement calls excluded) | n/a | n/a | 23 (12 of them paths into a top tier) | **0** (each has a held-out test) |

Usefulness against general Claude (B) on the 15 deal programs (REREVIEW §5) is **unchanged: 10 right, 4 partial,
1 missed, versus B's 14, 1, 0.** Revision 3 closes held-out failure paths; it adds no recall. B is still better on
recall (SKB315, LM-302's return, EO-3021's discontinuation, the twin's holder for sonesitatug vedotin). DealScreen
is still better on audit: every call cites a row, quote, file hash and date; staleness is explicit; it never turns
"no record" into "unencumbered". This does not show a competitive advantage. The comparison is AI-simulated and
uses one landscape.

Not fixed, and why:
- **LM-302** stays CONFLICTING: no library quote states that Bristol Myers Squibb succeeded Turning Point. One sourced
  acquisition row would make it RETURNED (`test_m1_…`); inventing it is not allowed.
- **SKB315** stays NO_RIGHTS_EVIDENCE: the return is not in the library. With a sourced return row it would now read
  RETURNED (K1).
- **EO-3021 / SYSA1801** read LICENSED, stale-flagged. The discontinuation is not in the library.
- **A twin's evidence** (AZD0901 → sonesitatug vedotin, XNW27011 → ASP546C) is not carried across an identity flag.
  Carrying it needs a human-confirmed identity decision.
- **"Worldwide (exclusive)"** reads as an unstated territory (conservative; named and asked about).

## 6. Regression checks

- Science unchanged: 0 of 62 CLDN18.2 scientific fields changed versus the frozen baseline (`compare.py`).
  Cross-version (the reviewer's `cross_version.py`, pre-R1 0ee7752 vs revision 3): synthetic 200 (192 assets),
  FcRn v1 (40), FcRn v2 (40) and C5 held-out (40) each show 0 scientific changes.
- Cycle-4 equivalence harness: byte-identical on all four workspaces (synthetic 200, real v1, real v2, real v1
  with cycle-1 assertions).
- `tests/dealscreen`: all pass (count in the commit). `ruff check src/bve/dealscreen tests/dealscreen`: clean.
- No file outside `src/bve/dealscreen/` changed in `src/`; valuation code is untouched.
- Full repository suite: 17,044 passed, 13 failed, 17 skipped, 3 xfailed (1 h 26 min; `tests/test_api.py` and `tests/test_ui_pages.py` are excluded because FastAPI is not installed). The 13 failures are the same 13 as the revision-2 run and none is in DealScreen code: two were confirmed failing at 0ee7752, before R1 (the architecture contract does not map `dealscreen`, a governance item; the S&E release-closure check). The other 11 are in modules R1 does not touch: FastAPI missing in `test_api_knowledge_fallback.py` (2), PDCD1 archive artifacts not on disk (6), sprint-47 buyer-thesis tiers (3).
- Repo-wide `ruff check src/` with ruff 0.17.1 reports 7,568 findings in files this cycle did not touch (rules the
  repository does not select, from ruff's newer defaults). Not changed here.
