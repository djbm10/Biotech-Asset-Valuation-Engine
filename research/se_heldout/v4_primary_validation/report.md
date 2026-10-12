# Frozen primary validation: H16–H20 v4

**Overall suite decision: FAIL. 0/5 query-level PASS.**

All five observed outcomes are the frozen primary validation. Original interrupted H17/H18 runs are excluded. H6–H10 remain UNRUN. No query was rerun, rephrased, or modified, and no engine changes or diagnosis were made.

**Source coverage limitation:** H16/H18/H19 have `INCOMPLETE` status and exit code 0. ClinicalTrials.gov, PubMed and AACR report SUCCESS. Company pipeline/presentation, company press releases, ASCO, ASH, EHA and SEC EDGAR are NOT_CONFIGURED. All three are scored under the explicitly preregistered `--allow-incomplete`; missing source configuration is not a post hoc invalidation rule. H17/H20 refused at query compilation; source coverage and shortlist metrics are N/A.

## Frozen rules quoted before scoring

From v4, run rules:

> live runs with `--allow-incomplete` and `--as-of` set to the run date. Each run goes to `~/se_runs/heldout_h<N>_v4`, one at a time, in the operator's terminal. A refused query fails and is not re-phrased.

From v4, metrics and overall-suite rule:

> Metrics and thresholds  These are unchanged from v1–v3 §4: - per query: P@20 ≥ 0.70 (UNVERIFIABLE excluded from the denominator), Recall@all ≥ 0.60,   NON_ASSET ≤ 1, DUPLICATE ≤ 2, false human-PoC = 0 (v1 §4 definition); - suite: PASS if at least 4/5 pass and there is no false human-PoC; PASS_WITH_LIMITATIONS if 3/5   pass; FAIL otherwise.  **Target-recognition readout** (reported; a different or additional target counts as a failure): H16 LAG3, H17 IL4R, H18 GLP1R, H19 TACSTD2, H20 F11.

Inherited v1 false-human-PoC definition: “a top-20 row with `human_poc_present` whose cited sentence is not numerical human efficacy for that product”. v1 §4 defines Recall@all as reference found anywhere on the shortlist and Recall@20 as reference found in the top 20; Recall@20 has no threshold. v2 §4 and the preserved v1 refusal results set query-level FAIL for refusal and show shortlist metrics as undefined, not invented zeros.

## Committed label freeze and extraction

Labels and human-PoC judgments were committed at `eed63eb7dd5c3ea4387a2b9789c6d886229bbaf5` before any metric aggregation or reference matching. `blind_top20.json` preserves every emitted position/name/asset ID for H16/H18/H19. Full emitted entries, all shortlist canonical names/aliases, source manifests, frozen-rule copies, input hashes and refusal logs are preserved in this packet. The frozen engine display helper was used only to expose uncapped shortlist entries from saved result bytes; its top20 was verified to exactly match the emitted shortlist artifact. This was not a search run or replay. Deferred low-support and excluded assets are not promoted into the shortlist for Recall@all, matching the prior frozen scoring procedure.

Label relevance is the frozen target-directed therapeutic-product definition; no additional modality, agonism, or indication constraint was introduced. Avexitide targets GLP1R and thus is RELEVANT under that definition. Later brand rows for the same active product are DUPLICATE. The diagnostic PET tracer is NON_ASSET for therapeutic-product precision; unspecified rescue-medication categories are NON_ASSET. Detailed NK-construct duplicate rationale is frozen in `public_label_sources.md`.

## Results

| Query | Target recognition | P@20 | Recall@all | Recall@20 | NON_ASSET | DUPLICATE | False human-PoC | Source coverage / status | Query verdict |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| H16 | LAG3 (correct) | 0.500 | 1.000 | 0.833 | 0 | 0 | 0 | 3 SUCCESS / 6 NOT_CONFIGURED; INCOMPLETE | **FAIL** |
| H17 | REFUSED; IL4R not recognized | N/A | N/A | N/A | N/A | N/A | N/A | N/A; REFUSED | **FAIL** |
| H18 | GLP1R (correct) | 0.750 | 1.000 | 0.625 | 0 | 5 | 1 | 3 SUCCESS / 6 NOT_CONFIGURED; INCOMPLETE | **FAIL** |
| H19 | TACSTD2 (correct) | 0.400 | 0.400 | 0.400 | 3 | 2 | 1 | 3 SUCCESS / 6 NOT_CONFIGURED; INCOMPLETE | **FAIL** |
| H20 | REFUSED; F11 not recognized | N/A | N/A | N/A | N/A | N/A | N/A | N/A; REFUSED | **FAIL** |

## Threshold application and reference matches

- **H16: FAIL** — P@20>=0.70.
  P@20 numerator/denominator: 10/20; Recall@all: 6/6; Recall@20: 5/6. All-shortlist reference matches: relatlimab, fianlimab, favezelimab, ieramilimab, encelimab, tebotelimab. Top20 matches: relatlimab, fianlimab, favezelimab, ieramilimab, tebotelimab.
- **H17: FAIL** — query refused / no target recognition.
  Preserved observed refusal: `blocked: no biological target recognized in the query`. No shortlist exists and no synthetic shortlist was created.
- **H18: FAIL** — DUPLICATE<=2; false_human_poc=0.
  P@20 numerator/denominator: 15/20; Recall@all: 8/8; Recall@20: 5/8. All-shortlist reference matches: semaglutide, tirzepatide, liraglutide, orforglipron, survodutide, retatrutide, mazdutide, danuglipron. Top20 matches: semaglutide, tirzepatide, liraglutide, survodutide, retatrutide.
- **H19: FAIL** — P@20>=0.70; recall_all>=0.60; NON_ASSET<=1; false_human_poc=0.
  P@20 numerator/denominator: 8/20; Recall@all: 2/5; Recall@20: 2/5. All-shortlist reference matches: sacituzumab govitecan, sacituzumab tirumotecan. Top20 matches: sacituzumab govitecan, sacituzumab tirumotecan.
- **H20: FAIL** — query refused / no target recognition.
  Preserved observed refusal: `blocked: no biological target recognized in the query`. No shortlist exists and no synthetic shortlist was created.

## Human-PoC row audit

- H16 Relatlimab: supported numerical patient response rates in a cited combination-treatment passage; false count 0. Another cited passage is nonnumerical, but the row has a qualifying numerical efficacy citation.
- H18 Tirzepatide: false human-PoC. The cited numerical changes are human-myotube respiration in vitro, not human-patient efficacy. Survodutide has numerical liver-fat response proportions in patients and is supported.
- H19 Sacituzumab Tirumotecan: false human-PoC. Its cited passage describes an economic-model simulation, not numerical observed human efficacy.
- H17/H20: N/A; no emitted rows or human-PoC claims to score.

## Frozen overall decision

The overall decision follows the quoted suite rule and includes both refused queries as query-level FAIL. Source configuration is prominently reported and does not by itself invalidate a scored result. This packet records primary validation only; it does not diagnose failures, propose fixes, change code, or run the secondary H6–H10 suite.
