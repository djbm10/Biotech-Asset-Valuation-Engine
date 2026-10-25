# Pilot il3ra_clinical_any_v1: preregistered protocol

**Status: UNVALIDATED (AI-run exploratory benchmark).** Claude (`claude-opus-5-5`) drew the
target mechanically, operates the engine, and will launch a separate Claude process for the
reference. No human prepared the answer key. This is not human-independent validation.

Written and committed **before any acquisition for this target**. It instantiates
`../target_draw_v3/PROTOCOL.md` (commit `3c7f48d`) with no deviation.

## Target draw

- Protocol and pool were pushed at 2026-10-25T18:41Z (`3c7f48d`; 153 eligible targets).
- Seed: drand mainnet round **6584099** (2026-10-25T18:46:30Z), randomness
  `45ede9c0…b17ee4` (`../target_draw_v3/drand_round_6584099.json`).
- Draw: smallest `sha256(seed:symbol)` → **IL3RA** (CD123; 5 drugs on direct edges). The next
  four, which are not used, were MAP2K2, MMP9, EDNRA and CDK1. The pool recomputed at draw
  time is identical to the committed one (`../target_draw_v3/draw_result.json`).
- Used as drawn.

## Question, criteria, problem

- `spec.json` and `criteria.json` are the frozen templates with `<T>` = IL3RA, as-of
  2026-10-25. Area unspecified, any modality, Phase 1 or later.
- Thresholds: strict precision ≥ 0.50, recall ≥ 0.60, trial coverage ≥ 0.50, identity errors
  ≤ 1, misleading claims ≤ 2. The official grade stays UNVALIDATED regardless.
- `engine_problem.yaml` was compiled by calling `bve.cli.se_search.problem_from_args` with
  `--query "IL3RA programs" --as-of 2026-10-25 --emit-problem …` from Python. That function
  compiles and writes. It does not search. `outputs/se/` stayed empty, and the run directory
  `~/se_runs/il3ra_pilot_v1` did not exist. Aliases are the ontology's (CD123, IL-3RA,
  interleukin-3 receptor subunit alpha, …). The one hand edit is
  `evidence_floor.minimum_stage: PHASE_1`.
- Engine: `git diff fcfefe3 -- src` is empty (verified).

## Run

`systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 timeout 3h bve-se-search
--problem engine_problem.yaml --output-dir ~/se_runs/il3ra_pilot_v1/run --format shortlist
--progress`, live, once.
- Same source configuration as both earlier pilots: no `--source-index`, no
  `BVE_SE_USER_AGENT`.
- NOT_CONFIGURED families are recorded from the engine's source report.
- The run is marked INCOMPLETE if the engine says so.
- Then export, seal both populations, commit and push before the reference session starts.

## Inclusion / exclusion (given to the reference preparer verbatim)

- **In scope:** a therapeutic whose binding target, or the antigen it is directed at, is
  IL3RA (CD123), with at least one human interventional study (Phase 1 or later) registered
  or published by 2026-10-25. Approved, active, discontinued, terminated and withdrawn
  programs all count. Any modality (antibody, ADC, bispecific/T-cell engager, CAR-T or other
  cell therapy, fusion protein, radioligand, small molecule) and any therapeutic area.
- **Bispecific or multi-specific agents** count when CD123 is one of the antigens they are
  directed at. **Ligand-directed agents** count when CD123/IL-3Rα is the receptor they are
  designed to target (for example an IL-3–toxin fusion).
- **Out of scope**, with negative controls drawn from these:
  - drugs for other targets, including other AML surface antigens (CD33, CLL-1/CLEC12A, CD47,
    CD70) and the IL-5/GM-CSF receptor α chains;
  - preclinical-only CD123 programs;
  - diagnostic or imaging-only agents.
