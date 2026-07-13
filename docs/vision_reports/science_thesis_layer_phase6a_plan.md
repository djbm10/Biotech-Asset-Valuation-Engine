# Science Thesis Layer Phase 6a Plan

## Phase 6a: Deterministic Evidence Extraction Into Bundle

Phase 6a adds a conservative extractor that maps existing structured repo
objects into `ScienceEvidenceBundle`.

It is a mapper, not an interpreter:

```text
structured object has explicit source-backed evidence
-> create ScienceEvidenceItem

structured object is ambiguous
-> bundle warning / unresolved gap

structured object lacks source or quote/span
-> skip item and warn
```

Phase 6a does not add LLM extraction, scoring changes, POS modifier changes, BD
actionability, thesis prose conclusions, or direct writes into `ScienceThesis`.

## Objective

Create a safe deterministic path:

```text
StructuredSignal / trial readout / endpoint / safety object
-> ScienceEvidenceExtractor
-> ScienceEvidenceBundle
-> ScienceThesisBuilder.from_existing_evidence(science_evidence_bundle=...)
-> ScienceThesis
```

The extractor only fills the Phase 5 schema. The Phase 5 builder adapter remains
the only route from extracted evidence into thesis/scoring.

## Proposed File

```text
src/bve/intelligence/science_evidence_extractor.py
```

## Core API

```python
class ScienceEvidenceExtractor:
    def extract_bundle(
        self,
        *,
        asset_id: str,
        asset_name: str = "",
        indication: str = "",
        phase: str = "",
        modality: str = "",
        target: str = "",
        mechanism: str = "",
        structured_signals: list[object] | None = None,
        trial_readouts: list[object] | None = None,
        endpoint_evidence: list[object] | None = None,
        safety_events: list[object] | None = None,
    ) -> ScienceEvidenceBundle:
        ...
```

Optional convenience functions may be added later, but Phase 6a should start
with one explicit entry point.

## Generic Object Access Helpers

Existing repo objects may be Pydantic models, dataclasses, normal classes, or
dicts. Add a small helper layer so the extractor can work across current object
shapes without hard-coding one schema.

Recommended helpers:

```python
_get(obj, "field")
_first(obj, ["quote", "text_span", "rationale", "description", "summary"])
_source_id(obj)
_source_uri(obj)
_confidence(obj)
_event_text(obj)
```

Rules:

- `_get` should support dict keys and object attributes.
- `_first` should return the first non-empty text-like value.
- `_source_id` should use existing document/source/run ids when available.
- `_source_uri` should use URL/path-like fields when available.
- If neither source id nor source URI exists, skip item and warn.
- If neither quote nor text span exists, skip item and warn.

## Extraction Mapping

Map only explicit structured evidence.

### T: Target / Mechanism / Pathway

Map to `T` when `event_type`, `claim_type`, `mapped_field`, label, or text
explicitly contains:

- target
- mechanism
- pathway
- MoA
- disease biology

### D: Dose / Exposure / PK-PD

Map to `D` when explicit fields/text contain:

- PK/PD
- exposure
- dose
- dose response
- exposure response
- tissue exposure
- tissue delivery
- target engagement
- delivery

### B: Biomarker / Translational Validity

Map to `B` when explicit fields/text contain:

- biomarker
- MRD
- PD marker
- surrogate
- translational bridge
- biomarker-to-clinical bridge

### H: Human Proof Of Concept

Map to `H` only for direct human efficacy / POC evidence:

- endpoint met
- efficacy
- clinical benefit
- response rate
- PFS / OS / remission / disease-specific efficacy endpoint
- human POC

Trial design quality does not map to H.

### M: Clinical Meaningfulness

Map to `M` for:

- endpoint validity
- standard-of-care relevance
- effect size meaningfulness
- patient-relevant endpoint
- clinically meaningful difference

### Q: Evidence Quality

Map to `Q` for:

- trial design
- randomized
- blinded
- controlled
- sample size
- reproducibility
- independent validation
- source credibility

### S: Safety / Tolerability

Map to `S` for:

- safety
- tolerability
- AE / SAE
- dose-limiting toxicity
- discontinuation
- liver / cardiac / immune safety signals
- mechanistic toxicity

## Direction Mapping

The extractor should set `ScienceEvidenceDirection` conservatively.

- positive/supportive language -> `supportive`
- negative/refuting/risk language -> `negative`
- mixed/unclear language -> `ambiguous`
- explicit absence/missing evidence -> `missing`

If direction is unclear, create a bundle warning or unresolved gap instead of a
positive item.

## Source-Backed Evidence Requirement

Every created `ScienceEvidenceItem` must include:

- source identity: `source_id` or `source_uri`
- source-backed text: `quote` or `text_span`
- mapped field
- mapped component
- direction
- confidence
- extraction method
- warnings

If source/text is missing:

```text
do not create item
add bundle warning
```

## Conservative Behavior

The extractor should not:

- infer PK/PD from generic translational language
- infer human POC from trial design
- infer clinical meaningfulness from endpoint presence alone
- infer safety margin from lack of safety events
- infer BD fit
- write science scores
- write POS modifiers
- create thesis prose conclusions

## Tests

Add:

```text
tests/test_science_evidence_extractor_phase6a.py
```

Required tests:

- `test_target_signal_maps_to_T`
- `test_pkpd_signal_maps_to_D`
- `test_biomarker_signal_maps_to_B`
- `test_endpoint_met_maps_to_H`
- `test_endpoint_validity_maps_to_M`
- `test_trial_design_maps_to_Q_not_H`
- `test_safety_signal_maps_to_S`
- `test_ambiguous_signal_adds_warning_or_gap`
- `test_missing_source_skips_item_and_warns`
- `test_missing_quote_or_span_skips_item_and_warns`
- `test_dict_pydantic_and_dataclass_like_objects_supported`
- `test_bundle_feeds_science_thesis_builder`
- `test_extractor_does_not_change_scoring_without_builder`

## Definition Of Done

Phase 6a is complete when:

1. Existing structured objects can be mapped into `ScienceEvidenceBundle`.
2. Items without source identity are skipped with warnings.
3. Items without quote/span are skipped with warnings.
4. Explicit target, PK/PD, biomarker, efficacy, meaningfulness, quality, and
   safety signals map to T/D/B/H/M/Q/S respectively.
5. Trial design maps to Q and never creates H credit.
6. Ambiguous structured evidence becomes warning/gap, not positive credit.
7. The bundle feeds `ScienceThesisBuilder.from_existing_evidence(...)`.
8. No LLM extraction, scoring changes, POS modifier changes, or BD actionability
   changes are introduced.

## Phase 6b Boundary

Phase 6b may add LLM/document extraction, but only as a producer of validated
`ScienceEvidenceItem` and `ScienceEvidenceBundle` objects. LLM output should be
rejected or downgraded when it lacks source-backed evidence. It should not write
scores, modifiers, BD actionability, or final thesis conclusions directly.
