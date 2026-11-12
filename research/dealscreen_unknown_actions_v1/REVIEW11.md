# Cycle U1 revision 11: eleventh adversarial review

INTERNAL DEVELOPMENT. This review was run by an AI. It is not a human review or an independent validation, and
nothing in it is an approval.

**Reviewed:** HEAD `3dd6b51` on `dealscreen-mvp` in `/home/djmann/projects/bve-b8`, read only. It holds U1 revision 11
committed together with R1 revision 17; U1 revision 10 is `f1a310d`. Among the U1 modules, `git diff f1a310d 3dd6b51`
changes only `indication_relations.py` (+56 lines) and the tests; `diagnostics.py`, `screening.py`, `facts.py`,
`workbook.py`, `memo.py` and the CLI are unchanged.
**Criteria:** `ACCEPTANCE.md` with its revision notes, `MEASUREMENT.md`, `REVIEW10.md` and `REVIEW10_RESPONSE.md`.

Every number below was recomputed by running code unless it is marked "read, not re-run". Scratch files, probes and
workspaces are in `/tmp/claude-1000/u1rr11/`.

Abbreviations:
- "r10" means revision 10's two U1 modules loaded beside HEAD from `git show f1a310d:…` (`rev10/`). The probe
  `probes/cmp1011.py` prints r10 and HEAD for each `KEY|name` line (`--cases` adds the upper- and lower-case forms).
  `probes/casecmp.py` prints rows whose class or "does not read" differs between as-written, UPPER, lower and Title case.
- `GAS` is the CLDN18.2 request `["gastric adenocarcinoma", "gastroesophageal junction adenocarcinoma"]`. Every other
  request was checked through `ir.read_request` to be exactly one NCIt concept (e.g. `CDI` central diabetes insipidus →
  Neurogenic Diabetes Insipidus; `CAD` cold agglutinin disease; `MPC` metastatic prostate carcinoma; `SMA2` spinal
  muscular atrophy type 2; `MEL` melanoma; `CKD` chronic kidney disease).
- `[UNK]` means the gate's positive reading does not pass, so the diagnostic is shown. Every defect row below is `[UNK]`.
- "E2E" means confirmed through `bve-dealscreen import`, `import-rights`, `screen`, `export` and `memo` on a workspace
  built from the `fin17_ws` inputs with four indication cells edited (`build.sh`, `buildall.sh`):
  - `ws_g11` (GAS request): SOT102 "Gastric adenocarcinoma, stage III or IV", Q-1802 "Sensitive or resistant gastric
    cancer", VBC108 "Metastatic or gastroesophageal junction signet ring cell carcinoma", RC118 "Gastric
    adenocarcinoma (stage 3 or 4)".
  - `ws_x11` (request [central diabetes insipidus, cold agglutinin disease, metastatic prostate carcinoma, spinal
    muscular atrophy type 2]): SOT102 "Central, nephrogenic or gestational diabetes insipidus", Q-1802 "Cold or warm
    autoimmune hemolytic anemia", VBC108 "Metastatic or neuroendocrine prostate carcinoma", RC118 "Spinal muscular
    atrophy, type 1 or 2".

## Verdict in one paragraph

Revision 11 changes no science, coverage is still complete, and letter case no longer decides what U1 reads: across
182 earlier probe rows and 165 of mine in four letter cases, only lower-case "all" (the English word) still reads
differently. REVIEW10's P1, P3, P7, P8 and P9 are fixed; P2, P4, P5 and P6 are fixed for the rows listed. **U1-7 is
still not met.** Two of the new rules make new false or lossy statements, both confirmed end to end:

1. **Q1 (high, new).** `_alone` now keeps every index synonym whose label does not hold the word. That brings back
   acronyms and "hives", but it also lets ordinary English words name unrelated diseases. "Central" is read as
   Conventional Osteosarcoma, "cold" as COPD and upper respiratory infection, "sensitive" as Hypersensitivity, and
   "diagnosis" as Disease or Disorder. Example: "Central, nephrogenic or gestational diabetes insipidus" for a
   central-DI buyer. Revision 10 named the requested concept (AMBIGUOUS_NAME). Revision 11 makes it UNREADABLE and
   says the record reads Conventional Osteosarcoma (E2E).
2. **Q2 (high, new).** The P5 change sends every "stage N" piece after a name to the inversion branch. When
   "stage N <name>" is not an NCIt label, the piece is marked unread. The list then has one name left, and
   `_list_pieces` throws it away together with the unread pieces. "Gastric adenocarcinoma, stage III or IV" was
   READS_AS_REQUESTED and is now NAMES_REQUESTED_SITE, "is not a name the NCIt authority reads" (E2E). "Melanoma,
   stage 3 or 4" was READS_AS_REQUESTED and is now UNREADABLE. In a sample of 250 one-concept NCIt labels L,
   "L, stage III or IV" with L requested was READS_AS_REQUESTED for 250 at r10; at HEAD it is 249 times UNREADABLE or
   NAMES_REQUESTED_SITE.
3. **Lower-severity defects (Q3 to Q8).**
   - The new site test counts histology words as sites, so it refuses endings the record needs (Q3).
   - It misses sites the request itself names (Q4).
   - The numbered inversion works only in prefix order (Q5).
   - Ordinals still attach to a numbered word (Q6).
   - A duplicated NCIt label is shown as both "not requested" and "requested" (Q7).
   - The response's list of changed probe rows misses the Q2 rows (Q8).

## Verdict per criterion

| AC | Verdict | Evidence |
|---|---|---|
| U1-1 coverage | **Met** | `coverage.py`: `fin17_ws` 38/38. `xv17f`: c5_heldout 28/28, fcrn_v1 28/28, fcrn_v2 28/28, synthetic_200 20/20, so 104/104. Nothing missing, nothing extra. In `ws_g11` and `ws_x11` every edited UNKNOWN carries a diagnostic on the Diligence sheet, the Screening sheet and the memo. |
| U1-2 authorities only | **Met (letter)** | Of the 56 `+` lines in `indication_relations.py`, disease words occur only in comments and docstrings (grep for gastr, cldn, gej, her2, crohn, colitis, leuk, gvhd, diabet, anemia, lymphom, myelo, nsclc, sepsis, pancrea, pharyn, prostat, cholang, urtic, hives, epilep, sclerosis, neuroendo, squamous). The new tests (`_names_site`, `_number`, `_numbered_piece`, `_alone`) use the NCIt index, labels and the "<site> Neoplasm" node names. Note: Q1 and Q3 come from taking NCIt's synonym and site tables at face value, not from landscape words. |
| U1-3 no change to science | **Met** | `science_diff.py` `fin17_ws` against `baseline/screening_R1.json`: 13 of 62 programs differ, in `transaction` only (R1's field). Disposition, rank, decisions, machine_recommendation and transaction_rank are unchanged, and the top level is equal. `txdiff.py`: 11 of the 13 are identical once `external_id`/`related_deal_id` are removed; the other two are Zolbetuximab and IMAB362, as in REVIEW9 and REVIEW10. `fin17_ws` against `fin16_ws`: only `unknown_diagnostics` differs, on one program (IBI343, its `strategy.indication` sentence). A fresh screen of a copy of `fin17_ws` is byte-identical. Held-out `xv17f` against `xv10` and against `xv16f`: 0 differing per-program keys and an equal top level in all four landscapes. |
| U1-4 held-back tests | **Met as written; not enough in substance** | `python -m pytest tests/dealscreen -q -p no:cacheprovider`: **2,076 passed**, 5 warnings, 174 s. The revision-11 block tests REVIEW10's rows in three cases. It has no control for a trailing stage pair that does not invert into an NCIt name (Q2). It has no ordinary-word synonym control (Q1). It has no histology word before a borrowed ending (Q3). The earlier probe row "Gastric adenocarcinoma (Stage III or IV)" (READS_AS_REQUESTED at r10) is not locked by any test, and it regressed. |
| U1-5 surfaces | **Met** | A fresh export and memo from a copy of `fin17_ws` match `after/`. `memo_u1.md` is byte-identical. `screening_u1.json` is equal. `u1_cldn18.xlsx` matches on all 9 sheets except the README timestamp (P9 fixed). In the E2E workspaces the Diligence "Next action", the Screening class and the memo's single-gate list all carry HEAD's sentences, so Q1–Q4 reach all three surfaces. |
| U1-6 per program vs reference | **Met as measured on CLDN18.2; harm reachable in the request's own therapy area (Q1, Q2)** | `measurement.json` class counts equal revision 10's. The only CLDN18.2 sentence that changed is IBI343 (P8 step added, class unchanged). Joining on program name matches 25 of the 30 reference-IN programs (12 ELIGIBLE, 12 UNRESOLVED, 1 EXCLUDED); among them the only DIFFERENT_DISEASE is SOT102 ("Pancreatic Cancer"), as before. Not in this landscape but in its therapy area: "Gastric adenocarcinoma, stage III or IV" drops from READS_AS_REQUESTED (Q2, E2E), and "Sensitive or resistant gastric cancer" is shown reading Hypersensitivity (Q1, E2E). |
| U1-7 adversarial review | **Not met** | Q1 and Q2 (high) are confirmed end to end. I found no hidden UNKNOWN, no stray diagnostic, no scope or recommendation wording and no change to science. |

## Status of REVIEW10's findings (P1 to P9)

How I checked:
- Every earlier probe was re-run unchanged (`runall.sh`, outputs in `out/earlier/`) and diffed against REVIEW10's
  (`/tmp/claude-1000/u1rr10/out/`).
- REVIEW10's `b1`–`b5` were run through `cmp1011.py` (r10 against HEAD, `out/r10_b*.out`) and through `casecmp.py`.
- Identical to REVIEW10: a1–a3, a5–a7, b5, p1–p3, p5–p10, `r3_p_*`, `p_ind4`, `p_sib`, `p_tgt4`, `restate`, `sites6`,
  `sib6`, `misc6`, `bk6`, `i6*`, `orq`, `bas`, `prop`, `prop2`, `t5`–`t9`, `ta5`. p4 has the same lines in a different
  order. So the following are unchanged at HEAD for every earlier input (the code is unchanged too):
  - the stage-only sibling rule
  - the restatement rule
  - the neoplasm-node site rule and lineage list used for NAMES_REQUESTED_SITE
  - role words, baskets and acronyms
  - negation and parenthesis handling in target text
  - placeholders
- Changed: a4, h7, h8, o7_all, q7, f, slash, caps, `u1r9_probe`, `u1r10_probe` and the sweep. They are discussed
  below and in Q2/Q8.
- `sweep9.py` (99,875 GAS names): 3,468 flagged, against 3,700 at r10. All 232 rows that left the flagged set are
  capitals rows the P1 shortcut had called DIFFERENT_DISEASE ("DIFFUSE GASTRIC CANCER OR ESOPHAGEAL ADENOCARCINOMA",
  …), and no row joined it. The sweep has no trailing-stage form, so it cannot see Q2.
- `capscmp.py` over REVIEW10's case probe sets: 34 rows differed by case at r10; 1 does at HEAD ("CML OR PH+ ALL"
  reads Ph+ ALL in capitals only, which is harmless).

| Id | Status | Input → output at HEAD |
|---|---|---|
| P1 capitals shortcut drops unread pieces | **Fixed** | Every P1 row now names its unread piece and none is DIFFERENT_DISEASE. "GASTRIC/GEJ ADENOCARCINOMA OR NSCLC" and "GEJ OR NSCLC" are NAMES_REQUESTED_SITE. "MGC OR NSCLC", "NSCLC OR PAIN", "SEVERE NSCLC OR PAIN", "CGVHD OR BRONCHIOLITIS OBLITERANS", "CHILDHOOD UC OR CROHN'S DISEASE", "LIMITED OR EXTENSIVE STAGE SCLC", "ADOLESCENTS/YOUNG ADULTS WITH ALL OR AML", "ADULT T-CELL LEUKAEMIA OR CTCL" and "CASTRATION-SENSITIVE OR CASTRATION-RESISTANT PROSTATE CANCER" are UNREADABLE with "does not read '…'". "NON-METASTATIC OR METASTATIC CRPC" is NAMES_REQUESTED_SITE. "ADVANCED NSCLC" and "RELAPSED AML" still take the gate's steps. I looked for a capitals cell that U1 reads wrongly but completely, where the shortcut would now pass a wrong reading through. The shortcut returns the gate's codes only when they equal U1's, so the class cannot change. The rows I tried with a wrong U1 reading (Q1 words in capitals) had different codes and kept U1's reading. |
| P2 acronyms and synonyms rejected | **Fixed for the listed rows; new defect Q1** | "mCRPC or mHSPC", "mCRPC or nmCRPC", "HCC or iCCA", "iCCA or eCCA", "ccRCC or pRCC", "nsclc or sclc", "Hives or angioedema", "Sepsis or septic shock", "Epilepsy or migraine" and "stad or esca" are AMBIGUOUS_NAME naming the request again, in every case. Disclosed F6: "iCCA" also reads "Infantile Convulsions and Paroxysmal Choreoathetosis, Familial" and "mds" reads Dystonia 11. New: the same rule keeps ordinary words' synonyms (Q1). |
| P3 N2 not fixed in capitals | **Fixed** | "DIFFUSE OR FOLLICULAR LYMPHOMA" (GAS and DLBCL), "INTESTINAL OR EXTRAINTESTINAL BEHCET'S DISEASE", "DIFFUSE OR FOLLICULAR LYMPHOMA OR PAIN" and "SYMPTOMATIC OR ASYMPTOMATIC MULTIPLE MYELOMA" no longer read a gastric or COVID-19 concept. "MIXED OR PURE GERM CELL TUMOR" now reads Mixed Germ Cell Tumor. |
| P4 borrowed ending drops a site | **Fixed for the listed rows; new defect Q3, residue Q4** | "Metastatic or pancreatic neuroendocrine carcinoma" (LNEC) is DIFFERENT_DISEASE reading Pancreatic NEC only. "Recurrent or pharyngeal SCC", "Metastatic or cutaneous SCC" and "Metastatic or anal SCC" (LSCC) are DIFFERENT_DISEASE, no longer "shares subtypes". "Relapsing or progressive multiple sclerosis" still names Relapsing MS. |
| P5 inverted numbered list unread | **Partly fixed; regression Q2; residue Q5** | "Diabetes mellitus, type 1 or 2", "Diabetes (type 1 or 2)", "Obesity or diabetes mellitus, type 1 or 2", "Follicular lymphoma, grade 1 or 2 / (grade 1 or 2) / grade 3a or 2" and "Gastric cancer, stage III or IV / IIIb or IV" now name the requested concept, in all three cases. Not fixed: a base whose NCIt label puts the number after it ("Spinal muscular atrophy, type 1 or 2", Q5). Regressed: a stage pair that does not invert into an NCIt label (Q2). |
| P6 line token numbered; carried prefix quoted | **Partly fixed; residue Q6** | "Stage III or 2L gastric cancer" no longer says "Stage 2L". "Grade 1 or 2 obesity or type 1 diabetes" quotes "'Grade 1 or 2 obesity'". Not fixed: ordinals ("Stage III or 1st line gastric cancer" → "'1st line gastric cancer' read as 'Stage 1st line gastric cancer'"). The class is unaffected. |
| P7 base carried across a basket | **Fixed** | "GVHD, acute, or other solid tumors, chronic" says "does not read 'chronic' with the name before it" and no longer names Chronic GVHD. "GVHD, chronic, or solid tumors, acute" and "Diabetes mellitus, or solid tumors, type 2" are treated the same way (the second is now UNREADABLE naming Diabetes Mellitus; this follows the rule as stated, and the input is contrived). |
| P8 nested steps hidden | **Fixed** | IBI343 ends "… and in 'Unresectable or Metastatic Gastric Adenocarcinoma', its 'or' list split into 2 names and 'Unresectable' read as 'Unresectable Gastric Adenocarcinoma'". "Recurrent or metastatic gastric or esophageal cancer" shows "in 'Recurrent or metastatic gastric cancer', 'recurrent' removed and 'metastatic' removed". The steps are true; the sentence is long (wording only). |
| P9 `after/` stale | **Fixed** | See U1-5. |
| J-a (outside U1) | **Carried** | The gate's coordination reading is unchanged. |

## Defects in revision 11, ranked by how much they could mislead

### Q1 (high; new in revision 11). `_alone` keeps any synonym whose label does not hold the word, so ordinary English words in a list name unrelated diseases

How it happens: `_alone` (line 782) refuses a one-word piece's reading only when the word is a non-head word of the
label. A reading whose label does not hold the word at all is always kept. The NCIt index maps many ordinary words to
unrelated concepts. Revision 10 refused these (the word was not the label's head) and then tried the piece with the
next name's head, which is the record's own coordination. Revision 11 keeps the synonym, so the head is never tried.

Index scan (`probes/alone_scan.py`, `out/alone_scan.txt`):
- 1,721 one-word non-modifier keys have a reading kept whose label lacks the word.
- 604 of them are not initials of their label.
- Of those, the words NCIt itself uses as a non-head word in other labels (`out/alone_adj.txt`) are the dangerous
  ones: `central` (233 labels) → Conventional Osteosarcoma; `sensitive` (44) → Hypersensitivity; `infection` (21);
  `cold` (7) → Chronic Obstructive Pulmonary Disease and Upper Respiratory Tract Infection.
- Others: `diagnosis` → Disease or Disorder, `recurrence` → Recurrent Neoplasm, `cello` → Barrett Esophagus,
  `stenotic` → Obstructive Ureterocele, `spleen` → Splenic Hodgkin Lymphoma, `stump`, `lamb`, `castle`, `candle`.

| Request | Record name (all `[UNK]`) | r10 | HEAD | Expected |
|---|---|---|---|---|
| CDI | "Central, nephrogenic or gestational diabetes insipidus" (**E2E** SOT102, `ws_x11`; memo: "no name the NCIt authority reads as a whole") | AMBIGUOUS_NAME: Neurogenic Diabetes Insipidus (requested); Nephrogenic DI; does not read 'gestational diabetes insipidus'; "'Central' read as 'Central diabetes insipidus'" | UNREADABLE: "reads Conventional Osteosarcoma (not requested); Nephrogenic Diabetes Insipidus (not requested) and does not read 'gestational diabetes insipidus'" | r10's |
| CDI | "Central or nephrogenic DI", "Diabetes insipidus, central or nephrogenic", "Central or nephrogenic diabetes insipidus, or polyuria" | UNREADABLE, "does not read 'Central'" | UNREADABLE, "reads Conventional Osteosarcoma" | no osteosarcoma |
| CAD | "Cold or warm autoimmune hemolytic anemia" (**E2E** Q-1802, `ws_x11`; memo: "a disease neither requested nor a subtype of one") | UNREADABLE: "does not read 'Cold'" | DIFFERENT_DISEASE: "reads as Chronic Obstructive Pulmonary Disease; Upper Respiratory Tract Infection; Warm Antibody AIHA" | r10's |
| COPD | same name | UNREADABLE | AMBIGUOUS_NAME: "Chronic Obstructive Pulmonary Disease (requested or a subtype)" | not requested |
| GAS | "Sensitive or resistant gastric cancer" (**E2E** Q-1802, `ws_g11`) | NAMES_REQUESTED_SITE: "names gastric … does not read 'Sensitive'" | AMBIGUOUS_NAME: "Hypersensitivity (not requested); Gastric Carcinoma (broader) …", and the site is no longer named | r10's |
| refractory SCLC / nephrotic syndrome / HGSOC | "Sensitive or refractory small cell lung cancer", "Sensitive or resistant nephrotic syndrome", "Sensitive or resistant high grade serous ovarian cancer" | "does not read 'Sensitive'" | "Hypersensitivity (not requested)" listed as read; for a Hypersensitivity request it is "requested or a subtype" | no Hypersensitivity |
| GAS | "Diagnosis or treatment of gastric adenocarcinoma", "Recurrence or metastasis of gastric cancer", "Cold or hot tumors of the stomach", "Central or peripheral nervous system metastases of gastric cancer" | NAMES_REQUESTED_SITE, nothing read | NAMES_REQUESTED_SITE, plus "reads Disease or Disorder (broader than requested)", "Recurrent Neoplasm (shares subtypes …)", "Chronic Obstructive Pulmonary Disease", "Conventional Osteosarcoma" | no such reading |

The same names in capitals and in lower case give the same output, so letter case does not hide this.

- **Why it misleads:** the sentence names a disease the record does not name. A record of the buyer's own disease
  moves down to UNREADABLE or DIFFERENT_DISEASE. This is the exact class of error U1-7 forbids. Revision 10 got these
  right in lower case. REVIEW10's suggested fix ("keep a reading whose label holds no word of the piece") caused this,
  and the response did not test that half.
- **Reach:** "Central or nephrogenic DI", "Cold or warm AIHA" and "Sensitive or refractory SCLC" are standard
  clinical shorthand. How often they occur in a vendor "or" cell is my judgement, not measured.
- **Fix:**
  - For a one-word piece followed by a name, try "<piece> <next head>" before keeping a synonym, as revision 10 did.
    The record's own coordination outranks an index synonym.
  - Keep a synonym reading without that test only when the piece is initials of the label (`_initials`), or when the
    word is never used as a non-head word in NCIt labels. That count comes from the authority itself.

### Q2 (high; new in revision 11). A trailing stage pair that does not invert into an NCIt name throws away the whole list, including the name U1 can read

How it happens: line 711 adds `_numbered_piece(piece)` to the inversion branch. "stage III" after a name now goes
there instead of being set aside (r10: "'stage III' set aside as a modifier, not a name", which also set
`set_aside`). If "stage III <name>" is not an NCIt label, the piece goes to `out.unread`. Only one name is left and
`set_aside` is False, so line 735 returns None. The unread pieces and the readable base are both discarded, and the
whole cell falls back to the whole-name lookup, which reads nothing.

| Request | Record name (all `[UNK]`) | r10 | HEAD | Expected |
|---|---|---|---|---|
| GAS | "Gastric adenocarcinoma, stage III or IV" (**E2E** SOT102, `ws_g11`) | READS_AS_REQUESTED: Gastric Adenocarcinoma, stages set aside | NAMES_REQUESTED_SITE: "names gastric, a requested site, but is not a name the NCIt authority reads." | r10's |
| GAS | "Gastric adenocarcinoma (stage 3 or 4)" (**E2E** RC118), "Gastric adenocarcinoma (Stage III or IV)" (REVIEW8's `slash` probe), "Gastric adenocarcinoma, stage 3 or 4" | READS_AS_REQUESTED | NAMES_REQUESTED_SITE, nothing read | r10's |
| GAS | "Gastric cancer, stage 3 or 4" | AMBIGUOUS_NAME_ALL_BROADER (Gastric Carcinoma) | NAMES_REQUESTED_SITE, nothing read | r10's |
| MEL | "Melanoma, stage 3 or 4" | READS_AS_REQUESTED | UNREADABLE: "is not a name the NCIt authority can read." | r10's |
| CKD / BRCA / CRC | "Chronic kidney disease, stage 3 or 4", "Breast cancer, stage 2 or 3" / "(stage 2 or 3)", "Colorectal cancer, stage 3 or 4" | READS_AS_REQUESTED / AMBIGUOUS_NAME naming the request | NAMES_REQUESTED_SITE, nothing read | r10's |

- **Measured** (`probes/q2sweep.py`, `out/q2sweep.out`): 250 random NCIt labels L of 2–4 words that are one concept,
  with L requested and the gate `[UNK]`.
  - "L, stage III or IV": READS_AS_REQUESTED for 250/250 at r10. At HEAD it is 167 UNREADABLE, 82
    NAMES_REQUESTED_SITE and 1 READS_AS_REQUESTED.
  - "L (stage 3 or 4)": the same.
  - "L, grade 1 or 2" and "L, type 1 or 2" were already 250/250 UNREADABLE or NAMES_REQUESTED_SITE at r10, and still
    are. That is the same collapse, carried, because "grade" and "type" were already in `_DEFINING`.
- **Why it misleads:** the record names the requested concept exactly, with a stage qualifier. U1 says the authority
  cannot read it, shows no unread piece, and drops it to the bottom class when the request has no site word. This is
  the most common way vendors and registries write a stage, and it is in the CLDN18.2 request's own therapy area.
- **Disclosure:** not disclosed. The response's §3 lists the earlier probe rows that changed, but omits `slash`'s
  "Gastric adenocarcinoma (Stage III or IV)" (Q8).
- **Fix:**
  - When `out.unread` is not empty, return the pieces even with one name, so `_conjuncts` reads the base and names
    the unread pieces.
  - Or set aside a numbered piece that does not invert, as revision 10 did for stage.
  - Add the stage, grade and type forms of a plain requested label as tests, in all three cases.

### Q3 (medium; new in revision 11). `_names_site` counts histology and lineage words as sites, so it refuses endings the record needs

How it happens: `_names_site` tests the dropped words against the raw `_neoplasm_sites()` set. That set has 1,800
phrases. It is not filtered the way `_site_names` filters (morphology lineage, `_clean_site`), so it holds
"neuroendocrine", "neural", "vascular", "mesenchymal", "stromal", "fibrous", "lymphoid", "myeloid", "endocrine",
"plasma cell", "mast cell" and even "advanced b cell" and "accelerated phase myeloproliferative".

| Request | Record name (all `[UNK]`) | r10 | HEAD | Expected |
|---|---|---|---|---|
| MPC | "Metastatic or neuroendocrine prostate carcinoma" (**E2E** VBC108, `ws_x11`) | AMBIGUOUS_NAME: Metastatic Prostate Carcinoma (requested); does not read 'neuroendocrine prostate carcinoma' | NAMES_REQUESTED_SITE: "names prostate … but is not a name the NCIt authority reads." | r10's |
| metastatic lung adenocarcinoma | "Metastatic or neuroendocrine lung adenocarcinoma" | AMBIGUOUS_NAME naming the request | NAMES_REQUESTED_SITE, nothing read | r10's |
| metastatic CRC | "Metastatic or vascular colorectal carcinoma" | AMBIGUOUS_NAME naming the request | NAMES_REQUESTED_SITE, nothing read | r10's |
| RMS | "Relapsing or neural multiple sclerosis" | AMBIGUOUS_NAME naming Relapsing MS | UNREADABLE | r10's |

- **Why it misleads:** the record names the requested concept ("metastatic … prostate carcinoma"), and it drops to
  "not a name the NCIt authority reads". "Neuroendocrine prostate carcinoma" (NEPC) is a standard term. The disclosed
  limit covers only missing sites, not non-sites counted as sites.
- **Fix:** use the same filter as `_site_names`: drop phrases that are morphology concepts or whose words are in
  `_NOT_IN_SITE`. Or refuse a tail only when the dropped words are a site of a by-site concept that is not in the
  tail concept's lineage.

### Q4 (low-medium; residue of P4). `_names_site` misses sites, including the CLDN18.2 request's own

`_names_site` returns False for:
- "gastroesophageal junction" and "esophagogastric junction" (NCIt names these only as "<histology> of the <site>",
  which `_of_sites` already reads);
- "extrahepatic", "intrahepatic" and "biliary";
- "ampullary", "salivary", "upper tract", "acral", "mucosal" and "extranodal".

| Request | Record name (`[UNK]`) | HEAD | Expected |
|---|---|---|---|
| GAS | "Metastatic or gastroesophageal junction signet ring cell carcinoma" (**E2E** VBC108, `ws_g11`), and the esophagogastric form | NAMES_REQUESTED_SITE (right), but "reads Metastatic Signet Ring Cell Adenocarcinoma": the request's own site is dropped from the borrowed reading | the modifier read with the whole next name, or named as unread |
| ICC | "Metastatic or extrahepatic bile duct carcinoma" | reads "Metastatic Bile Duct Carcinoma", so "extrahepatic" is dropped | as above |

The class is right in both rows; the borrowed concept is not on record. It is disclosed only generically ("knows
only '<site> Neoplasm' sites"). **Fix:** add `site_phrases(code)` of the requested concepts, and `_of_sites`, to the
set `_names_site` checks.

### Q5 (medium-low; P5 residue). The numbered inversion works only when NCIt puts the number first

"<base>, type 1 or 2" is inverted to "type 2 <base>" only. Many NCIt labels put the number after the base ("Spinal
Muscular Atrophy Type 2", "Neurofibromatosis Type 2", "Glycogen Storage Disease Type III", "Multiple Endocrine
Neoplasia Type 2", "Long QT Syndrome 2").

| Request | Record name (`[UNK]`, all three cases) | HEAD | Expected |
|---|---|---|---|
| SMA2 | "Spinal muscular atrophy, type 1 or 2" (**E2E** RC118, `ws_x11`), "Spinal muscular atrophy (type 1 or 2)" | UNREADABLE: "is not a name the NCIt authority can read." | names Spinal Muscular Atrophy Type 2 (requested) |
| NF2 / GSD III / MEN2 | "Neurofibromatosis, type 1 or 2", "Glycogen storage disease, type I or III", "Multiple endocrine neoplasia type 1 or 2" | UNREADABLE | names the requested type |

These rows are the same as r10, so this is not a regression. The no-comma form ("Spinal muscular atrophy type 1 or 2")
is the disclosed limit "read only right after '<word> N'". **Fix:** also try "<base> <word> N" (and "<base> N").

### Q6 (low; P6 residue). Ordinals are numbers to `_numbered`

"Stage III or 1st line gastric cancer" (GAS) gives "'1st line gastric cancer' read as 'Stage 1st line gastric
cancer'". `_number` excludes `[1-4]l` but `_STAGE_TOKEN` also accepts `\d+(st|nd|rd|th)`. The class is unchanged.

### Q7 (low; pre-existing, not reported before). Two NCIt codes with one label are shown with opposite statuses

"ITP or TTP" (request immune thrombocytopenic purpura → Primary Immune Thrombocytopenia) reads "Primary Immune
Thrombocytopenia (not requested); Primary Immune Thrombocytopenia (requested or a subtype); …". The sentence
contradicts itself. The output is the same at r10. **Fix:** show the code beside a label that two readings share.

### Q8 (low; process). The response's list of changed probe rows is incomplete

The response's §3 says the earlier probe rows that changed are the sepsis rows, "Follicular lymphoma, grade 1 or 2, or
MZL", "NSCLC, stage III, or SCLC" and the nested steps. Re-running them also changes:
- `slash` "Gastric adenocarcinoma (Stage III or IV)": READS_AS_REQUESTED → NAMES_REQUESTED_SITE (Q2);
- `a4` "GASTRIC CANCER, STAGE IV, OR NSCLC": AMBIGUOUS_NAME (Gastric Carcinoma, broader) → DIFFERENT_DISEASE (J-b
  below);
- `q7`, `f` and `o7_all` "Gastric adenocarcinoma, stage IV, or NSCLC": "'stage IV' set aside" → "does not read
  'stage IV' with the name before it" (same class);
- `a4` "GASTRIC OR GEJ ADENOCARCINOMA" and "ALL COMERS OR ALL": a gate-shortcut sentence → U1's own (`[PASS]`, so
  never shown).

### Carried, declared (not counted again)

- F6 acronym meanings ("iCCA" → Infantile Convulsions …; "HCC" → Hilar Cholangiocarcinoma; "mds" → Dystonia 11; "GC"
  → Gonorrhea; "NS" → Nuclear Cataract; "CS" → Cortical Cataract).
- The REVIEW2 N8 family.
- "Relapsed or refractory multiple myeloma".
- The D5 residue.
- "GEJ adenocarcinoma" is not an index name.
- J-a.
- "Castration-sensitive or castration-resistant prostate cancer" and "Limited or extensive stage SCLC" are UNREADABLE
  in every case (they no longer depend on case).

## Judgement calls (labelled; not counted as defects)

- **J-b (carried; wider reach in revision 11).** A gastric stage concept in a list beside another disease is
  DIFFERENT_DISEASE, because the stage-sibling rule is not applied to list readings. With P5, the MeSH-order form now
  reaches it too:
  - "GASTRIC CANCER, STAGE IV, OR NSCLC" and "Gastric cancer, stage III, or colorectal cancer, IV" (GAS) were
    AMBIGUOUS_NAME (Gastric Carcinoma, broader) at r10.
  - They are now "reads as Stage IV/III Gastric Cancer AJCC v7; … neither a requested indication nor a subtype of
    one, although it names gastric".

  The sentence is literally true. The stand-alone "Gastric cancer, stage III or IV" is UNDER_REQUESTED_PARENT.
- **J-p (new).** In an all-lower-case cell, "all" is read as the English word. In "children with all or aml",
  "children with all" is carried as a modifier of AML. The cell is DIFFERENT_DISEASE reading AML (childhood-ALL
  request), and the sentence does not say the piece was folded. Lower-case "all" really is ambiguous. Capitals and
  mixed case read the acronym.
- **J-q.** "Diabetes mellitus, or solid tumors, type 2" is now UNREADABLE ("does not read 'type 2' with the name
  before it"). This is the P7 rule applied as stated. The input is contrived.
- **J-r.** Some synonyms that `_alone` now keeps are true ("mole" → Nevus, "preinvasive" → Carcinoma In Situ,
  "stenotic … ureterocele" → Obstructive Ureterocele). Q1 is about the ones that name a different disease, not about
  synonyms in general.

## Science (step 3)

- CLDN18.2: `fin17_ws/screening.json` against `baseline/screening_R1.json`. Disposition, rank, decisions,
  machine_recommendation and transaction_rank are identical for all 62 programs. `transaction` differs on 13 (R1's)
  and `unknown_diagnostics` differs (U1's). Against `fin16_ws`, only IBI343's `unknown_diagnostics` differs.
- A fresh screen of a copy is byte-identical to `fin17_ws`.
- Held-out `xv17f` against `xv10` (and against `xv16f`): zero differing per-program keys and an equal top level in
  c5_heldout, fcrn_v1, fcrn_v2 and synthetic_200. No held-out landscape exercises the revision-11 rules.

## Reading the outputs as a BD analyst

For the CLDN18.2 landscape, the 38 actions are the same as revision 10's apart from IBI343. Each action states:
- what is on record and its class;
- the one cited fact that decides the gate;
- the `assert` field.

IBI343's sentence now shows how "Unresectable or Metastatic Gastric Adenocarcinoma" became two concepts. That is true,
but at about 90 words of steps it is hard to read. SOT102 ("Pancreatic Cancer") is the one reference-IN different
disease, as reported. The memo's only "in scope"/"out of scope" words are in the buyer's own need statement, and no
action has scope or recommendation wording. Carried, still less useful than it could be: the repeated "The gate never
fails on this evidence…" tail, and "'PD-1' not read by the target authority".

Nothing is hidden: every UNKNOWN on a program that is not excluded has its diagnostic, in `fin17_ws`, in the
held-out landscapes and in both of my E2E workspaces.

What an analyst would not see:
- In a CLDN18.2 screen, "Gastric adenocarcinoma, stage III or IV" is "not a name the NCIt authority reads" (Q2).
- In the same screen, "Sensitive or resistant gastric cancer" is shown reading Hypersensitivity (Q1).
- In a DI screen, "Central, nephrogenic or gestational diabetes insipidus" reads Conventional Osteosarcoma and sits
  in the lowest class (Q1).
- In a cold-agglutinin screen, "Cold or warm AIHA" is a different disease reading COPD (Q1).
- In a prostate screen, "Metastatic or neuroendocrine prostate carcinoma" is unread (Q3).
- In an SMA screen, "Spinal muscular atrophy, type 1 or 2" is unreadable (Q5).

## What I could not check

- **Cycle-4 equivalence** (`equivalence.main()`): not re-run. It writes the tracked
  `research/dealscreen_product_program/cycle4/equivalence_result.json`, which another session has already modified in
  the working tree. The implementer reports 4 of 4 byte-identical.
- **Held-out workbooks and memos:** I read only the held-out `screening.json` files. For E2E I read `screening.json`,
  the Diligence and Screening sheets and the markdown memos. I did not read the `.docx`.
- **Reach:** how often vendor cells use "Central/Cold/Sensitive or …" (Q1), a trailing stage pair (Q2), a histology
  word before a borrowed ending (Q3) or postfix-numbered rare diseases (Q5) is my judgement. Q2's 250-label sweep
  measures how general the mechanism is, not how often vendors write it.
- **NCIt facts:** the index keys, labels and site sets were checked through the U1 code against the frozen
  authority, not against NCIt directly.
- **Reference join:** joining `reference_calls.csv` to `fin17_ws` by program name matches 25 of the 30 reference-IN
  programs. The U1-6 statement for the other 5 rests on the unchanged class counts and on REVIEW10's join.
- **Test order:** I could not tell whether the revision-11 tests were written before the code.
- **Rights code (under concurrent review):** not touched. No U1 module has uncommitted changes, so every U1 output
  above is HEAD's.
- **Fixes:** none of Q1 to Q8 was implemented or tested.

## Reproduction

```
cd /home/djmann/projects/bve-b8 && . .venv/bin/activate && export TMPDIR=$HOME/.cache/dealscreen_suite
python -m pytest tests/dealscreen -q -p no:cacheprovider            # 2076 passed, 5 warnings, 174 s
bash /tmp/claude-1000/u1rr11/runall.sh                              # every earlier probe -> /tmp/claude-1000/u1rr11/out/earlier/
P=/tmp/claude-1000/u1rr11/probes
python $P/cmp1011.py /tmp/claude-1000/u1rr10/probes/b1.txt          # (b1-b5) REVIEW10 rows, r10 vs HEAD -> out/r10_b*.out
python $P/cmp1011.py $P/c1.txt; python $P/cmp1011.py $P/c2.txt      # Q1 ordinary-word synonyms
python $P/cmp1011.py $P/c3.txt --cases; python $P/cmp1011.py $P/c4.txt   # Q2, Q5 numbered lists
python $P/cmp1011.py $P/c5.txt; python $P/cmp1011.py $P/c5b.txt     # Q3, Q4 site test
python $P/cmp1011.py $P/c6.txt; python $P/cmp1011.py $P/c7.txt      # Q6, Q7, nested steps, baskets, acronyms
python $P/casecmp.py $P/c[1-5].txt /tmp/claude-1000/u1rr10/probes/b[1-5].txt   # letter-case consistency
python $P/alone_scan.py; python $P/q2sweep.py                       # index scan (Q1), 250-label sweep (Q2)
bash /tmp/claude-1000/u1rr11/buildall.sh                            # E2E ws_g11, ws_x11
python3 /tmp/claude-1000/u1rr/science_diff.py ~/.cache/rights_v1/fin17_ws/screening.json research/dealscreen_unknown_actions_v1/baseline/screening_R1.json
python3 /tmp/claude-1000/u1rr/coverage.py ~/.cache/rights_v1/fin17_ws/screening.json ~/.cache/rights_v1/xv17f/*/screening.json
```

## Summary of defects

| Severity | Count | Ids |
|---|---|---|
| High | 2 | Q1, Q2 |
| Medium | 1 | Q3 |
| Low-medium / medium-low | 2 | Q4, Q5 |
| Low | 3 | Q6, Q7, Q8 |

New in revision 11: Q1, Q2 and Q3. Q4 and Q6 are residues of P4 and P6. Q5 is a P5 residue that was already present at
r10. Q7 was present at r10 but not reported before. Q8 is process.

**Single highest-value next fix:** make an unread piece never cost U1 a name it can read. In `_list_pieces`, when
`out.unread` is not empty, return the pieces even if only one name is left (Q2; it also fixes the carried "L, grade 1
or 2" collapse). In `_alone`, try the record's own coordination ("<piece> <next head>") before keeping a synonym whose
label does not hold the word, and keep that synonym otherwise only for initials or for words NCIt never uses as a
non-head word (Q1). Add tests in lower, mixed and upper case for:
- "<requested label>, stage III or IV";
- "Central, nephrogenic or gestational diabetes insipidus";
- "Cold or warm autoimmune hemolytic anemia";
- "Metastatic or neuroendocrine prostate carcinoma".
