# A3 symmetry — targeted positive control

Status: **PREREGISTERED** 2026-09-24. Parent commit: `c98830e` (the v4 implementation).
Companion to `asset_qualification_evidence_subjects_v4.md` §8 (Amendment A3).

Written and committed **before** the A3-off control variant exists and before either run.

## 1. Why this exists

v4 passed its six criteria on the `mint4_on`/`mint4_off` pair, but **Amendment A3 was never
exercised** by that pair: `Descartes-08` is BCMA-only and absent from both runs, because the
acceptance query asks for *dual* CD19/BCMA therapies. A3 was measured only against the sealed CT.gov
snapshots by a standalone script. The operator's ruling is that A3 must not be treated as
production-proven on that basis.

This is therefore not an acceptance test of v4. It is a single targeted positive control answering
one question end-to-end: **does A3 protect a real asset that the asymmetric reading deletes?**

## 2. The instance under test

`Descartes-08` (Cartesian Therapeutics, autologous mRNA anti-BCMA CAR-T). In `NCT04146051`
(*Descartes-08 CAR-T Cells in Generalized Myasthenia Gravis*) the sponsor declares:

| arm type | label | interventions |
|---|---|---|
| `EXPERIMENTAL` | Phase 1b Dose-Escalation | `Drug: Descartes-08` |
| `EXPERIMENTAL` | Phase IIa Expansion | `Drug: Descartes-08` |
| `PLACEBO_COMPARATOR` | Phase IIb Randomized Control Trial | `Drug: Descartes-08` |

The third arm is named for its *design*, not its material. Descartes-08 is the sole occupant of a
control arm — the asymmetric §3a(1) reading of intervention-specificity — while also being the sole
occupant of two therapeutic arms in the same record. A3 says dominance does not fire on a record
that speaks entity-specifically on both sides.

This is a genuinely hard case, not a contrived one: 4 further Descartes-08 protocols
(`NCT03448978`, `NCT07391605`, `NCT06038474`, `NCT06799247`) are unambiguous, so the defect turns on
one protocol out of five and would be easy to miss.

## 3. Design

Paired targeted live run, same day, identical query / `--as-of` / source index. The only difference
is the symmetry subtraction in `_intervention_specific_comparators`.

| arm | commit | `_intervention_specific_comparators` returns |
|---|---|---|
| `a3_on` | `c98830e` (unmodified v4) | `sole_occupants(comparator_labels) - sole_occupants(therapeutic_labels)` |
| `a3_off` | a throwaway commit on a throwaway branch | `sole_occupants(comparator_labels)` |

`a3_off` is the **asymmetric reading A3 superseded**, i.e. §3a(1) exactly as originally written. It
is a control variant only: it is never merged, and the branch is deleted after measurement.

Query, chosen to reach the asset rather than to flatter the result — it names neither Descartes-08
nor its trials:

```
Find clinical-stage BCMA cell therapies for generalized myasthenia gravis with human efficacy.
```

`--as-of 2026-09-24`, `--therapeutic-area AUTOIMMUNE`, the same `source_index.yaml` as the mint
pairs, `--format shortlist --allow-incomplete`.

## 4. Preregistered expected result

1. **`a3_off` demotes `Descartes-08`.** `NCT04146051` contributes one specific-comparator
   observation; asset-level dominance fires; `is_comparator_only` is true; the asset leaves the
   default path and loses any `human_poc` PASS.
2. **`a3_on` keeps `Descartes-08`** on the default path with a named `qualification_reason`, and
   retains whatever `human_poc` verdict the evidence supports.
3. `Placebo` is **off** the default path in **both** arms — the A3 narrowing must not resurrect it.

## 5. Pass / fail

**PASS** requires (1), (2) and (3) together.

(1) is as load-bearing as (2). If `Descartes-08` survives in `a3_off` as well, then A3 changed
nothing on this query and the control **did not fire** — that is reported as *inconclusive*, not as
a pass, and the sealed-snapshot measurement remains A3's only evidence.

**FAIL** if `a3_on` does not retain `Descartes-08`, or if `Placebo` returns to the default path in
`a3_on`.

## 6. Out of scope

- No change to v4 as committed. This control either ratifies A3 or reopens it; it does not tune it.
- No ranking work.
- The class-term milestone (`CAR19`, `CART19`, `bsAbs`) is a separate preregistration.
- If the query reaches `Descartes-08` in neither arm, the finding is that the *query* failed, not
  that A3 passed. Report and stop; do not iterate on the query to manufacture an exercise.
