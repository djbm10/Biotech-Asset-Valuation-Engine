# Acquisition-ranking benchmark

This benchmark is separate from the V4 acquisition-disposition holdout. It tests the downstream
ranking contract: INCLUDE-only ordering, UNKNOWN diligence routing, EXCLUDE suppression, public
pre-diligence labeling, and the absence of valuation fields from the ranking boundary.

`development.json` is a visible regression fixture. `unseen_holdout.json` is a frozen, separate
fixture used only by the ranking holdout test; it is not used to choose weights or implement the
ranker. A real production release still requires an externally governed holdout custodian and
independent review of the ranking labels.
