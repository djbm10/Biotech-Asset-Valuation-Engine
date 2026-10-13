# THERAPEUTIC_PRODUCT_ROLE_QUALIFICATION_CONTRACT v1 — representation boundary

**NOT IMPLEMENTATION-READY. Production implementation was not started.** This executes the design audit preregistered in `d22f6b8`; it does not replace or amend that contract. The policy, original preregistration and input manifest remain byte-identical to that commit.

The frozen stop condition says: “Stop at an implementation-ready, fully frozen and offline-demonstrated contract OR a precise evidence/representation gap.” D8 permits a documented architecture boundary with zero production changes. That is the outcome here. The existing document specifies scientific constraints and a design exercise, but no exact replacement qualification predicate, admissible source-to-product binding rule, or frozen implementation delta. Inventing any of those now would not be implementation of an already specified rule.

## Evidence for the boundary

`AssetEvidence` receives a name, `structurally_typed_drug`, aggregate comparator/therapeutic/unknown observation counts, coarse identity/entity-link booleans and prose-support counts. It cannot represent:

- whether an assertion concerns the whole product, a generic intervention category, or a particular use;
- a product-kind assertion such as therapeutic, diagnostic-only, dual-use or unresolved;
- an intervention-use assertion tied to a specific source, trial, arm and intervention;
- the source field, raw span, authority basis or contradictory evidence supporting those assertions.

The raw H19 snapshots retain useful evidence, but the qualification function does not receive it. `CandidateHit` arm relationships become aggregate counters in the registry; `pipeline._asset_evidence` passes those counters into `qualification_reason`. Arm membership is thereby used as an independent product-qualification route. Recovering and interpreting raw descriptions inside the qualifier would require a new evidence-binding/extraction rule, outside the requested qualification-only change and absent from d22f6b8.

Two necessary structural controls were frozen in **99e9c06**, under the original contract's explicit allowance for additions before rule derivation. Both use the same synthetic name and exactly identical qualification input. One source describes a single therapeutic development product; the other explicitly describes a diagnostic-only substance. Both are typed DRUG in an EXPERIMENTAL arm. They both currently return STRUCTURED_THERAPEUTIC. The full `AssetEvidence` serialization is identical. No deterministic function of these inputs can distinguish the cases. This is a statement about missing information, not a proposal to blacklist a name or globally discard structured interventions.

Simply removing the route is not a demonstrated solution: the existing regression population explicitly protects therapeutic qualification through that route. No counterfactual removal implementation was attempted, and no hypothetical loss count is presented as measured.

## Frozen audit and baseline

`results/subject_scope_audit.json` and `subject_scope_table.md` account for all **46** design rows: 23 original H19 entity rows, 21 original controls and the two added structural witnesses. Each records the source/fixture, subject, scope, kind, role, baseline route, intended design outcome and unresolved evidence boundary. Synthetic semantic controls remain synthetic; no diagnostic annotation is promoted into production authority evidence.

Red-first tests against unchanged production code:

- Three frozen H19 non-assets: all three fail the intended negative checks.
- Synthetic diagnostic control: fails the intended negative check.
- Synthetic therapeutic control and the three existing therapeutic probes: all four pass.
- Total: **8 tests, four expected baseline failures, four passes, zero errors**.
- All **215 existing qualification regression tests pass**. Historical implementation expectations are preserved separately from the new semantic negative checks.

| Frozen non-asset | Before | After this milestone |
|---|---|---|
| [68Ga]Ga-TTP | STRUCTURED_THERAPEUTIC | Unchanged; no implementation |
| Rescue Medications | STRUCTURED_THERAPEUTIC | Unchanged; no implementation |
| Rescue Medication | STRUCTURED_THERAPEUTIC | Unchanged; no implementation |

All protected executable positives remain unchanged. The 12 stipulated semantic controls do not yet have an executable source-to-qualification mapping; they are not falsely reported as passing a new classifier. All **1,181 saved candidate qualification decisions** are preserved as a baseline artifact. Total implementation deltas: **0**; true therapeutic assets losing qualification: **0**; out-of-scope deltas: **0**. These zeros mean no behavior was changed, not that a successful fix was evaluated.

Independent seed-0/seed-42 design-audit builds produce byte-identical canonical artifacts. Original pinned inputs verify. Ruff is clean. Full tests/se was not run because there are no production changes; the complete relevant qualification regression population was run. The red test failures are the intended baseline evidence, not failed production-implementation results.

## Minimum extension required, not implemented

Preserve assertion-level qualification evidence before aggregation. The smallest interface must retain:

| Information | Why required |
|---|---|
| Exact candidate/product identity and source intervention locator | Prevent a category or another intervention's evidence being attached to the product |
| Assertion subject/scope: product identity, whole-product kind, or observation-specific use | Prevent use/context/component information becoming intrinsic product identity |
| Predicate/value and explicit UNKNOWN/CONFLICT status | Avoid replacing missing evidence with therapeutic status |
| Source artifact hash, document/trial/arm/intervention ID, raw field/span | Reproduce and audit the claim |
| Structured source declaration versus interpretation, with rule/version | Distinguish DRUG/EXPERIMENTAL declarations from a future therapeutic-product interpretation |
| Distinct supporting and contradictory assertions | Preserve mixed or dual-use evidence rather than collapsing it into a counter |

This is a minimum information requirement, **not a replacement contract, implemented schema or newly authorized evidence hierarchy**. The existing design still needs an explicit approved rule for binding source claims to those subjects and determining which positive assertions can establish therapeutic-product status. A future separately preregistered representation/evidence-binding implementation would be necessary before a qualification consumer can safely use that information. No such implementation is silently opened here.

The source code precedence issue is deliberately separate: the direct approved-name route preceding a non-product veto did not admit these three H19 rows. It was not changed or used as a shortcut around this boundary.

## Scope and reproduction

`audit.py` produces the deterministic design table and baseline custody record from the pinned diagnosis. Run with `PYTHONPATH=src python .../audit.py --output <new-directory>`; repeat under a second PYTHONHASHSEED and compare `hashes.json`. `test_baseline_role_controls.py` is an explicitly red baseline probe; four failures are expected until a separately authorized implementation exists. XML and logs are preserved in results. Do not interpret them as an adopted regression suite for a nonexistent fix.

No changes to extraction, nomination, qualification, modality, targets, identity, ranking or sources. Datopotamab, ESG401 and BL-M02D1 paths remain untouched. No adoption or revert applies because production implementation never began. Do not proceed to PRODUCT_VS_COMPONENT_MODALITY as though qualification had been adopted.

The 86 target-component cases remain closed. Human-PoC recovery stopped. H21–H25 untouched; H6–H10 unrun. Stop at the documented boundary, as required by d22f6b8 and the current instruction.
