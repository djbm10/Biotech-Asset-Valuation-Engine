# PRODUCT_VS_COMPONENT_MODALITY_SEMANTICS v4 — design preregistration

Design only; no gate consumer is authorized. Prerequisite: MODALITY_SCOPE_PRODUCT_DESCRIPTION v1 (Rule A appositive adopted; B removed; C/D/E unsupported). v3 (STOP at R3, `7e667bb`) is not evidence either way.

## Question

With the current scope representation, what would a whole-product modality gate consumer retain, withdraw and leave UNKNOWN, and is that trade acceptable?

## Required measurements (frozen before any rule)

1. The same population as v3 and the diagnosis: 293 rows = **172 distinct facts** (tac01/mint5_protoid_v1). Distinct facts are the primary denominator; also report rows keyed by `(run, fact_id)`.
2. Per fact: PRODUCT_LEVEL support under the adopted extractor, category (product / component / relational / ambiguous / none), and conflict flag.
3. Using the 13 adjudicated admitted facts (`research/se_modality_product_description_coverage_v1/adjudication.json`, unchanged): true facts retained, true facts lost, false facts withdrawn, false facts retained.
4. Precision/recall framing for a consumer that retains only PRODUCT_LEVEL-supported facts, compared with the legacy gate.

## Readiness (any failure → STOP with the boundary recorded)

- R1 zero adjudicated-FALSE admitted facts retained.
- R2 zero adjudicated-TRUE admitted facts whose adjudicated `support_type` is an **adopted** structure (currently APPOSITIVE only) are lost.
- R3 an explicit, preregistered policy for true facts whose support is an **unsupported** structure (COPULA, CLASS_OF, NAME_SELF_DESCRIBING, OTHERNAMES, cross-sentence). They must not be silently withdrawn; whether to withdraw them to UNKNOWN or keep legacy behaviour must be decided and justified before measurement.
- R4 conflicts resolve to UNKNOWN.

Out of scope: qualification, target identity, human-PoC, ESG401, ranking, acquisition, identity. H21–H25 not inspected; H6–H10 not run.
