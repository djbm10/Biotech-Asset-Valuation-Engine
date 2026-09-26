# Candidate-population validation (post TA-gate fix)

Date: 2026-09-26. Code: `f149aca`. This is analysis only; nothing was changed.

Inputs are the two accepted sealed replays:
- `se_runs/tac01_ta_fix_a1d`: CD19 cell therapy for R/R B-cell lymphoma, requested area ONCOLOGY.
- `se_runs/mint5_ta_fix_a1`: dual CD19/BCMA for autoimmune disease, requested area AUTOIMMUNE.

**Question:** before any ranking is preregistered, is the population a ranker would order the
right one? "Visible" means candidates that are neither EXCLUDED nor low-support.

## Headline

|                                   | TAC01 | mint5 |
|-----------------------------------|------:|------:|
| candidates                        | 5182  | 3188  |
| visible                           | 469   | 327   |
| visible with a registry trial     | **0** | 120   |
| visible with every gate UNKNOWN   | 436   | 202   |
| ELIGIBLE                          | 0     | 0     |

- **TAC01's population is inverted.** Every real CD19 CAR-T is EXCLUDED, and the visible
  population is entirely literature mentions with no trial.
- **mint5 is roughly usable.** The real autoimmune programmes are visible, but they sit among
  207 literature mentions: generic drugs, reagents and ordinary substances.

## Finding 1: TAC01 excludes every reference asset on `strategy.indication`

The following are all EXCLUDED, and the only FAIL on each is `strategy.indication`:
- axicabtagene ciloleucel, tisagenlecleucel, lisocabtagene maraleucel, brexucabtagene autoleucel
- relma-cel/JWCAR029, inaticabtagene autoleucel/CNCT19, zamtocabtagene autoleucel, IM19
- ALLO-501, cemacabtagene ansegedleucel, KITE-363, AUTO1/obecabtagene autoleucel
- TAC01, the positive control itself

**Cause:** parser defect #3 in `docs/se_parser_defects.md`. The query residue compiled into
`indications: [relapsed, refractory, B-cell, lymphoma]`, and those words are compared with the
registry's indication strings by exact membership. So "Relapsed/Refractory Diffuse Large B-cell
Lymphoma" fails the requirement. The defect was logged as cosmetic, but it decides the whole
TAC01 population.

**Consequence:** TAC01 cannot be a ranking benchmark until defect #3 is fixed. Any ranker
evaluated on it would be ordering noise.

## Finding 2: mint5 surfaces the expected programmes

Visible and trial-linked: GC012F, AZD0120, CNCT19/inaticabtagene autoleucel, CABA-201, RD06,
FKC289, ICG318, KN5501, QT-019C, BH2024, IM19, CM336, HBI0101 and others.

Correctly EXCLUDED on `target.expression`, because the query asks for dual CD19/BCMA and these
target CD19 only: KYV-101, obecabtagene autoleucel, CC-97540.

## Finding 3: newly observed defects (logged, not fixed)

1. **Identity merge misses.** One programme appears as two visible assets:
   - GC012F ≡ AZD0120
   - CNCT19 ≡ inaticabtagene autoleucel
   - CABA-201 ≡ resecabtagene autoleucel
   - HBI0101 ≡ "NXC-201 (formerly HBI0101)"
   - IM19 ≡ varnimcabtagene autoleucel
   - CTL019 ≡ tisagenlecleucel

   A ranker would list the same programme twice.
2. **Wrong construct target.** "BCMA-CD19 cCAR T cells" resolves to `TARGET:ST6GALNAC4`, so a
   genuine dual construct FAILs `target.expression` and is EXCLUDED.
3. **Arm and background interventions minted as assets.** 26 of mint5's 120 trial-linked visible
   assets are placebo arms, lymphodepletion or conditioning, chemotherapy backbones, dose arms or
   "X or Y" arm lists. A further 12 are descriptive construct names ("allogenic anti-CD19/BCMA
   CAR-T"), which may or may not be distinct programmes.
4. **Modality on literature mentions is co-occurrence noise.** For example, acetonitrile is
   typed T_CELL_ENGAGER, apigenin MONOCLONAL_ANTIBODY and basiliximab CAR_T.

## Implications for the ranking step

- The all-UNKNOWN literature tier has no trial and no stage. Under the declared lexicographic
  order (eligibility → human efficacy → maturity → …) it would fall below every trial-linked
  asset, so it does not block ranking. It should be shown as a separate "unassessed mentions"
  band rather than ranked among assets.
- **mint5** can serve as the autoimmune benchmark now. Merge misses (#1) and arm assets (#3)
  will show up as duplicate or non-asset rows; they should be scored as population defects, not
  ranking defects.
- **TAC01** cannot be the oncology benchmark until parser defect #3 is fixed. Either fix #3 as
  its own preregistered milestone first, or choose a different clean oncology query whose
  compilation leaves no residue.
