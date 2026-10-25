# Reproducibility and custody record

## Timeline (UTC; local clock and git; the only third-party timestamp is drand)

| Step | Time | Evidence |
|---|---|---|
| Draw protocol and pool pushed | 2026-10-25 18:40:58 | `3c7f48d` |
| drand round 6584099 | 18:46:30 | `../target_draw_v3/drand_round_6584099.json` (verifiable at api.drand.sh) |
| Problem compiled, no search | about 18:49 | `outputs/se/` empty afterwards; run dir absent |
| Prereg pushed | 18:50:32 | `dacbca2` |
| Engine run | 18:50:53–18:54:14 | `results/run.time.txt`, `results/engine_stderr.log` |
| Seal pushed | 18:56:35 | `6950960` |
| Reference session | 18:56:46–19:11:56 | `~/bve_il3ra_reference_isolated/{started,ended}_utc.txt` |
| Scoring | after 19:11:56 | `results/report_*.json` |

## Hashes (files kept outside the repo)

| File | sha256 |
|---|---|
| `~/se_runs/il3ra_pilot_v1/run/result.json` | `198bc9e443570483672a0569e03d7b2d95c1bec9df3308e7010ff21b6be8152a` |
| `~/se_runs/il3ra_pilot_v1/candidates.json` (official) | `4cb71774c7486740a16dcbbaa02da4bac6096ea565a0bc6768806d6282da5333` |
| `~/se_runs/il3ra_pilot_v1/candidates_review.json` | `20783cc8eb9df23d6b6f9a6a839f97e6f640ea16b1bea2087845ef8a56660f47` |
| `~/bve_il3ra_reference_isolated/reference.json` (as written by the session) | `66d0be6e2dad4c1ad264c73b570bbbdda81423c80ad958fa888ba9ef65ba9660` |
| `~/bve_il3ra_reference_isolated/reference_scoring.json` (provenance flags added) | `522c3067dfcbdad11d3cf6f7a08d99a9d0cc639d86099302b6a93c20e0ab5997` |
| `~/bve_il3ra_reference_isolated/research_notes.md` | `5d950aba3e4336aa9ec71e64ee5a7a0b07fa053f893618ddcae3e2735cd47338` |

## Commands

```bash
# draw
python research/se_blinded_pilot_v1/target_draw_v3/draw_target.py --pool-out draw_result.json \
  --seed-hex 45ede9c0fee94b5f8db5f1e3d23b7716f47539854c70972f893e8a995ab17ee4
# problem: compile only (no search)
python -c 'from bve.cli.se_search import problem_from_args, build_parser; \
  problem_from_args(build_parser().parse_args(["--query","IL3RA programs","--as-of","2026-10-25", \
  "--emit-problem","engine_problem.yaml"]))'   # then minimum_stage: PHASE_1
# run (~/se_runs/il3ra_pilot_v1/run.sh): systemd-run MemoryMax=4G, timeout 3h, bve-se-search … --progress
python -m bve.cli.se_pilot export --result run/result.json --spec-id il3ra_clinical_any_v1 \
  --engine-commit dacbca2a8a14ff8106f38b79d8b6a739dfd3ad44 --out candidates.json
python -m bve.cli.se_pilot seal  --spec … --criteria … --candidates candidates[_review].json --prereg … --out receipt[_review].json
python -m bve.cli.se_pilot score --receipt … --reference ~/bve_il3ra_reference_isolated/reference_scoring.json --out report[_review].json
python research/se_blinded_pilot_v1/chek1_clinical_any_v1/score_detail.py run/result.json candidates.json reference_scoring.json score_detail.json
python research/se_blinded_pilot_v1/il3ra_clinical_any_v1/adjudicate.py run/result.json reference_scoring.json adjudication.json
```

The review population is the official export filtered to `eligible_asset_ids ∪
unresolved_asset_ids`, as in the earlier pilots.

## Deviations

1. **Engine acquisition FAILED** (exit 3): one CT.gov query got HTTP 400. Candidates
   existed, so there was no retry. It is reported as INCOMPLETE, and the engine's own
   FAILED/UNSCOREABLE status is quoted.
2. **Reference provenance flags missing.**
   - The session omitted `independent_of_engine` and `synthetic`, and the scorer rejected
     the file.
   - `reference_scoring.json` adds exactly `independent_of_engine: false, synthetic: false`.
     `assets` was verified identical to the original, and the original is kept unmodified.
   - No reference content was changed.
3. The CHEK1 `--emit-problem` lapse was **not** repeated: no acquisition happened before the
   prereg push.

## Reference isolation

`claude -p "$(cat PROMPT.md)" --restricted --strict-mcp-config --tools "WebSearch,WebFetch,Read,Write,Edit"
--allowedTools "WebSearch,WebFetch,Read,Write,Edit" --permission-mode acceptEdits --no-session-persistence`.
It ran in `~/bve_il3ra_reference_isolated/`, which held only `spec.json`, `RULES.md` and
`PROMPT.md`.

What it achieved:
- no shell;
- file tools limited to its folder;
- no MCP or plugins;
- no engine output, candidate names or conversation context.

What it did not achieve:
- same machine, account and model as the operator;
- open web access (the GitHub commits it could reach contain no candidate names);
- global `~/.claude/CLAUDE.md` may have loaded.

## Not committed

Kept outside the repo:
- the hidden reference and its notes;
- `result.json`;
- the candidate exports;
- custody and snapshots;
- the session transcripts.
