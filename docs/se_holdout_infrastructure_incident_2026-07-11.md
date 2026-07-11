# S&E holdout infrastructure incident — 2026-07-11

The first and only invocation against sealed bundle
`9834651310c4f0a699373a91794976bcfb9aa7b37a4e666c6b142ae0880ea1e6` exited `1`
before inference and produced no prediction artifact. The bundle is consumed and must never be
rerun or used to tune retrieval, evidence gating, or disposition rules.

## Exact validation failure

`BuyerProblemV2.model_validate(...)` reported nine errors:

1. `version`: expected a string; received integer `1`.
2. `buyer`: required field missing.
3. `strategic_gap`: required field missing.
4. `title`: extra input not permitted.
5. `task`: extra input not permitted.
6. `allowed_dispositions`: extra input not permitted.
7. `labeling_rubric`: extra input not permitted.
8. `decision_rules`: extra input not permitted.
9. `source_text_policy`: extra input not permitted.

## Root cause and corrective boundary

The CLI documented `--problem` as a `BuyerProblemV2` file even though this runner performs
case-level evidence-triage classification and only used the parsed `problem_id`. The supplied
problem was a classification rubric, not a buyer-strategy/discovery query. `BuyerProblemV2` remains
the correct contract for acquisition workflows; the holdout CLI now uses a dedicated strict
`se_holdout_problem_v1` contract and provides a non-inference `--validate-only` preflight.
