# S&E Trial Universe Layer (M9B)

A source-agnostic boundary between "where trials come from" and "what the pipeline does
with them".

## Why this came second

M9A made target identity generalize. M9B makes *retrieval* generalize. The existing
`ClinicalTrialsGovAdapter` reads CT.gov's `protocolSection` JSON directly, so its field
names are load-bearing throughout discovery — switching to a bulk AACT mirror would have
meant rewriting matching, not swapping a backend.

## Layering

```
DiscoveryOrchestrator / adapters      consume TrialRecord only
        ↑
TrialUniverseProvider                 fetch(TrialQuery) -> TrialUniverseResult
        ↑
ctgov_rest v2 | aact | hybrid | frozen
```

## Design rules

**No raw payload crosses the boundary.** Providers snapshot their own upstream response
and pass a `TrialSnapshot` (content hash + optional path). Evidence fidelity is preserved
without CT.gov's or AACT's field names becoming a downstream dependency. `TrialRecord`
has no `raw` field on purpose — an "opaque, do not read" dict is a rule nothing enforces.

**Controlled vocabularies are folded, not passed through.** The REST API says
`"RECRUITING"` and `["PHASE1","PHASE2"]`; AACT says `"Recruiting"` and
`"Phase 1/Phase 2"`. `normalize_token` / `normalize_phases` collapse both, so a status or
phase filter returns the same trials on either backend. `test_both_backends_produce_the_
same_normalized_record` compares every field except snapshot and retrieval timestamp.

**A failed backend is `FAILED`, never an empty universe.** A network blip that returned
`SUCCESS` with zero records would be indistinguishable from "no such trials exist" — and
would silently zero out a coverage claim. `HybridTrialProvider` degrades to `PARTIAL`
when one backend is down rather than reporting a clean success over a narrowed universe.

**Providers translate; they do not reason.** `TrialQuery.terms` arrives already
alias-expanded by the M9A ontology. No provider contains biomedical knowledge, and no
provider takes a list of targets of interest.

**No-lookahead lives above the backend.** `TrialQuery.applies()` applies the `as_of_date`
cutoff in Python for every backend, so the guarantee does not depend on getting a `WHERE`
clause right in SQL.

**Alias terms are bound parameters.** Ontology snapshot values reach the AACT backend as
`%s` parameters, never string-interpolated SQL. Pinned by
`test_alias_terms_are_bound_parameters_not_interpolated_sql`.

## Backends

| Backend | Needs | Use |
|---|---|---|
| `ctgov` (default) | nothing | fresh clone, targeted queries |
| `aact` | local PostgreSQL mirror + `BVE_AACT_DSN` | whole-universe sweeps |
| `hybrid` | AACT if present | production: mirror breadth, API recency |
| `frozen` | a JSONL fixture | CI, replay |

`psycopg` is imported lazily inside the AACT backend, so it stays an optional dependency;
without a DSN the provider returns `FAILED` naming `BVE_AACT_DSN`.

`hybrid` queries every backend even when the first succeeds — a mirror a week stale would
otherwise hide newly registered trials — and merges by `trial_id` with first-provider-wins
ordering, so provider order expresses authority.

```python
from bve.se.universe import TrialQuery, build_trial_provider

provider = build_trial_provider("hybrid", aact_release="2026-07-30")
result = provider.fetch(TrialQuery(terms=["PDCD1", "PD-1", "CD279"], max_records=500))
result.provenance()   # "hybrid__aact__2026-07-30+ctgov_rest__v2"
```

`result.provenance()` is the manifest token, the trial-universe counterpart of M9A's
`ontology_version`. `truncated` reports when `max_records` cut the universe short, so a
coverage claim can say so instead of quietly under-reporting.

## Next

- **M9C** — natural language → `SearchIntent` → deterministic compile to `BuyerProblemV2`
- **M9D** — replace the CT.gov-shaped internals of `ClinicalTrialsGovAdapter` with this
  provider, record `provenance()` in `RunManifest`, and add the `--trial-backend` flag.
  The adapter's hardcoded `_TARGET_TERMS` / `_TCE_TERMS` tables come out at the same
  time: those are the CD19/BCMA benchmark leaking into the retrieval path, and M9A's
  alias expansion replaces them.
