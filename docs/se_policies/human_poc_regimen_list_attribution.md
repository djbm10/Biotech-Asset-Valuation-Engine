# Human-PoC: a regimen list item does not own the regimen's result

Status: **FROZEN**, 2026-09-27, written before any code change. This is the first population
milestone promoted by `ranking_lexicographic_v1.md` (K1 failed on population defects).
Ranking v1 is unchanged by this milestone.

## The defect

`efficacy_statements` (`evidence/human_poc.py`) credits a sentence's efficacy result to a
named asset unless a joining word ("plus", "and", "with", ...) sits directly next to the name.
A comma is not a joining word, so a drug listed inside a regimen owns the regimen's result:

- "...not cured with first-line R-CHOP (rituximab, cyclophosphamide, doxorubicin, vincristine,
  and prednisone or prednisolone)." credits cyclophosphamide, vincristine, prednisone and
  prednisolone.
- "...followed by fludarabine, cyclophosphamide, and rituximab (FCR) at 96.6%" credits
  cyclophosphamide.
- "...daratumumab plus bortezomib, lenalidomide, and dexamethasone (DVRd) versus VRd" credits
  lenalidomide.

Human efficacy is ranking v1's second key, so these credits put conditioning and chemotherapy
agents above approved CD19 CAR-Ts in TAC01 (ranks 1, 2 and 5).

## The rule

A name that is one item of a comma-delimited list is not credited with the sentence's result.
The name is a **list item** when all of the following hold:

1. **Bare segment.** The text between the nearest delimiters on either side of the name
   (`,` `(` `)` or the sentence edge) is the name alone, optionally preceded by `and` or `or`.
2. **Comma-adjacent.** A comma is one of those two delimiters.
3. **A list, not an apposition.** The comma-delimited run containing the name either sits
   inside parentheses, or has a later item starting with `and` / `or` (serial coordination).
4. **At least three items** in that run, counting the segments on each side of the run.

What this does not change:

- The existing joining-word and other-asset guards, the eligibility, safety, non-human and
  sentence-length exclusions.
- The structured clinical-result route.
- A name matched as a whole combination product ("CD19/BCMA dual CAR-T") keeps its result.
- An asset named once in a sentence with a comma clause ("In patients treated with axi-cel, the
  ORR was 83%") keeps its result: its segment is not bare.
- `CCL19` (a biomarker gene read as an asset) is out of scope. It is a separate non-asset
  extraction defect.

## Evaluation

The change only removes efficacy statements. It cannot add one. So on the accepted runs
(`tac01_ind_fix`, `mint5_ind_fix`) its effect is measured **offline and exactly** by applying the
new predicate to every `human_poc_present` claim of method `reported_efficacy_sentence`, and
keeping a fact only while one of its claims survives.

- TAC01 has no human-PoC requirement, so ranking reads the fact directly. The TAC01 shortlist is
  rebuilt from the derived result and re-scored with the frozen ranking v1 scorer.
- mint5 requires human PoC, so its `evidence.human_poc` gate decisions would change. Its claim
  removals are reported here; its ranking is re-scored only after a replay.

### Criteria (all must PASS)

- **H1 — negative controls lose the credit.** In both runs, every claim whose passage is one of
  the three regimen sentences above is removed. In TAC01, cyclophosphamide, vincristine and
  lenalidomide no longer hold a `human_poc_present` fact.
- **H2 — positive controls keep it.** These keep a `human_poc_present` fact:
  - TAC01: Brexucabtagene Autoleucel, CNCT19, Blinatumomab, Glofitamab.
  - mint5: ICG318, Idecabtagene Vicleucel, teclistamab, Talquetamab, elranatamab, Cevostamab,
    Glofitamab.
- **H3 — no valid PASS lost.** Every removed claim is listed and judged by hand. Zero removed
  claims may be sentences that attribute an outcome to that asset individually.
- **H4 — unit tests.** Cover `A, B, and C`; a parenthetical regimen expansion; an apposition
  (`the product, ABC-123, achieved ...`) which is kept; a single-agent comma clause which is
  kept; and a combination product name which is kept. The existing human-PoC suites stay green.

### Reported, not criteria

- TAC01 top 20 under the frozen ranking v1 scorer, judged with the frozen K1 rubric.
  K1 is **not** expected to pass from this milestone alone. The trial-stage attribution and
  duplicate-merge milestones follow.

### Decision rule, fixed now

- If H1–H4 pass, the rule is adopted.
- If H3 finds a valid PASS removed, the rule is FAILED_ACCEPTANCE and a revision needs an
  amendment. The rule is not loosened to rescue a K1 count.

## Result (appended 2026-09-27)

Measured offline as declared. Derived TAC01 result and scorer output:
`/home/djmann/se_runs/tac01_regimen_offline/`.

### Removed claims (all of them)

| run | asset | sentence | hand judgement |
|---|---|---|---|
| both | Cyclophosphamide, vincristine, rituximab | R-CHOP expansion | regimen, not individual |
| TAC01 | Cyclophosphamide | FCR | regimen, not individual |
| TAC01 | lenalidomide | DVRd | regimen, not individual |
| both | abatacept | "responsiveness ... to previously failed drugs (Janus kinase inhibitors, abatacept, tumour necrosis factor inhibitors) observed in 7 of 15 patients" | a list of drug classes regained after CAR-T; not a result for abatacept alone |
| TAC01 | CCL19 | biomarker gene list in a prognostic score | not an asset; removed incidentally, the CCL19 extraction defect stays open |

Facts lost: TAC01 cyclophosphamide, vincristine, lenalidomide, abatacept, CCL19;
mint5 cyclophosphamide, vincristine, abatacept. Rituximab keeps its fact in both runs through
other claims.

### Criteria

- **H1 — FAIL as written.** The three named TAC01 drugs lose their fact. But the R-CHOP
  sentence's `prednisone` and `Prednisolone` claims are **not** removed. Their segment is
  "and prednisone or prednisolone", which is two names, so rule 1 (bare segment) excludes it.
  The frozen rule and H1 contradict each other on that one segment. That is a preregistration
  error, recorded here, and it is not fixed silently. A final `A or B` alternative item needs an
  amendment.
- **H2 — PASS.** Every positive control in both runs keeps its fact.
- **H3 — PASS.** No removed claim attributes an outcome to the asset individually (table above).
- **H4 — PASS.** `tests/se/test_human_poc_regimen_lists.py`. One existing test
  (`test_human_poc_safety_context.py::test_flared_is_not_caught_by_flare_reaction`) used the
  abatacept sentence above as its fixture for a *flare* rule. Its sentence now names abatacept
  alone; what it tests (flared is not a flare reaction) is unchanged.

### TAC01 re-score (reported, not a criterion)

R1–R3 PASS (683 ranked). Top 20 under the frozen K1 rubric:

| # | row | judgement |
|---|---|---|
| 1 | Brexucabtagene Autoleucel | RELEVANT |
| 2 | CNCT19 | RELEVANT |
| 3 | Axicabtagene Ciloleucel | RELEVANT |
| 4 | Lisocabtagene Maraleucel | RELEVANT |
| 5 | Loncastuximab Tesirine | OFF_TARGET (CD19 ADC) |
| 6 | Tafasitamab | OFF_TARGET (CD19 mAb) |
| 7 | Tisagenlecleucel | RELEVANT |
| 8 | Cyclophosphamide | NON_ASSET |
| 9 | Fludarabine | NON_ASSET |
| 10 | CC-97540 | RELEVANT |
| 11 | Fludarabine-based | NON_ASSET |
| 12 | KITE-753 | RELEVANT |
| 13 | lenalidomide | NON_ASSET |
| 14 | NKTR-255 | NON_ASSET |
| 15 | R-mini-CHOP | NON_ASSET |
| 16 | denintuzumab mafodotin | OFF_TARGET (CD19 ADC) |
| 17 | KTE-C19 | DUPLICATE of axi-cel |
| 18 | KTE-X19 | DUPLICATE of brexu-cel |
| 19 | MEDI-551 | OFF_TARGET (inebilizumab, CD19 mAb) |
| 20 | SAR3419 | OFF_TARGET (coltuximab ravtansine, CD19 ADC) |

Tally: RELEVANT 7, NON_ASSET 6, DUPLICATE 2, OFF_TARGET 5. K1 still fails, as expected.

- The four approved CAR-Ts are now ranks 1, 3, 4 and 7 (were 3, 7, 8, 11). No chemo agent is
  above them.
- The six NON_ASSET rows left all rank on **trial-stage** facts: the next milestone.
- New observation: OFF_TARGET is now 5 of 20. They are CD19 antibodies and ADCs. The question
  asks for cell therapies, and ranking v1 has no modality key. This is not a population defect,
  so it counts against the order under the ranking v1 decision rule once the population
  milestones are done. It is recorded now so it is not discovered later as a surprise.

### Decision

H2–H4 pass and H1 fails only on the preregistration's own contradiction (prednisone/
prednisolone). The rule is **not adopted yet**. It needs Amendment 1 to state how a final
`A or B` item is treated, then it is re-measured.

**Superseded 2026-09-27:** adopted with `human_poc_regimen_list_attribution_amendment_1.md`.
