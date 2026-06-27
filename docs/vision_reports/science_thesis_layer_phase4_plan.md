# Science Thesis Layer - Phase 4 Plan

## Objective

Add compact JSON-safe Science/BD summaries for audit and replay.

Phase 3a/3b made Science Thesis and BD Fit visible in memos and watchlist summaries.
Phase 4 should preserve the key outputs in machine-readable JSON without serializing the
full rich `ScienceThesis` or `BDActionabilityResult` objects.

## Core Rule

Persist what users saw, not every internal object.

Use compact summaries:

```text
ScienceThesis / BDActionabilityResult
-> JSON-safe summary dict/model
-> valuation.json
-> watchlist summary_json
-> replay/audit tooling
```

Do not dump the full Pydantic/object graph. Full rich objects remain memo-facing and
runtime-facing only.

## Summary Fields

Science summary:

- `science_binding_question`
- `science_modifier`
- `science_score`
- `science_modifier_applied`
- `missing_critical_evidence_count`
- `next_readout_requirement`
- `warnings`

BD summary:

- `bd_route`
- `bd_hard_gate_passed`
- `bd_actionability_score`
- `failed_gates`

Optional metadata if already available:

- `science_scoring_version`
- `science_weight_set_version`
- `science_calibration_status`
- `buyer_problem_id`
- `buyer_id`

## Deliverable 1: Summary Builders

Likely file:

```text
src/bve/intelligence/science_thesis_summary.py
```

Functions or models:

```text
build_science_summary(science_thesis, *, modifier_applied: bool) -> dict
build_bd_summary(bd_actionability, *, buyer_problem=None) -> dict
```

Responsibilities:

- Return plain JSON-safe dictionaries.
- Convert enums to string values.
- Avoid nested rich objects.
- Use `None` for absent values.
- Keep field names stable.

Acceptance:

- Summaries serialize with `json.dumps()`.
- Missing science/BD objects return `None` or empty absent summaries by caller choice.
- Enums are serialized as strings.

## Deliverable 2: Valuation JSON Output

Likely files:

```text
src/bve/valuation/outputs.py
src/bve/valuation/valuation_engine.py
```

Add JSON-safe fields:

```text
science_summary: Optional[dict]
bd_summary: Optional[dict]
```

Keep existing full objects excluded:

```text
science_thesis: exclude=True
bd_actionability: exclude=True
```

Responsibilities:

- Attach `science_summary` when `science_thesis` exists.
- Set `science_modifier_applied` from engine flag.
- Attach `bd_summary` when `bd_actionability` exists.
- Ensure `valuation.json` contains compact summaries.

Acceptance:

- `valuation.json` includes no rich object dumps.
- Render-only `--science-thesis` sets `science_modifier_applied=false`.
- `--apply-science-pos-modifier` sets `science_modifier_applied=true`.
- BD mode includes route/gates/actionability fields.

## Deliverable 3: Watchlist Summary JSON

Likely file:

```text
src/bve/pipeline/watchlist_runner.py
```

Current read-only watchlist fields already include:

- `science_binding_question`
- `science_modifier`
- `science_missing_evidence_count`
- `science_next_readout`
- `bd_route`
- `bd_hard_gate_passed`
- `bd_actionability_score`

Phase 4 should ensure these are stable audit fields and add only if needed:

- `science_score`
- `science_modifier_applied` set to `false` for Phase 3b watchlist enrichment
- `failed_gates`

Responsibilities:

- Preserve disabled watchlist output unchanged.
- Keep enrichment read-only.
- Avoid ranking/composite/tier changes.

Acceptance:

- `summary_json` contains compact science/BD fields when enabled.
- Disabled summary output is unchanged.
- Watchlist science summary indicates modifier is not applied to valuation math.

## Deliverable 4: Tests

Add/extend tests:

```text
tests/test_science_thesis_summary.py
tests/test_deal_comps_integration.py
tests/pipeline/test_watchlist_runner.py
```

Required coverage:

- Science summary is JSON serializable.
- BD summary is JSON serializable.
- `valuation.json` contains compact summaries when enabled.
- `valuation.json` omits rich model dumps.
- render-only science thesis has `science_modifier_applied=false`.
- POS-modifier run has `science_modifier_applied=true`.
- watchlist `summary_json` includes stable science fields when enabled.
- disabled watchlist summary remains unchanged.

## Non-Goals

- No LLM extraction.
- No ranking changes.
- No scoring weight changes.
- No full object serialization.
- No calibration claims.

## Definition Of Done

Phase 4 is complete when `valuation.json` and watchlist `summary_json` preserve the
Science Thesis / BD Fit facts shown to the user in compact JSON-safe form, while full
rich models remain excluded from persisted artifacts.
