# H19_CANDIDATE_QUALIFICATION_DIAGNOSIS v1 — completed diagnosis

Population/protocol commit: `4d628ec`; baseline `d21bdd7`. No production behavior changed, no source was acquired, and no engine run/replay was launched. Frozen H19 metrics remain P@20 0.400, recall 0.400, three NON_ASSET, two duplicates and one false human-PoC. This is development diagnosis, not validation.

## Complete first-boundary register

`results/row_table.md` covers every emitted row and all references: 20 emitted rows plus the three missing references, 23 rows total. `row_audit.json.gz` carries exact candidate names/aliases, nomination mentions, identity metadata, type facts, supporting claims, source records, qualification routes, gates and first boundaries. `reference_coverage.json` separately accounts for all five references.

| First boundary | Rows | Interpretation |
|---|---:|---|
| A — non-asset admission | 3 | Experimental-arm DRUG presence promoted to therapeutic-product qualification |
| B — false product-type exclusion | 1 | Datopotamab qualifies, but component-derived PEPTIDE fact fails modality gate |
| C — candidate nomination | 1 | ESG401 appears in an arm description but is not nominated |
| D — captured-source coverage | 1 | BL-M02D1 absent from captured corpus |
| E — identity, separate future work | 2 | Frozen duplicate rows, not qualification failures |
| F — target evidence/review routing, out of scope | 7 | Real products; query-target evidence UNKNOWN, not non-assets |
| No qualification failure | 8 | Frozen relevant emitted rows; does not validate their other claims |

The duplicate boundaries remain distinct: TRODELVY's existing trade-name identity cannot enter the adopted identifier-only merger; the two NK construct names lack a trusted identity bridge. No duplicate fix or reassessment of the frozen labels occurred. False human-PoC remains stopped and separate.

## Datopotamab: component-level lexical type, not an ontology PEPTIDE assertion

The exact claim is `claim:2022030306a59db4acec`, source `document:463268b43ea527c591e7`, NCT07720284. `datopotamab_exact_field.json` pins the exact intervention index, description field, snapshot hash and source record. The raw text says:

> Dato-DXd is an ADC comprised of a recombinant humanised anti-TROP2 IgG1 mAb, MAAP-9001a, which is covalently conjugated via a cleavable drug-linker, MAAA1162a (the complex of MAAA-1181a and a maleimide tetrapeptide linker), using thioether bonds to the topoisomerase I inhibitor DXd.

The product-level subject is an ADC. The peptide text describes its linker, not a standalone peptide therapeutic, target, ontology parent or identity merge.

Exact path:

1. `discovery/adapters.py::_selected_interventions` joins intervention name, description and otherNames.
2. `QueryVocabulary.modality_in` performs substring tests and selects the longest matching modality alias (requested modality priority is empty during ontology-wide evidence extraction). `peptide` (7 characters) wins over `adc` (3), `igg`/`mab` (3). `trap` (4) also occurs inside `tetrapeptide`; no separate fusion-protein claim follows from that substring.
3. `evidence/clinicaltrials.py::ClinicalTrialsEvidenceExtractor.extract` uses `QueryVocabulary.for_ontology`, converts that selected label into a `clinicaltrials_structured` / `ctgov_v1` claim, with direct-observation flag and 0.95 extraction confidence.
4. `fact:71c28d48f9461eb004d3` carries PEPTIDE. The frozen `modality.required` gate observes it and fails. Identity and target gates pass; indication is UNKNOWN. Modality is the only FAIL.
5. The candidate is already `DIRECT_APPROVED_NAME` qualified. Its separate authority annotation is ADC/MATCH, based on `DRUG:DATOPOTAMAB DERUXTECAN`, ChEMBL `CHEMBL4297939`, whose frozen molecule type is **Antibody drug conjugate**. `_with_authority_modality` annotates that result separately and does not replace the gating fact.

Thus bucket B describes a false **modality exclusion**, not qualification rejection. The first error is product/component scope in lexical type extraction; the later disagreement between fact and authority channels compounds its effect. Do not special-case this product or simply prefer a convenient competing label. A future product-type scope contract must preserve genuine peptide/protein therapeutics and mixtures. No modality code changed here.

## Three non-assets: actual admission route versus hypothetical precedence

All three have no identity-bearing/corroborative drug-name lexicon match, no NCIt non-product veto match, no authority modality, and no existing qualification veto. Their saved route is `STRUCTURED_THERAPEUTIC`. `non_asset_routes.json` preserves all four source intervention observations and exact arms/design fields.

- **[68Ga]Ga-TTP**: NCT06715020, `armsInterventionsModule.interventions[1]`; source type DRUG, linked to experimental arms. `designModule.designInfo.primaryPurpose` is DIAGNOSTIC. Its own description specifies a TROP2-targeted PET radiotracer for imaging; the diagnostic arm explicitly withholds anticancer treatment between imaging examinations. The code ignores this distinction when converting arm membership to therapeutic observations. A true TROP2 binding/imaging role does not establish therapeutic-product status.
- **Rescue Medications**: NCT06132958 intervention index 4 and NCT07216703 index 6. Both are generic premedication categories, with alternatives/classes such as antihistamines, acetaminophen equivalents, corticosteroids and G-CSF. DRUG typing and experimental-arm linkage generate two therapeutic observations. No single product identity is established by this category label.
- **Rescue Medication**: NCT06841354 intervention index 2, the same generic premedication problem. Its description even contains the source's own H1 “agonist” wording; the audit preserves it without silently correcting the source.

First divergence: `adapters._arm_relationships` maps EXPERIMENTAL/ACTIVE_COMPARATOR to THERAPEUTIC. `resolution.registry` accumulates `therapeutic_observations` and `structurally_typed_drug`. `qualification_reason` treats DRUG/BIOLOGICAL plus one therapeutic observation as independently decisive. The first two terms describe schema/arm membership, not necessarily distinct therapeutic-product identity. Identity-validity PASS downstream does not repair that semantic gap.

All other routes were audited: direct-name and synonym routes have no hits; construct authority is not the recorded route; development-code and class/category heuristics do not veto these names; NCIt's sidecar contains only exclusively non-product semantic-type names and does not represent every diagnostic substance or generic supportive category. Pure-helper alternate probes with the structured route removed yielded no qualification for any of the three, including zero pharmacologic-context documents under the current helper. These probes do not replace the original saved decisions.

**Precedence is a real but independent risk.** Current order is class-term veto → direct approved-name route → comparator check → NCIt/composite/category veto → structured therapeutic route → corroborated routes. The frozen synthetic conflict probe confirms that direct-name authority returns before an explicit non-product veto can run. Therefore a molecule-name route can bypass such a veto. But none of these three H19 admissions used that route or had that veto. Do not falsely attribute their failure to ChEMBL overriding an NCIt negative.

A molecule's identity does not prove therapeutic use. Conversely, a real named therapeutic used supportively or as a comparator does not cease being a product. Study-level primary purpose must not automatically type every intervention. These distinctions prevent an immediate blanket precedence or diagnostic-purpose patch.

## ESG401 and BL-M02D1

All **779** captured query snapshots were scanned recursively by JSON string field; four additional ontology source records have no query snapshot. The search includes case and separator-normalized supplied forms and checks candidate aliases and raw identity-mention names. `source_scan.json` preserves every hit and exact locator.

**ESG401:** exactly one field hit, NCT06145308, `armsInterventionsModule.armGroups[3].description`: an alternative list specifies ESG401 16 mg/kg, sacituzumab govitecan, or sacituzumab tirumotecan. No ESG401 candidate or identity mention exists. The corresponding intervention name is the generic TROP2 ADC designation. `_selected_interventions` takes primary names and otherNames; it does not promote each alternative in an arm description into a named candidate. This is C, nomination/extraction, not a filtered or wrongly merged ESG401 identity. A future extractor must preserve alternatives and intervention linkage rather than infer that all listed treatments were given together.

**BL-M02D1:** zero source-field hits, candidates or identity-name hits. This is D, captured-source coverage. It does not establish global absence or identify which connector/query/pagination/provider boundary prevented capture. No new source or alternate-query acquisition was performed. H19's recorded INCOMPLETE source status remains a limitation, not an invalidation of its frozen score.

## Independent milestones and next priority

The evidence supports multiple workstreams, not one qualification patch:

1. **Therapeutic product identity versus intervention-use qualification**: three actual non-asset admissions. Highest next precision priority.
2. **Product versus component type scope**: datopotamab's false modality fact/exclusion, separate from qualification and ontology identity.
3. **Authority-name/negative-type precedence**: demonstrated route-order risk, requiring real provenance-aware conflict controls before semantic change.
4. **Candidate nomination from arm alternatives**: ESG401; separate from product typing.
5. **Source coverage**: BL-M02D1; no downstream qualification fix.

No general implementation rule is ready yet. The next step is a separately preregistered **THERAPEUTIC_PRODUCT_ROLE_QUALIFICATION_CONTRACT v1**, design only. It must separate entity identity, intrinsic product kind, observation-specific intervention use, and candidate qualification. It must protect named real therapeutics used supportively while rejecting generic categories and explicitly nontherapeutic entities; neither source membership nor arm role alone is enough. Additional structural controls, if necessary, must be frozen before deriving its final rule. No production implementation is authorized by this diagnosis.

## Validation and custody

All 23 rows, five references, exact claim/document links and 818 pinned input files verify. Existing positive/negative helper controls preserve expectations; 215 existing qualification tests pass. Twelve synthetic semantic controls are frozen for design, not scored against an invented new classifier. Ruff clean. No production changes or full engine replay; full tests/se not needed for diagnosis-only work.

H21–H25 untouched; H6–H10 unrun. The 86 target-identity cases remain closed/evidence-blocked. Human-PoC recovery remains stopped.
