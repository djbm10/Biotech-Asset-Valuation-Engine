# v3 execution freeze (design `b12ee79`, unchanged)

Frozen before any scope measurement of this population. Extractor = adopted head attachment `8c4bcae`.

## Population (b12ee79 item 3)

Non-holdout frozen development baselines `~/se_runs/tac01_protoid_v1/result.json` (sha256 prefix 2a423fb414d4) and `~/se_runs/mint5_protoid_v1/result.json` (085fd4f4c907): **293 stored `modality_id` facts** (TAC01 169, mint5 124), **13 gate-admitted** (all TAC01, all `modality.required` FAIL; mint5 has no modality requirement). H19's one fact is carried as before. No holdout, no live run, and H21–H25 are not inspected.

## API invocation per route (frozen; no new recognizer)

- `clinicaltrials_structured`: text = the intervention `description` field from the claim passage; product names = intervention `name` + `otherNames`. `name`, `type`, `otherNames` and `armGroupLabels` are non-sentence fields; the API has no representation for them, so they contribute **no scoped evidence**.
- `public_document_observed`: text = the claim's supporting passage; product names = the candidate's identity-layer names (`aliases`).
- Missing passage/description/names → `NO_SCOPED_EVIDENCE` (missing provenance), counted.

Category per fact (scoped assertions with the fact's value): `A_PRODUCT` (any PRODUCT_LEVEL), else `B_COMPONENT_ONLY`, `C_RELATIONAL`, `D_AMBIGUOUS`, `E_NO_SCOPED_EVIDENCE`. Conflict = a PRODUCT_LEVEL assertion of a *different* modality for the same candidate/source.

Proposed consumer (evaluated, not implemented): retain iff `A_PRODUCT` and no conflict; otherwise withdraw to UNKNOWN.

## Readiness (all required; first failure reported in this order)

- R1 — no frozen control (v2 14, head-attachment 25, `uncovered_controls.json` NON_PRODUCT) receives PRODUCT_LEVEL on a non-product focus; all v2/HA controls conform.
- R2 — all 293 facts accounted for with route, category and provenance; denominators reconcile.
- R3 — **zero** label-TRUE admitted facts (`labels.json`) would be withdrawn by the proposed consumer.
- R4 — no conflict resolved by selection (conflicts must go UNKNOWN).

Uncovered-structure controls' PRODUCT truths are measured as coverage (reported); their NON_PRODUCT truths are safety (R1). The verdict is computed by `checker.py`, which has no verdict constant and is self-tested.
