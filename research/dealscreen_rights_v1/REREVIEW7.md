# Adversarial re-review 7: cycle R1 revision 8, rights evidence (CLDN18.2)

**AI-SIMULATED INTERNAL REVIEW.** I am an AI (Claude) playing a skeptical pharma BD analyst and auditor. I am not a
human reviewer. I approve nothing, and nothing here is validation. I did not trust REREVIEW6_RESPONSE.md. I checked
each claim by running code or reading outputs. I report only what I ran or read.

Scope and method:
- Revision 8 is commit beecfcd. HEAD is f5ab4c4 (cycle U1). Revision 7 is 50fd206. I recorded the SHA-256 of every
  file in `src/bve/dealscreen/` at the start (`/tmp/claude-1000/rr8/sha_start.txt`) and at the end (`sha_end.txt`).
  No file changed. I edited nothing except this file. No commit, stash or git change. ruff ran with `--no-cache`;
  mypy's cache went to `/tmp/claude-1000/rr8/`.
- All scripts, workspace copies and outputs are in `/tmp/claude-1000/rr8/`. Per-program cases go through
  `screening.program_transaction` with the previous reviewer's harness `h5.py` (copied). Defaults: landscape company
  "Nerida Bio", buyer {US}, as-of 2025-06-01, max age 730 days, `encumbered_rights: deprioritize`. "China license"
  is one row Nerida Bio → Chinaco Pharma, exclusive, mainland China, 2025-01-01. Scripts: `a/pf8.py` (plain forms),
  `a/g8.py` (party names, covering rows, quote words, speakers, offers), `a/q8.py` (quotes), `a/d8.py` (dates).
- **I changed one thing in the harness: the default row quote.** `h5.py` gives every row the quote
  "(test) row N". Revision 8's new `_WIDER` pattern matches the English word "row" (case-insensitive), so every such
  row now blocks for that reason alone. I use "(test) record N" instead (`rr8/h5.py`). §1 explains what this does to
  the implementer's re-run numbers.
- Revision 7 comparison: `git archive 50fd206 src/bve` into `rr8/rev7/`. The same scripts against it give
  `a/*_rev7.out`, so I can tell new errors from old.
- End to end: `rr8/e2e/ws_h`, a copy of `~/.cache/rights_v1/after8_ws` (C3 buyer, as-of 2026-10-29), with rights rows
  Z01–Z12 appended to the CLDN18.2 rights file (`e2e/rights_h.csv`) and two analyst assertions (`e2e/assert_h.log`,
  reviewer kind SYNTHETIC_FIXTURE), then `import-rights`, `assert`, `screen`, `memo`, `export` at HEAD.
  Counterparties are fictional (Tessaly Pharma, Chinaco Pharma, Alpha Bio, Omega Holdings). Quotes start "(test)"
  or are invented; URLs are `example.test`. A landscape company appears only as licensor, acquired party or speaker.
  Nothing here is a fact about a real program.
- Checks: `tests/dealscreen` at HEAD: **1052 passed** (91 s; includes cycle U1's tests). `test_rights_rereview6.py`:
  60 collected. ruff: "All checks passed!". mypy `src/bve/dealscreen` + CLI: "Success: no issues found in 35 source
  files". `compare.py` against the frozen baseline: "AC8 scientific fields changed: 0 of 62" (on `after_v8` and on
  my HEAD re-screen).

## Summary

- **CLDN18.2: nothing changed from revision 7, and HEAD (U1) changed nothing about rights.** `after_transaction.csv`
  and the memo are identical to `after_v7`. A fresh HEAD re-screen of a copy of `after8_ws` differs from
  `screening_R1v8.json` only in the new `unknown_diagnostics` key; its `compare.py` CSV is byte-identical to
  `after_v8/after_transaction.csv`; the workbook's Screening sheet has 0 differences in shared columns and the
  COMMERCIAL diligence rows are equal. Usefulness against general Claude (B) is unchanged: 10 right / 4 partial / 1
  missed, against B's 14 / 1 / 0.
- **The response's own cases hold.** Every PLACE, SPK, QT and DATE input in REREVIEW6 that I re-ran behaves as
  claimed. The previous reviewer's workspaces ws_g, ws_e, ws_f have no top-tier program at HEAD; ws_d has only the
  control.
- **The party-name rule is a capital-letter test, so it fails on Title Case and ALL CAPS.** "LICENSED IN CHINA TO
  CHINACO PHARMA AND ELSEWHERE TO TESSALY PHARMA" and "Licensed In China To Chinaco Pharma And In California To
  Tessaly Pharma" read as "a grant over other places only". Capitalised rights words it does not list pass too:
  "…, Tessaly Pharma Has ROFN", "…, Subject To Tessaly Pharma Approval". Tier 1 on every field and origin; tier 0
  beside an availability statement.
- **A row whose own territory covers the buyer territory has its quote skipped, including endings and
  acquisitions.** A U.S. termination whose quote says "Tessaly Pharma holds an option on U.S. rights", or a worldwide
  acquisition whose quote says "U.S. rights … remain licensed to Tessaly Pharma", gives tier 1 (tier 0 with a
  statement). The ledger never reads quotes, so "left to the ledger" means "not read".
- **Quote clauses are read only for places and a fixed word list.** A clause that names a third party's grant
  without a place ("Nerida Bio also granted Tessaly Pharma a license to NB-7") passes. So do wider words not on the
  list ("opt-in to the remaining territories", "all other markets", "ex China", "beyond").
- **A license announced before the as-of date but effective after it is dropped.** It is shown as "not applied",
  and the program reaches tier 1 (tier 0 with a statement). This matters most in live use, where the as-of date is
  today.
- **The DATE fix covers endings, not availability.** A statement dated only "2025" or "2025-06" counts as current
  at as-of 2025-06-01 (tier 0).
- **New usefulness cost.** `_WIDER` matches ordinary words ("row", "option", "International", "except",
  "excluding", "global", "outside"), so real press sentences on clean China-license rows now block. The same match
  confounds the implementer's re-run numbers.

Definite new errors (not reported in REREVIEW6.md). None occurs in the CLDN18.2 output.

| Severity | Introduced by revision 8 | Claimed fixed, fails on a close variant | Older, first reported here | Total |
|---|---|---|---|---|
| High: tier 0 or 1 while a third party may hold buyer-territory rights, or on contrary, conditioned or future evidence | 0 | 3: PN-CASE, PN-WORD, QW2 | 3: COVER, FUT, DATE-AV | **6** |
| Medium: false encumbrance, false conflict, or a missed encumbrance that changes the tier | 0 | 0 | 0 | **0** |
| Low: false label, wording or citation; no tier change | 0 | 2: L3d (assert note), L1d (memo sentence) | 1: Q-FUT (question contradicts a cited row) | **3** |

Each High error was present at revision 7 too, at the same tier (`a/*_rev7.out`). COVER exists since quotes were
first read (revision 6). FUT and DATE-AV exist since R1. All six reach a top tier end to end (§2f).

## 1. REREVIEW6_RESPONSE.md, claim by claim

| § | Claim | Verdict | Evidence (run or read) |
|---|---|---|---|
| 1 | PLACE: the "other places" party must be a name: capitalised words, digits, corporate punctuation; no lower-case word, dash, known place, place-like word or rights word | **Held as written. Refuted on close variants** | The nine REREVIEW6 texts and the EU/JP/US+CA variants block (`rerun7n/g1.out`). But case is the test: Title Case and ALL CAPS texts pass, and capitalised rights or condition words not on the lists pass (PN-CASE, PN-WORD, §2a) |
| 1 | SPK: a "Name:" prefix is stripped only for the row's grantor or the company | **Held** | "Subject to Tessaly Pharma consent: …", "After Tessaly Pharma's U.S. option expires in 2027: …", "Tessaly Pharma: …" all `RIGHTS_UNRESOLVED`; "Nerida Bio U.S.:", "NERIDA BIO:" still stripped (`a/g8.out` S). Judgement: "Nerida Bio Inc., Tessaly, Japan:" is stripped (`drop_address`, older N-addr) |
| 1 | QW: a quote is read clause by clause for buyer-territory places and wider words | **Held for the listed words. Refuted as a safety rule** | Options, "worldwide", "North American", "right of first negotiation" block. Third-party grants with no place, and wider words not on the list, pass (QW2, §2c). Rows whose own territory covers the buyer are not read at all (COVER, §2b) |
| 1 | QW: "removes the inverted usefulness cost" | **Partly held** | The short "…; Nerida Bio retains U.S. rights" passes (U3). REREVIEW6's own example U2 ("… Nerida Bio retains all rights in the U.S. and the rest of the world") still blocks, and so does "… retains rights in the rest of the world" (`rerun7n/u1.out`, `a/q8.out`) |
| 1 | QW: "A row whose own territory already covers the buyer territory is left to the ledger" | **Refuted as a safety rule** | The ledger reads no quotes. For terminations, returns, lapses and acquisitions the quote is never read (COVER) |
| 1 | QT: an offer that names places must cover the buyer territory | **Held** | "U.S. rights available": `None` for EU and US+CA buyers, "an offer" for US (`a/pf8c.out`); g1 Q4 (EU) not top |
| 1 | DATE: endings, returns, lapses, acquisitions dated to a year or month containing the as-of date are not applied and block with a question; statuses judged on the period end | **Held for those records. Not extended to availability statements or future-effective grants** | D1a, D1d, D1f, D1j, D1k, D1l, D2a, D2b, D2e block; D1b, D1c, D2c, D2d (whole period before the as-of date) clear (`a/d8.out`). Statements dated "2025"/"2025-06" count (DATE-AV) |
| 1 | L1c reworded | **Wording held. The sentence still misleads on PN-CASE** | ws_h memo: "for 1 DealScreen's word rules found nothing else … that contradicts the statement" for ATG-022, beside a cited text naming Tessaly elsewhere (L1d) |
| 1 | L3c fixed by PLACE | **Refuted on PN-CASE** | `e2e/assert_h.log`: "the top-tier gate accepts it as a plain form for the buyer territory (US): a grant over other places only" for "LICENSED IN CHINA TO CHINACO PHARMA AND ELSEWHERE TO TESSALY PHARMA" (L3d) |
| 2 | Test counts (60 new; PLACE 32, SPK 5, QW 8, QT 6, DATE 9) | **Held** (60 collected); the suite has 1052 at HEAD | pytest |
| 2 | Q10, N3 kept as judgement | **Held** | Both still tier 0/1 (`rerun7n/g1.out`, `n1.out`) |
| 2 | Usefulness costs listed (press sentences, "said", "European", notes, colons) | **Held** | U4, U5, U7, U8, U15–U17 blocked (`rerun7n/u1.out`) |
| 3 | 876 tests pass; ruff, mypy clean | **Held** at beecfcd's scope; 1052 at HEAD | pytest, ruff, mypy |
| 3 | Reviewer's scripts re-run: g1 43 → 1, l1 11 → 3, u1 8 → 2, t1 1 → 0, n1 N3 only | **Reproduced byte for byte, but confounded** | My re-runs equal the implementer's `*.out`. But 36 of 47 g1 cases, 7 of 16 l1, 23 of 23 u1, 7 of 7 n1 cite the block "which says 'row'" from the harness quote "(test) row N". With a neutral quote: g1 2 top (G3e, a correct UK-buyer case, and Q10); l1 5 (adds L9, correct, and L10, the T1/O8 judgement); t1 1 (T4, clean); u1 9 (seven clean cases reach the top again); n1 4 (N1, N2, N4 are REREVIEW6's judgement items, not only N3). Clean usefulness is better than reported; the judgement items were never closed |
| 3 | ws_g 6 → 0; ws_d only the control; ws_e, ws_f none | **Held** | Fresh copies re-screened at HEAD |
| 3 | CLDN18.2 identical to revision 7; 0 of 62 scientific fields changed | **Held** | `cmp` of CSVs and memos; `compare.py` "0 of 62" |
| 3 | Cross-version 0 of 312; cycle-4 equivalence byte-identical, 4 of 4 | **Unverifiable** (not re-run) | Result files only (`scratchpad/rr8/equiv8.json`: byte_identical and fast_path on all four). Note: `research/dealscreen_product_program/cycle4/equivalence_result.json` is modified and uncommitted in the working tree |
| 3 | Usefulness 10/4/1 vs B 14/1/0 | **Held** | §6 |
| 4 | Costs: lower-case names ("Johnson and Johnson", "Laboratoires de X", "Acme plc") block | **Held, and wider** | Also "L & M Bio", "Kappa & Kappa" (an ampersand is not a name token; the CLDN18.2 landscape itself has a company written "L & L Bio"), "Chinaco Pharma International", "Asia Pacific Pharma" (`a/pf8.out`, `a/pf8b.out`); all passed at revision 7 |

## 2. Paths into the top tiers

### 2a. Party names (PN-CASE, PN-WORD)

`accepted_form` is the gate's own verdict (`a/pf8.out`). Per-program results are from `a/g8.out` (China license row
plus the text as a landscape cell on all three fields, and as an analyst geographic assertion).

| Id | Buyer | Text | Output (copied) | Expected |
|---|---|---|---|---|
| PN-CASE | US | "LICENSED IN CHINA TO CHINACO PHARMA AND ELSEWHERE TO TESSALY PHARMA" | `accepted='a grant over other places only'`; per program `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP` on us_rights, geographic and partnerships cells and the analyst assertion | blocked; Tessaly holds the rest |
| PN-CASE | US | "LICENSED IN CHINA TO CHINACO PHARMA AND THE REST TO TESSALY PHARMA"; "Licensed In China To Chinaco Pharma And In California To Tessaly Pharma"; "… And In Puerto Rico To …"; "… And Stateside To …"; "Licensed in China to Chinaco Pharma And Elsewhere To Tessaly Pharma" | accepted, tier 1 | blocked |
| PN-CASE → tier 0 | US | Availability row (Nerida Bio, US, 2025-03-01, quote "Nerida Bio: U.S. rights available") + geographic cell "LICENSED IN CHINA TO CHINACO PHARMA AND ELSEWHERE TO TESSALY PHARMA" | `AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED / AVAILABILITY_STATED_UNVERIFIED <<< TOP`; "reason: the landscape geographic rights note '…' (a grant over other places only)" | blocked |
| PN-CASE | EU | "LICENSED IN CHINA TO CHINACO PHARMA AND IN GERMANY TO TESSALY PHARMA"; "Licensed In China To Chinaco Pharma And In France To Tessaly Pharma" | tier 1 | blocked |
| PN-CASE | US+CA / JP | "Licensed In China To Chinaco Pharma And In Ontario To Tessaly Pharma"; "Licensed In Korea To Kappa Ltd And In Okinawa To Tessaly" | tier 1 / accepted | blocked |
| PN-WORD | US | "Licensed in China to Chinaco Pharma, Tessaly Pharma Has ROFN"; "…, ROFN Tessaly Pharma"; "…, ROFR Holder Tessaly Pharma"; "…, Tessaly Pharma Has First Look"; "…, Tessaly Pharma Opt-In" | accepted; tier 1 on all three fields and as analyst assertion | blocked: a third party's right of first negotiation/refusal or opt-in, scope unstated |
| PN-WORD | US | "Licensed in China to Chinaco Pharma, Subject To Tessaly Pharma Approval"; "…, Pending Tessaly Pharma Consent" | accepted; tier 1 | blocked: a condition (the same condition blocks as a quote prefix, SPK) |

Controls that held: "… And In The Americas To …", "… And All Other Markets To …", "…, US Rights To Tessaly",
"…, Option: Tessaly Pharma", "…, Tessaly Pharma Holds Option", "… & Tessaly Pharma LATAM" all `None`.

Cause:
- `_NAME_TOKEN` (`rights_allow.py:93`) accepts any word that starts with a capital or digit. In Title Case or ALL
  CAPS, "And", "In", "To", "The", "Rest", "Elsewhere", "Stateside", "Has", "Subject" are name tokens, so
  `_PARTY_NAME.fullmatch` passes the whole tail (`rights_allow.py:94, 104`). The rule assumes lower case marks
  "more text", which vendor exports in capitals break.
- `_PLACE_WORD` (`rights_allow.py:96-97`) and `_RIGHTS_TEXT` (`rights_allow.py:207-211`) are closed lists. They lack
  "elsewhere", "rest", "stateside", U.S. states and territories, EU member states, Canadian provinces, "ROFN",
  "ROFR", "first look", "opt-in", "consent", "approval", "subject", "pending". `_WIDER` in the gate has ROFN/ROFR, so
  the two modules disagree.

### 2b. Rows whose own territory covers the buyer territory (COVER)

U.S. license Nerida Bio → Alpha Bio, 2024-03-01, deal D1 (`a/g8.out`).

| Id | Input | Output (copied) | Expected |
|---|---|---|---|
| R1 | Termination linked D1, territory "United States", 2025-01-15, quote "Alpha Bio returns U.S. rights to Nerida Bio; Tessaly Pharma holds an option on U.S. rights" | `RIGHTS_RETURNED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP holder='Nerida Bio'`; "ask: Does Nerida Bio hold the returned US rights now, and have they been re-licensed since?" | blocked or OPTION_HELD; the quote names a third-party U.S. option |
| R2 | Return linked D1, US, quote "U.S. rights revert to Nerida Bio and are immediately re-licensed to Tessaly Pharma" | same, tier 1 | blocked |
| R3 | Termination linked D1, US, quote "Termination effective only after a 12-month transition; Alpha Bio sells in the U.S. until 2026" | same, tier 1 | blocked: not yet ended |
| R5 | U.S. option to Alpha Bio (D2) + lapse linked D2, US, quote "Alpha Bio let its option lapse; Tessaly Pharma has since licensed U.S. rights" | `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP` | blocked |
| R7 | Worldwide license (D3) + termination linked D3, "Worldwide", quote "Alpha Bio returns all rights except U.S. co-promotion rights, which Alpha Bio keeps" | `RIGHTS_RETURNED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP` | blocked (shared) |
| R8 | China license + acquisition of Nerida Bio by Omega Holdings, "Worldwide", 2025-02-01, quote "Omega Holdings acquires Nerida Bio; U.S. rights to NB-7 remain licensed to Tessaly Pharma" | `OWNER_ACQUIRED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP`, owner 'Omega Holdings'; "ask: Would Omega Holdings license or sell US rights?" | blocked. Control: the same acquisition with territory blank blocks ("names US, in the buyer territory") |
| R9 | R1 + availability row (US, 2025-03-01, "Nerida Bio: U.S. rights available") | `AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED / AVAILABILITY_STATED_UNVERIFIED <<< TOP` | blocked |
| R10 | EU buyer: EU license (D4) + termination linked D4, "Europe", quote "Alpha Bio returns European rights; Tessaly Pharma holds an option on EU rights" | `RIGHTS_RETURNED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP` | blocked |

Cause: `_quote_problem` returns None whenever `territory <= own` (`rights_gate.py:257-259`), for every row type
except availability statements. The comment "the ledger reads it as a grant there" is true only for grants. For
terminations, returns, lapses and acquisitions the clearing row is exactly the one whose quote must be read. Since
revision 6 (revision 7 skipped these rows too, `a/g8_rev7.out`); revision 8 states the skip as a rule.

### 2c. Quote clauses with no place or an unlisted wider word (QW2)

China license row, quote as given (`a/q8.out`, `a/g8.out` W). Each is
`NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP`, with "ask: Who holds US
rights? Recorded deals cover other territories only (licensor per evidence: Nerida Bio)."

| Kind | Quotes |
|---|---|
| Third-party grant, no place | "Chinaco Pharma licenses China rights; Nerida Bio also granted Tessaly Pharma a license to NB-7"; "…; Tessaly Pharma holds co-commercialization rights to NB-7"; "…; Tessaly Pharma has first right to negotiate any further license"; "…; Tessaly Pharma holds a buy-out right over NB-7"; "…; Tessaly Pharma acquired the remaining rights in 2024"; "…; the rest of NB-7 was sold to Tessaly Pharma"; "…; Tessaly Pharma holds the remaining territories" |
| Wider words not in `_WIDER` | "… and an opt-in to the remaining territories"; "… and all other markets"; "… rights in China and all other countries"; "Chinaco Pharma licenses ex China rights"; "… and non-China rights"; "… rights in China and beyond"; "… and may expand to further territories"; "…, with first refusal on any later deal" |
| U.S. places the reader does not know | "… and Puerto Rico rights"; "…; Tessaly Pharma licenses stateside rights"; "…; Tessaly Pharma licenses California rights" |

Expected: blocked (the first group should read like a grant with an unstated territory, AC3). Controls that block:
"… an option on worldwide rights", "…; Tessaly Pharma holds U.S. rights", "…; Tessaly Pharma has a right of first
refusal". Cause: a clause is read only when it names a buyer-territory place or matches `_WIDER`
(`rights_gate.py:260-264`); otherwise it is skipped, whatever party or right it names. `_WIDER`
(`rights_gate.py:226-228`) is a closed list.

### 2d. Dates (FUT, DATE-AV; `a/d8.out`)

| Id | Input | Output (copied) | Expected |
|---|---|---|---|
| FUT | China license + U.S. license to Tessaly Pharma, event date 2025-07-01, source date 2025-05-20 (announced before the as-of date, effective after) | `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP`; "reason: not applied, dated after the as-of date 2025-06-01: a license (2025-07-01) naming Tessaly Pharma"; "ask: Who holds US rights? Recorded deals cover other territories only" | encumbered, or blocked: the deal was known on the as-of date |
| FUT → tier 0 | Same license + availability row (US, 2025-03-01) | `AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED / AVAILABILITY_STATED_UNVERIFIED <<< TOP`, same "not applied" reason | CONFLICTING |
| FUT | U.S. license D1 terminated 2025-02-01; new U.S. license to Tessaly dated 2025-06-15, source 2025-05-30 (D3m) | `RIGHTS_RETURNED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP` | encumbered |
| DATE-AV | Availability row (US) dated "2025"; also "2025-06"; also undated with source "2025" | `AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED / AVAILABILITY_STATED_UNVERIFIED <<< TOP` each | blocked, as an ending with the same date is (D1a) |

Cause: `after_as_of` judges every record on the start of its event-date window (`rights_ledger.py:116`), never on
when it was reported, and adds only a reason (`rights_checks.py:85-89`), not a blocker. `straddling`
(`rights_ledger.py:119-120`) covers only `_CLEARS`, not `AVAILABILITY_STATED`. FUT is older (R1v3 N10). It bites in
live use: a vendor "Deal Date" is often the effective or closing date. DATE-AV only bites when the as-of date is in
the past (a replay); with as-of = today a statement cannot be dated later.

Held (`a/d8.out`): straddling endings block with "On what day did a termination (2025) naming Alpha Bio take
effect: before or after 2025-06-01?"; whole periods before the as-of date clear; an event on the as-of day applies; a
year-dated grant is applied (conservative). Judgement, unchanged: an ending dated before the as-of date but reported
in a later or year-dated source still clears (D1h, D1i, D3e; REREVIEW5 T1/O8).

### 2e. Speakers and offers (`a/g8.out` S, T)

No new top-tier path. Third-party prefixes, conditions after a stripped speaker, a second speaker and a ROFN after
the offer all block. Offers with no place ("Rights available", "Worldwide rights available") still count for any
buyer whose row covers it; a row with no territory counts for any buyer (Q10/T6, judgement as before). An offer row
whose territory is outside the buyer territory gives `NO_RIGHTS_EVIDENCE` (T2, T3, T5, T7).

### 2f. End to end (ws_h, C3 buyer, as-of 2026-10-29)

Outputs copied from `e2e/memo_h.md` and `ws_h/screening.json`.

| # | Program | Input added (fictional parties) | Output (copied) | Finding |
|---|---|---|---|---|
| 1 | ATG-022 | Z04 availability by Antengene Biologics, US, 2026-06-01, "Antengene Biologics: U.S. rights available"; Z05 China license; analyst geographic "LICENSED IN CHINA TO CHINACO PHARMA AND ELSEWHERE TO TESSALY PHARMA" | "#1 ATG-022: availability stated, unverified; … an analyst assertion geographic rights note 'LICENSED IN CHINA TO CHINACO PHARMA AND ELSEWHERE TO TESSALY PHARMA' (a grant over other places only)" | PN-CASE, tier 0 |
| 2 | QLS31905 | Z01 China license, quote "(test) Chinaco Pharma licenses China rights; Qilu Pharmaceutical also granted Tessaly Pharma a license to the program" | "#2 QLS31905: no third-party grant in evidence; … recorded grants do not cover US" | QW2 |
| 3 | JS107 | Z07 China license; Z08 U.S. license to Tessaly Pharma, Deal Date 2026-12-01, Source Date 2026-10-15 | "#3 JS107: no third-party grant in evidence; … not applied, dated after the as-of date 2026-10-29: a license (2026-12-01) naming Tessaly Pharma"; "ask: Who holds US rights? Recorded deals cover other territories only" | FUT, Q-FUT |
| 4 | BL-M05D1 | Z09 acquisition of Sichuan Baili Pharmaceutical by Omega Holdings, Worldwide, quote "(test) … U.S. rights to the program remain licensed to Tessaly Pharma"; Z10 China license | "#4 BL-M05D1: no third-party grant in evidence; rights position: owner acquired per evidence" | COVER |
| 5 | SKB315 | Z06 China license; analyst partnerships "Licensed in China to Chinaco Pharma, Tessaly Pharma Has ROFN" | "#5 SKB315: no third-party grant in evidence; … (a grant over other places only)" | PN-WORD |
| 6 | Spevatamig (PT886) | Z02 U.S. license to Alpha Bio; Z03 termination linked Z02, US, quote "(test) Alpha Bio returns U.S. rights; Tessaly Pharma holds an option on U.S. rights" | "#6 Spevatamig (PT886): no third-party grant in evidence; rights position: rights returned per evidence … rights returned per source to Phanes Therapeutics" | COVER |
| — | RC118 (unresolved) | Z12 availability by RemeGen, US, Deal Date "2026", no source date | `AVAILABILITY_STATED_UNVERIFIED`, holder 'RemeGen' (JSON; workbook Diligence: "rights position per evidence: AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED") | DATE-AV |
| 8 | TORL-2-307-ADC | Z11 China license, quote "(test) … TORL Biotherapeutics retains rights in the rest of the world" | "#8 TORL-2-307-ADC: rights unresolved; … which says 'rest of the world', which may reach beyond the row's own territory" | usefulness cost (§3) |

So test inputs take #1 (tier 0) and #2–#6 (tier 1) for the CLDN18.2 buyer.

## 3. Over-caution and usefulness

These are usefulness costs, not safety errors.

| Input | Revision 8 | Revision 7 | Note | Cause |
|---|---|---|---|---|
| China license row quotes: "Chinaco Pharma obtains exclusive China rights to NB-7, a potential new treatment option for gastric cancer"; "…, its third China deal in a row"; "Chinaco Pharma International obtains exclusive rights to NB-7 in mainland China"; "… in mainland China, except for diagnostic uses"; "Chinaco Pharma will pay royalties on net sales in mainland China, excluding sales by Nerida Bio"; "… Nerida Bio will continue global development outside China" | blocked: "which says 'option'" / "'row'" / "'International'" / "'except'" / "'excluding'" / "'global'" | tier 1 | **New.** Ordinary press words block a clean deal | `_WIDER` (`rights_gate.py:226-228`) matches "option", "except", "international", "global", "outside", "excluding", and "ROW" case-insensitively (the territory reader reads only capital "ROW", `rights_territory.py:45`) |
| China license row: "… Nerida Bio retains rights in the rest of the world"; "… retains all rights in the U.S. and the rest of the world" (REREVIEW6 U2; ws_h #8) | blocked | blocked | Claimed fixed; only the short "…; Nerida Bio retains U.S. rights" passes | `_RETAINS` (`rights_allow.py:75-76`) allows no place after "rights" except "in the us" |
| Text names: "Licensed in China to L & M Bio", "… to Kappa & Kappa", "… to Chinaco plc", "… to Kappa and Kappa", "… to Laboratoires de Chinaco", "… to Chinaco Pharma International", "… to Asia Pacific Pharma", "… to Chinaco Pharma and Kappa Ltd" | blocked | tier 1 | **New.** Lower case acknowledged in the response; "&", "International", "Asia Pacific" not | `_NAME_TOKEN`, `_PLACE_WORD` |
| Availability press sentences (U4, U5), "European rights available" (U7, U8), notes and colons in Partnerships (U15–U17), "U.S. and EU rights available", "Unpartnered outside China", "No U.S. partner" | blocked | blocked | Unchanged, acknowledged | closed word lists |
| Clean controls: current China-only license; "Ex-China rights retained"; "Nerida Bio retains all rights outside Greater China"; company "Nerida Bio (Hong Kong) Limited"; licensee "Chinaco Pharma (Shanghai) Co., Ltd." as a row party; returned then dated statement | tier 1 / tier 0 | same | Clean, held (`rerun7n/u1.out` with a neutral quote) | |

Judgement (introduced by revision 8): "Chinaco Pharma licenses China rights; U.S. rights: TBD" now passes as "no
grant stated" (tier 1; blocked at revision 7). "TBD" may mean "under negotiation".

## 4. Output honesty

In favour: the CLDN18.2 memo and workbook call nothing available or open; every holder and owner shown in
CLDN18.2 and in ws_h is cited by row; the ws_h memo prose has no position or tier codes (the only all-caps tokens are
quoted fixture text and "SYNTHETIC_FIXTURE"). HEAD adds the memo line "15 unresolved program(s) have one open gate"
(cycle U1): "open" there means an undecided scientific gate, not rights; I note it against AC2's literal wording only.

| # | Where | Output (copied) | Problem | Cause |
|---|---|---|---|---|
| Q-FUT | ws_h memo #3 JS107 | "ask: Who holds US rights? Recorded deals cover other territories only (licensor per evidence: NingBo Junyan Hongshi Biosciences)." beside "evidence (rights row 25): 2026-12-01 (source 2026-10-15) license, Tessaly Pharma …, United States" | The question says what the cited row contradicts | `rights_position.py:546`; FUT |
| L3d | `e2e/assert_h.log` | "Beside a clear position, the top-tier gate accepts it as a plain form for the buyer territory (US): a grant over other places only; it is still unverified." for "LICENSED IN CHINA TO CHINACO PHARMA AND ELSEWHERE TO TESSALY PHARMA" | The note reports PN-CASE as the gate's verdict (L3c class, claimed fixed by PLACE) | `cli/dealscreen.py:113`; PN-CASE |
| L1d | ws_h memo line 9 | "for 1 DealScreen's word rules found nothing else in the rights texts, names, rows and row quotes that contradicts the statement or that they cannot read (word rules can miss a condition written in other words)" | The program is ATG-022, whose cited analyst note gives Tessaly Pharma "ELSEWHERE". The hedge helps; the first clause is still false here | `memo.py:530-532` (HEAD); PN-CASE |
| (COVER) | ws_h #6 | "rights returned per source to Phanes Therapeutics"; ask "Does Phanes Therapeutics hold the returned US rights now …?" | No question names the Tessaly option the cited quote states (AC11) | §2b |

## 5. Acceptance criteria

| AC | Verdict | Evidence |
|---|---|---|
| AC1 | PASS | ws_h: "29 events, 0 rejected rows (license public/research_only)"; profile import; provenance in every evidence line |
| AC2 | PARTIAL | CLDN18.2: no OPEN tier, nothing called available. Held out: tier 0 beside an ALL-CAPS third-party text (ws_h #1), beside a covering termination whose quote names a third-party option (R9), on a future-effective third-party license (D3g), and on a statement dated only to the as-of year (RC118). L1d overclaims |
| AC3 | PARTIAL | Rights-file territories parse; QT fixed. Not met: PN-CASE and PN-WORD read a third-party grant or right as "other places only"; a quote naming a third-party grant with no territory is not treated as unstated (QW2) |
| AC4 | PARTIAL | DATE fixed for endings; returns and re-licensing work. Not met: a return/termination row covering the buyer is accepted whatever its quote says (COVER); LM-302 still not RETURNED (data) |
| AC5 | PASS on my inputs | Year-dated lapse blocks (D1k); exercises (D3k), expired options (L7) behave. R5's lapse quote is a COVER issue |
| AC6 | PARTIAL | Not met: PN-CASE/PN-WORD texts pass instead of conflicting; a known third-party U.S. license beside an availability statement is tier 0, not CONFLICTING (FUT) |
| AC7 | PARTIAL | DATE fixed for endings and statuses. Not met: DATE-AV, FUT; T1/O8 kept as judgement |
| AC8 | PASS | `compare.py` 0 of 62 on `after_v8` and on the HEAD re-screen; HEAD transaction and commercial outputs identical. Cross-version and cycle-4: result files only, not re-run |
| AC9 | PARTIAL | Territory, encumbered treatment, returned preference, age work; offers compared with the buyer territory (QT). Not met: the party-name rule depends on letter case (PN-CASE, incl. EU/JP/US+CA); non-U.S. availability quotes still never pass (usefulness) |
| AC10 | PARTIAL | Every gate text and quote is cited. Not met: false "(a grant over other places only)" labels (PN-CASE, PN-WORD); Q-FUT question contradicts a cited row |
| AC11 | PARTIAL | Not met: COVER, QW2 and PN cases ask no question naming Tessaly; Q-FUT |
| AC12 | PASS | 0 CLDN18.2 company or program names among the 230 strings (`/tmp/claude-1000/rr5/ac12_names.txt`) in the 1,422 lines added to `src/` since 50fd206; the only hits are the generic words "American" and "Single" |
| AC13 | PARTIAL | Unchanged: IBI343, SHR-A1904 not unobstructed; RC148, FL-301, XNW27011 encumbered; LM-302 CONFLICTING, not returned |
| AC14 | FAIL | 6 new High errors on held-out inputs; none in the CLDN18.2 output |

## 6. CLDN18.2 measured against the reference and B

| Item | Revision 7 | Revision 8 / HEAD |
|---|---|---|
| `after_transaction.csv` (62 programs) | — | byte-identical; HEAD re-screen identical |
| Memo | — | identical (HEAD adds only the U1 one-gate lines) |
| Scientific fields vs frozen baseline | 0 of 62 | 0 of 62 (`compare.py`) |
| Top-tier programs | 0 | 0 (44 rights unresolved, 17 deprioritized, 1 excluded by preference) |

Error classes against `reference_calls.csv` (re-read for the 15 deal programs from `after_v8/after_transaction.csv`;
identical to REREVIEW6 §7b): false unobstructed **0**; false encumbrance 0 definite, 2 likely outdated (EO-3021,
SYSA1801; stale-flagged); wrong holder 1, labelled (LM-302 "Turning Point Therapeutics (recorded; conflicting)");
wrong territory 0; missed return 1 (SKB315; LM-302 shown as conflicting).

Usefulness against general Claude (B), same 15 programs and scoring as REREVIEW6 §7c: DealScreen **10 right / 4
partial / 1 missed**; B **14 / 1 / 0**. No advantage is demonstrated. None of this review's errors shows in the
CLDN18.2 output: its landscape has no rights text in capitals, its covering rows have no third-party quotes, and its
rights file has no availability rows or future-dated grants.

## 7. Remaining issues, ranked

1. **(Safety, High) COVER.** A termination, return, lapse or acquisition row covering the buyer territory is
   accepted without reading its quote; a quote naming a third party's U.S. option, re-license or retained right
   gives tier 1 (tier 0 with a statement). ws_h #4, #6.
2. **(Safety, High) PN-CASE, PN-WORD.** The party-name rule is a capital-letter test; Title Case, ALL CAPS and
   capitalised ROFN/ROFR/opt-in/consent words pass. ws_h #1 (tier 0), #5.
3. **(Safety, High) FUT.** A third-party grant announced before the as-of date but effective after it is dropped;
   tier 1, tier 0 with a statement. Live use, not only replays. ws_h #3.
4. **(Safety, High) QW2.** Quote clauses naming a third-party grant without a place, or using wider words not on
   the list, pass. ws_h #2.
5. **(Safety, High, replay) DATE-AV.** Availability statements dated only to the as-of year or month count.
6. **(Usefulness, new)** `_WIDER` blocks ordinary press words ("option", "row", "International", "except",
   "excluding", "global"); names with "&", "plc", "International" block. On a real vendor export this will hold back
   most clean China-license programs.
7. **(Process)** The implementer's re-run counts rest on a harness quote containing "row"; they overstate blocking
   and hide three judgement items (N1, N2, N4) and two ledger cases (L9 correct, L10 judgement).
8. **(Judgement)** Q10, N1/N2/N4, T1/O8 (D1h, D1i, D3e), "U.S. rights: TBD" as no grant, rows keyed by program name.
9. **(Low)** Q-FUT, L3d, L1d.
10. **(Recall)** The rights file still caps recall (LM-302's successor, SKB315's return, EO-3021's discontinuation).

## 8. The single highest-value next fix

Read every cited row's quote, for every row type, with one fail-closed rule: a quote passes beside a clear position
only if every clause either is a plain form for the buyer territory or names no party other than the row's own
parties and the company. Delete the `territory <= own` shortcut (`rights_gate.py:257-259`), which today lets every
covering ending and acquisition through unread. A clause naming any other party (a capitalised name not equal to
the row's grantor, grantee or the company) blocks with a question naming that party. This one change closes COVER
and most of QW2, and it does not depend on a word list. Do the party-name rule the same way: compare the party span
with the clause's own case-folded words, so that "AND", "TO", "IN", "THE", "ELSEWHERE" inside it fail (PN-CASE).

Two small fixes follow. Judge whether a record was known on the as-of date by its source date when it has one, and
keep a grant reported before the as-of date as a grant (FUT). Extend `straddling` to `AVAILABILITY_STATED`
(DATE-AV). To limit the new usefulness cost, match "ROW" only in capitals and treat "option" as wider only in the
reader's own `_OPTION` sense ("option to/on/for … rights/license").
