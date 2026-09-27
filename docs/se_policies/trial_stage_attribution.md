# Trial stage attribution: a trial's phase belongs to what it investigates

Status: **FROZEN**, 2026-09-27, written before any code change. Second population milestone
promoted by `ranking_lexicographic_v1.md`. Follows the adopted regimen human-PoC rule
(`human_poc_regimen_list_attribution.md` + Amendment 1). Ranking v1 is unchanged.

## The defect

`ClinicalTrialsEvidenceExtractor` mints a `development_stage_order` fact for **every** hit on a
protocol from `designModule.phases`. Conditioning, chemotherapy and other co-administered
agents therefore carry the phase of the product under study. On TAC01 after the regimen fix,
six of the top 20 are NON_ASSET rows ranked on these facts (Cyclophosphamide, Fludarabine,
Fludarabine-based, lenalidomide, NKTR-255, R-mini-CHOP). Cyclophosphamide alone holds 205
stage facts.

## The rule

A hit receives the trial's phase only when the record gives evidence that the hit is what the
trial investigates. Otherwise the stage fact is **withheld**. Nothing else about the hit
changes: its identity, its other facts and its population membership are untouched.

Decided per hit, in this order. The first rule that applies decides.

1. **Title-derived hit.** Discovery names a hit after the trial's `briefTitle` when it finds no
   candidate intervention. That name *is* the trial's subject, so it is attributed:
   `STAGE_FROM_TRIAL_TITLE_SUBJECT`.
2. **Unresolved intervention.** No intervention on the record matches the hit (by `name`,
   `otherNames`, or an asset name observed in either): withheld, `WITHHELD_UNRESOLVED`.
3. **Declared support role.** The intervention declares itself supportive: withheld,
   `WITHHELD_SUPPORT_ROLE`. That is:
   - its `name` contains a support term; or
   - a sentence of its `description` that names the intervention itself contains a support
     term, or places it before an infusion, a cell product, a CAR or a transplant ("prior to",
     "before").
   - Support terms: lymphodepletion, conditioning, bridging, premedication, supportive care,
     prophylaxis, rescue.
   - A support term preceded by "following" or "after" describes what the intervention comes
     after, so it does not count.
   - A description sentence that does not name the intervention says nothing about its role.
     A CAR-T's description "Prior to cellular infusion, patients receive lymphodepletion" is
     about the conditioning, not the CAR-T.
4. **Not experimental.** The trial has more than one intervention and the existing
   `_arm_relationships` reading for this intervention is not therapeutic (comparator, specific
   comparator or unknown): withheld, `WITHHELD_NOT_EXPERIMENTAL`. Being in an experimental arm
   is necessary, not sufficient.
5. **Evidence of investigation.** Attributed only on one of:
   - the trial has exactly one intervention: `STAGE_FROM_SOLE_INTERVENTION`;
   - one of the intervention's names appears in `briefTitle` or `officialTitle`:
     `STAGE_FROM_TITLED_INTERVENTION`.
6. **Otherwise** withheld, `WITHHELD_AMBIGUOUS_PARTNER`. Ambiguity withholds; it never guesses.

The reason is machine-readable. An attributed stage claim carries
`extraction_method = "ctgov_stage:<REASON>"`. Withheld reasons are counted by the evaluation
script. No drug is named in the rule. NKTR-255 and lenalidomide get whatever it decides.

## Evaluation

The change is upstream of gating, so it is measured by **replay** of both accepted runs from
their sealed custody. Same commands as `se_runs/{tac01,mint5}_ind_fix/reproduce.sh`, with new
output dirs `se_runs/tac01_stage_fix` and `se_runs/mint5_stage_fix`. Replays run in the
operator's terminal. The regimen human-PoC rule is already in the code, so these replays carry
both population fixes.

### Criteria (all must PASS)

- **S1 — conditioning loses stage.** In TAC01, Cyclophosphamide, Fludarabine,
  Fludarabine-based and R-mini-CHOP each keep at most 10% of their `ind_fix` stage-fact count,
  and none of the four is in the top 20.
- **S2 — positive controls keep stage.** Each of these holds at least one
  `development_stage_order` fact:
  - TAC01: Axicabtagene Ciloleucel, Tisagenlecleucel, Lisocabtagene Maraleucel,
    Brexucabtagene Autoleucel, CC-97540, KITE-753.
  - mint5: AZD0120, CABA-201, FKC289, GC012F, BH2024, CM336, CNCT19, ICG318.
- **S3 — collateral is listed.** Every asset that holds a stage fact in `ind_fix` and none
  after the change is listed with its withheld reasons. Any asset judged by hand to be a real
  investigational programme on that list is a defect of the rule.
- **S4 — unit tests.** One test per reason code, the CAR-T description that mentions
  lymphodepletion (kept), and a comparator-arm drug (withheld). Full S&E suite green.
- **S5 — ranking conformance.** The frozen ranking v1 scorer reports R1–R3 PASS on both new
  runs.

### Reported, not criteria

- TAC01 and mint5 top 20 under the frozen K1/K2 rubric.
- Withheld-reason counts per run.
- NKTR-255 and lenalidomide positions.

### Decision rule, fixed now

- S1–S5 pass: adopted. Duplicate merging follows.
- S2 fails, or S3 finds a real programme stripped: FAILED_ACCEPTANCE. A revision needs an
  amendment. The rule is not loosened to rescue K1.
- K1 remains reported. Whether the remaining antibody/ADC rows need a modality-aware ranking
  amendment is decided only after duplicate merging.
