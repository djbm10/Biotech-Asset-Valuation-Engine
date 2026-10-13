# MODALITY_ASSERTION_SCOPE_REPRESENTATION v1

Preregistration **74a6f63**; red-first controls **ea639dd**; implementation **aedc91f**. Baseline **40f21f1**. This is an additive diagnostic API, with no production gate consumer. **ADOPTED: representation only.** All R1–R13 checks pass; no semantic v2 rule is implemented here.

## Representation boundary

The earliest stable boundary is the original individual source intervention record: candidate/hit identity, intervention name/otherNames, raw description, and local syntax coexist there. `scoped_modality_assertions` accepts those exact fields before legacy concatenation/scalar selection. The current extractor and legacy models are unchanged; the new API can be called alongside them and is exercised directly from pinned raw source artifacts by this milestone's diagnostic runner. It is deliberately **not automatically wired into live extraction or RunResult**. This adopts a reusable representation API and validated side artifacts, not a claim that all future live assertions now carry scope.

The immutable additive model carries candidate ID, nullable ontology modality, scope, raw mention/product/component/relation spans, relation types, exact source/artifact/hash/record/field and source names, raw text, rule/version, status, transformation description, stable content-derived assertion ID and legacy fact associations. Every record has `legacy_decision_bearing=false`. One legacy fact may coexist with many scoped assertions. Links describe coexistence with original source evidence, not reconstructed historical causal lineage.

The frozen closed grammar recognizes explicit named-product predication, possessed components and conjugation; component heads and peptide morphology were registered before implementation. Every lexical match is retained separately, including ambiguous embedded aliases. Exact source names establish the local subject; source-field membership alone does not establish every sentence's subject. No cross-sentence carry-forward, LLM, inferred alias or open-ended NLP was introduced. Raw constituent descriptions without an adopted ontology modality retain `modality=null` (viral vector/radionuclide/cytotoxic), not a new alias or guessed modality class. COMPOSITE_RELATIONAL asserts a relation, not authority certification of any overlapping composite alias.

## Frozen results

All **33** frozen focus expectations pass: 21 original witnesses and twelve additional structural controls. The separate repeated-peptide test shows one product-level peptide and one component-level peptide in the same sentence. **34 focused tests pass.** Original 21 legacy scalar outputs remain identical.

Across all matching assertions in the 33 controls (not one count per sentence):

| Scope | Count |
|---|---:|
| PRODUCT_LEVEL | 17 |
| COMPONENT_LEVEL | 14 |
| RELATIONAL_COMPOSITE | 2 |
| AMBIGUOUS | 19 |

All **23 H19 audit rows** and **1,181 saved candidate qualification decisions** remain unchanged. Among these H19 rows there is one stored modality fact; it has five coexisting raw-source assertions: **one PRODUCT_LEVEL, two COMPONENT_LEVEL, zero composite, two AMBIGUOUS**. Exact bounded aliases are intentionally stricter than legacy substring selection; `trap` inside tetrapeptide and `igg` inside IgG1 do not gain confident scope authority. The peptide linker remains component-level and the ADC predicate remains product-level. No claim of recovering every biologically interpretable constituent is made.

Datopotamab's legacy `PEPTIDE` fact (`fact:71c28d48f9461eb004d3`) and `modality.required FAIL` remain unchanged. Its correct qualification and independent ADC authority annotation are unchanged. No shortlist improvement is claimed. Synthetic controls have no real gate; diagnostics label that explicitly rather than fabricating one.

## Neutrality and provenance

- Independent seed-0/seed-42 builds are byte-identical, including assertion IDs.
- Every emitted span round-trips to the raw input text. H19 source fields and source-name bindings come from pinned original snapshots. All frozen input hashes are verified.
- All pre-existing production source files are unchanged. Only the new module and its tests were added; it imports no gate/fact/qualification code, and no existing production path imports it.
- An additional check reproduces **284 saved modality gate outcomes** using their recorded observed fact IDs, with zero status/fact-ID changes. This is not a live pipeline replay or a new entailment evaluation. An invalid exploratory all-stored-facts probe is retained and explained in `results/gate_harness_note.md`; it was not used as acceptance evidence and no production rule or expected outcome was patched.
- **Full tests/se: 1,873 passed, three existing xfails, zero failures/errors.** Ruff clean over src/bve/se, tests/se and new research code. Results are recorded in `results/quality.json` and original logs/XML. The focused red-first failure was missing-module collection before implementation, preserved in `results/red.log`.

## Acceptance interpretation

R1/R3/R11 neutrality is established by unchanged legacy-file hashes, saved-row preservation, scalar/gate-input reproduction, no new consumer, and regression tests. R2/R4–R8 exact frozen scope expectations pass; unsupported grammar remains AMBIGUOUS. R9 raw spans and original source field/identity lineage are preserved. R10 independent artifacts match. R12 no out-of-scope paths changed. R13 requires full tests/se and Ruff; see final quality result, not only focused tests.

The scope grammar is intentionally narrow and is not a universal biological text parser. It has no general coreference, dependency parser, authority contradiction policy, component-identity resolver or composite-modality ontology. Those limitations must remain visible; this result does not authorize a semantic gate change or establish untouched-query generalization. Any future consumer needs its own frozen scope and contradiction controls.

## Reproduction and artifacts

`PYTHONPATH=src PYTHONHASHSEED=0 python research/se_modality_assertion_scope_representation_v1/audit.py --output /tmp/modality_repr_seed0` (fresh output directory), then seed 42 with a separate directory. Frozen raw H19 artifacts are required. The API has no network effects. Run `tests/se/test_modality_scope.py` for the frozen expectations. `check_gates.py` reproduces saved gate inputs; it does not reevaluate source entailment. The source manifest pins existing code/data, not newly created module output.

`witnesses.json` contains candidate/source text/mentions/scope/relations/provenance and current scalar/fact/gate per control. `h19_assertions.json` and `h19_legacy_links.json` give source-grounded one-to-many associations. `h19_rows_unchanged.json` preserves all prior rows. `summary.json` records exact counts; `hashes.json` covers the canonical audit artifacts (additional reports/logs are outside that manifest).

After adoption the next milestone may be separately preregistered PRODUCT_VS_COMPONENT_MODALITY_SEMANTICS v2, consuming scoped assertions only after its own decision contract is frozen. It is not preregistered or implemented here. ESG401 nomination remains later independent work; BL-M02D1 remains source coverage. Therapeutic qualification v2 and the 86 target-component cases remain blocked; human-PoC recovery stopped; H21–H25 untouched; H6–H10 unrun.
