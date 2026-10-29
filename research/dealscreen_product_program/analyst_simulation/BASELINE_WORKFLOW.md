# Baseline workflow (cycle A1, before fixes) — AI-SIMULATED / INTERNAL DEVELOPMENT

Source: the frozen `ANALYST_FINDINGS.md` (commit 6fab6d8) and the analyst's own workspace,
snapshotted in `measure/baseline_A1.json`.

| Step an analyst takes | Commands | Worked? | Workaround |
|---|---|---|---|
| Install / find the CLI | — | No: `bve-dealscreen` not on PATH in the worktree venv until reinstalled | reinstall |
| Import 40-row landscape | 1 (`import`, ~28 s) | Yes; identity flags written to a file but not printed | read `identity.json` by hand |
| Screen, read funnel and queue | 2 | Yes: 4 / 14 / 22 | per-gate table built in Python |
| Understand why a program is unresolved | 1 per asset (`show`) | Yes, but JSON only | — |
| Run AI diligence | 2 (`research` offline + CT.gov) | 1 useful finding of 40 | fetch filings by hand |
| Record cited evidence | — | Refused for AI (correct policy) | none; NOT COMPLETED BY HUMAN |
| Mark candidates | 7 `decide` calls | Yes (AI_PREPARED, unapproved) | — |
| Value 3 programs | `value` | Crash (FileNotFoundError) | hand-built YAML + placeholder company; misplaced keys silently ignored |
| Export workbook + memo | 2 | Yes; Finalists sheet said "7 approved"; memo listed batoclimab twice | — |

Totals reported by the analyst: 25 logged commands, 4 workarounds, 14 unresolved programs (the
analyst's own view: 1 genuinely open plus rights questions), 7 human steps not completed.
