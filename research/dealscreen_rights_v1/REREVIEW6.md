# Adversarial re-review 6: cycle R1 revision 7, rights evidence (CLDN18.2)

**AI-SIMULATED INTERNAL REVIEW.** I am an AI (Claude) playing a skeptical pharma BD analyst and auditor. I am not a
human reviewer. I approve nothing, and nothing here is validation. I did not trust REREVIEW5_RESPONSE.md. I checked
each claim by running code or reading outputs. I report only what I ran or read.

Scope and method:
- Revision 7 is commit 50fd206 (HEAD of `dealscreen-mvp`; revisions 6 and 7 together). Revision 5 is d1d4b0f. I
  recorded the SHA-256 of every file in `src/bve/dealscreen/` at the start (`/tmp/claude-1000/rr7/sha_start.txt`) and
  at the end (`sha_end.txt`). No file changed.
- I edited nothing except this file. No commit, stash or git change. ruff ran with `--no-cache`; mypy's cache went
  to `/tmp/claude-1000/rr7/`. All scripts, workspace copies and outputs are in `/tmp/claude-1000/rr7/`.
- Per-program cases go through `screening.program_transaction` via the previous reviewer's harness `h5.py` (copied
  unchanged). Defaults: landscape company "Nerida Bio", buyer {US}, as-of 2025-06-01, max age 730 days,
  `encumbered_rights: deprioritize`. "China license" means one row Nerida Bio → Chinaco Pharma, exclusive, mainland
  China, 2025-01-01. Scripts: `pf.py` (plain forms), `g1.py`, `g2.py` (gate), `l1.py` (ledger), `t1.py`
  (territory), `u1.py` (usefulness), `n1.py` (names), `r1.py` (row guards), `c1.py` (company is a licensee).
- Revision 5 comparison: `git archive d1d4b0f src/bve` into `rr7/rev5/`. The same scripts run against it give
  `*_rev5.out`, so I can tell new errors from old.
- End to end: `rr7/e2e/ws_g`, a copy of `~/.cache/rights_v1/after7_ws` (C3 buyer, as-of 2026-10-29) with rights rows
  Y01–Y11 appended to the CLDN18.2 rights file (`rights_g.csv`) and five analyst assertions (`assert_g.log`, reviewer
  kind SYNTHETIC_FIXTURE), then `import-rights`, `assert`, `screen`, `memo`, `export`. Counterparties are fictional
  (Tessaly Pharma, Chinaco Pharma, Alpha Bio, Kappa Ltd, Omega Holdings). Row quotes start "(test)" or are
  invented; URLs are `example.test`. A landscape company appears only as licensor or speaker. Nothing here is a fact
  about a real program.
- I also re-screened fresh copies of the previous reviewer's workspaces ws_0, ws_d, ws_e, ws_f and re-ran their 12
  scripts unchanged (`rr7/rerun/`).
- Checks: `tests/dealscreen`: **816 passed** (79 s); `test_rights_rereview5.py`: 72 collected. ruff: "All checks
  passed!". mypy `src/bve/dealscreen` + CLI: "Success: no issues found in 33 source files". `compare.py` against the
  frozen baseline: "AC8 scientific fields changed: 0 of 62".

## Summary

- **CLDN18.2: nothing changed from revision 6.** `after_transaction.csv` and the memo are byte-identical; all 62
  screen records are equal field by field. A fresh re-screen of an unchanged workspace reproduces `after_v7` exactly.
  Usefulness against general Claude (B) is unchanged: 10 right / 4 partial / 1 missed, against B's 14 / 1 / 0.
- **The response's own cases hold.** Every PF1–PF4, OWN, QUOTE, TER-M, S2, NH, ORCD and usefulness input I re-ran
  behaves as claimed. The previous reviewer's workspaces have no flagged top-tier placement left.
- **The plain forms still let a third party through, by places the territory reader does not know.** The grant form
  ("a grant over other places only") checks a party span only for places `regions_named` knows and for rights words.
  "in the Americas", "in the rest of the world", "for ROW", "elsewhere", "the rest", "California", "Puerto Rico",
  "all of America" pass for a U.S. buyer; "France", "Germany" for an EU buyer; "Asia" for a JP buyer; "Ontario" for
  a US+CA buyer. Tier 1 on every field and both origins, and **tier 0** beside an availability statement.
- **The new row-quote reading has two holes and one inversion.** A condition written before a colon is stripped as
  a "speaker" ("Subject to Tessaly Pharma consent: U.S. rights available" → tier 0). A license quote naming
  "worldwide" or "North American" rights passes. But a license quote that *confirms* the company kept U.S. rights
  blocks, and so does almost every real press-release sentence on an availability row.
- **Imprecise dates straddling the as-of date are applied as known** (older, first reported): a termination dated
  "2025", a status reported "2025-06", an acquisition dated "2025" all clear a U.S. grant at as-of 2025-06-01.

Definite new errors (not reported in REREVIEW5.md). None occurs in the CLDN18.2 output.

| Severity | Introduced by revision 7 | Claimed fixed, fails on a close variant | Older, first reported here | Total |
|---|---|---|---|---|
| High: tier 0 or 1 while a third party may hold buyer-territory rights, or on contrary or conditioned evidence | 1: SPK | 3: PLACE (PF1/PF4 class), QW (QUOTE), QT (QUOTE, non-U.S.) | 1: DATE | **5** |
| Medium: false encumbrance, false conflict, or a missed encumbrance that changes the tier | 0 | 0 | 0 | **0** |
| Low: false label, wording or citation; no tier change | 1: L1c | 1: L3c | 0 | **2** |

PLACE, QW and QT existed at revision 5 too (same tiers in `g1_rev5.out`); they are listed as "claimed fixed" because
revision 7 says its plain forms read places "in the buyer's terms" and read row quotes. SPK exists only because
revision 7 reads quotes. All five High errors reach a top tier end to end (§2d).

## 1. REREVIEW5_RESPONSE.md, claim by claim

| § | Claim | Verdict | Evidence (run or read) |
|---|---|---|---|
| 1 | PF1: places read as written, so "U.S." in a party span or after a comma is seen | **Held for the U.S. as written. Refuted as "places read"** | The PF1 texts block (`rerun/p_forms.out`). But a place the territory reader does not know is never seen, in a party span or anywhere (PLACE, §2a) |
| 1 | PF4: every place is compared with the buyer territory | **Held for places the reader knows. Refuted on close variants** | "in France" (EU buyer), "in Asia" (JP), "in Ontario" (US+CA) → tier 1 (§2b G3a–G3d) |
| 1 | PF2: "the owner" is not the company; "we"/"it" only in a one-clause text | **Held** | `rerun/p_forms.out`: all PF2 texts `plain=None` |
| 1 | PF3: a note in parentheses or brackets is not a plain form | **Held for brackets. Gap: notes after a dash** | "Licensed in China to Chinaco Pharma - Tessaly Pharma has the rest" → a grant over other places only, tier 1 (part of PLACE). A dash, "c/o" or comma note in a *company* subject does not merge with the company (`n1.out`), so the return and kept forms hold |
| 1 | Unread text never widened, except "rights kept by the company" | **Held** | `accepted_form` (`rights_gate.py:153-160`). I found no kept-form text that the reader leaves unread and that names a third party |
| 1 | OWN: ownership words are rights words | **Held** | "Owned by", "Bought by", "Merged into", "Spun out to" all `rights_text=True` and block (`rerun/a_gate.out`) |
| 1 | QUOTE: a rights row's quote is read | **Held for the cited cases. Refuted as a safety rule** | ws_e ATG-022 is now rights unresolved. But SPK, QW, QT pass, and the rule blocks clean confirming quotes (§3) |
| 1 | LBL: contrary Partnerships/Geographic text is a conflict | **Held** | B3 → `CONFLICTING_EVIDENCE / RIGHTS_UNRESOLVED` (`rerun/a_clean.out`) |
| 2 | PF1–PF4, OWN, QUOTE out of tiers 0 and 1; counts of tests | **Held for the listed inputs**; test counts match (PF1 16, PF2 5, PF3 7, PF4 7, OWN 7, QUOTE 4, TER-M 2, S2 2, NH 3, L3b 2, R9 4, usefulness 5) | pytest `--co` |
| 2 | TER-M: the U.S.-rights field is read for a buyer territory containing the U.S.; an encumbrance keeps its effect | **Held** | {US, CA}, cell "Exclusive U.S. license to Tessaly Pharma (2024)", exclude → `LICENSED_IN_TERRITORY_PER_EVIDENCE / EXCLUDED_BY_BUYER_PREFERENCE`; "U.S. rights available" → `NO_RIGHTS_EVIDENCE` with "speak to the U.S. only, part of the buyer territory CA/US" (`t1.out` T5, T7) |
| 2 | ORCD: "Available for out-licensing or co-development" reads as an offer | **Held** | field path tier 0; beside a China license tier 1 (`rerun/a_clean.out`) |
| 2 | S2: a status ending with no source date blocks | **Held** | "current: the license (2024-03-01) is ended only by its status 'terminated', which no source date places before the as-of date 2025-06-01". Gap: a source date whose *period* contains the as-of date (DATE, §2c) |
| 2 | NH: a noted holder or owner is not shown | **Held** | N2, N3, A7b: `holder=None owner=None`, reason quotes the note |
| 2 | L1b, L2b, L3b wording | **L2b held. L1b, L3b partly held** | L1c and L3c below (§5) |
| 2 | WB, R9 | **Held** | ws_f workbook rows no longer top tier; R9 limits by territory (`r1.out`). R9 loses no row that could concern the buyer territory in my cases |
| 2 | Usefulness: five ordinary phrasings, "(Hong Kong) Limited" | **Held** | `rerun/a_clean.out`: tier 1 beside a China license; field path tier 0 for "Open to partnering discussions" and "Open to co-promotion in the U.S." |
| 2 | One-word partner in parentheses kept as a judgement | **Noted; it is wider than a name** | "Nerida Bio (Licensee) Inc." and "(Partner) Co." as the U.S. holder: note dropped, tier 1 (`n1.out` N2). Judgement with safety impact |
| 3 | 816 tests pass; ruff, mypy clean | **Held** | 816 passed; ruff, mypy clean |
| 3 | Reviewer's scripts re-run: only A4f and "Partner: Tessaly Pharma" in a top tier in `a_gate` | **Held** | My re-runs of all 12 scripts are byte-identical to the implementer's `*.out` |
| 3 | ws_e 7 → 0, ws_f 5 → 0, ws_d only the control | **Held** | Fresh copies re-screened (`rr7/e2e/memo_{e,f,d}.md`) |
| 3 | ws_0 memo and transaction view identical | **Held for the code at HEAD; the implementer's own artifact is stale** | Fresh ws_0: memo byte-identical to `after_v7`, 0 transaction differences. The implementer's `scratchpad/rr7/e2e/memo_0.md` differs on Givastomig's line (no "I-Mab and ABL Bio (shared)"); it was written at 20:01, before `screening.py` (20:02) and `after_v7` (20:03) |
| 3 | CLDN18.2 identical to revision 6; 0 of 62 scientific fields changed | **Held** | `cmp` of the CSVs and memos; JSON 0 field differences; `compare.py` "0 of 62" and its CSV equals `after_v7/after_transaction.csv` |
| 3 | Cross-version (312 assets, FcRn v2 NH effect) and cycle-4 equivalence | **Unverifiable** (not re-run) | Result files only: `~/.cache/rights_v1/xv7/`, `eq7/`; `cycle4/equivalence_result.json` says byte_identical and fast_path on all four |
| 3 | Usefulness 10/4/1 vs B 14/1/0 | **Held** | §7 |
| 4 | "Row quotes are read only for places and rights words" | **Understated** | Availability quotes must be a plain form, which blocks most real quotes (U4, U5), while a condition before a colon is discarded (SPK) |

## 2. Paths into the top tiers

### 2a. The plain forms, read alone (`pf1.out`)

Company "Nerida Bio", as-of 2025-06-01. "accepted" is `rights_gate.accepted_form`, the gate's own verdict.

| Buyer | Text | `accepted_form` | Reader | Meaning |
|---|---|---|---|---|
| US | "Licensed in China to Chinaco Pharma and in the Americas to Tessaly Pharma" | a grant over other places only | UNKNOWN, understood | Tessaly holds the Americas, the U.S. included |
| US | "Licensed in China to Chinaco Pharma, which also sells in the Americas" | same | UNKNOWN, understood | Chinaco sells in the U.S. |
| US | "Licensed in China to Chinaco Pharma and in the rest of the world to Tessaly Pharma"; "… and for ROW to Tessaly Pharma"; "… and elsewhere to Tessaly Pharma"; "… - Tessaly Pharma has the rest"; "… — Tessaly Pharma elsewhere" | same | UNKNOWN, understood | Tessaly holds the U.S. |
| US | "Licensed in China to Chinaco Pharma and in California to Tessaly Pharma"; "… in Puerto Rico …"; "… stateside …"; "… in the States …"; "… North American sales to …"; "… American sales to …" | same | UNKNOWN, understood | a U.S. grant |
| US | "Licensed for China to Chinaco Pharma for sales in all of America" | same | UNKNOWN, understood | Chinaco sells in the U.S. |
| US | "Licensed in China to Chinaco Pharma, Tessaly Pharma to follow in the West" | same | UNKNOWN, understood | a planned Western deal |
| EU | "Licensed in China to Chinaco Pharma and in France to Tessaly Pharma" (also "Germany") | same | UNKNOWN, understood | an EU grant |
| JP | "Licensed in Korea to Kappa Ltd and in Asia to Tessaly" | same | UNKNOWN, understood | Asia includes Japan |
| US+CA | "Licensed in China to Chinaco Pharma and in Ontario to Tessaly Pharma" | same | UNKNOWN, understood | a Canadian grant |
| EU | "U.S. rights available" (as an availability row's quote, §2b QT) | an offer | AVAILABLE | an offer of the U.S., not of Europe |

Controls that held: "North American markets" (rights word "market"), "N. America" (reader unread), "in European
markets", "Europe-wide", "EU5", "in the us" with a U.S. word in capitals elsewhere, "globally to Tessaly" (the
reader reads it as a grant over the world, which contests for a U.S. buyer and blocks for others).

Cause (PLACE):
- The grant form passes when the place group is a known region outside the buyer territory and the party span has
  no known region and no rights word (`rights_allow.py:164-169`). `named` (line 148) and the party check both use
  `regions_named`, which knows only the 15 terms in `rights_territory.py:25-41`. "Americas", "rest of the world",
  "ROW", "elsewhere", "the rest", "the West", U.S. states, EU member states, "Asia", Canadian provinces are not in it.
  `regions_named` also deliberately ignores "rest of world" (`rights_territory.py:118-121`).
- The reader agrees: `_covers_us` (`rights_reader.py:178-188`) sees only CN in these clauses, so the clause reads
  "consistent" and `understood` is True. The unread rule therefore does not catch it.
- The design rule is backwards here: the grant form treats an unknown word in a party span as a name. The territory
  reader itself treats any unknown word as unreadable (`rights_territory.py:9-13`). The plain form should too.

### 2b. Per program (`g1.out`, `g2.out`; revision 5 in `g1_rev5.out`)

| Id | Input | Revision 7 output (copied) | Rev 5 | Expected | Cause |
|---|---|---|---|---|---|
| PLACE | China license + landscape geographic note "Licensed in China to Chinaco Pharma and in the rest of the world to Tessaly Pharma" | `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP`; reason "the landscape geographic rights note '…' (a grant over other places only)"; ask "Who holds US rights? Recorded deals cover other territories only (licensor per evidence: Nerida Bio)." | same tier | CONFLICTING (Tessaly holds the rest of the world) | §2a |
| PLACE | The eight texts of `g1.py` (Americas, sells in the Americas, rest of the world, ROW, California, elsewhere, "- Tessaly Pharma has the rest", "all of America"), each as a US Rights cell, a Geographic Notes cell and a Partnerships cell (24 cases), and three as analyst Geographic and Partnerships assertions (6) | all 30: `… / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP` | same | blocked or CONFLICTING | §2a |
| PLACE → tier 0 | No rows; analyst us_rights "U.S. rights available" + landscape geographic "Licensed in China to Chinaco Pharma and in the rest of the world to Tessaly Pharma" (G4) | `AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED / AVAILABILITY_STATED_UNVERIFIED <<< TOP` | — | blocked | §2a |
| PLACE → tier 0 | Availability row (Nerida Bio, US, 2025-03-01) + geographic "Licensed in China to Chinaco Pharma and for ROW to Tessaly Pharma" (G6) | `AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED / AVAILABILITY_STATED_UNVERIFIED <<< TOP` | — | blocked | §2a |
| PLACE (PF4 class) | EU buyer: China license + geographic "Licensed in China to Chinaco Pharma and in France to Tessaly Pharma" (also Germany); JP buyer: "Licensed in Korea to Kappa Ltd and in Asia to Tessaly"; US+CA buyer: "… and in Ontario to Tessaly Pharma" | each `… / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP`; e.g. "recorded grants do not cover EU; … 'Licensed in China to Chinaco Pharma and in France to Tessaly Pharma' (a grant over other places only)" | same | CONFLICTING | §2a |
| SPK | Availability row (Nerida Bio, US, 2025-03-01), quote "Subject to Tessaly Pharma consent: U.S. rights available" | `AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED / AVAILABILITY_STATED_UNVERIFIED <<< TOP`; "ask: Confirm with Nerida Bio that US rights are unencumbered and available, and on what terms." | tier 0 (quotes not read) | blocked; the quote names a third party's consent | `_SPEAKER` (`rights_gate.py:221`) strips any capitalised prefix of up to 60 characters before a colon, then the rest is tested (`rights_gate.py:235`). A condition or a date before a colon is discarded as a "speaker" |
| SPK | Same, quote "After Tessaly Pharma's U.S. option expires in 2027: U.S. rights available" | tier 0, same lines | tier 0 | blocked: future, third-party option | same; REREVIEW5's QUOTE input, reworded with a colon |
| SPK | Same, quote "Tessaly Pharma: U.S. rights available" (row grantor Nerida Bio) | tier 0; holder 'Nerida Bio' | tier 0 | blocked: the speaker is a third party | same; the speaker is never compared with the row's party or the company |
| QW | China license row, quote "Chinaco Pharma licenses China rights and an option on worldwide rights" (also "… North American rights", "… right of first negotiation for the rest of the world") | `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP` | same | blocked: the quote names an option over the U.S. | a non-availability quote blocks only when `regions_named(quote)` names a buyer-territory place the row does not cover (`rights_gate.py:240-243`); "worldwide" and the rest are not places to `regions_named`. The control "… an option on United States rights" blocks |
| QT | EU buyer; availability row for Europe, quote "Nerida Bio: U.S. rights available" | `AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED / AVAILABILITY_STATED_UNVERIFIED <<< TOP`; "ask: Confirm with Nerida Bio that EU rights are unencumbered and available" | tier 0 | blocked: the quote offers the U.S. only | the offer form never compares the places in an offer with the buyer territory; "us" is an offer word (`rights_allow.py:54-64, 117-135, 170-171`) |

### 2c. Ledger: dates whose period contains the as-of date (`l1.out`; revision 5 identical)

U.S. license Nerida Bio → Alpha Bio, 2024-03-01, deal D1; as-of 2025-06-01.

| Id | Input | Output (copied) | Expected |
|---|---|---|---|
| DATE | Termination naming Alpha Bio, linked to D1, **dated "2025"** (year) | `RIGHTS_RETURNED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP`; "grant to Alpha Bio ended in US per source" | blocked: the termination may be after the as-of date |
| DATE | License status TERMINATED, **source date "2025"** | same, tier 1 | blocked |
| DATE | License status TERMINATED, **source date "2025-06"** (the as-of month) | same, tier 1 | blocked |
| DATE | Return naming Alpha Bio dated "2025-06"; option lapse dated "2025"; option status EXPIRED (source 2025-05-01 — correct) | tier 1 each | the first two blocked |
| DATE | Acquisition of Nerida Bio by Omega Holdings dated "2025" + China license | `OWNER_ACQUIRED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP`, owner 'Omega Holdings' | blocked |

Cause: `after_as_of` keeps an event unless the *start* of its date window is after the as-of date
(`rights_ledger.py:113`); the E2 status rule compares the *start* of the source-date period (`rights_ledger.py:240`).
An event whose window contains the as-of date is treated as known on it. Revision 7's own S2 rule says an end that
"no source date places before the as-of date" must block; a year or month date that contains the as-of date does not
place it before either. Older (since R1); first reported here. It bites only when the as-of date falls inside the
period, which is common for an as-of date in the current year.

Held: a termination naming only the licensor (L6) blocks; a termination of a different territory (L13) keeps the
license; a U.S.-only return of a worldwide license (L14) correctly returns the U.S.; a sublicense from the licensee
(L15) keeps an encumbrance; T1/O8 (termination dated before, reported after) unchanged, judgement as before.

### 2d. End to end (ws_g, as-of 2026-10-29)

Outputs copied from `rr7/e2e/memo_g.md` and `ws_g/screening.json`.

| # | Program | Input added (fictional parties) | Output (copied) | Finding |
|---|---|---|---|---|
| 1 | ATG-022 | Y02 "Seeking partner" by Antengene Biologics, US, 2026-06-01, quote "Subject to Tessaly Pharma consent: U.S. rights available" | "#1 ATG-022: availability stated, unverified; … stated by Antengene Biologics"; "ask: Confirm with Antengene Biologics that US rights are unencumbered and available, and on what terms." | SPK |
| 2 | QLS31905 | Y01 China license, quote "(test) Chinaco Pharma licenses China rights and an option on worldwide rights" | "#2 QLS31905: no third-party grant in evidence; … recorded grants do not cover US" | QW |
| 3 | JS107 | Y05 China license; analyst geographic "Licensed in China to Chinaco Pharma - Tessaly Pharma has the rest" | "#3 JS107: no third-party grant in evidence; … an analyst assertion geographic rights note 'Licensed in China to Chinaco Pharma - Tessaly Pharma has the rest' (a grant over other places only)" | PLACE |
| 4 | BL-M05D1 | Y04; analyst partnerships "Licensed in China to Chinaco Pharma and in the Americas to Tessaly Pharma" | "#4 BL-M05D1: no third-party grant in evidence; … (a grant over other places only)" | PLACE |
| 5 | SKB315 | Y03; analyst geographic "Licensed in China to Chinaco Pharma and in the rest of the world to Tessaly Pharma" | "#5 SKB315: no third-party grant in evidence; … (a grant over other places only)" | PLACE |
| 6 | Spevatamig (PT886) | Y07 U.S. license Phanes → Alpha Bio 2025-03-01; Y08 termination linked to Y07, dated "2026" | "#6 Spevatamig (PT886): no third-party grant in evidence; rights position: rights returned per evidence (grant to Alpha Bio ended in US per source; …)" | DATE |
| — | LB4330 (unresolved) | Y09 availability by L & L Bio, quote "After Tessaly Pharma's U.S. option expires in 2027: U.S. rights available" | workbook: tier `AVAILABILITY_STATED_UNVERIFIED`, holder 'L & L Bio' | SPK |
| — | ASP2138 | Y11 China license; analyst geographic "Licensed in China to Chinaco Pharma, which also sells in the Americas" | `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE / DEPRIORITIZED` (the buyer deprioritises the sponsor; the gate passed the text) | PLACE, masked by preference |
| 8 | TORL-2-307-ADC | Y06 China license, quote "… in mainland China; TORL Biotherapeutics retains all rights in the U.S. and the rest of the world" | "#8 TORL-2-307-ADC: rights unresolved; … the quote on rights row 23 (license) reads '…', which names US, in the buyer territory, which the row's own territory does not" | usefulness cost U2 (§3) |

So test inputs take #1 (tier 0) and #2–#6 (tier 1) on the CLDN18.2 buyer.

## 3. Over-caution and usefulness (`u1.out`; revision 5 in `u1_rev5.out`)

These are usefulness costs, not safety errors.

| Input | Revision 7 | Revision 5 | Note | Cause |
|---|---|---|---|---|
| Current China-only license; returned (dated termination) then dated statement; "Nerida Bio: U.S. rights available" as an availability quote | tier 1; tier 0; tier 0 | same | Clean cases reach the top | |
| China license + "Nerida Bio retains all rights outside Greater China"; "Ex-China rights retained" | tier 1 | blocked | **Improved** | |
| China license row whose quote **confirms the company kept U.S. rights**: "Chinaco Pharma obtains exclusive rights … in mainland China; Nerida Bio retains all rights in the U.S. and the rest of the world" (also the short "… Nerida Bio retains U.S. rights") | blocked: "the quote … names US, in the buyer territory, which the row's own territory does not" | tier 1 | **New cost, and inverted.** The best evidence for a clean China deal blocks, while "an option on worldwide rights" passes (QW). ws_g #8 | `rights_gate.py:240-243` blocks on any buyer-territory place, whatever the quote says about it |
| Availability row (US) with a press sentence: "Nerida Bio is actively seeking a partner to develop and commercialize NB-7 in the U.S."; "Nerida Bio said it is seeking a U.S. partner for NB-7" | blocked: "not one of the plain forms" | tier 0 | **New cost.** Vendor and press quotes are full sentences; only "<Speaker>: <plain form>" passes. ws_g RC118 | the offer vocabulary has no "to", "develop", program codes, "said" (`rights_allow.py:54-64`) |
| EU buyer: availability row for Europe, quote "Nerida Bio: European rights available" or "Rights available in Europe" | blocked | tier 0 | **New cost.** For a non-U.S. buyer, an availability quote naming its own territory can never pass | "us" is the only place word an offer may contain (`rights_allow.py:54-64`) |
| China license + "Licensed in Greater China to Chinaco Pharma U.S. Inc." | blocked | tier 1 | Acknowledged cost (PF1) | |
| China license + Partnerships "Chinaco Pharma (China license)", "Chinaco Pharma - Greater China license", "Greater China: Chinaco Pharma" | blocked | tier 1 | Cost from revision 6 (P), common vendor formats | reader unread; not a plain form |
| "U.S. and EU rights available", "Nerida Bio retains U.S. and EU rights", "Rights outside China retained by Nerida Bio", "Unpartnered outside China", "No U.S. partner" | blocked | blocked | Unchanged cost | closed word lists |
| Company "Nerida Bio (Hong Kong) Limited"; licensor "Nerida Bio U.S. Inc."; licensee "Chinaco Pharma (Shanghai) Co., Ltd." | tier 1 | — | Clean, held | |
| R9: an unattached row naming the company, territory mainland China | guards nothing | — | Fixed; a worldwide or unreadable-territory row still guards every program of the company (`r1.out`) | |

## 4. Names and rows

| Id | Input | Output | Verdict | Cause |
|---|---|---|---|---|
| N-role | U.S. holder cell "Nerida Bio (Licensee) Inc." (also "(Partner) Co.") + China license | `… / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP`; `content_note` = '' | **Judgement, safety impact.** The kept "one word is a city" rule drops a role word | `rights_territory.py:163-176` |
| N-addr | U.S. holder cell "Nerida Bio Inc., Tessaly, Japan" + China license | tier 1; `same_company(…, 'Nerida Bio')` True | Judgement: `drop_address` reads any single word before a region as a city | `rights_territory.py:188-205` |
| N-prefix | Company "Nerida"; holder cell "Nerida Biologics International" | tier 1 | Older C1 class (prefix + generic words merge) | `same_company` |
| CO | Landscape company "Tessaly Pharma" (a sponsor/licensee); China license from Nerida Bio | blocked: "the owner per the rights evidence is Nerida Bio, but the landscape names Tessaly Pharma as the program's company" | Correct. Minor label: "Owned by Tessaly Pharma" is then described as "(rights kept by the company)" | |
| Rows | Unattached row whose id is the program **name** ("SKB315" for CL-27), licensee only | guards nothing | Older (R2 class). A vendor deals file keyed by drug name attaches nothing; rows are matched only to landscape ids | `rights_gate.py:449-480`, `screening.py:362-369` |
| CLDN18.2 | — | no unattached or rejected rows; no guard | No guard is broad on this workspace | |

## 5. Output honesty

In favour: the CLDN18.2 memo calls nothing available or open; the only all-caps token in the ws_g memo prose is the
reviewer kind "SYNTHETIC_FIXTURE"; every holder and owner shown in CLDN18.2 is cited by row; noted names are hidden
(NH). The analyst-facts paragraph lists fields and no longer claims names-only Partnerships values are read (L2b).

| # | Where | Output (copied) | Problem | Cause |
|---|---|---|---|---|
| L1c | ws_g memo, line 9 | "A source states availability for 1 (read by rule, unverified); for 1 DealScreen found nothing else among the rights texts, names, rows and row quotes it reads that it cannot read or that contradicts the statement (it reads a row's quote only for places and rights words)." | The program is ATG-022. DealScreen discarded "Subject to Tessaly Pharma consent:" as a speaker, so it did not read the part that contradicts. The parenthesis also misstates the rule: an availability quote must be a plain form | `memo.py:485-487`; SPK |
| L3c | CLI `assert` (`e2e/assert_g.log`) | "Beside a clear position, the top-tier gate accepts it as a plain form for the buyer territory (US): a grant over other places only; it is still unverified." for "Licensed in China to Chinaco Pharma and in the rest of the world to Tessaly Pharma" | The note now reports the gate's real verdict for the buyer territory (L3b fixed), so it repeats PLACE as fact | `cli/dealscreen.py:113` |
| (PLACE) | ws_g memo #3–#5, workbook | "(a grant over other places only)" beside a text naming a licensee for the rest of the world or the Americas; ask "Who holds US rights? Recorded deals cover other territories only" | A false description; the question ignores the party the cited text names (AC11) | §2a |
| (SPK) | ws_g ATG-022 | holder 'Antengene Biologics'; "ask: Confirm with Antengene Biologics that US rights are unencumbered and available" | No question names Tessaly's consent, which the cited quote states | §2b |

## 6. Acceptance criteria

| AC | Verdict | Evidence |
|---|---|---|
| AC1 | PASS | ws_g: "28 events, 0 rejected rows"; ws_d re-screened: "rights row 18 for this program was rejected at import (unknown status label 'Actv')". |
| AC2 | PARTIAL | CLDN18.2: no OPEN tier, nothing called available. Held out: tier 0 on a quote conditioned before a colon (SPK, ws_g #1) and beside a rest-of-world licensee (G4, G6); the availability sentence overclaims (L1c). |
| AC3 | PARTIAL | Rights-file territories parse; TER-M fixed. Not met: a grant to a third party over places the reader does not know is "other places only" (PLACE), including EU, JP and CA variants. |
| AC4 | PARTIAL | S2 fixed; returns and re-licensing work. Not met: endings with a year or month date containing the as-of date clear a grant (DATE); LM-302 still not RETURNED (data). |
| AC5 | PASS on my inputs | Exercises, lapses and expired options behave (rerun `a_ledger`, `l1.out` L7); the year-dated lapse is a DATE issue (AC7). |
| AC6 | PARTIAL | The LBL contest branch works (B3 CONFLICTING). Not met: PLACE texts pass silently instead of conflicting. |
| AC7 | PARTIAL | S2 and E2 fixed. Not met: DATE; T1/O8 kept as judgement. |
| AC8 | PASS | `compare.py` 0 of 62; v6 → v7 0 field differences. Cross-version and cycle-4 equivalence: result files only, not re-run. |
| AC9 | PARTIAL | Territory, encumbered treatment, returned preference and age work; TER-M fixed. Not met: the plain forms compare only places the reader knows with the buyer territory (PLACE); non-U.S. availability quotes never pass (usefulness). |
| AC10 | PARTIAL | Every gate text and quote is cited. Not met: PLACE texts are cited under a false label; SPK's quote is cited but its condition is not reflected. |
| AC11 | PARTIAL | Blocked texts and quotes get a question. Not met: PLACE cases ask "Who holds US rights? Recorded deals cover other territories only" while the cited text names Tessaly; SPK asks no question about the consent. |
| AC12 | PASS | 0 matches for the 230 CLDN18.2 strings (`/tmp/claude-1000/rr5/ac12_names.txt`) in the 651 lines added to `src/` since d1d4b0f. |
| AC13 | PARTIAL | Unchanged: IBI343, SHR-A1904 not unobstructed; RC148, FL-301, XNW27011 encumbered; LM-302 CONFLICTING, not returned. |
| AC14 | FAIL | 5 new High errors on held-out inputs; none in the CLDN18.2 output. |

## 7. CLDN18.2 measured against the reference and B

### 7a. What changed from revision 6

| Item | Revision 6 | Revision 7 |
|---|---|---|
| `after_transaction.csv` (62 programs) | — | byte-identical |
| Memo | — | byte-identical |
| `screening.json` screens | — | 0 field differences in 62 records |
| Scientific fields vs frozen baseline | 0 of 62 | 0 of 62 (`compare.py`) |
| Top-tier programs | 0 | 0 (44 rights unresolved, 17 deprioritized, 1 excluded by preference) |

### 7b. Error classes against the reference (`reference_calls.csv`)

| Error class | Rev 6 | Rev 7 |
|---|---|---|
| False "unobstructed" (third-party U.S. rights in a top tier) | 0 | **0** |
| False encumbrance | 0 definite, 2 likely outdated (EO-3021, SYSA1801; stale-flagged) | **same** |
| Wrong holder | 1, labelled (LM-302: "Turning Point Therapeutics (recorded; conflicting)") | **same** |
| Wrong territory reading | 0 | **0** |
| Missed return | 1 (SKB315; LM-302 shown as conflicting, not returned) | **same** |

### 7c. Usefulness against general Claude (B), the 15 deal programs

Re-read from `after_v7/after_transaction.csv` (tier, position, holder, stale, rows) against the reference. Each row
matches REREVIEW5 §8c.

| Program | DealScreen revision 7 | Score | B |
|---|---|---|---|
| Zolbetuximab, IMAB362 | OWNER_ACQUIRED Astellas; stale | right, right | right, right |
| AZD0901, CMG901 | LICENSED AstraZeneca; stale | right, right | right, right |
| Sonesitatug vedotin | NO_RIGHTS_EVIDENCE | partial | right |
| IBI343 | LICENSED Takeda | right | right |
| LM-302 | CONFLICTING; "Turning Point Therapeutics (recorded; conflicting)" | partial | right |
| SHR-A1904 | OPTION_HELD Merck KGaA; stale | right | right |
| XNW27011 | LICENSED Astellas | right | right |
| Givastomig | SHARED, "I-Mab and ABL Bio (shared)" | right | right |
| EO-3021, SYSA1801 | LICENSED Elevation; stale | partial, partial | right, partial |
| RC148 | LICENSED AbbVie | right | right |
| SKB315 | NO_RIGHTS_EVIDENCE | missed | right |
| FL-301 | LICENSED Leap; stale | right | right |
| **Totals** | | **10 right / 4 partial / 1 missed** | **14 / 1 / 0** |

DealScreen wins on audit and restraint; B wins on recall. No advantage is demonstrated. None of this review's errors
shows in the CLDN18.2 output: its landscape has no US Rights or Geographic Notes text, its Partnerships cells are
names only, its rights file has no availability rows, and every rights row there is an encumbrance, so the quote
rule never runs.

## 8. Remaining issues, ranked

1. **(Safety, High) PLACE.** The grant plain form treats any unknown word in a party span as a name, so a second
   grant over "the Americas", "the rest of the world", "ROW", "elsewhere", a U.S. state, an EU country, "Asia" or a
   Canadian province reads as "other places only". Tier 1 on every field and origin; tier 0 beside an availability
   statement; ws_g #3–#5.
2. **(Safety, High) SPK.** The quote "speaker" rule discards a condition, a date or a third-party speaker written
   before a colon; ws_g #1 in tier 0.
3. **(Safety, High) QW, QT.** Non-availability quotes are read only for known place names ("option on worldwide
   rights" passes); offers never compare their place with a non-U.S. buyer territory.
4. **(Safety, High, older) DATE.** A year- or month-dated ending, status report or acquisition whose period contains
   the as-of date is applied as known; ws_g #6.
5. **(Usefulness) The quote rule is inverted on clean cases.** A license quote confirming the company kept U.S.
   rights blocks; real press-sentence availability quotes block; non-U.S. buyers can never pass an availability
   quote naming their territory. On a real vendor export these would hold back most clean programs.
6. **(Judgement)** one-word role notes in legal names ("(Licensee) Inc."); `drop_address` single words; rows keyed
   by program name never attach; T1/O8; availability rows with no territory count for any buyer.
7. **(Low)** L1c, L3c.
8. **(Recall)** the rights file still caps recall (LM-302's successor, SKB315's return, EO-3021's discontinuation).

## 9. The single highest-value next fix

Make the grant plain form fail closed on words it does not know, as the territory reader already does: a clause
passes as "a grant over other places only" only if, after removing the place group and the known grant words, the
rest is exactly one party name with no other words ("to <Party>" and nothing after it), and the place group parses
with `parse_territory` to regions outside the buyer territory. Any "and", "also", "which", "for sales", "elsewhere",
dash or second "to"/"in" in the party span blocks. This closes PLACE on all fields and all buyer territories in one
place (`rights_allow.py:164-169`) at little usefulness cost (the clean forms "Licensed in China to Chinaco Pharma",
"China license to Chinaco Pharma" still pass).

The next two fixes are small. Drop the `_SPEAKER` strip, or accept it only when the prefix is exactly the row's own
grantor or the program's company (SPK). For non-availability quotes, block on "worldwide", "global", "rest of the
world", "ex-<place>" and on any option/right-of-first wording, and stop blocking on a buyer-territory place when the
quote's clause is a kept form for the company (QW and the U2 usefulness inversion). For DATE, compare the *end* of
an ending's date window (and of a status's source-date window) with the as-of date, and block when the window
contains it.
