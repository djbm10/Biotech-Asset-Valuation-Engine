# Productization steps 6 and 7 — runtime, and the one-command workflow

## Step 6: what a run actually costs

Measured from `M17_run.log`, not estimated:

| stage | seconds | share |
| --- | --- | --- |
| DISCOVERY | 4556.7 | **92.4%** |
| EXTRACTION | 310.9 | 6.3% |
| ACQUISITION | 46.0 | 0.9% |
| IDENTITY | 18.3 | 0.4% |
| GATING | 3.5 | 0.1% |
| SCORING | 0.0 | 0.0% |
| total | ~4935 | |

DISCOVERY issued 1,419 attempts over **1,265 distinct** `(source, query)` pairs, fetching
2,692 pages and returning 15,454 records and 56,395 hits. So only 154 attempts — 10.9% of
the run — were repeats, and every one of them is a pass-1 query re-issued in pass 4.

That re-issue is not waste. It *is* the convergence proof:

```
LIVE_CONVERGED = the seed queries were actually re-issued to the live source
                 and produced zero growth.
```

A run cache would have served those 154 attempts from memory and the run would still have
reported CONVERGED — while having proven nothing about the live source. The pinning test
`test_orchestrator_converges_after_two_complete_zero_growth_passes` asserts
`adapter.calls > len(compile_problem_queries(problem))` precisely to prevent this, and it
was **not** relaxed. **Discovery is therefore the dominant, irreducible cost of strict live
convergence.** If a fast interactive path is ever wanted, it must be a separately labelled
mode (e.g. `LOCAL_FIXPOINT`) that reports its own status and is never scored as live
convergence. Nothing in this repository claims that status today; `summary.json` says
`convergence_mode: LIVE` and spells out what it attests.

### The optimization that was taken

`bve/se/evidence/snapshot_cache.py`. Extraction parsed each sealed snapshot — and
canonically re-serialized it — **once per hit**, and M17 had ~3.6 hits per record. The
bytes are content-addressed and, under custody, immutable for the whole run, so the repeat
parse cannot produce a different answer. The cache is keyed on `(path, size, mtime_ns)`
rather than the path, so a rewritten snapshot tree is not served stale. Its acceptance
condition is output equivalence, pinned in `tests/se/test_snapshot_cache.py`: a warm
extraction and a cold one must produce byte-identical bundles.

The returned objects are **shared and must not be mutated**. Every extractor here treats a
snapshot as a read-only record, which is what makes the sharing safe.

No acquisition or discovery semantics were changed.

## Step 7: `--output-dir`

Goal: a natural-language question to a cited shortlist in one command.

```bash
bve-se-search --query "small molecule CHRM1 programs in phase 2" --output-dir runs/chrm1-1
```

Everything was already reachable — through `--emit-problem`, `--output`, `--format`
(four times), `--acquisition-ledger`, `--custody-root`, `--snapshot-dir`,
`--pubmed-snapshot-dir` and `--run-id`. The user had to know all of it, and had to know
which internal stage each flag belonged to. `--output-dir` is a deterministic layout over
those existing writers; it builds nothing new in the pipeline.

```
runs/<id>/
  problem.yaml              the compiled, frozen BuyerProblem the question became
  result.json               the full machine-readable run artifact
  run_manifest.json         status, reasons, blind spots, provenance
  shortlist.txt             the human view, with citations and source coverage
  shortlist.json            the same object, machine-readable
  memo.md                   the run audit
  acquisition_ledger.jsonl  one line per issued query
  summary.txt / summary.json  the end-of-run summary, both views
  reproduce.sh              the exact command that produced this directory
  logs/run.log              everything the run said on stderr
  snapshots/                content-addressed source snapshots
  custody/                  the sealed acquisition
```

Rules that hold:

- **An explicit flag always wins.** `--output`, `--custody-root`, `--snapshot-dir` and the
  rest are only defaulted when the user did not choose. The two flags compose; neither
  silently discards the other.
- **Every view is written, whatever `--format` asked for.** A directory holding only the
  format someone happened to want sends them back to the sources for the next question.
- **A failed run leaves its artifacts.** `reproduce.sh` is written before acquisition
  starts; the result, both shortlists, the memo, the manifest, the ledger and the summary
  are written *before* the fail-closed exits, following the precedent already set by the
  acquisition ledger. An UNSCOREABLE run is something to read, not something to re-run.
- **stdout is the summary.** With a run directory and no explicit `--output`, stdout
  carries the end-of-run summary rather than a dump of one view over it.
- **No ranking score is invented.** The summary's `top` entries carry position, name,
  section and target status — the shortlist's declared display order — and no number that
  could be read as a score.

The summary reports: the query and how it was interpreted, run status and convergence mode,
eligible/review/excluded/low-support/total counts, blind spots, sources that did not fully
deliver, the top assets, the artifact paths, per-stage timings and elapsed time. Stage
timings came from `StageTelemetry`, which recorded them all along and only ever printed
them to stderr under `--progress`; they are now persisted in `summary.json`.

## Tests

- `tests/se/test_search_run_directory.py` — layout, explicit-flag precedence, artifacts
  after exit 3 and exit 2, the log surviving, `convergence_mode == LIVE`, no scores,
  the summary on stdout, and that a run without the flag still prints its result.
- `tests/se/test_snapshot_cache.py` — output equivalence, one read per document, staleness.

Both were checked non-vacuous: disabling `_write_run_artifacts` fails 7 of the 14
directory tests.
