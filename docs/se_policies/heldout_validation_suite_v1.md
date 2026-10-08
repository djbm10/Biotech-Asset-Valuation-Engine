# HELDOUT_VALIDATION_SUITE v1 — blind validation on questions the engine was not tuned on (preregistration)

**Status:** PREREGISTERED 2026-10-08. No run exists. Everything below is frozen before any
query is executed.
**Engine under test:** the commit at which this file is committed, with TAC01 and mint5
frozen. **No code change is permitted between the first and last held-out run.**

## 1. Queries

None of these targets, modalities or indications was used to design a rule. The targets
used by the identity milestones were PDCD1, SLC6A2, HRH1, HTR2A, CHRM1, CD19 and BCMA; all of
them are excluded.

| Id | Query | `--therapeutic-area` | What it stresses |
|---|---|---|---|
| H1 | Find clinical-stage GPRC5D-directed therapies for relapsed or refractory multiple myeloma. | ONCOLOGY | new antigen; bispecifics and CAR-T mixed |
| H2 | Find clinical-stage KRAS G12C inhibitors for non-small cell lung cancer. | ONCOLOGY | small molecules; mutation-specific target |
| H3 | Find clinical-stage FcRn-blocking antibodies for generalized myasthenia gravis. | AUTOIMMUNE | target named by protein, not gene (FCGRT); antibody modality |
| H4 | Find clinical-stage TL1A antibodies for ulcerative colitis. | AUTOIMMUNE | ligand target (TNFSF15); immunology |
| H5 | Find clinical-stage Claudin 18.2-directed therapies for gastric cancer. | ONCOLOGY | isoform-specific antigen (CLDN18.2); mixed modalities |

The as-of date is the run date. Runs are live (`--allow-incomplete`), each into
`~/se_runs/heldout_h<N>_v1`, run one at a time in the operator's terminal.

## 2. Reference sets (frozen now, from public knowledge; matched on any listed name)

- **H1:** talquetamab; forimtamig (RG6234); arlocabtagene autoleucel (BMS-986393, CC-95266);
  MCARH109; OriCAR-017.
- **H2:** sotorasib; adagrasib; divarasib; olomorasib (LY3537982); garsorasib (D-1553);
  fulzerasib (GFH925); glecirasib (JAB-21822); opnurasib (JDQ443); elironrasib (RMC-6291).
- **H3:** efgartigimod alfa; rozanolixizumab; nipocalimab; batoclimab; IMVT-1402.
- **H4:** tulisokibart (MK-7240, PRA023); duvakitug (TEV-48574); afimkibart (RVT-3101,
  RG6631, PF-06480605).
- **H5:** zolbetuximab; satricabtagene autoleucel (CT041); osemitamab (TST001); AZD0901
  (CMG901); IBI343; ASKB589.

A reference product counts as **found** if any listed name equals the canonical name or an
alias of a shortlist row (casefolded alphanumeric key).

## 3. Row rubric (applied to each top-20 row before metrics are computed)

| Label | Meaning |
|---|---|
| RELEVANT | a real, distinct therapeutic product directed at the query target |
| WRONG_TARGET | a real product not directed at the target, including background or comparator agents |
| DUPLICATE | another row is the same product |
| NON_ASSET | not a product (word, class, procedure, regimen, field label) |
| UNVERIFIABLE | cannot be judged from public information |

## 4. Metrics and pass thresholds (per query)

| Metric | Threshold |
|---|---|
| **P@20**: RELEVANT / labelled rows in the top 20 (UNVERIFIABLE excluded from the denominator) | ≥ 0.70 |
| **Recall@all**: reference found anywhere on the shortlist | ≥ 0.60 |
| **Recall@20**: reference found in the top 20 | reported, no threshold |
| **NON_ASSET** in the top 20 | ≤ 1 |
| **DUPLICATE** in the top 20 | ≤ 2 |
| **False human-PoC**: a top-20 row with `human_poc_present` whose cited sentence is not numerical human efficacy for that product | 0 |

**Suite verdict:**
- **PASS** if at least 4 of the 5 queries pass every threshold and no query has a false
  human-PoC row.
- **PASS_WITH_LIMITATIONS** if 3 of 5 pass.
- **FAIL** otherwise.

A query the compiler refuses (for example a target it cannot resolve) counts as a failed
query, with the refusal reason recorded. It is not re-phrased.

## 5. Procedure

1. Commit this file. Record the engine commit.
2. The operator runs H1–H5.
3. The rows are labelled per §3, blind to which rules produced them. Labels and the scorer
   output are committed before any diagnosis.
4. Only then are failures diagnosed. Any fix is preregistered on its own, then validated on
   the held-out runs it was **not** derived from where possible, and on frozen TAC01/mint5
   for regression only.
