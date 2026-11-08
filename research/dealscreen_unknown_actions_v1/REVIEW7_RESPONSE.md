# Response to the seventh U1 review (REVIEW7.md): revision 8

Revision 8 is U1 on top of revision 7 (d6d2d7f), committed with R1 revision 14 on `dealscreen-mvp`, as of
2026-11-08. Nobody has reviewed it yet. This file is the implementer's account, not a review: every claim below
should be checked by running code. The reviewer and the implementer are both AI. Neither is a human approval, and
nothing here is validation. U1-7 is not claimed.

U1 changes only diagnostics (the sentence and class that explain an UNKNOWN gate). It changes no gate, disposition,
rank or decision; §3 checks that.

## 1. F1 (high): the record's own "or" list is read on every path

REVIEW7's fix: split on the record's own "or" list whatever path read the name, on the original text; fold a
qualifier piece into the piece after it; never return DIFFERENT_DISEASE from a list unless every piece was read.

- `indication_relations._raw_lookup` now tries `_conjuncts` on the original name right after the exact index lookup,
  before the screen's reading and before U1's own clean-ups. A name with no "or" is not split.
- `_list_pieces` splits at "or", "and/or" and the commas of an "or" list. A piece made only of modifier words
  (extent, state, stage, grade, line, population and generic words, Roman or digit stages; `_MODIFIER_WORDS`,
  `_STAGE_TOKEN`) is never looked up alone. First in the list, it belongs to the name after it ("Locally advanced or
  metastatic gastric adenocarcinoma" is one name). Later, set apart by commas, it is set aside and the sentence says
  so ("'metastatic' set aside as a modifier, not a name"). A biomarker piece ("HER2+", "AChR+") is set aside the same
  way. A capitalised acronym ("ALL") is a name, never the word "all".
- A parenthesised "or" list is part of the list: "IBD (ulcerative colitis or Crohn's disease)" reads IBD (broader),
  ulcerative colitis (requested) and Crohn disease (not requested).
- A piece the index does not read is tried again without leading state words ("R/R adult ALL" -> "adult ALL").
- U1's own clean-up drops the "or" of a qualifier pair with it ("moderate or severe X" -> "X").
- A list whose every name reads as requested is READS_AS_REQUESTED, naming each reading.

Re-run of REVIEW7's rows (`u1rr7/probes/q7.py` and `h7.py`, and `scratchpad/u1r8/f.py`):

| Request | Record name | Revision 7 | Revision 8 |
|---|---|---|---|
| GAS | "Locally advanced or metastatic gastric adenocarcinoma or NSCLC" (and "Advanced or", "Unresectable or", "Recurrent or", "Relapsed or refractory") | DIFFERENT_DISEASE (NSCLC) | AMBIGUOUS_NAME: Gastric Adenocarcinoma (requested); NSCLC (not requested) |
| GAS | "Gastric adenocarcinoma or oesophageal adenocarcinoma" | DIFFERENT_DISEASE | AMBIGUOUS_NAME: Gastric Adenocarcinoma (requested); Esophageal Adenocarcinoma (not requested) |
| GAS | "Gastric adenocarcinoma, metastatic, or NSCLC"; ", stage IV,"; ", adult,"; ", HER2+,"; ", 2L," | DIFFERENT_DISEASE or NAMES_REQUESTED_SITE | AMBIGUOUS_NAME, the middle piece "set aside as a modifier, not a name" |
| UC | "Moderate or severe ulcerative colitis or Crohn's disease", "Relapsed or refractory …" | DIFFERENT_DISEASE | AMBIGUOUS_NAME: Ulcerative Colitis (requested); Crohn Disease (not requested) |
| MG | "Relapsed or refractory myasthenia gravis or CIDP", "Myasthenia gravis, AChR+, or CIDP" | DIFFERENT_DISEASE, UNREADABLE | AMBIGUOUS_NAME naming both |
| ALL-A | "Relapsed or refractory adult ALL or AML", "R/R adult ALL or AML" | DIFFERENT_DISEASE | AMBIGUOUS_NAME naming Adult ALL and AML |
| AML | "Relapsed or refractory ALL or AML" | READS_AS_REQUESTED (AML only) | AMBIGUOUS_NAME naming both |

"Relapsed/refractory adult ALL or AML" and "Newly diagnosed adult ALL or AML" are AMBIGUOUS_NAME too, through the
state-word retry ("'Newly diagnosed adult ALL' read as 'adult ALL'"). No row of `q7.py` is DIFFERENT_DISEASE.

## 2. F2-F6

- **F2 (medium).** A stage piece is never looked up alone, so no other organ's stage concept appears. "Stage III or
  stage IV gastric cancer", "Stage IIIB or stage IV gastric cancer" and "Stage IV or recurrent gastric cancer" are
  UNDER_REQUESTED_PARENT again (revision 6's class), naming only gastric stage concepts. "Stage III or IV gastric
  adenocarcinoma" is NAMES_REQUESTED_SITE. "Stage I or II NSCLC", "Grade 1 or 2 follicular lymphoma" and "Juvenile or
  adult rheumatoid arthritis" read as requested again. The edition note is given once (notes are de-duplicated).
- **F3 (medium).** A list that reads a requested name is AMBIGUOUS_NAME, never UNREADABLE, and its sentence says "is
  not a name the NCIt authority can read as a whole; of the names in its 'or' list it reads … and does not read …",
  not "matches several NCIt concepts". "Ulcerative colitis, pouchitis or Crohn's disease", "Myasthenia gravis, LEMS or
  CIDP" and "Obesity or type 2 diabetes" are AMBIGUOUS_NAME. The summaries now read "a name with several NCIt
  readings, or an 'or' list read only in part" and "no name the NCIt authority reads as a whole". A country piece
  ("China") is still quoted as unread; a marker or modifier piece is set aside.
- **F4 (medium).** "absent" before a symbol negates it only at the start of the part (`_ABSENT_BEFORE`). "HER2 absent
  CLDN18.2 positive" (E2E TQB2103), "PD-L1 absent CLDN18.2 high" and "KLX9-absent VORP3.1-high" name the target;
  "absent ABC1.2" still states it is not the target.
- **F5 (low-medium).** A negated part that names a second symbol ends "… also names another target, which DealScreen
  does not read apart from it", never "the record names no other target" (SG1906 "CLDN18.2 negative or positive for
  HER2"). Symbols are now found with hyphens inside ("PD-L1" is one symbol, not two).
- **F6 (low).** Head borrowing no longer reads "Localized" alone ("Localized or metastatic prostate cancer" reads as
  Prostate Carcinoma), and "Intestinal or diffuse type gastric adenocarcinoma" is AMBIGUOUS_NAME with the requested
  intestinal type read. Not changed: an acronym piece still gets the index's other meanings ("GC" -> Gonorrhea, "MDS"
  -> Dystonia 11). That is the authority's index, quoted with the record's piece; I did not add a rule for it.

Cosmetic "'pos' (not read as a target)" and the "not VORP3.1, positive" quote are not changed.

## 3. Measured (implementer, 2026-11-08, with R1 revision 14)

| Check | Revision 8 |
|---|---|
| CLDN18.2 open gates with a diagnostic (U1-1) | 38 of 38 |
| Held-out FcRn v1, FcRn v2, C5, synthetic | 104 of 104, no stray diagnostic |
| CLDN18.2 class counts | identical to revision 7 |
| CLDN18.2 screens against `after/` (revision 7) | 3 differ, all in `unknown_diagnostics`: two summaries now say "as a whole"; IBI343's "Unresectable or Metastatic Gastric or Gastroesophageal Junction Adenocarcinoma" now names both requested readings instead of one (same class, READS_AS_REQUESTED) |
| `after/unknown_actions.csv` | one row's sentence changed (IBI343, as above) |
| U1-3 (programs with a changed decision, disposition, rank or transaction) | the same 13 as revision 7, all from R1's two added rights fields; no U1 change touches a transaction field |
| Science fields | 0 of 62 (CLDN18.2), 0 of 312 (cross-version) |
| Cycle-4 equivalence | 4 of 4 byte-identical |
| `tests/dealscreen` | 1,803 pass (with R1 revision 14) |

End to end (copies of REVIEW7's workspaces, re-screened):
- `ws_e2e_gas7`: SOT102, Q-1802, VBC108 and RC118 are AMBIGUOUS_NAME naming gastric adenocarcinoma (requested);
  TQB2103 names the target; SG1906 states it is not CLDN18.2 and says the part names another target.
- `ws_e2e_gas7b`: SOT102, Q-1802 and RC118 are UNDER_REQUESTED_PARENT with gastric stage concepts only.
- `ws_e2e_uc7`: SOT102, Q-1802, VBC108 and RC118 are AMBIGUOUS_NAME naming ulcerative colitis (requested).

## 4. Tests

`tests/dealscreen/test_unknown_actions.py` adds a revision 8 block for F1-F5 (364 U1 tests). One revision 7 test
changed: "Gastric adenocarcinoma or pancreatic cancer" is now AMBIGUOUS_NAME naming both diseases, not
NAMES_REQUESTED_SITE.

## 5. Limits

- The list split reads what the NCIt index reads directly, with the last piece's head, or without leading state
  words. An abbreviation the index does not hold stays unread and is named; an abbreviation it holds may bring in
  another meaning (F6).
- A modifier word list decides what is set aside. A disease written only in such words would be set aside; I found
  none in the probes.
- The gate's own coordination reading is unchanged (J-a): a record can still pass the gate on one half of its name.
