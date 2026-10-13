# THERAPEUTIC_PRODUCT_ROLE_QUALIFICATION_CONTRACT v1 — design preregistration

Opened after completed H19 diagnosis c29ffa2 and its handoff. This is design only: no production behavior or qualification precedence changes are authorized. The diagnosis established multiple independent causes, not one implementation-ready fix.

## Question and scope

What evidence establishes that a nominated entity is one therapeutic product, separately from what a particular trial does with it? Define a deterministic, provenance-bearing contract for the three H19 non-asset admission mechanisms without a name blacklist or implicit trial-level inheritance.

Keep four questions separate:

1. Entity identity: one named product, a category, regimen, procedure, measurement or unresolved object?
2. Product kind: therapeutic, explicitly nontherapeutic/diagnostic, dual-use, conflicting or unknown, at the whole-product level?
3. Observation-specific use: therapeutic intervention, diagnostic/imaging use, supportive use, comparator, assay or unknown? Arm type and DRUG/BIOLOGICAL are source claims, not answers to all three questions.
4. Qualification for this candidate population: what exact positive/negative evidence is sufficient, and what remains UNKNOWN? Do not silently turn qualification into ranking or target relevance.

A therapeutic molecule used supportively or in a diagnostic study does not cease being a product. A generic rescue-medication category is not one such molecule. A radiolabeled diagnostic entity is not established as therapeutic merely because its arm is EXPERIMENTAL. A drug authority identifier is identity evidence, not proof of therapeutic purpose. Negative evidence must have an explicit subject and scope; a component, trial, arm or another intervention cannot supply an asset-level veto.

## Frozen design population

Reuse all 23 diagnosis rows, five reference matches, 21 frozen controls, exact non-asset source observations, the 215 existing qualification tests, and current route/veto implementations. The 12 stipulated structural controls include antibody, ADC, peptide, protein, diagnostic, imaging, generic support, named therapeutic used supportively, regimen, procedure, biomarker and reagent. They are synthetic semantic statements, not source authority facts. Pin diagnosis artifacts and test inputs in inputs.json.

Before deriving a final rule, inventory which structural ambiguities are not covered (especially dual-use products, mixed intervention roles, fixed-dose products versus lists, and conflict between exact product-level authority claims). Any necessary additions must be frozen with source/fixture rationale BEFORE derivation. Use existing captured or accepted evidence only; do not acquire sources or inspect holdouts. Do not infer a global negative from absence of therapeutic evidence.

## Required design output

For each row/control: exact entity, source field, claim subject, identity level, intrinsic kind, observation role, positive/negative/ambiguous evidence, route and precedence, proposed qualification outcome, unresolved boundary and provenance. Classify whether current booleans/counters preserve sufficient subject/role information; if not specify the minimum additive provenance representation without implementing it.

Evaluate authority precedence independently from the observed structured-arm problem. The synthetic approved-name/veto conflict establishes order only; it does not license a universal veto policy. Require scope-compatible authoritative claims and expose conflicts rather than silently selecting the convenient source.

## Acceptance and stop conditions

D1: every frozen row/control accounted for with no rewritten H19 labels. D2: no generic category or diagnostic-use observation is certified as a therapeutic product solely from DRUG/EXPERIMENTAL. D3: genuine named therapeutic controls remain supportable, including supportive/comparator uses where their product identity is independently established. D4: no trial-to-every-intervention or component-to-product inheritance. D5: no name-specific, H19-specific or substring blacklist rule. D6: every proposed decision is reproducible from exact subject-scoped evidence; ambiguous/dual-use/conflicting cases explicitly remain unresolved if unsupported. D7: compatibility with all existing qualification controls is explicitly measured; distinguish historical implementation expectations from verified biological controls, and do not alter either after testing. D8: deterministic offline rule table or documented architecture boundary, with zero production changes.

Stop at an implementation-ready, fully frozen and offline-demonstrated contract OR a precise evidence/representation gap. A later implementation requires its own preregistration and controls before code changes. This design is not itself an implementation authorization. Product/component modality, ESG401 nomination, BL-M02D1 acquisition, duplicate identity, target logic/aliases, ranking, indication and human-PoC are out of scope.

The 86 target-identity cases remain closed; H21–H25 untouched; H6–H10 unrun; human-PoC recovery stopped.
