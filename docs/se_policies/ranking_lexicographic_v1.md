# Shortlist ranking v1: declared lexicographic order

Status: **FROZEN**, 2026-09-27, written before any code change. This is the first ranking
milestone, opened by the operator after the TA-gate and indication fixes were accepted
(`ta_gate_semantics_amendment_1.md`, `indication_gate_semantics.md`). Background:
`docs/se_ranking_audit.md`, `docs/se_candidate_population_validation.md`.

## The defect

`build_shortlist` orders the visible population as follows: eligible first, then
`TargetAssertionStatus`, then **document count**, then mention count, then name.

- Document count measures how often a name is mentioned. It does not measure how relevant or
  how advanced an asset is.
- In `mint5_on`, conditioning chemotherapy filled ranks 1–12 of a dual CD19/BCMA autoimmune
  query.

The order says nothing a BD reader asks about: is it developed in humans, does it work, how far
along is it.

## The order (lexicographic; no weights, no score)

Visible assets are those neither EXCLUDED nor low-support. They are sorted by these keys, in
this order. Each key is compared only when every earlier key ties.

1. **Eligibility.** ELIGIBLE comes before review, which is today's first key, unchanged.
2. **Human efficacy.** PASS comes before UNKNOWN.
   - PASS means the asset's `evidence.human_poc` decision is PASS.
   - When the problem makes no human-PoC requirement, PASS means the asset has a
     `human_poc_present` fact whose value is true and which no claim contradicts.
   - Anything else is UNKNOWN. A visible asset cannot have a human-PoC FAIL.
3. **Maturity.** Higher first. Maturity is the highest `development_stage_order` fact on the
   asset, uncontradicted, on the engine's existing scale (`gates/engine.py` `_STAGE_ORDER`,
   `PHASE_1`=2 … `APPROVED`=6). An asset with no such fact sorts after every asset that has one.
   These facts are minted only from the asset's own trial records.
4. **Target confidence.**
   1. The `target.expression` decision: PASS comes before UNKNOWN, and UNKNOWN comes before no
      decision.
   2. Then the existing `TargetAssertionStatus` precedence, with no assertion last.
5. **Evidence completeness.** More first. This key is the number of the asset's gate decisions
   that are PASS. On a visible asset every decision is PASS or UNKNOWN, so this is "how much of
   the question is answered".
6. **Deterministic tie-break.** Casefolded canonical name, then asset id.

### Removed or unchanged

- **Removed:** document count and mention count. They are not ranking keys any more.
- **Unchanged:** a real pairwise rank from `rank_profiles` still supersedes the whole order.
  It is unwired today, and this milestone does not wire it.

### Coverage is shown, never a negative

No key reads source coverage, source family, document count or corpus size. A source that
was NOT_CONFIGURED or FAILED cannot move an asset down. Coverage stays in the shortlist's
corpus section exactly as today.

### Excluded because

Excluded assets are no longer only a count. The shortlist carries an `excluded` band:
- every EXCLUDED asset, ordered by casefolded name then asset id;
- each one naming every requirement it FAILed, with that decision's rationale.

It is rendered after the ranked list, capped at `limit` like the other sections. The counts
still describe the whole run. Excluded assets are not ranked.

### `ordering_basis`

The display-order basis changes from `declared_display_order` to
`declared_lexicographic_v1`. `pairwise_ranking` is unchanged.

## Not changed

- the population, gates, identity, evidence, retrieval and the low-support routing
- the entry cards, citations and facts
- the deferred (low-support) section's membership. Its order also uses the new key.

This is a rendering change downstream of gating, so it is evaluated **offline** by rebuilding
the shortlist from the accepted runs' `result.json`. No replay is needed.

## Evaluation

Benchmarks:
- oncology: `se_runs/tac01_ind_fix` (CD19 cell therapy, R/R B-cell lymphoma)
- autoimmune: `se_runs/mint5_ind_fix` (dual CD19/BCMA, autoimmune, with human efficacy)

Scorer: `scripts/se_ranking_v1_compare.py`, frozen with this declaration. It **re-derives the
key independently** from `result.json` and does not import the shortlist code's key.

### Implementation criteria (all must PASS)

- **R1 — conformance.** For each benchmark, the full visible order built by `build_shortlist`
  (unlimited) equals the scorer's independent order exactly.
- **R2 — population invariance.**
  - The set of ranked assets equals the pre-change visible set.
  - The deferred set equals `low_support_asset_ids`, excluding EXCLUDED assets.
  - The `excluded` band equals `excluded_asset_ids`, and every excluded entry names at least
    one FAIL requirement.
- **R3 — determinism.** Two builds of the same result are identical.
- **R4 — coverage-neutral.** A unit test shows that adding source documents to an asset, or
  marking a source family FAILED, changes no position.

### Benchmark readout (preregistered thresholds)

Each benchmark's **top 20** is listed in full and every row is judged by hand against this
rubric, fixed now:

- **RELEVANT:** a distinct therapeutic programme that plausibly answers the question.
  - TAC01: a CD19-directed cell therapy.
  - mint5: a CD19- and/or BCMA-directed therapy studied in autoimmune disease.
- **DUPLICATE:** the same programme as a higher-ranked row (for example GC012F ≡ AZD0120).
- **NON_ASSET:** an arm or background intervention, a conditioning or chemotherapy agent, a
  placebo, a reagent, an ordinary word or a descriptive non-programme.
- **OFF_TARGET:** a real programme that does not answer the question.

Thresholds:

- **K1 — TAC01.**
  - Axicabtagene ciloleucel, tisagenlecleucel, lisocabtagene maraleucel and brexucabtagene
    autoleucel are all in the top 20.
  - RELEVANT ≥ 10 of the top 20.
- **K2 — mint5.**
  - RELEVANT ≥ 10 of the top 20.
  - No conditioning or chemotherapy agent (NON_ASSET) is in the top 5.

### Decision rule, fixed now

- If R1–R4 fail, the implementation is wrong. Fix the code, not the policy.
- If K1 or K2 fails **and** DUPLICATE + NON_ASSET make up ≥ 10 of that top 20, the failure is
  a population defect, not an ordering defect.
  - The post-parser milestones (identity merge misses, arm/background assets) are promoted
    ahead of any ranking change.
  - The ranking policy is **not** tuned to hide them.
- If K1 or K2 fails with fewer than 10 population-defect rows, the order itself is
  wrong. That is recorded as FAILED_ACCEPTANCE, and any revision needs an amendment.
- Positions of `TAC01` and of the mint5 programmes named in the population validation are
  reported, not criteria.
