# Cycle U1 revision 3: third adversarial review

INTERNAL DEVELOPMENT. This is an AI-simulated adversarial review. It is not human or independent validation.

**Reviewed:** HEAD `f5ab4c4` on `dealscreen-mvp` in `/home/djmann/projects/bve-b8` (R1 revision 8 plus U1 revision 3),
read-only. **Criteria:** `ACCEPTANCE.md` with its revision notes, `MEASUREMENT.md`, `REVIEW2.md`, `REVIEW2_RESPONSE.md`.

Every number below was recomputed by running code unless marked "read, not re-run". Scratch files and probe scripts are
in `/tmp/claude-1000/u1rr3/`. `dg` = `bve.dealscreen.diagnostics`, `ir` = `bve.dealscreen.indication_relations`.
`GAS` = the CLDN18.2 request `["gastric adenocarcinoma", "gastroesophageal junction adenocarcinoma"]`.

## Verdict in one paragraph

Revision 3 still changes no science, coverage is still complete, and the shipped CLDN18.2 outputs contain no false
program-level statement that I could find. N1, N2, N6, N8, N10 and N12 are fixed as stated. N3, N5, N7, N9, N11 and
N13 are mostly fixed, with residues. **U1-7 is still not met.** On held-out inputs, the two new rules misstate the
record:

1. **The new sibling rule (`UNDER_REQUESTED_PARENT`) overreaches.** It is meant for stage concepts, but it admits any
   concept under any by-site direct parent of the request. Its summary, "a subtype of a broader parent of the request,
   naming a requested site", is shown for records that name no requested site ("Mycosis fungoides" for a cutaneous
   melanoma request) and for another organ's cancer ("Gallbladder adenocarcinoma, gastric foveolar type" for the
   CLDN18.2 request; confirmed end to end). It also lifts lymphomas, sarcomas and other histologies above BASKET.
2. **The new negation rule reads common qualifiers as negations.** "CLDN18.2-low", "CLDN18.2 low-expressing",
   "CLDN18.2 null-Fc" and "CLDN18.2 previously validated" each give "states it is not CLDN18.2". That is the opposite
   of the record, and was confirmed end to end. The disclosed safe direction ("never 'names the required target'" for
   other negation wordings) is also false: "lacking CLDN18.2 expression" gives "names the required target".
3. **The N4 acronym fix breaks baskets.** A capitalised Roman numeral is now treated as an acronym the authority
   reads. "Stage IV Solid Tumours" drops from BASKET to UNREADABLE (confirmed end to end), and "Advanced CANCER"
   becomes OVERLAPS_REQUESTED.

## Verdict per criterion

| AC | Verdict | Evidence |
|---|---|---|
| U1-1 coverage | **Met** | Measured with `coverage.py` on the shipped `u1_r3b_ws` and the four `u1_r3_xv` workspaces: CLDN18.2 38/38, c5_heldout 28/28, fcrn_v1 28/28, fcrn_v2 28/28, synthetic_200 20/20. None has an extra diagnostic or a missing one. A fresh `screen` of a copy of `u1_r3b_ws` gives a byte-identical `screening.json`. Every action names the value as written, or "nothing on record" / "No … on record". |
| U1-2 authorities only | **Met (letter), with notes** | A grep of the U1 modules, `screening.py`, `facts.py`, `workbook.py`, `memo.py` and `cli/dealscreen.py` for landscape words (gastr, claudin, cldn, gej, stomach, fcrn, myasthenia, tigit, zolbet, pancrea, junction, rilveg, volrus, esophag) finds only docstrings, comments, and the generic spelling pair `("oesophag","esophag")`. Several rules are DealScreen word lists, not authority facts: `_NOT_IN_SITE` (the lineage list), `_ROLE_AFTER`, `_NEGATION_WORDS`, `_PLACEHOLDER_WORDS` and `_SPELLING`. Defects D2 and D3 come from two of these lists. |
| U1-3 no change to science | **Met** | `science_diff.py` compared the fresh CLDN18.2 screen with `baseline/screening_R1.json`: 0 of 62 programs differ on disposition, rank, decisions, machine_recommendation, transaction or transaction_rank. The only per-program key that differs is `unknown_diagnostics`, and the top level is equal. Held-out (`u1_r3_xv` vs `rights_v1/xv8`): 0 of 40, 40, 40 and 192 programs differ. Equivalence: re-run, byte-identical with the fast path on 4 of 4 cases. |
| U1-4 held-back tests | **Met as written; insufficient in substance** | `tests/dealscreen`: 1,052 passed, 5 warnings (re-run, 82 s). `test_unknown_actions.py` has 69 test functions. The three N1 tests check stage concepts and one other-site sibling only. No test checks a sibling under a "Malignant <site> Neoplasm" parent, a sibling of another lineage, or a sibling whose record names no site (D1). The N7 test (line 582) fixes "ABC1.2 low" as a negation, which is the D2 defect. No test covers Roman numerals in a basket name (D3). |
| U1-5 surfaces | **Met** | The regenerated workbook is cell-identical to `after/u1_cldn18.xlsx` on every sheet except README, where only the timestamp differs. The regenerated memo is identical to `after/memo_u1.md` apart from the timestamp. Diligence keeps "(S&E: …)" beside the DealScreen action. A search of all 142 diagnostics in the five landscapes found no scope or recommendation wording (in/out of scope, exclude, eligible, recommend, prioriti, pursue, promising, should, attractive, relevant, drop). The memo's single-gate line now names SOT102 and Givastomig. The basket group still ends "(+1 more)" (J4). |
| U1-6 per program vs reference | **Met as measured** | Recomputed against `reference_calls.csv`: 15 reference-IN programs are UNRESOLVED, plus LCB02A, which is EXCLUDED (disclosed). No reference-IN gastric or GEJ name is DIFFERENT_DISEASE. SOT102 (record: "Pancreatic Cancer" only) is DIFFERENT_DISEASE and is reported. All 6 basket programs (RC118, VBC108, SG1906, TQB2103, AK132, Q-1802) are BASKET, with an action that names both requested indications. Rilvegostomig and volrustomig name TIGIT and CTLA-4 plus 'PD-1'; RC148 names 'PD-1'. IBI343 is READS_AS_REQUESTED, CMG901, AZD5863, SYSA1801 and AMG 910 are NAMES_REQUESTED_SITE, DA-3501 and EO-3021 are BROADER, and Givastomig is AMBIGUOUS_NAME_ALL_BROADER. |
| U1-7 adversarial review | **Not met** | D1–D3 below misstate the record on held-out inputs, and D1–D3 and D5–D6 were confirmed end to end through `import` and `screen`. D1 and D2 come from revision 3's new rules, and D3 is a regression caused by the N4 fix. I found no hidden UNKNOWN and no change to science. |

## Status of the second review's findings (N1–N13)

Inputs are the second reviewer's probes `/tmp/claude-1000/u1rr/probes/p1–p10.py`, re-run unchanged against HEAD
(outputs in `/tmp/claude-1000/u1rr3/p*.out`), plus my own probes.

| Id | Status | Input → output (HEAD) |
|---|---|---|
| N1 stage concepts | **Fixed, but the rule overreaches (D1)** | `dg.indication_diagnostic(["Stage IV gastric cancer"], GAS)` → UNDER_REQUESTED_PARENT, "… ('AJCC v7' is part of NCIt's label; the record states no edition), which NCIt files under a broader parent … and which names gastric". "Stage III gastric cancer" and "Stage IV colorectal cancer" (colorectal adenocarcinoma request) give the same. "Pancreatic adenocarcinoma" stays DIFFERENT_DISEASE. Word order still matters: "Gastric cancer stage IV" → NAMES_REQUESTED_SITE. |
| N2 restatement | **Fixed** | `ir.restatement`: pnh, astrocytoma, mesothelioma, endometrial cancer and gastric cancer → None. The action for `pnh` says "the buyer chooses among Periventricular Nodular Heterotopia; Paroxysmal Nocturnal Hemoglobinuria", and `_warn_unread_request` says "(its readings: …; choose one)" (read in code). glioblastoma → 'GBM'. |
| N3 multi-word sites, spelling | **Mostly fixed; residue (D5)** | "Gastroesophageal Junction Cancer", "Gastro-esophageal Junction Cancer", "Esophagogastric junction cancer", "Oesophagogastric junction cancer" and "Recurrent head and neck cancer, platinum-refractory" → NAMES_REQUESTED_SITE. `us_spelling("Gastroesophageal")` is unchanged. But **"Gastro-oesophageal junction cancer" → UNREADABLE**, because the "after o" branch never fires (D5). |
| N4 acronym basket | **Fixed for ALL; regression (D3)** | "ALL", "Adult ALL", "ALL (adult)" → READS_AS_REQUESTED. "Relapsed/refractory ALL" and "ALL, children" → UNREADABLE. "Stage IV solid tumours" → UNREADABLE (D3). |
| N5 non-site words | **Mostly fixed; residue (D7)** | All seven rows of the second review now give UNREADABLE or DIFFERENT_DISEASE without "a requested site" (p6). Still a site: "post transplant lymphoproliferative". |
| N6 negated mention | **Fixed for the listed forms; over-applied (D2)** | "KLX9 (VORP3.1 negative)" → SOURCE_NAMES_OTHER_TARGETS, "names KLX9 … ('VORP3.1 negative' states it is not VORP3.1)". "CLDN18.2-negative" and "not CLDN18.2" → SOURCE_STATES_NOT_REQUIRED_TARGET. "CLDN18.2-low" gives the same (D2). |
| N7 isoform, suffix, after-symbol negation | **Fixed** | "VORP3, isoform 2" → "isoform 2 of VORP3, not isoform 1". "VORP3-AS1" → may name. "non-expressing", "(formerly)" and "knockout" → states it is not. |
| N8 placeholders | **Fixed** | "Novel ADC target", "Proprietary antigen X", "Target 1", "Target A" → UNREADABLE placeholder. |
| N9 misquoted fragments | **Fixed for the listed cases; residue (D9)** | "CLDN6/9" is quoted whole and "N/A" is a placeholder. "CLDN18.2/4-1BB", "CLDN18.2 + PD-L1", "CLDN18.2 and PD-L1" and "CLDN18.2, PD-L1" do not mention the partner. "PD-1/PD-L1" is quoted as one unread name. |
| N10 "metastases of" | **Fixed** | "Peritoneal metastases of gastric cancer" → NAMES_REQUESTED_SITE. "Liver metastases from colorectal cancer" names colorectal (colorectal request) and not liver (HCC request). |
| N11 wording | **Mostly fixed; residue (D8)** | Labels are listed once and "'relapsed' set aside as a disease-state word" is in words. But `lymphoma` → "for example 'lymphomatous'" (an adjective; it was in N11's own list) and `neuroblastoma` → "'neural crest tumor malignant'" (an inverted index key). |
| N12 empty request | **Fixed** | `indication_diagnostic(names, [])` → OTHER, "The buyer file requests no indication, so no record name is compared." |
| N13 memo "3 more" | **Fixed as stated** | SOT102 and Givastomig are named. The basket group ends "(+1 more)", because names per phrase are still capped (disclosed). |

The second review's judgement calls J-a (lexical leads such as "Stomach flu"), J-b and J-c are unchanged
(re-run, p9).

## Defects in revision 3, ranked by how much they could mislead

"E2E" means confirmed through `bve-dealscreen import` and `screen` on `/tmp/claude-1000/u1rr3/ws_e2e`. That workspace
is the CLDN18.2 inputs with five cells edited (`/tmp/claude-1000/u1rr3/e2e_in/landscape.csv`).

### D1 (medium-high, new rule). `UNDER_REQUESTED_PARENT` is given to other organs, other lineages and records that name no requested site

The rule (`ir._sibling`) needs only two things: a direct parent of the request that has any by-site ancestor, and a
concept name that contains a request site phrase. Almost every NCIt neoplasm concept has a by-site ancestor, so
"never a morphology parent" is enforced only for pure-morphology parents such as "Adenocarcinoma". A parent such as
"Digestive System Adenocarcinoma", "Malignant Skin Neoplasm" or "Malignant Bile Duct Neoplasm" admits everything under
it. Across all NCIt concepts there are 78 siblings for gastric adenocarcinoma, 275 for cutaneous melanoma, 89 for
esophageal adenocarcinoma and 46 for renal cell carcinoma (`sib.py`, `sib_many.out`).

| Request | Record name | Output | What is wrong |
|---|---|---|---|
| GAS | "Gallbladder adenocarcinoma, gastric foveolar type" (**E2E**, SOT102) | UNDER_REQUESTED_PARENT, summary "a subtype of a broader parent of the request, naming a requested site", "… and which names gastric" | A gallbladder cancer. "gastric" is a histologic type descriptor, not its site. The response says "a sibling that names another site stays a different disease". |
| cutaneous melanoma | "Mycosis fungoides" | UNDER_REQUESTED_PARENT, "… and which names a requested site" | The record names no site. A T-cell lymphoma. |
| cutaneous melanoma | "Cutaneous T-cell lymphoma", "Basal cell carcinoma of the skin", "Non-melanoma skin cancer" | UNDER_REQUESTED_PARENT | Other lineages or histologies. The last one excludes the request in its own words. |
| cholangiocarcinoma | "Extrahepatic bile duct lymphoma", "Extrahepatic bile duct Kaposi sarcoma" | UNDER_REQUESTED_PARENT | Lymphoma and sarcoma placed above BASKET as a near-lead. |
| renal cell carcinoma | "Collecting duct carcinoma" | "… and which names a requested site" | The record names no site. |
| renal cell carcinoma | "Renal pelvis urothelial carcinoma", "Stage IV renal pelvis cancer" | "… names renal" | Upper-tract urothelial cancer: a different site (renal pelvis) and histology. |
| hepatocellular carcinoma | "Mucoepidermoid intrahepatic cholangiocarcinoma" | "… names a requested site" | The record names no site. Plain "Intrahepatic cholangiocarcinoma" → DIFFERENT_DISEASE, so the class depends on which synonyms NCIt holds. |

- **Inconsistent with revision 2's adopted J1.** For GAS, "Gastric lymphoma", "Gastric MALT lymphoma" and "Gastric
  GIST" stay DIFFERENT_DISEASE, because the request's parents are "Gastric Carcinoma" and "Digestive System
  Adenocarcinoma". When the parent is "Malignant <site> Neoplasm", the same kind of concept becomes
  UNDER_REQUESTED_PARENT. Whether a lymphoma counts as a near-lead depends on how NCIt shapes the request's parent.
- **Why it misleads:** the class is ordered above BASKET and DIFFERENT_DISEASE, and its summary appears on the
  Screening sheet and in the memo grouping. For the rows above, "naming a requested site" is false of the record.
- **Expected:**
  - Use the record's own site hits for the "names" clause and the summary. When the record names no requested site,
    do not say it does.
  - Admit a sibling only when it adds no morphology the request lacks. Every morphology-tree ancestor of the sibling
    should be an ancestor of, or equal to, a morphology ancestor of the request. Stage concepts sit under "Carcinoma",
    an ancestor of the request, so they pass. Squamous, neuroendocrine, lymphoma and sarcoma siblings, and the
    gallbladder foveolar case under "Digestive System Adenocarcinoma" via a gallbladder parent, would not.
  - Also apply the existing role-word rule to "<site> foveolar type".

### D2 (medium, new rule). Expression and engineering qualifiers are read as "states it is not the required target"

`_NEGATION_WORDS` after the symbol includes `low`, `loss`, `null`, `previously`, `former`, `ko`, `deficient`. Real
CLDN18.2 reader (`p_tgt.py`), each `target_diagnostic` → SOURCE_STATES_NOT_REQUIRED_TARGET, summary "states it is not
the required target", record "'…' states it is not CLDN18.2":

- "CLDN18.2-low" (**E2E**, RC118 target cell "Claudin 18.2-low": "'Claudin 18.2-low' states it is not Claudin 18.2")
- "CLDN18.2 low-expressing", "CLDN18.2 low and high", "CLDN18.2-low/high"
- "CLDN18.2 null-Fc" (an Fc-silenced antibody)
- "CLDN18.2 previously validated", "CLDN18.2 former Ganymed target"
- "CLDN18.2 loss-of-function", "CLDN18.2 KO-resistant", "CLDN18.2 deficient tumors"

The same rule reads near-identical text the other way:
- "low CLDN18.2" and "CLDN18.2 (low expression)" → SOURCE_NAMES_REQUIRED_TARGET.

**Why it misleads:** a program directed at CLDN18.2-low tumours is targeting CLDN18.2. The statement asserts the
opposite of the record, which is the error N6 was meant to remove, in the other direction. The N7 test at line 582
fixes "ABC1.2 low" as a negation.

**Expected:** treat only explicit absence as negation: "negative", "neg", "non-expressing", "knockout", "not", "no",
"non-". Treat expression levels ("low", "high") as naming the target. "previously" and "former" count only when no
current symbol follows. Never treat "null" as a negation when it is a hyphenated modifier ("null-Fc").

### D3 (medium, regression from the N4 fix). Roman numerals and capitalised words switch off BASKET

`ir.is_basket` now returns False when any capitalised token is a name the index reads. The index maps "IV", "III",
"II" and "I" to edition-specific stage concepts, "AST" to Cutaneous Spitz Melanocytoma, and "CANCER" to Malignant
Neoplasm.

| Record name (GAS) | Output | Expected |
|---|---|---|
| "Stage IV Solid Tumours" (**E2E**, VBC108) | UNREADABLE, "is not a name the NCIt authority can read" | BASKET (every token is a basket word, as before the N4 fix; inferred from the code, not re-run on revision 2) |
| "STAGE IV SOLID TUMORS", "Stage III/IV solid tumors", "Advanced Solid Tumors; Stage IV" | UNREADABLE | BASKET |
| "Solid Tumors (ALL COMERS)" | UNREADABLE | basket ("all comers") |
| "Advanced CANCER" | OVERLAPS_REQUESTED, "reads as Advanced Malignant Neoplasm … shares subtypes with it" | BASKET (lower case "Advanced cancer" → BASKET) |

- **Why it misleads:** a basket program drops below DIFFERENT_DISEASE to the bottom class, and loses the basket
  action U1-6 requires. "Advanced CANCER" in an all-caps vendor export is promoted to a class above BROADER.
- **Expected:** apply the acronym exception only to a token that is not itself a basket word or Roman numeral, and
  only when the token's reading is not a stage concept or `Malignant Neoplasm`. Or require the capitalised token to
  read as exactly one concept.

### D4 (low-medium). The response's disclosed safe direction for other negation wordings is false

REVIEW2_RESPONSE §4.4 says a negation written another way is "'may name' at worst, never 'names the required
target'". In fact:
- "lacking CLDN18.2 expression" → SOURCE_NAMES_REQUIRED_TARGET, "names CLDN18 (Claudin 18.2)".
- "CLDN18.2-independent" → SOURCE_NAMES_REQUIRED_TARGET.

The rule as built is not wrong for every input, but the disclosure misstates its failure mode.

### D5 (low). "After o" British spelling never applies; "Gastro-oesophageal junction cancer" is UNREADABLE

`us_spelling` uses the lookbehind `(?<![A-Za-np-z])` together with `re.IGNORECASE`. Under IGNORECASE, `[A-Z]` also
matches "o", so the "after o" branch never fires:
- `ir.us_spelling("tracheooesophageal")`, `ir.us_spelling("hypoglycaemia")` and `ir.us_spelling("Gastrooesophageal")`
  are returned unchanged. The docstring cites the first two as working.
- `sites_named` joins the hyphen before the spelling clean-up. As a result, "Gastro-oesophageal junction cancer"
  (**E2E**, AK132) → UNREADABLE, while "Gastro-esophageal junction cancer" → NAMES_REQUESTED_SITE.

This is an understatement, in the safe direction. REVIEW2_RESPONSE N3 implies the British form is handled.
**Fix:** drop IGNORECASE from the lookbehind, for example `(?<![A-Za-np-z])` on a case-folded string with an
explicit `[a-np-z]`, or apply the spelling after joining.

### D6 (low). One role-word occurrence blocks every occurrence of the same site

`sites_named` adds a phrase to `blocked` when any occurrence is followed by a role word, then removes it from all hits.
- "Gastric cancer with gastric outlet obstruction" (**E2E**, TQB2103) → UNREADABLE.
- "Gastric adenocarcinoma, gastric-type mucin" → UNREADABLE.

Expected: NAMES_REQUESTED_SITE, because the first "gastric" is the disease site. **Fix:** block per occurrence, not
per phrase.

### D7 (low, N5 residue). "post transplant lymphoproliferative" is a site

Request `post-transplant lymphoproliferative disorder`, record "Post-transplant lymphoproliferative disease, EBV+" →
"names post transplant lymphoproliferative, a requested site". The class is a fair lead, but "site" is false. The
second review's p5 sweep also still lists "hematologic" (22 concepts) as a site.

### D8 (low, N11 residue). Restatements that are not disease names

- Request `lymphoma` → "for example 'lymphomatous', which the authority reads as Lymphoma alone".
- Request `neuroblastoma` → "for example 'neural crest tumor malignant'".

N11 claimed restatements are "a label, an acronym in capitals, or a clean name, never an index key". The N11 test
does not include `lymphoma`.

### D9 (low, N9 residue). A second target is not mentioned

- "CLDN18.2/4-1BB", "CLDN18.2 x 4-1BB", "CLDN18.2 + PD-L1", "CLDN18.2 and PD-L1" and "CLDN18.2, PD-L1" → "names
  CLDN18 …" with no "also on record". "4-1BB/CLDN18.2" does list '4-1BB', so the output depends on the order.
- "PD-1/PD-L1" is quoted as one unread name.

The class is right; the partner is hidden.

## Judgement calls (labelled; not counted as defects)

- **J1. Same-site siblings of another histology.** For GAS, "Gastric squamous cell carcinoma", "Gastric neuroendocrine
  carcinoma" and "Gastric choriocarcinoma" are UNDER_REQUESTED_PARENT. For an esophageal adenocarcinoma request,
  "Esophageal squamous cell carcinoma" is the same. The NCIt statement is true, but for a histology-specific buyer
  these are different diseases ranked above BASKET. For a lung adenocarcinoma request, "Lung squamous cell carcinoma"
  stays DIFFERENT_DISEASE, because of NCIt's parent shape. The D1 morphology fix would also resolve this.
- **J2. The reading of the request is never shown.** Request `gc` resolves to Gonorrhea, and then "'Gastric cancer'
  reads as Gastric Carcinoma …, neither a requested indication nor a subtype of one", with the fact "a cited source
  naming gc". The gate does the same (S&E). But the diagnostic hides the request's reading, and no `screen` warning
  fires, because the request resolves. Suggest: "requested 'gc' is read as Gonorrhea (NCIt)" whenever the label
  differs from the text.
- **J3. The record excludes the requested histology.** "Gastric cancer (non-adenocarcinoma)", "Non-adenocarcinoma
  lung cancer" and "Stomach neoplasms except adenocarcinoma" → NAMES_REQUESTED_SITE. Each is true, but the record
  rules out the request (as in REVIEW2 J-b).
- **J4. Memo.** The basket group still ends "(+1 more)" (disclosed). IBI343's lead sentence reads only the GEJ concept
  "once 'unresectable' removed and coordination expanded", although the name also names gastric. This is true, but
  partial.
- **J5. Hand-made word lists (U1-2).** The lineage, role, negation and placeholder lists are generic, not landscape
  words, but they are DealScreen's, not the authority's. D2 and D3 show that they carry most of the remaining risk.

## Reading `after/` as a BD analyst

- **Specific and true.** Each of the 38 CLDN18.2 actions names what is on record, the class, and the one fact that
  decides the gate. Examples:
  - RC118: "'Advanced Solid Tumor' names no disease or site (a basket) (and 3 other name(s) on record). What would
    pass the gate: a cited source naming gastric adenocarcinoma or gastroesophageal junction adenocarcinoma …".
  - CMG901: "'Gastroesophageal Junction Cancer' names gastroesophageal junction, a requested site …".
  - The three PD-1 rows name TIGIT, CTLA-4 and 'PD-1'.
  - The "Imaging agent" modality rows give the allowed modalities.
- **Less useful.**
  - The "What would pass the gate … The gate never fails on this evidence, so a program for another indication stays
    open." tail repeats on 24 rows.
  - "'Malignant Neoplasm of Digestive System' is not a name the NCIt authority can read" is true, but it hides an
    obvious broader reading (Malignant Digestive System Neoplasm).
  - DA-3501's "GastroEsophageal Cancer" is UNREADABLE at the name level. This is an understatement and does not
    change the program class.
- **Nothing hidden.** Every UNKNOWN on a non-excluded program has its row. The memo's single-gate list names 15
  programs, with one basket name capped.

## What I could not check

- Whether the unit tests were written before the code was tuned.
- Workbooks and memos for the held-out landscapes; for those, only `screening.json` was read.
- The `.docx` memo was regenerated but not opened.
- External facts: that "CLDN18.2-low" and "null-Fc" are common vendor phrasings, and that mycosis fungoides is a
  T-cell lymphoma, are domain knowledge. The NCIt structure claims (parents, sibling counts, index readings of "IV"
  and "CANCER") were checked against the authority.
- Behaviour of revision 2 on D3's inputs. The revision 2 stage directory now holds revision 3 code, so the regression
  is inferred from `_BASKET_EXTRA` ("stage", "iv") and the second review's description of revision 2's `is_basket`.
- Whether the rights code under concurrent review affects any U1 surface (not in scope; not touched).

## Equivalence

I re-ran the cycle-4 harness by calling `equivalence.main()` in-process with output to `/tmp/claude-1000/u1rr3/equiv`.
This does not write the tracked `equivalence_result.json`, which was already modified in the working tree before this
review and was not touched by it. Result: `byte_identical: true` and `fast_path: true` on all 4 cases
(synthetic_200, real_v1, real_v2, real_v1_with_cycle1_assertions). The result is saved at
`/tmp/claude-1000/u1rr3/equiv.json`. U1-3 is met on every check.

## Reproduction

```
cd /home/djmann/projects/bve-b8 && . .venv/bin/activate && export TMPDIR=$HOME/.cache/dealscreen_suite
python -m pytest tests/dealscreen -q -p no:cacheprovider        # 1052 passed, 5 warnings
for p in p1 p2 p3 p6 p7 p8 p9 p10; do python /tmp/claude-1000/u1rr/probes/$p.py; done   # second review probes
python /tmp/claude-1000/u1rr3/sib.py "gastric adenocarcinoma" "cholangiocarcinoma" "cutaneous melanoma"   # D1 sweep
python /tmp/claude-1000/u1rr3/p_sib2.py      # D1 record names
python /tmp/claude-1000/u1rr3/p_tgt.py       # D2, D4, D9 (real CLDN18.2 reader)
python /tmp/claude-1000/u1rr3/p_ind.py       # D3, D6, D7, D8, J2, J3
python3 /tmp/claude-1000/u1rr/science_diff.py <screening.json> <reference screening.json>
python3 /tmp/claude-1000/u1rr/coverage.py <screening.json ...>
```

Scratch workspaces (copies; the originals were not modified):
- `/tmp/claude-1000/u1rr3/ws_copy`: a fresh CLDN18.2 screen, export and memo.
- `/tmp/claude-1000/u1rr3/ws_e2e`: D1, D2, D3, D5 and D6 end to end.
