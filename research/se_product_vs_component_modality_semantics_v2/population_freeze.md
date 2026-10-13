# Execution population for the unchanged 65cddd1 design

Baseline 258b425. This is the required additional population freeze, not a replacement design or semantic implementation preregistration. The original policy is hash-pinned and remains unchanged.

Complete available frozen baseline is the saved H19 result (all candidates/facts/claims/entailment/gates), all 23 H19 rows, all adopted scope artifacts/33 controls, existing modality/authority/gate tests plus existing evidence extractor tests. Production emitters and gate-admission code are pinned. No holdouts or newly acquired sources are included. H19 contains one stored modality fact; do not extrapolate broad semantic preservation from it.

Add 14 exact structural controls before using the API on them: six whole-product positives, three compound-modifier non-product mentions (peptide-linked conjugate, antibody-derived cell therapy, small-molecule-loaded nanoparticle), missing subject, unsupported coreference, relational conjugate, and two equal-authority conflicting product assertions. NON_PRODUCT permits component or ambiguous representation, but never independent whole-product authority. The modifiers describe a linkage/origin/loading relationship; the noun-phrase head describes the product. This is a structural test, not a name exception. No new scope recognizer is specified or permitted.

Conflicting product assertions must be jointly non-permitting; neither source gets priority. Missing scope and relational-only evidence cannot independently establish a candidate modality. Product-level status alone is a candidate for semantic use, not certification of identity, entailment or predicate-head attachment.

First audit original-source routes and scope adequacy, preserving all outputs. If a required non-product control receives PRODUCT_LEVEL, the adopted representation has not established safe product scope for gate consumption: stop under item 3 of 65cddd1. Do not patch scope extraction, blacklist phrases, or publish a production-ready semantic delta. Instead record an exact proposed-action register with BLOCKED/NOT_AUTHORIZED where needed. No blanket fact deletion is licensed by this audit.
