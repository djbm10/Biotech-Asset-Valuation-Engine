# BD coverage pilot: execution status

**Status: INCOMPLETE (computationally blocked), not a scientific STOP.**

Arms finished: `A_base` only. Arms still to run: `A_full`, `B_base` and `B_full`. No
comparison has been scored.

## What happened (evidence)

| Attempt | Start | Last on-disk activity | Outcome |
|---|---|---|---|
| `A_full/` | 2026-10-15 21:14 | 2026-10-16 07:11, `.custody-*` staging dir created, empty | killed under memory pressure |
| `A_full_20261016T111810Z/` | 2026-10-16 07:18 | 16:39, `.custody-*/query_attempts.jsonl` created, 0 bytes | killed under memory pressure |

- **Where both attempts died.** Both reached the custody seal: the staging directory exists and
  its first file had been opened. Discovery, which wrote its snapshots until 16:28, had finished.
  Nothing was written after the first seal file.
- **Correction.** An earlier report said the second attempt ran "about 1 h 40 min". That was
  inferred from monitor expiries and is wrong. File mtimes show about 9 h 20 min.
- **No logs.** Engine logs are empty for both attempts, because `--progress` was not passed. Peak
  RSS was not captured: GNU time writes its file only when the process exits.
- **Memory readings seen during runs** (`ps` RSS):
  - `A_base` (live): 3.1 GB at 1 h 37 min and 5.0 GB at 2 h 08 min.
  - First `A_full` replay: 6.05 GB at 1 h 01 min.
- **The machine.** 10.9 GB total. About 2.5–3 GB is held by resident tools: the headroom proxy
  (1.8 GB), this Claude session and the MCP servers.
- **Size of the data being written.** `A_base` produced `query_attempts.jsonl` of 639 MB,
  `query_record_map.jsonl` of 155 MB, `acquisition_ledger.jsonl` of 62 MB and `result.json` of
  402 MB.

## Diagnosis (evidence vs inference)

- **Evidence: avoidable duplication at the exact point of death.** `CustodyRecorder.seal`
  joined every attempt line into one string before writing, while all attempt models were
  already in memory. For a 640 MB file that is roughly 3× its size in transient memory: the
  per-line strings, the joined string, and the encoded buffer. A synthetic probe at that size
  measured a write peak of **1,254 MB (old) vs 10 MB (streamed)**. `result.json` used the same
  pattern (`json.dumps` of a 400 MB result).
- **Inference: why the seal was the breaking point.** The process was probably already
  at 6 GB or more when it reached the seal (the in-memory attempts and documents). The seal's
  transient spike then exceeded what was available. This is consistent with both deaths, but is
  not measured.
- **Not changed.** The resident footprint of attempts, documents, claims and candidates is
  inherent to the current pipeline design. Reducing it would be a pipeline rewrite, which is out
  of scope.

## Optimization made (`e697227`)

The JSONL writes in the custody seal and the `result.json` write are now streamed.

- **Equivalence.** Tests (`tests/se/test_streaming_writes.py`) pin the sealed files, and
  `result.json`, to the exact bytes of the old encoding.
- **Regression check.** The full `tests/se` suite passed: 1,976 passed, 3 xfailed.
- **Scope.** No scientific, ordering, identity or custody change.
- **Effect.** This removes about 1–1.3 GB of transient peak at the seal and about 0.4–0.8 GB at
  result write. It does not make a replay fit on this machine with confidence. The expected
  peak is still around 6–7 GB, against about 7.5 GB available after the resident tools.

## Requirement and how to finish

**Use 32 GB RAM. That should be sufficient.** The highest RSS measured during a run was about
6 GB, before the seal's spike; with the streaming fix, 2–3× headroom remains.

**Uncertainty.** No arm's true peak has been measured, because no `A_full` attempt completed.
The new runner records it.

### Steps on the larger machine

1. Check out `m11-identity-graph` at or after this commit, then run `pip install -e ".[dev]"`.
   The environment used here was Python 3.12.3 with pydantic 2.12.5.
2. Copy `data/se/ontology/` from this checkout. It is about 95 MB and not in git. Its `current/`
   folder is a symlink into `biotech-asset-valuation-engine/`, so copy with
   `cp -rL`/`rsync -L`.
3. Copy `/home/djmann/se_runs/bd_cov_v1/` (1.6 GB), including `A_base/custody` and
   `A_base/snapshots`, to **the same absolute path**. If you can't create that path, symlink it.
   - **Why:** the sealed ledger embeds 14,194 absolute snapshot paths. Rewriting them would change
     the sealed bytes, and the replay validates them.
   - **Alternative:** if `/home/djmann` cannot exist on the new machine, set `BVE_COV_ROOT` to the
     new location *and* bind-mount or symlink it at `/home/djmann/se_runs/bd_cov_v1`.
4. Run `python research/se_bd_discovery_source_coverage_v1/preflight.py`. It verifies, among
   other things, that every frozen-input hash matches.
5. Run each arm on its own, one after another:
   `research/se_bd_discovery_source_coverage_v1/run_replays.sh A_full`, then `B_base`, then
   `B_full`.
   - Each writes `<arm>_<stamp>/`, `.log` (with `--progress`), `.time`, `.exit` and `.mem.tsv`
     (30 s samples, flushed to disk).
   - The runner refuses to start if another arm is running or if preflight fails, and it never
     deletes anything.
6. Copy the new `<arm>_<stamp>` directories back. The preregistered scoring with `measure.py`
   then compares `A_base` with `A_full`, and `B_base` with `B_full`.

**Keep earlier attempts.** All earlier attempt directories stay where they are; none are
needed.
