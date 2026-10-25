# Second blinded S&E benchmark: preregistered target draw and protocol

**Status: UNVALIDATED (AI-run exploratory benchmark).** Claude (`claude-opus-5-5`) wrote
this protocol, will operate the engine, and will launch a separate Claude process to
prepare the reference. No human prepared or checked the answer key. This is not
human-independent validation.

Committed and pushed **before** the seed exists and before any target is known.

## 1. Candidate pool (`pool.json`, produced by `draw_target.py`)

- **Frame.** Targets in the engine's ontology snapshot (`data/se/ontology/current`,
  `edges.jsonl` sha256 `2a6b6ea8…3f551`) with at least **5 distinct drugs** on `USABLE`
  `DIRECT_TARGET` edges.
  - "Clinical-stage drug edge" means such an edge. Both edge sources, ChEMBL
    `drug_mechanism` and Open Targets drug mechanism-of-action, are curated for approved
    drugs and clinical candidates.
  - The snapshot stores no per-drug phase, so this is an **assumption about the sources,
    not a per-drug check**.
- **Exclusions, applied mechanically:**
  1. Named: PDCD1, CD274, CD19, TNFRSF17 (BCMA), SLC6A2, HRH1, HTR2A, CHRM1, GUCY2C,
     CD3E, MS4A1.
  2. Any target whose symbol appears as a whole word in any Markdown or YAML file under
     `research/` or `docs/`, which hold every prior benchmark report, problem file and
     development example. This over-excludes on purpose. A target merely mentioned once in
     a report is also out.
  3. Any target the engine's own resolver does not resolve unambiguously
     (`resolve_target(...).status != RESOLVED`). Otherwise the draw could land on a symbol
     the engine refuses by design.
- **Result:** 159 eligible, 101 excluded (78 rule 2, 13 rule 3, 10 rule 1). The full lists,
  with reasons, are in `pool.json`.
- **Bias, disclosed.** The frame is BVE's own ontology. It favours targets that ChEMBL and
  Open Targets already curate well, with at least 5 mechanism-annotated drugs. Such
  targets are better represented in the engine's data than a random human target, and the
  draw cannot measure performance on targets the ontology lacks.

## 2. Seed and draw

- **Seed:** the `randomness` value of the first **drand mainnet** round (League of Entropy
  default chain, `https://api.drand.sh/public/<round>`) whose time is **at least 5 minutes
  after this commit is pushed**. The push time is recorded from `git` and the remote. The
  round number is computed as `floor((push_time + 300 − 1595431050) / 30) + 2`, i.e. the
  first round strictly after that instant on the 30-second chain.
- **Draw:** for each eligible symbol `s`, `sha256(seed_hex + ":" + s)`. The target with the
  smallest digest is selected. There is no sort-order or tie freedom, and no second draw.
- **No override.** The drawn target is used even if it looks hard, easy, dull or
  unsuitable. If the engine later fails on it, that failure is the result.

## 3. Question (template, frozen now; only `<T>` is filled after the draw)

`spec.json` will be exactly:

```json
{
  "spec_id": "<t>_clinical_any_v1",
  "therapeutic_area": "unspecified",
  "indications": [],
  "targets": ["<T>"],
  "modalities": [],
  "stages": ["PHASE_1", "PHASE_2", "PHASE_3", "APPROVED"],
  "as_of_date": "<draw date, UTC>",
  "query_text": "Find every therapeutic directed at <T> (as its binding target or the antigen it is directed at) that has entered human clinical testing (Phase 1 or later) at any time up to the as-of date, including approved products and programs that were later discontinued, terminated or withdrawn. Any modality and any therapeutic area qualify. Exclude diagnostic or imaging-only agents, programs that never entered human trials, and drugs whose primary pharmacological target is something else. For each asset report all names and development codes, target, modality, highest development stage, and every associated clinical trial registration."
}
```

The area is **unspecified**. No narrower scope is justified before seeing the target, and
the engine treats an unspecified area as no constraint.

## 4. Pass/fail criteria (frozen now)

`criteria.json` will be exactly these thresholds, the same as `gucy2c_oncology_v1` so the
two are comparable in form:

```json
{"precision_basis": "strict",
 "thresholds": {"min_precision": 0.5, "min_recall": 0.6, "min_trial_coverage": 0.5,
                "max_identity_errors": 1, "max_misleading_claims": 2}}
```

The verdict is computed by the existing scorer and reported, but **the official grade
stays UNVALIDATED**, because the reference is AI-prepared (`independent_of_engine: false`).

## 5. Engine freeze and translation

- **Engine commit:** the commit that adds the drawn target's spec and prereg. It contains
  no `src/` change relative to `ba9becf`; that is verified with `git diff --stat ba9becf --
  src` = empty and recorded.
- **Problem:** compiled by the engine's own intent compiler, with
  `bve-se-search --query "<T> programs" --as-of <date> --emit-problem engine_problem.yaml`.
  The only hand edit is `evidence_floor.minimum_stage: PHASE_1`, as in the first pilot.
  Aliases come from the ontology. The therapeutic area and indications are left
  unspecified.
- **No changes after the draw** to the engine, gates, identity rules, ontology, query
  strategy or criteria.

## 6. Run

- `bve-se-search --problem engine_problem.yaml --output-dir <run> --format shortlist
  --progress`, live. The source configuration is the same as the first pilot: no
  `--source-index`, no `BVE_SE_USER_AGENT`, default free connectors. The missing families
  are recorded from the engine's own source report before scoring.
- Limits: `systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0`, `timeout 3h`.
- **One run.** A retry is allowed only for an infrastructure failure before any candidate is
  produced, and it is logged. An INCOMPLETE run is scored and reported as INCOMPLETE.
- Then `se_pilot export` → `seal` (official and review populations), committed and pushed
  before the reference session starts.

## 7. Reference

A separate `claude -p` process is started after the seal is pushed:
- with `--restricted`, file tools only, and web search/fetch;
- in a folder outside the repo holding only `spec.json`, the inclusion/exclusion rules and
  its prompt.

It writes `reference.json` (`preparer` = AI, `independent_of_engine: false`,
`synthetic: false`) with:
- in-scope assets, with names, codes, target, modality, stage and trials;
- commercial facts where sourced;
- 3–10 negative controls;
- recorded gaps.

The reference stays outside GitHub. It is not edited after scoring.

## 8. Scoring

`se_pilot score` on both sealed views. Scorer disagreements, AI-reviewed discrepancies and
primary-source checks are reported separately. No engine change, rerun or reference edit
follows from the score.
