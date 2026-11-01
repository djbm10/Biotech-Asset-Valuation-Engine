# Response to the R1 adversarial re-review 3 (REREVIEW3.md): revision 5

Revision 5 is the uncommitted working tree on `dealscreen-mvp` as of 2026-11-01. Nobody has reviewed it yet. This
file is the implementer's account, not a review: every claim below should be checked by running code.

## 1. The highest-value fix: one fail-closed gate on every path

REREVIEW3 section 13 asked for one rule that every tier-0 or tier-1 candidate passes, on the rights-file path and the
landscape/analyst path alike, where anything not understood blocks. Revision 5 implements its four parts.

1. **Ended grants are checked beside a statement** (`rights_position._decide`, `_ended_beside_statement`). When an
   availability statement decides the position, every grant that ever covered the buyer territory still passes the
   returned-path checks. An ending that names only the licensor and is not linked by deal id, an undated ending, an
   undated grant, a grant naming no licensee, or an undated acquisition that merged the grant blocks. An ending not
   dated before every statement blocks too (a statement made while the grant was in force may not describe the
   rights now).
2. **The position must rest on the landscape company** (`rights_checks._owner_check`, `rights_position._available`,
   the return-only rule). The licensor a clear position rests on, the party that made an availability statement and
   the recipient of a return must be the program's company per the landscape, compared by name
   (`rights_model._is_company`, which follows recorded acquisitions). Otherwise the position is blocked
   ("specific: … may hold the rights under a license") and the question asks "Does X own this program, or hold it
   under a license from Y?". A statement by another party never names an owner or holder.
3. **Every U.S.-rights statement and holder is read** (`rights_gate.reconcile`, both paths). All landscape cells
   and analyst assertions that were not rejected are read, not only the one the status came from
   (`CommercialAssessment.us_rights_all`, `us_rights_holder_all`). A contrary statement makes the position
   CONFLICTING and is cited and quoted. A statement the reader cannot fully read blocks ("uncontested: … cannot read
   as a rights statement; it may name a third-party holder, a condition or another place"). An offer made by a named
   party other than the company blocks. A holder written with a note ("Origin Bio (U.S. rights licensed to BigPharma
   Inc.)") blocks: the note is content and is not read. A holder who is neither the company nor the owner makes the
   position CONFLICTING. Statements dated after the as-of date are not applied and are named.
4. **Rows that were not applied guard the programs they may concern** (`rights_gate.row_guards`, `guards_for`). A
   rejected row whose program id matches no program, or names none, keeps every program out of tiers 0 and 1. A row,
   rejected or accepted, whose id is close to a program's id ("CL 24", "CL-041" beside "CL-24", "CL-41"; case,
   spaces, punctuation and leading zeros ignored) keeps that program out. Each such row is named once per program,
   in its most specific reason, and is listed with its parties and territory in the JSON, the memo and the workbook.

The U.S.-rights text reader was rewritten to be strict (`rights_reader.py`). A statement is split into clauses (";",
". ", "but", "however", "whereas", "although"). Each clause is read as an offer, a contest (not available, licensed,
optioned, returned), consistent text, or unread. A statement reads AVAILABLE only when every clause is read and one
offers rights in a place that covers the U.S.; an unread clause beside an offer makes it UNKNOWN and not understood.
Negations ("No U.S. rights available", "Available - no", "Available: N"), other places ("Available in Latin
America"), hedges, future and questions ("May be available", "Available from 2027", "Available?") never read as
availability. The offering party is taken from a capitalized subject ("Acme Bio is seeking a partner …").

The per-program step of screening is now one public function, `screening.program_transaction`, so the held-out tests
run the production path rather than a copy of it.

## 2. The findings

| § | Case | Revision 5 | Tests (`test_rights_rereview3.py`) |
|---|---|---|---|
| 2a | A1a, A1b, A1c, A1e: ended grant beside a statement | RIGHTS_UNRESOLVED, each blocked by the check the returned path applies ("names only the licensor and is not linked to its deal by id"; "has no date of its own"; "has no date, so its ending cannot be ordered against it"; "names no licensee"). The grant and its ending are cited beside the statement. | `test_a1_…` (5) |
| 2a | A1d (judgement) | Decided: an undated acquisition that merged the grant blocks beside a statement as it does on the returned path. | `test_a1_…[A1d]` |
| 2a | A2a, A2b, A2c: statement by BigPharma Inc / Kappa Pharma | RIGHTS_UNRESOLVED; holder and owner not set from the statement; "stated by X, which the landscape does not name as the program's company"; question "Does X own this program, or hold it under a license from Origin Bio?". | `test_a2_…` (3) |
| 2a | A3a: analyst "Available" + analyst holder BigPharma Inc. | CONFLICTING on the field path; the holder is named with its real source ("an analyst assertion names …"), cited once, and the plain "holder or labeler" line is replaced by the conflict. | `test_a3a_…` |
| 2a | A3b: conflicting landscape holders | CONFLICTING; "the position rests on an analyst assertion's statement (…), and no rights record shows a grant to BigPharma Inc.". | `test_a3b_…` |
| 2a | A3c: analyst statement dated after the as-of date | Not counted: "is dated 2026-01-01, after the as-of date 2025-06-01, so it is not counted". | `test_a3c_…` |
| 2a | A3d, A3e (judgement) | Decided: every statement is read, so a contrary one makes the position CONFLICTING whatever the entry order. Both statements are cited; the question names both and says "Reject the one that is wrong". | `test_a3d_a3e_…` (2) |
| 2a | T: seven analyst phrasings | None reaches tier 0. "No U.S. rights available" and "Available - no" read NOT_AVAILABLE; the rest are not read and leave no rights evidence. Each statement is cited. `assert` now prints how it read a U.S.-rights statement. | `test_t_…` (8) |
| 2a | A7a (judgement) | Decided: a statement covering part of the buyer territory blocks ("covers only part of CA/US"). | `test_a7a_…` |
| 2b | A4: nine landscape cells naming BigPharma Inc. beside a China license | RIGHTS_UNRESOLVED and the cell cited: CONFLICTING for the four the reader reads as a grant; blocked "cannot read as a rights statement" for the five it cannot read. | `test_a4_…` (9) |
| 2b | A5a, A5b: note beside the company name | Blocked; the note is quoted; question "Does the note '…' that the landscape writes beside Origin Bio mean that a third party holds U.S. rights?". | `test_a5_…` (2) |
| 2b | H2, H1: licensor not the landscape company | Blocked ("the owner per the rights evidence is Kappa Pharma, but the landscape names Origin Bio as the program's company"), with the ownership question. | `test_h1_h2_…` (2) |
| 2b | T2: "No U.S. rights available" beside a China license (analyst and cell) | CONFLICTING, the statement cited. | `test_t2_…` (2) |
| 2b | A6 (judgement) | Decided: every holder is read, so the landscape's BigPharma Inc. makes the position CONFLICTING despite an undated analyst holder. | `test_a6_…` |
| 2b | C2 (judgement) | Kept: "Origin Bio China" is the company's affiliate (country words are business-line words). | — |
| 2b | O8 (judgement) | Kept: a termination dated before the as-of date counts even if reported after it. | — |
| 2c | ws_e, ws_f, ws_h, re_ws_b | All 13 flagged top-tier placements are out (section 4). | workspace re-runs |
| 3 | Reader groups (57 phrasings) | Other places, rest of world, hedges, encumbered wording and third-party wording never read AVAILABLE; negations read NOT_AVAILABLE; FE offers read AVAILABLE and non-U.S. grants never read as a U.S. encumbrance. Residual: "Option available to partners" is not read, so it blocks (usefulness cost). | `test_reader_…` (59) |
| 4 | Names | One word list (`GENERIC_NAME_WORDS`) for every comparison; "U.S." and "U.S.A." read as "us"/"usa" (G10, G11); notes are content (`split_note`). New: an address written after the corporate form is not part of the name ("Acme Bio Co., Ltd., Lakeside, China" = "Acme Bio") when every tail item is one word and the last is a country the territory reader knows; a second party is never cut off. | `test_names_…` (11) |
| 5 | C1, G17 | Kept as usefulness costs: "Origin Bio" is neither "Origin Biotherapeutics" nor "Origin Biosciences" by name alone, so a program whose rights rows use the short form is held with the ownership question. G17 is new in revision 5 (the owner check). | `test_judgements_kept_…` |
| 5 | C4 / O-12 | The successor question no longer names one party twice. | `test_o12_…` |
| 6 | R-lost | Fixed: a rejected row whose id matches no program is listed (`unattributed_rejected_rows`, now "Rejected rights rows not attached to any program" in the memo and `RIGHTS_ROW_REJECTED_NO_PROGRAM` with the id in the workbook) and keeps every program out of tiers 0 and 1. | `test_r_lost_…` |
| 6 | Unattached accepted row (judgement) | Decided: it keeps a program whose id is close to its own out of tiers 0 and 1, with the question "Is rights row N (program id 'X') about this program?". | `test_near_match_…`, `test_a_rejected_row_close_…` |
| 7 | FE G12, G13, FE cells | G12 tier 1; G13 tier 0; "Licensed in China only", "Available for exclusive licensing", "Seeking a co-development partner" in the landscape are no longer a U.S. license (a vendor offer is still not counted). | `test_g12_…`, `test_g13_…`, `test_fe_…` (3) |
| 8 | G5b, G6, G8, G10, G11 | Tier 1: a dated return is not discarded as a repeat of a status flag; an old grant in another territory does not make the U.S. position stale; a co-development ended by both leaves the program with the company that was a partner; the company's U.S. affiliate is the company. | `test_over_caution_…` (5) |
| 8 | G5 (judgement) | Kept: a status flag on a 2021 deal says it ended, not when; stale. | `test_judgements_kept_…` |
| 9 | O-1 | A1a's reasons say which grant ended, and the blocker names the record. | `test_a1_…` |
| 9 | O-2 | ATG-022's owner is not set from a statement by another party. | `test_a2_…` |
| 9 | O-3 | A holder is named with the source it came from and cited. | `test_a3a_…` |
| 9 | O-4, O-5 | VBC108 blocked by its note; TORL asks whether Kappa owns the program or holds a license. | `test_a5_…`, `test_h1_h2_…` |
| 9 | O-6, O-7 | Reader: the cells now read as written; one analyst statement gives one reading. | `test_reader_…`, `test_t_…` |
| 9 | O-8 | The memo's availability sentence is computed: "None reaches the availability position" (with "a vendor field reading "available" is unverified and not counted" when one does), or the count of programs with availability stated and how many pass every rights check. | `test_o8_o13_…` |
| 9 | O-9 | Unattached and rejected rows are listed with type, date, parties, territory and the program whose id is close; the workbook row carries the same and names the program held back. | `test_r_lost_…`, `test_near_match_…` |
| 9 | O-10 | = R-lost. | |
| 9 | O-11 | The "also exists" line shows the first position reason, the first top-tier blocker and "(and N more reason(s) in the workbook)". | `test_o11_…` |
| 9 | O-13 | Words, not codes: positions and tiers in words with counts in parentheses; gates as "gates lacking evidence: indication (24), modality (8) …"; the funnel labels cover every gate id the gate engine produces. | `test_o8_o13_…` |
| 9 | O-14 | The blockers column also lists the rights rows not applied that may concern the program ("complete: …"); the field path now has the gate's blockers. | `test_a_guard_…` |

## 3. Found during revision 5 (not in REREVIEW3)

- Rows not applied were reported in the memo only when transaction preferences were declared; they are now always
  reported. The guard reasons are now stored on every program (`rights_rows_not_applied`), whatever its position.
- A finalist line showed the landscape's U.S.-rights field even when rights rows exist for the program; it now shows
  the rights-file position.
- On the field path, a holder conflict said "the rights evidence records no third-party grant" for a program with
  no rights rows; it now names the statement the position rests on. A conflicting statement's question named "the
  rights evidence" there too; it now names both statements.
- The "not counted" reason for an analyst statement listed three possible causes; it now names the one that applies.
- A statement-by-another-party blocker read "a statement naming BigPharma Inc is made by BigPharma Inc"; reworded.
- Real legal names with an address after the corporate form were split from their short name (the reviewer's ws_e
  LB4330 row). The address rule above fixes it without any landscape name in the code (AC12).

## 4. Measured result

| Check | Result |
|---|---|
| Tests | `tests/dealscreen`: 653 pass (512 at revision 4; 141 new in `test_rights_rereview3.py`). `ruff` and `mypy` clean on `bve.dealscreen` (31 files). Six earlier tests were edited, each for a stated rule: five now name the program's landscape company as the licensor instead of an unrelated party (rule 2), and two memo-wording assertions changed (the "not counted" reason and the rejected-rows heading). |
| Review's per-program cases (sections 2, 5, 7, 8) | Run through `program_transaction`: every section 2a and 2b case is out of tiers 0 and 1. Of the 23 clean or over-caution cases the review expects in a top tier (G1, G1b, G2–G4, G5b, G6–G18, G18b, G18c, K1, K3), 22 reach it; G17 is held (a new usefulness cost of rule 2). Also held: G5 (judgement kept) and C1 (kept). |
| Review's workspaces, re-screened from copies on this tree | Flagged top-tier placements 13 → 0: ws_e 7 → 0, ws_f 2 → 0, ws_h 3 → 0, re_ws_b 1 → 0. ws_g, re_ws_a, re_ws_c, re_ws_c2, re_ws_d, re_ws_d2 and re_ws_nr had none and have none. In ws_e each program is held by its own check, not only by the rejected row that guards all programs: QLS31905 (A1a), ATG-022 (A2a), SKB315 (A3a, CONFLICTING), TORL-2-307-ADC (H2), VBC108 (A5), JS107 (near-match row 23), LB4330 (near-match rejected row 27). |
| CLDN18.2 (`after_v5/`) | No tier, position, rank, holder or staleness changed from revision 4: eligible 8 rights unresolved, 6 deprioritized; none in tier 0 or 1. Reasons changed for Zolbetuximab only: its landscape labeler cell carries a note, which is now named and asked about (tier unchanged: excluded by buyer preference as marketed). Memo 1,609 → 1,701 words (summary sentences in words, the computed availability sentence, the "also exists" counts). |
| Science | 0 of 62 CLDN18.2 scientific fields changed against the frozen baseline. Cross-version against pre-R1 0ee7752 (`cross_version.py`): 0 scientific differences on 312 assets (synthetic 192, FcRn v1 40, FcRn v2 40, C5 40). Cycle-4 equivalence: byte-identical, fast path, on all four. |
| Usefulness against general Claude (B) | Unchanged: no CLDN18.2 call changed. 10 right / 4 partial / 1 missed against B's 14 / 1 / 0 on the 15 deal programs. No advantage is demonstrated. |

## 5. Acceptance criteria, as the implementer reads them (not a review)

| AC | Revision 4 (REREVIEW3) | Revision 5, implementer's reading |
|---|---|---|
| AC1, AC8, AC9, AC12 | PASS | unchanged; AC12: no CLDN18.2 name added to `src/` (the address rule uses the territory reader's country list) |
| AC2 no "available" without a dated, current statement | FAIL (A1–A3, T) | the held-out A1–A3, A7a and T inputs no longer reach tier 0 |
| AC3 territory | PARTIAL | A7a decided; FE non-U.S. grants no longer a U.S. encumbrance |
| AC4 returns | PARTIAL | A1 ended-grant checks beside a statement; G5b, G8 fixed; LM-302 still not RETURNED (data) |
| AC5 options | PARTIAL | unchanged |
| AC6 conflicts | FAIL (A4, A5, T2, H2) | every statement and holder is read on both paths |
| AC7 staleness | PARTIAL | A3c and G6 fixed; G5 judgement kept |
| AC10 evidence shown | PARTIAL | R-lost and A4 cells cited; unattached rows with parties; "also exists" line counts what it omits; still no quotes in that line |
| AC11 questions | PARTIAL | O-12 fixed; ownership questions for H1, H2, A2 |
| AC13 the named programs | PARTIAL | unchanged: LM-302 CONFLICTING, not returned |
| AC14 no new errors | FAIL | cannot be self-certified: needs a fresh adversarial review |

## 6. Remaining issues, ranked

1. **Recall is capped by the rights file** (unchanged): LM-302's successor, SKB315's return, EO-3021's
   discontinuation. General Claude still leads on recall (14 / 1 / 0 against 10 / 4 / 1).
2. **Name matching costs usefulness in both directions.** Near-namesakes are held with a question (C1, G17), and a
   legal name that starts with a place ("<Province> <Name> … Co., Ltd." against "<Name>") does not match. A short
   name followed only by business-line words still merges ("Origin" = "Origin Therapeutics"), which the review
   rated a possible false merge. The safe next step is analyst-declared company aliases, recorded as cited decisions,
   not inferred.
3. **Reader residuals.** "Option available to partners" is not read and blocks. Holder notes are never read, so a
   labeler note (Zolbetuximab) produces a question.
4. **Judgements kept:** G5 (status flag with no termination date is stale), O8 (report after the as-of date), C2.
