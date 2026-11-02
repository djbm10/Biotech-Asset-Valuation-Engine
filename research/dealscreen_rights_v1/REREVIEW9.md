# Adversarial re-review 9: cycle R1 revision 10, rights evidence (CLDN18.2)

**AI-SIMULATED INTERNAL REVIEW.** I am an AI (Claude) playing a skeptical pharma BD analyst and auditor. I am not a
human reviewer. I approve nothing, and nothing here is validation. I did not trust REREVIEW8_RESPONSE.md. I checked
each claim by running code or reading outputs. I report only what I ran or read.

Scope and method:
- Revision 10 is commit d905ff0. HEAD is b0388eb; it changes only `diagnostics.py` and `indication_relations.py`
  (cycle U1) under `src/`. I recorded the SHA-256 of all 36 files in `src/bve/dealscreen/` at the start
  (`/tmp/claude-1000/rr10/sha_start.txt`) and at the end (`sha_end.txt`). No file changed. I edited nothing except
  this file. No commit, stash or git change. ruff ran with `--no-cache`; mypy's cache went to `/tmp/claude-1000/rr10/`.
- All scripts and outputs are in `/tmp/claude-1000/rr10/`. Per-program cases go through
  `screening.program_transaction` with the previous reviewer's harness `h5.py` (copied). Defaults: company "Nerida
  Bio", program code NB-7, buyer {US}, as-of 2025-06-01, max age 730 days, `encumbered_rights: deprioritize`. "China
  license" = one row Nerida Bio → Chinaco Pharma, exclusive, mainland China, 2025-01-01. "US license D1" = Nerida Bio
  → Alpha Bio, United States, 2024-03-01, ended by a termination linked to D1, United States, 2025-01-15, whose quote
  varies. New scripts: `a/p10.py` (placement, wide words, endings, acquisitions), `a/u10.py` (realistic press
  wording), `a/d10.py` + `a/d10b.py` (dates, labels, ACQ-X, party names), `a/av10.py`, `a/rt10.py` (uncited rows),
  `a/real2.py` (each real CLDN18.2 quote read directly by `quote_problem`).
- Revision 9 comparison: `git archive b3e3fe9 src/bve` into `rr10/rev9/`; the same scripts with that tree first on
  `PYTHONPATH` give `a/*_rev9.out`. "Introduced by revision 10" below means tier 0/1 at revision 10 and blocked at
  revision 9.
- End to end: `e2e/ws_i`, `e2e/ws_h` (previous reviewer's workspaces, re-imported and re-screened at HEAD) and a new
  `e2e/ws_j`: a copy of `~/.cache/rights_v1/after10b_ws` (C3 buyer, as-of 2026-10-29) with rights file
  `e2e/rights_j.csv` (the 17 transcribed rows plus fictional rows Z01–Z14). Counterparties are fictional (Tessaly
  Pharma, Chinaco Pharma, Alpha Bio, Omega Holdings, Sideco Bio). Quotes start "(test)"; URLs are `example.test`.
  Nothing here is a fact about a real program.
- Checks at HEAD: `tests/dealscreen` **1,327 passed** (91 s). At d905ff0 (archived tree) 1,300 tests are collected.
  `test_rights_rereview8.py`: 122 collected. ruff: "All checks passed!". mypy `src/bve/dealscreen` + CLI: "Success:
  no issues found in 37 source files". `compare.py`: "AC8 scientific fields changed: 0 of 62".

## Summary

- **Every input REREVIEW8 listed now blocks**, except its own clean controls and judgement items. My re-runs of
  q9, w9, pn9, d9, u9 and pf8b are byte-identical to the implementer's; pf8 equals the implementer's `final2` run.
  The ws_i placements are all `RIGHTS_UNRESOLVED`.
- **The reader fails closed only for capitalised names.** A lower-case word that is in no class is read as harmless.
  So the response's key sentence, "a word missing from a class … cannot open a path into the top tiers", is false.
  59 of 75 attack inputs in `a/p10.py` reach tier 0 or 1.
- **The worst gap is in the row-type rule, not the name rule.** A termination, return or acquisition may use
  "grant" words, because the kinds that "restate" those rows include `grant` (`rights_signals.py:55-58`). So a
  quote that says the returned rights were re-licensed to "another company" or "a third party" passes.
- **Revision 10 opened new paths.** Placement treats as harmless: any name after "said", before "acts as", "serves
  as", "is acting as", "reported" or "has confirmed"; any acronym the quote defines; any word with a digit or on the
  acronym list; any name built only from words of known names ("Chinaco Bio" beside "Chinaco Pharma"); and "New Co".
  `_mask` also swallows "U.S.", "USA", "America" or "International" after a known name, so "Chinaco Pharma U.S.
  will commercialize NB-7" on a China row is tier 1.
- **An older path, first reported here.** Beside an availability statement, a return or a lapse, a grant over other
  territories is not cited and its quote is never read. A China license whose quote says "Tessaly Pharma holds U.S.
  rights" gives tier 0 next to an availability statement. ws_j ATG-022 is tier 0 this way.
- **Usefulness got worse on real press wording.** Datelines, capitalised executive titles, cities, disease names,
  target names ("Claudin 18.2"), designations, conferences, brand names and "shares" in acquisition quotes all
  block. 21 clean cases that reached tier 1 at revision 9 are now held back. Two of the real CLDN18.2 quotes (rows 3
  and 5) would fail the reader on "Claudin" and on the dateline "OSAKA, Japan and CAMBRIDGE, Massachusetts".
- **CLDN18.2 is unchanged.** `after_v10/after_transaction.csv` is byte-identical to `after_v9`; my HEAD re-screen
  gives the same JSON and memo. 0 top-tier programs. 0 of 62 scientific fields changed.

Definite new errors (not reported in REREVIEW8.md). None occurs in the CLDN18.2 output.

| Severity | Introduced by revision 10 | Claimed fixed, fails on a close variant | Older, first reported here | Total |
|---|---|---|---|---|
| High: tier 0 or 1 while a third party may hold buyer-territory rights, or on contrary, conditioned or future evidence | 2: PLACE, MASK | 5: LOWER, WIDER3, HEDGE3, FUT3, PN4 | 1: UNCITED | **8** |
| Medium: false encumbrance, false conflict, wrong holder or a missed encumbrance | 0 | 0 | 1: OWNER-KEY | **1** |
| Low: false label, wording or citation; no tier change | 0 | 3: LBL-NONE2, Q-FUT3, L1f | 1: L3f (assert note, follows PN4) | **4** |

Usefulness defects (definite, no safety effect): SHARE ("share", "shares" read as co-development on acquisitions;
introduced by revision 10) and the press-wording costs in §3.

## 1. REREVIEW8_RESPONSE.md, claim by claim

| § | Claim | Verdict | Evidence (run or read) |
|---|---|---|---|
| 1 | The quote reader fails closed; deny-lists removed from `rights_gate` | **Held as code. Refuted as a safety property** | The listed names are gone from `rights_gate.py`. But only capitalised runs fail closed; lower-case words outside the classes are harmless (§2a, §2c, §2d) |
| 1.1 | Every capitalised name is placed | **Refuted** | Names after "said", before "acts as" / "serves as" / "is acting as" / "reported" / "has confirmed", defined acronyms, words with a digit, `_NOT_HOLDERS` words, known-name words and "New Co" are all placed (§2b, PLACE) |
| 1.1 | "Tessaly's U.S." is not a place | **Held** | A10 blocks. But "Chinaco Pharma U.S." after a known party is masked whole (MASK) |
| 1.1 | "a subsidiary of X" only directly after a known party | **Held** | A8 blocks. The same pattern also takes "parent of" (P21, judgement) |
| 1.2 | Every rights word restates the row | **Held as written. Refuted as a safety rule** | Endings and acquisitions may use every `grant` word, so a re-grant restates nothing yet passes (LOWER) |
| 1.3–1.4 | No time or hedge word on an ending | **Held for listed words. Refuted on close variants** | "to return", "has elected to terminate", "is returning", "after a 180-day wind-down period", "as of 1 December 2025", "by year-end" pass (HEDGE3). No date in a quote is compared with the as-of date |
| 1.5 | No wide word or extra place on a row that does not cover the buyer territory | **Held for listed words. Refuted on close variants** | "any other territory", "every other market", "further rights", "additional rights", "all 50 states", "across the globe", "a matching right" pass (WIDER3). Hedge words such as "other" are ignored on grants |
| 1.6 | On an ending, no year later than the row's | **Held** | B1-type inputs block. A later date in the same year passes (H1) |
| 1 | "A word missing from a class … cannot open a path into the top tiers" | **Refuted** | 59 of 75 `a/p10.py` inputs reach a top tier; most turn on a lower-case word in no class |
| 2 | PARTY2 closed | **Held for the listed inputs. Refuted on close variants** | A1–A20, B20, W1–W4, W27 block (`prev/q9.out`). P1–P18, Q1–Q4, PC1–PC10 pass |
| 2 | HEDGE2 closed | **Held for B1–B15. Refuted on close variants** | HEDGE3 |
| 2 | WIDER2, WN closed | **Held for W5–W26. Refuted on close variants** | WIDER3 |
| 2 | PN3 closed | **Held for the listed words. Refuted on close variants** | "Tessaly Intercontinental", "Tessaly Transpacific", "Tessaly Exusa" accepted (PN4, low realism). pf8 accepted forms 16, matching the implementer's `final2` |
| 2 | FUT2 closed (E1, E1b, E2, E3, E7); E8 no longer blocks | **Held for grant rows. Refuted for option exercises** | E1, E4–E6, E11 block; E8 passes. A future-dated U.S. option exercise with no source date is dropped, tier 1 (FUT3) |
| 2 | ACQ-X closed | **Held** | F1, F1b, F3 block and are cited (`prev/d9.out`); ws_i ASP2138 blocks. A parent or a "US" arm still passes as the company (OWNER-KEY) |
| 2 | LBL-NONE: `RIGHTS_ROWS_NOT_APPLIED` | **Held for straddling and announced rows. Refuted for other unapplied rows** | ws_h RC118 now reads "rights rows recorded, none applied". A future Japan license, a future availability statement or a lone lapse still read `NO_RIGHTS_EVIDENCE` beside the cited row (LBL-NONE2) |
| 2 | LBL-CODE: a code has a digit, so it is neutral | **Held** | G1, G2, G11 pass. The same digit rule places "3Tessaly" and "T7 Pharma" (PLACE) |
| 2 | Q-FUT2 question | **Held for grants** | "…, from when, and was it agreed by 2025-06-01?". Not for an exercise (Q-FUT3) |
| 2 | L3e, L1e follow from PN3 | **L3e held. L1e refuted on new input** | "Everywhere Else" now gets the refusal note. ws_j memo line 9 repeats the L1 sentence for ATG-022 (L1f) |
| 2 | ACQ-X wording | **Held for ACQ-X** | Other owner wording is wrong (OWNER-KEY) |
| 2 | Judgement items kept | **Unchanged** | B18, "Chinaco & Tessaly", U7, E11, S5, Q10/T6, N-addr, "TBD" behave as stated |
| 3 | Tests 1,300; 122 in rereview8 tests; ruff, mypy clean | **Held** | 1,300 collected at d905ff0; 1,327 pass at HEAD (U1 adds tests); 122; ruff, mypy clean |
| 3 | CLDN18.2: 0 of 62; CSV and memo identical to revision 9; 0 top tier | **Held** | `cmp` of `after_v10` vs `after_v9`; my HEAD re-screen JSON equals `after10b_ws`; memo identical |
| 3 | Cross-version 0 of 312 | **Held at HEAD** | My HEAD run of `cross_version.py` (`rr10/xv/head`) equals the stored revision 9 (`xv9f`) and revision 10 (`xv10`) results on 312 programs. My own revision 9 re-run failed (the archived tree has no research data) |
| 3 | Cycle-4 equivalence 4 of 4 | **Held** | My HEAD re-run: byte-identical, fast path, 4 of 4 (§6) |
| 3 | ws_i: seven placements unresolved; Sonesitatug names Tessaly; ASP2138 blocks; ASP546C has no false blocker | **Held** | `e2e/tiers_i.txt` equals the implementer's `final`/`final2` |
| 3 | ws_h: only RC118 changed; TORL tier 1 | **Held** | `e2e/tiers_h.txt` identical to the implementer's |
| 3 | Probe counts q9 13, w9 8, pn9 5, d9 7, u9 4; pf8 16 | **Held** (byte-identical) | `prev/*.out`, `prev8/pf8.out` |
| 3 | Real CLDN18.2 quotes: 1 of 17 blocks | **Held as measured. Misleading as a usefulness check** | Only row 10 reaches a clear position; the other 16 are on encumbered, shared or already-blocked paths, so the reader is never asked. Read directly, 5 of 17 fail: rows 3 and 4 ("names Claudin"), row 5 ("names OSAKA, CAMBRIDGE"), row 9, row 10 (`a/real2.out`) |
| 4 | Costs: lower-case third parties; unplaced investors and universities block | **Held, and much wider** | The lower-case miss covers descriptions ("another company", "a third party", "a new licensee"), not just lower-case names (LOWER). The over-caution covers most press-release furniture (§3) |

## 2. Paths into the top tiers

### 2a. Endings and acquisitions that restate a new grant (LOWER; claimed fixed, close variant of PARTY2)

US license D1 + termination; each gives
`RIGHTS_RETURNED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE holder='Nerida Bio'`, no blocker
(`a/p10.out`). Expected: blocked, with a question about the new holder.

| Id | Termination quote |
|---|---|
| P1 | "Alpha Bio returns U.S. rights to Nerida Bio; U.S. rights then went to a third party" |
| P2 | "Alpha Bio returns U.S. rights to Nerida Bio; the U.S. rights-holder is now another company" |
| P3 | "Alpha Bio returns U.S. rights to Nerida Bio, which has since licensed them to another company" |
| P4 | "Alpha Bio returns U.S. rights to Nerida Bio; Nerida Bio has since granted an exclusive U.S. license to a new licensee" |
| P16 / P18 | "…, which licensed them to a newco" / "…, which licensed them to tessaly" |

China license + acquisition of Nerida Bio by Omega Holdings: `OWNER_ACQUIRED_PER_EVIDENCE /
NO_THIRD_PARTY_GRANT_IN_EVIDENCE holder='Omega Holdings'`, no blocker. Q1 "Omega Holdings acquires Nerida Bio, whose
U.S. licensee is unaffected"; Q2 "…; NB-7 is licensed in the U.S. to a third party"; Q4 "…, which granted another
company an exclusive U.S. license to NB-7".

China license: `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE`. PC8 "Chinaco Pharma
licenses NB-7 for mainland China; another company has all other rights"; PC9 "…; NB-7 is also licensed to a third
party"; PC10 "…; a global pharmaceutical company has the other rights" ("global pharmaceutical" is stripped as
ordinary).

Cause:
- `RESTATES` (`rights_signals.py:55-58`) lets TERMINATION, RIGHTS_RETURNED and ACQUISITION use the `grant` kind, which
  holds "license", "licensed", "granted", "exclusive", "rights", "receive". A new grant in the same clause restates
  the row by this test.
- `_Scan._read` (`rights_quote.py:162-177`) sends every lower-case token to `_word`, which only records class words.
  "another", "third", "party", "company", "went", "newco" and "rights-holder" are in no class, so the clause has
  nothing to block on.
- `HEDGE` blocks only on endings (`rights_quote.py:261`), so "other rights" on a grant is ignored.
- At revision 9 the same inputs also reached a top tier, except P3's close relative A3, which revision 10 now blocks
  on "partner".

### 2b. Names the placement rule treats as harmless (PLACE; introduced by revision 10, except P11/PC6)

Same termination. Each: `RIGHTS_RETURNED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE`, no blocker. At revision
9 each was `RIGHTS_UNRESOLVED` (`a/p10_rev9.out`), except P11 and PC6.

| Id | Quote after "Alpha Bio returns U.S. rights to Nerida Bio" | Placed by |
|---|---|---|
| P5 / P5b | "; Tessaly Pharma acts as the new U.S. licensee" / "; Tessaly Pharma is acting as U.S. licensee" | `_ADVISER` (`rights_quote.py:90-92`) |
| P6 | "; Tessaly Pharma serves as exclusive U.S. licensee of NB-7" | `_ADVISER` |
| P7 | "; Tessaly Pharma has confirmed its U.S. license to NB-7" | `_SOURCE` (`:99-100`) |
| P8 | "; Tessaly Pharma reported an exclusive U.S. license to NB-7" | `_SOURCE` |
| P9 / P9b | ", said Tessaly Pharma, the new U.S. licensee" / "; the new U.S. licensee, analysts said, Tessaly Pharma" | `_SAID` (`:89`) |
| P15 | " and licensed them to a newly formed company (Tessco); Tessco now has U.S. rights" | `_DEFINED` (`:103`): any acronym after a lower-case word |
| P17 / P23 | ", which licensed them to New Co" / "; a New Licensee now has the U.S. rights" | `_FUNCTION` (`:63-72`) has "new", "co", "licensee" |
| P11 / P12 | "; the new U.S. licensee is 3Tessaly" / "… is T7 Bio" | `_neutral` (`:159`): any digit; "Bio" is a known word |
| P13 / P14 | "… is Alpha Nerida" / "… is Star Bio" | `known_tokens` subset (`:222-223`); "star" in `_NOT_HOLDERS` (`:80`) |

China license (`NOT_ENCUMBERED… / NO_THIRD_PARTY_GRANT_IN_EVIDENCE`): PC5 "…; NB-7 is also licensed to Chinaco Bio"
(every word is a known word); PC6 "… to 3Tessaly"; PC7 "… to T7 Pharma".

Cause: `_Scan._placed` (`rights_quote.py:209-227`) places a run by its shape or by what stands next to it, not by
its role. `_SAID`, `_TITLE`, `_ADVISER` and `_SOURCE` apply to any run in any clause, including the subject of a
rights sentence. `_DEFINED` accepts an acronym the quote itself coins for a third party. A run is placed when its
words are a subset of the known names' words, so a different company that shares words with a known party is
placed.

### 2c. The known party's company words swallow the buyer territory (MASK; introduced by revision 10)

China license; quote as given. Each: `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE`,
no blocker. Revision 9: `RIGHTS_UNRESOLVED` for PC1–PC3.

| Id | Quote |
|---|---|
| PC1 | "Chinaco Pharma licenses NB-7 for mainland China, and Chinaco Pharma U.S. will commercialize NB-7" |
| PC2 | "Chinaco Pharma licenses NB-7 for mainland China; Chinaco Pharma USA will develop and commercialize NB-7" |
| PC3 | "…; Chinaco Pharma America will commercialize NB-7" |
| PC4 | "…; Chinaco Pharma International will commercialize NB-7" (also tier 1 at revision 9) |

Expected: blocked, "names US, in the buyer territory, which the row's own territory does not".

Cause: `_mask` (`rights_quote.py:130-136`) replaces a known name and any following `_COMPANY_WORDS`, which include all
of `GENERIC_NAME_WORDS` (`rights_territory.py:146-150`: "us", "usa", "america", "americas", "global",
"international", "europe", "japan", "china"). `_prepare` turns "U.S." and "USA" into "US" first. The place is then
gone before the place check at `rights_quote.py:265`. The same masking hides "Chinaco Pharma Europe" for an EU buyer.

### 2d. Wider reach in lower-case words (WIDER3; claimed fixed, close variant)

China license; quote as given (`a/p10.out`). Each: `NOT_ENCUMBERED… / NO_THIRD_PARTY_GRANT_IN_EVIDENCE`, no blocker.
Expected: blocked.

| Id | Quote |
|---|---|
| W1 / W2 | "Chinaco Pharma licenses NB-7 in mainland China and any other territory" / "… and every other market" |
| W3 / W4 | "Chinaco Pharma licenses mainland China rights to NB-7 and will receive further rights upon approval" / "… and will obtain additional rights" |
| W5 / W12 | "… in mainland China and all 50 states" / "… and across the globe" |
| W6 | "Chinaco Pharma licenses NB-7 in the Licensed Territory, which includes mainland China" |
| W17 | "Chinaco Pharma licenses mainland China rights and receives a matching right" |
| PC12 | "Chinaco Pharma licenses NB-7 for mainland China and will lead worldwide pivotal trials" ("worldwide pivotal trials" is stripped) |

Judgement: W9 "Nerida Bio granted domestic rights too"; W10 "all fields and the territory".

Cause: `WIDE` (`rights_signals.py:63-66`) lists only plurals ("territories", "markets"); singular "territory" is a
`grant` word and "market" a `develop` word, both allowed on a license. "further", "additional", "any", "every",
"globe", "states" and "matching" are in no class. `GRANT_TIME` (`:84-85`) lets "will" and "upon" through on grants.
`ORDINARY_WIDE` (`:67-70`) strips "worldwide pivotal trials" and "global pharmaceutical".

### 2e. Endings not yet in effect (HEDGE3; claimed fixed, close variant)

US license D1 + termination dated 2025-01-15, as-of 2025-06-01. Each: `RIGHTS_RETURNED_PER_EVIDENCE /
NO_THIRD_PARTY_GRANT_IN_EVIDENCE holder='Nerida Bio'`, no blocker. Expected: blocked (later or undecided).

| Id | Termination quote |
|---|---|
| H1 | "Alpha Bio returns U.S. rights to Nerida Bio as of 1 December 2025" |
| H2 | "Alpha Bio returns U.S. rights to Nerida Bio after a 180-day wind-down period" (blocked at revision 9) |
| H3 | "Alpha Bio to return U.S. rights to Nerida Bio" |
| H4 / H5 | "Alpha Bio has elected to terminate the U.S. license" / "Alpha Bio decided to terminate its U.S. license to NB-7" |
| H6 | "Alpha Bio is returning U.S. rights to Nerida Bio" |
| H9–H12 | "… starting in December"; "… by year-end"; "… in due course"; "Alpha Bio announced its decision to return U.S. rights to Nerida Bio" |

Judgement (partial scope, no hedge word): H7 "… U.S. rights to NB-7 in solid tumors …", H8 "… U.S. commercial
rights …".

Cause: `TIME` (`rights_signals.py:76-81`) lacks "to" + verb, "elected", "decided", "decision", "returning",
"starting", "wind-down", "due", "year-end". `_clause_problem` (`rights_quote.py:268-271`) compares only years with the
row's year; a date later in the same year, or after the as-of date, is never compared.

### 2f. A future-dated option exercise (FUT3; claimed fixed, close variant of FUT2)

| Id | Input | Output (copied) | Expected |
|---|---|---|---|
| E2 | China license + OPTION_EXERCISED, Tessaly Pharma, United States, 2025-07-01, no source date, no option row | `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE`; "reason: not applied, dated after the as-of date 2025-06-01: an option exercise (2025-07-01) naming Tessaly Pharma"; "ask: Who holds US rights? Recorded deals cover other territories only (licensor per evidence: Nerida Bio)." | blocked, as E1 is |
| E3 | Same, linked to a China-only option to Tessaly (2024-06-01) | tier 1 | blocked |
| ws_j JS107 | Z07 China license; Z08 "Option exercised", Tessaly Pharma, United States, Deal Date 2026-12-01, no Source Date | memo "#3 JS107: no third-party grant in evidence; … not applied, dated after the as-of date 2026-10-29: an option exercise (2026-12-01) naming Tessaly Pharma" | blocked |

Cause: `announced` (`rights_ledger.py:126-128`) takes only `_GRANT_TYPES` (`:29`: license, option, co-development,
co-promotion option). An exercise dated after the as-of date is removed from `events` (`:129-130`), so the
"exercise with no recorded option" rule (`rights_position.py:495-496`) never sees it.

### 2g. Rows that are never cited, so their quotes are never read (UNCITED; older, first reported here)

| Id | Input | Output (copied) | Expected |
|---|---|---|---|
| AV1 | availability (Nerida Bio, US, 2025-03-01) + China license, quote "Chinaco Pharma licenses China rights; Tessaly Pharma holds U.S. rights" | `AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED / AVAILABILITY_STATED_UNVERIFIED <<< TOP`; `cited=[1]` (the statement only) | blocked; the China row cited |
| AV3 / AV4 | Same, quote "Chinaco Pharma licenses worldwide rights to NB-7" / "… and holds an option on U.S. rights" | tier 0, statement only cited | blocked |
| AV6 (control) | The worldwide quote with no statement | `RIGHTS_UNRESOLVED`, "says 'worldwide'" | — |
| RT1 | US license D1 + plain termination + China license, quote "…worldwide rights…; Tessaly Pharma holds U.S. rights" | `RIGHTS_RETURNED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE`; `cited=[1, 2]` | blocked |
| RT2 | Option D2 + lapse + China license naming Tessaly | `NOT_ENCUMBERED… / NO_THIRD_PARTY_GRANT_IN_EVIDENCE`; China row not cited | blocked |
| ws_j ATG-022 | Z04 availability; Z05 China license, quote "(test) Chinaco Pharma licenses mainland China rights, and Chinaco Pharma U.S. will commercialize the program" | memo "#1 ATG-022: availability stated, unverified"; evidence: row 21 only; `top_tier_blockers: []` | blocked |

Cause: `_decide` (`rights_position.py:503-505`) adds to `used` only blocking, disputed, returned and merged grants and
the statements. A grant over other territories is cited only on the not-encumbered path (`:536`). The gate reads
quotes only of cited rows (`rights_gate.py:271`). All of these were the same at revision 9.

### 2h. Party names (PN4; claimed fixed, close variant, low realism)

China license + the text as a landscape geographic cell (`a/d10.out`):
"Licensed in China to Chinaco, Tessaly Intercontinental", "… Tessaly Transpacific", "… Tessaly Exusa" →
`'a grant over other places only'`, tier `NO_THIRD_PARTY_GRANT_IN_EVIDENCE`. The CLI `assert` note for the first
says "the top-tier gate accepts it as a plain form … a grant over other places only" (`e2e/assert_k.log`, L3f).
Cause: `_name_words_ok` (`rights_allow.py:129-139`) refuses only class words; a name with no company word has no
legal-form check. Judgement: "Licensed in China to Chinaco Pharma, Tessaly Pharma" is accepted (a comma joins two
China licensees, as "&" did).

### 2i. End to end (ws_j, C3 buyer, as-of 2026-10-29)

Copied from `e2e/memo_j.md` and `ws_j/screening.json`. Seven programs reach a top tier; at revision 10's own
workspace (ws_i) none did.

| # | Program | Rows added (fictional parties) | Output (copied) | Finding |
|---|---|---|---|---|
| 1 | ATG-022 | Z04 availability; Z05 China license, quote "… Chinaco Pharma U.S. will commercialize the program" | "#1 ATG-022: availability stated, unverified" | UNCITED + MASK, tier 0 |
| 2 | QLS31905 | Z01 China license, quote "(test) Chinaco Pharma licenses rights in mainland China; another company has all other rights" | "#2 QLS31905: no third-party grant in evidence" | LOWER |
| 3 | JS107 | Z07 China license; Z08 U.S. option exercised by Tessaly Pharma, 2026-12-01, no source date | "#3 JS107: no third-party grant in evidence; … not applied, dated after the as-of date 2026-10-29: an option exercise (2026-12-01) naming Tessaly Pharma" | FUT3, Q-FUT3 |
| 4 | BL-M05D1 | Z09 acquisition, quote "(test) Omega Holdings acquires Sichuan Baili Pharmaceutical, whose U.S. licensee is unaffected"; Z10 China license | "#4 BL-M05D1: no third-party grant in evidence; rights position: owner acquired per evidence" | LOWER |
| 5 | SKB315 | Z06 China license, quote "(test) Chinaco Pharma licenses the program in mainland China and any other territory" | "#5 SKB315: no third-party grant in evidence" | WIDER3 |
| 6 | Spevatamig (PT886) | Z02 U.S. license to Alpha Bio; Z03 termination, quote "(test) Alpha Bio returns U.S. rights to Phanes Therapeutics, which has since licensed them to another company" | "#6 Spevatamig (PT886): no third-party grant in evidence; rights position: rights returned per evidence" | LOWER |
| 7 | TORL-2-307-ADC | Z11 China license, quote "(test) … and will receive further rights upon approval" | "#7 TORL-2-307-ADC: no third-party grant in evidence" | WIDER3 |
| — | Sonesitatug vedotin | Z13, Z14 termination quote "(test) Alpha Bio to return U.S. rights to AstraZeneca" | `RIGHTS_RETURNED_PER_EVIDENCE`, blockers `[]`; `DEPRIORITIZED` only by sponsor | HEDGE3 |

## 3. Over-caution and usefulness

These are usefulness costs, not safety errors. Each case should reach tier 1 on its own facts (China license, plain
termination of D1, or a completed acquisition of Nerida Bio). "New" = tier 1 at revision 9 (`a/u10_rev9.out`).
Revision 10 holds back 29 of my 43 clean cases; 21 of them are new.

| Input | Revision 10 | New? | Cause |
|---|---|---|---|
| Datelines: "SAN DIEGO, March 3, 2025 /PRNewswire/ -- Nerida Bio, Inc. (Nasdaq: NRDA) today announced …" (UC1); "BOSTON and SHANGHAI, …" (UC2); "BOSTON, January 15, 2025 -- …" (UT4). Real row 5: "OSAKA, Japan and CAMBRIDGE, Massachusetts, October 21, 2025 – Takeda …" | "names SAN DIEGO, PRNewswire" / "names BOSTON, SHANGHAI" / "names OSAKA, CAMBRIDGE" | New | cities are not places to `regions_named`; unplaced capitals block |
| Executive quotes: '"This license brings NB-7 to patients in China," said Jane Doe, Chief Executive Officer of Nerida Bio' (UC3, UT2, UA3) | "names Chief Executive Officer" | New | `_TITLE` only places the run before the title |
| "About Nerida Bio: … based in Boston …" (UC5); "Shanghai-based Chinaco Pharma" (UC10); "headquartered in Shanghai" (UC23); "a Hong Kong-listed company" (UC26) | "names About, Boston" / "Shanghai-based" / "Shanghai" / "Hong Kong-listed" | New (UC10 old) | same |
| Forward-looking statement: "… Private Securities Litigation Reform Act of 1995" (UC6) | "names Private Securities, Reform Act" | New | same |
| Disease and target names: "Hodgkin lymphoma" (UC12), "Crohn's disease" (UC13). Real rows 3–4: "targeting Claudin 18.2" | "names Hodgkin" / "names Crohn" / "names Claudin" | New | same |
| "Breakthrough Therapy Designation" (UC14), "ASCO" (UC15), a brand name "Neridix (NB-7)" (UC20), "Fast Track … U.S. Food and Drug Administration" (UT5) | blocked as names | New | same |
| Acquisitions: "… for $25.00 per share in cash" (UA1), "… tender offer for all outstanding shares" (UA2), "… shares will cease trading on Nasdaq" (UA4) | "says 'share', which does not restate the row (acquisition)" | New. **A definite defect (SHARE)** | `codev` pattern `shar\w*` (`rights_signals.py:34`) is checked before `acquire` "shares?" (`:37`) |
| "Alpha Bio provided notice of termination of the U.S. license, effective March 1, 2025" (UT1; effective before the as-of date) | "says 'notice'" | New | every time word blocks an ending, whatever its date |
| "Alpha Bio completed the transition of U.S. rights" (UT8); "… and transfers the IND to Nerida Bio" (UT9); "Omega Merger Sub" (UA7) | blocked | UT8/UT9 old, UA7 new | termination may not use `acquire` or `transfer` words |
| "Chinaco Pharmaceutical (Suzhou) Co., Ltd. licenses NB-7 …" beside licensee "Chinaco Pharma" (UC11) | "names Chinaco Pharmaceutical" | Old | name variants are not matched |
| "Nerida Bio retains all rights to NB-7 outside mainland China" (UC21, UC22) | "says 'retains'" | Old (G5) | the plain form allows "to the program", not a code |
| Acquisition of the company under a variant name ("Nerida Biotherapeutics", F3) | blocked as ACQ-X | Introduced by ACQ-X; a small cost | `same_company` |
| Clean and reaching tier 1: UC4 (lower-case title), UC7, UC8, UC9, UC16, UC19, UC24, UC25, UC27, UT3, UT6, UT7, UA5, UA6; REREVIEW8's G1–G4, G10, G11, G13, G14, C1–C4, C8, C11, C13, C15, C18, C19, U3, U4, U8, B16, B17 | tier 1 | | |

Real wording carries datelines, titles, cities, disease and target names almost always. A vendor export of real
quotes would hold back most clear-path rows. The block names the word and asks a question, so nothing is dropped,
but the top tier becomes rare for clean cases.

## 4. Output honesty

In favour: the CLDN18.2 memo and workbook call nothing available or open as a rights tier. Memo prose has no position
or tier codes (the only all-caps code is "SYNTHETIC_FIXTURE" in ws_h/ws_i). The workbook Diligence sheet still has
91 "OPEN" question-status cells (not a rights tier; unchanged). Holders shown in CLDN18.2, ws_i and ws_j are cited.

| # | Where | Output (copied) | Problem | Cause |
|---|---|---|---|---|
| OWNER-KEY (Medium) | `a/d10b.out` F9: China license + acquisition of "Nerida Bio US" by Tessaly Pharma, United States | `OWNER_ACQUIRED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE holder='Nerida Bio' owner='Nerida Bio'`; "reason: Tessaly Pharma acquired Nerida Bio US …"; "ask: Would Tessaly Pharma license or sell US rights?" | The owner shown is the company whose U.S. arm Tessaly bought. F5 (parent "Nerida Holdings" acquired by Omega) and F6 (the company acquires Sideco Bio, read as "owner acquired") have the same split | `same_company` admits "US"/"Holdings" (`rights_ledger.py:201-203`); `owner()` (`:426`) keys on the grant's licensor name, which the acquisition does not match |
| LBL-NONE2 (Low) | `a/d10b.out` N2, N6; `a/d10.out` N3, N5 | "N2 … NO_RIGHTS_EVIDENCE … cited=[3]; reason: no usable grant recorded" | `NO_RIGHTS_EVIDENCE` beside a cited row (a future Japan license, a future statement, a lone lapse) | `rights_position.py:554` checks only straddling and announced rows |
| Q-FUT3 (Low) | E2; ws_j JS107 | "ask: Who holds US rights? Recorded deals cover other territories only" beside a cited future U.S. exercise | The question contradicts a cited row | `rights_position.py:547` keys on `announced` |
| L1f (Low) | ws_j memo line 9 | "for 1 DealScreen's word rules found nothing else in the rights texts, names, rows and row quotes that contradicts the statement" | ATG-022's China row quote names "Chinaco Pharma U.S."; it was never read | `memo.py:530`; UNCITED |
| L3f (Low) | `e2e/assert_k.log` | "Beside a clear position, the top-tier gate accepts it as a plain form … a grant over other places only" for "Licensed in China to Chinaco, Tessaly Transpacific" | Reports PN4 as the gate's verdict | `cli/dealscreen.py`; PN4 |

## 5. Acceptance criteria

| AC | Verdict | Evidence |
|---|---|---|
| AC1 | PASS | ws_j: "30 events, 0 rejected rows (license public/research_only)"; provenance in every evidence line |
| AC2 | PARTIAL | CLDN18.2: no OPEN tier, nothing called available. Held out: tier 0 beside a China row that names a U.S. arm or a U.S. holder (UNCITED, ws_j ATG-022); `NO_RIGHTS_EVIDENCE` beside cited rows (LBL-NONE2); L1f overclaims |
| AC3 | PARTIAL | Rights-file territories parse. Not met: wider reach and new grants in quotes read as "other territories only" (LOWER, WIDER3, MASK, PLACE); PN4 texts |
| AC4 | PARTIAL | REREVIEW8's ending inputs block. Not met: endings not yet in effect (HEDGE3); a re-grant after a return passes (LOWER); LM-302 still not RETURNED (data) |
| AC5 | PARTIAL | Exercise and lapse logic holds for recorded options. A future-dated exercise is dropped (FUT3). Clean lapse quotes pass (B16, U8) |
| AC6 | PARTIAL | Not met: a China row naming a U.S. holder beside a statement is tier 0, not CONFLICTING (UNCITED) |
| AC7 | PARTIAL | FUT2 fixed for grants. Not met: FUT3; a quote's later date is not compared with the as-of date (H1) |
| AC8 | PASS | `compare.py` 0 of 62; HEAD re-screen identical; cross-version 312 programs equal to the stored results; cycle-4 equivalence 4 of 4 byte-identical (re-run) |
| AC9 | PARTIAL | Preferences work. Many clean real phrasings are held back (§3) |
| AC10 | PARTIAL | Every holder shown is cited. Not met: rows not cited on availability, return and lapse paths (UNCITED); OWNER-KEY; Q-FUT3 |
| AC11 | PARTIAL | Not met: LOWER, PLACE, MASK, WIDER3, HEDGE3, FUT3 and UNCITED ask no question about the third party, the reach or the date |
| AC12 | PASS | `git diff b3e3fe9 d905ff0 -- src/` adds only generic words (US states, Canadian provinces, EU members, exchanges, currencies); no CLDN18.2 company or program name |
| AC13 | PARTIAL | Unchanged: IBI343, SHR-A1904 not unobstructed; RC148, FL-301, XNW27011 encumbered; LM-302 CONFLICTING, not returned |
| AC14 | FAIL | 8 new High errors on held-out inputs; none in the CLDN18.2 output |

## 6. CLDN18.2 measured against the reference and B

| Item | Revision 9 | Revision 10 |
|---|---|---|
| `after_transaction.csv` (62 programs) | — | byte-identical to `after_v9`; my HEAD re-screen identical |
| Memo | — | identical to `after_v10/memo_R1v10.md` at HEAD |
| Scientific fields vs frozen baseline | 0 of 62 | 0 of 62 (`compare.py`) |
| Top-tier programs | 0 | 0 |

Error classes against `reference_calls.csv`, re-read row by row from `after_v10/after_transaction.csv` for programs
with rights evidence or a reference deal: false unobstructed **0**; false encumbrance 0 definite, 2 likely outdated
(EO-3021, SYSA1801: reference "RETURNED_TO_ORIGINATOR_UNCLEAR", tool licensed to Elevation Oncology, deprioritised);
wrong holder 1, labelled (LM-302 "Turning Point Therapeutics (recorded; conflicting)"); wrong territory 0; missed
return 2 (SKB315 `NO_RIGHTS_EVIDENCE`; LM-302 conflicting). Programs the reference gives to large pharma without a
rights row (Sonesitatug vedotin, ASP2138, ASP546C, AZD5863, AMG 910) read `NO_RIGHTS_EVIDENCE`, deprioritised by
sponsor.

Usefulness against general Claude (B): inputs and outputs are identical to revisions 8 and 9, so the earlier score
stands: DealScreen **10 right / 4 partial / 1 missed**; B **14 / 1 / 0**. I re-read the rows and found the same
classes; I did not re-score independently. No advantage is shown. The CLDN18.2 run cannot show revision 10's
over-caution, because only one of its 17 real quotes sits on a clear path.

Cycle-4 equivalence: I re-ran it at HEAD with the implementer's wrapper copied to `rr10/xv/run_equiv.py` (output in
my directory; the tracked result file was not touched). Result: `byte_identical: true`, `fast_path: true` for
synthetic_200, real_v1, real_v2 and real_v1_with_cycle1_assertions (4 of 4). The response's claim holds.

## 7. Remaining issues, ranked

1. **(Safety, High) LOWER.** Endings and acquisitions may use every grant word, and lower-case descriptions of a
   third party are harmless. "… which has since licensed them to another company" is tier 1. ws_j #2, #4, #6.
2. **(Safety, High, older) UNCITED.** Beside a statement, a return or a lapse, grants over other territories are not
   cited and their quotes are not read. Tier 0. ws_j #1.
3. **(Safety, High, new) PLACE and MASK.** Placement by shape or neighbour ("said", "acts as", "reported", digits,
   defined acronyms, known-name words, "New Co"), and `_mask` eating "U.S."/"America" after a known name.
4. **(Safety, High) WIDER3 and HEDGE3.** Missing words ("any other territory", "further rights", "all 50 states";
   "to return", "elected to terminate", "wind-down"); no quote date is compared with the as-of date.
5. **(Safety, High) FUT3.** A future-dated option exercise is dropped. ws_j #3.
6. **(Usefulness, new)** Datelines, titles, cities, disease and target names, designations, "shares": most real
   press quotes now block. SHARE is a plain class-order defect.
7. **(Medium) OWNER-KEY.** Owner shown as the company after its U.S. arm or parent is acquired.
8. **(Low)** LBL-NONE2, Q-FUT3, L1f, L3f; PN4 (low realism).
9. **(Judgement)** "parent of" and "a subsidiary of" describing the company (P20, P21); comma-joined China licensees;
   partial-scope returns (H7, H8); W9, W10; B18/B19.
10. **(Recall)** The rights file still caps recall (LM-302's and SKB315's returns).

## 8. The single highest-value next fix

Make the positive form positive in its words, not only in its names. On a clear path, a clause should pass only if
every word is in a small allow-list for its row type (the parties, the program, places, dates, amounts, and the
verbs and nouns that restate that exact row: "returns … rights to <licensor>", "licenses <program> to <licensee> in
<place>"), and anything else (another grant, "another company", "any other territory", "to return") blocks with the
word quoted. Read every row the program has, not only the cited ones. Together these close LOWER, WIDER3, HEDGE3,
PLACE, MASK and UNCITED. To pay for it, strip press-release furniture before reading (a leading dateline up to "--"
or "–", a "said <person>, <title> of <known party>" tail, "About <known party>" and forward-looking boilerplate) and
fix the "shares" class order, so clean real quotes still reach tier 1.
