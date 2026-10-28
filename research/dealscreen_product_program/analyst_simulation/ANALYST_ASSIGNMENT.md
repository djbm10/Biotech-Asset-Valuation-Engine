# Analyst simulation: assignment (AI-SIMULATED / INTERNAL DEVELOPMENT)

The analysts are AI subagents. Nothing here is human validation, and no human sign-off is
claimed. Gate H and Gate B stay open.

## Assignment given to the simulated analyst (verbatim brief)

"Find clinical-stage therapeutic programs fitting our specified disease mechanism. Exclude
unsuitable biology and modalities, prioritize compelling human evidence, investigate ownership
and U.S. licensing restrictions, and identify the best opportunities for preliminary financial
evaluation."

Tasks A-G: understand the landscape (A), screen (B), scientific diligence (C), commercial
diligence (D), shortlist of up to 10 (E), preliminary valuation of up to 3 (F), and the workbook
and memo as a BD deliverable (G).

## Inputs the analyst may use

- `examples/dealscreen_real/landscape_fcrn_gmg_v2.csv` (40 public programs)
- `examples/dealscreen_real/profile_public_landscape_v2.yaml`, `buyer_fcrn_gmg.yaml`
- `examples/dealscreen_real/valuation_assumptions_hypothetical.yaml`, `field_provenance.csv`, `sources/`
- `docs/dealscreen/README.md` and the CLI help (`bve-dealscreen`, `bve-dealscreen-value`, `bve-asset`)
- public web sources

## Withheld until the analyst assessment is frozen

- `examples/dealscreen_real/reference_manual_assessment.csv` (the pre-committed reference)
- `research/dealscreen_real_v1/`, `research/dealscreen_product_program/` (prior results, bug lists)
- `src/` and `tests/` (implementation)

Human-only steps are recorded as NOT COMPLETED BY HUMAN. Timings are AI-simulated and are
never a human time-saving claim.
