# Amendment 2: title is corroboration, support is a clause relation, co-products are studied

Status: **FROZEN**, 2026-09-27, written before any code change. It amends
`trial_stage_attribution.md` and its Amendment 1. The code that failed acceptance (73665a5) was
reverted in 409cbb7.

The criteria S1–S5, the positive controls, the replay commands, the output directories and the
decision rule are unchanged. The new output directories are
`se_runs/{tac01,mint5}_stage_fix_a2`.

## What failed and why (from the recorded result)

1. **Title evidence included backbones.** R-mini-CHOP was attributed through
   `STAGE_FROM_TITLED_INTERVENTION`. The registry records it as follows (NCT07215585):
   - it is in the experimental arm with AZD0486;
   - it is the only intervention of the `ACTIVE_COMPARATOR` arm.
2. **The support test did not ask what the support clause is about.**
   - "A conditioning therapy with cyclophosphamide and fludarabine will be conducted before
     CD19-UCART injection" stripped CD19-UCART, which is the reference point of that clause, not
     its agent.
   - The same happened to YTB323 ("receive lymphodepleting chemotherapy, followed by … YTB323")
     and to JWCAR029 ("During JWCAR029 production, subjects will receive a conditioning …").
3. **Co-investigated products were treated as ambiguous.** In each of these trials the registry
   names each product in its own experimental arm's label:
   - KYMRIAH, YESCARTA, Tecartus and Breyanzi (NCT03642626);
   - SCRI-huCAR19v1 and SCRI-huCAR19v2 (NCT03684889);
   - huCART19 (NCT03620058, arm "CART22-65s in combination with huCART19").

## The rule, as amended

Decided per hit, in this order. The first rule that applies decides.

1. **Title-derived hit** (unchanged): `STAGE_FROM_TRIAL_TITLE_SUBJECT`.
   - Here the title is the hit's own name. Discovery found no intervention to name the hit
     after, so this is not title evidence about an intervention, and Change A does not reach it.
2. **Unresolved** (unchanged): `WITHHELD_UNRESOLVED`.
3. **Support role, clause-aware** (replaces rule 3): `WITHHELD_SUPPORT_ROLE`.
   - The intervention's own `name` contains a support term. This part is unchanged.
   - Or the intervention is the **agent** of a support clause. The rule reads every intervention
     `description` and every arm-group `description` of the trial, not only the intervention's
     own.
   - **Clause.** A sentence is split into clauses at `,` `;` and `:`.
   - **Support clause.** A clause is a support clause if either:
     - it contains a support term (lymphodepletion, conditioning, bridging, premedication,
       supportive care, prophylaxis, rescue); or
     - it contains "prior to" or "before" followed by an infusion, a cell product, a CAR or a
       transplant.
   - **Agent.** A name in a support clause is its agent unless it is the **reference point**.
   - **Reference point.** The name is preceded, within the same clause, by a temporal marker:
     "before", "prior to", "after", "following", "followed by", "then", "during", "until".
   - Consequences:
     - "conditioning … before CD19-UCART injection" makes cyclophosphamide and fludarabine the
       agents and CD19-UCART the reference point.
     - "Prior to cellular infusion, patients receive lymphodepletion with fludarabine" marks
       fludarabine as the agent, even though the sentence is in the CAR-T's description.
4. **Not the variable under study** (extends Amendment 1): `WITHHELD_NOT_EXPERIMENTAL`. This
   applies when the trial has more than one intervention and any of these holds:
   - the intervention is not linked to an `EXPERIMENTAL` arm (Amendment 1);
   - its `_arm_relationships` reading is not therapeutic (Amendment 1);
   - **new:** it is linked to any arm typed `ACTIVE_COMPARATOR`, `PLACEBO_COMPARATOR`,
     `SHAM_COMPARATOR` or `NO_INTERVENTION`. An agent given in the control arm is shared
     background, not what the trial varies.
   - Linkage uses both CT.gov directions throughout.
5. **Evidence of investigation** (replaces rule 5). Stage is attributed on the first of:
   - `STAGE_FROM_SOLE_INTERVENTION`: the trial has exactly one intervention.
   - `STAGE_FROM_SOLE_PRODUCT`: it is the only intervention left after rules 3–4 in the trial.
     That is, every other intervention is support, not experimental, or control background.
   - `STAGE_FROM_ARM_LABEL`: one of its names (name, otherNames, or an asset name observed in
     either) appears as a whole word, normalized, in the label of an `EXPERIMENTAL` arm it is
     linked to. The registry presents it as what that arm studies.
6. **Otherwise** withheld: `WITHHELD_AMBIGUOUS_PARTNER` (unchanged).

**Change A: title is corroboration only.** `STAGE_FROM_TITLED_INTERVENTION` is removed. A title
match never grants stage. When an attributed intervention is also named in `briefTitle` or
`officialTitle`, its claim records that fact as `extraction_method =
"ctgov_stage:<REASON>+TITLE"`. The title can annotate a grant but can never make one.

No drug is named in the rule. NKTR-255 is named in the label of its only experimental arm
("Treatment (CD19/CD22 CAR T cells, chemotherapy, NKTR-255)"). It is attributed by rule 5 as
written, and that is reported, not corrected.

## Unit tests required (S4)

S4 requires one test per reason code. The prior cases carry over as follows:
- **Kept:** the CAR-T lymphodepletion description, and a comparator-arm drug withheld.
- **Replaced:** the prior `STAGE_FROM_TITLED_INTERVENTION` test becomes a test that a titled
  backbone in the comparator arm is withheld.

New cases:
- the CD19-UCART, YTB323 and JWCAR029 sentences keep the product;
- a basket trial with one product named per arm label attributes each product and withholds
  the conditioning agents;
- the R-mini-CHOP arm structure withholds R-mini-CHOP and attributes AZD0486.
