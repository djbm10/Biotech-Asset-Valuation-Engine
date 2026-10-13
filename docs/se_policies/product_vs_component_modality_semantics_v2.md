# PRODUCT_VS_COMPONENT_MODALITY_SEMANTICS v2 — design preregistration

Representation prerequisite adopted in 7df34fb (implementation aedc91f; preregistration 74a6f63). This is a separately registered **design phase**, not permission to implement a gate rule. No scope rules or representations may be silently retuned based on semantic outcomes.

## Question and inputs

Determine whether the adopted scoped assertions can safely replace or qualify existing whole-candidate modality assertions without losing supported whole-product evidence. Use the frozen representation population/results, all 23 H19 diagnosis rows, existing modality/authority/gate controls and the complete baseline corpus of modality facts. H19 is development data. Do not inspect H21–H25 or run H6–H10. Closed qualification, target-component and human-PoC work stays closed.

Before deriving a final decision rule, hash-freeze all additional legacy modality facts, their source/entailment inputs, scoped assertions and gate outcomes, plus necessary contradiction/missing-scope/composite controls. Freeze product-level expectations independently of downstream shortlist position. A nullable modality is not a supported ontology identity. Explicit scope does not alone certify identity, source reliability or entailment.

## Candidate principle to evaluate, not yet adopted

Only a sufficiently attributed PRODUCT_LEVEL assertion may contribute whole-candidate modality. COMPONENT_LEVEL must not independently type the whole product. AMBIGUOUS remains non-decisive. COMPOSITE_RELATIONAL must follow a separately explicit composite policy rather than inherit a constituent or alias match. Evaluate genuine whole-product conflicts, unrepresented source routes and admitted-versus-stored facts before defining precedence. Preserve current adopted authority identity/modality semantics unless separately shown incorrect.

## Design acceptance and implementation gate

1. Account for every baseline modality fact and source route, including unavailable scope and prior entailment rejection. Do not run an all-stored-facts comparison as though it were the pipeline's admitted inputs.
2. Identify exact general rules and predicted gate deltas, including unchanged positives, transitions to UNKNOWN, legitimate new PASS and remaining conflicts. Never optimize datopotamab or the H19 top 20.
3. Demonstrate that a consumer can use the existing scoped representation without inventing raw scope downstream, adding aliases, changing qualification/ranking/nomination, or rewriting scope rules. If missing representation/identity evidence prevents this, STOP and document it.
4. If a rule is ready, commit a separate implementation preregistration with exact population/expected deltas and red-first positive/negative tests **before production edits**. Full tests/se, Ruff, deterministic frozen evaluation and no post-result patch loop remain mandatory.
5. If no rule is ready, retain this design boundary. No blanket deletion of existing facts or whole-product authority inheritance is authorized by this document.

No implementation in the representation milestone. No live source acquisition/replay or protected holdout use. ESG401 nomination remains a separate later defect; BL-M02D1 remains source coverage.
