# Pilot chek1_clinical_any_v1: preregistered protocol

**Status: UNVALIDATED (AI-run exploratory benchmark).** Claude (`claude-opus-5-5`) drew the
target mechanically, operates the engine, and will launch a separate Claude process for the
reference. No human prepared the answer key. This is not human-independent validation.

Written and committed **before** the official engine run. It instantiates the protocol frozen
in `../target_draw_v2/PROTOCOL.md` (commit `faf35aa`). Nothing here departs from that
protocol except the deviation recorded below.

## Target draw

- Protocol and pool were pushed at 2026-10-25T15:50:07Z (`faf35aa`; 159 eligible targets).
- Seed: drand mainnet round **6583757** (2026-10-25T15:55:30Z, 5 min 23 s after the push),
  randomness `67608e0e…88e681`. The round JSON is in `../target_draw_v2/drand_round_6583757.json`.
- Draw: smallest `sha256(seed:symbol)` → **CHEK1** (checkpoint kinase 1; 9 drugs on direct
  edges). The next four, which are not used, were PTGFR, OPRM1, CD40 and CYP11B1. The full
  output is in `../target_draw_v2/draw_result.json`, and the pool recomputed at draw time is
  identical to the committed `pool.json`.
- Used as drawn. No override.

## Question, criteria, problem

- `spec.json` and `criteria.json` are the frozen templates with `<T>` = CHEK1 and as-of
  2026-10-25. Area unspecified, any modality, Phase 1 or later including approved and
  discontinued programs.
- `engine_problem.yaml` was compiled by `bve-se-search --query "CHEK1 programs" --as-of
  2026-10-25 --emit-problem …`. The one hand edit is `evidence_floor.minimum_stage:
  PHASE_1`. Aliases come from the ontology (CHK1, OZEMA21, checkpoint kinase 1, …). The area
  is `UNSPECIFIED`, so no area gate is built.
- Engine commit: this commit. `git diff ba9becf -- src` is empty (verified, 0 lines).

## Deviation: aborted pre-registration acquisition (operator error)

`--emit-problem` writes the problem **and then continues into a live search**. The operator
assumed it only emitted the file. The command was run at 15:57 UTC and stopped by the
operator after about 2 minutes, **before this preregistration was committed**.

- What it produced: 463 raw source snapshots (27 CT.gov, 436 PubMed) written to the
  gitignored `outputs/se/`. No result, shortlist or candidate list was written, and none was
  displayed: stdout and stderr went to `tail` and the process was killed first.
- Handling: the 463 files were moved **unread** to
  `~/se_runs/chek1_aborted_prereg_acquisition/`, outside the repo (tree sha256
  `7b2354e1…cbe0`). They are not an input to the official run, which writes its own
  snapshot and custody directories under its own output directory.
- Effect: the operator saw no candidate. The draw, spec, criteria and problem did not change
  after it (spec and criteria were written before it; the problem file was written by the
  same command before the search started).
- Disclosure: a procedural lapse, not a result. It is recorded so that a reader can weigh
  it.

## Run (unchanged from the frozen protocol)

- `systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 timeout 3h bve-se-search
  --problem engine_problem.yaml --output-dir ~/se_runs/chek1_pilot_v1/run --format shortlist
  --progress`, live.
- Source configuration, the same as the first pilot: no `--source-index`, no
  `BVE_SE_USER_AGENT`. Expected NOT_CONFIGURED families, as in pilot 1:
  - `company_pipeline_or_presentation`
  - `company_press_release`
  - `conference_aacr`
  - `conference_asco`
  - `conference_ash`
  - `conference_eha`
  - `sec_edgar`

  These are confirmed from the engine's own source report. Expected configured:
  ClinicalTrials.gov and PubMed.
- One run, then export, seal (official and review populations), commit and push. The
  reference session starts only after that push.

## Inclusion / exclusion (given to the reference preparer verbatim)

- **In scope:** a therapeutic whose binding target, or the antigen it is directed at, is
  CHEK1, with at least one human interventional study (Phase 1 or later) registered or
  published by 2026-10-25. Approved, active, discontinued, terminated and withdrawn
  programs all count. Any modality and any therapeutic area.
- **Dual or multi-kinase inhibitors** count when CHEK1 is a primary, intended target
  (named as a primary target by the developer or the primary literature, for example a
  CHK1/CHK2 inhibitor). They do not count when CHEK1 inhibition is only an off-target
  activity of a drug developed against something else.
- **Out of scope**, with negative controls drawn from these:
  - drugs whose primary target is something else, including other DNA-damage-response
    kinases (CHEK2-selective, WEE1, ATR, ATM, DNA-PK) and chemotherapies often combined with
    CHK1 inhibitors;
  - preclinical-only CHK1 compounds;
  - diagnostic or tool compounds.
