# MODALITY_PRODUCT_DESCRIPTION_COVERAGE_DIAGNOSIS v1 — preregistration

Diagnosis only. No production code, no gate consumer, no grammar change. v3 stays unadopted at `7e667bb`; its labels are unchanged. Re-adjudication: `research/se_modality_product_description_coverage_v1/adjudication.json` (13/13 agree; three evidence limitations recorded).

## v3 denominator reconciliation

v3 categories are mutually exclusive: 282 D_AMBIGUOUS + 11 E_NO_SCOPED_EVIDENCE = 293. "conflict" is an orthogonal flag on one D_AMBIGUOUS row (`fact:6920bacb462745c896a4`), not a category. The v3 README's prose listed it in-line, which read as additive. No accounting error; the verdict is unaffected.

## Population

The same 293 facts (tac01/mint5_protoid_v1, hashes in v3 `freeze_hashes.txt`). Diagnostics read each fact's full source snapshot, not only the truncated claim passage. No holdout or live run; H21–H25 not inspected.

## Structure taxonomy (fixed before measurement)

Names: CT.gov = intervention `name` + `otherNames`; public documents = candidate aliases. A name of the form `A (B)` also yields `A` and `B` (general parenthetical expansion). M = any ontology alias of the fact's own modality. "Same clause" = no `.;\n` between.

Explicit, product-anchored (eligible):
- `COPULA`: N [optional (…)] is/are (a|an) <≤8 words, no boundary verb> M
- `APPOSITIVE`: N [optional (…)] , (a|an) <≤8 words> M
- `CLASS_OF`: N … is … (in|of) the class of … M, same clause
- `NAME_SELF_DESCRIBING`: the CT.gov intervention `name` itself contains M
- `STRUCTURED_OTHERNAMES`: an `otherNames` entry contains M

Not eligible (reported):
- `REGISTRY_CATEGORY`: M only as a `<Type>/<M>:` prefix
- `CO_OCCURRENCE`: N and M in the same document but no eligible pattern
- `NAME_ABSENT`: no candidate name in the source text
- `MODALITY_ABSENT`: no M in the source text
- `NO_SOURCE`: snapshot or field unavailable

Each fact gets every matching class plus one mutually exclusive primary (the first eligible class in the order above, else the first non-eligible one).

## Readiness rule (frozen; computed by `diagnose.py`, self-tested)

- C1 safety: no adjudicated-FALSE admitted fact has any eligible class.
- C2 explicit recall: every adjudicated-TRUE admitted fact whose `support_type` is an eligible class has an eligible class. `CROSS_SENTENCE_COREFERENCE` facts are expected to have none, and a match on one counts as a failure: it would mean the rule over-reaches.
- C3 accounting: 293 facts, one primary each.

**JUSTIFIED** (a general extraction milestone may be preregistered) iff C1–C3 pass; otherwise **STOP**. Whole-population coverage by class is reported but has no threshold. These are diagnostic matchers in research code, not a production recognizer.
