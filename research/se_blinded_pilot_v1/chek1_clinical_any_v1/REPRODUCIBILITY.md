# Reproducibility and custody record

## Timeline (UTC; local clock and git, no third-party timestamp except drand)

| Step | Time | Evidence |
|---|---|---|
| Draw protocol and pool pushed | 2026-10-25 15:50:07 | `faf35aa` |
| drand round 6583757 published | 15:55:30 | `../target_draw_v2/drand_round_6583757.json` (verifiable at api.drand.sh) |
| Aborted pre-registration acquisition (operator error) | about 15:57–15:59 | quarantined, unread: `~/se_runs/chek1_aborted_prereg_acquisition/` (463 files, tree sha256 `7b2354e1…`) |
| Prereg pushed | 16:01:49 | `80a0a00` |
| Engine run | 16:02:04–16:05:10 | `results/run.time.txt`, `results/engine_stderr.log` |
| Seal pushed | 16:06:49 | `a0dcb1b` |
| Reference attempt 1 (no output; web tools blocked) | 16:07:03–16:07:47 | `~/bve_chek1_reference_attempt1/` |
| Reference attempt 2 | 16:08:39–16:15:17 | `~/bve_chek1_reference_isolated/` |
| Scoring | after 16:15:17 | `results/report_*.json` |

## Hashes (files kept outside the repo)

| File | sha256 |
|---|---|
| `~/se_runs/chek1_pilot_v1/run/result.json` (18 MB) | `d862a2609c5d556caa0d4854dbeba37693a65a91eb897b595a88e6a8cd970fd0` |
| `~/se_runs/chek1_pilot_v1/candidates.json` (official) | `1b14a6d75350c5d17c5aaf56e664793911c3ccd9faa8b2d4b5289e398fa45bb2` |
| `~/se_runs/chek1_pilot_v1/candidates_review.json` | `8b54316086b424a75950e81cc8755bfd05cc64182f7bc2a4de0eadaac1a2f82e` |
| `~/bve_chek1_reference_isolated/reference.json` (hidden key) | `e28e608c42fdb305711ec9196188cbc2c1b98a7ccd8b8529b80eccec6a92d50d` |
| `~/bve_chek1_reference_isolated/research_notes.md` | `2b2793df18254579e9bc7701d01a5d77846a23a5dcf2ff601b832280c38a2047` |

## Commands

```bash
python research/se_blinded_pilot_v1/target_draw_v2/draw_target.py --pool-out draw_result.json \
  --seed-hex 67608e0e44d8f45136e72744c0a03917f8b224a70e02dc50e8dd391e2288e681
~/se_runs/chek1_pilot_v1/run.sh      # systemd-run MemoryMax=4G, timeout 3h, bve-se-search … --progress
python -m bve.cli.se_pilot export --result run/result.json --spec-id chek1_clinical_any_v1 \
  --engine-commit 80a0a0060a3158803e7f14e32788473c44959b6f --out candidates.json
python -m bve.cli.se_pilot seal  --spec … --criteria … --candidates candidates[_review].json --prereg … --out receipt[_review].json
python -m bve.cli.se_pilot score --receipt … --reference ~/bve_chek1_reference_isolated/reference.json --out report[_review].json
python research/se_blinded_pilot_v1/chek1_clinical_any_v1/score_detail.py run/result.json candidates.json reference.json score_detail.json
```

Replay from sealed bytes: `bve-se-search --problem … --replay-corpus ~/se_runs/chek1_pilot_v1/run/custody`.

## Reference isolation

`claude -p "$(cat PROMPT.md)" --restricted --strict-mcp-config --tools "WebSearch,WebFetch,Read,Write,Edit"
--allowedTools "WebSearch,WebFetch,Read,Write,Edit" --permission-mode acceptEdits --no-session-persistence`,
run in a folder outside the repo holding only `spec.json`, `RULES.md` and `PROMPT.md`.

What it achieved:
- no shell;
- file tools confined to its folder;
- no MCP or plugins;
- no engine output or conversation context.

What it did not achieve:
- it ran on the same machine, account and model;
- it had open web access;
- global `~/.claude/CLAUDE.md` may have loaded.

Attempt 1 lacked `--allowedTools`. Its web tools were refused, and it wrote no reference. Its
reply named candidate drugs from memory, marked unverified, which the operator read. The
engine output was already sealed by then.
