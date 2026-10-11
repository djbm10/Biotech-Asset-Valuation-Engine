# INDICATION_GATE_SEMANTICS v3 — authority coverage audit

Baseline 8da5e61, before preregistration or gate code changes. Audit only.
Every proposed control is checked directly against pinned NCIt 26.08e names and
explicit parent edges, independently of gate implementation. Adopted B-cell positive
controls retain their frozen vocabulary authority and record the matching whole-word
terms and source policy. Complete proof inventory: authority_audit.json.

The 28 proposed controls contain 10 demonstrably positive cases and 18 UNKNOWN
cases. Psoriasis Vulgaris has no alias in the pinned disease graph; it is UNKNOWN
in the new oracle. The failed-v2 oracle and all results remain unchanged. No synonym
has been inserted, no hierarchy inferred, and no gate behavior changed.
Positive controls have an authority identity/path or accepted controlled B-cell rule.
Missing, ambiguous, absent-path and incomplete disease typing cannot establish PASS.
This audit proves snapshot coverage, not universal biomedical equivalence; controls
whose possible real-world relationship is unprovable remain UNKNOWN.
