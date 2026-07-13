# Live Acquisition-to-Asset Development Replay — 2026-07-12

## Decision

**PASS for the end-to-end development replay gate.** The acquired public corpus was consumed
directly—without reference asset names entering retrieval or extraction—and produced canonical
assets covering GOLD 5/5, SILVER 16/16, and total 21/21 of the development reference universe.

This is not a claim that every discovered asset is transaction-ready. The BuyerProblem requires
human proof of concept and a feasible deal route; public evidence left all 89 discovered assets in
the explicit diligence/UNKNOWN route. No UNKNOWN asset entered ranking.

## End-to-end results

| Stage | Result |
|---|---:|
| Acquired corpus documents | 1,299 |
| Source families represented | 6 |
| Canonical assets | 89 |
| Identity mentions | 341 |
| Cited claims | 1,440 |
| Entailed facts | 1,092 |
| Gate evaluations | 89 |
| Eligible / excluded / unresolved | 0 / 0 / 89 |
| Ranked | 0 |
| Discovery passes | 3 |
| Search attempts | 1,920 |
| Discovery status | CONVERGED |
| Route leakage | 0 |
| Processing failures | 0 |

## Development reference coverage

| Tier | Covered |
|---|---:|
| GOLD | 5/5 |
| SILVER | 16/16 |
| Total | 21/21 |

Reference identities were supplied only to the post-run evaluator
(`bve.se.evaluation.discovery_coverage`). The live/replay runner, corpus adapter, query compiler,
identity registry, gates, and ranking did not read `reference_universe.csv`.

## Operational controls exercised

- complete corpus integrity validation before discovery;
- direct snapshot reuse without a duplicate discovery snapshot tree;
- observed program-name extraction (no publication-title or URL fallback);
- two complete zero-growth passes;
- immutable result, memo, source-health, monitoring, audit, receipt, and checksum artifacts;
- exact INCLUDE / EXCLUDE / UNKNOWN route partition checks;
- explicit all-UNKNOWN monitoring alert with safe ranking abstention.

## Historical-corpus caveat

The historical corpus contains three failed company-press observations and one failed
company/pipeline observation alongside later successes. Under the strict production policy those
families are `DEGRADED`, and `bve-se-run` correctly exits 3 before discovery. This replay used the
four clean API families as required and the two historical company families as optional solely to
validate downstream wiring. A fresh live production run must use the strict six-family policy and
may promote only if every required family is `OK` or `NO_DATA`. That fresh six-family validation
subsequently passed; see `production_live_report_2026-07-12.md`.

## Historical reproduction provenance

The commands below record the development replay used for this report. The current production
runner now requires `source_health.json` and `seal.json` inside a portable corpus and therefore
intentionally rejects this older snapshot-only corpus. New replays should use a promoted live
run's complete `corpus/` directory as documented in the live pipeline runbook.

```bash
MPLCONFIGDIR=/tmp/mpl python -m bve.cli.se_run \
  --problem examples/configs/se/benchmarks/cd19_or_bcma_tce.yaml \
  --source-policy research/se_benchmarks/live_pipeline/development_replay_policy.yaml \
  --replay research/se_benchmarks/cd19_bcma/development/corpus \
  --output-root /tmp/se-production-replay-diagnostic-v6 \
  --repo-root . \
  --run-id corpus-e2e-diagnostic-v6

MPLCONFIGDIR=/tmp/mpl python -m bve.cli.se_evaluate \
  --reference-universe research/se_benchmarks/cd19_bcma/development/reference_universe.csv \
  --result /tmp/se-production-replay-diagnostic-v6/runs/corpus-e2e-diagnostic-v6/result.json \
  --require-release-thresholds
```
