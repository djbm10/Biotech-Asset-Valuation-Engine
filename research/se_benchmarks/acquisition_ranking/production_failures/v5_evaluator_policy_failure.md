# V5 production holdout — consumed evaluator-policy failure

- Frozen result: `FAIL`; V5 is permanently consumed and must never be rescored.
- Ranking status: `BLOCKED`.
- Prediction SHA-256:
  `104228728e29daece7a4813614f1068c02507225dbb21e6321a830664db248b3`.
- Evaluation report SHA-256:
  `15537d1cb65a6ea023182f9c41987b5dd0d8ae98929d460b66118f8ad4788c44`.
- Report path: `/tmp/se_production_holdout_20260711_v5/final/production_evaluation_report.md`.

All ranking, citation, rationale, diligence, coverage, and valuation-leakage criteria passed. V5
failed because the frozen evaluator treated the legitimate required field
`missing_or_conflicting_gate` as leakage through generic key-text matching. That frozen FAIL
stands. The forward correction defines gate leakage semantically as a violation of the mutually
exclusive INCLUDE/ranked, UNKNOWN/diligence_queue, and EXCLUDE/exclusions routes.
