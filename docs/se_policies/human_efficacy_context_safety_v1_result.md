# HUMAN_EFFICACY_CONTEXT_SAFETY v1 — failed acceptance result

**Decision: FAILED_ACCEPTANCE. Do not adopt. Normal reversion required.**

Preregistration `38ca6c8`; implementation attempt `755e9c1`; scorer-only required-fixture
completion `b1645a3` before the scorer's first execution. No production change, label
change or acceptance-rule amendment followed the failing measurement.

This is diagnostic evidence-only evaluation, not a search replay or top20 rescore.
H6–H10 remain UNRUN. Frozen primary validation remains FAIL 0/5. H16–H20 are exposed
development data and cannot count as future generalization evidence.

## Frozen criteria

| Criterion | Result |
|---|---|
| E1 | PASS |
| E2 | PASS |
| E3 | FAIL |
| E4 | PASS |
| E5 | FAIL |
| E6 | FAIL |
| E7 | PASS |
| E8 | PASS |
| E9 | FAIL |
| E10 | FAIL |

Both exact primary false witnesses are rejected by the attempted reader. H18's human-cell
assay and H19's model/discount-rate sentence cannot supply human-PoC under the attempt.
That alone is insufficient for adoption: true-positive preservation and other frozen
requirements must pass simultaneously.

Full tests/se: **1971 passed,
20 failed, 0 errors, 3 expected xfails**.
Required Ruff checks are clean. The first Ruff invocation did not inspect code because
the sandbox refused its cache write; an unchanged-code `--no-cache` retry passed. That
infrastructure retry and original log are preserved separately.

Of 162 pre-adjudicated clinical claim witnesses,
143 remain admitted. Of 59 pre-adjudicated
numerical false witnesses, 57 reject. Existing reader-call
outcomes preserved: 94/96.
These are per-claim/run witnesses, so repeated source sentences across benchmarks count
separately here; preregistration also records distinct-passage and test-input counts.

## Exact failed semantic controls

- C053 (clinical_flare): expected True, actual False. `RX-001 produced a 63% reduction in disease flare risk in treated patients.`
- C056 (regimen): expected False, actual True. `Patients treated with RX-001, RX-002, and RX-003 achieved a response rate of 63%.`

## Exact failed preserved/adjudicated witnesses

- TAC01 / Bevacizumab / survey 11 / `claim:d873e0fa9c925007ee4e`: expected True, actual False.
- mint5 / Venetoclax / survey 26 / `claim:5ededd17eb739d2e1106`: expected True, actual False.
- AACR_accepted / PET30 / survey 42 / `claim:2ab7b26095caafbfad9b`: expected True, actual False.
- AACR_accepted / Venetoclax / survey 26 / `claim:5ededd17eb739d2e1106`: expected True, actual False.
- AACR_accepted / though / survey 54 / `claim:95e146d23911c954540c`: expected True, actual False.
- TAC01_regimen_accepted / Bevacizumab / survey 11 / `claim:d873e0fa9c925007ee4e`: expected True, actual False.
- H16 / Relugolix / survey 62 / `claim:dfa26674a43723ab9e68`: expected True, actual False.
- H16 / Ivermectin / survey 64 / `claim:fda8d13dfda69b782423`: expected False, actual True.
- H16 / Glecaprevir / survey 69 / `claim:888e9c2c9ce421d305e4`: expected True, actual False.
- H16 / pibrentasvir / survey 69 / `claim:f93f85d51368a0574d97`: expected True, actual False.
- H16 / bevacizumab / survey 78 / `claim:1672c26a362bce427334`: expected True, actual False.
- H16 / Dupilumab / survey 64 / `claim:6fe84fe83a76085b6cb1`: expected False, actual True.
- H16 / atazanavir / survey 80 / `claim:e9f5d18fea7bd5531e0e`: expected True, actual False.
- H16 / ritonavir / survey 80 / `claim:e02f9edf1a088951bfae`: expected True, actual False.
- H16 / Lopinavir / survey 80 / `claim:ad115c2cb6291b6ce2e9`: expected True, actual False.
- H16 / Fosamprenavir / survey 80 / `claim:d6109ffeff6ee4cfadca`: expected True, actual False.
- H16 / Lamivudine / survey 92 / `claim:5104ef3bd86e3a7f4e83`: expected True, actual False.
- H16 / Lamivudine / survey 80 / `claim:07de85a540078d3b5cec`: expected True, actual False.
- H18 / ROSE-010 / survey 99 / `claim:b420098f328b37ad2838`: expected True, actual False.
- H18 / glepaglutide / survey 103 / `claim:0c74e255816f9655f5cf`: expected True, actual False.
- H18 / survodutide / survey 104 / `claim:13f922afecbd81303713`: expected True, actual False.

## Reversion and stopping rule

The measurement exposed these independent failure details:

- The extra outcome matcher is too conservative for genuine clinical language. It rejects
  the existing `10/16 evaluable pts ... ongoing BM CR` witness and observed quantified flare
  risk reduction, as well as some comparator/ellipsis and patient-count formulations.
  Across run/claim witnesses it drops 19 pre-adjudicated clinical contents, while two
  receptor-number false witnesses (survey 64, different assets) still pass. The 160-character
  linking heuristic is not a sound outcome grammar and cannot be rescued by case patches.
- C056 was already PASS before implementation but was frozen as expected UNKNOWN. It is
  a first-item regimen-list attribution defect, not a nonclinical numeric-context example.
  The preregistration forbids changing the existing attribution functions. This is an
  inadequately scoped acceptance control, disclosed rather than removed after scoring.
- `test_indication_gate_semantics_v3.py::test_frozen_compilation_and_source_isolation`
  pins the earlier experiment's human-PoC source hash. It necessarily fails for this
  authorized module change even though this milestone's E8 isolation check passes.
  Historical experiment isolation versus subsequent authorized source evolution needs
  an explicit test-lifecycle decision before a future attempt. No hash oracle is changed
  or xfailed here. Even without that test and C056, genuine-witness preservation fails.

The stricter structural matcher was not adequate for the whole frozen clinical population.
The full failure inventory, first scorer output, attempted source/test/scorer bytes and
preregistered judgments are retained. No individual failure may be rescued by a post-result
patch, new exception, edited positive label, weaker criterion or benchmark/top20 optimization.

Revert the scorer-fixture commit and the implementation commit normally, verify byte-level
restoration against the preregistered clean baseline, update the handoff, and stop. A future
v2 requires new diagnosis/preregistration; this result does not authorize it or any later
target, qualification, identity, modality or ranking milestone.
