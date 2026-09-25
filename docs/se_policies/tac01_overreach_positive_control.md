# TAC01-CD19 — class-term over-reach positive control

Status: **PREREGISTERED** 2026-09-24. Parent commit: `cc1bde7`.
Companion to `class_terms_v5.md`. Written and committed **before** the run.

## 1. Why this exists, and what it is not

v5 passed its seven criteria, and the operator has **adopted** v4 + A3 + v5. This control is
therefore *not* a gate on adoption. The operator's ruling, verbatim: *"do one targeted
positive-control validation, but do not hold v5 adoption hostage to it … Treat the targeted TAC01
check as a post-adoption validation of recall, analogous to the A3 check — not another opportunity to
tune v5."*

It answers one question: **does the class-term veto demote a named asset whose only individuating
token is a sponsor stem?** `TAC01-CD19` is the designated canary because it is a CD19-directed cell
therapy whose name is `sponsor-stem + target designation` — the shape a rule that over-reaches takes
first. It was absent from both `mint5` arms, so v5's most informative recall control never fired.

## 2. The instance under test

`TAC01-CD19` (Triumvira Immunologics, autologous TAC T cells). Sole occurrence in the corpus:

| field | value |
|---|---|
| trial | `NCT03880279`, *Autologous TAC T Cells Targeting CD19 in R/R Large B-Cell Lymphoma* |
| sponsor | Triumvira Immunologics, Inc. (`INDUSTRY`) |
| condition | Lymphoma, B-Cell |
| intervention | `BIOLOGICAL: TAC01-CD19`, no `otherNames` |
| arm | `EXPERIMENTAL` / `TAC01-CD19` |
| phase / status | Phase 1/2, **WITHDRAWN** |

This is an oncology record. That, not a defect, is why an `AUTOIMMUNE` acceptance query did not reach
it. Under the rule as implemented, `individuating_residue("TAC01-CD19") == ("TAC01",)` and
`is_class_term` is `False`, so the *predicted* outcome is retention; this control tests that
prediction end-to-end on live evidence rather than in a unit test.

## 3. Design — one arm, and why that is sufficient

Single live run at the adopted commit. **No fix-off control arm**, for a stated reason rather than
for convenience: the v5 veto is *monotone in the removing direction* — it can only refuse names that
would otherwise qualify, never admit ones that would not. So if `TAC01-CD19` appears on the default
path with v5 **on**, over-reach demonstrably did not occur, and an off arm could only confirm a
standing that is already implied. A3 needed a paired arm because A3 *narrows a veto*, i.e. its effect
is to retain; the question there was whether the thing it retains would otherwise be lost.

Query, naming neither the asset, its sponsor, nor its `TAC` modality:

```
Find clinical-stage CD19-directed cell therapies for relapsed or refractory large B-cell lymphoma.
```

`--as-of 2026-09-24`, `--therapeutic-area ONCOLOGY`, the same `source_index.yaml` as the mint pairs,
`--format shortlist --allow-incomplete`. No phase or status term appears in the query, deliberately:
the record is `WITHDRAWN`, and a stage/intent gate firing on it would confound an identity question
with a status question.

## 4. Preregistered expected result

1. `TAC01-CD19` is present as a candidate and is **on the default path**, with a named
   `qualification_reason`.
2. Plain class descriptors in the same run (`CD19 CAR-T cells`, `CAR-T`, `anti-CD19 CAR-T` and the
   like) are **in review** — the rule is still doing its job in this corpus, so retention of
   `TAC01-CD19` is discriminating rather than a rule that quietly failed to run.
3. No frozen v4/v5 negative reaches the default path.

## 5. Pass / fail

**PASS** requires (1) and (2). (2) is load-bearing exactly as §5(1) was for A3: if *no* class term is
demoted in this run, the veto did not fire at all and `TAC01-CD19`'s survival proves nothing — that
is reported as **inconclusive**, not as a pass.

**FAIL** if `TAC01-CD19` is demoted to review. Per the operator, that outcome — and only that
outcome — reopens v5: *"Do not start another general identity milestone unless that TAC01 test
actually shows a named asset being demoted."*

If `TAC01-CD19` is absent from the run entirely, the finding is that the **query** failed to reach it,
not that v5 passed. Report and stop; do not iterate on the query to manufacture an exercise.

## 6. Out of scope

- **No carve-outs.** The operator ruled on the B1.2 disputed 20: *"do not add carve-outs … Without a
  sponsor code, proper asset name, trial-linked identifier, or other individuating residue,
  review/class-term treatment is appropriate."* That question is closed, not deferred.
- No change to v4, A3, v5, fragmentation, or any threshold.
- The `CD19-CAR-DNT` → `NT5C` mis-resolution is a separate **ontology ambiguity**, logged as such. Per
  the operator it *"should not motivate a class-term exception."*
- No ranking work inside this control. Ranking is the next arc, after this reports.
