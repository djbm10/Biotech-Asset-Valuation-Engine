# Third blinded S&E benchmark: preregistered target draw and protocol

**Status: UNVALIDATED (AI-run exploratory benchmark).** Claude (`claude-opus-5-5`) wrote
this protocol, will operate the engine, and will launch a separate Claude process to
prepare the reference. No human prepared or checked the answer key. This is not
human-independent validation.

Committed and pushed **before** the seed exists and before any target is known. It reuses
the method of `../target_draw_v2/PROTOCOL.md` unchanged except where marked **(v3)**.

## 1. Candidate pool (`pool.json`, produced by `draw_target.py`)

- **Frame.** Same as v2: targets in the engine ontology snapshot (`edges.jsonl` sha256
  `2a6b6ea8…3f551`, unchanged since v2) with at least 5 distinct drugs on `USABLE`
  `DIRECT_TARGET` edges.
- **Exclusions, applied mechanically:**
  1. Named: PDCD1, CD274, CD19, TNFRSF17, SLC6A2, HRH1, HTR2A, CHRM1, GUCY2C, CD3E, MS4A1,
     **CHEK1 (v3)**.
  2. Whole-word symbol in any Markdown/YAML file under `research/` or `docs/`. This now also
     covers the CHEK1 pilot, the v2 draw (its runner-up targets PTGFR, OPRM1, CD40 and CYP11B1
     are named in the CHEK1 protocol), and the development policies written since.
  3. **(v3)** Whole-word symbol in S&E development test code (`tests/se/**/*.py`). This removes
     VEGFA. The code changed between the CHEK1 draw (`faf35aa`) and the engine commit
     (`fcfefe3`) names no pool target (checked).
  4. Does not resolve unambiguously in the engine resolver.
- **Result:** 153 eligible, 107 excluded. The lists and reasons are in `pool.json`.
- **Bias, disclosed.** As in v2, the frame is BVE's own ontology, so it favours targets that
  ChEMBL and Open Targets curate well. It says nothing about targets outside the ontology.

## 2. Seed and draw

- **Seed:** the `randomness` of the first drand mainnet round
  (`https://api.drand.sh/public/<round>`) whose time is at least 5 minutes after this commit
  is pushed: round = `floor((push_time + 300 − 1595431050) / 30) + 2`.
- **Draw:** smallest `sha256(seed_hex + ":" + symbol)` over the eligible pool. No second draw
  and no override.

## 3. Question, criteria (frozen now; only `<T>` and the date are filled)

`spec.json` and `criteria.json` are the v2 templates, verbatim: area unspecified, any
modality, Phase 1 or later including approved and discontinued programs. The thresholds are:
- strict precision ≥ 0.50;
- recall ≥ 0.60;
- trial coverage ≥ 0.50;
- identity errors ≤ 1;
- misleading claims ≤ 2.

The scorer's comparison is reported, but the **official grade stays UNVALIDATED**.

The inclusion/exclusion rules given to the reference preparer are the CHEK1 rules with `<T>`
substituted:
- multi-target drugs count only when `<T>` is a primary intended target;
- negative controls are drugs for related targets, preclinical-only compounds and diagnostic
  agents.

## 4. Engine freeze and translation

- **Engine:** `src/` identical to `fcfefe3` (the end of the intervention-naming milestone).
  The prereg commit is verified with `git diff --stat fcfefe3 -- src` = empty.
- **No search before preregistration (v3).** In the CHEK1 pilot, `--emit-problem` started a
  live search. Here the problem is compiled by calling the CLI's own
  `bve.cli.se_search.problem_from_args` from Python with the arguments
  `--query "<T> programs" --as-of <date> --emit-problem engine_problem.yaml`. It runs
  `compile_intent` and writes the YAML, and nothing else. The run directory is checked to be
  absent before the official run.
- The only hand edit is `evidence_floor.minimum_stage: PHASE_1`.

## 5. Run

- `bve-se-search --problem engine_problem.yaml --output-dir <run> --format shortlist
  --progress`, live, once.
- Same source configuration as both earlier pilots: no `--source-index`, no
  `BVE_SE_USER_AGENT`. The NOT_CONFIGURED families are recorded from the engine's source
  report, and the run is reported INCOMPLETE if the engine says so.
- Limits: `systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0`, `timeout 3h`.
- A retry is allowed only for an infrastructure failure before any candidate exists.
- Export, then seal the official (all candidates) and review (ELIGIBLE + REVIEW) populations,
  and commit and push before the reference session starts.

## 6. Reference

A separate `claude -p --restricted --strict-mcp-config` process, with web and file tools
explicitly allowed (`--allowedTools`), started after the seal push. It runs in a new folder
outside the repo containing only `spec.json`, `RULES.md` and `PROMPT.md`. It writes
`reference.json` (AI preparer, `independent_of_engine: false`, `synthetic: false`) and
`research_notes.md`, with 3–10 negative controls. The reference never enters git and is not
edited after scoring.

## 7. Scoring and usefulness

`se_pilot score` on both sealed views, plus a per-asset detail script. The report answers:
- precision and recall;
- identity errors;
- trial coverage;
- target/modality accuracy;
- unsupported claims;
- wrong eligibility decisions;
- the analyst-usefulness questions: relevant programs found, irrelevant items to inspect,
  programs with complete clinical histories, missing scientific and commercial facts, and
  the manual checking needed.

Every preregistered threshold failure is reported as a failure. No engine change, rerun or
reference edit follows from the score.
