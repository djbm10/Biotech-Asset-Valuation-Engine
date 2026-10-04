# RANKING_LEXICOGRAPHIC v2 — declared-constraint-first (preregistration)

**Status:** PREREGISTERED 2026-10-04. No implementation exists.
**Predecessor:** `ranking_lexicographic_v1.md` plus amendment 1 (query-modality match,
`authority_modality_v1.md`).
**Decision:** the operator chose Option A on 2026-10-04. Evidence rules are untouched.

## 1. Principle

When a query explicitly declares a therapeutic target, confirmed satisfaction of that
constraint ranks before downstream evidence strength. A target-UNKNOWN asset must not
outrank a target-PASS asset only because it has stronger efficacy or stage evidence.

## 2. Order (frozen)

The key is conditional on whether the problem declares targets, meaning
`strategic_gap.target_expression.targets` is non-empty.

| # | Target declared (v2) | No target declared (unchanged v1 + amendment 1) |
|---|---|---|
| 1 | eligibility | eligibility |
| 2 | declared-modality match (MATCH < UNKNOWN < MISMATCH; ties when undeclared) | same |
| 3 | **target decision: PASS < UNKNOWN < no decision** | human efficacy |
| 4 | human efficacy | maturity |
| 5 | maturity | target decision |
| 6 | target-assertion precedence | target-assertion precedence |
| 7 | evidence completeness | evidence completeness |
| 8 | name, then id | name, then id |

**FAIL rows.** A target-FAIL asset is EXCLUDED, and an excluded asset is never visible
(v1). A FAIL therefore cannot outrank an UNKNOWN. The key keeps v1's `_DECISION_PRECEDENCE`
values unchanged.

**What does not change:**
- the shortlist population (visibility, low-support deferral, exclusion);
- every fact, gate and qualification;
- the pairwise-rank supersession.

## 3. Measurement

Ranking is a pure function of a run's `result.json`, so the benchmarks are scored
**offline**. The scorer builds `build_shortlist` from the frozen `*_qual_v7` results. No
pipeline replay is needed for TAC01 or mint5.

**Target-free control.** No sealed run in `~/se_runs` lacks a declared target. That was
checked over all 73 `problem.yaml` files. The control is therefore a new run, made in the
operator's terminal.

- **Query:** "Find clinical-stage cell therapies for relapsed or refractory B-cell lymphoma."
- **Parser check, done now:** modality CELL_THERAPY, no targets. The disease words stay as
  residual free text.
- **Measurement:** build the control run's shortlist under the v1 key and under the v2 key.
  The two must be identical.

## 4. Baseline readout (v1 order on `*_qual_v7`), judged NOW, before any v2 order exists

The rubric is v1's, unchanged:
- **RELEVANT:** TAC01, a CD19-directed cell therapy; mint5, a CD19- and/or BCMA-directed
  therapy studied in autoimmune disease.
- **DUPLICATE**, **NON_ASSET**, **OFF_TARGET:** as defined in v1.
- **UNVERIFIED** (added): the programme's target cannot be verified from the run's evidence
  or from established public knowledge. It is counted as **not** RELEVANT.

### TAC01 v1 top 20: RELEVANT 16, OFF_TARGET 4. K1 PASS.

**RELEVANT:**
- brexu-cel, axi-cel, liso-cel, tisa-cel
- CC-97540, cema-cel, prizlon-cel, anbal-cel, varnim-cel
- rese-cel, TAK-007, CNCT19, KITE-753
- 7×19-THEMIS CAR-T, ALLO-501A, Allogeneic CD19-STAR T

**OFF_TARGET:** tabelecleucel, lifileucel, satri-cel, NKTR-255.

### mint5 v1 top 20: RELEVANT 8, DUPLICATE 1, OFF_TARGET 2, NON_ASSET 1, UNVERIFIED 8. K2 FAIL.

| Category | Rows |
|---|---|
| RELEVANT | AZD0120, FKC289, umbilical cord blood CD19-BCMA CAR-T, CD19-BCMA dual nanobody CAR-T, budoprutug, CM336, IMPT-514, inaticabtagene |
| DUPLICATE | GC012F (≡ AZD0120) |
| OFF_TARGET | mezigdomide, AT-007 |
| NON_ASSET | busulfan, a conditioning agent, at #20 |
| UNVERIFIED | ICG318, BC19, BH2024, CD19CART, CRT-402, FT839, INCA000585, QEL-005 |

## 5. Acceptance (frozen)

- **G1.** The population is unchanged. Each benchmark's set of visible and deferred asset
  ids, and every fact, are identical under v1 and v2. This holds by construction and is
  verified anyway.
- **G2 (target-free).** The control run's v1 and v2 orders are identical, in full.
- **G3.** Every order change is explained solely by the key reorder. Mechanically: no pair
  of assets with equal target decision changes relative order.
- **G4 (K1).** All four approved CD19 products stay in the TAC01 top 20, and RELEVANT is
  at least 16 (no regression from §4).
- **G5 (K2).** mint5 RELEVANT in the top 20 is at least 8 (no regression from §4), and no
  NON_ASSET is in the top 5.
- **G6.** No conditioning or regimen NON_ASSET is in either top 20, beyond the baseline's one
  (busulfan). Any NON_ASSET entering is a failure.
- **G7.** Determinism: two builds per benchmark are identical.
- **G8.** `tests/se` and ruff pass, including the updated v1 conformance tests.

**Judging rule.** v2 top-20 rows are judged with the §4 rubric. A row already judged in §4
keeps its §4 label; that label is frozen. Only rows that are new to a top 20 are judged
fresh, and UNVERIFIED counts as not RELEVANT.

## 6. Stop condition

- **Adopt** only if G1–G8 all pass.
- **Otherwise** record the failure and revert. Do not tune the key, and do not change any
  evidence rule.

## 7. Pre-measurement disclosure — 2026-10-04, before any v2 order was computed

The §3 target-free control **cannot be executed**:
- `compile_intent` refuses the control query with `IntentNotCompilable: no biological target
  recognized in the query`;
- `BuyerProblem.strategic_gap.target_expression` is a required field, with
  `targets` `min_length=1`.

Every query the engine can run therefore declares a target, and the v1 branch of the key is
unreachable in production today. G2 is consequently **vacuous**. It is re-stated as a unit
test, `tests/se/test_ranking_v2.py`: under `target_declared=False` the key is element-for-
element the v1 + amendment 1 key.

No criterion is relaxed. The control simply has no population. The unreachability is
recorded as a product limitation: target-free search is not supported. I did not add a
target-free path, because that would change query semantics and is out of scope.

## 8. Result — 2026-10-04 (offline, on frozen `*_qual_v7` results)

**Scorer:** `scripts/score_ranking_v2.py` → `research/se_ranking_v2/score_v2.txt`.

| Criterion | Result |
|---|---|
| **G1** | **PASS.** Visible and deferred asset sets are identical under v1 and v2: 553 TAC01, 245 mint5. No fact is touched, because ranking reads `result.json` only. |
| **G2** | **VACUOUS**, per §7. Unit test `test_undeclared_key_is_v1_element_for_element` passes. |
| **G3** | **PASS.** No pair of assets with the same target decision changed relative order, in either benchmark. |
| **G4 (K1)** | **PASS.** All four approved CD19 products are in the TAC01 top 20, and RELEVANT is 17 (baseline 16). Change: NKTR-255 (OFF_TARGET, target UNKNOWN) left, and *Allogenic CD19-CAR-γδT cell* (new, judged RELEVANT) entered at #20. The UNKNOWN cell therapies at #10–14 stay above the PASS rows CNCT19 and KITE-753 (#15–16), because modality MATCH precedes target under the frozen order. That is not a defect of v2. |
| **G5 (K2)** | **PASS.** See the mint5 tally below. No NON_ASSET is in the top 5. |
| **G6** | **PASS.** No NON_ASSET is in either top 20; busulfan left. |
| **G7** | **PASS.** Two builds per benchmark are identical. |
| **G8** | **PASS.** `tests/se` 1588 passed, 3 xfailed. Ruff is clean. |

**mint5 top 20 under v2:** RELEVANT 16, DUPLICATE 2, UNVERIFIED 2, OFF_TARGET 0, NON_ASSET 0.

- **Rows carried over from §4, labels frozen:**
  - AZD0120, FKC289, umbilical cord blood CD19-BCMA CAR-T and CD19-BCMA dual nanobody CAR-T
    (RELEVANT);
  - GC012F (DUPLICATE).
- **New rows**, each verified against its construct fact (CD19 + TNFRSF17) and its
  therapeutic-area gate (PASS, autoimmune arm):
  - **RELEVANT:** Allogeneic CD19/BCMA CAR-γδT, allogenic anti-CD19/BCMA CAR-T (RD06-05),
    anti-CD19/BCMA U CAR-T (KN3601 arm), BCMA-CD19 cCAR (C174412), CD19-BCMA Targeted CAR-T
    Dose 1, CD19/BCMA in vivo CAR-T, CD19/BCMA Lupus Nephritis Targeted CAR-T,
    FIT-(BCMA+CD19)-CAR-T, KN5601 (CAR-NK), KSVCBD (in vivo CAR-T), KT501, PRG-2311.
  - **DUPLICATE:** CD19-BCMA Targeted CAR-T Dose 2, the same programme as Dose 1.
  - **UNVERIFIED, counted as not RELEVANT:**
    - "allogeneic umbilical cord blood-derived CAR-T targeting CD19 and BCMA" may be the
      same programme as the #4 cord-blood row;
    - "Assigned Interventions CD19/BCMA CAR T-cells" is an unnamed arm label and may be the
      same programme as the Lupus Nephritis row.

**Known residuals, recorded but not acted on:** the DUPLICATE and UNVERIFIED rows are
identity-merge misses for unnamed arm-label constructs. That is a population/identity
defect, not an ordering one.

**Status: ADOPTED.** No new replays are needed. The next run of any query uses v2.
