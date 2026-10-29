# Freeze record (cycle C1)

Frozen before any workflow ran (2026-10-29): `PROTOCOL.md`, `SOP_SPREADSHEET.md`, `programs.yaml`,
`build_landscape.py`, `sources/` (ClinicalTrials.gov snapshot, openFDA snapshot, curator evidence:
153 verbatim items for 61/62 programs), `inputs/` (landscape 62 rows built mechanically, field
provenance, evidence library, buyer, mapping profile, hypothetical valuation inputs) and
`reference/` (AI reference curator: 30 IN rows / 25 distinct molecules, 28 OUT, 4 UNRESOLVED;
top candidates). The landscape was not cleaned: mechanical derivation leaves vendor-style cell
errors (listed only in the reference). The freeze commit hash is the commit that adds this file.

No DealScreen code changed between the start of cycle C1 and this freeze (HEAD before: 92ad1e6).
