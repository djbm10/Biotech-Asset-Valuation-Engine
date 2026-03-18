# Knowledge Layer (Minimal, Structured Retrieval)

`bve.intelligence.knowledge_layer.KnowledgeStore` is a SQLite-backed store for
Phase 2 intelligence artifacts. It intentionally prioritizes relational filters
over vector search.

## Stored Record Types

- `events`
- `valuation_diffs`
- `review_decisions`
- `memos`
- `dossiers`
- `raw_documents`
- `extraction_results`
- `structured_signals`

Each row stores `source_trace_json` so provenance can be recovered for audit.

## Example Queries

```python
from datetime import date
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.taxonomy import EventType

store = KnowledgeStore("outputs/intelligence_phase2/knowledge.db")

# Events by company + event type + date range
events = store.get_events(
    company_id="company-rly",
    event_type=EventType.TRIAL_READOUT,
    date_from=date(2026, 1, 1),
    date_to=date(2026, 3, 1),
)

# Valuation diffs for one asset, restricted to trial readouts
diffs = store.get_valuation_diffs(
    asset_id="asset-rly2608",
    event_type=EventType.TRIAL_READOUT,
    limit=20,
)

# Review decisions for financing-driven runs
reviews = store.get_review_decisions(event_type=EventType.FINANCING, limit=20)

# Generate and persist a dossier snapshot
dossier = store.generate_dossier(company_id="company-rly", asset_id="asset-rly2608")

# Retrieve provenance for any stored record
trace = store.get_source_trace("valuation_diffs", diffs[0].run_id)

# Reconstruct full chain (source_url -> raw_document -> extraction_result
# -> structured_signal -> event -> valuation_diff -> review_decision -> memo)
record = store.get_record_with_trace("valuation_diffs", diffs[0].run_id)
chain = record.provenance_chain
source_url = chain["source_url"]
```

## Dossier Contents

`generate_dossier()` composes:
- recent events
- current assumptions (from latest valuation snapshot context)
- latest valuation snapshot
- recent valuation changes
- open questions (from deferred reviews and memos)

The generated dossier is itself stored with provenance and can be filtered by
company/asset/date through `get_dossiers(...)`.

## Valuation Diff Storage Boundary

Knowledge storage uses `StoredValuationDiff` (local model) instead of valuation
engine classes. `add_valuation_diff(...)` accepts either:
- a `StoredValuationDiff`
- a Phase 2 valuation diff object (converted internally)
