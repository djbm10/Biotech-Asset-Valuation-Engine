# Cycle U1 revision 10: tenth adversarial review

INTERNAL DEVELOPMENT. This review was run by an AI. It is not a human review or an independent validation, and
nothing in it is an approval.

**Reviewed:** HEAD `f1a310d` on `dealscreen-mvp` in `/home/djmann/projects/bve-b8`, read only. It holds U1 revision 10
committed together with R1 revision 16; U1 revision 9 is `28535ea`. Among the U1 modules, `git diff 28535ea f1a310d`
changes only `diagnostics.py` and `indication_relations.py`. `git diff HEAD` shows no uncommitted edit to any U1
module (see "What I could not check" for the other session's files).
**Criteria:** `ACCEPTANCE.md` with its revision notes, `MEASUREMENT.md`, `REVIEW9.md` and `REVIEW9_RESPONSE.md`.

Every number below was recomputed by running code unless it is marked "read, not re-run". Scratch files, probes and
workspaces are in `/tmp/claude-1000/u1rr10/`.

Abbreviations:
- "rev9" means revision 9's two U1 modules loaded beside HEAD from `git show 28535ea:…` (`rev9/`). The probe
  `probes/cmp910.py` prints rev9 and HEAD for each `KEY|name` line.
- `GAS` is the CLDN18.2 request `["gastric adenocarcinoma", "gastroesophageal junction adenocarcinoma"]`. I checked
  every other request through `ir.read_request` to be exactly one NCIt concept. Each is written as its key: `MCRPC`
  is metastatic castration-resistant prostate carcinoma, `CSPC` castration-sensitive prostate carcinoma, `ICC`
  intrahepatic cholangiocarcinoma, `LNEC` lung neuroendocrine carcinoma, `LSCC` lung squamous cell carcinoma, `T2D`
  type 2 diabetes mellitus, `FL2` grade 2 follicular lymphoma, `CGVHD` chronic graft versus host disease, and so on.
- `[UNK]` means the gate's positive reading does not pass, so the diagnostic is shown. `[PASS]` rows were tested at
  unit level only.
- "E2E" means confirmed through `bve-dealscreen import`, `import-rights`, `screen`, `export` and `memo` on a workspace
  built from the `fin16_ws` inputs, with four indication cells edited (and, for `mix10`, the buyer's indications).
  The scripts are `build.sh` and `buildall.sh`.

## Verdict in one paragraph

Revision 10 changes no science, and coverage is still complete. The rows REVIEW9 gave for N1 to N9 now give the
expected output in lower and mixed case. **U1-7 is still not met**, because two of the new rules cause new false
statements and one fix does not reach cells written in capitals:

1. **P1 (high, new in revision 10).** In a cell written in capitals, the N6 shortcut throws away the parts of the
   record U1 did not read. The record is then called a different disease, judged on half of it. In the CLDN18.2
   request, "GASTRIC/GEJ ADENOCARCINOMA OR NSCLC" is now DIFFERENT_DISEASE. The memo lists it under "a disease
   neither requested nor a subtype of one" (E2E). Revision 9 called it NAMES_REQUESTED_SITE.
2. **P2 (high, new in revision 10).** The N2 rule (`_alone`) rejects acronyms written in mixed case or lower case,
   and every one-word synonym. The authority reads "mCRPC", "iCCA", "ccRCC" and "pRCC", yet "mCRPC or mHSPC" for an
   mCRPC request is UNREADABLE: "is not a name the NCIt authority can read" (E2E). In the index, 1,631 of 2,578
   one-word keys are now rejected in a list, and 705 of those are acronyms of their own label.
3. **P3 (high, carried: N2 not fixed in capitals).** "DIFFUSE OR FOLLICULAR LYMPHOMA" still reads "Gastric Diffuse
   Adenocarcinoma (requested or a subtype)" for the CLDN18.2 request (E2E).
4. **Lower-severity defects (P4 to P9).**
   - A borrowed ending drops the site: "Metastatic or pancreatic neuroendocrine carcinoma" shares subtypes with a
     lung-NEC request.
   - Inverted numbered lists are unread: "Diabetes mellitus, type 1 or 2".
   - `_numbered` attaches to a line token.
   - The inversion base is carried across a basket.
   - The steps of a nested split are hidden, and `after/` is one sentence stale.

## Verdict per criterion

| AC | Verdict | Evidence |
|---|---|---|
| U1-1 coverage | **Met** | `coverage.py`: `fin16_ws` 38/38. `xv16f`: c5_heldout 28/28, fcrn_v1 28/28, fcrn_v2 28/28, synthetic_200 20/20, so 104/104. My E2E workspaces `ws_caps10` and `ws_mix10` carry a diagnostic on every edited UNKNOWN. Nothing is missing and nothing is extra. |
| U1-2 authorities only | **Met (letter)** | Of the 118 `+` lines in revision 10, disease and target words appear only in comments and docstrings. I grepped for gastr, cldn, gej, her2, pd-l1, klx, vorp, crohn, colitis, leuk, gvhd, diabet, anemia, lymphom, myelo, nsclc, ihc, china, asia, sclerosis, sepsis. The new tables (`_NUMBERED`, `_POPULATION_LABEL`, `_STATE_SYMBOLS` additions, `_NOT_TARGET_TOKEN`) are generic English, NCIt's own population label words, or token shapes. Note: P2 and P3 come from a case heuristic placed in front of the authority, not from the authority. |
| U1-3 no change to science | **Met** | `science_diff.py` on `fin16_ws` against `baseline/screening_R1.json`: 13 of 62 programs differ, all in `transaction` only, which is R1's field. Disposition, rank, decisions, machine_recommendation and transaction_rank are unchanged, and the top level is equal. `txdiff.py`: 11 of the 13 are identical once `external_id` and `related_deal_id` are removed; the other two are Zolbetuximab and IMAB362, as in REVIEW9. A fresh screen of a copy is byte-identical to `fin16_ws`. A copy screened with `screening.diagnose` stubbed out (`nou1.py`) differs only in `unknown_diagnostics`. `fin16_ws` against `fin15_ws`: only IBI343's `unknown_diagnostics` differs, which matches the response. Held-out `xv16f` against `xv10` and against `xv15f`: 0 differing per-program keys and an equal top level in all four landscapes. |
| U1-4 held-back tests | **Met as written; not enough in substance** | `python -m pytest tests/dealscreen -q -p no:cacheprovider`: **1,956 passed**, 5 warnings, 370 s. The revision-10 block tests exactly REVIEW9's rows. There is no capitals form of any N2 row (P3), no capitals list read only in part (P1), no acronym in mixed case inside a list (P2), and no inverted numbered list (P5). |
| U1-5 surfaces | **Met, with one stale artifact** | A fresh memo from a copy of `fin16_ws` is identical to `after/memo_u1.md`. A fresh workbook matches `after/u1_cldn18.xlsx` cell for cell on all 9 sheets, apart from the README timestamp and **one Diligence cell (row 70, IBI343)**. `after/screening_u1.json` differs from `fin16_ws` in the same sentence. `after/` was last committed in `624b2f0`, so it no longer shows HEAD's output (P9). In the E2E workspaces the Diligence "Next action", the Screening class and the memo's single-gate list carry the HEAD sentences (P1 to P3 confirmed on all three surfaces). |
| U1-6 per program vs reference | **Met as measured on CLDN18.2; the harm is reachable in the CLDN18.2 request's own therapy area through capitals (P1, P3)** | Of the 30 reference-IN programs, 14 are ELIGIBLE, 15 UNRESOLVED and 1 EXCLUDED. The only DIFFERENT_DISEASE among them is SOT102 ("Pancreatic Cancer"), as before. GAS sweep (`sweep9.py`, 99,875 generated names): 3,615 DIFFERENT_DISEASE results (rev9: 493). By distinct name, 129 are new, and **all 129** are the population-child shape: "Juvenile / Children with / Pediatric gastric carcinoma" now reads Childhood Gastric Carcinoma (judgement call J-m below). 54 BROADER_THAN_REQUESTED names left that class for the same reason. The sweep does not cover P1's shape (a gastric piece the U1 reader cannot read, in capitals, beside another disease). |
| U1-7 adversarial review | **Not met** | P1, P2 and P3 (high) are confirmed end to end. I found no hidden UNKNOWN, no stray diagnostic, no scope or recommendation wording and no change to science. |

## Status of REVIEW9's findings (N1 to N9)

How I checked:
- Inputs: every earlier probe re-run unchanged (`runall.sh`, outputs in `out/`) and diffed against REVIEW9's
  (`/tmp/claude-1000/u1rr9/out/`). REVIEW9's `a1`–`a7` were run through `cmp910.py` (rev9 against HEAD).
- Identical to REVIEW9: p1–p3, p5–p10, `r3_p_ind`, `r3_p_sib2`, `r3_p_tgt`, `p_sib`, `p_tgt4`, `restate`, `sites6`,
  `sib6`, `misc6`, `bk6`, `i6`, `i6b`, `i6c`, `orq`, `prop`, `prop2`, `slash`, `t5`–`t8`, `ta5`. p4 has the same lines
  in a different order. So the following are unchanged at HEAD for every earlier input:
  - the stage-only sibling rule
  - the restatement rule
  - the neoplasm-node site rule and the lineage list
  - role words
  - baskets and acronyms
  - negation and parenthesis handling in target text
  - "/" and "and/or"
  - placeholders
- Changed outputs:
  - `caps`, `b5`, `p_ind4`, `h8`: N6 and N7.
  - `f`, `h7`, `q7`, `o7_all`, `a2`, `a3`, `a5`, `a6`: N1 and N3 to N5.
  - `bas`, `f`, `q7`: N9 wording.
  - `t9`: N8.
  - Plus two regressions, both P2: `h7` "mCRPC or mHSPC" and `o7_all` "HCC or iCCA".
- The implementer's `u1r10/probe.py` output (`out/u1r10_probe.out`) matches the response's §1 and §2 tables.

| Id | Status | Input → output at HEAD |
|---|---|---|
| N1 leading modifier folded | **Fixed for the listed rows; new defect P4** | RMS: "Relapsing or progressive multiple sclerosis", "Relapsing and/or …", "RELAPSING OR PROGRESSIVE …" and "Relapsing or Progressive Multiple Sclerosis" are AMBIGUOUS_NAME naming Relapsing MS (requested). `a6`: "Locally advanced / Metastatic / Unresectable or … gastric adenocarcinoma" (MGAS), "Refractory or relapsed AML" (RAML) and "Recurrent or metastatic HNSCC" (RHN) now name the requested concept. "Relapsed or refractory multiple myeloma" still folds to BROADER (disclosed). New: the borrowed ending can drop a site (P4). |
| N2 one-word piece read alone | **Fixed in lower and mixed case; not fixed in capitals (P3); new cost far wider than disclosed (P2)** | "Diffuse or follicular lymphoma", "Intestinal or extraintestinal Behçet's disease", "Mixed or pure germ cell tumor", "Diffuse, follicular, or mantle cell lymphoma" (GAS) and "Symptomatic or asymptomatic multiple myeloma" (COVID) no longer read a gastric or COVID concept, and "Diffuse and/or …" is fixed too. The same names in capitals still do (P3). The response discloses the cost as "Sepsis", "infection" and "epilepsy". It also covers "Hives" (Urticaria), acronyms in mixed case ("mCRPC", "nmCRPC", "iCCA", "eCCA", "ccRCC", "pRCC") and every acronym in a lower-case cell ("nsclc or sclc"), which is P2. |
| N3 number loses its word | **Fixed for a leading pair; not for an inverted or parenthesised pair (P5); attaches to line tokens (P7)** | "Type 1 or 2 diabetes mellitus", "Type I or II diabetes mellitus", "TYPE 1 OR 2 DIABETES MELLITUS" and "Type 1 or 2 diabetes mellitus or obesity" name T2D (requested). "Grade 1 or 2" and "Grade 2 or 3a follicular lymphoma" name the grade. "Stage III or IV gastric cancer" and "Stage III or IV NSCLC" read both stages (J-k closed). **Not fixed:** "Diabetes mellitus, type 1 or 2", "Diabetes (type 1 or 2)", "Follicular lymphoma, grade 1 or 2" and "Follicular lymphoma (grade 1 or 2)" are UNREADABLE. |
| N4 population read as parent | **Fixed** | "Children with ALL or AML" and "Pediatric patients with ALL or AML" (ALLA) read Childhood ALL and are DIFFERENT_DISEASE. "Adults with ALL or AML" (childhood ALL request) reads Adult ALL. "Pediatric Hodgkin lymphoma or NHL" reads Childhood HL. "Adult B-ALL or AML" now reads Adult B-ALL (requested). Capitals ("CHILDREN WITH ALL OR AML") are the same. Without a population child the parent stays and the step is shown ("Children with arthritis" reads Arthritis). Side effect: J-m. |
| N5 inverted chain | **Fixed; residue P8** | "GVHD, acute or chronic (, or AML)", "Graft versus host disease, acute or chronic", "GVHD, chronic or acute", "Diabetes (mellitus), type 1 or type 2", "Leukemia, acute or chronic (, or lymphoma)", "Hepatitis B, acute or chronic, or hepatitis C" and "GVHD, ACUTE OR CHRONIC" name both subtypes. A later name resets the base correctly ("GVHD, acute, or AML, chronic" says it "does not read 'chronic' with the name before it"). A basket does not reset it (P8). |
| N6 capitals said "the gate does not apply" | **Fixed for single-name cells; new defect P1** | "ADVANCED NSCLC", "RELAPSED AML", "RELAPSED CLL", "ALL (ADULT)" and "CHRONIC OR ACCELERATED PHASE CML" now carry the gate's own steps. The shortcut also fires on lists that U1 reads only in part, where it hides the unread part (P1). |
| N7 quotes not as written | **Fixed** | "'CHILD-PUGH A' or 'B'", "'TYPE 2 DIABETES MELLITUS'", "'ALL COMERS'", "'LOCALLY ADVANCED' removed", "'RELAPSED' removed", "'GEJ CANCER'". |
| N8 grade or line token as a target | **Fixed** | "CLDN18.2 negative in G1/G2 tumours", "CLDN18.2 NEGATIVE IN 2L", "… in 3L" and "… IN 2L OR 3L" say "names no other target the authority reads". Controls still name a target: "… positive for HER2", "… NEGATIVE WITH CD47", "… NEGATIVE, IL2", "… factor IX", "… NEGATIVE VS HER2". The REVIEW2 N8 family is carried: comma pieces such as "Q3W" and "stage IIIA" are "names other targets only". |
| N9 set-apart modifier called a name | **Fixed** | "does not read 'severe' / 'moderate to severe' / 'high grade' / 'adult' with the name before it". Wording nit, not counted: the basket phrase "any other tumour type" also gets "with the name before it". |
| J-a (outside U1) | **Carried** | The gate's coordination reading is unchanged. P1 shows that it now also supplies the class for capitals cells that U1 reads only in part. |

## Defects in revision 10, ranked by how much they could mislead

### P1 (high; new in revision 10). The capitals shortcut keeps the screen's lossy coordination reading and drops the parts U1 could not read, so a record that names the request is called a different disease

How it happens: `_raw_lookup` (N6) softens a cell in capitals and reads it. When the codes it reads equal the codes the
screen reads (`set(codes) == set(found.codes)`), it returns the screen's reading in place of U1's. The comparison
ignores `found.unread` and `found.baskets`. Take a list in which U1 reads one half and cannot read the other: the
screen's coordination reading of the same cell reads the same one half. The shortcut fires and the unread half
disappears. The class is then decided on half the record, which is exactly the outcome the REVIEW7 and REVIEW8 guard
was meant to stop. In lower case the same cell stays UNREADABLE or NAMES_REQUESTED_SITE and says "does not read …".

| Request | Record name (all `[UNK]`) | rev9 | HEAD | Expected |
|---|---|---|---|---|
| GAS | "GASTRIC/GEJ ADENOCARCINOMA OR NSCLC" (**E2E** Q-1802, `ws_caps10`; memo: "a disease neither requested nor a subtype of one") | NAMES_REQUESTED_SITE: "… does not read 'GASTRIC/GEJ adenocarcinoma'" | DIFFERENT_DISEASE: "reads as Lung Non-Small Cell Carcinoma (NCIt) once coordination expanded, neither a requested indication nor a subtype of one, although it names gastric and GEJ" | rev9's class and sentence, in capitals |
| GAS | "MGC OR NSCLC" (**E2E** VBC108), "GEJ OR NSCLC", "NSCLC OR PAIN", "SEVERE NSCLC OR PAIN" | UNREADABLE / NAMES_REQUESTED_SITE, naming the unread piece | DIFFERENT_DISEASE, the unread piece not named | as rev9 |
| CSPC (mix10: MCRPC+CSPC+ICC+T2D) | "CASTRATION-SENSITIVE OR CASTRATION-RESISTANT PROSTATE CANCER" (**E2E** Q-1802, `ws_mix10`) | UNREADABLE: "does not read 'CASTRATION-SENSITIVE'" | DIFFERENT_DISEASE (CSPC request); BROADER_THAN_REQUESTED (mix10): "reads as Castration-Resistant Prostate Carcinoma …", with no mention of the castration-sensitive half, which is a requested indication | at least rev9's; ideally AMBIGUOUS_NAME naming CSPC (REVIEW9 N2 row, still open in lower case) |
| CGVHD | "CGVHD OR BRONCHIOLITIS OBLITERANS" | UNREADABLE: "does not read 'CGVHD'" | DIFFERENT_DISEASE: reads Bronchiolitis Obliterans | not DIFFERENT_DISEASE |
| UC | "CHILDHOOD UC OR CROHN'S DISEASE" | UNREADABLE | DIFFERENT_DISEASE: reads Crohn Disease | not DIFFERENT_DISEASE |
| limited-stage SCLC | "LIMITED OR EXTENSIVE STAGE SCLC" | UNREADABLE | DIFFERENT_DISEASE: reads Extensive Stage SCLC | not DIFFERENT_DISEASE |
| childhood ALL | "ADOLESCENTS WITH ALL OR AML", "YOUNG ADULTS WITH ALL OR AML", "ADULTS AND CHILDREN WITH ALL OR AML" | UNREADABLE | DIFFERENT_DISEASE: reads AML only | not DIFFERENT_DISEASE |
| ATLL | "ADULT T-CELL LEUKAEMIA OR CTCL" | UNREADABLE | DIFFERENT_DISEASE: reads CTCL only | not DIFFERENT_DISEASE |
| MCRPC | "NON-METASTATIC OR METASTATIC CASTRATION-RESISTANT PROSTATE CANCER" | NAMES_REQUESTED_SITE | BROADER_THAN_REQUESTED, "'metastatic' removed and coordination expanded" | as rev9 |

- **Measured:** `probes/capscmp.py` runs each name of my probe sets, REVIEW9's a1–a7 and REVIEW8's probe sets in its
  own case and in capitals. Of 34 rows that differ between the two, 13 are this shape (lower case "does not read …",
  capitals DIFFERENT_DISEASE or BROADER). The other rows are P2 and P3.
- **Why it misleads:** it is the U1-6 harm in the buyer's own therapy area. A gastric or GEJ program, or a
  castration-sensitive program for a CSPC buyer, is filed among the different diseases, and the sentence says it
  reads as the other disease alone. The response's §2 N6 describes the shortcut only for cells the gate reads "the
  same way"; for these cells the gate reads a different, smaller thing.
- **Fix:** take the shortcut only when the softened reading has no `unread` and no `baskets` (compare the whole
  Lookup, not the codes). Otherwise keep U1's reading with the capitals step, as in revision 9.

### P2 (high; new in revision 10). `_alone` rejects acronyms written in mixed or lower case, and every one-word synonym, although the authority reads them

How it happens: `_alone` keeps the index reading of a one-word list piece only in three cases:
- the word is the label's last word;
- the word is the first word of a two-word label;
- every word of the label is in the record.

It passes a piece through untouched only when it is all capitals (`piece.isupper()`). A mixed-case acronym is
therefore judged like an adjective: "mCRPC" → Metastatic Castration-Resistant Prostate Carcinoma fails all three tests
and is dropped. A one-word synonym (hives → Urticaria, sepsis → Septicemia) is dropped the same way.

`out/alone_scan.txt` scans every one-word alphabetic index key that is not a modifier word, as a lower-case list
piece:
- 1,631 of 2,578 keys are fully rejected and 33 partly.
- 705 of the 1,631 look like acronyms of their own label (initials match), for example `aml`, `alcl`, `als`, `apl`,
  `ards`, `afib`.
- Many of the rest are real synonyms: "amoebiasis" (the British spelling of Amebiasis), "mucormycosis",
  "scurvy", "rectitis", "amyloid".

When a list is written in mixed case, this matters for the acronyms written that way.

| Request | Record name (all `[UNK]`) | rev9 | HEAD | Expected |
|---|---|---|---|---|
| MCRPC | "mCRPC or mHSPC" (**E2E** SOT102, `ws_mix10`; memo: "no name the NCIt authority reads as a whole") | AMBIGUOUS_NAME: reads Metastatic CRPC (requested), "does not read 'mHSPC'" | UNREADABLE: "'mCRPC or mHSPC' is not a name the NCIt authority can read." | rev9's |
| MCRPC | "mCRPC or nmCRPC" | AMBIGUOUS_NAME naming both | UNREADABLE | rev9's |
| ICC | "HCC or iCCA" (**E2E** VBC108, `ws_mix10`), "iCCA or HCC", "iCCA or eCCA" | AMBIGUOUS_NAME: Intrahepatic Cholangiocarcinoma (requested) | UNREADABLE: "does not read 'iCCA'" | rev9's |
| ccRCC | "ccRCC or pRCC" | AMBIGUOUS_NAME: ccRCC (requested) | UNREADABLE | rev9's |
| NSCLC | "nsclc or sclc" | AMBIGUOUS_NAME | UNREADABLE | rev9's |
| urticaria | "Hives or angioedema" | AMBIGUOUS_NAME: Urticaria (requested) | UNREADABLE | rev9's |
| sepsis | "Sepsis or septic shock" | AMBIGUOUS_NAME: Septicemia (requested) | UNREADABLE (disclosed shape) | rev9's |

- **Why it misleads:** the sentence "is not a name the NCIt authority can read" / "does not read 'iCCA'" is false.
  The authority reads the word, and in each row it reads it as the requested concept. A program naming the request
  drops from AMBIGUOUS_NAME to UNREADABLE, the lowest class. "mCRPC", "nmCRPC", "iCCA" and "ccRCC" are standard
  oncology spellings; how often they occur in a vendor "or" cell is my judgement, not measured.
- **The response understates it.** §1 says "An acronym in mixed case ("ALL") is kept", but "ALL" is in capitals. §5
  names only synonyms ("Sepsis"), not acronyms. The same names in capitals are read (see P3 for why), so the
  behaviour depends on letter case.
- **Fix:** keep a reading when the piece is an acronym of the label. The module already has `_initials`/`_abbreviates`.
  Also keep a token with an internal capital ("mCRPC") as an acronym, and keep a reading whose label holds no word of
  the piece (a synonym: "hives" → Urticaria). Refuse only when the word appears inside the label as a non-head word
  ("diffuse" in Gastric Diffuse Adenocarcinoma), which is the N2 shape.

### P3 (high; carried: N2 is not fixed for cells in capitals)

How it happens: `_raw_lookup` softens a capitals cell ("DIFFUSE or FOLLICULAR LYMPHOMA", where only "OR" is a modifier
word) and reads the softened text. The softened text is no longer all capitals, so `_conjuncts` runs with
`caps=False`. In `_alone`, "DIFFUSE".isupper() is then taken for an acronym and every index reading is kept.

| Request | Record name (all `[UNK]`) | HEAD (rev9 identical) | Expected |
|---|---|---|---|
| GAS | "DIFFUSE OR FOLLICULAR LYMPHOMA" (**E2E** SOT102, `ws_caps10`; memo: "a name with several NCIt readings") | AMBIGUOUS_NAME: "Gastric Diffuse Adenocarcinoma (requested or a subtype); Follicular Lymphoma (not requested)" | no gastric reading (as in lower case) |
| GAS | "INTESTINAL OR EXTRAINTESTINAL BEHCET'S DISEASE", "INTESTINAL OR HEPATIC SCHISTOSOMIASIS", "MIXED OR PURE GERM CELL TUMOR", "DIFFUSE, FOLLICULAR, OR MANTLE CELL LYMPHOMA", "DIFFUSE OR FOLLICULAR LYMPHOMA OR PAIN" | AMBIGUOUS_NAME naming Gastric Intestinal-Type / Mixed / Diffuse Adenocarcinoma (requested) | no gastric reading |
| DLBCL NOS | "DIFFUSE OR FOLLICULAR LYMPHOMA" | DIFFERENT_DISEASE: "reads as Gastric Diffuse Adenocarcinoma; Follicular Lymphoma" | no gastric reading |
| COVID-19 | "SYMPTOMATIC OR ASYMPTOMATIC MULTIPLE MYELOMA", "ASYMPTOMATIC OR SYMPTOMATIC HYPERURICEMIA" | AMBIGUOUS_NAME naming a COVID-19 concept (requested) | no COVID-19 reading |

- **Why it misleads:** the same as REVIEW9's N2, on any vendor export written in capitals. REVIEW8's D4 treats such
  exports as in scope, and the response claims N2 fixed. The test block tests only the lower-case forms.
- **Fix:** pass the original cell's `caps` into `_alone` (or test `_acronym(piece)` whatever the case). Add the
  capitals form of every N2 row to the tests.

### P4 (medium-low; new in revision 10). A borrowed ending can drop a site, so the record is read as a site-less concept that it does not name

How it happens: `_heads` lets a leading modifier borrow the next name's longest ending of two words or more that the
index reads, whatever words that ending drops. When the dropped words are the site, the borrowed concept has no
site.

`out/tail_sweep.txt` crosses 14 modifiers with every NCIt label of three words or more. It finds 9,441
(modifier, label) pairs where a tail is borrowed and named. Dropped words include sites: pharyngeal, pancreatic,
gastroesophageal junction, head and neck, laryngeal, breast, ureter, endometrial, vaginal, colon, and others.

| Request | Record name (all `[UNK]`) | HEAD | Expected |
|---|---|---|---|
| LNEC | "Metastatic or pancreatic neuroendocrine carcinoma" | AMBIGUOUS_NAME: "'Metastatic' read as 'Metastatic neuroendocrine carcinoma' …: Metastatic Neuroendocrine Carcinoma (**shares subtypes with a requested concept**); Pancreatic NEC (not requested)" | DIFFERENT_DISEASE, or the modifier read with the whole next name |
| LSCC | "Recurrent or pharyngeal squamous cell carcinoma" | AMBIGUOUS_NAME: Recurrent Squamous Cell Carcinoma (shares subtypes) | as above |
| GAS | "Metastatic or pharyngeal squamous cell carcinoma" (**E2E** RC118, `ws_caps10`) | DIFFERENT_DISEASE naming "Metastatic Squamous Cell Carcinoma; Pharyngeal SCC" | class right; the first concept is not on record |

- **Why it misleads:** a pancreatic-only record is shown to a lung buyer as sharing subtypes with the request, in the
  AMBIGUOUS_NAME group above the different diseases. The docstring says a one-word ending "would drop the site"; a
  multi-word ending drops it too.
- **Reach:** "M or <site> <histology>" is less common than "M or M' <site> <histology>", which takes the head path
  and is right. That is judgement, not measured.
- **Fix:** refuse a tail when the dropped words name a site (`site_phrases` / `_neoplasm_sites`). Alternatively,
  borrow only when the dropped words are themselves modifier-like.

### P5 (medium-low; residue of N3/N5). A numbered alternative in an inverted or parenthesised list is unread

`_numbered` applies only to a name piece whose previous raw piece is exactly "<word> N". In an inverted list the
second number ("2") is a modifier piece, so it is "set aside as a modifier".

| Request | Record name (all `[UNK]`) | HEAD (= rev9) | Expected |
|---|---|---|---|
| T2D | "Diabetes mellitus, type 1 or 2" (**E2E** RC118, `ws_mix10`: "is not a name the NCIt authority can read"), "Diabetes (type 1 or 2)" | UNREADABLE | AMBIGUOUS_NAME naming T2D, as "Diabetes mellitus, type 1 or type 2" already does |
| FL2 | "Follicular lymphoma, grade 1 or 2", "Follicular lymphoma (grade 1 or 2)" | UNREADABLE | names Grade 2 FL |
| stage IV gastric cancer | "Gastric cancer, stage III or IV", "Gastric cancer (stage III or IV)" | AMBIGUOUS_NAME_ALL_BROADER, "'stage III' set aside … 'IV' set aside" | names the stage concepts, as the leading form does |

- **Fix:** when a later inverted piece is a bare number and the piece before it was "<word> N", invert "<word> <number>"
  with the base name.

### P6 (low; new in revision 10). `_numbered` attaches to a line token, and a carried prefix is quoted as if written

- "Stage III or 2L gastric cancer" (GAS) gives "'2L gastric cancer' read as 'Stage 2L gastric cancer' and 'Stage 2L
  gastric cancer' read as 'gastric cancer'". `_STAGE_TOKEN` accepts "2L". The class (UNDER_REQUESTED_PARENT) is
  unaffected.
- "Grade 1 or 2 obesity or type 1 diabetes" (T1D) gives "does not read 'Grade 1 or Grade 2 obesity'". The record
  says "Grade 1 or 2 obesity".
- **Fix:** exclude line tokens (`[1-4]l`) from `_numbered`. Quote the record's own words for an unread carried piece.

### P7 (low; new in revision 10). The inversion base is carried across a basket

"GVHD, acute, or other solid tumors, chronic" (CGVHD) reads "'GVHD, chronic' read as 'chronic GVHD'" and names Chronic
GVHD (requested), although in the record "chronic" follows "other solid tumors". A basket piece `continue`s before
`base` is reset. The input is contrived; a name piece resets the base correctly.

### P8 (low; D8 residue). The steps of a nested split are hidden

IBI343 ("Unresectable or Metastatic Gastric or Gastroesophageal Junction Adenocarcinoma", the one CLDN18.2 sentence
revision 10 changed) gives: "reads as Unresectable Gastric Adenocarcinoma; Metastatic Gastric Adenocarcinoma;
Gastroesophageal Junction Adenocarcinoma … once its 'or' list split into **2 names** and 'Unresectable or Metastatic
Gastric' read as 'Unresectable or Metastatic Gastric Adenocarcinoma'". It names three concepts and never shows how
"Unresectable or Metastatic Gastric Adenocarcinoma" became two. `_conjuncts` keeps only `_lookup(piece).codes`, so
the inner `_list_pieces` steps are dropped. The class is correct.

### P9 (low; process). `after/` is not HEAD's output

`after/screening_u1.json`, `after/u1_cldn18.xlsx` (Diligence row 70) and the measurement in `after/` predate revision
10 by IBI343's sentence. The memo is unaffected.

### Carried, declared (not counted again)

- F6 acronym meanings ("HCC" → Hilar Cholangiocarcinoma; "MDS" → Dystonia 11; "GC" → Gonorrhea).
- The REVIEW2 N8 family ("Q3W", "stage IIIA" as "names other targets only").
- "Relapsed or refractory multiple myeloma" (folded, disclosed).
- The D5 residue "Adult or pediatric ulcerative colitis or Crohn's disease".
- REVIEW9's N2-table rows that revision 10 does not address in lower case: "Castration-sensitive or
  castration-resistant prostate cancer", "Limited or extensive stage SCLC" and "Squamous or non-squamous NSCLC" are
  UNREADABLE.
- J-a.

## Judgement calls (labelled; not counted as defects)

- **J-m (new): population child under a broader parent.** "Children with gastric carcinoma or …", "Juvenile gastric
  carcinoma …" and "Pediatric gastric carcinoma …" (GAS) now read Childhood Gastric Carcinoma and are
  DIFFERENT_DISEASE. There are 129 such names in the GAS sweep; rev9 said Gastric Carcinoma (BROADER). NCIt does not
  file Childhood Gastric Carcinoma under gastric adenocarcinoma, so "neither a requested indication nor a subtype of
  one" is literally true. But it sits under the request's own parent, and the stage-only sibling rule keeps
  UNDER_REQUESTED_PARENT from it. An analyst would read "different disease" for a pediatric gastric cancer. Mapping
  "juvenile" to "childhood" (`_POPULATION_LABEL`) is also a choice the authority does not make.
- **J-n: the class for a pediatric record against an adult request.** "Children with ALL or AML" (adult-ALL request)
  is DIFFERENT_DISEASE, consistent with "Childhood ALL or AML". This is the response's stated intent, and I agree it
  is what NCIt supports.
- **J-o: `_alone` keeps "Lupus" → Lupus Erythematosus** by the two-word-label rule (a broader reading of SLE). That
  is reasonable.

## Science (step 3)

- CLDN18.2: `fin16_ws/screening.json` against `baseline/screening_R1.json`. Disposition, rank, decisions,
  machine_recommendation and transaction_rank are identical for all 62 programs. `transaction` differs on 13 (R1's)
  and `unknown_diagnostics` differs (U1's).
- A fresh screen of a copy is byte-identical to `fin16_ws`. With U1 stubbed out, only `unknown_diagnostics` differs.
- Held-out `xv16f` against `xv10`: zero differing per-program keys and an equal top level in c5_heldout, fcrn_v1,
  fcrn_v2 and synthetic_200. The same holds against `xv15f`; even `unknown_diagnostics` is unchanged, so no held-out
  landscape exercises the revision-10 rules.

## Reading the outputs as a BD analyst

For the CLDN18.2 landscape, REVIEW9's reading of the 38 actions holds. Each action states:
- what is on record and its class;
- the one cited fact that decides the gate;
- the `assert` field.

The one changed sentence (IBI343) is true and more specific: it names unresectable and metastatic gastric
adenocarcinoma. Its steps miss the inner split (P8). SOT102 ("Pancreatic Cancer") is the one reference-IN different
disease, as reported. The memo's only "in scope"/"out of scope" words are in the buyer's own need statement, and no
action has scope or recommendation wording. Still less useful than it could be (carried): the repeated "The gate
never fails on this evidence…" tail, and "'PD-1' not read by the target authority".

Nothing is hidden: every UNKNOWN on a program that is not excluded has its diagnostic, in `fin16_ws`, in the
held-out landscapes and in both of my E2E workspaces.

What an analyst would not see:
- In a CLDN18.2 screen of a capitals export, a "GASTRIC/GEJ ADENOCARCINOMA OR NSCLC" program sits among "a disease
  neither requested nor a subtype of one", and its sentence says it reads as NSCLC (P1).
- In the same export, a "DIFFUSE OR FOLLICULAR LYMPHOMA" program is still shown as reading gastric diffuse
  adenocarcinoma, requested (P3).
- In a prostate or biliary screen, "mCRPC or mHSPC" and "HCC or iCCA" are "not a name the NCIt authority can read",
  in the lowest class (P2).
- In a lung-NEC screen, a pancreatic-NEC record "shares subtypes" with the request (P4).
- In a diabetes screen, MeSH-order "Diabetes mellitus, type 1 or 2" is unreadable (P5).

## What I could not check

- **Cycle-4 equivalence** (`equivalence.main()`): not re-run. The implementer reports 4 of 4 byte-identical.
  `research/dealscreen_product_program/cycle4/equivalence_result.json` is modified in the working tree (another
  session's).
- **Held-out workbooks and memos:** I read only the held-out landscapes' `screening.json` (unchanged since `xv10`).
  For my E2E workspaces I read `screening.json`, the Diligence sheets and the markdown memos; the `.docx` memos were
  generated but not read.
- **Reach:** how often vendor cells are written in capitals with an "or" list (P1, P3), use mixed-case acronyms in a
  list (P2), use "M or <site> <histology>" (P4), or use MeSH-order numbered lists (P5) is my judgement, not measured.
- **NCIt facts:** my claims (index keys "mcrpc", "icca", "ccrcc", "hives"; labels; Childhood Gastric Carcinoma's
  parents) were checked through the U1 code against the frozen authority, not against NCIt directly.
- **Test order:** whether the revision-10 tests were written before the code.
- **Rights code (under concurrent review):** not touched. `git status` shows only the start-of-session files and
  another session's untracked `research/dealscreen_rights_v1/REREVIEW15.md`. No U1 module has uncommitted changes,
  so every U1 output above is HEAD's.
- **Fixes:** none of P1 to P9 was implemented or tested.

## Reproduction

```
cd /home/djmann/projects/bve-b8 && . .venv/bin/activate && export TMPDIR=$HOME/.cache/dealscreen_suite
python -m pytest tests/dealscreen -q -p no:cacheprovider            # 1956 passed, 5 warnings, 370 s
bash /tmp/claude-1000/u1rr10/runall.sh                              # every earlier probe -> /tmp/claude-1000/u1rr10/out/
P=/tmp/claude-1000/u1rr10/probes
python $P/cmp910.py $P/b1.txt     # shared modifiers, numbered/inverted lists (P5, P6), one-word diseases, population, base carry (P7), tails
python $P/cmp910.py $P/b2.txt     # acronyms in mixed case (P2)
python $P/cmp910.py $P/b3.txt     # capitals: shortcut (P1) and N2 in capitals (P3)
python $P/cmp910.py $P/b4.txt --head   # borrowed ending drops a site (P4)
python $P/cmp910.py $P/b5.txt     # and/or, slash, placeholders, fictional names, capitals numbered/inverted
python $P/capscmp.py $P/b1.txt $P/b2.txt /tmp/claude-1000/u1rr9/probes/a*.txt /tmp/claude-1000/u1rr8/probes/*.txt   # each name vs capitals
# _alone index scan: out/alone_scan.txt; borrowed-tail sweep: out/tail_sweep.txt (inline scripts, see transcript of this review)
bash /tmp/claude-1000/u1rr10/buildall.sh                            # E2E ws_caps10, ws_mix10
python3 /tmp/claude-1000/u1rr/science_diff.py ~/.cache/rights_v1/fin16_ws/screening.json research/dealscreen_unknown_actions_v1/baseline/screening_R1.json
python3 /tmp/claude-1000/u1rr7/probes/txdiff.py <same two files>
python /tmp/claude-1000/u1rr6b/probes/nou1.py <copy of fin16_ws>    # screen with U1 stubbed out
python3 /tmp/claude-1000/u1rr/coverage.py <screening.json ...>
```

E2E workspaces (copies; originals not modified):
- `ws_copy`: a fresh CLDN18.2 screen (`ws_copy_out.xlsx`, `ws_copy_memo.md`). `ws_nou1`: the same with U1 stubbed
  out.
- `ws_caps10` (`e2e_caps10/`): GAS request, with these edited cells:
  - SOT102 "DIFFUSE OR FOLLICULAR LYMPHOMA"
  - Q-1802 "GASTRIC/GEJ ADENOCARCINOMA OR NSCLC"
  - VBC108 "MGC OR NSCLC"
  - RC118 "Metastatic or pharyngeal squamous cell carcinoma"
- `ws_mix10` (`e2e_mix10/`): request [metastatic castration-resistant prostate carcinoma, castration-sensitive
  prostate carcinoma, intrahepatic cholangiocarcinoma, type 2 diabetes mellitus], with these edited cells:
  - SOT102 "mCRPC or mHSPC"
  - Q-1802 "CASTRATION-SENSITIVE OR CASTRATION-RESISTANT PROSTATE CANCER"
  - VBC108 "HCC or iCCA"
  - RC118 "Diabetes mellitus, type 1 or 2"

## Summary of defects

| Severity | Count | Ids |
|---|---|---|
| High | 3 | P1, P2, P3 |
| Medium-low | 2 | P4, P5 |
| Low | 4 | P6, P7, P8, P9 |

New in revision 10: P1, P2, P4, P6 and P7. P3 is REVIEW9's N2 unfixed for capitals. P5 is a residue of N3/N5. P8
and P9 are residues of D8 and process.

**Single highest-value next fix:** stop letter case from deciding what U1 reads. In `_raw_lookup`, take the N6 screen
shortcut only when the softened reading has no unread and no basket pieces (P1). Pass the original cell's
capitals flag into `_alone`, and keep a reading there when the piece is an acronym of the label (`_initials`) or has
an internal capital (P2, P3). Test every N2 row and every acronym row in lower, mixed and upper case.
