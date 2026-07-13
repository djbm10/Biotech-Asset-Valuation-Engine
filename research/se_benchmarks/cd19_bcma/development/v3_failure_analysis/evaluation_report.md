# Independent Holdout Evaluation Report

## Identity and integrity

- Evaluator/session: Codex independent holdout evaluator; session 2026-07-11.
- Evaluation date/time: 2026-07-11, America/New_York.
- Frozen commit: `e13efb9acc5a5578afbaeef40f01777e2f851e81` (verified).
- Detached worktree: `/tmp/se_dev_frozen_e13efb9`; exists, detached at the required commit,
  clean, and with no untracked or ignored artifacts before inference.
- Source archive: `/tmp/se_dev_source_e13efb9.tar`.
- Source archive SHA-256: `3ae999a75e8b4b1551e566d99f986648a7ae7bee7041feefe3636a62f1178120`.
- Manifest: `/tmp/se_holdout_custodian_20260711_v3/evaluator_manifest.md`.
- Manifest SHA-256: `d983e7364a4977da4aeff33023750566d59534415699307f0c3d5cc2e4071894`.
- Bundle: `/tmp/se_holdout_custodian_20260711_v3.tar`.
- Bundle SHA-256: `9c111570fe5150d6b6ea214fea4dfde5dbe771fa00a634d7d163bb946b7b7021`.

Verified holdout artifact hashes:

| Artifact | SHA-256 | Initial mode |
|---|---|---:|
| `problem.yaml` | `522c56e50b313f97ce3572e2bbecb65456d23a2462ee44b7c2a653887d5cc0af` | 0444 |
| `holdout_data.jsonl` | `1d590e37419f9c8ca1fd4a9ed871a2bb566cf6d02ddde632f3a40bd920f84d0c` | 0444 |
| `holdout_labels.jsonl` | `be25bbbdcbcc7702eae77bf16d6f0cd45b09db2441a374c20b891c237d8f045c` | 0000 |
| `label_digest.txt` | `563c0825150c2d18cc898203d061e908d86063d5980d552a8862b7fb8c912af8` | 0444 |
| `acceptance_and_scoring.md` | `fdb72e3fbc39156ffe3bb8aa470898d2b662f198f5f542a52135e9f1b8e1870f` | 0444 |
| `construction_and_adjudication.md` | `37346a42fc0d8722ebc761ec641f59567b9478298fc78551fbaefe8ff21fa811` | 0444 |
| `label_adjudication_notes.jsonl` | `87994f1cbdd2636c1d4ce74e9a6ba958e0dd85f23d8582a94582fb7ce89cdf85` | 0000 |

The manifest was frozen before inference. Labels and adjudication notes were mode `000` before
inference and remained inaccessible until prediction sealing. They were restored to read access
only afterward for scoring. No replacement prediction artifact existed before inference.

## Validation-only preflight

Exact command:

```text
PYTHONPATH=src python -m bve.cli.se_holdout_evaluate --problem /tmp/se_holdout_custodian_20260711_v3/problem.yaml --holdout-data /tmp/se_holdout_custodian_20260711_v3/holdout_data.jsonl --validate-only
```

- Exit status: `0`.
- Stdout/stderr capture: the complete tool capture contained a Matplotlib cache warning followed
  by `{"problem_id": "se_acquisition_triage_v3", "validation_status": "PASS", "case_count": 36}`;
  stream separation was not provided by the execution wrapper.
- Result: PASS; exactly 36 cases; no prediction file created; labels inaccessible.

## Single-shot inference

Exact command:

```text
PYTHONPATH=src python -m bve.cli.se_holdout_evaluate --problem /tmp/se_holdout_custodian_20260711_v3/problem.yaml --holdout-data /tmp/se_holdout_custodian_20260711_v3/holdout_data.jsonl --output /tmp/se_holdout_custodian_20260711_v3/predictions.json
```

- Working directory: `/tmp/se_dev_frozen_e13efb9`.
- Python: `3.12.3`.
- Relevant environment: `PYTHONPATH=src`; no label paths, labels, notes, scoring specification,
  construction record, or manifest were supplied to inference.
- Dependencies recorded/manifest-verified: Pydantic 2.12.5; PyYAML 6.0.1; pytest 9.0.2;
  NumPy 2.2.0; SciPy 1.17.0; Ruff 0.15.8.
- Start: `2026-07-11T14:46:19-04:00`.
- Completion: `2026-07-11T14:46:22-04:00`.
- Exit status: `0`.
- Complete captured output: a Matplotlib non-writable-cache warning; no prediction text was
  emitted by the evaluator. Stream separation was not provided by the execution wrapper.
- The inference command was executed exactly once. A pre-inference version probe reported that
  the imported Ruff module had no `__version__` attribute; this did not alter inference inputs,
  code, or environment.

## Prediction sealing and structural validation

- Raw prediction: `/tmp/se_holdout_custodian_20260711_v3/predictions.json`.
- Sealed prediction: `/tmp/se_holdout_custodian_20260711_v3/predictions.sealed.json`.
- Raw/sealed SHA-256: `d4b888c665079a3f2ec2c3fe6c0ea5f9369ed6f6866fff294754912d6f4aaced`.
- Raw size: 2772 bytes; raw mode after sealing: 0444.
- Sealed size: 2772 bytes; sealed mode: 0444; byte-for-byte identical: yes.
- Expected cases: 36. Produced records: 36. Unique IDs: 36.
- Missing IDs: none. Extra IDs: none. Duplicate IDs: none. Malformed records: 0.
- Invalid classes: 0. Prediction counts: INCLUDE 35, EXCLUDE 0, UNKNOWN 1.
- Unlabeled input: exactly 36 unique case IDs; no label-bearing fields detected.

## Scoring

Confusion matrix (authoritative label by sealed prediction):

| Actual \\ Predicted | INCLUDE | EXCLUDE | UNKNOWN |
|---|---:|---:|---:|
| INCLUDE | 12 | 0 | 0 |
| EXCLUDE | 12 | 0 | 0 |
| UNKNOWN | 11 | 0 | 1 |

| Metric | Result | Threshold | Criterion |
|---|---:|---:|---|
| Exact accuracy | 0.361111 | >= 0.750 | FAIL |
| INCLUDE recall | 1.000000 | >= 0.800 | PASS |
| EXCLUDE recall | 0.000000 | >= 0.800 | FAIL |
| EXCLUDE precision | undefined (zero denominator) | >= 0.750 | FAIL |
| UNKNOWN recall | 0.083333 | >= 0.700 | FAIL |
| Macro-F1 | 0.221495 | >= 0.700 | FAIL |
| Valid coverage | 0.972222 | 0.50 to 0.80 inclusive | FAIL |
| Abstention rate | 0.027778 | derived | — |

The authoritative composition was INCLUDE 12, EXCLUDE 12, UNKNOWN 12. Specialized metrics use
the sealed specification; zero EXCLUDE predictions makes EXCLUDE precision undefined and failing,
while the EXCLUDE-class F1 contribution is zero.

## Case-level reconciliation

`case_id: sealed prediction / authoritative label / exact correctness`

```text
v3-a7k2m9: INCLUDE / INCLUDE / yes
v3-aa3h8k1: INCLUDE / UNKNOWN / no
v3-ab9p4v6: INCLUDE / UNKNOWN / no
v3-ac2n7s5: INCLUDE / UNKNOWN / no
v3-ad6r1j8: INCLUDE / UNKNOWN / no
v3-ae4w9c2: INCLUDE / UNKNOWN / no
v3-af8k3m7: INCLUDE / UNKNOWN / no
v3-ag1d6q9: UNKNOWN / UNKNOWN / yes
v3-ah7v2b4: INCLUDE / UNKNOWN / no
v3-aj3s8x1: INCLUDE / UNKNOWN / no
v3-ak9c4n6: INCLUDE / UNKNOWN / no
v3-al2q7h5: INCLUDE / UNKNOWN / no
v3-am6f1p8: INCLUDE / UNKNOWN / no
v3-b4n8q1: INCLUDE / INCLUDE / yes
v3-c9r3t6: INCLUDE / INCLUDE / yes
v3-d2w7p5: INCLUDE / INCLUDE / yes
v3-e8h1v4: INCLUDE / INCLUDE / yes
v3-f5s9j2: INCLUDE / INCLUDE / yes
v3-g1x6l8: INCLUDE / INCLUDE / yes
v3-h7c2z9: INCLUDE / INCLUDE / yes
v3-j3m8f1: INCLUDE / INCLUDE / yes
v3-k9q4d6: INCLUDE / INCLUDE / yes
v3-l2v7n5: INCLUDE / INCLUDE / yes
v3-m6p1s8: INCLUDE / INCLUDE / yes
v3-n4t9b2: INCLUDE / EXCLUDE / no
v3-p8d3k7: INCLUDE / EXCLUDE / no
v3-q1f6w9: INCLUDE / EXCLUDE / no
v3-r7j2c4: INCLUDE / EXCLUDE / no
v3-s3z8m1: INCLUDE / EXCLUDE / no
v3-t9l4q6: INCLUDE / EXCLUDE / no
v3-u2b7h5: INCLUDE / EXCLUDE / no
v3-v6n1x8: INCLUDE / EXCLUDE / no
v3-w4s9p2: INCLUDE / EXCLUDE / no
v3-x8c3r7: INCLUDE / EXCLUDE / no
v3-y1m6d9: INCLUDE / EXCLUDE / no
v3-z7q2f4: INCLUDE / EXCLUDE / no
```

## Protocol decision

- Package integrity: PASS.
- Label isolation through sealing: PASS.
- Single-shot inference: PASS.
- Prediction immutability and completeness: PASS.
- Numerical acceptance: FAIL.
- Protocol deviations: none affecting evaluation integrity. The environment lacked the requested
  `rtk` wrapper, so equivalent read-only commands were used; no `rtk` command was available.
- Failure classification: numerical acceptance failure; not an infrastructure rejection or
  protocol failure.

**FAIL — acquisition is rejected, ranking remains blocked, and development is unfrozen.**
