# INDICATION_GATE_SEMANTICS v1 — diagnosis and unresolved evidence contract

Date: 2026-10-11. Baseline: ebbb554, adopted compilation v3.
Status: DIAGNOSIS ONLY. No behavior preregistered, implemented, scored or adopted.

## Frozen evidence audit

The manifest freezes existing H2/H4/H11–H14, TAC01 and mint5 result hashes,
38 reference products, all 655 historical diagnostic indication-only exclusions,
the 16 prior semantic controls, accepted compilation readout, and source hashes.
The baseline population retains current indication decisions, requested requirements,
raw facts, supporting claims and source documents. Semantic classes are deliberately
unlabeled pending the incompatibility contract decision. This is a diagnosis freeze,
not an acceptance population or a completed preregistration.

Across the eight frozen runs, all 9,127 indication facts are raw strings, confidence
0.95, not analyst-confirmed, supported by clinicaltrials_structured indication claims
from REGISTRY-tier ClinicalTrials.gov trial_registry_record documents. No indication
value is an ID-bearing mapping or list. No asset-level negative assertion or exhaustive
asset indication inventory exists in these populations.

The registry extractor emits the first conditionsModule.conditions entry as the fact
value; the supporting passage retains the complete condition list. Facts are remapped
onto assets. A trial condition positively supports development in that condition;
it does not establish that the asset cannot address another condition.

NormalizedFact carries claim IDs and review/confidence fields, but has no explicit
indication scope, completeness, exclusion relation or normalized disease-ID contract.
The gate receives facts, not source documents. The extraction schema therefore cannot
establish an asset-level incompatible indication merely from a different condition.

The current gate routes all-literal requests to exact IN comparison; a nonmatch is
FAIL. Only the legacy B-cell concept uses its controlled vocabulary helper, which
also treats unrelated conditions as NO and all-NO as FAIL. These are closed-world
assumptions over open-world, partial trial evidence. Current compilation-v3 baseline:
38 references = 0 PASS / 5 UNKNOWN / 33 FAIL. The 33 historical indication-only
excluded references remain FAIL. This is diagnosis, not a new experiment result.

The frozen NCIt disease graph can support unique authority identity/synonym and
observed-descendant/requested-ancestor comparisons. Missing typing or paths cannot
prove incompatibility. Hidradenitis suppurativa's Finding typing illustrates this.
An observed parent alone cannot prove the requested subtype. Matching evidence must
win over unrelated trials. Those positive/uncertainty rules are scientifically
resolvable; a nonvacuous positive incompatibility contract is not yet established.

## Scientific/architecture decision required before preregistration

G3 requires nonempty controls with sufficient positive incompatibility evidence.
Neither different trial diseases, missing NCIt paths, nor old NO vocabulary labels
provide such evidence about an asset. Keeping them as FAIL would violate the user's
core rule; an empty negative population would make G3 vacuous.

Proposed next option: authorize a separately explicit, claim-backed, analyst-reviewed
asset-level indication incompatibility assertion contract, scoped to the requested
authority disease concept. It must distinguish a reviewed negative assertion from
a positive trial condition, preserve citations, and specify conflict/aggregation rules.
Only that assertion could establish FAIL; partial unrelated trial conditions would
remain UNKNOWN. No emitter, schema or contract has been added in this diagnosis.

Alternative: explicitly rescope the next milestone to positive compatibility and
uncertainty only, deferring FAIL and G3 until such an evidence contract exists. This
requires a user scientific decision, rather than silently weakening acceptance.

Earlier adopted B-cell policy authorizes condition-level disjointness and all-NO
FAIL; it does not define a reviewed asset-level negative evidence contract. The
current user's stronger asset evidence rule takes precedence. Benchmark changes
would require independent defect demonstrations under G7, not preservation by
special-case exceptions. Negation support remains deferred.

## Preservation and next action

Production source, tests and scripts are unchanged from ebbb554. No acceptance
criteria have been scored and no new quality run is claimed. Previous full suite
result remains compilation-v3's 1,672 passed / 3 expected xfails, Ruff clean.
All failed experiments and adopted compilation-v3 artifacts remain unchanged.
H16–H20 were not run, inspected or resolved; H6–H10 remain unrun. No live acquisition
or replay was launched. Resolve the evidence contract, then preregister a complete
gate-specific population and G1–G9 before any behavior-changing code.
