# V4 Holdout Evaluation Report

## Session

- Evaluator: independent V4 holdout evaluator (Codex)
- Session date: 2026-07-11, America/New_York
- Frozen commit: `adfc9bdb9b10532211fc1731c2c7fb4b66438824` — verified
- Frozen worktree: `/tmp/se_dev_frozen_adfc9bd` — exists, detached, exact HEAD, clean
- Worktree artifact check: no modified, untracked, ignored, or cache-directory entries
- Post-preflight/inference note: Python generated ignored `__pycache__` runtime files in the
  frozen worktree; these were absent at initial integrity verification and were not modified or
  removed after execution.
- V3, synthetic adversarial scenarios, and other benchmarks: not run

## Package integrity

- Manifest: `/tmp/se_holdout_custodian_20260711_v4/evaluator_manifest.md`
- Manifest SHA-256: `d184618f75f64183eddea53b9b665169b548ac1faa5545586ad005b4d09be8ac` — verified
- Source archive: `/tmp/se_dev_source_adfc9bd.tar`
- Source archive SHA-256: `ef9e6cac94fd5c1f936f622bbca25a1efce50943be50add31c658ca31eaddbf6` — verified
- Final bundle: `/tmp/se_holdout_custodian_20260711_v4.tar`
- Authoritative bundle SHA-256: `cddee27fce6712d08a32bbb03f47e705ae8135c2106d7afddbd148f8a89cc1ea` — verified

Verified artifact hashes:

| Artifact | SHA-256 | Result |
|---|---|---|
| problem.yaml | `704452cbafd635fd32acd5c448f0ad6afb5f28bb02b1b5906934479bb741bf98` | PASS |
| holdout_data.jsonl | `39cd12b2cfc3e5db2c4722d1ac82ace92f585c7d1857df22cce172b1264a458d` | PASS |
| holdout_labels.jsonl | `0350c21e46686283942afab5ba6fc1bec13917702f654649d50e060334b38372` | PASS |
| label_digest.txt | `e35767780a222a50879adea539be0421ceec03c44b2de9f0adc547ad97f01fba` | PASS |
| acceptance_and_scoring.md | `503a0246964d6658823fb889a3f11a93ae6a45f583a0085755c7f11cbc903e83` | PASS |
| construction_and_adjudication.md | `0149871dc1d75ef9331d49b95ac76ae21513e59c880cfe3901634e428f331806` | PASS |
| label_adjudication_notes.jsonl | `a3dd7aa9cce7a9387c90e0a773bc4199b9f2f1fb813611d9f0e1cf7ae8c84a6e` | PASS |

The bundle contains only the seven manifest artifacts. Expected sealed composition is 10 INCLUDE,
10 EXCLUDE, and 10 UNKNOWN. The unlabeled data parsed as exactly 30 unique case IDs with no
duplicates and fields only `case_id`, `target`, `modality`, `required_buyer_capability`,
`buyer_capabilities`, and `source_text`. No prediction artifact existed before inference.

Labels and adjudication notes were mode `000` before inference and inside the archive. They were
not accessed during preflight or inference. Evaluator-only access was restored to mode `0444` only
after prediction sealing.

## Validation-only preflight

Command, run from `/tmp/se_dev_frozen_adfc9bd`:

```text
PYTHONPATH=src python -m bve.cli.se_holdout_evaluate --problem /tmp/se_holdout_custodian_20260711_v4/problem.yaml --holdout-data /tmp/se_holdout_custodian_20260711_v4/holdout_data.jsonl --validate-only
```

- Exit status: `0`
- Result: `validation_status: PASS`
- Validated cases: `30`
- Prediction artifact created: no
- stdout: `{"problem_id":"se_acquisition_triage_v4","validation_status":"PASS","case_count":30}`
- stderr: Matplotlib cache warning; no evaluation failure

## Single-shot inference

- Exact command:

```text
PYTHONPATH=src python -m bve.cli.se_holdout_evaluate --problem /tmp/se_holdout_custodian_20260711_v4/problem.yaml --holdout-data /tmp/se_holdout_custodian_20260711_v4/holdout_data.jsonl --output /tmp/se_holdout_custodian_20260711_v4/predictions.json
```

- Working directory: `/tmp/se_dev_frozen_adfc9bd`
- Python: `3.12.3`
- Dependencies: Pydantic `2.12.5`; PyYAML `6.0.1`; pytest `9.0.2`; NumPy `2.2.0`; SciPy `1.17.0`; Ruff `0.15.8`
- Relevant environment: `PYTHONPATH=src`; no `MPLCONFIGDIR`; standard `PATH`
- Start: `2026-07-11T15:17:59-04:00`
- Completion observed: `2026-07-11T15:18:02-04:00`
- Exit status: `0`
- stdout: empty
- stderr: Matplotlib cache warning only
- Inference runs: exactly one

## Prediction sealing and contract validation

- Raw artifact: `/tmp/se_holdout_custodian_20260711_v4/predictions.json`
- Raw size: `40557` bytes; mode `0444`; SHA-256 `de094db4058e4e82c4d610971bce5942a0bdd84b9dbc3c5da88ea62577ce8cb3`
- Raw modification time: `2026-07-11 15:18:02.517829349 -0400`
- Sealed copy: `/tmp/se_holdout_custodian_20260711_v4/predictions.sealed.json`
- Sealed size: `40557` bytes; mode `0444`; SHA-256 `de094db4058e4e82c4d610971bce5942a0bdd84b9dbc3c5da88ea62577ce8cb3`
- Sealed copy: byte-for-byte identical — PASS
- Expected / produced: `30 / 30`
- Missing IDs: none
- Extra IDs: none
- Duplicate IDs: none
- Malformed records: none
- Invalid dispositions: none
- Missing overall reasons: none
- Missing gate detail fields: none
- Invalid gate statuses: none; all statuses were in `PASS`, `FAIL`, `UNKNOWN`
- Prediction counts: INCLUDE `11`, EXCLUDE `10`, UNKNOWN `9`

## Case-level reconciliation

Gate statuses are shown as `gate=status`.

| case_id | prediction | true label | result | gate statuses |
|---|---|---|---|---|
| v4-a4q9s2 | EXCLUDE | EXCLUDE | correct | target_match=PASS; modality_match=PASS; buyer_capability=FAIL; evidence_provenance=PASS; evidence_threshold=PASS |
| v4-b1x7f4 | INCLUDE | INCLUDE | correct | target_match=PASS; modality_match=PASS; evidence_provenance=PASS; evidence_threshold=PASS |
| v4-b5v9j3 | UNKNOWN | UNKNOWN | correct | target_match=PASS; modality_match=UNKNOWN; evidence_provenance=PASS; evidence_threshold=PASS |
| v4-c3w7p5 | UNKNOWN | UNKNOWN | correct | target_match=PASS; modality_match=UNKNOWN; evidence_provenance=UNKNOWN; evidence_threshold=UNKNOWN |
| v4-c9y3p7 | INCLUDE | INCLUDE | correct | target_match=PASS; modality_match=PASS; evidence_provenance=PASS; evidence_threshold=PASS |
| v4-d4n9q2 | INCLUDE | INCLUDE | correct | target_match=PASS; modality_match=PASS; evidence_provenance=PASS; evidence_threshold=PASS |
| v4-e3p9r5 | EXCLUDE | EXCLUDE | correct | target_match=PASS; modality_match=PASS; evidence_provenance=FAIL; evidence_threshold=FAIL |
| v4-f2c8l6 | UNKNOWN | UNKNOWN | correct | target_match=PASS; modality_match=PASS; buyer_capability=UNKNOWN; evidence_provenance=PASS; evidence_threshold=PASS |
| v4-f7u1c9 | INCLUDE | INCLUDE | correct | target_match=PASS; modality_match=PASS; buyer_capability=PASS; evidence_provenance=PASS; evidence_threshold=PASS |
| v4-g4d8m2 | EXCLUDE | EXCLUDE | correct | target_match=PASS; modality_match=FAIL; evidence_provenance=PASS; evidence_threshold=PASS |
| v4-h8s3v6 | INCLUDE | INCLUDE | correct | target_match=PASS; modality_match=PASS; evidence_provenance=PASS; evidence_threshold=PASS |
| v4-i1m7s4 | INCLUDE | UNKNOWN | incorrect | target_match=PASS; modality_match=PASS; evidence_provenance=PASS; evidence_threshold=PASS |
| v4-j8v3b6 | EXCLUDE | EXCLUDE | correct | target_match=PASS; modality_match=PASS; evidence_provenance=FAIL; evidence_threshold=FAIL |
| v4-k2r8m5 | INCLUDE | INCLUDE | correct | target_match=PASS; modality_match=PASS; evidence_provenance=PASS; evidence_threshold=PASS |
| v4-l7t1z9 | EXCLUDE | EXCLUDE | correct | target_match=PASS; modality_match=PASS; evidence_provenance=FAIL; evidence_threshold=FAIL |
| v4-m6j2t8 | INCLUDE | INCLUDE | correct | target_match=PASS; modality_match=PASS; evidence_provenance=PASS; evidence_threshold=PASS |
| v4-n1f7x4 | EXCLUDE | EXCLUDE | correct | target_match=PASS; modality_match=PASS; evidence_provenance=FAIL; evidence_threshold=FAIL |
| v4-o6q2d8 | UNKNOWN | UNKNOWN | correct | target_match=PASS; modality_match=UNKNOWN; evidence_provenance=UNKNOWN; evidence_threshold=UNKNOWN |
| v4-p7c1w9 | INCLUDE | INCLUDE | correct | target_match=PASS; modality_match=PASS; evidence_provenance=PASS; evidence_threshold=PASS |
| v4-q3a9l5 | INCLUDE | INCLUDE | correct | target_match=PASS; modality_match=PASS; evidence_provenance=PASS; evidence_threshold=PASS |
| v4-r4e8n2 | INCLUDE | INCLUDE | correct | target_match=PASS; modality_match=PASS; buyer_capability=PASS; evidence_provenance=PASS; evidence_threshold=PASS |
| v4-r9n4e1 | UNKNOWN | UNKNOWN | correct | target_match=PASS; modality_match=PASS; evidence_provenance=UNKNOWN; evidence_threshold=UNKNOWN |
| v4-s6c2h8 | EXCLUDE | EXCLUDE | correct | target_match=PASS; modality_match=PASS; evidence_provenance=FAIL; evidence_threshold=FAIL |
| v4-t2g8k5 | EXCLUDE | EXCLUDE | correct | target_match=FAIL; modality_match=PASS; evidence_provenance=PASS; evidence_threshold=PASS |
| v4-u4k9w2 | UNKNOWN | UNKNOWN | correct | target_match=PASS; modality_match=PASS; evidence_provenance=UNKNOWN; evidence_threshold=UNKNOWN |
| v4-v9b3q6 | EXCLUDE | EXCLUDE | correct | target_match=PASS; modality_match=PASS; evidence_provenance=FAIL; evidence_threshold=FAIL |
| v4-w7m1d9 | EXCLUDE | EXCLUDE | correct | target_match=PASS; modality_match=FAIL; evidence_provenance=PASS; evidence_threshold=PASS |
| v4-x2n8c5 | UNKNOWN | UNKNOWN | correct | target_match=UNKNOWN; modality_match=PASS; evidence_provenance=PASS; evidence_threshold=UNKNOWN |
| v4-y8r3a6 | UNKNOWN | UNKNOWN | correct | target_match=UNKNOWN; modality_match=UNKNOWN; evidence_provenance=UNKNOWN; evidence_threshold=UNKNOWN |
| v4-z7h1f9 | UNKNOWN | UNKNOWN | correct | target_match=PASS; modality_match=PASS; evidence_provenance=PASS; evidence_threshold=UNKNOWN |

## Sealed metrics and acceptance criteria

| Criterion | Result | Threshold | PASS/FAIL |
|---|---:|---:|---|
| Exact accuracy | 0.966667 (29/30) | >= 0.750 | PASS |
| INCLUDE recall | 1.000000 (10/10) | >= 0.800 | PASS |
| EXCLUDE recall | 1.000000 (10/10) | >= 0.800 | PASS |
| EXCLUDE precision | 1.000000 (10/10) | >= 0.750 | PASS |
| UNKNOWN recall | 0.900000 (9/10) | >= 0.700 | PASS |
| Macro-F1 | 0.966583 | >= 0.700 | PASS |
| Valid coverage | 0.700000 (21/30) | 0.50 to 0.80 inclusive | PASS |

Per-class F1: INCLUDE `0.952381`, EXCLUDE `1.000000`, UNKNOWN `0.947368`.
Output-contract completeness: PASS. Protocol checks: PASS. No gate-state metric was separately
specified in the frozen scoring specification.

## Deviations and decision

The repository instructions requested the `rtk` command wrapper, but `rtk` was unavailable in the
execution environment. Equivalent raw read-only commands were used; this did not alter source,
inputs, predictions, or scoring. No other protocol deviation occurred. No development, debugging,
tuning, code review, holdout construction, implementation change, V3 run, or rerun occurred.

**PASS — acquisition is formally accepted. Ranking is authorized and may now begin.**
