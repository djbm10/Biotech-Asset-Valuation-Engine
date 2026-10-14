# HUMAN_POC_PRECISION_FIRST v1 — DESIGN STOP (R3 first; R4 also fails)

Prereg `729c500` (`docs/se_policies/human_poc_precision_first_v1.md`). Design only; no production change. Reproduce: `PYTHONPATH=src python research/se_human_poc_precision_first_v1/audit.py --output <new dir>`. Hashes for the six run results, the adjudications and the two extractor files are verified; two builds are byte-identical. Self-test: a valid fixture is IMPLEMENTATION_READY; a false admission fails R1; unsupported structured provenance fails R2; withdrawn protected evidence fails R3; a zero-positive system is a DESIGN_STOP (never "ready"); a missing status fails R4.

## The critical finding is confirmed: no structured confirmation route exists

- **Code (static AST scan):** exactly one `ClinicalResult(...)` constructor in `src/`, at `evidence/clinicaltrials.py:286`. It hardcodes `incomplete_reporting=True` with no effect size. `result_supports_human_poc` rejects both conditions, so the `structured_clinical_result` route is **unreachable by construction**. PubMed and public-document extractors emit no `ClinicalResult`.
- **Data:** none of the 151 human-PoC fact observations in the six frozen runs has a structured claim. All 151 are `reported_efficacy_sentence` prose.
- **Source:** the CT.gov connector keeps only `protocolSection` (`connectors.py:169`). Across 1,932 captured trials, **0 snapshots contain `resultsSection`**, so posted registry results are never acquired. (The saved results also do not serialize `clinical_results`; the code scan, not that field, is the authority.)

## Baseline vs precision-first (frozen population)

| | Baseline | Proposed |
|---|---|---|
| human_poc_present=True, distinct (subject, passage) | 159 (113 subjects; 151 run observations) | **0 CONFIRMED**, 159 UNVERIFIED_PROSE |
| Adjudicated-true distinct passages confirmed | 97 | **0** |
| Adjudicated-false distinct passages confirmed | 29 (+24 facts whose passages mix true and false) | **0** |
| Gate `evidence.human_poc` (observations) | 64 PASS, 87 no requirement | 64 PASS → **UNKNOWN** |

The truth labels are the frozen context-safety v1 adjudications (110 passages, matched by exact text); 9 passages are unadjudicated. Exposed controls: H18 tirzepatide and H19 sacituzumab tirumotecan (false) would no longer be confirmed, but neither would H16 relatlimab, H18 survodutide or any other adjudicated-true passage.

## Requirements

| | Result |
|---|---|
| R1 no false confirmed | PASS (vacuously: nothing is confirmed) |
| R2 structured support verified | PASS (vacuously) |
| **R3 meaningful capability** (≥1 dev confirmed and ≥25% of true kept) | **FAIL: 0 confirmed, 0/97 true kept** |
| **R4 unverified status representable** | **FAIL**: `VerificationStatus` = EXTRACTED / MACHINE_VERIFIED / ANALYST_CONFIRMED / REJECTED. UNVERIFIED_PROSE would overload EXTRACTED, which the prereg forbids |

## Answers

1. **Complete structured human-PoC results:** none exist, by construction and in data.
2. **Human-PoC-required searches:** under structured-only routing they would return every row as UNKNOWN. That is **not useful as a filter**, and zero positives must not be presented as a precision win.
3. **Production implementation:** **not authorized.**

## Degraded safety mode (described, not authorized)

If the user prefers no false human-PoC over any human-PoC, the minimal mode is: prose never sets `human_poc_present=True`; the passage is preserved under a new explicit non-decisional status (needs R4's representation); `evidence.human_poc` reports UNKNOWN with a "no structured result source configured" disclosure. This removes the H18/H19 suite failures by disabling the capability, and must be labelled that way.

## Recommended next

- **Real fix (source data, not regex):** `CTGOV_POSTED_RESULTS_SOURCE v1`. Acquire `resultsSection` (outcome measures with posted values, analysed groups and arm attribution) and emit complete `ClinicalResult`s from it. This is the one authoritative structured efficacy source already in the stack. Its coverage (trials with posted results) must be measured first.
- **Ordering:** `TARGET_ALIAS_AUTHORITY_SOURCE v1` remains the stronger immediate next milestone. It fixes a decisive CRITICAL failure (refusals) with authoritative inputs. The posted-results milestone is the prerequisite for any honest human-PoC capability and should follow, or run in parallel if capacity allows.
