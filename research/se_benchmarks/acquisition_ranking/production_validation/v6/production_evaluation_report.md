# V6 Production Holdout Evaluation Report

## Frozen decision

**PASS — RELEASE ELIGIBLE.** Every frozen numeric threshold and mandatory semantic gate passed. Ranking is therefore **UNBLOCKED for V6** under `acquisition_ranking_production_validation_v6`.

## Independent evaluator and custody attestation

- Evaluation was performed by a fresh independent V6 evaluator from the sealed V6 manifest, custody report, and production validation specification.
- V5 was not rescored and no V5 hidden artifact was accessed.
- V6 custody records attest 36 wholly new queries, 216 wholly new evidence records, and wholly new hidden judgments, with no reuse of V5 queries, evidence, predictions, labels, rubrics, or hidden artifacts.
- The semantic evaluator/specification and INCLUDE/UNKNOWN/EXCLUDE routing semantics were frozen before V6 construction and inference.
- Package state and holdout status were `SEALED`; predictions and this report were absent before preflight.
- Frozen coverage was adequate: 36 queries, 6 buyers, 9 targets, 6 modalities, and 9 evidence profiles.
- Permitted inputs were mode `0444`; all seven hidden artifacts were mode `000` before evaluation and were restored to mode `000` immediately after the single scoring execution.
- All hidden unlock paths in the manifest were absolute. Only those seven V6 paths were unlocked for scoring.
- `missing_or_conflicting_gate` and legitimate gate explanations were treated as expressly permitted fields, not leakage. Gate leakage was evaluated solely as a semantic route-partition violation.

## Frozen integrity evidence

| Artifact | SHA-256 | Result |
|---|---|---|
| Source archive | `fa1a9dcad64a46f76a9faa0fd89bbe5eab12f5ec32b019528d7970c228e98ba3` | Match |
| Production specification | `de1867d345f8dca209c60cbaa59b9c9ba229c2f6b5e7248ef84fa94c142f8fcb` | Match |
| Bundled scoring specification | `de1867d345f8dca209c60cbaa59b9c9ba229c2f6b5e7248ef84fa94c142f8fcb` | Match |
| Evaluator manifest | `88b17a784efd95b155a3a5e30e1417c49ad966b767feee27017b44924db044fd` | Match |
| Holdout bundle | `2ce28068566dda8db55379a061fe0bde56bf46c443d868dc1c175e84d8f15786` | Match |
| Predictions | `f8d618025595ce76130970fa32a83d85eba9f54c57296b9929992a415b86dfa1` | Sealed mode `0444` |

The bundle contained the exact frozen 14-artifact inventory. Bundle member hashes and modes matched the inventory; filesystem modes matched the sealed contract. The source archive is anchored to frozen base commit `7695cd21e6876070f678c3f166573ce9b2ca2427` and is not a byte-identical `git archive` of that commit: an independent extracted-tree comparison found exactly two modified production files (`src/bve/se/evaluation/ranking_holdout.py` and `src/bve/se/ranking/acquisition.py`) plus the new frozen adapter `src/bve/se/evaluation/production_inference.py`. Those files implement the frozen UNKNOWN queue fields, semantic route-partition evaluation, and the manifest-declared inference entry point. The complete resulting source package is the immutable archive identified by the manifest SHA-256 above; inference ran only from its matching extraction.

## Execution attestations

### Exact preflight

- Executions: 1
- Exit status: `0`
- Stdout: `V6_INTEGRITY_PREFLIGHT_PASS`
- Stderr: empty
- Contract: PASS

### Exact inference

- Executions: 1; no retry
- Exit status: `0`
- Stdout: `PRODUCTION_INFERENCE_COMPLETE queries=36 output=/tmp/se_production_holdout_20260711_v6/predictions.jsonl`
- Stderr: empty
- Contract: PASS

### Prediction structural validation

- 36 unique query predictions matched the 36 frozen query IDs.
- All 216 candidates were routed exactly once: 108 INCLUDE-ranked, 72 UNKNOWN diligence-only, and 36 EXCLUDE-only.
- Ranked, diligence, and exclusion partitions were pairwise disjoint and exhaustive for every query.
- UNKNOWN assets appeared exactly once only in `diligence_queue`; every entry populated `asset_id`, `missing_or_conflicting_gate`, `supporting_evidence`, and `specific_diligence_question`.
- No duplicate or crossed route was present. Serialized and top-level routes agreed.
- Result: PASS

### Exact scoring

- Executions: 1; no retry
- Exit status: `0`
- Stderr: empty
- Scorer status: `PASS`
- Release eligible: `true`
- Failures: none
- Hidden artifacts were immediately relocked to mode `000` after scoring.

## Frozen scoring results

| Gate | Result | Frozen requirement | Status |
|---|---:|---:|---|
| Top-k | 5 | 5 | PASS |
| Top-k shortlist recall | 1.0000 | >= 0.8000 | PASS |
| NDCG@k | 1.0000 | >= 0.7500 | PASS |
| Citation completeness | 1.0000 | >= 0.9500 | PASS |
| Rationale quality | 0.9000 | >= 0.8000 | PASS |
| Diligence-question usefulness | 0.9000 | >= 0.8000 | PASS |
| Zero gate leakage | true | required | PASS |
| Zero valuation leakage | true | required | PASS |
| UNKNOWN routing | exact, diligence-only | required | PASS |
| Minimum queries | 36 | 36 | PASS |
| Minimum buyers | 6 | 6 | PASS |
| Minimum targets | 9 | 9 | PASS |
| Minimum modalities | 6 | 6 | PASS |
| Minimum evidence profiles | 9 | 9 | PASS |

## Final release decision

The frozen overall rule is PASS if and only if every threshold and mandatory gate passes. All gates passed with no failures. V6 production-holdout evaluation is **PASS**, release eligibility is **true**, and ranking is **UNBLOCKED for V6**.
