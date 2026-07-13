# V4 production holdout — consumed failure record

- Final status: `FAIL`; V4 is permanently consumed.
- Ranking status: `BLOCKED`.
- Immutable prediction SHA-256:
  `7e0d98c8e0ce9956dfaa7200cb6cff900885c1fa919540706fdb8898a8016e43`.
- Scoring-only continuation report SHA-256:
  `c18d6ebcd3f435d126a6e374b1e4b7d756f305b38be65ea521ed5dc405814735`.
- Custody report:
  `/tmp/se_production_holdout_20260711_v4/final/scoring_only_continuation_report.md`.

All frozen numeric ranking, citation, rationale, diligence-quality, coverage, and leakage criteria
passed. The mandatory UNKNOWN diligence-routing gate failed in all 24 queries. This is a valid
production failure and must not be waived. V4 may not be rerun or reused as a holdout.

Root cause: the production adapter exposed only a flat `diligence_asset_ids` handoff and routed a
narrower public-status subset than the required diligence set. It did not provide a structured
query-level diligence queue carrying the missing/conflicting gate, supporting evidence, and a
specific diligence question. The remediation adds that contract and fail-closed partition
invariants; production eligibility still requires evaluation on a completely new V5 holdout.
