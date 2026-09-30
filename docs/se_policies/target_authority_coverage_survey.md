# Target-authority coverage survey: the 13 unresolved TAC01 top-20 rows

Date: 2026-09-29. Baseline: `se_runs/tac01_fragment_a1`, TAC01 rows #8–20, all with the target
gate UNKNOWN. This survey is read-only and changes no code. Ranking is frozen. It was run after
`asset_sentence_target_v1` closed (§5.2) to decide which single structured authority to
preregister next.

## Method

- **ChEMBL / Open Targets.** The installed snapshot `data/se/ontology/current`
  (ChEMBL_37, OT 26.06): edges in `edges.jsonl`, identity in `records.jsonl`.
- **Sponsor pipeline.** Document types that mention each asset in the sealed TAC01 corpus.
- **Trial registry.** A live CT.gov v2 query (2026-09-29) by INN and development code, with each
  intervention that names the asset passed through the **existing, unchanged**
  `intervention_construct_targets` reader. This measures what the proven route would produce
  if the records were acquired.
- **Other authority.** An NCIt EVS search (26.08e) on the approved name, recording both the
  concept's structured roles and its definition.
- GtoPdb needs an API key and was not surveyed.
- **Expected target.** Established pharmacology, cross-checked against NCIt and CT.gov where
  those answer.

## Matrix

| # | Asset | Current identity (ChEMBL) | ChEMBL target | Open Targets | Sponsor pipeline (corpus) | CT.gov structured → existing reader | NCIt (26.08e) | Expected |
|---|---|---|---|---|---|---|---|---|
| 8 | Tabelecleucel | TABELECLEUCEL (Cell) | row, target not in snapshot | — | none (1 conf + 1 pub abstract) | 6 trials, 0 target sets | C143140: EBV antigens (prose) | EBV antigens, no human gene → not CD19 |
| 9 | ALLO-715 | NENDOCABTAGENE ONOGEDLEUCEL | none | none | none (1 pub) | 1 trial → **TNFRSF17** | C165779: BCMA (prose) | BCMA |
| 10 | Anbalcabtagene autoleucel | ANBALCABTAGENE AUTOLEUCEL | none | none | none (6 pub) | 1 trial, 0 target sets | C180584: CD19 (prose) | CD19 |
| 11 | Anitocabtagene autoleucel | ANITOCABTAGENE AUTOLEUCEL | none | none | none (1 pub) | 5 trials → **TNFRSF17** ×3, none ×7 | C199003: BCMA (prose) | BCMA |
| 12 | CT053 | ZEVORCABTAGENE AUTOLEUCEL | none | none | none (1 pub) | 2 trials → **TNFRSF17** ×2, none ×2 | C165507: BCMA (prose) | BCMA |
| 13 | Equecabtagene autoleucel | EQUECABTAGENE AUTOLEUCEL | none | none | none (1 pub) | 7 trials → **TNFRSF17** ×7, none ×6 | C185123: BCMA (prose) | BCMA |
| 14 | Lifileucel | LIFILEUCEL (Cell) | row, target not in snapshot | — | none (1 pub) | 15 trials, 0 target sets | C120552: polyclonal TIL (prose) | none (TIL) → not CD19 |
| 15 | Orvacabtagene autoleucel | ORVACABTAGENE AUTOLEUCEL | none | none | none (2 pub) | 2 trials, 0 target sets | C147523: BCMA (prose) | BCMA |
| 16 | Resecabtagene autoleucel | RESECABTAGENE AUTOLEUCEL | none | none | none (1 pub) | 6 trials, 0 target sets | C211706 (definition present) | CD19 |
| 17 | Satricabtagene autoleucel | SATRICABTAGENE AUTOLEUCEL | none | none | none (6 pub) | 5 trials (as CT041), 0 target sets; "anti-claudin18.2" is not symbol-shaped | C150382: Claudin18.2 (prose) | CLDN18 (isoform 2) |
| 18 | TAK-007 | SITOCABNAGENE LOXIVELEUCEL | none | none | none (2 pub) | 2 trials, 0 target sets | C203060: CD19 (prose) | CD19 |
| 19 | Varnimcabtagene autoleucel | VARNIMCABTAGENE AUTOLEUCEL | none | none | none (8 pub) | 0 trials found by INN or IMPT-314 | C179725 (definition present) | CD19 + CD20, to verify |
| 20 | CNCT19 | none (identity not authority-backed, M11) | — | — | none | 17 trials → **CD19** ×3, none ×18 | C199061 (inaticabtagene) | CD19 |

## Findings

1. **ChEMBL and Open Targets are exhausted for this population.**
   - 0/13 have a human target edge.
   - The two edges that exist (tabelecleucel, lifileucel) carry a non-human or polyclonal
     target, correctly absent from a human-gene snapshot.
   - Identity is resolved for 12/13, so the gap is mechanism data, not identity.
2. **Sponsor pipeline data is absent from the frozen corpus for all 13.** Every mention is a
   publication or conference abstract. Collecting pipeline data would mean per-company HTML
   acquisition, which is not structured as field/column data for any of these rows. This is
   priority 1 in principle, but it resolves **0/13** today without a new acquisition layer.
3. **CT.gov through the existing reader: 5/13 resolved, all correct, no disagreements.**
   - Resolved: ALLO-715, anito-cel, CT053 and eque-cel (BCMA), and CNCT19 (CD19).
   - This would move 4 wrong-target rows to FAIL for the right reason and 1 CD19 row toward
     PASS.
   - It misses all 4 genuine CD19 INN programmes except CNCT19, because their sponsors do not
     state the target in the intervention field.
   - It is acquisition-side, so it needs a new live corpus and cannot be measured under
     sealed replay.
4. **NCIt covers 13/13, but only in definition prose.**
   - The concept's structured roles carry mechanism class ("Antigen Sensitization"), not the
     gene.
   - The definitions are curated and highly templated ("CAR specific for the TAA B-cell
     maturation antigen (BCMA; tumor necrosis factor receptor superfamily member 17; …)").
   - Unlike corpus free text, the *subject* is fixed by the concept, so there is no
     asset-attribution problem. The only open problem is naming the antigen, and that is
     exactly where the sentence route failed (alias collisions, non-symbol names).
   - It would be a pinned, ontology-side sidecar like the modality one, so it is measurable
     under sealed replay.
5. **Tabelecleucel and lifileucel have no human gene target at all.** No gene authority can
   ever put them below the CD19 line. They need a "target is not a human gene product" answer,
   which none of the surveyed routes emits as structure.

## Implication for the next preregistration

No single **structured** source solves most of the problem:

- CT.gov gives 5/13 and is precise but misses the CD19 INNs.
- NCIt reaches 13/13, but its target is prose, even if curated and templated.
- Pipelines give 0/13 without new acquisition.

The choice between the pinned CT.gov lookup (structured, 5/13, needs a live corpus) and an NCIt
sidecar (curated prose, 13/13, sealed-replay measurable) is left to the user.
