# Pilot gucy2c_oncology_v1: preregistered protocol

**Status: UNVALIDATED (AI-run exploratory benchmark).** Claude (Anthropic model `claude-opus-5-5`)
chose the question, operated the engine and will prepare the reference. No human analyst
built the answer key. This is not human-independent validation.

Written and committed **before** the engine runs. The spec, criteria and engine problem in this
folder are frozen once this commit is pushed.

## Question

Every anticancer therapeutic directed at guanylyl cyclase C (GUCY2C / GCC / GC-C) that entered
human trials (Phase 1 or later) at any time up to **2026-10-24**, including programs later
discontinued, terminated or withdrawn. Any modality.

Why this area: no prior BVE benchmark, review packet or development set covered GUCY2C (repo
grep shows the symbol only inside bulk ontology surveys). It has a small, publicly documented
landscape and built-in traps (GUCY2C agonist peptides for GI disorders share the target).

## Inclusion

- Target: GUCY2C, as the therapeutic's binding target or the antigen it is directed at.
- Intended use: treatment of cancer.
- Stage: at least one human interventional study registered or published by the as-of date.
- Any modality: ADC, bispecific/T-cell engager, CAR-T or other cell therapy, vaccine,
  radioligand, naked antibody, small molecule.

## Exclusion (negative controls are drawn from these)

- GUCY2C agonist peptides for constipation, IBS or other bowel disorders.
- Diagnostic or imaging-only agents.
- Preclinical-only programs.
- Drugs that target something else and were merely tested in GUCY2C-expressing tumours.

## Scoring rules (fixed now)

- `criteria.json` thresholds: strict precision ≥ 0.50, recall ≥ 0.60, overall trial coverage
  ≥ 0.50, identity errors ≤ 1, misleading claims ≤ 2.
- The scorer's verdict is reported, but the official grade stays **UNVALIDATED** because the
  reference is AI-prepared (`independent_of_engine: false`).
- No engine change, tuning or rerun after the result is observed. A failed run is reported as a
  failure.

## Engine translation (`engine_problem.yaml`)

Compiled deterministically by the engine's own intent compiler from the asset-free question
"GUCY2C programs" (TA = ONCOLOGY, as-of 2026-10-24); the only hand edit is
`evidence_floor.minimum_stage: PHASE_1`. Target aliases come from the engine's ontology, not
from the operator. Indications are left empty: the spec's indication list ends with "other
GUCY2C-expressing solid tumors", so the oncology TA gate is the faithful translation and a
narrower indication gate would exclude in-scope assets by construction.

## Resource limits

- Command: `bve-se-search --problem engine_problem.yaml --output-dir <run dir> --progress`
  (live public sources only: ClinicalTrials.gov, PubMed and the engine's other free
  connectors). No paid API, no cloud resources.
- Memory: capped at 4 GiB for the process (`systemd-run --user --scope -p MemoryMax=4G`, or
  `ulimit -v` if systemd is unavailable).
- Wall clock: 3 hours hard timeout. A run that exceeds it is recorded as a failure.
- One run. No retry after seeing candidates. A retry is allowed only for an infrastructure
  failure before any candidate is produced, and is logged.

## Reference preparation

After the engine output is sealed, a fresh Claude subagent receives only `spec.json` and this
file's inclusion/exclusion rules, researches public primary sources, and writes
`reference.json` outside the repository. Isolation actually achieved is recorded in the report.
