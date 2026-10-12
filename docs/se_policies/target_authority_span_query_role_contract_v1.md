# TARGET_AUTHORITY_SPAN_QUERY_ROLE_CONTRACT v1 — design population freeze

Date: 2026-10-12. Baseline: `04b184b`. Status: DIAGNOSIS/DESIGN ONLY.

Use all 1,344 recorded observations from 96 frozen name pairs, all 32 English whole-name mismatches, and 48 newly frozen structural grammar controls. The controls add roles absent from the therapeutic-name-only survey: disease, patient biomarker, mutation, pathway, family/complex, assay, ligand/receptor relation, mixed roles and same-identity/different-role occurrences. They also include existing symbol, affix, ambiguity and separator examples. They introduce no biological aliases and are constructed grammar probes, not biomedical truth claims about disease existence or drug feasibility.

`research/se_target_authority_span_query_role_contract_v1/population_manifest.json` pins the source populations, baseline production model/parser, and structural-control labels. Commit these before any final decision rule or measurement of these controls. Existing biological references remain unchanged. Greek spellings have biological design references but no newly authorized lexical equivalence: unsupported alias is distinct from span or role failure. No forced 32/32 recovery.

Deliver a per-observation audit: exact query, proposed spans and their authority status/provenance, current selections, expected complete span, biological reference versus authority-permitted outcome, role, smaller aliases, first boundary (A span; B role; C identity ambiguity; D unsupported alias; E valid behavior). Retain secondary boundaries rather than hiding unsupported identity under a span label. Preserve every original frozen row. Existing accidental correct-identity fragments are not assumed to have correct provenance.

The design must separate identity candidates from query roles, retain overlapping/nested candidates until arbitration, preserve scientific punctuation and all ambiguity claimants, and specify deterministic abstention. A whole authority match is not a request for that target. Smaller aliases need independent grammatical support. Neither unrestricted substring matching nor blindly choosing the longest match is permissible.

Acceptance is a design target, not permission to change labels: account for every frozen observation and control; zero unsupported identity merge; zero nested-name target promotion; preserve every independently correct adopted parse. Report gaps and contradictions explicitly. If the current model cannot safely represent the distinction, stop at B: document the smallest intermediate representation and the separate preregistration required. Do not claim a passed implementation or a complete classifier when only architectural invariants have been demonstrated.

No production code, target authorities, identity graph, indication, modality, efficacy, acquisition, ranking, qualification, duplicates or routing changes. No live runs/replays. Human-PoC recovery stopped. H21–H25 not inspected; H6–H10 unrun. Full tests/Ruff are required only if production implementation is separately authorized by a demonstrated contract; this study may end at the explicitly requested architecture boundary.

## Final design finding — STOP B (2026-10-12)

**The current parser cannot represent identity and query role independently and safely. No production implementation is authorized by this study.** This is a contract for the minimum representation and decision invariants, not a claim that a complete grammatical classifier is implemented or passes acceptance. The 48 controls were frozen in `d3fa60d` before measurements. Two labels conflict with adopted separator behavior; they remain unchanged and are recorded as failed preregistration expectations.

### 1. Independent questions and exact spans

An authority candidate answers BIOLOGICAL_IDENTITY for an exact span; a role assignment answers QUERY_ROLE for that occurrence. A resolved identity does not supply a role. Two occurrences of the same identity may have different roles. A scientific phrase with an unresolved identity can still have a known target-request role; that produces UNKNOWN, never permission to search its interior for a more convenient target.

The unit is an original-query half-open character interval `[start,end)`. Preserve `query[start:end]` verbatim, including scientific parentheses, commas, digits, hyphens, qualifiers and source-name-internal conjunctions. Store normalized lookup text separately with the exact adopted transformation and offset map. Query wrapper removal (e.g. `anti-`) must not remove scientific name content. No new Greek transliteration, fuzzy comparison, substring inference or authority merge is introduced.

Authority candidate enumeration must be separate from target emission. Consider complete lexical-boundary spans supported by the installed approved authority and retain all claimants with their existing resolver decision and provenance. Existing source precedence and fragment veto are not redesigned here. Do not discard an ambiguous or ineligible longer claim to make an embedded shorter claim unique. The three uncertified merged groups remain uncertified; no elected symbol substitutes for a source-identity certificate.

### 2. Minimum evidence for TARGET role

A role certificate requires both (a) a grammar-delimited therapeutic target position and (b) full coverage of that position by a supported target atom or an explicitly composed target expression. A positive certificate can come from:

- the direct object of an explicit therapeutic `targeting` or `against` construction, with the complete object represented;
- the complete modifier position in an existing therapeutic request, e.g. `Find clinical-stage [TARGET EXPRESSION] therapies`, or `[TARGET EXPRESSION] antibodies`, where the asset/modality head is **outside** the biological name;
- an adopted affix around a complete target atom (`anti-`, `-directed`, `-targeting`, `-blocking`, `-binding`, `-specific`), only if the occurrence is itself in that therapeutic position;
- components of a target expression connected by the already adopted operator/separator grammar, only when each component has its own valid target or ambiguous-target interpretation and no complete atomic authority name owns the connector.

These are the evidence requirements for a future role binder, not a new synonym list and not permission to treat any nearby occurrence as a target. The exact general grammar for selecting competing positions is not yet demonstrated; where two compatible analyses do not agree, the role must be UNRESOLVED. Affixes alone are insufficient inside an assay, patient criterion, or another scientific name.

Known non-target roles must survive as separate records: CONDITION, PATIENT_BIOMARKER, MUTATION_CONTEXT, PATHWAY_OR_FAMILY, ASSAY_OR_MEASUREMENT, and RELATION_ARGUMENT. These may be grouped as NON_TARGET for emission but retain the specific reason. A phrase following a condition construction (`for`/`in` a patient condition) cannot become a target because it contains a protein alias. An expression/measurement/biomarker predicate supplies its own role. A mutation-specific therapeutic target cannot silently degrade to the parent gene: the existing TargetTerm has no variant restriction, so this remains UNRESOLVED_SCIENTIFIC. Do not interpret every `for` or `in` token as a boundary: some authority names contain these words. Role ownership must be established for the complete enclosing phrase first.

A family/complex **name** that the approved authority explicitly identifies as a particular supported target is different from a query for an unspecified family or a complex *containing* a gene. Likewise, a complete receptor name may identify a receptor; `receptor of X` does not license selecting ligand X or inventing a receptor. No word blacklist (e.g. rejecting every name containing `family`, `receptor`, `subunit`, `peptide`) can implement this distinction.

### 3. Deterministic ownership and emission kernel

Given independently established candidate intervals and role certificates:

1. Require exact source-supported identity, an independently certified TARGET role, and complete target-slot coverage. If identity is ambiguous, retain all ambiguity and emit no resolved target for that atom. If the requested entity scope is unrepresentable, emit an explicit unresolved scientific constraint.
2. A full authority-supported atomic name with TARGET role owns its interval. Internal candidate aliases are biological mentions/name components only. They cannot emit targets, modalities or operators merely because they resolve in isolation. If an enclosing CONDITION/BIOMARKER/ASSAY phrase owns the interval, none of its inner biological aliases gains TARGET role.
3. Permit component targets only through an explicit grammatical composition certificate. `CD19 and BCMA` can be a composed target expression; the `and` inside the complete C5 authority name is part of the name. `dual` does not license splitting a known single name to manufacture two targets; preserve the adopted unsatisfied-conjunction blocker.
4. Existing separator behavior is preserved: independent whole-name authority wins within a separator-bearing token; otherwise every component needs existing valid target/ambiguous-target coverage. An ambiguous component is not a resolved component and blocks compilation; it does not erase the other valid component. No automatic rejection of all slash-containing names, and no admission of new Greek-ending separators.
5. Multiple non-contained overlapping candidates or competing grammatical ownership certificates remain unresolved unless all surviving analyses agree on identity, span, role and operator. Source ordering, string length and proximity are not tie-breakers. Keep the alternatives and the conflict in provenance.
6. Missing full-name authority or missing role support is UNKNOWN. An unsupported longer phrase does not make a nested alias decisive. An independently delimited target elsewhere in the same query can still be retained; do not confuse query-level compilation refusal with absence of every resolved target.

Formally, a target may be projected only if `identity_supported AND role_is_TARGET AND ownership_certified AND scope_representable`. The conjunction is necessary; an arbitrary gold role label does not demonstrate that a parser can derive it. This study verifies evidence coverage and the representation conflict, **not** a total role derivation algorithm.

### 4. Required minimal architectural extension (not implemented)

Introduce an internal, typed pre-resolution ledger rather than a parallel target resolver:

| Record | Required contents |
|---|---|
| AuthoritySpanCandidate | deterministic occurrence ID; original offsets/surface; lookup text and normalization/offset provenance; snapshot version; resolution status; all authority claimants; certified identity reference if available; alias/source-record/identifier provenance; identity eligibility and reason |
| QueryRoleBinding | occurrence or enclosing phrase ID; role independent of identity; governing predicate/head and offsets; clause/owner interval; coverage/composition certificate; conflicting/containing candidates; decision status and named rule |
| ProjectionDecision | candidate ID; accept/ambiguous/unresolved/non-target; all four emission predicates; owning phrase ID; exact reason; source and grammar provenance |

No arbitrary confidence score is needed. Use explicit SUPPORTED / AMBIGUOUS / UNSUPPORTED / UNRESOLVED statuses. Stable IDs derive from query, offsets and snapshot; serialization and ordering must be deterministic. A non-target candidate may carry a resolved biological reference in this **separate ledger**. Do not weaken IntentSpan's current validator or give a non-target candidate to TargetExpression.

Perform authority candidate discovery and query-role hypothesis collection without consuming tokens. Arbitrate supported ownership, then project accepted targets into the existing IntentSpan/TargetTerm structures. Keep rejected and unresolved candidates in the ledger for audit. Only after projection may the existing operator/compilation layer consume accepted target spans. Existing modality/indication algorithms are not changed here; future integration must demonstrate that their inputs/outputs preserve the frozen contracts, including the name-internal `peptide` collision. Adding the ledger without defining this integration would not repair parsing.

### 5. Why current architecture is insufficient

- `IntentSpan.reference_belongs_to_target` rejects a TargetReference on RESIDUAL and UNRESOLVED_SCIENTIFIC. The exact runtime probe accepts TARGET and rejects both other kinds. `candidates` is an untyped list used for ambiguity, and `explanation` is prose; neither supplies a separate typed identity/role contract.
- `parse_query` consumes spans as soon as a vocabulary wins; overlapping alternatives are skipped. Authority lookup is limited to two tokens after status/modality/evidence/class handling. The complete identity and competing role evidence are never jointly represented.
- Every resulting TARGET span becomes a TargetTerm. There is no independent role gate between resolving an alias and adding a target requirement.
- Later indication compilation can recognize condition spans, but does not retract target assignments already placed in SearchIntent. Reusing the role index may be appropriate in a future preregistration; silently changing indication or downstream target facts now is not.

This does not mean Python or Pydantic cannot represent the problem. It means the current adopted schema/control flow cannot do so without a new typed intermediate representation and arbitration step. Increasing a length limit or adding a longest-name prepass alone does not provide that distinction.

### 6. Frozen population accounting and limitations

All 1,344 observations are audited, with complete query, candidate spans, current selections, expected full phrase, whole and nested authority evidence, role conflicts, first boundary and A–E categories. First categories: A 665, B 0, C 84, D 413, E 182. Fourteen observations additionally show B (name-internal modality). These are descriptive categories, not acceptance scores. The 48 added controls supply direct role errors absent from the original therapeutic-slot-only population.

All **32 English mismatches / 224 frames** have exact complete-name support to the existing certified reference. Their first boundary is A; they are *potentially* addressable once target-slot ownership is represented. None requires new Greek/common-name admission. This is not a measured claim of 32 production recoveries.

Across the full 96 pairs, 90 English whole names are source-certified; six remain C (three ambiguous names, three uncertified merged identities). All 96 Greek spellings lack whole-name support under the adopted resolver, so no lexical equivalence is introduced. A full-name-only projection would lose **21 frames / three existing correct-identity Greek names**: those preservation obligations remain unmet. A safe component/appositional rule is not inferred merely to recover them.

Structural baseline target sets agree with **26/48** frozen labels; this is not full-intent accuracy. Review finds a PD-1 authority ambiguity (C) and two frozen label errors (S041/S042). Their original labels, results and conflict explanations remain recorded. S041 incorrectly expected no target for a whole source-supported separator name. S042 incorrectly expected a valid target to disappear when the other component is ambiguous. These errors preclude declaring the frozen design population passed. They are not patched, excluded from the denominator or changed retrospectively.

The mutation controls additionally expose BRAF resolving to the installed KIAA1549 component. This is an independent source-identity concern, recorded without changing that graph or asserting a new equivalence. Role rejection must not depend on this particular alias or elected symbol.

### 7. Decision and next narrow milestone

**STOP B: representation/arbitration extension required; no production change; no adoption claim.** The scientific invariants above are explicit, but a total implementation-ready role selector has not been demonstrated and the frozen controls contain two conflicting expectations. An implementation milestone is therefore not opened.

The next possible milestone is a separately preregistered **TARGET_MENTION_ROLE_REPRESENTATION v1**, initially decision-neutral: retain exact authority candidates and independent role/provenance records, with all existing compiled targets/constraints unchanged. Before any behavior-changing arbitration study, freeze corrected successor control labels with explicit links to these failed expectations, plus the three unmet Greek preservation cases; never edit this study's labels. A later arbitration milestone must run all 4,704 frozen parses, adopted affix/separator/indication controls, full tests/se and Ruff against preregistered deltas. Do not implement the representation now under this design-only stop condition.

Human-PoC remains stopped. No holdout query was inspected or run. No target authority, graph, indication, modality, qualification, deduplication, ranking, source acquisition or shortlist production behavior changed.
