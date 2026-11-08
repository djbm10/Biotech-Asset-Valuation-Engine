# Cycle U1 revision 7: seventh adversarial review

INTERNAL DEVELOPMENT. This is an AI-simulated adversarial review. It is not human or independent validation, and
nothing in it is an approval.

**Reviewed:** HEAD `d6d2d7f` on `dealscreen-mvp` in `/home/djmann/projects/bve-b8`, read-only (U1 revision 7
committed together with R1 revision 13). U1 revision 6 is `7a62efd`; its U1 modules are identical at `55ac585`.
Among the U1 modules, `git diff 55ac585 d6d2d7f` changes only `diagnostics.py` and `indication_relations.py`.
`workbook.py`, `memo.py`, `screening.py` and `facts.py` are not touched by `d6d2d7f`. The `cli/dealscreen.py`
change in `d6d2d7f` is rights-only.
**Criteria:** `ACCEPTANCE.md` with its revision notes (including the revision-7 note), `MEASUREMENT.md`,
`REVIEW6.md` and `REVIEW6_RESPONSE.md`.

Every number below was recomputed by running code, unless it is marked "read, not re-run". Scratch files, probe
scripts and workspaces are in `/tmp/claude-1000/u1rr7/`.

Abbreviations:
- `dg` = `bve.dealscreen.diagnostics`; `ir` = `bve.dealscreen.indication_relations`.
- `GAS` = the CLDN18.2 request `["gastric adenocarcinoma", "gastroesophageal junction adenocarcinoma"]`.
- `UC` = `["ulcerative colitis"]`; `MG` = `["myasthenia gravis"]`; `ALL-A` = `["adult acute lymphoblastic leukemia"]`.
- `VORP3` = REVIEW6's fictional required target (label "Vorpin 3.1"), with a fictional reader that knows `KLX9`.
- "rev6" = revision 6's two U1 modules, loaded side by side from `git show 55ac585:…` (`/tmp/claude-1000/u1rr7/rev6/`).
- "E2E" = confirmed through `bve-dealscreen import`, `import-rights` and `screen` (plus `export` and `memo`), on a
  workspace built from the CLDN18.2 inputs with some cells edited (see Reproduction).

## Verdict in one paragraph

Revision 7 changes no science, and coverage is still complete. Every input REVIEW6 listed for E1–E7 now gives the
expected output, including REVIEW6's own E2E workspaces re-screened at HEAD. U1-1 to U1-6 are met.

**U1-7 is still not met.** E1 is fixed only on one of the paths that reads a name:
1. **F1 (high): E1 survives on the other paths.** The "or" split runs only when the screen's own reading of the
   untouched name says "coordination expanded". It does not run when U1's own clean-up makes the name readable,
   for example by removing a leading qualifier or reading a British spelling. It is also abandoned when one piece is
   a qualifier. In those cases U1 still classes the whole name by its right-hand disease. Two E2E memos list five
   cells that name the requested indication under "a disease neither requested nor a subtype of one". Examples:
   "Locally advanced or metastatic gastric adenocarcinoma or NSCLC", "Gastric adenocarcinoma or oesophageal
   adenocarcinoma", "Gastric adenocarcinoma, metastatic, or NSCLC", "Moderate or severe ulcerative colitis or
   Crohn's disease" and "Relapsed or refractory ulcerative colitis or Crohn's disease".
2. **F2 (medium; new in revision 7):** the split looks up a bare stage or grade piece ("Stage III", "stage IV", "I")
   on its own. The NCIt index reads "stage iii" as the stage III concepts of unrelated organs. So "Stage III or stage
   IV gastric cancer" changes from revision 6's UNDER_REQUESTED_PARENT to DIFFERENT_DISEASE. The sentence says it
   "reads as Masaoka-Koga Stage III; Stage III Head and Neck Cutaneous Squamous Cell Carcinoma; Stage III Pancreatic
   Cancer; … Stage III Testicular Cancer …". Confirmed E2E.
3. **F3 (medium; new in revision 7):** when one piece is unread, the record is classed UNREADABLE, the lowest class,
   whose memo label is "no name the NCIt authority reads". This happens even when another piece reads as the
   requested indication. Confirmed E2E. The unread pieces are often not names at all ("adult", "China", "HER2+",
   "Operable", "2 follicular lymphoma", "IBD (ulcerative colitis"), but the sentence calls them "names in its 'or'
   list".
4. **F4 (medium; new in revision 7):** adding "absent" to the words before a symbol lets another target's absence
   negate the required target. "HER2 absent CLDN18.2 positive" → "states it is not CLDN18.2". Confirmed E2E.

## Verdict per criterion

| AC | Verdict | Evidence |
|---|---|---|
| U1-1 coverage | **Met** | `coverage.py` (re-run): `fin13_ws` 38/38; `xv13f` c5_heldout 28/28, fcrn_v1 28/28, fcrn_v2 28/28, synthetic_200 20/20. My E2E workspaces: `ws_e2e_gas7` 41/41, `ws_e2e_uc7` 53/53, `ws_e2e_gas7b` (indication rows checked). REVIEW6's workspaces re-screened at HEAD (`r6_gas6` 41/41, `r6_uc6` 52/52). Missing 0 and extra 0 everywhere. |
| U1-2 authorities only | **Met (letter), with notes** | I grepped the revision-7 additions for landscape words (gastr, claudin, cldn, gej, stomach, fcrn, myasthen, tigit, zolbet, pancrea, junction, esophag, oesoph, lymphoblastic, leuk, crohn, colitis, her2, pd-l1, cd3, cd47, klx, vorp, ALL, UC, cidp, nsclc). The only hits are comments and docstrings. The new word lists (`_STATE_ROLES`, `_TUMOUR_HEADS`, the cohort words in `_STATE_END`, `_PLURAL_HEADS`) are generic. Note: F2 and part of F6 come from looking up a fragment ("Stage III", "GC", "MDS", "Localized cancer") in the NCIt index. The authority answers that lookup, but the fragment is not a name the record states. |
| U1-3 no change to science | **Met** | `science_diff.py`: `fin13_ws` vs `baseline/screening_R1.json` shows 13 of 62 programs changed, all in `transaction` only; disposition, rank, decisions, machine_recommendation and transaction_rank are unchanged, and the top level is equal. **Attribution:** with `external_id` and `related_deal_id` removed from both sides (`probes/txdiff.py`), 11 of the 13 are identical. The other two (Zolbetuximab, IMAB362) are REVIEW6's R1 rows. A screen of a copy of `fin13_ws` with `screening.diagnose` stubbed out (`nou1.py`) is science-identical to `fin13_ws`, transactions included; the only differing key is `unknown_diagnostics`. The same stub on my two E2E workspaces changes only `unknown_diagnostics`. `fin13_ws` is science-identical to `after_v13/screening_R1v13.json` and byte-identical to `after/screening_u1.json`. A fresh screen of a copy of `fin13_ws` is byte-identical. So the 13 programs listed in `after/measurement.json` come from R1, as the response says. Held-out: `xv13f` vs `xv10` and vs `xv12f`: 0 differing per-program keys in all four landscapes. vs `xv8` (no U1): 0 science fields; only `unknown_diagnostics` differs. Cycle-4 equivalence (`equivalence.main()` in-process, output to scratch): 4/4 `byte_identical: true`, `fast_path: true`. The tracked `equivalence_result.json` md5 is unchanged. |
| U1-4 held-back tests | **Met as written; insufficient in substance** | `python -m pytest tests/dealscreen -q -p no:cacheprovider`: **1,726 passed**, 5 warnings, 194 s. The revision-7 block tests REVIEW6's rows. The only "qualifier list" test (`test_r7_e1_qualifier_lists_and_unread_lists_keep_their_reading`) uses names with no second disease. No test puts a leading qualifier coordination or a British spelling before a two-disease list (F1), a stage or grade coordination (F2), a partly read list that holds the request (F3), or "absent" after another target (F4). |
| U1-5 surfaces | **Met** | A regenerated memo from a copy of `fin13_ws` is identical to `after/memo_u1.md`. A regenerated workbook is cell-identical to `after/u1_cldn18.xlsx` on all 9 sheets, apart from the README timestamp. `after/` is current at HEAD. The `unknown_diagnostics` in `after/screening_u1.json` are identical to revision 6's, and `unknown_actions.csv` is unchanged since `7a62efd`. F1 and F2 show in the Diligence sheet and the memo's indication group of the E2E workspaces. |
| U1-6 per program vs reference | **Met as measured; the harm is still reachable (F1)** | Re-run from `reference_calls.csv` (names matched without the parenthesised code): 29 reference-IN programs matched (13 ELIGIBLE, 15 UNRESOLVED, 1 EXCLUDED: LCB02A, disclosed). No gastric or GEJ name is DIFFERENT_DISEASE. SOT102 ("Pancreatic Cancer") is DIFFERENT_DISEASE and is reported. But F1 produces the forbidden outcome as soon as a reference-IN record writes "Locally advanced or metastatic gastric adenocarcinoma or <another disease>", "Gastric adenocarcinoma, metastatic, or <another disease>" or "Gastric adenocarcinoma or oesophageal adenocarcinoma" (E2E: SOT102, RC118, Q-1802). |
| U1-7 adversarial review | **Not met** | F1 (high) and F2–F4 (medium) are confirmed end to end. I found no hidden UNKNOWN, no stray diagnostic, no scope or recommendation wording and no change to science. |

## Status of REVIEW6's findings

Inputs: REVIEW6's probes (`/tmp/claude-1000/u1rr6b/probes/i6.py`, `i6b.py`, `i6c.py`, `misc6.py`, `sib6.py`,
`sites6.py`, `t6.py`), the stalled revision-6 review's `bk6.py`, REVIEW5's `b5.py`, `t5.py` and `ta5.py`,
REVIEW4's `p_ind4.py`, `p_sib.py`, `p_tgt4.py` and `restate.py`, the third reviewer's `p_ind.py`, `p_tgt.py` and
`p_sib2.py`, and the second reviewer's `p1–p10.py`. All were re-run unchanged from the repository root and diffed
against REVIEW6's saved outputs (`/tmp/claude-1000/u1rr7/out/`):
- Identical: p1–p3, p5–p10, `r3_p_sib2`, `r3_p_tgt`, `p_sib`, `restate`, `sib6`, `sites6`, `b5`, `ta5`.
- p4: the same lines in a different order (identical when sorted).
- Changed exactly on the E1–E7 rows: `i6`, `i6b`, `i6c`, `misc6`, `bk6`, `t5`, `t6`, `p_tgt4`, `p_ind4`, `r3_p_ind`.
  The extra `bk6` changes are "AN cancer" → UNREADABLE and "MILD disease" → BROADER_THAN_REQUESTED ("Disease or
  Disorder"). Both are fair.

REVIEW6's E2E workspaces, copied and re-screened at HEAD (`/tmp/claude-1000/u1rr7/r6_gas6`, `r6_uc6`):
- SOT102, Q-1802 and VBC108 (GAS) are AMBIGUOUS_NAME, naming Gastric Adenocarcinoma (requested) and the other
  disease.
- RC118 "Adult ALL disease" is UNREADABLE.
- SG1906 is SOURCE_NAMES_OTHER_TARGETS with "('CLDN18.2 negative' states it is not CLDN18.2)".
- AK132 "non–CLDN18.2" is SOURCE_STATES_NOT_REQUIRED_TARGET.
- TQB2103 "CLDN18.2 negative and/or positive" names the target, with 'positive' also on record.
- UC: SOT102 is AMBIGUOUS_NAME; Q-1802 is UNREADABLE, naming 'UC' as unread; VBC108 is ELIGIBLE (J-a).

All of this is as the response states.

| Id | Status | Input → output at HEAD |
|---|---|---|
| E1 two-disease "or" name classed by one half | **Partly fixed** | Fixed for all 11 rows of the response's table, unit and E2E (above). **Not fixed** when U1's own clean-up makes the name readable, or when one piece is a qualifier or generic word: see F1. **New errors** from the split: F2 and F3. |
| E2 another target's "positive" cancels the negation | **Fixed for REVIEW6's inputs; residue F5** | `t6`: "VORP3.1 negative, positive KLX9 expression", "… pos. KLX9", "… positive (KLX9)", "… positive in KLX9 cohort" → SOURCE_NAMES_OTHER_TARGETS with the negation. "VORP3.1 negative or positive for KLX9" and "… / positive for KLX9" → SOURCE_STATES_NOT_REQUIRED_TARGET. E2E SG1906 (above). Residue: in the unsplit cases the sentence ends "the record names no other target the authority reads", which is false when the other target is readable (F5). |
| E3 both states joined by "and/or", "+", "\|", a dash, doubled space or a parenthesis | **Fixed** | All 9 rows of REVIEW6 → SOURCE_NAMES_REQUIRED_TARGET (`t6`); TQB2103 E2E. Declared residue still open: a second state followed by a non-cohort word is a negation. "VORP3.1 negative or positive tumors", "… in all lines", "… negative and positive arms" and "… neg/pos (all comers)" → "states it is not VORP3.1". The response calls this an understatement. The sentence says the opposite of the record, so I call it a low misstatement, declared. |
| E4 Unicode dashes | **Fixed** | All REVIEW6 rows → STATES_NOT, including "not–VORP3.1". AK132 E2E. |
| E5 "ALL" before a singular head | **Fixed** | All 13 `i6` rows and 16 `bk6` rows → UNREADABLE; controls "ALL cancers", "ALL solid tumors", "ALL COMERS", "ALL tumors" stay BASKET. RC118 E2E. |
| E6 absence words; "negative or low" order | **Fixed; new regression F4** | "not expressed", "expression absent", "absent X" → STATES_NOT. "negative or low" and "low or negative" → both SOURCE_NAMES_REQUIRED_TARGET. But "absent" before a symbol also takes another target's absence (F4). |
| E7 state word after a site | **Fixed; side effect labelled J-c** | All 5 rows → NAMES_REQUESTED_SITE (`misc6`). "Gastric therapy-resistant" and "gastric outlet obstruction" are still not a site. |

## Defects in revision 7, ranked by how much they could mislead

### F1 (high; E1 residue). The "or" split never runs on U1's own clean-up path, and a qualifier piece abandons it: a record naming the requested indication is still called a different disease

How it happens:
- **The clean-up path never splits.** `ir._raw_lookup` calls `_conjuncts` only when the screen's reading of the
  untouched name gives codes and says "coordination expanded". When the screen reads nothing, U1 runs its own
  clean-up: a British spelling is read as American, or a leading qualifier is removed. Then it calls
  `_screen_readings(cleaned)` and returns its codes without splitting.
- **A leading qualifier coordination mangles the name.** For a leading qualifier coordination ("Locally advanced or
  metastatic …", "Moderate or severe …", "Relapsed or refractory …"), the clean-up removes the first qualifier and
  leaves "or metastatic gastric adenocarcinoma or NSCLC". The screen reads that as NSCLC alone.
- **A qualifier piece abandons the split.** `_conjuncts` returns None when any piece is a qualifier or a generic
  word ("metastatic", "refractory", "recurrent", "cancer", "tumor"). The code then falls back to the screen's
  one-half reading.

| Request | Record name | HEAD (= rev6) | Expected |
|---|---|---|---|
| GAS | "Locally advanced or metastatic gastric adenocarcinoma or NSCLC" (**E2E** SOT102; Diligence and memo) | DIFFERENT_DISEASE: "reads as Lung Non-Small Cell Carcinoma (NCIt) once 'locally advanced' removed and coordination expanded, a clean-up the gate does not apply, neither a requested indication nor a subtype of one, although it names gastric" | AMBIGUOUS_NAME naming Gastric Adenocarcinoma (requested) and NSCLC |
| GAS | "Gastric adenocarcinoma or oesophageal adenocarcinoma" (**E2E** Q-1802) | DIFFERENT_DISEASE: "reads as Esophageal Adenocarcinoma … once British spelling read as American and coordination expanded …" | as above |
| GAS | "Gastric adenocarcinoma, metastatic, or NSCLC" (**E2E** RC118); also ", refractory,", ", recurrent,", ", cancer,", ", tumor," | DIFFERENT_DISEASE: "reads as Lung Non-Small Cell Carcinoma … once coordination expanded" | as above |
| GAS | "Advanced or metastatic …", "Unresectable or metastatic …", "Recurrent or metastatic …", "Relapsed or refractory gastric adenocarcinoma or NSCLC" | DIFFERENT_DISEASE (NSCLC only) | as above |
| UC | "Moderate or severe ulcerative colitis or Crohn's disease" (**E2E** SOT102), "Mild or moderate …", "Relapsed or refractory …" (**E2E** Q-1802) | DIFFERENT_DISEASE: "reads as Crohn Disease (NCIt) once 'moderate' removed and coordination expanded …" | AMBIGUOUS_NAME naming UC (requested) and Crohn Disease |
| MG | "Relapsed or refractory myasthenia gravis or CIDP", "Moderate or severe myasthenia gravis or CIDP" | DIFFERENT_DISEASE (CIDP) | as above |
| ALL-A | "Relapsed or refractory adult ALL or AML" | DIFFERENT_DISEASE (AML) | as above |
| AML request | "Relapsed or refractory ALL or AML" | READS_AS_REQUESTED: "reads as Acute Myeloid Leukemia … a requested indication or a subtype" (the ALL half is dropped: an overstatement) | AMBIGUOUS_NAME naming both |
| controls | "Moderate to severe UC or Crohn's disease", "Refractory myasthenia gravis or CIDP", "Advanced gastric adenocarcinoma or advanced NSCLC", "Metastatic gastric adenocarcinoma or NSCLC" | AMBIGUOUS_NAME (correct: the screen's own reading expands the coordination) | — |

- **Why it misleads:** this is E1 itself, the outcome U1-6 forbids, on very common trial-condition wording.
  "Locally advanced or metastatic X", "Relapsed or refractory X" and "Moderate(ly) or severe(ly) active X" are
  standard, and "oesophageal" is the usual spelling in EU and UK sources.
  - In the E2E GAS memo (`e2e_gas7/memo.md`, line 47), RC118, SOT102 and Q-1802 are listed under "a disease neither
    requested nor a subtype of one". Each of them names gastric adenocarcinoma.
  - In the UC memo, SOT102 and Q-1802 fall in that group's "(+10 more)".
  - Revision 6 gave the same output on every row (`probes/cmp67.py`). So this is not a regression, but revision 7's
    claim "U1 never classes a name from a reading of half of it" (`REVIEW6_RESPONSE.md` §1) does not hold.
- **Fix:** split on the record's own "or" list whatever path read the name. That means after U1's clean-up too, and
  on the original text, not on a clean-up that has eaten one half of a qualifier coordination. Fold a qualifier
  piece into the piece after it ("locally advanced or metastatic gastric adenocarcinoma" is one piece) instead of
  abandoning the split. Never return DIFFERENT_DISEASE, or "neither a requested indication", from a reading whose
  steps include "coordination expanded" unless every piece was read. Add the rows above as tests.

### F2 (medium; new in revision 7). A stage, grade or number piece is looked up alone, and NCIt's bare stage index puts unrelated organs' cancers into the sentence

`_conjuncts` looks up each piece with `_lookup`. The NCIt index holds "stage iii", "stage iv", "stage i" and so on as
keys for the stage concepts of many organs. So a piece that is only a stage reads as "Stage III Pancreatic Cancer",
"Stage III Lung Cancer", "Stage III Testicular Cancer" and others. The head-borrowing fallback ("Stage III" + "gastric
cancer") is tried only when the piece reads as nothing, so it never runs here. The screen's own coordination reading
has a depth and generic guard (`indications._specific`); `_conjuncts` does not.

| Request | Record name | rev6 | HEAD |
|---|---|---|---|
| GAS | "Stage III or stage IV gastric cancer" (**E2E** SOT102, `ws_e2e_gas7b`) | UNDER_REQUESTED_PARENT: "reads as Stage IV Gastric Cancer AJCC v7; Stage III Gastric Cancer AJCC v7 …" | DIFFERENT_DISEASE: "reads as Masaoka-Koga Stage III; Stage III Head and Neck Cutaneous Squamous Cell Carcinoma AJCC v8; Stage III Pancreatic Cancer AJCC v8; Stage III Lung Cancer AJCC v8; Stage III Uterine Corpus Carcinoma or Carcinosarcoma AJCC v8; Stage III Renal Cell Cancer AJCC v8; Ann Arbor Stage III Grade 1 Follicular Lymphoma; Stage III Testicular Cancer AJCC v6 and v7; Stage IV Gastric Cancer AJCC v7 …"; memo: "a disease neither requested nor a subtype of one" |
| GAS | "Stage IIIB or stage IV gastric cancer" (**E2E** RC118) | UNDER_REQUESTED_PARENT | DIFFERENT_DISEASE: "Stage IIIB Lung Cancer AJCC v8; Pathologic Stage IIIB Cutaneous Melanoma AJCC v8; Stage IIIB Testicular Cancer …" |
| GAS | "Stage IV or recurrent gastric cancer" (**E2E** Q-1802) | UNDER_REQUESTED_PARENT | AMBIGUOUS_NAME listing seven organs' stage IV concepts, with the note "'AJCC v8' is part of NCIt's label; the record states no edition" repeated six times |
| GAS | "Gastric adenocarcinoma, stage IV, or NSCLC" (**E2E** VBC108, `ws_e2e_gas7`), "Gastric adenocarcinoma, I, or NSCLC" | DIFFERENT_DISEASE (NSCLC) | AMBIGUOUS_NAME listing 9 concepts, 7 of them other organs' stage IV (stage I) concepts |
| GAS | "Stage III or IV gastric cancer" | UNDER_REQUESTED_PARENT | NAMES_REQUESTED_SITE, with the stage III concepts listed as read and 'IV gastric cancer' as unread |
| NSCLC | "Stage I or II NSCLC", "Stage III or IV NSCLC" (unit; the gate passes these, so no diagnostic is shown) | READS_AS_REQUESTED | UNREADABLE, listing Masaoka-Koga, head and neck, pancreatic, renal and testicular stage concepts |
| FL | "Grade 1 or 2 follicular lymphoma" (unit; gate passes) | READS_AS_REQUESTED | UNREADABLE: "does not read '2 follicular lymphoma'" |

- **Why it misleads:** the sentence names diseases the record never mentions as readings of it, attributed to "NCIt".
  It also demotes a correct UNDER_REQUESTED_PARENT to DIFFERENT_DISEASE. "Stage III or IV" and "stage IIIB or IV"
  are among the most common oncology condition strings. The output is obviously odd, which limits the harm.
- **Fix:** never look up a piece that is only a stage, grade, number, qualifier or population word. Attach it to the
  head of the next piece ("Stage III" + "gastric cancer"), or keep the screen's reading. Apply the screen's
  `_specific` guard to each piece's reading. De-duplicate notes.

### F3 (medium; new in revision 7). A partly read list that contains the request is classed UNREADABLE ("no name the NCIt authority reads"), the lowest class; and the "unread names" are often not names

`classify_name` returns NAMES_REQUESTED_SITE if a requested site word is present, and UNREADABLE otherwise, whenever
any piece is unread. It does this whatever the read pieces are. UNREADABLE is last in `ORDER`, after
DIFFERENT_DISEASE, and its summary is "no name the NCIt authority reads". `_OR_JOIN` also splits at every comma, so
modifiers become "names".

| Request | Record name | HEAD |
|---|---|---|
| UC | "Ulcerative colitis, pouchitis or Crohn's disease" (**E2E** VBC108, `ws_e2e_uc7`; memo: "no name the NCIt authority reads: RC118, VBC108, AMG 910") | UNREADABLE: "… it reads Ulcerative Colitis (requested or a subtype); Crohn Disease (not requested) and does not read 'pouchitis'" |
| UC | "IBD (ulcerative colitis or Crohn's disease)" (**E2E** RC118) | UNREADABLE: "… reads Crohn Disease (not requested) and does not read 'IBD (ulcerative colitis'". The quote is broken at the parenthesis and the requested name is not read. |
| MG | "Myasthenia gravis, AChR+, or CIDP", "Myasthenia gravis, LEMS or CIDP" | UNREADABLE, reading Myasthenia Gravis (requested) |
| GAS | "Gastric adenocarcinoma, adult, or NSCLC" / ", China," / ", HER2+," / ", 2L," / ", Phase 2," / ", monotherapy," / ", other," | NAMES_REQUESTED_SITE: "… does not read 'China'" (etc.), calling a country, a biomarker or a line of therapy one of "the names in its 'or' list" |
| RA (unit) | "Juvenile or adult rheumatoid arthritis" | UNREADABLE, reading Juvenile Rheumatoid Arthritis (requested) |
| T2D (unit) | "Obesity or type 2 diabetes" | UNREADABLE, reading Type 2 Diabetes Mellitus (requested) |

- **Why it misleads:** the class label and the memo group say the authority reads nothing. The sentence says it reads
  the requested indication. In the memo the program sorts below the different diseases. Revision 6 gave DIFFERENT_DISEASE
  for the first three rows, which was worse, so this is a partial improvement with a new misstatement.
- **Fix:** when a read piece is requested (or a subtype), do not use UNREADABLE. Use AMBIGUOUS_NAME with the
  unread piece named, or a class of its own with an honest summary. Split at commas only between pieces that are
  themselves disease names. Strip parentheses before quoting a piece.

### F4 (medium; new in revision 7). "absent" before a symbol negates the required target when the absence belongs to the target before it

`_NEGATED` gained "absent" (E6). It matches any "absent" directly before the required symbol, including one that
ends another target's phrase.

| Target cell | HEAD | rev6 | Expected |
|---|---|---|---|
| "HER2 absent CLDN18.2 positive" (**E2E** TQB2103, `ws_e2e_gas7`) | SOURCE_STATES_NOT_REQUIRED_TARGET: "'HER2 absent CLDN18.2 positive' states it is not CLDN18.2; the record names no other target the authority reads" | names CLDN18 | names CLDN18; HER2 shown as another target |
| "PD-L1 absent CLDN18.2 high", "KLX9 absent VORP3.1 positive", "KLX9-absent VORP3.1-high" | STATES_NOT | names the target | as above |
| controls: "CLDN18.2 positive, HER2 absent", "VORP3.1 high; KLX9 absent", "KLX9 not expressed VORP3.1 positive" | names the target (correct) | — | — |

- **Why it misleads:** this is REVIEW2's N6 harm, the exact opposite of the record. It also hides the other target.
  "<marker> absent <target> positive" without a separator is uncommon, which limits the reach.
- **Fix:** read "absent" as a negation only after the symbol, or before it only at the start of the part.

### F5 (low-medium; E2 residue). "The record names no other target the authority reads" is false when the other target is inside the unsplit part

| Target cell | HEAD |
|---|---|
| "CLDN18.2 negative or positive for HER2" (**E2E** SG1906), "CLDN18.2 negative / positive for PD-L1" | STATES_NOT: "… states it is not CLDN18.2; the record names no other target the authority reads". The real reader reads "HER2" as ERBB2 (cell "HER2" → "names HER2 (ERBB2)"). |
| "CLDN18.2 negative HER2 neg/pos", "VORP3.1 negative KLX9 positive or negative", "VORP3.1 negative - positive KLX9" | the same; the first also quotes 'CLDN18.2 negative HER2 neg' and drops '/pos' |

- The class is right (the record negates the required target). The closing clause hides a target the record names.
- **Fix:** read target symbols inside a negated part too, or drop the clause when the part holds a second symbol.

### F6 (low). The split reads fragments the record does not state as names

- **Head borrowing has no specificity guard.** "Localized or metastatic prostate cancer" reads 'Localized' as
  'Localized cancer' → Localized Malignant Neoplasm (the site is dropped). Unit-level; the gate passes it for a
  prostate request.
- **Acronym pieces bring in the index's other meanings.** "Gastric adenocarcinoma or GC" → "… Gonorrhea (not
  requested)". "MDS or AML" → "Dystonia 11, Myoclonic (not requested); Myelodysplastic Syndrome …". This is
  literally the authority's index, but now attributed to the record. Judgement whether to keep.
- **A whole piece is unread when one modifier blocks it.** "Intestinal or diffuse type gastric adenocarcinoma" →
  "does not read 'diffuse type gastric adenocarcinoma'", although NCIt has Gastric Diffuse Adenocarcinoma ("Diffuse
  or intestinal gastric adenocarcinoma" reads both). Revision 6 said READS_AS_REQUESTED; the gate passes it (E2E
  VBC108 in `ws_e2e_gas7b` is ELIGIBLE), so no diagnostic is shown.

### Cosmetic

- Repeated notes: "'AJCC v8' is part of NCIt's label; the record states no edition" appears once per concept, up to
  six times in one sentence (F2 rows).
- "also on record: 'pos' (not read as a target: 'pos')" treats a state word as a candidate target ("CLDN18.2
  neg/pos", "VORP3.1 negative, high").
- "'not VORP3.1' names VORP3 (Vorpin 3.1)" for "not VORP3.1, positive": a true reading of an odd cell, but an odd
  quote.

## Judgement calls (labelled; not counted as defects)

- **J-a (unchanged, outside U1).** The screen's coordination reading is lossy and asymmetric. VBC108 "Crohn's disease
  or ulcerative colitis" still passes the UC gate (`r6_uc6`, ELIGIBLE). U1 now describes it correctly where it
  shows a diagnostic.
- **J-b. Sibling and restatement rules.** The code is unchanged since revision 5 or 6. `sib6`, `p_sib`, `p_sib2` and
  `restate` are identical to REVIEW6's outputs. I did not repeat the full sweep. Through the new split, a stage
  sibling beside another disease is DIFFERENT_DISEASE ("Stage IV gastric cancer or NSCLC": "reads as Stage IV
  Gastric Cancer AJCC v7; Lung Non-Small Cell Carcinoma …, neither a requested indication nor a subtype of one,
  although it names gastric"). The sentence is literally true, but it loses the UNDER_REQUESTED_PARENT reading that
  the stage piece has alone.
- **J-c. E7 site rule side effect.** A state word before a tumour head now keeps the word before it as the site,
  including a metastasis site:
  - "Liver metastatic cancer" and "Liver metastatic carcinoma" (HCC request) → NAMES_REQUESTED_SITE "names liver".
  - "Lung metastatic carcinoma", "Lung metastatic tumours" and "Lung metastatic cancer from colorectal primary"
    (NSCLC request) → "names lung".
  - "Liver metastatic disease" and "Liver metastatic colorectal cancer" stay UNREADABLE.

  The sentence is literally true (the record names the organ), but these are usually cancers metastatic *to* that
  organ. `sites6` (70 requests) is unchanged.
- **J-d. Placeholders and basket/acronym rule.** Placeholders are unchanged (`misc6` rows identical). "MILD disease"
  → BROADER_THAN_REQUESTED ("Disease or Disorder" once 'mild' removed) and "AN cancer" → UNREADABLE. Both are
  acceptable.

## Reading `after/` as a BD analyst

`after/` is current at HEAD: the memo is identical and the workbook is cell-identical apart from the timestamp. The
38 CLDN18.2 actions are unchanged from revision 6. No CLDN18.2 record contains a two-disease "or" list, a stage
coordination or "absent", so none of F1–F5 appears in the shipped landscape.

REVIEW4–6's reading still holds:
- Each action states what is on record, its class, the one cited fact that decides the gate, and the `assert` field.
- The PD-1 rows name TIGIT, CTLA-4 and 'PD-1'.
- The six basket rows name both requested indications.
- The memo's single-gate list has no scope or recommendation words.

Still less useful:
- The repeated "The gate never fails on this evidence…" tail.
- DR30303's "not a name the NCIt authority can read".
- "'PD-1' not read by the target authority" (an authority gap).

Nothing is hidden: every UNKNOWN on a non-excluded program has its diagnostic, here and in every E2E workspace.

The risk an analyst would not see is F1. On the E2E landscape, three programs whose records name gastric
adenocarcinoma are filed among "different diseases". The Diligence sheet sentence even explains how the
misreading happened ("once 'locally advanced' removed and coordination expanded, a clean-up the gate does not
apply"), but not that half the name was dropped. F2 is visible but confusing: a gastric stage record is said to read
as pancreatic, lung and testicular cancer.

## What I could not check

- Whether the revision-7 tests were written before the code was tuned.
- Workbooks and memos for the held-out landscapes; I read their `screening.json` only. For my E2E workspaces I
  generated both workbooks and all three memos. The `.docx` memos were generated but not opened.
- Domain judgements used to rate reach, not checked against an authority:
  - how often vendor cells write "Locally advanced or metastatic X or Y", "Stage III or IV X", British spellings or
    "<marker> absent <target>";
  - that "Liver metastatic cancer" usually means a metastasis to the liver.

  The NCIt claims (index keys "stage iii"/"stage iv", "GC", "MDS"; readings of UC, Crohn Disease, CIDP, NSCLC,
  Esophageal Adenocarcinoma) were checked through the U1 code against the frozen authority.
- F1–F6 fixes were not implemented or tested.
- I did not repeat REVIEW5's full stage-sibling sweep (code unchanged).
- The rights code (under concurrent review): not touched. I used it only to attribute the transaction changes.

## Reproduction

```
cd /home/djmann/projects/bve-b8 && . .venv/bin/activate && export TMPDIR=$HOME/.cache/dealscreen_suite
# run every probe from the repository root (the S&E target snapshot path is relative)
python -m pytest tests/dealscreen -q -p no:cacheprovider        # 1726 passed, 5 warnings, 194 s
P=/tmp/claude-1000/u1rr7/probes
python $P/o7.py [GAS UC MG ...]   # ~200 "or" names across 19 requests
python $P/q7.py                   # F1 rows
python $P/h7.py                   # F2, F6, J-c rows
python $P/cmp67.py                # revision 6 vs HEAD side by side (rev6 modules in /tmp/claude-1000/u1rr7/rev6/)
python $P/t7.py                   # F4, F5, E3 residue (fictional and real reader)
python3 $P/txdiff.py <fin13_ws/screening.json> research/dealscreen_unknown_actions_v1/baseline/screening_R1.json
python /tmp/claude-1000/u1rr6b/probes/nou1.py <copy of a workspace>   # screen with U1 stubbed out
python3 /tmp/claude-1000/u1rr/science_diff.py <screening.json> <reference screening.json>
python3 /tmp/claude-1000/u1rr/coverage.py <screening.json ...>
python3 /tmp/claude-1000/u1rr5/probes/show.py <screening.json> <program names>
```

Scratch workspaces (copies; the originals were not modified):
- `ws_copy`: a fresh CLDN18.2 screen (byte-identical to `fin13_ws`), with `out.xlsx` and `memo.md`.
- `ws_nou1`, `nou1_gas7`, `nou1_uc7`: screens with `diagnose` stubbed out.
- `r6_gas6`, `r6_uc6`: REVIEW6's E2E workspaces re-screened at HEAD.
- `ws_e2e_gas7` (inputs, `out.xlsx` and `memo.md` in `e2e_gas7/`): GAS request, with these cells:
  - SOT102 "Locally advanced or metastatic gastric adenocarcinoma or NSCLC"
  - Q-1802 "Gastric adenocarcinoma or oesophageal adenocarcinoma"
  - VBC108 "Gastric adenocarcinoma, stage IV, or NSCLC"
  - RC118 "Gastric adenocarcinoma, metastatic, or NSCLC"
  - targets TQB2103 "HER2 absent CLDN18.2 positive" and SG1906 "CLDN18.2 negative or positive for HER2"
- `ws_e2e_gas7b` (`e2e_gas7b/`): GAS request, with these cells:
  - SOT102 "Stage III or stage IV gastric cancer"
  - Q-1802 "Stage IV or recurrent gastric cancer"
  - RC118 "Stage IIIB or stage IV gastric cancer"
  - VBC108 "Intestinal or diffuse type gastric adenocarcinoma"
- `ws_e2e_uc7` (`e2e_uc7/`): UC request, with these cells:
  - SOT102 "Moderate or severe ulcerative colitis or Crohn's disease"
  - Q-1802 "Relapsed or refractory ulcerative colitis or Crohn's disease"
  - VBC108 "Ulcerative colitis, pouchitis or Crohn's disease"
  - RC118 "IBD (ulcerative colitis or Crohn's disease)"
- Equivalence: `/tmp/claude-1000/u1rr7/equiv.log`.
