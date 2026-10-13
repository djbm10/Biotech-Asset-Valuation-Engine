# PRODUCT_VS_COMPONENT_MODALITY_SEMANTICS v2 — design STOP

Design preregistration `65cddd1` (unchanged); population freeze `43e30ce` (unchanged). Verdict: **STOP_UNSAFE_PRODUCT_LEVEL_CERTIFICATION** under item 3 of `65cddd1` and the stop rule in `population_freeze.md`. v2 is **not adopted**; no semantic delta is authorized.

Reproduce: `PYTHONPATH=src python research/se_product_vs_component_modality_semantics_v2/audit.py --output <new dir>`. The script verifies every frozen input hash, reads the saved H19 run and calls the adopted `scoped_modality_assertions` API unchanged. Two independent builds produce byte-identical outputs (`results/hashes.json`).

## Control results (14 frozen structural controls)

11 adequate. All six whole-product positives (`P_PEPTIDE`, `P_ADC`, `P_CELL`, `P_GENE`, `P_ANTIBODY`, `P_SMALL`) receive PRODUCT_LEVEL; `MISSING_SCOPE` and `NO_COREFERENCE` stay AMBIGUOUS; `COMPOSITE` stays RELATIONAL_COMPOSITE; both `CONFLICT_*` assertions are PRODUCT_LEVEL and would be jointly non-permitting.

Three inadequate, all compound-modifier controls. Each fails the same way: rule `explicit_product_predicate` binds "Novel Product is a ..." to the **first** modality mention, which is the modifier, while the noun-phrase head is left AMBIGUOUS (`unproven_subject_or_relation`):

| Control | Text | Modifier (expected non-product) | Head (actual product) |
|---|---|---|---|
| MODIFIER_PEPTIDE | peptide-linked antibody-drug conjugate | `peptide` → PEPTIDE **PRODUCT_LEVEL** | `antibody-drug conjugate` → AMBIGUOUS |
| MODIFIER_ANTIBODY | antibody-derived cell therapy | `antibody` → MONOCLONAL_ANTIBODY **PRODUCT_LEVEL** | `cell therapy` → AMBIGUOUS |
| MODIFIER_PAYLOAD | small-molecule-loaded nanoparticle | `small-molecule` → SMALL_MOLECULE **PRODUCT_LEVEL** | (nanoparticle: no modality vocabulary) |

So a consumer that trusts PRODUCT_LEVEL would type a peptide-linked ADC as a PEPTIDE product: the same false whole-product PEPTIDE this program exists to remove, now certified rather than legacy. The scope representation does not attach predicates to the noun-phrase head, so PRODUCT_LEVEL is not safe as a gate input.

## Legacy fact register

H19 has 1 stored modality fact (1 admitted, route `clinicaltrials_structured`) across 1,181 candidates / 783 documents. It is datopotamab's PEPTIDE fact, category **B_COMPONENT_ONLY** (its PEPTIDE-valued scoped assertions are all COMPONENT_LEVEL), current `modality.required` FAIL. Proposed action: `NONE_BLOCKED_SCOPE_CERTIFICATION`; the legacy fact is retained. One fact cannot show broad preservation, and the classification does not license acting on it while PRODUCT_LEVEL itself is unsafe.

## Audit-script correction (disclosed)

The uncommitted draft left by the previous session hardcoded `design_status` and `proposed_semantic_disposition`. The committed `audit.py` derives the status from the frozen stop rule (any NON_PRODUCT control receiving PRODUCT_LEVEL) and maps disposition from category. The scoring logic, controls and outputs are otherwise identical, and the derived verdict matches the draft's.

## Boundary and what is not authorized

- No production, scope-extractor, rule, expectation or contract change. The scope grammar is **not** patched here: per `population_freeze.md` no new recognizer or phrase blacklist is permitted after seeing outcomes.
- Next step requires a **separately preregistered** representation milestone, e.g. noun-phrase head attachment for `explicit_product_predicate`, with the three modifier controls frozen beforehand, and then a fresh v3 semantic design. Not started.
- Datopotamab's false PEPTIDE exclusion remains, by design.
- ESG401 candidate nomination, BL-M02D1, qualification, 86 component identities, human-PoC: unchanged/separate. H21–H25 untouched; H6–H10 unrun.
