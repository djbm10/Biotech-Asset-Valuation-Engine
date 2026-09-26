# TAC01-CD19 over-reach control — Amendment 2 (non-v5 review routing)

Status: **PREREGISTERED** 2026-09-26, append-only. Parent commit: `4605be1`.
Written and committed **while `/home/djmann/se_runs/tac01_control_a1` is still running and before
any of its output has been inspected.** Nothing below was chosen after seeing TAC01's routing.

This amends the decision table in Amendment 1 §4. The original preregistration, Amendment 1 and the
scorer `scripts/se_tac01_control_report.py` are all unchanged. The scorer stays frozen at sha256
`231aedf979289f52cb54b2bc392f00ae868b31f3d577c12927cfb17625a4fa62`.

## 1. The gap this closes

The frozen scorer prints `FAIL` for *any* move of `TAC01-CD19` to review. The hypothesis under test
is narrower: does the v5 class-term rule consume TAC01's sponsor residue? A review routing for low
support, or for any other evidence reason, does not bear on that hypothesis.

## 2. What to inspect, and nothing else

1. Was `TAC01-CD19` observed?
2. Did the v5 class-term predicate fire on it (`is_class_term`)?
3. What disposition and `qualification_reason` / review reason did it receive?
4. Did its sponsor residue survive classification (`individuating_residue == ("TAC01",)`)?

## 3. Adjudication

| verdict | condition |
|---|---|
| **PASS** | on the default path, and the class-term rule did not consume the residue |
| **FAIL** | in review or low support *specifically because* the v5 class-term rule consumed `TAC01` |
| **INCONCLUSIVE_FOR_V5_OVERREACH** | retrieved, but in review for an unrelated support or evidence reason, with the class-term predicate not firing |
| **INCONCLUSIVE** | not retrieved |
| **QUERY_FAILURE** | parser wrong. Already ruled out for this run: the compiled problem is `ANY of CD19` with no `LARGE1`. |

The scorer's raw output is kept verbatim. Wherever the amendment-level verdict differs from the
scorer's printed verdict, the reason is stated explicitly.

## 4. Source incompleteness

The run recorded zero records and one failed query each for `conference_ash`, `conference_eha` and
`sec_edgar`. This does **not** change the verdict unless TAC01's evidence actually depends on one of
those unavailable sources.
