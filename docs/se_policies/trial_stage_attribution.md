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

## Result (appended 2026-09-27): FAILED_ACCEPTANCE

TAC01 replay `se_runs/tac01_stage_fix` (code 73665a5, with Amendment 1). Per-asset counts in
`stage_attribution_eval.txt`. Reasons were recomputed from the sealed snapshots with `why.py`.
Stage facts fell from 2,268 to 1,232. Assets holding a stage fact fell from 1,057 to 745.

- **S1: FAIL.** Cyclophosphamide 205→6, Fludarabine 181→2 and Fludarabine-based 1→0 pass.
  R-mini-CHOP keeps 1 of 1 and stays in the top 20 (#10). It is attributed
  `STAGE_FROM_TITLED_INTERVENTION` on NCT07215585, whose title names the backbone next to the
  bispecific under study ("AZD0486 with R-mini-CHOP"). A title names combination backbones as
  well as investigational products. Title presence is not evidence of investigation.
- **S2 (TAC01): PASS.** Axi-cel 20→14, tisa-cel 8→4, liso-cel 10→6, brexu-cel 7→7,
  CC-97540 7→7 and KITE-753 1→1. mint5 is not needed for the decision.
- **S3: FAIL, real programs stripped.** 312 assets lost every stage fact. Most are correct:
  biospecimen collection, leukapheresis, conditioning, placebo, transplant procedures. Real
  investigational programs are among them too, by two defects:
  1. **Support-role false positives.** The product's own description names it as the reference
     point for the conditioning: "conditioning therapy ... conducted before CD19-UCART
     injection" (CD19-UCART); "receive lymphodepleting chemotherapy, followed by ... rapcabtagene
     autoleucel (YTB323)" (YTB323); "During JWCAR029 production, subjects receive conditioning"
     (JWCAR029, sole intervention). The self-naming sentence test cannot tell the subject of a
     support clause from its reference point.
  2. **Ambiguous-partner false withholds.** Co-investigational products in one trial:
     - SCRI-huCAR19v1/v2, where the title names neither;
     - huCART19 alongside CART22, where the title says "huCART19" but the intervention is
       "huCART19 Cells" and the observed-name channel did not yield the short form;
     - KYMRIAH, YESCARTA, Tecartus and Breyanzi on a multi-product commercial CAR-T protocol.
     Also stripped: JCAR015, JCAR017 schedules, cilta-cel, SL19, 4SCAR19 constructs.
- **S4: PASS.** 10 unit tests; full S&E suite 1499 passed, 3 xfailed.
- **S5: PASS.** Frozen scorer R1–R3 PASS (`ranking_v1_compare.txt`).

Reported:
- Top 20: brexu-cel, CNCT19, axi-cel, tafasitamab, tisa-cel, CC-97540, KITE-753,
  lenalidomide, NKTR-255, R-mini-CHOP, denintuzumab, KTE-C19, KTE-X19, liso-cel,
  loncastuximab, MEDI-551, SAR3419, 7×19-THEMIS, ALLO-501A, anti-CD19+anti-CD20 CAR-T.
- Cyclophosphamide and Fludarabine are gone from the top 20. Lenalidomide (#8, titled in a
  multi-agent DLBCL trial) and NKTR-255 (#9, titled "with or without NKTR-255") are the
  honest result of rule 5 as written.

**Decision: FAILED_ACCEPTANCE.** The code at 73665a5 is not adopted. Per the decision rule, it
is not loosened to rescue K1. A revision needs an amendment addressing all three defects:
- title evidence that includes backbones;
- the self-naming support test;
- partner ambiguity between co-investigational products.
