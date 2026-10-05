# NCIT_MODALITY v1 — NCIt Cell-typed product concepts supply a missing authority modality (preregistration)

**Status:** PREREGISTERED 2026-10-05. No implementation exists.
**Operator plan:** NCIt-backed modality coverage comes after the human-efficacy diagnosis
(`human_efficacy_coverage_diagnosis_v1.md`), as the next structured cleanup.
**Baselines:** `~/se_runs/{tac01,mint5}_armid_v1`, ranked under ranking v2.

## 1. Problem

Authority modality comes only from ChEMBL `molecule_type` (`authority_modality_v1`). Many
cell products have no ChEMBL record, or are seen only under a code or trade name ChEMBL does
not hold. Examples: CNCT19, KITE-753, ALLO-501A, YESCARTA, Tecartus. Their modality is
UNKNOWN. In a cell-therapy query, modality ranks before target, so a confirmed-CD19 CAR-T
with UNKNOWN modality sorts below an UNKNOWN-target cell product with a known modality.

## 2. Rule (frozen)

**Precondition.** Fill-only: the rule applies when the ChEMBL authority modality is `None`.
ChEMBL keeps precedence and is never overridden.

**Rule.** If the asset has an **unambiguous** NCIt link (the adopted NCIt sidecar linking,
`ncit_target_sidecar_v1` §3.5), and that NCIt product concept carries the UMLS semantic type
**`Cell`**, then:
- `authority_modality = CELL_THERAPY`;
- `authority_modality_basis = NCIt:<code> (Cell)`.

`modality_match` is recomputed by the existing `modality_match` function.

**What it does not touch:**
- NCIt concepts not typed `Cell` (for example Nelipepimut-S, or "Chemical Viewed
  Functionally" class concepts);
- ambiguous links;
- every other NCIt disposition field.

**Data and replay.** A new sidecar, `data/se/ontology/ncit/ncit_26.08e_cell_products.json`,
holds the list of sidecar product codes typed `Cell`. It is built from the same frozen zip.
Its token goes into `extractor_versions["ncit_cell_products"]` and is fail-closed on replay,
like the other NCIt sidecars.

**Out of scope:** targets, qualification, identity and ranking code. No modality other than
CELL_THERAPY is derived.

## 3. Frozen population (enumerated and audited before code)

The population is `research/se_ncit_modality/population_v1.json`
(sha256 `5b7e22a384b83c5b28d172edb561c84e6ee3dc6793e3196f42b02e58481b7a9c`). It contains
201 fills: 103 in TAC01 and 98 in mint5, over 101 distinct NCIt concepts.

**Audit.** I read every unique name→concept pair. Each concept is a CAR-T, CAR-NK, TCR-T,
γδ-T, TIL, NK-cell-line or virus-specific T-cell preparation, which is a cell therapy by
construction. Generic concept names ("Natural Killer Cells", "NK-92") are cell products too:
the modality is correct even where identity qualification is a separate question.
**0 incorrect fills are expected.**

## 4. Acceptance (frozen)

Sealed replays go into new directories. Facts, identity and gates are compared against
`*_armid_v1`. Ranking is compared against `*_armid_v1` **rebuilt under ranking v2**.

- **N1.** The set of assets whose `authority_modality` changed from `None` to CELL_THERAPY
  equals the frozen population exactly.
- **N2.** No asset with a ChEMBL authority modality changes.
- **N3.** No fact, target gate, qualification reason, identity merge or candidate set
  changes. Determinism comparisons exclude `created_at` and `applied_at`, declared now.
- **N4.** `modality_match` changes only on population rows, and only to the value
  `modality_match("CELL_THERAPY", query)` gives. In TAC01 that is UNKNOWN→MATCH. mint5
  declares no modality, so its value stays `None`.
- **N5.** Ranking code is unchanged. Every top-50 movement is explained by a population row's
  `modality_match` change, or by its deterministic consequence. The mint5 order must be
  identical, because no modality is declared.
- **N6.** Two TAC01 replays give identical results, with timestamps excluded.
- **N7.** `tests/se` and ruff pass.

## 5. Stop condition

- **Adopt** if N1–N7 all pass.
- **Otherwise** record the failure and revert. Do not extend beyond `Cell` and
  CELL_THERAPY.
