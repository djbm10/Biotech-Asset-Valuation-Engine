# Adversarial re-review 11: cycle R1 revision 12, rights evidence (CLDN18.2)

**AI-SIMULATED INTERNAL REVIEW.** I am an AI (Claude) playing a skeptical pharma BD analyst and auditor. I am not a
human reviewer. I approve nothing, and nothing here is validation. I did not trust REREVIEW10_RESPONSE.md. I checked
each claim by running code or reading outputs. I report only what I ran or read.

Scope and method:
- Revision 12 is commit 55ac585 (HEAD). I recorded the SHA-256 of all 37 files in `src/bve/dealscreen/` at the start
  (`/tmp/claude-1000/rr12/sha_start.txt`) and at the end (`sha_end.txt`); see §10. I edited nothing except this file.
  No commit, stash or git change.
- All my scripts and outputs are in `/tmp/claude-1000/rr12/`. Harness `h12.py` is the previous reviewer's `h11.py`
  plus a `confirmed_rows` argument. Per-program cases go through `screening.program_transaction`. Defaults as in
  REREVIEW10: company "Nerida Bio", program NB-7, buyer {US}, as-of 2025-06-01, max age 730 days,
  `encumbered_rights: deprioritize`. "China license" = Nerida Bio → Chinaco Pharma, exclusive, mainland China,
  2025-01-01. "US license D1" = Nerida Bio → Alpha Bio, United States, 2024-03-01, ended by a termination linked to D1
  dated 2025-01-15. "Acquisition" = Omega Holdings acquires Nerida Bio, Worldwide, 2025-02-01, beside the China
  license. Every party is fictional; URLs are `example.test`.
- New probes: `a/p12.py` (93 inputs), `a/p12b.py` (32: lapses with a clean option row, present tense, condition
  words, acquisition options), `a/p12c.py` (13: OWNER-KEY2, ACQ-TWO), `a/p12d.py` (6: non-Latin text), `a/u12.py`
  (24 realistic clean press sentences), `a/c12.py` (confirmation through the harness), `a/dbg.py` (prints the masked
  clause, the slots and the folded text). "Rev 11" columns come from running the same scripts with `git archive
  7a62efd` first on the path (`a/run_rev11.py`, outputs `*_rev11.out`).
- End to end: copies of `~/.cache/rights_v1/fin12_ws` (C3 buyer, as-of 2026-10-29). `e2e/ws_h2`, `ws_i2`, `ws_j2`,
  `ws_l` re-run the previous reviewer's rights files. `e2e/ws_m` = the 17 transcribed CLDN18.2 rows plus my 8
  fictional rows Z01–Z08 (`e2e/rights_m.csv`). `e2e/ws_conf` = a copy of `ws_i2` for the confirmation tests.

## Summary

- **The templates closed every REREVIEW10 path I re-ran.** The previous reviewer's 75 probes give 5 top-tier
  results, all controls or usefulness cases; my re-runs of `p11`, `q11`, `p10`, `p10b`, `av10`, `d10`, `d10b`, `rt10`,
  `u10` are byte-identical to the implementer's `fin12/out`. The four end-to-end workspaces give the same tiers and
  the same memos as the implementer's. CLDN18.2 output equals `after_v12` and changes no position.
- **But the quote reader still has a second door that is a word pattern.** Before the templates, each clause is
  offered to the old plain-form reader (`rights_allow.plain_form`), one clause at a time. That reader treats "it",
  "we" and "the company" as the program's company whenever the text it sees has one clause, which is always true
  here. So "Chinaco Pharma licenses NB-7 for mainland China; it holds all rights in the U.S." is tier 1, and so is
  "Alpha Bio terminated the U.S. license with Nerida Bio; it retains all rights". The same door uses `same_company`,
  so "Nerida Bio Holdings retains all rights in the U.S." passes although revision 12 says Holdings is another entity.
- **Text that is not ASCII letters or digits is not read at all.** A Chinese clause after a full-width comma ("，美国权利
  由第三方持有": U.S. rights held by a third party) is dropped, and the English template beside it passes.
- **Revision 12 opened two template paths.** "an option to acquire NB-7" and "exercised its option to acquire NB-7"
  have no place slot requirement, so a China-only option row reaches tier 1 with a quote that gives a third party an
  option over the whole program. A grant with no place ("acquired the rights to NB-7", "the sole rights to develop,
  manufacture and commercialize SKB315") reads as the row's China grant, although "all rights" is blocked for exactly
  that reason. A termination quote about "the option agreement" ends a license.
- **The anchored strips still take a headline.** A dateline's "place parts" are any capitalised words, and an
  all-capitals headline on the line above the city is read as the city.
- **Confirmation works as coded and is hash-bound, but "HUMAN only" is a default label.** `decide` records
  `reviewer_kind=HUMAN` unless told otherwise. I am an AI; I recorded a confirmation without the flag and the block
  cleared. The implementer's own end-to-end demonstration did the same: decision `dec:00003` by "jdoe" (HUMAN) with
  the rationale "test: the option is mainland China only", on the row "Chinaco Pharma licenses China rights and also
  receives an exclusive option" (an attack row). Any change to the rights file voids every confirmation silently,
  because the event id holds the file hash: "one confirmation per row" is one per row per import.
- **End to end:** in `ws_m`, 7 programs reach tier 1 through these paths (QLS31905, ATG-022, JS107, BL-M05D1, SKB315,
  Spevatamig, TORL-2-307-ADC). CLDN18.2 itself has 0 top-tier programs.
- **Usefulness:** the response's numbers hold (3 of 43 clean cases; 16 of 17 real quotes block when read directly;
  4 of 17 through the gate). Of my 23 realistic clean sentences, 11 pass. Against general Claude the score is
  unchanged at 8/6/1 (B 14/1/0): no advantage is shown.

Definite new errors (not reported in REREVIEW10.md). None occurs in the CLDN18.2 output.

| Severity | Introduced by revision 12 | Claimed fixed, fails on a close variant | Older, first reported here | Total |
|---|---|---|---|---|
| High: tier 0 or 1 while a third party may hold buyer-territory rights, or on contrary or conditioned evidence | 1: ACQ-OPT | 3: SUFFIX2, HEADLINE2, VOCAB2 | 2: PF-PRONOUN, NONLATIN | **6** |
| Medium: wrong owner, a wider grant read as the row, a wrong deal, a low-realism strip, a process hole | 3: UNPLACED, DEAL-KIND, CONFIRM-KIND | 0 | 2: STRIP-CAPS, OWNER-THE | **5** |
| Low: wording, a silent loss of confirmations; no tier change toward the top | 2: CONFIRM-REIMPORT, MEMO-CODE | 0 | 0 | **2** |

Judgement calls and usefulness costs are listed separately (§2j, §4) and not counted. PF-PRONOUN also defeats an older fix: review R1v6 PF2 ("we" and "it" only in a one-clause text).

## 1. REREVIEW10_RESPONSE.md, claim by claim

| § | Claim | Verdict | Evidence (run or read) |
|---|---|---|---|
| 1 | `rights_vocab` (the word lists) is deleted | **Held as stated. Misleading as a safety property** | The file is gone (`git diff --stat`). But `rights_quote.py:186` still passes any clause that `rights_allow.plain_form` reads as "rights kept by the company" or "no grant stated", and that reader is a word pattern with pronoun and `same_company` rules (PF-PRONOUN, SUFFIX2). `descriptor_words` filters field words with `_FUNCTION_WORDS`, a word list (VOCAB2) |
| 1 | Each clause of every applied row's quote must match a template for the row's type | **Held for clauses that reach the templates. Refuted for the clause set** | Clauses that the plain-form reader accepts never reach `read_clause` (PF1–PF15). Words outside `[A-Za-z0-9]` never become slots (NONLATIN). A clause emptied by a strip is skipped (`rights_quote.py:189`; STRIP-CAPS) |
| 1 | A party is masked only as the same legal entity; Holdings/Group/International never absorbed (SUFFIX) | **Held in the template path. Refuted in the plain-form path** | Template: M2, M5 block ("may be different companies"). Plain form: PF7 "Nerida Bio Holdings retains all rights in the U.S.", PF8 "Nerida Bio International owns the rights in the US", PF12 "Nerida Bio Global …" are tier 1 |
| 1 | The program masked first; an initials acronym counts only once defined (CODE2) | **Held** | REREVIEW10 E18/L15 block (`prev/p11.out`); M3 (a defined acronym reused for a third party) blocks |
| 1 | A description folds only when every word is a description word; a field cannot add a connective, a place or a rights word (VOCAB) | **Held for "from", "outside", "rights". Refuted for conditions and holder words** | "after", "following", "co-owned", "jointly-owned", "licensee" from a field become description words: QC1, QC3–QC5, Q5, Q6, Q9 tier 1 (VOCAB2). I found none of these in the 62 CLDN18.2 programs' fields |
| 1 | Verbs per type; no modal, no holding "has", no "not" outside lapses, no sale, no condition | **Held inside the templates** | LP1–LP6 block when the option row's quote is a template (`a/p12b.out`); PT4 "acquires" blocks; E3, E4, A1–A7 block (`prev/p11.out`). Note: REREVIEW10's own LP probes block on the option row's quote ("Alpha Bio receives an option on U.S. rights to NB-7" is no template), not on the lapse quote; LP0 control blocks too. I re-ran them with a template option row |
| 1 | A place must lie inside the row's territory; "all" only when the row covers the buyer territory (WIDER4) | **Held for named places and "all". Refuted for an unplaced grant** | R1, R3, R4, R8–R10 block. But the place slot is optional, so "the rights to NB-7", "the sole rights to develop, manufacture and commercialize NB-7" and "an option to acquire NB-7" read as the row's own China grant (UNPLACED, ACQ-OPT) |
| 1 | A date needs a year; "may" never a month; a period passes if it ends by the as-of date or holds the row's own date (MAY, UNDATED) | **Held** | E10–E15, E20 block; D6, D8 block; E22, E23 pass. Judgement: D1 "effective 2025" passes by the row-date rule (§2j) |
| 1 | No notice sentence (NOTICE) | **Held** | E16, E17 block; UC23 "The termination … is effective January 15, 2025" also blocks (usefulness) |
| 1 | Only datelines, "(EXCHANGE: TICKER)", attributions, advisers and bylines anchored to a known party are removed (HEADLINE, NOTE) | **Held for NOTE and for REREVIEW10's L18. Refuted for close variants** | L16, L17 block. HD1 "BOSTON, Tessaly Holds Rights, March 3, 2026 -- …", HD3 "TESSALY HOLDS RIGHTS⏎BOSTON, March 3, 2025 -- …" are tier 1 (HEADLINE2). HD6–HD8: the adviser, byline and attribution names are any capitalised words (STRIP-CAPS) |
| 1 | A title-case headline is read with template words lower-cased; other capitals stay names | **Held** | I found no template-word company name that fills a party slot; "May", "Will" in a headline block |
| 1 | Confirmation: HUMAN only, refused from AI-prepared or synthetic reviewers, for unknown events, without context | **Held as code. Refuted as "No AI can clear a block"** | C1 AI_PREPARED refused; C2 SYNTHETIC_FIXTURE refused; C3 unknown event refused; C3b state REJECTED refused. C4: the CLI default is HUMAN (`cli/dealscreen.py:382`); I recorded `dec:00001` as "rr12-ai-reviewer" with no flag and TORL went to tier 1. The implementer's demo log `scratchpad/r12/cli_ws/decisions.jsonl` holds `dec:00003 jdoe HUMAN … "test: the option is mainland China only"` (CONFIRM-KIND) |
| 1 | The record stores `row_sha256`; if the row changed the block says "a confirmation was recorded for an earlier version" | **Held at unit level. Unreachable through import** | `a/c12.py` C-b: a stale hash shows the sentence. But the event id is `rx:<file sha[:8]>:<row>` (`rights.py:275`): any edit to the file changes every event id, so the old record is never found and the sentence never appears (C6, C8). The safety direction holds: a changed row is never confirmed |
| 1 | OWNER-KEY2 | **Held** | O1–O3 block; AT3 blocks. Older gap: "The Nerida Bio" acquired gives owner "Nerida Bio" at tier 1 (OWNER-THE) |
| 1 | ACQ-TWO: two acquirers make both rows contested | **Held** | O4, AT1, AT2, AT6, AT7, AT8 blocked with "who owns it is not established". The position stays `NOT_ENCUMBERED…` with owner "Nerida Bio", not `CONFLICTING` (judgement, §2j) |
| 1 | LBL-OWNER, LBL-DATE wording | **Held** | `after_v11` vs `after_v12` differ only in those two rows' reasons (diff above in §6) |
| 2 | The findings table (LOWER2 … L14) | **Held for every listed input** | All REREVIEW10 attack inputs block (`prev/p11.out`, my p12b re-run of LP1–LP6). Close variants in §2 |
| 2 | 31 close variants block, 38 clean restatements pass; 156 tests | **Held for the test file** | `test_rights_rereview10.py`: 156 passed |
| 3 | `tests/dealscreen` 1,575 pass; ruff, mypy clean | **Held** | I re-ran: `tests/dealscreen` 1,575 passed (235 s); `ruff check --no-cache` "All checks passed!"; mypy (cache in my directory) "Success: no issues found in 38 source files" |
| 3 | CLDN18.2: 0 of 62 science fields changed | **Held** | `compare.py` on my HEAD re-screen of `after8_ws`: "AC8 scientific fields changed: 0 of 62" |
| 3 | CLDN18.2 transaction: 2 of 62 rows differ from `after_v11`, wording only; 0 top tier | **Held** | My re-screen's CSV is byte-identical to `after_v12/after_transaction.csv`; screens in the JSON identical; memo identical; `diff after_v11 after_v12` shows only Zolbetuximab and IMAB362 |
| 3 | Cross-version 0 of 312; cycle-4 equivalence byte-identical 4 of 4 | **Held** | My cross-version re-run: 0 of 312 assets differ against both `xv11f` and `xv12f`. Equivalence: 4 of 4 `byte_identical: true` (§10) |
| 3 | `rr11/a/p11.py` 5 of 75, all controls or usefulness; rr10 probes 0/0/0 | **Held** | byte-identical re-runs |
| 3 | ws_l 0, ws_j2 0, ws_h2 3, ws_i2 2, each a clean control | **Held** | `e2e/tiers_*.txt` identical to `fin12/out`; memos identical |
| 3 | Confirmation end to end on ws_i2 | **Held as run. The row chosen is an attack row** | The confirmed quote says Chinaco "also receives an exclusive option" with no scope; the demo confirms it as "mainland China only". This shows the risk the response lists as cost 3 |
| 3 | Usefulness: 3 of 43; 4 of 17 through the gate; 16 of 17 directly | **Held** | `prev/u10.out` 3; `real_quotes.out` byte-identical |
| 3 | Breakdown of the 16 real blocks | **Mostly held; one reason wrong** | Row 12 (givastomig) does not block on "joint partnership": the reader marks "global" in "global partnership" as a place and reads "excluding Greater China and South Korea" after "worldwide rights," as its own place, then says the quote "names CN/HK/KR/MO/TW, which the row's own territory … does not cover", although the quote restates the row's territory (`a/dbg.py`) |
| 3 | Earlier clean cases that now block (REV12_BLOCKED) | **Held** | 15 cases, listed in the test; plus test edits: rereview2 H7 reversed (Holdings is another entity), rereview9 UA1 input changed from "will acquire" to "acquired" so it still passes |
| 4 | Costs 1–8 | **Held, and cost 1 is larger** | Confirmations do not survive a re-import (CONFIRM-REIMPORT): one confirmation per row per refresh |

## 2. Paths into the top tiers

All outputs copied from `a/p12.out`, `a/p12b.out`, `a/p12d.out`, `a/p12c.out` unless stated. "blk: (none)" means
`top_tier_blockers` is empty. Abbreviations in the output column: `NOT_ENC/T1` = `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE
/ NO_THIRD_PARTY_GRANT_IN_EVIDENCE holder=None owner='Nerida Bio'`, blk: (none); `RET/T1` = `RIGHTS_RETURNED_PER_EVIDENCE
/ NO_THIRD_PARTY_GRANT_IN_EVIDENCE holder='Nerida Bio' owner='Nerida Bio'`, blk: (none). Expected in every row of §2a–2g:
blocked, naming the clause.

### 2a. PF-PRONOUN: a clause read as a plain form, one clause at a time (High; older, first reported here)

| Id | Row | Quote | Output | Rev 11 |
|---|---|---|---|---|
| PF1 | China license | "Chinaco Pharma licenses NB-7 for mainland China; it holds all rights in the U.S." | NOT_ENC/T1 | T1 |
| PF2 | China license | "Chinaco Pharma obtained rights to NB-7 in mainland China from Nerida Bio; it holds the rights in the US" | NOT_ENC/T1 | T1 |
| PF3 | China license | "…; we own all rights in the United States" (the licensee's own press release) | NOT_ENC/T1 | T1 |
| PF4 | D1 termination | "Alpha Bio terminated the U.S. license with Nerida Bio; it retains all rights" | RET/T1 | T1 |
| PF5 | D1 termination | "…; the company retains all rights in the U.S." | RET/T1 | T1 |
| PF6 | China license | "…; the company holds all rights in the U.S." | NOT_ENC/T1 | T1 |
| PF10 | D1 termination | "…; rights retained by it" | RET/T1 | T1 |
| PF13 | China license | "…; it keeps all rights in the US and rest of world" | NOT_ENC/T1 | T1 |
| PF15 | China license | "…; owned by it" | NOT_ENC/T1 | T1 |
| LP9 / LP10 | lapse (clean option row) | "Alpha Bio let its option to NB-7 lapse; it retains all rights" / "the option on the U.S. rights to NB-7 lapsed; the company holds the rights in the US" | NOT_ENC/T1 | T1 |
| ws_m QLS31905 | Z01 | "Chinaco Pharma licenses QLS31905 for mainland China; it holds all rights in the U.S." | memo "#1 QLS31905: no third-party grant in evidence; rights position: no grant over the buyer territory per evidence" | — |
| ws_m Spevatamig | Z02 + Z03 | "Alpha Bio terminated the U.S. license with Phanes Therapeutics; it retains all rights" | memo "#6 Spevatamig (PT886): no third-party grant in evidence; rights position: rights returned per evidence" | — |
| ws_m ATG-022 | Z08 | "Chinaco Pharma licenses ATG-022 for mainland China; the company holds all rights in the U.S." | memo "#2 ATG-022: no third-party grant in evidence" | — |

In each, "it", "we" or "the company" most naturally means the party named just before it (the licensee), or is
ambiguous. Cause: `quote_problem` offers every clause to `plain_form` first and skips the templates when it answers
"rights kept by the company" or "no grant stated" (`rights_quote.py:185-187`). `plain_form` treats "we"/"it" as the
company when its text has one clause (`rights_allow.py:162-163`, `:249` `len(clauses) == 1`), and a single clause is
always one clause. "the company" is the company in any text (`rights_allow.py:47`, `:164`). `_RETAINS` accepts
"holds", "owns", "keeps" and "the US" (`rights_allow.py:82-85`). The PF2 rule ("we" and "it" only in a one-clause
text, review R1v6) is defeated by the per-clause call.

### 2b. SUFFIX2: Holdings, International, Global in the plain-form path (High; claimed fixed: SUFFIX)

| Id | Quote (China license) | Output |
|---|---|---|
| PF7 | "Chinaco Pharma licenses NB-7 for mainland China; Nerida Bio Holdings retains all rights in the U.S." | NOT_ENC/T1 |
| PF8 | "…; Nerida Bio International owns the rights in the US" | NOT_ENC/T1 |
| PF12 | "…; Nerida Bio Global holds all rights in the U.S." | NOT_ENC/T1 |
| ws_m TORL-2-307-ADC | Z06 "Chinaco Pharma licenses TORL-2-307-ADC for mainland China; TORL Biotherapeutics Holdings retains all rights in the U.S." | memo "#7 TORL-2-307-ADC: no third-party grant in evidence" |

The response says "Holdings", "Group", "International" are other entities, and the template path agrees (M2, M5
block). Cause: `_is_company` uses `same_company` (`rights_allow.py:164`), whose `party_key` drops "holdings" and
"group" (`rights_territory.py:126-128`) and whose `GENERIC_NAME_WORDS` absorbs "international", "global", "us",
"china" (`rights_territory.py:146-150`).

### 2c. NONLATIN: text outside ASCII letters and digits is not read (High; older, first reported here)

| Id | Row | Quote | Output | Rev 11 |
|---|---|---|---|---|
| NL1 | China license | "Chinaco Pharma licenses NB-7 for mainland China，美国权利由第三方持有" ("U.S. rights are held by a third party") | NOT_ENC/T1 | T1 |
| NL2 | China license | "…。美国权利已授予第三方。" ("U.S. rights have been granted to a third party") | NOT_ENC/T1 | T1 |
| NL3 | China license | "… ＴＥＳＳＡＬＹ ＨＯＬＤＳ ＵＳ ＲＩＧＨＴＳ" (full-width letters) | NOT_ENC/T1 | T1 |
| NL5 | D1 termination | "Alpha Bio returns U.S. rights to NB-7 to Nerida Bio，但阿尔法保留美国商业化权利" ("but Alpha keeps U.S. commercialization rights") | RET/T1 | T1 |
| NL4 (control) | China license | "…; 美国权利由第三方持有" (after an ASCII semicolon) | blocked: "has the clause '美国权利由第三方持有', which is not one of the sentences …" | — |

Cause: the slot tokenizer `_WORD` only starts a token at `[A-Za-z0-9]` (`rights_template.py:212-213`), so CJK and
full-width text produce no token and vanish from the clause. `_SPLIT` (`rights_reader.py:73`) splits on ASCII ";",
"." and "!" only, so "，", "。" and "；" keep the foreign text inside the English clause. Realism: CLDN18.2 is mostly
Chinese originators; bilingual quotes from HKEX or Chinese-language releases are plausible in a real export.

### 2d. HEADLINE2 and STRIP-CAPS: the anchored strips (HEADLINE2 High, claimed fixed; STRIP-CAPS Medium, older)

| Id | Quote (China license) | Output | Rev 11 |
|---|---|---|---|
| HD1 | "BOSTON, Tessaly Holds Rights, March 3, 2025 -- Chinaco Pharma licenses NB-7 for mainland China" | NOT_ENC/T1 | T1 |
| HD2 | "BOSTON, Tessaly Pharma Holds, All U.S. Rights, March 3, 2025 -- …" | NOT_ENC/T1 | T1 |
| HD3 | "TESSALY HOLDS RIGHTS⏎BOSTON, March 3, 2025 -- …" (an all-capitals headline on the line above the dateline) | NOT_ENC/T1 | T1 |
| HD4 | "TESSALY HOLDS US RIGHTS, March 3, 2025 -- …" | NOT_ENC/T1 | T1 |
| ws_m BL-M05D1 | Z05 "BOSTON, Tessaly Holds Rights, March 3, 2026 -- Chinaco Pharma licenses BL-M05D1 for mainland China" | memo "#4 BL-M05D1: no third-party grant in evidence" | — |
| HD6 (STRIP-CAPS) | "Chinaco Pharma licenses NB-7 for mainland China. Tessaly Holds US Rights advised Nerida Bio" | NOT_ENC/T1 | T1 |
| HD7 (STRIP-CAPS) | "…, Tessaly Holds US Rights has learned" | NOT_ENC/T1 | T1 |
| HD8 (STRIP-CAPS) | "…, said Tessaly Holds-US-Rights, Chief Executive Officer of Nerida Bio" | NOT_ENC/T1 | T1 |

`a/dbg.py` shows the stripped text: for HD1 and HD3 only "Chinaco Pharma licenses NB-7 for mainland China" is read;
HD6's second clause becomes empty and is skipped. Causes: `_CITY` is up to four capitalised tokens joined by `\s+`,
which spans a line break, and `_REGION_PART` is any one to three capitalised words, up to two of them, never checked
as places (`rights_quote.py:59-60`, `:65-68`). The adviser, byline and attribution patterns take any `_CAPS` run as
the name (`rights_quote.py:70`, `:77`, `:80-83`, `:92`), and an emptied clause is skipped (`:189-190`). HD3 is the
realistic one: an all-capitals headline of two or three words above the city. HD6–HD8 are unnatural sentences;
I count them as Medium for low realism.

### 2e. ACQ-OPT and UNPLACED: a place-free object reads as the row's place (ACQ-OPT High, UNPLACED Medium; both introduced)

| Id | Row | Quote | Output | Rev 11 |
|---|---|---|---|---|
| AO1 | option, Chinaco Pharma, mainland China | "Nerida Bio granted Chinaco Pharma an option to acquire NB-7" | NOT_ENC/T1 | blocked |
| AO2 | same | "Chinaco Pharma obtained an exclusive option to acquire NB-7 from Nerida Bio" | NOT_ENC/T1 | blocked |
| AO3 | option + exercise, mainland China | "Chinaco Pharma exercised its option to acquire NB-7" | NOT_ENC/T1 | blocked |
| ws_m JS107 | Z04 option, mainland China | "NingBo Junyan Hongshi Biosciences granted Chinaco Pharma an option to acquire JS107" | memo "#3 JS107: no third-party grant in evidence" | — |
| UN1 | China license | "Chinaco Pharma acquired the rights to NB-7 from Nerida Bio" | NOT_ENC/T1 | blocked |
| UN6 | China license | "Chinaco Pharma obtained the sole rights to develop, manufacture and commercialize NB-7" | NOT_ENC/T1 | blocked |
| UN2 | China license | "Nerida Bio granted Chinaco Pharma the exclusive rights to NB-7" | NOT_ENC/T1 | T1 |
| ws_m SKB315 | Z07 | "Chinaco Pharma obtained the sole rights to develop, manufacture and commercialize SKB315 from Sichuan Kelun-Biotech Biopharmaceutical" | memo "#5 SKB315: no third-party grant in evidence" | — |

An option to acquire a program, or its exercise, is an option over the program in every territory, including the
buyer's; the row says mainland China. "the sole rights to develop, manufacture and commercialize NB-7" with no place
reads, to a BD analyst, as worldwide rights; revision 12 blocks "all rights" on a China row for exactly that reason
(WIDER4) but accepts the same claim without the word "all". Expected: blocked, or the place required in these
sentences. Causes: `what` allows "option to … acquire … P" (`rights_template.py:416-417`) and the exercise template
"exercised its option to … acquire … P" (`:430-431`); `_RIGHTS_TO` accepts "the rights to" with no place (`:334`) and
`_PLACE` is optional in every frame (`:328`, `:347-350`). UNPLACED is Medium because the row's own territory field is
explicit; ACQ-OPT is High because "acquire" names the whole program.

### 2f. VOCAB2: condition and holder words from the program's own fields (High; claimed fixed: VOCAB; held-out only)

Field text passed as `program_text`: indication "gastric cancer following two prior lines of therapy, after
progression" (QC), or the mechanism shown.

| Id | Row | Quote | Field | Output | Control without the field |
|---|---|---|---|---|---|
| QC1 | D1 termination | "Alpha Bio returns U.S. rights to NB-7, after phase 3, to Nerida Bio" | indication | RET/T1 | QC1c blocked |
| QC3 | D1 termination | "Nerida Bio regains U.S. rights to NB-7, after phase 3" | indication | RET/T1 | — |
| QC4 | D1 termination | "Alpha Bio terminates the U.S. license for NB-7, after progression" | indication | RET/T1 | — |
| QC5 | D1 termination | "Alpha Bio returns U.S. rights to the after phase 3 NB-7 to Nerida Bio" | indication | RET/T1 | — |
| Q5 | China license | "Nerida Bio licensed NB-7, a co-owned antibody, for mainland China to Chinaco Pharma" | "co-owned antibody" | NOT_ENC/T1 | — |
| Q6 | China license | "…, a jointly-owned antibody, …" | "jointly-owned antibody" | NOT_ENC/T1 | — |
| Q9 | China license | "…, the licensee product, …" | "licensee product antibody" | NOT_ENC/T1 | — |

The present tense with "after phase 3" is REREVIEW10's HEDGE4 E3 in description position. Cause: `descriptor_words`
keeps every lower-case field word except `_FUNCTION_WORDS` and template words (`rights_template.py:185-189`); the
filter is a word list (`:192-197`) without "after", "following", "prior", "co-owned", "licensee". `_DESCRIPTION`,
`_BEFORE` and `_PURPOSE` then fold them (`:283-287`, `:315-317`). Realism: none of the 62 CLDN18.2 programs has such
a word in its description fields (I listed all 20 non-standard description words; none is a condition or holder
word). Indication fields that say "after prior therapy" or "following progression" are common in other landscapes.

### 2g. DEAL-KIND: an ending of another deal ends the license (Medium; introduced)

| Id | Termination quote (row ends license D1) | Output | Rev 11 |
|---|---|---|---|
| X5 | "Nerida Bio terminated the option agreement with Alpha Bio" | RET/T1 | blocked |
| X4 | "Nerida Bio and Alpha Bio terminated their co-development agreement" | RET/T1 | blocked |

The quote ends a deal of another kind; the license may still be in force. Cause: `_endings` accepts any of
"license, collaboration, option, co-development, partnership" whatever the related grant's type
(`rights_template.py:359-360`).

### 2h. OWNER-THE: the owner stays with the acquired company (Medium; older, first reported here)

| Id | Input | Output (copied) | Expected |
|---|---|---|---|
| OK3 | China license; acquisition "Omega Holdings acquired The Nerida Bio" (grantor "The Nerida Bio") | `OWNER_ACQUIRED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE <<< TOP holder='Nerida Bio' owner='Nerida Bio'`, reason "Omega Holdings acquired The Nerida Bio (the company or its rights to this program) per source" | owner Omega Holdings, or blocked |

Rev 11 gives the same. Cause: the acquired party is matched with `_one_entity`, which drops "the"
(`rights_ledger.py:105-106`), but the succession map is keyed by `party_key`, which keeps it (`:257`, `:270-272`), so
the owner chain from "Nerida Bio" never finds Omega. The position says "owner acquired" and names the old owner.

### 2i. What held (selected)

LP1–LP6 (lapse quotes that deny the lapse), PT4 ("acquires"), R1/R3/R4/R8/R9/R10 (wider or unknown places), M2/M5
(variant names), M3 (a defined acronym reused), D3/D4/D6/D8 (later or unread dates), Q3/Q4 (field words "partnered",
"sublicensed"), AT1–AT8 (two acquirers; one written two ways), O1–O3 (OWNER-KEY2), HD9 (a quote attributed to the
licensee's officer) all block.

### 2j. Judgement calls (not counted)

- PF9 / PF14 "Chinaco Pharma licenses NB-7 for mainland China; US rights: undisclosed" / "…: TBD": read as "no grant
  stated", tier 1. "undisclosed" may mean a U.S. deal with undisclosed terms.
- PT1 / PT2 "Alpha Bio terminates the U.S. license with Nerida Bio" (present tense) passes, while "Omega Holdings
  acquires Nerida Bio" blocks because "a pending deal reads the same". A termination announcement in the present tense
  is often a notice with a later effective date.
- D1 "Alpha Bio terminated the U.S. license with Nerida Bio effective 2025" passes by the row-date rule (row
  2025-01-15, as-of 2025-06-01); the effective date may fall after June.
- X6 / X7 partial-scope returns (H7, H8, disclosed); UN8 / UN10 a quote that is only "rights to NB-7"; X2 / X3 "Chinaco
  Pharma has licensed NB-7" (in or out?); UN5 / M1 a second, unplaced license to the same licensee.
- ACQ-TWO: the position stays `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE` with owner "Nerida Bio" beside a blocker that
  says two parties acquired Nerida Bio; AC6 would call this CONFLICTING.
- A confirmation is bound to the row, not to the buyer territory or as-of date the analyst answered for; the hash
  leaves out `related_deal_id` and `external_id` (`rights_model.py:88-89`). Through import these cannot change without
  the event id changing (read, not run).

## 3. The confirmation (CONFIRM_RIGHTS_ROW)

Run on `e2e/ws_conf` (a copy of ws_i2; TORL-2-307-ADC row 28 blocks: "Chinaco Pharma licenses China rights and also
receives an exclusive option … is not one of the sentences DealScreen reads as restating the row").

| # | Input | Output (copied) | Verdict |
|---|---|---|---|
| C1 | `decide --action CONFIRM_RIGHTS_ROW --subject rx:9d396ce9:28 --new-state CONFIRMED --reviewer-kind AI_PREPARED` | "REFUSED: an AI-prepared record cannot CONFIRM_RIGHTS_ROW: evidence is confirmed or rejected only by a human analyst" | held |
| C2 | same, `--reviewer-kind SYNTHETIC_FIXTURE` | "REFUSED: a rights row is confirmed only by a human analyst who has read the source" | held |
| C3 | `--subject rx:deadbeef:28` | "REFUSED: unknown rights row 'rx:deadbeef:28'; the block on the program names its event id" | held |
| C3b | `--new-state REJECTED` | "REFUSED: a rights row confirmation has new_state CONFIRMED or WITHDRAWN" | held |
| C4 | same as C1 with no `--reviewer-kind`, `--reviewer rr12-ai-reviewer` (I am an AI) | "recorded dec:00001: CONFIRM_RIGHTS_ROW rx:9d396ce9:28 UNCONFIRMED -> CONFIRMED"; after `screen`: TORL `NO_THIRD_PARTY_GRANT_IN_EVIDENCE`, blockers `[]` | **CONFIRM-KIND** |
| C5 | `--new-state WITHDRAWN` | block returns, tier `RIGHTS_UNRESOLVED` | held |
| C6 | re-confirm, then re-import the same file with one unrelated row appended | event id becomes `rx:ffae0067:28`; block returns with no mention of the earlier confirmation | **CONFIRM-REIMPORT** (fail closed) |
| C7 | re-import the original file | event id `rx:9d396ce9:28` again; tier 1 again (the old confirmation re-applies) | held (same bytes) |
| C8 | re-import with row 28's quote changed to "…; Tessaly Pharma holds U.S. rights" | blocked ("names US, which the row's own territory (CN) does not cover"); no "earlier version" note | held for safety; the promised note never appears |
| C-a | harness, matching hash, quote "…; Tessaly Pharma holds U.S. rights" | tier 1, reason "the quote on rights row 1 (license) was confirmed as restating the row by jroe (dec:00009, 2026-11-07); it is not read again" | by design: nothing reads a confirmed quote |
| C-b | harness, stale hash | blocked, "… (a confirmation was recorded for an earlier version of this row)" | held |
| C-c | harness, the confirmation keyed to another event id | blocked | held: no leak across rows |

Findings:

- **CONFIRM-KIND (Medium; process).** Only the kind label decides. `decide` defaults to HUMAN
  (`cli/dealscreen.py:382`), `DecisionLog.record` defaults to HUMAN (`review.py:223`),
  and `_apply` trusts the stored kind (`review.py:174-176`). The hash chain has no key (`review.py:135`), so it shows
  edits, not authorship. An AI agent with a shell clears any block by omitting one flag. The implementer's own
  demonstration did so: `scratchpad/r12/cli_ws/decisions.jsonl` holds `dec:00003 jdoe HUMAN CONFIRM_RIGHTS_ROW
  rx:9d396ce9:28 CONFIRMED "test: the option is mainland China only"`. That row is a REREVIEW9 attack row: its quote
  gives Chinaco an exclusive option with no stated territory, and nothing in the source says "mainland China only".
  The response's "No AI can clear a block" is a policy, not a property. The response does disclose that there is no
  identity check on `--reviewer` (cost 3).
- **What a confirmation binds to.** Holds: the event id and the row hash; it never applies to another row (C-c) or
  to a changed row (C8, C-b); a withdrawal works (C5). Outputs name the confirmer and the decision (memo
  "confirmed as restating the row by rr12-ai-reviewer (dec:00001, 2026-11-07); it is not read again"; the Screening
  sheet carries the same text). They do not say the confirmer's kind.
- **CONFIRM-REIMPORT (Low; introduced).** The event id is `rx:<rights-file sha256[:8]>:<row>` (`rights.py:275`), and
  the confirmation is looked up by event id (`rights_gate.py:284`). Any change to the file, even an added row for
  another program, orphans every confirmation silently. `rights_model.py:84-85` says "the row number, dataset version … are not [hashed]: a re-import of the
  same row keeps its confirmation"; but `event_id`, which holds the file hash and the row number, is the lookup key
  and is itself the first hashed field (`:86`). It holds only for a byte-identical file. The "earlier version of this row" note
  (`rights_gate.py:295`) cannot be reached through `import-rights`. This fails closed, so it is a usefulness cost and a
  wording error, not a safety error. It makes the response's "one confirmation per real rights row" one per row per
  vendor refresh.
- **A confirmed row is read for nothing else.** Party notes (`_read_names`) and holders from the landscape still
  apply. The quote itself is never read again, so a mistaken confirmation (as in the demo) hides the quote's content
  from the tier. The memo still prints the quote verbatim beside the program.

## 4. Over-caution and usefulness

These are usefulness costs, not safety errors.

| Measure | Result | Source |
|---|---|---|
| Previous reviewer's 43 clean cases (`rr10/a/u10.py`) | 3 pass (response: 3) | `prev/u10.out` |
| Real CLDN18.2 quotes, each row alone through the gate | 4 of 17 block (all 4 rows that give a clear position alone) | `real_quotes.out` (byte-identical to the implementer's) |
| Real CLDN18.2 quotes read directly | 16 of 17 block | same |
| My 23 realistic clean press sentences (`a/u12.py`; UC22 "will return" is a correct block, not counted) | 11 pass, 12 blocked | `a/u12.out` |

Clean cases held back (reviewer-written, fictional; each `RIGHTS_UNRESOLVED` with the clause quoted):

| Id | Quote | Why it blocks |
|---|---|---|
| UC1 | "Nerida Bio and Chinaco Pharma today announced an exclusive license agreement for NB-7 in Greater China" | no "announced an … agreement" template |
| UC2 | "Under the terms of the agreement, Chinaco Pharma will receive exclusive rights to develop and commercialize NB-7 in mainland China" | "will"; the standard signing-day sentence (real row 15 has this shape) |
| UC4 | "Nerida Bio will receive an upfront payment of $20 million" | "will" |
| UC6 | "Nerida Bio retains all rights to NB-7 outside mainland China" | "outside mainland China" is wider than the China row |
| UC13 | "Chinaco Pharma will be responsible for development and commercialization of NB-7 in mainland China" | "will" |
| UC16 | "Nerida Bio Inc. (Nasdaq: NRDA) today announced that it has regained worldwide rights to NB-7 from Alpha Bio" | "worldwide" on a U.S.-only termination row |
| UC18 | "Chinaco Pharma paid $20 million upfront for rights to NB-7 in mainland China" | no "paid" template |
| UC19 | "Nerida Bio licensed NB-7 to Chinaco Pharma for mainland China for $20 million upfront and up to $200 million in milestones" | the place comes before the amount; `_MONEY_TAIL` must follow the party directly |
| UC20 | "Chinaco Pharma gains exclusive rights to NB-7 in mainland China, while Nerida Bio retains rights in the rest of the world" | "rest of the world" alone is an unreadable territory |
| UC21 | "U.S. rights to NB-7 revert to Nerida Bio" | present "revert" has no template ("reverted" has) |
| UC23 | "The termination of the U.S. license with Alpha Bio is effective January 15, 2025" | no template |
| UC7 | "Nerida Bio regained global rights to NB-7 following Alpha Bio's decision to terminate the agreement" | "following" |

Real-quote breakdown: I agree with the response's grouping except row 12 (givastomig), which blocks on a place
misread, not on "joint partnership" (§1). Row 16 ("… is currently in a Phase 1 clinical trial in cancer patients in
China") and rows 9/10 (China co-promotion beside an ex-China option) are reasonable blocks.

Judgement on the response's usefulness claims: the counts are honest. "About one confirmation per real rights row" is
not the real cost: confirmations are lost at every re-import (CONFIRM-REIMPORT), and two of the most common deal
sentences (UC1 announced agreement; UC2 "will receive" on signing day) never pass. A BD analyst would confirm nearly
every row by hand on every refresh. Meanwhile the paths in §2 pass without any confirmation. The template design moves
the trust to a human but leaves two unread doors (plain forms, non-Latin text).

## 5. Output honesty

In favour: no CLDN18.2 or ws_m output calls a program available or open as a rights tier. The memo prose carries no
position or tier code (`grep` of `cldn_memo.md`, `e2e/memo_m.md`). Every holder shown in ws_m is cited. Each
top-tier program's memo entry quotes its row verbatim, so a careful reader sees "it holds all rights in the U.S."
beside "no third-party grant in evidence"; the tier contradicts the quote it prints.

| # | Where | Output (copied) | Problem | Cause |
|---|---|---|---|---|
| MEMO-CODE (Low, introduced) | `e2e/memo_conf.md` lines 29, 37, 41 | "… a human analyst who has read the source can record CONFIRM_RIGHTS_ROW for event rx:9d396…" | an action code and an internal event id in memo prose | the gate's question text (`rights_gate.py:297-299`) is copied into the memo's "ask" lines |
| — | `e2e/memo_conf.md` line 19 | "the quote on rights row 28 (license) was confirmed as restating the row by rr12-ai-reviewer (dec:00001, 2026-11-07)" | says who confirmed (good); does not say the reviewer kind | `rights_gate.py:287-289` |
| — | ws_m memo #6 Spevatamig | "rights returned per evidence (grant to Alpha Bio ended in US per source; …)" beside the quote "…; it retains all rights" | reason contradicts the quote it cites (PF-PRONOUN) | §2a |

The CLI `rights_reading_note` (`cli/dealscreen.py:105-131`) is unchanged by revision 12 and speaks only for asserted
availability text via `accepted_form`; it says nothing about rights-row confirmations. No contradiction found.

## 6. CLDN18.2 measured against the reference and B

| Item | Revision 11 | Revision 12 |
|---|---|---|
| `after_transaction.csv` (62 programs) | — | my HEAD re-screen of a copy of `after8_ws` is byte-identical to `after_v12/after_transaction.csv`; it differs from `after_v11` only in the reasons of Zolbetuximab and IMAB362 (LBL-OWNER, LBL-DATE wording) |
| Memo, screens in the JSON | — | identical to `after_v12/memo_R1v12.md` and `screening_R1v12.json` (generation stamps ignored) |
| Scientific fields vs frozen baseline (`compare.py`) | 0 of 62 | **0 of 62** ("AC8 scientific fields changed: 0 of 62") |
| Tiers | 44 / 17 / 1, 0 top tier | 44 RIGHTS_UNRESOLVED, 17 DEPRIORITIZED, 1 EXCLUDED_BY_BUYER_PREFERENCE; **0 top tier** |

Error classes against `reference_calls.csv`, re-read for the 18 programs with rights evidence or a reference deal.
No position changed from revision 11, so the classes are REREVIEW10's:

| Class | Count | Programs |
|---|---|---|
| False unobstructed | **0** | — |
| False encumbrance | 0 definite; 2 likely outdated | EO-3021, SYSA1801 (reference "RETURNED_TO_ORIGINATOR_UNCLEAR"; tool: licensed to Elevation Oncology, deprioritized) |
| Wrong holder | 1, labelled | LM-302 "Turning Point Therapeutics (recorded; conflicting)" (reference: returned by BMS) |
| Wrong territory | 0 | — |
| Missed return | 2 | SKB315 (`NO_RIGHTS_EVIDENCE`; the return is not in the frozen library), LM-302 (conflicting) |
| Missed owner | 2 (not a false call) | Zolbetuximab, IMAB362 show no owner; reference "Astellas (owns 100% via Ganymed acquisition)" |

Programs the reference gives to large pharma without a rights row (Sonesitatug vedotin, ASP546C) read
`NO_RIGHTS_EVIDENCE` and are deprioritized by sponsor. Usefulness against general Claude (B), REREVIEW.md's 15 deal
programs: unchanged, **DealScreen 8 right / 6 partial / 1 missed; B 14 / 1 / 0**. I re-checked that no position or
holder changed; I did not re-score the other 13 rows. No advantage is shown.

## 7. Acceptance criteria

| AC | Verdict | Evidence |
|---|---|---|
| AC1 | PASS | ws_h2/i2/j2/l/m: "N events, 0 rejected rows"; provenance in every evidence line |
| AC2 | PARTIAL | CLDN18.2: no OPEN tier; nothing called available. Held-out: ws_m reaches tier 1 for 7 programs whose quotes say a third party holds or may hold U.S. rights (§2) |
| AC3 | PARTIAL | Rights-file territories parse; named wider places in quotes block. Not met: unplaced grants and acquisition options read as the row's territory (UNPLACED, ACQ-OPT); "it/the company holds U.S. rights" read as the company (PF-PRONOUN); non-Latin text unread (NONLATIN) |
| AC4 | PARTIAL | REREVIEW10's ending inputs block. Not met: "…; it retains all rights" (PF4), a termination of "the option agreement" ends a license (DEAL-KIND), "after phase 3" via field words (VOCAB2); LM-302 still not RETURNED (data) |
| AC5 | PASS for the inputs I ran | LP1–LP6 block with a clean option row; LP7, LP8, LP11 clean lapses pass. Option exercise "to acquire NB-7" is read as a China license (ACQ-OPT; counted under AC3) |
| AC6 | PARTIAL | ACQ-TWO now blocks both acquirers, but the position is not CONFLICTING (judgement); OWNER-THE shows the old owner after an acquisition |
| AC7 | PASS | Dates without a year never pass; a bare same year holding the row date passes (E22, E23); later dates block (D3, D6, D8) |
| AC8 | PASS | `compare.py` 0 of 62; HEAD re-screen identical to `after_v12`; cycle-4 equivalence re-run: `byte_identical: true`, `fast_path: true` 4 of 4 (`/tmp/claude-1000/rr12/equiv.json`; the tracked result file's md5 unchanged); cross-version: §10 |
| AC9 | PARTIAL | Preferences work. Most real phrasings are held back (§4), and confirmations are lost at each re-import |
| AC10 | PARTIAL | Every applied row is cited beside a clear position; a confirmed row names its confirmer. Not met: OWNER-THE (owner shown is not the acquirer); memo tier lines contradict the quotes they print (§5) |
| AC11 | PARTIAL | Blocked rows ask a specific question with the event id; the §2 paths ask nothing about the holder in the quote |
| AC12 | PASS | `git diff 7a62efd 55ac585 -- src/` adds no CLDN18.2 company or program name (grep of added lines; below §7) |
| AC13 | PARTIAL | IBI343, SHR-A1904 not unobstructed; RC148, FL-301, XNW27011 encumbered; LM-302 CONFLICTING, not returned |
| AC14 | FAIL | 6 new High errors on held-out inputs (§2); none in the CLDN18.2 output |

AC12 detail: I grepped the 752 added lines of `git diff 7a62efd 55ac585 -- src/` for 95 company, licensee, licensor
and program names from the CLDN18.2 landscape and rights file; the only hit is "China", a place.

## 8. Remaining issues, ranked

1. **(Safety, High) PF-PRONOUN and SUFFIX2: the plain-form door.** Every clause is first offered to `plain_form`,
   which reads "it", "we", "the company" and "<company> Holdings/International/Global" as the program's company.
   Tier 1 beside "it holds all rights in the U.S." End to end: QLS31905, ATG-022, Spevatamig, TORL-2-307-ADC.
2. **(Safety, High) NONLATIN.** Chinese and full-width text is invisible to the template reader; "，"/"。" keep it in
   the English clause. Plausible in a China-heavy landscape.
3. **(Safety, High, introduced) ACQ-OPT**, and (Medium) **UNPLACED**: "option to acquire NB-7", "exercised its option
   to acquire NB-7", "the sole rights to develop, manufacture and commercialize NB-7" read as the row's China grant.
   End to end: JS107, SKB315.
4. **(Safety, High) HEADLINE2**: an all-capitals headline above the city, or capitalised "place parts", is stripped as
   a dateline. End to end: BL-M05D1. (Medium) STRIP-CAPS for advisers, bylines, attributions.
5. **(Safety, High, held-out) VOCAB2**: "after", "following", "co-owned", "licensee" from a field fold into a
   description.
6. **(Process, Medium) CONFIRM-KIND**: HUMAN is the default kind; an AI can clear any block by omitting a flag, and
   the implementer's own demo confirmed an attack row.
7. **(Medium) DEAL-KIND, OWNER-THE.**
8. **(Usefulness)** 16 of 17 real quotes and 40 of 43 earlier clean cases need a confirmation; 12 of my 23 realistic
   clean sentences block, including "announced an exclusive license agreement" and "will receive exclusive rights";
   confirmations are lost at each re-import (CONFIRM-REIMPORT); row 12 blocks on a place misread.
9. **(Low)** MEMO-CODE; the "earlier version" note is unreachable; the `_CONFIRMED_FIELDS` comment is wrong.
10. **(Judgement)** PF9/PF14 placeholders; present-tense endings; "effective 2025"; partial-scope returns; ACQ-TWO not
    CONFLICTING; rows with no quote pass unread (REREVIEW10 §2l, unchanged).
11. **(Recall)** The rights file still caps recall (LM-302's and SKB315's returns).

## 9. The single highest-value next fix

Make the template reader the only reader of a rights row's quote, and make it read every character. Concretely:
in `quote_problem`, stop passing clauses to `plain_form` (or allow only a "rights kept by <party named by mask as the
grantor>" template inside `rights_template`, with no pronoun and no `same_company`); and make any clause that contains
a character `_WORD` cannot tokenise (anything outside ASCII letters, digits and listed punctuation) block with the
clause quoted. In the same change, require a place slot in the option-to-acquire and exercise templates and in the
unplaced "rights to P" objects, or block them. This closes the four highest-ranked paths with one rule: nothing in a
quote is skipped, and nothing but a fixed sentence passes. Separately, key confirmations by the row hash rather than
the file-hash event id so they survive a re-import of unchanged rows, and record the reviewer kind in the memo line.

## 10. Checks

| Check | Result |
|---|---|
| `tests/dealscreen` at HEAD | 1,575 passed, 5 warnings (234.6 s) |
| `ruff check --no-cache src/bve/dealscreen src/bve/cli/dealscreen.py` | "All checks passed!" |
| `mypy` (cache in `/tmp/claude-1000/rr12/mypy_cache`) | "Success: no issues found in 38 source files" |
| `compare.py` (frozen baseline `baseline_ws/screening.json`) | "AC8 scientific fields changed: 0 of 62" |
| Cycle-4 equivalence (`run_equiv.py`, which does not write the tracked file) | 4 of 4 `byte_identical: true`, `fast_path: true`; tracked `cycle4/equivalence_result.json` md5 identical before and after |
| `test_rights_rereview10.py` | 156 passed |
| Cross-version (`cross_version.py`: synthetic_200, fcrn_v1, fcrn_v2, c5_heldout) | 312 assets; disposition, rank, decisions and machine recommendation differ for 0 of 312 against both `xv11f` and `xv12f` (`/tmp/claude-1000/rr12/xv/science.json`). This run went from 13:14 to 13:18 on 2026-11-08, so it overlapped the `diagnostics.py` change below; it still matched both references |
| SHA-256 of `src/bve/dealscreen/*.py` | **Final check (`sha_end2.txt`): two U1 files changed during my review, not by me: `diagnostics.py` and `indication_relations.py`, both rewritten again at 2026-11-08 13:18:48 (`git diff --stat` now +103/−19 over the two). No rights file changed. First check (`sha_end.txt`):** one file changed, `diagnostics.py` (U1 unknown-gate diagnostics), mtime 2026-11-08 13:15:45, `git diff` +26/−10 lines (`_NEGATED`, `_NEGATION_WORDS`, `_BOTH_STATES`, `_SECOND_STATE`, `_DASHES`; review U1 R6). Every rights result in this report was produced before that time (probes 2026-11-07 16:39–16:59, end to end 16:52–16:54, equivalence 17:10, pytest finished 2026-11-08 13:12). No rights file (`rights*.py`, `review.py`, `transaction.py`, `screening.py`) changed. The other 36 hashes are identical to `sha_start.txt` |
