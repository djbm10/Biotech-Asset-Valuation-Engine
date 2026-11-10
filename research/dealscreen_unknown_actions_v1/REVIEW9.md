# Cycle U1 revision 9: ninth adversarial review

INTERNAL DEVELOPMENT. This is an AI-simulated adversarial review. It is not human or independent validation, and
nothing in it is an approval.

**Reviewed:** HEAD `28535ea` on `dealscreen-mvp` in `/home/djmann/projects/bve-b8`, read-only (U1 revision 9
committed together with R1 revision 15). U1 revision 8 is `624b2f0`. Among the U1 modules, `git diff 624b2f0 28535ea`
changes only `diagnostics.py` and `indication_relations.py`; `screening.py`, `facts.py`, `workbook.py`, `memo.py` and
`cli/dealscreen.py` are untouched.
**Criteria:** `ACCEPTANCE.md` with its revision notes (including the revision-9 note), `MEASUREMENT.md`, `REVIEW8.md`
and `REVIEW8_RESPONSE.md`.

Every number below was recomputed by running code unless marked "read, not re-run". Scratch files, probes and
workspaces are in `/tmp/claude-1000/u1rr9/`.

Abbreviations:
- `GAS` = the CLDN18.2 request `["gastric adenocarcinoma", "gastroesophageal junction adenocarcinoma"]`. Other
  requests are written as their NCIt label (each checked to be exactly one NCIt concept through `ir.read_request`):
  `T2D` type 2 diabetes mellitus, `RMS` relapsing multiple sclerosis, `ALLA` adult acute lymphoblastic leukemia,
  `cGVHD` chronic graft versus host disease, `DLBCL` diffuse large B-cell lymphoma, not otherwise specified, etc.
- "rev8" = revision 8's two U1 modules loaded side by side from `git show 624b2f0:…` (`/tmp/claude-1000/u1rr9/rev8/`,
  probe `probes/cmp89.py`, which prints rev8 and HEAD for each `KEY|name` line).
- `[UNK]` = the gate's positive reading (name or any `indication_readings` reading through
  `indication_compatibility.compatibility`) does not pass, so the diagnostic is shown. `[PASS]` rows are unit-level.
- "E2E" = confirmed through `bve-dealscreen import`, `import-rights`, `screen`, `export` and `memo` on a workspace
  built from the `fin15_ws` inputs with four indication cells (and for `mix9` the buyer's indications) edited
  (`build.sh`, `buildall.sh`; see Reproduction).

## Verdict in one paragraph

Revision 9 changes no science and coverage is still complete. Every row REVIEW8 gave for D1–D9 now gives the expected
output, unit and end to end (REVIEW8's `ws_gas8`, `ws_heme8`, `ws_uc8` re-screened at HEAD). U1-1 to U1-5 are met;
U1-6 is met as measured on CLDN18.2 (unchanged from revision 8, and a 99,875-name GAS sweep finds no gastric name
called a different disease apart from the carried J-b stage rows).

**U1-7 is still not met.** The D1 fix is a word list (`_DEFINING`) gating the authority test, so the D1 harm is one
word away, and the new retries add misstatements of their own:
1. **N1 (high): a leading alternative outside `_DEFINING` is still folded.** "Relapsing or progressive multiple
   sclerosis" is DIFFERENT_DISEASE for a relapsing-MS request ("reads as Progressive Multiple Sclerosis"), although
   NCIt has Relapsing Multiple Sclerosis. E2E. The revision-9 note in `ACCEPTANCE.md` ("a modifier that, with the
   name's head, is its own NCIt concept … is read as that concept, never folded") is false for it.
2. **N2 (high): a lone adjective piece is looked up alone, and the index reads it as a gastric concept.** "Diffuse or
   follicular lymphoma" in the CLDN18.2 request reads "Gastric Diffuse Adenocarcinoma (requested or a subtype)";
   "Intestinal or extraintestinal Behçet's disease" reads "Gastric Intestinal-Type Adenocarcinoma (requested)"; for a
   DLBCL request "Diffuse or follicular lymphoma" is DIFFERENT_DISEASE naming gastric cancer. E2E. (The "Diffuse"
   row exists since the revision-7 split and is unchanged in revisions 8 and 9; not reported before.)
3. **N3, N4 (medium):** "Type 1 or 2 diabetes mellitus" reads the second piece as "diabetes mellitus" (broader) and
   never names T2D (E2E); the population retry turns "Children with ALL" into ALL, "broader than" an adult-ALL request,
   while "Childhood ALL" is correctly a different disease (E2E).
4. **N5–N9 (lower):** inverted chains ("GVHD, acute or chronic, or AML" is UNREADABLE for cGVHD; E2E); every
   all-capitals cell the screen reads now says "a clean-up the gate does not apply" (E2E); softened quotes that are
   not the record as written; grade/line tokens counted as a second target; a set-apart severity word called a name.


## Verdict per criterion

| AC | Verdict | Evidence |
|---|---|---|
| U1-1 coverage | **Met** | `coverage.py`: `fin15_ws` 38/38; `xv15f` c5_heldout 28/28, fcrn_v1 28/28, fcrn_v2 28/28, synthetic_200 20/20 (104/104); REVIEW8's E2E re-screened at HEAD `r8_ws_gas8` 40/40, `r8_ws_heme8` 53/53, `r8_ws_uc8` 53/53; my E2E `ws_gas9` 38/38, `ws_mix9` 53/53. Missing 0, extra 0 everywhere. |
| U1-2 authorities only | **Met (letter), with a note** | The revision-9 `+` lines name diseases and targets only in comments and docstrings (grep for gastr, cldn, gej, her2, pd-l1, klx, vorp, crohn, colitis, leuk, gvhd, diabet, anemia, lymphom, myelo, nsclc, ihc, gc, china, asia). New lists (`_DEFINING`, `_STATE_SYMBOLS`, `_PEOPLE_WITH`) are generic English. Note: `_DEFINING` decides which modifiers the NCIt index is even asked about; N1 and N2 come from that gate, not from the authority. |
| U1-3 no change to science | **Met** | `science_diff.py` `fin15_ws` vs `baseline/screening_R1.json`: 13 of 62 programs differ, all in `transaction` only (R1's; `txdiff.py`: 11 of 13 identical once `external_id`/`related_deal_id` are removed, the other two Zolbetuximab and IMAB362 as in REVIEW8); disposition, rank, decisions, machine_recommendation, transaction_rank unchanged; top level equal. `fin15_ws/screening.json` is byte-identical to `fin14_ws` and to `after/screening_u1.json`. A fresh screen of a copy is byte-identical to `fin15_ws`; a copy screened with `screening.diagnose` stubbed out (`nou1.py`) differs only in `unknown_diagnostics`. Held-out `xv15f` vs `xv10` and vs `xv14f`: 0 differing per-program keys in all four landscapes (not even `unknown_diagnostics`). Cycle-4 equivalence not re-run by me (see "Could not check"). |
| U1-4 held-back tests | **Met as written; insufficient in substance** | `python -m pytest tests/dealscreen -q -p no:cacheprovider`: **1,886 passed**, 5 warnings, 282 s. The revision-9 block tests REVIEW8's rows. No test has a leading alternative outside `_DEFINING` ("Relapsing or …", "Diffuse or …", "Squamous or …"), a numbered second piece ("Type 1 or 2 …"), a population retry against a population-specific request, an inverted chain ("X, acute or chronic"), or an all-capitals cell the screen already reads. |
| U1-5 surfaces | **Met** | A fresh memo from a copy of `fin15_ws` is identical to `after/memo_u1.md`; a fresh workbook is cell-identical to `after/u1_cldn18.xlsx` on all 9 sheets apart from the README timestamp. In `ws_gas9`/`ws_mix9` the Diligence "Next action", the Screening class and the memo's single-gate list carry the revision-9 sentences (N1–N6 confirmed on the Diligence sheet). |
| U1-6 per program vs reference | **Met as measured; the harm is reachable in other therapy areas (N1) and a false "requested" lead is reachable in the gastric request (N2)** | From `reference_calls.csv` (names matched without the parenthesised code): 30 reference-IN programs, 14 ELIGIBLE, 15 UNRESOLVED, 1 EXCLUDED (LCB02A, disclosed). The only DIFFERENT_DISEASE among them is SOT102 ("Pancreatic Cancer"), reported. GAS sweep (`probes/sweep9.py`, 99,875 generated names, modifiers × gastric names × other diseases, every seventh in capitals): 493 DIFFERENT_DISEASE, all the J-b shape (a stage-IV gastric piece beside another disease), 139 BROADER_THAN_REQUESTED, all naming "gastric cancer/carcinoma" (correctly broader), 0 UNREADABLE. |
| U1-7 adversarial review | **Not met** | N1, N2 (high) and N3, N4 (medium) are confirmed end to end. I found no hidden UNKNOWN, no stray diagnostic, no scope or recommendation wording in any action, and no change to science. |

## Status of REVIEW8's findings (D1–D9)

Inputs: every earlier probe re-run unchanged from the repository root (`runall.sh`), outputs in
`/tmp/claude-1000/u1rr9/out/`, diffed against REVIEW8's (`/tmp/claude-1000/u1rr8/out/`):
- Identical: p1–p3, p5–p10, `r3_p_sib2`, `r3_p_tgt`, `p_sib`, `p_tgt4`, `restate`, `sites6`, `sib6`, `misc6`, `bk6`,
  `i6`, `i6b`, `ta5`, `t7`. p4: the same lines in a different order. So the stage-only sibling rule, the restatement
  rule, the neoplasm-node site rule, the lineage list, role words, baskets/acronyms, negation/parenthesis handling,
  "/" and "and/or" and placeholders are unchanged at HEAD for every earlier input.
- Changed: `h8` (18 class changes), `orq` (10), `bas` (9), `caps` (5), `prop` (5), `prop2` (6), `slash` (4), `t8`
  (4 sentences), `t6`, `t5` (1 each), and wording only (the steps now shown, D8) in `q7`, `h7`, `o7_all`, `f`, `i6c`,
  `b5`, `p_ind4`, `r3_p_ind`. Every class change is the response's, or a list now split and read, except the rows in
  N5 and N6 below. Class changes: `probes/chg.py <rev8 out> <head out>`.
- REVIEW8's E2E workspaces, copied and re-screened at HEAD (`r8_ws_gas8`, `r8_ws_heme8`, `r8_ws_uc8`): every row is as
  the response's §3 states.
- The implementer's `u1r9/probe.py` output (`out/u1r9_probe.out`) matches the response's tables.

| Id | Status | Input → output at HEAD |
|---|---|---|
| D1 leading defining word folded | **Fixed for every listed row; not fixed in general (N1, N2)** | `orq`: "Chronic or acute myeloid/myelogenous/lymphocytic leukemia", "… pancreatitis", "… hepatitis B", "Chronic or acute GVHD/graft versus host disease", "Severe or non-severe/moderate aplastic anemia" → AMBIGUOUS_NAME naming the requested chronic/severe concept; GVHD request: "Acute or chronic GVHD" → READS_AS_REQUESTED naming both. E2E `r8_ws_heme8`: SOT102, Q-1802, VBC108 AMBIGUOUS_NAME naming the request. Also "Juvenile or chronic myelomonocytic leukemia" (JMML/CMML) and "Adult or childhood AML" now read both halves. **Not fixed** for a leading alternative outside `_DEFINING` (N1: "Relapsing or progressive MS" → DIFFERENT_DISEASE), for one that is not a modifier word at all (N2), or for the second piece of a numbered pair (N3). |
| D2 basket piece set aside | **Fixed** | `bas`, `a3`: every "…, or other solid tumors / all comers / other cancers / metastatic disease / any solid tumour" → AMBIGUOUS_NAME "reads 'other solid tumors' as a basket of diseases, not one name"; "… or pain" → "does not read 'pain'"; "Infection or sepsis" → Infectious Disorder (broader). E2E `r8_ws_gas8` VBC108. In capitals the basket is still a basket ("GASTRIC ADENOCARCINOMA OR ALL COMERS"). Judgement J-h: "carcinoma", "malignant neoplasm", "neoplastic disease" in a list are baskets although NCIt has those concepts (consistent with the stand-alone BASKET class). |
| D3 inverted name loses its defining word | **Fixed for one inverted piece; not for a chain (N5)** | "Myeloid leukemia, chronic, or ALL, or AML" → names CML (requested); "Diabetes mellitus, type 2, or obesity" → T2D (requested); "Hepatitis B, chronic, or hepatitis D" → Chronic Hepatitis B; "AML, or ALL, adult" → Adult ALL; "Obesity, or diabetes mellitus, type 2" → T2D; a defining word that makes no concept is named as unread ("Gastric adenocarcinoma, adult, or NSCLC" → "does not read 'adult'"). **Not fixed**: "X, acute or chronic" (N5). |
| D4 capitals | **Fixed for every listed row; new misstatements (N6, N7)** | "STAGE III OR STAGE IV GASTRIC CANCER" → UNDER_REQUESTED_PARENT, gastric stage concepts only; "MODERATE OR SEVERE ULCERATIVE COLITIS OR CROHN'S DISEASE" no longer names COVID-19; "LOCALLY ADVANCED OR METASTATIC GASTRIC CANCER" → AMBIGUOUS_NAME_ALL_BROADER; "MILD OR MODERATE ASTHMA" (COVID request) → asthma, not Mild COVID-19. "ALL OR AML", "ADULT ALL OR AML", "ALL, ADULT, OR AML" keep ALL. A scan of all 107 modifier words in capitals against the index finds no acronym collision other than "ALL" and "AN", so the response's limit holds. |
| D5 population word | **Fixed for a leading population; new misreading (N4), residue** | "Patients with / Adult / Pediatric / Juvenile / Adults with / Elderly patients with ulcerative colitis or Crohn's disease" → AMBIGUOUS_NAME naming UC (requested). E2E `r8_ws_uc8`. Residue: "Adult or pediatric ulcerative colitis or Crohn's disease" (UC) → still UNREADABLE, "does not read 'Adult or pediatric ulcerative colitis'". |
| D6 "or" in an NCIt label | **Fixed** | `prop`, `prop2`: "Advanced/Severe/Metastatic/Relapsed high grade B-cell lymphoma with MYC and BCL2 or BCL6 rearrangements" → READS_AS_REQUESTED (the whole concept); "Advanced ampullary pancreaticobiliary or gastric type adenocarcinoma" → READS_AS_REQUESTED (AMP) and DIFFERENT_DISEASE (GAS, correct); AML inv(16) rows → READS_AS_REQUESTED. Judgement J-i on `_whole` reach below. |
| D7 state word as a second target | **Fixed; residue (N8)** | "CLDN18.2 NEGATIVE", "CLDN18.2-negative by IHC", "NOT CLDN18.2", "CLDN18.2 negative in GC", "CLDN18.2 NEG", "VORP3.1 NEGATIVE", "CLDN18.2 NOT EXPRESSED", "… in ITT/FAS" → "no other target the authority reads"; "CLDN18.2 negative or positive for HER2" still "also names another target". E2E `r8_ws_gas8` TQB2103, SG1906. |
| D8 steps hidden | **Fixed** | Every partly-read sentence ends "(read once …)" with the split, set-aside, inverted, population and basket steps. |
| D9 non-name pieces | **Fixed for the listed rows** | "Gastric adenocarcinoma (first or second line)" → READS_AS_REQUESTED, "its 'or' list read as one name"; "Either gastric adenocarcinoma or NSCLC" → AMBIGUOUS_NAME without "Either". Declared and unchanged: therapy pieces ("after platinum"), "Grade 1, 2 or 3a follicular lymphoma" (UNREADABLE). Residue: N9. |
| F6 acronyms (declared) | **Carried** | "Pediatric AML or MDS" → "Dystonia 11, Myoclonic"; "HCC OR RCC" → Hilar Cholangiocarcinoma, Refractory Cytopenia of Childhood; "RA or PsA" → Refractory Anemia; "… PDAC or CCA" → Congenital Contractural Arachnodactyly. N2 is the same mechanism for ordinary adjectives, with a worse effect. |

## Defects in revision 9, ranked by how much they could mislead

### N1 (high; D1 residue). A leading alternative that is not on `_DEFINING` is folded, so the record is read by its right half and called a different disease

How it happens: in `_list_pieces` a first piece made only of modifier words is tried with the next name's head only
if `_defining(piece)`, that is, if it holds one of 21 listed words. "Relapsing", "refractory", "recurrent",
"metastatic", "localized", "generalized", "advanced", "intermediate", "persistent", "active" are modifier words but not
on the list, so the piece is folded ("Relapsing or progressive multiple sclerosis" is one name), `_conjuncts` returns
None and the screen's lossy coordinated reading (J-a) supplies the class. The NCIt index does hold the borrowed
candidate: `_named("Relapsing multiple sclerosis")` is true (Relapsing Multiple Sclerosis is the request).

| Request | Record name | rev8 | HEAD | Expected |
|---|---|---|---|---|
| RMS | "Relapsing or progressive multiple sclerosis" `[UNK]` (**E2E** Q-1802, `ws_mix9`; memo: "a disease neither requested nor a subtype of one" group) | DIFFERENT_DISEASE | DIFFERENT_DISEASE: "reads as Progressive Multiple Sclerosis (NCIt) once coordination expanded, neither a requested indication nor a subtype of one" | AMBIGUOUS_NAME: Relapsing Multiple Sclerosis (requested); Progressive Multiple Sclerosis (not requested) |
| progressive MS | "Progressive or relapsing multiple sclerosis" `[PASS]` | — | AMBIGUOUS_NAME naming both (the left piece is not a modifier word, so it is split) | (control) |

- **Why it misleads:** it is the outcome U1-6 forbids and D1 described, in neurology instead of haematology; only the
  word changed. The revision-9 note in `ACCEPTANCE.md` says "A modifier that, with the name's head, is its own NCIt
  concept … is read as that concept, never folded or set aside"; for "relapsing" it is folded. The response's §1 says
  "The rule is decided by the NCIt authority, not by a word list alone"; the authority is asked only when the word
  list allows it.
- **Not reached on GAS wording:** my 99,875-name GAS sweep has no gastric name called a different disease outside J-b.
  For state-level requests the same fold gives BROADER_THAN_REQUESTED: "Relapsed or refractory multiple myeloma" for a
  refractory-myeloma request reads "Multiple Myeloma (NCIt) …, broader than requested"; "Locally advanced or metastatic
  gastric adenocarcinoma" for a metastatic-gastric request reads "Gastric Adenocarcinoma …, broader"; "Recurrent or
  metastatic head and neck squamous cell carcinoma" likewise. In each the index reads the borrowed candidate
  (`_named` is true for "Refractory multiple myeloma", "Metastatic gastric adenocarcinoma", "Recurrent head and neck
  squamous cell carcinoma"), so the record names the requested concept and the sentence says it names only its parent.
  Lower harm than the RMS row (the union is broader than the request), same mechanism; counted inside N1.
- **Fix:** try the head-borrowed candidate for every first modifier-only piece (drop the `_defining` precondition, or
  extend it to every word of `_MODIFIER_WORDS` except stage/grade/line tokens); keep folding only when the index does
  not read the candidate. Add the REVIEW7/REVIEW8 guard: no DIFFERENT_DISEASE from a reading whose steps include
  "coordination expanded" unless every half was read.

### N2 (high; new to this review, present since revision 7). A one-word piece is looked up alone, and the index reads an adjective as an unrelated concept, often a gastric one

How it happens: a first piece that is not made only of modifier words is a name ("Diffuse", "Intestinal", "Mixed",
"Symptomatic", "Squamous", "Castration-sensitive", "Limited"), so it is looked up by itself. The frozen index holds
single adjectives as synonyms of specific concepts. A scan of one-word index keys (`out/` inline, see Reproduction)
finds: `diffuse` → Gastric Diffuse Adenocarcinoma, `intestinal` → Gastric Intestinal-Type Adenocarcinoma, `mixed` →
Gastric Mixed Adenocarcinoma, `symptomatic`/`asymptomatic` → Symptomatic/Asymptomatic COVID-19 Infection
Laboratory-Confirmed, `central` → Conventional Osteosarcoma, `endemic` → Endemic Burkitt Lymphoma, `sensitive` →
Hypersensitivity, `moderate` → Moderate COVID-19 Infection. When the lookup fails, the piece is "unread" and the list
falls to UNREADABLE or a single-half class.

| Request | Record name | HEAD (rev8 identical unless marked) | Expected |
|---|---|---|---|
| GAS | "Diffuse or follicular lymphoma" `[UNK]` (**E2E** SOT102, `ws_gas9`; memo: "a name with several NCIt readings" group) | AMBIGUOUS_NAME: "matches several NCIt concepts …: Gastric Diffuse Adenocarcinoma (requested or a subtype); Follicular Lymphoma (not requested)" | DIFFERENT_DISEASE or UNREADABLE naming lymphomas only; never a gastric reading |
| GAS | "Intestinal or extraintestinal Behçet's disease" `[UNK]` (**E2E** Q-1802, `ws_gas9`) | AMBIGUOUS_NAME: "it reads Gastric Intestinal-Type Adenocarcinoma (requested or a subtype) and does not read 'extraintestinal Behcet's disease'" (rev7: UNREADABLE) | no gastric reading |
| GAS | "Diffuse or limited cutaneous systemic sclerosis", "Diffuse or focal glomerulosclerosis", "Diffuse or nodular goiter", "Mixed or pure germ cell tumor", "Intestinal or hepatic schistosomiasis", "Diffuse, follicular, or mantle cell lymphoma" `[UNK]` | AMBIGUOUS_NAME naming Gastric Diffuse / Mixed / Intestinal-Type Adenocarcinoma "(requested or a subtype)" | as above |
| DLBCL | "Diffuse or follicular lymphoma" `[UNK]` | DIFFERENT_DISEASE: "reads as Gastric Diffuse Adenocarcinoma; Follicular Lymphoma (NCIt) …, neither a requested indication nor a subtype of one" | the record names diffuse lymphoma; at least no gastric reading, and not DIFFERENT_DISEASE from half the list |
| MM | "Symptomatic or asymptomatic multiple myeloma" `[UNK]` | UNREADABLE: "it reads Symptomatic COVID-19 Infection Laboratory-Confirmed (not requested) and does not read 'asymptomatic multiple myeloma'" | Multiple Myeloma (requested) |
| COVID-19 | "Symptomatic or asymptomatic multiple myeloma", "Asymptomatic or symptomatic hyperuricemia" `[UNK]` | AMBIGUOUS_NAME naming a COVID-19 concept "(requested or a subtype)" | no COVID-19 reading |
| castration-sensitive prostate carcinoma | "Castration-sensitive or castration-resistant prostate cancer", "Hormone-sensitive or …" `[UNK]` | UNREADABLE: "reads Castration-Resistant Prostate Carcinoma (not requested) and does not read 'Castration-sensitive'" | AMBIGUOUS_NAME naming the request |
| limited-stage SCLC | "Limited or extensive stage SCLC" `[UNK]` | UNREADABLE (the "small cell lung cancer" spelling is read correctly) | AMBIGUOUS_NAME naming the request |
| NSCLC; non-squamous NSCLC | "Squamous or non-squamous NSCLC" `[UNK]` | UNREADABLE: "is not a name the NCIt authority can read" | AMBIGUOUS_NAME or READS_AS_REQUESTED |

- **Why it misleads:** the sentence attributes to the record a disease it never names, and in the CLDN18.2 request's
  own therapy area that disease is the *requested* one: a lymphoma or scleroderma program is shown to the analyst as
  "Gastric Diffuse Adenocarcinoma (requested or a subtype)" and sits in the AMBIGUOUS_NAME group above the different
  diseases. In the other direction a DLBCL record is "a different disease" that "reads as Gastric Diffuse
  Adenocarcinoma". Lauren-type and diffuse/follicular wording is ordinary in oncology vendor cells (judgement on reach;
  not measured).
- **Not in the CLDN18.2 landscape:** no `fin15_ws` cell has this shape.
- **Fix:** never look up a head-less first piece alone. Try it with the next name's head first ("diffuse lymphoma",
  "symptomatic multiple myeloma", "squamous NSCLC"); use that when the index reads it; otherwise name the piece as
  unread. Optionally refuse a single-word reading whose concept label has words the record does not contain
  ("diffuse" → "Gastric Diffuse Adenocarcinoma").

### N3 (medium; new in revision 9). The second piece of a numbered pair loses its defining word: "Type 1 or 2 diabetes mellitus" never names type 2

How it happens: the head borrowing gives "Type 1" the head "diabetes mellitus", but the second piece "2 diabetes
mellitus" keeps no "type". It is unread, so `_state_removed` strips "2" as a stage token and reads "diabetes mellitus".

| Request | Record name (all `[UNK]`) | rev8 | HEAD | Expected |
|---|---|---|---|---|
| T2D | "Type 1 or 2 diabetes mellitus" (**E2E** SOT102, `ws_mix9`), "Type 1 or 2 diabetes" | DIFFERENT_DISEASE (T1D) | AMBIGUOUS_NAME: "… 'Type 1' read as 'Type 1 diabetes mellitus' and '2 diabetes mellitus' read as 'diabetes mellitus' …: Type 1 Diabetes Mellitus (not requested); Diabetes Mellitus (broader than requested)" | Type 1 Diabetes Mellitus (not requested); Type 2 Diabetes Mellitus (requested) |
| T1D | "Type 2 or 1 diabetes mellitus" | DIFFERENT_DISEASE | AMBIGUOUS_NAME: Type 2 (not requested); Diabetes Mellitus (broader) | names T1D (requested) |
| grade 2 follicular lymphoma | "Grade 1 or 2 follicular lymphoma" | — | AMBIGUOUS_NAME: Grade 1 Follicular Lymphoma (not requested); Follicular Lymphoma (broader) | names Grade 2 FL (requested) |
| grade 3a follicular lymphoma | "Grade 2 or 3a follicular lymphoma" | — | Grade 2 FL (not requested); Follicular Lymphoma (broader) | names Grade 3a FL |
| colorectal moderately differentiated adenocarcinoma | "Grade 1 or 2 colorectal adenocarcinoma" | — | Colorectal Well Differentiated Adenocarcinoma (not requested); Colorectal Adenocarcinoma (broader) | names the moderately differentiated concept ('grade 2 colorectal adenocarcinoma' is an index key) |

- **Why it misleads:** the step "'2 diabetes mellitus' read as 'diabetes mellitus'" removes the number that defines
  the disease and calls it a clean-up; the sentence tells the analyst the record names type 1 and a broader diabetes,
  not the requested type 2. The class is AMBIGUOUS_NAME either way (better than revision 8's DIFFERENT_DISEASE), so
  the ranking harm is small. For broad requests (FL, CRC) the class is right and the sentence half right.
- **Fix:** when the first piece is "<defining word> N" and the next piece starts with a bare number or grade token,
  give the next piece the same defining word ("type 2 diabetes mellitus", "grade 2 follicular lymphoma"); never let
  `_state_removed` drop a number that follows a defining word in the record.

### N4 (medium; new in revision 9). The population retry reads a population subtype as its parent and calls it broader than a population-specific request

How it happens: `_population_removed` strips "children with", "pediatric", "adults with", … from an unread piece and
reads the rest. The record's population is then lost, and the relation is computed for the parent. The same record
written with NCIt's own population word ("Childhood ALL") is read as the population concept.

| Request | Record name (all `[UNK]`) | HEAD | Same record in NCIt's wording |
|---|---|---|---|
| ALLA | "Children with ALL or AML" (**E2E** VBC108, `ws_mix9`), "Pediatric patients with ALL or AML" | AMBIGUOUS_NAME: "'Children with ALL' read as 'ALL' …: Acute Lymphoblastic Leukemia (broader than requested); Acute Myeloid Leukemia (not requested)" | "Childhood ALL or AML", "Pediatric ALL or lymphoblastic lymphoma" → DIFFERENT_DISEASE naming Childhood Acute Lymphoblastic Leukemia |
| childhood ALL | "Adults with ALL or AML", "Adult patients with acute lymphoblastic leukemia or AML" | AMBIGUOUS_NAME: ALL (broader than requested) | "Adult ALL or AML" → DIFFERENT_DISEASE (Adult ALL) |
| adult Hodgkin lymphoma | "Pediatric Hodgkin lymphoma or NHL" | AMBIGUOUS_NAME: "'Pediatric Hodgkin lymphoma' read as 'Hodgkin lymphoma'": Hodgkin Lymphoma (broader) | "Adult Hodgkin lymphoma or NHL" for a childhood request → DIFFERENT_DISEASE |
| childhood-onset SLE | "Adult SLE or lupus nephritis" | AMBIGUOUS_NAME: SLE (broader) | — |

- **Why it misleads:** a pediatric program is presented to an adult-indication buyer as "broader than requested"
  (AMBIGUOUS_NAME, above the different diseases) when the record names the sibling population, which NCIt files as a
  separate concept. The step is disclosed, which limits the harm. Where the request is not population-specific (UC,
  T1D) the retry is correct.
- **Residue of D5:** "Adult or pediatric ulcerative colitis or Crohn's disease" (UC) is still UNREADABLE.
- **Fix:** after removing a population, look for the read concept's own population child ("Childhood <label>",
  "Adult <label>", via the label index or `_without_population` in reverse) and use it; if there is none, keep the
  relation but do not call the piece broader when a requested concept carries a population word.

### N5 (medium-low; new in revision 9). An inverted chain attaches only the first defining word: "GVHD, acute or chronic" is unreadable

How it happens: in "X, acute or chronic" the first later piece "acute" inverts with X ("acute X"); the second piece
"chronic" is then tried with the already-inverted name ("chronic acute X"), which the index does not read, so it is
named unread. When only one name is left the whole list returns None and the record falls to "not a name the NCIt
authority can read".

| Request | Record name (all `[UNK]`) | rev8 | HEAD | Expected |
|---|---|---|---|---|
| cGVHD | "GVHD, acute or chronic, or AML" (**E2E** RC118, `ws_mix9`) | UNREADABLE | UNREADABLE: "reads Acute Graft Versus Host Disease (not requested); Acute Myeloid Leukemia (not requested) and does not read 'chronic'" | AMBIGUOUS_NAME naming Chronic GVHD (requested) |
| cGVHD; aGVHD | "GVHD, acute or chronic", "Graft versus host disease, acute or chronic", "GVHD, chronic or acute" | UNREADABLE | UNREADABLE: "is not a name the NCIt authority can read" | AMBIGUOUS_NAME naming both subtypes |
| T1D; T2D | "Diabetes mellitus, type 1 or type 2", "Diabetes, type 1 or type 2", "Diabetes mellitus, type 1, or type 2" | UNREADABLE | UNREADABLE | AMBIGUOUS_NAME naming T1D and T2D |
| ALL | "Leukemia, acute or chronic, or lymphoma" | AMBIGUOUS_NAME | **UNREADABLE** (regression): "reads Acute Leukemia (broader than requested); Lymphoma (not requested) and does not read 'chronic'" | Acute Leukemia (broader); Chronic Leukemia; Lymphoma |

- **Why it misleads:** UNREADABLE is the lowest class, and the record names the requested disease. MeSH-order
  "X, acute or chronic" is a common registry shape (judgement on reach).
- **Fix:** invert each later defining piece with the same base name, not with the previous result.

### N6 (low-medium; new in revision 9). Every all-capitals cell the screen already reads is said to need "a clean-up the gate does not apply"

How it happens: `_raw_lookup` tries `_softened` before `_screen_readings` and sets `screen_reads=False`. For a cell in
capitals that the screen reads (its `indication_readings` give the same concept), U1 now adds "modifier words in
capitals read as ordinary words" and says the gate does not apply the reading; `screen_applies_steps` is false.

| Request | Record name | Screen's own reading | rev8 | HEAD |
|---|---|---|---|---|
| GAS | "ADVANCED NSCLC" `[UNK]` (**E2E** VBC108, `ws_gas9`) | NSCLC, "qualifiers ['advanced']" | "reads as Lung Non-Small Cell Carcinoma (NCIt) once qualifier(s) 'advanced' removed, neither …" | "… once modifier words in capitals read as ordinary words and qualifier(s) 'advanced' removed, **a clean-up the gate does not apply**, neither …" |
| ALL | "RELAPSED AML" | AML, "relapsed" | gate applies | "a clean-up the gate does not apply" |
| adult ALL | "ALL (ADULT)" (`b5`) | ALL, "acronym removed" | gate applies | "a clean-up the gate does not apply" |
| GAS | "STAGE III OR IV GASTRIC CANCER" (**E2E** SOT102, `r8_ws_gas8`) | Stage III Gastric Cancer AJCC v7, "coordination expanded" (shown on the Screening sheet beside it) | — | "a clean-up the gate does not apply" |

- **Why it misleads:** the sentence states something false about the gate (that it does not read the cell as it
  does), and contradicts the Screening sheet's gate reading in the same row. Class unaffected.
- **Fix:** try the screen's readings (and the exact index) before softening; soften only when they read nothing.

### N7 (low; new in revision 9). Quotes from a softened cell are not the record as written

`_softened` lower-cases every modifier word, including the function word "a", and the pieces are then quoted:
- "HCC (CHILD-PUGH A OR B)" → "does not read 'child-PUGH a' or 'B'" (Child-Pugh classes also called names).
- "DIABETES MELLITUS, TYPE 2, OR OBESITY" → "'DIABETES MELLITUS, type 2' read as 'type 2 DIABETES MELLITUS'".
- "GASTRIC ADENOCARCINOMA OR ALL COMERS" → "reads 'ALL comers' as a basket".
- **Fix:** keep the record's own text for quotes; use the softened form only for lookups.

### N8 (low; D7 residue). A grade or line token counts as a second target in a negated cell

`_other_target` counts any word with a digit. "CLDN18.2 negative in G1/G2 tumours" and "CLDN18.2 NEGATIVE IN 2L" →
"… also names another target, which DealScreen does not read apart from it". Expected: "names no other target the
authority reads". (Carried, not counted: REVIEW2's N8 family, where any unread part of a target cell, such as
"stage IV", "ECOG 0-1", "Phase 2", "1L", "Q2W", is "names other targets only".)

### N9 (low). A set-apart severity word is called one of "the names in its 'or' list"

"Crohn's disease or ulcerative colitis, severe", "Ulcerative colitis or Crohn's disease, moderate to severe",
"NSCLC, early, or SCLC", "Gastric adenocarcinoma, high grade, or NSCLC" → "of the names in its 'or' list it … does not
read 'severe'" / "'moderate to severe'" / "'early'" / "'high grade'". The class (AMBIGUOUS_NAME naming the request) is
right; the words are modifiers that did not invert, not names. Expected: "'severe' not read with the name before it".

### Carried, declared (not counted again)

- F6 acronym pieces (above). J-a (outside U1): the gate's coordination reading is lossy; N1 shows it still decides
  the class whenever U1 folds a list.
- REVIEW2 N8 family: unread non-target text in a target cell ("Stage IV", "Phase 2", "ECOG 0-1", "1L", "Q2W",
  "IHC 1+") is SOURCE_NAMES_OTHER_TARGETS, "names other targets only" (re-checked, unchanged since revision 8).

## Judgement calls (labelled; not counted as defects)

- **J-b (carried).** A stage-IV gastric piece beside another disease is DIFFERENT_DISEASE ("NSCLC or Stage IV gastric
  cancer"); all 493 DIFFERENT_DISEASE rows of my GAS sweep are this shape.
- **J-h (new).** "Gastric adenocarcinoma or carcinoma / malignant neoplasm / neoplastic disease / other neoplasms" call
  the second piece "a basket of diseases, not one name" although NCIt has Carcinoma, Malignant Neoplasm and Neoplasm.
  Consistent with the stand-alone BASKET class; the record is AMBIGUOUS_NAME naming the request either way.
- **J-i (`_whole` reach).** `_whole` reads index synonyms that contain "or". The index maps "relapsed or refractory high
  risk myelodysplastic syndrome" to Recurrent Acute Myeloid Leukemia, Myelodysplasia-Related, so "Advanced relapsed or
  refractory high risk myelodysplastic syndrome" (AML request, `[UNK]`) is now READS_AS_REQUESTED (rev8: UNREADABLE):
  an MDS record in the top class of an AML screen. The reading is the authority's own synonym and the step is shown;
  the exact name already read so in revision 8 (`[PASS]`). "Advanced stomach or intestinal disorder" now reads the
  index's Digestive System Disorder instead of two pieces; also authority-supported.
- **J-k.** "STAGE III OR IV GASTRIC CANCER" and "Stage III or IV gastric cancer" read only Stage III Gastric Cancer
  (the screen's coordination drops "IV"); the class UNDER_REQUESTED_PARENT is right, the sentence names half the
  record. Lower case was the same in revision 8.
- **J-l.** "Arthritis, juvenile, or uveitis" (JIA) moved AMBIGUOUS_NAME → UNREADABLE because no piece reads a
  requested concept; it now names 'juvenile' as unread, as REVIEW8 asked.

## Science (step 3)

- CLDN18.2: `fin15_ws/screening.json` vs `baseline/screening_R1.json`: disposition, rank, decisions,
  machine_recommendation and transaction_rank identical for all 62 programs; `transaction` differs on 13 (R1's);
  `unknown_diagnostics` differs (U1's). `fin15_ws` = `fin14_ws` = `after/screening_u1.json` byte for byte.
- A copy screened fresh at HEAD is byte-identical to `fin15_ws`; a copy screened with U1 stubbed out differs only in
  `unknown_diagnostics`. My E2E workspaces were not stub-compared (their science is irrelevant to U1's sentences).
- Held-out `xv15f` vs `xv10`: zero differing per-program keys and equal top level in c5_heldout, fcrn_v1, fcrn_v2,
  synthetic_200; the same against `xv14f`.

## Reading the outputs as a BD analyst

`after/` is current at HEAD: the memo is identical and the workbook cell-identical (timestamp apart) to a fresh export
of `fin15_ws`, and `git log` shows `after/` last changed in `624b2f0`. REVIEW8's reading of the 38 CLDN18.2 actions
holds unchanged: each states what is on record, its class, the one cited fact that decides the gate and the `assert`
field; the basket programs name both requested indications; the PD-1 rows name the other targets; SOT102 ("Pancreatic
Cancer") is the one reference-IN different disease, reported. The memo's only "in scope"/"out of scope" words are in
the buyer's own need statement; no action has scope or recommendation wording. Still less useful (carried): the
repeated "The gate never fails on this evidence…" tail and "'PD-1' not read by the target authority".

Nothing is hidden: every UNKNOWN on a non-excluded program has its diagnostic in `fin15_ws`, the held-out landscapes
and all five E2E workspaces I screened.

What an analyst would not see: in a gastric screen whose landscape includes lymphoma, Behçet's or scleroderma
programs written "Diffuse or …"/"Intestinal or …" (N2), the Diligence sheet tells the analyst the record reads as
gastric diffuse or intestinal-type adenocarcinoma, requested. In an MS screen a relapsing-MS program sits among "a
disease neither requested nor a subtype of one" (N1). In a diabetes screen "Type 1 or 2 diabetes mellitus" never
mentions type 2 (N3). In an adult-leukaemia screen a pediatric program is a "broader" lead (N4). In a capitalised
export every cell the gate reads is said not to be read by the gate (N6).

## What I could not check

- Cycle-4 equivalence (`equivalence.main()`): not re-run; the implementer reports 4/4 byte-identical and REVIEW8
  confirmed it at revision 8. Revision 9 touches no file outside the two U1 modules and R1's rights code, and the
  held-out workspaces are unchanged, so I judge the risk low, but it is not verified here.
- The held-out landscapes' workbooks and memos (I read their `screening.json` only; they are unchanged since `xv10`).
  For my E2E workspaces I read the Diligence sheets and the markdown memos; the `.docx` memos were not generated.
- Reach: how often vendor cells use "Relapsing or …", "Diffuse or …", "Type 1 or 2 …", "Children with …", or MeSH-order
  "X, acute or chronic" is my judgement, not measured.
- Whether the revision-9 tests were written before the code was tuned.
- The NCIt claims (index keys "diffuse", "intestinal", "mixed", "symptomatic", "relapsing multiple sclerosis",
  "grade 2 colorectal adenocarcinoma", "relapsed or refractory high risk myelodysplastic syndrome") were checked through
  the U1 code against the frozen authority, not against NCIt directly.
- The rights code (under concurrent review): not touched. `git status` at start showed only `AGENTS.md`, the
  cycle-4 `equivalence_result.json`, `biotech_tickers.yaml` and untracked files modified, none a U1 module; an
  untracked `research/dealscreen_rights_v1/REREVIEW14.md` and uncommitted edits to `rights_quote.py` and
  `rights_template.py` appeared during this review (another session's, not mine). `git diff HEAD` shows no change to
  any U1 module (`diagnostics.py`, `indication_relations.py`, `indications.py`, `screening.py`, `facts.py`,
  `workbook.py`, `memo.py`, `cli/dealscreen.py`), so every U1 output above is HEAD's. Later screens may have run with
  those rights edits; the fresh CLDN18.2 screen is byte-identical to `fin15_ws`, and my U1-3 stub comparison uses one
  tree for both sides.
- None of N1–N9 fixes were implemented or tested.

## Reproduction

```
cd /home/djmann/projects/bve-b8 && . .venv/bin/activate && export TMPDIR=$HOME/.cache/dealscreen_suite
python -m pytest tests/dealscreen -q -p no:cacheprovider          # 1886 passed, 5 warnings, 282 s
/tmp/claude-1000/u1rr9/runall.sh                                   # every earlier probe -> /tmp/claude-1000/u1rr9/out/
P=/tmp/claude-1000/u1rr9/probes
python3 $P/chg.py /tmp/claude-1000/u1rr8/out/h8.out /tmp/claude-1000/u1rr9/out/h8.out   # class changes rev8 -> HEAD
python $P/cmp89.py $P/a1.txt    # defining words, head borrowing (N3 rows, CKD, MI, HF)
python $P/cmp89.py $P/a2.txt    # numbered pairs (N3), inverted chains (N5), set-apart pieces (N9)
python $P/cmp89.py $P/a3.txt    # population retry (N4), baskets (D2, J-h)
python $P/cmp89.py $P/a4.txt    # capitals (D4, N6, N7)
python $P/cmp89.py $P/a5.txt    # leading adjectives outside _DEFINING (N2)
python $P/cmp89.py $P/a6.txt    # N1 and N2 core rows, state-level requests
python $P/cmp89.py $P/a7.txt    # _whole reach (J-i), stage rows (J-k)
python $P/t9.py                 # target: N8 and the N8-family rows (t9_r8.py: the same at rev8)
python $P/sweep9.py             # GAS sweep, 99,875 names
bash /tmp/claude-1000/u1rr9/buildall.sh                            # E2E ws_gas9, ws_mix9 (import, rights, screen, export, memo)
python3 /tmp/claude-1000/u1rr7/probes/txdiff.py <fin15_ws/screening.json> research/dealscreen_unknown_actions_v1/baseline/screening_R1.json
python /tmp/claude-1000/u1rr6b/probes/nou1.py <copy of a workspace>   # screen with U1 stubbed out
python3 /tmp/claude-1000/u1rr/science_diff.py <screening.json> <reference screening.json>
python3 /tmp/claude-1000/u1rr/coverage.py <screening.json ...>
```

Scratch workspaces (copies; originals not modified):
- `ws_copy` (fresh CLDN18.2 screen; `ws_copy_out.xlsx`, `ws_copy_memo.md`), `ws_nou1` (U1 stubbed out).
- `r8_ws_gas8`, `r8_ws_heme8`, `r8_ws_uc8`: REVIEW8's E2E workspaces re-screened at HEAD.
- `ws_gas9` (`e2e_gas9/`): GAS request; SOT102 "Diffuse or follicular lymphoma", Q-1802 "Intestinal or
  extraintestinal Behcet's disease", VBC108 "ADVANCED NSCLC", RC118 "Gastric adenocarcinoma or other carcinomas".
- `ws_mix9` (`e2e_mix9/`): request [type 2 diabetes mellitus, relapsing multiple sclerosis, adult acute lymphoblastic
  leukemia, chronic graft versus host disease]; SOT102 "Type 1 or 2 diabetes mellitus", Q-1802 "Relapsing or
  progressive multiple sclerosis", VBC108 "Children with ALL or AML", RC118 "GVHD, acute or chronic, or AML".

## Summary of defects

| Severity | Count | Ids |
|---|---|---|
| High | 2 | N1, N2 |
| Medium | 2 | N3, N4 |
| Medium-low / low-medium | 2 | N5, N6 |
| Low | 3 | N7, N8, N9 |

New in revision 9: N3, N4, N5, N6, N7 (N8, N9 residues of D7, D9). Present before revision 9 and not reported:
N2. D1 residue, present since before revision 7: N1.

Single highest-value next fix: in `_list_pieces`, try the head-borrowed candidate for **every** head-less first piece
(any modifier-only piece, not only `_DEFINING` words, and any lone adjective such as "Diffuse", "Squamous",
"Symptomatic"), use it when the NCIt index reads it, and never look such a piece up alone; add the long-requested
guard that no DIFFERENT_DISEASE comes from a "coordination expanded" reading unless every half was read. That closes
N1 and N2 and, by carrying the defining word into the next piece, most of N3.
