# Adversarial re-review 16: cycle R1 revision 17, rights evidence (CLDN18.2)

**AI-SIMULATED INTERNAL REVIEW.** I am an AI (Claude) playing a skeptical pharma BD analyst and auditor. I am not a
human reviewer. I approve nothing, and nothing here is validation. I did not trust REREVIEW15_RESPONSE.md. I checked
each claim by running code or reading outputs. I report only what I ran or read.

## Scope and method

- Revision 17 is commit 3dd6b51 (HEAD of `dealscreen-mvp`). I recorded the SHA-256 of all 37 files in
  `src/bve/dealscreen/` at the start (`/tmp/claude-1000/rr17/sha_start.txt`) and at the end (`sha_end.txt`). They are
  identical.
- My scripts and outputs are in `/tmp/claude-1000/rr17/`. Harness `h17.py` and `a/lib17.py` are copies of the
  REREVIEW15 harness (`rr16/h16.py`, `rr16/a/lib16.py`); only the path changed. Per-program cases go through
  `screening.program_transaction`.
- Defaults as in REREVIEW11–15: company "Nerida Bio", program NB-7, buyer {US}, as-of 2025-06-01, max age 730 days,
  `encumbered_rights: deprioritize`.
- Shorthand:
  - "C" = "Chinaco Pharma licenses NB-7 for mainland China".
  - "G" = "Nerida Bio granted Chinaco Pharma exclusive rights to NB-7 in mainland China".
  - "China license" = Nerida Bio → Chinaco Pharma, exclusive, mainland China, 2025-01-01.
  - "US term" = a US license Nerida Bio → Alpha Bio (D1, 2024-03-01) plus a termination row (2025-01-15).
  - "US option" = Alpha Bio's US option (D2, 2024-03-01, quote "Nerida Bio granted Alpha Bio an option on NB-7 in the
    United States") plus a lapse row (2025-01-15).
  - `NOT_ENC/T1` = `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE holder=None
    owner='Nerida Bio'`, no blocker. `RET/T1` = `RIGHTS_RETURNED_PER_EVIDENCE / NO_THIRD_PARTY_GRANT_IN_EVIDENCE
    holder='Nerida Bio' owner='Nerida Bio'`, no blocker.
- Every party in my attack inputs is fictional; URLs are `example.test`. End to end, my rows had to attach to CLDN18.2
  programs, so they use the landscape company as grantor and a fictional licensee (as REREVIEW14 and 15 did).
- Revision 16 for comparison: `git archive f1a310d src/bve` unpacked into `rr17/rev16/`, run with `PYTHONPATH`. No
  checkout, no git change. Columns "r16" below come from `a/p17_rev16.out` and `a/p17b_rev16.out`.
- New probes: `a/p17.py` (76 inputs), `a/p17b.py` (32 inputs), `a/dbg17.py` (masked clause, template text, verdict).
- End to end: `e2e/ws_r` is a copy of `~/.cache/rights_v1/fin17_ws` with the 17 transcribed CLDN18.2 rows plus my 10
  fictional rows Z31–Z40 (`e2e/rights_r.csv`, built by `e2e/build_r.py`). Script: `e2e/run_e2e.sh`.
- Previous probes (rr10 … rr16) were re-run in place with `python -B`; outputs in `prev/`.
- **Confirmations I recorded: none.** §4 lists every attempt; each was refused, and no decision log exists in the
  scratch copy.

## Summary

- **The response's named fixes hold on the inputs they name.**
  - All 26 earlier probe outputs (p10 … p16b, u10 … u14, cf15) are byte-identical to the implementer's `fin17/out`.
  - Against revision 16 (`fin16/out` and REREVIEW15's own `p16.out`/`p16b.out`), only these outcomes changed:
    p16 31 → 16 of 67 (SR1, RU1, RU2, RU7, RU17, OM1, OM3, OM4, OM6–OM12, OM15 now block; RM1 passes again);
    p16b 8 → 3 of 10 (PE1–PE3, PE5, PE8 block); p12 26 → 25 of 93 (UN8 blocks). Every other probe has the same
    pass/block status, as the response says.
  - End to end ws_h2 … ws_q: tier files identical to `fin17/out`; ws_q has 0 top-tier programs.
  - CLDN18.2: CSV byte-identical to `fin17/out` and `after_v13`; `screening.json` byte-identical to `fin17_ws`;
    0 of 62 scientific fields changed; cycle-4 equivalence 4 of 4.
- **One new High, older than revision 17, first reported here (DATE-BEFORE).** An ending or lapse quote dated
  *before the deal it ends* reaches tier 1. "On January 15, 2023, Alpha Bio terminated the license agreement with
  Nerida Bio for NB-7" ends a license signed on 2024-03-01 and gives `RETURNED`, tier 1. The quote cannot be about that
  license, and Alpha Bio may still hold U.S. rights. End to end: JS107 (ws_r) is tier 1, rank 3, "rights returned per
  evidence".
- **The use check fails on a close variant (USE-AFTER-DESC, Medium; claimed fixed: RET-PARTIAL4, PARTIAL-RETURN).**
  A closed appositive between the program and the use hides the use: "Nerida Bio regains U.S. rights to NB-7, an
  antibody, for solid tumors" gives `RETURNED`, tier 1; the same in a retention gives tier 1. `use_limit` looks for
  "for/in" right after the program; the folder then removes ", an antibody," and `_PURPOSE` folds "for solid tumors".
  End to end: QLS31905 (rank 1) and ATG-022 (rank 2, holder "Antengene Biologics") in ws_r.
- **Lapses have no use check (PARTIAL-LAPSE, Medium, older, first reported here).** "Alpha Bio did not exercise its
  option on NB-7 for gastric cancer" clears a whole-program U.S. option: tier 1. End to end: SKB315 (rank 5).
- **Low findings:**
  - *CUT2* (claimed fixed: CUT): a cut quote closed by a quotation mark or bracket passes: `…in mainland China,"`,
    `…,”`, `…,)`, `…, .`. End to end: BL-M05D1.
  - *START-CUT*: a quote that starts with ", ", "-- ", "; ", ": " or "— " (its opening was cut) passes. End to end:
    TORL-2-307-ADC.
  - *DASH-UNICODE* (claimed fixed: CUT): "Chinaco Pharma—exclusive rights" (em dash, no spaces) passes, while
    "Chinaco Pharma--exclusive" blocks. `_TYPOGRAPHY` writes "—" as one "-". End to end: Spevatamig.
  - *TILDE-DATE* (introduced by revision 17): "~" is now exempt before any digit, so "returned … in ~2024" passes as a
    dated return (blocked in revision 16).
  - *NAME-MARK* (introduced by revision 17): a footnote mark inside a party name is blanked with the name: grantee
    "Chinaco Pharma*" and quote "…granted Chinaco Pharma* exclusive rights…" pass (blocked in revision 16).
  - *RESP-ASCII2* (introduced by revision 17, docstring): "No character is dropped unread" is false: a trailing "(",
    a stray "$", "'" or "/" are dropped (MK10, MK12–MK14 pass).
- **Confirmation:** unchanged since revision 15. All refusals hold (C1–C3, C6, C9, C10). The agent check is still
  bypassable with `env -i` or with only `CLAUDE_PID`/`CLAUDE_EFFORT` set (disclosed).
- **Usefulness:** the response's numbers are honest. RM1 passes again. Real CLDN18.2 quotes: 15 of 17 still block
  when read directly, 4 of 17 through the gate (unchanged). New costs are those the response lists ("&", trailing
  comma or semicolon, "for all indications"); "R&D" is one more instance of the "&" rule that it does not name.

Definite new errors (not reported in REREVIEW15.md). None occurs in the CLDN18.2 output.

| Severity | Introduced by revision 17 | Claimed fixed, fails on a close variant | Older, first reported here | Total |
|---|---|---|---|---|
| High: tier 0 or 1 while a third party may hold buyer-territory rights, or on contrary evidence | 0 | 0 | 1: DATE-BEFORE | **1** |
| Medium: a wider grant read as the row, a quote that does not support the row, a partial ending | 0 | 1: USE-AFTER-DESC | 1: PARTIAL-LAPSE | **2** |
| Low: wording, rare input, a quote that says little | 3: TILDE-DATE, NAME-MARK, RESP-ASCII2 | 2: CUT2, DASH-UNICODE | 1: START-CUT | **6** |

I keep REREVIEW13–15's scale: a partial retention or ending is Medium. DATE-BEFORE is High under that scale because
the quote contradicts the row (an ending before the deal began) and the licensee may still hold U.S. rights. A reader
who requires a realistic vendor error for High may call it Medium: it needs a row that links an old ending quote to a
newer deal.

## 1. REREVIEW15_RESPONSE.md, claim by claim

| § | Claim | Verdict | Evidence (run or read) |
|---|---|---|---|
| top | No confirmation was recorded for any measurement | **Unverifiable; consistent** | `fin17_ws` has no decision log; my re-screen of a copy is `cmp`-identical to its `screening.json` |
| 1 | RET-PARTIAL4: `use_limit` reads the use with no word limit, with or without a comma, before folding; RU1, RU2, RU7, RU17 block | **Held for those inputs. Refuted on a close variant** | RU1, RU2, RU7, RU17 block (`prev/p16.out`; RU1 reason "says the company keeps rights only for locally advanced unresectable or metastatic solid tumors, so another party may hold rights for other uses"). RP1/RP2 ", an antibody, for solid tumors" → NOT_ENC/T1 (§2a) |
| 1 | `_EVERY_USE`: "all indications", "any use", "all fields of use" are not a limit | **Held; harmless** | It also accepts "all other indications" (EU1, EU2), which implies some uses went elsewhere. No template reads the words, so EU1–EU5 block anyway ("keeps rights in words DealScreen does not read" / "not one of the sentences") |
| 1 | PARTIAL-RETURN: the same check on TERMINATION and RIGHTS_RETURNED; PE1–PE3, PE5, PE8 block | **Held for those inputs. Refuted on a close variant** | PE1 reason "says the rights ended or returned only for solid tumors…". RP6–RP9, RP13, RP14, RQ2–RQ4 → RET/T1 (§2a). OPTION_LAPSED has no use check (§2b) |
| 1 | CUT: a quote ending in ",", ":", ";" or "-", or holding a dash between words, blocks; OM1, OM3, OM4, OM11, OM12 block | **Held for those inputs. Refuted on close variants** | All block. CQ1 `…China,"`, CQ2 `…China,”`, CQ3 `…,)`, CQ4 `…, .`, CQ6 ` --"`, CQ7 ` -.`, CU1–CU5 pass; DU1 "Pharma—exclusive", DU8 "regains—U.S." pass (§2c) |
| 1 | FOOTNOTE2: "+", "=", "@", "!", "_", "&" outside a name, "%" not after a number block; "~" only before an amount; OM6–OM10 block | **Held for those inputs; "~" rule is wider than stated** | OM6–OM10, OM15 block; MK6 "& Taiwan" blocks; MK5 "Chen & Wu Pharma" passes. `~(?!\s*[$\d])` exempts "~" before any digit, so MK1 "in ~2024" passes (TILDE-DATE) |
| 1 | Names are blanked before the check, "&" in a party passes, the reason quotes the original | **Held; one side effect** | MK5 passes; MK6's reason quotes the original text. A "*" inside a party name passes too (MK4, NAME-MARK) |
| 1 | BARE-RIGHTS: "mainland China rights" alone blocks; beside a grant it passes | **Held** | SR1 blocks with the NOTHING-READ reason ("…a bare "<place> rights" or press text…"); p12 UN8 blocks |
| 1 | RESP-ASCII: the reader reads letters, digits, spaces and . , ; : ' " ( ) / - $ … every other ASCII mark blocks | **Partly refuted** | The listed "read" marks are dropped by `_WORD`, not read: a trailing "(" (MK14), stray "$" (MK10), "'" (MK12), "/" (MK13) pass. The docstring's "No character is dropped unread" (`rights_quote.py:11`) is false (RESP-ASCII2) |
| 2 | Costs table (RM1 passes; RU9/RU10 still blocked with the new reason; "- the first deal" blocks; bare rights blocks) | **Held** | RM1 TOP; RU9 reason "keeps rights in words DealScreen does not read (only plain "retains rights to the program in one place")…" |
| 2 | Three test edits use a grant sentence instead of bare rights; nothing they test changed | **Held** | Diffs read (`test_rights_rereview.py:425`, `test_rights_rereview2.py:447`, `test_rights_rereview10.py:211`). Each edit makes a quote that would now block into one that passes; no safety expectation is loosened |
| 2 | `test_rights_rereview15.py` covers the attacks, reasons, clean cases, four end-to-end shapes | **Held** | 12 test functions. None uses an appositive before a use, a lapse with a use, a closing quote after a cut, a leading cut, an em dash without spaces, or an ending dated before its deal |
| 3 | `tests/dealscreen` 2,076 pass; ruff and mypy clean | **Held** | "2076 passed, 5 warnings in 178.07s"; ruff "All checks passed!"; mypy "Success: no issues found in 37 source files" |
| 3 | CLDN18.2 0 of 62; CSV and memo byte-identical to revision 16 | **Held** | `compare.py` "AC8 scientific fields changed: 0 of 62"; CSV `cmp`-identical to `fin17/out` and `after_v13`; memo identical without the generation line |
| 3 | `screening.json` differs from revision 16 only in one U1 sentence (IBI343) | **Partly verified** | My re-screen is identical to `fin17_ws`. I did not diff against a revision-16 screen (U1 scope; the other reviewer's) |
| 3 | Cycle-4 equivalence 4 of 4 | **Held** | `equiv.json`: 4 of 4 `byte_identical: true`, `fast_path: true`; tracked `cycle4/equivalence_result.json` md5 `94450c24…` before and after |
| 3 | Cross-version 0 of 312 | **Read, not re-run** | `fin17/out/coverage.log`: `science_changed` empty for all four sets, `assets_compared: 312` |
| 3 | p16 31 → 16 of 67; p16b 8 → 3 of 10; ws_q 5 → 0; p12 26 → 25 (UN8) | **Held** | `prev/p16.out` "TOP COUNT 16 of 67", `p16b.out` "3 of 10", `p12.out` "25 of 93"; `e2e/tiers_q.txt` 0 top tier; diffs listed in the Summary |
| 3 | Other probes: outcomes unchanged, only reasons changed | **Held** | Status-only diff of all 26 probes against `fin16/out`: only p12 UN8 changed |
| 3 | ws_h2 … ws_p tiers identical; real quotes unchanged | **Held** | `e2e/cmp.txt`: all SAME; `real_quotes.out` SAME |
| 3a | What still reaches a top tier in p16/p16b is a control, by design or a disclosed judgement row | **Held** | p16 TOP: SR7, SR10, RU5, RU6, RU8, RU11, RU12, RU16, DO4, DO8, RM1, ST1–ST4, ST7; p16b TOP: PE6, PE7, PE10 |
| 4 | REREVIEW15 §6 stands (0 false unobstructed; 1 labelled wrong holder; 2 missed returns; 2 missed owners; 8/6/1 vs 14/1/0) | **Held** | No CLDN18.2 position changed (CSV byte-identical to `after_v13`) |
| 5 | Costs 1–4 | **Held, incomplete** | Cost 1 is false for a use after a description (§2a). Not listed: "R&D" (UQ24) |
| 6 | "The reader fails closed on every path the reviews have found" | **Refuted** | USE-AFTER-DESC and CUT2 are close variants of paths REREVIEW15 found; DATE-BEFORE and PARTIAL-LAPSE are new paths |

## 2. Paths into the top tiers

Outputs copied from `a/p17.out`, `a/p17b.out`; "r16" from the same scripts on revision 16.

### 2a. USE-AFTER-DESC: a use after a closed description (Medium; claimed fixed: RET-PARTIAL4, PARTIAL-RETURN)

| Id | Row | Quote | Output | r16 | Expected |
|---|---|---|---|---|---|
| RP1 | China license | "C; Nerida Bio retains U.S. rights to NB-7, an antibody, for solid tumors" | NOT_ENC/T1 | T1 | block: "keeps rights only for solid tumors" |
| RP2 | China license | the RP1 retention alone | NOT_ENC/T1 | T1 | block |
| RQ1 | China license (field "gastric cancer", "antibody-drug conjugate") | "C; Nerida Bio retains rights to NB-7, its lead ADC, for gastric cancer in the United States" | NOT_ENC/T1 | T1 | block |
| RP6 | US term | "Nerida Bio regains U.S. rights to NB-7, an antibody, for solid tumors" | RET/T1 | T1 | block: "ended or returned only for solid tumors" |
| RP7 | US term | "Alpha Bio returned U.S. rights to NB-7, an antibody, for solid tumors, to Nerida Bio" | RET/T1 | T1 | block |
| RP8 | RIGHTS_RETURNED row | "Nerida Bio regained U.S. rights to NB-7, an antibody, for solid tumors" | RET/T1 | T1 | block |
| RP9 | US term | "Alpha Bio terminated the license with Nerida Bio for NB-7, an antibody, for solid tumors" | RET/T1 | T1 | block |
| RQ2 | US term (fields) | "Nerida Bio regains U.S. rights to NB-7, a claudin18.2-directed antibody-drug conjugate, for gastric cancer" | RET/T1 | T1 | block |
| RQ3, RQ4, RP13, RP14 | US term | "…, an investigational ADC, for the treatment of gastric cancer, to Nerida Bio"; "…, a monoclonal antibody, for first-line gastric cancer, from Alpha Bio"; "…, an antibody, for solid tumors, from Alpha Bio"; "…, a novel antibody, for first-line solid tumors" | RET/T1 each | T1 | block |
| ws_r QLS31905 | Z31 China license | "Chinaco Pharma licenses QLS31905 for mainland China; Qilu Pharmaceutical retains U.S. rights to QLS31905, an antibody, for solid tumors" | memo "#1 QLS31905: no third-party grant in evidence; rights position: no grant over the buyer territory per evidence (recorded grants do not cover US; …)" | — | block |
| ws_r ATG-022 | Z32 US license + Z33 termination | "Antengene Biologics regains U.S. rights to ATG-022, an antibody, for solid tumors" | memo "#2 ATG-022: no third-party grant in evidence; rights position: rights returned per evidence…"; workbook "Rights holder per evidence: Antengene Biologics" | — | block; no holder for the whole program |

Controls that block: RP11 "NB-7, for solid tumors"; RP10 "in the U.S., for solid tumors"; RP12 "NB-7 (an antibody) for
solid tumors"; RP3/RP4 ", a monoclonal antibody, in solid tumors" (no template reads a trailing "in <use>"); RP5 a
use of more than six words after the description (`_PURPOSE` does not fold it).

Cause (read with `a/dbg17.py`; RP1's clause becomes `G retains R rights to P , an antibody , for solid tumors`):

- `use_limit` (`rights_template.py:359-370`) uses `_RETAINED_USE` (`:353-354`), which needs "for" or "in" directly
  after `P` or `R`, with at most one comma between. Here `P` is followed by ", an", so there is no match.
- `fold_descriptions` (`:403`) then folds "P , an antibody ," to "P" through `_DESCRIPTION` (`:375`), and `_PURPOSE`
  (`:404`, `:349-350`) folds "P for solid tumors" to "P" when the use is at most six description words.
- The template text is `G retains R rights to P` (or `G regains R rights to P`), which passes (`:682`, `:722` see no
  use).
- ", <description>, for <use>" is common press wording. A trailing "for <use>" after a closed appositive limits the
  rights, not the program. REREVIEW15 accepted RU5 "NB-7, an antibody for solid tumors" (no second comma) as a
  description; RP1 has the second comma and is the partial case. The ACCEPTANCE note for revision 17 ("limited to a
  use … however long, with or without a comma, blocks") is false for it.
- Expected: run the use check on the text after `_DESCRIPTION` and before `_PURPOSE` (or refuse to fold a description
  that is followed by "for/in"); in a retention or an ending, any "for/in <words>" left after the program blocks.

### 2b. PARTIAL-LAPSE: a use limit on a lapse (Medium; older, first reported here)

| Id | Row | Lapse quote | Output | r16 |
|---|---|---|---|---|
| LP2 | US option | "Alpha Bio did not exercise its option on NB-7 for solid tumors" | NOT_ENC/T1 | T1 |
| LP5 | US option | "Alpha Bio declined to exercise its option on NB-7 for the treatment of solid tumors" | NOT_ENC/T1 | T1 |
| LQ1 | US option (field "gastric cancer") | "Alpha Bio did not exercise its option on NB-7 for gastric cancer" | NOT_ENC/T1 | T1 |
| LQ2 | US option | "Alpha Bio declined to exercise its option on NB-7 for first-line gastric cancer" | NOT_ENC/T1 | T1 |
| LP6 | US option | "Alpha Bio's option on NB-7, an antibody, lapsed" | NOT_ENC/T1 | T1 (a description; judgement) |
| ws_r SKB315 | Z37 US option + Z38 lapse | "Alpha Bio did not exercise its option on SKB315 for solid tumors" | memo "#5 SKB315: no third-party grant in evidence; … (option to Alpha Bio lapsed in US per source; …)" | — |

Controls that block: LP1 "let its option on NB-7 for solid tumors lapse", LP3, LP4, LQ3, LQ4 (the use is not at the
end, so `_PURPOSE` does not fold it and no template matches). LPc/LQ5 (no use) pass, correctly.

Cause: the use check runs only for retentions (`rights_template.py:682`) and for TERMINATION and RIGHTS_RETURNED
(`:722`). OPTION_LAPSED templates (`:599-609`) read the folded text, and `_PURPOSE` folds "P for solid tumors" when it
ends the clause. The option row covered the whole program in the U.S.; the lapse quote says only the solid-tumor (or
gastric) option was not exercised. Alpha Bio may still hold an option for other uses. Revision 17's own reason for
endings ("another party may still hold rights for other uses") applies. Expected: apply `use_limit` to OPTION_LAPSED
too. Whether the result also depends on position (LP1 blocks, LP2 passes) is a sign the fold, not a rule, decides.

### 2c. DATE-BEFORE: an ending dated before the deal it ends (High; older, first reported here)

| Id | Row | Quote | Output | r16 |
|---|---|---|---|---|
| DQ1 | US term (license 2024-03-01, termination 2025-01-15) | "Alpha Bio returned U.S. rights to NB-7 to Nerida Bio in 2019" | RET/T1 | T1 |
| DQ2 | US term | "On January 15, 2023, Alpha Bio terminated the license agreement with Nerida Bio for NB-7" | RET/T1 | T1 |
| DB1 | US term | "Alpha Bio returned U.S. rights to NB-7 to Nerida Bio in 2023" | RET/T1 | T1 |
| DB2 | US term | "In February 2024, Nerida Bio regained U.S. rights to NB-7 from Alpha Bio" (license 2024-03-01) | RET/T1 | T1 |
| DB6 | RIGHTS_RETURNED row | "In 2022, Alpha Bio returned U.S. rights to NB-7 to Nerida Bio" | RET/T1 | T1 |
| DB3 | US option (2024-03-01) + lapse | "On June 1, 2023, Alpha Bio's option on NB-7 lapsed" | NOT_ENC/T1 | T1 |
| ws_r JS107 | Z34 US license 2025-06-01 + Z35 termination 2026-03-01 | "On January 15, 2024, Alpha Bio terminated the license agreement with NingBo Junyan Hongshi Biosciences for JS107" | memo "#3 JS107: no third-party grant in evidence; rights position: rights returned per evidence (grant to Alpha Bio ended in US per source; …)"; ask "Does NingBo Junyan Hongshi Biosciences hold the returned US rights now, and have they been re-licensed since?" | — |

Judgement, not counted: DB4 "On June 1, 2024, Alpha Bio terminated …" (after the license, seven months before the
row's 2025-01-15) passes; an announcement may precede the effective date. DQ3 "In 2019, Nerida Bio retained U.S.
rights" passes (the disclosed RT6/RU20 family).

Cause:

- `date_problem` (`rights_template.py:114-126`) checks only that a period ends by the as-of date, or holds the row's
  own date. It never compares a quote's date with the row's date or with the date of the deal the row ends.
- `quote_problem` (`rights_quote.py:371`) passes only the row's own day (`_row_day`); the related deal's date is not
  available to it.
- The ledger applies the termination to D1 through `related_deal_id`, so the position is RETURNED.
- An ending dated before the start of the license it ends describes a different (earlier) event. The quote is
  contrary evidence, and the 2024 licensee may hold U.S. rights today. A vendor row that links an old termination
  press release to a newer deal is the realistic way this arises.
- Expected: an ending or lapse whose quote names a date that ends before the related deal's own date blocks ("dates
  the ending before the deal it ends"); a full day date that differs from the row's day is at least a question.

### 2d. CUT2, START-CUT and DASH-UNICODE (Low)

| Id | Quote (China license) | Output | r16 | Finding |
|---|---|---|---|---|
| CQ1 | `G,"` | NOT_ENC/T1 | T1 | CUT2 |
| CQ2 | `G,”` (curly) | NOT_ENC/T1 | T1 | CUT2 |
| CQ3, CQ4, CQ6, CQ7, CQ8, CQ9 | `G,)`, `G, .`, `G --"`, `G -.`, `G,'`, `"G,"` | NOT_ENC/T1 each | T1 | CUT2 |
| CU1–CU5 | `G,’`, `G -"`, `G:)`, `G, /`, `G,$` | NOT_ENC/T1 each | T1 | CUT2 |
| SC1–SC6 | `, G`, `-- G`, `; G`, `: G`, `- G`, `— G` | NOT_ENC/T1 each | T1 | START-CUT |
| DU1 | "Nerida Bio granted Chinaco Pharma—exclusive rights to NB-7 in mainland China" | NOT_ENC/T1 | T1 | DASH-UNICODE |
| DU2, DU3 | "…NB-7—in mainland China", "…NB-7–in mainland China" | NOT_ENC/T1 | T1 | DASH-UNICODE |
| DU8 | US term: "Nerida Bio regains—U.S. rights to NB-7" | RET/T1 | T1 | DASH-UNICODE |
| ws_r BL-M05D1 | Z36 `…exclusive rights to BL-M05D1 in mainland China,"` | memo "#4 BL-M05D1: no third-party grant in evidence" | — | CUT2 |
| ws_r TORL-2-307-ADC | Z39 `, TORL Biotherapeutics granted Chinaco Pharma exclusive rights to TORL-2-307-ADC in mainland China` | memo "#7 TORL-2-307-ADC: no third-party grant in evidence" | — | START-CUT |
| ws_r Spevatamig | Z40 "Phanes Therapeutics granted Chinaco Pharma—exclusive rights to Spevatamig in mainland China" | memo "#6 Spevatamig (PT886): no third-party grant in evidence" | — | DASH-UNICODE |

Controls that block: OM1 `G,`, CQ5 `G;"` (the '"' becomes its own clause), DU4 `G—` (trailing), DU5 " — " with spaces,
DU6 "Pharma--exclusive", SC7 "and G", SC8 "... G".

Cause:

- `_CUT` (`rights_quote.py:319`) is tested at `:356` on the last character of the whole text. A closing '"', "'", ")",
  "." or "/" after the comma hides it; the masked clause is then stripped of " ,." (`:367`) and the quote mark is
  dropped by `_WORD`.
- A leading ",", ":", "-" is stripped from each clause by `rights_reader._clauses` (`rights_reader.py:83`) and by
  `.strip(" ,.")` at `rights_quote.py:367`, and `_DASH` (`:322`) needs whitespace before the dash. A cut at the start
  can remove a condition ("Subject to CFIUS clearance, …").
- `_TYPOGRAPHY` (`:51`) writes "—" and "–" as one "-", the same as a hyphen, so `_DASH` cannot see an unspaced em dash.
- Words are still read, so none of these can hide a holder or a place inside the quote. They hide that words are
  missing. Rated Low, as CUT was.

### 2e. Marks (Low)

| Id | Row / quote | Output | r16 | Finding |
|---|---|---|---|---|
| MK1 | US term: "Alpha Bio returned U.S. rights to NB-7 to Nerida Bio in ~2024" | RET/T1 | **blocked ("~")** | TILDE-DATE: "about 2024" read as 2024 |
| MK2 | same, "~2025" | RET/T1 | blocked | TILDE-DATE |
| MK4 | grantee "Chinaco Pharma*": "Nerida Bio granted Chinaco Pharma* exclusive rights to NB-7 in mainland China" | NOT_ENC/T1 | **blocked ("*")** | NAME-MARK: `_blank_names` (`rights_quote.py:291-295`, used at `:340`, `:346`) blanks the "*" with the name |
| MK10, MK12, MK13, MK14 | `G $`, `G'`, `G /`, `G (` | NOT_ENC/T1 each | T1 | RESP-ASCII2: dropped unread |
| MK9 | program name "NB-7+" | NOT_ENC/T1 | T1 | by design (the program's own name) |
| MK3 | "NB-7%" | blocked ("%": the "7" is blanked with the name) | passed | fail-closed change |
| MK7 | "…in mainland China for ~$20 million" | NOT_ENC/T1 | passed | clean (as RM1) |

`_REFERENCE` (`rights_quote.py:317`) is `~(?!\s*[$\d])`: "~" before any digit passes, not only before an amount as the
docstring and response say.

### 2f. What was asked and found closed

- **`_EVERY_USE` dressed as every use.** "for all other indications" is accepted as "every use" by `use_limit`, but no
  template reads it, and "all"/"other" can never become description words (`_FUNCTION_WORDS`). EU1–EU5 block. No hole.
- **Use limits on grants, options and exercises.** A China grant "for solid tumors" (OT1) or a China exercise (OT2)
  passes; correct, since the grant is outside the buyer territory. A US grant, option or exercise is an encumbrance
  whatever its use. No hole.
- **Co-development rows** block on their own (unchanged; SR3–SR6 in `prev/p16.out`).
- **Bare rights.** Every bare form I tried blocks; `_bare_rights` uses the same frame (dates, "under the agreement",
  "announced") as the templates.
- **Characters `_TYPOGRAPHY` writes in ASCII.** Only the dashes matter (DASH-UNICODE). Curly quotes and primes become
  quote marks, which `_WORD` drops (CQ2, CU1). Zero-width and ® ™ © are deleted; non-ASCII outside a name still blocks.
- **Ledger (OWNER-KEY2, ACQ-TWO).** `git diff f1a310d 3dd6b51 -- src/` changes only `rights_quote.py`,
  `rights_template.py` and U1 files. `prev/p14b.out` (AQ rows) is byte-identical. ws_r imported "27 events, 0 rejected
  rows", and every Z row appears in the memo with its quote. I found no row that is silently dropped.
- **Disclosed judgement rows still passing**, unchanged: SR7, RU5/RU6/RU16, PE6 (descriptions of the program), RS2/RS3,
  CP dateline cities, CF1/CF2, ST1–ST4, ST7, RU14/RU20/RT6/RT8–RT10, SG8, EL5, SB4/SB5, RG7, DT4, DL11.

## 3. Over-caution and usefulness

These are usefulness costs, not safety errors.

| Measure | Result | Source |
|---|---|---|
| REREVIEW10's 43 clean cases | 6 pass (status of every row identical to revision 16) | `prev/u10.out` |
| REREVIEW11/12/13 sets | 16 of 24 / 4 of 8 / 13 of 18 pass (identical to revision 16) | `prev/u12.out`, `u13.out`, `u14.out` |
| REREVIEW14 UQ (16) | 12 pass (identical) | `prev/p15b.out` |
| Real CLDN18.2 quotes, directly / through the gate | 15 of 17 / 4 of 17 block (identical) | `e2e/real_quotes.out` |
| RM1 "~$20 million" | passes again | `prev/p16.out` |

Clean cases held back (reviewer-written, fictional; each `RIGHTS_UNRESOLVED`):

| Id | Quote | r16 | Why it blocks |
|---|---|---|---|
| UQ21 | "C; Nerida Bio retains rights to NB-7 in the U.S. & Canada" | blocked | "&" (disclosed cost 3) |
| UQ24 | "Nerida Bio granted Chinaco Pharma exclusive R&D and commercialization rights to NB-7 in mainland China" | blocked | "&" in "R&D" (same rule; not named in the response) |
| UQ22 | "G," | **passed** | trailing comma (disclosed cost 2) |
| UQ26 | "G; Chinaco Pharma will pay Nerida Bio $20 million upfront;" | **passed** | trailing ";" (disclosed cost 2) |
| UQ27, RU9, RU10 | "…retains rights to NB-7 in the United States for all indications" | blocked | "for all indications" not read (disclosed cost 1) |
| UQ25 | "Nerida Bio Regains U.S. Rights to NB-7 — Alpha Bio Ends License" | blocked | not a template (a headline with a second clause) |

Clean cases kept: UQ23 (a curly-quoted full sentence), MK5 ("Chen & Wu Pharma"), RM1, MK7, RU8, RU11, RU12, RU16.

Judgement:

- The response's usefulness numbers are honest for the sets it measured. Revision 17 costs nothing on the 17 real
  quotes (none ends in a comma, semicolon or dash, and none holds "&", "+", "=", "@", "!", "_" or "~").
- One analyst confirmation per row, kept across re-imports of an unchanged row, is a fair cost for 17 rows. With 15 of
  17 real quotes needing one, the reader's value on this landscape is catching bad paths, not clearing good ones.

## 4. The confirmation (CONFIRM_RIGHTS_ROW)

`conf/conf17.sh` ran on `conf/ws_conf`, a copy of `e2e/ws_r`, with subject `rx:8ecd9079:19` (the ATG-022 license row).
Output: `conf/conf17.out`. `review.py` is unchanged since revision 15 (`git diff --stat 28535ea 3dd6b51 -- src/`).

| # | Input | Output (copied) | Verdict |
|---|---|---|---|
| C1 | CLI `decide … --new-state CONFIRMED --reviewer-kind HUMAN` in this shell | "REFUSED: this shell is run by an AI agent (CLAUDECODE is set); a rights row is confirmed only by a human analyst who has read the source" | held |
| C2 | same with `env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT` | "REFUSED: … (CLAUDE_CODE_CHILD_SESSION is set); …" | held |
| C3 | Python `decision_log().record(…, reviewer_kind=HUMAN, context=…)` | "REFUSED: … (CLAUDECODE is set); …" | held |
| C4 | `agent_shell(env)` without CLAUDECODE and every `CLAUDE_CODE_*` (no record) | "agent_shell -> None \| still set: ['CLAUDE_EFFORT', 'CLAUDE_PID']" | limit (disclosed) |
| C6 | WITHDRAWN with nothing recorded | "REFUSED: no confirmation of this row or an earlier version of it is recorded, so there is nothing to withdraw" | held |
| C7 | `agent_shell({})`, PATH/HOME only (no record) | "{} -> None", "PATH/HOME only -> None" | limit (disclosed: `env -i` passes) |
| C8 | `env -i … --new-state WITHDRAWN` | "REFUSED: no confirmation … nothing to withdraw" | no record |
| C9 | CLI `--reviewer-kind AI_PREPARED` and `SYNTHETIC_FIXTURE` | "REFUSED: this shell is run by an AI agent (CLAUDECODE is set); …" (both) | held |
| C10 | Python, no `reviewer_kind` | "REFUSED: a rights row confirmation states its reviewer kind explicitly (HUMAN, for a human analyst who has read the source)" | held |
| C11 | `agent_shell` on `CLAUDE_EFFORT`, `CLAUDE_PID`, `CLAUDECODE=''` (no record) | None, None, CLAUDECODE | as designed |

After the run, `ws_conf` has no decision log. **No record was made.** I did not attempt a CONFIRMED record under
`env -i`.

What a confirmation binds to and voids is unchanged: `row_sha256` over 13 content fields (`rights_model.py:90-101`),
withdrawal by event id or `row_key`. `prev/cf15.out` is identical to revision 16: a confirmed row is not read again
(CF1, CF2 pass by design), its reason names the confirmer and says DealScreen cannot verify a human, and a hash does
not cross programs (CF3). A confirmation does not shield DATE-BEFORE or the other §2 paths, because those rows pass
without one.

## 5. Output honesty

In favour:

- No memo I produced (CLDN18.2, ws_r) calls a program available or open; "available" appears only in the buyer
  statement and the fixed boilerplate.
- `grep -cE "[A-Z]{3,}_[A-Z_]{3,}"`: 0 hits in `memo_r.md` and `cldn_memo.md`.
- Every holder shown in ws_r is cited with row, URL and quote; workbook and memo agree with `screening.json` for the
  seven attacked programs.
- `memo.py`, `workbook.py` and `cli/dealscreen.py` are unchanged since revision 14.

Against (all caused by §2, none in CLDN18.2):

| # | Where | Output (copied) | Problem | Cause |
|---|---|---|---|---|
| O18 | `memo_r.md` #3 JS107 | "rights returned per evidence (grant to Alpha Bio ended in US per source; …)" beside "2026-03-01 termination … "On January 15, 2024, Alpha Bio terminated the license agreement …"" and the license "2025-06-01" | the row date and the quote date disagree, and the quote predates the license; the memo shows both without comment | DATE-BEFORE |
| O19 | workbook ATG-022 | "Rights holder per evidence (not availability): Antengene Biologics" beside "…regains U.S. rights to ATG-022, an antibody, for solid tumors" | a holder for the whole program from a partial return | USE-AFTER-DESC |
| O20 | `memo_r.md` #5 SKB315 | "option to Alpha Bio lapsed in US per source" beside "did not exercise its option on SKB315 for solid tumors" | a whole-program lapse from a partial one | PARTIAL-LAPSE |
| O21 | `memo_r.md` #4, #6, #7 | tier 1 beside `…mainland China,""`, ", TORL Biotherapeutics granted …", "…Chinaco Pharma—exclusive…" | a cut quote printed as evidence for a clear position | CUT2, START-CUT, DASH-UNICODE |
| O22 | asks on all seven | e.g. "Does NingBo Junyan Hongshi Biosciences hold the returned US rights now, and have they been re-licensed since?" | the ask ignores the date or use the quote states | as above |

## 6. CLDN18.2 measured against the reference and B

| Item | Result |
|---|---|
| `after_transaction.csv` (62 programs), my HEAD re-screen of a copy of `fin17_ws` | `cmp`-identical to `fin17/out` and to `after_v13` |
| `screening.json` | `cmp`-identical to `fin17_ws` |
| Memo | identical to `fin17/out/memo.md` without the generation line |
| Scientific fields (`compare.py`, frozen `baseline_ws/screening.json`) | **0 of 62** |
| Tiers | 44 RIGHTS_UNRESOLVED, 17 DEPRIORITIZED, 1 EXCLUDED_BY_BUYER_PREFERENCE; **0 top tier** |
| Positions | 49 NO_RIGHTS_EVIDENCE, 8 LICENSED, 2 RIGHTS_ROWS_NOT_APPLIED, 1 CONFLICTING, 1 OPTION_HELD, 1 SHARED |

No CLDN18.2 position or holder changed since revision 13 (byte-identical CSV), so the error classes are REREVIEW13–15's.
I checked that nothing changed; I did not re-score each row.

| Class | Count | Programs |
|---|---|---|
| False unobstructed | **0** | — |
| False encumbrance | 0 definite; 2 likely outdated | EO-3021, SYSA1801 |
| Wrong holder | 1, labelled | LM-302 "Turning Point Therapeutics (recorded; conflicting)" |
| Wrong territory | 0 | — |
| Missed return | 2 | SKB315 (not in the rights file), LM-302 (conflicting) |
| Missed owner | 2 (not a false call) | Zolbetuximab, IMAB362 |

Usefulness against general Claude (B) on the 15 deal programs: **DealScreen 8 right / 6 partial / 1 missed; B 14 / 1
/ 0** (carried over). No advantage is shown.

## 7. Acceptance criteria

| AC | Verdict | Evidence |
|---|---|---|
| AC1 | PASS | ws_r "27 events, 0 rejected rows"; provenance on every evidence line; import code unchanged |
| AC2 | PARTIAL | CLDN18.2: no OPEN tier, nothing called available. Held-out: ws_r puts 7 programs in tier 1 on quotes that limit, contradict or cut the row (§2) |
| AC3 | PARTIAL | Bare rights, trailing comma/colon/semicolon/dash, spaced dashes, the new marks block. Not met: a cut closed by a quote mark (CUT2), a cut at the start, an unspaced em dash |
| AC4 | PARTIAL | PE1–PE3, PE5, PE8 block. Not met: a use after a description (RP6–RP9, RQ2–RQ4); an ending dated before its deal gives RETURNED (DATE-BEFORE); LM-302 still not RETURNED (data) |
| AC5 | PARTIAL | Clean lapses pass; option exercise unchanged. Not met: a use-limited lapse clears the whole option (LP2, LQ1); a lapse dated before the option clears it (DB3) |
| AC6 | PASS for the inputs I ran | Ledger unchanged; p14b identical |
| AC7 | PASS (age) | Staleness unchanged. A quote date before the deal is not checked (counted under AC4/AC5) |
| AC8 | PASS | 0 of 62; equivalence 4 of 4 byte-identical; cross-version read 0 of 312 |
| AC9 | PARTIAL | Preferences work. 15 of 17 real quotes still need a confirmation |
| AC10 | PARTIAL | Every applied row is cited; confirmed rows name the confirmer. Not met: O18–O21 |
| AC11 | PARTIAL | Blocked rows ask specific questions; on the §2 paths the ask ignores the quote's date or use (O22) |
| AC12 | PASS | 136 added lines of `git diff f1a310d 3dd6b51 -- src/` checked against 145 CLDN18.2 landscape and rights-file names (4+ characters): no hit |
| AC13 | PARTIAL | IBI343, SHR-A1904 not unobstructed; RC148, FL-301, XNW27011 encumbered; LM-302 CONFLICTING, not returned |
| AC14 | FAIL | 1 High, 2 Medium, 6 Low new errors on held-out inputs (§2); none in the CLDN18.2 output |

## 8. Remaining issues, ranked

1. **(High) DATE-BEFORE.** An ending or lapse quote dated before the deal it ends gives RETURNED or a cleared option,
   tier 1 (DQ1, DQ2, DB1–DB3, DB6; ws_r JS107).
2. **(Medium) USE-AFTER-DESC.** ", <description>, for <use>" after the program hides the use from `use_limit` in
   retentions and endings (RP1, RP2, RP6–RP9, RQ1–RQ4; ws_r QLS31905, ATG-022).
3. **(Medium) PARTIAL-LAPSE.** A lapse "for <use>" clears a whole-program option (LP2, LP5, LQ1, LQ2; ws_r SKB315).
4. **(Low) CUT2, START-CUT, DASH-UNICODE.** A cut closed by a quote mark, a cut at the start, an unspaced em dash pass
   (ws_r BL-M05D1, TORL-2-307-ADC, Spevatamig).
5. **(Low) TILDE-DATE, NAME-MARK, RESP-ASCII2.** Introduced by revision 17's exemptions and docstring.
6. **(Usefulness)** "&" (including "R&D"), trailing comma/semicolon, "for all indications"; 15 of 17 real quotes need
   one analyst confirmation.
7. **(Judgement, unchanged)** descriptions of the program (RU5, RU6, RU16, PE6, LP6), RS2/RS3, CP dateline cities, a
   confirmed row is never re-read, `CLAUDE_PID`/`CLAUDE_EFFORT`/`env -i` pass the agent check, DB4 (an ending dated
   between the deal and the row).
8. **(Recall)** The rights file still caps recall (LM-302, SKB315); no real vendor export tested.

## 9. The single highest-value next fix

Compare every date a quote names with the deal the row ends. In `rights_gate`/`quote_problem`, pass the related
deal's own date (or start of period) for TERMINATION, RIGHTS_RETURNED and OPTION_LAPSED rows, and block when a period
in the quote ends before it ("dates the ending before the deal it ends, so it may describe another deal"). That closes
the only High. In the same change, run `use_limit` after `_DESCRIPTION` folds and before `_PURPOSE` does, and apply it
to OPTION_LAPSED; that closes both Mediums. The only real CLDN18.2 ending rows (R07 termination, R08 return) name no
year in their quotes and no use after an appositive, so the cost there should be nil (read, not run on a fix).

## 10. Checks

| Check | Result |
|---|---|
| `tests/dealscreen` at HEAD | 2,076 passed, 5 warnings (178.1 s) |
| `ruff check --no-cache src/bve/dealscreen src/bve/cli/dealscreen.py` | "All checks passed!" |
| `mypy src/bve/dealscreen/` (cache in `/tmp/claude-1000/rr17/mypy_cache`) | "Success: no issues found in 37 source files" |
| `compare.py` (frozen baseline) | "AC8 scientific fields changed: 0 of 62" |
| Cycle-4 equivalence (`rr12/run_equiv.py` into `rr17/eq`; does not write the tracked file) | 4 of 4 `byte_identical: true`, `fast_path: true`; tracked md5 `94450c24dd45550248f008573c800843` before and after |
| Previous probes re-run (26) | all byte-identical to `fin17/out` (`prev/cmp.txt`) |
| End to end (CLDN18.2, ws_h2, ws_i2, ws_j2, ws_l, ws_m, ws_n, ws_o, ws_p, ws_q) | tiers identical to `fin17/out`; CSV identical to `fin17/out` and `after_v13`; memo identical without the generation line; `real_quotes.out` identical (`e2e/cmp.txt`) |
| SHA-256 of the 37 files in `src/bve/dealscreen/` | start and end identical |
| Confirmations | none recorded; C1–C3, C6, C9, C10 refused; C8 a withdrawal of nothing |
| Git | no commit, stash or checkout by me (`git archive` read only); the only new file from me in the repository is this report |
