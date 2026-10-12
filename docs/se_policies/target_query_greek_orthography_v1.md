# TARGET_QUERY_GREEK_ORTHOGRAPHY v1

Status: PREREGISTERED rules and oracle derivation, before oracle generation and production implementation. Parent TARGET_QUERY_ALIAS_COVERAGE v1 remains open. Source-identity diagnosis `0fcfa5a` is a prerequisite; the identity/retrieval interface is already adopted.

## Hypothesis and scope

Greek-letter spelling of an existing, explicitly asserted target name can be understood without adding a biological equivalence. This is a query-only fallback, not a new cross-source identity join. Existing exact resolver decisions take precedence and remain byte/semantically unchanged. No common-name admission, global resolver repair, human-PoC, ranking, qualification, identity consolidation, modality, indication, source acquisition or shortlist changes.

The three diagnosed merged groups cannot certify one interchangeable gene identity. No new aliases may inherit those groups. Their existing resolver outcomes are not repaired in this milestone; abstention for new spellings must use general source-record checks rather than target IDs or conflict-flag presence.

## Exact rule

1. Add a query-target resolver used only by the intent parser. Obtain the existing target resolver result first. Return any existing RESOLVED or AMBIGUOUS result unchanged, and return the existing no-snapshot behavior unchanged. Only an UNRESOLVED query may use this fallback.
2. Require at least one literal canonical Greek letter (the 24 letters alpha through omega, upper/lower case). MICRO SIGN, variant glyphs, Cyrillic and Latin lookalikes are not admitted by the new rule. Do not normalize a new whole-name alias across `/` or `×`; existing separator parsing remains responsible for those boundaries.
3. Form a comparison key: apply existing target lookup case/separator/whitespace normalization; replace standalone English Greek-letter names with their corresponding Greek letter (English letter boundaries, so alpha2 qualifies but alphabet does not); surround each canonical Greek letter with whitespace and collapse whitespace. Standard names are alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega. All remaining characters, digits, words and biological qualifiers remain present. No fuzzy distance, substring search, qualifier deletion or target-specific mapping.
4. Require a non-Greek Latin alphabetic anchor after removing the Greek qualifier tokens; isolated Greek letters or Greek-plus-number labels do not establish a biological target in this study. This conservative scope is frozen before evaluation.
5. Build a local index of existing TARGET aliases of types SYMBOL, APPROVED_NAME or SYNONYM containing a supported Greek qualifier under the same comparison relation. Use all claimants, including ineligible entities, when checking ambiguity. Do not make an alias unique by filtering conflicting claimants away. No DRUG/DISEASE lookup or global alias table changes.
6. Admission requires exactly one claiming existing entity. Multiple claimants return AMBIGUOUS with sorted candidates and no certified reference. For a sole entity, require exactly one nonempty canonical symbol across all contributing source records, agreement with the entity's elected symbol, exactly one distinct Ensembl gene ID across all contributing records, and an Open Targets record identifying that same gene. Multiple genes/symbols or missing gene identity return UNRESOLVED. Shared aliases elsewhere on the entity are not automatic rejection.
7. At least one matching original authority alias must independently resolve through the unchanged resolver to that same entity. This preserves the existing fragment veto and alias safeguards. Choose a certifying original alias deterministically by (alias type value, casefolded spelling, exact spelling). Preserve its exact source/record keys and identifier provenance in a ResolutionBasis, identify the orthographic rule, and retain the original observed query. Never create a new entity. The TargetReference carries the original resolver's exact entity/version.
8. Source retrieval uses the already adopted reference/surface interface; it continues to use the original biological canonical symbol and existing authority search aliases. Do not insert ontology IDs or automatically add generated Greek strings to source requests.
9. Bump intent compiler version from `intent_v1__target_reference_v1` to `intent_v1__target_reference_v1__target_query_greek_v1`. Underlying authority snapshot version and global target resolver are unchanged. Legacy queries may differ only in this explicit compiler-version metadata. Update the active compatibility projection for this exact declared version and independently validate query references through the new query resolver. Do not edit any historical population, source hash, acceptance receipt or scorer.

## Frozen population and oracle derivation

Use all 672 forms / 4,704 query frames and 16 controls already frozen in `se_target_query_alias_coverage_v1`; all 96 Greek proposals remain part of the evaluation, including long-name and ambiguous cases. The installed authority records and resolver code are hash-pinned by the oracle manifest. The three source-identity traces and seven official gene identities remain immutable.

The accompanying `freeze_greek_query_oracle.py` is frozen with these rules before execution. It derives expected raw query-target outcomes from existing authority aliases and all contributing identities, records exact matching claims and abstention reasons, and captures complete baseline parser outputs for new explicit controls. It never calls a candidate query resolver. Commit its derived labels/manifest before production changes. Do not revise the rule or labels to improve subsequent candidate results. If derivation exposes a contradiction with the scientific controls, record it and stop this candidate before implementation.

Add explicit controls for all 24 letters in an independent synthetic authority fixture, attached/spaced/hyphenated spelling, wrong qualifiers, digits, embedded English substrings, confusables, missing snapshot, multi-gene/multi-symbol merges, ambiguous competing claimants (including an ineligible competitor), original-alias fragment veto, and source provenance. Their explicit expected decisions must be frozen before implementation. Synthetic data test the relation, not biological facts.

## Acceptance — every criterion required

G1: All existing direct global resolver outcomes stay unchanged. For the 576 non-proposal frozen forms, query resolution and all 4,032 parser frames preserve complete existing scientific fields/spans/provenance, apart from the declared compiler-version component. Preserve all 16 original controls except the preregistered H17 Greek recognition improvement; H20 factor XI and bare F11 ambiguity remain unchanged.

G2: Every raw query-target decision in the independently frozen 96-case authority oracle matches exactly, including abstentions and candidate sets. Every accepted new alias has its original authority spelling, unique claimant, coherent single-gene source record set and exact existing entity/version recorded. No minimum admission quota overrides ambiguity.

G3: All three diagnosed multi-gene Greek proposals remain non-RESOLVED. Original ambiguous spellings cannot become unique through claimant filtering. All explicit positive/negative synthetic controls pass.

G4: The exact frozen H17 query resolves TARGET:IL4R and compiles complete offline discovery/source plans with no namespace literals and no query rewriting. This is diagnostic development evidence only. H20 remains unresolved pending separately reviewed common-name evidence.

G5: Across all 672 forms and seven frozen frames, every newly emitted orthographic TARGET span resolves as a complete authority alias under the frozen oracle relation. For each Greek proposal, no new target outside its independently certified whole-name entity may be introduced; an abstaining whole-name oracle permits no newly added target. Pre-existing parser limitations are recorded, not hidden. Long names need not newly compile, but any new false target or unsafe partial-fragment attribution fails the milestone.

G6: Affix, separator, duplicate-mention and wrong-subunit controls preserve their frozen expected biological identities/operators/refusals. Equivalent English/Greek mentions deduplicate by the existing certified identity. No changes to the affix or separator implementation are allowed.

G7: All 103 current scientific compatibility cases and 1,791 historical source checks pass under only the declared compiler-version metadata projection. Historical artifacts/scorers are byte-identical. Previously adopted target-reference source-request, ambiguity and serialization tests pass.

G8: Exact new intent/problem/plan/provenance outputs are identical under hash seeds 0, 1 and 42. This does not claim to fix the separate capitalization nondeterminism milestone.

G9: Full tests/se: all non-xfail tests pass; the three existing xfails remain unchanged. Ruff clean for src/bve/se, tests/se and new scripts.

G10: Production changes restricted to a new query-target orthography module, the parser's target-resolver import/delegation, and the compiler-version constant in intent.py. New tests/evaluation scripts and the explicit compatibility validator/version projection update are allowed. No global resolver, source snapshot, human-PoC, candidate qualification, ranking or duplication behavior changes. No live asset search/replay. H21–H25 remain untouched; H6–H10 secondary/unrun.

## Decision

Commit rules, then frozen derived expectations before implementing. Focused development precedes one formal evaluation. On any formal criterion failure, record the failure and normally revert; no post-result patching or label changes. On all-pass, adopt and report exact admissions/abstentions, source coverage limitations and commits. Parent target-recognition work remains incomplete until common-name admission is separately adopted/reverted; do not run primary holdouts yet.
