# PRODUCT_VS_COMPONENT_MODALITY_SEMANTICS v1

**STOP at the representation boundary. Design diagnosis complete; no production implementation, adoption or revert.** Population/preregistration: `939806e`; baseline `83f7447`.

## First failure boundary and exact lifecycle

1. Frozen CT.gov NCT07720284, `armsInterventionsModule.interventions[0].description`, source `document:463268b43ea527c591e7`, SHA-256 `4828b8f5fbd71186fa071a4b54ba423670dbea52ac962fb367adf091931dc35e`. The full raw description and exact raw focus offsets are preserved in `results/scope_table.json` and `results/scope_table.md`. Its subject is an ADC comprised of an IgG1 mAb conjugated through a drug-linker to DXd; “tetrapeptide” modifies “linker.”
2. `discovery/adapters.py::_candidate_interventions` concatenates name, description and otherNames, case-folds the text and invokes `QueryVocabulary.modality_in`. That function tests aliases by substring and returns **one string**, selected by requested-modality priority, then alias length, then canonical name. Ontology-wide evidence extraction has no requested-modality priority. In the frozen description, `peptide` wins over `adc`, `igg`, `mab`; `trap` also occurs inside “tetrapeptide.” The `trap` match is not a legitimate fusion assertion. These are diagnostic observations of existing behavior, not approved recognition rules.
3. **First scope loss:** `modality_in` reduces the text to a modality scalar without recording its subject, match span or product/component relation. **First candidate-level promotion:** `_candidate_interventions` places that scalar beside the intervention name; `ClinicalTrialsEvidenceExtractor.extract` makes it an assertion about that hit. A whole-protocol fallback can additionally supply a modality when intervention-specific text has none; this is a separate potential attribution risk, documented but unchanged.
4. `evidence/clinicaltrials.py::_claim` emits `claim:2022030306a59db4acec`, predicate `modality_id`, normalized value `PEPTIDE`, extraction method `clinicaltrials_structured`, version `ctgov_v1`, confidence 0.95, direct observation. It retains the intervention JSON as supporting passage and a broad intervention locator, but no exact matched span or scope relationship. The source is structurally formatted; the actual modality inference is lexical, not an explicit structured product-type assertion.
5. `_fact` emits `fact:71c28d48f9461eb004d3`, fact type `modality_id`, scalar `PEPTIDE`, linked claim ID. `pipeline.py` reattaches the hit subject to the canonical asset via `model_copy`; it does not recover scope. `EvidenceLedger.add_claim/add_fact` store the models without interpreting product/component scope.
6. `gates/engine.py` builds `modality.required` as an IN requirement over whole-candidate `modality_id`. `gates/evaluator.py` compares scalar values after missing/conflicting/stale checks; it has no component-scope check. The saved gate is **FAIL**, and the saved overall disposition is **EXCLUDED**. The cited fact is decisive for the modality failure; no claim that removing it alone proves final eligibility is made.
7. Shortlist reporting consumes exclusions/gate disposition and separately uses authority-modality annotations. Datopotamab already qualifies through DIRECT_APPROVED_NAME and has ChEMBL CHEMBL4297939 “Antibody drug conjugate” / ADC / MATCH annotation. That independent whole-product annotation does not undo the PEPTIDE gate fact. No precedence fix, ranking change or candidate change was attempted.

`results/datopotamab_lifecycle.json` preserves the complete candidate, claim, fact and gate evaluation. `results/h19_rows.json.gz` preserves all 23 previous H19 audit rows (20 emitted rows plus missing references) unchanged, including their claims, facts and first-boundary diagnoses. This is development diagnosis, not a rerun or new primary score.

## Frozen population and scope classification

The frozen population includes the exact H19 witness, 20 synthetic paired/structural text probes, and the complete existing authority-modality, NCIt-modality, optional-modality/dual-target, gate and qualification test files. Existing tests cover adopted structured ADC, antibody, small molecule, cell/gene therapy and unknown behavior; the structural probes add explicit peptide therapeutic versus peptide-component and conjugate contrasts. No new live evidence was acquired.

Focus mentions: **6 PRODUCT_LEVEL, 9 COMPONENT_LEVEL, 1 RELATIONAL_COMPOSITE, 5 AMBIGUOUS**. These are focus-mention counts, not mutually exclusive whole-sentence classifications: the H19 passage contains a product-level ADC mention and component-level peptide/antibody mentions simultaneously. `all_mention_scopes.json` records each actual lexical match independently; `structured_control_scopes.json` records seven existing molecule-type fixture assertions without changing their expected interpretation. `existing_control_inventory.json` identifies 65 test functions; parametrization executes 105 tests.

All synthetic observations are frozen diagnostic probes, not authoritative biological claims or generalization evidence. Terms absent from the current vocabulary (for example a radionuclide component) remain absent; no alias was added. Existing substring matches must not be mistaken for real semantic mentions. The “antibody conjugated to a radionuclide” example requires composite semantics, not automatic inheritance of whichever conjugate alias happens to match.

## Design contract: subject-scoped modality

The general separating property is **what entity the modality predicate describes**, not the length of a matching term:

- A product-level assertion must bind a modality predicate to the same named/resolved therapeutic product, through a structured whole-product field or an explicit grammatical predication. “X is a peptide therapeutic” supplies that relation. A name elsewhere in the document does not.
- A constituent assertion binds the modality to a subpart and binds that subpart to the product. “X contains a peptide linker” describes the linker. This supplies no product-level PEPTIDE fact, even though the same alias occurs and the product is named.
- Multiple assertions may coexist: a whole-product ADC assertion plus antibody, linker and payload assertions. Do not select a single longest alias to erase these relations.
- Composite/conjugate relations preserve constituent identities and relation type. They require an independently supported composite product classification; they never inherit every constituent's modality. Existing ontology vocabulary is not broadened to invent missing composite classes.
- Unbound lists, assay context, comparisons and uncertain subject attachment remain AMBIGUOUS. An ambiguous/component assertion must eventually be non-decisive for a whole-product modality requirement. UNKNOWN does not mean a proven modality match.
- The preregistered evidence hierarchy is retained. Lower-level assertions cannot overwrite whole-product assertions. Competing whole-product claims require an explicit contradiction policy; no new source priority is implemented here.

This is a general semantic relation demonstrated by the paired controls, **not an implementation-ready deterministic prose binder**. Grammatical coordination, negation, multiple products, cross-sentence references, component nesting, source conflicts, historical versions and overlapping aliases still require separately frozen representation/decision contracts. No regex or phrase list is proposed as a validated universal solution.

## Architecture gate and smallest extension

Current `ExtractedClaim` retains passage/locator and generic predicate/value, but has no typed modality scope, exact matched span or parent/component relation. `NormalizedFact` has candidate, type, value, supporting/contradicting claims and confidence; no scope. Generic `Any` storage does not make an incompatible structured modality value safe for existing string consumers. A retained passage allows later re-analysis; it does not mean the relation survived extraction.

Therefore the required distinction **cannot safely be expressed through the existing modality fact interface**. Stop before behavior changes. The smallest next milestone is separately preregistered **MODALITY_ASSERTION_SCOPE_REPRESENTATION v1**, additive and decision-neutral:

- assertion ID and candidate/hit identity with canonical attachment lineage;
- modality value, plus scope PRODUCT_LEVEL / COMPONENT_LEVEL / RELATIONAL_COMPOSITE / AMBIGUOUS;
- source artifact/hash/document and exact field/component locator;
- original text and raw-coordinate span, separate normalized-match coordinates/transformation lineage;
- semantic subject span/identity, parent product and component/relation references when supported;
- explicit asserted/inferred/unknown/conflicting status and extraction rule/version;
- links to existing claim/fact IDs and a separate flag recording whether current legacy decisions consume that fact.

The additive record may initially live alongside legacy facts. No new record or scope annotation may change existing modality decisions in that milestone. Missing scope is AMBIGUOUS, not retroactively product-level. Preserve legacy evidence while exposing why it currently gates. Only a later separately preregistered semantic consumer can restrict gate facts to certified whole-product scope and apply contradiction rules. Existing correct product interpretations and all aliases remain untouched now.

## Acceptance and validation

M1: first loss/promotion precisely identified. M2: all 21 focus witnesses, every matched alias, seven existing structured fixture assertions, 65 existing test functions and all 23 H19 audit rows accounted for. M3/M4: paired grammatical relations explain the distinction while retaining genuine product predicates; no production preservation claim beyond unchanged code. M5/M6: contract prohibits substring/proximity promotion and ambiguous-scope exclusion, but the old engine still exhibits those defects. M7: no asset-specific production exceptions. M8: candidate population and ranking unchanged.

105 existing tests pass; Ruff clean for audit/report scripts. Two seed builds must be byte-identical and input hashes unchanged (see validation.json). Full tests/se was not run because this is diagnosis-only and no production/schema changed. No adoption/reversion, no new modality decisions, no therapeutic qualification change. The saved PEPTIDE exclusion remains present.

Reproduce from repository with `PYTHONPATH=src PYTHONHASHSEED=0 python research/se_product_vs_component_modality_semantics_v1/audit.py --output /tmp/modality_scope_seed0`, then seed 42 into `/tmp/modality_scope_seed42` (fresh directories). Run `report.py` after the seed-0 output exists. Original frozen snapshots are required. No network, discovery or replay is used.

Therapeutic-product-role qualification v2 and the 86 target-component cases remain blocked; human-PoC recovery stopped. H21–H25 untouched; H6–H10 unrun. ESG401 nomination, BL-M02D1 coverage, duplicates and other independent defects remain untouched. No move to nomination is justified by this diagnosis-only boundary.
