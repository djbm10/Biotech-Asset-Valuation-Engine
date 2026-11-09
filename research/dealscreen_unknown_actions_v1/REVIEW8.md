# Cycle U1 revision 8: eighth adversarial review

INTERNAL DEVELOPMENT. This is an AI-simulated adversarial review. It is not human or independent validation, and
nothing in it is an approval.

**Reviewed:** HEAD `624b2f0` on `dealscreen-mvp` in `/home/djmann/projects/bve-b8`, read-only (U1 revision 8
committed together with R1 revision 14). U1 revision 7 is `d6d2d7f`. Among the U1 modules, `git diff d6d2d7f 624b2f0`
changes only `diagnostics.py` and `indication_relations.py`; `workbook.py`, `memo.py`, `screening.py`, `facts.py` and
`cli/dealscreen.py` are untouched by it.
**Criteria:** `ACCEPTANCE.md` with its revision notes (including the revision-8 note), `MEASUREMENT.md`,
`REVIEW7.md` and `REVIEW7_RESPONSE.md`.

Every number below was recomputed by running code unless marked "read, not re-run". Scratch files, probe scripts and
workspaces are in `/tmp/claude-1000/u1rr8/`.

Abbreviations:
- `dg` = `bve.dealscreen.diagnostics`; `ir` = `bve.dealscreen.indication_relations`.
- `GAS` = the CLDN18.2 request `["gastric adenocarcinoma", "gastroesophageal junction adenocarcinoma"]`.
- Other requests are written as their NCIt label: `CML` = chronic myeloid leukemia, `cGVHD` = chronic graft versus
  host disease, `SAA` = severe aplastic anemia, `UC` = ulcerative colitis, `T2D` = type 2 diabetes mellitus, `DHL` =
  high grade B-cell lymphoma with MYC and BCL2 or BCL6 rearrangements, `AMP` = ampulla of Vater
  pancreaticobiliary or gastric type adenocarcinoma. Each resolves to exactly one NCIt concept (`ir.read_request`).
- "rev7" = revision 7's two U1 modules loaded side by side from `git show d6d2d7f:…`
  (`/tmp/claude-1000/u1rr8/rev7/`, probe `probes/cmp78.py`).
- `[UNK]` = the gate's positive reading (name or any `indication_readings` reading, through
  `indication_compatibility.compatibility`) does not pass, so the diagnostic is shown. `[PASS]` rows show no
  diagnostic and are unit-level only.
- "E2E" = confirmed through `bve-dealscreen import`, `import-rights`, `screen`, `export` and `memo` on a workspace
  built from the `fin14_ws` inputs with some cells (and for `heme8`/`uc8` the buyer's indications) edited
  (see Reproduction).

## Verdict in one paragraph

Revision 8 changes no science and coverage is still complete. REVIEW7's F1–F5 rows all give the expected output,
unit and end to end, including REVIEW7's own E2E workspaces re-screened at HEAD. U1-1 to U1-5 are met; U1-6 is met
as measured on CLDN18.2.

**U1-7 is still not met.** The revision fixes the rows it was shown, but the new word lists and the new order of
reading create or leave misstatements one step away:
1. **D1 (high): a leading "chronic", "acute" or "severe" piece is folded as a modifier, so "Chronic or acute
   myeloid leukemia" is read by its right half only and called a different disease for a CML request.** Same for
   "Chronic or acute GVHD" (cGVHD; new in revision 8 through the new "or" strip), "Severe or non-severe aplastic
   anemia" (SAA), "Chronic or acute lymphocytic leukemia", "… pancreatitis", "… hepatitis B". E2E: three programs
   in the memo's "a disease neither requested nor a subtype of one" group name the requested indication. This is
   E1/F1's harm in another therapy area; REVIEW7's recommended guard ("never DIFFERENT_DISEASE from a coordination
   reading unless every piece was read") was not implemented.
2. **D2 (medium; new): a basket piece is "set aside as a modifier, not a name", so a basket list reads as
   requested.** "Gastric adenocarcinoma, gastroesophageal junction adenocarcinoma, or other solid tumors" (also "…
   or all comers", "… or other cancers", "… or metastatic disease", "… or pain") is READS_AS_REQUESTED, the top
   class. E2E VBC108.
3. **D3–D5 (medium):** inverted names ("Myeloid leukemia, chronic, …"; "Diabetes mellitus, type 2, …") are read as
   the broader parent; capitalised cells turn modifier words into names ("MODERATE" → Moderate COVID-19 Infection,
   "CHRONIC" → Chronic GVHD, "STAGE III" → other organs' stage III, F2 again); and "Patients with / Adult / Pediatric
   ulcerative colitis or Crohn's disease" is still UNREADABLE, reading only Crohn's (F3 residue).
4. **D6–D9 (lower):** "or" inside an NCIt proper name is now split before the clean-up (regressions on double-hit
   lymphoma, AML inv(16)/t(16;16), ampullary pancreaticobiliary-or-gastric type); the F5 fix says a negated cell
   "also names another target" when the second "symbol" is `NEGATIVE`, `NOT`, `IHC` or `GC`; the partly-read
   sentence hides its set-aside steps; therapy/line pieces are called "names".

## Verdict per criterion

| AC | Verdict | Evidence |
|---|---|---|
| U1-1 coverage | **Met** | `coverage.py`: `fin14_ws` 38/38; `xv14f` c5_heldout 28/28, fcrn_v1 28/28, fcrn_v2 28/28, synthetic_200 20/20 (104/104); my E2E `ws_gas8` 40/40, `ws_heme8` 53/53, `ws_uc8` 53/53; REVIEW7's E2E re-screened at HEAD 41/41, 40/40, 53/53. Missing 0, extra 0 everywhere. |
| U1-2 authorities only | **Met (letter), with a note** | The revision-8 `+` lines contain landscape words only in comments and docstrings (grep of gastr, cldn, gej, her2, pd-l1, klx, vorp, crohn, colitis, ALL, UC, nsclc, china, …; the `all(` hits are the Python builtin). Note: `_MODIFIER_WORDS` is generic but holds disease-defining words (`acute`, `chronic`, `severe`, `juvenile`, `type`, `grade`, `low`, `high`, `early`) and generic disease names (`pain`, `infection`, `syndrome`); D1–D3 come from that. |
| U1-3 no change to science | **Met** | `science_diff.py` `fin14_ws` vs `baseline/screening_R1.json`: 13 of 62 programs differ, all in `transaction` only; disposition, rank, decisions, machine_recommendation and transaction_rank unchanged; top level equal. `txdiff.py`: 11 of 13 identical once `external_id`/`related_deal_id` are removed; the other two (Zolbetuximab, IMAB362) are R1's (same as REVIEW7). A copy of `fin14_ws` screened with `screening.diagnose` stubbed out (`nou1.py`) differs from a fresh screen only in `unknown_diagnostics`; the fresh screen is byte-identical to `fin14_ws/screening.json` and to `after/screening_u1.json`. The same stub on my three E2E workspaces changes only `unknown_diagnostics`. Held-out `xv14f` vs `xv10`: 0 differing per-program keys in all four landscapes; vs `xv13f`: 0 (not even `unknown_diagnostics`); vs `xv8`: 0 science fields. Cycle-4 equivalence (`equivalence.main()` in-process, scratch output): 4/4 `byte_identical: true`, `fast_path: true`; tracked `equivalence_result.json` md5 unchanged (`94450c24…`). |
| U1-4 held-back tests | **Met as written; insufficient in substance** | `python -m pytest tests/dealscreen -q -p no:cacheprovider`: **1,803 passed**, 5 warnings, 135 s. The revision-8 block tests REVIEW7's rows only (gastric, UC, MG, AML; lower case). No test has a disease-defining leading modifier ("Chronic or acute X"), a basket piece in a requested list, an inverted name, a capitalised cell, a population-word list, an NCIt label containing "or", or a capitalised state word in a negated target cell. |
| U1-5 surfaces | **Met** | A fresh memo from a copy of `fin14_ws` is identical to `after/memo_u1.md`; a fresh workbook is cell-identical to `after/u1_cldn18.xlsx` on all 9 sheets apart from the README timestamp. In the E2E workspaces the Diligence "Next action", the Screening class and the memo's single-gate list all carry the revision-8 sentences (D1, D2, D4, D5 confirmed on all three surfaces). |
| U1-6 per program vs reference | **Met as measured; the harm is reachable in other therapy areas (D1) and in a GAS basket list (D2)** | Re-run from `reference_calls.csv` (names matched without the parenthesised code): all 30 reference-IN programs matched (REVIEW7 matched 29; the 30th, Spevatamig (PT886), matches when the parenthesis is stripped on both sides): 14 ELIGIBLE, 15 UNRESOLVED, 1 EXCLUDED (LCB02A, disclosed). No gastric or GEJ name of a reference-IN program is DIFFERENT_DISEASE; SOT102 ("Pancreatic Cancer") is DIFFERENT_DISEASE and reported; RC118 and the basket programs name both requested indications; RC148, Volrustomig and Rilvegostomig name PD-1 and their other targets. A GAS sweep of 8,184 generated modifier/list names (`out/sweep_gas.out`) finds no gastric name called a different disease apart from J-b (a stage concept beside another disease). |
| U1-7 adversarial review | **Not met** | D1 (high) and D2–D5 (medium) are confirmed end to end. I found no hidden UNKNOWN, no stray diagnostic, no scope or recommendation wording in any action, and no change to science. |

## Status of REVIEW7's findings

Inputs: every earlier probe re-run unchanged from the repository root and diffed against REVIEW7's saved outputs
(`/tmp/claude-1000/u1rr7/out/`, `/tmp/claude-1000/u1rr7/*.out`); new outputs in `/tmp/claude-1000/u1rr8/out/`:
- Identical: p1–p3, p5–p10, `r3_p_sib2`, `r3_p_tgt`, `p_sib`, `restate`, `sites6`, `misc6`, `bk6`, `i6`, `ta5`.
  p4: the same lines in a different order.
- Changed only on F1–F5 rows or by the de-duplicated edition note: `q7`, `h7`, `t7`, `t6`, `t5`, `b5`, `i6b`, `i6c`,
  `p_ind4`, `p_tgt4`, `r3_p_ind`, `sib6`. Every class change is listed in `out/class_changes.txt`; the extra changes beyond the response's table are all lists now split and read
  ("Gastric or pancreatic cancer", "CRC or gastric cancer", "Hepatocellular carcinoma or RCC", "B-ALL or T-ALL", …:
  NAMES_REQUESTED_SITE/UNREADABLE → AMBIGUOUS_NAME), except the two target rows in D7 below.
- The implementer's `scratchpad/u1r8/f.py` output matches the response's table.

REVIEW7's E2E workspaces, copied and re-screened at HEAD (`/tmp/claude-1000/u1rr8/r7_ws_e2e_*`):
- `ws_e2e_gas7`: SOT102, Q-1802, VBC108 and RC118 are AMBIGUOUS_NAME naming Gastric Adenocarcinoma (requested);
  TQB2103 "HER2 absent CLDN18.2 positive" names CLDN18; SG1906 states it is not CLDN18.2 "and also names another
  target".
- `ws_e2e_gas7b`: SOT102, Q-1802, RC118 are UNDER_REQUESTED_PARENT with gastric stage concepts only.
- `ws_e2e_uc7`: SOT102, Q-1802, VBC108 and RC118 are AMBIGUOUS_NAME naming Ulcerative Colitis (requested).

| Id | Status | Input → output at HEAD |
|---|---|---|
| F1 two-disease list classed by one half on other paths | **Fixed for every row REVIEW7 listed; not fixed in general (D1)** | All 35 GAS, 17 UC, 5 MG, 6 ALL-A and 4 AML rows of `q7.py` are AMBIGUOUS_NAME naming the requested reading, except "Adult/Paediatric ulcerative colitis or Crohn's disease" (UNREADABLE, D5). E2E above. **Not fixed** when the left piece is a word on the modifier list that defines the disease ("Chronic or acute myeloid leukemia" → DIFFERENT_DISEASE for CML): the fold makes the list one piece, so `_conjuncts` returns None and the screen's lossy reading is used (D1). The claim "the record's own 'or' list is split on every path" does not hold for those lists. |
| F2 stage pieces looked up alone | **Fixed in lower and title case; not in capitals (D4)** | "Stage III or stage IV gastric cancer", "Stage IIIB or stage IV…", "Stage IV or recurrent…" → UNDER_REQUESTED_PARENT with gastric stage concepts only; "Stage I or II NSCLC", "Grade 1 or 2 follicular lymphoma" → READS_AS_REQUESTED; edition note given once. "STAGE III OR STAGE IV GASTRIC CANCER" → still DIFFERENT_DISEASE listing Masaoka-Koga, head and neck, pancreatic, lung, … stage III (D4). |
| F3 partly-read list containing the request is UNREADABLE | **Fixed for REVIEW7's rows; residue D5** | "Ulcerative colitis, pouchitis or Crohn's disease", "Myasthenia gravis, LEMS or CIDP", "Obesity or type 2 diabetes" → AMBIGUOUS_NAME, "is not a name the NCIt authority can read as a whole; of the names in its 'or' list it reads …". Residue: when the requested piece itself is not read (a population word, "Patients with …"), the record is still UNREADABLE (D5). |
| F4 "absent" before a symbol | **Fixed** | "HER2 absent CLDN18.2 positive", "PD-L1 absent CLDN18.2 high", "KLX9-absent VORP3.1-high" → SOURCE_NAMES_REQUIRED_TARGET; "absent CLDN18.2", "Absent CLDN18.2 expression", "HER2, absent CLDN18.2" → STATES_NOT. Judgement residue J-e. |
| F5 "no other target" when the part names one | **Fixed; new false positive (D7)** | "CLDN18.2 negative or positive for HER2", "… / positive for PD-L1", "VORP3.1 negative KLX9 positive or negative" → "… also names another target, which DealScreen does not read apart from it". But `_symbols` counts any word in capitals, so "CLDN18.2 NEGATIVE", "NOT CLDN18.2", "CLDN18.2-negative by IHC", "CLDN18.2 negative in GC", "CLDN18.2 NEG" now say the same (D7). |
| F6 head borrowing, acronym meanings, blocked modifier | **Partly fixed; acronym part declared and kept** | "Localized or metastatic prostate cancer" → Prostate Carcinoma; "Intestinal or diffuse type gastric adenocarcinoma" → AMBIGUOUS_NAME with the intestinal type (requested) read. Declared, unchanged: "Gastric adenocarcinoma or GC" → "Gonorrhea (not requested)"; also "Hepatocellular carcinoma or RCC" → "Refractory Cytopenia of Childhood"; "Stomach adenocarcinoma or HCC" → "Hilar Cholangiocarcinoma"; "Early RA or psoriatic arthritis" → "Refractory Anemia"; "MDS" → "Dystonia 11, Myoclonic". |
| Cosmetic | **Partly** | Edition note de-duplicated. "'pos' (not read as a target)" and the "not VORP3.1, positive" quote unchanged (declared). |

## Defects in revision 8, ranked by how much they could mislead

### D1 (high; F1 residue, partly new). A disease-defining word first in an "or" list is folded as a modifier, so the list is read by its right half and a record naming the request is called a different disease

How it happens:
- `_MODIFIER_WORDS` holds `acute`, `chronic`, `severe` (and `early`, `low`, `high`, `juvenile`, `adult`, `type`,
  `grade`). In `_list_pieces` a modifier-only piece first in the list is folded into the next piece, so "Chronic or
  acute myeloid leukemia" is one piece and `_conjuncts` returns None.
- `_raw_lookup` then takes the screen's reading. The screen's `_coordinated` treats a left piece that is in
  `QUALIFIERS` (`chronic`, `severe`, …) as a severity qualifier and keeps only the right phrase: "acute myeloid
  leukemia".
- When the screen reads nothing (depth guard on "chronic GVHD"), U1's clean-up removes the qualifier `chronic` and,
  new in revision 8, the "or" after it, leaving "acute GVHD".
- `classify_name` then returns DIFFERENT_DISEASE from a reading of half the list. REVIEW7's recommended guard (never
  DIFFERENT_DISEASE from a reading whose steps expand a coordination unless every piece was read) is not in the code.

| Request | Record name | rev7 | HEAD | Expected |
|---|---|---|---|---|
| CML | "Chronic or acute myeloid leukemia" (**E2E** Q-1802, `ws_heme8`) `[UNK]` | DIFFERENT_DISEASE | DIFFERENT_DISEASE: "reads as Acute Myeloid Leukemia (NCIt) once coordination expanded, neither a requested indication nor a subtype of one" | AMBIGUOUS_NAME: Chronic Myeloid Leukemia (requested); Acute Myeloid Leukemia (not requested) |
| cGVHD | "Chronic or acute GVHD" (**E2E** SOT102, `ws_heme8`) `[UNK]`; also "Chronic or acute graft versus host disease" | UNREADABLE | DIFFERENT_DISEASE: "reads as Acute Graft Versus Host Disease (NCIt) once 'chronic' removed, a clean-up the gate does not apply, neither a requested indication nor a subtype of one" (**new in revision 8**) | AMBIGUOUS_NAME naming Chronic GVHD (requested) and Acute GVHD |
| SAA | "Severe or non-severe aplastic anemia" (**E2E** VBC108, `ws_heme8`) `[UNK]` | DIFFERENT_DISEASE | DIFFERENT_DISEASE: "reads as Non-Severe Aplastic Anemia (NCIt) once coordination expanded …" | AMBIGUOUS_NAME naming Severe Aplastic Anemia (requested) |
| CLL | "Chronic or acute lymphocytic leukemia" `[UNK]` | DIFFERENT_DISEASE | DIFFERENT_DISEASE (Acute Lymphoblastic Leukemia) | AMBIGUOUS_NAME naming CLL |
| chronic pancreatitis | "Chronic or acute pancreatitis" `[UNK]` | DIFFERENT_DISEASE | DIFFERENT_DISEASE (Acute Pancreatitis) | AMBIGUOUS_NAME |
| chronic hepatitis B | "Chronic or acute hepatitis B" `[UNK]` | DIFFERENT_DISEASE | DIFFERENT_DISEASE (Acute Hepatitis B Infection) | AMBIGUOUS_NAME |
| GVHD | "Chronic or acute GVHD" `[UNK]` | UNREADABLE | READS_AS_REQUESTED, "reads as Acute Graft Versus Host Disease … once 'chronic' removed" (right class, half the record) | READS_AS_REQUESTED naming both subtypes |
| GVHD | "Acute or chronic GVHD", "Acute or chronic graft versus host disease" `[UNK]` | UNREADABLE | UNREADABLE: "is not a name the NCIt authority can read" (both halves are NCIt subtypes of the request) | READS_AS_REQUESTED |

- **E2E:** in `e2e_heme8/memo.md` (line 20) SOT102, Q-1802 and VBC108 fall in "a disease neither requested nor a
  subtype of one" (in the "+11 more"); the Diligence sheet's next action and the Screening sheet's class say
  DIFFERENT_DISEASE for all three. Each record names a requested indication.
- **Why it misleads:** this is the outcome U1-6 forbids, the exact E1/F1 harm, on ordinary wording in haematology,
  transplant and hepatology. "Acute or chronic GVHD" and "chronic or acute GVHD" are standard. Revision 8's note says
  "the record's own 'or' list is split on every path that reads a name, before any clean-up"; for these lists it is
  not.
- **Not reachable on GAS wording I tried:** a sweep of 8,184 generated GAS names (`out/sweep_gas.out`) gives no
  gastric name called DIFFERENT_DISEASE except the J-b stage-sibling rows.
- **Fix (in U1 only; the screen's reading is the gate's and must not change):** fold a leading modifier piece only
  when the modifier is an extent or state word that does not change the disease (the gate's `EXTENT_QUALIFIERS` and `relapsed`/`refractory`-type words); otherwise read "A or B X" as "A
  X" and "B X" with the head borrowed. And add the guard REVIEW7 asked for: no DIFFERENT_DISEASE (or any single-half
  class) from a reading whose steps expand a coordination or remove an "or" unless every half was read.

### D2 (medium; new in revision 8). A basket or generic piece is "set aside as a modifier, not a name", so a basket list reads as requested

`_MODIFIER_WORDS` includes `_BASKET_EXTRA` (`other`, `any`, `all`, `solid`, `comers`, …) and `GENERIC_REMAINDERS`
(`tumors`, `cancers`, `disease`, `pain`, `infection`, …). A later piece made only of these is set aside. If every
remaining piece is requested, `classify_name` returns READS_AS_REQUESTED.

| Request | Record name (all `[UNK]`) | rev7 | HEAD | Expected |
|---|---|---|---|---|
| GAS | "Gastric adenocarcinoma, gastroesophageal junction adenocarcinoma, or other solid tumors" (**E2E** VBC108, `ws_gas8`) | NAMES_REQUESTED_SITE | READS_AS_REQUESTED: "reads as Gastric Adenocarcinoma; Gastroesophageal Junction Adenocarcinoma (NCIt) once its 'or' list split into 2 names and 'other solid tumors' set aside as a modifier, not a name, a clean-up the gate does not apply, a requested indication or a subtype" | AMBIGUOUS_NAME (or a list class) naming both requested readings **and** 'other solid tumors' as a basket |
| GAS | the same with "… or any solid tumour", "… or all comers", "… or other cancers", "… or metastatic disease", "… or any other tumour type", "… or pain" | NAMES_REQUESTED_SITE | READS_AS_REQUESTED, each with the piece "set aside as a modifier, not a name" | as above; "pain" is a symptom, not a modifier |
| sepsis | "Sepsis, infection, or pneumonia" | — | AMBIGUOUS_NAME, "'infection' set aside as a modifier, not a name" (NCIt reads "infection" as Infectious Disorder, broader than sepsis) | 'infection' read as Infectious Disorder (broader) |

- **E2E:** in `e2e_gas8/memo.md` (line 47) VBC108 is listed under "a name that reads as requested only after a
  clean-up the gate does not apply"; the Diligence sheet says READS_AS_REQUESTED.
- **Why it misleads:** READS_AS_REQUESTED is the first class in `ORDER`, the one an analyst works first. For a split
  list it now means "every name of the record's own list is requested" (code comment), which is false for a basket
  list; U1's own BASKET class calls "other solid tumors" a basket when it stands alone. The sentence does disclose
  the set-aside piece, which limits the harm.
- **Fix:** a piece that `is_basket` accepts is a basket name, not a modifier: keep it in the list and class the
  record as a list with a basket member. Remove `pain`, `infection`, `inflammation`, `syndrome`, `illness` from the
  words that can be set aside.

### D3 (medium; new in revision 8). An inverted name loses its defining word: "Myeloid leukemia, chronic, …" reads as the broader parent

A comma piece made only of modifier words after a disease name is usually the inverted qualifier of that name
(MeSH order: "Leukemia, Myelogenous, Chronic", "Diabetes Mellitus, Type 2", "Hepatitis B, Chronic"). Revision 8
sets it aside and reads the head alone.

| Request | Record name (all `[UNK]`) | HEAD | Expected |
|---|---|---|---|
| CML | "Myeloid leukemia, chronic, or ALL, or AML" (**E2E** RC118, `ws_heme8`; memo: "an 'or' list read only in part") | AMBIGUOUS_NAME: "… 'chronic' set aside as a modifier, not a name …: Myeloid Leukemia (broader than requested); Acute Lymphoblastic Leukemia (not requested); Acute Myeloid Leukemia (not requested)" | Chronic Myeloid Leukemia (requested) read, or the piece kept with its name and named as unread |
| T2D | "Diabetes mellitus, type 2, or obesity" (**E2E** RC118, `ws_uc8` with a UC request shows the same reading) | UNREADABLE: "… it reads Diabetes Mellitus (broader than requested) and does not read 'obesity'" (the set-aside 'type 2' is not mentioned, D8) | Type 2 Diabetes Mellitus (requested) |
| CLL | "Lymphocytic leukemia, chronic, or SLL, or MCL" | AMBIGUOUS_NAME: Lymphoid Leukemia (broader) | CLL (requested) |
| T1D | "Diabetes mellitus, type 1, or celiac disease, or psoriasis" | AMBIGUOUS_NAME: Diabetes Mellitus (broader) | T1D (requested) |
| chronic hepatitis B | "Hepatitis B, chronic, or hepatitis D" | UNREADABLE: Hepatitis B Infection (broader) | Chronic Hepatitis B (requested) |
| JIA | "Arthritis, juvenile, or uveitis" | AMBIGUOUS_NAME: Arthritis (broader) | — (NCIt has no "juvenile arthritis" key; at least not "set aside as a modifier") |
| AML | "Myeloid leukemia, acute, or MDS, or CMML" | AMBIGUOUS_NAME: Myeloid Leukemia (broader) | AML (requested) |

- **Why it misleads:** the sentence says the record names a disease broader than requested when it names the
  requested one, and it tells the analyst that "chronic" or "type 2" is "a modifier, not a name". The class is
  usually AMBIGUOUS_NAME either way, so the ranking harm is small; the T2D row drops to UNREADABLE.
- **Fix:** try a set-aside comma piece as an inverted qualifier of the piece before it ("Myeloid leukemia, chronic"
  → "chronic myeloid leukemia") before setting it aside; never set aside `acute`, `chronic`, `type N`, `juvenile`,
  `adult`, `grade N` silently.

### D4 (medium; F2 residue, partly new). In a capitalised cell every modifier word is an "acronym", so modifiers are looked up as names

`_modifier_word` exempts any word in capitals (`word.isupper() and len(word) > 1`) so that "ALL" stays a name. In a
cell written in capitals, "STAGE", "LOCALLY", "ADVANCED", "MODERATE", "CHRONIC" are all exempt, so the pieces are
looked up in the NCIt index, which reads "moderate", "chronic", "stage iii" and "locally advanced" as unrelated
concepts. Since revision 8 runs the split before the screen's reading, U1 also contradicts the screen: the Screening
sheet of `ws_gas8` shows the gate reading "'STAGE III OR IV GASTRIC CANCER' read as 'Stage III Gastric Cancer AJCC
v7' (coordination expanded)" beside U1's sentence below.

| Request | Record name (all `[UNK]` unless marked) | rev7 | HEAD |
|---|---|---|---|
| GAS | "STAGE III OR IV GASTRIC CANCER" (**E2E** SOT102, `ws_gas8`) | NAMES_REQUESTED_SITE, listing the other organs as read | AMBIGUOUS_NAME: "matches several NCIt concepts …: Masaoka-Koga Stage III (not requested); Stage III Head and Neck Cutaneous Squamous Cell Carcinoma AJCC v8 (not requested); Stage III Pancreatic Cancer AJCC v8 …" |
| GAS | "STAGE III OR STAGE IV GASTRIC CANCER" | DIFFERENT_DISEASE (same list) | DIFFERENT_DISEASE (same list): REVIEW7's F2 row, unchanged in capitals |
| GAS | "LOCALLY ADVANCED OR METASTATIC GASTRIC CANCER" (**E2E** Q-1802, `ws_gas8`) | NAMES_REQUESTED_SITE | AMBIGUOUS_NAME: "Locally Advanced Malignant Neoplasm (shares subtypes with a requested concept); Gastric Carcinoma (broader than requested); …" |
| UC | "MODERATE OR SEVERE ULCERATIVE COLITIS OR CROHN'S DISEASE" | DIFFERENT_DISEASE | AMBIGUOUS_NAME: "Moderate COVID-19 Infection (not requested); Ulcerative Colitis (requested or a subtype); Crohn Disease (not requested)" |
| CML | "CHRONIC OR ACCELERATED PHASE CML" `[PASS]` | READS_AS_REQUESTED | AMBIGUOUS_NAME: "Chronic Graft Versus Host Disease (not requested); Accelerated Phase Chronic Myeloid Leukemia …" |

- **Why it misleads:** the sentence attributes to the record diseases it never names (COVID-19, GVHD, thymoma
  staging, head and neck cancer), as "NCIt" readings. The class is not demoted below AMBIGUOUS_NAME except in the
  "STAGE III OR STAGE IV" row, which is still the F2 DIFFERENT_DISEASE outcome. Some registries and vendor exports
  write conditions in capitals (judgement on reach, not measured).
- **Fix:** decide "acronym" by shape in context (a short capitalised token in a mixed-case cell), not by
  `isupper()` alone; in an all-capitals cell, test modifier words case-insensitively and keep only acronyms that are
  not modifier words ("ALL" is still a name because `all` is excluded only before a basket head).

### D5 (medium; F3 residue). A population word in front of the requested name leaves it unread, and the record is UNREADABLE

`_state_removed` keeps population words ("a population word stays, it is part of the disease name"), and no other
retry removes them. When the requested piece is unread, `classify_name` has no REQUESTED reading, so the F3 fix does
not apply and the record is UNREADABLE, the lowest class.

| Request | Record name (all `[UNK]`) | HEAD |
|---|---|---|
| UC | "Patients with ulcerative colitis or Crohn's disease" (**E2E** SOT102, `ws_uc8`) | UNREADABLE: "is not a name the NCIt authority can read as a whole; of the names in its 'or' list it reads Crohn Disease (not requested) and does not read 'Patients with ulcerative colitis'" |
| UC | "Adult ulcerative colitis or Crohn's disease" (**E2E** Q-1802), "Pediatric …" (**E2E** VBC108), "Paediatric …", "Juvenile …", "Adults with …" | UNREADABLE, the same sentence |
| controls | "Ulcerative colitis or Crohn's disease in children", "Acute severe ulcerative colitis or Crohn's disease" | AMBIGUOUS_NAME naming UC (requested) |

- **E2E:** `e2e_uc8/memo.md` line 20 lists the four edited programs under "no name the NCIt authority reads as a
  whole", below the different diseases. "Patients with X or Y" is very common condition wording.
- **Fix:** retry an unread piece without leading population words and "patients/adults with", disclosing it ("read
  as 'ulcerative colitis'"); when a list holds an unread piece that names a requested concept's label words, do not
  use UNREADABLE.

### D6 (medium-low; new in revision 8). "or" inside an NCIt proper name is split before the clean-up

`_raw_lookup` now tries `_conjuncts` right after the exact index lookup. When the exact lookup misses only because of
a leading qualifier, the split breaks a proper name that contains "or", and the clean-up that would have read it
whole never runs.

| Request | Record name | rev7 | HEAD |
|---|---|---|---|
| DHL | "Advanced high grade B-cell lymphoma with MYC and BCL2 or BCL6 rearrangements" `[UNK]`; also "Metastatic …" `[UNK]`, "Severe …", "…, relapsed" `[PASS]` | READS_AS_REQUESTED (the whole concept) | AMBIGUOUS_NAME: "it reads High Grade B-Cell Lymphoma with MYC and BCL2 Rearrangements (requested or a subtype) and does not read 'BCL6 rearrangements'" |
| AMP | "Advanced ampullary pancreaticobiliary or gastric type adenocarcinoma" `[UNK]`; "Metastatic ampulla of Vater …" | READS_AS_REQUESTED | UNREADABLE: "is not a name the NCIt authority can read" |
| GAS | the same two names `[UNK]` | DIFFERENT_DISEASE (Ampulla of Vater Pancreaticobiliary/Gastric Type Adenocarcinoma: correct) | UNREADABLE |
| AML | "Advanced acute myeloid leukemia with inv(16)(p13.1q22) or t(16;16)(p13.1;q22); CBFB-MYH11" `[UNK]` | READS_AS_REQUESTED | AMBIGUOUS_NAME, "does not read 't(16;16)(p13.1;q22); CBFB-MYH11'" |

- **Why it misleads:** the sentence names a different NCIt concept from the one the record names, calls a
  karyotype or a rearrangement "a name in its 'or' list", and in the ampullary rows says the authority cannot read a
  name it read in revision 7. 99 NCIt labels contain "or" (double-hit lymphoma and AML cytogenetic subtypes among
  them).
- **Fix:** before splitting, try the whole name through U1's clean-up (and the screen's reading); split only when
  the whole is unread, or keep whichever reading reads more of the record.

### D7 (low-medium; new in revision 8). The F5 tail says a negated cell "also names another target" when the second "symbol" is a state word, an assay or a disease acronym

`_symbols` counts any word in capitals of length > 1. In the negated part it then finds a second "symbol".

| Target cell (real CLDN18.2 reader, `probes/t8.py`) | HEAD |
|---|---|
| "CLDN18.2 NEGATIVE" (**E2E** TQB2103, `ws_gas8`) | "'CLDN18.2 NEGATIVE' states it is not CLDN18.2; 'CLDN18.2 NEGATIVE' also names another target, which DealScreen does not read apart from it" |
| "CLDN18.2-negative by IHC" (**E2E** SG1906), "NOT CLDN18.2", "CLDN18.2 negative in GC", "CLDN18.2 NEG" (`t5`) | the same tail |
| controls: "CLDN18.2 negative", "non-CLDN18.2", "CLDN18.2 negative per FDA-approved test" | "the record names no other target the authority reads" (correct) |

- The class is right; the tail invents a target. Revision 7 said "no other target" for these, which was true.
- **Fix:** count a second symbol only if it is not a state word (`NEGATIVE`, `NEG`, `NOT`, `POSITIVE`, `POS`, `LOW`,
  `HIGH`) and, where a reader is available, only if the target reader reads it or it has the symbol shape (letters
  and a digit).

### D8 (low). The partly-read sentence hides its steps, including the basket it set aside

When `reading.unread` is non-empty, `_indication_sentence` uses "is not a name the NCIt authority can read" and
`_partly_read`, but never `_how_read`. The set-aside and "read as" steps are dropped.
- "Gastric adenocarcinoma, GEJ adenocarcinoma, or other solid tumors" (**E2E** RC118, `ws_gas8`): "of the names in
  its 'or' list it reads Gastric Adenocarcinoma (requested or a subtype) and does not read 'GEJ adenocarcinoma'". The
  basket member is not mentioned; the sentence implies the list has two names.
- "Diabetes mellitus, type 2, or obesity" (D3): 'type 2' set aside without a word.
- Also: a piece "GEJ adenocarcinoma" is unread on its own although the screen reads "Gastric or GEJ adenocarcinoma".
- **Fix:** append `_how_read` to the partly-read sentence.

### D9 (low). Pieces that are not disease names are still called "names in its 'or' list", or swallow the list

- Therapy and line pieces: "Gastric adenocarcinoma, HER2-negative, after platinum or taxane" → "does not read
  'HER2-negative' or 'after platinum' or 'taxane'"; "Gastric adenocarcinoma (first or second line)" → "does not read
  'first' or 'second line'"; "Gastric adenocarcinoma (PD-L1 CPS ≥1 or <1)" → "does not read 'PD-L1 CPS ≥1' or
  '<1'". `first`/`second` are not on the modifier list although `1l`/`2l` are.
- Grade lists swallow the whole name: "Grade 1, 2 or 3a follicular lymphoma", "Follicular lymphoma grade 1, 2 or
  3a", "Grade 3a or 3b FL" (FL request, `[UNK]`) → UNREADABLE, "is not a name the NCIt authority can read".
- "Either gastric adenocarcinoma or NSCLC" → "does not read 'Either gastric adenocarcinoma'".
- The class is usually acceptable (AMBIGUOUS_NAME or NAMES_REQUESTED_SITE); the wording misdescribes the record.

### Carried, declared (not counted again)

- F6 acronym pieces bring in the index's other meanings, now in more lists because more lists are split:
  "Gastric adenocarcinoma or GC" → Gonorrhea; "Hepatocellular carcinoma or RCC" → Refractory Cytopenia of Childhood;
  "Stomach adenocarcinoma or HCC" → Hilar Cholangiocarcinoma; "Early RA or psoriatic arthritis" → Refractory Anemia;
  "… or MDS …" → Dystonia 11, Myoclonic. The implementer declined a rule; I still count these as statements about
  the record that the record does not make, low.
- J-a (outside U1): the gate's coordination reading is lossy. D1 shows it also reads "Chronic or acute myeloid
  leukemia" as AML alone, so an AML request would pass a record that also names CML.

## Judgement calls (labelled; not counted as defects)

- **J-b (carried, wider reach).** A stage concept beside another disease is DIFFERENT_DISEASE: "Stage IV gastric
  cancer or NSCLC" → "reads as Stage IV Gastric Cancer AJCC v7; Lung Non-Small Cell Carcinoma …, neither a requested
  indication nor a subtype of one, although it names gastric". Literally true, but the same stage piece alone is
  UNDER_REQUESTED_PARENT, and a REQUESTED piece beside a different disease is AMBIGUOUS_NAME; only the SIBLING piece
  loses its class in a list (`kinds <= {SIBLING, DIFFERENT}`). All 60 rows my GAS sweep flagged are of this shape
  ("Stage IV or metastatic gastric cancer or NSCLC", "NSCLC or stage IV gastric cancer", …). These names now reach it
  through U1's own split as well as through the screen's.
- **J-c, J-d (carried).** `sites6`, `misc6`, `bk6` are identical to REVIEW7's outputs.
- **J-e (F4 residue).** "HER2+ absent CLDN18.2" and "HER2-low absent CLDN18.2" → "names CLDN18". The other marker
  already carries its own state, so "absent" more likely belongs to CLDN18.2. Without punctuation the cell is
  ambiguous; reading it as naming the target is the less harmful error.
- **J-f.** For a fully read split list, AMBIGUOUS_NAME still says "matches several NCIt concepts" ("'Gastric
  adenocarcinoma or NSCLC' matches several NCIt concepts once its 'or' list split into 2 names …"). The record names
  several diseases; no single name matches several concepts. The summary now covers both meanings, so this is
  wording only.
- **J-g.** "Stage III or IV gastric adenocarcinoma", "Grade 2 or 3 gastric adenocarcinoma" → NAMES_REQUESTED_SITE
  ("is not a name the NCIt authority reads"): true, an under-reading, harmless in rank.

## Reading the outputs as a BD analyst

`after/` is current at HEAD: the memo is identical and the workbook cell-identical (timestamp apart) to a fresh
export of `fin14_ws`. The 38 CLDN18.2 actions are unchanged from revision 7 except IBI343, which now names both
requested readings of "Unresectable or Metastatic Gastric or Gastroesophageal Junction Adenocarcinoma" (its step,
"'Unresectable or Metastatic Gastric' read as 'Unresectable or Metastatic Gastric Adenocarcinoma'", quotes a piece
with "or" inside it, which reads oddly). No CLDN18.2 record contains any D1–D9 shape, so none of them appears in the
shipped landscape.

REVIEW4–7's reading still holds: each action states what is on record, its class, the one cited fact that decides
the gate and the `assert` field; the PD-1 rows name TIGIT, CTLA-4 and 'PD-1'; the basket rows name both requested
indications; the memo's single-gate list has no scope or recommendation words (the only "In scope"/"Out of scope"
in the memos is the buyer's own need statement). Still less useful: the repeated "The gate never fails on this
evidence…" tail, DR30303's "not a name the NCIt authority can read", and "'PD-1' not read by the target authority".

Nothing is hidden: every UNKNOWN on a non-excluded program has its diagnostic, in `fin14_ws`, the held-out
landscapes and all six E2E workspaces.

What an analyst would not see: in a transplant/haematology screen (D1) three records naming the requested disease
sit in the memo's "different disease" group, and in a gastric screen (D2) a basket program sits at the top of the
indication group as "reads as requested". In a capitalised export (D4) the Diligence sheet tells the analyst the
record reads as thymoma staging, head-and-neck cancer or COVID-19.

## What I could not check

- Whether the revision-8 tests were written before the code was tuned.
- Workbooks and memos for the held-out landscapes; I read their `screening.json` only (they are unchanged from
  `xv13f`, so revision 8 does not touch them). For my E2E workspaces I generated both workbooks and the markdown
  memos; the `.docx` memos were generated but not opened. (`bve-dealscreen memo --out memo.docx` reports the same
  path for markdown and docx; I generated the markdown separately with `--out memo.md`. Not a U1 matter.)
- Domain judgements used to rate reach, not checked against an authority: how often vendor cells are written in
  capitals, in MeSH inverted order inside an "or" list, or as "Chronic or acute X"; that "Patients with X or Y" is
  common.
- The NCIt claims (index keys "chronic", "acute", "moderate", "stage iii", "locally advanced", "infection"; the
  readings of CML, Acute GVHD, Non-Severe Aplastic Anemia, Diabetes Mellitus, Myeloid Leukemia; 99 labels containing
  "or") were checked through the U1 code against the frozen authority.
- D1–D9 fixes were not implemented or tested.
- The rights code (under concurrent review): not touched; used only to attribute the transaction changes.
- During this review another session left uncommitted edits in `rights_quote.py`, `rights_template.py` and a rights
  test (not mine). `git diff HEAD` shows no change to any U1 module (`diagnostics.py`, `indication_relations.py`,
  `indications.py`, `screening.py`, `facts.py`, `workbook.py`, `memo.py`, `cli/dealscreen.py`), so every U1 output
  above is HEAD's. Some later screens (E2E, the stubbed copies) may have run with those rights edits; my U1-3 checks
  compare a stubbed and an unstubbed screen on the same tree, and the fresh CLDN18.2 screen is byte-identical to
  `fin14_ws`, so they are unaffected.

## Reproduction

```
cd /home/djmann/projects/bve-b8 && . .venv/bin/activate && export TMPDIR=$HOME/.cache/dealscreen_suite
python -m pytest tests/dealscreen -q -p no:cacheprovider        # 1803 passed, 5 warnings, 135 s
/tmp/claude-1000/u1rr8/runall.sh                                 # every earlier probe -> /tmp/claude-1000/u1rr8/out/
P=/tmp/claude-1000/u1rr8/probes
python $P/h8.py                       # D1-D5, D9 rows with the gate's positive reading ([UNK]/[PASS])
python $P/cmp78.py $P/orq.txt         # D1: rev7 vs HEAD ("Chronic or acute X")
python $P/cmp78.py $P/bas.txt         # D2: basket pieces set aside
python $P/cmp78.py $P/caps.txt        # D4: capitalised cells
python $P/cmp78.py $P/prop.txt        # D6: "or" in NCIt proper names (also prop2.txt)
python $P/cmp78.py $P/slash.txt       # "/", "and/or", parenthesised lists
python $P/t8.py                       # D7, J-e (real CLDN18.2 target reader)
python3 /tmp/claude-1000/u1rr7/probes/txdiff.py <fin14_ws/screening.json> research/dealscreen_unknown_actions_v1/baseline/screening_R1.json
python /tmp/claude-1000/u1rr6b/probes/nou1.py <copy of a workspace>   # screen with U1 stubbed out
python3 /tmp/claude-1000/u1rr/science_diff.py <screening.json> <reference screening.json>
python3 /tmp/claude-1000/u1rr/coverage.py <screening.json ...>
/tmp/claude-1000/u1rr8/build.sh <name> "<indications>" "<cell edits>"   # E2E builder (import, rights, screen, export, memo)
```

Scratch workspaces (copies; originals not modified):
- `ws_copy` (fresh CLDN18.2 screen, byte-identical to `fin14_ws`; `ws_copy_out.xlsx`, `ws_copy_memo.md`),
  `ws_nou1`, `nou1_gas8`, `nou1_heme8`, `nou1_uc8` (U1 stubbed out).
- `r7_ws_e2e_gas7`, `r7_ws_e2e_gas7b`, `r7_ws_e2e_uc7`: REVIEW7's E2E workspaces re-screened at HEAD.
- `ws_gas8` (`e2e_gas8/`): GAS request; SOT102 "STAGE III OR IV GASTRIC CANCER", Q-1802 "LOCALLY ADVANCED OR
  METASTATIC GASTRIC CANCER", VBC108 "Gastric adenocarcinoma, gastroesophageal junction adenocarcinoma, or other solid
  tumors", RC118 "Gastric adenocarcinoma, GEJ adenocarcinoma, or other solid tumors"; targets TQB2103 "CLDN18.2
  NEGATIVE", SG1906 "CLDN18.2-negative by IHC".
- `ws_heme8` (`e2e_heme8/`): request [chronic graft versus host disease, chronic myeloid leukemia, severe aplastic
  anemia]; SOT102 "Chronic or acute GVHD", Q-1802 "Chronic or acute myeloid leukemia", VBC108 "Severe or non-severe
  aplastic anemia", RC118 "Myeloid leukemia, chronic, or ALL, or AML".
- `ws_uc8` (`e2e_uc8/`): request [ulcerative colitis]; SOT102 "Patients with ulcerative colitis or Crohn's
  disease", Q-1802 "Adult …", VBC108 "Pediatric …", RC118 "Diabetes mellitus, type 2, or obesity".
- Equivalence: `/tmp/claude-1000/u1rr8/equiv.log`.

## Summary of defects

| Severity | Count | Ids |
|---|---|---|
| High | 1 | D1 |
| Medium | 4 | D2, D3, D4, D5 |
| Low-medium / medium-low | 2 | D6, D7 |
| Low | 2 | D8, D9 |

Single highest-value next fix: in U1's reading of an "or" list, treat a leading `chronic`/`acute`/`severe`/
`juvenile`/`type N`/`grade N` piece as a disease-defining alternative (borrow the head: "Chronic or acute X" → "chronic
X", "acute X"), not as a modifier to fold, and add the guard that no single-half class (DIFFERENT_DISEASE above all)
comes from a reading that expanded a coordination or removed an "or" unless every half was read. That closes D1 and,
with the same "is it really a modifier" test applied to set-aside pieces, most of D2 and D3.
