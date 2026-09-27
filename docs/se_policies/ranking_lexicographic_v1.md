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

## Result (appended 2026-09-27)

Scored offline with the frozen scorer. Raw output is at `se_runs/<run>/ranking_v1_compare.txt`.

### Implementation: R1–R4 PASS

| | TAC01 (`tac01_ind_fix`) | mint5 (`mint5_ind_fix`) |
|---|---|---|
| **R1** conformance | 683/683, no divergence | 327/327, no divergence |
| **R2** population invariance | excluded band 760/760, 0 entries naming no FAIL | excluded band 705/705, 0 entries naming no FAIL |
| **R3** determinism | identical | identical |

In both runs the ranked set equals the visible set, and the deferred set equals low-support minus EXCLUDED.

**R4** is covered by `tests/se/test_shortlist_ranking_v1.py::TestCoverageNeutral`. The tests show that eight extra documents on one asset, or a FAILED or NOT_CONFIGURED source, move no position.

### K1: TAC01 top 20, judged by hand

The "4 approved" condition passes: brexu-cel is at #3, axi-cel at #7, liso-cel at #8 and tisa-cel at #11.

| # | row | judgement |
|---|---|---|
| 1 | Cyclophosphamide | NON_ASSET (conditioning) |
| 2 | lenalidomide | NON_ASSET (combination arm) |
| 3 | Brexucabtagene Autoleucel | RELEVANT |
| 4 | CNCT19 | RELEVANT |
| 5 | vincristine | NON_ASSET (chemo) |
| 6 | CCL19 | NON_ASSET (construct fragment of "7×19" CAR-T) |
| 7 | Axicabtagene Ciloleucel | RELEVANT |
| 8 | Lisocabtagene Maraleucel | RELEVANT |
| 9 | Loncastuximab Tesirine | OFF_TARGET (CD19 ADC, not cell therapy) |
| 10 | Tafasitamab | OFF_TARGET (CD19 mAb) |
| 11 | Tisagenlecleucel | RELEVANT |
| 12 | Fludarabine | NON_ASSET (conditioning) |
| 13 | CC-97540 | RELEVANT |
| 14 | Fludarabine-based | NON_ASSET (conditioning) |
| 15 | KITE-753 | RELEVANT |
| 16 | NKTR-255 | NON_ASSET (adjunct arm to CAR-T; see note) |
| 17 | R-mini-CHOP | NON_ASSET (chemo) |
| 18 | denintuzumab mafodotin | OFF_TARGET (CD19 ADC) |
| 19 | KTE-C19 | DUPLICATE of axi-cel |
| 20 | KTE-X19 | DUPLICATE of brexu-cel |

Tally: RELEVANT 7, NON_ASSET 8, DUPLICATE 2, OFF_TARGET 3.

- RELEVANT is 7, below the 10 required, so **K1 FAILS**.
- DUPLICATE + NON_ASSET is 10, which meets the ≥ 10 bar.

**Boundary disclosure.** The count sits exactly at the threshold, and one row decides it:

- NKTR-255 is an IL-15 agonist. It appears here only as an adjunct arm in CD19 CAR-T trials, so it is judged the way lenalidomide is judged.
- If it were judged OFF_TARGET instead, the count would be 9, and the decision rule would read FAILED_ACCEPTANCE rather than a population defect.

The substance favours the population reading:
- The rows above the approved products are arm and conditioning agents. They carry their trial's `human_poc_present` and stage facts, which is the logged arm/background-asset milestone.
- The two duplicates are the logged identity-merge milestone.
- The order itself is behaving as declared.

### K2: mint5 top 20, judged by hand

| # | row | judgement |
|---|---|---|
| 1 | ICG318 | RELEVANT |
| 2 | CCS1477 | OFF_TARGET (p300/CBP inhibitor, myeloma) |
| 3 | Inobrodib | DUPLICATE of CCS1477 |
| 4 | mezigdomide | OFF_TARGET (CELMoD, myeloma) |
| 5 | pomalidomide | OFF_TARGET (IMiD, myeloma; not a conditioning or chemo agent) |
| 6 | vedolizumab | OFF_TARGET (α4β7, IBD) |
| 7 | AZD0120 | RELEVANT |
| 8 | CABA-201 | RELEVANT |
| 9 | FKC289 | RELEVANT |
| 10 | GC012F | DUPLICATE of AZD0120 |
| 11 | umbilical cord blood CD19-BCMA CAR-T cells infusion | RELEVANT |
| 12 | CD19-BCMA dual nanobody based CAR-T Cells | RELEVANT |
| 13 | BC19 | RELEVANT (IgG4-RD; target not independently verified) |
| 14 | BH2024 | RELEVANT |
| 15 | budoprutug | RELEVANT (anti-CD19 mAb, SLE/PMN) |
| 16 | CD19CART | NON_ASSET (descriptive name merged across sponsors) |
| 17 | Chemotherapy Agents | NON_ASSET |
| 18 | CM336 | RELEVANT |
| 19 | CNCT19 | RELEVANT |
| 20 | CRT-402 | RELEVANT (autoimmune; target not independently verified) |

- RELEVANT is 12, or 10 without the two unverified rows, so the ≥ 10 condition is met.
- No conditioning or chemo agent is in the top 5.
- **K2 PASSES.**

Observation (not a criterion): ranks 2–6 are myeloma and IBD drugs that have no stage fact. They rank on a literature human-PoC PASS, which is an evidence-subject question and not an ordering one.

### Decision

- R1–R4 pass, so the ranker stays as implemented.
- K1 fails with population defects at 10 of 20 (boundary disclosed above). Under the rule fixed in this declaration, **the post-parser population milestones are promoted**: arm/background non-asset records and identity-merge misses. **The ranking policy is not tuned.**
- Reference positions: TAC01 is at #87. In mint5: ICG318 #1, AZD0120 #7, CABA-201 #8, FKC289 #9, GC012F #10, BH2024 #14, CM336 #18, CNCT19 #19, HBI0101 #24, IM19 #25, Inaticabtagene autoleucel #27, QT-019C #56, KN5501 #74, RD06 #79.

### Limitation: mint5 passes on hand judgement, not engine target facts (appended 2026-09-27)

In the mint5 top 20, all 20 rows have `UNRESOLVED` target status. K2's RELEVANT count therefore rests on the hand rubric: rows 13
(BC19) and 20 (CRT-402) are counted without independent target verification. This is a
target-evidence coverage problem, not a reason to change the order.
