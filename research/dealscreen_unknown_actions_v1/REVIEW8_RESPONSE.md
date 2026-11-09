# Response to the eighth U1 review (REVIEW8.md): revision 9

Revision 9 is U1 on top of revision 8 (624b2f0), committed with R1 revision 15 on `dealscreen-mvp`, as of
2026-11-08. Nobody has reviewed it yet. This file is the implementer's account, not a review: every claim below
should be checked by running code. The reviewer and the implementer are both AI. Neither is a human approval, and
nothing here is validation. U1-7 is not claimed.

U1 changes only diagnostics (the sentence and class that explain an UNKNOWN gate). It changes no gate, disposition,
rank or decision; §3 checks that. The gate's own coordination reading (J-a) is not changed.

## 1. D1 (high): a disease-defining word first in an "or" list

The fix is in U1's own reading. The rule is decided by the NCIt authority, not by a word list alone.
- `_DEFINING` lists the modifier words that can make another concept: acute, chronic, severe, mild, moderate,
  juvenile, adult, pediatric, childhood, early, late, high, low, type, grade, "non-".
- A first piece made only of modifier words that holds one of these is tried with the next name's head
  (`_list_pieces`, `_head`). The candidate is used only when the index reads it as a name (`_named`).
  - "Chronic or acute myeloid leukemia" reads as "Chronic myeloid leukemia" and "acute myeloid leukemia".
  - "Severe or non-severe aplastic anemia" reads as Severe Aplastic Anemia and Non-Severe Aplastic Anemia.
- When the index does not read the candidate, NCIt has no separate concept, and the piece is folded as before.
  - "Moderate or severe ulcerative colitis" is ulcerative colitis.
  - "Locally advanced or metastatic gastric adenocarcinoma" stays one name.

| Request | Record name | Revision 8 | Revision 9 |
|---|---|---|---|
| CML | "Chronic or acute myeloid leukemia" | DIFFERENT_DISEASE (AML) | AMBIGUOUS_NAME: Chronic Myeloid Leukemia (requested); Acute Myeloid Leukemia (not requested) |
| cGVHD | "Chronic or acute GVHD", "… graft versus host disease" | DIFFERENT_DISEASE | AMBIGUOUS_NAME: Chronic GVHD (requested); Acute GVHD (not requested) |
| SAA | "Severe or non-severe aplastic anemia" | DIFFERENT_DISEASE | AMBIGUOUS_NAME: Severe Aplastic Anemia (requested); Non-Severe Aplastic Anemia (not requested) |
| CLL, chronic pancreatitis, chronic hepatitis B | "Chronic or acute …" | DIFFERENT_DISEASE | AMBIGUOUS_NAME naming the requested chronic concept |
| GVHD | "Chronic or acute GVHD", "Acute or chronic GVHD", "Acute or chronic graft versus host disease" | READS_AS_REQUESTED (half), UNREADABLE | READS_AS_REQUESTED naming both subtypes |

REVIEW7's broad guard (no single-half class from any coordinated reading) is not added in that form. It would also
demote "Locally advanced or metastatic NSCLC", which is correctly a different disease for a gastric request. Instead,
a list whose first piece makes its own NCIt concept is now always split. Where NCIt has no such concept, the folded
reading is NCIt's own reading of the disease.

## 2. D2-D9

- **D2 (medium).** A basket piece is no longer set aside as a modifier.
  - A piece that `is_basket` accepts and that names a disease head ("other solid tumors", "all comers", "other
    cancers", "any solid tumour", "metastatic disease") is kept as a basket member (`_basket_piece`, `baskets`).
  - The record is then AMBIGUOUS_NAME, never READS_AS_REQUESTED, and the sentence says it "reads 'other solid
    tumors' as a basket of diseases, not one name".
  - "pain", "infection(s)", "inflammation", "syndrome(s)" and "illness" are no longer modifier words. "Sepsis,
    infection, or pneumonia" reads "infection" as Infectious Disorder (broader).
- **D3 (medium).** An inverted name keeps its defining word.
  - A later comma piece that holds a defining word is tried as the inverted modifier of the name before it
    ("Myeloid leukemia, chronic" → "chronic Myeloid leukemia"; "Diabetes mellitus, type 2" → "type 2 Diabetes
    mellitus"; "Hepatitis B, chronic" → Chronic Hepatitis B).
  - When the index does not read the pair, the piece is named as unread ("does not read 'adult'"), never set aside
    in silence.
- **D4 (medium).** Modifier words in an all-capitals cell are read as words. A cell in capitals is read once with
  its modifier words in lower case (`_softened`); "ALL" stays a name. The step is disclosed ("modifier words in
  capitals read as ordinary words").
  - "STAGE III OR STAGE IV GASTRIC CANCER" is UNDER_REQUESTED_PARENT with gastric stage concepts only, as in lower
    case.
  - "MODERATE OR SEVERE ULCERATIVE COLITIS OR CROHN'S DISEASE" no longer names COVID-19.
  - "LOCALLY ADVANCED OR METASTATIC GASTRIC CANCER" reads Gastric Carcinoma and Malignant Gastric Neoplasm, both
    broader than requested.
- **D5 (medium).** An unread piece is tried again without a leading population (`_population_removed`).
  "Patients with ulcerative colitis or Crohn's disease", "Adult …" and "Pediatric …" are AMBIGUOUS_NAME naming
  Ulcerative Colitis (requested), with the step "'Patients with ulcerative colitis' read as 'ulcerative colitis'".
- **D6 (medium-low).** A name with "or" is tried whole, once its leading qualifiers are removed, before the list is
  split (`_whole`). "Advanced high grade B-cell lymphoma with MYC and BCL2 or BCL6 rearrangements" and "Advanced
  ampullary pancreaticobiliary or gastric type adenocarcinoma" read as their NCIt concepts again, as in revision 7.
- **D7 (low-medium).**
  - A state word in capitals ("NEGATIVE", "NEG", "NOT", "POSITIVE", "LOW", "HIGH", "ABSENT") is never a target
    symbol (`_STATE_SYMBOLS`).
  - A second symbol in a negated part counts only when it has a digit or the target reader reads it
    (`_other_target`).
  - "CLDN18.2 NEGATIVE", "NOT CLDN18.2", "CLDN18.2-negative by IHC" and "CLDN18.2 negative in GC" say "the record
    names no other target the authority reads". SG1906's "… positive for HER2" still says "also names another
    target".
- **D8 (low).** The partly read sentence now ends with the steps that read it, for example "(read once its 'or' list
  split into 3 names and 'metastatic' set aside as a modifier, not a name, a clean-up the gate does not apply)".
- **D9 (low).**
  - "first", "second" and "third" are modifier words. "Gastric adenocarcinoma (first or second line)" is one name
    once they are set aside ("its 'or' list read as one name"), and reads as requested.
  - A leading "Either" is dropped.
  - Not changed: therapy pieces ("after platinum"), and grade lists such as "Grade 1, 2 or 3a follicular lymphoma".

Not changed: F6 acronym meanings ("MDS" → Dystonia 11), declared in revision 8.

## 3. Measured (implementer, 2026-11-08, with R1 revision 15)

| Check | Revision 9 |
|---|---|
| CLDN18.2 open gates with a diagnostic (U1-1) | 38 of 38 |
| Held-out FcRn v1, FcRn v2, C5, synthetic | 104 of 104, no stray diagnostic |
| CLDN18.2 `screening.json` | byte-identical to revision 8, so `after/` is unchanged |
| U1-3 | the same 13 programs as revision 8, all from R1's rights fields |
| Science fields | 0 of 62 (CLDN18.2), 0 of 312 (cross-version) |
| Cycle-4 equivalence | 4 of 4 byte-identical |
| `tests/dealscreen` | 1,886 pass (with R1 revision 15) |

End to end (copies of REVIEW8's workspaces, re-screened):
- `ws_heme8`: SOT102, Q-1802 and VBC108 are AMBIGUOUS_NAME naming the requested chronic GVHD, CML and severe
  aplastic anemia. RC118 reads Chronic Myeloid Leukemia (requested) and is AMBIGUOUS_NAME. None is in "a disease
  neither requested nor a subtype of one".
- `ws_gas8`:
  - VBC108 and RC118 are AMBIGUOUS_NAME and name 'other solid tumors' as a basket.
  - SOT102 is UNDER_REQUESTED_PARENT with gastric stage concepts only.
  - Q-1802 is AMBIGUOUS_NAME_ALL_BROADER (Gastric Carcinoma, Malignant Gastric Neoplasm).
  - TQB2103 and SG1906 say "names no other target the authority reads".
- `ws_uc8`:
  - SOT102, Q-1802 and VBC108 are AMBIGUOUS_NAME naming Ulcerative Colitis (requested).
  - RC118 ("Diabetes mellitus, type 2, or obesity" against a UC request) is UNREADABLE. It reads Type 2 Diabetes
    Mellitus (not requested) and says it does not read 'obesity'.

## 4. Tests

`tests/dealscreen/test_unknown_actions.py` adds a revision 9 block for D1-D9 and controls (397 U1 tests). One
revision 8 test changed: "Gastric adenocarcinoma, adult, or NSCLC" now names 'adult' as unread instead of setting it
aside, because "adult" can make another NCIt concept.

## 5. Limits

- The defining-word rule depends on what the NCIt index holds. A modifier that makes a concept the index does not
  hold is folded, and the reading is NCIt's reading of the head.
- In an all-capitals cell every modifier word is read as a word; an acronym spelled like a modifier word other than
  "ALL" would be missed. I found none in the probes.
- The gate's own coordination reading is unchanged (J-a): a record can still pass the gate on one half of its name.
