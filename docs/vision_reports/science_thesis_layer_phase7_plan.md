# Science Thesis Layer Phase 7 Plan

## Phase 7: Optional Evidence Extraction Pipeline Wiring

Phase 7 makes the Phase 6b LLM evidence extractor usable from existing document
replay or ingestion flows. It should not add new science logic.

The flow is:

```text
document replay / ingestion
-> ScienceEvidenceLLMExtractor
-> ScienceEvidenceBundle
-> optional ScienceThesisBuilder
-> science_summary / memo output
```

## Core Rule

Evidence extraction is opt-in and schema-only.

Phase 7 must not change default valuation, watchlist, replay, scoring, POS, or
BD behavior.

## Scope

### In Scope

- Add an explicit flag such as `--extract-science-evidence`.
- Wire existing document text and metadata into `ScienceEvidenceLLMExtractor`.
- Attach or persist only:
  - `ScienceEvidenceBundle`
  - extraction warnings
  - validation warnings
- Feed the bundle into `ScienceThesisBuilder` only when `--science-thesis` is
  also enabled.
- Preserve existing POS behavior:
  - no POS change unless `--apply-science-pos-modifier` is explicitly set.
- Add fixture/fake-client tests.

### Out Of Scope

- New science scoring.
- New POS modifier behavior.
- Default extraction behavior.
- LLM-generated `ScienceThesis`.
- LLM-generated BD recommendation.
- Buyer strategy expansion.
- Network tests.
- Provider-specific production tuning.

## Proposed Flags

Single-asset or replay path:

```bash
--extract-science-evidence
```

Required combinations:

- `--extract-science-evidence` alone creates/attaches a validated
  `ScienceEvidenceBundle` and warnings only.
- `--extract-science-evidence --science-thesis` feeds the bundle into
  `ScienceThesisBuilder`.
- `--apply-science-pos-modifier` still requires `--science-thesis`.

Do not auto-apply the science modifier because evidence extraction is enabled.

## Pipeline Behavior

### Flag Off

Existing behavior must remain unchanged.

### Flag On

For each eligible document:

1. Collect document text.
2. Collect metadata:
   - document id
   - source URI/path when available
   - source type
   - title
   - published date
   - asset id / company id when available
3. Call `ScienceEvidenceLLMExtractor`.
4. Validate output as `ScienceEvidenceBundle`.
5. Attach or persist the bundle and warnings.

If the extractor returns invalid JSON, unsupported fields, missing source-backed
quotes/spans, or low-confidence/ambiguous evidence, preserve warnings. Do not
silently coerce unsupported output into credit.

## Builder Integration

Only when `--science-thesis` is enabled:

```text
ScienceEvidenceBundle
-> ScienceThesisBuilder.from_existing_evidence(science_evidence_bundle=...)
-> ScienceThesis
```

When `--science-thesis` is disabled, extracted bundles should remain evidence
artifacts only.

## Persistence / Attachment

Prefer a compact attachment first, not a broad schema migration.

Acceptable Phase 7 options:

- attach bundle to an in-memory replay result;
- write a JSON artifact next to replay output;
- persist bundle JSON in an existing document/result metadata field if one
  already exists.

Avoid designing a new long-term evidence database schema in Phase 7 unless the
existing pipeline requires it.

## Guardrails

- LLM output may create only `ScienceEvidenceItem` / `ScienceEvidenceBundle`.
- LLM output may not create:
  - science scores
  - heuristic science modifiers
  - POS changes
  - BD actionability
  - deal route
  - final ScienceThesis prose conclusions
- Missing source identity prevents extraction or item creation.
- Missing quote/span rejects the item.
- Ambiguous/unsupported evidence becomes warnings or unresolved gaps.
- Low-confidence evidence should not create full thesis credit.

## Tests

Use fake clients and fixture documents only.

Required tests:

- `test_extract_science_evidence_flag_off_unchanged`
- `test_extract_science_evidence_flag_on_creates_bundle`
- `test_invalid_llm_output_preserves_warning`
- `test_missing_quote_or_source_rejects_item`
- `test_bundle_feeds_thesis_only_when_science_thesis_enabled`
- `test_no_pos_change_without_apply_science_pos_modifier`
- `test_pos_change_requires_existing_modifier_flag`
- `test_llm_output_does_not_create_bd_actionability`

## Definition Of Done

Phase 7 is complete when:

1. An explicit flag can run science evidence extraction from existing document
   text/metadata.
2. The output is a validated `ScienceEvidenceBundle` plus warnings.
3. Default behavior is unchanged with the flag off.
4. The bundle feeds `ScienceThesisBuilder` only when `--science-thesis` is also
   enabled.
5. POS changes only when the existing explicit modifier flag is enabled.
6. Tests use fake clients only and require no network.
7. No LLM output writes scores, modifiers, BD recommendations, or final thesis
   conclusions directly.
