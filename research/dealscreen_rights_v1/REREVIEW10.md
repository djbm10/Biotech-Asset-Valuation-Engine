# Adversarial re-review 10: cycle R1 revision 11, rights evidence (CLDN18.2)

**AI-SIMULATED INTERNAL REVIEW.** I am an AI (Claude) playing a skeptical pharma BD analyst and auditor. I am not a
human reviewer. I approve nothing, and nothing here is validation. I did not trust REREVIEW9_RESPONSE.md. I checked
each claim by running code or reading outputs. I report only what I ran or read.

Scope and method:
- Revision 11 is commit 7a62efd (HEAD; it also holds U1 revision 6). I recorded the SHA-256 of all 37 files in
  `src/bve/dealscreen/` at the start (`/tmp/claude-1000/rr11/sha_start.txt`) and at the end (`sha_end.txt`). No file
  changed. I edited nothing except this file. No commit, stash or git change. ruff ran with `--no-cache`; mypy's cache
  went to `/tmp/claude-1000/rr11/mypy_cache`. The tracked `cycle4/equivalence_result.json` has the same md5 before and
  after my equivalence run.
- All scripts and outputs are in `/tmp/claude-1000/rr11/`. Per-program cases go through
  `screening.program_transaction`. My harness `h11.py` is the implementer's placeholder-free `h5.py` plus the
  `program_text` and `program_names` arguments that screening passes. Defaults: company "Nerida Bio", program NB-7,
  buyer {US}, as-of 2025-06-01, max age 730 days, `encumbered_rights: deprioritize`. Every row in my probes has its
  own quote (no placeholder). "China license" = Nerida Bio → Chinaco Pharma, exclusive, mainland China, 2025-01-01.
  "US license D1" = Nerida Bio → Alpha Bio, United States, 2024-03-01, ended by a termination linked to D1,
  2025-01-15. "Option D2" = Alpha Bio's U.S. option (2024-03-01) and a lapse linked to it (2025-01-15).
  "Acquisition" = Omega Holdings acquires Nerida Bio, Worldwide, 2025-02-01, beside the China license.
- New scripts: `a/p11.py` (75 inputs), `a/q11.py` (spot checks). `a/p11_rev10.out` is the same script run on
  `git archive b0388eb` (revision 10) first on `PYTHONPATH`, so "introduced by revision 11" means tier 0/1 at
  revision 11 and blocked at revision 10.
- End to end: copies of `~/.cache/rights_v1/fin11_ws` (C3 buyer, as-of 2026-10-29) with new rights files:
  `e2e/rights_l.csv` (the 17 transcribed rows plus my fictional rows Y01–Y14) and `e2e/rights_j2.csv` (REREVIEW9's
  ws_j rows with the "(test) " prefix removed). Also `ws_h2`, `ws_i2` (REREVIEW9's ws_h and ws_i without the prefix).
  Counterparties are fictional (Chinaco Pharma, Alpha Bio, Omega Holdings, Tessaly Pharma, Sideco Bio). URLs are
  `example.test`. Nothing here is a fact about a real program.
- Checks at HEAD: `tests/dealscreen` **1,436 passed** (75 s). ruff: "All checks passed!". mypy `src/bve/dealscreen` +
  CLI: "Success: no issues found in 38 source files". `compare.py`: "AC8 scientific fields changed: 0 of 62".

## Summary

- **Every input REREVIEW9 listed now blocks**, except its own clean controls and judgement items. My re-runs of the
  previous reviewer's probes are byte-identical to the implementer's (`fin11/out` with the placeholder,
  `fin11/probe/a` without it). REREVIEW9's ws_j rows block on real words once the "(test)" prefix is removed (ws_j2).
- **The allow-list is a bag of words, and the bag holds the words a third party needs.** "has", "had", "own",
  "both", "they", "all", "full", "first", "after", "following", "term" and "end" are grammar or row words. A lapse may
  say "not" and "exercise". A license may say "sale" and "transferred"; an acquisition "sold" and "sells". So
  "Alpha Bio has the U.S. rights to NB-7" passes as a termination quote, "Alpha Bio did not let the U.S. option lapse"
  as a lapse quote, and "NB-7 was sold for $50 million in cash" as an acquisition quote.
- **Revision 11 opened new paths.** "may" is accepted as the month May, so "Alpha Bio's U.S. rights to NB-7 may
  revert to Nerida Bio" is tier 1. A notice of termination passes when any date in the clause is past, even the
  notice date itself. Landscape words are allowed in quotes, capitalised or not, so a partner named in an alias or a
  mechanism field is no longer a name. A title-case headline before a dateline is stripped.
- **Dates are compared only when they carry a four-digit year.** "on December 1", "in Q4", "in H2", "on Friday" and
  "in December '26" pass on an ending. A bare "2025" or "January 10th, 2025" reads as 31 December and blocks clean
  past events (usefulness cost).
- **Names: three older holes.** The reader treats "Chinaco Holdings" and "Alpha Holdings" as the known party
  (`same_company` drops "Holdings" and "Group"); a lone letter-digit token ("X4", "C4") is placed as a program code;
  a parenthetical with an exchange name is deleted before reading, so "(Nasdaq-listed Tessaly Pharma holds U.S.
  rights)" is never read.
- **End to end:** in `ws_l`, 7 programs reach a top tier through these paths, ATG-022 at tier 0. CLDN18.2 itself has
  0 top-tier programs, and its output is byte-identical to the implementer's run.
- **OWNER-KEY is only partly fixed.** "Nerida Bio Holdings" or "Nerida Bio Group" acquired still counts as the
  company, because the party check uses `party_key`, which drops those words. Two different acquirers of the company
  are not a conflict: the last one silently wins.
- **Usefulness.** The response's numbers hold (11 of 43 clean cases pass without the placeholder; 13 of 17 real
  quotes block read directly). The response's own end-to-end counts also rest on the "(test)" prefix: ws_h's clean
  TORL case is tier 1 at revision 11 once the prefix is removed, not 0. OWNER-KEY lowers the usefulness score against
  general Claude from 10/4/1 to 8/6/1 (B: 14/1/0).

Definite new errors (not reported in REREVIEW9.md). None occurs in the CLDN18.2 output.

| Severity | Introduced by revision 11 | Claimed fixed, fails on a close variant | Older, first reported here | Total |
|---|---|---|---|---|
| High: tier 0 or 1 while a third party may hold buyer-territory rights, or on contrary, conditioned or future evidence | 4: MAY, NOTICE, VOCAB, HEADLINE | 5: LOWER2, WIDER4, HEDGE4, UNDATED, CODE2 | 4: LAPSE-NEG, SALE, SUFFIX, NOTE | **13** |
| Medium: wrong holder or owner, a missed conflict | 1: MINORITY | 1: OWNER-KEY2 | 2: ACQ-TWO, ACQ-PENDING | **4** |
| Low: false label or wording; no tier change | 2: LBL-OWNER, LBL-DATE | 0 | 0 | **2** |

Disclosed by the implementer and confirmed, not counted: a name made only of allowed words ("Advanced Medicine has
all rights to NB-7", L14, tier 1). Usefulness costs (no safety effect) are in §3.

## 1. REREVIEW9_RESPONSE.md, claim by claim

| § | Claim | Verdict | Evidence (run or read) |
|---|---|---|---|
| 1 | Every word is read; a clause passes only if each word is on a list | **Held as code. Refuted as a safety property** | `_Reader.word_ok` checks every token. But the lists hold hold-verbs, pronouns, quantifiers, conditions and sale words (§2a–2h); 67 of my 75 inputs reach a top tier (61 attacks and 6 clean controls) |
| 1 | "another", "other", "any", "every", "further", "additional", "new", "third", "party", "company", "licensee", "partner", "not" are in no list | **Held for those words. Refuted for "not"** | "not" is in `_LAPSE` (`rights_vocab.py:77`): LP1, LP6 pass |
| 1 | "The words that point at another holder, place or time are in no list" | **Refuted** | "has", "own", "both", "they" (holder); "all", "full" (reach); "after", "following", "may" (time) are allowed (§2a–2d) |
| 1 | A word missing from the lists blocks; it cannot open a path into the top tiers | **Held as stated** | True for missing words. The paths come from words that are on the lists |
| 1 | `NEVER` keeps those words out of the program's own words | **Held for NEVER words. Refuted as a safety rule** | A partner name or "American"/"European" in a landscape field becomes an allowed word (VOCAB) |
| 1 | Capitalised corporate word always makes a name; MASK place words not absorbed | **Held** | PC1–PC4 block (`prevnp/a/p10.out`) |
| 1 | Placement by shape removed; only a lone program code is placed | **Held as code. Refuted as a safety rule** | A lone code-shaped company name ("X4", "C4") is placed (CODE2) |
| 1 | One known root with two business words blocks | **Held for business words. Refuted for legal words** | "Chinaco Holdings", "Chinaco Group", "Alpha Holdings" pass as the known party (SUFFIX) |
| 1 | Datelines, attributions, advisers, bylines removed only when anchored | **Held for attributions, advisers, bylines. Refuted for datelines** | `_DATELINE` accepts any capitalised words before the date, so a headline "Tessaly Pharma Holds Rights, BOSTON, March 3, 2025 --" is removed (HEADLINE). Exchange notes are removed unanchored (NOTE) |
| 1 | Every date in a clause is compared with the as-of date | **Refuted** | Only dates with a four-digit year are read (UNDATED) |
| 1 | Notice words allowed only when every date is on or before the as-of date | **Held as code. Refuted as a safety rule** | The notice date itself satisfies it (NOTICE) |
| 1 | UNCITED: every applied row is cited beside a clear position | **Held** | AV1–AV4, RT1, RT2 block and cite the China row (`prevnp/a/av10.out`, `rt10.out`); ws_j2 ATG-022 blocks on "names US" |
| 2 | LOWER, PLACE, MASK, WIDER3, HEDGE3 fixed | **Held for the listed inputs. Refuted on close variants** | All P, PC, W, H inputs of REREVIEW9 block except P20, H7, H8 (judgement). Close variants: §2a–2e |
| 2 | FUT3: a future-dated exercise is announced | **Held** | E2, E3 block (`prevnp/a/d10.out`); ws_j2 JS107 blocks |
| 2 | PN4 | **Held** | "Licensed in China to Chinaco, Tessaly Transpacific" → refused; the CLI note agrees (`rights_reading_note`) |
| 2 | OWNER-KEY: "Nerida Bio US", "Nerida Holdings", "Nerida Bio International" are other entities | **Held for those names. Refuted on close variants** | "Nerida Bio Holdings", "Nerida Bio Group" (with company "Nerida Bio") and "Nerida Holdings" (with company "Nerida") count as the company (OWNER-KEY2) |
| 2 | LBL-NONE2, Q-FUT3, L1f, L3f | **Held** | N1–N6 read `RIGHTS_ROWS_NOT_APPLIED` (N4 is a clear return-only path); E2 asks "Recorded deals in force on the as-of date …"; ws_j2 memo no longer repeats L1 for ATG-022 |
| 2 | SHARE fixed | **Held** | UA1, UA2 reach tier 1 (`prevnp/a/u10.out`) |
| 3 | Tests 1,436; ruff, mypy clean | **Held** | Re-run at HEAD |
| 3 | CLDN18.2: 0 of 62 science; 2 transaction changes (Zolbetuximab, IMAB362) | **Held** | `compare.py` 0 of 62; my HEAD re-screen equals `after_v11` (CSV `cmp` identical, screens JSON identical, memo identical); `after_v10` vs `after_v11` differ only in those two programs |
| 3 | Cross-version 0 of 312; cycle-4 equivalence 4 of 4 | **Held** | My HEAD run of `cross_version.py` equals the revision 10 HEAD run on 312 programs; equivalence `byte_identical: true`, `fast_path: true` 4 of 4 |
| 3 | Probes: p10 0/75, p10b 0/5, d10 0/30 with the placeholder; p10 4/75, d10 7/30 without | **Held** (byte-identical) | The 7 d10 cases (E9, E12, N4, F2, F4, F8, F10) are correct by the replay rules |
| 3 | ws_h 0, ws_i 0, ws_j 0 top-tier placements | **Held as measured. Misleading** | Every fictional quote in those workspaces starts "(test)", and "test" blocks: 9, 14 and 12 blockers say "says 'test'". Without the prefix: ws_h2 1 (TORL, a clean control: "… TORL Biotherapeutics retains rights in the rest of the world" — correct), ws_i2 0, ws_j2 0. The safety result holds for i and j; for h the response understates usefulness |
| 3 | The placeholder argument | **Held** | The placeholder blocks on "test"/"record". The response reports both counts. It did not apply the same correction to its own end-to-end counts (above) |
| 3 | Usefulness: 11 of 43; 3 of 17 through the gate; 13 of 17 read directly | **Held** | `prevnp/a/u10.out` 11; `real_quotes.out` "3 of 17 … (4 rows give a clear position alone)", "13 of 17" |
| 3 | Breakdown of the 13: "2 on news style … the rest on ordinary deal words" | **Partly refuted** | Only 1 blocks on news style (row 8, "meanwhile"); row 7 now passes. Rows 13 and 14 block on the target name "Claudin18.2", which the response says program words handle: their landscape target is "Claudin 18.2" (spaced). Row 5 blocks on "late-stage" |
| 3 | Disease names pass in screening | **Held** | UC12 with `program_text=["Hodgkin lymphoma"]` is tier 1 (`a/q11.out`) |
| 3 | Usefulness against B "not re-measured" | **Unverified by the implementer; I re-scored the two changed rows** | Zolbetuximab and IMAB362 go from right to partial: 8/6/1 against B 14/1/0 (§6) |
| 4 | Open issues 1–7 | **Held, and wider** | Item 4 (allowed-word names) confirmed (L14). Item 5 ("a wrong entry would let a word through") is the main finding of this review, not a side note |

## 2. Paths into the top tiers

All outputs copied from `a/p11.out` unless stated. "blk: (none)" means `top_tier_blockers` is empty.

### 2a. Hold words and pronouns (LOWER2; claimed fixed, close variant; "own" introduced by revision 11)

US license D1 + termination. Output for each: `RIGHTS_RETURNED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE
holder='Nerida Bio' owner='Nerida Bio'`, blk: (none). Expected: blocked; the quote says Alpha Bio or someone else
still holds rights.

| Id | Termination quote | Revision 10 |
|---|---|---|
| E1 | "Alpha Bio has the U.S. rights to NB-7" | tier 1 |
| E2 | "Alpha Bio returns U.S. development rights to Nerida Bio; Alpha Bio has the commercial rights" | tier 1 |
| E7 | "Alpha Bio returns U.S. rights to Nerida Bio; both have the U.S. rights" | tier 1 |
| E8 | "Alpha Bio returns U.S. development rights to Nerida Bio; they own the commercial rights" | **blocked** |
| E9 | "Alpha Bio returns U.S. rights to Nerida Bio, which handed the rights back to Alpha Bio" | tier 1 |
| LP3 (lapse D2) | "Alpha Bio let the option lapse; Alpha Bio has the U.S. rights" | tier 1 |

China license, quote as given: `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE`, blk:
(none). L3 "…; Chinaco Pharma will own all rights to NB-7" (blocked at revision 10); L5 "… and has all rights to
NB-7"; L6 "…; both own all rights to NB-7" (blocked at revision 10); L20 "…; they have all rights to NB-7".

Cause: `FUNCTION_WORDS` (`rights_vocab.py:41-47`) holds "has have had" (:43), "both" (:43), "they them their who
whose" (:42) and "own" (:46). `_ENDING` holds "handed hands back" and "commercial", "development" (:72-73). The
reader checks each word, not who does what (`rights_quote.py:310-325`): a word on the list passes whatever its role.

### 2b. Reach in grammar words (WIDER4; claimed fixed, close variant)

China license; each `NOT_ENCUMBERED… / NO_THIRD_PARTY_GRANT_IN_EVIDENCE`, blk: (none). All tier 1 at revision 10 too.

| Id | Quote |
|---|---|
| L1 | "Chinaco Pharma licenses mainland China rights to NB-7 and will receive all rights upon approval" |
| L2 | "Chinaco Pharma receives full rights to NB-7" |
| L13 | "Chinaco Pharma licenses NB-7 for mainland China and receives all-territory rights" |
| L21 | "… and receives the first right to all rights" |

Cause: "all", "full", "first" are in `FUNCTION_WORDS` (`rights_vocab.py:45-46`); "will" and "upon" are allowed on
grants (`GRANT_TIME`, `rights_quote.py:226`); hyphen parts are checked one by one (`:232-233`), so "all-territory"
passes. A word on a list is never checked against `signal` (`:311`).

### 2c. Conditions in grammar words (HEDGE4; claimed fixed, close variant)

US license D1 + termination; each `RIGHTS_RETURNED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE`, blk: (none);
tier 1 at revision 10 too. Expected: blocked (the ending waits on a later event).

| Id | Quote |
|---|---|
| E3 | "Alpha Bio returns U.S. rights to Nerida Bio after the phase 3 trial" |
| E4 | "Alpha Bio returns U.S. rights to Nerida Bio following approval" |
| E5 | "Alpha Bio's U.S. license to NB-7 ends at the end of the term" |

Cause: "after", "following", "prior", "now", "term", "terms" are `FUNCTION_WORDS` (`rights_vocab.py:44`); "phase",
"trial", "approval" are `GENERAL_WORDS` (:54-57); "end", "ends" are `_ENDING` (:73).

### 2d. "may" read as a month (MAY; introduced by revision 11)

| Id | Row | Quote | Output | Revision 10 |
|---|---|---|---|---|
| E10 | termination | "Alpha Bio's U.S. rights to NB-7 may revert to Nerida Bio" | `RIGHTS_RETURNED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE`, blk: (none) | blocked |
| E11 | termination | "Alpha Bio may end the U.S. license to NB-7" | same | blocked |
| LP4 / LP5 | lapse | "Alpha Bio may exercise the U.S. option" / "The U.S. option to NB-7 may lapse" | `NOT_ENCUMBERED… / NO_THIRD_PARTY_GRANT_IN_EVIDENCE` | blocked |
| L9 | China license | "… and may receive all rights" | same | blocked |
| A7 | acquisition | "Omega Holdings may acquire Nerida Bio for $5 per share" | `OWNER_ACQUIRED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE holder='Omega Holdings'` | blocked |
| ws_l Spevatamig | Y03 termination | "Alpha Bio's U.S. rights to Spevatamig may revert to Phanes Therapeutics" | memo "#6 Spevatamig (PT886): no third-party grant in evidence; rights position: rights returned per evidence" | — |

Cause: `_MONTH_WORDS` (`rights_quote.py:74-77`) takes every `calendar.month_abbr`, including "may", and `word_ok`
returns True for it (`:224`) before the `TIME` signal (`rights_signals.py:76`) is consulted.

### 2e. Dates without a four-digit year (UNDATED; claimed fixed, close variant of HEDGE3 H1)

US license D1 + termination dated 2025-01-15, as-of 2025-06-01. Each `RIGHTS_RETURNED_PER_EVIDENCE /
NO_THIRD_PARTY_GRANT_IN_EVIDENCE`, blk: (none). Expected: blocked (the date may be after the as-of date).

E12 "… on December 1"; E13 "… in Q4"; E14 "… in H2"; E15 "… in December '26"; E20 "… on Friday".

Cause: `_clause_dates` (`rights_quote.py:151-170`) reads only patterns with `\d{4}`. Month, quarter, half and weekday
words are allowed as words (`_MONTH_WORDS`, `:76-77`). The response says "every date in a clause … is compared".

### 2f. Notice of termination with no effective date (NOTICE; introduced by revision 11)

| Id | Termination quote | Output | Revision 10 |
|---|---|---|---|
| E16 | "Alpha Bio gave notice of termination of the U.S. license on January 10, 2025" | `RIGHTS_RETURNED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE`, blk: (none) | blocked |
| E17 | "Alpha Bio provided notice of termination on January 10, 2025, effective following approval" | same | blocked |
| ws_l Sonesitatug | Y14 "Alpha Bio provided notice of termination of the U.S. license on February 1, 2026" | `RIGHTS_RETURNED_PER_EVIDENCE`, `top_tier_blockers: []` (DEPRIORITIZED only by sponsor) | — |

Expected: blocked. A notice date says when notice was given; license notice periods are commonly months, so the end
may fall after the as-of date. Cause: `dated_ok=bool(dates)` (`rights_quote.py:303`) lets `DATED_ENDING_WORDS`
(`rights_vocab.py:102`) pass when the clause holds any date not after the as-of date (`rights_quote.py:228`).

### 2g. Lapse rows that say the option did not lapse (LAPSE-NEG; older, first reported here)

Option D2 + lapse; each `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE holder=None`,
blk: (none); tier 1 at revision 10 too. LP1 "Alpha Bio did not let the U.S. option lapse"; LP2 "Alpha Bio did
exercise the U.S. option"; LP6 "The option did not expire". ws_l JS107 (Y08 "Alpha Bio did not let the U.S. option
lapse"): memo "#3 JS107: no third-party grant in evidence; … option to Alpha Bio lapsed in US per source".
Expected: blocked; the quote contradicts the row. Cause: `_LAPSE` holds "not", "did", "let", "exercise"
(`rights_vocab.py:76-78`).

### 2h. Sale and transfer words (SALE; older, first reported here)

| Id | Row | Quote | Output |
|---|---|---|---|
| L4 | China license | "Chinaco Pharma licenses NB-7 for mainland China; Nerida Bio announced the sale of all rights to NB-7 for $40 million in cash" | `NOT_ENCUMBERED… / NO_THIRD_PARTY_GRANT_IN_EVIDENCE` |
| L7 | China license | "…; Nerida Bio transferred all rights to NB-7 for $40 million" | same |
| A1 | acquisition | "Omega Holdings acquires Nerida Bio; NB-7 was sold for $50 million in cash" | `OWNER_ACQUIRED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE holder='Omega Holdings'` |
| A2 | acquisition | "Omega Holdings acquires Nerida Bio, which sold NB-7 prior to the merger" | same |
| A4 | acquisition | "Omega Holdings acquires Nerida Bio and sells NB-7" | same |
| ws_l BL-M05D1 | Y09 | "Omega Holdings acquires Sichuan Baili Pharmaceutical, which sold BL-M05D1 prior to the merger" | memo "#4 BL-M05D1: no third-party grant in evidence; rights position: owner acquired per evidence" |

Expected: blocked; the program went to an unnamed buyer. Cause: `_GRANT` holds "sale", "sell", "transfer",
"transferred" (`rights_vocab.py:65-68`); `_ACQUISITION` holds "sold sell sells" (:84). All tier 1 at revision 10.

### 2i. Names (SUFFIX, CODE2, NOTE, HEADLINE)

| Id | Finding | Quote | Output | Revision 10 |
|---|---|---|---|---|
| L10 / L11 | SUFFIX (older) | China license "…; NB-7 is also licensed to Chinaco Holdings" / "… Chinaco Group" | `NOT_ENCUMBERED… / NO_THIRD_PARTY_GRANT_IN_EVIDENCE`, blk: (none) | tier 1 |
| E6 | SUFFIX | termination "Alpha Bio returns U.S. rights to Nerida Bio; Alpha Holdings has the U.S. rights" | `RIGHTS_RETURNED… / NO_THIRD_PARTY_GRANT_IN_EVIDENCE` | tier 1 |
| ws_l TORL-2-307-ADC | SUFFIX | Y11 "Chinaco Pharma licenses TORL-2-307-ADC for mainland China; TORL-2-307-ADC is also licensed to Chinaco Holdings" | memo "#7 TORL-2-307-ADC: no third-party grant in evidence" | — |
| E18 / L15 | CODE2 (claimed fixed: PLACE) | "…; X4 has the U.S. rights" / "…; NB-7 is also licensed to C4" | tier 1, blk: (none) | tier 1 |
| L16 / L17 | NOTE (older) | "Chinaco Pharma licenses NB-7 for mainland China (Nasdaq-listed Tessaly Pharma holds U.S. rights)" / "(U.S. rights: Tessaly Pharma, NYSE: TSLY)" | tier 1, blk: (none) | tier 1 |
| ws_l ATG-022 | NOTE + UNCITED path | Y04 availability; Y05 China license with the L16 quote | memo "#1 ATG-022: availability stated, unverified"; the Y05 quote is cited verbatim beside it | — |
| L18 | HEADLINE (introduced, low realism) | "Tessaly Pharma Holds Rights, BOSTON, March 3, 2025 -- Chinaco Pharma licenses NB-7 for mainland China" | tier 1, blk: (none) | blocked |

Expected: blocked, naming the party. Causes:
- SUFFIX: `_Reader._run` places a run when `same_company(full, k)` (`rights_quote.py:283-287`). `party_key` drops
  "holdings", "group", "company" (`rights_territory.py:126-128`), so "Chinaco Holdings" equals "Chinaco Pharma" minus
  a business word. `_variants` lists only business words (`rights_quote.py:194`), not legal ones, so it does not see
  the second form.
- CODE2: `_CODE` (`rights_quote.py:143`) places any lone `[A-Z]{1,6}\d{1,6}` token (`:277-280`). Company short names
  of that shape exist.
- NOTE: `_EXCHANGE_NOTE` (`rights_quote.py:95-96`) removes any parenthetical containing an exchange name, whatever
  else it says, before any reading (`:340`).
- HEADLINE: `_PLACE_RX` (`rights_quote.py:98`) is any run of up to four capitalised words; `_DATELINE` (:101-103)
  chains them with commas, so a title-case headline is removed as a place.

### 2j. The program's own words (VOCAB; introduced by revision 11; held-out only)

| Id | Landscape text passed | Quote | Output | Revision 10 |
|---|---|---|---|---|
| V2 | indication "AJCC (American Joint Committee on Cancer) stage IV gastric cancer" | China license "… and receives American rights" | `NOT_ENCUMBERED… / NO_THIRD_PARTY_GRANT_IN_EVIDENCE` | blocked |
| V1 (control) | none | same | blocked: "names American" | blocked |
| V3 | alias "Tessaly-501" | China license "…; Tessaly has all rights to NB-7" | tier 1 | blocked |
| V4 | mechanism "anti-CLDN18.2 ADC from Tessaly" | termination "…; Tessaly has the U.S. rights" | tier 1 | blocked |
| V6 | indication "European patients with gastric cancer"; buyer {EU} | China license "… and receives European rights" | tier 1 (V7 control without the text: blocked) | blocked |

Cause: `program_vocabulary` (`rights_vocab.py:112-122`) adds every landscape word that is not in `NEVER` and not a
signal; a company word or a place adjective is neither. A vocabulary word is never name-like, even capitalised
(`rights_quote.py:242`). "American", "European" and "North American" are not regions (`rights_territory.py:25-41`).
Realism: I checked all 62 CLDN18.2 programs; no rights party's distinctive word is in any program's vocabulary
(only "torl", the company's own word in TORL-2-307-ADC). But real fields are noisy: LM-302's indication field holds
"Candonilimab", another product.

### 2k. Acquisitions (Medium)

| Id | Finding | Input | Output (copied) | Expected |
|---|---|---|---|---|
| A3 / A6 | ACQ-PENDING (A3 older, A6 introduced) | "Omega Holdings will acquire Nerida Bio, subject to closing conditions" / "… for $5 per share, pending approval" | `OWNER_ACQUIRED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE holder='Omega Holdings'` | blocked; owner not established. Real rows 1–2 have this shape ("Astellas will pay EUR 422 million to acquire …") and pass the reader directly (`real_quotes.out`) |
| A5 | MINORITY (introduced) | "Omega Holdings acquires 10 percent of the shares of Nerida Bio" | same, owner 'Omega Holdings' | blocked; a minority stake is not an acquisition |
| O1 / O2 | OWNER-KEY2 | acquisition of "Nerida Bio Holdings" / "Nerida Bio Group" by Omega, company "Nerida Bio" | `OWNER_ACQUIRED… / NO_THIRD_PARTY_GRANT_IN_EVIDENCE holder='Omega Holdings'` | blocked, as for "Nerida Holdings" (F5) |
| O3 | OWNER-KEY2 | company and China licensor "Nerida"; "Nerida Holdings" acquired | same | blocked |
| O4 | ACQ-TWO (older) | Omega acquires Nerida Bio (2025-02-01); Sideco Bio acquires Nerida Bio (2025-03-01) | `OWNER_ACQUIRED… / NO_THIRD_PARTY_GRANT_IN_EVIDENCE holder='Sideco Bio'`, blk: (none) | CONFLICTING, citing both |

Causes: acquisitions are in `_ANNOUNCED` (`rights_quote.py:71`), so `GRANT_TIME` words pass (`:226`); "percent" is a
function word and "shares" an acquisition word. The party check uses `party_key(e.grantor) not in parties`
(`rights_ledger.py:183`, `:224`), and `party_key` drops "Holdings" and "Group"; `_one_entity` is used only for the
company. `succession[party_key(e.grantor)] = …` (`rights_ledger.py:237`) overwrites an earlier acquirer silently.

### 2l. Judgement calls (not counted)

- L8 "…; Nerida Bio pays royalties on all sales of NB-7" (tier 1): royalties paid out suggest an upstream licensor.
- L12 "…; NB-7 is also licensed to Chinaco Pharma" (tier 1): a second license, territory unstated.
- P20 (subsidiary of a known party), H7, H8 (partial-scope returns): unchanged.
- A row with no quote passes the gate unread (`rights_gate.py:275`), while the same row with an unusual word blocks:
  `a/q11.out` NOQ, a China license and a D1 termination with no quotes, is tier 1. This is consistent with the design
  (structured fields decide), but it means a sparser export scores better than a richer one.

## 3. Over-caution and usefulness

These are usefulness costs, not safety errors.

| Input | Revision 11 | Cause |
|---|---|---|
| E22 "Alpha Bio returned U.S. rights to Nerida Bio in 2025" (as-of 2025-06-01) | blocked: "gives the date 2025-12-31, after the as-of date" | a bare year is read as 31 December (`rights_quote.py:169`); new (tier 1 at revision 10) |
| E23 "… on January 10th, 2025" | same | the ordinal day is not parsed, so only "2025" is read; new |
| Real CLDN18.2 quotes read directly | 13 of 17 block | 'i' (rows 3, 4), 'late-stage', 'Company', 'meanwhile', 'co-promote', 'worldwide' (correct), 'region', 'through' (rows 12, 16), 'Claudin18.2' (rows 13, 14), 'biotechnology' |
| "Claudin18.2" in a quote when the landscape target is "Claudin 18.2" | blocked ("names Claudin18.2") | vocabulary keeps tokens as written; a spaced landscape form does not cover the joined form |
| Reviewer's 43 clean cases, no placeholder | 11 pass | exec quotes, "About" boilerplate, cities, "retains all rights … outside mainland China" (UC21), "We", "listed", brand names |
| Zolbetuximab, IMAB362 | owner lost (OWNER-KEY) | the company bought the originator; no grant row names the originator |
| ws_h TORL (clean "retains rights in the rest of the world") | tier 1 without the "(test)" prefix; the response's "0" is the prefix | — |

The response's usefulness numbers are honest as counts. Its placeholder argument is right. Two omissions: its
end-to-end counts are subject to the same prefix artifact, and two of the 13 real blocks are on the target name it
says program words solve. In practice a clean real press quote rarely reaches a top tier, and the blocks that remain
are not the dangerous ones: §2 shows that dangerous wording often passes while ordinary press furniture blocks.

## 4. Output honesty

In favour: the CLDN18.2 memo and workbook call nothing available or open as a rights tier. The only "available" in
the workbook is "a source states the program is available or a partner is sought (unverified)". The Diligence sheet
still has 91 "OPEN" question-status cells (not a rights tier; unchanged). Memo prose has no position or tier codes.
The CLI `assert` note uses the gate's own `accepted_form`, so the two agree; PN4 inputs are now refused in both.
Every holder shown in ws_l is cited, and each top-tier program's memo entry quotes the row verbatim, so a careful
reader can see the contradiction the tier hides.

| # | Where | Output (copied) | Problem | Cause |
|---|---|---|---|---|
| LBL-OWNER (Low, introduced) | CLDN18.2 Zolbetuximab reasons | "rights holder or owner per evidence 'Astellas Pharma US, Inc. (U.S. labeler per FDA label; not a rights statement)' matches declared 'Astellas'" | calls an FDA labeler the owner "per evidence" while the same text says it is not a rights statement; holder_per_evidence is empty | `transaction.py:218-222` reads `pos.holders`, which `also_named` filled with the labeler; before revision 11 the acquisition owner Astellas matched first |
| LBL-DATE (Low, introduced) | CLDN18.2 memo line 31 | "Zolbetuximab (excluded): rights rows recorded, none applied on the as-of date, newest evidence 2016-10" | the row was not applied because of OWNER-KEY, not because of the as-of date | `rights_position.py:556-558` uses one reason for every unapplied row |

## 5. Acceptance criteria

| AC | Verdict | Evidence |
|---|---|---|
| AC1 | PASS | ws_l and ws_j2: "30 events, 0 rejected rows"; provenance in every evidence line |
| AC2 | PARTIAL | CLDN18.2: no OPEN tier, nothing called available. Held out: ws_l ATG-022 tier 0 beside a China row whose quote says Tessaly holds U.S. rights (NOTE) |
| AC3 | PARTIAL | Rights-file territories parse. Not met: "all rights", "full rights", a sale or a second licensee in a quote read as "other territories only" (WIDER4, SALE, SUFFIX, CODE2, VOCAB) |
| AC4 | PARTIAL | REREVIEW9's ending inputs block. Not met: "may revert", "after the phase 3 trial", undated months, a notice date, "Alpha Bio has the U.S. rights" (MAY, HEDGE4, UNDATED, NOTICE, LOWER2); LM-302 still not RETURNED (data) |
| AC5 | PARTIAL | FUT3 fixed. A lapse row whose quote says the option did not lapse, or was exercised, is read as lapsed (LAPSE-NEG) |
| AC6 | PARTIAL | Two acquirers of one company are not CONFLICTING (ACQ-TWO); ATG-022 in ws_l is tier 0, not CONFLICTING |
| AC7 | PARTIAL | Four-digit dates compared. Not met: dates without a year (UNDATED). Over-caution: a bare same year reads as 31 December |
| AC8 | PASS | `compare.py` 0 of 62; HEAD re-screen identical to `after_v11`; cross-version 0 of 312; cycle-4 equivalence 4 of 4 byte-identical (re-run) |
| AC9 | PARTIAL | Preferences work. Most real phrasings are held back (§3) |
| AC10 | PARTIAL | Every applied row is now cited beside a clear position (UNCITED fixed). Not met: owner shown for a pending acquisition or a minority stake (ACQ-PENDING, MINORITY); LBL-OWNER |
| AC11 | PARTIAL | The §2 paths ask no question about the holder, the condition or the date |
| AC12 | PASS | `git diff b0388eb 7a62efd -- src/` adds no CLDN18.2 company or program name (grep of added lines) |
| AC13 | PARTIAL | IBI343, SHR-A1904 not unobstructed; RC148, FL-301, XNW27011 encumbered; LM-302 CONFLICTING, not returned |
| AC14 | FAIL | 13 new High errors on held-out inputs; none in the CLDN18.2 output |

## 6. CLDN18.2 measured against the reference and B

| Item | Revision 10 | Revision 11 |
|---|---|---|
| `after_transaction.csv` (62 programs) | — | differs from `after_v10` only for Zolbetuximab and IMAB362; my HEAD re-screen byte-identical to `after_v11` |
| Memo | — | identical to `after_v11/memo_R1v11.md` at HEAD |
| Scientific fields vs frozen baseline | 0 of 62 | 0 of 62 (`compare.py`) |
| Top-tier programs | 0 | 0 (tiers: 44 RIGHTS_UNRESOLVED, 17 DEPRIORITIZED, 1 EXCLUDED_BY_BUYER_PREFERENCE) |

Error classes against `reference_calls.csv`, re-read row by row for programs with rights evidence or a reference
deal: false unobstructed **0**; false encumbrance 0 definite, 2 likely outdated (EO-3021, SYSA1801: reference
"RETURNED_TO_ORIGINATOR_UNCLEAR", tool licensed to Elevation Oncology, deprioritised); wrong holder 1, labelled (LM-302
"Turning Point Therapeutics (recorded; conflicting)"); wrong territory 0; missed return 2 (SKB315
`NO_RIGHTS_EVIDENCE`; LM-302 conflicting). New: Zolbetuximab and IMAB362 no longer show an owner (reference:
"Astellas (owns 100% via Ganymed acquisition)"); this is a missed owner, not a false call. Programs the reference
gives to large pharma without a rights row (Sonesitatug vedotin, ASP2138, ASP546C, AZD5863, AMG 910) read
`NO_RIGHTS_EVIDENCE`, deprioritised by sponsor.

Usefulness against general Claude (B), on REREVIEW.md's 15 deal programs: only Zolbetuximab and IMAB362 changed.
Both were "right" (owner acquired, Astellas); now each shows no owner and asks "What rights to this program did
Ganymed hold when Astellas acquired it?", so I score them partial. DealScreen **8 right / 6 partial / 1 missed**;
B **14 / 1 / 0**. I re-scored only those two rows. No advantage is shown.

## 7. Remaining issues, ranked

1. **(Safety, High) The allow-list passes structure it cannot see.** Hold verbs and pronouns ("has", "own", "both",
   "they"), quantifiers ("all", "full"), conditions ("after", "following", "term"), "not" on lapses, and sale words
   on licenses and acquisitions. LOWER2, WIDER4, HEDGE4, LAPSE-NEG, SALE. ws_l #2, #3, #4, #5.
2. **(Safety, High, new) MAY and NOTICE.** "may" passes as a month; a notice date satisfies the dated-ending rule.
   ws_l #6.
3. **(Safety, High) Dates without a four-digit year are never compared** (UNDATED).
4. **(Safety, High) Name placement leaks.** "Holdings"/"Group" variants of a known party (SUFFIX), lone code-shaped
   names (CODE2), exchange parentheticals deleted unread (NOTE, ws_l #1 tier 0), title-case headlines (HEADLINE). ws_l #7.
5. **(Safety, High, new, held-out) VOCAB.** Landscape words, capitalised or not, become allowed; place adjectives are
   not places.
6. **(Medium)** OWNER-KEY2, ACQ-TWO, ACQ-PENDING (real rows have this wording), MINORITY.
7. **(Usefulness)** 13 of 17 real quotes and 32 of 43 clean cases blocked; a bare same-year date reads as 31 December;
   OWNER-KEY drops the Astellas owner (8/6/1 against B).
8. **(Low)** LBL-OWNER, LBL-DATE.
9. **(Judgement)** L8, L12, P20, H7, H8; rows with no quote pass unread.
10. **(Recall)** The rights file still caps recall (LM-302's and SKB315's returns).

## 8. The single highest-value next fix

Stop letting a word list decide that a quote restates its row. Eleven reviews show that every list holds a word that
can carry a holder, a reach or a condition. Instead, beside a clear position, a quote should pass only if each clause
matches one of a few fixed templates for its row type, read as a whole clause: subject = the row's own party (by
`_one_entity`, not `same_company`), verb = that row type's past or present verb (no modal, no "has", no negation),
object = rights to the program, optional place = inside the row's territory, optional date = a full date not after
the as-of date. Anything else (including press furniture the templates do not cover) blocks with the clause quoted,
and the analyst clears it with one recorded confirmation of the row. Fix `_MONTH_WORDS` ("may" only before a day or
year) and `_EXCHANGE_NOTE` (only "(Exchange: TICKER)") in the same change. This makes the top tier depend on a
template or a human, not on a vocabulary, and it should be cheap to test against the 17 real quotes.
