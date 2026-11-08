# Response to the sixth U1 review (REVIEW6.md): revision 7

Revision 7 is U1 on top of revision 6 (7a62efd), committed with R1 revision 13 on `dealscreen-mvp`, as of
2026-11-08. Nobody has reviewed it yet. This file is the implementer's account, not a review: every claim below
should be checked by running code. The reviewer and the implementer are both AI. Neither is a human approval, and
nothing here is validation. U1-7 is not claimed.

U1 changes only diagnostics (the sentence and class that explain an UNKNOWN gate). It changes no gate, disposition,
rank or decision; the measurements in §3 check that.

## 1. E1 (high): a two-disease "or" name classed by one half

The reviewer's preferred fix. `indication_relations._conjuncts` splits an "or" list itself and looks each piece up
in the NCIt authority. An unread piece is tried again with the last piece's head words ("Pancreatic" →
"Pancreatic adenocarcinoma"). If a piece is a qualifier ("locally advanced or metastatic …") or a generic remainder,
the split is abandoned and the earlier reading stands. `_raw_lookup` uses the split whenever the screen's reading
says "coordination expanded", so U1 never classes a name from a reading of half of it. When every piece is read, the
name is classed by all the readings, as an ambiguous name already was. When some pieces are unread, the class is
NAMES_REQUESTED_SITE if a requested site is named, otherwise UNREADABLE, and the sentence names what was and was not
read: "'UC or Crohn's disease' is not a name the NCIt authority can read as a whole; of the names in its 'or' list it
reads Crohn Disease (not requested) and does not read 'UC' (a reading the gate does not apply)".

The reviewer's rows (`i6c.py`, `i6b.py`, re-run at revision 7):

| Request | Record name | Revision 6 | Revision 7 |
|---|---|---|---|
| UC | "Ulcerative colitis or Crohn's disease" | DIFFERENT_DISEASE | AMBIGUOUS_NAME: Ulcerative Colitis (requested or a subtype); Crohn Disease (not requested) |
| UC | "UC or Crohn's disease" | DIFFERENT_DISEASE | UNREADABLE, naming Crohn Disease as read and 'UC' as not read |
| UC | "Crohn's disease or ulcerative colitis" | READS_AS_REQUESTED | AMBIGUOUS_NAME naming both (the gate's own PASS is unchanged: J-a) |
| MG | "Myasthenia gravis or CIDP" | DIFFERENT_DISEASE | AMBIGUOUS_NAME: Myasthenia Gravis (requested); CIDP (not requested) |
| ALL-A | "Adult ALL or AML", "Adult acute lymphoblastic leukemia or AML" | DIFFERENT_DISEASE | AMBIGUOUS_NAME: Adult ALL (requested); AML (not requested) |
| ALL-A | "ALL or AML", "AML or ALL" | DIFFERENT_DISEASE, BROADER | AMBIGUOUS_NAME: ALL (broader); AML (not requested), in both orders |
| HCC | "HCC or cholangiocarcinoma" | DIFFERENT_DISEASE | AMBIGUOUS_NAME: Hepatocellular Carcinoma (requested); Hilar Cholangiocarcinoma and Cholangiocarcinoma (the index's two readings of "cholangiocarcinoma"; not requested) |
| GAS | "Gastric adenocarcinoma or NSCLC" | DIFFERENT_DISEASE | AMBIGUOUS_NAME: Gastric Adenocarcinoma (requested); NSCLC (not requested) |
| GAS | "Gastric Adenocarcinoma or Pancreatic Ductal Adenocarcinoma" | DIFFERENT_DISEASE | AMBIGUOUS_NAME, both named |
| GAS | "Pancreatic, gastric or esophageal adenocarcinoma" | DIFFERENT_DISEASE | AMBIGUOUS_NAME, three readings named |
| GAS | controls "Gastric adenocarcinoma or pancreatic cancer", "Locally advanced or metastatic gastric adenocarcinoma" | NAMES_REQUESTED_SITE, READS_AS_REQUESTED | unchanged |

The asymmetry of the gate itself (J-a) belongs to the owner of `indications.py` and is not changed. U1 no longer
turns it into a statement about the record.

## 2. E2-E7

- **E2 (medium).** A second state counts for the negated target only when nothing but punctuation, the end of the
  cell or a cohort, population, status or expression word follows it (`_STATE_END`). That test now covers the part
  itself, not only the text after it. A full stop counts only at the end of the cell, so the "pos." in "pos. KLX9"
  is an abbreviation. A part that holds two target symbols ("VORP3.1 negative KLX9 neg/pos") never reads as both
  states, because the second state belongs to the other symbol. "CLDN18.2 negative, positive PD-L1 expression"
  (SG1906) is now SOURCE_NAMES_OTHER_TARGETS with "('CLDN18.2 negative' states it is not CLDN18.2)", and so are the
  VORP3.1/KLX9 rows. "… negative or positive for KLX9" and "… negative / positive for KLX9" are
  SOURCE_STATES_NOT_REQUIRED_TARGET.
- **E3 (low).** Both states may be joined by "and/or", "&/or", "/", "or", "and", "&", ",", "+", "plus", "|" or a
  dash (`_STATE_JOIN`). Whitespace and dashes are normalised before comparing, and a part rebuilt around a
  parenthesis is compared without parentheses. "CLDN18.2 negative and/or positive" (TQB2103) now names the target and
  lists 'positive' as also on record. It is no longer read as a negation.
- **E4 (low).** Every Unicode dash and hyphen (U+2010-2015, U+2212, U+FE58, U+FE63, U+FF0D) is read as "-" for
  matching, on both sides of the symbol. "non–CLDN18.2" (AK132) and "CLDN18.2‑negative" are
  SOURCE_STATES_NOT_REQUIRED_TARGET.
- **E5 (low).** "ALL" is the word "all" only before a plural head, "solid" or "comers". "ALL disease", "Adult ALL
  disease" (RC118), "ALL malignancy" and the other singular heads are UNREADABLE, not baskets. "ALL cancers", "ALL
  solid tumors", "ALL COMERS" and "ALL tumors" stay baskets.
- **E6 (low).** "absent", "not expressed" and "expression absent" are negations. "negative or low" and "low or
  negative" both state two states and name the target, in either order.
- **E7 (low).** A state word ("metastatic", "refractory", "resistant") before a tumour head keeps the site. "Gastric
  metastatic adenocarcinoma", "Gastric Metastatic Cancer", "Gastric refractory cancer", "Gastric
  treatment-refractory cancer" and "Gastric resistant cancer" are NAMES_REQUESTED_SITE.

Cosmetic items (the "skin unspecified" site phrases and the colorectal subsites) are not changed.

## 3. Measured (implementer, 2026-11-08, with R1 revision 13)

| Check | Revision 7 |
|---|---|
| CLDN18.2 open gates with a diagnostic (U1-1) | 38 of 38 |
| Held-out FcRn v1, FcRn v2, C5, synthetic | 104 of 104, no stray diagnostic |
| `after/unknown_actions.csv` | byte-identical to revision 6 (no CLDN18.2 record uses the changed wordings) |
| CLDN18.2 class counts | identical to revision 6 |
| Science fields | 0 of 62 (CLDN18.2), 0 of 312 (cross-version) |
| Cycle-4 equivalence | 4 of 4 byte-identical |
| `tests/dealscreen` | 1,726 pass (with R1 revision 13) |

`after/measurement.json` now lists 13 programs under U1-3. All 13 have rights evidence. Each cited rights row
carries two more fields from R1 revision 13 (`external_id`, `related_deal_id`). With those removed, all 62 screens
are identical to revision 6's. No U1 change touches a transaction field.

The reviewer's end-to-end workspaces, re-screened (copies; the originals were not modified):
- `ws_e2e_gas6`:
  - SOT102, Q-1802 and VBC108 are AMBIGUOUS_NAME, naming the requested gastric adenocarcinoma and the other disease;
  - RC118 ("Adult ALL disease") is UNREADABLE;
  - SG1906 is SOURCE_NAMES_OTHER_TARGETS with "('CLDN18.2 negative' states it is not CLDN18.2)";
  - AK132 ("non–CLDN18.2") is SOURCE_STATES_NOT_REQUIRED_TARGET;
  - TQB2103 ("negative and/or positive") names the target, with 'positive' also on record.
- `e2e_uc6` inputs, rebuilt as a workspace:
  - SOT102 is AMBIGUOUS_NAME (Ulcerative Colitis requested; Crohn Disease not);
  - Q-1802 is UNREADABLE, naming 'UC' as unread;
  - VBC108 still passes the gate (J-a, unchanged).

## 4. Tests

`tests/dealscreen/test_unknown_actions.py` adds a revision 7 block for E1-E7 and their controls, including the abbreviation and two-symbol rows found while re-running the reviewer's probes (335 U1 tests).

## 5. Limits

- The "or" split reads only what the NCIt index reads directly or with the last piece's head. An abbreviation the
  index does not hold ("UC") stays unread and is named as unread.
- The gate's own coordination reading is unchanged (J-a), so a record can still pass the gate on one half of its
  name. U1 describes the record; it does not change the gate.
- A second state followed by a word outside the cohort list is read as another target's state. A rarer wording
  ("negative or positive in all lines") is read as a negation. That is an understatement, not a reversal.
