# Adversarial re-review 14: cycle R1 revision 15, rights evidence (CLDN18.2)

**AI-SIMULATED INTERNAL REVIEW.** I am an AI (Claude) playing a skeptical pharma BD analyst and auditor. I am not a
human reviewer. I approve nothing, and nothing here is validation. I did not trust REREVIEW13_RESPONSE.md. I checked
each claim by running code or reading outputs. I report only what I ran or read.

## Scope and method

- Revision 15 is commit 28535ea (HEAD of `dealscreen-mvp`). SHA-256 of all 37 files in `src/bve/dealscreen/` recorded
  at the start (`/tmp/claude-1000/rr15/sha_start.txt`) and at the end (`sha_end.txt`); see §10.
- All my scripts and outputs are in `/tmp/claude-1000/rr15/`. Harness `h15.py` and `a/lib15.py` are copies of the
  previous reviewer's `h14.py` and `lib14.py`. Per-program cases go through `screening.program_transaction`. Defaults
  as in REREVIEW11–13: company "Nerida Bio", program NB-7, buyer {US}, as-of 2025-06-01, max age 730 days,
  `encumbered_rights: deprioritize`. "C" = "Chinaco Pharma licenses NB-7 for mainland China"; "China license" =
  Nerida Bio → Chinaco Pharma, exclusive, mainland China, 2025-01-01. "DL" = "BOSTON, Mass., March 3, 2025
  /PRNewswire/ -- ". Every party is fictional; URLs are `example.test`.
- Revision 14 for comparison: `git archive 624b2f0 src/bve` unpacked into `/tmp/claude-1000/rr15/rev14/` and run with
  `PYTHONPATH` (no checkout, no git state change). Each of my probes ran on both revisions (`*_rev14.out`).
- New probes: `a/p15.py` (71 inputs), `a/p15b.py` (29), `a/p15c.py` (7), `a/cf15.py` (confirmation effects through a
  plain `confirmed_rows` dict; nothing recorded), `a/dbg_run.py` (masked clause, template text, places, verdict).
  End to end: `e2e/ws_p` = a copy of `~/.cache/rights_v1/fin15_ws` with the 17 transcribed CLDN18.2 rows plus my 8
  fictional rows Z11–Z18 (`e2e/rights_p.csv`). Previous probes were run in place with `python -B` (no file written
  in their folders); outputs in `prev/`.
- **Confirmations I recorded: none.** `conf/conf15.sh` made three HUMAN confirmation attempts (CLI in this shell, CLI
  with `env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT`, Python API) and one withdrawal attempt, on a scratch copy
  (`conf/ws_conf`); all four were refused. The scratch copy has no decision log. Confirmation effects were tested
  only by passing a dict to `program_transaction` (`a/cf15.py`), which writes nothing.

## Summary

- **The response's named fixes hold on the inputs they name.** Every REREVIEW13 attack it lists blocks. All 20
  earlier probe outputs (p10 … p14b, u10 … u14) are byte-identical to the implementer's `fin15/out`. ws_h2 … ws_o
  tier files are identical; ws_o has 0 top-tier programs. CLDN18.2 output is unchanged (CSV byte-identical to
  `after_v13`; `screening.json` byte-identical to the revision-14 screen; 0 of 62 science fields changed). The
  one-place rule held on every split and nested-exclusion input I wrote (RP1–RP9 block).
- **Each of three fixes fails on a close variant.**
  - *Partial retention through a comma.* "Nerida Bio retains U.S. rights to NB-7, for solid tumors" passes: the
    description folder removes ", for solid tumors" before the purpose check can see "P for". Tier 1.
  - *Elision without brackets.* A Unicode "…", "...", ". . ." or "{...}" is not an omission mark to the reader. "…
    rights to NB-7 in mainland China …" and "{...}" inside a grant pass. Tier 1.
  - *Payment-only on a co-promotion option row.* The rule covers LICENSE and OPTION only. Tier 1.
- **New in revision 15: the "Upon the termination," opener reads a contract condition as an event.** "Upon the
  termination, Nerida Bio regains U.S. rights to NB-7" and "Upon the expiration of the license agreement, Alpha Bio
  returns U.S. rights …" give RIGHTS_RETURNED, tier 1. The module's own docstring says there is no slot for "upon".
- **Older, first reported here: a quote that states nothing still passes.** A quote that is only an adviser line
  ("Goldman Sachs advised Nerida Bio on the transaction.") is stripped to nothing and passes; so does "Nerida Bio
  retains all other rights to NB-7" alone, which does not say what was granted or where. Revision 15 now blocks a
  payment-only quote for exactly that reason; these say even less.
- **Usefulness:** the dateline date now kept as "On <date>," pushes the first word of the body off position 0, so
  "DL + Under the terms of the agreement, …" and "DL + The license agreement grants …" now block (they passed in
  revision 14). The response does not disclose this cost. Real CLDN18.2 quotes: still 15 of 17 block directly, 4 of
  17 through the gate. Against general Claude the score is unchanged at 8 / 6 / 1 (B 14 / 1 / 0).

Definite new errors (not reported in REREVIEW13.md). None occurs in the CLDN18.2 output.

| Severity | Introduced by revision 15 | Claimed fixed, fails on a close variant | Older, first reported here | Total |
|---|---|---|---|---|
| High: tier 0 or 1 while a third party may hold buyer-territory rights, or on contrary evidence | 0 | 0 | 0 | **0** |
| Medium: wrong owner, a wider grant read as the row, a process hole, a quote that does not support the row | 1: UPON-COND | 2: RET-PARTIAL3, ELISION2 | 1: NOTHING-READ | **4** |
| Low: wording, unrealistic input, replay-only | 1: RESP-C4 (response text) | 1: PAYONLY-CPO | 1: FOOTNOTE | **3** |

I keep REREVIEW13's scale: it rated partial retention (RET-PARTIAL2) and elision (ELISION) Medium, so their close
variants are Medium here too. A reader who rates "a third party may hold U.S. rights for other indications" as High
would move RET-PARTIAL3 up. Judgement calls and usefulness costs are listed separately (§2h, §4) and not counted.

EOF
## 1. REREVIEW13_RESPONSE.md, claim by claim

| § | Claim | Verdict | Evidence (run or read) |
|---|---|---|---|
| 0 | The implementer recorded no confirmation for any measurement | **Unverifiable; consistent** | `~/.cache/rights_v1/fin15_ws` has no decision log; my re-screen of a copy is byte-identical to its `screening.json` |
| 1 | RET-PLACE2: a retention with more than one place blocks; RU1–RU5, RU18, RU19, ROW1 block | **Held** | `prev/p14.out`: all block. RU1 reason (`a/p15c.out` V4): "…names more than one place for the rights the company keeps (worldwide; excluding the US), so DealScreen cannot tell where it keeps them…" |
| 1 | One span still reads as one territory: UC44, "U.S. and the rest of the world", "outside mainland China" pass | **Held** | V7 (UC44), RC4, RC5 (`a/p15b.out`) tier 1 |
| 1 | I found no way to split one retention across clauses or hide an exclusion inside one span | **(my test) Held** | RP1 (nested exclusion in one span → "names a territory DealScreen cannot read"), RP2 ("worldwide ex-U.S." → keeps rights only in all-but-US), RP3/RP4/RP5/RP8 (the exclusion in a second clause), RP9 (exclusion before the subject): all block (`a/p15.out`) |
| 1 | RET-PARTIAL2: the retention object is plain "rights"; "rights to develop/commercialize", "market and sell" no longer match | **Held** | RU7, RU8, RU9 block with the `_KEEPS` reason (V3) |
| 1 | "U.S. rights to NB-7 for gastric cancer" blocks "whatever the case of the landscape's indication field", with "says the company keeps rights only for gastric cancer" | **Blocks: held. Reason: refuted for a title-case field** | Lower-case field: the purpose reason. Title-case field (V5): "says a party keeps rights in words DealScreen does not read …". Wording only |
| 1 | Partial retentions block | **Refuted on a close variant** | PU1 "C; Nerida Bio retains U.S. rights to NB-7, for solid tumors" → tier 1 (§2a, RET-PARTIAL3) |
| 1 | RET-REASON: an unread retention says so | **Held** | V3, RC7 ("will retain"): "says a party keeps rights in words DealScreen does not read …" |
| 1 | ELISION: "[...]", "[…]", "(...)", "[the Company]" block; EL1, EL2, EL4, EL7, ws_o BL-M05D1 block | **Held for brackets. Refuted for other omission marks** | EL1/2/4/7 block (`prev/p14.out`); V6 "[the Company]" blocks; EL12 "(…)" blocks. EL8 trailing "…", EL9 leading "...", EL10/EL11 "..." / ". . ." between clauses, EL13 "{...}" → tier 1 (§2c, ELISION2) |
| 2 | DATELINE-DATE: DT1 blocks "gives the date 2026-03-03, which may be after the as-of date" | **Held. Usefulness cost not disclosed** | V2: "…the clause 'On March 3, 2026, Alpha Bio terminated the US license with Nerida Bio', which gives the date 2026-03-03, which may be after the as-of date 2025-06-01…". DT10 blocks. Cost: UQ1, UQ7 (§4) |
| 2 | HEADLINE-1WORD: TAKEOVER, DIVESTITURE, TESSALY-CONTROLLED, NORTH ACQUIRES block; a one-word name passes | **Held (disclosed)** | DL10, DL15, DL16 block; V1 "NORTH ACQUIRES, U.S." blocks (on "names US", the dateline left in). CP3 "PURCHASED", CP4 "ASSIGNED", CP1 "NEW HOLDER", CP2 "NEW BUYER", CP9 "TESSALY'S" pass (§2e, judgement) |
| 2 | PAYONLY: a payment-only quote blocks unless the row covers the buyer territory; PY8, PY9, ws_o TORL block | **Held for LICENSE and OPTION. Refuted for CO_PROMOTION_OPTION** | PY8, PY9 block; PO8 (dateline + payment) blocks; PO6 (payment + adviser line) blocks. PO1 "Chinaco Pharma paid Nerida Bio $5 million" on a co-promotion option row → tier 1 (§2d) |
| 2 | "A payment beside a grant still passes" | **Held; but a payment beside a clause that grants nothing also passes** | PO2 "Chinaco Pharma paid Nerida Bio $20 million; Nerida Bio retains all other rights to NB-7" → tier 1 (§2d, NOTHING-READ) |
| 2 | UC41, UC42 pass beside a grant | **Held** | RC1, RC2 tier 1. Alone, both still block as payment-only (`prev/u14.out`); the response names only UC41 |
| 2 | UC43 "full rights" | **Held** | `prev/u14.out` UC43 tier 1; RC3 tier 1 |
| 2 | UC47 "responsible for" needs a place | **Held** | RS1 tier 1; RS4 (no place) blocks "grants rights or states an agreement without naming a place"; RS5 (adds the US) blocks |
| 2 | UC49–UC51: two-word city with a prefix passes | **Held** | `prev/u14.out` UC49–UC51 tier 1; CP10 tier 1 |
| 2 | UC54: "Following/After/Upon the termination ," may open an ending sentence | **Held, and unsafe** | UC54, FT1 tier 1; FT2/FT3/FT6/FT7 ("Upon the termination/expiration …", a contract condition) also tier 1 (§2b, UPON-COND) |
| 2 | C4: "Not changed: the agent check reads the variables in its list" | **Refuted (the code changed)** | `review.py:455` adds `AGENT_ENV_PREFIXES = ("CLAUDE_CODE_", "CODEX_", "CURSOR_AGENT", "GEMINI_CLI")` and `:462` tests them; the response's own Tests line names "the agent prefix". The table row is stale (RESP-C4, Low). The prefix check works: C2 is now refused (§3) |
| 2 | RU14, RU20, RT6, RT8–RT10 still pass (judgement) | **Held (disclosed)** | `prev/p14.out` RU14, RU20 TOP; p13 RT6, RT8–RT10 TOP |
| 2 | Tests: `test_rights_rereview13.py`; `test_rights_rereview12.py` clean list now puts payments after a grant | **Held** | 13 test functions in the new file. The rereview12 edit replaces three payment-only clean cases by "C; " + the same payment: it follows the new rule and loosens no safety expectation, but it removes the last test that a payment-only quote passes |
| 3 | `tests/dealscreen` 1,886 pass; ruff, mypy clean | **Held** | "1886 passed, 5 warnings in 135.29s"; ruff "All checks passed!"; mypy "Success: no issues found in 37 source files" |
| 3 | CLDN18.2: 0 of 62; JSON, CSV, memo byte-identical to revision 14 | **Held** | `compare.py` "AC8 scientific fields changed: 0 of 62"; `screening.json` `cmp`-identical to the revision-14 reviewer's screen (`rr14/e2e/cldn_ws`) and to `fin15_ws`; CSV `cmp`-identical to `fin15/out` and `after_v13`; memo identical without the generation line |
| 3 | Cycle-4 equivalence 4 of 4 | **Held** | 4 of 4 `byte_identical: true`, `fast_path: true` (`/tmp/claude-1000/rr15/equiv.json`); tracked file md5 `94450c24…` before and after |
| 3 | p14 15/57, p14b 2/11, ws_o 0; p13 11, p13b 2; p12 26/10/6/0; p10 0/75, p11 5/75; ws_h2 … ws_n unchanged | **Held** | All 20 probe outputs `cmp`-identical to `fin15/out`; tiers of ws_h2, i2, j2, l, m, n, o identical (top-tier counts 3, 2, 0, 0, 0, 0, 0) |
| 3a | What still reaches a top tier in p14/p14b is a control, a usefulness row or a disclosed judgement row | **Held** | p14 TOP: RU13, RU14, RU16, RU20, SG7, SG8, SG9, DT4, EL5, DL11, DL12, DL13, DL14, SB4, SB5; p14b TOP: RG7 (judgement) and RW1 (control) |
| 4 | Usefulness: u14 13/18, u13 4/8, u12 16/24, u10 6/43, real quotes 15 / 4 of 17 | **Held** | `prev/u14.out` 13 TOP; u13 4; u12 16; u10 "HELD BACK 37 of 43"; `e2e/real_quotes.out` "15 of 17" / "4 of 17" (= `fin15/out`) |
| 4 | PAYONLY costs 5 clean sentences | **Held as counted; incomplete** | UC41 and UC42 alone also block as payment-only (they blocked before for other reasons). The dateline-opener cost (UQ1, UQ7) is not listed |
| 5 | REREVIEW13 §6 stands | **Held** | No CLDN18.2 position changed (§6) |
| 6 | Costs 1–5 | **Held, with additions** | Add: the dateline-opener cost (§4), the comma-description retention, bare ellipses, the "upon" condition, nothing-read quotes (§2) |

## 2. Paths into the top tiers

Outputs copied from `a/p15.out`, `a/p15b.out`. `NOT_ENC/T1` = `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE /
NO_THIRD_PARTY_GRANT_IN_EVIDENCE holder=None owner='Nerida Bio'`, no blocker. `RET/T1` =
`RIGHTS_RETURNED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE holder='Nerida Bio' owner='Nerida Bio'`, no blocker.
"r14" says what revision 14 gave on the same input (`a/p15_rev14.out`).

### 2a. RET-PARTIAL3: a partial retention written as a comma description (Medium; claimed fixed: RET-PARTIAL2)

| Id | Quote (China license) | Output | r14 |
|---|---|---|---|
| PU1 | "C; Nerida Bio retains U.S. rights to NB-7, for solid tumors" | NOT_ENC/T1 | T1 |
| PU2 | "C; Nerida Bio retains U.S. rights to NB-7, in solid tumors" | NOT_ENC/T1 | T1 |
| PU3 | "C; Nerida Bio retains rights to NB-7, for solid tumors, in the United States" | NOT_ENC/T1 | T1 |
| PU4 | "C; Nerida Bio retains U.S. rights to NB-7, for first-line treatment" | NOT_ENC/T1 | T1 |
| PU5 | "C; Nerida Bio retains U.S. rights to NB-7, for gastric cancer" (field "gastric cancer") | NOT_ENC/T1 | T1 |
| PU8 | "C; Nerida Bio retains U.S. rights to NB-7, for patients with advanced solid tumors" | NOT_ENC/T1 | T1 |
| ws_p QLS31905 | Z11 "Chinaco Pharma licenses QLS31905 for mainland China; Qilu Pharmaceutical retains U.S. rights to QLS31905, for solid tumors" | memo "#1 QLS31905: no third-party grant in evidence; rights position: no grant over the buyer territory per evidence (recorded grants do not cover US; …)" | — |

Control: PU6, the same words without the comma, blocks: "…which says the company keeps rights only for solid
tumors, so another party may hold rights for other uses".

Cause, read in `a/dbg_run.py`: PU1's clause becomes `G retains R rights to P , for solid tumors`. `_DESCRIPTION`
(`rights_template.py:349`) folds "P , <up to 12 words>" when every word is a description word, and "for", "in",
"solid", "tumors", "first-line", "treatment", "patients", "advanced" are all in `DESCRIPTOR_WORDS` (`:206`), so the
template text is `G retains R rights to P`. The purpose check (`:641`) searches `slots.text` for "P for"; the comma
sits between "P" and "for", so it never matches. A BD analyst reads PU1 as "Nerida keeps U.S. rights only in solid
tumors"; someone else may hold U.S. rights in other indications. Realism: moderate ("retains U.S. rights to X, for
oncology indications" is common; here only words on the description list work, which covers most tumor wording).
Severity: Medium, as REREVIEW13 rated RET-PARTIAL2.

### 2b. UPON-COND: "Upon the termination," reads a contract condition as an event (Medium; introduced by revision 15)

| Id | Row | Quote | Output | r14 |
|---|---|---|---|---|
| FT2 | US license D1 + termination | "Upon the termination, Nerida Bio regains U.S. rights to NB-7" | RET/T1 | blocked |
| FT3 | same | "Upon the expiration of the license agreement, Alpha Bio returns U.S. rights to NB-7 to Nerida Bio" | RET/T1 | blocked |
| FT6 | US license + rights-returned row | "Upon the termination, Nerida Bio regains U.S. rights to NB-7" | RET/T1 | blocked |
| FT7 | US license + termination | "Upon the termination of the agreement, Nerida Bio regains U.S. rights to NB-7" | RET/T1 | blocked |
| FT5 | same | "After its termination, Nerida Bio regains U.S. rights to NB-7" ("its" names no deal) | RET/T1 | blocked |
| ws_p Spevatamig | Z15 US license + Z16 termination "Upon the termination, Phanes Therapeutics regains U.S. rights to Spevatamig" | memo "#6 Spevatamig (PT886): no third-party grant in evidence; rights position: rights returned per evidence (grant to Alpha Bio ended in US per source; …)" | — |

Controls: FT1 / UC54 ("Following the termination, …") pass, which is the intended use. FT4 ("…revert to …")
blocks.

Cause: `_endings` now prefixes every ending sentence with `(?:following|after|upon) (?:the|this|its)
(?:termination|expiration|end)(?: of (?:the|its) {deal})? , ` (`rights_template.py:435`, `:445`), and `_OPENERS`
lower-cases "Following", "After", "Upon" at the start (`:274-275`). The module docstring (`:16-18`) still says "There
is no slot for … a condition ("after", "following", "upon", "subject to")". "Upon termination, X regains rights" is the
standard way a signing release or a 10-K describes a contract term; it does not say the termination happened. The
quote is what checks a TERMINATION row; here it confirms only that the contract has such a clause. If the vendor
filed a contract term as a termination event (or the notice period has not run), the licensee still holds U.S. rights
and the program shows RIGHTS_RETURNED in tier 1. "After its termination" also lets "its" name a deal the row does not
show. Expected: block "upon"/"after its", or accept only "Following the termination of the license agreement with E".

### 2c. ELISION2: omission marks other than brackets (Medium; claimed fixed: ELISION)

| Id | Row | Quote | Output | r14 |
|---|---|---|---|---|
| EL8 | China license | "Nerida Bio granted Chinaco Pharma exclusive rights to NB-7 in mainland China …" | NOT_ENC/T1 | T1 |
| EL9 | China license | "... Chinaco Pharma licenses NB-7 for mainland China" | NOT_ENC/T1 | T1 |
| EL10 | China license | "C ... Chinaco Pharma will pay Nerida Bio $20 million upfront" | NOT_ENC/T1 | T1 |
| EL11 | China license | "C . . . Nerida Bio retains all other rights to NB-7" | NOT_ENC/T1 | T1 |
| EL13 | China license | "Nerida Bio granted Chinaco Pharma exclusive rights to NB-7 {...} in mainland China" | NOT_ENC/T1 | T1 |
| EL15 | US license + termination | "Alpha Bio terminated the U.S. license with Nerida Bio..." | RET/T1 | T1 |
| ws_p ATG-022 | Z12 | "Antengene Biologics granted Chinaco Pharma exclusive rights to ATG-022 in mainland China …" | memo "#2 ATG-022: no third-party grant in evidence" | — |
| ws_p SKB315 | Z18 | "Sichuan Kelun-Biotech Biopharmaceutical granted Chinaco Pharma exclusive rights to SKB315 {...} in mainland China" | memo "#5 SKB315: no third-party grant in evidence" | — |

Controls that block: EL1, EL2, EL4, EL7 (brackets, "(...)"), EL12 "(…)", EL14 ("<...>" in the middle, because the
first half has no place).

Cause: `_ELISION` (`rights_quote.py:303`) matches only "[", "]" and a parenthesised ellipsis. A bare "..." or "…"
(written "..." by `_TYPOGRAPHY`, `:51`) is a sentence end to `_SPLIT` (`rights_reader.py:73`, `\.(?=\s|$)`), so the
text on each side is read as a whole sentence and the omission vanishes; a trailing or leading ellipsis leaves an
empty clause, which is skipped (`rights_quote.py:339-341`). "{" and "}" are not tokens of `_WORD`
(`rights_template.py:271-272`), so EL13 reads as if the braces and their dots were not there, which is the original
ELISION path. The unbracketed ellipsis is the most common excerpt mark in vendor quote fields; EL8's missing tail may
be "and the United States". Expected: block any "...", "…", ". . ." or brace, as brackets now do.

### 2d. NOTHING-READ and PAYONLY-CPO: quotes that state no grant and no place

| Id | Row | Quote | Output | r14 | Severity |
|---|---|---|---|---|---|
| PO4 | China license | "Goldman Sachs advised Nerida Bio on the transaction." | NOT_ENC/T1 | T1 | Medium (older) |
| PO3 | China license | "Nerida Bio retains all other rights to NB-7" | NOT_ENC/T1 | T1 | Medium (older) |
| PO2 | China license | "Chinaco Pharma paid Nerida Bio $20 million; Nerida Bio retains all other rights to NB-7" | NOT_ENC/T1 | T1 | Medium (older) |
| PO12 | China option | "Nerida Bio retains all remaining rights to NB-7" | NOT_ENC/T1 | T1 | Medium (older) |
| PO9 | China option | "Chinaco Pharma paid Nerida Bio $5 million; Nerida Bio retains all remaining rights to NB-7" | NOT_ENC/T1 | T1 | Medium (older) |
| PO1 | China co-promotion option | "Chinaco Pharma paid Nerida Bio $5 million" | NOT_ENC/T1 | T1 | Low (claimed fixed: PAYONLY) |
| ws_p BL-M05D1 | Z14 China license | "Goldman Sachs advised Sichuan Baili Pharmaceutical on the transaction." | memo "#4 BL-M05D1: no third-party grant in evidence" | — | |
| ws_p JS107 | Z13 | "NingBo Junyan Hongshi Biosciences retains all other rights to JS107" | memo "#3 JS107: no third-party grant in evidence" | — | |
| ws_p TORL-2-307-ADC | Z17 co-promotion option | "Chinaco Pharma paid TORL Biotherapeutics $5 million" | memo "#7 TORL-2-307-ADC: no third-party grant in evidence" | — | |

Controls that block: PY8, PY9 (payment alone, license and option), PO6 (payment + adviser line), PO5 (exchange note
alone), PO7 (attribution alone), PO10, PO11 (a name alone).

Cause: `quote_problem` (`rights_quote.py:337-351`) skips a clause that masks to nothing and blocks a payment-only quote
only when `read_any and money_only`. PO4's only clause is removed whole by `_ADVISER` (`:116-119`), so nothing is
read and `read_any` stays False: the quote passes. A retention "all other/remaining rights" with no place passes
`_read_retention` (`rights_template.py:657`) and is not `money_only`, so a payment beside it passes too. PO1:
`_templates` adds the payment sentences to OPTION and CO_PROMOTION_OPTION (`:538`, `:554`), but `read_clause` marks
them `money_only` only for LICENSE and OPTION (`:681`), so on a co-promotion option they match an ordinary no-place
template. Revision 15 itself says a payment-only quote "states only payments between the parties, not which rights
were granted or where" and blocks it; PO2–PO4 and PO12 say even less about what was granted. A BD analyst reading
"retains all other rights" cannot tell whether the grant was China or the U.S. The row's own territory is still the
vendor field, so this is a quote that does not support the row, not a false holder (Medium).

### 2e. Low findings

| Id | Input | Output | Expected | Cause |
|---|---|---|---|---|
| FOOTNOTE | FN1 "C*"; FN3 "C #" | NOT_ENC/T1 each (r14 the same) | blocked: a footnote mark points to text not in the quote ("*excluding Hong Kong", "*and the U.S. under the option") | `_WORD` (`rights_template.py:271-272`) drops every ASCII character that is not a letter, digit, slot mark or comma; `_unreadable` (`rights_quote.py:288-299`) checks non-ASCII only. A dagger (FN2) blocks. The module docstring says "Every character is read" (`rights_quote.py:11`); ASCII punctuation is not |
| PAYONLY-CPO | PO1 (above) | NOT_ENC/T1 | blocked as PY9 | `rights_template.py:681` |
| RESP-C4 | REREVIEW13_RESPONSE §2 row C4 | "Not changed: the agent check reads the variables in its list" | "a prefix test was added" | the response row is stale; the code changed (`review.py:453-462`) |

### 2f. What held (selected)

RP1–RP9 (one place, splits, nested exclusions); RU1–RU5, RU7–RU10, RU18, RU19, ROW1; RC6 (two spans that both cover
the US block, the disclosed cost); RC7 ("will retain"); EL1, EL2, EL4, EL7, EL12, V6; DT1, DT10; DL10, DL15, DL16,
V1, CP5 ("SUBLICENSED"); PY8, PY9, PO5–PO8, PO10, PO11; RS4, RS5; FT4; FN2, FN4, FN5. OWNER-KEY2 and ACQ-TWO code is
unchanged since revision 14 (`git diff 624b2f0 28535ea -- src/bve/dealscreen/rights_ledger.py` is empty) and
`prev/p14b.out` AQ rows are byte-identical to `fin15/out`.

### 2g. Judgement calls (not counted)

- RS2 "Chinaco Pharma will be responsible for the manufacturing of NB-7 in mainland China" and RS3 ("regulatory
  activities") pass as licence sentences (new in revision 15; r14 blocked). A manufacturing role is not a licence,
  but the sentence names no other holder and no wider place.
- PU7 "retains U.S. rights to the subcutaneous NB-7" (a formulation) and PU9 "…, in oral" pass: a formulation-limited
  retention. Unrealistic wording; same cause as §2a.
- Dateline cities: CP1 "NEW HOLDER", CP2 "NEW BUYER", CP3 "PURCHASED", CP4 "ASSIGNED", CP8 "SAN SUCCESSOR", CP9
  "TESSALY'S" pass (`_DEAL_WORD`, `rights_quote.py:238-241`, lacks holder/buyer/purchas-/assign-/successor; CP3/CP4/CP9
  passed in revision 14 too). None can carry a holder and a place together, because "US", "China" etc. are in
  `_HOLD_WORDS`. Low realism.
- CF2 (`a/cf15.out`): a row confirmed as restating itself is never re-read, even when its quote says "Tessaly Pharma
  holds U.S. rights to NB-7" (tier 1) or dates the deal after the as-of date (CF1, tier 1). That is what a
  confirmation means; the memo still prints the quote. A human error is not caught.
- The agent check (C4 in §3): `CLAUDE_PID` and `CLAUDE_EFFORT` are not covered by the prefixes.
- Still disclosed and unchanged: RU14, RU20, RT6, RT8–RT10, SG8, EL5, SB4, SB5, RG7, DT4, DL11.

## 3. The confirmation (CONFIRM_RIGHTS_ROW)

Run by `conf/conf15.sh` on `conf/ws_conf` (a copy of my `e2e/ws_p`), subject `rx:d4a98078:6` (an LM-302 row).
Output: `conf/conf15.out`. Agent variables in this shell: `CLAUDECODE CLAUDE_CODE_CHILD_SESSION
CLAUDE_CODE_ENTRYPOINT CLAUDE_CODE_EXECPATH CLAUDE_CODE_MESSAGING_SOCKET CLAUDE_CODE_MESSAGING_TOKEN
CLAUDE_CODE_SESSION_ATTENDED CLAUDE_CODE_SESSION_ID CLAUDE_EFFORT CLAUDE_PID`.

| # | Input | Output (copied) | Verdict |
|---|---|---|---|
| C1 | CLI `decide … --new-state CONFIRMED --reviewer-kind HUMAN` in this shell | "REFUSED: this shell is run by an AI agent (CLAUDECODE is set); …" | held |
| C2 | same with `env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT` (REREVIEW13's C6 path, which recorded) | "REFUSED: this shell is run by an AI agent (CLAUDE_CODE_CHILD_SESSION is set); …" | held: REREVIEW13 C4/C6 closed by the prefix |
| C3 | Python `ws.decision_log().record(…, reviewer_kind=HUMAN, context=…)` | "REFUSED: this shell is run by an AI agent (CLAUDECODE is set) …" | held |
| C4 | `agent_shell(env)` with `CLAUDECODE` and every `CLAUDE_CODE_*` removed (no record attempted) | "agent_shell -> None \| still set: ['CLAUDE_EFFORT', 'CLAUDE_PID']" | limit (judgement): `CLAUDE_` is not a prefix (`review.py:455`) |
| C5 | `agent_shell` on single variables | `CLAUDE_CODE_X=''` → caught; `CODEX_HOME` → caught; `GEMINI_CLI_IDE_SERVER_PORT` → caught; `CLAUDE_PID` → None | as designed |
| C6 | WITHDRAWN with nothing recorded | "REFUSED: no confirmation of this row or an earlier version of it is recorded, so there is nothing to withdraw" | held |

The scratch copy ends with no decision log: no record was made.

What a confirmation binds to and what it does (read `rights_model.py:85-107`, `rights_gate.py:284-307`; run
`a/cf15.py` with a plain dict, no record): the key is a hash of external id, deal, related deal, type, parties,
territory as written, exclusivity, dates, status, URL and quote. Another program's row never shares it (CF3: the
hash differs when only the external id differs). A confirmed row is still read by the ledger and for party notes;
its quote is not read at all, so neither the as-of date (CF1: a quote dated 2026 at as-of 2025-06-01, tier 1) nor a
holder in the quote (CF2: "…; Tessaly Pharma holds U.S. rights to NB-7", tier 1) is checked. The reason line names
the confirmer and says DealScreen cannot verify the kind: "the quote on rights row 1 (license) was confirmed as
restating the row by TEST-DICT-NOT-A-RECORD, recorded as a human analyst (DealScreen cannot verify this; dec:test,
2026-11-10); it is not read again". The decision log is hash-chained but has no secret, so anyone who can write the
file can append a valid HUMAN line; nothing in DealScreen can stop that (disclosed since revision 13).

## 4. Over-caution and usefulness

These are usefulness costs, not safety errors.

| Measure | Result | Source |
|---|---|---|
| REREVIEW10's 43 clean cases | 6 pass (response: 6) | `prev/u10.out` "HELD BACK 37 of 43" |
| REREVIEW11's 24 | 16 pass (response: 16) | `prev/u12.out` |
| REREVIEW12's 8 | 4 pass (response: 4) | `prev/u13.out` |
| REREVIEW13's 18 | 13 pass (response: 13) | `prev/u14.out` |
| Real CLDN18.2 quotes, directly / through the gate | 15 of 17 / 4 of 17 block | `e2e/real_quotes.out` (= `fin15/out`) |
| My 16 realistic sentences (`a/p15b.py` UQ) | 9 pass; 2 newly held back by revision 15 (UQ1, UQ7); 2 newly passing (UQ5, UQ9); 1 held back by design (UQ10) | `a/p15b.out` vs `a/p15b_rev14.out` |

Clean cases held back (reviewer-written, fictional; each `RIGHTS_UNRESOLVED`):

| Id | Quote | r14 | Why it blocks |
|---|---|---|---|
| UQ1 | "DL Under the terms of the agreement, Chinaco Pharma will receive exclusive rights to develop and commercialize NB-7 in mainland China." | **passed** | "names Under, which is not a party to the row …": the kept date makes the clause "On March 3, 2025, Under the terms …", so "Under" is no longer at position 0 and is read as a name (`rights_quote.py:216`, `rights_template.py:333`). Without the dateline (UQ1n) it passes |
| UQ7 | "DL The license agreement grants Chinaco Pharma exclusive rights to NB-7 in mainland China." | **passed** | same cause ("names The"); UQ7n passes |
| UQ6 | "DL Following the termination, Nerida Bio regains U.S. rights to NB-7." | blocked | same cause ("Following" capitalised after "On <date>,") |
| UQ13 | "DL Today, Nerida Bio granted Chinaco Pharma exclusive rights …" | blocked | "names Today"; "today ," is no opener form |
| UQ14 | "DL Pursuant to the agreement, Chinaco Pharma obtains exclusive rights …" | blocked | "names Pursuant" |
| UQ8 | "Chinaco Pharma will be responsible for all development, manufacturing and commercialization activities for NB-7 in mainland China." | blocked | "activities for" is not in the new sentence |
| UQ10 | "Nerida Bio will receive $20 million upfront from Chinaco Pharma." | passed | payment-only (by design, disclosed) |
| RC6 | "C; Nerida Bio retains U.S. rights to NB-7 worldwide" | passed | two place spans (disclosed cost 2) |

Judgement: the response's usefulness counts are honest for the sets it measured. It omits one new cost: every press
release whose body starts with a capitalised opener after the dateline ("Under the terms…", "The agreement…",
"Following…") now blocks. That is a common release shape; the cause is mechanical (the inserted "On <date>," should
let the next word count as the first). The payment-only cost (5 listed, plus UC41/UC42 alone) is a defensible
trade, consistent with UNPLACED2. One analyst confirmation per row, kept across re-imports of an unchanged row,
remains a fair cost for a deal list of this size; with 15 of 17 real quotes needing one, the reader is still not
saving the analyst much reading.

## 5. Output honesty

In favour: no memo I produced (CLDN18.2, ws_p) calls a program available or open; the words occur only in the fixed
boilerplate ("availability must be evidenced", "one open gate"). No position, tier or action code appears in memo
prose (`grep -E "[A-Z]{3,}_[A-Z_]{3,}" e2e/memo_p.md` and `cldn_memo.md`: 0 hits). Every holder shown in ws_p is
cited. A confirmed row names its confirmer and says the kind cannot be verified (CF1). The CLI `rights_reading_note`,
`memo.py` and `workbook.py` are unchanged by revision 15 (`git diff --stat 624b2f0 28535ea` lists none of them).

| # | Where | Output (copied) | Problem | Cause |
|---|---|---|---|---|
| O9 | `e2e/memo_p.md` #6 Spevatamig | "rights returned per evidence (grant to Alpha Bio ended in US per source; …)" beside "Upon the termination, Phanes Therapeutics regains U.S. rights to Spevatamig" | the reason says the grant ended; the quote states a condition | UPON-COND |
| O10 | `memo_p.md` #1 QLS31905 | "no grant over the buyer territory per evidence" beside "…retains U.S. rights to QLS31905, for solid tumors" | the clean reason sits beside a partial retention | RET-PARTIAL3 |
| O11 | `memo_p.md` #2 ATG-022, #5 SKB315 | tier 1 beside "… in mainland China …" and "… {...} in mainland China" | an elided quote printed as evidence for a clear position | ELISION2 |
| O12 | `memo_p.md` #4 BL-M05D1 | tier 1; the only evidence quote is "Goldman Sachs advised Sichuan Baili Pharmaceutical on the transaction." | the cited "evidence" says nothing about rights | NOTHING-READ |
| O13 | workbook `e2e/ws_p.xlsx` Screening sheet | BL-M05D1 "NO_THIRD_PARTY_GRANT_IN_EVIDENCE … recorded grants do not cover US" | same as O12 (the workbook carries tier codes in its code column, by design) | NOTHING-READ |
| O4 | confirmed row reason | "…dec:test, 2026-11-10…" | an internal id in memo prose; harmless (unchanged) | `rights_gate.py:289-291` |

For the 7 ws_p top-tier programs I compared the memo line with `screening.json` and the workbook Screening row: tier, position and reason agree.

## 6. CLDN18.2 measured against the reference and B

| Item | Result |
|---|---|
| `after_transaction.csv` (62 programs), my HEAD re-screen of a copy of `fin15_ws` | `cmp`-identical to `fin15/out` and to `after_v13` |
| screening.json | `cmp`-identical to `fin15_ws` and to the revision-14 reviewer's screen (`rr14/e2e/cldn_ws`) |
| Memo | identical to `fin15/out/memo.md` without the generation line |
| Scientific fields (`compare.py`, frozen `baseline_ws/screening.json`) | **0 of 62** |
| Tiers | 44 RIGHTS_UNRESOLVED, 17 DEPRIORITIZED, 1 EXCLUDED_BY_BUYER_PREFERENCE; **0 top tier** |
| Positions | 49 NO_RIGHTS_EVIDENCE, 8 LICENSED, 2 RIGHTS_ROWS_NOT_APPLIED, 1 CONFLICTING, 1 OPTION_HELD, 1 SHARED |

Error classes against `reference_calls.csv`. No position or holder changed since revision 13, so these are
REREVIEW13's (I checked that nothing changed; I did not re-score each row):

| Class | Count | Programs |
|---|---|---|
| False unobstructed | **0** | — (no top tier) |
| False encumbrance | 0 definite; 2 likely outdated | EO-3021, SYSA1801 (reference "RETURNED_TO_ORIGINATOR_UNCLEAR"; tool: licensed, deprioritized) |
| Wrong holder | 1, labelled | LM-302 "Turning Point Therapeutics (recorded; conflicting)" |
| Wrong territory | 0 | — |
| Missed return | 2 | SKB315 (`NO_RIGHTS_EVIDENCE`; not in the rights file), LM-302 (conflicting) |
| Missed owner | 2 (not a false call) | Zolbetuximab, IMAB362 (`RIGHTS_ROWS_NOT_APPLIED`) |

Usefulness against general Claude (B) on REREVIEW.md's 15 deal programs: **DealScreen 8 right / 6 partial / 1
missed; B 14 / 1 / 0**. No advantage is shown.

## 7. Acceptance criteria

| AC | Verdict | Evidence |
|---|---|---|
| AC1 | PASS | ws_p "25 events, 0 rejected rows"; earlier workspaces' imports unchanged; provenance on every evidence line |
| AC2 | PARTIAL | CLDN18.2: no OPEN tier, nothing called available. Held-out: ws_p reaches tier 1 for 7 programs on quotes that do not support the row (§2) |
| AC3 | PARTIAL | Grant places, unplaced grants, two-place retentions and bracket elisions block. Not met: partial retention through a comma description (RET-PARTIAL3), unbracketed elisions (ELISION2), quotes that state no grant (NOTHING-READ) |
| AC4 | PARTIAL | RU5 and DT1 now block. Not met: "Upon the termination, … regains" (a condition) gives RETURNED tier 1 (UPON-COND; ws_p Spevatamig); "…terminated the U.S. license with Nerida Bio..." (EL15) passes; LM-302 still not RETURNED (data) |
| AC5 | PASS for the inputs I ran | Option rows unchanged; PY9 (payment-only option) blocks. Note PAYONLY-CPO (Low) on co-promotion options |
| AC6 | PASS for the inputs I ran | Ledger unchanged; p14b AQ rows identical to `fin15/out` |
| AC7 | PASS (age) | Staleness unchanged; the dateline date is now read (DT1, DT10 block). DT4 (wire form, no date) is disclosed |
| AC8 | PASS | 0 of 62; equivalence 4 of 4 byte-identical; JSON byte-identical to revision 14 |
| AC9 | PARTIAL | Preferences work. 15 of 17 real quotes still need a confirmation; the dateline-opener cost is new (UQ1, UQ7) |
| AC10 | PARTIAL | Every applied row is cited; a confirmed row names its confirmer. Not met: clean reasons beside quotes that state a condition, a partial retention, an elision or nothing (O9–O13) |
| AC11 | PARTIAL | Blocked rows ask a specific question; on the §2 paths the ask "Who holds US rights? Recorded deals cover other territories only" ignores what the quote leaves out |
| AC12 | PASS | 267 added lines of `git diff 624b2f0 28535ea -- src/` checked against 243 CLDN18.2 landscape and rights-file company and program names: no hit. The target symbol "CLDN18.2" appears once, in a U1 comment in `indication_relations.py` ("CLDN18.2 NEGATIVE"), which is a target, not a company or program (U1 scope) |
| AC13 | PARTIAL | IBI343, SHR-A1904 not unobstructed; RC148, FL-301, XNW27011 encumbered; LM-302 CONFLICTING, not returned |
| AC14 | FAIL | 4 new Medium and 3 Low errors on held-out inputs (§2); none in the CLDN18.2 output |

## 8. Remaining issues, ranked

1. **(Medium) ELISION2.** A bare "…", "...", ". . ." or "{...}" is not read as an omission: a trailing ellipsis after a
   grant, or one between two passing sentences, passes. This is the most common excerpt mark in vendor quote fields.
   End to end: ATG-022, SKB315 (ws_p).
2. **(Medium) UPON-COND (new).** "Upon the termination/expiration …, G regains / E returns …" reads a contract term as
   an event and gives RIGHTS_RETURNED tier 1; "After its termination" lets "its" name an unshown deal. End to end:
   Spevatamig (ws_p).
3. **(Medium) RET-PARTIAL3.** "retains U.S. rights to P, for solid tumors" passes because the description folder
   removes the purpose before the purpose check reads it. End to end: QLS31905 (ws_p).
4. **(Medium) NOTHING-READ.** A quote that masks to nothing (an adviser line) or says only "retains all other rights"
   passes, although it states neither the grant nor its place; revision 15 blocks a payment-only quote for that very
   reason. End to end: BL-M05D1, JS107 (ws_p).
5. **(Usefulness, new)** The kept dateline date makes every capitalised opener after a dateline a name ("Under the
   terms …", "The license agreement …", "Following the termination …"). Real quotes: 15 of 17 still need one analyst
   confirmation.
6. **(Low)** PAYONLY-CPO (co-promotion option rows), FOOTNOTE ("*", "#" dropped unread), the stale C4 row in the
   response, the purpose-reason wording for a title-case field, a decision id in memo prose.
7. **(Judgement)** "responsible for the manufacturing/regulatory activities" read as a licence; dateline city words
   such as HOLDER, BUYER, PURCHASED, ASSIGNED; `CLAUDE_PID`/`CLAUDE_EFFORT` not covered by the agent prefixes; a
   confirmed row is never re-read (date, holder); past retentions and business-word variants (disclosed).
8. **(Recall)** The rights file still caps recall (LM-302's and SKB315's returns); no real vendor export tested.

## 9. The single highest-value next fix

Make "nothing left out, nothing unread" one check that runs before the templates, in `rights_quote.quote_problem`:
block a quote that contains any omission or reference mark ("...", "…", ". . .", any bracket or brace, "*", "#"),
and block a quote in which no clause was read as a grant, a retention with a place, or an ending (an adviser line, a
bare "all other rights", a payment, on every row type). In the same change, read `_PURPOSE` on the clause before
`_DESCRIPTION` folds it (or refuse "for/in" inside a comma description of a retained program), and drop "upon" and
"its" from the new ending opener (keep "Following/After the termination of the license agreement"). These four
small changes close all four Medium paths in §2 and cost no clean case I found: none of the 16 realistic sentences,
the 18 of REREVIEW13 or the real CLDN18.2 quotes that pass uses an ellipsis, a brace, "upon", or a comma purpose.
Separately, let the word after an inserted "On <date>," count as the first word, to recover UQ1 and UQ7.

## 10. Checks

| Check | Result |
|---|---|
| `tests/dealscreen` at HEAD | 1,886 passed, 5 warnings (135.3 s) |
| `ruff check --no-cache src/bve/dealscreen src/bve/cli/dealscreen.py` | "All checks passed!" |
| `mypy src/bve/dealscreen/` (cache in `/tmp/claude-1000/rr15/mypy_cache`) | "Success: no issues found in 37 source files" |
| `compare.py` (frozen baseline) | "AC8 scientific fields changed: 0 of 62" |
| Cycle-4 equivalence (`rr12/run_equiv.py`, which does not write the tracked file) | 4 of 4 `byte_identical: true`, `fast_path: true`; tracked `cycle4/equivalence_result.json` md5 `94450c24dd45550248f008573c800843` before and after |
| Previous probes re-run (p10, p10b, av10, d10, d10b, rt10, u10, p11, q11, p12, p12b, p12c, p12d, u12, p13, p13b, u13, p14, p14b, u14) | all byte-identical to `fin15/out` |
| End to end (CLDN18.2, ws_h2, ws_i2, ws_j2, ws_l, ws_m, ws_n, ws_o) | tiers identical to `fin15/out`; CSV identical to `fin15/out` and `after_v13`; memo identical without the generation line; `real_quotes.out` identical |
| SHA-256 of the 37 files in `src/bve/dealscreen/` | start and end identical: no file changed during the review |
| Confirmations | none recorded; four attempts refused (§3) |
| Git | no commit, stash or checkout by me; the only new file from me is this report (the U1 reviewer's `REVIEW9.md` also appeared) |
