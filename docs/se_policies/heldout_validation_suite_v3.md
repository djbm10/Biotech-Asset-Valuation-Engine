# HELDOUT_VALIDATION_SUITE v3 (H11–H15) — untouched suite for target-recognition generalization (preregistration)

**Status:** PREREGISTERED 2026-10-09. **Not run.** These targets have **not** been run through
the engine, looked up in the target resolver, or checked against the ontology.
**When to run:** only after TARGET_AFFIX_RECOGNITION v2 is adopted or reverted, at one declared
engine commit with no code change between runs. This suite is the **primary** judgment of
target-recognition generalization.

**H6–H10 status (operator, 2026-10-09).** HER2, PCSK9, IL-23, DLL3 and LRRK2 were looked up
in the resolver during the v1 diagnosis. H6–H10 are kept but marked **partially exposed** for
target-recognition validation. They are secondary end-to-end confirmation only.

**Excluded concepts:** CD19, BCMA, PDCD1, SLC6A2, HRH1, HTR2A, CHRM1, GPRC5D, KRAS, FcRn,
TL1A, CLDN18.2, HER2, PCSK9, IL-23, DLL3, LRRK2.

## 1. Queries

| Id | Query | `--therapeutic-area` |
|---|---|---|
| H11 | Find clinical-stage TIGIT antibodies for non-small cell lung cancer. | ONCOLOGY |
| H12 | Find clinical-stage C5 complement inhibitors for paroxysmal nocturnal hemoglobinuria. | *(omitted → UNSPECIFIED)* |
| H13 | Find clinical-stage anti-IL-17A antibodies for hidradenitis suppurativa. | AUTOIMMUNE |
| H14 | Find clinical-stage CD38-directed antibodies for multiple myeloma. | ONCOLOGY |
| H15 | Find clinical-stage ANGPTL3 inhibitors for homozygous familial hypercholesterolemia. | *(omitted → UNSPECIFIED)* |

H13 and H14 deliberately use the affixed forms (`anti-X`, `X-directed`).

**Run rules.**
- Live runs with `--allow-incomplete` and `--as-of` equal to the run date.
- Each run goes into `~/se_runs/heldout_h<N>_v3`, one at a time, in the operator's terminal.

## 2. Reference sets (any listed name, including trade names and codes)

- **H11:** tiragolumab; domvanalimab (AB154); vibostolimab (MK-7684); ociperlimab (BGB-A1217);
  belrestotug (EOS-448, GSK4428859); rilvegostomig (AZD2936).
- **H12:** eculizumab (Soliris); ravulizumab (Ultomiris); crovalimab (PiaSky, SKY59);
  pozelimab (REGN3918); zilucoplan (Zilbrysq); cemdisiran; tesidolumab (LFG316).
- **H13:** secukinumab (Cosentyx); ixekizumab (Taltz); bimekizumab (Bimzelx); izokibep;
  sonelokimab (M1095); netakimab; vunakizumab; xeligekimab.
- **H14:** daratumumab (Darzalex); isatuximab (Sarclisa); felzartamab (MOR202);
  mezagitamab (TAK-079); CID-103.
- **H15:** evinacumab (Evkeeza); zodasiran (ARO-ANG3); solbinsiran (LY3561774);
  vupanorsen; SHR-1918.

**Matching** follows v2: casefolded alphanumeric key on the canonical name or any alias.

## 3–4. Rubric, metrics and thresholds

These are identical to `heldout_validation_suite_v2.md` §3–§4:
- labels: RELEVANT, WRONG_TARGET, DUPLICATE, NON_ASSET, UNVERIFIABLE, committed before
  scoring;
- per query: P@20 ≥ 0.70, Recall@all ≥ 0.60, NON_ASSET ≤ 1, DUPLICATE ≤ 2, false human-PoC = 0;
- suite: PASS if at least 4/5 queries pass and there is no false human-PoC;
  PASS_WITH_LIMITATIONS if 3/5 pass; FAIL otherwise. A refused query fails.

**Additional target-recognition readout (reported, no threshold):** for each query, the
compiled target ids and whether they equal the intended target:

| Query | Intended target |
|---|---|
| H11 | TIGIT |
| H12 | C5 |
| H13 | IL17A |
| H14 | CD38 |
| H15 | ANGPTL3 |

A query that compiles to a different or additional target counts as a target-recognition
failure, even if the shortlist passes.
