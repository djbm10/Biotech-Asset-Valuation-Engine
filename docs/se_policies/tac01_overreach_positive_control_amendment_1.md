# TAC01-CD19 over-reach control — Amendment 1 (query instrument)

Status: **PREREGISTERED** 2026-09-26, append-only. Parent commit: `9b6df42`.
Amends `tac01_overreach_positive_control.md` without editing it. That file stays frozen at sha256
`70773afe1f4a6584f2c8abf49e8b61250451bcc8e1a676a0359e96a704df3928`. The scorer
`scripts/se_tac01_control_report.py` stays frozen at sha256
`231aedf979289f52cb54b2bc392f00ae868b31f3d577c12927cfb17625a4fa62`.
Written and committed **before** the run.

## 1. The original attempt: QUERY_FAILURE / NOT_TESTED

The preregistered query (`… relapsed or refractory large B-cell lymphoma.`) compiled to
`target constraint: ANY of LARGE1`. The parser matched `large` to the gene `LARGE1`
(`unique_alias_match`) and left `CD19-directed` as `RESIDUAL`. Two runs are recorded:

- `/home/djmann/se_runs/tac01_control`, started 2026-09-24. It died after more than 28 hours with no
  output.
- `/home/djmann/se_runs/tac01_control_r2`, started 2026-09-26. Its `problem.yaml` was identical, and
  it was stopped after about 2 minutes.

Neither run measured CD19. The recorded outcome is **QUERY_FAILURE / NOT_TESTED**. It is not a v5
result in either direction.

## 2. The only change: the literal query text

```
Find clinical-stage CD19 cell therapies for relapsed or refractory B-cell lymphoma.
```

This corrects the measurement instrument. It does not change the hypothesis. The following are
unchanged:

- v4, A3 and v5
- fragmentation, and every threshold
- the scorer logic
- the source index (`/home/djmann/se_runs/aacr_probe5/source_index.yaml`)
- `--as-of 2026-09-24`, `--therapeutic-area ONCOLOGY`, `--format shortlist --allow-incomplete`
- the predicted outcome for `TAC01-CD19`: retention, with `individuating_residue == ("TAC01",)`
  and `is_class_term == False`

The new run writes to `/home/djmann/se_runs/tac01_control_a1`.

## 3. Frozen parser interpretation (checked before the run, no search executed)

```
'clinical-stage' -> EVIDENCE minimum_stage
'CD19'           -> TARGET CD19 [unique_alias_match]
'cell therapies' -> MODALITY CELL_THERAPY
'relapsed' / 'refractory' / 'B-cell' / 'lymphoma' -> RESIDUAL
target constraint: ANY of CD19
modality constraint: CELL_THERAPY
phase constraint: none
evidence floor: minimum_stage=PHASE_1
```

The run's `problem.yaml` must carry exactly one target, `CD19`, and no `LARGE1` or any other
target. If it does not, the outcome is **QUERY_FAILURE**, and the run is stopped before acquisition
completes.

## 4. Decision rule

| outcome | condition |
|---|---|
| **QUERY_FAILURE** | the compiled problem differs from §3 |
| **PASS** | `TAC01-CD19` is retrieved, is on the default path with a named `qualification_reason`, and class terms are held in review in the same run (original §4(2), unchanged) |
| **FAIL** | `TAC01-CD19` is retrieved but routed to review because the class-term rule consumed its sponsor residue (`is_class_term == True`). This reopens that narrow v5 issue only. |
| **INCONCLUSIVE** | valid CD19 acquisition completes but `TAC01-CD19` is never observed, or no class term is demoted in the run (original §5, unchanged) |

The scorer is frozen and prints `FAIL` for *any* move to review. It also prints the canary's
`qualification_reason` and `is_class_term`. If `TAC01-CD19` is in review with
`is_class_term == False`, the class-term rule did not demote it. That can happen for low support,
because the record is a single WITHDRAWN trial with no `otherNames`. That case is reported verbatim
to the operator as a **non-v5 routing**, with the scorer's raw output alongside. It is not relabelled
as a v5 failure, and it is not relabelled as a pass.

## 5. No further query iteration

This is the last query. If it fails to retrieve or exercise `TAC01-CD19`, the result is
**INCONCLUSIVE** and there is no further rewrite.

## 6. Out of scope

The two parser defects are a separate, future parser milestone and are not fixed here:

- a common English word minted as a target (`large` → `LARGE1`)
- the `-directed` suffix not being stripped (`CD19-directed` → `RESIDUAL`)

Everything else in the original §6 still holds: no carve-outs, and no ranking work inside this
control.
