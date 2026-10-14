# ESG401_CANDIDATE_NOMINATION_DIAGNOSIS v1 — preregistration

Diagnosis only; no production change. Modality gating stays parked at v4. H21–H25 are not inspected, H6–H10 are not run, and nothing is acquired live.

## Population (frozen before measurement)

`research/se_esg401_candidate_nomination_diagnosis_v1/sample.py` → `sample.json`. It covers the non-holdout development CT.gov snapshots in tac01/mint5_protoid_v1: 1,932 trials and 3,509 arms with descriptions. Shape strata are ALT (`or` / `either` / ` / `), COMB (`+` / `and` / `plus` / `combined` / `followed by`) and OTHER; each stratum takes its first 15 units by sha256 order. That gives 45 independent arms plus the H19 ESG401 arm as development reference (`NCT06145308` arm 3, snapshot sha `4c21f6a5…`). `labels.json`: blind adjudication of every named entity, with kind, role and arm-level relation.

## Measurements

Per entity:
- **Covered**: the name is reachable through the trial's existing nomination inputs (`interventions[].name` / `otherNames`, normalized substring either way).
- **Extracted by the existing mention extractor** over the arm description (`extract_observed_asset_names`), as a probe of what a description route would emit.
- **Spurious**: the probe emits a string that is not an adjudicated THERAPEUTIC_PRODUCT.

The primary denominator is distinct source mentions; distinct names are reported separately.

Pool-wide prevalence: on all 3,509 arms, count arms where the probe emits a name not covered by the trial's interventions. This count is unadjudicated and reported as an upper bound.

The ESG401 end-to-end trace is recorded stage by stage from code and the frozen H19 artifacts.

## Decision (computed by `diagnose.py`, self-tested)

- J1 failure class: ≥5 adjudicated **uncovered** THERAPEUTIC_PRODUCT mentions with role ADMINISTERED in ≥3 distinct **independent** trials (development reference excluded).
- J2 probe safety: the existing extractor over arm descriptions emits **0** spurious names on the 45 independent units.
- J3 relationship representation: the schema can express an arm-level product **alternative** distinct from combination and randomized allocation. Read from `IdentityRelationship`.

JUSTIFIED (specify ARM_ALTERNATIVE_CANDIDATE_NOMINATION v1) iff J1 ∧ J2 ∧ J3. Otherwise STOP at the first failing requirement in that order. Missing J3 alone defines the smallest needed representation rather than blocking.
