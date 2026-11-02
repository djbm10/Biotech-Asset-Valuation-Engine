# Adversarial re-review 8: cycle R1 revision 9, rights evidence (CLDN18.2)

**AI-SIMULATED INTERNAL REVIEW.** I am an AI (Claude) playing a skeptical pharma BD analyst and auditor. I am not a
human reviewer. I approve nothing, and nothing here is validation. I did not trust REREVIEW7_RESPONSE.md. I checked
each claim by running code or reading outputs. I report only what I ran or read.

Scope and method:
- Revision 9 is commit b3e3fe9 (HEAD). Its parent 04faab7 carries R1 revision 8. I recorded the SHA-256 of all 34
  files in `src/bve/dealscreen/` at the start (`/tmp/claude-1000/rr9/sha_start.txt`) and at the end (`sha_end.txt`).
  No file changed. I edited nothing except this file. No commit, stash or git change. ruff ran with `--no-cache`;
  mypy's cache went to `/tmp/claude-1000/rr9/`.
- All scripts, workspace copies and outputs are in `/tmp/claude-1000/rr9/`. Per-program cases go through
  `screening.program_transaction` with the previous reviewer's harness `h5.py` (copied, default quote
  "(test) record N"). Defaults: landscape company "Nerida Bio", buyer {US}, as-of 2025-06-01, max age 730 days,
  `encumbered_rights: deprioritize`. "China license" is one row Nerida Bio → Chinaco Pharma, exclusive, mainland
  China, 2025-01-01. "US license D1" is Nerida Bio → Alpha Bio, United States, 2024-03-01, ended by a termination
  linked to D1, United States, 2025-01-15. New scripts: `a/q9.py` (party and hedge rules on endings), `a/w9.py`
  (China-row quotes, `_WIDER`, press wording), `a/pn9.py` (party names), `a/d9.py` (dates, dropped rows),
  `a/u9.py` (headlines).
- Revision 8 comparison: `git archive 04faab7 src/bve` into `rr9/rev8/`. The same scripts against it give
  `a/*_rev8.out`; `a/cmp_rev8.txt` lines them up.
- End to end: `e2e/ws_h` (REREVIEW7's workspace, re-imported and re-screened at HEAD) and `e2e/ws_i`, a copy of
  `~/.cache/rights_v1/after9f_ws` (C3 buyer, as-of 2026-10-29) with rows Z01–Z17 (`e2e/rights_i.csv`) and two
  analyst assertions (`e2e/assert_i.log`, reviewer kind SYNTHETIC_FIXTURE). Counterparties are fictional (Tessaly
  Pharma, Chinaco Pharma, Alpha Bio, Omega Holdings, Sideco Bio). Quotes start "(test)"; URLs are `example.test`. A
  landscape company appears only as licensor or acquired party. Nothing here is a fact about a real program.
- Checks: `tests/dealscreen` at HEAD: **1178 passed** (92 s). `test_rights_rereview7.py`: 79 collected. ruff: "All
  checks passed!". mypy `src/bve/dealscreen` + CLI: "Success: no issues found in 35 source files". `compare.py`
  against the frozen baseline: "AC8 scientific fields changed: 0 of 62" (on `after_v9` and on my HEAD re-screen).

## Summary

- **Every input REREVIEW7 reported now blocks.** PN-CASE, PN-WORD, COVER R1–R10, QW2, FUT, DATE-AV and the ws_h
  placements are all `RIGHTS_UNRESOLVED` at HEAD. My re-runs of the previous probe scripts are byte-identical to the
  implementer's.
- **Each fix is still a closed word list, and each list has gaps.** Close variants reach the top tiers again:
  - a third party with no corporate word, or with a verb the list lacks ("U.S. rights are now held by Tessaly",
    "Tessaly will commercialize NB-7 in the U.S.", "Tessaly's U.S. license is unaffected");
  - "a subsidiary of Tessaly Pharma" is deleted from the clause wherever it stands, so "U.S. rights are now held
    by a subsidiary of Tessaly Pharma" reads as clean;
  - endings that are not yet in effect or are partial, in words the hedge list lacks ("will return U.S. rights …
    on 1 January 2026", "intends to return", "with the exception of", "apart from", "most");
  - wider reach in words `_WIDER` lacks ("other markets", "other countries", "everywhere else");
  - party-name words `_NOT_IN_NAME` lacks ("Tessaly Pharma Everywhere Else", "… Western Hemisphere", "… ROTW").
- **Revision 9 opened one new path.** The narrowed `_WIDER` no longer reads the row's own licensee holding "an
  exclusive option" (no rights word follows), nor "international development and commercial rights". Tier 1.
- **FUT is fixed only when the source date is a day on or before the as-of date.** A future-dated U.S. grant with no
  source date, or a source date given only as a month or year, is still dropped (tier 1; tier 0 with a statement).
  In live use (as-of = today) a future-dated row in today's export is known today.
- **An older path, first reported here.** An acquisition of a party that is in no grant and is not the company
  ("Omega Holdings acquires Sideco Bio") gives `OWNER_ACQUIRED` tier 1. Beside a return, the same row is not cited,
  so its quote is never read.
- **New usefulness costs.** The party rule reads a program code after "rights to" as a company ("granted Chinaco
  Pharma exclusive rights to NB-7" blocks and says "names NB-7"). The hedge rule blocks clean wording ("after a
  strategic review", "will continue to develop", any lapse quote that says "option"). Advisers, investors, name
  variants, Title Case headlines and ALL CAPS quotes block.
- **CLDN18.2 is unchanged.** `after_v9/after_transaction.csv` is byte-identical to `after_v8`; the memo differs only
  by cycle U1's gate lines; a HEAD re-screen of `after9f_ws` equals `screening_R1v9.json`. 0 top-tier programs.
  0 of 62 scientific fields changed.

Definite new errors (not reported in REREVIEW7.md). None occurs in the CLDN18.2 output.

| Severity | Introduced by revision 9 | Claimed fixed, fails on a close variant | Older, first reported here | Total |
|---|---|---|---|---|
| High: tier 0 or 1 while a third party may hold buyer-territory rights, or on contrary, conditioned or future evidence | 1: WN | 5: PARTY2, HEDGE2, WIDER2, PN3, FUT2 | 1: ACQ-X | **7** |
| Medium: false encumbrance, false conflict, or a missed encumbrance that changes the tier | 0 | 0 | 0 | **0** |
| Low: false label, wording or citation; no tier change | 2: LBL-CODE, LBL-NONE | 3: L3e (assert note), L1e (memo sentence), Q-FUT2 | 1: ACQ-X wording | **6** |

All seven High errors reach a top tier end to end (§2g), except ACQ-X and one PARTY2 case, which land only on
programs the C3 buyer deprioritises by sponsor; their own top-tier blocker lists are empty. Six of the seven were
already top tier at revision 8 (`a/cmp_rev8.txt`); revision 9 did not close them. WN is top tier only at revision 9.

## 1. REREVIEW7_RESPONSE.md, claim by claim

| § | Claim | Verdict | Evidence (run or read) |
|---|---|---|---|
| 1 | The `territory <= own` shortcut is gone; every cited non-availability quote is read | **Held for cited rows** | COVER R1–R10 all block (`prev/g8.out`). A row that is not cited is still not read: ACQ-X beside a return (§2f) |
| 1 | Another company = capitalised run with a corporate word, or a capitalised name that holds, takes or receives rights | **Held as written. Refuted as a safety rule** | "Tessaly holds U.S. rights" blocks (A20). "are now held by Tessaly", "belong to Tessaly", "Tessaly will commercialize", "partnered with Tessaly", "Tessaly's U.S. license", "U.S. licensee: Tessaly", "licensee is TPC" pass (PARTY2) |
| 1 | "X, a subsidiary of Y" describes the row's own party | **Refuted** | `_DESCRIBES` deletes the phrase anywhere in the clause, not only after a row party: "U.S. rights are now held by a subsidiary of Tessaly Pharma" passes (A8) |
| 1 | Places, roles and pronouns are not parties; "no list of company names" | **Partly refuted** | A program code after "rights to" is read as a party: "names NB-7", "names ASP546C" (LBL-CODE). Title Case headline words become a "company": "names Chinaco Pharma Acquires Development" |
| 1 | A partial, conditional or not-yet-effective ending blocks (hedge words) | **Held for listed words. Refuted as a safety rule** | "except", "until", "only", "keeps", "re-licensed", "option" block. "will return … on 1 January 2026", "takes effect in 2026", "intends", "negotiating", "may terminate", "with the exception of", "apart from", "most", "disputed", "arbitration" pass (HEDGE2) |
| 1 | A capitalised name before "rights" that the reader cannot read blocks | **Held** | "Hawaii rights", "Puerto Rico rights", "California rights" block. Places after "in" are not read: "rights in mainland China and Puerto Rico" / "… and Guam" pass (WIDER2) |
| 2 | PN-CASE, PN-WORD closed by `_NOT_IN_NAME` | **Held for the listed words. Refuted on close variants** | All 11 REREVIEW7 P texts block. "Tessaly Pharma Everywhere Else / Otherwise / Western Hemisphere / ROTW / WW / Beyond / Upon Exercise / Thereafter / Remainder / North / Pre-Emption / Veto" are accepted (PN3) |
| 2 | "&" may join name words, not two companies | **Held as written. Judgement** | "Chinaco Pharma & Tessaly Pharma" refused. "Chinaco Holdings & Tessaly Pharma", "Chinaco Inc. & Tessaly Pharma", "Chinaco & Tessaly" accepted ("holdings" and "inc" are not in `GENERIC_NAME_WORDS`). Each names China only, so no buyer-territory reach |
| 2 | COVER R1–R10 closed; a plain ending still clears | **Held** | R1–R8, R10 block; C1, C6, C8, C9 clear (`a/q9.out`) |
| 2 | QW2 closed; wider list extended | **Held for REREVIEW7's inputs. Refuted on close variants** | All 18 W inputs block. "other markets", "other countries", "other major markets", "everywhere else", "additional territories", "further countries", "all markets", "rest of the globe", "expansion rights", "NA" pass (WIDER2) |
| 2 | FUT: a grant announced before the as-of date and effective after it blocks | **Held for a day source date. Refuted on close variants** | D3f, D3g, D3m, E4, E5, E6 block. No source date, source "2025", source "2025-06": tier 1; tier 0 with a statement (FUT2) |
| 2 | DATE-AV: a statement dated to a period containing the as-of date blocks | **Held** | S2, S3, RC118 block. But the position then reads `NO_RIGHTS_EVIDENCE` beside the cited row (LBL-NONE) |
| 2 | Q-FUT: question says "in force on the as-of date" | **Held when the grant is "announced"** | Not for FUT2: ws_i JS107 still asks "Recorded deals cover other territories only" beside a cited U.S. license to Tessaly (Q-FUT2) |
| 2 | L3d follows from PN-CASE | **Refuted on PN3** | `e2e/assert_i.log`: "the top-tier gate accepts it as a plain form for the buyer territory (US): a grant over other places only" for "Licensed in China to Chinaco Pharma, Tessaly Pharma Everywhere Else" (L3e) |
| 2 | L1d: ws_h no longer has a tier-0 program | **True for ws_h. Not a fix** | ws_i memo line 9: "for 1 DealScreen's word rules found nothing else … that contradicts the statement" for ATG-022, beside "Tessaly Pharma Everywhere Else" (L1e) |
| 2 | Usefulness: ordinary "option", lower-case "row", "International", "global", "except" no longer block; "retains rights in the rest of the world" is a plain form | **Held** | q8 tops: the treatment-option, "in a row", "Chinaco Pharma International", rest-of-world cases reach tier 1. The same narrowing opened WN (§2c) |
| 3 | 1,178 tests pass; 79 in `test_rights_rereview7.py`; ruff, mypy clean | **Held** | pytest, ruff, mypy |
| 3 | CLDN18.2: 0 of 62 science changed; 0 of 62 transaction views differ from revision 8 | **Held** | `cmp` of CSVs; HEAD re-screen JSON equal to `screening_R1v9.json`; `compare.py` "0 of 62" |
| 3 | Cross-version 0 of 312; cycle-4 equivalence 4 of 4 | **Unverifiable** (not re-run) | Result directories `~/.cache/rights_v1/xv9f`, `eq9f` exist; I did not re-run them |
| 3 | ws_h: six placements and RC118 now unresolved; TORL to tier 1 | **Held** | My re-import and re-screen of ws_h equals the implementer's tiers line for line (`e2e/tiers_h.txt`); memo identical |
| 3 | Probe counts d8 17→10, g8 53→20, q8 11→8, pf8 48→29, pf8b 3→6 | **Held** (byte-identical outputs) | `prev/*.out` |
| 3 | "Every remaining top-tier result is a clean control or a judgement item"; "the new accepted forms are all §3 usefulness cases" | **Held for d8/g8/q8. Refuted for pf8** | Accepted pf8 forms include REREVIEW7's own attack inputs, carried since revision 7: "… Chinaco Pharma, Tessaly Pharma NA", "… Tessaly Pharma Delaware", "… Tessaly Pharma Inc., New Jersey", "… Chinaco Pharma Plus Tessaly Pharma", "… Chinaco Pharma TBD". Each is tier 1 per program (`a/pn9.out`). "NA" may mean North America |
| 3 | Real CLDN18.2 quotes: 1 of 17 blocks (row 10) | **Held** | `real_quotes.out`: only row 10 ("says 'worldwide'") |
| 4 | Costs: lower case and verb-less third parties missed; "Kappa and Kappa" refused; "subsidiary of Y" read as describing | **Held, and wider** | Lower case "tessaly pharma holds an option" happens to block on "option"; PARTY2 shows the miss is much wider than lower case. The subsidiary rule is a safety error (A8), not only a cost |

## 2. Paths into the top tiers

### 2a. Third parties the party rule misses (PARTY2)

US license D1 + termination linked D1; the quote varies (`a/q9.out`). Each gives
`RIGHTS_RETURNED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP holder='Nerida Bio'`, ask "Does Nerida Bio
hold the returned US rights now, and have they been re-licensed since?". Expected: blocked, with a question naming
Tessaly.

| Id | Termination quote |
|---|---|
| A1 | "Alpha Bio returns U.S. rights to Nerida Bio; U.S. rights are now held by Tessaly" |
| A3 | "Alpha Bio returns U.S. rights to Nerida Bio, which has since licensed them to a new partner" |
| A4 | "…; Tessaly will commercialize NB-7 in the U.S." |
| A5 / A6 | "…; NB-7 is partnered with Tessaly in the U.S." / "…; U.S. rights now belong to Tessaly" |
| A8 | "…; U.S. rights are now held by a subsidiary of Tessaly Pharma" |
| A9 | "…; an affiliate of Tessaly Pharma holds U.S. rights" |
| A10 / A11 | "…; Tessaly's U.S. license is unaffected" / "…; Tessaly co-commercializes NB-7 in the U.S." |
| A12 / A13 | "…; U.S. rights were acquired by Tessaly" / "…; U.S. commercialization is led by Tessaly" |
| A14 / A15 | "…; the U.S. licensee is TPC" / "…; U.S. licensee: Tessaly" |
| A18 / A19 | "…; the program is now in-licensed by Tessaly in the U.S." / "…; Nerida Bio signed a U.S. deal with Tessaly" |

Also: acquisition of Nerida Bio by Omega Holdings + China license, quote "Omega Holdings acquires Nerida Bio; U.S.
rights to NB-7 are held by Tessaly" → `OWNER_ACQUIRED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP`
(B20). China license with no place: "…; Tessaly's license to NB-7 is unaffected", "…; Nerida Bio's other partner for
NB-7 is Tessaly", "…; an affiliate of Tessaly Pharma holds a license to NB-7", "…; NB-7 is also partnered with
Tessaly", "…; co-exclusive with kappa bio" → `NOT_ENCUMBERED… / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP` (W1–W4,
W27). Controls that block: "Tessaly Pharma" (corporate word), "Tessaly holds U.S. rights", "granted them to
Tessaly".

Cause:
- `_other_parties` (`rights_gate.py:299`) finds a party only through `_CORPORATE` (`:261`), `_VERB_PARTY` (`:268`) or
  `_TO_PARTY` (`:271`). A one-word name is found only as the subject of a listed active verb or the object of
  "sold/licensed/granted/… to". Passive voice ("held by", "acquired by", "led by"), other verbs ("commercialize",
  "belong", "partnered with"), possessives and colons are not on any list.
- `clause = _DESCRIBES.sub(" ", clause)` (`:308`) removes "a/an/the subsidiary|affiliate|unit|division of <Name>"
  wherever it occurs. Nothing checks that the phrase follows a row party.
- On a termination the U.S. place is the row's own, so the second loop (`:375`) returns early; only the party and
  hedge rules stand.

### 2b. Endings the hedge rule passes (HEDGE2)

Same US license D1 + termination; each gives `RIGHTS_RETURNED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<<
TOP` (`a/q9.out`). Expected: blocked (not yet in effect, partial or disputed).

| Kind | Termination quote |
|---|---|
| Not yet in effect | B1 "Alpha Bio will return U.S. rights to Nerida Bio on 1 January 2026"; B2 "Alpha Bio gave notice to terminate; termination takes effect in 2026"; B4 "… effective on 1 March 2026"; B5 "Alpha Bio intends to return U.S. rights to Nerida Bio"; B6 "… are negotiating the return of U.S. rights"; B11 "Alpha Bio may terminate the U.S. license"; B12 "Alpha Bio served a 180-day termination notice on the U.S. license" |
| Partial | B3 "…, with the exception of co-promotion rights"; B7 "Alpha Bio returns most U.S. rights to Nerida Bio"; B8 "…, apart from co-promotion rights"; B9 "…; Alpha Bio will still co-promote NB-7"; B13 "… and will stay on as U.S. co-promotion partner" |
| Disputed | B10 "…; the termination is disputed by Alpha Bio"; B14 "…; Alpha Bio has started arbitration over the termination" |
| Lapse | B15 option D2 + lapse, quote "Alpha Bio's U.S. right was extended by twelve months" → `NOT_ENCUMBERED… / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP` |
| Pending acquisition | B18 "Omega Holdings to acquire Nerida Bio for $1.1 billion"; B19 "Omega Holdings agreed to acquire Nerida Bio; closing is expected in the third quarter" → `OWNER_ACQUIRED / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP` (judgement: an owner change, not a third-party grant) |

Cause: `_HEDGE` (`rights_gate.py:255`) is a closed list. "exception" does not match `\bexcept\b`; "will", "effective",
"takes effect", "intends", "notice", "may", "most", "apart from", "still", "disputed", "arbitration" are absent. A
B1-type quote is also a date problem: the row's event date is before the as-of date and the quote's is after; no
rule compares them.

### 2c. Wider reach `_WIDER` misses (WIDER2) and reach it stopped catching (WN, new)

China license row, quote as given (`a/w9.out`). Each is `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE /
NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP`, ask "Who holds US rights? Recorded deals cover other territories only".
Expected: blocked.

| Id | Kind | Quote | Revision 8 |
|---|---|---|---|
| WN (W5) | Own licensee's option, scope unstated | "Chinaco Pharma licenses China rights and also receives an exclusive option" | blocked |
| WN (W26) | Same | "Chinaco Pharma licenses China rights and has an option to expand" | blocked |
| WN (W14) | Wider rights | "Chinaco Pharma licenses China rights and international development and commercial rights" | blocked |
| WIDER2 | Other places | W6 "… holds a license in other major markets"; W7 "… rights in China and in other countries"; W8 "… in China and other markets"; W9 "… may add additional territories"; W10 "… in China and everywhere else"; W12 "… may opt into further countries"; W19 "… rights in all markets"; W20 "… and the rest of the globe"; W21 "…; the remainder of the world goes to Chinaco Pharma in 2026"; W18 "…, with expansion rights"; W17 "… in China and NA" | tier 1 |
| WIDER2 | U.S. places after "in" | W15 "… rights in mainland China and Puerto Rico"; W16 "… and Guam" | tier 1 |

Judgement: W13 "… with a path to a global partnership" (tier 1 at revision 9, blocked at revision 8).

Cause: `_WIDER` (`rights_gate.py:237-245`). Revision 9 made "option" count only as "option to/on/for/over" with a
rights word within 60 characters, and "international" only before rights/territories/markets. A bare "an exclusive
option" or "international development and commercial rights" no longer matches. The other words were never listed.
`_NAMED_RIGHTS` (`:248`) reads only a capitalised name directly before "rights", so a U.S. place after "in" is not
read.

### 2d. Party names in rights texts (PN3)

China license row + the text as a landscape geographic cell, a Partnerships cell and an analyst geographic assertion
(`a/pn9.out`). Each text: `accepted_form` = 'a grant over other places only'; tier
`NO_THIRD_PARTY_GRANT_IN_EVIDENCE` on all three. Beside an availability row (Nerida Bio, US, 2025-03-01) the program
is `AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED / AVAILABILITY_STATED_UNVERIFIED <<< TOP` (PN-T0, PN-T0b).

| Texts (each "Licensed in China to Chinaco Pharma, Tessaly Pharma …") | Expected |
|---|---|
| "Everywhere Else", "EVERYWHERE ELSE" (all caps), "Otherwise", "Remainder", "Beyond", "North", "Western Hemisphere", "ROTW", "WW" | blocked: Tessaly holds the rest |
| "Upon Exercise", "Thereafter", "Thereon", "Pre-Emption", "Veto" | blocked: a condition or a right |

Cause: `_NOT_IN_NAME` (`rights_allow.py:113-120`) and `_PLACE_WORD` (`:106`) are closed lists; `_PARTY_NAME`
accepts any capitalised token. REREVIEW7's own pf8 inputs "Tessaly Pharma NA", "Delaware", "Inc., New Jersey",
"Plus Tessaly Pharma", "TBD" are still accepted (since revision 7).

### 2e. Dates (FUT2; `a/d9.out`)

| Id | Input | Output (copied) | Expected |
|---|---|---|---|
| E1 | China license + US license to Tessaly Pharma, event 2025-07-01, **no source date** | `NOT_ENCUMBERED… / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP`; "reason: not applied, dated after the as-of date 2025-06-01: a license (2025-07-01) naming Tessaly Pharma"; "ask: Who holds US rights? Recorded deals cover other territories only" | blocked: when it was known is not stated |
| E1b | E1 + availability row (US, 2025-03-01) | `AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED / AVAILABILITY_STATED_UNVERIFIED <<< TOP` | CONFLICTING or blocked |
| E2 / E3 | Same license, source date "2025" / "2025-06" (periods containing the as-of date) | tier 1, same reason | blocked, as a straddling ending is |
| E7 | Live use: as-of 2026-11-02; US license to Tessaly dated 2027-01-01, no source date | tier 1 | blocked: the row is in today's export |
| Held | E4 (event "2025-07", source 2025-05-20), E5 (event "2026"), E6 (day dates) | `RIGHTS_UNRESOLVED` with "reported before the as-of date … but effective after it" | — |

Cause: `self.announced` (`rights_ledger.py:124-125`) requires `e.source_date` and judges it on the end of its
period. A future-dated grant with no source date, or with a coarse one, is in `after_as_of` only, which adds a reason
and no blocker. In live use a vendor's "Deal Date" is often a future effective date and the export often has no
separate source date.

### 2f. An acquisition of a party in no grant (ACQ-X; older)

| Id | Input | Output (copied) | Expected |
|---|---|---|---|
| F1 / F1b | China license + acquisition of Sideco Bio by Omega Holdings, Worldwide, 2025-02-01; quote "Omega Holdings acquires Sideco Bio, which holds U.S. rights to NB-7" (F1) or neutral (F1b) | `OWNER_ACQUIRED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP holder='Nerida Bio' owner='Nerida Bio'`; "reason: Omega Holdings acquired Sideco Bio (the company or its rights to this program) per source; no third-party grant recorded"; "ask: Would Omega Holdings license or sell US rights?" | blocked: the acquired party is neither the company nor a party to any grant, so it (now Omega) may hold rights to this program |
| F3 | US license D1 + termination D1 + the same acquisition | `RIGHTS_RETURNED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP`; `cited=[41, 42]`: the acquisition row is **not cited**, its quote is not read, and no reason mentions it | blocked; the row cited |

Cause: `_Ledger._acquisitions` (`rights_ledger.py:194-196`) adds any applied acquisition whose acquired party holds no
grant to `owner_acquisitions`, without checking that the party is the company or a licensor. `_decide`
(`rights_position.py:531-532`) then returns `_owner_acquired`. On the returned path `_cleared` (`:529`) returns first.
Only grant events and their chains are cited (`:502-503`), so the acquisition is never in `used`. The gate reads only cited rows
(`rights_gate.py:394`). Both behaviours were the same at revision 8.

### 2g. End to end (ws_i, C3 buyer, as-of 2026-10-29)

Copied from `e2e/memo_i.md` and `ws_i/screening.json`. Seven programs reach a top tier.

| # | Program | Input added (fictional parties) | Output (copied) | Finding |
|---|---|---|---|---|
| 1 | ATG-022 | Z04 availability by Antengene Biologics, US; Z05 China license; analyst geographic "Licensed in China to Chinaco Pharma, Tessaly Pharma Everywhere Else" | "#1 ATG-022: availability stated, unverified; … an analyst assertion geographic rights note 'Licensed in China to Chinaco Pharma, Tessaly Pharma Everywhere Else' (a grant over other places only)" | PN3, tier 0 |
| 2 | QLS31905 | Z01 China license, quote "(test) Chinaco Pharma licenses rights in mainland China and other markets" | "#2 QLS31905: no third-party grant in evidence" | WIDER2 |
| 3 | JS107 | Z07 China license; Z08 U.S. license to Tessaly Pharma, Deal Date 2026-12-01, no Source Date | "#3 JS107: no third-party grant in evidence; … not applied, dated after the as-of date 2026-10-29: a license (2026-12-01) naming Tessaly Pharma"; "ask: Who holds US rights? Recorded deals cover other territories only" | FUT2, Q-FUT2 |
| 4 | BL-M05D1 | Z09 acquisition of Sichuan Baili Pharmaceutical by Omega Holdings, quote "(test) … U.S. rights to the program are held by Tessaly"; Z10 China license | "#4 BL-M05D1: no third-party grant in evidence; rights position: owner acquired per evidence" | PARTY2 |
| 5 | SKB315 | Z06 China license; analyst Partnerships "Licensed in China to Chinaco Pharma, Tessaly Pharma Western Hemisphere" | "#5 SKB315: no third-party grant in evidence; … (a grant over other places only)" | PN3 |
| 6 | Spevatamig (PT886) | Z02 U.S. license to Alpha Bio; Z03 termination, quote "(test) Alpha Bio will return U.S. rights to Phanes Therapeutics on 1 January 2027" | "#6 Spevatamig (PT886): no third-party grant in evidence; rights position: rights returned per evidence" | HEDGE2 |
| 7 | TORL-2-307-ADC | Z11 China license, quote "(test) Chinaco Pharma licenses China rights and also receives an exclusive option" | "#7 TORL-2-307-ADC: no third-party grant in evidence" | WN (new) |
| — | Sonesitatug vedotin | Z13 U.S. license to Alpha Bio; Z14 termination, quote "(test) … U.S. rights are now held by a subsidiary of Tessaly Pharma" | `RIGHTS_RETURNED_PER_EVIDENCE`, top-tier blockers `[]`; `DEPRIORITIZED` only by the buyer's sponsor preference | PARTY2 (A8) |
| — | ASP2138 | Z15 China license; Z16 acquisition of Sideco Bio by Omega Holdings | `OWNER_ACQUIRED_PER_EVIDENCE`, blockers `[]`, "Would Omega Holdings license or sell US rights?"; `DEPRIORITIZED` by sponsor | ACQ-X |
| — | ASP546C | Z17 China license, quote "(test) Astellas Pharma Global Development granted Chinaco Pharma exclusive rights to ASP546C in mainland China" | blocker "…which names ASP546C, which is not a party to the row or the program's company, so it may hold rights the row does not show" | LBL-CODE, usefulness |

RC118 (Z12, availability dated "2026") stays `RIGHTS_UNRESOLVED` (DATE-AV held).

## 3. Over-caution and usefulness

These are usefulness costs, not safety errors. "New" means it reached tier 1 at revision 8 (`a/cmp_rev8.txt`).

| Input | Revision 9 | Note | Cause |
|---|---|---|---|
| China license quotes "Nerida Bio granted Chinaco Pharma exclusive rights to NB-7 in mainland China" (G1), "Nerida Bio licensed China rights to NB-7 to Chinaco Pharma" (G2), "Nerida Bio transferred China rights to NB-7 to Chinaco Pharma" (G11); termination "Following a portfolio review, Alpha Bio returned U.S. rights to NB-7 to Nerida Bio" (C2) | blocked: "names NB-7, which is not a party" | **New.** This is the most common press phrasing for a license or a return. It will hold back many clean real rows | `_TO_PARTY` (`rights_gate.py:271`) skips up to four words after the verb, so "granted … rights to NB-7" captures the program code |
| Endings: "… after a strategic review" (C3), "… after Alpha Bio exits" (C4), "…, which it will continue to develop" (C5), "… based only on portfolio priorities" (C7); acquisitions: "Nerida Bio will continue to operate as a wholly owned subsidiary" (C16), "Nerida Bio remains headquartered in Boston" (U5), "Nerida Bio shareholders sold all shares to Omega Holdings" (U6) | blocked: "says 'after' / 'continue' / 'only' / 'remains' / 'sold'" | **New** | `_HEDGE` matches a word anywhere in the clause |
| Lapse quotes "Alpha Bio did not exercise its option on U.S. rights to NB-7" (B16), "Alpha Bio's option on U.S. rights to NB-7 expired unexercised" (U8) | blocked: "says 'option'" | **New.** Almost every lapse quote names the option | `_HEDGE` contains `option\w*`, applied to lapses |
| Advisers and investors: "Harlow Partners LLC advised Nerida Bio" (C13, C18), "a company backed by Lumen Capital" (C17), "facilitated by Harlow Partners" (G6) | blocked: "names Harlow Partners LLC …" | **New.** Real acquisition releases name advisers | `_CORPORATE` |
| Name variants of a known party: "Nerida Biopharma" (C12), "Chinaco Pharmaceutical Group" (G7), "Chinaco (Shanghai) Pharmaceutical Co., Ltd." (G8, "names Pharmaceutical Co"); another known licensee: "Chinaco Pharma keeps its China license" on a U.S. termination (C14) | blocked | **New** | `same_company`/`name_matches` only; `known` is the row's own parties |
| Title Case headlines and ALL CAPS quotes (U1–U4): "Alpha Bio Returns U.S. Rights to NB-7 to Nerida Bio" | blocked: "names Alpha Bio Returns US Rights" | **New**; the label is also false (LBL-CODE) | `_CAP_SPAN` joins every capitalised word |
| A grant outside the buyer territory announced before the as-of date and effective after it (E8: Japan license to Kappa KK) | blocked | New; a small cost | `announced` covers every grant type and territory |
| "Nerida Bio retains all rights to NB-7 outside of Greater China" (G5) | blocked ("outside") | Old | `_RETAINS` allows "to the program/asset", not a code |
| Clean, held: C1, C6, C8–C11, C15, C19, G3, G4, G9, G10, G12–G14; TORL "retains rights in the rest of the world" | tier 1 | Clean | |

Judgement items unchanged from earlier rounds: Q10/T6 (an offer with no place), N-addr, T1/O8 (D1h, D1i, D3e,
S5), "U.S. rights: TBD" as no grant, speakers such as "Nerida Bio Americas:".

## 4. Output honesty

In favour: the CLDN18.2 memo and workbook call nothing available or open as a rights tier. Every holder and owner
shown in CLDN18.2 and ws_i is cited by row. The memo prose has no position or tier codes (the one all-caps hit is
"SYNTHETIC_FIXTURE"). The workbook Diligence sheet has a status column whose value is "OPEN" (91 cells, question
status, not a rights tier; unchanged since earlier rounds).

| # | Where | Output (copied) | Problem | Cause |
|---|---|---|---|---|
| LBL-CODE | ws_i ASP546C blocker; `a/w9.out` G1; `a/u9.out` U4 | "which names ASP546C, which is not a party to the row or the program's company, so it may hold rights the row does not show"; "which names Alpha Bio Returns US Rights, which is not a party …" | A program code and headline words are reported as a company that may hold rights | `_TO_PARTY`, `_CAP_SPAN` (`rights_gate.py:260, 271`) |
| LBL-NONE | ws_h RC118; `a/d9.out` S2, S3; `prev/d8.out` D3f | "RC118 NO_RIGHTS_EVIDENCE … cited rows: [29]"; "D3f … NO_RIGHTS_EVIDENCE / RIGHTS_UNRESOLVED" beside a cited U.S. license to Tessaly Pharma | AC2 reserves `NO_RIGHTS_EVIDENCE` for no evidence; here a cited row exists | `_decide` falls to `P_NONE` ("no usable grant recorded", `rights_position.py:553`) when the only row is straddling or announced |
| L3e | `e2e/assert_i.log` | "Beside a clear position, the top-tier gate accepts it as a plain form for the buyer territory (US): a grant over other places only; it is still unverified." for "Licensed in China to Chinaco Pharma, Tessaly Pharma Everywhere Else" | Reports PN3 as the gate's verdict | `cli/dealscreen.py:113`; PN3 |
| L1e | ws_i memo line 9 | "for 1 DealScreen's word rules found nothing else in the rights texts, names, rows and row quotes that contradicts the statement or that they cannot read" | The program is ATG-022, whose cited note gives Tessaly Pharma "Everywhere Else" | `memo.py:530`; PN3 |
| Q-FUT2 | ws_i memo #3 JS107 | "ask: Who holds US rights? Recorded deals cover other territories only (licensor per evidence: NingBo Junyan Hongshi Biosciences)." beside "evidence (rights row 25): 2026-12-01 license, Tessaly Pharma …, United States" | The question says what the cited row contradicts | `rights_position.py:546` checks only `announced`; FUT2 |
| ACQ-X wording | `a/d9.out` F1 | `holder='Nerida Bio' owner='Nerida Bio'`, "Omega Holdings acquired Sideco Bio (the company or its rights to this program)", "ask: Would Omega Holdings license or sell US rights?" | Holder, reason and question name three different owners | `_owner_acquired` (`rights_position.py:606-622`) |

## 5. Acceptance criteria

| AC | Verdict | Evidence |
|---|---|---|
| AC1 | PASS | ws_i: "33 events, 0 rejected rows (license public/research_only)"; provenance (row, URL, quote, date) in every evidence line |
| AC2 | PARTIAL | CLDN18.2: no OPEN tier, nothing called available. Held out: tier 0 beside "Tessaly Pharma Everywhere Else" (ws_i ATG-022, PN-T0) and beside a known future U.S. license with no source date (E1b). `NO_RIGHTS_EVIDENCE` shown beside cited rows (LBL-NONE). L1e overclaims |
| AC3 | PARTIAL | Rights-file territories parse. Not met: third-party grants and wider reach in quotes (PARTY2, WIDER2, WN) and texts (PN3) read as "other territories only" |
| AC4 | PARTIAL | Returns clear; REREVIEW7's COVER inputs block. Not met: endings not yet in effect or partial pass (HEDGE2); a third party in a return's quote passes (PARTY2); an acquisition beside a return is dropped (ACQ-X F3); LM-302 still not RETURNED (data) |
| AC5 | PASS on my inputs | Exercise, lapse and "no outcome" logic hold (E10 OPTION_HELD; R5 lapse blocks). Quote issues on lapses are counted under AC4/AC14 (B15) and usefulness (B16) |
| AC6 | PARTIAL | Not met: a known third-party U.S. license with no source date beside a statement is tier 0, not CONFLICTING (E1b); PN3 texts pass instead of conflicting |
| AC7 | PARTIAL | DATE-AV and day-dated FUT fixed. Not met: FUT2; T1/O8 kept as judgement |
| AC8 | PASS | `compare.py` 0 of 62 on `after_v9` and on my HEAD re-screen; transaction views identical to revision 8. Cross-version and cycle-4: result files only, not re-run |
| AC9 | PARTIAL | Preferences work. Not met: the party-name rule is a closed list (PN3); many clean real phrasings are held back (§3) |
| AC10 | PARTIAL | Every text and quote is cited. Not met: false "(a grant over other places only)" labels (PN3); false "names NB-7 … may hold rights" labels (LBL-CODE); Q-FUT2 |
| AC11 | PARTIAL | Not met: PARTY2, HEDGE2, WIDER2, WN, PN3, FUT2 and ACQ-X ask no question naming Tessaly, Sideco or the effective date |
| AC12 | PASS | 0 of the 230 CLDN18.2 names in `/tmp/claude-1000/rr5/ac12_names.txt` among the 182 lines revision 9 added to `src/`; the only hit is the generic "American" (in `_WIDER`) |
| AC13 | PARTIAL | Unchanged: IBI343, SHR-A1904 not unobstructed; RC148, FL-301, XNW27011 encumbered; LM-302 CONFLICTING, not returned |
| AC14 | FAIL | 7 new High errors on held-out inputs; none in the CLDN18.2 output |

## 6. CLDN18.2 measured against the reference and B

| Item | Revision 8 | Revision 9 |
|---|---|---|
| `after_transaction.csv` (62 programs) | — | byte-identical; my HEAD re-screen identical (JSON equal) |
| Memo | — | identical except cycle U1's gate lines |
| Scientific fields vs frozen baseline | 0 of 62 | 0 of 62 (`compare.py`) |
| Top-tier programs | 0 | 0 |

Error classes against `reference_calls.csv`, re-read row by row from `after_v9/after_transaction.csv` for the
programs with rights evidence or a reference deal: false unobstructed **0**; false encumbrance 0 definite, 2 likely
outdated (EO-3021, SYSA1801: reference "RETURNED_TO_ORIGINATOR_UNCLEAR", tool licensed to Elevation Oncology,
deprioritised); wrong holder 1, labelled (LM-302 "Turning Point Therapeutics (recorded; conflicting)"); wrong
territory 0; missed return 2 (SKB315 `NO_RIGHTS_EVIDENCE`; LM-302 conflicting). Programs the reference gives to
large pharma without a rights row (Sonesitatug vedotin, ASP2138, ASP546C, AZD5863, AMG 910) read
`NO_RIGHTS_EVIDENCE`, deprioritised by sponsor.

Usefulness against general Claude (B): the inputs and outputs are identical to revision 8, so REREVIEW7's score
stands: DealScreen **10 right / 4 partial / 1 missed**; B **14 / 1 / 0**. I re-read the rows and found the same
classes; I did not re-score independently. No advantage is shown. Revision 9's new usefulness costs (§3) do not show
in CLDN18.2 because only one of its 17 real quotes sits on a clear position path, and none says "rights to <code>".

## 7. Remaining issues, ranked

1. **(Safety, High) PARTY2.** The party rule finds a third party only by a corporate word or a listed active verb.
   Passive voice, other verbs, possessives and colons pass, and "a subsidiary of X" is deleted anywhere. ws_i #4;
   Sonesitatug.
2. **(Safety, High) HEDGE2.** Endings that are not yet in effect, partial or disputed pass in unlisted words. ws_i #6.
   Live vendor data will say "will return … effective <date>".
3. **(Safety, High) FUT2.** A future-dated grant with no source date (the usual vendor case) or a coarse one is
   dropped; tier 0 beside a statement. ws_i #3.
4. **(Safety, High) PN3 and WIDER2.** Closed lists of name words and wider words. ws_i #1 (tier 0), #2, #5.
5. **(Safety, High, new) WN.** The narrowed `_WIDER` no longer sees the licensee's own unscoped option or
   "international … rights". ws_i #7.
6. **(Safety, High, older) ACQ-X.** An acquisition of a party in no grant gives OWNER_ACQUIRED tier 1, and beside a
   return it is not cited at all.
7. **(Usefulness, new)** "rights to <code>" read as a party; hedge words in ordinary sentences; "option" on every
   lapse; advisers; name variants; headlines. On a real vendor export these will hold back most clean rows.
8. **(Low)** LBL-CODE, LBL-NONE, L3e, L1e, Q-FUT2, ACQ-X wording.
9. **(Judgement)** "&" joining two China licensees; W13; B18/B19 pending acquisitions; Q10, N-addr, T1/O8, "TBD".
10. **(Recall)** The rights file still caps recall (LM-302's return, SKB315's return).

## 8. The single highest-value next fix

Stop extending word lists and invert the quote rule for clear positions. On a clear path, a cited quote should pass
only if **every clause is one of a small set of positive forms** that the gate already knows how to read: the row's
own grant restated (its parties, its type, its territory, nothing else), a plain ending restated (the row's licensee
returns or ends rights to the licensor, with no date later than the row's), the company keeping rights, or a
clause with no party, place, right or date words at all. Anything else blocks with the clause quoted and a question.
That is the inversion revision 6 applied to landscape texts, applied now to quotes. It closes PARTY2, HEDGE2, WIDER2
and WN together because none of them is one of the positive forms, and it removes the "rights to NB-7" cost if the
row's own program code is accepted as part of a restated grant.

Two small fixes follow. Treat a grant dated after the as-of date as known when it has no source date or a coarse
one, and block (FUT2). Require an acquisition's acquired party to be the company or a grant party, else block and
cite the row (ACQ-X).
