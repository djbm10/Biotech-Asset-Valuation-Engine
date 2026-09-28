# Amendment 6: explicit trial roles, corpus history only for bare records

Status: **FROZEN**, 2026-09-27, written before any code change. It replaces the decision rule of
`trial_stage_attribution.md` and Amendments 1–5. The code that failed acceptance under Amendment 5
(184e470) was reverted in 7887411.

The criteria S1–S5, the positive controls, the replay commands, the sealed corpora, the frozen
ranking scorer and the decision rule are unchanged. The new output directories are
`se_runs/{tac01,mint5}_stage_fix_a6`.

**Stopping rule, agreed in advance.** If Amendment 6 fails S1–S5, iteration on prose heuristics
stops. The conclusion recorded will be that CT.gov alone cannot support reliable
intervention-level stage attribution without an explicit regimen/role model.

## Why

Amendment 2 required proof that a hit is investigational and stripped real programs (S3).
Amendment 5 required proof that it is support and restored conditioning chemotherapy, because
most conditioning records are bare ("Given IV") (S1). A single trial record often cannot decide.
Amendment 6 decides from the trial record when it is explicit. For bare records it uses what the
drug's *other* trials say explicitly.

## Step 1: the local role of an intervention in one trial

Each intervention in each CT.gov trial gets exactly one local role. The first rule that applies
decides.

1. **`CONTROL`** applies if either:
   - its `name` contains "placebo", "sham" or "vehicle" (whole word); or
   - it is linked, in either CT.gov direction, to an arm typed `ACTIVE_COMPARATOR`,
     `PLACEBO_COMPARATOR`, `SHAM_COMPARATOR` or `NO_INTERVENTION`.
2. **`NON_PRODUCT`** applies if either:
   - its CT.gov `type` is `DIAGNOSTIC_TEST`, `PROCEDURE`, `BEHAVIORAL`, `DEVICE` or `RADIATION`; or
   - its `name`, or the first sentence of its own `description`, contains "imaging agent",
     "radiotracer", "tracer", "contrast agent", "diagnostic" or "PET".
   - These two rules are unchanged from Amendment 5.
3. **`SUPPORT`**: the trial explicitly makes it the **referent** of a support phrase (defined
   below). Its own `name` containing a support term also counts.
4. **`INVESTIGATIONAL`**: the trial explicitly presents it as studied, by one of:
   - **Sole product.** It is the only intervention in the trial left after roles 1–3 are
     assigned.
   - **Arm label.** One of its names appears as a whole word in the label of an `EXPERIMENTAL`
     arm it is linked to.
     - A trailing formulation word may be dropped: cells, cell, injection, product, suspension or
       infusion (Amendment 3).
   - **Investigational wording.** Its own `description` contains "investigational", "study drug"
     or "study product".
5. **`UNKNOWN`**: otherwise. This covers "Given IV", generic arm labels and similar.

Explicit support (3) outranks the arm-label and wording signals (4). A drug named directly in a
support phrase is used as support in that trial, even when an arm label also lists it.

### Support phrases and their referents (structural)

A support phrase can withhold stage only from the intervention it grammatically refers to.

**Where the phrases come from.** The texts read are:
- every intervention `description`;
- every arm-group `description`;
- each intervention's own `name`.

**Clauses.** A text is split into clauses at `,` `;` `:` and at sentence and line boundaries.

**Sequencing connectives.** These relate two events in time: before, prior to, after, following,
follows, followed by, preceded by, post, subsequent to, then, during, until.

**Support phrase.** A support phrase begins at a support term: lymphodepletion, conditioning,
bridging, premedication, supportive care, prophylaxis or rescue. It extends to the end of its
clause, or to the next sequencing connective, whichever comes first.

**Referents.** The referents of a support phrase are:

1. **Forward attachment.** Every intervention named inside the phrase.
   - "conditioning with fludarabine and cyclophosphamide" refers to both drugs.
   - "lymphodepletion regimen comprised of cyclophosphamide" refers to cyclophosphamide.
2. **Backward attachment.** An intervention named in the same clause and joined to the support
   term only by "for" or "as" (within four words) is also a referent.
   - "Cyclophosphamide … for lymphodepletion" refers to cyclophosphamide.
   - "given as conditioning" refers to the intervention named in that clause.
3. **Self-reference.** In an intervention's own `description`, a phrase with no intervention
   named inside it refers to that intervention itself, if both hold:
   - no sequencing connective precedes the support term in its clause; and
   - no other intervention is named in the clause.
   - "Lymphodepletion chemotherapy" and "Chemotherapy for lymphodepletion" are self-references.
   - "administered following lymphodepleting chemotherapy" is not: a connective governs it.
   - "treatment follows a lymphodepletion" is not.
4. **Before-product.** In an intervention's own `description`, the intervention is also a
   referent of its own support if both hold:
   - a clause contains "prior to" or "before" followed by infusion, cells, CAR or transplant; and
   - no other intervention is named before that marker in the clause.
   - Example: "Cyclophosphamide will be given … prior to CAR-T infusion."

Anything named **after** a sequencing connective is never a referent of the phrase before it.

Worked cases:
- "A conditioning chemotherapy regimen of fludarabine and cyclophosphamide may be administered,
  followed by … CD19-TriCAR-T cells" → only fludarabine and cyclophosphamide are referents.
- "Single IV infusion of ALA-101 post chemotherapy conditioning with Fludarabine and
  Cyclophosphamide" → only fludarabine and cyclophosphamide are referents.
- "SC291 with lymphodepleting therapy" → no referent.
- "ALLO-329 without a lymphodepletion regimen" → no referent.

## Step 2: the corpus prior, leave-one-out

- **The corpus.** Every CT.gov trial in the run's discovered set.
- **Drug identity.** A drug is identified by any normalized name of the intervention: its name,
  otherNames, or asset names observed in either.

For a hit on trial *T*, drug *D* is **`SUPPORT_DOMINANT`** at *T* iff both:
- at least **3** trials other than *T* give *D* the local role `SUPPORT`; and
- `SUPPORT / (SUPPORT + INVESTIGATIONAL) ≥ 2/3` over trials other than *T*.

Only `SUPPORT` and `INVESTIGATIONAL` enter the denominator. `CONTROL`, `NON_PRODUCT` and `UNKNOWN`
do not. Trial *T* never contributes to its own prior. When the same drug appears in a trial under
several interventions, that trial counts once, with its most explicit role; `SUPPORT` outranks
`INVESTIGATIONAL`.

## Step 3: the decision per hit

1. **Title-derived hit** (unchanged): `STAGE_FROM_TRIAL_TITLE_SUBJECT`.
2. **Unresolved** (unchanged): `WITHHELD_UNRESOLVED`.
3. Otherwise the hit's local role in this trial decides. If several interventions resolve to the
   hit, the most favourable role is used, in the order INVESTIGATIONAL > UNKNOWN > SUPPORT >
   NON_PRODUCT > CONTROL.
   - `INVESTIGATIONAL` → `STAGE_FROM_EXPLICIT_INVESTIGATIONAL`. This applies even when the drug is
     support-dominant elsewhere; mixed-use drugs keep the trials that study them.
   - `CONTROL` → `WITHHELD_CONTROL_ROLE`.
   - `NON_PRODUCT` → `WITHHELD_NON_PRODUCT`.
   - `SUPPORT` → `WITHHELD_SUPPORT_ROLE`.
   - `UNKNOWN` and support-dominant at *T* → `WITHHELD_SUPPORT_DOMINANT`.
   - `UNKNOWN` otherwise → `STAGE_FROM_STRUCTURED_INTERVENTION`.

**Title handling is as in Amendment 5.** The title never grants or withholds stage. An attributed
claim records `extraction_method = "ctgov_stage:<REASON>"`, with a `+TITLE` suffix when the hit's
intervention is named in `briefTitle` or `officialTitle`.

No drug is named in the rule. The thresholds 3 and 2/3 are fixed here and are not tuned.

## Unit tests required (S4)

One test per reason code, plus:
- **Referent cases.** CD19-TriCAR-T/SILK, ALA-101, CAR-NK-CD19 ("treatment follows a
  lymphodepletion"), SC291, ALLO-329 and TranspoCART19 each keep stage. Their conditioning agents
  are `SUPPORT` where named in the phrase.
- **Leave-one-out.** A drug with exactly 3 explicit-support trials:
  - is not support-dominant at one of those three trials, since only 2 others remain;
  - is support-dominant at a fourth, bare trial.
- **Supermajority.** 3 support and 2 investigational trials give 3/5 < 2/3, so the drug is not
  dominant. 4 support and 2 investigational trials give 4/6 = 2/3, so it is dominant.
- **Mixed use.** A support-dominant drug named in an experimental arm label keeps stage.
- **Carried over.** The Amendment 5 registry cases still pass: DuoCAR, huCART19-IL18 with the
  imaging agent, BMS-986337 with the placebo, CART22-65s + huCART19, R-mini-CHOP/AZD0486, and the
  title annotation.

## Result (appended 2026-09-28): FAILED_ACCEPTANCE — stopping rule invoked

Replays `se_runs/{tac01,mint5}_stage_fix_a6` (code b9c254d, Amendments 6 and 6.1). Per-asset
counts are in `stage_attribution_eval.txt`; scorer output in `ranking_v1_compare.txt`; reasons
recomputed from the sealed snapshots with the run's own leave-one-out index by
`se_runs/tac01_stage_fix/why6.py`.

- **S1: FAIL (narrowly).** Cyclophosphamide 205→7 (3.4%) and Fludarabine 181→5 (2.8%) pass.
  The corpus prior did the work: 94 cyclophosphamide and 76 fludarabine hits were withheld as
  `WITHHELD_SUPPORT_DOMINANT`, and 86 and 84 as explicit support. R-mini-CHOP 1→0 passes.
  **Fludarabine-based keeps 1 of 1** and is #8 in the TAC01 top 20.
- **S2: PASS.** Every control keeps stage: axi-cel 20→15, tisa-cel 8→6, liso-cel 10→9,
  brexu-cel 7→6, CC-97540 7→6, KITE-753 1→1. All eight mint5 controls keep at least one;
  FKC289 3→2, CNCT19 6→5 and ICG318 3→2 are reduced.
- **S3: FAIL.** 163 TAC01 assets and 130 mint5 assets lose all stage. Amendment 5's three
  stripped products now keep stage (CAR-NK-CD19 Cells, CD19-TriCAR-T/SILK, ALA-101), but new real
  programs are stripped as `WITHHELD_SUPPORT_ROLE`. The forward-referent rule reads sponsor prose
  that runs past the support phrase:
  - **Coordination after the support term, with no connective:**
    - TranspoCART19: "followed by lymphodepleting chemotherapy and administration of
      TranspoCART19".
    - KITE-363: "lymphodepleting chemotherapy with cyclophosphamide and fludarabine followed
      Phase 1ab recommended dose of KITE-363" (the text says "followed", not "followed by").
    - Cilta-cel / JNJ-68284528 (mint5, NCT05257083): the conditioning-regimen sentence of the
      experimental arm.
  - **Before-product self-reference on a product description that names unregistered
    chemotherapy:**
    - pCAR-19B cells: "Subjects treated with Fludarabine and Cyclophosphamide before cell
      infusion."
    - CD19/CD20 Dual-CAR-T cells: "5 days prior to infusion of CAR-T cells, subjects receive
      fludarabine …".
  - **Missing sentence spacing** merges clauses: BCT301, "…CAR-iT cells.Participants … Prior to
    infusion, patients undergo a lymphodepleting conditioning …".
  - Also stripped: JCAR015, RN1201, BLB101, BC19, CAR2219. These were not individually
    diagnosed.
- **S4: PASS.** 25 unit tests; full S&E suite 1514 passed, 3 xfailed.
- **S5: PASS.** R1–R3 PASS on both runs. TAC01 is at #77.

**Decision: FAILED_ACCEPTANCE.** b9c254d is not adopted.

**Conclusion, per the stopping rule agreed before this amendment.** Across six amendments,
every rule that reads CT.gov prose to decide an intervention's role either strips real programs
or restores conditioning agents; fixing one class of sponsor phrasing exposes another. The
corpus prior is the one component that worked as designed: it separates conditioning agents from
products across trials. What fails is the per-trial prose reading that feeds it. Reliable
intervention-level stage attribution needs an explicit regimen/role model — structured roles
per intervention, not inferred from free text. It cannot come from CT.gov prose heuristics
alone. Iteration on prose heuristics stops here.
