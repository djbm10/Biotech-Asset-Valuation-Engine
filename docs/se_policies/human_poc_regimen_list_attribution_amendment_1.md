# Amendment 1: a list item may be a set of alternatives

Status: **FROZEN**, 2026-09-27, written before any code change. Amends
`human_poc_regimen_list_attribution.md`, whose first measurement failed H1 on its own wording.

## Why

The R-CHOP expansion ends "..., and prednisone or prednisolone)". Rule 1 (bare segment)
required the segment to be the name alone, so the two-name alternative item was never a list
item, and prednisone and prednisolone kept the regimen's result. H1 named that sentence, so the
rule and its criterion contradicted each other.

## Change

Rule 1 becomes: the segment, after an optional leading `and` / `or`, is either the name alone or
a set of alternatives joined by ` or `, one of which is the name alone.

Rules 2–4, H2–H4 and the decision rule are unchanged. Rule 3's serial-coordination test is
unchanged too: a segment beginning with `and` or `or` still marks the run as a list.

## Re-measurement

Same offline method, same runs, same criteria. H1 additionally requires the R-CHOP sentence's
`prednisone` and `Prednisolone` claims to be removed in both runs. The derived TAC01 result is
rebuilt and re-scored with the frozen ranking v1 scorer.

## Result (appended 2026-09-27)

- **H1 — PASS.** Every claim on the R-CHOP, FCR and DVRd sentences is removed (mint5 holds
  only the R-CHOP sentence), now including `prednisone` and `Prednisolone` in both runs. TAC01 cyclophosphamide, vincristine and
  lenalidomide hold no `human_poc_present` fact.
- **H2 — PASS.** Every positive control keeps its fact in both runs.
- **H3 — PASS.** The only new removals are prednisone and Prednisolone on the R-CHOP
  expansion: a regimen, not an individual result.
- **H4 — PASS.** `test_a_final_item_of_alternatives` added; human-PoC suites green (110).

TAC01 re-score (`/home/djmann/se_runs/tac01_regimen_offline/`): R1–R3 PASS, and the top 20 is
identical to the first measurement (neither steroid was in it). Tally unchanged: RELEVANT 7,
NON_ASSET 6, DUPLICATE 2, OFF_TARGET 5. K1 still fails, as expected.

**Decision: the rule with Amendment 1 is ADOPTED.** Next milestone: trial-stage attribution.
The modality observation (CD19 antibodies and ADCs at OFF_TARGET) stays logged, and no ranking
key is added until the population milestones are done.
