# Adversarial re-review 5: cycle R1 revision 6, rights evidence (CLDN18.2)

**AI-SIMULATED INTERNAL REVIEW.** I am an AI (Claude) playing a skeptical pharma BD analyst and auditor. I am not a
human reviewer. I approve nothing, and nothing here is validation. I did not trust REREVIEW4_RESPONSE.md. I checked
each claim by running code or reading outputs. I report only what I ran or read.

Scope and method:
- Revision 6 is the uncommitted working tree on `dealscreen-mvp` (HEAD 1436d95; revision 5 = d1d4b0f). I recorded the
  SHA-256 of every file in `src/bve/dealscreen/` at the start (`/tmp/claude-1000/rr6/sha_start.txt`) and checked it
  midway and at the end. No file changed.
- I edited nothing except this file. No commit, stash or git change. ruff ran with `--no-cache`; mypy's cache went to
  `/tmp/claude-1000/rr6/`. All my scripts, workspace copies and outputs are in `/tmp/claude-1000/rr6/`.
- Per-program cases go through `screening.program_transaction` (the production per-program step) via the previous
  reviewer's harness `h5.py` (copied unchanged). Defaults: landscape company "Nerida Bio", buyer {US}, as-of
  2025-06-01, max age 730 days, `encumbered_rights: deprioritize`. Scripts: `p_forms.py` (plain forms and the reader),
  `a_gate.py`, `a_ledger.py`, `a_rows.py`, `a_clean.py`; outputs in `out/`.
- Revision 5 comparison: `git archive d1d4b0f src/bve` into `rr6/rev5/` (read-only use of git objects). The same
  scripts run against it give `out/*_rev5.out`, so I can tell new errors from old.
- End to end on copies of the revision-6 CLDN18.2 workspace (`~/.cache/rights_v1/after6_ws`; C3 buyer, as-of
  2026-10-29), with `import`, `import-rights`, `assert`, `screen`, `export` and `memo` (all in `rr6/e2e/`):
  - `ws_e`: rights rows X01–X07 (`rights_e.csv`) and five analyst assertions (`assert.log`; reviewer kind
    SYNTHETIC_FIXTURE).
  - `ws_f`: five landscape cells edited (`in_f/landscape_f.csv`) and China licenses X01–X04, X06 (`rights_f.csv`).
  - `ws_d`: one rejected row (V01, status "Actv") with SKB315's own id.
  - `ws_0`: an unchanged copy. Its memo is byte-identical to `after_v6/memo_R1v6.md`; its transaction view is
    identical to `after_v6/screening_R1v6.json`.
  - Counterparties are fictional (Tessaly Pharma, Chinaco Pharma, Alpha Bio, Kappa Ltd). Row quotes start "(test)";
    URLs are `example.test`. A landscape company appears as licensor only so a row attaches to its program, and in
    two texts as the subject of "retains". Nothing here is a fact about a real program.
- I re-screened fresh copies of the previous reviewer's workspaces ws_a–ws_d (`rr6/re5/`).
- Checks: `tests/dealscreen`: **744 passed** (95 s). `test_rights_rereview4.py`: 91 tests collected. ruff: "All checks
  passed!". mypy `src/bve/dealscreen`: "Success: no issues found in 32 source files". `compare.py` against the
  frozen baseline: "AC8 scientific fields changed: 0 of 62" for `after_v6` and for `ws_e`. A strict check of every
  field except `transaction`, `transaction_rank` and `commercial`: 0 differences.

## Summary

- **CLDN18.2: no tier, position, rank or holder changed from revision 5.** `after_v5` and `after_v6`
  `after_transaction.csv` are identical. Only seven memo lines changed ("no rights record" → "no rights record
  applied"). Usefulness against general Claude (B) is unchanged: 10 right / 4 partial / 1 missed, against B's 14 / 1 / 0.
- **The response's own cases hold.** Every REREVIEW4 High and Medium input I re-ran is out of tiers 0 and 1, or no
  longer a false conflict. The 18 flagged top-tier placements in the previous reviewer's workspaces are gone.
- **The inverted default did not fail closed. The plain forms are new paths in.** They are word patterns run on
  lower-cased text. Lower-casing makes "U.S." invisible inside a party name. A pronoun ("it", "the owner") counts as
  the company. A note inside the text is dropped. "Other places" means "not the U.S.", whatever the buyer territory.
- **It is a regression on the U.S.-rights field.** The gate now accepts a plain form even when the reader marks the
  text unread. Four landscape U.S.-rights texts that revision 5 blocked or called conflicting now reach tier 1.
- **Inputs still not read:** a rights row's own quote; a Partnerships value that states ownership without a "rights
  word" ("Owned by Tessaly Pharma").
- End to end, test inputs take **#1 in tier 0 and #2–#7 in tier 1** (ws_e; #6 is a judgement case) and **#1–#5 in
  tier 1** (ws_f).
- **Usefulness:** company-retains wording, "Ex-China rights available" and city names in legal names now reach the top
  tier, as promised. New costs: "Open to partnering discussions", "Partnered in China; U.S. rights available",
  "Worldwide rights (ex-China) available" and similar ordinary phrasings are now held back.

Definite new errors (not reported in REREVIEW4.md). None occurs in the CLDN18.2 output.

| Severity | Introduced by revision 6 | Claimed fixed, fails on a close variant | Older, first reported here | Total |
|---|---|---|---|---|
| High: tier 0 or 1 while a third party may hold buyer-territory rights, or on contrary or unread evidence | 2: PF1, PF2 | 3: PF3, PF4, OWN | 1: QUOTE | **6** |
| Medium: false encumbrance, false conflict, or a missed encumbrance that changes the tier | 1: TER-M | 0 | 1: ORCD | **2** |
| Low: false label, wording or citation; no tier change | 4: L1b, L2b, L3b, LBL | 1: NH | 1: WB | **6** |

PF1, PF2 and PF3 also hit the U.S.-rights field itself, where revision 5 blocked them (§2c). All six High errors reach
a top tier end to end (§2d).

## 1. REREVIEW4_RESPONSE.md, claim by claim

| § | Claim | Verdict | Evidence (run or read) |
|---|---|---|---|
| 1 | Plain forms: an offer with "no party but the program's company"; company keeps rights; return to the company; "a grant over named places other than the U.S. only"; anything else blocks | **Refuted as a safety rule.** Each form has inputs that fit its words and mean the opposite | PF1: "Licensed to Tessaly Pharma (U.S.) and to Chinaco Pharma in China" → "a grant over other places only". PF2: "Licensed to Tessaly Pharma in Japan; it holds U.S. rights" → "rights kept by the company". PF3: "Rights retained by Nerida Bio (Tessaly Pharma holds U.S.)" → "rights kept by the company" (`out/p_forms.out`) |
| 1 | Every input is read: statements, holders, Partnerships, Geographic Notes | **Held for those four fields. Refuted as "every".** | Not read: a rights row's quote (QUOTE); a Partnerships value with ownership words but no "rights word" (OWN) |
| 1 | The gate runs for every buyer territory | **Held literally. Refuted in effect.** | The gate runs, but its plain forms are U.S.-centric: an EU, CA or JP grant to a third party is "a grant over other places only" for an EU, US+CA or JP buyer (PF4) |
| 1 | Notes in names block wherever they appear | **Held for names on cited rows, holders and the company. Refuted for notes inside a rights text** | A7 (note on an uncited older Japan row) blocks. PF3 passes. N2, N3 still print the noted name as holder or owner (NH) |
| 1 | One-word place before the corporate form is part of the legal name | **Held** (judgement kept on "Inc. (Delaware)") | "Nerida Bio (Suzhou) Co., Ltd." tier 1; "Nerida Bio, Inc. (Delaware)" blocked. Side effect: "Nerida Bio (Tessaly) Inc." also passes (judgement, §4) |
| 1 | Ledger: status after the as-of date not applied (E2); status-only ending beside a statement blocks (E1, E3); undated acquisition blocks (O1) | **Held** | E2 → `LICENSED_IN_TERRITORY_PER_EVIDENCE / DEPRIORITIZED`; E1, E3, O1 blocked (`out/rv_owner_ended.out`). Gap: a status with no source date at all is applied (S2, judgement, §5) |
| 1 | Field path only for a buyer territory of exactly {US} | **Held. Side effect refuted as harmless** | TER1, TER3 → NO_RIGHTS_EVIDENCE with the stated reason. TER-M: a {US, CA} buyer loses a U.S. license cell entirely (§6) |
| 1 | Reader: R1, R2, R3, R4, RET, FE4, K2, U1 | **Held** | `out/rv_reader.out`, `out/rv_gate.out`, `out/rv_clean.out` |
| 1 | Rows: `ids_close`; company-party rows when the id points nowhere; transposed id guards nothing | **Held as stated** | `out/rv_rows.out`: `CL-24 (ADC)`, `RC-148 (ADC)`, `CLDN-24`, `LB4330-01` each guard their program. (The file `rr5/out/rv_rows_v6.out` shows 0 for these; it predates the current tree. My re-run shows 1.) Gaps and breadth: §6 |
| 2 | R1, R2/R3, R4, R5, E1/E3, E2, O1, TER-F, TER2, K2/FE4/RET, U1, U2, U3 as tabled | **Held** for the listed inputs | My re-runs of `rv_gate`, `rv_owner_ended`, `rv_clean`, `rv_company_note`, `rv_text57` match the implementer's `rr5/out/*_v6.out` byte for byte |
| 2 | P: P1–P7 blocked; names-only Partnerships neutral | **Held for P1–P7. Close variants pass** | PF1–PF3 in Partnerships/Geographic Notes; OWN |
| 2 | N, CN: block; N1 no longer sets the holder | **Held for N1, CN1–CN3. Partly refuted** | N2 holder 'Nerida Bio (on behalf of Tessaly Pharma)', N3 owner 'Nerida Bio (U.S. sublicensed to Tessaly Pharma)' (blocked, but printed: NH). PF3 |
| 2 | TER-G | **Refuted on a close variant** | PF4 |
| 2 | L1 availability sentence | **Partly held** | New wording, but it says DealScreen found "nothing else in the record that it cannot read" while it never reads row quotes (L1b) |
| 2 | L2 analyst-facts paragraph | **Partly held** | Fields are listed now. It still says "the transaction view reads them" for a Partnerships value the CLI says is not read (L2b) |
| 2 | L3 `assert` note | **Partly held** | It reports the gate's verdict, and so repeats its errors: a U.S. grant "accepted as a plain form (a grant over other places only)"; "Owned by Tessaly Pharma" is "names of organisations only" (L3b) |
| 2 | L4 own rejected row shown | **Held** | ws_d: "#7 SKB315: rights unresolved; no rights record applied (rights row 18 for this program was rejected at import (unknown status label 'Actv'); the rights evidence is incomplete)" |
| 2 | L6, D1, D2 unchanged | Judgements; noted | D1, D2 still tier 1 / tier 0 (`out/rv_gate.out`) |
| 3 | 743 tests pass, 90 new; ruff, mypy clean | **Held, numbers off by one** | 744 passed; 91 collected in `test_rights_rereview4.py`; ruff, mypy clean |
| 3 | Reviewer's scripts re-run: every High/Medium case out of the top tiers; K1, K3–K6, K13, FE3, O6 now top tier; K8 cited | **Held** | `out/rv_*.out` |
| 3 | Reviewer's workspaces 18 → 0 flagged top-tier placements; Spevatamig in ws_a is the unflagged control | **Held** | Fresh copies re-screened (`rr6/re5/*.show`): the only top-tier program is ws_a #1 Spevatamig |
| 3 | CLDN18.2: no tier, position, rank, holder or blocker changed; memo wording only | **Held** | CSVs identical; memo diff is seven lines; ws_0 reproduces after_v6 exactly |
| 3 | 0 of 62 scientific fields changed | **Held** | `compare.py` (after_v6 and ws_e); strict check 0 |
| 3 | Cross-version 312 assets; cycle-4 equivalence byte-identical | **Unverifiable** (not re-run) | Result files only: `~/.cache/rights_v1/xv6/`, `cycle4/equivalence_result.json` says byte_identical and fast_path on all four |
| 3 | Usefulness 10/4/1 vs B 14/1/0 | **Held** | §8 |
| 5 | "The plain forms are word patterns … a reviewer should try phrasings that fit a form and mean something else" | **Confirmed**: §2 | |

## 2. Paths into the top tiers

### 2a. The plain forms (`rights_allow.plain_form`), read alone

From `out/p_forms.out` (company "Nerida Bio", as-of 2025-06-01).

| Text | `plain_form` | Reader | Meaning |
|---|---|---|---|
| "Licensed to Tessaly Pharma (U.S.) and to Chinaco Pharma in China" | a grant over other places only | ENCUMBERED | Tessaly holds the U.S. |
| "China license to Chinaco Pharma, with Tessaly Pharma for the U.S." | a grant over other places only | UNKNOWN, unread | same |
| "Licensed in China to Tessaly Pharma, also covering the U.S." | a grant over other places only | ENCUMBERED | same |
| "Licensed in Greater China to Chinaco Pharma, which holds the U.S. too" | a grant over other places only | ENCUMBERED | Chinaco holds the U.S. |
| "Licensed to Tessaly Pharma in Japan; it holds U.S. rights" | a grant over other places only; rights kept by the company | UNKNOWN, unread | "it" is Tessaly |
| "Japan license to Tessaly Pharma; it retains U.S. rights" | same | UNKNOWN, unread | ambiguous at best |
| "The owner holds U.S. rights" | rights kept by the company | UNKNOWN, unread | who is the owner? |
| "Rights retained by Nerida Bio (Tessaly Pharma holds U.S.)" | rights kept by the company | UNKNOWN, unread | Tessaly holds the U.S. |
| "U.S. rights were returned to Nerida Bio Inc. (Tessaly) in 2024" | rights returned to the company | RETURNED | note dropped |
| "Licensed in Europe to Tessaly Pharma"; "EU license to Tessaly Pharma"; "Licensed in Canada to Tessaly Pharma" | a grant over other places only | UNKNOWN | other places only for a U.S. buyer; the buyer's own place for an EU or CA buyer |
| "Ex-Europe rights available" | an offer | AVAILABLE | for an EU buyer: Europe is not offered |
| "Owned by Tessaly Pharma", "Bought by Tessaly Pharma", "Tessaly Pharma (owner)" | None; `is_rights_text` False | — | a third party owns the program; as a Partnerships value it is never read |

Causes:
- **PF1.** `_clause_form` casefolds the text first (`rights_allow.py:120`). The grant form then checks the party span
  with `regions_named(party)` (`rights_allow.py:139`). "US" is matched only in capitals (`rights_territory.py:36`),
  and `_prepare` has already turned "U.S." and "United States" into "US"; after casefolding it is "us", which is
  never a place. So no U.S. mention after "to <party>" or after a comma is ever seen.
- **PF2.** `_GENERIC_SUBJECT` holds "we", "it", "the owner", "owner" (`rights_allow.py:37`); `_is_company` returns True
  for any of them, and for no subject at all (`rights_allow.py:78-82`). Clauses are judged one by one
  (`rights_allow.py:149-155`), so "it" in the second clause is never tied to the party in the first.
- **PF3.** `_is_company` calls `same_company`, which drops notes in parentheses or brackets
  (`rights_territory.py:209`). Its docstring says "a caller must report them"; `rights_allow` does not.
- **PF4.** "Other places" is hard-coded as "not the U.S." (`rights_allow.py:88`, `rights_allow.py:138`), and
  `plain_form` takes no territory. The gate calls it for every buyer territory since revision 6
  (`rights_gate.py:161`, `rights_gate.py:181`).
- **OWN.** `is_rights_text` (`rights_allow.py:159-169`) has no ownership words ("owned", "owner", "owns", "bought",
  "merged", "spun out"). A Partnerships value without one is skipped (`rights_gate.py:177`).
- **Why PF1–PF3 are a regression on the U.S.-rights field:** `_read_statements` accepts any statement whose reading is
  not a contest and that has a plain form (`rights_gate.py:161`). It no longer checks `understood`. In revision 5 an
  unread statement blocked.

### 2b. Per program (`out/a_gate.out`, revision 5 in `out/a_gate_rev5.out`)

Rights-file path: one China license row Nerida Bio → Chinaco Pharma (mainland China, 2025-01-01), plus one text.

| Id | Input | Revision 6 output (copied) | Revision 5 | Expected | Cause |
|---|---|---|---|---|---|
| PF1 | landscape us_rights cell "China license to Chinaco Pharma, with Tessaly Pharma for the U.S." (also as an analyst assertion) | `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE  <<< TOP`; reason "the landscape also states 'China license to Chinaco Pharma, with Tessaly Pharma for the U.S.' (a grant over other places only)" | RIGHTS_UNRESOLVED (blocked, unread) | CONFLICTING, or at least blocked | §2a PF1 |
| PF1 | geographic_rights "Licensed to Tessaly Pharma (U.S.) and to Chinaco Pharma in China"; Partnerships "China license to Chinaco Pharma, with Tessaly Pharma for the U.S."; geographic "Licensed in Greater China to Chinaco Pharma, which holds the U.S. too"; Partnerships "Licensed in China to Tessaly Pharma, also covering the U.S." | each tier 1, `<<< TOP` | tier 1 (fields not read, P) | CONFLICTING | §2a PF1 |
| PF2 | us_rights cell "Licensed to Tessaly Pharma in Japan; it holds U.S. rights"; us_rights cell "The owner holds U.S. rights" | each tier 1; reason "(a grant over other places only; rights kept by the company)" | RIGHTS_UNRESOLVED (blocked) | blocked | §2a PF2 |
| PF2 | geographic "Licensed to Tessaly Pharma in Japan; it holds U.S. rights"; Partnerships "Japan license to Tessaly Pharma; it retains U.S. rights" | tier 1 | tier 1 (not read) | blocked | §2a PF2 |
| PF3 | us_rights cell "Rights retained by Nerida Bio (Tessaly Pharma holds U.S.)" | tier 1; reason "(rights kept by the company)" | `CONFLICTING_EVIDENCE / RIGHTS_UNRESOLVED` | CONFLICTING or blocked | §2a PF3 |
| PF3 | us_rights cell "U.S. rights were returned to Nerida Bio (on behalf of Tessaly Pharma) in 2024"; geographic "Rights retained by Nerida Bio (Tessaly Pharma holds U.S.)"; Partnerships "Wholly owned by Nerida Bio [U.S. sublicensed to Tessaly Pharma]" | tier 1 | tier 1 | blocked | §2a PF3 |
| PF4 | buyer {EU}: China license + geographic "Licensed in Europe to Tessaly Pharma" | tier 1 | tier 1 | CONFLICTING (an EU license to a third party) | §2a PF4 |
| PF4 | buyer {EU}: China license + us_rights cell "EU license to Tessaly Pharma" | tier 1 | tier 1 | CONFLICTING | same |
| PF4 | buyer {EU}: China license + Partnerships "Ex-Europe rights available" | tier 1 | tier 1 | blocked | same |
| PF4 | buyer {US, CA}: China license + geographic "Licensed in Canada to Tessaly Pharma" | tier 1 | tier 1 | CONFLICTING | same |
| PF4 | buyer {EU}: availability row for Europe (2025-03-01) + analyst us_rights "Licensed in Europe to Tessaly Pharma" | `AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED / AVAILABILITY_STATED_UNVERIFIED  <<< TOP` | tier 0 | CONFLICTING | same |
| PF4 | buyer {JP}: China license + geographic "Licensed in Japan to Kappa Ltd" (`out/ter_extra.out`) | tier 1; reason "the landscape geographic rights note 'Licensed in Japan to Kappa Ltd' (a grant over other places only)" | — | CONFLICTING | same |
| OWN | China license + Partnerships "Owned by Tessaly Pharma"; also "Bought by Tessaly Pharma", "Tessaly Pharma (owner)" | tier 1; the value is cited nowhere in the position | tier 1 (not read) | blocked | §2a OWN |
| QUOTE | Availability row by Nerida Bio, US, 2025-03-01, quote "(test) Nerida Bio: U.S. rights available after Tessaly Pharma's option expires in 2027" | `AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED / AVAILABILITY_STATED_UNVERIFIED  <<< TOP` | tier 0 | blocked: the statement is about the future and names a third-party option | The gate never reads a row's `evidence_quote`; it is carried only for display (`rights_model.py:84`). Older (since R1) |
| QUOTE | China license row with quote "(test) Chinaco Pharma licenses China rights and an option on U.S. rights" | tier 1 | tier 1 | blocked | same |

Controls that held: an older Japan row whose licensee carries a note (A7) blocks; an acquirer with a note (A7b) blocks;
the field path blocks PF2 and PF3 texts asserted alone (A2-field, A3-field); B3 (a confirmed agent finding
"U.S. rights licensed to Tessaly Pharma") blocks.

### 2c. The U.S.-rights field regression, end to end (ws_f)

Landscape US Rights cells edited, one China license row each (X01–X04, X06). Outputs copied from `e2e/memo_f.md`.

| # | Program | Input | Memo (copied) |
|---|---|---|---|
| 1 | QLS31905 | US Rights "China license to Chinaco Pharma, with Tessaly Pharma for the U.S." | "#1 QLS31905: no third-party grant in evidence; … the landscape also states 'China license to Chinaco Pharma, with Tessaly Pharma for the U.S.' (a grant over other places only)" |
| 2 | JS107 | US Rights "The owner holds U.S. rights" | "#2 JS107: no third-party grant in evidence; … (rights kept by the company)" |
| 3 | BL-M05D1 | US Rights "Rights retained by Sichuan Baili Pharmaceutical (Tessaly Pharma holds U.S.)" | "#3 BL-M05D1: no third-party grant in evidence; … (rights kept by the company)" |
| 4 | SKB315 | US Rights "Licensed to Tessaly Pharma in Japan; it holds U.S. rights" | "#4 SKB315: no third-party grant in evidence; … (a grant over other places only; rights kept by the company)" |
| 5 | TORL-2-307-ADC | Geographic Notes "Licensed in China to Tessaly Pharma, also covering the U.S." | "#5 TORL-2-307-ADC: no third-party grant in evidence" |

The workbook beside #1 and #3: "U.S.-rights field in the landscape, as read" = "UNKNOWN", tier
"NO_THIRD_PARTY_GRANT_IN_EVIDENCE", blockers column empty (WB). `assert` refused these four U.S.-rights texts as
analyst values ("cannot be read as a us_rights value"), so PF1–PF3 enter the U.S.-rights field through landscape
cells, and the other fields through analyst assertions (ws_e).

### 2d. End to end through assertions and rows (ws_e)

Outputs copied from `e2e/memo_e.md` and `e2e/show_e.out`.

| # | Program | Input added (fictional parties) | Output (copied) | Finding |
|---|---|---|---|---|
| 1 | ATG-022 | X05 "Seeking partner" by Antengene Biologics, US, 2026-06-01, quote "(test) Antengene: U.S. rights available once Tessaly Pharma's U.S. option expires in 2027" | "#1 ATG-022: availability stated, unverified; … stated by Antengene Biologics"; "ask: Confirm with Antengene Biologics that US rights are unencumbered and available, and on what terms." | QUOTE |
| 2 | QLS31905 | X01 China license; analyst geographic_rights "Licensed to Tessaly Pharma (U.S.) and to Chinaco Pharma in China" | "#2 QLS31905: no third-party grant in evidence; … an analyst assertion geographic rights note 'Licensed to Tessaly Pharma (U.S.) and to Chinaco Pharma in China' (a grant over other places only)" | PF1 |
| 3 | JS107 | X04 China license; analyst partnerships "Owned by Tessaly Pharma" | "#3 JS107: no third-party grant in evidence; rights position: no grant over the buyer territory per evidence (recorded grants do not cover US; …)"; the assertion is not in the line | OWN |
| 4 | BL-M05D1 | X03; analyst geographic_rights "Rights retained by Sichuan Baili Pharmaceutical (Tessaly Pharma holds U.S.)" | "#4 BL-M05D1: no third-party grant in evidence; … (rights kept by the company)" | PF3 |
| 5 | SKB315 | X02; analyst geographic_rights "Licensed to Tessaly Pharma in Japan; it holds U.S. rights" | "#5 SKB315: no third-party grant in evidence; … (a grant over other places only; rights kept by the company)" | PF2 |
| 6 | Spevatamig (PT886) | X07 U.S. license Phanes → Alpha Bio, 2025-03-01, status "Terminated", no source date | "#6 Spevatamig (PT886): no third-party grant in evidence; rights position: rights returned per evidence (grant to Alpha Bio ended in US per source; …)" | S2 (judgement, §5) |
| 7 | TORL-2-307-ADC | X06; analyst partnerships "China license to Chinaco Pharma, with Tessaly Pharma for the U.S." | "#7 TORL-2-307-ADC: no third-party grant in evidence; … (a grant over other places only)" | PF1 |

## 3. Over-caution and usefulness (`out/a_clean.out`, revision 5 in `out/a_clean_rev5.out`)

These are usefulness costs, not safety errors.

| Input | Revision 6 | Revision 5 | Note | Cause |
|---|---|---|---|---|
| China license + cell "Nerida Bio retains all ex-China rights" / "… worldwide rights outside Greater China" / "Nerida Bio Co., Ltd. retains rights outside of Greater China" | tier 1 | blocked | **Improved** (U2) | `_RETAINS` |
| No rows; analyst "Ex-China rights available" | tier 0 | NO_RIGHTS_EVIDENCE | **Improved** (U1) | |
| Holder "Nerida Bio (Shanghai) Co., Ltd." / "(Suzhou) Co., Ltd." | tier 1 | blocked | **Improved** (U3) | `content_note` |
| Current China-only license; dated owner statement; returned (dated termination) then a dated statement | tier 1; tier 0; tier 0 | same | Clean cases reach the top | |
| China license + cell "Partnered in China; U.S. rights available" | blocked | tier 1 | **New cost.** Common wording | the grant form needs "licensed"/"license" (`rights_allow.py:69-75`) |
| China license + cell "Worldwide rights (ex-China) available" | blocked | tier 1 | **New cost** | "(" is not an offer word (`rights_allow.py:43-52`) |
| China license + cell "Seeking partner(s) for development and commercialization outside China" | blocked | tier 1 | **New cost** | same |
| "Open to partnering discussions": China license + cell; and no rows + analyst assertion | blocked; field path tier 0 lost | tier 1; tier 0 | **New cost.** The reader reads AVAILABLE; the gate refuses it | "discussions", "offers" not in `_OFFER_WORDS` |
| "Open to co-promotion in the U.S." (both paths) | blocked | tier 1; tier 0 | **New cost** | "co-promotion" not in `_OFFER_WORDS` |
| Company "Nerida Bio (Hong Kong) Limited" + statement row by Nerida Bio | blocked ("the note 'Hong Kong' is not read") | tier 0 | **New cost**; a two-word city is a note | `_IN_LEGAL_NAME` allows one word (`rights_territory.py:164`) |
| Holder "Nerida Bio (Hong Kong) Limited", "Nerida Bio Co., Ltd. (Suzhou)" | blocked | blocked | Unchanged cost | |
| "Rights returned by Alpha Bio in 2025; seeking a partner" beside a dated return (K2) | blocked | CONFLICTING | No false conflict now; still held back | "returned by" is no plain form |
| "U.S. and EU rights available", "Available for licensing in North America and Europe", "Nerida Bio retains U.S. and EU rights", "Seeking a licensee or acquirer" | blocked | blocked | Unchanged cost | closed word list |
| An unattached row for another program of a landscape company (id `AZ-904`, licensor Big Pharma AB) | guards all three of that company's programs (`out/a_rows.out`, R9) | — | **New cost.** A vendor deals export usually covers a company's whole pipeline; each unrelated row would hold every program of that company. No effect on CLDN18.2 (no unattached rows) | `rights_gate.py:401-402` |

## 4. Names

| Id | Input | Output | Verdict | Cause |
|---|---|---|---|---|
| NH | N2 return recipient "Nerida Bio (on behalf of Tessaly Pharma)"; N3 licensor "Nerida Bio (U.S. sublicensed to Tessaly Pharma)"; A7b acquirer "Omega Holdings (U.S. rights to Tessaly Pharma)" | blocked, but `holder='Nerida Bio (on behalf of Tessaly Pharma)'`; `owner='Nerida Bio (U.S. sublicensed to Tessaly Pharma)'`; `holder=owner='Omega Holdings (U.S. rights to Tessaly Pharma)'` | **Low**: the response says "N1 no longer sets the holder"; these close variants still print the noted name as holder or owner | `_return_only` (`rights_position.py:375-381`), `owner()` (`rights_ledger.py:383-392`) |
| — | Holder cell or company "Nerida Bio (Tessaly) Inc." / "Nerida Bio (Tessaly) Co., Ltd." | tier 1 / tier 0; revision 5 blocked | **Judgement.** Any one word in parentheses before a corporate form is dropped, so a one-word partner name ("(Tessaly)") is read as a city | `rights_territory.py:164-171` |
| — | Holder "Nerida Biopharma (Suzhou) Co., Ltd." | `CONFLICTING_EVIDENCE` | Unchanged (C1 name split) | `same_company` |
| — | CLDN18.2 landscape: five company names carry a parenthesis ("Innovent Biologics (Suzhou) Co. Ltd." etc.) | `content_note` finds no note in any | Correct | |

## 5. Ledger

| Id | Input | Output | Verdict |
|---|---|---|---|
| E1, E2, E3, O1 | REREVIEW4 inputs | blocked; E2 LICENSED | Held |
| S1, S5 | U.S. license to Alpha (2024-03-01), status TERMINATED, source 2025-05-01; no statement | `RIGHTS_RETURNED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE`; current judged on the grant date | As accepted in REREVIEW3 (G5 judgement); not an error |
| S2 | Same, **no source date** (also S3: option EXPIRED, no source date) | tier 1; ws_e #6 end to end | **Judgement with safety impact.** The E2 fix applies only when a source date is after the as-of date (`rights_ledger.py:240`). A vendor status with no date reflects the export, which may be after the as-of date. Unknown is treated as known before |
| T1 | U.S. license 2024-03-01; termination dated 2025-04-01, reported 2025-09-01 (after the as-of date) | tier 1 | Judgement (O8, kept); inconsistent with the E2 rule for status flags |
| Q1, Q3 | Acquisition of the company by Tessaly (dated, or dated only by its report) | `OWNER_ACQUIRED_PER_EVIDENCE`, owner Tessaly, tier 1 | By design: the acquirer is the owner, not a licensee; it is named and cited |
| I1 | U.S. license Nerida Bio → "Nerida Bio USA, Inc." | `LICENSED / DEPRIORITIZED`, holder 'Nerida Bio USA, Inc.' | Older judgement: an intra-group license reads as an encumbrance (`ledger.same` uses exact keys, `same_company` would merge) |

## 6. Territory and rows

| Id | Input | Output (copied) | Expected | Verdict and cause |
|---|---|---|---|---|
| TER-M | Buyer {US, CA}, `encumbered_rights: exclude`; no rows; cell "Exclusive U.S. license to Tessaly Pharma (2024)" | `NO_RIGHTS_EVIDENCE / RIGHTS_UNRESOLVED`; "the landscape's U.S.-rights fields speak to the U.S. only; the buyer territory is CA/US, so they are not read as a position there"; cited=[] | Encumbered in part of the territory; excluded by the buyer's preference. Same cell, buyer {US}: `EXCLUDED_BY_BUYER_PREFERENCE` | **Medium, introduced by revision 6.** The TER-F fix drops the field for every territory but {US}, including territories that contain the U.S. (`screening.py:294-302`) |
| PF4 | §2b | | | High |
| R2 | Unattached row, id "Spevamab" (program "Spevamab (PX886)"), licensee only | guards nothing | guard the program | Gap: `ids_close` needs a digit in the shorter id, and the company-party rule needs a named company (`rights_gate.py:361-362, 401`). Listed in the memo's import issues. Judgement |
| R3 | Unattached row, id "NB-71", licensor "Nerida Biotherapeutics" | guards nothing | guard NB-7 | Gap: name variant (C1 class). Judgement |
| R9 | §3 | | | Usefulness cost |
| CLDN18.2 | — | `rights_import_issues`: no unattached or rejected rows; no program has a row guard | — | No guard is broad on this workspace |

## 7. Output honesty

In favour: the CLDN18.2 memo (ws_0, identical to after_v6) calls nothing available or open. No memo I produced has
codes in prose; the only all-caps token is the reviewer kind "SYNTHETIC_FIXTURE". Every holder and owner in the
CLDN18.2 output is cited by row. L4 is fixed.

| # | Where | Output (copied) | Problem | Cause |
|---|---|---|---|---|
| L1b | ws_e memo, line 9 | "A source states availability for 1 (read by rule, unverified); for 1 DealScreen found nothing else in the record that it cannot read or that contradicts the statement. This is not a check that any statement is true: …" | The program is ATG-022, whose own row quote names Tessaly's U.S. option. DealScreen never reads row quotes, so "nothing … that it cannot read" is false | `memo.py:479` |
| L2b | ws_e memo, line 59 | "rights assertions changed no gate; the transaction view reads them, as one input among the rights evidence, for: … JS107 (asserted: partnerships; transaction view now: no third-party grant in evidence)" | The CLI told the analyst this value "is not read as rights evidence and changes no transaction tier" | `memo.py:269` |
| L3b | CLI `assert` (`e2e/assert.log`) | "The top-tier gate accepts it as a plain form (a grant over other places only); it is still unverified." for "Licensed to Tessaly Pharma (U.S.) and to Chinaco Pharma in China"; "DealScreen reads this Partnerships value as names of organisations only" for "Owned by Tessaly Pharma" | The note repeats PF1 and OWN as fact. Latent: for an unread U.S.-rights text the note says it "keeps the program out of the top two transaction tiers", but the gate passes such a text when it has a plain form (`out/l3_notes.out`); `assert` refuses those values first, so the analyst does not see it | `cli/dealscreen.py:102-125` |
| LBL | ws_e, ws_f memo and workbook | "(a grant over other places only)" beside a text naming a U.S. licensee | A false description in the output (part of PF1) | `rights_gate.py:163, 183` |
| LBL | B3: confirmed finding "U.S. rights licensed to Tessaly Pharma" | position `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE`; blocker "uncontested: an analyst-confirmed finding reads 'U.S. rights licensed to Tessaly Pharma' …" | Contrary Partnerships or Geographic Notes text blocks but is labelled "uncontested", never CONFLICTING (AC6) | `_read_other` has no contest branch (`rights_gate.py:169-187`) |
| WB | ws_f workbook, QLS31905 and BL-M05D1 | "U.S.-rights field in the landscape, as read" = "UNKNOWN"; tier "NO_THIRD_PARTY_GRANT_IN_EVIDENCE"; blockers empty | One row says the field was not read; the tier rests on reading it as plain | §2a |
| (OWN) | ws_e JS107 | memo line cites only the China license; the Partnerships assertion appears only in the Screening and Diligence sheets | AC10: the contrary text is cited nowhere in the transaction | §2a OWN |
| (QUOTE) | ws_e ATG-022 | "ask: Confirm with Antengene Biologics that US rights are unencumbered and available" | No question names Tessaly's option, although the cited quote does (AC11) | QUOTE |
| (older) | ws_d SKB315 | "rights row 18 for this program was rejected at import (unknown status label 'Actv')" | The reason still omits the row's parties and territory (a U.S. license to Tessaly Pharma). Noted in REREVIEW4 | `rights_gate.py:447-449` |

## 8. CLDN18.2 measured against the reference and B

### 8a. What changed from revision 5

| Item | Revision 5 | Revision 6 |
|---|---|---|
| `after_transaction.csv` (62 programs: tier, rank, position, holder, staleness, reasons, questions, rows) | — | identical |
| Memo | 1,701 words | 1,708 words; seven lines read "no rights record applied" |
| Scientific fields vs frozen baseline | 0 of 62 | 0 of 62 (`compare.py`); strict check 0 |

### 8b. Error classes against the reference (`reference_calls.csv`)

| Error class | Rev 5 | Rev 6 |
|---|---|---|
| False "unobstructed" (third-party U.S. rights in a top tier) | 0 | **0** |
| False encumbrance | 0 definite, 2 likely outdated (EO-3021, SYSA1801; stale-flagged) | **same** |
| Wrong holder | 1, labelled (LM-302: "Turning Point Therapeutics (recorded; conflicting)") | **same** |
| Wrong territory reading | 0 | **0** |
| Missed return | 1 (SKB315; LM-302 shown as conflicting, not returned) | **same** |

### 8c. Usefulness against general Claude (B), the 15 deal programs

I re-read each row of `after_v6/after_transaction.csv` against the reference and spot-checked B's `calls.csv`
(CL-03–05, CL-07, CL-14, CL-15, CL-27). Every row is as REREVIEW4 §10c scored it.

| Program | DealScreen revision 6 | Score | B |
|---|---|---|---|
| CL-01 zolbetuximab, CL-02 IMAB362 | OWNER_ACQUIRED Astellas; stale | right, right | right, right |
| CL-03 AZD0901, CL-04 CMG901 | LICENSED AstraZeneca, global; stale | right, right | right, right |
| CL-05 sonesitatug vedotin | NO_RIGHTS_EVIDENCE (identity flag) | partial | right |
| CL-06 IBI343 | LICENSED Takeda | right | right |
| CL-07 LM-302 | CONFLICTING; Turning Point "(recorded; conflicting)" | partial | right |
| CL-08 SHR-A1904 | OPTION_HELD Merck KGaA; stale | right | right |
| CL-11 XNW27011 | LICENSED Astellas | right | right |
| CL-13 givastomig | SHARED, I-Mab and ABL Bio | right | right |
| CL-14 EO-3021, CL-15 SYSA1801 | LICENSED Elevation; stale | partial, partial | right, partial |
| CL-26 RC148 | LICENSED AbbVie | right | right |
| CL-27 SKB315 | NO_RIGHTS_EVIDENCE | missed | right |
| CL-30 FL-301 | LICENSED Leap; stale | right | right |
| **Totals** | | **10 right / 4 partial / 1 missed** | **14 / 1 / 0** |

DealScreen still wins on audit and restraint; B still wins on recall. No advantage is demonstrated. None of this
review's errors shows in the CLDN18.2 output: that landscape has no US Rights or Geographic Notes text, and its
rights file has no availability rows. Its Partnerships cells are collaborator names only (for example "Merck Sharp &
Dohme LLC" beside ATG-022 and Spevatamig); they stay neutral by design on the rights-file path, but turn an
availability statement into a conflict on the field path (`commercial.py:107-109`). That inconsistency is older.

## 9. Acceptance criteria

| AC | Verdict | Evidence |
|---|---|---|
| AC1 | PASS | Imports through the profile with provenance; ws_d: "REJECTED rights row 18: unknown status label 'Actv'". |
| AC2 | PARTIAL | CLDN18.2: no OPEN tier, nothing called available. Held out: tier 0 on a row whose quote makes availability depend on a third party's option (QUOTE, ws_e #1); the availability sentence overclaims (L1b). |
| AC3 | PARTIAL | Rights-file territories parse; R4 fixed. Not met: U.S. grants inside party spans read as "other places" (PF1); EU, CA, JP grants read as "other places" for those buyers (PF4); a U.S. license cell is dropped for a {US, CA} buyer (TER-M). |
| AC4 | PARTIAL | E1, E2, E3 fixed; K2 no longer conflicting. Not met: LM-302 still not RETURNED (data); a status ending with no source date is applied (S2, judgement). |
| AC5 | PASS on my inputs | E7 (partial exercise then lapse) keeps the U.S. license; S3 expired option cleared. |
| AC6 | PARTIAL | Readable statements and holders conflict on both paths. Not met: PF1–PF3 and OWN pass silently; contrary Partnerships and Geographic Notes text blocks but is never CONFLICTING (LBL); false conflict for "Available for out-licensing or co-development" (ORCD). |
| AC7 | PARTIAL | E2, O1, R1 fixed. Not met: status endings with no source date (S2, judgement); T1/O8 kept. |
| AC8 | PASS | 0 of 62 (`compare.py`, twice; strict check 0). Cross-version and cycle-4 equivalence: result files only, not re-run. |
| AC9 | PARTIAL | Encumbered treatment, returned preference and age work. The territory preference now drops U.S. evidence for buyers whose territory contains the U.S. (TER-M) and the plain forms ignore the territory (PF4). |
| AC10 | PARTIAL | Blocked texts are cited; L4 fixed. Not met: an ownership statement in Partnerships is cited nowhere in the transaction (OWN); row quotes are shown but not read (QUOTE). |
| AC11 | PARTIAL | Blocked texts get a question naming the text; O1 asks for a date. Not met: PF cases get "Who holds US rights? Recorded deals cover other territories only", while the cited text names Tessaly; QUOTE asks no question about the option. |
| AC12 | PASS | 0 matches for the previous reviewer's 230 CLDN18.2 strings (`/tmp/claude-1000/rr5/ac12_names.txt`) in every line revision 6 added to `src/` and in `rights_allow.py`. |
| AC13 | PARTIAL | Unchanged: IBI343, SHR-A1904 not unobstructed; RC148, FL-301, XNW27011 encumbered; LM-302 CONFLICTING, not returned. |
| AC14 | FAIL | 6 new High, 2 new Medium errors on held-out inputs; none in the CLDN18.2 output. |

Medium error not shown above:
- **ORCD (older, first reported here).** "Available for out-licensing or co-development": no rows + analyst assertion →
  `LICENSED_IN_TERRITORY_PER_EVIDENCE / DEPRIORITIZED`; beside a China license → `CONFLICTING_EVIDENCE`. Revision 5
  gives the same. An offer is read as a grant. Cause: "or" is not in the reader's `_VOCAB`, so `_offer` fails and
  "co-development" matches `_GRANT` (`rights_reader.py:125, 160, 205-218, 260`).

## 10. Remaining issues, ranked

1. **(Safety, High) The plain forms let contrary text through, and override the reader.** Lower-casing hides "U.S."
   in party spans (PF1); pronouns and "the owner" count as the company (PF2); notes inside the text are dropped
   (PF3). On the U.S.-rights field this is a regression from revision 5. End to end: ws_f #1–#4, ws_e #2, #4, #5, #7.
2. **(Safety, High) The plain forms assume the buyer is in the U.S.** For EU, CA or JP buyers a third-party grant in
   the buyer's own territory is "a grant over other places only" (PF4).
3. **(Safety, High) Inputs still not read:** the rights row's own quote (QUOTE, ws_e #1 in tier 0); ownership words in
   Partnerships (OWN, ws_e #3).
4. **(Medium) TER-M:** a {US, CA} buyer loses a U.S. license cell and its exclude preference. ORCD: an offer read as a
   grant.
5. **(Safety, judgement)** status endings with no source date (S2, ws_e #6); a one-word partner name in parentheses
   read as a city; unattached rows with name ids or variant company names guard nothing (R2, R3).
6. **(Usefulness)** new costs: "Open to partnering discussions", "Partnered in China; U.S. rights available",
   "Worldwide rights (ex-China) available", "Seeking partner(s) …", "Open to co-promotion in the U.S.", two-word
   cities in company names; and the company-party row guard will hold every program of a company whose unrelated
   deals are in the export (R9).
7. **(Low) Output honesty:** L1b, L2b, L3b, LBL, WB, NH.
8. **(Recall)** the rights file caps recall (LM-302's successor, SKB315's return, EO-3021's discontinuation).
   Unchanged; B still leads.

## 11. The single highest-value next fix

Make `plain_form` read what it accepts, in the buyer's terms, and never widen the reader:

1. Judge places on the original text, before casefolding, everywhere in the clause, including party spans and text
   after a comma, and compare them with the **buyer territory** (pass it in), not with "the U.S.". A grant form passes
   only if every place it names is outside the buyer territory and no buyer-territory place appears anywhere in the
   clause.
2. Refuse any clause with a parenthetical or bracketed note, and any pronoun or role subject ("it", "we", "the owner")
   in a text with more than one clause.
3. Beside a clear position, never accept a statement the reader marks unread unless its form is one of the
   company-keeps forms that `rights_allow` was built to admit (U2); everything else unread blocks, as in revision 5.

This closes PF1–PF4 and the regression in one place, at little usefulness cost. The next two fixes are small: add
ownership words to `is_rights_text` (OWN), and read the availability row's own quote with the same plain-form test
(QUOTE). For TER-M, read the U.S.-rights field for any buyer territory that contains the U.S., as a position over
part of the territory that blocks the top tiers but keeps the encumbrance.
