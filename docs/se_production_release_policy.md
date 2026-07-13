# S&E controlled-production release policy

Public label: **Production-validated public-data S&E screen; pre-diligence—not verified truth.**

V6 validated acquisition ranking, hard gating, semantic INCLUDE/UNKNOWN/EXCLUDE routing,
structured diligence queues, citations, and separation from valuation. Production use remains
limited to that public-data, pre-diligence scope.

Every production run must persist append-only audit events containing the run, code, evaluator,
specification, and source-configuration identities. Monitoring must cover source-family health,
UNKNOWN rate, citation failure rate, semantic route leakage, and drift from the approved baseline.
Route leakage is a stop condition; other alerts require documented review under operating limits.

Revalidation is mandatory after any material ranking, gating, routing, evaluator, rubric, or source
configuration change. It is also required at least every 180 days as public sources and schemas
evolve. A changed hash or elapsed interval fails closed; prior holdouts must never be rescored.
