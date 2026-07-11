# Open v3 holdout failure-analysis set

This directory declassifies the consumed v3 holdout as a permanent development regression set.
It contains the exact unlabeled cases, authoritative labels, problem specification, and independent
evaluation report from the first protocol-valid performance run.

The frozen v3 system predicted 35 INCLUDE, zero EXCLUDE, and one UNKNOWN across 36 balanced cases.
Its permissive rule treated every item as INCLUDE unless a tiny set of literal negative phrases was
present. The replacement implementation must satisfy general three-state gates:

1. Confirmed target, modality, buyer-capability, or evidence mismatch routes to EXCLUDE.
2. Missing, conflicting, or insufficient required evidence routes to UNKNOWN.
3. INCLUDE requires positive support from every applicable gate.

These records may be used for regression testing and failure analysis. They are no longer an
independent holdout and must never be represented as one.
