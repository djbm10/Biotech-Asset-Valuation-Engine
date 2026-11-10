# Response to the ninth U1 review (REVIEW9.md): revision 10

Revision 10 is U1 on top of revision 9 (28535ea), committed with R1 revision 16 on `dealscreen-mvp`, as of
2026-11-10. Nobody has reviewed it yet. This file is the implementer's account, not a review: every claim below
should be checked by running code. The reviewer and the implementer are both AI. Neither is a human approval, and
nothing here is validation. U1-7 is not claimed.

U1 changes only diagnostics (the sentence and class that explain an UNKNOWN gate). It changes no gate, disposition,
rank or decision; §3 checks that. The gate's own coordination reading (J-a) is not changed.

## 1. N1 and N2 (high): NCIt decides, not a word list

- **N1.** A leading piece made only of modifier words is now tried with the next name's head whatever its words
  (`_list_pieces`; the `_defining` precondition is gone).
  - The head is the next name without its modifier words. When that removes nothing, it is the next name's longest
    ending that is itself an NCIt name of two words or more (`_heads`). "progressive multiple sclerosis" gives
    "multiple sclerosis". A one-word ending ("adenocarcinoma") is never borrowed, because it would drop the site.
  - "Relapsing or progressive multiple sclerosis" is AMBIGUOUS_NAME: Relapsing Multiple Sclerosis (requested);
    Progressive Multiple Sclerosis (not requested).
  - "Locally advanced or metastatic gastric adenocarcinoma" now reads Locally Advanced Gastric Adenocarcinoma and
    Metastatic Gastric Adenocarcinoma. The class is still READS_AS_REQUESTED for a gastric request.
  - Where NCIt has no concept for the borrowed name, the list is still folded. "Relapsed or refractory multiple
    myeloma" stays BROADER_THAN_REQUESTED for a refractory-myeloma request, because NCIt does not hold "relapsed
    multiple myeloma". That is the authority's index; I did not add a guard over the gate's coordination reading
    (see §2).
- **N2.** A one-word piece read alone keeps only readings that are that word's own disease (`_alone`). That is
  true when the word is the head of the label ("myeloma" → Multiple Myeloma), the first word of a two-word label
  ("diabetes" → Diabetes Mellitus), or when every word of the label is in the record. An acronym in mixed case
  ("ALL") is kept. Otherwise the piece is tried with the last name's head, as before, and named as unread when that
  fails.
  - "Diffuse or follicular lymphoma", "Intestinal or extraintestinal Behçet's disease", "Mixed or pure germ cell
    tumor" and "Diffuse, follicular, or mantle cell lymphoma" read no gastric concept. "Mixed germ cell tumor" and
    "Diffuse cutaneous systemic sclerosis" are read with the borrowed head.
  - "Symptomatic or asymptomatic multiple myeloma" reads no COVID-19 concept; it is UNREADABLE.
  - Cost: "Sepsis" (index: Septicemia), "infection" (Infectious Disorder) and "epilepsy" (Seizure Disorder) are no
    longer read alone in a list, and are named as unread. "Sepsis, infection, or pneumonia" moved from
    AMBIGUOUS_NAME to UNREADABLE. That is the cost of refusing synonyms whose label does not hold the word.

| Request | Record name | Revision 9 | Revision 10 |
|---|---|---|---|
| RMS | "Relapsing or progressive multiple sclerosis" | DIFFERENT_DISEASE (Progressive MS) | AMBIGUOUS_NAME naming Relapsing MS (requested) |
| GAS | "Diffuse or follicular lymphoma" | AMBIGUOUS_NAME: Gastric Diffuse Adenocarcinoma (requested) | UNREADABLE: reads Follicular Lymphoma, does not read 'Diffuse' |
| GAS | "Intestinal or extraintestinal Behçet's disease" | AMBIGUOUS_NAME: Gastric Intestinal-Type Adenocarcinoma | UNREADABLE |
| COVID-19 | "Symptomatic or asymptomatic multiple myeloma" | AMBIGUOUS_NAME naming a COVID-19 concept | UNREADABLE, no COVID-19 reading |

## 2. N3-N9

- **N3 (medium).** A number keeps the word it numbers (`_numbered`). After "Type 1", "Grade 2" or "Stage III", a
  piece that starts with a bare number is read with that word.
  - "Type 1 or 2 diabetes mellitus" names Type 2 Diabetes Mellitus (requested).
  - "Grade 1 or 2 follicular lymphoma" names Grade 2 FL; "Grade 2 or 3a" names Grade 3a FL.
  - "Stage III or IV gastric cancer" now reads both stage concepts (J-k).
- **N4 (medium).** A piece read once its population is removed is read as the concept's own population child,
  when NCIt has one that is a descendant (`_with_population`).
  - "Children with ALL or AML" reads Childhood Acute Lymphoblastic Leukemia; "Adults with ALL or AML" reads Adult
    ALL; "Pediatric Hodgkin lymphoma or NHL" reads Childhood Hodgkin Lymphoma. None is "broader".
  - Where NCIt has no population child ("Adult ulcerative colitis", "Adult SLE"), the parent reading stays, with
    the step shown.
- **N5 (medium-low).** Each later modifier is inverted with the same base name, not with the previous result.
  "GVHD, acute or chronic, or AML" names Acute GVHD, Chronic GVHD (requested) and AML; "Diabetes mellitus, type 1 or
  type 2" and "Leukemia, acute or chronic, or lymphoma" name both subtypes.
- **N6 (low-medium).** When the cell in capitals, softened, reads the same concepts as the screen's own reading of
  the cell, the screen's reading and steps are used. "ADVANCED NSCLC" and "RELAPSED AML" no longer say "a clean-up
  the gate does not apply". Where the two differ ("STAGE III OR IV GASTRIC CANCER", which the gate reads as stage
  III only), U1's reading is kept and says so.
- **N7 (low).** Pieces quoted from a cell in capitals are quoted in capitals (`_as_written`): "'CHILD-PUGH A'",
  "'TYPE 2 DIABETES MELLITUS'", "'ALL COMERS'".
- **N8 (low).** Grade, line, stage and cycle tokens ("G1/G2", "2L", "IV", "Q2W") are not a second target, and
  function words in capitals ("IN", "OF", "WITH") are not target symbols. "CLDN18.2 negative in G1/G2 tumours" and
  "CLDN18.2 NEGATIVE IN 2L" say "names no other target the authority reads". "… positive for HER2" and "NOT CLDN18.2
  OR HER2" still name another target.
- **N9 (low).** A modifier set apart by commas that was not read with the name before it is named that way: "does
  not read 'severe' with the name before it". It is no longer called one of the names of the list.

Not changed:
- REVIEW7/REVIEW8's broad guard (no DIFFERENT_DISEASE from the gate's coordination reading). With N1, a leading
  modifier that makes its own NCIt concept is always split. A fold now happens only where NCIt has no such concept,
  and the guard would demote correct readings such as "Locally advanced or metastatic NSCLC" for a gastric request.
- F6 acronym meanings.
- The D5 residue "Adult or pediatric ulcerative colitis or Crohn's disease".
- J-b, J-h, J-i, J-l.

## 3. Measured (implementer, 2026-11-10, with R1 revision 16)

| Check | Revision 10 |
|---|---|
| CLDN18.2 open gates with a diagnostic (U1-1) | 38 of 38 |
| Held-out FcRn v1, FcRn v2, C5, synthetic | 104 of 104, no stray diagnostic |
| CLDN18.2 class counts | identical to revision 9 |
| CLDN18.2 `screening.json` against revision 9 | one sentence differs, in `unknown_diagnostics` and its action. IBI343's "Unresectable or Metastatic Gastric or Gastroesophageal Junction Adenocarcinoma" now names Unresectable Gastric Adenocarcinoma and Metastatic Gastric Adenocarcinoma instead of Gastric Adenocarcinoma. Same class (READS_AS_REQUESTED) |
| U1-3 | the same 13 programs as revision 9, all from R1's rights fields |
| Science fields | 0 of 62 (CLDN18.2), 0 of 312 (cross-version) |
| Cycle-4 equivalence | 4 of 4 byte-identical |
| `tests/dealscreen` | 1,956 pass (with R1 revision 16) |

End to end (copies of REVIEW9's workspaces, re-screened):
- `ws_gas9`:
  - SOT102 ("Diffuse or follicular lymphoma") and Q-1802 ("Intestinal or extraintestinal Behcet's disease") are
    UNREADABLE and name no gastric concept.
  - VBC108 ("ADVANCED NSCLC") is DIFFERENT_DISEASE with the gate's own steps.
- `ws_mix9`:
  - SOT102 names Type 2 Diabetes Mellitus (requested).
  - Q-1802 names Relapsing Multiple Sclerosis (requested).
  - RC118 names Chronic GVHD (requested).
  - VBC108 ("Children with ALL or AML") reads Childhood ALL and AML. It is DIFFERENT_DISEASE for an adult-ALL
    request, as "Childhood ALL or AML" is.
- `ws_gas8` (REVIEW8's):
  - SOT102 ("STAGE III OR IV GASTRIC CANCER") now names both stage concepts.
  - Q-1802 quotes 'LOCALLY ADVANCED' as written.
  - Nothing else in the U1 diagnostics changed.
- `ws_heme8` and `ws_uc8`: no U1 diagnostic changed for the reviewed programs.

## 4. Tests

`tests/dealscreen/test_unknown_actions.py` adds a revision 10 block for N1-N9 and controls (21 tests). No earlier U1
test changed.

## 5. Limits

- The one-word rule trusts the label's shape. A one-word synonym whose label does not hold the word (Septicemia for
  "sepsis") is now named as unread.
- The borrowed head is the next name's longest ending that NCIt reads, so a modifier that makes a concept only with
  a shorter, one-word ending is folded.
- A population child is found only by NCIt's label "Childhood <label>" or "Adult <label>".
- The gate's own coordination reading is unchanged (J-a): a record can still pass the gate on one half of its name.
