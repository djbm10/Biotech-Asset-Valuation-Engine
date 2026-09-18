# S&E Search Intent Layer (M9C)

Turns a typed question into a `BuyerProblemV2` — deterministically, or not at all.

## Why this came third

M9A made target identity generalize; M9B made retrieval generalize. Neither is reachable
from a question until something maps free text onto them. This layer is only worth
building now because the ontology beneath it generalizes: on the old 47-line alias stub,
an NL front end would have been a plausible-sounding interface over a two-target system.

```
"recruiting phase 1/2 CD19 bispecific T cell engager trials"
        ↓  parse_query          (deterministic, rule-based)
SearchIntent                    spans + resolved criteria + residuals + warnings
        ↓  compile_intent       (pure function)
BuyerProblemV2                  → existing S&E pipeline
        ↘  intent_to_trial_query
TrialQuery                      → M9B provider
```

Both halves are persisted: `SearchIntent.original_query` keeps what was asked, and the
spans keep how it was read.

## Design rules

**Rule-based, not model-based.** A language model reading the question would resolve
targets by plausibility — the exact failure M9A removed. This parser can only recognize
what the ontology snapshot and the closed registry vocabularies contain.

**Deterministic end to end.** `problem_id` is `nlq_` + a digest of the whitespace- and
case-normalized query, so the same question always produces the same problem id and a
byte-identical compiled problem. Pinned by
`test_compilation_is_byte_identical_for_the_same_question`.

**Longest phrase wins, non-overlapping.** `bispecific T cell engager` resolves as one
`T_CELL_ENGAGER` rather than `bispecific` plus a separate engager term.

**Targets resolve from single tokens or pairs only.** Letting a four-word phrase reach the
resolver would match approved protein *names* and drag in whole families.

**Unrecognized text stays unrecognized.** Anything no vocabulary claims becomes a
`RESIDUAL` span and, at compile time, a free-text indication — flagged in `warnings`, never
promoted to a resolved criterion. Guessing that `myeloma` is an indication concept would
require a disease ontology the snapshot does not yet carry.

**Underdetermined questions do not compile.** No target or no modality raises
`IntentNotCompilable` naming the blockers. Filling in a plausible value to make the
pipeline run would reintroduce the guessing M9A removed. Ambiguity is a blocker too: `p150`
reports both `TARGET:ABL1` and `TARGET:ELP1` and refuses rather than picking.

**No snapshot means no compile.** Without one, no target resolves, so an NL question
abstains with an explicit warning. This is the same degradation contract as M9A: narrower,
never silently wrong.

## The one real inference

Multiple targets force a reading: `CD19xCD3` means one molecule hitting both
(`EXACT_COMBINATION`/`ALL`), `CD19 or BCMA` means either (`ANY`). `_infer_operator`
decides from the connector text *between* the target spans and records the rule. Because
it is the most consequential reading of a query, the inference is always surfaced in
`warnings` so it can be overruled.

## Explaining an interpretation

```python
intent = parse_query("recruiting phase 2 PD-1 monoclonal antibody in melanoma")
intent.explain()
# "'recruiting' -> STATUS RECRUITING [registry_status_vocabulary]"
# "'phase 2' -> PHASE PHASE2 [phase_vocabulary]"
# "'PD-1' -> TARGET PDCD1 [unique_alias_match]"
# "'monoclonal antibody' -> MODALITY MONOCLONAL_ANTIBODY [modality_vocabulary]"
# "'melanoma' -> RESIDUAL [no_vocabulary_match]"
```

Target spans additionally carry M9A's `ResolutionBasis.explain()` output, so the chain
runs query substring → alias → asserting source → canonical symbol → identifier edge.

`BuyerProblemV2.version` is `intent_v1__<ontology_version>`, pinning both the compiler and
the snapshot it resolved against.

## Not yet derivable from a question

`therapeutic_areas` and `indications` need a disease ontology. `StrategicGap` requires at
least one therapeutic area, so an unspecified one compiles to the literal
`"UNSPECIFIED"` rather than being inferred from the target. Callers who know better pass
them explicitly. Adding the Open Targets `disease` dataset to the snapshot closes this.

## Next

- **M9D** — wire `parse_query` → `compile_intent` → `DiscoveryOrchestrator` and the M9B
  provider; add the CLI entry point and record `SearchIntent` alongside the `RunManifest`.
- **Disease entities** — extend the ontology snapshot so indications resolve instead of
  falling through to residual free text.
