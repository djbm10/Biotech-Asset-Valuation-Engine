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

## 6. Result — 2026-10-09, engine `40b7ec9`

**Order of work.** Blind labels were committed at `c0e1c67` before any scoring. The scorer is
`scripts/score_heldout_suite_v1.py` → `research/se_heldout/score_v1.json`. No code,
threshold, query, reference or label was changed.

**Deviation, disclosed.** The operator ran every query with `--as-of 2026-09-24`, not the run
date. It is not material to any verdict below.

| Query | P@20 | Recall@all | Recall@20 | NON_ASSET | DUP | False hPoC | Verdict |
|---|---|---|---|---|---|---|---|
| H1 GPRC5D | — | — | — | — | — | — | **FAIL**: refused, "no biological target recognized in the query" |
| H2 KRAS G12C | 0.053 (1/19) | 0.111 (1/9: elironrasib) | 0.0 | 11 | 0 | 0 | **FAIL**: P@20, recall and NON_ASSET |
| H3 FcRn | — | — | — | — | — | — | **FAIL**: refused, same reason |
| H4 TL1A | 0.15 (3/20) | 1.0 (3/3) | 1.0 | 10 | 0 | 0 | **FAIL**: P@20 and NON_ASSET |
| H5 Claudin 18.2 | — | — | — | — | — | — | **FAIL**: refused, same reason |

**Suite verdict: FAIL (0 of 5 queries pass).**

**Scoring notes:**
- **False human-PoC.** Two H2 top-20 rows carry `human_poc_present`: aficamten (ΔpVO₂ responder
  analysis) and Trimix (dose-stratified responders). Each cited sentence is numerical human
  efficacy for that same product, so neither is a false human-PoC under §4. Both rows are
  WRONG_TARGET or NON_ASSET by label.
- **H2 matching.** Rank #1, "Krazati", is adagrasib's trade name. §2 lists only "adagrasib"
  and the row carries no alias for it, so it counts as not found. Under the frozen matching
  rule it does not count toward recall.
- **H4.** All three references sit at #1–3. Every row below them is a reagent, solvent, ion
  or unrelated drug.

Diagnosis has not started. It follows only after this result is committed.

## 7. Status change (operator, 2026-10-09)

The 0/5 FAIL above is preserved permanently. **H1–H5 are no longer held out.** They are a
frozen diagnostic set, and improved H1–H5 scores are never evidence of generalization. The
untouched validation suite is now `heldout_validation_suite_v2.md` (H6–H10).
