# GUCY2C analyst-view cleanup (v2): development report

**Grade: DEVELOPMENT.** Every number is from replaying the sealed custody corpus of the
frozen pilot `gucy2c_oncology_v1`, scored against its already-disclosed AI-prepared
reference with the pilot scorer's own definitions. The change was designed after reading
those candidates. **This is not independent or out-of-sample validation.** The frozen
pilot, its sealed outputs, reference and score are unchanged.

Policy and frozen acceptance criteria: `docs/se_policies/gi_area_evidence_v1.md`, committed
at `15c6cf1` before implementation. It also records the results and one labelled post-hoc
amendment.

## Runs (identical sealed bytes: `~/se_runs/gucy2c_pilot_v1/run/custody`)

| Run | Code | Wall | Peak RSS |
|---|---|---:|---:|
| `after_final` (v1 end state) | `94fefff` | 2:09 | 2.47 GB |
| `gi_v1_preC10` (this change) | `94fefff` + G1/G2 | 2:00 | 2.42 GB |
| `gi_v1` (discarded) | `15c6cf1` + G1/G2 | 1:54 | 2.53 GB |

`gi_v1` shows that **the current HEAD cannot replay this corpus.** C10 removed `"STAR"`
from the main query text, and that text is the custody key. The main CT.gov query therefore
fails as a replay divergence, and every trial asset drops out (252 candidates). The change
was measured on the pre-C10 code instead, so both arms differ only by G1/G2. The shortlist
`Status:` line is renderer-only and does not affect these numbers.

## Diagnosis of the 19 irrelevant visible candidates

All 19 entered by one route: `DIRECT_APPROVED_NAME`, PubMed-only, 0 trials, 0 targets, and
no area fact. The cause: `PubMedEvidenceExtractor` emitted no area fact at all, and the
lexicon could not see constipation or IBS.

| Class | n | Candidates | Outcome |
|---|---:|---|---|
| Positive evidence of an unrelated (GI) indication | 8 | sennosides, rifaximin, Magnesium oxide, lactulose, bisacodyl, sodium picosulfate, senna, polyethylene glycol | 7 EXCLUDED (GI-only); **PEG stays**, because one cited abstract is oncology |
| Unrelated indication, not classifiable | 1 | efinaconazole (pharmacovigilance paper) | stays (no area evidence) |
| Reagent / nontherapeutic, only in GI papers | 4 | fluorescein, isothiocyanate, vehicle, creatinine | EXCLUDED as off-area. **The exclusion reason is the area, not "reagent"**: no offline authority classifies reagents |
| Reagent / nontherapeutic, in oncology papers or unclassified | 5 | water, ether, aniline, amino acids, dextran | stay: the evidence does not prove irrelevance |
| Incidental in an oncology paper, relevance unknown | 1 | hematoporphyrin | stays |
| Genuine GUCY2C oncology programme | 0 | – | – |

Per-candidate source trace: `trace_visible.py` (each document, title, and the areas its
title+abstract supports).

## Results

| Measure | after_final | gi_v1_preC10 |
|---|---:|---:|
| Candidates (all) | 279 | 279 |
| Analyst-visible (eligible + review) | 32 (0 + 32) | **21** (1 + 20) |
| Named in-scope recall, visible / all | 12/17 / 12/17 | 12/17 / 12/17 |
| Visible strict precision | 37.5% | **57.1%** |
| Confirmed irrelevant visible (the 19 above) | 19 | **8** |
| Negative-control hits visible | 0 | 0 (3 agonists EXCLUDED by agonist rule) |
| EXCLUDED | 26 | 37 (+11, each with a cited GI-only area fact) |
| LOW_SUPPORT | 221 | 221 |
| Visible with a stated target | 1 | 1 |
| Visible with a modality value | 24 | 18 |
| Visible with an authority modality | 18 | 10 |
| Visible with an area fact | 12 | 19 |
| Engine merges / scorer merges / splits | 2 / 0 / 1 (R-005) | 2 / 0 / 1 |
| Trial coverage overall, all ids / NCT only | 52% / 65% | 52% / 65% |
| ELIGIBLE | 0 | 1 (TAK-264, see below) |
| `human_poc_present` facts | 0 | 0 |

The modality and authority-modality counts fall only because laxatives left the view.
Several of the remaining 8 carry nonsense modalities read from document context: dextran
`T_CELL_ENGAGER`, aniline `ANTIBODY_DRUG_CONJUGATE`, ether `RNA_THERAPEUTIC`. That
document-level modality attribution is an open defect, not coverage.

**TAK-264 became ELIGIBLE.** Its CT.gov conditions say "carcinoma" and "malignancies", and
neither is an ONCOLOGY lexicon term, so its area was UNKNOWN. Its PubMed abstracts now
supply entailed ONCOLOGY facts. Every declared gate passes:
- confirmed GUCY2C target;
- authority action BINDING AGENT;
- area;
- stage.

This fails frozen criteria B4/B7 *as written*. It is adopted by a labelled post-hoc
amendment, because those criteria were meant to stop promotion without evidence. The
shortlist now shows `Status: COMPLETED, TERMINATED` beside it: every one of its trials has
ended.

Machine-checked criteria: `check_acceptance.py` → `results/acceptance_gi_v1_preC10.json`.

## C10 and follow-ups: bounded live diagnostic (2026-10-25)

`live_c10_followups.py`: 8 live searches on free endpoints, built exactly as
`bve-se-search` builds its live adapters. Total 41 s, 1.76 GB peak. Output is in
`~/se_runs/gucy2c_live_diag/live.json` (not committed: it holds live third-party records).

| Search | Records kept | Notes |
|---|---:|---|
| CT.gov, C10 main query | 25 | `query.intr` is built from the **admitted** alias set, so `STAR` was never sent to CT.gov, before or after C10 |
| CT.gov, pre-C10 string (with `STAR`) | 25 | identical request |
| PubMed, C10 main query | 4 of 50 fetched | E-utilities count **7,062** |
| PubMed, pre-C10 string | 1 of 50 fetched | E-utilities count **64,627**: `STAR` widens the search about 9×, and the newest-50 window fills with irrelevant papers |
| CT.gov follow-up PF-07062119 | 1 | emits only the lead (`PF-07062119`) |
| CT.gov follow-up XKDCT080 | 1 | emits only the lead |
| PubMed follow-up PF-07062119 | 4 | 36 raw mentions (pre-qualification; mostly ordinary words) |
| PubMed follow-up XKDCT080 | 0 | `NO_EVIDENCE_FOUND` |

The main CT.gov query proposed 7 follow-ups: IM96, LYL273, MLN0264, PF-07062119, TAK-164,
WD-01 and XKDCT080. All are real product codes, and none is an ordinary word.

What this establishes:
- C10 prevents shared-alias expansion where it can act, which is PubMed.
- On CT.gov, C10 is a no-op on the wire.
- Follow-up queries are well-formed, run without error, and emit only their lead on CT.gov.

What it does not establish:
- the end-to-end effect on a full live run;
- whether the 8 remaining irrelevant candidates, or new ones, appear under live PubMed
  ranking (newest-50 is a narrow, date-dependent window);
- anything about sources that are not configured.

## Unresolved

- 8 irrelevant candidates remain visible: water, ether, aniline, amino acids, dextran,
  efinaconazole, polyethylene glycol and hematoporphyrin. Removing them needs either a
  reagent or nontherapeutic authority, which ChEMBL `max_phase`/indication data could
  supply but is not in the offline snapshot, or asset-level rather than abstract-level
  area attribution.
- Document-level attribution: an abstract's areas and modality attach to every name in it.
- The ONCOLOGY lexicon misses `carcinoma`/`malignancies` (frozen list; a separate declared
  change).
- 11 of 12 recovered assets still have target UNKNOWN; R-005 is still split; R-013/R-016
  are still generic; R-012/R-014/R-017 are not acquired.
- `Phase:` shows the first trial record's stage, not the highest.
- The current HEAD cannot replay the pilot corpus (C10 changed the custody key). Any future
  GUCY2C measurement needs a new live acquisition.
