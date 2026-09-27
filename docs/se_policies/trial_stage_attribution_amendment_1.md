# Amendment 1: rule 4 reads the experimental arm, not the therapeutic reading

Status: **FROZEN**, 2026-09-27, written before any replay or measurement. Amends
`trial_stage_attribution.md`.

## Why

Rule 4 said "being in an experimental arm is necessary" but implemented that as "the existing
`_arm_relationships` reading is therapeutic". That reading counts `ACTIVE_COMPARATOR` as
therapeutic (`_THERAPEUTIC_ARM_TYPES`), because for identity an active comparator is a real
drug. For stage it is the control. The S4 unit test for a comparator-arm drug (R-GDP in an
`ACTIVE_COMPARATOR` arm, named in "... versus R-GDP") was attributed
`STAGE_FROM_TITLED_INTERVENTION`, so the rule contradicted its own sentence. This was found by
the first unit-test run, before any code shipped.

## Change

Rule 4 becomes: the trial has more than one intervention, and the intervention either
- is not linked to any `EXPERIMENTAL` arm (through `armGroups[].interventionNames` or
  `interventions[].armGroupLabels`); or
- has an `_arm_relationships` reading other than therapeutic (this keeps the
  sole-occupant-of-a-control-arm and self-contradiction protections).

Either one withholds: `WITHHELD_NOT_EXPERIMENTAL`. Everything else in the policy, S1–S5 and the
decision rule are unchanged.
