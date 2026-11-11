# Response to the tenth U1 review (REVIEW10.md): revision 11

Revision 11 is U1 on top of revision 10 (f1a310d), committed with R1 revision 17 on `dealscreen-mvp`, as of
2026-11-11. Nobody has reviewed it yet. This file is the implementer's account, not a review: every claim below
should be checked by running code. The reviewer and the implementer are both AI. Neither is a human approval, and
nothing here is validation. U1-7 is not claimed.

U1 changes only diagnostics (the sentence and class that explain an UNKNOWN gate). It changes no gate, disposition,
rank or decision; §3 checks that. The gate's own coordination reading (J-a) is not changed.

## 1. P1-P3 (high): letter case no longer decides what U1 reads

- **P1.** `_raw_lookup` takes the screen's reading of a capitals cell only when U1's softened reading has the same
  codes and no unread and no basket piece. Otherwise U1's reading is kept with the capitals step, as in revision 9.
  - "GASTRIC/GEJ ADENOCARCINOMA OR NSCLC" and "GEJ OR NSCLC" are NAMES_REQUESTED_SITE and name the piece U1 does not
    read.
  - "MGC OR NSCLC", "NSCLC OR PAIN", "CGVHD OR BRONCHIOLITIS OBLITERANS", "CHILDHOOD UC OR CROHN'S DISEASE",
    "LIMITED OR EXTENSIVE STAGE SCLC", "ADOLESCENTS WITH ALL OR AML", "ADULT T-CELL LEUKAEMIA OR CTCL" and
    "CASTRATION-SENSITIVE OR CASTRATION-RESISTANT PROSTATE CANCER" are UNREADABLE and name the unread piece; none is
    DIFFERENT_DISEASE.
  - "NON-METASTATIC OR METASTATIC CASTRATION-RESISTANT PROSTATE CANCER" is NAMES_REQUESTED_SITE, as in revision 9.
  - "ADVANCED NSCLC" and "RELAPSED AML" still take the gate's own reading and steps (N6 kept).
- **P2 and P3.** `_alone` no longer looks at letter case. A one-word piece's reading is refused only when the word
  is a word of the label but not its head (the N2 shape: "diffuse" in Gastric Diffuse Adenocarcinoma, "symptomatic"
  in a COVID-19 label), unless the label has two words and the word is the first, or every word of the label is in
  the record. Every other reading is kept, whatever the case:
  - the label's head ("myeloma");
  - an acronym ("mCRPC", "iCCA", "ccRCC", "aml");
  - a synonym that holds no word of the label ("hives" → Urticaria, "sepsis" → Septicemia, "epilepsy" → Seizure
    Disorder).

  So "mCRPC or mHSPC", "mCRPC or nmCRPC", "HCC or iCCA", "iCCA or eCCA", "ccRCC or pRCC", "nsclc or sclc", "Hives or
  angioedema" and "Sepsis or septic shock" are AMBIGUOUS_NAME naming the requested concept again. "DIFFUSE OR
  FOLLICULAR LYMPHOMA", "INTESTINAL OR EXTRAINTESTINAL BEHCET'S DISEASE", "MIXED OR PURE GERM CELL TUMOR", "DIFFUSE
  OR FOLLICULAR LYMPHOMA OR PAIN" and "SYMPTOMATIC OR ASYMPTOMATIC MULTIPLE MYELOMA" read no gastric or COVID-19
  concept, as in lower case. Revision 10's disclosed cost (sepsis, infection and epilepsy named as unread) is gone.

## 2. P4-P9

- **P4 (medium-low).** A borrowed ending is refused when the words it drops hold a site that NCIt names as "<site>
  Neoplasm" (`_names_site`, adjectives included: "Pancreatic Neoplasm"). "Metastatic or pancreatic neuroendocrine
  carcinoma" is then one name, and the gate's own reading applies: Pancreatic Neuroendocrine Carcinoma,
  DIFFERENT_DISEASE for a lung-NEC request. "Recurrent or pharyngeal squamous cell carcinoma" reads Pharyngeal SCC
  only. Neither "shares subtypes" with a lung request. "Relapsing or progressive multiple sclerosis" still names
  Relapsing MS.
- **P5 (medium-low).** A bare number after an inverted "<type|grade|stage|class> N" piece keeps that word. "Diabetes
  mellitus, type 1 or 2" and "Diabetes (type 1 or 2)" name Type 2 Diabetes Mellitus (requested). "Follicular
  lymphoma, grade 1 or 2" and "(grade 1 or 2)" name Grade 2 FL. "Gastric cancer, stage III or IV" names both stage
  concepts. These hold in all three cases.
- **P6 (low).** A line token ("2L") is never a number of `_numbered` ("Stage III or 2L gastric cancer" no longer
  says "Stage 2L"). A carried prefix is quoted as written: "does not read 'Grade 1 or 2 obesity'".
- **P7 (low).** An inverted modifier after a basket piece has no name before it and is named as unread. "GVHD, acute,
  or other solid tumors, chronic" no longer names Chronic GVHD.
- **P8 (low).** A nested list shows its own steps as one step: IBI343 now ends "… and in 'Unresectable or Metastatic
  Gastric Adenocarcinoma', its 'or' list split into 2 names and 'Unresectable' read as 'Unresectable Gastric
  Adenocarcinoma'". Class unchanged.
- **P9 (process).** `after/` is regenerated from revision 11's CLDN18.2 run (§3).

Carried, declared, not changed:
- F6 acronym meanings. With P2, "iCCA" again also reads an unrelated NCIt acronym, "Infantile Convulsions and
  Paroxysmal Choreoathetosis, Familial" (not requested), as in revision 9.
- The REVIEW2 N8 family.
- "Relapsed or refractory multiple myeloma".
- The D5 residue.
- "GEJ adenocarcinoma" is not an index name.
- J-a; J-m (population child under a broader parent) is unchanged.

## 3. Measured (implementer, 2026-11-11, with R1 revision 17)

| Check | Revision 11 |
|---|---|
| CLDN18.2 open gates with a diagnostic (U1-1) | 38 of 38 |
| Held-out FcRn v1, FcRn v2, C5, synthetic | 104 of 104, no stray diagnostic; every held-out `screening.json` program identical to revision 10 |
| CLDN18.2 class counts | identical to revision 10 (`measurement.json` equal) |
| CLDN18.2 `screening.json` against revision 10 | one program differs, in `unknown_diagnostics` only: IBI343's sentence adds its nested step (P8). Same class |
| U1-3 | the same 13 programs as revision 10, all from R1's rights fields |
| Science fields | 0 of 62 (CLDN18.2), 0 of 312 (cross-version) |
| Cycle-4 equivalence | 4 of 4 byte-identical |
| `after/` | regenerated from this run (P9); it was one IBI343 sentence behind |
| `tests/dealscreen` | 2,076 pass (with R1 revision 17) |

End to end (copies of REVIEW10's workspaces, re-screened):
- `ws_caps10`:
  - SOT102 ("DIFFUSE OR FOLLICULAR LYMPHOMA") is UNREADABLE, reads Follicular Lymphoma only and does not read
    'DIFFUSE'.
  - Q-1802 ("GASTRIC/GEJ ADENOCARCINOMA OR NSCLC") is NAMES_REQUESTED_SITE and names the unread gastric piece.
  - VBC108 ("MGC OR NSCLC") is UNREADABLE and names 'MGC'.
  - RC118 ("Metastatic or pharyngeal squamous cell carcinoma") is DIFFERENT_DISEASE and reads Pharyngeal SCC only.
- `ws_mix10`:
  - SOT102 ("mCRPC or mHSPC") is AMBIGUOUS_NAME naming Metastatic CRPC (requested).
  - Q-1802 (the CSPC/CRPC capitals cell) is NAMES_REQUESTED_SITE.
  - VBC108 ("HCC or iCCA") is AMBIGUOUS_NAME naming Intrahepatic Cholangiocarcinoma (requested), with the F6 meaning
    beside it.
  - RC118 ("Diabetes mellitus, type 1 or 2") is AMBIGUOUS_NAME naming Type 2 Diabetes Mellitus (requested).

Reviewer probes `b1`-`b5` (`cmp910.py --head`), against revision 10:
- every P1-P7 row moved as REVIEW10's "Expected" column says;
- no other row of those files changed class.

Earlier probe sets: the U1 rows that changed are:
- the revision 10 cost rows ("Sepsis, infection, or pneumonia", "Infection or sepsis", "Severe AKI or sepsis"), which
  are read again;
- "Follicular lymphoma, grade 1 or 2, or MZL", which now names Grade 2 FL;
- "NSCLC, stage III, or SCLC", which now reads Stage III NSCLC;
- the nested steps (P8).

## 4. Tests

`tests/dealscreen/test_unknown_actions.py` adds a revision 11 block (76 tests). Every N2 row and every acronym row
is tested as written, in lower case and in capitals (`_cases`). It also has P1 capitals lists, P4-P8 and controls. No
earlier U1 test changed.

## 5. Limits

- `_alone` keeps any reading whose label does not hold the word, so a one-word acronym with several NCIt meanings
  names all of them (F6).
- The site test knows only the sites NCIt names as "<site> Neoplasm"; a site named only by a disorder is not one.
- A numbered alternative is read only right after "<word> N".
- The gate's own coordination reading is unchanged (J-a).
