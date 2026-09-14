# S&E engine — handoff state

**As of 2026-09-14, engine `f57f4bc` on branch `m11-identity-graph` (pushed).**

This is the "where we left off" document. It records the current state of the search &
evidence engine, what is frozen, what the next work is, and the environment facts that cost
time to rediscover. Milestone detail lives in the per-milestone reports; this file is the
index and the operating manual.

## 1. Where the work stands

The architecture-remediation loop is **complete and should not be continued**. Three
consecutive mechanically drawn targets trace the arc:

| milestone | target | discovery | identification | false target assertions |
|---|---|---|---|---|
| M13 | SLC6A2 | 5/41 | 0/41 | 0 (vacuous) |
| M15 | HRH1 | 49/51 | 6/51 (11.8%) | 0 |
| M16 | HTR2A | 40/41 | 29/41 (70.7%) | 0 |
| **M17** | **CHRM1** | **21/21** | **21/21 (100%)** | **0**, 0/26 traps with 16 surfaced |

M15 exposed identification as the binding constraint; M16 showed the fix generalizing;
M17 closed it against the hardest trap set drawn (CHRM2/3/4 — sibling subtypes one
character from the target). The stopping condition set for this loop is met.

**Next work is productization, not another target draw.** A fourth draw would re-measure
the same architecture at rising cost — M17's discovery stage alone ran 76 minutes over a
15,454-record corpus.

## 2. The one subsystem to fix first

**Mention-layer precision.** It is the dominant remaining failure layer, and it degraded as
recall improved:

| class | M16 | M16R | M17 |
|---|---|---|---|
| known_molecule | 849 (39.1%) | 1,645 (35.3%) | 1,892 (23.4%) |
| development_code | 688 (31.7%) | 684 (14.7%) | 1,071 (13.3%) |
| **unknown_word (false accepts)** | **576 (26.5%)** | **2,270 (48.7%)** | **4,480 (55.5%)** |

More than half of what the engine nominates is an ordinary alphabetic token the frozen
ontology has no drug record for: chemical-class nouns (`phenols`, `quinolines`,
`xanthones`), demonyms and place names (`Afghanistan`, `Jordanian`), hyphen compounds.

It costs **zero** benchmark metrics — the identity and `CandidateTargetAssertion` gates hold,
extraction may nominate but never assert, and false target assertions stayed at 0 across
8,080 candidates. But it is why `SCORING` reports 7,966 unresolved against 114 excluded and
0 eligible, and anything downstream consuming *candidates* rather than *assertions* inherits
the noise directly.

The fix is a filtering layer at the nomination boundary. Unlike everything in the
remediation loop, **it can be evaluated without drawing a new target** — rerun
`mention_precision_audit.py` against the existing sealed results.

Other open items, unchanged: endogenous-ligand collision (HISTAMINE), dose/salt/combination
decoration, `MIN_SUPPORTED_DOCS = 5` conflating contested with rare, and the rule-6
`\bAR\b`/`\bMET\b` English-word false-positive mode.

## 3. What is frozen and must not be touched

- **M13** stays at 5/41 discovery, 0/41 identification. Never rewrite.
- **M16** stays at the published 29/41 identification. The corrected-harness reading
  (30/41) is reported *alongside*, never substituted.
- **M15** unchanged; **M15L** published 41/51, corrected reading 42/51.
- Benchmark rules are never changed after observing results.
- Sealed corpora are never mutated. The 5 PDCD1 identification misses are not hand-solved;
  Lambrolizumab stays separate from Pembrolizumab.
- The drug-name-shape model, its features and its threshold (0.2498) are frozen. Any future
  recall gap gets a new *mechanically derived* route — never a lowered threshold, never a
  hand-added suffix.
- The ≥40-molecule stem threshold stays at 40.

## 4. Reports and artifacts

Reports in `docs/`: `m13_zero_shot_generalization_report.md`,
`m14_slc6a2_remediation_report.md`, `m15_hrh1_zero_shot_report.md`,
`m15l_hrh1_remediation_report.md`, `m16_htr2a_zero_shot_report.md`,
`m17_chrm1_zero_shot_report.md`.

Commit lineage for the identity work: `e0743eb` (M16 report) → `e689936` (canonical identity
contract) → `aeea608` (drug-name-shape route) → `f57f4bc` (M17 report).

Run artifacts live in **`/home/djmann/staging/pdcd1_baseline`**, which is outside the repo
and untracked by git. M17 artifacts: `M17_result.json` (419 MB), `M17_score.json`
(sha256 `70a17735…`), `M17_mention_audit.json` (sha256 `3468f12b…`), `M17_custody/`,
`M17_alias_probes.json`, `M17_run.log`, `m17_benchmark_v1.json` (sha256 `03876755…`),
`m17_chrm1_problem.yaml`, `m17_pool_rules.json`, plus `score_m17.sh` and `run_m17.sh`.

## 5. Environment facts that cost time to rediscover

- **Worktree is `/home/djmann/projects/bve-b8`.** The shell's default working directory is
  `/home/djmann/projects/biotech-asset-valuation-engine`, a *different* worktree, and the
  Bash tool resets cwd between calls. Always `cd` or use absolute paths.
- Every command needs `PYTHONPATH=/home/djmann/projects/bve-b8/src` (editable-install
  contamination) and
  `BVE_SE_ONTOLOGY_SNAPSHOT=/home/djmann/projects/bve-b8/data/se/ontology/current` — the
  default is CWD-relative and **fails open** to `no_snapshot` rather than erroring.
- **Exit code 2 = `RunStatus.INCOMPLETE`** and is the expected diagnostic state for a
  discovery-only run. Exit 3 is fatal. A missing output file is the real failure signal.
- `score_zero_shot.score()` arguments must be `pathlib.Path`, not `str`.
- **scikit-learn is not installed.** The shape model is pure-Python naive Bayes by necessity.
- Ontology snapshot `chembl_ChEMBL_37__open_targets_26.06__resolver_v2__modality_v2`:
  84,560 TARGET + 71,506 DRUG entities. TARGET records have no `canonical_id`/`name`;
  `aliases` is a list of `{"alias_type","value"}` dicts.
- Machine has 10 GB RAM. **The system reaps background tasks under memory pressure** — five
  watchers were killed during M17 even one that slept 60s between checks. The primary
  scientific process survived each time and must never be killed for a watcher's
  convenience. Wait in the **foreground** instead (a `for`-loop with `sleep`, 10-minute tool
  timeout, repeated); foreground calls are not reaped.
- `pgrep -f "<string in your own command>"` self-matches.
- Multi-line Bash commands are flattened — use a heredoc or a script file.
- Large JSON dumps printed to the shell get elided/mangled. **Always verify counts
  programmatically**; a list that displayed as 14 items was actually 40.

## 6. Security constraints in force

- Credential at `~/.config/bve/env`, sourced before any live acquisition. Never print or
  persist the value; verify only that `BVE_SE_USER_AGENT` is present and its SHA-256 matches
  `456da4da5c35d281066d62aacc673f13a17a5499de717bbb41fd5149a9dead58`. Record only
  `user_agent_contact_present = true` / `user_agent_sha256 = …`.
- Never commit: operator email, credentials, secrets, or large artifacts that belong in
  staging rather than git.
- The operator's own email identifies the operator only and must never be sent to an
  unrelated service — not in a header, URL, or payload. It is not an acquisition header.
- Not permitted: spoofing browser identity, bypassing anti-bot systems, circumventing
  authentication or paywalls, fabricating headers or provenance, scraping around access
  controls, or initiating paid/account actions without authorization.
- No ASCO/AACR/ASH licences are to be requested or paid.

**HARD STOP conditions** (only these): a required paid purchase/licence/DUA/login/CAPTCHA;
a missing required credential; anything requiring bypass of an access control; anything
requiring fabricated provenance; changing frozen benchmark rules after seeing outcomes;
mutating a sealed artifact; two defensible scientific choices that would materially change
benchmark meaning; a source that changed fundamentally; a destructive system action.

## 7. If picking this up cold

1. Read `docs/m17_chrm1_zero_shot_report.md` — it carries the current result and the
   route-confound and corroboration caveats that belong beside it.
2. Do not draw another benchmark target.
3. Start on §2, mention-layer precision, evaluated against existing sealed results.
