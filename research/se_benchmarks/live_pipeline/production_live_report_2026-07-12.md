# Live Public-Data Acquisition-to-Asset Production Validation — 2026-07-12

## Decision

**PASS.** Release `se-live-cd19-bcma-tce-2026-07-12-v2` completed a fresh live
six-family acquisition, sealed and verified the corpus and exact artifact set, converged in
three discovery passes, and atomically promoted `CURRENT.json`.

The output remains a public pre-diligence screen, not verified truth. All 75 canonical assets
were conservatively routed to `UNKNOWN` because the public evidence did not satisfy the required
human proof-of-concept and deal-access gates. No unresolved asset entered ranking.

## Promoted run

| Field | Result |
|---|---|
| Run ID | `se-2026-07-12-235520-ed4d4bfe5a` |
| Logical date | `2026-07-12` |
| CLI / receipt status | `PROMOTED` / `SEALED` |
| Discovery status | `CONVERGED` |
| Discovery passes | 3 |
| Release manifest hash | `71508a6d1aed78b981d64aa2c073372978327d7b1c9119a489fd5df709f8717b` |
| Corpus manifest hash | `0dcf98693133c8f05dabd47cc6fbc23d12548102cc961c532423b0e3675562c5` |
| Corpus documents / snapshots | 1,273 / 1,273 |
| Search-consumed documents | 546 |
| Canonical assets | 75 |
| Identity mentions | 290 |
| Claims / facts | 1,243 / 1,015 |
| Gate evaluations | 75 |
| Eligible / excluded / unresolved | 0 / 0 / 75 |
| Ranked | 0 |
| Processing failures | 0 |
| Route leakage | 0 |
| Monitoring stops | 0 |
| Immutable artifacts | 1,283 |

## Required source health

| Source family | Verdict | Raw records | Indexed observations | Sealed unique documents |
|---|---:|---:|---:|---:|
| ClinicalTrials.gov | `OK` | 664 | 664 | 656 |
| FDA labels | `OK` | 11 | 11 | 11 |
| PubMed | `OK` | 579 | 579 | 579 |
| SEC EDGAR | `OK` | 222 | 25 | 25 |
| Company press release | `OK` | 1 | 1 | 1 |
| Company pipeline/presentation | `OK` | 1 | 1 | 1 |

All required families were `OK`; there were no `DEGRADED`, `FAILED`, missing, or corpus-health
reconciliation findings. The difference between retrieval observations and sealed documents is
expected provenance-aware deduplication, chiefly repeated ClinicalTrials.gov records returned by
the two target queries.

## Safe abstention

Monitoring emitted one non-blocking alert:

> all discovered assets require diligence; ranking abstained

`unknown_rate` was `1.0`, citation failure rate was `0.0`, route leakage was `0`, and
`stop_reasons` was empty. Promotion certifies operational integrity and conservative routing; it
does not convert missing public evidence into a positive or negative diligence conclusion.

## Incident exercised before promotion

The first strict attempt stopped with exit code 3 because Merck had retired the generic
`/news/` index and returned HTTP 404. No `CURRENT` pointer was created. A header-only diagnostic
identified the canonical generic index at `/media/news/`; the policy was updated without adding
any reference-asset URL, release v2 was rebuilt with a new policy and manifest hash, and dry-run
preflight passed before the successful live retry.

## Verification

The supported `verify_current_run` verifier successfully checked the strict current pointer,
receipt and artifact-manifest anchors, `SEALED` live receipt, result identity, forbidden-symlink
rules, and exact artifact set. A subsequent invocation under the same stable Git revision returned
the same run with `reused: true` and performed no acquisition.

An offline replay from the promoted `corpus/` seal returned `VERIFIED_REPLAY`; canonical candidate,
claim, fact, route, and ranking identities matched the live result exactly, and the replay's own
immutable artifact manifest verified.

Local artifacts are under:

`outputs/se/production/runs/se-2026-07-12-235520-ed4d4bfe5a/`

The scheduled workflow will preserve and restore the most recent verified production artifact for
cross-run continuity. Its repository Actions variable `BVE_SE_USER_AGENT` must contain the same
kind of descriptive agent name and monitored contact email used by this validation.
