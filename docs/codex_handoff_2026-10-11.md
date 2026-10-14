# 2026-10-14 — TARGET_ALIAS_AUTHORITY_SOURCE v2: STOP — target-alias work PARKED

Prereg `42b94f7`; read `research/se_target_alias_authority_source_v2/README.md`. 26,230-name universe; 113 independent negatives (DRUG aliases / NCIt non-product); 400-target disjoint sample reviewed blind by a separate agent. Policy A (NCIt protein, single chain) admits 20 negatives (angiotensin, vasopressin, human albumin…) and 14 reviewer-unsafe names (isoforms, precursors, families, non-human P450s), plus `statin-like`; coverage 1.5%. Policy B (HGNC current) is safe-ish but has ~0 coverage and no factor XI. Historical names include disease names. H20 factor XI → F11 works offline but only under unsafe policy A; H17 unchanged. No implementation; no v3. Next: CT.gov posted-results source-availability survey. H21–H25 sealed; H6–H10 unrun.

---

# 2026-10-14 — TARGET_ALIAS_AUTHORITY_SOURCE v1: computed JUSTIFIED_EXCLUDING_H17 — implementation NOT authorized

Prereg `7d5c7ad`; read `research/se_target_alias_authority_source_v1/README.md`. Frozen HGNC (complete) + NCIt 26.09d protein records: 186/233 new names are claimant-unique; 49 are reachable under the 2-token cap; 29/192 entities (15%). H17 `IL-4Rα` has no exact spelling in any authority and is not repairable without an orthographic transform. H20 `factor XI` is certified via NCIt C201572 → HGNC:3529, and the injected offline chain compiles 5 plans carrying TARGET:F11. Post-measurement inspection found `statin` certified to EEF1A2 (an HGNC previous name), EC reaction-class codes, and 80 historical previous names: claimant uniqueness is not safety. The rubric is not amended, so this is a mechanical pass, not authorization. Next: preregister v2 with ordinary-word/drug-class, EC and previous-name controls frozen first. No production change. H21–H25 sealed; H6–H10 unrun.

---

# 2026-10-14 — HUMAN_POC_PRECISION_FIRST v1: DESIGN STOP (no structured route exists)

Prereg `729c500`; read `research/se_human_poc_precision_first_v1/README.md`. The only `ClinicalResult` constructor hardcodes `incomplete_reporting=True` with no effect size, so the structured human-PoC route is unreachable. The CT.gov connector keeps only `protocolSection`, and 0 of 1,932 snapshots have `resultsSection`. All 151 human-PoC observations (159 distinct passages; 97 adjudicated true, 29 false) are prose. Structured-only would give 0 confirmed and turn 64 gate PASS into UNKNOWN; R3 and R4 fail (no non-decisional status in `VerificationStatus`). Implementation NOT authorized. A degraded safety mode is described, not authorized. Next: TARGET_ALIAS_AUTHORITY_SOURCE v1; then CTGOV_POSTED_RESULTS_SOURCE v1 as the real human-PoC prerequisite. H21–H25 sealed; H6–H10 unrun.

---

# 2026-10-14 — SE_VALIDATION_READINESS_REVIEW v1: NO-GO — keep H21–H25 SEALED

Rubric `6f024d4`; read `research/se_validation_readiness_review_v1/README.md`. Technical GO (deterministic; 1,941 passed / 3 xfail). Scientific NO-GO, measured on current code: the exact H18/H19 false human-PoC sentences are **still accepted**; H17 and H20 still yield zero target spans (refusal); datopotamab structured modality is still PEPTIDE; all six brands still fail `resolve_identifier`; qualification and ordering code are unchanged since frozen engine `5feee85`. No H16–H20 failure is demonstrably corrected; every adopted change since is an interface refactor or decision-neutral. Ranked next: (1) HUMAN_POC_PRECISION_FIRST v1 (structured-route-only human-PoC, prose → UNVERIFIED; needs an explicit user decision since human-PoC recovery was stopped); (2) TARGET_ALIAS_AUTHORITY_SOURCE v1 (HGNC/UniProt names, a source not grammar); (3) review ordering by target evidence. Nothing opened. H6–H10 unrun.

---

# 2026-10-14 — TRADE_NAME_ASSET_IDENTITY_DIAGNOSIS v1: STOP

Prereg `e0b3750`; read `research/se_trade_name_asset_identity_diagnosis_v1/README.md`. All 6 H18/H19 brand duplicates resolve through single-claimant TRADE_NAME; the first boundary is `_IDENTIFIER_ALIAS_TYPES` (intended). 69 independent dev trade-name-only pairs: 25 are ordinary or company words with a single claimant (36%), so single-claimant TRADE_NAME (T0) certifies 29 false pairs. Source-corroborated T1 has 0 false pairs but certifies 2 biosimilars without a product relation, reaches only 47% of true brands, and doesn't fix TRODELVY. No contract is justified; no production change. Next, if pursued: preregister a decision-neutral PRODUCT_LEVEL_IDENTITY_RELATION v1. H21–H25 untouched; H6–H10 unrun.

---

# 2026-10-13 — ESG401_CANDIDATE_NOMINATION_DIAGNOSIS v1: STOP

Prereg `505121d`; read `research/se_esg401_candidate_nomination_diagnosis_v1/README.md`. ESG401 is first lost at nomination input selection: only `interventions[].name/otherNames` are read, the arm's intervention is the class label "TROP2 ADC", and no arm-description route exists. The relation is an investigator-choice alternative, and the schema has no alternative relation. Independent 45-arm development sample: 41/45 product mentions are already nomination inputs, 4 uncovered are background lymphodepletion, and there are 0 other product alternatives. So J1 (failure class) FAILS. The existing name extractor over arm prose mints 29 ordinary words (J2 FAILS). ARM_ALTERNATIVE_CANDIDATE_NOMINATION is not justified. No production change; no ESG401 exception. Modality stays parked. H21–H25 untouched; H6–H10 unrun.

---

# 2026-10-13 — PRODUCT_VS_COMPONENT_MODALITY_SEMANTICS v4: STOP — modality gating PARKED

Design `8ca2a76`; R3 policy `78c3694` (frozen pre-measurement); read `research/se_product_vs_component_modality_semantics_v4/README.md`. 172 distinct facts / 293 rows: 4 RETAIN, 167 UNKNOWN_REVIEW, 1 UNKNOWN_CONFLICT. R1/R4 pass (0 false retained, conflict → UNKNOWN). R2 fails: CC312's appositive is blocked because `trispecific` is a MULTISPECIFIC_ANTIBODY alias (frozen same-modality guard; not patched). R3 fails: 7/8 true admitted facts go to UNKNOWN. On the 13 adjudicated facts, precision rises 0.62 → 1.00 while recall falls 8/8 → 1/8, which is not deployable. Modality gating is parked; datopotamab's false PEPTIDE exclusion remains. Next: separately preregister the ESG401 candidate-nomination diagnosis (not started). H21–H25 untouched; H6–H10 unrun.

---

# 2026-10-13 — MODALITY_SCOPE_PRODUCT_DESCRIPTION v1: Rule A ADOPTED, Rule B removed

Prereg `ce9aa9b`, red tests `8bdb992`; read `research/se_modality_scope_product_description_v1/README.md`. Independent 103-unit sample from sources disjoint from the protoid baselines (tac01_control_r2 CT.gov + aacr_safety abstracts), blind labels. Appositive rule A: 5/5 recall, 0 unsafe, adopted (`explicit_product_appositive`). Premodified copula rule B: 2 unsafe (radioconjugate Bexxar; class-label subject "Immune Checkpoint Inhibitor"), removed under the frozen per-rule fallback. Class-of, CT.gov name and otherNames are unsupported (no examples / identity boundary). No frozen assertion changed; 5 false admitted facts unsupported; still no consumer. Full tests/se 1,941 passed, 3 xfail; Ruff clean; deterministic. Process errors disclosed in the README (a display-compression hook misled a predicted delta). Next: v4 semantic design preregistered (`docs/se_policies/product_vs_component_modality_semantics_v4.md`), not executed. ESG401 not started; H21–H25 untouched; H6–H10 unrun.

---

# 2026-10-13 — MODALITY_PRODUCT_DESCRIPTION_COVERAGE_DIAGNOSIS v1: JUSTIFIED (narrow)

Prereg `19c9074`; read `research/se_modality_product_description_coverage_v1/README.md`. Re-adjudication: 13/13 v3 labels agree (limits: CLN-978 needs cross-sentence coreference, two generic-class candidate names, BNT162b2 only via otherNames). v3 denominator: categories exclusive (282+11), the conflict is a flag; **the 293 are rows = 172 distinct facts (121 in both runs)**. Coverage: 42/293 rows have an explicit product structure (APPOSITIVE 15, NAME_SELF_DESCRIBING 11, COPULA 10, OTHERNAMES 4, CLASS_OF 2); 199 co-occurrence, 50 name/modality absent, 2 registry category; PEPTIDE 0/32. Computed readiness: C1 safety, C2 explicit recall and C3 all pass, giving JUSTIFIED. No production change; v3 unadopted. Recommended next (not preregistered): decision-neutral `MODALITY_SCOPE_PRODUCT_DESCRIPTION v1`. ESG401 not started; H21–H25 untouched; H6–H10 unrun.

---

# 2026-10-13 — PRODUCT_VS_COMPONENT_MODALITY_SEMANTICS v3: DESIGN STOP (R3)

Design `b12ee79` unchanged; freeze `7dd05ae`; read `research/se_product_vs_component_modality_semantics_v3/README.md`. Population: 293 modality facts from frozen non-holdout baselines tac01/mint5_protoid_v1, 13 gate-admitted. R1 (control safety) passes: the former v2 modifier failures are fixed. R3 fails: **0/293 facts get PRODUCT_LEVEL support** (282 ambiguous, 11 no scoped evidence), so a consumer would withdraw all 8 true admitted TCE/vaccine facts alongside 5 false ones. The representation is safe but lacks recall on appositives, "class of", titles and non-hyphenated premodifiers. Implementation NOT authorized; no production change. Next (if pursued): a separately preregistered representation-recall milestone. ESG401 not started; H21–H25 untouched; H6–H10 unrun.

---

# 2026-10-13 — MODALITY_SCOPE_HEAD_ATTACHMENT v1 ADOPTED

Preregistration `07cb021`; red-first `248a05e` (46 red / 9 green); adoption commit follows. Read `research/se_modality_scope_head_attachment_v1/README.md` and policy `docs/se_policies/modality_scope_head_attachment_v1.md`. `explicit_product_predicate` now certifies only the predicate noun phrase's head designation (hyphenated premodifiers before it, generic product nouns after it); modifiers become AMBIGUOUS `product_phrase_not_head`, coordination is AMBIGUOUS, and non-modality heads invent nothing. Seven of 78 frozen existing assertions changed, all preregistered: the three v2 modifier errors fixed, ADC/cell-therapy heads now PRODUCT_LEVEL, and the `antibody` sub-span inside "antibody-drug conjugate" is no longer a whole-product antibody. The 33 v1 witnesses and H19 are byte-identical. The independent checker has no verdict constant, and its self-test shows it fails, passes and flips. Full tests/se 1,928 passed, 3 xfail; Ruff clean; still decision-neutral (no importer).

Next: `PRODUCT_VS_COMPONENT_MODALITY_SEMANTICS v3` design (preregistered separately, not executed). ESG401 not started. H21–H25 untouched; H6–H10 unrun.

---

# 2026-10-13 — PRODUCT_VS_COMPONENT_MODALITY_SEMANTICS v2: DESIGN STOP

Design `65cddd1` and population freeze `43e30ce` executed unchanged. Read `research/se_product_vs_component_modality_semantics_v2/README.md` and `results/`. Verdict **STOP_UNSAFE_PRODUCT_LEVEL_CERTIFICATION**: 11/14 controls adequate; all three compound-modifier controls (`peptide-linked ADC`, `antibody-derived cell therapy`, `small-molecule-loaded nanoparticle`) get the modifier as PRODUCT_LEVEL via `explicit_product_predicate` and leave the head AMBIGUOUS. A PRODUCT_LEVEL consumer would certify the exact false-PEPTIDE pattern. H19's single modality fact (datopotamab PEPTIDE) is B_COMPONENT_ONLY; action blocked, legacy fact retained. Deterministic; zero production changes; v2 NOT adopted.

Next: separately preregistered scope-representation milestone (noun-phrase head attachment) before any v3 semantic design. ESG401 nomination remains separate and not started. H21–H25 untouched; H6–H10 unrun.

---

# 2026-10-13 — MODALITY_ASSERTION_SCOPE_REPRESENTATION v1 ADOPTED

Preregistration **74a6f63**; red-first tests **ea639dd**; implementation **aedc91f**; adoption/results **7df34fb**. Read `research/se_modality_assertion_scope_representation_v1/README.md`, `results/quality.json`, `results/witness_table.md` and policy `docs/se_policies/modality_assertion_scope_representation_v1.md`.

New immutable diagnostic API: `src/bve/se/evidence/modality_scope.py::scoped_modality_assertions`. It accepts an original raw source field, candidate identity, source names and exact provenance; retains all matches, product/component/relational/ambiguous scope, raw subject/component/relation spans, rule/version, stable ID and legacy-fact associations. No existing extractor/gate/RunResult imports or consumes it. This is an adopted representation API plus original-source diagnostic artifacts, **not live extraction integration or a semantic fix**.

All 33 frozen focus expectations pass (21 original + 12 structural controls); 34 focused tests pass. Controls produce 17 PRODUCT_LEVEL, 14 COMPONENT_LEVEL, two RELATIONAL_COMPOSITE, 19 AMBIGUOUS assertions. These count all mentions, not one per witness. Nullable modality retains unknown constituent vocabulary without new aliases. Closed grammar is intentionally incomplete; unsupported subject/scope remains ambiguous and does not confer authority identity.

All 23 H19 audit rows and 1,181 saved candidate decisions unchanged. Their one stored modality fact links to five coexisting source assertions: one product, two component, two ambiguous. Datopotamab's peptide linker is component-level, while its legacy PEPTIDE fact and modality.required FAIL remain unchanged. Correct qualification/ADC authority annotation unchanged. Original 21 scalar winners unchanged; all 284 recorded modality gates reproduced with their saved admitted input fact IDs. An invalid exploratory all-stored-facts probe is preserved/documented; stored facts include evidence not admitted for gating. No semantic rule or expectation was patched.

Independent seed builds byte-identical; every raw span/source field verified. Full tests/se: **1,873 passed, three existing xfails, zero failures/errors**. Ruff clean over src/bve/se, tests/se and new research code. New assertions are never decision-bearing. R1–R13 pass; no adoption threshold was based on diagnostic counts.

Next separate **PRODUCT_VS_COMPONENT_MODALITY_SEMANTICS v2 design phase** preregistered in **65cddd1**, policy `docs/se_policies/product_vs_component_modality_semantics_v2.md`. No semantic implementation authorized by that design document. First freeze complete baseline modality facts/source routes/admitted gate inputs and additional contradiction/composite/missing-scope controls; derive exact permitted deltas and stop on unsupported scope/identity. Commit implementation preregistration before any future gate changes. Do not silently improve the scope grammar after seeing semantic outcomes.

Qualification v2 and 86 target-component cases remain blocked; human-PoC recovery stopped. ESG401 nomination later and separate; BL-M02D1 source coverage separate. H21–H25 untouched; H6–H10 unrun. No target/alias/qualification/nomination/identity/ranking/source behavior changed.

---

# 2026-10-13 — PRODUCT_VS_COMPONENT_MODALITY_SEMANTICS v1: REPRESENTATION BOUNDARY

Preregistration/freeze **939806e**; diagnosis/results **88dadb8**. Read `research/se_product_vs_component_modality_semantics_v1/README.md`, `results/scope_table.md`, `results/all_mention_scopes.json` and `results/datopotamab_lifecycle.json`.

**STOP: no production implementation/adoption/revert.** First loss: QueryVocabulary.modality_in returns a single scalar without subject/match-span/scope. First promotion: candidate intervention tuple then clinicaltrials modality_id claim attaches that scalar to the product hit. The claim retains the passage but no typed product/component relation; NormalizedFact discards passage and carries a scalar plus claim IDs. The gate compares scalar modality without scope. Re-reading a passage would require new semantic extraction, not consumption of preserved scope.

The exact datopotamab source is NCT07720284 intervention[0].description; peptide modifies tetrapeptide linker, ADC predicates the whole product. PEPTIDE wins substring length over ADC/IgG/mAb; trap also appears inside tetrapeptide and is not a genuine fusion assertion. Saved claim:2022030306a59db4acec → fact:71c28d48f9461eb004d3 → modality.required FAIL → saved EXCLUDED. Qualification remains DIRECT_APPROVED_NAME; independent ChEMBL ADC/MATCH remains intact. No claim that removal of this fact alone guarantees eligibility.

Frozen focus population: 21 text witnesses (one exact H19 plus 20 synthetic structural probes), classified as six PRODUCT_LEVEL, nine COMPONENT_LEVEL, one RELATIONAL_COMPOSITE, five AMBIGUOUS. Every lexical match separately annotated; product and component mentions coexist in a sentence. Seven existing structured molecule-type fixture assertions retained; 65 test functions inventory / 105 executed tests pass. All 23 previous H19 audit rows preserved unchanged. Two seeded builds byte-identical, exact source/focus spans verified, Ruff clean. Full tests/se not run because no production/schema changed. Zero decision changes; false PEPTIDE exclusion remains present.

Smallest prerequisite is separately preregistered **MODALITY_ASSERTION_SCOPE_REPRESENTATION v1**, additive and decision-neutral: preserve candidate/source identity, exact raw field and span, normalized coordinate lineage, modality, scope, semantic subject, parent/component relation, assertion status and rule/version, plus links to legacy claims/facts. Scope unknown must remain AMBIGUOUS. Existing legacy decisions must remain unchanged in that future milestone. Only afterward may a separately frozen consumer admit whole-product assertions to gates. Current design explains the semantic distinction but is not a validated deterministic prose binder; coordination, multiple products, negation, discourse, nesting and contradictory whole-product evidence remain explicit design questions.

Do not start ESG401 nomination on the assumption this defect is fixed. Therapeutic-product-role qualification v2 remains source-blocked; 86 target-component cases closed; human-PoC recovery stopped. H21–H25 untouched and H6–H10 unrun. No target/alias/qualification/identity/ranking/source changes.

---

# 2026-10-13 — THERAPEUTIC_PRODUCT_ROLE_EVIDENCE_REPRESENTATION v1: SOURCE GATE STOP

Preregistration/population **918d296**; audit/results **be80f0a**. Read `research/se_therapeutic_product_role_evidence_representation_v1/README.md` and `results/summary.json`.

**G0 FAIL: required distinction is prose-only or at the wrong semantic level. Production implementation NOT_STARTED; representation NOT_ADOPTED.** No revert is needed. The original qualification design contract d22f6b8 remains unchanged. Do not open qualification v2 on the basis of this audit.

All 1,181 saved qualification decisions remain unchanged; all three H19 non-assets still qualify as STRUCTURED_THERAPEUTIC. No therapeutic control lost qualification. All 215 qualification regressions and four focused audit checks pass; Ruff clean. Full tests/se was not run because no production code/schema changed. These are read-only saved-decision comparisons, not live replays.

Audited all 779 raw snapshots and four snapshot-less ontology references; verified 802 pinned input hashes. All 7,220 recorded source-field assertions round-trip exactly. Independent canonical audit builds are byte-identical. Structured intervention links exist for 75 candidates; 32 have unmatched CT.gov document associations; 1,171 have unclassified source text. Three native type variations and six mixed-arm contexts remain explicit.

Product-kind and intervention-use semantic bins both remain UNKNOWN for all 1,181 rows (cross-tab UNKNOWN/UNKNOWN = 1,181, all other cells zero). This is an availability/authorization result, not a claim that native fields are empty or every product is scientifically ambiguous. Native DIAGNOSTIC_TEST declarations occur for five candidates and other entity types are preserved; no new category interpretation is adopted. The key DRUG/EXPERIMENTAL controls still require information not encoded as typed product/use assertions.

H19: [68Ga]Ga-TTP has DRUG/EXPERIMENTAL and study-level DIAGNOSTIC, with radiotracer/imaging semantics in its description. Rescue Medications/Rescue Medication have DRUG/EXPERIMENTAL and study-level TREATMENT, with rescue/premedication semantics in descriptions. Study purpose cannot become every intervention's product identity/use. Exact fields, paths, snapshot hashes and candidate links are in `results/h19_visibility.json`. The paired diagnostic/therapeutic controls differ only in free-text description. Arm and entity facts cannot supply the missing product-role assertion.

Minimum prerequisite: separately specified candidate/product-scoped kind assertions and trial/intervention/arm-scoped use assertions, each with exact authority/artifact/field/component provenance, declared semantic scope and UNKNOWN/conflict handling. Either obtain an appropriate structured evidence source under a separate source contract or separately design/validate text-to-assertion binding. Neither is implemented here; adding enum fields alone is insufficient. Stop this qualification path at the requested source-evidence boundary rather than inventing prose heuristics.

Datopotamab product/component modality, ESG401 nomination and BL-M02D1 coverage remain separate and untouched. The 86 target-component cases remain closed; human-PoC recovery stopped; H21–H25 untouched; H6–H10 unrun.

---

# 2026-10-13 — THERAPEUTIC_PRODUCT_ROLE_QUALIFICATION_CONTRACT v1: STOP AT REPRESENTATION BOUNDARY

Used the exact design preregistration **d22f6b8**. Its policy, preregistration and original input manifest are unchanged. Additional paired structural controls were frozen under its explicit allowance in **99e9c06**; completed boundary audit and red-first evidence are **feebefc**. No replacement contract was written.

Read `research/se_therapeutic_product_role_qualification_contract_v1/README.md` and `results/decision.json`. Status: **NOT IMPLEMENTATION-READY; production implementation NOT_STARTED**. The existing contract defines a design exercise and scientific constraints, not a fully specified replacement predicate or implementation delta. Its D8 stop condition permits a precise evidence/representation gap; that boundary is now demonstrated.

AssetEvidence loses the distinction between whole-product identity/kind and observation-specific intervention use: it receives a name, coarse identity flags and DRUG/arm counters, without source-field/product-subject/role assertions. Two frozen records with distinct therapeutic versus diagnostic source semantics yield identical complete qualification inputs and both return STRUCTURED_THERAPEUTIC. A qualification-only function cannot separate them. Reading/interpreting raw descriptions inside it would introduce a new evidence-binding/extraction rule not supplied by the contract and outside the current implementation scope.

All 46 design rows are audited: 23 H19 entities, 21 original controls, two additional structural witnesses. The three H19 non-assets still qualify; no claim of remediation. Red-first baseline: 8 tests, four expected failures (three non-assets and synthetic diagnostic), four protected-positive passes, zero errors. All 215 existing qualification regressions pass. Semantic fixtures remain distinct from executable historical regressions; no expectations modified. Independent seed-0/seed-42 audit artifacts are byte-identical; Ruff clean.

All 1,181 saved candidate qualification decisions remain unchanged. Total implementation deltas 0; therapeutic losses 0; out-of-scope changes 0, because no production behavior changed. Full tests/se was not run: no production changes; the complete frozen qualification regression set was run. No adoption or revert applies.

Minimum prerequisite, not implemented: subject-scoped qualification assertions retaining exact candidate/intervention identity, product-kind versus observation-use scope, explicit value/UNKNOWN/CONFLICT, source artifact and field/span provenance, interpretation rule/version, and conflicting assertions before aggregation. A source-to-assertion binding rule and positive-evidence sufficiency contract must be frozen before any consumer can use that representation. This is a documented architecture requirement, not a replacement contract or permission to invent new evidence types.

STOP here as instructed when the existing contract is not implementation-ready. Do not delete the structured route blindly, add name vetoes, expand scope into extraction, or treat a zero-change audit as qualification adoption. Consequently do not advance to PRODUCT_VS_COMPONENT_MODALITY under the conditional post-adoption plan. Datopotamab, ESG401, BL-M02D1 paths remain untouched. The 86 target-component cases remain closed; human-PoC recovery stopped; H21–H25 untouched; H6–H10 unrun.

---

# 2026-10-13 — H19_CANDIDATE_QUALIFICATION_DIAGNOSIS v1 COMPLETE

Freeze **4d628ec**; diagnosis/results **c29ffa2**. No production behavior changes. Read `research/se_h19_candidate_qualification_diagnosis_v1/README.md`, `results/row_table.md`, and policy `docs/se_policies/h19_candidate_qualification_diagnosis_v1.md`.

All 20 emitted rows and all five reference assets are accounted for in 23 first-boundary rows. A non-asset admission: 3; B false product-type exclusion: 1; C nomination: 1; D source coverage: 1; E duplicate identity: 2; F target evidence/review routing: 7; no qualification failure: 8. Frozen metrics and labels unchanged.

Key correction: datopotamab already qualifies DIRECT_APPROVED_NAME. PEPTIDE is not an erroneous ontology identity/type record: the current lexical modality extractor sees `peptide` inside the description's `tetrapeptide linker`, selects it over ADC, and emits claim:2022030306a59db4acec / fact:71c28d48f9461eb004d3 from NCT07720284. That fact causes modality.required FAIL, while the separate ChEMBL CHEMBL4297939 product type is Antibody drug conjugate and authority annotation is ADC/MATCH. First boundary is product-versus-component scope in modality extraction. Do not fix through qualification or an asset exception.

All three NON_ASSET rows use STRUCTURED_THERAPEUTIC from DRUG typing plus experimental-arm membership. None has a direct molecule-name route or NCIt veto. [68Ga]Ga-TTP's own source is a diagnostic PET tracer in a DIAGNOSTIC trial; the two rescue-medication names denote generic premedication categories. Current code separately permits approved-name qualification before the non-product veto; a synthetic route probe confirms this risk, but it is not the cause of these three admissions. Do not collapse the two defects.

ESG401: one raw leaf hit in NCT06145308 armsInterventionsModule.armGroups[3].description, listing alternative drugs; zero candidates/identity mentions. Generic TROP2 ADC is the intervention name. BL-M02D1: zero supplied-form/separator-normalized hits across 779 captured snapshots, zero candidates/mentions. Four ontology source records have no query snapshot. No reacquisition; captured absence does not establish global absence or connector cause.

Validation: all 818 pinned inputs unchanged, exact claim/document links verified, existing helper controls preserved; 215 qualification tests pass, Ruff clean. No source/production/ontology modifications or live replay. Full tests/se not needed for diagnosis-only work. Twelve synthetic semantic design controls are frozen, not scored against a new classifier.

Next highest-value work is **THERAPEUTIC_PRODUCT_ROLE_QUALIFICATION_CONTRACT v1**, design only. There is no implementation-ready general rule yet. Separate product identity, intrinsic kind, observation-specific use, and query eligibility. Protect named therapeutic products used supportively; do not inherit trial purpose into every intervention or treat experimental-arm membership as therapeutic identity. Product/component modality, name nomination, coverage, duplicates, ranking and authority precedence remain independent workstreams. Preregister the design before deriving a rule; no production change authorized by this diagnosis.

The 86 target-role identity cases remain CLOSED/evidence-blocked. Human-PoC recovery stopped. H21–H25 untouched; H6–H10 unrun; H19 development data only.

The next design-only milestone is now preregistered in `docs/se_policies/therapeutic_product_role_qualification_contract_v1.md`, with pinned inputs under `research/se_therapeutic_product_role_qualification_contract_v1/`. Status: PREREGISTERED; no final contract or production rule has been adopted. Its first step is the frozen control-gap/subject-scope audit.

---

# 2026-10-13 — TARGET_COMPONENT_IDENTITY_CERTIFICATE v2 ADOPTED

Current milestone: independently adopted offline biological identity certificates, with no production consumer or target decision changes.

Commits: preregistration **a9bf585**; implementation **b17f9da**; adoption/results **3cbc737**. Baseline was d968f30. Policy: `docs/se_policies/target_component_identity_certificate_v2.md`. Full audit and reproduction: `research/se_target_component_identity_certificate_v2/README.md` and `results/`.

All 234 frozen certificate expectations passed: 55 CERTIFIED_SINGLE_ENTITY, 15 CERTIFIED_RELATIONAL_ENTITY, three CERTIFIED_MULTI_ENTITY, 35 CONFLICT, 126 AMBIGUOUS, zero UNRESOLVED. The 55 positives are 52 exact primary gene assertions and three exact protein components; none permits blanket inheritance to other aliases or merged resolver groups. The 48 original resolver groups remain ambiguous as ingestion unions, not authority-defined biological entities.

For the 86 blocked target-role proposals: **0 SINGLE, 0 MULTI, 0 RELATIONAL, 35 CONFLICT, 51 AMBIGUOUS, 0 UNRESOLVED**. The ALK/EML4 gene-ID conflict remains explicit. No authority priority or normalized-name reconciliation was introduced. No additional source was acquired.

Provenance validation: 495 source records, 11,806 exact adopted field assertions, all 3,534 sidecar origins; independent seed-0/seed-42 artifacts byte-identical. Both canonical-ID collision families survive in component certificates (seven SNORA62 components; two CDC42BPA components). Recoverable-origin collision reporting covers one family because historical ChEMBL-only origins are absent; this is explicitly separated from component collisions. All 629 multiple-origin keys remain represented, including 94 keys with distinct raw strings. No missing historical lineage is fabricated.

All **6,199 parser decisions unchanged**. Fifteen focused/compatibility tests pass; Ruff clean. No changes to production `src`, `tests`, `scripts`, or `data/se/ontology` against baseline. Full `tests/se` was not run because C12 requires it only for production-code changes; none occurred. The red-first failure, final test logs, complete certificates, evidence registry, collision audit and input/output hashes are retained in the study.

**Stop work on recovering these 86 cases. This target-role repair path is evidence-blocked.** Do not add another authority, weaken certificates, implement role changes, or reopen alias expansion on their basis. A permitting primary control is not permission to certify its whole resolver group.

Broader roadmap reassessment: next independently diagnose the known H19 non-asset/PEPTIDE candidate-qualification defect, starting from frozen primary-validation evidence and the current first failure boundary. This has direct precision value and is independent of blocked target identity. Keep qualification, duplicate consolidation, ranking and reproducibility work separate; preregister any behavior change. No such change was implemented in this milestone.

H21–H25 remain untouched. H6–H10 remain unrun. H17/H20 remain development diagnostics only. Human-PoC recovery remains stopped. C056 and historical failed preregistrations remain separate and unchanged.

---

# 2026-10-13 TARGET COMPONENT IDENTITY CERTIFICATE v1 — SOURCE GATE FAILED

## 2026-10-13 — TARGET_COMPONENT_IDENTITY_AUTHORITY_EVIDENCE v1 ADOPTED

Decision-neutral source/evidence infrastructure is independently adopted. No certificates, aliases, parser semantics, or production code changed.

Commits: preregistration `a8938d6`; frozen acquisition/controls `b37b476`; offline evidence implementation `1889503`; adoption/results `3aafe01`.

Policy: `docs/se_policies/target_component_identity_authority_evidence_v1.md`. Reproduction, source comparison, limitations and results: `research/se_target_component_identity_authority_evidence_v1/README.md` and `results/`.

Frozen sources are ChEMBL 37 SQLite, the exact HGNC GCS object generation 1791894733877675, and UniProtKB release 2026_03. Raw artifacts and both deterministic builds are retained under `/home/djmann/se_runs/target_component_identity_authority_evidence_v1/`. This is additive independent source evidence, not reconstruction of historical ChEMBL HTTP payloads. Existing accepted authority snapshots and assertion provenance artifacts remain byte-identical.

Validation: 5,102 source records and 1,291,485 field assertions independently round-trip to frozen raw sources; two builds are byte-identical. All 6,199 parser decisions remain unchanged. Six focused tests pass; Ruff passes across source, SE tests and this study. Full `tests/se` was not run: S11 requires it if production code changes, and none changed. Isolation was verified against `d47b810` for `src`, `tests`, `scripts`, and `data/se/ontology`.

All 48 audited components, nine implicated groups, and 86 proposed changes are retained. All 29 formerly missing ChEMBL target records are recovered. Structured controls preserve fusion, complex, family, multi-subunit and relationship membership. Evidence coverage for the 86 remains 35 CONFLICTING and 51 AMBIGUOUS; uniquely supported, multi-entity, relational and no-evidence counts are each zero under the frozen precedence. These are diagnostic source-evidence classes, not certificates, and do not override the prior failed certificate result.

Limitations remain explicit: 12 historical Ensembl IDs have no selected HGNC match; UniProt includes two unreviewed and one inactive record; four ChEMBL RNA components have no protein accession and retain native identity. No substitute identifiers or inferred equivalences were invented. Source claims, canonical-ID collisions and different biological levels remain separately visible in `results/source_claim_comparison.json`.

Next: separately preregister `TARGET_COMPONENT_IDENTITY_CERTIFICATE v2` using the frozen additive structured evidence plus existing ChEMBL provenance. Do not implement certificates or target-role decisions as part of this adopted milestone. Evidence availability does not itself certify component-to-canonical equivalence. Preserve conflicts and fail closed when typed evidence cannot establish identity.

H21–H25 remain untouched; H6–H10 remain unrun; H17/H20 remain development diagnostics only. Human-PoC recovery remains stopped.

---

Preregistration **5af5775**; source-gate failure/evidence **a1ff1b0**. **No production implementation or adoption.**
Stopped at the preregistered G0 source-readiness gate; no candidate exists to revert.

Audited 48 frozen components, all nine implicated groups and all 86 blocked proposals.
Retained evidence: 72 raw Open Targets gene records, 3,534 exact assertion-sidecar rows,
four raw Greek-form labels. Twenty-nine ChEMBL raw member records are missing. Each of
the nine groups includes missing ChEMBL component evidence; normalized rows cannot recover
original target type, member ownership or biological relationships. Counting graph members
is not an authority certificate of a biological multi-entity target.

**86 diagnostic results:** 0 certified single; 0 certified multi; 0 certified relational;
35 primary gene-ID mapping conflicts; 51 ambiguous. All 86 lack a permitting certificate.
All nine whole-group identities remain AMBIGUOUS. Five approved-name gene mismatches, each
in seven frames: H4C1→H4C8, BOLA2→BOLA2B, UBA52→RPS27A, ALK→EML4, JMJD7→PLA2G4B. These are
explicit gene-identity conflicts, not a claim that every encoded/mature protein differs.
Nineteen broader clean primary gene mappings have raw support; this does not certify all
synonyms in their records or settle gene/protein/complex granularity.

Evidence: `research/se_target_component_identity_certificate_v1/results/`; policy:
`docs/se_policies/target_component_identity_certificate_v1.md`. Three audit seeds
0/1/42 byte-identical. All 6,199 parser/compiler/trial/buyer hashes recomputed unchanged.
Ruff clean. Production src/tests/scripts and accepted ontology bytes unchanged from e2b31bf.
Full tests/se not rerun because source gate failed before implementation; no C10 claim.

**Next prerequisite:** a separately preregistered structured target-component authority
source contract; see `results/minimum_source_contract.md`. It must preserve typed target
and component membership/relations at explicit gene/protein/complex granularity, include
real complex/fusion/relational positive controls, and retain raw structural-field lineage.
Use a frozen release-addressed evidence bundle; distinguish new independent evidence from
unrecoverable historical HTTP origin. No new source was acquired in this milestone.
Do not infer equivalence from shared accession, spelling, record membership or sequence.
Do not repair the authority graph, admit aliases, or implement target-role decision v2 yet.

H21–H25 untouched; H6–H10 unrun; human-PoC stopped. Existing mappings and separator oracle
defects unchanged. No private advice/meeting material included, no push.

---

# 2026-10-13 TARGET MENTION ROLE DECISION v1 — DESIGN BOUNDARY

Diagnosis/evidence **8ec028c**. **No implementation preregistration, production change,
adoption, or revert.** The preflight rejected the proposed identity certificate before
freezing behavioral deltas. Do not call these observations a scored implementation.

The complete 6,199-case probe proposes 2,276 whole-target-slot operations. It covers all
224 frames of the 32 English mismatches and leaves all 21 protected Greek frames alone.
However, **86 proposed operations across nine components contain multiple source gene
records**, despite each matched label having a single component and exact raw lineage.
Examples include the native ALK approved-name resolution to TARGET:EML4, BOLA2 approved
name to TARGET:BOLA2B, and JMJD7 synonym to TARGET:PLA2G4B. This diagnoses an existing
grouping/certification boundary; it does not assert that every multi-source component
has identical biology or that every such grouping is wrong.

The sidecar is sound and retains complete component membership. The adopted mention's
matching source-record list is not a component-wide identity-equivalence certificate.
A pointer to correct ingestion history must not authorize a stronger biological claim.
No nine-ID blacklist or benchmark-only subset was implemented.

**Next narrow prerequisite:** separately preregister
`TARGET_COMPONENT_IDENTITY_ELIGIBILITY v1`, decision-neutral. Expose complete source
membership, source-symbol assertion IDs, elected canonical linkage and explicit
certification/UNKNOWN status using the adopted sidecar. Do not modify the identity graph,
merge source records, select a preferred gene, or add aliases. Multi-source equivalence
requires scoped authority evidence; no blanket shared-component inheritance. Then revisit
a full frozen role-decision delta, including fail-closed handling of uncertified whole
names and independent grammar evidence for retained embedded targets.

Evidence and proposed interface:
`docs/se_policies/target_mention_role_decision_v1.md` and
`research/se_target_mention_role_decision_v1/`. All 6,199 baseline parser/compiler/trial/
buyer hashes recomputed unchanged; four adopted representation tests pass; Ruff clean
for src/bve/se, tests/se and new diagnostic scripts. Production src/tests/scripts and
accepted snapshot bytes unchanged from 1c78cd6. Full tests/se not rerun for this
research/documentation-only boundary. H21–H25 untouched, H6–H10 unrun, human-PoC stopped;
known separator oracle defects remain unchanged.

Source-of-truth check: GitHub branch is still 979ba4d (2026-09-22), an ancestor 285 commits
behind starting local HEAD 1c78cd6. The user's explicitly named local adopted commits
therefore govern this work. Connected Biotech Tool Context root/docs listings exposed
older material, not a newer target-role handoff. No private advice or meeting preparation
files were fetched into or committed to the repository. No push performed.

---

# 2026-10-13 TARGET MENTION ROLE REPRESENTATION v2 — ADOPTED

Preregistration **dec7b2c**; red tests **d8880b4**; candidate **4aca4d1**; final schema
identifier/evaluator **20ddc7e**; adoption/evidence **679557d**. All R1–R11 passed; no post-scoring patch. Representation
and sidecar access only: existing target/parser/compiler and all scientific decisions
remain unchanged. The analysis API is not called by the production target-decision path.

**Evidence:** 6,199/6,199 frozen decisions unchanged, 1,687/1,687 required spans retained,
77/77 historical provenance failures closed using exact sidecar IDs. Independent streaming
of adopted raw-assertion artifacts verifies every emitted provenance match. All 1,392
complete diagnostic/structural rows byte-identical across seeds 0/1/42. All 245 English/
protected-Greek explanations retained (35 spelling families, seven frames each).
Full tests/se **1,839 passed, 3 existing xfails**; four focused controls pass; Ruff clean.

**Diagnostic state:** 1,344 queries, 3,164 mentions; 364 single-mention, 980 multiple,
448 overlapping queries. Roles: 2,422 ambiguous, 735 embedded, seven contextual.
Fourteen mention occurrences have no recoverable raw match; no provenance or therapeutic
role is guessed. Overlaps do not force ownership. Canonical IDs and source component IDs
remain separate, with all matching raw assertion IDs preserved. Missing historical
ChEMBL origins remain missing. No source reconstruction from canonical IDs or labels.

Policy: `docs/se_policies/target_mention_role_representation_v2.md`.
Frozen inputs, evaluator, README and full acceptance evidence:
`research/se_target_mention_role_representation_v2/`.
Derived index/output: `/home/djmann/se_runs/target_mention_role_representation_v2/`.
The index is a read-only access aid, not a new authority; expected adopted hashes are
required and independent sidecar verification is part of the evaluator.

**Next:** separately preregister TARGET_MENTION_ROLE_DECISION v1. It may evaluate whole-
name/query-role corrections using this representation, but must first establish a general
rule and freeze controls. No semantic target-role rule or new alias was implemented here.
Known separator oracle defects remain frozen. Human-PoC stopped; H21–H25 untouched;
H6–H10 unrun. Other known reliability milestones remain separate.

---

# 2026-10-13 AUTHORITY ASSERTION PROVENANCE SIDECAR v1 — ADOPTED

Preregistration **0bb2e7a**; red tests **f634e8e**; implementation **2f74f93**; adoption/evidence **d8cb1b2**.
All P1–P11 passed without post-result patches. New standalone provenance module and
offline generator only; existing target/parser/identity and all other decision paths
remain unchanged. The legacy ingestion builder does not automatically call the new API.

**Evidence:** 6,199/6,199 full frozen parser/compiler decisions unchanged; 124/124 lookup
outcomes unchanged; all 77 earlier failure cases have complete raw provenance. Across
443 audited snapshot-field occurrences: 410 recoverable, 33 explicitly unrecoverable,
exactly as preregistered. Full tests/se **1,835 passed, 3 existing xfails**, Ruff clean.

**Artifacts:** 910,548 raw-origin sidecar rows; 517,905 recoverable snapshot fields;
55,613 ChEMBL fields unrecoverable because original ingestion responses were not retained.
76,773 canonical IDs have raw sidecar assertions; 75,702 have multiple assertions.
41,798 normalization collisions and 463 canonical-ID/component collisions remain visible
without merging identities. Independent seed-0/42 output files byte-identical; source
and accepted snapshot bytes unchanged. All three original Open Targets shard hashes
are bound by the accepted snapshot manifest and reproduce its 78,691 records exactly.

Policy: `docs/se_policies/authority_assertion_provenance_sidecar_v1.md`.
Schema, frozen controls, results and receipts:
`research/se_authority_assertion_provenance_sidecar_v1/`.
Large generated artifacts:
`/home/djmann/se_runs/authority_assertion_provenance_sidecar_v1/seed0/` and `seed42/`.
Do not treat a separate ChEMBL release database as the missing original API payloads.

**Next:** separately preregister TARGET_MENTION_ROLE_REPRESENTATION v2 using the adopted
sidecar and explicit UNRECOVERABLE states. Preserve all existing target decisions; do
not combine that work with role selection or alias expansion. No blanket canonical-ID
lookup may replace source-component lineage. Human-PoC stopped; H21–H25 untouched;
H6–H10 unrun. Ranking, qualification, duplicates and other known defects remain separate.

---

# 2026-10-12 AUTHORITY LOOKUP SOURCE COMPONENT PROVENANCE DIAGNOSIS v1 — STOP B

Population freeze **5aa8fdd**; baseline **cc609b1**. Diagnosis/design only; no production
or snapshot changes. Policy: `docs/se_policies/authority_lookup_source_component_provenance_diagnosis_v1.md`.
Audit: `research/se_authority_lookup_source_component_provenance_diagnosis_v1/`.

All **77** failed observations recover exact stored snapshot assertions. The broader
frozen population has **124 observations / 443 assertion locators**; all raw fields and
query offsets round-trip. Audit output is byte-identical in an independent seed-42 process.
Current outcomes: **60 RESOLVED, 62 AMBIGUOUS, 2 UNRESOLVED**. These are diagnostic counts,
not target recovery. No parser decisions changed or new aliases admitted.

The substrate has two levels: snapshot field/component provenance is reconstructible,
but original upstream synonym spelling/field and ChEMBL component-to-alias ownership
were discarded by ingestion cleanup, flattening and deduplication. A snapshot locator
must not masquerade as original authority lineage. **Boundary B:** minimum extension is
an ingestion source-assertion sidecar binding raw artifact digest + field path + component
+ transforms to snapshot assertions. No snapshot regeneration or implementation here.

A separate resolver-component key and match-assertion ledger can preserve colliding
canonical IDs without changing or merging their identities. Design is documented, but
full upstream provenance implementation is not ready on current snapshot schema.
Next narrow work, if resumed: preregister captured-source assertion lineage/schema design;
first check retained upstream artifacts, with no identity or decision changes. Do not
reattempt target-mention representation or target-role decisions yet.

Diagnostic scripts pass Ruff. Production src/tests/scripts and snapshots match cc609b1;
full tests/se were not rerun for this documentation/offline diagnostic change. Prior
failed representation evidence and reversions remain intact. Human-PoC stopped;
H21–H25 untouched; H6–H10 unrun. All other semantic milestones remain separate.

---

# 2026-10-12 TARGET MENTION ROLE REPRESENTATION v1 — FAILED / REVERTED

Preregistration **d26949f**; red-first tests **cbdb8d2**; candidate **1bbfceb**;
frozen failure evidence **d9775a4**; normal implementation revert **bc564f8**;
dependent-test revert **2d694e5**. No candidate production behavior remains.

- Decision neutrality: **6,199/6,199** full parser/compiler decisions unchanged.
- Coverage: **1,687/1,687** required spans represented; all **245** mismatch/protected-Greek explanation rows produced.
- Determinism: **1,392** complete diagnostic records identical across seeds 0, 1, 42; repeated analysis unchanged across all 6,199 observations.
- **R3 failed:** 77 mention observations lack exact source provenance. Of these, 35 involve a raw source label ` gene` normalized to `gene` without preserving the raw-field transformation; 42 involve MRCK/E2 alias entries whose symbol-derived canonical ID retrieves a different source component. Existing resolver components collide at TARGET:CDC42BPA (two components) and TARGET:SNORA62 (seven). This does not establish biological equivalence and must not be repaired by merging them.
- **R8 incomplete:** seven English explanation frames inherit the raw-label provenance gap. R1/R2/R4/R5/R6/R7/R9/R10 passed. No post-result patch or threshold change.
- Candidate quality gates: **1,835 passed, 3 existing xfails**, zero failures; Ruff clean.
- Restoration: src/tests/scripts byte-identical to **92e8f56**; regenerated 6,199-decision baseline and required-span file byte-identical to the preregistration; restored Ruff clean. Full suite was not repeated after removing only the candidate module and its seven tests.

Evidence: `research/se_target_mention_role_representation_v1/results/`;
restoration: `research/se_target_mention_role_representation_v1/restoration/`;
policy: `docs/se_policies/target_mention_role_representation_v1.md`.
Historical candidate evaluation scripts require the recorded candidate commit; they are not installed production code.

Next narrow milestone: **TARGET_AUTHORITY_LOOKUP_PROVENANCE_DIAGNOSIS v1**.
Trace alias-index entries to their exact originating source component and raw assertion;
determine a stable provenance representation without changing target identity or merging
source groups. Diagnose before preregistering any implementation. A target-role decision
rule is not yet implementation-ready because its mention provenance prerequisite failed.
No further alias expansion or human-PoC recovery. H21–H25 remain untouched; H6–H10
remain unrun. Ranking, qualification, deduplication, identity graph, source acquisition,
and shortlist routing remain unchanged. Known separator oracle defects remain frozen.

---

# 2026-10-12 TARGET AUTHORITY SPAN / QUERY ROLE — STOP B

Population freeze **d3fa60d**; design/audit **36da8d6**; results and final contract in `research/se_target_authority_span_query_role_contract_v1/results/` and `docs/se_policies/target_authority_span_query_role_contract_v1.md`.

**Architecture extension required; no production implementation.** The current IntentSpan model permits identity references only on TARGET spans, greedy consumption drops competing name/role hypotheses, and each TARGET span becomes a query target without a separate role decision. The final design requires a typed pre-resolution authority-candidate ledger, independent role/ownership certificates and an audited projection step. Do not weaken the existing TargetReference validator or change the identity graph.

All **1,344 observations / 96 pairs** and **48 frozen structural controls** audited. All **32 English mismatches / 224 frames** have complete-name source support, but this is potential recovery conditioned on correct role ownership, not a tested parser recovery. A whole-name-only policy loses **21 currently correct-identity frames / three Greek names**. No Greek/common-name alias admission.

**Frozen-label errors preserved:** S041 wrongly expected no target for the whole source-supported ABP/ZF alias; S042 wrongly expected CD19 to disappear when CAR is ambiguous. Both remain in the denominator and are not patched. S002 (PD-1) is an authority ambiguity, not a span error. BRAF mutation controls expose another installed merged-identity concern; record separately, do not repair it in span work. The study does not pass implementation acceptance.

Read-only artifact integrity checks pass; research scripts Ruff clean. Source/tests/scripts remain identical to **04b184b**. No new full-suite run was needed; restored baseline evidence remains **1,828 passed / three existing xfails**.

**Next possible milestone, separately preregistered:** TARGET_MENTION_ROLE_REPRESENTATION v1, decision-neutral, followed only later by a demonstrated role/ownership arbitration contract. Freeze successor controls explicitly correcting the two failed expectations; never edit this study's labels. Current user stop condition B reached: do not implement the extension in this milestone.

Human-PoC recovery STOPPED; ranking/qualification/duplicates unchanged. H21–H25 untouched; H6–H10 unrun. Engine unvalidated. This supersedes earlier “next” instructions below.

# 2026-10-12 AUTHORITY-SPAN DIAGNOSIS — NO NEW IMPLEMENTATION

Scope freeze **2ff9604**; read-only trace/audit **4409c68**. Packet: `research/se_target_query_authority_span_boundary_diagnosis_v1/`.

All 96 frozen authority-name pairs were parsed on the restored baseline in seven existing frames: **1,344 traces**. 67/96 complete names exceed the target-specific two-token cap; another has scientific parentheses changed by edge stripping. Only 28 complete names are offered in every frame. Against the existing certified whole-name references, original English names emit outside-reference targets for **32 names / 224 frames**; Greek names do so for **31 names / 217 frames**. These are baseline diagnostic mismatches, not new candidate failures. Six uncertified identities are excluded from that comparison.

The three failed Greek cases already have English nested-alias analogues. One additional role conflict: the name `Thymopoietin-related peptide isoform alpha` (TMPO reference) produces PEPTIDE modality. Do not fix modality in this milestone. The original cap rationale is documented in `be41c23` and `docs/se_search_intent_layer.md`: avoid protein-family inference. Merely raising the n-gram cap is not justified.

**Next:** finish diagnosis/design for atomic complete authority spans and separate query-role ownership. Freeze structural controls for nested/overlapping names, ambiguous longer claimants, family/complex descriptors, true dual-target requests, scientific punctuation and clinical-role collisions before preregistering any behavior change. Preserve all ambiguity claimants; no name-specific suppression or broad substring inference. No implementation contract is ready yet. Unicode separator coverage and NCIt common-name semantics remain separate pending work.

Greek v2 remains failed/reverted (**00ab163 / 9a7cdeb**). Source/tests/scripts are byte-identical to pre-candidate **8ee443a**. Restored full suite: **1,828 passed / three existing xfails / zero failures**, exit 0; Ruff clean. Restoration evidence: `research/se_target_query_greek_orthography_v2/restoration/`. Existing identity/retrieval separation remains adopted. Human-PoC recovery STOPPED; ranking/qualification/duplicates untouched. H21–H25 untouched; H6–H10 secondary/unrun. Engine remains unvalidated.

# 2026-10-12 GREEK QUERY CANDIDATE — FAILED AND REVERTED

Source-identity checks completed in **0fcfa5a**: the three multi-gene groups cannot support a single-gene alias. The adopted identity/retrieval separation remains intact.

Greek v1 rules **ebff4b4** failed during oracle review before implementation (**dadef78**). Its raw spelling abstention was incorrectly used as a no-target-in-query oracle. V2 separately froze biological references in **8ee443a**, candidate **e3ad3fd**, failure evidence **00ab163**, normal revert **9a7cdeb**. Do not patch or relabel either failed study.

V2: **704/704 raw lookup expectations; 4,032 preserved non-proposal parses; 21 unsafe Greek query frames across three names**. Full tests **1,926 passed / three failed / three existing xfails**, Ruff clean. The exact H17 query compiled offline to IL4R with three plans; that does not outweigh new false target assignments. All three unsafe merged groups abstained. Full evidence and traces: `research/se_target_query_greek_orthography_v2/results/`.

First scientific boundary: the parser skips target lookup for `size > 2`; complete names never reach the correct whole-name resolver. It instead adds FCGRT from “α chain” inside an HLA-B name, A2M from the domain description in a C5 name, and CD8B from “CD8 β” inside the SMYD1 alias “CD8 β opposite”. Prioritize **TARGET_QUERY_AUTHORITY_SPAN_BOUNDARY_DIAGNOSIS v1**, diagnosis/design only, before another alias implementation. Inspect whole-name ownership, embedded aliases, and existing grammar/modality/indication/family safeguards; do not simply raise a token limit or blacklist phrases.

Separate: `_TARGET_JOIN` has an ASCII-only lookbehind, blocking Greek-ending dual names. Also, I misread source election: it keeps the FIRST symbol per source, not the last. One synthetic expected ambiguous candidate ID was therefore wrong (GQ32 versus actual GQ31). This remains a failed preregistration error. Future fixture oracles must validate expected canonical IDs against the frozen baseline before implementation.

Restored src/tests/scripts are byte-identical to **8ee443a** (the adopted target-reference implementation). Restored full tests are running; record their result before treating restoration verification as complete. No aliases from the failed candidate remain active. Human-PoC recovery stays STOPPED. No ranking, qualification or duplicate changes. H21–H25 remain untouched; H6–H10 secondary/unrun. Engine remains unvalidated. This supersedes older next-step instructions below.

# 2026-10-12 SOURCE IDENTITY CHECKS — COMPLETE; THREE GROUPS ABSTAIN

`research/se_target_source_identity_checks_v1/` captures all seven HGNC genes, current reviewed UniProt entries and every shared cross-gene accession in the three suspect groups. **None certifies a single interchangeable gene identity.** Tubulin and interferon have distinct sequences and inactive/demerged shared identifiers; calmodulin has identical sequences but three distinct genes/accessions plus ambiguous unreviewed/historical bridges. New aliases for these groups must remain unresolved. Existing graph repair is separate; no production changes here.

Proceed autonomously with a general, conservative Greek orthography preregistration: retain exact lookup behavior, require uniquely grounded contributing gene identities for new admissions, preserve all ambiguous claims rather than filtering competitors away, and freeze authority-derived collision expectations before implementation. Do not use a three-target blacklist or rely solely on current disagreement flags. Common-name/NCIt admission remains separate. All holdouts, human-PoC stop and isolation restrictions below persist.

# 2026-10-12 ALIAS DIAGNOSIS RESUMED — AUTHORITY IDENTITY CHECK REQUIRED

The target-reference interface is adopted (details below). New read-only diagnosis of the existing 96 Greek proposals is in `research/se_target_query_alias_coverage_v1/greek_authority_form_diagnosis.md` and JSON. Original authority spellings: **93 resolved / three ambiguous; 92 source-symbol agreements**. Three resolved groups have multiple canonical source-record symbols, but only one has a canonical-symbol disagreement flag. Inspect actual contributing identifiers before admitting new aliases; a raw RESOLVED flag alone is insufficient. Do not patch the resolver or choose a preferred gene in an alias milestone. No new alias implementation/preregistration yet. Next: diagnose those source groups and freeze a principled eligibility/abstention rule, then orthography; NCIt synonym admission remains separate. All holdout and human-PoC restrictions below persist.

# 2026-10-12 TARGET REFERENCE INTERFACE — ADOPTED

Preregistration **3ac5faa**; implementation **07d104b**. `TARGET_REFERENCE_IDENTITY_SURFACE v1` passed all T1–T12: **1,828 tests passed / three existing xfails**, Ruff clean. Exact identity now travels separately from biological retrieval text; wrong entity/version/symbol references fail closed. Qualified IDs cannot leak into connector literals. Legacy canonical symbols/labels and absent-reference serialization are preserved.

Formal evidence: `research/se_target_reference_identity_surface_v1/`. **4,704 parses / zero scientific differences; 16 unchanged raw+intent controls; 103 complete scientific compatibility cases; 1,791 historical source checks; 36 source-request comparisons; nine gate comparisons; seeds 0/1/42 identical.** Historical tests now distinguish immutable acceptance provenance from current compatibility, exactly as preregistered; no historical artifacts/scorers were changed. The failed prior identity experiment remains recorded and reverted.

FXI now carries TARGET:F11 through five plans with biological search literals. Bare F11 remains ambiguous. **IL-4Rα and factor XI still lack aliases.** This is diagnostic development evidence only, not validation.

Next: resume `TARGET_QUERY_ALIAS_COVERAGE v1`. Read its policy and source packet, then diagnose/freeze general authority-backed Greek orthography and NCIt synonym semantics before implementing either. The bulk NCIt structural projection is not alias admission; validate protein forms and P90 annotation/source semantics. No fuzzy matching, substring inference, qualifier deletion, target-specific rules or trial-level inheritance.

**H21–H25 remain frozen/unrun/unprobed; H6–H10 remain unrun. Human-PoC recovery stays STOPPED.** C056, capitalization nondeterminism and the failed prednisone/prednisolone preregistration remain separate. No live searches or replays in this milestone. Overall engine remains unvalidated. This supersedes the historical in-progress entries below.

# 2026-10-12 TARGET REFERENCE INTERFACE DIAGNOSIS — IN PROGRESS

Checkpoint **31cc721** records 25 direct consumer reads and the next design at
`research/target_reference_identity_surface_diagnosis_v1/design.md`. No new
implementation preregistered yet. Investigate additive exact ontology references
separate from biological retrieval surfaces, and historical/current contract-test
separation without changing frozen evidence. Production remains restored to
533c699. Continue with baseline stubbed source-request/attribution controls before
freezing any successor implementation. All holdout and human-PoC restrictions below
remain in force.

# 2026-10-12 TARGET QUERY COVERAGE — FROZEN SUITE; IDENTITY DEPENDENCY REVERTED

Human-PoC recovery remains STOPPED. H6–H10 remain UNRUN. Fresh H21–H25 primary
suite frozen first in **1e1705c**; still unrun/unprobed. No new holdout answers were
used for target development. Parent **TARGET_QUERY_ALIAS_COVERAGE v1** opened in
**e4a5b8d** with 672 authority forms / 276 entities / seven frames / 16 controls.

Diagnosis: IL-4Rα lacks Greek spelling equivalence to installed IL-4R-alpha;
authorities establish approved IL4R (IL4RA is a synonym). Factor XI has an NCIt
protein -> UniProt -> encoded HGNC gene relationship to F11; raw name matching
also finds a measurement concept and is insufficient. Bare F11 is ambiguous
with ZNF160. Unique FXI recognition subsequently loses identity by serializing
only F11, causing discovery compilation refusal. No new aliases implemented.

**TARGET_QUERY_RESOLVED_IDENTITY_PRESERVATION v1: FAILED / REVERTED.**
Preregistration **533c699**, candidate **612c088**, failure **ed33b7d**, revert
**7e8f58e**. Frozen audit: 4,704 parses with zero compared biological-target or
span/provenance differences; 16/16 resolver controls unchanged. FXI compiled five
plans; bare F11 remained ambiguous. New focused tests 14 pass; three hash seeds
produce identical JSON. Full tests: **1,709 pass / 6 fail / 3 existing xfails**;
Ruff clean. Failure I8 includes legacy AK6 serialization, sealed parser-output
contracts and a protected discovery-source hash. I6 independently fails: a
stubbed FDA connector searches `description:"TARGET:GAX1"` rather than GAX1.
No candidate changes after results. Restoration **106 tests pass** and full
src/tests/scripts diff against 533c699 is empty. Human-PoC bytes unchanged.

Evidence: `research/se_target_query_resolved_identity_preservation_v1/`.
Next justified work is an identity-versus-search-surface interface diagnosis,
including every consumer and historical frozen-contract migration semantics,
before preregistering another implementation. The shared canonical_id field
currently serves incompatible roles. Preserve historical failed results; never
change old frozen populations/source hashes to make a successor pass.

NCIt 26.09d public bulk structure survey: 13,032 identifier records; 6,060 satisfy
unique protein-accession/encoded-HGNC structural checks. This is NOT alias
admission; protein-form and P90 synonym semantics still require a contract.
Receipt and extracted assertions are preserved under the parent alias packet.
No target-specific source selection, new source calls at runtime, live runs or
replays. Alias capitalization nondeterminism and the failed prednisone/prednisolone
receipt oracle remain separate and unchanged; C056 remains unchanged.

Source reconciliation: connected GitHub m11-identity-graph was **979ba4d**, an
ancestor 237 commits behind local e4a5b8d when inspected. Checked Biotech Tool
Context Drive material was older (entity-layer design August); targeted handoff/
alias searches found no newer project policy. Newer local October evidence
governs. No private advice/meeting-preparation material was copied.

# 2026-10-12 TREATMENT_COHORT_ATTRIBUTION_REPRESENTATION v1 — FAILED / REVERTED

Policy: `docs/se_policies/treatment_cohort_attribution_representation_v1.md`.
Result: `research/se_treatment_cohort_attribution_representation_v1/result/summary.md`.
Preregistration **bbf52e5**; candidate **56513a2**; scoring freeze **a17d3af**;
formal failure **97a82c0**; normal implementation revert **98ed522**.

R1 failed because the new frozen receipt labels overclaimed receipt of each
alternative in “prednisone or prednisolone.” Both controls were incorrectly
labeled REGIMEN_RECEIPT. The 33 adopted attribution-audit labels were not changed.
R7's exact reader-output comparison also failed on pre-existing hash-dependent
case-variant alias selection (`human_poc.py:389`). Neither failure was patched or
rescored. Supplementary probes preserve all 98 reader decisions across three
hash seeds; only alias capitalization differs. The formal R7 failure stands.

R2–R6, R8 and R9 passed. Full candidate tests: **1,824 passed / 3 existing xfails**;
Ruff clean. Restoration tests: **87 passed**. All **1,707** pre-existing tracked
src/tests/scripts files and all **seven original result files** retain baseline
hashes. Diff of src/tests/scripts against **7103da1** is empty. C056 remains
unchanged, including the existing reader defect. No live runs or replays.

Failed-candidate counts: **15 ownership / 13 receipt / 26 regimen receipt /
44 unresolved**; these are not adopted relationships (two receipt labels fail
grounding). All 65 negative expectations remain non-owning. The previously
unresolved 14 still yield **nine regimen receipt / five unresolved / zero new
ownership**. No human-PoC fact, gate, shortlist membership or ranking changed.

**STOP further human-PoC recovery of these 14 until stronger sources or explicit
structured result attribution exist.** Do not implement another attribution
rule, fix alias ordering, retry this representation, or move to the next root
cause under this milestone. Historical materializer/scorer require the reverted
candidate model; archived source and exact failure evidence are retained.
H6–H10 remain **UNRUN**; H16–H20 remain development evidence.

# 2026-10-12 HUMAN_EFFICACY_TREATMENT_ATTRIBUTION_CONTRACT v1 — DESIGN COMPLETE

Contract: `docs/se_policies/human_efficacy_treatment_attribution_contract_v1.md`.
Packet: `research/se_human_efficacy_treatment_attribution_contract_v1/`.
Captured evidence and annotated controls frozen in **eaf98d2 before evaluation**.

Complete 33-row source/arm/alias audit; 9,359 registry document entries scanned
across the seven frozen runs (includes repeated snapshots). Raw CT.gov arm
labels, intervention links, IDs and aliases exist, but no validated result-arm
bridge rescues any of the 14 unresolved asset-specific claims. Background
references, ordinary-word protocol/acronym matches and candidate trial lists
are explicitly excluded as ownership proof.

Recovery counts for asset-specific efficacy: **0 safely certifiable; 0 blocked
only by identity; 0 recoverable by representation alone; 14 unsupported under
the captured result scope** (12 regimen/pooled-result limitations, two non-
treatment candidates). **9/14 have certifiable receipt-only component edges**;
those do not license regimen efficacy inheritance. Three PI-specific result
strata remain missing. Clinical-content and quantity labels are unchanged.

Grounded contract checks: 65/65 existing negative expectations remain UNKNOWN;
six existing positive attribution reader outputs unchanged; eight structured
and three prior discourse designs match their constraints. Current reader
still falsely accepts C056's first regimen-list item; that parser defect is
not fixed by this design. These are grounded-record checks, not automatic
prose extraction or generalization validation. The 33-row scientific decision
remains 15 scoped positives / 18 UNKNOWN, not a rescore of primary validation.

**Human-PoC behavior is NOT implementation-ready.** Minimum extension:
TreatmentCohortAttribution with separate receipt and efficacy-owner status,
asset/trial/arm/result-group identities, regimen scope, exact provenance,
qualifiers and contradiction reasons. Raw payload retention is already
available; current flat statements/clinical results lack this certificate.
Next proposed separately preregistered milestone:
**TREATMENT_COHORT_ATTRIBUTION_REPRESENTATION v1**, lossless representation only,
without human-PoC promotion, identity changes or routing changes. Not opened.

Stop before implementation. No production/source/tests/scripts changes; all
still match c5bc865. Earlier frozen packets remain hash-identical. H16–H20 stay
diagnostic/development data; **H6–H10 remain UNRUN**. No searches or replays.

# 2026-10-11 HUMAN_EFFICACY_QUANTITY_BINDING_CONTRACT v1 — NOT IMPLEMENTATION-READY

Design: `docs/se_policies/human_efficacy_quantity_binding_contract_v1.md`.
Packet: `research/se_human_efficacy_quantity_binding_contract_v1/` (every-witness
relation table, exact spans/edges, unchanged expected labels, offline results,
and smallest proposed local ResultBinding extension). Design inputs plus three
necessary discourse ambiguity cases were frozen in **120b669 before evaluation**.

**No production change or implementation preregistration.** The offline check
operates on manually grounded semantic records, not a new text extractor.
Clinical-content binding matches all **33/33** labels: four false witnesses
reject; all 19 removed clinical rows, both legacy positives and all eight
controls retain positive content. Full asset-specific binding matches only
**19/33**, preserving **5/19** removed clinical rows, both legacy positives and
all controls, while rejecting the four false numerical cases. The remaining
14 positive-content rows cannot certify their candidate treatment edge under
strict identity/regimen policy (PET30/though, regimen components/pooled arms,
and unresolved compound-treatment identity). Labels remain frozen; this is
not a holdout rescore or a declaration that their clinical outcomes are false.

**Required full-chain acceptance target FAILED; stop before implementation.**
The proposed representation is local typed treatment/cohort/outcome/quantity
spans and relation kinds, with existing fact routing and attribution guards
retained. It is not coded. A minimal grammar/grounder and boundary provenance
are absent from the current flat EfficacyStatement. Implementation readiness
requires reconciling positive clinical-content expectations with asset-specific
emission, plus specifying/test-grounding automatic edges and multi-span limits.
A representation cannot make a conjunction or response stratum into a drug.

Previous efficacy v1 remains REVERTED. Source/tests/scripts still match c5bc865;
v1 and diagnosis-v2 packet hashes are intact. No target/indication/qualification/
identity/modality/ranking/routing changes, searches or replays. False human-PoC
remains first priority. H16–H20 are diagnostic/development data, never future
generalization evidence; **H6–H10 remain UNRUN**.

# 2026-10-11 HUMAN_EFFICACY_BOUNDARY_DIAGNOSIS v2 — DIAGNOSIS ONLY / COMPLETE

Frozen diagnosis: `docs/se_policies/human_efficacy_boundary_diagnosis_v2.md`.
Evidence packet: `research/se_human_efficacy_boundary_diagnosis_v2/` (exact
side-by-side passages, source context, offsets, current/archived predicate
traces, selection and integrity checks).

Compared all **4 false claim witnesses (3 distinct passages)**, all **19 v1
clinical claim/run losses (12 distinct passages)**, both changed legacy
positives, and 8 representative accepted claims. All 33 reproduce PASS under
restored human_poc_v4. All 21 wrongly lost clinical/legacy inputs pass the
archived population check but fail its quantity binder. This isolates the
failed attempt's preservation defect to its clause/quantity-link mechanism.

Supported semantic boundary: an observed clinical-result proposition must
resolve clinical participants, disease outcome, outcome magnitude, and treated
asset/arm roles. Those roles can span clauses and bounded comparison
continuations. Identifiers, assay measurements, modeled entities/parameters,
confidence levels, thresholds, baseline burden and cohort size have different
roles. Clinical-content truth is separate from strict asset/regimen attribution;
existing regimen and nonasset identity concerns are recorded without changing
frozen labels.

**No implementation-ready rule has been preregistered. No efficacy fix or other
root-cause work is authorized by this diagnosis. Stop here.** The failed v1
attempt remains REVERTED; all source/tests/scripts still match c5bc865 and the
prior preregistered/first-result packet hashes remain intact. False human-PoC
remains first priority; a later proposal must make the relational boundary
concrete before changing behavior. H16–H20 remain diagnostic/development data,
not future generalization evidence. **H6–H10 remain UNRUN.**

# Codex handoff — S&E engine, 2026-10-11

## Current outcome — HUMAN_EFFICACY_CONTEXT_SAFETY v1 REVERTED

Clean milestone baseline / primary diagnosis **c5bc865**. Preregistration **38ca6c8**;
implementation **755e9c1**; scorer fixture completion **b1645a3** (before scoring);
failed-result record **5b5eccf**; normal fixture revert **7abb0bc** and implementation
revert **39bcef1**. Production source/tests/scripts are byte-identical to c5bc865;
extractor is again `human_poc_v4`. No post-result behavior or label patch was made.

Frozen rules: `docs/se_policies/human_efficacy_context_safety_v1.md`.
First result: `docs/se_policies/human_efficacy_context_safety_v1_result.md`.
Population, accepted/UNKNOWN examples, independent witness judgments, attempted code,
all first-result scores/quality logs and byte-restoration proofs:
`research/se_human_efficacy_context_safety_v1/` and its `result/` directory.
Failed scorer is retained in the result packet and in b1645a3 history; it is removed
from production scripts by the normal revert. Do not run it against restored source
and overwrite the preserved failed attempt.

**Frozen E1–E10:** E1 PASS; E2 PASS; E3 FAIL; E4 PASS; E5 FAIL; E6 FAIL;
E7 PASS; E8 PASS; E9 FAIL; E10 FAIL. **Decision: FAILED_ACCEPTANCE / REVERTED.**
Both exact H18/H19 false witnesses reject under the attempt, but that is not adoption.
The structural quantity matcher preserves only **143/162** pre-adjudicated clinical
claim/run witnesses, rejects **57/59** independently adjudicated false numerical witnesses,
and preserves **94/96** legacy reader-call outcomes. The frozen population includes
110 distinct admitted passages, 71 new semantic controls, 13 structured controls and
all 96 existing reader inputs captured during the baseline full suite.

Attempt quality: **1,971 passed / 20 failed / 3 expected xfails**, 1,994 total.
Required Ruff checks clean (cache-write sandbox failure retried without cache, no code change).
After normal reversion: all **87** old human-PoC tests pass; restored-source Ruff clean.
Full tests/se was not rerun after reversal: exact source/tests/scripts restoration is
independently verified against the baseline full run of **1,701 passed / 3 expected xfails**.
Every protected policy/source and original selected run hash is unchanged.

Failure details BEFORE any future preregistration:
- Clinical grammar is over-restricted: `10/16 evaluable pts ... ongoing BM CR`, measured
  flare-risk reduction, comparator ellipses and plain patient-count outcome formulations
  lose valid admission. Some receptor/identifier ratios still masquerade as outcome values.
- C056 was baseline PASS but frozen expected UNKNOWN: a first-item regimen attribution
  weakness, outside the intended nonclinical-context scope. Do not retroactively remove
  this failed control or silently change the v1 expectation.
- Earlier `test_indication_gate_semantics_v3.py::test_frozen_compilation_and_source_isolation`
  pins the old human-PoC source hash and rejects any authorized later module change. An
  explicit historical-test lifecycle/ownership decision is needed before a new attempt.
  No old hash oracle was edited or xfailed. Even without that conflict, E6/E9 fail.

**No durable efficacy fix is adopted.** The two original false human-PoC defects remain
unresolved under restored production. Context safety remains the first milestone priority,
but a future v2 needs new diagnosis/preregistration; v1 may never be patched or rescued.
Stop here. No target-alias, qualification, modality, identity, ranking or routing milestone
was implemented. Later causes stay separate: H17/H20 aliases; H19 qualification/PEPTIDE/
discovery; H18 trade names; H16 modality-before-target ordering.

## Primary validation and diagnosis — preserved

Primary H16–H20 validation is **FAIL 0/5**, label commit **eed63eb**, result **ab0f02b**,
diagnosis **c5bc865**. `PRIMARY_VALIDATION_FAILURE_DIAGNOSIS v1` and the 66-entry failure
boundary register remain frozen. H16/H18/H19 INCOMPLETE outputs are valid scoring inputs
under preregistered `--allow-incomplete`; H17/H20 are frozen refusals, not rephrased.
Original interrupted H17/H18 runs remain excluded. **H16–H20 are now exposed diagnostic /
development data, never fresh generalization evidence. H6–H10 remain UNRUN.** No live search,
corpus replay, top20 optimization or later root-cause implementation was launched.

All older “untouched H16–H20” descriptions below are historical states, superseded here.
The adopted indication stack remains intact. The previous outcomes are preserved verbatim.

## Historical handoff — prior outcomes

# Codex handoff — S&E engine, 2026-10-11

## Current outcome — INDICATION_GATE_SEMANTICS v3 ADOPTED (2026-10-11)

Audit **ff2a69b**, preregistration **6b82d42**, implementation **625db7a**,
adoption **dc16bdb**. Clean baseline 8da5e61. **V3-G1–V3-G10 all PASS.**
Production gate bytes exactly match the v2 attempt 148b71e; only the new validation
oracle differs. Psoriasis Vulgaris is UNKNOWN because the pinned NCIt authority has
no disease alias. No special alias, threshold, scientific exception or post-score patch.
Failed v2 and all earlier experiments are permanently preserved below and in history.

Policy: docs/se_policies/indication_gate_semantics_v3.md (sealed preregistration);
result: docs/se_policies/indication_gate_semantics_v3_result.md. Frozen artifacts,
authority proofs, fresh score, review, quality and post-adoption projections:
research/se_indication_gate_semantics_v3/. Scorers:
scripts/score_indication_gate_semantics_v3.py and readout_indication_gate_semantics_v3.py.

Frozen population: 38 references, 655 historical diagnostic indication-only exclusions,
eight original result hashes including TAC01/mint5, all 28 controls (9 authority-proved
PASS / 19 UNKNOWN), JCAR014, and all 103 compilation-v3 controls. Direct preimplementation
authority audit proves each positive identity/synonym/path or accepted B-cell rule.
Every control correct; all 103 compiled outputs exact; all historical artifact hashes
and compiler hashes unchanged. No non-indication source/facts/decision/policy changed.

Rules: PASS from unique frozen disease ID/synonym, observed-descendant/requested-parent
authority path, or accepted B-cell positive rule. Reverse direction unsupported -> UNKNOWN.
One compatible record suffices after existing conflict/staleness guards. Missing,
ambiguous, incomplete, unrelated or unresolved evidence -> UNKNOWN. Registry evidence
never establishes indication FAIL. Negative-query semantics remain limited/deferred.
INDICATION_NEGATIVE_EVIDENCE_CONTRACT v1 is deferred, not implemented.

Fresh targeted **86 passed**. Full tests/se **1,701 passed / 3 expected xfails**,
1,704 total, zero failures. **ruff check src/ clean.** Fresh sample review: 124 witnesses,
20 distinct pairs, zero unsupported; expanded post-adoption review: all 27 distinct new
PASS pairs across 128 diagnostic new PASS assets, zero unsupported.

References **0 PASS / 5 UNKNOWN / 33 FAIL -> 18 PASS / 20 UNKNOWN / 0 FAIL**;
visible/rankable **5/38 -> 38/38**, all 33 recovered. Diagnostic indication-only
exclusions **655 -> 0**. TAC01 all 157 prior PASS preserved; 324 unsupported FAIL -> UNKNOWN,
membership **545 -> 747**, top-20 order changed; JCAR014 PASS. mint5 unchanged:
membership **244 -> 244**, top-20 order unchanged. Ranking policy unchanged.

Six development top-20 lists: confirmed 30 TARGET_UNKNOWN_FILL, 10 NON_PRODUCT,
2 DUPLICATE, 35 RELEVANT; **41 new rows UNLABELED**. Precision bounds 29.2%–63.3%,
not a point estimate. Exact per-query bounds/rows in diagnostic_readout.json. Full
new blind labels are needed to determine the dominant remaining shortlist root cause;
do not infer junk/off-target status from unknown evidence or start later milestones.
These are development data, not generalization evidence.

**The indication stack is sufficiently finalized for a separate untouched validation
stage. H16–H20 remain completely untouched; H6–H10 unrun.** No targets, reference
products or outputs from those suites were inspected; no live acquisition/replay run.
Stop before holdout execution. Next: separately authorize/plan primary validation,
with terminal commands only when requested; do not automatically run or inspect it.

## Preserved failed outcomes

## Current outcome — INDICATION_GATE_SEMANTICS v2 REVERTED (2026-10-11)

User resolved diagnosis 4cf8485: no negative-evidence contract now; current registry
indications may establish positive PASS or UNKNOWN only. That decision remains valid.
Preregistration **43c7cc5**, implementation **148b71e**, failure record **5a4940e**,
normal revert **518185c**. Source and tests are byte-identical to 4cf8485; adopted
compilation v3 stayed frozen throughout. No post-result behavior/test/control patch.

Policy: docs/se_policies/indication_gate_semantics_v2.md. Population, authority manifest,
score, manual review, quality logs, failure and restoration:
research/se_indication_gate_semantics_v2/. Scorer preserved at
scripts/score_indication_gate_semantics_v2.py (requires the failed implementation to
reproduce; checkout its commit plus the preserved scorer, not restored production).

Frozen: 38 references, all 655 historical diagnostic indication-only exclusions,
eight original run hashes including TAC01/mint5, original 16 controls plus 12 new
controls, JCAR014 NOS and compilation-v3 source/query preservation.
**V2-G1 PASS; G2 PASS; G3 FAIL; G4 PASS; G5 PASS; G6 PASS; G7 PASS;
G8 PASS; G9 PASS; G10 FAIL.** 27/28 semantic controls correct.
Failure: psoriasis_synonym expected PASS for Psoriasis Vulgaris, but no alias exists
in the selected frozen NCIt disease names (nor disease/finding query roles). The
implementation correctly preserved insufficient normalization as UNKNOWN; however,
the frozen PASS criterion failed. The positive-control authority premise was not
verified before preregistration. Do not amend, retroactively rescue or adopt v2.

Targeted **85 passed / 1 failed**. Full tests/se **1,700 passed / 1 failed /
3 expected xfails** (1,704 collected), sole failure psoriasis_synonym. Attempt and
restored-source Ruff clean. Full suite not rerun after normal reversion; exact source/
tests restoration independently verified. Test logs retain harmless cache-write warnings.

Failed-development readout: references **18 PASS / 20 UNKNOWN / 0 FAIL**, all 33 former
indication-only excluded references free of other FAIL gates (gate-rankable; shortlist
membership/order not recomputed). Diagnostic indication-only exclusions **655 -> 0**;
128 newly PASS diagnostic assets. Manual sample: 124 witness records, 20 distinct
disease pairs, zero unsupported positive claims. TAC01 preserves 157 old PASS,
324 unsupported FAIL -> UNKNOWN, no new PASS; JCAR014 control PASS. mint5 unchanged.
These are failed-attempt observations, not adoption or generalization evidence.

After revert, durable counts remain **0 PASS / 5 UNKNOWN / 33 FAIL** references and
**655** diagnostic indication-only exclusions. Historical visible references 5/38;
top-20 diagnostic pollution remains 57 TARGET_UNKNOWN_FILL, 40 NON_PRODUCT_GENERATION
plus one QUALIFICATION_MISS, four duplicates. No post-adoption precision/membership/
order readout applies. Ranking and all other policy layers stayed unchanged.

**Next:** independently verify authority coverage for every positive control before
a NEW gate preregistration. No invented synonym or post-result expectation change.
Keep insufficient normalization UNKNOWN. INDICATION_NEGATIVE_EVIDENCE_CONTRACT v1
is deferred: claim type, identity, indication, negative relation, authority/provenance,
review/confidence and contradictions must be designed separately; nothing added here.

The indication stack is **NOT finalized** for primary validation. **H16–H20 remain
completely untouched; H6–H10 unrun.** No live acquisitions/replays launched. No user
terminal run is justified now. All prior failures and diagnosis remain preserved below.

## Preserved diagnosis and previous outcomes

## Current gate milestone — DIAGNOSIS ONLY, evidence contract unresolved (2026-10-11)

Production remains adopted compilation v3 at **ebbb554**. No gate code or query
compilation changed. Diagnosis and baseline freeze:
docs/se_policies/indication_gate_semantics_v1_diagnosis.md and
research/se_indication_gate_semantics_v1/ (manifest, provenance audit, baseline population).
Frozen: 38 references, 655 historical diagnostic indication-only exclusions, prior
16 semantic controls, TAC01/mint5, compilation readout and all source hashes.
Current reference indication decisions: **0 PASS / 5 UNKNOWN / 33 FAIL**.

All 9,127 indication facts across eight existing runs are unreviewed registry first-
condition strings, not exhaustive asset inventories or negative incompatibility
assertions. Different disease evidence cannot establish asset-level incompatibility.
G3 cannot be made nonvacuous from these facts without a new negative-evidence contract.
Stop under the user's unresolved scientific/architecture exception: decide whether
to authorize an explicit reviewed, claim-backed asset-level incompatibility assertion
contract, or separately defer FAIL/G3. No preregistration or acceptance score exists
yet; do not treat this diagnosis as an adopted/reverted experiment.

Next: resolve that contract, then preregister and execute gate semantics. All prior
failures and compilation v3 remain preserved. **H16–H20 completely untouched;
H6–H10 unrun.** No live acquisition/replay or terminal run is needed now.

## Preserved adopted compilation result

## Current outcome — INDICATION_REQUIREMENT_COMPILATION v3 ADOPTED (2026-10-11)

Clean baseline **2633539**, preregistration **5e972d5**, implementation **4cdfa8a**.
All frozen criteria C3.1–C3.8 PASS. Entire v2 population 76/76; expanded population
103/103. All 19 grammatical-negation controls retain the negator in one coherent
UNRESOLVED disease span. Parser consumes that grammatical operator before entity
lookup. Compiler preserves it against molecular component trimming and positive concept
normalization. No global NOT suppression: six biological contexts and actual resolver
NOT ambiguity (ALG3/NR4A2) are unchanged; explicit ALG3/NR4A2 remain uniquely resolved.
Three syntax-insufficient controls retain ambiguity and existing refusal.

Scope: compilation only. Production changes are the five preregistered intent files:
parser.py prepass, intent.py GRAMMATICAL_OPERATOR, compiler.py coherent construction,
indication_compilation.py (v2 algorithm plus operator protection), grammar.py (shared
frozen query-role loader and syntactic rule). No downstream gate/compatibility/identity/
qualification/modality/efficacy/ranking/routing/attribution changes. All protected source
hashes and every v2 research/policy hash remain fixed. No patch after acceptance results.

Targeted tests **117 passed**. Full tests/se **1,672 passed, 3 expected xfails** (1,675
collected); `ruff check src/` clean. TAC01 and mint5 retain semantic equivalence;
JCAR014's accepted PASS and all 16 gate controls are byte-identical. Failed v2/v1 history
below is permanently preserved; v3 does not amend or retroactively adopt either attempt.

Policy: docs/se_policies/indication_requirement_compilation_v3.md. Frozen population,
manifest, authority diagnosis, exact scorer output, combined acceptance, quality logs and
offline diagnostic readout: research/se_indication_compilation_v3/. Offline scorer:
scripts/score_indication_compilation_v3.py. Correct compilation for H2/H4/H11–H14:
non-small cell lung cancer, ulcerative colitis, non-small cell lung cancer, paroxysmal
nocturnal hemoglobinuria, hidradenitis suppurativa, multiple myeloma, respectively.
Each is one coherent requirement, with no target/mutation/format residual requirements.
H13 source Finding remains unresolved normalization, rather than erased or declared disease.

Limits: the unchanged gate still compares most literal disease requests exactly; synonym,
case/spacing, subtype and incomplete indication evidence remain downstream defects.
Negation is represented correctly but the gate does not enforce exclusion semantics.
No claim of recovering the 33 indication-excluded references or improving shortlist
precision/recall; no development result is generalization evidence. The readout measures
compilation only and does not recompute product/ranking outcomes.

**Next separate milestone: INDICATION_GATE_SEMANTICS v1.** Diagnose/preregister its
population and criteria before implementing same-disease/synonym/subtype PASS, positive
incompatibility FAIL, sparse/incomparable evidence UNKNOWN, and incomplete NCIt typing.
That milestone is NOT implemented here. Qualification/routing/target milestones remain
deferred. **H16–H20 remain completely untouched; H6–H10 remain unrun.** No live acquisition
or long replay launched. No terminal run is needed now; stop before gate implementation.

## Preserved prior outcomes

## Current outcome — INDICATION_REQUIREMENT_COMPILATION v2 REVERTED (2026-10-11)

Preregistration **30bfdbe**, implementation **f46dd76**, failure record **2b0a80e**,
normal git revert **2e297c6**. The failed indication-semantics v1 history below remains
authoritative and preserved. Worktree source/tests/scripts equal clean baseline 7f09c26.

Frozen population: 76 exact queries (six diagnostic queries H2/H4/H11–H14, TAC01,
mint5, every v1 semantic/leakage control and failure, JCAR014, and general constructions),
35 positive and 41 negative compilation controls, 16 unchanged gate controls, all protected
source hashes. Frozen NCIt roles locate query spans only; no new disease gate semantics.
See docs/se_policies/indication_requirement_compilation_v2.md and
research/se_indication_compilation_v2/ (manifest, population, scorer output, failure and
restoration records). Acceptance: C1 FAIL, C2 PASS, C3 PASS, C4 FAIL, C5 PASS,
C6 PASS, C7 PASS, C8 FAIL. Exact query controls: 75/76.

The attempt coherently compiled all six diagnostic disease phrases and removed their
nonclinical residual leakage; TAC01, mint5 and JCAR014 PASS remained equivalent. All
parser/retrieval/non-indication fields, 16 gate decisions and protected source were fixed.
However, frozen `not NSCLC` produced `NSCLC`. Existing parser marks `not` ambiguous
between TARGET:ALG3/TARGET:NR4A2; NCIt also lists NOT as a molecular alias. Independent
component trimming overrode grammatical negation and the intended soft boundary. This
can replace a negative disease request with a positive assertion. No post-result patch.

Attempt targeted tests: 114 passed / 2 failed. Full tests/se: 1,669 passed / 2 failed /
3 expected xfails (1,674 collected). Ruff failed with 3 E741 violations. After normal
reversion: 108 indication/intent tests pass, ruff check src/ clean, exact byte restoration
verified. Full suite was not rerun after reversion; the failed-attempt suite is retained.

No durable diagnostic improvement: all requirements/results return to baseline. Reference
visibility remains the frozen 5/38, with 33 indication-only exclusions; 57 TARGET_UNKNOWN_FILL
and 40 NON_PRODUCT_GENERATION plus one QUALIFICATION_MISS top-20 rows remain recorded.
No post-adoption remeasurement applies because this milestone was reverted.

Next principled option: NEW compilation-only preregistration with query grammatical
operator/span binding preceding molecular-role trimming and conservative retention of
overlapping lexical roles. Do not retry v1's broad compilation+gate implementation.
INDICATION_GATE_SEMANTICS v1 is deferred and has NOT been preregistered/implemented:
compilation must first be adopted. Qualification/routing/target milestones remain deferred.
H16–H20 remain completely untouched. No live acquisition/replay launched; no user
terminal run is required at this point.

## Preserved previous outcome

## Current outcome — INDICATION_REQUIREMENT_SEMANTICS v1 REVERTED (2026-10-11)

The operator authorized v1. It was preregistered at `0aefe85`, implemented at `93c1f83`,
scored/recorded FAILED_ACCEPTANCE at `8f466b4`, and reverted normally at `d8f5023`.
Engine source and tests are byte-identical to `c70461e` (engine `f0e90e6`).
Worktree remains `/home/djmann/projects/bve-b8`, branch `m11-identity-graph`.

Authoritative record: `docs/se_policies/indication_requirement_semantics_v1.md`.
Frozen artifacts: `research/se_indication_semantics_v1/`. 38 reference products, 33
indication-only reference exclusions, 655 indication-only excluded assets, 16 semantic
controls, 18 non-disease terms, and TAC01/mint5 accepted artifacts were frozen before code.

Criteria: I1 FAIL; I2 PASS; I3 PASS; I4 PASS; I5 FAIL; I6 FAIL; I7 PASS; I8 FAIL.
Attempt tests/se: 1,653 passed, 10 failed, 3 expected xfails. Attempt and restored ruff
check src/ are clean. After reversion, 108 indication/intent tests passed. The full suite
was not rerun after reversion; source/tests restoration is verified byte-for-byte.

The attempt made 31/33 excluded references visible, but 21 through absent requirements,
only 10 through proper PASS decisions; Crovalimab and zilucoplan still FAIL. TAC01 lost
JCAR014's accepted PASS (Not Otherwise Specified treated as negation), with 14/20 order
positions changed; mint5 stayed invariant. All non-indication data/decisions stayed fixed;
23 positive condition strings reviewed, no false positive indication assertion found.

Failures to diagnose BEFORE a newly preregistered v2:
- NSCLC crosses the parser's AMBIGUOUS_TARGET `cell` span; residual-only grouping erases
  the disease requirement. Recover full disease spans without changing target parsing.
- NCIt C128429 Hidradenitis Suppurativa is typed Finding; the disease-type filter omits it.
  Use an authority taxonomy with explicit indication semantics, not all Findings.
- Different observed diseases do not establish an exhaustive drug indication history:
  Crovalimab has only aHUS facts, zilucoplan only COVID-19 in the frozen rows. Preregister
  the positive incompatibility evidence needed under incomplete/open-world coverage.
- Legacy B-cell lymphoma has a broad/subtype name ambiguity (C188021/C3457), and disease
  qualifiers cannot be handled by an unrestricted negation-token veto.

No behavior patch after results. Failed attempt remains in history. No durable diagnostic
improvement: frozen baseline remains 5/38 visible references, 33 indication-excluded,
57 TARGET_UNKNOWN_FILL, 40 NON_PRODUCT_GENERATION plus 1 QUALIFICATION_MISS top-20 rows.
No post-adoption remeasurement applies. Do not start qualification/routing/target milestones.
**H16–H20 remain entirely untouched. Do not run or inspect them.** No long live acquisition
or benchmark replay was launched. Next action: a NEW v2 preregistration resolving these
indication semantics failures; untouched validation is premature until adoption.


Start here, then read `docs/se_handoff_state.md` for the older context. That file predates
the target-recognition work, so this file wins wherever the two disagree.

## 1. Where you are

- **Worktree:** `/home/djmann/projects/bve-b8`. This is **not** the main repo checkout at
  `~/projects/biotech-asset-valuation-engine`.
- **Branch:** `m11-identity-graph`. **HEAD:** `a508831`, the diagnosis commit (or later).
  The tree is clean apart from this file.
- **Engine code version:** `f0e90e6`. Every later commit is docs, labels or research scripts
  only.
- **Environment:**
  - conda env `biotech-env`;
  - `PYTHONPATH=/home/djmann/projects/bve-b8/src` when running anything from this worktree
    (an editable install may point at another worktree);
  - tests: `python -m pytest tests/se -q`, last run 1,663 passed, 3 xfailed;
  - lint: `ruff check src/`.
- **Live runs:** `bve-se-search` with `--source-index ~/se_runs/aacr_probe5/source_index.yaml`,
  output under `~/se_runs/<name>/`.

  **Never launch live runs or TAC01/mint5 replays yourself.** Background jobs are
  memory-reaped. Ask the operator to run them in their own terminal, giving the exact
  command.

## 2. Non-negotiable workflow rules (operator)

1. Every milestone gets a preregistration doc in `docs/se_policies/<NAME>_v<k>.md`, which
   freezes the population and acceptance criteria. It is committed **before** any
   implementation.
2. Adopt or revert strictly. Never patch after results, and never weaken criteria to fit an
   implementation. A failed version is recorded as FAILED_ACCEPTANCE, reverted, and
   re-preregistered as v<k+1>.
3. No query-specific, product-specific or name-list exclusions.
4. Do **not** tune ranking. The order in `reporting/shortlist._rank_key` is frozen.
5. Never combine distinct root causes in one implementation.
6. UNKNOWN is preferable to a false target. Preserve every adopted TAC01/mint5 identity,
   target, modality and efficacy rule.
7. Commits use conventional messages via `git commit -m ... -m ...`. A hook blocks
   `--no-verify` and the `printf | git commit -F` pattern. End every commit message with
   `Co-Authored-By:` attribution.

## 3. Validation sets and their status

| Set | Doc | Status | Use |
|---|---|---|---|
| TAC01, mint5 | (benchmarks) | **FROZEN** | Only to confirm a fix for an independently found bug |
| H1–H5 | `heldout_validation_suite_v1.md` | Run; FAIL 0/5 | Diagnostic only, never generalization evidence |
| H6–H10 | `heldout_validation_suite_v2.md` | **Unrun**, partially exposed | Secondary confirmation only |
| H11–H15 | `heldout_validation_suite_v3.md` §5 | Run at f0e90e6; FAIL 0/5; target recognition 4/5 exact | Now **diagnostic** only |
| **H16–H20** | `heldout_validation_suite_v4.md` (`eaace55`) | **Untouched**: never run, never resolved, no outputs inspected | **Primary** validation for the next shortlist fix |

H16–H20 must stay untouched. Do not run their queries, do not resolve their targets, and do
not look up their reference products in any run output.

Rubric, used by every suite:
- labels: RELEVANT, WRONG_TARGET, DUPLICATE, NON_ASSET, UNVERIFIABLE;
- blind labels are committed before scoring;
- per query: P@20 ≥ 0.70, Recall@all ≥ 0.60, NON_ASSET ≤ 1, DUP ≤ 2, false human-PoC = 0;
- suite: PASS at ≥4/5.

Scorers live at `scripts/score_heldout_suite_v{1,3}.py`, with labels in
`research/se_heldout/labels_v{1,3}.json`.

## 4. What was just finished

- **TARGET_AFFIX_RECOGNITION v5 ADOPTED** (`f0e90e6`): `anti-X` and `X-directed` parse exactly
  as bare `X`.
- **DUAL_TARGET_SEPARATOR_SAFETY ADOPTED** (earlier).
- **HELDOUT v3 (H11–H15) scored** (`b0580ec`): FAIL 0/5, with no false human-PoC.
- **SHORTLIST_NONPRODUCT_OFFTARGET_DIAGNOSIS v1** (`a508831`), diagnosis only. Read
  `docs/se_policies/shortlist_nonproduct_offtarget_diagnosis_v1.md`. Data is in
  `research/se_shortlist_diag/`.

Key findings:
- **All 38/38 reference products in H2, H4 and H11–H14 were discovered, and 33 are
  EXCLUDED solely by `strategy.indication` FAIL.**
  - `ontology/indications.py` knows a single concept (B_CELL_LYMPHOMA).
  - `intent/compiler.residual_indications` turns every other disease phrase into single-word
    literals, e.g. `["non-small","lung","cancer"]`.
  - It also includes non-disease words such as `inhibitors`, `G12C` and `complement`.
  - These literals are compared by exact `IN` against whole registry condition strings. So
    any asset *with* indication evidence FAILs, while evidence-less names stay UNKNOWN and are
    shown.
- The 102 bad top-20 rows break down as:

  | Class | Rows |
  |---|---|
  | D TARGET_UNKNOWN_FILL | 57 |
  | A NON_PRODUCT_GENERATION | 40 (all qualify via `DIRECT_APPROVED_NAME` = a ChEMBL molecule name) |
  | B QUALIFICATION_MISS | 1 (methane; the NCIt veto sits below the ontology route) |
  | H DUPLICATE | 4 (trade name vs INN) |
  | C false target PASS, E known incompatible, G discovery miss | 0 each |

- F (ranking) has 3 relevant rows displaced because modality precedence comes before the
  target decision. This is recorded only.
- **Requiring target PASS is unsafe.** 5 of the 15 RELEVANT rows are target-UNKNOWN (all of
  H4's TL1A hits, plus gumokimab and netakimab).
- **An entity link is not a junk discriminator.** 5 of the 15 RELEVANT rows also have none.
- **H15_EXTRA_TARGET_DIAGNOSIS v1** is recorded but not fixed (`h15_extra_target_diagnosis_v1.md`):
  - the LDLR alias "familial hypercholesterolemia" turned the disease phrase into a target;
  - the H15 indication became `["inhibitors","homozygous"]`.

## 5. Historical v1 recommendation (superseded by the outcome above)

The diagnosis recommends this milestone as having the highest precision benefit and the
lowest false-negative risk. The operator subsequently authorized it; v1 was attempted and reverted as recorded above.

Proposed shape:
- Disease phrases compile to concepts, matched against registry conditions by
  name-or-subtype. This generalizes the adopted B-cell-lymphoma mechanism in
  `ontology/indications.py` and `gates/evaluator.evaluate_indication`.
- Non-disease residual words are no longer indication literals. `residual_terms` must stay
  untouched, because they drive trial retrieval (see the docstring of `residual_indications`).
- A phrase that cannot be matched yields **UNKNOWN, never FAIL**.
- The vocabulary must come from an authority, not hand-picked per query. A hand-picked
  list would be tuning on diagnostic data.
- Preregister:
  - a population of query disease phrases and registry conditions that is **not** drawn from
    H11–H20;
  - acceptance criteria that include the off-indication admission risk;
  - TAC01/mint5 parity;
  - `tests/se` green.

  Then validate on H16–H20, with the operator running it live.

Later milestones, each separate, in this order:
1. NONPRODUCT_QUALIFICATION v1 (A+B). Use an authority substance-type discriminator above
   the `DIRECT_APPROVED_NAME` route. No name lists, no entity-link rule.
2. TARGET_UNKNOWN_SHORTLIST_ROUTING v1 (D). Re-measure after the indication fix first.
3. TARGET_AUTHORITY_COVERAGE v1.
4. TRADE_NAME_IDENTITY v1 (H).
5. H15_EXTRA_TARGET_DIAGNOSIS.
6. D-var (KRAS G12C) and D-iso (Claudin 18.2).
7. Merged-survivor display-name cleanup.

## 6. Code map (only what you need next)

| Path | Role |
|---|---|
| `src/bve/se/intent/parser.py` | Query to spans. Contains the affix and separator rules (adopted; do not touch) |
| `src/bve/se/intent/compiler.py` | `residual_indications` builds `strategic_gap.indications` |
| `src/bve/se/ontology/indications.py` | Indication concept vocabulary (frozen by `indication_gate_semantics.md`; a change is declared) |
| `src/bve/se/gates/engine.py` (~L227) and `gates/evaluator.py` (`evaluate_indication`, `evaluate_requirement`) | The indication gate |
| `src/bve/se/discovery/asset_qualification.py` | `qualification_reason` (route order) and `qualification_veto` |
| `src/bve/se/pipeline.py` (~L915–1030) | Qualification, low-support routing, gating |
| `src/bve/se/reporting/shortlist.py` | `build_shortlist`, `_rank_key` (frozen) |
| `scripts/score_heldout_suite_v3.py` | Template for a v4 scorer (swap REFS/INTENDED/paths/labels) |

## 7. Known caveats

- Ruff flags style issues (E702, E741, F401) in `research/se_shortlist_diag/*.py`. They are
  research scripts outside the `src/` lint scope, and they reproduce their committed JSON
  outputs.
- Under the frozen matching rule, suffixed INNs (`pozelimab-bbfg`) don't match the bare
  reference. This is recorded as-is in v3 §5 and carried into v4 §2.
- In the final report of the previous session, the diagnosis commit hash was misquoted as
  "4a0e1c2…". The correct hash is **`a508831`**.
