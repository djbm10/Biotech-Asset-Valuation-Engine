# Response to the eleventh U1 review (REVIEW11.md): revision 12

Revision 12 is U1 on top of revision 11 (3dd6b51), committed with R1 revision 18 on `dealscreen-mvp`, as of
2026-11-11. Nobody has reviewed it yet. This file is the implementer's account, not a review: every claim below
should be checked by running code. The reviewer and the implementer are both AI. Neither is a human approval, and
nothing here is validation. U1-7 is not claimed.

U1 changes only diagnostics (the sentence and class that explain an UNKNOWN gate). It changes no gate, disposition,
rank or decision; §3 checks that. The gate's own coordination reading (J-a) is not changed.

## 1. Q1 and Q2 (high)

- **Q1. An ordinary word no longer reads an unrelated disease.** `_alone` refuses an index reading of a one-word
  piece when the word is an ordinary modifier, and the counts come from NCIt's own labels (`_word_uses`):
  - the word is used more often inside labels than as their head ("central" 233 to 0, "sensitive" 44 to 1,
    "diagnosis" 1 to 0). For a reading the word abbreviates, the word must also be used inside at least three labels,
    so "cold" (7 to 0) no longer reads Chronic Obstructive Pulmonary Disease and "aml" (1 to 0) still reads Acute
    Myeloid Leukemia;
  - or the word is never a head and the label holds a modifier of the same stem ("recurrence" → Recurrent Neoplasm).

  A refused piece is read with the last name's head, as in revision 10, and is otherwise named as unread. Even when a
  synonym is kept, the record's own coordination is tried first and wins when NCIt reads it (`_synonyms_only`,
  `_borrow`).
  - "Central, nephrogenic or gestational diabetes insipidus" (central DI request) is AMBIGUOUS_NAME naming Neurogenic
    Diabetes Insipidus (requested), as in revision 10.
  - "Cold or warm autoimmune hemolytic anemia" is UNREADABLE and "does not read 'Cold'", for a cold-agglutinin and a
    COPD request alike.
  - "Sensitive or resistant gastric cancer" is NAMES_REQUESTED_SITE and "does not read 'Sensitive'". The
    "Sensitive or …" SCLC, nephrotic and HGSOC rows no longer list Hypersensitivity.
  - "Diagnosis or treatment of …", "Recurrence or metastasis of …", "Cold or hot tumors of the stomach" and "Central
    or peripheral nervous system metastases of …" no longer read Disease or Disorder, Recurrent Neoplasm, COPD or
    Conventional Osteosarcoma.
  - Kept, because NCIt uses the word as a head at least as often: "sepsis" (Septicemia), "infection" (Infectious
    Disorder), "epilepsy" (Seizure Disorder), "hives" (Urticaria). REVIEW10's cost rows ("Sepsis, infection, or
    pneumonia", "Infection or sepsis") read as in revision 11.
- **Q2. A trailing stage pair keeps the name.**
  - A "stage N" piece that NCIt does not read with the name before it is set aside again, as in revision 10
    (`_list_pieces`).
  - A "grade N" or "type N" piece that does not invert is named as unread. One name beside an unread piece is still
    returned as a list, so the name is read.
  - "Gastric adenocarcinoma, stage III or IV", "(stage 3 or 4)", "(Stage III or IV)", "Melanoma, stage 3 or 4" and
    "Chronic kidney disease, stage 3 or 4" are READS_AS_REQUESTED again. "Breast cancer, stage 2 or 3" and
    "Colorectal cancer, stage 3 or 4" are AMBIGUOUS_NAME naming the request.
  - REVIEW11's 250-label sweep (`q2sweep.py`, revision 11 against revision 12):
    - "L, stage III or IV" and "L (stage 3 or 4)" are READS_AS_REQUESTED for 250 of 250, against 1 at revision 11.
    - "L, grade 1 or 2" is AMBIGUOUS_NAME naming L (requested), with the grades named as unread, for 250 of 250.
      "L, type 1 or 2" is the same for 249 of 250; the 250th, "Familial Hypertrophic Cardiomyopathy, type 1 or 2",
      reads as requested. Both were 0 of 250 at revision 11 and at revision 10 (UNREADABLE or NAMES_REQUESTED_SITE).

## 2. Q3-Q8

- **Q3 (medium). A lineage word is not a site.** `_names_site` reads `_place_sites`: the "<site> Neoplasm" phrases
  `_site_names` keeps (by-site concepts that are not morphology concepts, cleaned with `_NOT_IN_SITE`), plus the
  "<histology> of the <site>" phrases (`_of_sites`), minus tissues that run through every organ (`_TISSUES`:
  vascular, neural, fibrous, endocrine, connective or soft tissue, nervous system).
  - "Metastatic or neuroendocrine prostate carcinoma", "… lung adenocarcinoma" and "Metastatic or vascular colorectal
    carcinoma" are AMBIGUOUS_NAME naming the requested metastatic concept, and name the other piece as unread.
  - "Relapsing or neural multiple sclerosis" names Relapsing MS.
- **Q4 (low-medium). A site that starts in the dropped words counts.** The test now looks at every phrase that starts
  in the words a borrowed ending drops, even when it ends inside the ending ("extrahepatic bile duct"). Junction sites
  come from `_of_sites`.
  - "Metastatic or gastroesophageal junction signet ring cell carcinoma" and the esophagogastric form no longer read
    Metastatic Signet Ring Cell Adenocarcinoma. They are NAMES_REQUESTED_SITE with nothing read.
  - "Metastatic or extrahepatic bile duct carcinoma" no longer reads Metastatic Bile Duct Carcinoma. The list is one
    name, so the gate's own reading applies: Extrahepatic Cholangiocarcinoma and Extrahepatic Bile Duct Carcinoma,
    DIFFERENT_DISEASE for an intrahepatic request. That reading drops "metastatic", as P4's rows do (J-a).
  - Not done: one-word site adjectives that NCIt does not name as "<adjective> Neoplasm" ("biliary", "ampullary")
    are still not sites.
- **Q5 (medium-low).** An inverted "type/grade/stage/class N" is also tried after the name ("<base> type 2").
  "Spinal muscular atrophy, type 1 or 2", "(type 1 or 2)", "Neurofibromatosis, type 1 or 2" and "Glycogen storage
  disease, type I or III" name the requested type, in all three cases. The no-comma form ("Spinal muscular atrophy
  type 1 or 2") is still the disclosed limit.
- **Q6 (low).** An ordinal ("1st") is not a number to `_number`. "Stage III or 1st line gastric cancer" no longer
  says "Stage 1st line".
- **Q7 (low).** A label two readings share is shown with each NCIt code: "Primary Immune Thrombocytopenia (C180701)
  (not requested); Primary Immune Thrombocytopenia (C3446) (requested or a subtype)".
- **Q8 (process).** §3 lists every earlier probe row whose class or text changed, from a full re-run of the earlier
  probe files against revision 11.

Carried, declared, not changed:
- F6 acronym meanings ("iCCA" also reads an unrelated NCIt acronym; "mds" reads Dystonia 11).
- The REVIEW2 N8 family.
- "Relapsed or refractory multiple myeloma".
- The D5 residue.
- "GEJ adenocarcinoma" is not an index name.
- J-a, J-b, J-m.

## 3. Measured (implementer, 2026-11-11, with R1 revision 18)

| Check | Revision 12 |
|---|---|
| CLDN18.2 open gates with a diagnostic (U1-1) | 38 of 38 |
| Held-out FcRn v1, FcRn v2, C5, synthetic | 104 of 104, no stray diagnostic |
| CLDN18.2 class counts | identical to revision 11 (`measurement.json` equal) |
| CLDN18.2 `screening.json` against revision 11 | byte-identical |
| U1-3 | the same 13 programs as revision 11, all from R1's rights fields |
| Science fields | 0 of 62 (CLDN18.2), 0 of 312 (cross-version) |
| Cycle-4 equivalence | 4 of 4 byte-identical |
| `after/` | unchanged; no CLDN18.2 sentence changed |
| `tests/dealscreen` | 2,316 pass (with R1 revision 18) |

End to end (copies of REVIEW11's workspaces, re-screened):
- `ws_x11`:
  - SOT102 ("Central, nephrogenic or gestational diabetes insipidus") is AMBIGUOUS_NAME naming Neurogenic Diabetes
    Insipidus (requested). No osteosarcoma.
  - Q-1802 ("Cold or warm autoimmune hemolytic anemia") is UNREADABLE and "does not read 'Cold'". No COPD.
  - VBC108 ("Metastatic or neuroendocrine prostate carcinoma") is AMBIGUOUS_NAME naming Metastatic Prostate Carcinoma
    (requested).
  - RC118 ("Spinal muscular atrophy, type 1 or 2") is AMBIGUOUS_NAME naming the requested type 2.
- `ws_g11`:
  - SOT102 ("Gastric adenocarcinoma, stage III or IV") and RC118 ("Gastric adenocarcinoma (stage 3 or 4)") are
    READS_AS_REQUESTED.
  - Q-1802 ("Sensitive or resistant gastric cancer") is NAMES_REQUESTED_SITE and "does not read 'Sensitive'".
  - VBC108 ("Metastatic or gastroesophageal junction signet ring cell carcinoma") is NAMES_REQUESTED_SITE, with no
    borrowed reading.

REVIEW11's probe files `c1`-`c7` (`cmp1112.py`, revision 11 against revision 12; 239 rows): 48 rows changed class
and 29 changed text only. Every changed row is one of these:
- a Q1 row: the "Central", "Cold", "Sensitive", "Diagnosis" and "Recurrence" rows, including "Central or branch
  retinal vein occlusion", which now names Central Retinal Vein Occlusion (requested);
- a Q2 stage, grade or type row. One of these is a cost. "SCLC, stage III or IV NSCLC" now sets "stage III" aside, as
  revision 10 did, where revision 11 named it as unread. Neither reads it as Stage III NSCLC, and the class is
  unchanged (AMBIGUOUS_NAME);
- a Q3 lineage row;
- a Q5 postfix-number row;
- "Preinvasive or invasive breast cancer", which shows a new step ("'Preinvasive' read as 'Preinvasive cancer'") and
  reads the same concepts;
- "Recurrent or intrahepatic bile duct carcinoma" (ICC request). It was AMBIGUOUS_NAME, reading "Recurrent bile duct
  carcinoma", which drops the site. The borrowed ending is now refused (Q4), the list is one name, and the gate's
  own reading applies: READS_AS_REQUESTED, Intrahepatic Cholangiocarcinoma. That reading drops "recurrent" (J-a).

Earlier probe sets (REVIEW8 `t8`/`h8`, REVIEW9 `t9`, REVIEW10 `b1`-`b5`, the implementer's revision 9 and 10 probes):
one row changed, in text only. "Mixed or pure germ cell tumor" now names "Mixed Germ Cell Tumor (C4285)" and "Mixed
Germ Cell Tumor (C4290)" (Q7). No class changed.

Rows of REVIEW11 §Q8's list:
- `slash` "Gastric adenocarcinoma (Stage III or IV)" is READS_AS_REQUESTED again;
- "Gastric adenocarcinoma, stage IV, or NSCLC" says "'stage IV' set aside" again;
- `a4` "GASTRIC CANCER, STAGE IV, OR NSCLC" is unchanged from revision 11 (DIFFERENT_DISEASE, J-b).

## 4. Tests

`tests/dealscreen/test_unknown_actions.py` adds a revision 12 block (146 tests). Every Q1-Q6 row is tested as
written, in lower case and in capitals (`_cases`), with the controls REVIEW11 asked for:
- an ordinary-word synonym;
- the stage, grade and type forms of a plain requested label;
- a lineage word before a borrowed ending;
- a junction and a duct site;
- a postfix number;
- an ordinal;
- the shared label;
- the disease words that keep their synonym (sepsis, infection, epilepsy, hives, AML).

No earlier U1 test changed.

## 5. Limits

- The ordinary-word test is a count over NCIt labels, not a dictionary. A word NCIt uses as often as a head as inside
  labels keeps its synonym, even when the record uses it as an adjective.
- A one-word piece read through an acronym is refused only when the word is used inside three labels or more, so an
  acronym that is also a rare English word may still read its disease.
- `_TISSUES` is a short list of generic tissue words, like `_NOT_IN_SITE`. A one-word site adjective NCIt does not
  name as "<adjective> Neoplasm" is not a site.
- A numbered alternative is read only right after "<word> N".
- The gate's own coordination reading is unchanged (J-a).
