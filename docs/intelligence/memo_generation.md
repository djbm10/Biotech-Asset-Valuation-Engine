# Weekly Memo Generation

`bve.intelligence.memo_generation` builds a short, deterministic weekly memo from
structured records (no free-form claim invention).

## Inputs

- `DossierRecord`
- `StructuredSignal[]` (recent events)
- `StoredValuationDiff[]`
- `ReviewDecision[]`
- optional `ambiguous_signal_ids[]`

## Output

`WeeklyMemoOutput` with:
- markdown memo
- citation metadata (`cited_signal_ids`, `cited_run_ids`, etc.)
- unresolved/open questions
- period bounds (`period_start`, `period_end`)

The memo can be converted to `MemoRecord` via `to_memo_record(...)`.
Persisted `MemoRecord` stores structured references:
- `referenced_event_ids`
- `referenced_diff_ids`
- `referenced_review_ids`

## Required Sections

- `## Key Events`
- `## Valuation Changes`
- `## Why It Changed`
- `## Uncertainties`
- `## Needs Review Next`
- `## Sources`

Every factual bullet includes record citations such as
`[signal:<id>]`, `[event:<id>]`, `[diff:<run_id>]`, `[review:<id>]`.
If valuation diffs are provided, the generator enforces at least one `diff`
citation in the valuation section.

## Prompt Builder

`WeeklyMemoPromptBuilder` emits strict grounding instructions for optional LLM
summarization workflows:
- no invented claims
- mandatory record citations
- explicit uncertainty handling

The deterministic `WeeklyMemoGenerator` is the default path and does not depend
on LLM calls.
