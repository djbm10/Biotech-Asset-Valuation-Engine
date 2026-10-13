# THERAPEUTIC_PRODUCT_ROLE_EVIDENCE_REPRESENTATION v1

Status: **STOP at G0 source-evidence boundary. Production implementation NOT_STARTED; representation NOT_ADOPTED.** Preregistration: `918d296`; baseline: `ae78bb7`. The existing scientific contract `d22f6b8` is unchanged. No production code, schema, authority snapshot or qualification decision changed; nothing requires reverting.

## Finding

The upstream evidence is richer than AssetEvidence, but it does not provide the required typed product/use distinction for the frozen negative-versus-positive controls. Native CT.gov intervention type, arm type, intervention-to-arm links and study purpose are recoverable. Descriptions contain additional semantics. A container can preserve these fields but cannot turn their contents into independent product-kind or intervention-use assertions without a new extraction/source contract.

The complete native-field inventory covers all 779 captured snapshots (128 distinct CT.gov leaf paths, seven AACR paths, four PubMed paths), plus four snapshot-less ontology references. ClinicalTrials.gov's intervention schema in this corpus contains name, otherNames, type, description and armGroupLabels; arm records contain label, type, description and interventionNames. Study primaryPurpose has study scope. Contact/official `role` fields concern people, not interventions. None supplies the missing typed assertion for the three H19 entities or the paired therapeutic/diagnostic probes.

This is not a claim that every native type is uninformative. Five candidates have DIAGNOSTIC_TEST declarations, three DEVICE, and other native types remain visible. No new interpretation of those categories is adopted. In particular, their existence does not distinguish two DRUG interventions with identical arm fields. The audit's UNKNOWN semantic bins mean **no new product/use classification has been authorized**, not that all source records lack relevant information or that all candidates are clinically ambiguous.

## Evidence availability by level

| Evidence path | Available information | Boundary |
|---|---|---|
| CT.gov intervention/arm records | Exact entity type, name/other names, arm links/types, descriptions | Raw structured context is reduced to flags/counters before qualification; descriptions are free text |
| Trial purpose | DIAGNOSTIC/TREATMENT/PREVENTION at study level | Cannot be inherited by every intervention as intrinsic product kind or individual use |
| Sponsor/collaborator | Organisation identity | No candidate-linked sponsor product designation in these fields |
| Saved claims/facts | Identity, target, indication, stage, modality, efficacy and relevance | No independently typed product-kind/intervention-use predicate; identity_valid and qualification reasons are engine conclusions |
| ChEMBL molecule-type sidecar | Antibody/ADC/protein/small-molecule classification | Molecular/product modality does not itself certify therapeutic development role |
| NCIt cell-product sidecar | Adopted cell-product membership | Existing modality semantics cannot be expanded into a universal product/use authority |
| NCIt non-product sidecar | Non-product semantic categories/veto names | No applicable veto for the three H19 entities; absence of veto is not affirmative therapeutic evidence |
| PubMed/AACR | Captured scientific text | No new prose classifier permitted |

The ledger preserves raw values, snapshot SHA-256, document and JSON component paths, semantic scope, identity transformation and deterministic assertion IDs. Candidate linkage uses existing mentions/aliases with exact case/whitespace normalization only; it does not nominate new candidates. Unmatched links remain explicit. Legacy authority annotations cite their exact saved-result fields and are labelled as such, not fabricated original ontology provenance. No new product/use assertion is emitted.

## H19 and controls

| Entity | Raw structured context | Distinguishing evidence | Qualification before → after |
|---|---|---|---|
| [68Ga]Ga-TTP | NCT06715020 intervention[1], DRUG; experimental arms; study purpose DIAGNOSTIC | Intervention description describes PET radiotracer/imaging; study purpose alone is wrong scope | STRUCTURED_THERAPEUTIC → unchanged |
| Rescue Medications | NCT06132958 intervention[4], NCT07216703 intervention[6]; DRUG, EXPERIMENTAL; TREATMENT study purpose | Descriptions enumerate premedication/rescue/supportive use | STRUCTURED_THERAPEUTIC → unchanged |
| Rescue Medication | NCT06841354 intervention[2]; DRUG, EXPERIMENTAL; TREATMENT study purpose | Description states supportive administration | STRUCTURED_THERAPEUTIC → unchanged |

`results/h19_visibility.json` includes every linked source field, exact raw values and lineage for these rows. No description is converted into a machine-certified role. The two previously frozen paired controls differ in intervention description only; the qualifier inputs and DRUG/EXPERIMENTAL declarations are identical. Four negative semantic probes therefore remain known failing controls, not repaired tests. The protected therapeutic probe and three existing therapeutic controls retain qualification. Eight additional preregistered native-schema controls preserve therapeutic, diagnostic, supportive, conditioning, comparator, placebo, combination and nontherapeutic-study context without arm promotion.

## Counts

1181 candidate rows; 7220 exact field round-trips; 75 candidates with matched structured interventions; 32 with unmatched CT.gov source-document associations; 1171 with available unclassified text. These sets overlap. Three entity-type variations and six mixed-arm contexts are preserved; they are not automatically product-kind conflicts.

| Product-kind bin | Count |
|---|---:|
| ambiguous/conflicting | 0 |
| diagnostic/imaging | 0 |
| other non-therapeutic | 0 |
| supportive/background | 0 |
| therapeutic | 0 |
| unknown | 1181 |

| Intervention-use bin | Count |
|---|---:|
| ambiguous | 0 |
| background/concomitant | 0 |
| comparator | 0 |
| conditioning | 0 |
| diagnostic | 0 |
| investigational therapeutic | 0 |
| placebo/control | 0 |
| supportive | 0 |
| unknown | 1181 |

Cross-tab: UNKNOWN × UNKNOWN = 1,181; every other cell = 0. Full cross-tab and native entity/arm/purpose counts are in `results/summary.json`. These are availability/authorization diagnostics, not a newly validated classifier.

## Validation and acceptance

- All 802 pinned input hashes verified, including the original contract and all 779 snapshots.
- All 1,181 stored qualification reasons preserved exactly. This is a read-only comparison, not a live replay or recomputation of frozen candidates.
- 7,220 source-field assertions round-trip to exact pinned values; no arm assertion emits therapeutic-product or intervention-use certification.
- Seed-0/default and seed-42 independent audit outputs are byte-identical, including deterministic gzip artifacts and assertion IDs. `results/hashes.json` covers generated audit outputs; H19 visibility is a derived report.
- Four focused audit tests pass. All 215 qualification regressions pass. Ruff clean.
- Full tests/se not run because no production code/schema changed. The preregistration requires it if production changes; that branch was never entered.

G0 fails: required distinction is prose-only or represented at a different semantic level. R1/R2 neutrality, R4 visibility, R5/R6 separation, R7 provenance, R8 explicit unknowns, R9 determinism and R10 isolation are satisfied as audit properties. R3 has no structured discrimination to demonstrate for the paired probes; it is not waived or falsely claimed as a semantic success. R11 audit checks pass. No adoption or qualification-v2 preregistration follows.

## Minimum prerequisite, not acquired or implemented

A future evidence contract must supply (1) an exact candidate/product identifier with an explicit product-level kind assertion, and separately (2) exact trial/intervention/arm identifiers with a typed use assertion. Each requires the declaring authority, artifact/release/hash, raw record/field/component and value, semantic scope, deterministic transformation and assertion ID. A regimen/component or study assertion must not substitute for a product assertion. Missing and contradictory assertions remain explicit; source disagreements are retained rather than ranked away.

For the current DRUG/EXPERIMENTAL cases, the captured descriptions could support a separately preregistered, validated evidence-binding/extraction design, but no such classifier is authorized here. Alternatively, a structured authority would need to supply those precise subject-scoped relationships. Merely adding enums, interpreting arm labels, or copying study purpose would not satisfy the requirement. No new source has been acquired and no source's ability to meet this contract is assumed.

Stop at this boundary. Do not open THERAPEUTIC_PRODUCT_ROLE_QUALIFICATION v2 until admissible assertions exist. Datopotamab modality, ESG401 nomination and BL-M02D1 coverage remain separate. Target-component cases stay closed; human-PoC recovery stays stopped; H21–H25 untouched and H6–H10 unrun.

## Reproduction

From the repository, run `python research/se_therapeutic_product_role_evidence_representation_v1/audit.py --output /tmp/product_role_rep_seed0` and a second build with `PYTHONHASHSEED=42` and output `/tmp/product_role_rep_seed42` (fresh output directories required). Run `python -m pytest research/se_therapeutic_product_role_evidence_representation_v1/test_audit.py -q`. The audit requires the pinned original run/snapshot files. No network or replay is used.
