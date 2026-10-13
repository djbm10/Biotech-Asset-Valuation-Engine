# THERAPEUTIC_PRODUCT_ROLE_EVIDENCE_REPRESENTATION v1

Baseline ae78bb7. Decision-neutral milestone with a mandatory evidence-availability audit before any production representation implementation. Preserve the scientific contract d22f6b8 byte-for-byte. Do not replace it, change qualification, or acquire sources.

## Frozen population and inputs

Freeze all 1,181 H19 candidate IDs/names/qualification reasons; all 779 raw query snapshots and four snapshot-less ontology document references in the existing result; original 23 H19 diagnosis rows and 21 controls; the two paired information-loss controls from 99e9c06; four negative red probes (three H19 and the paired diagnostic) and four protected positives (paired therapeutic and three existing positive probes); existing qualification regression files. Eight additional native CT.gov schema controls are frozen before rules: therapeutic, imaging, supportive, conditioning, active comparator, placebo/control, combination membership, and a drug in a nontherapeutic-purpose study. They do not introduce new source fields or authority labels. Inputs/population/structural_controls are hash-addressed scientific inputs, not future holdouts.

## G0 source-availability gate

Audit exact fields and semantic levels first. The required therapeutic/nontherapeutic distinction must be supported by an existing structured assertion at the product or intervention-use level, not by an arm/entity/study declaration or an analyst interpretation of descriptive prose. Explicit study purpose, arm type, intervention type, linkage and source text are useful context and must remain visible even when product/use is UNKNOWN.

If the available required distinction exists only in prose, or if all available structured fields assert a different semantic level, STOP at the source-contract boundary. Do not introduce heuristic text labels or adopt a nominal representation that claims the evidence prerequisite has been solved. Missing distinctions for individual cases must remain UNKNOWN; no number of recoveries is an acceptance quota. This gate concerns availability of admissible evidence, not matching frozen H19 outcomes.

## Offline audit mechanics

Read only pinned source/result artifacts. Link candidates to captured records through existing mention IDs and supporting claim document IDs. Link interventions by exact raw mention/existing alias equality after casefold and whitespace collapse; record this transformation and linkage basis. Do not create aliases, merge identities or force ambiguous matches. Keep unmatched candidate/document links visible.

Preserve native intervention type/name/otherNames/description, arm labels/type/interventionNames, both intervention-arm linkage channels, study primary purpose, sponsor/record identifiers, existing source-linked claims and ontology modality annotations. Preserve every raw value with snapshot SHA, document/study ID, JSON path/component index, semantic scope, identity transformation, and deterministic assertion ID. Retain conflicting or different declarations as separate records; different uses across trials are not automatically biological conflicts.

No new kind/use classifier is specified by this audit. DRUG/BIOLOGICAL are ENTITY_TYPE; arm EXPERIMENTAL/ACTIVE_COMPARATOR/PLACEBO_COMPARATOR is ARM_CONTEXT; study primaryPurpose is STUDY_CONTEXT; descriptions are FREE_TEXT, not typed facts. Existing modality/NCIt Cell membership is a product/molecular-type observation under its adopted semantics, not newly inferred therapeutic purpose. Sponsor organisation identity is not sponsor product designation. Existing qualification/identity-validity decisions are observations of the old engine, not independent authority evidence.

Any truly explicit product-kind/use assertion found must be inventoried with its source schema and exact scope; mapping it into a semantic status requires an independently documented authority contract. If none exists, product-kind and intervention-use status is UNKNOWN, while richer native evidence availability is separately measured. Do not use expected labels, string shape, rank, frequency, or qualification route as product-kind evidence.

## Measurements and potential representation

For all 1,181 candidates report availability of structured evidence dropped before qualification, free-text evidence, absent kind/use assertions, and source disagreements with semantic scope. Report required product-kind/use diagnostic bins and their cross-tab, including zeros; UNKNOWN is not absence of all evidence and not nontherapeutic. Separately report native types, arm contexts, study purposes and unmatched linkages. The three H19 non-assets and paired controls require exact field-level explanations of any distinguishing evidence versus missing/prose-only semantics.

If G0 passes, freeze exact representation expectations before coding a production module: source assertion IDs, candidate and context linkage, semantic scope, raw and normalized values, declared/interpreted/unknown/conflicting status, and transformation lineage. No qualification consumer. If G0 fails, an offline availability ledger is audit evidence only, not adoption of a ProductRoleEvidence implementation.

## Acceptance R1–R11

R1: all 1,181 frozen decisions preserved exactly and inputs unchanged; no replay or new qualification rule. R2: protected positive regression expectations unchanged. R3: every structured distinction is visible at its actual scope; no demanded inference where absent. R4: all three H19 non-assets expose exact upstream fields and missing/prose-only evidence. R5: zero experimental-arm to therapeutic-product promotions. R6: entity/product/context/arm/free-text levels remain distinct. R7: 100% emitted audit assertions round-trip to pinned source fields; no fabricated original raw ontology provenance. R8: missing semantic evidence explicitly UNKNOWN; differing source claims preserved, not silently resolved. R9: two independent builds/seeds byte-identical canonical audit artifacts. R10: no production/ontology changes outside an independently justified additive representation; no target/alias/human-PoC/indication/modality/nomination/identity/ranking/acquisition changes. R11: focused audit checks and Ruff; if production code/schema is implemented, additionally full qualification regressions and full tests/se. Do not waive those for a small production change.

If any implementation acceptance fails, record and normally revert without post-result patching. G0 failure instead records the evidence gap and minimum source contract; there is no production implementation to revert. Do not open qualification v2 unless representation is independently adopted. H21–H25 untouched; H6–H10 unrun; human-PoC stopped; 86 target-component cases closed. Datopotamab modality, ESG401 nomination, BL-M02D1 coverage remain separate.
