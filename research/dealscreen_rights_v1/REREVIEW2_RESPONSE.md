# Response to the R1 adversarial re-review 2 (REREVIEW2.md): revision 4

INTERNAL DEVELOPMENT. Written by the implementer, not the reviewer. It claims nothing about whether the fixes are
adequate, and it is not validation. AI-simulated measurement only. **Revision 4 has not been reviewed by a separate
context.** Each earlier round found new paths into a top tier that the implementer had missed, so every number below
is the implementer's own and needs the same independent check.

Revision 4 is on `dealscreen-mvp` after e805f0b. Every input in REREVIEW2 §2 and §3 is a held-out test with fictional
parties in `tests/dealscreen/test_rights_rereview2.py` (69 tests in 40 functions), named by the review's case id.
The reviewer's own scripts (`adv_top.py`, `adv_ledger.py`, `adv_order.py`, `adv_coarse.py`, `adv_field.py`, and the
previous reviewer's `adv2.py`–`adv5.py`) were re-run unchanged. Outputs were regenerated in `after_v4/`.

## 1. The highest-value fix: tiers 0 and 1 are an allow-list

REREVIEW2 §7 asked that a program enter AVAILABILITY_STATED_UNVERIFIED or NO_THIRD_PARTY_GRANT_IN_EVIDENCE only if
four checks pass, decided once from the records the position rests on. Revision 4 does this.

- Every clear position (returned, not encumbered, owner acquired, availability stated) carries
  `top_tier_blockers`, each written `check: detail`. The transaction view admits a clear position to tier 0 or 1
  only with no blocker, no guard (a rejected rights row) and no stale flag. Otherwise it is RIGHTS_UNRESOLVED, with
  the reason "not counted for the top tiers: …" and the question "What record would make this rights evidence
  {checks}? …". The blockers are in the JSON (`transaction.top_tier_blockers`), the workbook Screening sheet and the
  memo reasons.
- **Complete.** Every outcome is attached and explained. Ambiguous, unordered, misdated or unreadable outcomes, an
  outcome that matches no grant, an acquisition that could not be applied, and an acquisition with nothing else
  recorded all block. One exception, found during this revision (section 3): an ending that meets the
  return-only standard below and returns the rights to the program's company is explained.
- **Specific.** The grants a position rests on name licensor and licensee. An ending that names only the licensor
  counts only when it is linked to its deal by id. A return or termination recorded without its grant counts only
  when it names both parties, states a territory covering the buyer's, and returns the rights to the program's company
  per the landscape. The current holder must be established.
- **Current.** Each record the position rests on (`ledger.deciding`) is judged on its own date: the event date,
  else the date of the report that records it, at the start of its period. It must be within the buyer's age limit
  on the as-of date. Acquisitions and later reports never refresh it. Undated never qualifies, and without an as-of
  date nothing qualifies. One ordering rule for licenses and options: an outcome follows its grant by definition
  only when linked by deal id. Records dated after the as-of date are not applied.
- **Uncontested** (in `screening.py`). A landscape or analyst U.S.-rights statement that disagrees, or a named U.S.
  holder that is not the owner or holder per the evidence, makes the position CONFLICTING_EVIDENCE. Analyst text is
  read with the same negation, place and tense rules as the landscape cell. An analyst availability statement counts
  only with a source date within the age limit, and is cited.

## 2. The findings

| § | Case | Revision 4 | Tests |
|---|---|---|---|
| 2a | N1a, N1b, N1c: a grant naming no licensee | Held by "a licensee not named": LICENSED / OPTION_HELD / SHARED; never merged with its licensor. The question says the record names no licensee. | `test_n1a_…`, `test_n1b_n1c_…` |
| 2a | N1d: intra-group license | Judgement kept (tier 1). The reason now says the grant "is within one company as written", not "do not cover". | `test_n1d_…` |
| 2a | N3a: acquisition limited to Greater China | Acquisitions apply only over the territory they state. One naming one party, or covering an unreadable, partial or other territory, is not applied; it is named, cited and blocks (complete). LICENSED to Alpha. | `test_n3a_…` |
| 2a | R1, R1b: option dated by its report, earlier lapse | One ordering rule for licenses and options: CONFLICTING. | `test_r1_…` (2) |
| 2b | E2-holder | CONFLICTING. The reason names the source ("an analyst assertion names BigPharma Inc. as the U.S. rights holder"), the question names BigPharma, and the claim is cited. Companies are compared by name with only business-line and country words and notes in parentheses ignored, so "Acme" is not "Acme KGaA" (section 3). | `test_e2_holder_…` (4, one end to end) |
| 2b | E3-ids (a), (b) | Program ids match without regard to case or spaces. Accepted rows that attach to no program are listed in the JSON (`rights_import_issues.unlinked_rows`), the memo and the workbook Diligence sheet (`RIGHTS_ROW_NOT_ATTACHED`). A rejected row that names no program keeps every program out of tiers 0 and 1, with the row named. | `test_e3_ids_…` (2, end to end) |
| 2b | F1-analyst | "Available for licensing: no" and "Available? No." read NOT_AVAILABLE; "but not in the U.S.", "Ex-U.S.", "China rights available", "was available until", "previously available" read UNKNOWN. An analyst-asserted or -confirmed AVAILABLE counts only with a source date within the age limit; it is cited as evidence in the JSON, workbook and memo. Otherwise "not counted". | `test_f1_…` (10 phrases, 3 dates, 1 end to end) |
| 2b | N6a, N6b, N6c | Statements are judged on their own dates. An undated statement never counts, and a statement that was not counted or was superseded no longer makes the position current. N6c is RETURNED (the A3 rule). | `test_n6_…` |
| 2b | N7b, N7c | Acquisitions never refresh age. Stale, RIGHTS_UNRESOLVED, blocked "current". | `test_n7b_n7c_…` (2) |
| 2b | N8a, N8b | A co-development ended by one partner stays SHARED: "whether Alpha Bio now holds all US rights is not in the evidence", with a question. | `test_n8_…` |
| 2c | N2a, N2b, H1 | An exercise with no recorded option is evidence of a license: CONFLICTING, "Beta Pharma may hold US rights through it". | `test_n2_h1_…` |
| 2c | N7a | The event date wins over a later report: the 2015 statement is not counted. | `test_n7a_…` |
| 2c | N10 | Records dated after the as-of date are not applied; they are named and cited. | `test_n10_…` |
| 2d | N4a–N4c | RETURNED, not top tier (specific: parties or territory missing). | `test_n4_…` (3) |
| 2d | N4d | RETURNED. Counts for the top tiers only when the recipient is the program's company per the landscape; otherwise the owner is not established and a question asks whether Kappa owns the program or holds it under a license. | `test_n4d_…` |
| 2d | N4f, N5a–N5c, N9a, N9b | Not top tier (current: undated). | `test_n4f_n5_n9_…` (6) |
| 2d | N3c | OWNER_ACQUIRED, not top tier (complete: "only an acquisition is recorded"). | `test_n3c_…` |
| 2d | N9c | Not top tier unless the ending is linked to the deal by id. | `test_n9c_…` |
| 2d | H7 | Judgement kept: "Holdings" is a corporate suffix, so licensor and licensee merge. | `test_h7_…` |
| 2d | N11 | Not top tier (current: no as-of date). | `test_n11_…` |
| 3 | P1 (E2, E7, E8, E1-JP, E3-JP) | The license split from an option by a partial exercise has its own identity (a parent link). Option outcomes never apply to it; a deal-id-linked termination does. A later lapse ends the rest of the option. | `test_p1_…` (2) |
| 3 | N3b | An acquisition outside the buyer territory does not change the U.S. owner: NO_RIGHTS_EVIDENCE, owner None. | `test_n3b_…` |
| 3 | Negated words | "Not licensed", "Never partnered", "Not optioned" are not an encumbrance and create no conflict. | `test_negated_…` (4) |
| 3 | NA-label | NOT_AVAILABLE_PER_SOURCE, worded "not available per source", governed by the buyer's `encumbered_rights`. | `test_na_label_…` |
| 3 | W1, N7e | A fresh re-license is current and the older one is not flagged; an acquisition does not make an old license current. | `test_w1_…`, `test_n7e_…` |
| 3 | H6, H3/N7c, H5 | Every acquisition in a chain is named; "grant to Alpha Bio (now Gamma Corp) ended"; an EXPIRED option is a lapse. | `test_h6_…`, `test_h3_…`, `test_h5_…` |
| 3 | Memo "no effect" | Rights assertions are listed as feeding the transaction view, with each program's tier in words. | `test_f1_analyst_availability_…` |
| 3 | Originator note | Names only the recipient: "rights returned per source to Kappa Pharma". | `test_n4d_…` |

Output honesty (REREVIEW2 §4):
- N1's reason no longer contradicts its evidence (N1a).
- Memo line 9 ("Nothing is shown as available without an explicit, dated statement") is now enforced: only a dated,
  current statement counts (N6, N7a, F1-analyst).
- Analyst tier-0 entries carry their citation in the JSON, workbook and memo.
- Codes in prose are replaced with words ("the U.S.-rights field reads: not available (source-provided)").
- The memo's "Rights evidence also exists for …" line now gives each program's newest evidence date and the reason
  for its position (not a buyer-preference match), with its rows. It still gives no quote or URL; those are in the
  workbook, to keep the memo bounded (`test_ac10_…`).

## 3. Found during revision 4 (not in REREVIEW2)

- **Holder names matched too loosely.** The new holder check first compared names by whole-word containment, so
  "Acme" matched "Acme KGaA" and a namesake's U.S. claim would have been absorbed. `same_company` now ignores only
  business-line and country words (pharma, bio, US, Japan, …) and notes in parentheses: "Acme" and "Acme Pharma US,
  Inc. (U.S. labeler …)" are one company; "Acme" and "Acme KGaA" are not.
- **Returned, then offered (REREVIEW K3).** An owner's fresh statement beside a return recorded without its grant
  was held back as "incomplete", so the most useful BD pattern could not reach tier 0 unless the original grant was
  also in the file. The return is now explained when it meets the return-only standard and returns the rights to the
  program's company (`test_k3_…`). Without a program company (a direct caller) it still blocks.
- **Wording.** The landscape "available" cell was described as "undated" while its evidence line showed the row's
  date; it now says "a vendor field is unverified, so it is not counted".
- **Code health.** `rights_position.py` had grown to 1,066 lines. The event replay moved to `rights_ledger.py`
  (368 lines); `rights_position.py` is 750. mypy reported 40 errors in the R1 modules; all 27 `bve.dealscreen`
  modules are now clean.

## 4. Measured result

| Check | Result |
|---|---|
| Tests | `tests/dealscreen` 512 collected, all pass (443 at revision 3). `ruff` and `mypy` clean on `bve.dealscreen`. |
| Reviewer's scripts, re-run unchanged | Every definite case meets its expected value. Tiers 0/1 are reached only by cases the reviewers listed as expected or accepted (C2, C4, C5, E1-JP, E2, E7, E8, H3–H7, N1d, N6c, R6–R8, D5, A3, G4, K4). Five results the reviewers accepted in a top tier are now held back, all in the conservative direction: K1 and K3 (no program company to compare in the script; with the company given they reach tier 1 and tier 0), H2 (an ending with no territory written), D6 (the single ordering rule), M1 (a return dated only "2024" is stale). K2 has the N4a shape the reviewer doubted and is held back too. |
| Reviewer's end-to-end workspaces (ws_a–ws_d rebuilt on revision 4) | Top-tier placements the reviewer flagged as errors: 12 → 0 (ws_a 6, ws_b 1, ws_c 3, ws_d 2). One program entered tier 1: JS107 in ws_b, whose analyst text "Not licensed in the U.S." revision 3 misread as an encumbrance (the reviewer's "negated words" false conflict). |
| CLDN18.2 (`after_v4/`) | Tiers unchanged: eligible 8 rights unresolved, 6 deprioritized; none in tier 0 or 1. Two excluded programs changed text: IMAB362 and Zolbetuximab now name the acquisition their stale position rests on and list their blockers; Zolbetuximab's redundant "also names … Astellas Pharma US" note is gone because the labeler is matched as Astellas. The memo's "also exists" line now gives dates and reasons (1,439 → 1,609 words). |
| Science | 0 of 62 CLDN18.2 scientific fields changed against the frozen baseline. Cross-version against pre-R1 0ee7752: 0 scientific differences on 312 assets (synthetic 192, FcRn v1 40, FcRn v2 40, C5 40). Cycle-4 equivalence: byte-identical, fast path, on all four. |
| Usefulness against general Claude (B) | Unchanged: no CLDN18.2 call changed. 10 right / 4 partial / 1 missed against B's 14 / 1 / 0 on the 15 deal programs. No advantage is demonstrated. |

## 5. Acceptance criteria, as the implementer reads them (not a review)

| AC | Revision 3 (REREVIEW2) | Revision 4, implementer's reading |
|---|---|---|
| AC1, AC8, AC9, AC12 | PASS | unchanged |
| AC2 no "available" without a dated, current statement | PARTIAL | the held-out N6, N7a and F1-analyst inputs no longer reach tier 0 |
| AC3 territory | PARTIAL | N1, N3a, N3b fixed |
| AC4 returns | PARTIAL | N8 and H1 fixed; return-only rules stated; LM-302 still not RETURNED (data) |
| AC5 options | PARTIAL | R1, P1, N2 and H5 fixed |
| AC6 conflicts | PARTIAL | E2-holder and N2a fixed; negated words no longer conflict |
| AC7 staleness | PARTIAL | N6, N7a, N7b/c, N7e and W1 fixed; undated clearing evidence never reaches a top tier |
| AC10 evidence shown | PARTIAL | analyst entries cited; unattached and id-less rows in every output; "also exists" line has dates and reasons, still no quotes |
| AC11 questions | PARTIAL | N1, E2-holder, E3-ids and N8 questions fixed; each blocker has a question |
| AC13 the named programs | PARTIAL | unchanged: LM-302 CONFLICTING, not returned |
| AC14 no new errors | FAIL | cannot be self-certified: needs a fresh adversarial review |

## 6. Remaining issues, ranked

1. **Recall is capped by the rights file.** LM-302's successor, SKB315's return and EO-3021's discontinuation are
   not in the frozen library, which is why general Claude still leads on recall. This needs licensed vendor deal
   data or analyst-entered, cited rights rows. It is the highest-value next issue for usefulness, and it is blocked
   on data, not code.
2. **Party identity is by name only.** A subsidiary under a different name, or a vendor's short name for the
   landscape's legal name ("Kelun-Biotech" against "Sichuan Kelun-Biotech Biopharmaceutical Co., Ltd."), creates a
   false conflict or holds a return back, with a question. This errs toward caution. A party alias table would
   remove it.
3. **Revision 4 has not been independently re-reviewed.** Each earlier round found new top-tier paths.
4. **The default age limit.** At 730 days, SKB315's August 2024 return would be stale at the C3 as-of date even
   with perfect evidence. The buyer sets `max_evidence_age_days`.
