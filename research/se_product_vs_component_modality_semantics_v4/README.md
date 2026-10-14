# PRODUCT_VS_COMPONENT_MODALITY_SEMANTICS v4 — design STOP (R2 first, R3 also fails)

Design `8ca2a76` unchanged; R3 policy frozen at `78c3694` before measurement. Verdict computed by `audit.py::criteria`: **STOP**. Modality gating is **parked**. No production change.

Reproduce: `PYTHONPATH=src python research/se_product_vs_component_modality_semantics_v4/audit.py --output <new dir>`. v3 routing and categorization are reused unchanged and run-snapshot hashes are verified. Two builds are byte-identical. Self-test: a valid fixture is DESIGN_READY; false retention fails R1, a withdrawn supported true fact fails R2, an invalid R3 policy fails R3, a chosen conflict fails R4, and an altered population fails R0.

## Population

172 distinct facts (primary); 293 run rows keyed by `(run, fact_id)`. Distinct: 4 A_PRODUCT, 158 D_AMBIGUOUS, 10 E_NO_SCOPED_EVIDENCE. Dispositions (distinct): **4 RETAIN, 167 UNKNOWN_REVIEW, 1 UNKNOWN_CONFLICT**. Rows: 8 / 284 / 1.

## Requirements

| | Result |
|---|---|
| R0 frozen population | PASS |
| R1 no false admitted fact retained | PASS (0/5 retained; registry-category CAR-T, co-arm vaccines and other-product TCE all withdrawn) |
| **R2 no adopted-structure true fact lost** | **FAIL**: CC312 (APPOSITIVE) is not certified |
| **R3 policy + no true fact to UNKNOWN** | **FAIL**: 7/8 true admitted facts go to UNKNOWN_REVIEW (prediction was 6; CC312 is the extra one) |
| R4 conflicts → UNKNOWN | PASS (1 conflict) |

**Why CC312 fails:** "CC312, a *trispecific* CD19-targeting co-stimulatory T cell engager". `trispecific` is itself an ontology alias (MULTISPECIFIC_ANTIBODY), so the frozen Rule A guard (premodifier mentions must share the head's modality) blocks the T_CELL_ENGAGER head. The rule worked as specified; whether a trispecific TCE should be MULTISPECIFIC or TCE is an ontology-hierarchy question, not something to fix here. Not patched.

## Trade-off (13 adjudicated admitted facts only, not population-wide)

| | Legacy gate | v4 consumer |
|---|---|---|
| True retained | 8 | **1** (blinatumomab appositive) |
| True → UNKNOWN | 0 | 7 |
| False retained | 5 | **0** |
| False withdrawn | 0 | 5 |
| Precision of decisional facts | 8/13 = 0.62 | 1/1 = 1.00 |
| Recall of true facts | 8/8 | 1/8 = 0.125 |

The v4 consumer passes its mechanical safety checks (R1, R4) but is not scientifically deployable. It removes the false facts only by also discarding 7 of 8 verified true ones, since the representation cannot tell them apart. Keeping unsupported facts instead would fail R1. That is the boundary the R3 policy predicted.

Specific protections held: Bexxar is not a monoclonal antibody (Rule B removed); the ICI class label is not a product; the "Biological/Vaccine" CAR-T is not a vaccine; datopotamab's peptide linker is component-level (the legacy PEPTIDE exclusion remains). There is no drug-specific logic and no cross-sentence coreference.

## Closure

Modality gating is parked. Re-opening it needs product-level evidence for copula, class-of and structured CT.gov descriptions under an identity authority that can tell named products from class labels; that is a different milestone. Next priority per the brief: a separately preregistered **ESG401 candidate-nomination diagnosis**, kept separate from modality.
