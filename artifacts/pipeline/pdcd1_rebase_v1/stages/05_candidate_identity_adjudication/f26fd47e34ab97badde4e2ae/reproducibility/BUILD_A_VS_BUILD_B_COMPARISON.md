# Milestone 5 - Build A vs Build B Candidate Identity Comparison

Build A subjects: `554`
Build B subjects: `554`
Subject coverage agreement: `554/554` covered.
Identity agreement: `554/554` (100.0%).
Disagreements: `0`, fully enumerated in `reconciliation_ledger.jsonl`.

Both builds read the same frozen M4 snapshot. Build A keeps M4 conflict subjects unresolved unless explicit identity evidence resolves the identity axis; Build B independently iterates reversed inputs and adjudicates product identity whenever explicit identity evidence is present. Reconciliation favours the conservative Build A output for the canonical published ledgers.
