# Reproducibility and custody record

## Timeline (UTC)

| Step | Time | Evidence |
|---|---|---|
| Prereg committed and pushed | 2026-10-24 20:51:35 | commit `e909f4d`, on `origin/m11-identity-graph` |
| Engine launched | 20:53:17 (manifest `started_at` 20:53:44) | run `se:d710e7c8-c9ce-43a7-80ab-6fb08a36bf8a`, engine commit `e909f4d` |
| Engine ended (exit 2, INCOMPLETE) | 21:52:10 | `results/run.time.txt`, `results/engine_stderr.log` |
| Both views sealed | 21:53:18 | `sealed/receipt*.json`, commit `f7f3fad` (pushed 21:53:57) |
| Reference session ran | 21:54:13 – 22:05:41 | started after the seal was pushed |
| Scoring | after 22:05:41 | `results/report_*.json` |

All times come from the local clock and git. **No independent third-party timestamp was
obtained.** The handoff's email step was not done.

## Hashes

| File (kept outside the repo) | sha256 |
|---|---|
| `~/se_runs/gucy2c_pilot_v1/run/result.json` (248 MB) | `3b86c76a…0d94b1` |
| `~/se_runs/gucy2c_pilot_v1/candidates.json` (official) | `e7aae615…c31f95` |
| `~/se_runs/gucy2c_pilot_v1/candidates_review.json` | `ebd01745…b6e92e` |
| `~/bve_pilot_reference_isolated/reference.json` (hidden key) | `ceff6f84…3f7bc7` |
| `~/bve_pilot_reference_isolated/research_notes.md` | `62b2f8b7…391644` |

Spec, criteria and prereg hashes are in `prereg.json` and the receipts.

## Commands

```bash
# engine (memory cap 4 GiB, 3 h timeout); the exact script is ~/se_runs/gucy2c_pilot_v1/run.sh
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 timeout 3h \
  bve-se-search --problem research/se_blinded_pilot_v1/gucy2c_oncology_v1/engine_problem.yaml \
  --output-dir ~/se_runs/gucy2c_pilot_v1/run --format shortlist --progress
python -m bve.cli.se_pilot export --result run/result.json --spec-id gucy2c_oncology_v1 \
  --engine-commit e909f4d4e167ef24e47bccc74fa2a140758e76da --out candidates.json
python -m bve.cli.se_pilot seal  --spec … --criteria … --candidates candidates.json --prereg … --out receipt.json
python -m bve.cli.se_pilot score --receipt receipt.json … --reference ~/bve_pilot_reference_isolated/reference.json --out report.json
```

`bve-se-pilot` is not installed as a console script in this venv. It was run as
`python -m bve.cli.se_pilot`.

Replay of the engine from sealed bytes: `bve-se-search … --replay-corpus ~/se_runs/gucy2c_pilot_v1/run/custody`.

## Engine deviations

- `BVE_SE_USER_AGENT` was not set, and no `--source-index` was supplied. Seven required source
  families reported NOT_CONFIGURED, and the run is INCOMPLETE. This was not corrected after the
  fact, because the protocol allows no rerun once candidates exist.
- The production `bve-se-run` path is scope-locked to CD19/BCMA T-cell engagers by its release
  manifest. It was not used. The general `bve-se-search` path was.

## Reference-session isolation (what was achieved)

The answer key was built by a separate `claude -p` process, not a subagent of this session:

```bash
cd ~/bve_pilot_reference_isolated   # outside the repo; held only spec.json, RULES.md, PROMPT.md
claude -p "$(cat PROMPT.md)" --restricted --strict-mcp-config \
  --tools "WebSearch,WebFetch,Read,Write,Edit" --permission-mode acceptEdits --no-session-persistence
```

What this isolation achieved:
- **No shell.** `--restricted` removes the shell tools.
- **File tools confined to its own folder.** It could not read the repo or `~/se_runs`.
- **No user/project settings, plugins or MCP servers**, including the claude-mem memory plugin.
- **No conversation context.** It received no engine output, names, logs or scores.
- **No different Claude Code project memory**: its working directory differs from this one.

What it did not achieve:
- It ran on the same machine and user account, with the same model.
- It had open web access. The prereg and seal commits were on GitHub, but neither contains a
  candidate name.
- Global `~/.claude/CLAUDE.md` instructions (generic tooling notes) may have loaded.

It is process-level isolation, not a separate machine or account.

## Not committed

These stay out of the repo:
- the hidden reference and its research notes;
- `result.json`;
- the candidate exports;
- the engine custody corpus.

They live under `~/bve_pilot_reference_isolated/` and `~/se_runs/gucy2c_pilot_v1/`.
