# Science Thesis Layer Phase 5 Plan

## Phase 5: Structured Evidence Landing Zone

Phase 5 adds typed science evidence objects and a conservative adapter into
`ScienceThesisBuilder`. It does not add document parsing, LLM extraction,
scoring changes, buyer strategy expansion, or calibration.

The goal is to make future extraction safe:

```text
documents / readouts / decks / transcripts
-> ScienceEvidenceItem / ScienceEvidenceBundle
-> ScienceThesisBuilder.from_existing_evidence(...)
-> ScienceThesis
-> memo / JSON summary / watchlist output
```

Future LLM/document extraction must write into this schema. It should not write
free-form prose directly into scoring.

## Scope

### In Scope

- Add `ScienceEvidenceItem`.
- Add `ScienceEvidenceBundle`.
- Add enums:
  - `ScienceEvidenceDirection`
  - `ScienceEvidenceSourceType`
  - `ScienceEvidenceMappedComponent`
  - `ScienceEvidenceMappedField`
- Add `science_evidence_bundle` to
  `ScienceThesisBuilder.from_existing_evidence(...)`.
- Optionally add:

```python
ScienceThesisBuilder.from_evidence_bundle(bundle, explicit_inputs=None)
```

- Map evidence bundles into existing conservative builder inputs.
- Add unit and regression tests for schema validation and bundle-to-builder
  behavior.

### Out Of Scope

- LLM extraction.
- Document parsing.
- PubMed/news/deck ingestion changes.
- New science weights.
- POS modifier changes.
- Buyer problem library expansion.
- Historical calibration.
- Free-form LLM-to-score paths.

## Models

### ScienceEvidenceItem

Each item is one extracted evidence claim or observation. Every item must be
source-backed.

Required fields:

- `evidence_id`
- `asset_id`
- `source_type`
- `source_id` or `source_uri`
- `quote` or `text_span`
- `mapped_component`
- `mapped_field`
- `direction`
- `confidence`

Recommended fields:

- `document_title`
- `published_at`
- `page_number`
- `section`
- `extraction_method`
- `rationale`
- `warnings`

Validation rules:

- Reject items without source identity.
- Reject items without `quote` or `text_span`.
- Confidence must be bounded from `0.0` to `1.0`.
- Direction must be explicit: supportive, negative, ambiguous, or missing.
- Mapped component and mapped field must be explicit.

### ScienceEvidenceBundle

The bundle groups extracted evidence for one asset.

Fields:

- `asset_id`
- `asset_name`
- `indication`
- `phase`
- `modality`
- `target`
- `mechanism`
- `items`
- `bundle_warnings`
- `unresolved_gaps`

Bundle responsibilities:

- Provide evidence to the builder.
- Preserve unresolved gaps.
- Preserve extraction warnings.
- Avoid collapsing evidence into a score.

## Enums

### ScienceEvidenceDirection

- `supportive`
- `negative`
- `ambiguous`
- `missing`

### ScienceEvidenceSourceType

- `company_deck`
- `press_release`
- `clinical_trial_registry`
- `clinical_readout`
- `paper`
- `abstract`
- `earnings_call`
- `sec_filing`
- `analyst_report`
- `manual`
- `other`

### ScienceEvidenceMappedComponent

- `T`: target/pathway/mechanism confidence
- `D`: dose/exposure/PK-PD/tissue delivery confidence
- `B`: biomarker/translational validity
- `H`: direct human proof-of-concept / efficacy signal
- `M`: clinical meaningfulness
- `S`: safety/tolerability
- `Q`: evidence quality

### ScienceEvidenceMappedField

Use explicit mapped fields so later extractors cannot hide vague claims inside a
generic evidence bucket.

Initial fields:

- `target_pathway_rationale`
- `mechanism_rationale`
- `pkpd_evidence`
- `human_pkpd_evidence`
- `tissue_exposure`
- `target_engagement`
- `dose_response`
- `exposure_response`
- `biomarker_validation`
- `biomarker_clinical_bridge`
- `human_poc`
- `clinical_effect_size`
- `standard_of_care_relevance`
- `mechanistic_safety`
- `observed_clinical_safety`
- `trial_design_quality`
- `endpoint_validity`
- `sample_size_relevance`
- `reproducibility`
- `source_credibility`
- `unsupported_or_ambiguous`

## Builder Adapter

Add a new optional argument:

```python
ScienceThesisBuilder.from_existing_evidence(
    asset_dossier=None,
    science_assessment=None,
    science_result=None,
    science_evidence_bundle=None,
    explicit_inputs=None,
)
```

Optional convenience method:

```python
ScienceThesisBuilder.from_evidence_bundle(
    bundle,
    explicit_inputs=None,
)
```

Internal helper:

```python
_extract_components_from_science_evidence_bundle(bundle)
```

The adapter should map only evidence that exists and is sufficiently direct.
Missing, ambiguous, or unsupported evidence should become warnings, evidence
gaps, diligence questions, or missing critical evidence, not positive credit.

## Mapping Guardrails

### T: Target / Pathway / Mechanism

Credit only direct target, pathway, or mechanism evidence.

Examples:

- genetic validation
- causal pathway evidence
- direct mechanism rationale
- human disease biology support

### D: Dose / Exposure / PK-PD

Credit only direct PK/PD, exposure, tissue delivery, target engagement,
dose-response, or exposure-response evidence.

Do not credit vague translational language as D.

### B: Biomarker / Translational Validity

Credit biomarker validity or biomarker-to-clinical bridge evidence.

Examples:

- biomarker predicts clinical benefit
- biomarker is proximal to mechanism
- biomarker change tracks clinical endpoint

### H: Human POC

Credit direct human efficacy / proof-of-concept only.

Do not let trial design, endpoint quality, or preclinical evidence become H.

### M: Clinical Meaningfulness

Credit clinically meaningful effect vs standard of care or relevant comparator.

Examples:

- effect size is meaningful in indication context
- endpoint improvement is patient-relevant
- benefit exceeds standard-of-care threshold

### S: Safety / Tolerability

Credit observed or mechanistic safety evidence.

Separate:

- mechanistic safety concern
- observed clinical safety signal
- tolerability/adherence risk
- regulatory safety burden

### Q: Evidence Quality

Credit evidence quality, not efficacy.

Examples:

- trial design
- endpoint validity
- source credibility
- sample size
- independent validation
- reproducibility

Trial design maps to Q. It does not establish human proof-of-concept.

## Ambiguity Rules

- Ambiguous translational evidence does not auto-credit D.
- Low-confidence evidence may add partial confidence or warnings, but should not
  give full credit.
- Unsupported mapped claims should add
  `ambiguous_science_evidence_item_mapping`.
- Missing source or quote/span invalidates the item.
- Negative evidence should populate evidence against or warnings, not disappear.
- Conflicting evidence should add conflict warnings and lower confidence.

## Tests

Add:

- `tests/test_science_evidence_schema.py`
- `tests/test_science_evidence_bundle_adapter.py`

Required tests:

- `test_science_evidence_item_requires_source`
- `test_science_evidence_item_requires_quote_or_span`
- `test_science_evidence_item_rejects_invalid_confidence`
- `test_target_evidence_maps_to_T`
- `test_pkpd_evidence_maps_to_D`
- `test_biomarker_bridge_maps_to_B`
- `test_direct_human_efficacy_maps_to_H`
- `test_trial_design_maps_to_Q_not_H`
- `test_ambiguous_translational_evidence_does_not_credit_D`
- `test_low_confidence_evidence_does_not_give_full_credit`
- `test_negative_evidence_adds_warning_or_evidence_against`
- `test_missing_evidence_stays_missing`
- `test_bundle_feeds_science_thesis_builder`
- `test_explicit_inputs_can_override_or_merge_bundle_inputs`

## Definition Of Done

Phase 5 is complete when:

1. A typed `ScienceEvidenceBundle` can be created without document parsing.
2. Every evidence item is source-backed and quote/span-backed.
3. The builder accepts `science_evidence_bundle`.
4. Direct evidence maps conservatively into T/D/B/H/M/S/Q.
5. Trial design maps to Q but not H.
6. Ambiguous translational evidence does not create PK/PD credit.
7. Missing evidence remains visible in the resulting `ScienceThesis`.
8. Existing Phase 1-4 behavior and tests remain unchanged.

## Next Phase

Phase 6 can add LLM/document extraction into `ScienceEvidenceItem` and
`ScienceEvidenceBundle`. The extraction layer should produce source-backed
structured evidence only; it should not directly write scores, modifiers, or BD
actionability.
