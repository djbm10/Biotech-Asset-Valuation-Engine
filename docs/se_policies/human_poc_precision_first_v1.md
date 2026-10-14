# HUMAN_POC_PRECISION_FIRST v1 — design & coverage audit (preregistration)

Authorized by the user as a precision-first **design** milestone. No production change. The rejected context-safety recovery stays reverted. H16/H18/H19 are development controls only. H21–H25 are not inspected; H6–H10 are not run; nothing is acquired live or replayed.

## Population (hashes in `research/se_human_poc_precision_first_v1/freeze_hashes.txt`)

- Saved results tac01_protoid_v1, mint5_protoid_v1 and aacr_safety (non-holdout dev), plus heldout_h16_v4, heldout_h18_v4_rerun1 (the scored H18) and heldout_h19_v4 (exposed controls).
- Every fact with `fact_type == human_poc_present` and value True, and every supporting claim.
- **Denominators:** distinct facts keyed by `(subject canonical name casefold, supporting passage)`, plus run-level observations keyed by `(run, fact_id)`.
- **Truth labels:** the frozen 110-passage `witness_adjudications.json` (81 expected_pass / 29 not) from context-safety v1, matched by exact passage text. Unmatched passages are UNADJUDICATED; they are counted but not called true or false.

## Route classes per supporting claim

1. `STRUCTURED_COMPLETE`: `extraction_method == structured_clinical_result`. A ClinicalResult with an effect size and not incomplete; source, population, attribution and magnitude still require verification.
2. `STRUCTURED_INCOMPLETE`: a protocol endpoint without a result. It cannot support human-PoC (`result_supports_human_poc`).
3. `PROSE`: `reported_efficacy_sentence` (and other sentence routes).
4. `OTHER`: anything else.

Also measured from code: the set of `ClinicalResult` emitters, and whether any can set `incomplete_reporting=False` with an `effect_size`.

## Proposed policy (evaluated, not implemented)

CONFIRMED only from STRUCTURED_COMPLETE with verified attribution; UNVERIFIED_PROSE for PROSE (never True, never False); UNKNOWN otherwise. The audit also checks whether the current schema can express UNVERIFIED_PROSE without overloading `verification_status` or confidence.

## Readiness (computed by `audit.py`, self-tested; first failure reported)

- R1 no adjudicated-false passage is CONFIRMED.
- R2 every CONFIRMED fact has STRUCTURED_COMPLETE support with a non-empty population, an endpoint and an effect size.
- R3 **capability:** CONFIRMED distinct facts ≥ 1 in the dev population **and** ≥ 25% of adjudicated-true distinct passages remain CONFIRMED. Below this, the structured-only route is not a meaningful human-PoC capability.
- R4 representation: the schema has a distinct non-decisional status for unverified prose.

All pass → implementation proposal. R3 fails → **design STOP** (missing structured result coverage), with a degraded safety mode described separately and not authorized. Zero CONFIRMED is never reported as precision success.
