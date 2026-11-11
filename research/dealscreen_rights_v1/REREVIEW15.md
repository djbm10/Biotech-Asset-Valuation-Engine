# Adversarial re-review 15: cycle R1 revision 16, rights evidence (CLDN18.2)

**AI-SIMULATED INTERNAL REVIEW.** I am an AI (Claude) playing a skeptical pharma BD analyst and auditor. I am not a
human reviewer. I approve nothing, and nothing here is validation. I did not trust REREVIEW14_RESPONSE.md. I checked
each claim by running code or reading outputs. I report only what I ran or read.

## Scope and method

- Revision 16 is commit f1a310d (HEAD of `dealscreen-mvp`). I recorded the SHA-256 of all 37 files in
  `src/bve/dealscreen/` at the start (`/tmp/claude-1000/rr16/sha_start.txt`) and at the end (`sha_end.txt`). See §10.
- My scripts and outputs are in `/tmp/claude-1000/rr16/`. Harness `h16.py` and `a/lib16.py` are copies of
  `rr15/h15.py` and `rr15/a/lib15.py`; only the path changed. Per-program cases go through
  `screening.program_transaction`.
- Defaults are as in REREVIEW11–14: company "Nerida Bio", program NB-7, buyer {US}, as-of 2025-06-01, max age 730
  days, `encumbered_rights: deprioritize`.
- Shorthand. "C" = "Chinaco Pharma licenses NB-7 for mainland China". "China license" = Nerida Bio → Chinaco Pharma,
  exclusive, mainland China, 2025-01-01. "DL" = "BOSTON, Mass., March 3, 2025 /PRNewswire/ -- ". "US term" = a US
  license from Nerida Bio to Alpha Bio (D1) plus a termination row.
- Every party in my attack inputs is fictional, and the URLs are `example.test`. End to end, my rows had to attach to
  CLDN18.2 programs, so they use the landscape company as grantor (as REREVIEW14 did) and a fictional licensee.
- Revision 15 for comparison: `git archive 28535ea src/bve` unpacked into `rr16/rev15/` and run with `PYTHONPATH`. I
  made no checkout and no git change. Each new probe ran on both revisions (`a/*_rev15.out`).
- New probes:
  - `a/p16.py`: 67 inputs;
  - `a/p16b.py`: 10 inputs (partial endings);
  - `a/dbg16.py`: masked clause, template text, places and verdict.
- End to end: `e2e/ws_q` is a copy of `~/.cache/rights_v1/fin16_ws` with the 17 transcribed CLDN18.2 rows plus my 5
  fictional rows Z21–Z25 (`e2e/rights_q.csv`). Script: `e2e/run_e2e.sh`.
- Previous probes (rr10 … rr15) were re-run in place with `python -B`, so no file was written in their folders.
  Outputs are in `prev/`.
- **Confirmations I recorded: none.** §3 lists every attempt; each was refused, and no decision log exists in the
  scratch copy.

## Summary

- **The response's named fixes hold on the inputs they name.**
  - Every REREVIEW14 attack it lists now blocks: PU1–PU5, PU8, PO1–PO4, PO9, PO12, FT2, FT3, FT5–FT7, EL8–EL11, EL13,
    EL15, FN1 and FN3.
  - All 24 earlier probe outputs (p10 … p15c, u10 … u14, cf15) are byte-identical to the implementer's `fin16/out`.
  - The tier files of ws_h2 … ws_p are identical too, and ws_p now has 0 top-tier programs.
  - CLDN18.2 output: the CSV is byte-identical to `after_v13`. `screening.json` differs from the revision-15 screen
    only in IBI343's U1 `unknown_diagnostics`. 0 of 62 science fields changed.
  - No clean sentence in the usefulness sets went from pass to block. UQ1, UQ6 and UQ7 pass again.
- **One fix fails on a close variant (RET-PARTIAL4, Medium).** "Nerida Bio retains U.S. rights to NB-7, for the
  treatment of locally advanced unresectable or metastatic solid tumors" still gives tier 1. `_RETAINED_USE` reads at
  most six words of use. A longer use made only of description words is then folded away by `_DESCRIPTION`, which
  takes up to twelve. This is standard label wording. End to end: QLS31905 (ws_q) is tier 1, rank 1.
- **The same use limit is not applied to returns (PARTIAL-RETURN, older and disclosed, but now inconsistent).**
  "Nerida Bio regains U.S. rights to NB-7 for solid tumors" gives RIGHTS_RETURNED, tier 1. Revision 16 blocks a
  partial *retention* for exactly that reason ("another party may hold rights for other uses"). The ending templates
  fold "P for <use>" away first. The implementer has kept partial-scope returns as a judgement call since REREVIEW9
  (H7/H8), so I do not count it as new. It is the same risk as RET-PARTIAL3, which revision 16 treats as Medium.
- **Low findings, first reported here:**
  - *CUT*: a quote cut mid-sentence with no omission mark still passes ("… in mainland China," / " --" / ":" / ";").
  - *FOOTNOTE2*: "+", "=", "@", "&" and "%" are still dropped unread, so the module's "every ASCII character is …
    read" is false.
  - *BARE-RIGHTS*: "mainland China rights" alone counts as stating the row. It states no grant, retention, ending or
    event, which are the four things the response says a quote must state.
- **Dateline opener at position 3: no hole found.** Only words in `_OPENERS` are lower-cased there, the same set as
  at position 0. A capitalised name after the dateline still blocks (DO6).
- **Confirmation: unchanged since revision 15** (`review.py` was not touched by revision 16).
  - All four refusals hold.
  - `agent_shell` returns None for an empty environment (`env -i`) and for one with only `CLAUDE_PID` /
    `CLAUDE_EFFORT` set, so the agent check is still bypassable (disclosed).
- **Usefulness:** the response's counts are honest. The new marks cost nothing on the 17 real CLDN18.2 quotes, since
  none contains "...", "*", "#", "|", "~", "^", "\\" or a bracket. They do block "~$20 million" (RM1; it passed in
  revision 15). 15 of 17 real quotes still need one analyst confirmation each.

Definite new errors (not reported in REREVIEW14.md). None occurs in the CLDN18.2 output.

| Severity | Introduced by revision 16 | Claimed fixed, fails on a close variant | Older, first reported here | Total |
|---|---|---|---|---|
| High: tier 0 or 1 while a third party may hold buyer-territory rights, or on contrary evidence | 0 | 0 | 0 | **0** |
| Medium: wrong owner, a wider grant read as the row, a process hole, a quote that does not support the row | 0 | 1: RET-PARTIAL4 | 0 | **1** |
| Low: wording, unrealistic input, a quote that says little | 1: RESP-ASCII (response/docstring claim) | 0 | 3: CUT, FOOTNOTE2, BARE-RIGHTS | **4** |

I keep the scale of REREVIEW13 and 14: partial retention is Medium. PARTIAL-RETURN is a disclosed judgement call
(§2g), not counted. A reader who applies revision 16's own retention rule to returns would count it as a further
Medium.

## 1. REREVIEW14_RESPONSE.md, claim by claim

| § | Claim | Verdict | Evidence (run or read) |
|---|---|---|---|
| 0 | No confirmation was recorded for any measurement | **Unverifiable; consistent** | `fin16_ws` has no decision log; my re-screen of a copy is `cmp`-identical to its `screening.json` |
| 1 | ELISION2: "...", ". . .", "…", brackets, braces and angle brackets block | **Held** | EL8–EL11, EL13, EL15 block (`prev/p15.out`); RM5 "C... C2" blocks with "marks words as left out or edited ('Pharma licenses NB-7 for mainland China... Chinaco Ph…')" |
| 1 | FOOTNOTE: "*", "#", "\|", "~", "^", "\\" block | **Held** | FN1, FN3 block; RM4 "C*" → "has the mark '*' …" |
| 1 | "Every character is read now holds for ASCII marks: each ASCII character is a letter, a digit, read punctuation or one of these blocked marks" | **Refuted** | OM6 "…in mainland China+", OM7 "… =", OM8 "… @", OM9 "… &", OM10 "… %" → tier 1 each. `_WORD` (`rights_template.py:272`) drops them unread (§2d, FOOTNOTE2) |
| 1 | NOTHING-READ / PAYONLY-CPO: a quote in which no clause states rights blocks, on every row type; PO1–PO4, PO9, PO12 block | **Held for those inputs; one template counts too much** | PO1–PO4, PO9, PO12 block (`prev/p15.out`); CF4 (adviser only) now blocks (`prev/cf15.out`). But the bare template "mainland China rights" counts as stating the row (SR1, ws_q BL-M05D1 tier 1; §2c BARE-RIGHTS) |
| 1 | RET-PARTIAL3: `_RETAINED_USE` reads the clause before folding; PU1–PU5, PU8 block | **Held for those inputs. Refuted on a close variant** | PU1–PU5, PU8, PU9 block. RU1, RU2, RU7, RU17 (a use of 7+ words after a comma) → tier 1 (§2a, RET-PARTIAL4) |
| 1 | `_PURPOSE` is unchanged; "for Tessaly" is still read in a licence sentence | **Held** | `git diff 28535ea f1a310d` leaves `_PURPOSE` untouched; earlier probe outputs identical |
| 1 | UPON-COND: only "Following/After the/this termination …" opens an ending; FT2, FT3, FT5–FT7 block | **Held** | All block; DO3 "DL + Upon the termination, …" blocks; DO4 "DL + After the termination, …" passes (control) |
| 2 | UQ1, UQ6, UQ7 pass again after a dateline | **Held** | `prev/p15b.out`: UQ1, UQ6, UQ7 TOP |
| 2 | UQ13, UQ14, UQ8 still block | **Held** | `prev/p15b.out` (copied in §4) |
| 2 | RESP-C4 correction | **Held** | `review.py:455` has `AGENT_ENV_PREFIXES`; revision 16 does not change `review.py` |
| 2 | Payment-only quotes on rows that cover the buyer territory now block; the edits to `test_rights_rereview13`/`11` are by design | **Held** | Diffs read: both edits make a quote block that passed before; no safety expectation is loosened |
| 2 | Tests in `test_rights_rereview14.py` | **Held** | 12 test functions. None uses a use of more than six words, a partial return, a trailing comma or "+" |
| 3 | `tests/dealscreen` 1,956 pass; ruff, mypy clean | **Held** | "1956 passed, 5 warnings in 366.92s"; ruff "All checks passed!"; mypy "Success: no issues found in 37 source files" |
| 3 | CLDN18.2: 0 of 62; CSV and memo byte-identical to revision 15; JSON differs in one IBI343 U1 sentence | **Held** | `compare.py` "AC8 scientific fields changed: 0 of 62". CSV `cmp`-identical to `fin16/out` and `after_v13`. Memo identical without the generation line. JSON: only IBI343 `unknown_diagnostics` differs from `rr15/e2e/cldn_ws` (the label list and sentence, U1 scope) |
| 3 | Cycle-4 equivalence 4 of 4 | **Held** | `equiv.json`: 4 of 4 `byte_identical: true`, `fast_path: true`; tracked `cycle4/equivalence_result.json` md5 `94450c24…` before and after |
| 3 | Cross-version 0 of 312 | **Read, not re-run** | `fin16/out/coverage.log`: `"science_changed"` empty for all four sets, `"assets_compared": 312` |
| 3 | p15 47 → 25 of 71; p15b 16 → 17 of 28; ws_p 7 → 0 | **Held** | My re-runs: "TOP COUNT 25 of 71", "17 of 28"; tiers_p 0 top |
| 3 | p14/p14b 15/2 unchanged, reasons changed for blocked payment and mark rows; p13 one reason now names "~" | **Held** | p14 diff vs revision 15: reason text only; pass/block identical |
| 3 | ws_h2 … ws_o tiers identical | **Held** | `e2e/cmp.txt`: all SAME (and ws_p) |
| 3a | What still reaches a top tier in p15 is a control, a usefulness row or a judgement row | **Held** | My p15 TOP list is exactly the 25 the response names |
| 4 | Usefulness: UQ 12/16, u14 13/18, u13 4/8, u12 16/24, u10 6/43, real quotes 15/4 of 17; no clean sentence went from pass to block | **Held** | Status of every row in u10–u14 identical to revision 15; real_quotes.out identical. Not listed: RM1 "~$20 million" newly blocks (§4) |
| 5 | REREVIEW14 §6 stands | **Held** | No CLDN18.2 position changed (§6) |
| 6 | Costs 1–5 | **Held, incomplete** | Add RM1 "~" in money (§4). Cost 4 ("a retention 'in' or 'for' a use blocks, whatever the use") is false for uses of more than six words (§2a) |
| 7 | "The reader now fails closed on every path the reviews have found" | **Refuted** | RET-PARTIAL4 is a close variant of a path the reviews found |

## 2. Paths into the top tiers

Outputs are copied from `a/p16.out` and `a/p16b.out`. Shorthand used in the tables:

- `NOT_ENC/T1` = `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE holder=None
  owner='Nerida Bio'`, no blocker.
- `RET/T1` = `RIGHTS_RETURNED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE holder='Nerida Bio' owner='Nerida
  Bio'`, no blocker.
- "r15" says what revision 15 gave on the same input.

### 2a. RET-PARTIAL4: a long use after a comma (Medium; claimed fixed: RET-PARTIAL3)

| Id | Quote (China license) | Output | r15 |
|---|---|---|---|
| RU1 | "C; Nerida Bio retains U.S. rights to NB-7, for locally advanced unresectable or metastatic solid tumors" | NOT_ENC/T1 | T1 |
| RU2 | "C; Nerida Bio retains U.S. rights to NB-7, for the treatment of locally advanced unresectable or metastatic solid tumors" | NOT_ENC/T1 | T1 |
| RU7 | "C; Nerida Bio retains U.S. rights to NB-7, for first-line locally advanced unresectable or metastatic gastric cancer" (field "gastric cancer") | NOT_ENC/T1 | T1 |
| RU17 | the RU1 retention alone, with no grant clause | NOT_ENC/T1 | T1 |
| ws_q QLS31905 | Z21 "Chinaco Pharma licenses QLS31905 for mainland China; Qilu Pharmaceutical retains U.S. rights to QLS31905, for the treatment of locally advanced unresectable or metastatic solid tumors" | memo "#1 QLS31905: no third-party grant in evidence; rights position: no grant over the buyer territory per evidence (recorded grants do not cover US; …)" | — |

Controls that block:

- RU4, the same with a six-word use: "…which says the company keeps rights only for locally advanced or metastatic solid
  tumors, so another party may hold rights for other uses".
- RU3, the seven-word use without a comma: not a template.
- RU13 "for use in solid tumors", RU14 (headline "For Solid Tumors"), RU15 "with the exception of solid tumors".

Cause, read in `a/dbg16.py`. RU2's clause becomes `G retains R rights to P , for the treatment of locally advanced
unresectable or metastatic solid tumors`.

- `_RETAINED_USE` (`rights_template.py:353-354`) takes `{0,5}?` words plus one, so six words at most. It must then
  stop at " to|in|from|for|with ", " ," or the end. Seven words with none of those stops do not match, and the
  optional "the treatment of" makes no difference.
- `_DESCRIPTION` (`:357`) then folds "P , <up to 12 words>" when every word is in `DESCRIPTOR_WORDS` (`:207`). All of
  "for, the, treatment, of, locally, advanced, unresectable, or, metastatic, solid, tumors" are on that list.
- The template text is therefore `G retains R rights to P`, which passes.

"Locally advanced unresectable or metastatic …" is the standard US label phrase, so this is realistic retention
wording. The quote says Nerida keeps U.S. rights only in one setting; someone else may hold the rest. Expected: block
any "for/in" after the program in a retention, whatever its length (for example `{0,11}` to match `_DESCRIPTION`, or
refuse "for"/"in" inside a description folded after a retained program).

### 2b. Dateline opener at position 3 (no hole found)

| Id | Quote | Output |
|---|---|---|
| DO6 | "DL + Tessaly Pharma licenses NB-7 for mainland China" | blocked: "names Tessaly, Pharma, which is not a party to the row …" |
| DO2 | "DL + Its partner Chinaco Pharma licenses NB-7 for mainland China" | blocked ("not one of the sentences") |
| DO1 | "DL + All rights to NB-7 in mainland China" | blocked |
| DO3 | "DL + Upon the termination, Nerida Bio regains U.S. rights to NB-7" (US term) | blocked |
| DO5, DO7, DO9, DO10 | "Effective today,", "As …", "Today,", "In mainland China, …" | blocked (usefulness: DO9 = UQ13) |
| DO4 | "DL + After the termination, Nerida Bio regains U.S. rights to NB-7" | RET/T1 (control; blocked in r15) |
| DO8 | "On March 3, 2025, Following the termination, …" (a body date, not a dateline) | RET/T1 (blocked in r15) |

Cause read: `to_slots` (`rights_template.py:325`) adds position 3 to `starts` only when the tokens begin with "On",
the date mark and ","; it lower-cases only words in `_OPENERS`, the same set as at position 0. DO8 shows that this
applies to any clause that starts with a date, not only to a dateline. I found no input where that matters: the date
is still checked against the as-of date.

### 2c. What counts as stating the row (`states_rights`)

| Id | Row | Quote | Output | r15 | Finding |
|---|---|---|---|---|---|
| SR1 | China license | "mainland China rights" | NOT_ENC/T1 | T1 | BARE-RIGHTS (Low) |
| ws_q BL-M05D1 | Z24 China license | "mainland China rights" | memo "#4 BL-M05D1: no third-party grant in evidence" | — | BARE-RIGHTS |
| SR7 | China license | "Nerida Bio and Chinaco Pharma entered into a license agreement in mainland China" | NOT_ENC/T1 | T1 | judgement: the place may be where it was signed |
| SR2 | China license | "Exclusive rights to NB-7" | blocked ("names Exclusive …") | — | held |
| SR3–SR6 | co-development row, mainland China | signing sentences with and without a place | `RIGHTS_UNRESOLVED` (the co-development row itself blocks) | — | held |
| SR8, SR8b | acquisition row with territory "mainland China" | "Omega Holdings acquired Nerida Bio" | `RIGHTS_ROWS_NOT_APPLIED / RIGHTS_UNRESOLVED` | — | held |
| SR10 | China license + acquisition of the licensee | "Omega Holdings acquired Chinaco Pharma" | NOT_ENC/T1 | — | correct (the acquirer holds only China) |

Cause of BARE-RIGHTS:

- `TemplateRead.states_rights` defaults to True (`rights_template.py:625`). Every template other than the payment
  sentences and an unplaced retention sets it.
- That includes the bare "rights" template (`:603`): `(?:the |)?(?:exclusive |sole )?(?:R )?rights(?: (?:to|for|of)
  P)?`.
- "mainland China rights" names the row's place and nothing else: no grantee, no grant, no date. Revision 16 blocks
  "Chinaco Pharma paid Nerida Bio $20 million" because it "does not show which rights the row covers or where". The
  bare fragment shows where, but not that anything was granted.
- The ACCEPTANCE note says a quote must state "a grant, a retention with a place, an ending or the event". This
  fragment is none of those.
- It cannot name a wider place (places must be inside the row's own territory), so I rate it Low.

### 2d. CUT and FOOTNOTE2: an excerpt cut or marked without an omission mark (Low)

| Id | Quote (China license) | Output | r15 |
|---|---|---|---|
| OM1 | "Nerida Bio granted Chinaco Pharma exclusive rights to NB-7 in mainland China," | NOT_ENC/T1 | T1 |
| OM3 | same + " --" | NOT_ENC/T1 | T1 |
| OM4 | same + ":" | NOT_ENC/T1 | T1 |
| OM12 | same + ";" | NOT_ENC/T1 | T1 |
| OM11 | "Nerida Bio granted Chinaco Pharma -- exclusive rights to NB-7 in mainland China" | NOT_ENC/T1 | T1 |
| OM6 | same + "+" ("mainland China+") | NOT_ENC/T1 | T1 |
| OM7, OM8, OM9, OM10 | same + " =", " @", " &", " %" | NOT_ENC/T1 each | T1 |
| ws_q SKB315 | Z25 "…granted Chinaco Pharma exclusive rights to SKB315 in mainland China," | memo "#5 SKB315: no third-party grant in evidence" | — |
| ws_q ATG-022 | Z22 "…exclusive rights to ATG-022 in mainland China --" | memo "#2 ATG-022: no third-party grant in evidence" | — |
| ws_q JS107 | Z23 "…exclusive rights to JS107 in mainland China+" | memo "#3 JS107: no third-party grant in evidence" | — |

Controls that block: OM2 (trailing "and"), OM5 (", etc."), OM16 (", including"), OM13 "(1)", OM14 "China1".

Cause:

- `quote_problem` strips " ,." from each masked clause (`rights_quote.py:346`), so a trailing comma, the usual sign
  that a vendor cut the sentence, disappears.
- `_WORD` (`rights_template.py:272-273`) tokenises only letters, digits, slot marks and ",". Every other ASCII mark
  ("-", ":", ";", "+", "=", "@", "&", "%", "!") is dropped unread.
- Words are still read, so a dropped mark cannot hide a holder or a place. A cut can: OM1's missing tail may be "and
  the United States".
- The response's claim "each ASCII character is a letter, a digit, read punctuation or one of these blocked marks"
  (and the comment at `rights_quote.py:305-306`) is false for "+", "=", "@", "&" and "%" (RESP-ASCII, Low).
- Realism: a trailing comma or dash in a vendor quote field is common; "+" or "&" as a footnote mark is rare.
- Expected: block a quote that ends in ",", ":", "--" or ";" (a cut), and add the remaining unread ASCII marks to
  `_REFERENCE` or drop the claim.

### 2e. Strips and characters (held)

| Id | Quote (China license) | Output | Note |
|---|---|---|---|
| ST1 | "C. Tessaly Pharma advised Nerida Bio on the transaction." | NOT_ENC/T1 | by design: an adviser does not hold rights |
| ST2 | "C, Tessaly Pharma has learned" | NOT_ENC/T1 | by design: a byline |
| ST3 | "Chinaco Pharma (Nasdaq: TSLY) licenses NB-7 for mainland China" | NOT_ENC/T1 | by design: a ticker |
| ST4 | "C, said Jane Doe, Chief Executive Officer of Chinaco Pharma" | NOT_ENC/T1 | by design |
| ST5 | "C. Tessaly US advised Nerida Bio on the transaction." | blocked ("names US …") | held: `_name_ok` |
| ST6 | grantee "Chinaco Pharma (中国)" | blocked ("the note '中国' is not read") | held |
| ST7 | "Chinaco Pharma, a global biopharmaceutical company, licenses NB-7 for mainland China" | NOT_ENC/T1 | by design |

I found no strip that removes a rights statement. Each one takes out a whole anchored shape, and its name must hold
no rights, template or place word.

### 2f. Ledger (OWNER-KEY2, ACQ-TWO)

`git diff 624b2f0 f1a310d` is empty for `rights_ledger.py`, `rights_position.py`, `rights_gate.py`,
`rights_model.py`, `screening.py`, `transaction.py`, `commercial.py`, `memo.py`, `workbook.py` and
`cli/dealscreen.py`. `prev/p14b.out` (the AQ rows) is byte-identical to `fin16/out` and to revision 15. I found no new
path that silently drops a row: ws_q imported "22 events, 0 rejected rows", and every Z row appears in the memo with
its quote.

### 2g. Judgement calls (not counted)

PARTIAL-RETURN: a use limit on a return still passes. Same harness, US term row:

| Id | Quote | Output |
|---|---|---|
| PE1 | "Nerida Bio regains U.S. rights to NB-7 for solid tumors" | RET/T1 |
| PE2 | "Alpha Bio returned U.S. rights to NB-7 for solid tumors to Nerida Bio" | RET/T1 |
| PE3 | "Nerida Bio regained U.S. rights to NB-7, for gastric cancer" | RET/T1 |
| PE5 | "Alpha Bio terminated the U.S. license with Nerida Bio for NB-7 for solid tumors" | RET/T1 |
| PE8 | RIGHTS_RETURNED row: "Alpha Bio returned U.S. rights to NB-7 for first-line treatment to Nerida Bio" | RET/T1 |
| PE6 | "Nerida Bio regains U.S. rights to the subcutaneous NB-7" | RET/T1 |
| PE4 (control) | "U.S. rights to NB-7 in solid tumors reverted to Nerida Bio" | blocked |

Cause: the use check (`_RETAINED_USE`) runs only in `_read_retention` (`rights_template.py:655`). The ending templates
(`:447-452`) read the folded text, and `fold_descriptions` removes "P for <description words>" through `_PURPOSE`
(`:386`).

The implementer has kept partial-scope returns as a judgement call since REREVIEW9 (H7/H8, REREVIEW10_RESPONSE §5).
Revision 16 now blocks the same words in a retention, saying "another party may hold rights for other uses", and that
reason applies equally here: Alpha Bio may keep U.S. rights for other indications. I list this as the most important
judgement call to revisit, not as a new error.

Other judgement calls, all unchanged:

- SR7 (a place after "agreement").
- RU5 "NB-7, an antibody for solid tumors" and RU6 "the solid tumor NB-7" pass. They describe NB-7 rather than limit
  the retention; same family as PU7.
- RS2/RS3 "responsible for the manufacturing / regulatory activities".
- The CP dateline cities.
- A confirmed row is never re-read (CF1, CF2).
- `CLAUDE_PID` and `CLAUDE_EFFORT` are not covered by the agent prefixes.
- RU14, RU20, RT6, RT8–RT10, SG8, EL5, SB4, SB5, RG7, DT4 and DL11 (disclosed).

## 3. The confirmation (CONFIRM_RIGHTS_ROW)

`conf/conf16.sh` ran on `conf/ws_conf`, a copy of my `e2e/ws_q`, with subject `rx:d591d785:6` (an LM-302 row).
Output: `conf/conf16.out`. Agent variables in this shell: `CLAUDECODE CLAUDE_CODE_CHILD_SESSION CLAUDE_CODE_ENTRYPOINT
CLAUDE_CODE_EXECPATH CLAUDE_CODE_MESSAGING_SOCKET CLAUDE_CODE_MESSAGING_TOKEN CLAUDE_CODE_SESSION_ATTENDED
CLAUDE_CODE_SESSION_ID CLAUDE_EFFORT CLAUDE_PID`.

| # | Input | Output (copied) | Verdict |
|---|---|---|---|
| C1 | CLI `decide … --new-state CONFIRMED --reviewer-kind HUMAN` in this shell | "REFUSED: this shell is run by an AI agent (CLAUDECODE is set); a rights row is confirmed only by a human analyst who has read the source" | held |
| C2 | same with `env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT` | "REFUSED: this shell is run by an AI agent (CLAUDE_CODE_CHILD_SESSION is set); …" | held |
| C3 | Python `ws.decision_log().record(…, reviewer_kind=HUMAN, context=…)` | "REFUSED: this shell is run by an AI agent (CLAUDECODE is set); …" | held |
| C4 | `agent_shell(env)` with `CLAUDECODE` and every `CLAUDE_CODE_*` removed (no record attempted) | "agent_shell -> None \| still set: ['CLAUDE_EFFORT', 'CLAUDE_PID']" | limit (disclosed) |
| C5 | `agent_shell` on single variables | `CLAUDE_CODE_X` → caught; `CODEX_HOME` → caught; `GEMINI_CLI_IDE_SERVER_PORT` → caught; `CLAUDE_PID` → None; `ANTHROPIC_API_KEY` → None | as designed |
| C6 | WITHDRAWN with nothing recorded | "REFUSED: no confirmation of this row or an earlier version of it is recorded, so there is nothing to withdraw" | held |
| C7 | `agent_shell({})` and `agent_shell(PATH, HOME only)` (no record) | "{} -> None", "PATH/HOME only -> None" | limit: an `env -i` shell passes the agent check (disclosed: "the agent check does not prove a person made a HUMAN record") |
| C8 | `env -i PATH HOME TMPDIR … --new-state WITHDRAWN` (a withdrawal of nothing; cannot record) | "REFUSED: no confirmation … nothing to withdraw" | no record |

After the run, `ws_conf` has no decision log (the listing in `conf16.out` shows none). **No record was made.** I did
not attempt a CONFIRMED record under `env -i`, because C7 already shows it would pass the agent check, and the task
forbids recording one except to test a refusal.

What a confirmation binds to, voids and shows: `rights_model.py`, `rights_gate.py` and `review.py` are unchanged by
revision 16, and `prev/cf15.out` is identical to revision 15 apart from CF4. CF4 is the unconfirmed adviser-only row
used for comparison, which now blocks with "states no grant, no retention with a place and no ending …".

- The key is the row's content hash. CF3: another program's row does not share it.
- A confirmed row's quote is not read at all, so the new `states_rights` rule does not apply to it. A confirmed
  payment-only quote passes. That is what a confirmation means.
- The reason line names the confirmer and says DealScreen cannot verify that the confirmer is a human.

## 4. Over-caution and usefulness

These are usefulness costs, not safety errors.

| Measure | Result | Source |
|---|---|---|
| REREVIEW10's 43 clean cases | 6 pass ("HELD BACK 37 of 43") | `prev/u10.out` |
| REREVIEW11's 24 / REREVIEW12's 8 / REREVIEW13's 18 | 16 / 4 / 13 pass | `prev/u12.out`, `u13.out`, `u14.out`; status of every row identical to revision 15 |
| REREVIEW14's 16 realistic sentences (UQ) | 12 pass (UQ1, UQ6, UQ7 newly pass) | `prev/p15b.out` |
| Real CLDN18.2 quotes, directly / through the gate | 15 of 17 / 4 of 17 block | `e2e/real_quotes.out` (= `fin16/out`) |
| New marks in the 17 real quotes | 0 of 17 contain "...", "…", "*", "#", "\|", "~", "^", "\\" or a bracket | `grep` of `inputs/rights_cldn18.csv` |

Clean cases held back (reviewer-written, fictional; each `RIGHTS_UNRESOLVED`):

| Id | Quote | r15 | Why it blocks |
|---|---|---|---|
| RM1 | "C; Chinaco Pharma will pay Nerida Bio ~$20 million upfront" | **passed** | "has the mark '~' …": `_REFERENCE` (`rights_quote.py:307`); "~" means "about" here. New in revision 16, not disclosed |
| RU9 / RU10 | "C; Nerida Bio retains U.S. rights to NB-7 for / in all indications" | blocked | "keeps rights only for all indications"; a full retention read as a partial one (wording cost; unchanged) |
| RM2 | "BOSTON, Mass., March 3, 2025 \| C" | blocked | "has the mark '\|'"; a pipe dateline separator (rare) |
| RM3 | "C, the #1 market" | blocked | "#" (it blocked in r15 too, for its words) |
| DO5, DO7, DO9 | "DL + Effective today, …", "As …", "Today, …" | blocked | opener forms not in the templates (unchanged) |
| UQ8, UQ14 | "responsible for all … activities for", "Pursuant to the agreement," | blocked | unchanged |
| RU8 | "C; Nerida Bio retains rights to NB-7 in the rest of the world" | **passes** | clean case kept (the question in the task) |
| RU11, RU12, RU16 | "in the United States", "all rights … in the U.S.", "NB-7, its lead antibody" | **pass** | clean cases kept |

Judgement:

- The response's usefulness numbers are honest for the sets it measured. It omits RM1.
- Revision 16's new blocks cost nothing on the real CLDN18.2 quotes, so the "any ... or * blocks" cost is real only
  for other sources.
- One analyst confirmation per row, kept across re-imports of an unchanged row, is a fair cost for a deal list of 17
  rows. With 15 of 17 real quotes needing one, however, the reader still saves the analyst very little reading. On
  this landscape the reader's main value is catching the bad paths, not clearing the good ones.

## 5. Output honesty

In favour:

- No memo I produced (CLDN18.2, ws_q) calls a program available or open. The words occur only in the fixed
  boilerplate ("availability must be evidenced", "this is not a statement of availability").
- No position, tier or action code appears in memo prose: `grep -cE "[A-Z]{3,}_[A-Z_]{3,}"` finds 0 hits in
  `memo_q.md` and in `cldn_memo.md`.
- Every holder shown in ws_q is cited.
- A confirmed row names its confirmer (`prev/cf15.out`).
- `memo.py`, `workbook.py` and the CLI `rights_reading_note` are unchanged since revision 14.
- For the 5 ws_q top-tier programs, tier and position agree between `screening.json` (`tiers_q.txt`) and the memo.

Against:

| # | Where | Output (copied) | Problem | Cause |
|---|---|---|---|---|
| O14 | `e2e/memo_q.md` #1 QLS31905 | "no grant over the buyer territory per evidence (recorded grants do not cover US; …)" beside "…retains U.S. rights to QLS31905, for the treatment of locally advanced unresectable or metastatic solid tumors" | a clean reason beside a partial retention | RET-PARTIAL4 |
| O15 | `memo_q.md` #4 BL-M05D1 | tier 1; the only evidence quote is "mainland China rights" | the cited "evidence" states no grant | BARE-RIGHTS |
| O16 | `memo_q.md` #2 ATG-022, #5 SKB315, #3 JS107 | tier 1 beside "… in mainland China --", "… in mainland China,", "… in mainland China+" | a cut or marked quote printed as evidence for a clear position | CUT, FOOTNOTE2 |
| O17 | memo ask line on all five | "Who holds US rights? Recorded deals cover other territories only (licensor per evidence: …)" | the ask ignores what the quote limits or leaves out | as above |
| O4 | confirmed row reason | "…dec:test, 2026-11-10…" | an internal id in memo prose; harmless (unchanged) | `rights_gate.py:289-291` |

## 6. CLDN18.2 measured against the reference and B

| Item | Result |
|---|---|
| `after_transaction.csv` (62 programs), my HEAD re-screen of a copy of `fin16_ws` | `cmp`-identical to `fin16/out` and to `after_v13` |
| `screening.json` | `cmp`-identical to `fin16_ws`; vs the revision-15 reviewer's screen, only IBI343 `unknown_diagnostics` differs (U1) |
| Memo | identical to `fin16/out/memo.md` without the generation line |
| Scientific fields (`compare.py`, frozen `baseline_ws/screening.json`) | **0 of 62** |
| Tiers | 44 RIGHTS_UNRESOLVED, 17 DEPRIORITIZED, 1 EXCLUDED_BY_BUYER_PREFERENCE; **0 top tier** |
| Positions | 49 NO_RIGHTS_EVIDENCE, 8 LICENSED, 2 RIGHTS_ROWS_NOT_APPLIED, 1 CONFLICTING, 1 OPTION_HELD, 1 SHARED |

Error classes against `reference_calls.csv`. No CLDN18.2 position or holder changed since revision 13 (the CSV is
byte-identical to `after_v13`), so these are REREVIEW13's and REREVIEW14's. I checked that nothing changed; I did not
re-score each row.

| Class | Count | Programs |
|---|---|---|
| False unobstructed | **0** | — (no top tier) |
| False encumbrance | 0 definite; 2 likely outdated | EO-3021, SYSA1801 (reference "RETURNED_TO_ORIGINATOR_UNCLEAR"; tool: licensed, deprioritized) |
| Wrong holder | 1, labelled | LM-302 "Turning Point Therapeutics (recorded; conflicting)" |
| Wrong territory | 0 | — |
| Missed return | 2 | SKB315 (not in the rights file), LM-302 (conflicting) |
| Missed owner | 2 (not a false call) | Zolbetuximab, IMAB362 (`RIGHTS_ROWS_NOT_APPLIED`) |

Usefulness against general Claude (B) on REREVIEW.md's 15 deal programs: **DealScreen 8 right / 6 partial / 1
missed; B 14 / 1 / 0**. These are carried over because no position changed. No advantage is shown.

## 7. Acceptance criteria

| AC | Verdict | Evidence |
|---|---|---|
| AC1 | PASS | ws_q "22 events, 0 rejected rows"; provenance on every evidence line; the import code is unchanged |
| AC2 | PARTIAL | CLDN18.2: no OPEN tier, nothing called available. Held-out: ws_q reaches tier 1 for 5 programs on quotes that limit, cut or barely state the row (§2a, §2c, §2d) |
| AC3 | PARTIAL | Grant places, unplaced grants, two-place retentions, every bracketed or dotted elision, payment-only and nothing-read quotes block. Not met: a partial retention with a use of 7+ words after a comma (RET-PARTIAL4); a quote cut at a comma or dash; "mainland China rights" alone |
| AC4 | PARTIAL | UPON-COND is closed (FT2, FT3, FT5–FT7, DO3 block). Not met: a use-limited return gives RIGHTS_RETURNED, tier 1 (PE1–PE3, PE5, PE8; disclosed judgement); LM-302 still not RETURNED (data) |
| AC5 | PASS for the inputs I ran | Option rows unchanged; payment-only option and co-promotion option rows block (PO1) |
| AC6 | PASS for the inputs I ran | Ledger unchanged since revision 14; p14b AQ rows identical |
| AC7 | PASS (age) | Staleness unchanged; dateline and body dates are read against the as-of date (DT1, DT10 block) |
| AC8 | PASS | 0 of 62; equivalence 4 of 4 byte-identical; JSON differs from revision 15 only in a U1 diagnostic |
| AC9 | PARTIAL | Preferences work. 15 of 17 real quotes still need a confirmation; RM1 "~$20 million" is a new cost |
| AC10 | PARTIAL | Every applied row is cited; a confirmed row names its confirmer. Not met: clean reasons beside a partial retention, a cut quote or a bare fragment (O14–O16) |
| AC11 | PARTIAL | Blocked rows ask a specific question; on the §2 paths the ask ignores what the quote limits or leaves out (O17) |
| AC12 | PASS | 165 added lines of `git diff 28535ea f1a310d -- src/` checked against 143 CLDN18.2 landscape and rights-file company and program names: no hit |
| AC13 | PARTIAL | IBI343, SHR-A1904 not unobstructed; RC148, FL-301, XNW27011 encumbered; LM-302 CONFLICTING, not returned |
| AC14 | FAIL | 1 Medium and 4 Low new errors on held-out inputs (§2); none in the CLDN18.2 output |

## 8. Remaining issues, ranked

1. **(Medium) RET-PARTIAL4.** "retains U.S. rights to P, for the treatment of locally advanced unresectable or
   metastatic solid tumors" passes: the use check reads at most six words and the description folder takes twelve.
   End to end: QLS31905 (ws_q, rank 1).
2. **(Judgement, same risk) PARTIAL-RETURN.** "regains / returned U.S. rights to P for solid tumors" gives
   RIGHTS_RETURNED, tier 1. It is the retention rule's own reason, not applied to endings. Disclosed since REREVIEW9,
   but now inconsistent.
3. **(Low) CUT.** A quote that ends in ",", " --", ":" or ";" passes; a trailing comma is how a cut vendor excerpt
   looks. End to end: SKB315, ATG-022.
4. **(Low) BARE-RIGHTS.** "mainland China rights" alone counts as stating the row. End to end: BL-M05D1.
5. **(Low) FOOTNOTE2 / RESP-ASCII.** "+", "=", "@", "&", "%" are dropped unread; the docstring and response claim the
   opposite. End to end: JS107.
6. **(Usefulness)** RM1 "~$20 million" newly blocks. RU9/RU10 "for all indications" read as a partial retention. 15 of
   17 real quotes still need one analyst confirmation.
7. **(Judgement, unchanged)** RS2/RS3, CP dateline cities, a confirmed row is never re-read, `CLAUDE_PID` /
   `CLAUDE_EFFORT` / `env -i` pass the agent check.
8. **(Recall)** The rights file still caps recall (LM-302's and SKB315's returns); no real vendor export tested.

## 9. The single highest-value next fix

Read one use check on every sentence that places rights, not only on retentions, and without a word limit. In
`rights_template.read_clause`, before `_template_text` folds descriptions, block any clause of a retention or an
ending in which the program or the place is followed (with or without a comma) by "for" or "in" and words that are
not a place: "P , for <any length>", "P for …", "R for …". That closes RET-PARTIAL4 and PARTIAL-RETURN together.

In the same change, block a quote whose last character before stripping is ",", ":", ";" or "-", and either add the
remaining unread ASCII marks to `_REFERENCE` or correct the claim.

None of the 17 real CLDN18.2 quotes contains "retain", "regain", "return", "revert" or "remain" (`grep` of
`inputs/rights_cldn18.csv`), so the fix costs nothing there. The one clean form that would be held back is "for all indications" (already blocked).

## 10. Checks

| Check | Result |
|---|---|
| `tests/dealscreen` at HEAD | 1,956 passed, 5 warnings (366.9 s) |
| `ruff check --no-cache src/bve/dealscreen src/bve/cli/dealscreen.py` | "All checks passed!" |
| `mypy src/bve/dealscreen/` (cache in `/tmp/claude-1000/rr16/mypy_cache`) | "Success: no issues found in 37 source files" |
| `compare.py` (frozen baseline) | "AC8 scientific fields changed: 0 of 62" |
| Cycle-4 equivalence (`rr12/run_equiv.py`, which does not write the tracked file) | 4 of 4 `byte_identical: true`, `fast_path: true`; tracked file md5 `94450c24dd45550248f008573c800843` before and after |
| Previous probes re-run (p10, p10b, av10, d10, d10b, rt10, u10, p11, q11, p12–p12d, u12, p13, p13b, u13, p14, p14b, u14, p15, p15b, p15c, cf15) | all 24 byte-identical to `fin16/out` |
| End to end (CLDN18.2, ws_h2, ws_i2, ws_j2, ws_l, ws_m, ws_n, ws_o, ws_p) | tiers identical to `fin16/out` (top-tier counts 3, 2, 0, 0, 0, 0, 0, 0); CSV identical to `fin16/out` and `after_v13`; memo identical without the generation line; `real_quotes.out` identical |
| SHA-256 of the 37 files in `src/bve/dealscreen/` | start and end identical: no file changed during the review |
| Confirmations | none recorded; C1–C3 and C6 refused, C8 a withdrawal of nothing (§3) |
| Git | no commit, stash or checkout by me; the only new file from me is this report |
