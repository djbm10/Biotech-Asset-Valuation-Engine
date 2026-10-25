# Gastrointestinal area evidence and PubMed area facts (v1)

Status: **DECLARED**, 2026-10-25, before any code change. Development work against the
already-disclosed GUCY2C pilot reference (`gucy2c_oncology_v1`); **not validation**.
Follows `gucy2c_pilot_remediation_v1.md`. Amends the frozen lexicon in `ta_gate_semantics.md`
by one area; every other rule there is unchanged.

## Diagnosis (dev replay `after_final`, 32 analyst-visible)

12 visible candidates are named reference assets, plus 1 second spelling of R-005 (a split,
already reported). The other 19 all share one route: `DIRECT_APPROVED_NAME` (a ChEMBL name),
**PubMed-only**, 0 trials, 0 targets, and **no `therapeutic_area` fact at all**.

| Class | Candidates | Source evidence |
|---|---|---|
| Positive evidence of an unrelated indication | sennosides, rifaximin, Magnesium oxide, lactulose, bisacodyl, sodium picosulfate, senna, polyethylene glycol, efinaconazole | constipation / IBS guidelines, reviews, cost studies; efinaconazole: pharmacovigilance paper |
| Laboratory reagents / nontherapeutic substances | water, vehicle, ether, amino acids, fluorescein, isothiocyanate, dextran, creatinine, aniline | rat IBS and DSS-colitis models (FITC-dextran, vehicle), TAK-164 catabolism study, nanosensitizer chemistry, a nephropathy case report |
| Incidental in an oncology paper, relevance unknown | hematoporphyrin | photosensitizer in a colorectal-cancer imaging-therapy paper |
| Genuine GUCY2C oncology programme | none of the 19 | – |

Root causes:

1. **`PubMedEvidenceExtractor` emits no area fact.** It records only `publication_relevance`.
   So every PubMed-only candidate's area is UNKNOWN by construction, and the area gate can
   never act on it however explicit the abstract is.
2. **The lexicon cannot see non-malignant GI disease.** It classifies ONCOLOGY and
   AUTOIMMUNE only, so "chronic idiopathic constipation" yields no area, and its absence is
   (correctly) not a negative.

No offline provenance exists for a nontherapeutic classification: the ontology snapshot
holds ChEMBL names with no phase, indication or reagent metadata (`WATER`, `ANILINE` are
bare `APPROVED_NAME` records). This change therefore does **not** classify reagents. Those
that appear only in GI-classified papers leave the view as off-area; the rest stay visible
as unknown. That residual is reported, not hidden.

## Changes

- **G1. One lexicon area, `GASTROINTESTINAL`: non-malignant digestive disease.** Terms
  (casefolded substring, as for the other areas): `constipation`, `irritable bowel`,
  `gastroparesis`, `functional dyspepsia`, `gastroesophageal reflux`, `fecal incontinence`,
  `faecal incontinence`, `functional gastrointestinal`. Gastrointestinal *cancers* remain
  ONCOLOGY, and Crohn's disease and ulcerative colitis remain AUTOIMMUNE. Deliberately excluded:
  - bare `colitis`, which is a model-induction term in DSS papers;
  - `diarrhea`/`nausea`, which are adverse events in oncology papers;
  - `bowel preparation`, which is a procedure, not a disease.

  Aliases: `GI`, `GASTROENTEROLOGY`.
- **G2. PubMed area facts.** `PubMedEvidenceExtractor` emits one `therapeutic_area` fact per
  area that the title + abstract supports. Each cites a span naming that area, by the same
  rule as `generic.py`. Document-level attribution applies, as it already does for every
  other source: an abstract's areas attach to every asset it names.

The area gate itself is unchanged: PASS when the union of observed areas meets the request,
and FAIL only when observed areas exist, are disjoint, and every requested area is
classified. A FAIL routes the candidate to EXCLUDED with that reason. The candidate is not
deleted, and a molecule with **any** oncology-classified evidence still PASSes.

Not changed:
- human-PoC rules (C9 still keys on the requested areas only);
- qualification routes, identity, targets, modality, ranking;
- every frozen experiment and sealed artifact.

## Acceptance criteria (frozen before implementation)

Measured by replaying the same sealed bytes (`~/se_runs/gucy2c_pilot_v1/run/custody`) with
`engine_problem_dev.yaml`, against `after_final`, with the same evaluator (`dev_evaluate.py`).

| | Criterion |
|---|---|
| B1 | Named in-scope recall unchanged: 12/17 visible and 12/17 all candidates. Every one of the 12 stays analyst-visible. |
| B2 | Negative-control hits visible: 0. The three agonists stay EXCLUDED with their `target_action_type` reason. |
| B3 | Visible non-reference candidates 19 → **≤ 9**. Every candidate leaving the view is EXCLUDED by `strategy.therapeutic_area` with a cited, entailed area fact, and none carries an ONCOLOGY area fact. |
| B4 | No visible candidate that has ONCOLOGY area evidence becomes EXCLUDED, and no reference asset changes route. |
| B5 | No new target assertion; stated targets correct/stated unchanged (1/1); modality values of the 12 unchanged. |
| B6 | Identity unchanged: total candidates 279, engine merges 2, scorer merges 0, splits 1. |
| B7 | ELIGIBLE stays 0, and no new `human_poc_present`. |
| B8 | Wall clock ≤ `after_final` + 20%; peak RSS ≤ 4.5 GB. |

Failing B1, B2, B4, B5, B6 or B7 rejects the change. A B3 miss is reported with the cause,
and the lexicon is not tuned further against this reference.
