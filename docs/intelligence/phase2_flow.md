# Phase 2: Mapping and Valuation Integration Flow

This document describes the Phase 2 service layer that turns extracted
`StructuredSignal` events into auditable valuation reruns.

## Goals

- Convert structured events into `AssumptionChangeProposal` objects.
- Route large or uncertain deltas to manual review.
- Apply accepted scalar overrides without changing valuation formulas.
- Run before/after snapshots and persist an explicit valuation diff.
- Support rollback to the pre-run state.

## Components

1. `bve.intelligence.phase2.policy.MappingPolicy`  
   Typed config for:
   - allowed parameters per `EventType`
   - minimum extraction confidence for auto-apply
   - materiality threshold (`|delta_pct|`) for mandatory review
   - review mode (`rule_based` or `manual_only`)

2. `bve.intelligence.phase2.mapping_engine.MappingEngine`  
   Input: `StructuredSignal` + current valuation state (`Asset`, `trials`,
   `MarketModel`)  
   Output: `MappingBatchResult` with:
   - generated `AssumptionChangeProposal` records
   - per-proposal audit entries (current value, proposed value, delta, rationale)
   - skipped rule diagnostics

3. `bve.intelligence.phase2.review_queue.ReviewQueue`  
   Routes proposals to:
   - `auto_apply` (AUTO + high confidence + below threshold)
   - manual queue (BOUNDED/MANUAL, low confidence, or high materiality)  
   Reviewer decisions are logged as immutable `ReviewDecision` records.

4. `bve.intelligence.phase2.valuation_integration.ValuationSession`  
   Applies effective overrides (auto + accepted reviews), runs `ValuationEngine`
   before and after, and writes:
  - `before_valuation.json`
  - `after_valuation.json`
  - `valuation_diff.json`  
  - `run_manifest.json` (run_id, timestamp, asset_id, assumptions snapshot, artifact paths)
  Also emits `ValuationRun` metadata and supports `rollback_last()`.

`valuation_diff.json` schema includes:
- `asset_id`
- `event_id`
- `assumptions_changed[]` with `{field, old_value, new_value, delta, delta_pct}`
- `valuation_before`
- `valuation_after`
- `delta_npv`

## Safety Invariants

- Existing valuation formulas are unchanged.
- Non-scalar parameters (`lifecycle_events`, `competition_model`) are never
  auto-mutated.
- LLM output is not applied directly; only schema-validated proposals can
  reach valuation integration.
- Every applied delta is traceable via proposal IDs, reviewer decisions,
  override map, and persisted before/after artifacts.
