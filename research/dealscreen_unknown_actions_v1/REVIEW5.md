# Cycle U1 revision 5: fifth adversarial review

INTERNAL DEVELOPMENT. This is an AI-simulated adversarial review. It is not human or independent validation, and
nothing in it is an approval.

**Reviewed:** HEAD `b0388eb` on `dealscreen-mvp` in `/home/djmann/projects/bve-b8`, read-only. U1 revision 4 is
`04faab7`. R1 revision 10 (`d905ff0`) touched only rights code, and `git diff d905ff0 b0388eb -- src/` changes only
`diagnostics.py` (+7/-1) and `indication_relations.py` (+26/-9).
**Criteria:** `ACCEPTANCE.md` with its revision notes, `MEASUREMENT.md`, `REVIEW4.md` and `REVIEW4_RESPONSE.md`.

Every number below was recomputed by running code, unless it is marked "read, not re-run". Scratch files and probe
scripts are in `/tmp/claude-1000/u1rr5/`. Abbreviations:
- `dg` = `bve.dealscreen.diagnostics`; `ir` = `bve.dealscreen.indication_relations`.
- `GAS` = the CLDN18.2 request `["gastric adenocarcinoma", "gastroesophageal junction adenocarcinoma"]`.
- `ALL-A` = the request `["adult acute lymphoblastic leukemia"]` (one NCIt concept).
- "E2E" = confirmed through `bve-dealscreen import` and `screen` on a workspace built from the CLDN18.2 inputs with
  cells edited (details under Reproduction).
- "rev4" = revision 4's two modules, loaded side by side from `git show 04faab7:…`
  (`/tmp/claude-1000/u1rr5/rev4/`).

## Verdict in one paragraph

Revision 5 changes no science. Coverage is complete. The shipped CLDN18.2 outputs are byte- or cell-identical to a
fresh run, and the held-out screens are identical to revision 4's, diagnostics included. D2, D4, D8 and D9 of REVIEW4
are fixed. The D2 fix holds over all of NCIt: no stage concept of another lineage is called "under a broader parent"
for any of 7,680 request concepts. D1 and D3 are fixed for the inputs REVIEW4 listed. D5, D6 and D7 are open, as
the response says.

**U1-7 is still not met.** Both fixes for REVIEW4's medium findings over-reach. Each creates a new false statement
of the same kind, and both are confirmed end to end:
1. **N1 (medium; regression from the D1 fix).** "ALL" before any "basket word" is read as the word "all". The basket
   word list includes qualifiers, population words and function words (relapsed, refractory, advanced, adults,
   patients, in, of). So "Relapsed ALL in adults", "Relapsed or refractory ALL in adults", "ALL in children", "ALL
   relapsed" and "ALL patients" are now said to "name no disease or site (a basket)". Revision 4 called them
   UNREADABLE.
2. **N2 (medium; regression from the D3 fix).** The "stated both negative and positive" test runs over the whole
   cell, not over the part that names the target. If another target in the same cell is "negative or positive",
   "pos/neg" or "…, positive for…", the required target's own negation is ignored. The program is then summarised as
   "the required target in a form DealScreen does not read", and the other target disappears from the sentence. Two
   examples: "not CLDN18.2; HER2 positive or negative" and "CLDN18.2 negative, positive for CD47". Revision 4 said
   these cells state the program is not CLDN18.2 and named the other target.

## Verdict per criterion

| AC | Verdict | Evidence |
|---|---|---|
| U1-1 coverage | **Met** | `coverage.py` (second reviewer's script, re-run) on `u1r5_ws` and `rights_v1/xvu5/*`: CLDN18.2 38/38, c5_heldout 28/28, fcrn_v1 28/28, fcrn_v2 28/28, synthetic_200 20/20. Missing 0, extra 0. A fresh `screen` of a copy of `u1r5_ws` is byte-identical to `u1r5_ws/screening.json` and to `after/screening_u1.json`. |
| U1-2 authorities only | **Met (letter), with notes** | I grepped both U1 modules for landscape words (gastr, claudin, cldn, gej, stomach, fcrn, myasthen, tigit, zolbet, pancrea, junction, rilveg, volrus, esophag, oesoph, lymphoblastic, leuk, tl1a, ibd). The hits are docstrings, comments and the generic spelling pairs. The new logic is generic: `"stage" in label(a)`, `_BASKET_WORDS - {"all"}`, a negative/positive regex and a tumour-head test. As before (J5), the basket, negation, role and lineage word lists are DealScreen's own. N1 comes from reusing the basket word list as a "this capital word is ordinary" signal. |
| U1-3 no change to science | **Met** | `science_diff.py`: `u1r5_ws` vs `baseline/screening_R1.json` gives 0 of 62 programs changed on disposition, rank, decisions, machine_recommendation, transaction and transaction_rank; the only differing key is `unknown_diagnostics`, and the top level is equal. `xvu5` vs `xv10`: 0 differing per-program keys of any kind in all four landscapes (40, 40, 40 and 192 programs), so revision 5 does not change even a diagnostic there. `xvu5` vs `xv8`: 0 science fields. Cycle-4 equivalence: `equivalence.main()` was called in-process with output to scratch, and all 4 cases are `byte_identical: true`, `fast_path: true`. The md5 of the tracked `equivalence_result.json` (`94450c24…`) was the same before and after. That file was already modified in the working tree before this review, by someone else. |
| U1-4 held-back tests | **Met as written; insufficient in substance** | `python -m pytest tests/dealscreen -q -p no:cacheprovider`: **1,327 passed**, 5 warnings, 85 s. `test_unknown_actions.py`: 250 cases, 88 functions. The new D1 tests check only that some "ALL" names are not baskets and that "ALL COMERS"/"ALL SOLID TUMORS" are. No test puts "ALL" before a qualifier, population or function word (N1). The new D3 tests check only cells with a single target, plus "ABC1.2 negative; XYZ positive", which has no both-states phrase (N2). |
| U1-5 surfaces | **Met** | A regenerated workbook vs `after/u1_cldn18.xlsx`: all 9 sheets are cell-identical except the README "Generated" timestamp. The regenerated `memo.md` is identical to `after/memo_u1.md`. The Diligence sheet keeps the S&E text beside the DealScreen action. On the E2E workspace, the Diligence sheet shows N2's false sentence and class (below). |
| U1-6 per program vs reference | **Met as measured (unchanged)** | Recomputed from `reference_calls.csv` by program id: 30 reference-IN programs, of which 14 are ELIGIBLE, 15 UNRESOLVED and 1 EXCLUDED (LCB02A, disclosed). No gastric or GEJ name is DIFFERENT_DISEASE. SOT102 ("Pancreatic Cancer") is DIFFERENT_DISEASE and is reported. RC118, VBC108, SG1906, TQB2103, AK132 and Q-1802 are BASKET, and the action names both requested indications. Rilvegostomig names TIGIT and 'PD-1', volrustomig names CTLA-4 and 'PD-1', and RC148 names 'PD-1'. |
| U1-7 adversarial review | **Not met** | N1 and N2 are confirmed end to end. I found no hidden UNKNOWN, no stray diagnostic, no scope or recommendation wording and no change to science. |

## Status of REVIEW4's findings

Inputs: REVIEW4's probes `/tmp/claude-1000/u1rr4/p_ind4.py`, `p_sib.py`, `p_tgt4.py` and `restate.py`; the third
reviewer's `u1rr3/p_ind.py`, `p_tgt.py` and `p_sib2.py`; the second reviewer's `u1rr/probes/p1–p10.py`. I re-ran them
unchanged against HEAD and diffed against REVIEW4's saved outputs. p1–p10 and `p_sib2` are unchanged, except for
p4's order among tied counts. `p_ind` changes only on "Solid tumors, ALL comers" and "Advanced solid tumors (AST)",
both now BASKET. `p_tgt4` changes only on the three D3 rows. (Note: the S&E target snapshot path is relative to
the working directory. Run from another directory, `p7` and `p_tgt` read 'CLDN6' and 'PDL1' as unread. This is
environmental, not a U1 defect; every result here was run from the repository root.)

| Id | Status | Input → output at HEAD |
|---|---|---|
| D1 all-caps qualifier + ALL | **Fixed as stated; regression N1** | E2E (REVIEW4's `ws_e2e_all`, re-screened): Q-1802 "RELAPSED ALL" → BROADER_THAN_REQUESTED; TQB2103 "PEDIATRIC ALL" → DIFFERENT_DISEASE (Childhood ALL); RC118 "Relapsed ALL" → BROADER. Unit: "ALL, RELAPSED" and "ADVANCED ALL" are not baskets; "ADULT ALL" → READS_AS_REQUESTED. But "ALL" *before* a qualifier or population word is now a basket in mixed case too (N1). |
| D2 stage siblings of other lineages | **Fixed** | All REVIEW4 rows are now DIFFERENT_DISEASE: "Stage IV gastric neuroendocrine tumor", "Stage III Gastric Neuroendocrine Tumor AJCC v8", "Stage IV pancreatic neuroendocrine tumor", "Stage IV colorectal neuroendocrine tumor", "Stage IV small cell lung cancer", "Stage IV uterine corpus leiomyosarcoma", "Stage IV Uterine Corpus Endometrial Stromal Sarcoma AJCC v8", "Stage IV mycosis fungoides". Kept: "Stage IV gastric cancer" (also E2E, RC118), "Stage IV endometrial cancer" (Uterine Corpus Carcinoma or Carcinosarcoma) and "Stage D prostate cancer". **Full sweep** (`sib5b.py`): every NCIt concept under a by-site node whose label ends in a tumour head (7,680), against all 2,732 stage concepts. This gives 178 distinct sibling stems. I read all of them: each is the request's own parent disease or a staging grouping that contains it (for example "Gastric Neuroendocrine Tumor" only for "Gastric Gastrin-Producing Neuroendocrine Tumor", "Lung Small Cell Carcinoma" only for SCLC requests, "Soft Tissue Sarcoma" for "Gastric Sarcoma"). None is another lineage. The disclosed cost is confirmed: "Stage IV anal cancer" (anal SCC request) and "Stage IV adult primary liver cancer" (HCC request) → DIFFERENT_DISEASE. |
| D3 both expression states read as negation | **Fixed for single-target cells; regression N2** | "CLDN18.2 negative or positive" (and fictional "VORP3.1 negative or positive", "VORP3.1 negative and positive cohorts") → SOURCE_MAY_NAME_REQUIRED_TARGET. Residues are under N3. |
| D4 basket with its own acronym | **Fixed** | "Advanced solid tumors (AST)", "Advanced Cancer (AC)", "Malignant solid tumor (MST)", "Advanced malignancies (AM)", "Solid tumours (ST)", "Solid tumors (STs)", "Metastatic cancer (MC)", "Advanced Solid Tumor (AST) ", "Other cancers (OC)", "Selected solid tumors (SST)" and "ADVANCED SOLID TUMORS (AST)" → BASKET. Rev4 gave UNREADABLE, OVERLAPS, BROADER or DIFFERENT for these. "Advanced cancers (AC), gastric" → NAMES_REQUESTED_SITE (correct). Judgement J-b below. |
| D5 TNBC request has no site words | **Open (declared)** | `site_phrases("triple-negative breast carcinoma")` = ∅. "Stage IV breast cancer" → DIFFERENT_DISEASE; "Breast cancer" → AMBIGUOUS_NAME_ALL_BROADER. |
| D6 partner hidden after " / ", "or", "vs", "→" | **Open (declared)** | "CLDN18.2 / CD3", "CLDN18.2 or PD-L1", "CLDN18.2 vs PD-L1" and "CLDN18.2 → TROP2" → names the target with no "also on record". Also "CLDN18.2/ CD3", "CLDN18.2 /CD3", "CLDN18.2 \| CD3", "CLDN18.2 &/or CD3" and "CLDN18.2 – CD3" (unit). |
| D7 "without X selection" | **Open (declared)** | "No CLDN18.2 selection", "without CLDN18.2 selection" and "non-CLDN18.2 arm: PD-1" → SOURCE_STATES_NOT_REQUIRED_TARGET ('PD-1' not shown). |
| D8 "<site> <head> type" as role | **Fixed** | "Gastric cancer type: diffuse", "Gastric carcinoma type 2" → NAMES_REQUESTED_SITE. "Gastric-type" (no head between) is still a role. |
| D9 'TUMOR' restatement | **Fixed** | `restate.py` over all NCIt labels: 29 restatements (was 30), all acronyms or abbreviations (GBM, DLBCL, NHL, MPNST, CA, …). `restatement("Neoplasm")` → None. |

## Defects in revision 5, ranked by how much they could mislead

### N1 (medium; regression from the D1 fix). "ALL" before a qualifier, population or function word is called a basket

`ir._before_basket_word` treats a capitalised acronym as the ordinary word "all" when the next word is in
`_BASKET_WORDS - {"all"}`. That set is not only tumour heads and "solid"/"comers". It also contains every DealScreen
qualifier (relapsed, refractory, recurrent, advanced, metastatic, chronic, severe…), every population word (adult(s),
children, patients, participants…) and the function words (in, of, with, and, or…). Of the basket words, only "all"
(and the trivial "an" and "mild") is also an index acronym, so the exposure is "ALL". This is the commonest
acronym in haematology.

| Request | Record name | HEAD | rev4 | Expected |
|---|---|---|---|---|
| ALL-A | "Relapsed ALL in adults" (**E2E**, RC118) | BASKET, "names no disease or site (a basket)" | UNREADABLE | not BASKET (UNREADABLE, or BROADER via the screen's reading) |
| ALL-A | "Relapsed or refractory ALL in adults" (**E2E**, VBC108) | BASKET | UNREADABLE | same |
| ALL-A | "ALL in children" (**E2E**, TQB2103) | BASKET | UNREADABLE | same (or Childhood ALL) |
| ALL-A | "ALL RELAPSED" (**E2E**, Q-1802) | BASKET | BASKET (REVIEW4 D1 residue) | same |
| ALL-A | "ALL in adults", "ALL relapsed", "ALL patients", "ALL Adults", "ALL Stage IV", "ALL of any stage" | BASKET | UNREADABLE | same |
| ALL-A | "ALL REFRACTORY", "ALL - RELAPSED", "ALL ADVANCED", "ALL PATIENTS" | BASKET | BASKET | same |
| control | "RELAPSED ALL" (**E2E**, AK132), "ALL, relapsed", "ADULT ALL" | BROADER / BROADER / READS_AS_REQUESTED | BASKET / UNREADABLE / BASKET | (correct now) |

- **Why it misleads:** the sentence is false about the record, which names a disease. The memo's single-open-gate list
  puts RC118 and VBC108 in the group "a basket naming no disease or site" (E2E memo, line 20). This is REVIEW4 D1's
  harm, now also in mixed case, which revision 4 got right.
- **Expected and fix:** read a capitalised index acronym as the word "all" only before a tumour head, "solid" or
  "comers" (REVIEW4's suggestion): `_BASKET_HEADS | {"solid", "comers"}`. A more robust fix: in `is_basket`, a name
  whose acronym the screen's reading (`_lookup`) resolves to a disease is never a basket. Add the rows above as tests.

### N2 (medium; regression from the D3 fix). A both-states phrase anywhere in the cell cancels the required target's negation

`dg.target_diagnostic` sets `both = [v for v in values if _BOTH_STATES.search(v)]`. It then drops every negated part
`p` with `any(p in v for v in both)`. The check is on the whole cell, and `p` is a substring of its own cell, so one
"X negative or positive", "X pos/neg" or "negative, positive" anywhere in the cell un-negates every target in it.
The part becomes "maybe", and the SOURCE_MAY_NAME branch prints only the maybe part. The other target is not
mentioned.

| Target cell (GAS reader unless fictional) | HEAD | rev4 |
|---|---|---|
| "not CLDN18.2; HER2 positive or negative" (**E2E**, SG1906; Diligence sheet too) | SOURCE_MAY_NAME_REQUIRED_TARGET: "'not CLDN18.2' contains CLDN18 or its name, in a form neither the target authority nor DealScreen reads"; summary "the required target in a form DealScreen does not read" | SOURCE_NAMES_OTHER_TARGETS: names 'HER2 positive or negative' … ('not CLDN18.2' states it is not CLDN18.2) |
| "CLDN18.2 negative, positive for CD47" (**E2E**, AK132) | MAY_NAME: "'CLDN18.2 negative' contains CLDN18 …" | NAMES_OTHER_TARGETS with the negation shown |
| "CLDN18.2 negative; PD-L1 negative or positive" | MAY_NAME, PD-L1 not mentioned | NAMES_OTHER_TARGETS, negation shown |
| "CLDN18.2-negative, HER2 neg/pos"; "CLDN18.2 negative (PD-L1 positive or negative)" | MAY_NAME | NAMES_OTHER_TARGETS |
| fictional "VORP3.1 negative; KLX9 negative or positive", "not VORP3.1; KLX9 neg/pos", "VORP3.1 neg, pos selection" | MAY_NAME | NAMES_OTHER_TARGETS / STATES_NOT |
| "VORP3.1 negative or positive; not VORP3.1" | MAY_NAME for both parts | (rev4 called both negated) |
| control: two values `["VORP3.1 negative", "KLX9 negative or positive"]` | negation kept (separate values) | same |

- **Why it misleads:** the record says the program is *not* the required target (N6 of the second review). The
  summary says the opposite: the required target is there in an unreadable form. The program's real target (HER2,
  PD-L1, CD47) is dropped from the sentence. This is the N6/D2/D3 failure family again, and the partner-hiding of
  REVIEW3 D9.
- **Expected:** revision 4's output for these cells.
- **Fix:** test `_BOTH_STATES` on the span after the symbol in the part itself. For "X neg/pos", which the slash
  splits into "X neg" and "pos", test the text between this match and the next symbol, not the whole cell. Also
  list the other parts in the SOURCE_MAY_NAME sentence. This is pre-existing: "VORP3L1; KLX9" already omits KLX9
  there. N2 makes it reachable more often.

### N3 (low). D3 residues and quoting

- "VORP3.1 neg & pos" → SOURCE_STATES_NOT_REQUIRED_TARGET ("&" is not in `_BOTH_STATES`).
- "VORP3.1 negative or low" and "VORP3.1-negative or -low" → "states it is not VORP3.1". Expression "low" names the
  target under the D2 rule of the third review (judgement).
- "CLDN18.2 neg/pos" and "CLDN18.2-negative and -positive" → the sentence quotes only 'CLDN18.2 neg' or
  'CLDN18.2-negative' as the form that "contains CLDN18". The positive half, which is why it is not a negation, is
  not shown.
- "CLDN18.2 (neg/pos)" → quotes 'CLDN18.2 (neg' and "also on record: 'pos)'", with broken parentheses.
  "CLDN18.2 and / or CD3" → "also on record: '/ or CD3'".
- "CLDN18.2–negative" (en dash) → "names CLDN18 (Claudin 18.2)": the negation is missed. The hyphen form is read as
  negated.

### Pre-existing, still open (not counted again)

D5, D6, D7 (above), J2 and J3 of REVIEW3, and REVIEW4's J-a lexical leads ("Stomach flu", "Dry mouth", "Dry eye
disease" → NAMES_REQUESTED_SITE).

## Judgement calls (labelled; not counted as defects)

- **J-a. The D2 cost.** With the sibling rule now exact for every lineage I swept, its cost is the same-disease stage
  concepts that NCIt files under a population or staging-system node: "Stage IV anal cancer" (anal SCC request),
  "Stage IV adult primary liver cancer" (HCC request) and FIGO endometrial. These are DIFFERENT_DISEASE again, "neither
  a requested indication nor a subtype of one". The sentence is true to NCIt. The class name overstates, and these
  programs sort below BASKET. This is disclosed, and I agree it is the better side to err on.
  - Measured with the same sweep on revision 4 (`sib5b_r4.py`): the distinct sibling stems fall from 220 to 178.
  - Removed entirely: every neuroendocrine stem (gastric, pancreatic, colorectal, appendix, duodenal, jejunal/ileal,
    ampullary, digestive-system), every GIST stem, Merkel cell, mycosis fungoides, both Ann Arbor lymphoma stems,
    medullary and follicular thyroid, osteosarcoma, every uterine sarcoma stem, and the FIGO 2023 molecular endometrial
    stems.
  - Reduced to the request's own lineage: SCLC (128 → 4 requests) and occult lung cancer (128 → 6).
  - Reduced in reach, the cost: adult liver cancer (28 → 4 requests), anal canal cancer (48 → 22), distal bile duct
    cancer (35 → 1), major salivary gland cancer (46 → 5) and intrahepatic cholangiocarcinoma (16 → 0).
  - No stem was added.
- **J-b. A basket's "own" acronym is found by letters, not by meaning.** "Advanced malignancies (AML)" → BASKET.
  'AML' fits "Advanced MaLignancies", but the index reads it as Acute Myeloid Leukemia, so the record may mean AML.
  Among the acronyms I tried, only AML is index-read ("AST" reads as Cutaneous Spitz Melanocytoma, and is
  correctly dropped as the basket's acronym). A safer rule would keep a parenthetical that the index reads as a
  disease, unless it is a basket-word acronym.
- **J-c. The screen's own clean-up steps are reported faithfully, and some are lossy.** "ALL (ADULT)" → "reads as
  Acute Lymphoblastic Leukemia once acronym removed, broader than requested". The record states the requested
  population, but the screen's reading drops "(ADULT)". "Advanced cancer (CUP)" → "reads as Advanced Malignant
  Neoplasm once acronym removed". These are screen readings (`indication_readings`), outside U1. The U1 sentence is
  true to them. Revision 4 called "ALL (ADULT)" a basket.
- **J-d. Other therapy areas.** UC request: "Colitis" → DIFFERENT_DISEASE (NCIt does not file UC under Colitis);
  "UC", "Moderate to severe UC" → UNREADABLE (the index does not read "UC"); "IBD" → BROADER. RA request: "RA" →
  AMBIGUOUS_NAME (Refractory Anemia; Rheumatoid Arthritis); "Juvenile idiopathic arthritis" → DIFFERENT_DISEASE.
  None of these changed in revision 5, and all are true to the authority.

## Reading `after/` as a BD analyst

The CLDN18.2 outputs are unchanged from revisions 3 and 4 (the cells are identical). REVIEW4's reading still holds:
- Each of the 38 actions says what is on record, its class and the one cited fact that would decide the gate.
- The three PD-1 rows name TIGIT, CTLA-4 and 'PD-1'.
- The six basket rows name both requested indications.
- The "Imaging agent" rows give the allowed modalities.

Still less useful:
- The repeated "The gate never fails on this evidence…" tail on 24 rows.
- DR30303's "'Malignant Neoplasm of Digestive System' is not a name the NCIt authority can read", which hides an
  obvious broader reading.
- "(+1 more)" in the memo's basket group.

Nothing is hidden: every UNKNOWN on a non-excluded program has its diagnostic. N1 and N2 need inputs this landscape
does not contain: "ALL" before a qualifier, and a target cell with a negated required target beside a both-states
partner. The held-out landscapes do not contain them either; their diagnostics did not change at all.

## What I could not check

- Whether the new tests were written before the code was tuned.
- Workbooks and memos for the held-out landscapes; I read only their `screening.json`. For the E2E workspaces I
  generated the ALL memo and the GAS workbook only.
- The `.docx` memo was regenerated but not opened.
- Domain judgements used to rate harm, not checked against an authority: that "Relapsed ALL in adults" means acute
  lymphoblastic leukemia; that "not CLDN18.2; HER2 positive or negative" describes a non-CLDN18.2 program; and that
  "Advanced malignancies (AML)" could mean acute myeloid leukemia. The NCIt structure claims (ancestors, stage
  groupings, sibling stems, index readings of AML, AST, ACC, STS) were checked against the frozen authority.
- The N1 and N2 fixes were not implemented or tested.
- The rights code under concurrent review (out of scope; not touched). At about 13:56, after every suite run,
  screen, export and memo in this review, another process modified `rights_quote.py` and `rights_signals.py` in the
  working tree and added `rights_vocab.py`. The test suite (13:18) and every screen (by 13:35) ran on HEAD's
  committed code. I did not re-run anything against the modified tree.

## Reproduction

```
cd /home/djmann/projects/bve-b8 && . .venv/bin/activate && export TMPDIR=$HOME/.cache/dealscreen_suite
# run every probe from the repository root (the S&E target snapshot path is relative)
python -m pytest tests/dealscreen -q -p no:cacheprovider              # 1327 passed, 5 warnings
for p in p1 p2 p3 p4 p5 p6 p7 p8 p9 p10; do python /tmp/claude-1000/u1rr/probes/$p.py; done
python /tmp/claude-1000/u1rr3/p_ind.py; python /tmp/claude-1000/u1rr3/p_tgt.py; python /tmp/claude-1000/u1rr3/p_sib2.py
python /tmp/claude-1000/u1rr4/p_ind4.py; python /tmp/claude-1000/u1rr4/p_sib.py; python /tmp/claude-1000/u1rr4/p_tgt4.py
python /tmp/claude-1000/u1rr4/restate.py
python /tmp/claude-1000/u1rr5/probes/b5.py [r4]     # N1 and D4 (r4 = revision 4 modules)
python /tmp/claude-1000/u1rr5/probes/t5.py          # N2, N3; t5_r4.py = revision 4
python /tmp/claude-1000/u1rr5/probes/sib5b.py       # D2 full sweep (7,680 requests); sib5b_r4.py = revision 4
python /tmp/claude-1000/u1rr5/probes/ta5.py         # other therapy areas (J-d)
python3 /tmp/claude-1000/u1rr/science_diff.py <screening.json> <reference screening.json>
python3 /tmp/claude-1000/u1rr/coverage.py <screening.json ...>
python3 /tmp/claude-1000/u1rr5/probes/show.py <screening.json> <program names>   # diagnostics per program
```

Scratch workspaces (copies; the originals were not modified):
- `/tmp/claude-1000/u1rr5/ws_copy`: a fresh CLDN18.2 screen, export (`out.xlsx`) and memo (`memo.md`).
- `/tmp/claude-1000/u1rr5/ws_r4_e2e_all`: REVIEW4's `ws_e2e_all`, re-screened at HEAD (D1 check).
- `/tmp/claude-1000/u1rr5/ws_e2e_all5`: the CLDN18.2 inputs, with the buyer's indications set to `[adult acute
  lymphoblastic leukemia]` and these indication cells: RC118 "Relapsed ALL in adults", Q-1802 "ALL RELAPSED",
  TQB2103 "ALL in children", VBC108 "Relapsed or refractory ALL in adults", AK132 "RELAPSED ALL" (N1).
- `/tmp/claude-1000/u1rr5/ws_e2e_gas5`: the CLDN18.2 inputs with these cells: SG1906 target "not CLDN18.2; HER2
  positive or negative", AK132 target "CLDN18.2 negative, positive for CD47" (N2), and RC118 indication "Stage IV
  gastric cancer" (D2 control: UNDER_REQUESTED_PARENT). The workbook is `e2e_gas5/out.xlsx`.
- Inputs for both are in `/tmp/claude-1000/u1rr5/e2e_all5/` and `/tmp/claude-1000/u1rr5/e2e_gas5/`.
- Equivalence result: `/tmp/claude-1000/u1rr5/equiv.log`.
