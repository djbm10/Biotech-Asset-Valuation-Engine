# Adversarial re-review 3: cycle R1 revision 4, rights evidence (CLDN18.2)

**AI-SIMULATED INTERNAL REVIEW.** I am an AI (Claude) playing a skeptical pharma BD analyst and auditor. I am not a
human reviewer. I approve nothing, and nothing here is validation. I did not trust REREVIEW2_RESPONSE.md. I
re-checked each claim by running code or reading outputs. I report only what I ran or read.

Scope and method:
- Revision 4 is the uncommitted working tree on `dealscreen-mvp` after e805f0b. I recorded the SHA-256 of all 27
  files in `src/bve/dealscreen/` at the start (`/tmp/claude-1000/rr4/sha_start.txt`) and again at the end
  (`sha_end.txt`). No file changed.
- I edited nothing except this file. I did not commit, stash or change git state. Scripts, workspace copies and
  outputs are in `/tmp/claude-1000/rr4/`.
- Per-program cases: `adv_allow.py`, `adv_text.py`, `adv_names.py`, `adv_clean.py`, `adv_oldgrant.py`, `adv_t2.py`
  (outputs `*.v4.out`). `verify_quotes.py` checks that every output quoted below occurs in a saved output. The helper `h4.py` `pipe()` runs one program through the same steps as `screening._transaction`:
  `rights_position` with the landscape company, `_reconcile_with_field` (with the holder contest), the holder note,
  then `assess_transaction`. `v3_compare.py` and `text_v3v4.py` run the same inputs on the revision-3 snapshot, to
  tell new errors from old ones. Defaults: buyer territory {US}, as-of 2025-06-01, max age 730 days,
  `encumbered_rights: deprioritize`, landscape company "Origin Bio".
- End-to-end runs on copies of the revision-4 CLDN18.2 workspace (`~/.cache/rights_v1/after4_ws`; C3 buyer, as-of
  2026-10-29), with `import`, `import-rights`, `assert`, `screen`, `export` and `memo`:
  - `ws_e`: the 17 real rows plus test rows X01–X12 (`rights_e.csv`; X06 has program id `CL 24`; X11 is rejected),
    plus five analyst assertions. Outputs in `out_e/`.
  - `ws_f`: four landscape "US Rights" cells edited (`in_f/landscape_f.csv`) plus China licenses X05 and X12.
    Outputs in `out_f/`.
  - `ws_g`: `ws_f` plus one rejected row with no program id. Outputs in `out_g/`.
  - `ws_h`: three analyst assertions only. Memo in `out_h/`.
  - All test rows and assertions are fictional: "(test)" quotes, `example.test` URLs, fictional counterparties
    (Alpha Bio, BigPharma Inc, ChinaCo, Kappa Pharma). Where a test row names a landscape company as licensor, that
    is only so the row attaches to that program. Nothing here is a fact about a real program.
- The previous reviewers' scripts (`adv_top`, `adv_ledger`, `adv_order`, `adv_coarse`, `adv_field`; `adv2`–`adv5`)
  were re-run unchanged from copies. Their workspaces (`ws_a`–`ws_d`, `ws_c2`, `ws_d2`, `ws_nr`, `ws_t`) were
  re-screened from fresh copies on this tree (`re_ws_*`).
- Checks: `tests/dealscreen`: 512 passed (255 s). `ruff check src/bve/dealscreen`: "All checks passed!".
  `mypy src/bve/dealscreen`: "no issues found in 27 source files". `compare.py` against the frozen baseline: "AC8
  scientific fields changed: 0 of 62", for both `after_v4/screening_R1v4.json` and the after4 workspace. A stricter
  check of every field except `transaction`, `transaction_rank` and `commercial` also found 0 differences.

## Summary

- **CLDN18.2: no tier and no call changed.** Only the IMAB362 and zolbetuximab reasons changed. Error counts
  against the reference are unchanged. Usefulness against general Claude (B) is unchanged: 10 right, 4 partial,
  1 missed, versus B's 14, 1, 0.
- **The response's case results hold.** Every REREVIEW2 input I re-ran gives the result the response states. The
  re-screened reviewer workspaces have no flagged top-tier error left.
- **The allow-list is not total.** Its checks run in full only on the "returned" path. They do not run on the
  grants an availability statement clears (A1), on who made the statement (A2), on the field path (A3), on
  landscape text the reader cannot read (A4), or on a holder whose note is in parentheses (A5). A licensor who is
  not the landscape company becomes the owner with no question (H2). A rejected row with a wrong id vanishes from
  every output (R-lost). Analyst text that says "No U.S. rights available" still reads as availability (T).
- On copies of the CLDN18.2 workspace these put test cases at **#1, #2 and #3 of the transaction view in tier 0**
  (ws_e and ws_h, twice over) and at **#1 in tier 1** (ws_f).
- **Usefulness:** two clean cases that revision 3 passed are now held back (G6, G8). The new name rule splits
  "Origin Bio U.S., Inc." from "Origin Bio" (G10, G11).
- Net: a real gain on the inputs it targeted. It is not yet a fail-closed gate: the same error class re-enters
  through the paths the gate does not cover.

Definite new errors (not reported in REREVIEW2.md). None of them occurs in the CLDN18.2 output.

| Severity | Introduced by revision 4 | Claimed fixed, fails on a close variant | Older, first reported here | Total |
|---|---|---|---|---|
| High: tier 0 or 1 while a third party may hold U.S. rights, or on contrary, undated or unattached evidence | 1: A5 | 7: A1, A2, A3, A4, H2, R-lost, T | 0 | **8** |
| Medium: false encumbrance, or a false conflict that changes the tier | 1: name split (G10, G11) | 1: FE (availability and non-U.S. text read as an encumbrance) | 0 | **2** |
| Low: false label, wording or citation; no tier change | 3: unattached-row line, "also exists" reason, C4 question | 4: A3c, field-path holder wording, reasons that contradict the text, memo line 9 | 1: codes in memo prose | **8** |

Six of the eight High errors reach a top tier end to end on a copy of the CLDN18.2 workspace (§2c). The other two
(A2b, A3c) were shown per program only.

## 1. REREVIEW2_RESPONSE.md, claim by claim

| § | Claim | Verdict | Evidence (run or read) |
|---|---|---|---|
| 1 | A clear position enters tier 0 or 1 only with no blocker, no guard and no stale flag | **Held as a mechanism. Refuted as coverage.** | `transaction.py:260` sends a blocked, guarded or stale clear position to RIGHTS_UNRESOLVED (ws_g: one id-less rejected row keeps every program out). But blockers come only from `ledger.deciding`, and the availability and field paths put almost nothing there (A1, A2, A3). |
| 1 | Complete: every outcome is attached and explained | **Refuted** | A1a: a termination that names only the licensor, with no deal id, clears Alpha Bio's U.S. license with no blocker when a statement is present. Tier 0. |
| 1 | Specific: a licensor-only ending counts only when linked by id; a return-only record must return the rights to the program's company; the current holder must be established | **Held on the returned path. Refuted elsewhere.** | A1a-control is blocked: "names only the licensor and is not linked to its deal by id". A1a with a statement is tier 0. The company rule covers returns only: a statement by BigPharma Inc (A2a) or a license from Kappa Pharma (H2) makes that party the owner, in tier 0 or 1. |
| 1 | Current: each record judged on its own date; undated never qualifies; records after the as-of date are not applied | **Held on the returned path. Refuted on the availability and field paths.** | Returned path: N5, N9a, N9b, A8, O1, O9 blocked or stale. A1b (undated termination) and A1c (undated license) reach tier 0 beside a statement. A3c: an analyst source dated 2026-01-01 counts on as-of 2025-06-01. |
| 1 | Uncontested: a disagreeing statement, or a holder who is not the owner, makes the position CONFLICTING | **Held for readable statements and plain names on the ledger path. Refuted otherwise.** | Unreadable text is dropped (A4; ws_f JS107 #1, tier 1). A note in parentheses is absorbed (A5; ws_e VBC108, tier 1). The field path never contests (A3; ws_e SKB315 #3, tier 0). An analyst "No U.S. rights available" beside a China license is dropped (T2, tier 1). |
| 1 | Analyst text uses the landscape rules; counts only when dated within the age limit; is cited | **Held as stated. The rules are too weak.** | Same function (`commercial.rights_status`). Undated and old analyst statements are not counted. Cited in JSON, workbook and memo (ws_e SKB315 `dec:00001`). But "No U.S. rights available" reads AVAILABLE and reaches tier 0 (ws_h #3). |
| 2a | N1a–N1c | **Held** | N1a LICENSED to "a licensee not named", question "The record names no licensee"; N1b OPTION_HELD; N1c SHARED. |
| 2a | N1d judgement kept, reason reworded | **Held** | Tier 1: "is within one company as written (the names differ only by a corporate suffix)". |
| 2a | N3a | **Held** | LICENSED to Alpha. |
| 2a | R1, R1b | **Held** | CONFLICTING: "the dates cannot order them, so the grant is kept". |
| 2b | E2-holder | **Held for plain names on the ledger path. Refuted for a note in parentheses and on the field path.** | A5a, A5b, A3a, A3b (§2). "Acme" and "Acme KGaA" stay apart. |
| 2b | E3-ids (a): case and spaces ignored; unattached accepted rows listed in JSON, memo, workbook | **Held** | ws_e row 23 (`CL 24`) is in `rights_import_issues.unlinked_rows`, the memo and the Diligence sheet (`RIGHTS_ROW_NOT_ATTACHED`). Its near-match program JS107 stays tier 1, #4 (judgement, §6). |
| 2b | E3-ids (b): a rejected row naming no program keeps every program out of tiers 0 and 1 | **Held. Refuted for a rejected row with an unmatched id.** | ws_g: no program in tiers 0 or 1; memo "Rejected rights rows that name no program. 1 row(s): row 20 …"; the row is in every program's questions. ws_e row 27 (`CL-041`, rejected) appears in no output (R-lost, §6). |
| 2b | F1-analyst | **Held for the listed phrases. Refuted for close variants.** | "Available for licensing: no" and "Available? No." read NOT_AVAILABLE; the five others read UNKNOWN. But "No U.S. rights available", "Available in Latin America" and "Available upon expiry of the BigPharma Inc. license in 2028" reach tier 0 end to end (ws_h #1–#3). |
| 2b | N6a–N6c | **Held** | N6a, N6b, N6d not counted; N6c RETURNED, tier 1. |
| 2b | N7b, N7c | **Held** | Stale; RIGHTS_UNRESOLVED. |
| 2b | N8a, N8b | **Held** | SHARED: "whether Alpha Bio now holds all US rights is not in the evidence", with a question. |
| 2c | N2a, N2b, H1 | **Held** | CONFLICTING: "Beta Pharma may hold US rights through it". |
| 2c | N7a | **Held** | Not counted. |
| 2c | N10 | **Held on the ledger. Refuted on the field path.** | O1 LICENSED on 2025-06-01. A3c tier 0. |
| 2d | N4a–N4c, N4f, N5a–N5c, N9a, N9b, N3c, N11 | **Held on the returned path** | All blocked. The same shapes beside a statement reach tier 0 (A1b, A1c). |
| 2d | N4d | **Held for returns. Refuted for licenses and statements.** | V-N4d blocked: "Kappa Pharma may hold them under a license". H2 (a license from Kappa) and A2 (a statement by BigPharma) are not checked. |
| 2d | N9c | **Held on the returned path. Refuted beside a statement.** | A1a; ws_e QLS31905 #1. |
| 2d | H7 | **Held** (judgement kept) | OWNER_ACQUIRED, tier 1. |
| 3 | P1 | **Held** | O3, O4 LICENSED in the US; rr3 E1–E8 as stated. |
| 3 | N3b | **Held** | NO_RIGHTS_EVIDENCE, owner None. |
| 3 | Negated words | **Held for the three phrases. Close variants fail.** | "Not licensed", "Never partnered", "Not optioned" read UNKNOWN. "Not encumbered" and "Not licensed in the U.S.; licensed in China to ChinaCo" read ENCUMBERED (FE, §3). |
| 3 | NA-label | **Held** | "Not available" → NOT_AVAILABLE_PER_SOURCE, "not available (source-provided)", DEPRIORITIZED. |
| 3 | W1, N7e, H6, H3/N7c, H5 | **Held** | W1 not stale; N7e stale; wording as claimed. |
| 3 | Memo "no effect"; originator note | **Held** | ws_e memo: "rights assertions changed no gate but feed the transaction view for: SKB315 (availability stated, unverified), …". Note text read at `transaction.py:243-245`. |
| Output | N1 reason; analyst tier-0 entries cited | **Held** | N1a reason: "license to a licensee not named covering US". |
| Output | Memo line 9 "now enforced" | **Refuted** | ws_h line 9 sits above three tier-0 entries whose dated statements say "No U.S. rights available", "Available in Latin America" and "Available upon expiry of the BigPharma Inc. license in 2028". |
| Output | Codes in prose replaced with words | **Mostly held** | Reason templates use words. The memo summary lines still print codes (§9, O-13). |
| Output | "Also exists" line gives dates, reasons and rows | **Held, with gaps** | It gives only the first reason: VBC108 loses the note naming BigPharma's U.S. license. LB4330's line does not mention its lost rejected row. |
| §3 | `same_company`: "Acme" ≠ "Acme KGaA"; "Acme" = "Acme Pharma US, Inc. (U.S. labeler …)" | **Held. New errors in both directions.** | Notes in parentheses are ignored (A5). "Origin" = "Origin Therapeutics"; "Nova" = "Nova Biotech". "Origin Bio U.S., Inc.", "Origin Biotherapeutics" and "LaNova Medicines Zhejiang Co., Ltd." do not match their short names (§4). |
| §3 | K3 | **Held** | Tier 0 with the company given. |
| §3 | Vendor "available" wording | **Held, with a gap** | The same reason says "states availability" for the cell "No U.S. rights available" (ws_f SKB315). |
| §3 | Code health | **Held** | 750 and 368 lines; ruff and mypy clean. |
| §4 | 512 tests pass | **Held** | 512 passed. |
| §4 | Reviewer scripts: tiers 0/1 only for listed cases | **Held** | Every `<<< TOP TIER` line in the re-run rr3 outputs is on the response's list (N1d, N6c, E1-JP, E2, E7, E8, H3–H7, R6–R8, C2, C4, C5). |
| §4 | Reviewer workspaces 12 → 0; JS107 in ws_b enters tier 1 | **Held** | Re-screened from fresh copies on this tree: identical to my first re-screen. ws_t is refused ("unknown territory code 'usa'"), as designed. But ws_b JS107's owner is "Origin Bio" while the landscape company is NingBo Junyan Hongshi Biosciences (H2). |
| §4 | CLDN18.2 tiers unchanged; two reasons changed; memo 1,439 → 1,609 words | **Held** | after_v3 vs after_v4 CSV; `wc -w`. |
| §4 | 0 of 62 scientific fields changed | **Held** | `compare.py`, twice; strict check 0. |
| §4 | Cross-version (312 assets) and cycle-4 equivalence | **Unverifiable** | Not re-run. The result file says byte-identical and fast path on all four sets. |
| §4 | Usefulness 10/4/1 vs 14/1/0 | **Held** | §10. |
| §6 #2 | Name-only identity "errs toward caution" | **Refuted in part** | It also errs toward clearance: A5, and "Origin" = "Origin Therapeutics". |

## 2. Paths into the top tiers

Per-program cases: as-of 2025-06-01, buyer {US}, landscape company "Origin Bio". Output copied from `adv_*.v4.out`.

### 2a. Tier 0 (availability stated, unverified)

| Id | Input | Output (copied) | Expected | Cause |
|---|---|---|---|---|
| A1a | US license to Alpha Bio (2024-03-01); termination naming only the licensor Origin Bio, no deal id (2025-01-01); Origin's statement for the US (2025-03-01) | `tier=AVAILABILITY_STATED_UNVERIFIED … blockers=[]` | Blocked as in A1a-control ("names only the licensor and is not linked to its deal by id"), or CONFLICTING | `rights_position.py:522-523` returns `_available` before `_cleared`, so `_check_ended` (`423-439`) never runs. `_available` puts only the statements in `ledger.deciding` (`550-551`); `_clear_checks` (`681-702`) judges nothing else. |
| A1b | Same, but the termination names Alpha and is undated | tier 0, `blockers=[]` | Blocked: undated ending (N9a) | Same |
| A1c | Same, but the license is undated; termination 2025-01-01 | tier 0, `blockers=[]` | Blocked: an undated grant cannot be ordered (N9b) | Same |
| A1e | License naming no licensee (2024-03-01); termination naming only Origin (2025-01-01); statement (2025-03-01) | tier 0, `blockers=[]` | Blocked: "names no licensee" (N1) | Same |
| A2a | Only a statement by "BigPharma Inc" seeking a partner for the US (2025-03-01) | tier 0, `owner='BigPharma Inc'` | Blocked as N4d: the stating party is not the landscape company and may be a licensee | `rights_position.py:548-549`: the party is the ledger owner, else whoever made the statement. Only `_returned_to_company` (`582-589`) compares with `ledger.company`. |
| A2b | China license Origin → ChinaCo (2025-01-01) + statement by BigPharma Inc for the US (2025-03-01) | tier 0, `holder='Origin Bio' owner='Origin Bio'` | Not tier 0. BigPharma's statement must not be shown as Origin's | Same lines: the ledger owner replaces the stating party |
| A2c | Statement naming only a grantee, "Kappa Pharma" (2025-03-01) | tier 0, `owner='Kappa Pharma'` | Blocked | Same |
| A3a | No rights rows; analyst `us_rights` "Available" (2025-03-01); holder "BigPharma Inc." | tier 0, `holder='BigPharma Inc.'`; reason "the landscape names a U.S. rights holder or labeler: BigPharma Inc. (a labeler is not the owner; neither says whether rights are available)" | CONFLICTING (the E2-holder rule) | `screening.py:389-401`: `_reconcile_with_field` and `_contest_holder` run only for programs with rights rows. `transaction.py:181-184` adds the holder as a label. |
| A3b | Analyst "Seeking a partner for U.S. rights" (2025-03-01); landscape holders "Origin Bio" and "BigPharma Inc." | tier 0, `holder=None`, `field_holder='CONFLICTING: Origin Bio \| BigPharma Inc.'` | Not tier 0 | `screening.py:399-401` passes `us_rights_holder`, which is None when holders conflict. `us_rights_holder_conflict` is never read on this path. |
| A3c | Analyst "Available", source date 2026-01-01 (after the as-of date) | tier 0 | Not counted (N10) | `transaction.py:140-143`: a negative age passes the age test |
| T | Analyst `us_rights`, dated 2025-03-01, no rights rows: "Available in Latin America"; "No U.S. rights available"; "May be available"; "Available upon expiry of the BigPharma Inc. license in 2028"; "BigPharma Inc. holds U.S. rights; available in Europe"; "Available?"; "Available - no" | each tier 0 | Not tier 0 | The reader (§3) reads each as AVAILABLE. A dated analyst AVAILABLE passes the age check (`transaction.py:164`) and becomes a clear position (`171-178`). |
| A1d (judgement) | US license to Alpha (2024-03-01); undated acquisition "Origin Bio acquires Alpha Bio"; statement (2025-03-01) | tier 0 | The returned path blocks the same undated acquisition (O9: "has no date of its own") | `rights_position.py:522-523` (merged grants skip the checks too) |
| A3d (judgement) | Landscape "Not available" (2025-05-01) + analyst "Available" (2024-01-01) | tier 0; the newer landscape statement is not shown | At least cite the newer contrary statement | `commercial.assess`: a confirmed claim replaces source claims |
| A3e (judgement) | Analyst "Not available" (2025-05-01, entered first), then "Available" (2024-01-01, entered second) | tier 0 | The newer source says no | The last entered wins, whatever the source dates |
| A7a (judgement) | Buyer {US, CA}; statement for "United States" only (2025-03-01) | tier 0; ask "Confirm with the owner that CA/US rights are unencumbered and available" | A return covering part of the territory is blocked (A7b); a statement is not | `rights_position.py:332` accepts any overlap |

### 2b. Tier 1 (no third-party grant in evidence)

| Id | Input | Output (copied) | Expected | Cause |
|---|---|---|---|---|
| A4 | China license Origin → ChinaCo (2025-01-01) + landscape `us_rights` (2025-04-01): "U.S. rights held by BigPharma Inc."; "Sublicensed to BigPharma Inc. (U.S.)"; "Acquired by BigPharma Inc."; "BigPharma Inc. has U.S. commercialization rights"; "U.S. rights sold to BigPharma Inc."; "Collaboration with BigPharma Inc. covering the U.S."; "BigPharma Inc. (U.S. rights)"; "U.S. rights: BigPharma Inc."; "Assigned to BigPharma Inc. in 2024" | each `tier=NO_THIRD_PARTY_GRANT_IN_EVIDENCE`, `field_status=UNKNOWN`; the cell is not a reason and is not cited | CONFLICTING, citing the cell | The reader returns UNKNOWN (`commercial.py:67-81`). Only ENCUMBERED, OPTION, NOT_AVAILABLE and CONFLICTING contest (`screening.py:280, 308`); UNKNOWN is dropped. |
| A5a | China license (2025-01-01) + landscape holder "Origin Bio (U.S. rights licensed to BigPharma Inc.)" | tier 1; reason "the landscape also names a U.S. rights holder or labeler: Origin Bio (U.S. rights licensed to BigPharma Inc.)" | CONFLICTING | `rights_territory.py:153` deletes text in parentheses before comparing. `_contest_holder` (`screening.py:323-324`) then sees "Origin Bio". |
| A5b | US license to Alpha (2023-06-01), termination naming Alpha (2025-02-01) + holder "Origin Bio (partnered with BigPharma Inc. in the U.S.)" | tier 1; the note appears in no reason | CONFLICTING | Same; `screening.py:394` skips the "also names" note when the names match |
| H2 | China license from "Kappa Pharma" to ChinaCo (2025-01-01); landscape company Origin Bio | tier 1, `owner='Kappa Pharma'`; question "Who holds US rights (Kappa Pharma)? Recorded deals cover other territories only." | Blocked, with "Does Kappa Pharma own this program, or hold it under a license from Origin Bio?" (the N4d rule) | `rights_position.py:528-538`: the owner is the licensor and is never compared with `ledger.company` |
| H1 (variant) | US license from Origin Bio to Alpha (2024-03-01), returned (2025-02-01); landscape company "Kappa Pharma" | tier 1, owner Origin Bio, no question | Same question | `rights_position.py:451-466` (returned path, same gap) |
| T2 | China license (2025-01-01) + analyst "No U.S. rights available" (2025-03-01) (`adv_t2.v4.out`) | `position=NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE tier=NO_THIRD_PARTY_GRANT_IN_EVIDENCE`, `field_status=AVAILABLE_ANALYST_CONFIRMED`, `cited rows=[1]` (the license only). The same text as a landscape cell (2025-04-01): tier 1, `cited rows=[3]`. Control: the cell "Not available" gives CONFLICTING and cites the cell (`cited rows=[5, 1]`). | CONFLICTING, citing the statement | The reader says AVAILABLE. `screening.py:300-313` has no branch for AVAILABLE beside a clear position, so the statement is dropped. |
| A6 (judgement) | China license + landscape holder "BigPharma Inc." + undated analyst holder "Origin Bio" | tier 1; BigPharma appears nowhere | An undated assertion silently removes a third-party holder | `commercial.assess`: the analyst holder replaces the landscape holder |
| C2 (judgement) | Return-only, Delta Bio → "Origin Bio China", US (2025-02-01) | tier 1 | A U.S. return to a China affiliate; probably fine | `rights_territory.py:142-145` treats "china" as a generic word |
| O8 (judgement) | US license (2024-03-01) + termination dated 2025-05-31, reported 2025-09-01 | tier 1 | The report is after the as-of date; acceptable | — |

Accepted top-tier cases (listed by earlier reviewers or clean): N1d, N6c, E1-JP, E2, E7, E8, H3–H7, R6–R8, C2, C4,
C5 (rr3 scripts); C3, O7 (mine); and the clean cases in §8.

### 2c. End to end on copies of the CLDN18.2 workspace (C3 buyer, as-of 2026-10-29)

| Workspace | Program | Input added (all fictional) | Output (copied) | Finding |
|---|---|---|---|---|
| ws_e | QLS31905 | X01 license Qilu → Alpha Bio, US, 2025-03-01; X02 termination naming only Qilu, 2026-01-15; X03 "Seeking partner" by Qilu, US, 2026-06-01 | memo "#1 QLS31905: availability stated, unverified; rights position: availability stated by a source (unverified) (a source states the program is available or a partner is sought (unverified))"; blockers column empty | A1a |
| ws_e | ATG-022 | X04 "Seeking partner" stated by BigPharma Inc, US, 2026-05-01 (landscape company Antengene) | memo "#2 ATG-022: availability stated, unverified"; workbook "Owner / licensor per evidence: BigPharma Inc" | A2a |
| ws_e | SKB315 | Analyst `us_rights` "Available" and `us_rights_holder` "BigPharma Inc." (quote "(test) BigPharma Inc. holds U.S. rights"), both 2026-09-01 | memo "#3 SKB315: availability stated, unverified; … the landscape names a U.S. rights holder or labeler: BigPharma Inc. …" | A3a |
| ws_e | TORL-2-307-ADC | X08 license Kappa Pharma → ChinaCo, mainland China, 2026-02-01 (landscape company TORL Biotherapeutics) | memo "#5 TORL-2-307-ADC: no third-party grant in evidence"; "ask: Who holds US rights (Kappa Pharma)?" | H2 |
| ws_e | VBC108 | X12 China license; analyst holder "VelaVigo Bio (U.S. rights licensed to BigPharma Inc.)" | tier NO_THIRD_PARTY_GRANT_IN_EVIDENCE; reason "an analyst assertion also names a U.S. rights holder or labeler: VelaVigo Bio (U.S. rights licensed to BigPharma Inc.)" | A5 |
| ws_e | LB4330 | X10 China license; X11 U.S. license L & L Bio → BigPharma Inc, id `CL-041`, status "Actv" (rejected) | tier NO_THIRD_PARTY_GRANT_IN_EVIDENCE; row 27 in no output | R-lost |
| ws_e | JS107 | X05 China license; X06 U.S. license to BigPharma Inc under id `CL 24` (accepted, unattached) | memo "#4 JS107: no third-party grant in evidence" | judgement (§6) |
| ws_f | JS107 | Landscape "US Rights" = "U.S. rights held by BigPharma Inc."; X05 China license | memo "#1 JS107: no third-party grant in evidence; rights position: no grant over the buyer territory per evidence (recorded grants do not cover US; …)"; the cell is cited nowhere | A4 |
| ws_f | VBC108 | Landscape "US Rights" = "Sublicensed to BigPharma Inc. (U.S.)"; X12 China license | tier NO_THIRD_PARTY_GRANT_IN_EVIDENCE | A4 |
| ws_h | QLS31905 | Analyst "Available in Latin America", 2026-09-01 | memo "#1 QLS31905: availability stated, unverified; … (the U.S.-rights field reads: available (analyst-asserted or -confirmed from a cited source) (no rights record))" | T |
| ws_h | JS107 | Analyst "Available upon expiry of the BigPharma Inc. license in 2028", 2026-09-01 | memo "#2 JS107: availability stated, unverified" | T |
| ws_h | SKB315 | Analyst "No U.S. rights available", 2026-09-01 | memo "#3 SKB315: availability stated, unverified" | T |
| re_ws_b | JS107 | rr3 row Y02, license Origin Bio → ChinaCo; analyst "Not licensed in the U.S." | tier 1, #1; "Who holds US rights (Origin Bio)?" (landscape company NingBo) | H2 |

The `assert` command never shows how it read the text. It printed only "recorded dec:00001:
us_rights='No U.S. rights available' on ds:1b1a19108b04. Re-run `screen` to apply it." (format at
`src/bve/cli/dealscreen.py:429-430`; the record is `ws_h/decisions.jsonl` seq 1). The analyst gets no warning that
"No" became "available".

In ws_e, Spevatamig ("Available in Latin America") and BL-M05D1 ("No U.S. rights available") did not reach tier 0.
Both landscape rows have a Partnerships cell, which turned the misread "available" into CONFLICTING by accident. The
reason for BL-M05D1 then says "an analyst assertion reads: conflicting statements" (O-7).

## 3. The U.S.-rights text reader (`commercial.rights_status`)

Same reading in revision 3 for 56 of 57 phrasings (`text_v3v4.out`); only "Available in China" changed (now
UNKNOWN). So most of this is older, but F1-analyst and "negated words" were claimed fixed.

| Group | Text | Reads | A careful reader | Effect |
|---|---|---|---|---|
| Other places | "Available in Latin America", "Rights available in South America", "Available in Asia", "Available in Asia-Pacific", "Available in Australia", "Available in Germany", "Available in Brazil and Mexico", "Available in the Middle East", "Available in emerging markets", "Seeking a partner for India" | AVAILABLE_PER_SOURCE | Not about the U.S. | Analyst: tier 0 (ws_h #1) |
| Rest of world (judgement) | "Available in rest of world", "Available for ROW" | AVAILABLE_PER_SOURCE | Usually means outside the major markets | Same |
| Negation | "No U.S. rights available", "None available", "Nothing available for licensing", "Available - no", "Available = No", "Available? Not anymore", "Available: not at this time", "Available: N", "Available (no)", "Rights: none available" | AVAILABLE_PER_SOURCE | Not available | Analyst: tier 0 (ws_h #3); beside a China license: tier 1, dropped (T2) |
| Hedge, future, question | "May be available", "Possibly available", "Could become available in 2027", "Expected to become available", "Available from 2027", "Available after 2027", "Available?", "Available? TBD" | AVAILABLE_PER_SOURCE | Not a statement of availability now | Analyst: tier 0 |
| Encumbered, worded as availability | "Available subject to BigPharma Inc.'s right of first negotiation", "Available upon expiry of the BigPharma Inc. license in 2028", "BigPharma Inc. holds U.S. rights; available in Europe", "U.S. rights held by BigPharma Inc.; rest of world available", "Sublicensable rights available from BigPharma Inc. (U.S. licensee)" | AVAILABLE_PER_SOURCE | Encumbered in the U.S. | Analyst: tier 0 (ws_h #2) |
| Third-party holder not understood | "U.S. rights held by BigPharma Inc.", "Sublicensed to BigPharma Inc.", "Acquired by BigPharma Inc.", "BigPharma Inc. has U.S. commercialization rights", "Assigned to BigPharma Inc." | UNKNOWN | Encumbered, or a third-party owner | Landscape cell dropped: tier 1 (ws_f #1, A4) |
| Availability or non-U.S. grant read as encumbrance (FE) | "Seeking a co-development partner", "Available for exclusive licensing", "Open to co-promotion partnerships in the U.S.", "Option available to partners", "Not encumbered", "Licensed in China only", "Out-licensed to ChinaCo for Greater China", "Not licensed in the U.S.; licensed in China to ChinaCo", "Exclusive China license to ChinaCo; U.S. rights retained" | ENCUMBERED_PER_SOURCE | Availability, or no U.S. encumbrance | Field path: LICENSED → DEPRIORITIZED (G13). Ledger path: false CONFLICTING (G12). |
| Handled (controls) | "Available in China", "Available ex-U.S.", "Available, but not in the U.S.", "China rights available", "Previously available", "Available for licensing: no", "Available? No.", "Not available", "Not licensed", "Will be available after the option period ends", "Available if BigPharma Inc. declines its option" | UNKNOWN, NOT_AVAILABLE or ENCUMBERED as a careful reader would | — | — |

Causes (`commercial.py`): `_AVAILABLE` (line 60) matches "available" anywhere. `_availability` (84-92) treats a place
outside the region list as no place, so the text reads as U.S. availability. `_NEGATED` (33-34) needs
"not / no longer / never … available" or the exact words "no rights". `_ANSWERED_NO` (41) needs ":" or "?" right
before "no". `_ENCUMBERED` (48) is tested at line 77, before availability at line 79. It has no place check, and fires on
"co-development", "exclusive", "option", "encumber…" and "licensed" in any sense.

## 4. Names: `same_company`

`same_company` (`rights_territory.py:148-157`) decides the return-only exception (`rights_position.py:582-589`), the
holder contest (`screening.py:318-336`) and the holder note (`screening.py:394`).

| Pair | Result | Correct reading | Effect |
|---|---|---|---|
| "Acme" / "Acme KGaA" | False | different | control, held |
| "Acme" / "Acme Pharma US, Inc. (U.S. labeler)" | True | same | control, held |
| "Origin Bio" / "Origin Bio (U.S. rights licensed to BigPharma Inc.)" | **True** | the note names a third party | A5: false clearance (line 153 deletes the note) |
| "Origin Bio" / "Origin Bio [licensed to BigPharma Inc.]" | False | same | square brackets are not deleted: CONFLICTING (inconsistent) |
| "Origin" / "Origin Therapeutics"; "Nova" / "Nova Biotech" | **True** | may be different companies | false merge (generic-word list, 142-145) |
| "Origin Bio" / "Origin Bio China", "Origin Bio Japan" | True | affiliate; judgement | C2 |
| "Origin Bio" / "Origin Bio U.S., Inc." | **False** | same | G10, G11: "U.S." becomes "u s", which is not in the list ("us" is) |
| "Origin Bio" / "Origin Biotherapeutics" | **False** | probably same | C1 (acknowledged as response #2) |
| "Origin Bio" / "Origin Bio Sciences", "Origin Bio Oncology" | **False** | same | `transaction._GENERIC_NEXT` lists "sciences", "oncology", "medicines" and "development"; `_GENERIC_NAME_WORDS` does not. Two lists, two answers. |
| Read-only, real landscape names: "LaNova" / "LaNova Medicines Zhejiang Co., Ltd."; "Kelun-Biotech" / "Sichuan Kelun-Biotech Biopharmaceutical Co., Ltd."; "Hengrui" / "Jiangsu HengRui Medicine Co., Ltd." | **False** | same | A return-only row to the company as news reports name it would be held back for the reference's two HIGH-attractiveness returned assets (LM-302, SKB315). Usefulness risk. |
| "Origin Bio" / "Origin Bio and BigPharma Inc.", "… ; BigPharma Inc.", "BigPharma Inc. / Origin Bio" | False | two parties | correct |

## 5. Returns, ordering, acquisitions, partial exercises, co-development exits, as-of

| Id | Input | Output | Verdict |
|---|---|---|---|
| C1 | Return-only Delta → "Origin Bio", US, 2025-02-01; company "Origin Biotherapeutics, Inc." | RIGHTS_UNRESOLVED; "… but the landscape names Origin Biotherapeutics, Inc. as the program's company; Origin Bio may hold them under a license" | Usefulness cost (acknowledged) |
| C3 | China license + unmatched termination BigPharma Inc → Origin, US, 2025-03-01 | tier 1; "… returned the rights covering US to Origin Bio, the program's company per the landscape" | Acceptable |
| C4 | C3 + BigPharma Inc exercised an option for the US (2025-04-01) | CONFLICTING; question "Is BigPharma Inc the successor of BigPharma Inc? …" | Tier right; question wrong (Low, O-12) |
| C5 | Two return-only rows: Delta → Origin (US, 2025-02); Epsilon → Kappa (US, 2024-11) | RIGHTS_UNRESOLVED; "complete: a rights return (2024-11-01) naming Epsilon Bio matches no recorded grant" | Correct |
| C6 | Return-only to Origin + undated U.S. license Origin → BigPharma | CONFLICTING | Correct |
| O1 | US license Alpha (2024-03); "Origin acquires Alpha" dated 2026-01 | LICENSED on 2025-06-01 | Correct |
| O2 | License reported 2025-04 (no event date); termination naming Alpha 2025-02 | CONFLICTING | Correct |
| O3, O4 | Worldwide option, US exercise (2024-02), then a Japan termination or a lapse | LICENSED in the US | Correct |
| O5 (= G8) | Co-development Origin + Alpha ended by both (2025-02) | RIGHTS_UNRESOLVED: "who holds the US rights now is not established" | Usefulness cost (judgement) |
| O6 | Co-development; only Alpha exits | SHARED | Correct (N8) |
| O7 | "Gamma Corp acquires Origin Bio" (2025-01) + China license | OWNER_ACQUIRED Gamma, tier 1 | Correct (Gamma not on this buyer's list) |
| O8 | Termination dated 2025-05-31, reported 2025-09 | RETURNED, tier 1 | Judgement |
| O9 | Undated acquisition Origin acquires Alpha + US license | RIGHTS_UNRESOLVED: "an acquisition (undated) naming Origin Bio has no date of its own" | Correct; contrast A1d |
| G18 | US license Alpha 2020-01; termination naming both 2025-03 | RETURNED, tier 1 | Correct: an old grant returned recently is current |

## 6. Unattached, id-less and rejected rows

| Case | Input | Output | Verdict | Cause |
|---|---|---|---|---|
| Id-less rejected row (ws_g) | Row 20: no program id, status "Actv" | All programs out of tiers 0 and 1; memo "Rejected rights rows that name no program. 1 row(s): row 20 (missing external_id; unknown status label 'Actv')"; question added to every program | Held | `screening.py:376-378` |
| **R-lost (ws_e)** | Row 27: `X11,CL-041,Licensing,Exclusive,BigPharma Inc,L & L Bio,United States,2026-03-01,Actv,…` | `rights.json` keeps it under `rejected`. `rights_import_issues` = `{"unattributed_rejected_rows": [], "unlinked_rows": [row 23]}`. No memo line, no Diligence row; the Audit Trail lists only the landscape manifest. LB4330 (CL-41) is NO_THIRD_PARTY_GRANT_IN_EVIDENCE. | **Definite, High.** A rejected row whose id matches no program falls between the two lists. | `screening.py:344-355` files it under its own id; `402` looks rows up only by a program's own key; `unlinked` (374) takes accepted events only |
| Unattached accepted row (ws_e) | Row 23: `X06,CL 24,Licensing,Exclusive,BigPharma Inc,NingBo Junyan Hongshi Biosciences,United States,2026-03-01,…` | Listed: memo "row 23 ('CL 24', license, 2026-03-01)"; Diligence `RIGHTS_ROW_NOT_ATTACHED`. JS107 (CL-24) stays tier 1, #4. | Listing held. The line omits licensee and territory (Low, O-9). Leaving the near-match program in tier 1 is a judgement call. | `screening.py:339-341` matches ids by case and outer spaces only |

## 7. False encumbrance, wrong holder, wrong owner

| Id | Input | Output | Expected | Kind |
|---|---|---|---|---|
| FE / G13 | No rights rows; analyst "Seeking a co-development partner for U.S. rights" (2025-03-01) | LICENSED_IN_TERRITORY_PER_EVIDENCE, DEPRIORITIZED: "the U.S.-rights field reads: licensed, optioned or partnered (source-provided)" | Tier 0 (an owner seeking a partner) | False encumbrance (Medium) |
| FE (field) | Landscape "Licensed in China only", "Available for exclusive licensing", "Seeking a co-development partner" (2025-04-01), no rights rows | LICENSED, DEPRIORITIZED | Not "licensed in the buyer territory" | False encumbrance (Medium) |
| FE / G12 | China license + landscape "Exclusive China license to ChinaCo; U.S. rights retained" | CONFLICTING: "the landscape reads: licensed, optioned or partnered (source-provided); the rights evidence records no third-party grant over the U.S." | Tier 1 | False conflict (Medium) |
| Name split / G11 | Clean return + landscape holder "Origin Bio U.S., Inc." | CONFLICTING: "the landscape names Origin Bio U.S., Inc. as the U.S. rights holder; …" | Tier 1 | False conflict (Medium) |
| A2a (ws_e ATG-022) | Statement by BigPharma Inc | owner "BigPharma Inc" | owner not established | Wrong owner (part of High A2) |
| A2b | China license by Origin + statement by BigPharma | holder and owner "Origin Bio" | the statement is BigPharma's | Wrong attribution (part of A2) |
| H2 (ws_e TORL, re_ws_b JS107) | License by Kappa Pharma / Origin Bio; landscape company TORL / NingBo | owner "Kappa Pharma" / "Origin Bio" | owner per evidence differs from the landscape: ask | Wrong owner (part of High H2) |
| A3a (ws_e SKB315) | Analyst holder "BigPharma Inc." | holder shown, but called "a labeler" from "the landscape" | an analyst-stated U.S. holder | Wrong source (Low) |

## 8. Over-caution: clean cases held back (usefulness costs, not safety errors)

| Id | Input | Revision 4 | Revision 3 | Verdict | Cause |
|---|---|---|---|---|---|
| G5b | US license to Alpha, deal date 2021-05-01, status TERMINATED, report 2025-02; plus a rights-return row naming Alpha, 2025-02-01 | RIGHTS_UNRESOLVED: "a rights return (2025-02-01) naming Alpha Bio repeats the end of the grant …"; "current: a license (2021-05-01) … is more than 730 days" | — | **Definite.** A dated 2025 return is discarded as a repeat of a status flag dated by the deal date | `rights_ledger.py:233-235` (status ends the grant at the deal date), `265` (later return = repeat) |
| G6 | China license (2025-01-01) + an old Japan license to JapanCo (2012-01-01) | RIGHTS_UNRESOLVED: "current: a license (2012-01-01) naming JapanCo is more than 730 days …" | tier 1 | **Definite; regression.** A 2012 Japan deal says nothing about the U.S. now. The reason also says the position "rests on" it | `rights_position.py:532` puts every grant's events in `ledger.deciding`; `_clear_checks` (689-700) then blocks on each one's age and marks the position stale |
| G10 | Return-only to "Origin Bio U.S., Inc.", US, 2025-02-01 | blocked: "… may hold them under a license" | — | **Definite; new** | `rights_territory.py:131-157` |
| G11 | Clean return + landscape holder "Origin Bio U.S., Inc." | CONFLICTING | — | **Definite; new** | same |
| G12 | China license + "Exclusive China license to ChinaCo; U.S. rights retained" | CONFLICTING | CONFLICTING | Definite; older | `commercial.py:48, 77-80` |
| G13 | Analyst "Seeking a co-development partner for U.S. rights" | DEPRIORITIZED as LICENSED | same | Definite; older | same |
| C1 | Company "Origin Biotherapeutics, Inc.", return to "Origin Bio" | blocked | — | Definite; acknowledged (response #2) | `rights_territory.py:142-157` |
| G5 | Vendor row status TERMINATED, deal date 2021-05, report 2025-02, no return row | stale | tier 1 | Judgement: the termination date is unknown | as G5b |
| G8 | Co-development Origin + Alpha (2023) ended by both (2025-02) | "owner not established" | tier 1 | Judgement; regression | `rights_ledger.py:359-368` excludes co-development grants from `owner()` |

Clean cases that pass: G1, G1b, G2, G3, G4, G7, G9, G14, G15, G16, G17, G18, G18b, G18c, K1, K3.

## 9. Output honesty (memo and workbook)

In favour: in the CLDN18.2 outputs (`after_v4/`), every holder and owner shown is cited by rights row. No output
calls a program available or open; "available" appears only in disclaimers and "availability not evidenced". The
blockers column is filled for IMAB362 and zolbetuximab.

| # | Where | Output (copied) | Problem | Cause |
|---|---|---|---|---|
| O-1 | ws_e memo #1 QLS31905 | "(a source states the program is available or a partner is sought (unverified))", above evidence rows 18 (license to Alpha Bio) and 19 ("licensee not named") | The reason does not say the license is treated as ended, or by which record (part of A1) | `rights_position.py:546-560` |
| O-2 | ws_e workbook ATG-022 | "Owner / licensor per evidence: BigPharma Inc"; memo ask "Confirm with the owner that US rights are unencumbered …" | The row is a partner-seeking statement. It does not say BigPharma owns the program; the landscape names Antengene (part of A2) | `rights_position.py:548-549` |
| O-3 | ws_e SKB315 (JSON, workbook, memo) | "the landscape names a U.S. rights holder or labeler: BigPharma Inc. (a labeler is not the owner; …)"; transaction evidence lists only `dec:00001` | The holder came from analyst assertion `dec:00002` ("(test) BigPharma Inc. holds U.S. rights"). It is cited only in other columns. A stated U.S. holder is called "a labeler" | `transaction.py:181-184` |
| O-4 | ws_e VBC108 | tier "no third-party grant in evidence" with reason "… VelaVigo Bio (U.S. rights licensed to BigPharma Inc.)" | The reason states a third-party U.S. license; the tier says there is none (A5) | `rights_territory.py:153` |
| O-5 | ws_e TORL-2-307-ADC | "ask: Who holds US rights (Kappa Pharma)? Recorded deals cover other territories only." | Presumes Kappa owns it; the JSON `ownership_per_source` is TORL Biotherapeutics (H2) | `rights_position.py:528-538` |
| O-6 | ws_f SKB315, QLS31905 | "the landscape U.S.-rights field states availability; a vendor field is unverified, so it is not counted"; workbook "U.S.-rights field … as read": "AVAILABLE (source-provided, unverified)" | The cells say "No U.S. rights available" and "Available in Latin America" | reader, §3 |
| O-7 | ws_e BL-M05D1 | "an analyst assertion reads: conflicting statements; the rights evidence records no third-party grant over the U.S." | The analyst wrote one statement, "No U.S. rights available" | `screening.py:308-313` with the reader |
| O-8 | ws_h memo line 9 | "Nothing is shown as available without an explicit, dated statement." above "#3 SKB315: availability stated, unverified" | The sentence is printed unconditionally; the statement it relies on says "No" | `memo.py:411` |
| O-9 | ws_e memo; Diligence | "row 23 ('CL 24', license, 2026-03-01)"; "Rights row 23 (license, 2026-03-01) names program id 'CL 24', which matches no landscape program" | Omits licensee (BigPharma Inc) and territory (United States). The near-match program JS107 is #4 in tier 1 | `memo.py:316-332`, `workbook.py:493-500` |
| O-10 | ws_e, all outputs | rejected row 27 | Absent from screening.json, memo and workbook (R-lost) | `screening.py:344-355, 402` |
| O-11 | ws_e memo "also exists" line | "VBC108 (unresolved): no grant over the buyer territory per evidence, newest evidence 2026-02-01 (recorded grants do not cover US; this is not a statement of availability) [rights rows 28]" | Drops the holder note naming BigPharma's U.S. license. LB4330's entry says nothing about its rejected row | `memo.py:380-396` (first reason only) |
| O-12 | C4 (per program) | "Is BigPharma Inc the successor of BigPharma Inc? If so, the grant has ended: record the acquisition or link the deal id." | Names one party twice | `rights_position.py:635` |
| O-13 | Every memo | "rights position in the buyer territory per rights evidence is: availability stated by source unverified 3, … not encumbered in territory per evidence 2, …"; "availability stated unverified 3, … no third party grant in evidence 2"; "open gates: strategy.indication (24), modality.required (8), target.expression (4), evidence.phase_constraint (2)" | Codes in prose, lower-cased. The open-gates line predates R1 | `memo.py:132, 406, 408` |
| O-14 | Workbook blockers column | Empty for every held-out top-tier error above | It shows only what the checks computed. On the field path it can hold at most two blockers | `transaction.py:174-178` |

## 10. CLDN18.2 measured against the reference and B

### 10a. What changed from revision 3

| Program | Revision 3 | Revision 4 | Effect |
|---|---|---|---|
| Zolbetuximab | "latest evidence for this position is dated 2016-10 …"; "the landscape also names … Astellas Pharma US, Inc. (U.S. labeler per FDA label; not a rights statement)" | "an acquisition (reported 2016-10) naming Astellas, which this position rests on, is more than 730 days …"; the labeler note is gone (matched as Astellas); blockers column filled | Audit improvement; the labeler is still in the workbook's labeler column. Neutral for calls |
| IMAB362 | same staleness wording | same new wording; blockers filled | Audit improvement |
| Memo | 1,439 words | 1,609 words; "also exists" line has dates and reasons | Audit improvement |
| All 62 | | tiers identical; eligible: 8 rights unresolved, 6 deprioritized; none in tier 0 or 1 | No change in calls |

### 10b. Error classes against the reference

| Error class | Baseline | R1 | Revision 2 | Revision 3 | Revision 4 |
|---|---|---|---|---|---|
| False "unobstructed" (third-party U.S. rights shown OPEN or in a top tier) | 4 definite + zanidatamab | 0 | 0 | 0 | **0** |
| False encumbrance | 0 | 0 definite, 2 likely outdated | same | same | **same** (EO-3021, SYSA1801; stale-flagged) |
| Wrong holder | n/a | 3 | 1, labelled | 1, labelled | **1, labelled** (LM-302: Turning Point "(recorded; conflicting)") |
| Wrong territory reading | n/a | 1 | 0 | 0 | **0** |
| Missed return | n/a | 1 | 1 | 1 | **1** (SKB315) |

### 10c. Usefulness against general Claude (B), the 15 deal programs

| Program | DealScreen revision 4 | Score | B | Change from rev 3 |
|---|---|---|---|---|
| CL-01 zolbetuximab | OWNER_ACQUIRED Astellas; excluded (marketed); stale | right | right | wording only |
| CL-02 IMAB362 | OWNER_ACQUIRED Astellas; stale | right | right | wording only |
| CL-03 AZD0901 / CL-04 CMG901 | LICENSED AstraZeneca, global; stale | right / right | right / right | none |
| CL-05 sonesitatug vedotin | NO_RIGHTS_EVIDENCE; identity flag to AZD0901 | partial | right | none |
| CL-06 IBI343 | LICENSED Takeda ex-Greater China | right | right | none |
| CL-07 LM-302 | CONFLICTING; Turning Point "(recorded; conflicting)"; successor and in-force questions | partial | right | none |
| CL-08 SHR-A1904 | OPTION_HELD Merck KGaA; stale | right | right | none |
| CL-11 XNW27011 | LICENSED Astellas ex-Greater China | right | right | none |
| CL-13 givastomig | SHARED, I-Mab and ABL Bio | right | right | none |
| CL-14 EO-3021 | LICENSED Elevation; stale | partial | right | none |
| CL-15 SYSA1801 | same as CL-14 | partial | partial | none |
| CL-26 RC148 | LICENSED AbbVie ex-Greater China | right | right | none |
| CL-27 SKB315 | NO_RIGHTS_EVIDENCE | missed | right | none |
| CL-30 FL-301 | LICENSED Leap, ex-China, rows 16 and 17; stale | right | right | none |
| **Totals** | | **10 right / 4 partial / 1 missed** | **14 / 1 / 0** | unchanged |

Notes:
- DealScreen still wins on audit and restraint. B still wins on recall. No advantage is demonstrated.
- Latent risk for closing the recall gap: if SKB315's or LM-302's return were added as a return-only row naming the
  company as news reports do ("Kelun-Biotech", "LaNova"), the company check would hold it back (§4), on top of the
  730-day limit.

## 11. Acceptance criteria

| AC | Verdict | Evidence |
|---|---|---|
| AC1 | PASS | Imports through the profile with source system, dataset hash, row, URL, quote and dates. "Actv" and a missing id are rejected and printed (ws_e, ws_g). Losing a rejected row afterwards is an AC10 failure, not an import failure. |
| AC2 | PARTIAL | CLDN18.2: no OPEN tier; no output says available. Held-out: "No U.S. rights available" reaches tier 0 (ws_h #3) and shows "AVAILABLE (source-provided, unverified)" in the workbook (ws_f). |
| AC3 | PARTIAL | Territory phrasings parse; N1, N3a, N3b fixed. A licensor who is not the company is named as owner (H2); a statement's party is taken as owner (A2); a partial-territory statement counts (A7a, judgement). |
| AC4 | PARTIAL | Clean returns, re-licenses, K1, K3, G18 work. Not met: endings unchecked beside a statement (A1); a dated return discarded as a repeat (G5b); co-development ended by both (G8); name splits (G10); LM-302 not RETURNED (data). |
| AC5 | PASS on my inputs | Exercises, lapses, partial exercises, R1, P1, N2, H5 as stated (O3, O4, G7, C4, rr3 E-cases). |
| AC6 | PARTIAL | Readable statements and plain holders conflict. Not met: unreadable text (A4), notes in parentheses (A5), field path (A3), an analyst "no" beside a China license (T2). False conflicts: G11, G12. |
| AC7 | PARTIAL | Returned-path staleness works (N5, N7, A8). Not met: undated records under a statement (A1b, A1c); a source after the as-of date (A3c). Over-caution: G5b, G6. |
| AC8 | PASS | 0 of 62 scientific fields changed (compare.py, strict check 0). Cycle-4 equivalence and cross-version: result file only, not re-run. |
| AC9 | PASS | Territory, encumbered treatment, returned preference and age work; "usa" is refused (ws_t). Defaults imply nothing. |
| AC10 | PARTIAL | CLDN18.2 holders cited. Not met: A4 cells cited nowhere; R-lost row in no output; the SKB315 holder not in its evidence; unattached-row line without parties; "also exists" drops reasons. |
| AC11 | PARTIAL | Most questions name party and territory. Not met: H2 presumes the licensor owns it; tier-0 asks say "the owner" when the owner is a third party (A2); C4 self-reference. |
| AC12 | PASS | 0 matches for 150 CLDN18.2 program, company and party names in the 12 new or changed `src/bve/dealscreen` files. |
| AC13 | PARTIAL | IBI343 and SHR-A1904 not unobstructed; RC148, FL-301, XNW27011 encumbered; no-evidence programs NO_RIGHTS_EVIDENCE. LM-302 is CONFLICTING, not returned. |
| AC14 | FAIL | This review finds new false-availability errors (8 High) and false encumbrances (2 Medium) on held-out inputs. None in the CLDN18.2 output. |

## 12. Remaining issues, ranked

1. **(Safety, High) The top-tier checks cover one path.** The availability path skips the checks on the grants it
   clears (A1) and on who made the statement (A2). The field path has no holder or currency checks (A3, A3c).
   End to end: ws_e QLS31905 #1, ATG-022 #2, SKB315 #3 in tier 0.
2. **(Safety, High) Text that is not understood is dropped, not blocked.** Third-party holders in unknown wording
   (A4), notes in parentheses (A5), and analyst text that says no, names another place or hedges (T, T2). End to
   end: ws_f JS107 #1 in tier 1; ws_h #1–#3 in tier 0.
3. **(Safety, High) The owner per evidence is compared with the landscape company only for return-only rows.**
   A licensor (H2, H1) or a stating party (A2) who is not the company becomes the owner. End to end: ws_e TORL #5,
   re_ws_b JS107 #1.
4. **(Safety, High, needs an input error) A rejected row with an unmatched id vanishes** (R-lost). An unattached
   accepted row leaves its near-match program in tier 1 (judgement).
5. **(Medium) False encumbrance from availability and non-U.S. wording** (FE: G12, G13).
6. **(Medium, usefulness) Name matching splits and merges wrongly:** "U.S.", "Biotherapeutics", two inconsistent
   generic-word lists, real names such as "LaNova" and "Kelun-Biotech"; "Origin" = "Origin Therapeutics".
7. **(Usefulness) Over-caution:** a dated return discarded as a repeat (G5b), an old other-territory grant makes the
   position stale (G6), co-development ended by both (G8).
8. **(Low) Output honesty:** reasons that contradict the text (O-6, O-7), misattributed holder source (O-3),
   unconditional memo line 9 (O-8), unattached-row line without parties (O-9), first-reason-only summary (O-11),
   self-referential question (O-12), codes in prose (O-13).
9. **(Recall) The rights file caps recall** (LM-302's successor, SKB315's return, EO-3021's discontinuation).
   Unchanged; B still leads on recall.
10. **(Low) Lookahead on the field path** (A3c) and by report date (O8, judgement).

## 13. The single highest-value next fix

Make the top-tier gate fail closed, in one function that every tier-0 or tier-1 candidate passes through, ledger
path and field path alike. A program enters tier 0 or 1 only if all of these hold, and anything not understood
blocks:

1. Every grant that ever covered the buyer territory, and every record that ended it, passes the returned-path
   checks (`_check_ended`), also when a statement is present.
2. The party the position rests on (the licensor, the stating party, the return's recipient) is the landscape
   company, compared on the full name with notes kept as content.
3. Every landscape and analyst U.S.-rights statement and holder for the program is read and agrees. A statement read
   as UNKNOWN, a named third party, or a holder conflict blocks, and is cited.
4. No rejected or unattached rights row could belong to the program (no id, or an id that matches no program).

This closes A1–A5, H2, R-lost and T2 at once. T still needs a stricter reader, but under this rule an unread or
hedged sentence would block instead of pass.
