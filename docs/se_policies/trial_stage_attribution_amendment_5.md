# Amendment 5: stage by default, withheld only on positive evidence (v3)

Status: **FROZEN**, 2026-09-27, written before any code change. It replaces the decision rule of
`trial_stage_attribution.md` and Amendments 1–4. The code that failed acceptance under Amendments
2–4 (6bbb2cf) was reverted in 32ba146.

The criteria S1–S5, the positive controls, the replay commands, the sealed corpora, the frozen
ranking scorer and the decision rule are unchanged. The new output directories are
`se_runs/{tac01,mint5}_stage_fix_v3`.

## Why the principle changes

Two attempts required positive proof, read from prose, that a hit is "the one being studied".
Each round fixed the phrasings it named and stripped real programs on new ones (SC291, ALLO-329,
TranspoCART19, KITE-363, CART22-65s, huCART19-IL18). CT.gov prose is too inconsistent to support
that burden of proof. The burden moves:

> **A structured trial intervention keeps the trial's stage unless there is positive evidence
> that it is not the investigational program.**

The known cost: co-given drugs whose own record is bare ("Given IV") regain stage. S1 is the
guardrail that measures it; it is not loosened.

## The rule

Decided per hit, in this order. The first rule that applies decides.

1. **Title-derived hit** (unchanged): `STAGE_FROM_TRIAL_TITLE_SUBJECT`.
2. **Unresolved** (unchanged): no intervention's names (name, otherNames, or an asset name
   observed in either) match the hit → `WITHHELD_UNRESOLVED`.
3. **Positive exclusions.** Evidence is read only from the matching intervention's own structured
   record and its arm links, never from other interventions, arm descriptions or the title.
   - `WITHHELD_CONTROL_ROLE`:
     - the intervention's `name` contains "placebo", "sham" or "vehicle" (whole word); or
     - it is linked (either CT.gov direction) to any arm typed `ACTIVE_COMPARATOR`,
       `PLACEBO_COMPARATOR`, `SHAM_COMPARATOR` or `NO_INTERVENTION`.
   - `WITHHELD_NON_PRODUCT`:
     - its CT.gov `type` is `DIAGNOSTIC_TEST`, `PROCEDURE`, `BEHAVIORAL`, `DEVICE` or
       `RADIATION`; or
     - its `name` or the **first sentence** of its own `description` contains a diagnostic term:
       "imaging agent", "tracer", "contrast agent", "radiotracer", "diagnostic", "PET".
   - `WITHHELD_SUPPORT_ROLE`: its `name`, or the **first sentence** of its own `description`,
     contains a support term (lymphodepletion, conditioning, bridging, premedication, supportive
     care, prophylaxis, rescue) that is **not preceded** in that sentence by a temporal marker
     ("before", "prior to", "after", "following", "followed by", "then", "during", "until").
     - "Lymphodepletion chemotherapy", "Chemotherapy for lymphodepletion" → support.
     - "CAR-T cell therapy administered following lymphodepleting chemotherapy" → not support;
       the chemotherapy is the reference point, not what the record describes.
     - "Prior to cellular infusion, patients receive lymphodepletion …" → not support.
4. **Otherwise** attributed: `STAGE_FROM_STRUCTURED_INTERVENTION`.

Consequences stated in advance:
- A trial's only intervention keeps stage unless rule 3 applies to it.
- Co-interventions never withhold stage from a hit; there is no ambiguity code. Generic arm
  labels ("Dose Finding Arm") are irrelevant.
- Arm descriptions are not read. "SC291 with lymphodepleting therapy" cannot withhold SC291.
- When several interventions resolve to the hit (e.g. "BMS-986337" and "BMS-986337 Placebo"),
  stage is attributed if any of them is attributed.
- **Title**: never grants or withholds. An attributed claim whose intervention is named in
  `briefTitle` or `officialTitle` records `extraction_method = "ctgov_stage:<REASON>+TITLE"`,
  otherwise `"ctgov_stage:<REASON>"` (as Amendment 2, change A).
- No drug is named. Lenalidomide, NKTR-255 and cyclophosphamide get what the rule decides.

## Unit tests required (S4)

One test per reason code, plus:
- SC291 (sole intervention, arm "with lymphodepleting therapy") attributed;
- TranspoCART19 (own description "administered following lymphodepleting chemotherapy") attributed;
- DuoCAR with partners "Fludarabine (Conditional therapy)" described "Lymphodepletion
  chemotherapy": product attributed, partners support;
- huCART19-IL18 attributed, the [18F] imaging agent `WITHHELD_NON_PRODUCT`;
- BMS-986337 attributed despite placebo and famotidine partners; the placebo is control role;
- CART22-65s and huCART19 under generic arm labels both attributed;
- the R-mini-CHOP/AZD0486 structure: R-mini-CHOP control role, AZD0486 attributed;
- title annotation present/absent, and a title never rescuing an excluded intervention.

## Result (appended 2026-09-27): FAILED_ACCEPTANCE

Replays `se_runs/{tac01,mint5}_stage_fix_v3` (code 184e470). Per-asset counts are in
`stage_attribution_eval.txt`; scorer output in `ranking_v1_compare.txt`.

- **S1: FAIL.** Cyclophosphamide 205→147 (72%), Fludarabine 181→132 (73%), Fludarabine-based
  1→1 (100%); R-mini-CHOP 1→0. Cyclophosphamide (#7), Fludarabine (#8) and Fludarabine-based
  (#10) are in the TAC01 top 20. Of the cyclophosphamide hits, 146 are attributed, 41 support,
  13 control: most conditioning records are bare ("Given IV") and give no positive evidence.
- **S2: PASS.** Every control keeps stage (axi-cel 20→18, tisa-cel 8→7, liso-cel 10→9,
  brexu-cel 7→7, CC-97540 7→7, KITE-753 1→1; all eight mint5 controls unchanged).
- **S3: FAIL, much reduced.** 113 TAC01 assets lose all stage (295 under Amendment 2), mostly
  real non-programs (Placebo, Biospecimen Collection, Leukapheresis, HSCT, CliniMACS device).
  Every Amendment 2 defect case is fixed (SC291, TranspoCART19, ALLO-329, KITE-363, huCART19,
  DuoCAR, BMS-986337, JCAR015, FT576, CART22, ET019002). Real products still stripped by the
  first-sentence support test, because sponsors write the regimen into the product's own record:
  - CAR-NK-CD19 Cells: "…, treatment follows a lymphodepletion" (clause after a comma);
  - ALA-101: "Single IV infusion of ALA-101 post chemotherapy conditioning" ("post" is not a
    listed marker);
  - CD19-TriCAR-T/SILK: "A conditioning chemotherapy regimen … may be administered, followed by
    … CD19-TriCAR-T cells" (support term leads the sentence).
- **S4: PASS.** 16 unit tests; full S&E suite 1505 passed, 3 xfailed.
- **S5: PASS.** R1–R3 PASS on both runs.

TAC01 is at #81. The mint5 top 20 differs from Amendment 2's only by "Chemotherapy Agents"
entering at #17.

**Decision: FAILED_ACCEPTANCE.** 184e470 is not adopted.

The two failures bracket the problem. Requiring positive proof of investigation strips real
programs (S3); requiring positive proof of support restores conditioning (S1). Per-intervention
text does not reliably separate the two in either direction.
