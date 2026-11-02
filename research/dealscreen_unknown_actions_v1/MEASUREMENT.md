# Cycle U1 measurement: a concrete next action for every tool UNKNOWN

INTERNAL DEVELOPMENT. AI-simulated measurement only; no human validation is claimed.

Measured on 2026-11-01 (R1 revision 8 plus U1 revision 4; CLDN18.2 outputs identical to revision 3, and on 2026-11-02 identical again with R1 revision 10 plus U1 revision 5), CLDN18.2 landscape, buyer C3, as-of 2026-10-29.
Baseline: `research/dealscreen_rights_v1/after_v8/screening_R1v8.json` (R1 revision 8, no U1), copied to
`baseline/screening_R1.json`. Outputs: `after/`. Criteria: `ACCEPTANCE.md` (frozen before code; the revision note
lists what changed during implementation and review).

## Result in one paragraph

Every UNKNOWN gate decision on a program that is not excluded carries a DealScreen diagnostic: 38 of 38 on
CLDN18.2 (baseline 0 of 38), and 104 of 104 on the FcRn v1, FcRn v2, C5 held-out and synthetic landscapes. Each
diagnostic names what the record holds, as written, and the one cited fact that would decide the gate. No gate,
disposition, rank, machine recommendation or transaction field changed (0 of 62 CLDN18.2 programs, 0 of 312
cross-version programs; equivalence byte-identical on 4 of 4 workspaces). One reference-IN program (SOT102) gets an
indication action that points away from it, because its record names only pancreatic cancer; it is reported below.
U1 does not reach excluded programs: on CLDN18.2, 17 UNKNOWN decisions on 16 excluded programs get no diagnostic
(one of them, LCB02A, is reference IN).

## U1-1: coverage

| Landscape | UNKNOWN decisions on non-excluded programs | With a diagnostic | Diagnostics on other decisions or excluded programs |
|---|---|---|---|
| CLDN18.2 (C3) | 38 | 38 | 0 |
| FcRn v1 | 28 | 28 | 0 |
| FcRn v2 | 28 | 28 | 0 |
| C5 held-out | 28 | 28 | 0 |
| Synthetic 200 | 20 | 20 | 0 |

Before U1, the 38 CLDN18.2 decisions carried one of four generic S&E actions: "Obtain specific,
authority-comparable indication evidence.", "Research fact type 'development_stage_order'.", "Research fact type
'modality_id'." and "Resolve the asset's construct-level target set." The S&E text is kept beside the new action.

Classes on CLDN18.2:

| Gate | Class | Count |
|---|---|---|
| strategy.indication | BASKET | 11 |
| strategy.indication | NAMES_REQUESTED_SITE | 4 |
| strategy.indication | AMBIGUOUS_NAME_ALL_BROADER | 2 |
| strategy.indication | BROADER_THAN_REQUESTED | 2 |
| strategy.indication | DIFFERENT_DISEASE | 2 |
| strategy.indication | UNREADABLE | 2 |
| strategy.indication | READS_AS_REQUESTED | 1 |
| modality.required | NO_RECORD | 5 |
| modality.required | SOURCE_MODALITY_UNREADABLE | 3 |
| target.expression | SOURCE_NAMES_OTHER_TARGETS | 3 |
| target.expression | NO_RECORD | 1 |
| evidence.phase_constraint | NO_RECORD | 2 |

Against U1 revision 1: AZD5863 ("Gastric Cancer") moved from NAMES_REQUESTED_SITE to AMBIGUOUS_NAME_ALL_BROADER
(the authority reads the name as two concepts, both broader; review J1), and DA-3501 ("Gastric (Stomach) Cancer")
moved to BROADER_THAN_REQUESTED, with the index artefact it rests on stated (review D7).

Against U1 revision 2 (review 2, N3): revision 2 rewrote the British "oesophag" inside "Gastroesophageal" and
dropped every multi-word site, so spelled-out junction names were unreadable. Revision 3 fixes both. AZD5863
("Gastro-esophageal Junction Cancer") moved from AMBIGUOUS_NAME_ALL_BROADER to NAMES_REQUESTED_SITE, and IBI343
("Unresectable or Metastatic Gastric or Gastroesophageal Junction Adenocarcinoma") to READS_AS_REQUESTED: the name
reads as Gastroesophageal Junction Adenocarcinoma once "unresectable" is removed and the coordination expanded, a
clean-up the gate does not apply. CMG901, AMG 910 and SYSA1801 keep their class with the junction now named. The
memo's single-gate line lists every record phrase, so SOT102 (DIFFERENT_DISEASE) and Givastomig are no longer
hidden behind "3 more" (N13).

Examples, copied from `after/unknown_actions.csv`:
- RC118: "'Advanced Solid Tumor' names no disease or site (a basket) (and 3 other name(s) on record). What would
  pass the gate: a cited source naming gastric adenocarcinoma or gastroesophageal junction adenocarcinoma (or a
  subtype) for this program; enter it with `assert --field indication`, the source URL and a verbatim quote. The
  gate never fails on this evidence, so a program for another indication stays open."
- DA-3501: "'Gastric (Stomach) Cancer' reads as Gastric Carcinoma (NCIt) ('Childhood Gastric Carcinoma' read as
  'Gastric Carcinoma' (the record states no population)), broader than requested (and 2 other name(s) on record)."
- [18F]F-RESCA-3A12: "'Igestive System Neoplasms' is not a name the NCIt authority can read". The source cell is
  spelled "Igestive"; the action quotes the record as written.

## U1-2: no landscape words in logic

`grep -i` for program, company, disease and target words of the test landscapes in `diagnostics.py` and
`indication_relations.py`: matches only in docstrings or comments that explain a rule with an example. Classes come
from the frozen NCIt authority (via `bve.dealscreen.indications`), the target and modality readers, and the
buyer's requirement. The site rule reads sites from NCIt's own names ("<histology> of the <site>"), not from a word
list.

## U1-3: no change to science or transactions

| Check | Result |
|---|---|
| CLDN18.2: disposition, rank, decisions, machine recommendation, transaction, transaction rank vs `baseline/screening_R1.json` | 0 of 62 programs changed |
| Cross-version (synthetic 200, FcRn v1, FcRn v2, C5 held-out) vs the R1 science dump (disposition, rank, decisions, machine recommendation, tier) | 0 of 312 programs changed |
| Equivalence harness (cycle 4), 4 workspaces | byte-identical, fast path, 4 of 4 |

## U1-4: held-out tests

`tests/dealscreen/test_unknown_actions.py`: 250 cases, with fictional or other-therapy-area strings. Revision 2
added the first review's probes (D1–D13, J1–J3) as tests; revision 3 adds the second review's (N1–N13) and
held-out variants of each (another site's stage concept, other non-site words, other placeholders); revision 4 adds
the third review's (D1–D9); revision 5 adds the fourth review's (D1–D4, D8, D9). DealScreen suite with U1:
1,327 passed (1,300 at R1 revision 10 alone).

## U1-5: surfaces

- Workbook, Diligence sheet: 38 GATE_UNKNOWN rows. "Next action" shows the DealScreen action followed by the S&E
  text in brackets; "Confidence limitations" starts with "Record class ... (DealScreen; describes the record, which
  can be wrong)".
- Workbook, Screening sheet: a last column, "Open gates: what the record holds", per open gate and, for a gate with
  several names, each name's class.
- Memo: under the unresolved queue, the programs with a single open gate, grouped by gate and by what the record
  holds, with the deciding fact stated once per gate; every record phrase is shown. Memo length 1,835 words (R1
  revision 8: 1,708).
- CLI: `screen` prints a warning when a requested indication is not one NCIt concept. It suggests a restatement
  only when one reading's label is the request itself; otherwise it lists the readings for the buyer to choose.

## U1-6: per UNRESOLVED program against the frozen reference

15 reference-IN programs are UNRESOLVED (the criterion text said 16; LCB02A, the 16th reference-IN program that is
not ELIGIBLE, is EXCLUDED by a modality FAIL and is outside U1's reach).

| Rank | Program | Reference call | Open gates: class | Indication record (summary) |
|---|---|---|---|---|
| 1 | IBI343 | IN | required SOURCE_MODALITY_UNREADABLE; indication READS_AS_REQUESTED | a name that reads as requested only after a clean-up the gate does not apply |
| 2 | Rilvegostomig (AZD2936) | OUT | expression SOURCE_NAMES_OTHER_TARGETS |  |
| 3 | RC118 | IN | indication BASKET | a basket naming no disease or site |
| 4 | CMG901 | IN | indication NAMES_REQUESTED_SITE | names a requested site in a name NCIt cannot read |
| 5 | LB4330 | OUT | required NO_RECORD; indication BASKET | a basket naming no disease or site |
| 6 | VBC108 | IN | indication BASKET | a basket naming no disease or site |
| 7 | ANO31905 | UNRESOLVED | required NO_RECORD; indication DIFFERENT_DISEASE | a disease neither requested nor a subtype of one |
| 8 | AZD5863 | IN | indication NAMES_REQUESTED_SITE | names a requested site in a name NCIt cannot read |
| 9 | Givastomig | IN | indication AMBIGUOUS_NAME_ALL_BROADER | a name whose NCIt readings are all broader than requested |
| 10 | TAC01-CLDN18.2 | OUT | required NO_RECORD; indication BASKET | a basket naming no disease or site |
| 11 | Volrustomig | OUT | indication AMBIGUOUS_NAME_ALL_BROADER; expression SOURCE_NAMES_OTHER_TARGETS | a name whose NCIt readings are all broader than requested |
| 12 | SOT102 | IN | indication DIFFERENT_DISEASE | a disease neither requested nor a subtype of one |
| 13 | RC148 | OUT | indication BASKET; expression SOURCE_NAMES_OTHER_TARGETS | a basket naming no disease or site |
| 14 | DA-3501 | IN | indication BROADER_THAN_REQUESTED | a disease broader than requested |
| 15 | SG1906 | IN | indication BASKET | a basket naming no disease or site |
| 16 | [18F]F-RESCA-3A12 | OUT | phase_constraint NO_RECORD; required SOURCE_MODALITY_UNREADABLE; indication UNREADABLE | no name the NCIt authority reads |
| 17 | EO-3021 | IN | indication BROADER_THAN_REQUESTED | a disease broader than requested |
| 18 | SYSA1801 | IN | indication NAMES_REQUESTED_SITE | names a requested site in a name NCIt cannot read |
| 19 | TQB2103 | IN | indication BASKET | a basket naming no disease or site |
| 20 | AK132 | IN | indication BASKET | a basket naming no disease or site |
| 21 | AMG 910 | IN | indication NAMES_REQUESTED_SITE | names a requested site in a name NCIt cannot read |
| 22 | Bio-008 | UNRESOLVED | required NO_RECORD; indication BASKET; expression NO_RECORD | a basket naming no disease or site |
| 23 | DR30303 | UNRESOLVED | required NO_RECORD; indication UNREADABLE | no name the NCIt authority reads |
| 24 | Q-1802 | IN | indication BASKET | a basket naming no disease or site |
| 25 | 89Zr-NY005 | OUT | phase_constraint NO_RECORD; required SOURCE_MODALITY_UNREADABLE; indication BASKET | a basket naming no disease or site |

- No reference-IN program gets an action that calls a gastric or GEJ name a different disease (0 of 15).
- RC118 and the other 10 basket records get a basket action naming the requested indications (11 of 11).
- The three PD-1 combination-partner rows get a target action naming the other targets. "PD-1" is not read by
  the target authority, and the action now says so (review J4): Rilvegostomig "The record names TIGIT; none is
  CLDN18 (Claudin 18.2). It also names 'PD-1', which the target authority does not read; it is not written as
  CLDN18 or its name"; Volrustomig the same with CTLA-4 (CTLA4); RC148 "The record names 'PD-1', which the target
  authority does not read; it is not written as CLDN18 or its name".
- Points away, reported: SOT102 (reference IN). Its record names only "Pancreatic Cancer", which the authority
  reads as pancreatic carcinoma: DIFFERENT_DISEASE. The action is true to the record; the reference calls it IN from
  evidence outside it. An analyst who trusts the action without reading on would deprioritise an IN program.

## U1-7: adversarial review

`REVIEW.md` (AI, separate context) reviewed U1 revision 1: one critical defect (D1, an unresolvable request made
every record a "different disease"), two high (D2 non-site "site words", D3 the acronym clean-up), and lower ones.
`REVIEW_RESPONSE.md` gives the fix and the evidence for each. `REVIEW2.md` re-reviewed revision 2 and found U1-7
not met (N1–N13, two high). `REVIEW2_RESPONSE.md` gives revision 3's fix for each. `REVIEW3.md` reviewed revision 3: U1-1 to U1-6 met, U1-7
not met (9 definite defects, the worst medium-high). `REVIEW3_RESPONSE.md` gives revision 4's fix for each. `REVIEW4.md`
reviewed revision 4: U1-1 to U1-6 met, U1-7 not met (2 medium, 7 lower). `REVIEW4_RESPONSE.md` gives revision 5's
fix for each it closes. U1 revision 5 has not been reviewed, so U1-7 is not claimed.

## Limits

- The diagnostics describe the record. A wrong vendor cell gives a true description of a wrong record (IBI343's
  modality cell "Imaging agent").
- Excluded programs get no diagnostic, even when one of their gates is UNKNOWN (17 decisions on 16 programs).
- Some requested-site spellings stay UNREADABLE ("Oesophagogastric adenocarcinoma"): an understatement, not a
  wrong class.
- Site words are read only where NCIt has a by-site "<site> Neoplasm" node. A few real sites named only by a
  disorder node (for example "biliary" on its own) are no longer reported as sites: an understatement.
- RC118's recall miss is not fixed: the supplied documents name gastric cancer, but U1 does not read documents.
