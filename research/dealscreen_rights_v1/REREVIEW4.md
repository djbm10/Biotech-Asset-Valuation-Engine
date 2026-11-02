# Adversarial re-review 4: cycle R1 revision 5, rights evidence (CLDN18.2)

**AI-SIMULATED INTERNAL REVIEW.** I am an AI (Claude) playing a skeptical pharma BD analyst and auditor. I am not a
human reviewer. I approve nothing, and nothing here is validation. I did not trust REREVIEW3_RESPONSE.md. I checked
each claim by running code or reading outputs. I report only what I ran or read.

Scope and method:
- Revision 5 was the uncommitted working tree on `dealscreen-mvp` when I started. During the review it was committed
  as d1d4b0f ("cycle R1 revisions 2-5"); HEAD is now 1436d95 (a docs commit). I checked the SHA-256 of the 32 files
  (`src/bve/dealscreen/*.py`, `src/bve/cli/dealscreen.py`) against `/tmp/claude-1000/rr5/sha_launch.txt` at the
  start, midway and at the end. No file changed.
- I edited nothing except this file. I did not commit, stash or change git state. ruff ran with `--no-cache`; mypy's
  cache went to `/tmp/claude-1000/rr5/`. Scripts, workspace copies and outputs are in `/tmp/claude-1000/rr5/`.
- Per-program cases: `h5.py` runs one program through `commercial.assess` and `screening.program_transaction` (the
  production per-program step, called at `screening.py:332`). Defaults: landscape company "Nerida Bio", buyer
  territory {US}, as-of 2025-06-01, max age 730 days, `encumbered_rights: deprioritize`. Scripts `rv_reader.py`,
  `rv_gate.py`, `rv_owner_ended.py`, `rv_rows.py`, `rv_clean.py`, `rv_company_note.py`, `rv_text57.py`,
  `rv_v3reader.py`; outputs in `out/`.
- `rv_v3reader.py` reads my phrasings with the revision-3 reader snapshot, to tell new errors from old ones. The
  revision-4 tree was never committed, so I could not run it. REREVIEW3 found revisions 3 and 4 read 56 of 57
  phrasings alike.
- I ran the implementer's probe (`implementer_probe.py`, REREVIEW3's own inputs) unchanged, only to check the
  response's case table. Every other input is mine.
- End to end on copies of the revision-5 CLDN18.2 workspace (`~/.cache/rights_v1/after5c_ws`; C3 buyer, as-of
  2026-10-29), with `import`, `import-rights`, `assert`, `screen`, `export` and `memo` (all in `e2e/`):
  - `ws_a`: rows Y01–Y05 (`rights_a.csv`) and five analyst assertions (`assert.log`).
  - `ws_b`: rows Z01–Z09 (`rights_b.csv`; Z06 has program id `CL-37 (ADC)`) and one analyst assertion.
  - `ws_c`: six landscape cells edited (`in_c/landscape_c.csv`) and China licenses W01–W06 (`rights_c.csv`).
  - `ws_d`: one rejected row (V01, status "Actv") with SKB315's own program id.
  - `ws_0`: an unchanged copy. Its regenerated memo is byte-identical to `after_v5/memo_R1v5.md` (1,701 words).
  - All counterparties are fictional (Tessaly Pharma, Chinaco Pharma, Alpha Bio). Row quotes start "(test)"; URLs
    are `example.test`. A landscape company appears as licensor only so that a row attaches to its program. Nothing
    here is a fact about a real program.
- I re-screened fresh copies of the previous reviewer's 11 workspaces (`re/`).
- Checks: `tests/dealscreen`: 653 passed (116 s). `ruff check --no-cache src/bve/dealscreen src/bve/cli/dealscreen.py`:
  "All checks passed!". `mypy src/bve/dealscreen`: "Success: no issues found in 31 source files". `compare.py`
  against the frozen baseline: "AC8 scientific fields changed: 0 of 62", for `after_v5/screening_R1v5.json` and for
  the after5c workspace. A stricter check of every field except `transaction`, `transaction_rank` and `commercial`
  found 0 differences.

## Summary

- **CLDN18.2: no tier and no call changed.** Only zolbetuximab's reasons and questions changed. Usefulness against
  general Claude (B) is unchanged: 10 right, 4 partial, 1 missed, against B's 14, 1, 0.
- **The response's own cases hold.** Every REREVIEW3 input gives the result the response states. The 13 flagged
  top-tier placements in the previous reviewer's workspaces are gone.
- **The gate is one function now, but it does not fail closed.** It blocks what its reader marks as not understood.
  The reader marks some wrong readings as understood: future dates ("Available 2H27"), a third party's offer ("The
  licensee is seeking a partner for U.S. rights"), and U.S. grants whose "to the U.S." the party-name eraser deletes
  ("with an option to U.S. rights"). A return "to Tessaly Pharma" never contests.
- **The gate reads two of the fields that carry rights text.** It reads U.S.-rights statements and holders. It does
  not read Partnerships or Geographic Notes, notes inside rights-row party names or inside the landscape company
  name, or anything at all when the buyer territory lacks the U.S.
- **The ledger trusts status flags and undated acquisitions.** A "Terminated" or "Expired" status is dated by the
  grant's start date, so it passes the new "ended before every statement" check. A status reported after the as-of
  date still ends the grant. An undated acquisition makes a third party "the company".
- End to end on copies of the CLDN18.2 workspace, test cases take **#1 to #6 of the transaction view in tier 0**
  (ws_a), #1–#2 in tier 0 and #3–#6 in tier 1 (ws_b), and #1–#6 in tier 1 (ws_c).
- **Usefulness:** "Ex-China rights available", usual wording for a Chinese originator, no longer reads as an offer
  (revision 3 read it as one). Company-retains wording and holder legal names with a city note are held back, by
  design.
- Net: the gate closes every input it was built for. The same error class re-enters through the inputs next to them.

Definite new errors (not reported in REREVIEW3.md). None of them occurs in the CLDN18.2 output.

| Severity | Introduced by revision 5 | Claimed fixed, fails on a close variant | Older, first reported here | Total |
|---|---|---|---|---|
| High: tier 0 or 1 while a third party may hold buyer-territory rights, or on contrary, undated, future or unread evidence | 2: R4, TER-G | 5: R1, R2, N, E1, O1 | 4: R5, P, E2, TER-F | **11** |
| Medium: false encumbrance, or a false conflict that changes the tier | 1: K2 | 1: FE4 | 2: RET, TER2 | **4** |
| Low: false label, wording or citation; no tier change | 4: L1, L3, L4, L6 | 0 | 1: L2 | **5** |

Nine of the eleven High errors reach a top tier end to end on a copy of the CLDN18.2 workspace (§2c). TER-F and
TER-G need a buyer territory other than {US}; I showed them per program only.

## 1. REREVIEW3_RESPONSE.md, claim by claim

| § | Claim | Verdict | Evidence (run or read) |
|---|---|---|---|
| 1.1 | Ended grants are checked beside a statement: undated endings, licensor-only endings, undated grants and undated merging acquisitions block; an ending not dated before every statement blocks | **Held for the A1 inputs. Refuted for status-flag endings.** | A1a–A1e RIGHTS_UNRESOLVED (`implementer_probe.out`). A license or option ended only by its status passes beside a statement (E1, E3: tier 0; ws_a ATG-022 #2, ws_b ATG-022 #1). E1-control (a dated termination after the statement) is blocked. |
| 1.2 | The position rests on the landscape company; `_is_company` follows recorded acquisitions; "a statement by another party never names an owner or holder" | **Held for A2, H1, H2, O2, O7. Refuted for undated acquisitions and for notes.** | O1: an undated, uncited acquisition makes Tessaly Pharma's statement the company's; tier 0, `holder='Tessaly Pharma'` (ws_b JS107 #2). N1: maker "TORL Biotherapeutics (U.S. rights licensed to Tessaly Pharma)" is holder and owner in tier 0 (ws_a TORL #6). |
| 1.3 | Every U.S.-rights statement and holder is read on both paths; unread text blocks; a named other party's offer blocks; a noted holder blocks; statements after the as-of date are not applied | **Held for us_rights and us_rights_holder text the reader reads correctly, for a buyer territory with the U.S. Refuted as "every".** | Held: A3a–A3e, A4, A5, A6, T2 (probe). Refuted: Partnerships and Geographic Notes are not read (P); a return to a third party is not a contest (R5); misread text counts as understood (R1, R2, R4); a territory without the U.S. skips the gate (TER-G). |
| 1.4 | Rows not applied guard the programs they may concern, and are listed in JSON, memo and workbook | **Held as stated. Gap for realistic id variants (judgement, §6).** | re/ws_e: JS107 held by row 23 (`CL 24`), LB4330 by rejected row 27 (`CL-041`). ws_b: an accepted row `CL-37 (ADC)` naming TORL Biotherapeutics as licensor of a U.S. license is listed in the memo; TORL stays #6 in tier 1. |
| 1 | Reader: AVAILABLE only when every clause is read; future, hedges and questions never read as availability; the offering party comes from a capitalized subject | **Held for the listed phrases. Refuted for close variants.** | "Available from 2027" is unread. "Available 2H27", "US rights available post-2026", "Available FY27", "Rights available after-2027" read AVAILABLE. "The licensee is seeking a partner for U.S. rights" reads AVAILABLE with no party (§3). |
| 1 | `screening.program_transaction` is the production per-program step | **Held** | `screening.py:275-303`, called at 332. End-to-end results match the per-program results for the same shapes. |
| 2a | A1a–A1e blocked; A1d decided | **Held** | probe. Close variants: E1, E3, O1. |
| 2a | A2a–A2c blocked with the ownership question | **Held** | probe: "Does BigPharma Inc own this program, or hold it under a license from Origin Bio?" |
| 2a | A3a, A3b CONFLICTING; A3c not counted; A3d, A3e decided | **Held** | probe. |
| 2a | T: none of seven phrasings reaches tier 0 | **Held. Close variants reach tier 0.** | probe; R1, R2 (§3). |
| 2a | A7a: a statement covering part of the territory blocks | **Held on the rights-file path. Refuted on the field path.** | TER4 blocked ("covers only part of CA/US"). TER3: buyer {US, CA}, analyst "U.S. rights available": tier 0. |
| 2b | A4: nine cells out of tier 1 | **Held. Close variants reach tier 1.** | probe; R4, R5. |
| 2b | A5a, A5b: a note beside the company name blocks | **Held for landscape and analyst holders. Refuted for rights-row party names and the landscape company name.** | N1–N3, CN1–CN3 (§4). |
| 2b | H1, H2, T2, A6 | **Held** | probe. |
| 2b | C2, O8 kept | Judgements; noted | — |
| 2c | ws_e, ws_f, ws_h, re_ws_b: flagged placements 13 → 0; the others had none | **Held** | Re-screened from fresh copies: no eligible program in tier 0 or 1 in any of the 11 workspaces. ws_e programs are held by their own checks, as stated. |
| 3 | Reader groups (57 phrasings) | **Held** | `rv_text57.out` (60 phrasings from REREVIEW3 §3): none reads AVAILABLE when it should not; negations read NOT_AVAILABLE; "Option available to partners" is unread. |
| 4 | Names: one word list; "U.S." fixed; address rule; "a second party is never cut off" | **Held, with a judgement gap** | G10, G11 tier 1 (probe). D1, D2: "Nerida Bio Inc., Tessaly, US" reads as Nerida Bio at an address; if "Tessaly" is a second party, it is cut off. |
| 5 | C1, G17 kept as usefulness costs; C4/O-12 fixed | **Held** | K10, K11 blocked; probe O-12: "Does BigPharma Inc hold US rights through the option it exercised (2025-04-01)? The option is not in the evidence." |
| 6 | R-lost fixed | **Held** | `rv_rows.out` A1r: a rejected row with id `CL-42` guards all four programs. |
| 6 | Unattached accepted row guards near-id programs (judgement) | **Held as decided; asymmetric (§6)** | A6 (`CL 24`) guards CL-24 only. |
| 7 | G12 tier 1, G13 tier 0, FE cells no longer a U.S. license | **Held. A close variant fails.** | probe; FE4 (§7). |
| 8 | G5b, G6, G8, G10, G11 tier 1; G5 kept | **Held** | probe. |
| 9 | O-1 to O-14 | **Held, except the O-8 wording (L1)** | O-9: ws_b memo lists row 23 with parties. O-13: no codes in any memo I produced (grep). O-14: ws_d blockers column "complete: rights row 18 for this program was rejected at import (unknown status label 'Actv'); the rights evidence is incomplete". |
| 3 | Rows not applied are always reported | **Held in JSON and workbook. Not in the memo for a program with no applied row (L4).** | ws_d SKB315. |
| 3 | A finalist line shows the rights-file position | Read, not run | `memo.py:407-413`; no finalist in any workspace. |
| 3 | Field-path holder conflict names the statement; "not counted" names one cause; reworded blocker | **Held** | probe A3a, A3c, A2a text. |
| 4 | 653 tests, 141 new; ruff and mypy clean | **Held** | 653 passed; 141 collected in `test_rights_rereview3.py`. |
| 4 | Six earlier tests edited, each for a stated rule | **Unverifiable** | Revisions 2–5 are one commit; the revision-4 tree is not available. |
| 4 | 22 of 23 clean cases in a top tier; G17 held | **Held** | probe. |
| 4 | CLDN18.2: no tier, position, rank, holder or staleness changed; zolbetuximab reasons only; memo 1,609 → 1,701 words | **Held** | after_v4 vs after_v5 CSV; ws_0 memo. |
| 4 | 0 of 62 scientific fields changed | **Held** | `compare.py` twice; strict check 0. |
| 4 | Cross-version (312 assets) and cycle-4 equivalence | **Unverifiable** | Not re-run (it needs a checkout of 0ee7752). `~/.cache/rights_v1/xv5/science.json` holds 312 revision-5 assets but not the pre-R1 side. The working-tree `equivalence_result.json` says byte-identical and fast path on all four. |
| 4 | Usefulness 10/4/1 vs 14/1/0 | **Held** | §10. |
| 5 | AC table (implementer's reading) | See §11 | AC2, AC6, AC7 are not met on held-out inputs. |

## 2. Paths into the top tiers

Per-program cases: as-of 2025-06-01, buyer {US} unless stated, landscape company "Nerida Bio". Outputs copied from
`out/rv_gate.out`, `out/rv_owner_ended.out`, `out/rv_company_note.out` and `out/rv_rows.out`.

### 2a. Tier 0 (availability stated, unverified)

| Id | Input | Output (copied) | Expected | Cause |
|---|---|---|---|---|
| R1 | No rights rows. Analyst `us_rights` "US rights available post-2026" (2025-03-01); also "Available 2H26" | `AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED / AVAILABILITY_STATED_UNVERIFIED`; ask "Confirm the U.S.-rights statement against a primary source." | Not a statement about now: unread, blocked | `rights_reader.py:136`: `_CODE` accepts any token mixing letters and digits; `_offer` (193) then accepts "post-2026", "2h26", "fy27", "q3" as program codes |
| R2 | No rows. Analyst "The licensee is seeking a partner for U.S. rights"; also "Our licensee seeks a partner for US rights", "Collaborator open to licensing U.S. rights" | tier 0, `holder=None owner=None`; reason "the U.S.-rights field reads 'The licensee is seeking a partner for U.S. rights' (available (analyst-asserted or -confirmed from a cited source); no rights record)" | Blocked: a third party's offer | `_subject` (`rights_reader.py:170-181`) takes a party only from capitalized words; "licensee", "collaborator", "partner", "acquirer" are in `_VOCAB` (139-151); the gate checks named parties only (`rights_gate.py:147-155`) |
| R3 | No rows. Analyst "U.S. rights available to the licensee"; also "Product available in the US" | tier 0 | A right held by a third party; supply, not rights | "to" and "licensee" are in `_VOCAB`; "product" too |
| P7 | No rows. Analyst `us_rights` "Available" + landscape Geographic Notes "U.S. rights licensed to Tessaly Pharma" | tier 0; `cited=['Available']`; the cell is in no reason | CONFLICTING, citing the cell | `reconcile` reads only `us_rights_all` and `us_rights_holder_all` (`rights_gate.py:210, 218`; `commercial.py:134-135`). geographic_rights is imported (`mapping.py:35`) and assertable (`models.py:144`) but read nowhere |
| P5 | Statement row by Nerida Bio for the US (2025-03-01) + landscape Partnerships "Exclusive U.S. license to Tessaly Pharma (2024)" | `AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED / AVAILABILITY_STATED_UNVERIFIED  <<< TOP holder='Nerida Bio'` | CONFLICTING. On the field path a Partnerships cell already turns "available" into a conflict (`commercial.py:107-109`) | The rights-file path never reads `partnerships` |
| N1 | Statement row, US, 2025-03-01, maker "Nerida Bio (U.S. rights licensed to Tessaly Pharma)" | tier 0, `holder='Nerida Bio (U.S. rights licensed to Tessaly Pharma)' owner='Nerida Bio (U.S. rights licensed to Tessaly Pharma)'` | Blocked: the note names a third-party U.S. license (the A5 rule) | `same_company` drops notes (`rights_territory.py:192-202`, via `split_note` 154-160) and its docstring says "a caller must report them"; `_is_company` (`rights_model.py:57-64`) and `_owner_check` (`rights_checks.py:95-102`) never do. Only landscape and analyst holders report notes (`rights_gate.py:166-172`) |
| CN2 | Landscape company "Nerida Bio (in-licensed from Tessaly Pharma)"; statement row by Nerida Bio | tier 0, `holder='Nerida Bio'` | Blocked: the note says the company is a licensee | same |
| CN3 | Landscape company "Nerida Bio (U.S. rights licensed to Tessaly Pharma)"; no rows; analyst "Seeking a partner for U.S. rights" | tier 0 | Blocked | the field path never reads the company field |
| E1 | US license to Alpha Bio (2024-03-01, status TERMINATED, source 2025-05-01) + statement for the US (2025-03-01) | tier 0; reason "grant to Alpha Bio ended in US per source; not a statement of availability"; no blocker | Blocked, as E1-control: "complete: the end of the license to Alpha Bio (a termination (2025-04-01) naming Alpha Bio) is not dated before every availability statement; …" | A status ending is the grant record itself (`rights_ledger.py:233-235`); `_endings` keeps it (`rights_position.py:387`); its "own date" is the grant's start date, so the checks at `rights_position.py:402-405` pass |
| E3 | US option to Alpha Bio (2024-03-01, status EXPIRED) + statement (2025-03-01) | tier 0; reason "option to Alpha Bio lapsed in US per source; not a statement of availability" | Blocked: the lapse has no date | same |
| O1 | Undated acquisition (acquirer Nerida Bio, target Tessaly Pharma) + statement by Tessaly Pharma for the US (2025-03-01) | tier 0, `holder='Tessaly Pharma' owner='Nerida Bio'`; `cited=[2]` (the statement only) | Blocked: the acquisition has no date (the returned path and the A1d decision block undated acquisitions). At least cite it | `_is_company` follows `ledger.current` (`rights_model.py:62`), built by `_acquisitions` (`rights_ledger.py:138-173`) with no date check; the acquisition is not cited. Control O2 (acquisition dated after the as-of date) is blocked |
| TER-F | Buyer {EU}; no rows; analyst "U.S. rights available" (2025-03-01). Same with buyer {US, CA} | both `AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED / AVAILABILITY_STATED_UNVERIFIED` | {EU}: the statement says nothing about the buyer's territory. {US, CA}: blocked, as on the rights-file path (TER4) | `position_from_field` takes no territory (`transaction.py:155-206`); for {EU} the gate also returns at `rights_gate.py:216` |
| D2 (judgement) | Statement maker "Nerida Bio Inc., Tessaly, US" | tier 0, `holder='Nerida Bio Inc., Tessaly, US'` | An address, or a second party "Tessaly": unclear | `drop_address` (`rights_territory.py:172-189`) drops any one-word tail ending in a known country |
| O3 (judgement, acknowledged) | Company "Nerida"; statement by "Nerida Therapeutics" | tier 0 | — | GENERIC_NAME_WORDS (response §6 #2) |

Accepted tier-0 cases: K7 (analyst "Nerida Bio is seeking a partner for U.S. rights"), K9 (statement by "Nerida Bio
USA, Inc."), E4 (worldwide license, U.S.-only termination before the statement), E5, E6; the implementer's G2, G4,
G9, G13, G18c, K3.

### 2b. Tier 1 (no third-party grant in evidence)

| Id | Input | Output (copied) | Expected | Cause |
|---|---|---|---|---|
| R4 | China license Nerida Bio → Chinaco Pharma (mainland China, 2025-01-01) + landscape `us_rights` (2025-04-01): "Licensed in Greater China, with an option to U.S. rights"; "Licensed in China and Japan, extended to the U.S. in 2024"; "Licensed in Japan to Kappa Ltd, later expanded to North America"; "Licensed in China, option to US" | each `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE`; only the license row is cited; the cell is in no reason | CONFLICTING, citing the cell. Revision 3 read all four ENCUMBERED (`rv_v3reader.out`) | `_PARTY_SPAN` (`rights_reader.py:133`) reads "to US", "to the US", "with US" and "to North America" as party names; `_covers_us` (161) deletes them before looking for the U.S.; the option or grant clause becomes "consistent" (221, 223). Reading: UNKNOWN, understood |
| R5 | China license + cell "U.S. rights returned to Tessaly Pharma"; also "Tessaly Pharma regained U.S. rights" | tier 1, `owner='Nerida Bio'`; the cell is not cited | CONFLICTING: the rights went to a party that is not the company | RETURNED is not in `CONTESTS` (`rights_reader.py:44`); the reader keeps no recipient; `_read_statements` has no branch for it (`rights_gate.py:135-155`) |
| L-R | China license + cell "Available 2H26", or "The licensee is seeking a partner for U.S. rights" | tier 1; the cell is not cited | Blocked (R1, R2) | As R1, R2; an understood offer beside a clear position is silently consistent |
| P1–P4, P6 | China license + Partnerships cell "Exclusive U.S. license to Tessaly Pharma (2024)" (P1); the same as an analyst assertion (P2); Geographic Notes "U.S. rights licensed to Tessaly Pharma; China to Chinaco Pharma" (P3); analyst geographic_rights "Tessaly Pharma: U.S. and Europe" (P4); a dated return + Partnerships "U.S. co-promotion with Tessaly Pharma" (P6) | each tier 1; only the rows are cited | CONFLICTING, citing the text | As P5, P7 |
| N2, N3 | Return-only row, recipient "Nerida Bio (on behalf of Tessaly Pharma)" (N2); China license from "Nerida Bio (U.S. sublicensed to Tessaly Pharma)" (N3) | tier 1; N3 `owner='Nerida Bio (U.S. sublicensed to Tessaly Pharma)'` | Blocked | As N1 |
| CN1 | Landscape company "Nerida Bio (U.S. rights licensed to Tessaly Pharma)"; China license from Nerida Bio | tier 1, `owner='Nerida Bio'` | Blocked | As N1 |
| E2 | US license to Alpha Bio (2024-03-01), status TERMINATED in a source dated 2025-09-01, after the as-of date 2025-06-01 | `RIGHTS_RETURNED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE` | Not known on the as-of date: LICENSED, or at least blocked | `after_as_of` tests the event's own date window (`rights_ledger.py:113`); the status is applied whatever its source date (233-235). Not O8: there the termination was dated before the as-of date |
| TER-G | Buyer {EU}; China license + landscape holder "Tessaly Pharma (worldwide licensee)" | tier 1; reason "the landscape also names a U.S. rights holder or labeler: Tessaly Pharma (worldwide licensee)" | Blocked (note) or CONFLICTING (holder) | `reconcile` returns when "US" is not in the territory (`rights_gate.py:216`) |
| ROW (judgement) | China license + an accepted row with id `CL-24 (ADC)` (U.S. license to Tessaly Pharma); also ids `RC-148 (ADC)`, `CLDN-24`, `LB4330-01` | no program guarded (`rv_rows.out`) | The row may concern CL-24 | `near_key` keeps extra tokens (`rights_gate.py:272-275`): "cl24adc" is not "cl24" |
| D1 (judgement) | China license + holder "Nerida Bio Inc., Tessaly, US" | tier 1 | As D2 | As D2 |

Accepted tier-1 cases: K12 (dated return + "U.S. rights returned to Nerida Bio (2025)"), O4 (licensor "Nerida Bio
International"), O5; the implementer's G1, G1b, G3, G5b, G6, G7, G8, G10, G11, G12, G14–G16, G18, G18b, K1.

### 2c. End to end on copies of the CLDN18.2 workspace (C3 buyer, as-of 2026-10-29)

Outputs copied from `e2e/memo_a.md`, `memo_b.md`, `memo_c.md` and `show_*.out` (the screening JSON).

| Workspace | Program | Input added (all fictional) | Output (copied) | Finding |
|---|---|---|---|---|
| ws_a | QLS31905 | Analyst us_rights "The licensee is seeking a partner for U.S. rights" (2026-09-01) | "#1 QLS31905: availability stated, unverified; rights position: availability stated by a source (unverified)" | R2 |
| ws_a | ATG-022 | Y03 US license Antengene Biologics → Alpha Bio, 2025-03-01, status "Terminated", source 2026-08-01; Y04 "Seeking partner" by Antengene Biologics, US, 2026-06-01 | "#2 ATG-022: availability stated, unverified; … grant to Alpha Bio ended in US per source; not a statement of availability" | E1 |
| ws_a | JS107 | Analyst us_rights "Seeking a partner for U.S. rights"; analyst geographic_rights "U.S. rights licensed to Tessaly Pharma (2025)" | "#3 JS107: availability stated, unverified"; the workbook shows both assertions in the same row | P |
| ws_a | BL-M05D1 | Y01 "Seeking partner" by Sichuan Baili Pharmaceutical, US, 2026-06-01; analyst partnerships "Exclusive U.S. license to Tessaly Pharma (2025)" | "#4 BL-M05D1: availability stated, unverified; … stated by Sichuan Baili Pharmaceutical" | P |
| ws_a | SKB315 | Analyst us_rights "Available 2H27" (2026-09-01) | "#5 SKB315: availability stated, unverified; rights position: availability stated by a source (unverified) (the U.S.-rights field reads 'Available 2H27' …" | R1 |
| ws_a | TORL-2-307-ADC | Y02 "Seeking partner", licensor "TORL Biotherapeutics (U.S. rights licensed to Tessaly Pharma)", US, 2026-06-01 | "#6 TORL-2-307-ADC: availability stated, unverified"; "ask: Confirm with TORL Biotherapeutics (U.S. rights licensed to Tessaly Pharma) that US rights are unencumbered and available, and on what terms." | N |
| ws_b | ATG-022 | Z07 US option to Alpha Bio, 2025-03-01, "Expired", source 2026-08-01; Z08 statement, 2026-06-01 | "#1 ATG-022: availability stated, unverified; … option to Alpha Bio lapsed in US per source" | E1 (E3) |
| ws_b | JS107 | Z03 acquisition: NingBo Junyan Hongshi Biosciences acquires Tessaly Pharma, no dates; Z04 "Seeking partner" by Tessaly Pharma, US, 2026-06-01 | "#2 JS107: availability stated, unverified; … stated by Tessaly Pharma"; only row 21 cited; "ask: Confirm with Tessaly Pharma that US rights are unencumbered and available, and on what terms." | O1 |
| ws_b | QLS31905 | Z01 China license; analyst geographic_rights "U.S. rights licensed to Tessaly Pharma (2025)" | "#3 QLS31905: no third-party grant in evidence"; "Analyst-entered facts. 1 cited assertion(s) by HUMAN reviewer(s) changed gate decisions for 0 program(s); 0 override a different source value; no effect on: QLS31905." | P |
| ws_b | SKB315 | Z02 US license to Alpha Bio, 2025-03-01, "Terminated", source 2026-12-15 (after the as-of date) | "#4 SKB315: no third-party grant in evidence; rights position: rights returned per evidence"; evidence "2025-03-01 (source 2026-12-15) license" | E2 |
| ws_b | Spevatamig (PT886) | Z09 China license from "Phanes Therapeutics (U.S. sublicensed to Tessaly Pharma)" | "#5 Spevatamig (PT886): no third-party grant in evidence"; "(licensor per evidence: Phanes Therapeutics (U.S. sublicensed to Tessaly Pharma))" | N |
| ws_b | TORL-2-307-ADC | Z05 China license; Z06 accepted, id `CL-37 (ADC)`, U.S. license TORL Biotherapeutics → Tessaly Pharma | "#6 TORL-2-307-ADC: no third-party grant in evidence"; "row 23 ('CL-37 (ADC)', license, 2026-03-01; Tessaly Pharma from TORL Biotherapeutics; United States)" | ROW (judgement) |
| ws_c | QLS31905 | US Rights cell "Licensed in Greater China, with an option to U.S. rights"; W01 China license | "#1 QLS31905: no third-party grant in evidence"; the cell is cited nowhere | R4 |
| ws_c | ATG-022 | Partnerships cell "Exclusive U.S. license to Tessaly Pharma (2025)"; W05 | "#2 ATG-022: no third-party grant in evidence" | P |
| ws_c | JS107 | US Rights cell "U.S. rights returned to Tessaly Pharma"; W02 | "#3 JS107: no third-party grant in evidence"; workbook field "RIGHTS RETURNED TO ORIGINATOR (source-provided; not a statement of availability)" | R5 |
| ws_c | BL-M05D1 | US Rights cell "The licensee is seeking a partner for U.S. rights"; W06 | "#4 BL-M05D1: no third-party grant in evidence"; workbook field "CONFLICTING SOURCES" in the same row | R2 |
| ws_c | SKB315 | US Rights cell "Licensed in China and Japan, extended to the U.S. in 2024"; W03 | "#5 SKB315: no third-party grant in evidence" | R4 |
| ws_c | TORL-2-307-ADC | Geographic Notes "U.S. rights licensed to Tessaly Pharma; China to Chinaco Pharma"; W04 | "#6 TORL-2-307-ADC: no third-party grant in evidence" | P |

`assert` refused "Licensed in Greater China, with an option to U.S. rights" as an analyst value ("cannot be read as a
us_rights value, so it could not change any decision"). So R4 enters only through landscape cells. It also refused
every us_rights assertion whose quote began "(test) " ("the quoted evidence does not" state that status), so the
analyst assertions above quote the value verbatim.

## 3. The strict reader (`rights_reader.py`)

Readings copied from `out/rv_reader.out`.

| Group | Text | Reads | A careful reader | Effect |
|---|---|---|---|---|
| Dates as codes (R1) | "U.S. rights available Q3", "Available 2H26", "Available in 1H2027", "US rights available post-2026", "Partner sought 2H22", "Available FY27", "Rights available after-2027", "Available Q4-2026 for all territories" | AVAILABLE_PER_SOURCE, understood | Future or past, not now | Analyst: tier 0 (ws_a #5) |
| Control | "Available from Q1-2027" | UNKNOWN, unread | — | blocked |
| Role nouns (R2) | "The licensee is seeking a partner for U.S. rights", "Licensee seeking a co-development partner", "Our licensee seeks a partner for US rights", "The collaborator is seeking a partner for U.S. rights", "The acquirer is open to a deal", "Collaborator open to licensing U.S. rights", "Its partner is seeking a licensee" | AVAILABLE, parties [] | A third party's offer | tier 0 (ws_a #1) |
| Control | "Partner is seeking a licensee for U.S. rights" | AVAILABLE, parties ['Partner'] | — | blocked by the gate (a named party) |
| Offers to a party (R3) | "U.S. rights available to the partner", "Rights available to collaborator", "Available to licensee", "U.S. rights available to the licensee", "Available to 3SBio", "Open to 3SBio" | AVAILABLE, parties [] | A right held by a third party | tier 0 |
| U.S. erased as a party (R4) | "Licensed in Japan to Kappa Ltd, later expanded to North America", "Licensed in China and Japan, extended to the U.S. in 2024", "Licensed in Greater China, with an option to U.S. rights", "Licensed in China, option to US", "Licensed in China, co-promotion with US partner", "Licensed in China to Chinaco Pharma, sublicensed to US partner" | UNKNOWN, understood | A U.S. grant or option | tier 1, cell dropped (ws_c #1, #5) |
| Control | "Exclusive license in Korea; rights expanded to the United States" | UNKNOWN, unread | — | blocked |
| Return to a third party (R5) | "U.S. rights returned to Tessaly Pharma", "Rights reverted to Tessaly Pharma (licensor) in 2024", "Tessaly Pharma regained U.S. rights", "US rights returned to licensor Tessaly Pharma" | RIGHTS_RETURNED, understood | Tessaly holds U.S. rights | tier 1 (ws_c #3) |
| Retained by (RET) | "US rights retained by Nerida Bio", "Rights retained by the company", "Global rights retained by Nerida Bio" | NOT_AVAILABLE | The company holds them | false encumbrance (§7) |
| Retained, other forms | "Nerida Bio retains U.S. rights", "Retained", "Company retains all rights outside Greater China", "Wholly owned by Nerida Bio" | UNKNOWN, unread | The company holds them | blocked (§8) |
| Exclusion offers | "Ex-China rights available", "Rights outside China available" | UNKNOWN, understood | An offer that covers the U.S. | not counted (§8) |
| Return, then offer | "Rights returned by Tessaly Pharma; seeking partner" | CONFLICTING | Consistent | false conflict (K2) |
| ROFN | "Seeking partner; Tessaly Pharma holds ROFN", "Available, ROFN to Tessaly Pharma", "Available (Tessaly Pharma has ROFN)" | UNKNOWN, unread | Encumbered | blocked (correct) |

Causes. `_CODE` (`rights_reader.py:136`) accepts any token that mixes letters and digits, so date tokens pass as program
codes (193). `_VOCAB` (139-151) holds other parties' role nouns ("licensee", "collaborator", "partner", "acquirer"),
"to" and "product"; `_subject` (170-181) names a party only from capitalized words, so a lower-case third party is no
party. `_PARTY_SPAN` (133) matches "to US", "to the US", "with US" and "to North America" because "US" and "North"
are capitalized; `_covers_us` (161) deletes the span before it looks for the U.S. "rights retained by" is in
`_NOT_AVAILABLE` (108) whoever retains them, while plain "U.S. rights retained" is consistent (129-130, 224). The
offer path treats an exclusion ("Ex-China") as a list of other places (226-229), although `_covers_us` reads the same
exclusion as covering the U.S. (165).

Old or new (`out/rv_v3reader.out`): revision 3 already read R1, R2, R3, R5, RET and FE4 the same way. R4 and K2 are
new: revision 3 read the R4 texts as ENCUMBERED and K2 as RETURNED. "Ex-China rights available" read AVAILABLE in
revision 3 and does not now.

## 4. Owner check and names

| Id | Input | Output | Verdict | Cause |
|---|---|---|---|---|
| N1–N3 | Notes in rights-row party names (§2) | tier 0 or 1, holder or owner printed with the note | **Definite, High** | `split_note` inside `same_company`; no caller reports the note on the rights-file path |
| N4 | China license; licensee "Chinaco Pharma (and Tessaly Pharma for the U.S.)" | tier 1, the licensee note unread | Part of N | same |
| CN1–CN3 | Note in the landscape company name | CN1 tier 1, CN2 tier 0, CN3 tier 0 | **Definite, High** (part of N) | same; the field path never reads the company field |
| O1 | Undated acquisition (§2a) | tier 0 | **Definite, High** | `rights_model.py:62`, `rights_ledger.py:138-173` |
| O2 | Acquisition dated after the as-of date | blocked; "not applied, dated after the as-of date 2025-06-01: an acquisition (2025-09-01) naming Nerida Bio" | Correct | |
| O3 | "Nerida" / "Nerida Therapeutics" | tier 0 | Judgement (acknowledged) | GENERIC_NAME_WORDS |
| O4 | Licensor "Nerida Bio International" | tier 1 | Acceptable (affiliate) | |
| O5 | Company "Nerida Bio (Suzhou) Co., Ltd."; rows "Nerida Bio" | tier 1 | Correct | |
| O6/K1, K14 | Holder "Nerida Bio (Suzhou) Co., Ltd." / "Nerida Bio, Inc. (Delaware)" | blocked: "the note 'Suzhou' is not read, and it may name a third party" | Usefulness cost (by design, §8) | `rights_gate.py:166-172` |
| O7 | Company Tessaly Pharma; China license Nerida → Chinaco; statement by Tessaly | blocked, with the ownership question | Correct | |
| K10, K11 | Company "Nerida Biotherapeutics, Inc." / "Jiangsu Nerida Bio Co., Ltd."; rows "Nerida Bio" | blocked | Usefulness cost (acknowledged C1, G17) | |
| D1, D2 | "Nerida Bio Inc., Tessaly, US" | read as Nerida Bio | Judgement | `drop_address` |

Real CLDN18.2 company names carry city notes too: seven landscape companies have one, e.g. "Innovent Biologics
(Suzhou) Co. Ltd.", "Zai Biopharmaceutical (Suzhou) Co., Ltd.". Written that way as a U.S. rights holder, each would
be held back by the note rule.

## 5. Ended grants, ordering, acquisitions, partial exercises, co-development exits, as-of

| Id | Input | Output | Verdict |
|---|---|---|---|
| E1 | Status-flag ending + statement (§2a) | tier 0 | **Definite, High** |
| E1-control | Same, ending as a dated termination (2025-04-01) after the statement | blocked ("is not dated before every availability statement") | Correct |
| E2 | Status reported after the as-of date (§2b) | tier 1, RETURNED | **Definite, High** |
| E3 | Option EXPIRED by status + statement | tier 0 | **Definite, High** (same cause as E1) |
| E4 | Worldwide license to Alpha; termination for the United States only (2025-01-15); statement (2025-03-01) | tier 0 | Correct |
| E5 | Return-only row to the company (2024-09-01) + later Japan license + statement | tier 0 | Correct |
| E6 | Co-development ended by both (2025-02-01) + statement | tier 0 | Correct |
| E7 | Worldwide option; U.S. exercise (2024-06-01); then a lapse naming the holder | `LICENSED_IN_TERRITORY_PER_EVIDENCE / DEPRIORITIZED holder='Alpha Bio'` | Correct |
| O1, O2 | §4 | | |

## 6. Rows not applied

| Case | Input | Output | Verdict | Cause |
|---|---|---|---|---|
| A6 | Accepted row, id `CL 24` | guards CL-24 only | Held | |
| A7 | Rejected row with the program's own id `RC148` | guards RC148 | Held | |
| A1r | Rejected row, transposed id `CL-42` | guards all four programs | Held (R-lost fix) | |
| A1 | The same row, accepted | guards none | Judgement: asymmetric. An accepted row with a wrong id may belong to any program, just like a rejected one | `row_guards` (`rights_gate.py:296-333`) |
| A2–A5 | Accepted rows with ids `CL-24 (ADC)`, `RC-148 (ADC)`, `CLDN-24`, `LB4330-01` | guard none (`near_key`: 'cl24adc', 'rc148adc', 'cldn24', 'lb43301') | Judgement with safety impact: realistic id variants | `near_key` (`rights_gate.py:272-275`) |
| ws_b | `CL-37 (ADC)`, a U.S. license by TORL Biotherapeutics | listed in the memo with its parties; TORL-2-307-ADC #6 in tier 1 | The row names the program's own company as licensor; nothing links them | as A2 |
| ws_d | Rejected row with SKB315's own id (U.S. license to Tessaly Pharma, status "Actv") | JSON and workbook: "complete: rights row 18 for this program was rejected at import (unknown status label 'Actv'); the rights evidence is incomplete". Memo: "#6 SKB315: rights unresolved; no rights record; first contact: registry sponsor 'Sichuan Kelun-Biotech Biopharmaceutical Co., Ltd.'" | Tier right (2). The memo hides the row (L4). The reason omits the row's parties and territory | `memo.py:388-391` |

## 7. False encumbrance, false conflict, wrong holder, wrong owner

| Id | Input | Output (copied) | Expected | Kind and cause |
|---|---|---|---|---|
| FE4 | No rows; analyst "Licensed in China and Japan and available in US" | `LICENSED_IN_TERRITORY_PER_EVIDENCE / DEPRIORITIZED` | An offer of U.S. rights, or at least not encumbered | False encumbrance (Medium). `rights_reader.py:213-217` splits into "Licensed in China", "Japan", "available in US"; "Japan" is unread, so the whole clause falls to `_GRANT` (222-223) and `_covers_us` sees "US" |
| RET | No rows; analyst "US rights retained by Nerida Bio"; cell "Rights retained by the company"; China license + cell "Global rights retained by Nerida Bio" | `NOT_AVAILABLE_PER_SOURCE / DEPRIORITIZED` (first two); `CONFLICTING_EVIDENCE / RIGHTS_UNRESOLVED` (third) | The company holds the rights: tier 2 with no rows, tier 1 beside the China license | False encumbrance and false conflict (Medium). `rights_reader.py:108` |
| K2 | Dated return of Alpha Bio's U.S. license (2025-02-01) + cell "Rights returned by Alpha Bio in 2025; seeking a partner" | `CONFLICTING_EVIDENCE / RIGHTS_UNRESOLVED holder='Nerida Bio (recorded; conflicting)'` | tier 1 | False conflict (Medium), new: RETURNED and AVAILABLE clauses give CONFLICTING (`rights_reader.py:240`), which contests (`CONTESTS`, 44) |
| TER2 | Buyer {EU}; no rows; cell "Licensed to Tessaly Pharma for the U.S. only" | `LICENSED_IN_TERRITORY_PER_EVIDENCE / DEPRIORITIZED` | Not an EU encumbrance | False encumbrance (Medium); `transaction.py:155-206` |
| N1 | §2a | holder and owner "Nerida Bio (U.S. rights licensed to Tessaly Pharma)" | not established | Wrong holder (part of N) |
| O1 | ws_b JS107 | holder "Tessaly Pharma", owner "NingBo Junyan Hongshi Biosciences" | not established | Wrong holder (part of O1) |

## 8. Over-caution: clean cases held back (usefulness costs, not safety errors)

| Id | Input | Revision 5 | Verdict | Cause |
|---|---|---|---|---|
| U1 (K6) | No rows; analyst "Ex-China rights available" (the company's press release) | `NO_RIGHTS_EVIDENCE / RIGHTS_UNRESOLVED`; "DealScreen does not read it as a statement that rights are available, licensed or returned" | **Definite; regression** (revision 3 read AVAILABLE). Usual wording for a Chinese originator | `rights_reader.py:184-196, 226-229` |
| U2 (K3, K4, K5, K13) | China license + cell "Nerida Bio retains U.S. rights" / "Wholly owned by Nerida Bio" / "Company retains all rights outside Greater China" / "Retained" | blocked: "which DealScreen cannot read as a rights statement" | By design (fail closed); a real cost | `_NO_GRANT`, `_RETAINED` accept only bare forms (`rights_reader.py:92-97, 129-130`) |
| U3 (K1, K14) | China license + holder "Nerida Bio (Suzhou) Co., Ltd." / "Nerida Bio, Inc. (Delaware)" | blocked; "Does the note 'Suzhou' that the landscape writes beside Nerida Bio Co., Ltd. mean that a third party holds U.S. rights?" | By design (A5); a real cost (see §4) | `rights_gate.py:166-172` |
| K2, RET | §7 | | Medium errors that also hold clean cases back | |
| K8 | China license + analyst "Nerida Bio is seeking a partner for U.S. rights" | tier 1; the statement is not cited | Judgement: an understood company offer is ignored and not shown | `rights_gate.py:147-155` |
| K10, K11 | Name splits | blocked | Acknowledged (C1, G17) | |
| — | "Returned; now seeking a partner" | UNKNOWN, unread ("Returned") | Minor | |

## 9. Output honesty (memo, workbook, `assert` note)

In favour: the CLDN18.2 memo (ws_0, identical to after_v5) calls nothing available or open; "available" appears only
in the buyer's statement and the disclaimer. No memo I produced has codes in prose. Every holder and owner in the
CLDN18.2 output is cited by row. The memo lists unattached rows with their parties (ws_b). The workbook blockers
column carries rows not applied (ws_d).

| # | Where | Output (copied) | Problem | Cause |
|---|---|---|---|---|
| L1 | ws_a memo, line 9 | "A source states availability for 6 (read by rule, unverified); 6 pass every rights check (a recent dated statement, attributed to the program's company or to no other party, contradicted by no other cited evidence and by no rights row left unapplied)." | The number counts programs with no blocker. The description is false for these six: "Available 2H27" is not about now; "The licensee …" is another party; TORL's maker names Tessaly's U.S. license; JS107 and BL-M05D1 carry contrary analyst assertions | `memo.py:456-462` |
| L2 | ws_a memo, line 56 | "rights assertions changed no gate but feed the transaction view for: QLS31905 (availability stated, unverified), SKB315 (availability stated, unverified), BL-M05D1 (availability stated, unverified), JS107 (availability stated, unverified)" | BL-M05D1's only assertion is partnerships "Exclusive U.S. license to Tessaly Pharma (2025)". It fed nothing; the line pairs it with "availability stated" | `memo.py:258-267`, `_RIGHTS_FIELDS` (327) |
| L3 | CLI `assert` | "DealScreen reads it as: available." for "The licensee is seeking a partner for U.S. rights" and for "Available 2H27"; nothing printed for the geographic_rights and partnerships assertions | The note does not show that the party and the date were not read. No warning that a geographic_rights assertion has no effect | `cli/dealscreen.py:101-111, 445-446` |
| L4 | ws_d memo | "#6 SKB315: rights unresolved; no rights record; first contact: registry sponsor 'Sichuan Kelun-Biotech Biopharmaceutical Co., Ltd.'" | A rights row for this program exists (rejected: a U.S. license to Tessaly Pharma). The memo never mentions it | `memo.py:388-391`; `_import_issue_lines` (336-359) lists only rows of no program |
| L6 | CLDN18.2 zolbetuximab (JSON, workbook) | "Does the note 'U.S. labeler per FDA label; not a rights statement' that the landscape writes beside Astellas Pharma US, Inc. mean that a third party holds U.S. rights?" | The note says itself that it is not a rights statement | `rights_gate.py:169-172` |
| (P) | ws_c workbook, BL-M05D1 | field "CONFLICTING SOURCES"; tier "NO_THIRD_PARTY_GRANT_IN_EVIDENCE"; blockers column empty | Two columns of one row disagree | part of P |
| (N) | ws_a TORL | "Confirm with TORL Biotherapeutics (U.S. rights licensed to Tessaly Pharma) that US rights are unencumbered and available, and on what terms." | A tier-0 question that quotes a third-party U.S. license | part of N |
| (O1) | ws_b JS107 | only row 21 cited; holder "Tessaly Pharma", owner "NingBo Junyan Hongshi Biosciences" | The acquisition that links them is not cited (AC10) | part of O1 |
| (E2) | ws_b SKB315 | "2025-03-01 (source 2026-12-15) license" | A source after the as-of date decides a top-tier position; nothing flags it | part of E2 |
| (R2) | ws_a QLS31905 | "ask: Confirm the U.S.-rights statement against a primary source." | No question asks who "the licensee" is (AC11) | field-path questions |

## 10. CLDN18.2 measured against the reference and B

### 10a. What changed from revision 4

| Program | Revision 4 | Revision 5 | Effect |
|---|---|---|---|
| Zolbetuximab | two questions; evidence rows "1" | adds "the landscape also names a U.S. rights holder or lab[eler] …" and the note question (L6); evidence rows "1;1" | Tier unchanged (excluded as marketed) |
| All 62 | | tiers, positions, ranks, holders and staleness identical (after_v4 vs after_v5 CSV) | No change in calls |
| Memo | 1,609 words | 1,701 words | Wording only |

### 10b. Error classes against the reference

| Error class | Baseline | R1 | Rev 2 | Rev 3 | Rev 4 | Rev 5 |
|---|---|---|---|---|---|---|
| False "unobstructed" (third-party U.S. rights shown OPEN or in a top tier) | 4 definite + zanidatamab | 0 | 0 | 0 | 0 | **0** |
| False encumbrance | 0 | 0 definite, 2 likely outdated | same | same | same | **same** (EO-3021, SYSA1801; stale-flagged) |
| Wrong holder | n/a | 3 | 1, labelled | 1, labelled | 1, labelled | **1, labelled** (LM-302: "Turning Point Therapeutics (recorded; conflicting)") |
| Wrong territory reading | n/a | 1 | 0 | 0 | 0 | **0** |
| Missed return | n/a | 1 | 1 | 1 | 1 | **1** (SKB315) |

### 10c. Usefulness against general Claude (B), the 15 deal programs

| Program | DealScreen revision 5 | Score | B | Change from rev 4 |
|---|---|---|---|---|
| CL-01 zolbetuximab | OWNER_ACQUIRED Astellas; excluded (marketed); stale | right | right | a question added |
| CL-02 IMAB362 | OWNER_ACQUIRED Astellas; stale | right | right | none |
| CL-03 AZD0901 / CL-04 CMG901 | LICENSED AstraZeneca, global; stale | right / right | right / right | none |
| CL-05 sonesitatug vedotin | NO_RIGHTS_EVIDENCE; identity flag to AZD0901 | partial | right | none |
| CL-06 IBI343 | LICENSED Takeda ex-Greater China | right | right | none |
| CL-07 LM-302 | CONFLICTING; Turning Point "(recorded; conflicting)" | partial | right | none |
| CL-08 SHR-A1904 | OPTION_HELD Merck KGaA; stale | right | right | none |
| CL-11 XNW27011 | LICENSED Astellas ex-Greater China | right | right | none |
| CL-13 givastomig | SHARED, I-Mab and ABL Bio | right | right | none |
| CL-14 EO-3021 | LICENSED Elevation; stale | partial | right | none |
| CL-15 SYSA1801 | same as CL-14 | partial | partial | none |
| CL-26 RC148 | LICENSED AbbVie ex-Greater China | right | right | none |
| CL-27 SKB315 | NO_RIGHTS_EVIDENCE | missed | right | none |
| CL-30 FL-301 | LICENSED Leap, rows 16 and 17; stale | right | right | none |
| **Totals** | | **10 right / 4 partial / 1 missed** | **14 / 1 / 0** | unchanged |

Notes:
- DealScreen still wins on audit and restraint. B still wins on recall. No advantage is demonstrated.
- None of this review's errors shows in the CLDN18.2 output. That landscape has no US Rights or Geographic Notes text
  and one holder cell; its rights file has no availability statements. The errors need realistic vendor or analyst
  text that this landscape does not contain.
- Recall risk: "Ex-China rights available", the usual wording in a Chinese company's release, no longer counts as an
  offer.

## 11. Acceptance criteria

| AC | Verdict | Evidence |
|---|---|---|
| AC1 | PASS | Imports through the profile with provenance. "Actv" is rejected and printed ("REJECTED rights row 18: unknown status label 'Actv'", ws_d). |
| AC2 | PARTIAL | CLDN18.2: no OPEN tier; no output says available. Held-out: "Available 2H27" and "The licensee is seeking a partner for U.S. rights" reach tier 0 end to end (ws_a #5, #1); the memo then says all six "pass every rights check" (L1). |
| AC3 | PARTIAL | Rights-file territories parse; A7a decided; FE non-U.S. grants fixed. Not met: U.S. grants hidden by the party eraser (R4); the field path ignores the buyer territory (TER-F, TER2); the gate skips territories without the U.S. (TER-G); holder and owner printed with third-party notes (N). |
| AC4 | PARTIAL | Clean returns, G5b, G8, G18 work. Not met: status-flag endings beside a statement (E1); a status reported after the as-of date (E2); a return to a third party is not a contest (R5); K2 false conflict; LM-302 still not RETURNED (data). |
| AC5 | PASS on my inputs | Partial exercise then lapse keeps the U.S. license (E7); expired options are cleared (E3's ordering problem is AC7). |
| AC6 | PARTIAL | Readable statements and plain holders conflict on both paths (A3, A4, A6, T2). Not met: Partnerships and Geographic Notes (P), returns to a third party (R5), misread offers (R2, R4), notes in rights-row and company names (N). False conflicts: K2, RET. |
| AC7 | PARTIAL | A3c and G6 fixed; dated endings ordered against statements. Not met: undated status endings (E1, E3), a status reported after the as-of date (E2), an undated acquisition (O1), future-dated availability counted as current (R1). |
| AC8 | PASS | 0 of 62 (compare.py, twice; strict check 0). Cross-version and cycle-4 equivalence: result files only, not re-run. |
| AC9 | PARTIAL | Encumbered treatment, returned preference and age work. The territory preference is not applied on the field path (TER-F, TER2) or in the gate (TER-G). |
| AC10 | PARTIAL | CLDN18.2 holders cited. Not met: contrary text the gate does not read is cited nowhere in the transaction (P, R4, R5); the acquisition behind O1 is not cited; a program's own rejected row is hidden in the memo (L4). |
| AC11 | PARTIAL | Ownership questions work (A2, H1, H2, O7). Not met: field-path tier-0 entries ask only "Confirm the U.S.-rights statement against a primary source." (R2: who is "the licensee"?); N1 asks to confirm with a party whose name quotes a third-party license; L6. |
| AC12 | PASS | 0 matches for 230 CLDN18.2 strings (programs, aliases, companies, partners, rights-file parties and their first words) in the 17 `src/` files changed since 0eb739e; the only hit, "single", is ordinary English from a trial-design alias. |
| AC13 | PARTIAL | Unchanged: IBI343 and SHR-A1904 not unobstructed; RC148, FL-301, XNW27011 encumbered; LM-302 CONFLICTING, not returned. |
| AC14 | FAIL | 11 new High and 4 new Medium errors on held-out inputs; none in the CLDN18.2 output. |

## 12. Remaining issues, ranked

1. **(Safety, High) The gate passes what its reader misreads as understood.** Date tokens as codes (R1), third-party
   role nouns and offers to a party (R2), U.S. grants erased as party names (R4), returns to a third party (R5). End
   to end: ws_a #1, #5 in tier 0; ws_c #1, #3, #4, #5 in tier 1.
2. **(Safety, High) The gate reads too few inputs.** Partnerships and Geographic Notes (P), notes in rights-row and
   company names (N), and nothing when the buyer territory lacks the U.S. (TER-G). End to end: ws_a #3, #4, #6 in
   tier 0; ws_b #3, #5 and ws_c #2, #6 in tier 1.
3. **(Safety, High) The ledger dates status flags by the grant date and trusts undated acquisitions** (E1, E3, E2,
   O1). End to end: ws_a #2 and ws_b #1, #2 in tier 0; ws_b #4 in tier 1.
4. **(Safety, High) The field path ignores the buyer territory** (TER-F; also the false encumbrance TER2).
5. **(Safety, judgement) Unattached accepted rows guard only near ids**; suffixed ids and wrong ids guard nothing,
   while the same row rejected guards everything (ROW).
6. **(Medium) False encumbrance and false conflict:** "retained by the company" (RET), FE4, K2.
7. **(Usefulness) "Ex-China rights available" no longer reads as an offer** (U1, regression); company-retains wording
   and city notes in legal names are held back (U2, U3); C1/G17 name splits.
8. **(Low) Output honesty:** the availability sentence describes checks that do not hold (L1); "feed the transaction
   view" for an assertion that fed nothing (L2); the `assert` note hides what was not read (L3); a program's own
   rejected row hidden in the memo (L4); the zolbetuximab note question (L6).
9. **(Recall) The rights file caps recall** (LM-302's successor, SKB315's return, EO-3021's discontinuation).
   Unchanged; B still leads.

## 13. The single highest-value next fix

Invert the gate's default. Today an input blocks only if the reader proves it contrary or marks it unread. Make every
rights-bearing input prove it is consistent, or block, cited:

1. Read every non-empty U.S.-rights, holder, Partnerships and Geographic Notes value (landscape and analyst), every
   note in any party name (rights rows and the landscape company included), and do so for every buyer territory.
2. Count a value as consistent only if it is a placeholder, a bare no-grant phrase, a plain name of the company, or
   an offer built from a closed word list with no digits other than a program id, no party nouns ("licensee",
   "partner", "collaborator", "acquirer") and no "to …"; a RETURNED reading counts only if it names the company as
   recipient. Everything else, including UNKNOWN text the reader thinks it understood, blocks. A bare list of
   organisation names in Partnerships is not rights evidence (design constraint) and may stay neutral.

This closes R1, R2, R4, R5, P, N and TER-G (seven of the eleven High errors) in one place. It will hold back more
clean cases; pair it with an explicit allow-list for "Ex-China rights available" and company-retains wording, which
are the costs that matter most for Chinese originators. The next two fixes are smaller: date a status-flag ending as
undated and apply it only from its source date (E1, E2, E3), require an own date on or before the as-of date before an
acquisition changes who the company is (O1); and make the field path apply only to a buyer territory of exactly {US}
(TER-F, TER2).
