# Cycle U1 revision 4: fourth adversarial review

INTERNAL DEVELOPMENT. This is an AI-simulated adversarial review. It is not human or independent validation, and
nothing in it is an approval.

**Reviewed:** HEAD `b3e3fe9` on `dealscreen-mvp` in `/home/djmann/projects/bve-b8`, read-only. U1 revision 4 is
`04faab7`. `git diff --stat 04faab7 b3e3fe9` shows that R1 revision 9 touched only `rights_*.py` under `src/`.
**Criteria:** `ACCEPTANCE.md` with its revision notes, `MEASUREMENT.md`, `REVIEW3.md` and `REVIEW3_RESPONSE.md`.

Every number below was recomputed by running code, unless it is marked "read, not re-run". Scratch files and probe
scripts are in `/tmp/claude-1000/u1rr4/`. Abbreviations:
- `dg` = `bve.dealscreen.diagnostics`; `ir` = `bve.dealscreen.indication_relations`.
- `GAS` = the CLDN18.2 request `["gastric adenocarcinoma", "gastroesophageal junction adenocarcinoma"]`.
- "E2E" = confirmed through `bve-dealscreen import` and `screen` on a workspace built from the CLDN18.2 inputs with
  cells edited (`/tmp/claude-1000/u1rr4/e2e_gas`, `/tmp/claude-1000/u1rr4/e2e_all`; details under Reproduction).
- "rev3" = revision 3's modules, loaded side by side from `git show f5ab4c4:…` (`/tmp/claude-1000/u1rr4/rev3/`).

## Verdict in one paragraph

Revision 4 changes no science. Coverage is complete. The shipped CLDN18.2 outputs are byte- or cell-identical to a
fresh run, and I found no false program-level statement in them. D2, D4, D5, D6, D7 and D8 of REVIEW3 are fixed.
D1 is mostly fixed: lymphomas, other organs and records that name no site are out of the sibling class. D3 and D9
are partly fixed.

**U1-7 is still not met.** Two medium defects remain:
1. **The D3 fix overcorrects (a regression from revision 3).** In text with two or more capitalised words, "ALL" is
   no longer read as an acronym. For an adult-ALL request, "RELAPSED ALL" and "PEDIATRIC ALL" are now said to
   "name no disease or site (a basket)" (E2E). Revision 3 read them as Acute Lymphoblastic Leukemia (broader) and as
   Childhood ALL. The same text in mixed case ("Relapsed ALL") is still read correctly.
2. **The stage-only sibling rule still admits other lineages.** NCIt files neuroendocrine, GIST, small-cell and
   sarcoma lineages under by-site nodes, so the "no non-site category the request lacks" test does not see them.
   - "Stage IV gastric neuroendocrine tumor" (GAS, E2E), "Stage IV pancreatic neuroendocrine tumor" (PDAC request),
     "Stage IV small cell lung cancer" (lung adenocarcinoma request) and "Stage IV uterine corpus leiomyosarcoma"
     (endometrioid adenocarcinoma request) are `UNDER_REQUESTED_PARENT`.
   - The same diseases without a stage ("Gastric neuroendocrine carcinoma", "Pancreatic Neuroendocrine Tumor",
     "Extensive-stage small cell lung cancer") are `DIFFERENT_DISEASE`.
   - The code's docstring says a sarcoma stays a different disease. For these stage concepts it does not.

## Verdict per criterion

| AC | Verdict | Evidence |
|---|---|---|
| U1-1 coverage | **Met** | `coverage.py` (second reviewer's script, re-run) on a fresh screen of a copy of `after9f_ws`, and on `rights_v1/xv9f/*`: CLDN18.2 38/38, c5_heldout 28/28, fcrn_v1 28/28, fcrn_v2 28/28, synthetic_200 20/20. Missing 0, extra 0. The fresh `screening.json` is byte-identical to `after9f_ws/screening.json` and to `after/screening_u1.json`. Every action names the value as written, or "nothing on record" / "No … on record". |
| U1-2 authorities only | **Met (letter), with notes** | I grepped `indication_relations.py` and `diagnostics.py` for landscape words (gastr, claudin, cldn, gej, stomach, fcrn, myasthen, tigit, zolbet, pancrea, junction, rilveg, volrus, esophag, oesoph, neuroendocrine, lymphoblastic, tl1a, ibd). The hits are docstrings and comments, the generic spelling pair `("oesophag","esophag")`, and the generic lineage word "neuroendocrine". `screening.py`, `facts.py`, `workbook.py`, `memo.py` and `cli/dealscreen.py` are unchanged since `f5ab4c4`. Revision 4 adds more DealScreen heuristics: the "shouting" rule, `_acronym`, the stage-label regex, `<word> type` as a role, and a list of list-separator words. D1, D4, D6 and D8 come from these (J5 of REVIEW3 still applies). |
| U1-3 no change to science | **Met** | `science_diff.py` compared the fresh CLDN18.2 screen with `baseline/screening_R1.json`. On disposition, rank, decisions, machine_recommendation, transaction and transaction_rank, 0 of 62 programs differ. The only differing per-program key is `unknown_diagnostics`, and the top level is equal. Held-out `xv9f` vs `xv8`: 0 of 40, 40, 40 and 192 programs differ. Cycle-4 equivalence: I called `equivalence.main()` in-process with output to scratch, and all 4 cases are `byte_identical: true`, `fast_path: true`. The tracked `equivalence_result.json` was checked by md5 and was not touched. |
| U1-4 held-back tests | **Met as written; insufficient in substance** | `python -m pytest tests/dealscreen -q -p no:cacheprovider`: **1,178 passed**, 5 warnings, 78 s. The response's 1,099 is at `04faab7`; R1 revision 9 added `test_rights_rereview7.py`. `test_unknown_actions.py` has 80 test functions. None covers a stage concept of another lineage under the request's site (D2), or an all-caps qualifier with "ALL" (D1). Line 539 tests only "Relapsed/refractory ALL", "ALL", "Adult ALL" and "ALL, children" in mixed case. |
| U1-5 surfaces | **Met** | Regenerated workbook vs `after/u1_cldn18.xlsx`: all 9 sheets are cell-identical except README's "Generated" timestamp. The regenerated `memo.md` is identical to `after/memo_u1.md`. Diligence keeps the S&E text beside the DealScreen action. `coverage.py`'s scope-wording search over all 142 diagnostics in five landscapes found none. |
| U1-6 per program vs reference | **Met as measured (unchanged)** | Recomputed from `reference_calls.csv` and the fresh screen. 15 reference-IN programs are UNRESOLVED; LCB02A is EXCLUDED (disclosed). No gastric or GEJ name is DIFFERENT_DISEASE. SOT102 ("Pancreatic Cancer") is DIFFERENT_DISEASE and is reported. RC118, VBC108, SG1906, TQB2103, AK132 and Q-1802 are BASKET, and the action names both requested indications. Rilvegostomig names TIGIT and 'PD-1', volrustomig names CTLA-4 and 'PD-1', and RC148 names 'PD-1'. |
| U1-7 adversarial review | **Not met** | D1 (a regression) and D2 below are confirmed end to end, and so are D3 and D4. I found no hidden UNKNOWN, no stray diagnostic and no change to science. |

## Status of the third review's findings

Inputs: the third reviewer's probes `/tmp/claude-1000/u1rr3/p_ind.py`, `p_tgt.py` and `p_sib2.py`, and the second
reviewer's `/tmp/claude-1000/u1rr/probes/p1–p10.py`. I re-ran them unchanged against HEAD and diffed the outputs
against the third review's saved outputs (`/tmp/claude-1000/u1rr4/r3_*.out` and `p*.out`).

| Id | Status | Input → output at HEAD |
|---|---|---|
| D1 sibling overreach | **Mostly fixed; residue (D2 below)** | All rows of REVIEW3 D1 and J1 are now DIFFERENT_DISEASE: Gallbladder foveolar type, Mycosis fungoides, Cutaneous T-cell lymphoma, Basal cell carcinoma of the skin, Non-melanoma skin cancer, Extrahepatic bile duct lymphoma and Kaposi sarcoma, Collecting duct carcinoma, Renal pelvis urothelial carcinoma, Stage IV renal pelvis cancer, Mucoepidermoid intrahepatic cholangiocarcinoma, Gastric squamous, neuroendocrine and choriocarcinoma, Esophageal SCC and Ovarian clear cell. "although it names <site>" appears only when the record names the site. Kept as intended: "Stage IV gastric cancer", "Stage IV colorectal cancer", "Stage IV pancreatic neuroendocrine…" (see D2), "Stage D prostate cancer" and "Stage IV anal cancer". **Residue:** stage concepts of other lineages under the same site (D2). |
| D2 qualifiers as negation | **Fixed** | "CLDN18.2-low", "low-expressing", "null-Fc", "previously validated", "former Ganymed target", "loss-of-function", "KO-resistant" and "deficient tumors" → SOURCE_NAMES_REQUIRED_TARGET. "VORP3.1 low" (p7) → names. |
| D3 capitals switch off BASKET | **Partly; regression (D1 below)** | "Stage IV Solid Tumours", "STAGE IV SOLID TUMORS", "Solid Tumors (ALL COMERS)" and "Advanced CANCER" → BASKET. But an all-caps qualifier with "ALL" → BASKET (D1). A basket with its own acronym in parentheses still is not one (D4; existed in revision 3). |
| D4 other negation wordings | **Fixed as stated** | "lacking CLDN18.2 expression" and "CLDN18.2-independent" → SOURCE_STATES_NOT_REQUIRED_TARGET. New over-reach in D7 below. |
| D5 "after o" spelling | **Fixed** | `us_spelling`: "tracheooesophageal" → "tracheoesophageal", "hypoglycaemia" → "hypoglycemia". "Gastro-oesophageal junction cancer" and its all-caps form → NAMES_REQUESTED_SITE. "tracheoesophageal" is unchanged. |
| D6 role word per occurrence | **Fixed** | "Gastric cancer with gastric outlet obstruction" and "Gastric adenocarcinoma, gastric-type mucin" → NAMES_REQUESTED_SITE. The new "<word> type" role costs some recall (D8). |
| D7 transplant states | **Fixed** | "Post-transplant lymphoproliferative disease, EBV+" → UNREADABLE. "hematologic" is no longer a site (p5: 22 → 0 concepts). This understates in the safe direction for requests such as "hematologic neoplasm with germline predisposition" (p6). |
| D8 restatements | **Fixed for the cited cases; one residue (D9)** | `lymphoma`, `neuroblastoma` and `osteosarcoma` → no example; `glioblastoma` → 'GBM'. Across every NCIt label the gate does not read as its own concept, 30 restatements are offered. 29 are acronyms; one is a word ('Neoplasm' → 'TUMOR'). |
| D9 partner target hidden | **Partly fixed; residue (D6 below)** | "CLDN18.2/4-1BB", "4-1BB/CLDN18.2", "CLDN18.2 x 4-1BB", " + ", " and ", ", ", " & " and " plus " now list the partner. "PD-1/PD-L1" is split into PD-L1 (CD274) and 'PD-1'. Still hidden: "CLDN18.2 / CD3" (spaced slash; it was in REVIEW3's own probe list), " or ", " vs " and " → ". |
| J2 request reading not shown | **Unchanged (disclosed)** | `read_request(["gc"])` → Gonorrhea (C92950); no note. |
| J3 record excludes the requested histology | **Unchanged (disclosed)** | "Gastric cancer (non-adenocarcinoma)" and "Stomach neoplasms except adenocarcinoma" → NAMES_REQUESTED_SITE. |

## Defects in revision 4, ranked by how much they could mislead

### D1 (medium; regression from the D3 fix). An all-caps qualifier makes an "ALL" record a basket

`ir.is_basket` sets `shouting` when the name has two or more capitalised words of three or more letters that are
not Roman numerals. In that case no capitalised token is treated as an acronym. "RELAPSED ALL" therefore becomes
the basket words {relapsed, all}. The authority's own reading is never consulted:
`ir._lookup("RELAPSED ALL")` returns Acute Lymphoblastic Leukemia, a reading the screen applies.

| Request | Record name | Revision 4 | Revision 3 | Expected |
|---|---|---|---|---|
| adult acute lymphoblastic leukemia | "RELAPSED ALL" (**E2E**, Q-1802) | BASKET, "names no disease or site (a basket)" | BROADER_THAN_REQUESTED | BROADER_THAN_REQUESTED |
| same | "PEDIATRIC ALL" (**E2E**, TQB2103) | BASKET | DIFFERENT_DISEASE (Childhood ALL) | DIFFERENT_DISEASE |
| same | "ALL, RELAPSED", "ADULT ALL", "ADVANCED ALL", "RELAPSED/REFRACTORY ALL" | BASKET | BROADER / UNREADABLE | not BASKET |
| childhood acute lymphoblastic leukemia | "RELAPSED ALL" | BASKET | BROADER_THAN_REQUESTED | BROADER |
| same, control | "Relapsed ALL" (**E2E**, RC118) | BROADER_THAN_REQUESTED | same | (correct) |

- **Why it misleads:** the sentence is false about the record. The class drops from BROADER to BASKET, so the memo
  puts the program in the basket group. Vendor exports in capitals are common, and "R/R ALL" is common in
  haematology.
- **Expected:** treat "ALL" as the word "all" only where it reads as one: before a basket head or "comers"
  ("ALL COMERS", "ALL SOLID TUMORS"). Alternatively, in shouted text, call a name a basket only when the screen's
  reading (`_lookup`) finds no concept, or finds only a generic one (Malignant Neoplasm, a stage concept).
  Add the rows above as tests.

### D2 (medium; residue of REVIEW3 D1). The stage-only sibling rule admits stage concepts of other lineages

`ir._sibling` requires that every ancestor of the stage concept that is not under a site be an ancestor of the
request. NCIt files "Neuroendocrine Neoplasm", "Endocrine Neoplasm", "Sarcoma", "Soft Tissue Sarcoma" and
"Leiomyosarcoma" under by-site roots ("Endocrine Neoplasm", "Connective and Soft Tissue Neoplasm"), so these
lineages are invisible to the test. The non-site ancestors of "Stage IV Pancreatic Neuroendocrine Tumor AJCC v8" are
only {C7057, Disease or Disorder, Neoplasm}. Sweep over all 2,732 NCIt stage concepts (`sib4.py`, `p_sib.py`):

| Request | Record name (resolves to one NCIt stage concept) | Output |
|---|---|---|
| GAS | "Stage IV gastric neuroendocrine tumor" (**E2E**, RC118) | UNDER_REQUESTED_PARENT, "…which NCIt files under a broader parent of a requested indication … and which names gastric" |
| GAS | "Stage III Gastric Neuroendocrine Tumor AJCC v8" | UNDER_REQUESTED_PARENT. NCIt also lists 8 "Stage … Gastric Gastrointestinal Stromal Tumor AJCC v7" siblings; the record wording "Stage IV gastric GIST" is not readable, so it gives NAMES_REQUESTED_SITE |
| pancreatic ductal adenocarcinoma | "Stage IV pancreatic neuroendocrine tumor" | UNDER_REQUESTED_PARENT, "…names pancreatic" |
| colorectal adenocarcinoma | "Stage IV colorectal neuroendocrine tumor" | UNDER_REQUESTED_PARENT |
| lung adenocarcinoma | "Stage IV small cell lung cancer" | UNDER_REQUESTED_PARENT, "…names lung" |
| endometrial endometrioid adenocarcinoma | "Stage IV uterine corpus leiomyosarcoma", "Stage IV Uterine Corpus Endometrial Stromal Sarcoma AJCC v8", "Uterine corpus leiomyosarcoma by AJCC v8 stage" | UNDER_REQUESTED_PARENT |

- Per request, the stage siblings whose own lineage is NET, GIST, small-cell or sarcoma: gastric 15 of 59,
  pancreatic 8 of 26, colorectal 14 of 44, lung 13 of 51, and the uterine leiomyosarcoma and endometrial stromal
  sarcoma groups for the endometrioid request.
- For cutaneous melanoma, the 4 "Stage … Mycosis Fungoides AJCC v7" concepts are siblings, but the record-site
  check rescues them: "Stage IV mycosis fungoides" → DIFFERENT_DISEASE.
- **Inconsistent with the same diseases without a stage.** "Pancreatic Neuroendocrine Tumor", "Gastric
  neuroendocrine carcinoma" and "Extensive-stage small cell lung cancer" are DIFFERENT_DISEASE. Adding "Stage IV"
  lifts the program above BASKET and DIFFERENT_DISEASE.
- The `_sibling` docstring says "a lymphoma, a sarcoma or another organ's cancer, stay different diseases".
  REVIEW3_RESPONSE §1 says the rule excludes any "non-site category the request lacks". Both are false for these
  inputs.
- **Why it misleads:** the NCIt sentence is literally true, but the summary on the Screening sheet and in the memo
  grouping, "a subtype of a broader parent of the request, naming a requested site", presents a NET, small-cell or
  sarcoma program as a near-lead for an adenocarcinoma buyer. That is the J1/D1 harm REVIEW3 described.
- **Expected and tested fix:** also require that every ancestor of the stage concept that the request does not share
  has "stage" in its label (that is, the only extra ancestors are the stage groupings).
  - On the 12 requests I swept, this removes every NET, GIST, small-cell, leiomyosarcoma, endometrial stromal
    sarcoma, mycosis fungoides and "Occult Lung Cancer" sibling.
  - It keeps every gastric, pancreatic, colorectal, lung, prostate, cervical, ovarian and esophageal *cancer* stage
    concept.
  - **Cost:** it also drops "Stage … Endometrial Cancer FIGO 2023", "Stage … Adult Liver Cancer AJCC v7" (HCC request)
    and "Stage … Anal Canal Cancer". Those become DIFFERENT_DISEASE, the old understatement.
  - Add the rows above as tests.

### D3 (low-medium). A record that states both expression states is read as "states it is not the target"

| Target cell | Output | Expected |
|---|---|---|
| "CLDN18.2 negative or positive" (**E2E**, SG1906) | SOURCE_STATES_NOT_REQUIRED_TARGET, "'CLDN18.2 negative or positive' states it is not CLDN18.2" | names (or may name) the target |
| "CLDN18.2 neg/pos" | "'CLDN18.2 neg' states it is not CLDN18.2"; 'pos' is not mentioned | same |
| "CLDN18.2-negative and -positive" | "'CLDN18.2-negative' states it is not CLDN18.2"; '-positive' is not mentioned | same |
| control: "CLDN18.2 positive and negative" | names the target | (correct) |

- This existed in revision 3 for the first and third rows. Revision 4's " and " split now drops the "-positive"
  part from the sentence, because the negated branch prints no notes.
- **Why it misleads:** the record says the opposite of the summary, which is the N6/D2 failure in another wording.
- **Fix:** do not call a part negated when the same value also states "positive", "pos", "+" or "high". Show the
  notes in the negated sentence too.

### D4 (low-medium; D3 residue, existed in revision 3). A basket with its own acronym in parentheses is not a basket

`is_basket` sees the acronym as a non-basket word. `_lookup` then removes it as an "acronym" and reads the rest.

| Record name (GAS) | Output | Expected |
|---|---|---|
| "Advanced solid tumors (AST)" (**E2E**, VBC108) | UNREADABLE | BASKET |
| "Advanced Cancer (AC)" | OVERLAPS_REQUESTED, "reads as Advanced Malignant Neoplasm … shares subtypes" | BASKET |
| "Malignant solid tumor (MST)" | DIFFERENT_DISEASE, "reads as Malignant Solid Neoplasm" | BASKET |
| "Solid Tumors (STs)", "Advanced malignancies (AM)" | UNREADABLE | BASKET |

- **Why it misleads:** a basket program loses the basket action that U1-6 requires. In one case it is promoted
  above BROADER.
- **Fix:** apply `_acronyms_removed` before the basket-word test.

### D5 (low). The N1 problem remains for a request without site phrases

`site_phrases("triple-negative breast carcinoma")` is empty, because "breast" sits after "negative", which is not a
generic word. As a result:
- "Stage IV breast cancer" and "Stage III breast cancer" against a TNBC request → DIFFERENT_DISEASE, "neither a
  requested indication nor a subtype of one".
- "Breast cancer" and "Metastatic breast cancer" → AMBIGUOUS_NAME_ALL_BROADER.

The NCIt sentence is true. But adding a stage moves a program from "broader" to "a disease neither requested…", the
reverse of what N1 fixed for gastric. Expected: UNDER_REQUESTED_PARENT, or at least not below BROADER. The cause is
the site-phrase boundary rule (biomarker words before the site), not the stage rule.

### D6 (low; D9 residue). A partner target is still hidden for some separators

- "CLDN18.2 / CD3" and "CLDN18.2 / 4-1BB" (`_SLASH` needs two non-space characters before the slash), "CLDN18.2 or
  PD-L1", "CLDN18.2 vs PD-L1" and "CLDN18.2 → TROP2" → "names CLDN18 …, but no target set was built from it", with no
  "also on record".
- "non-CLDN18.2 arm: PD-1" → "the record names no other target the authority reads"; 'PD-1' is not shown.
- (Existed in revision 3.) "CLDN18.1 and 18.2" → SOURCE_NAMES_OTHER_TARGETS, "names other targets only". The record
  names both isoforms. Revision 4's " and " split now quotes '18.2' as an unread name "not written as CLDN18".

E2E note: "CLDN18.2 / CD47" in AK132's target cell built a target set (gate PASS), so for that program no diagnostic
appears. The rows above are unit-level.

### D7 (low). New negation over-reach and inconsistency

- "without CLDN18.2 selection" → "states it is not CLDN18.2". Revision 3 said it names the target; the change came
  from adding "without" to `_NEGATED`.
- "No CLDN18.2 selection" (also in revision 3) → same. Both phrasings usually mean "patients not selected by
  CLDN18.2", not "not a CLDN18.2 program".
- "CLDN18.2 knockout-resistant" → states it is not CLDN18.2, while "CLDN18.2 KO-resistant" → names it (the D2 test
  case).
- "CLDN18.2 negative-selection" → states it is not.

### D8 (low; understatement from the new role rule). "<site> <word> type" blocks the disease site

"Gastric cancer type: diffuse" and "Gastric carcinoma type 2" (GAS) → UNREADABLE. Expected: NAMES_REQUESTED_SITE.
`_role_after` treats any "<site> X type" as a role, even when X is a tumour head. Restrict the role to X not in
`_BASKET_HEADS`. This errs in the safe direction.

### D9 (very low). One restatement is not an acronym

An unresolved request "Neoplasm" → "for example 'TUMOR'". The `[a-z]{2,6}` filter admits short words. The
other 29 restatements offered over all NCIt labels are acronyms (for example GBM, DLBCL, NHL, MPNST).

## Judgement calls (labelled; not counted as defects)

- **J-a (second review), unchanged.** Lexical leads still give NAMES_REQUESTED_SITE: "Dry mouth" and "Mouth ulcers"
  (oral cavity SCC request), "Dry eye disease" (ocular melanoma request) and "Stomach flu" (GAS). All existed in
  revision 3.
- **Same-node site names.** Revision 4 adds a by-site node's other single-word names to the request's site phrases.
  Over 4,000 sampled concepts, 321 gain words and 14 lose words. Most gains are true synonyms (pancreas,
  stomach, kidney, esophagus, cutaneous, cns, colonic, osseous). A few are broader than the request:
  - 'gastrointestinal' for digestive-system requests;
  - 'gynecologic' for female-reproductive requests;
  - 'pns' for "peripheral nerve".

  They name the request's own by-site node, so I count them as acceptable. All 14 losses are 'hematologic', PTLD or
  'hematopoietic and lymphatic system' (D7 of REVIEW3, intended).
- **J2, J3 of REVIEW3:** unchanged, as disclosed.
- **"Lentigo Maligna", "Occult Lung Cancer" and "Testicular … In Situ" count as stage concepts** because they sit under
  "… by AJCC vN Stage" groupings. Only "Occult Lung Cancer" reached the sibling class in my sweep. The D2 fix
  removes it.
- **Memo CLI (outside U1).** `bve-dealscreen memo --out x.docx` reports `"markdown": x.docx`: the Markdown is written
  to the .docx path, and the .docx then overwrites it. With `--out x.md`, both are written. Not a U1 surface, so it
  is not counted.

## Reading `after/` as a BD analyst

The CLDN18.2 outputs are unchanged from revision 3. REVIEW3's reading still holds:
- Each of the 38 actions says what is on record, its class and the one fact that would decide the gate.
- The three PD-1 rows name TIGIT, CTLA-4 and 'PD-1'.
- The basket rows name both requested indications.
- "Imaging agent" rows give the allowed modalities.

Less useful:
- The 24-row "The gate never fails on this evidence…" tail.
- "'Malignant Neoplasm of Digestive System' is not a name the NCIt authority can read", which hides an obvious
  broader reading.
- The memo's basket group still ends "(+1 more)".

Nothing is hidden: every UNKNOWN on a non-excluded program has its diagnostic. None of the revision 4 defects
appears in the CLDN18.2 landscape. They need inputs this landscape does not contain (all-caps ALL, stage-NET
records, acronym baskets, two-state target cells).

## What I could not check

- Whether the new tests were written before the code was tuned.
- Workbooks and memos for the held-out landscapes; for those, I read only `screening.json`. The two E2E workspaces
  were screened but not exported.
- The `.docx` memo was regenerated but not opened.
- Domain knowledge used to judge harm, not checked against an authority: that pancreatic NET, gastric NET or GIST,
  SCLC and uterine leiomyosarcoma are different diseases from the corresponding adenocarcinomas; that "ALL" in capitals
  usually means acute lymphoblastic leukemia; and that "no CLDN18.2 selection" usually means unselected patients.
  The NCIt structure claims (ancestors, stage groupings, sibling counts, index readings of "AST", "ALL" and "MILD")
  were checked against the frozen authority.
- The D2 fix was tested only on the 12 requests listed; the D1 fix was not implemented or tested.
- The rights code under concurrent review (out of scope; not touched).

## Reproduction

```
cd /home/djmann/projects/bve-b8 && . .venv/bin/activate && export TMPDIR=$HOME/.cache/dealscreen_suite
python -m pytest tests/dealscreen -q -p no:cacheprovider          # 1178 passed, 5 warnings
for p in p1 p2 p3 p4 p5 p6 p7 p8 p9 p10; do python /tmp/claude-1000/u1rr/probes/$p.py; done   # second review
python /tmp/claude-1000/u1rr3/p_ind.py; python /tmp/claude-1000/u1rr3/p_tgt.py; python /tmp/claude-1000/u1rr3/p_sib2.py
python /tmp/claude-1000/u1rr4/sib4.py "gastric adenocarcinoma" "lung adenocarcinoma" ...   # D2 sweep
python /tmp/claude-1000/u1rr4/p_sib.py       # D2 record names
python /tmp/claude-1000/u1rr4/p_ind4.py      # D4, D5, D8, J-a
python /tmp/claude-1000/u1rr4/p_tgt4.py      # D3, D6, D7 (real CLDN18.2 reader); p_tgt4_r3.py = revision 3
python /tmp/claude-1000/u1rr4/restate.py     # D9
python /tmp/claude-1000/u1rr4/site_diff.py   # site-phrase gains and losses vs revision 3
python3 /tmp/claude-1000/u1rr/science_diff.py <screening.json> <reference screening.json>
python3 /tmp/claude-1000/u1rr/coverage.py <screening.json ...>
```

Scratch workspaces (copies; the originals were not modified):
- `/tmp/claude-1000/u1rr4/ws_copy`: a fresh CLDN18.2 screen, export (`out.xlsx`) and memo (`memo.md`).
- `/tmp/claude-1000/u1rr4/ws_e2e_gas`: the CLDN18.2 inputs with four cells edited. RC118's indication is "Stage IV
  gastric neuroendocrine tumor", VBC108's indication "Advanced solid tumors (AST)", SG1906's target "CLDN18.2
  negative or positive" and AK132's target "CLDN18.2 / CD47".
- `/tmp/claude-1000/u1rr4/ws_e2e_all`: the same inputs with the buyer's `strategic_gap.indications` set to
  `[adult acute lymphoblastic leukemia]`. Q-1802's indication is "RELAPSED ALL", TQB2103's "PEDIATRIC ALL" and
  RC118's "Relapsed ALL".
- Inputs for both are in `/tmp/claude-1000/u1rr4/e2e_gas/` and `/tmp/claude-1000/u1rr4/e2e_all/`.
- Equivalence result: `/tmp/claude-1000/u1rr4/equiv.json`.
