# HELDOUT_VALIDATION_SUITE v2 (H6–H10) — untouched validation suite (preregistration)

**Status:** PREREGISTERED 2026-10-09. **Not run.** No engine output for these queries has been
generated or inspected.

**Standing rule.** H1–H5 (`heldout_validation_suite_v1.md`) failed at 0/5. They are now a
**frozen diagnostic and development set**. An improved H1–H5 score is never evidence of
generalization. Any behaviour change motivated by H1–H5, TAC01 or mint5 is judged on this
suite.

**Excluded concepts.** Nothing below overlaps with targets, indications or modality focus
already used: CD19, BCMA, PDCD1, SLC6A2, HRH1, HTR2A, CHRM1, GPRC5D, KRAS, FcRn, TL1A,
CLDN18.2.

## 1. Queries

| Id | Query | `--therapeutic-area` | Stresses |
|---|---|---|---|
| H6 | Find clinical-stage HER2-directed antibody-drug conjugates for breast cancer. | ONCOLOGY | common name ≠ gene symbol (ERBB2); ADC modality |
| H7 | Find clinical-stage PCSK9 inhibitors for hypercholesterolemia. | *(omitted → UNSPECIFIED)* | cardiovascular; antibody + siRNA + oral small molecule |
| H8 | Find clinical-stage IL-23 p19 antibodies for psoriasis. | AUTOIMMUNE | subunit-specific (IL23A, not IL12B) |
| H9 | Find clinical-stage DLL3-directed therapies for small cell lung cancer. | ONCOLOGY | bispecific T-cell engagers, ADC, CAR-T |
| H10 | Find clinical-stage LRRK2 inhibitors for Parkinson's disease. | *(omitted → UNSPECIFIED)* | neurology; kinase small molecules |

The therapeutic-area flag is omitted for H7 and H10 on purpose: the classified areas are only
ONCOLOGY and AUTOIMMUNE. This is the engine's documented behaviour for other areas, and it is
part of what the suite tests.

**Run rules.**
- Live runs with `--allow-incomplete` and `--as-of` equal to the run date.
- Each run goes into `~/se_runs/heldout_h<N>_v2`, one at a time, in the operator's terminal,
  at a single declared engine commit.
- No code change between the first and last run.

## 2. Reference sets (frozen now, from public knowledge; matched on any listed name or alias)

- **H6:** trastuzumab deruxtecan (DS-8201, Enhertu); trastuzumab emtansine (T-DM1, Kadcyla);
  disitamab vedotin (RC48); trastuzumab duocarmazine (SYD985); trastuzumab rezetecan
  (SHR-A1811); ARX788; DB-1303 (BNT323); zanidatamab zovodotin (ZW49).
- **H7:** evolocumab (Repatha); alirocumab (Praluent); inclisiran (Leqvio); lerodalcibep;
  enlicitide (MK-0616); recaticimab; tafolecimab; ongericimab; ebronucimab; AZD0780.
- **H8:** guselkumab (Tremfya); risankizumab (Skyrizi); tildrakizumab (Ilumya); mirikizumab
  (Omvoh); picankibart (IBI112).
- **H9:** tarlatamab (AMG 757, Imdelltra); obrixtamig (BI 764532); gocatamig (MK-6070,
  HPN328); ZL-1310; rovalpituzumab tesirine (Rova-T).
- **H10:** BIIB122 (DNL151); DNL201; NEU-411.

**Matching rule (amended from v1, declared before any run).** A reference counts as found if
**any listed name, including trade names**, equals the canonical name or an alias of a
shortlist row, by casefolded alphanumeric key. v1 counted a trade-name row ("Krazati") as not
found; v2 lists trade names explicitly instead.

## 3. Row rubric

The rubric is unchanged from v1 §3:

| Label | Meaning |
|---|---|
| RELEVANT | a real, distinct therapeutic product directed at the query target |
| WRONG_TARGET | a real product not directed at the target |
| DUPLICATE | another row is the same product |
| NON_ASSET | not a product |
| UNVERIFIABLE | cannot be judged from public information |

Labels are committed before scoring.

## 4. Metrics and thresholds

These are unchanged from v1 §4:

| Metric | Threshold |
|---|---|
| P@20 (UNVERIFIABLE excluded from the denominator) | ≥ 0.70 |
| Recall@all | ≥ 0.60 |
| Recall@20 | reported |
| NON_ASSET in the top 20 | ≤ 1 |
| DUPLICATE in the top 20 | ≤ 2 |
| False human-PoC in the top 20 | 0 |

**Suite verdict:**
- **PASS:** at least 4/5 queries pass and there is no false human-PoC.
- **PASS_WITH_LIMITATIONS:** 3/5 pass.
- **FAIL:** otherwise.

A refused query fails and is not re-phrased.

## 5. When to run

Only after the milestones motivated by H1–H5 are adopted or closed (target recognition, then
shortlist non-product/off-target), at a single frozen engine commit declared in this file
before the first run.
