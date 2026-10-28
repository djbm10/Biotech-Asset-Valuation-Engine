# Prioritized backlog

Ranked by expected reduction in important analyst work or decision error per unit of effort.
Evidence references are to `PRODUCT_AUDIT.md`.

| Rank | Item | Analyst impact | Reliability gain | Frequency / breadth | Effort | Risk | External dependency | Evidence |
|---|---|---|---|---|---|---|---|---|
| 1 | **Analyst fact entry with citation** (ASSERT_FACT: a human adds one field value plus a source; it is stored as an analyst claim; re-screen) | Very high: removes the leave-the-tool loop | High: fixes stay linked to records | 38/39 real open gates; all 5 in-scope misses | Small (reuses claims and the log) | Low: no gate rule changes; human-only; citation required | None | Finding 1 |
| 2 | **Block commercial-stage pre-approval valuation** | Medium | High: prevents a wrong financial deliverable | Every marketed finalist (3 of 7 real candidates) | Very small | Very low | None | Finding 4 |
| 3 | **Cross-holder same-molecule flag** (review only, never merge) | Medium-high for BD (licensee mapping) | Medium | Real: HBM9161 / batoclimab; common in licensed assets | Small | Low: flag only | None | Finding 5 |
| 4 | **Rights-holder vs availability model** (U.S. label → holder known, availability UNKNOWN; territorial licensee notes) | High for Gate D | High | Every marketed asset; every licensed asset | Medium | Medium: must not imply availability | Public filings for real facts | Finding 2 |
| 5 | Stage semantics: separate U.S.-marketed, ex-U.S.-marketed and Phase 4 study | Medium | Medium | Real: rozanolixizumab, telitacicept | Small–medium | Low | None | Finding 6 |
| 6 | Refresh diff between two exports, carrying analyst decisions forward | High once in use | Medium | Every refresh cycle | Medium | Medium (claim-id stability) | None | Finding 9 |
| 7 | Agent: approval / status extraction | Medium | Medium | Marketed assets | Small | Low | None | Finding 8 |
| 8 | Reviewed synonym layer (indication / modality) | Medium | Medium | 11 indication + 8 modality gates on real data | Medium | **High**: touches S&E behaviour and benchmarks; needs a policy | S&E governance | Finding 7 |
| 9 | Performance: avoid a 30 s ontology load per CLI call | Medium | None | Every command | Medium | Low | None | Scorecard 13 |
| 10 | Independent held-out landscape and preregistered thresholds | Required for Gate B | — | — | Medium | — | **Independent curator** | Finding 3 |
| 11 | Real analyst session (Gate H) | Decisive | — | — | Small to organise | — | **A BD professional** | Finding 3 |

## Decision for Cycle 1

Item 1. It is the largest measured obstacle, the cheapest to build, and needs no sign-off.
Items 2 and 3 are small and independent, and follow in Cycle 2 if resources allow.
