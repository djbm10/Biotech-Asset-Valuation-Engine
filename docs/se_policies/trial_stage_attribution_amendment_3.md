# Amendment 3: an arm label may name a product without its formulation word

Status: **FROZEN**, 2026-09-27, written after the unit tests and before any replay or
measurement. It amends Amendment 2, rule 5, `STAGE_FROM_ARM_LABEL`, only.

## Why

Amendment 2 lists huCART19 (NCT03620058) as a co-investigated product that its arm label
names. The arm label is "CART22-65s in combination with huCART19", but the intervention is
named "huCART19 Cells". None of rule 5's name channels yields "huCART19":
`extract_observed_asset_names("huCART19 Cells")` returns nothing. So the rule as frozen does not
reach a case the amendment says it fixes. The first unit-test run found this.

## Change

For `STAGE_FROM_ARM_LABEL` matching only, each intervention name also counts with one trailing
generic formulation word removed. The words are: cells, cell, injection, product, suspension,
infusion. The stripped form must be at least 3 characters and match the label as a whole
normalized word, as before.

Nothing else changes. In particular:
- identity resolution (rule 2) does not use the stripped form;
- support detection (rule 3) does not use it;
- title corroboration does not use it.
