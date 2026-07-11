# Acquisition-ranking validation report

Date: 2026-07-11

The downstream ranking contract was evaluated independently of the V4 acquisition classifier.
Both fixtures use the same public, evidence-first input contract but the unseen holdout cases
were not used to select dimensions or implement the ranker.

| Set | Cases | INCLUDE order | UNKNOWN routed | EXCLUDE ranked | Result |
|---|---:|---|---:|---:|---|
| Development benchmark | 4 | exact | 1/1 | 0 | PASS |
| Frozen unseen holdout | 4 | exact | 1/1 | 0 | PASS |

Contract checks also passed:

- valuation and rNPV fields are rejected at the ranking boundary;
- duplicate asset IDs fail closed;
- only INCLUDE candidates receive ranks;
- UNKNOWN candidates route to DILIGENCE with required checks;
- EXCLUDE candidates are retained only in the excluded list;
- every ranked conclusion is labeled public_pre_diligence.

This is a ranking-contract validation, not a production effectiveness claim. Production use still
requires an independently governed, sufficiently powered ranking holdout with expert labels,
frozen before the production run.
