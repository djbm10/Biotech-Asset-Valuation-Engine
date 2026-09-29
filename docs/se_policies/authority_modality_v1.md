# Authority modality v1, and ranking v1 amendment 1 (query-modality match)

Status: **PREREGISTERED** 2026-09-28. Parent commit: `589f357`.
Parent policies: `ranking_lexicographic_v1.md` (frozen) and `authority_identity_merge_v1.md` (ADOPTED).

This document was written and committed **before** any code change. The acceptance criteria in §6
are fixed here and are not revised after seeing the result.

## 1. What this closes

`CanonicalAsset.modality_id` is **discovery context**: the modality of the trial or query an asset
was found through. In TAC01 that is why cyclophosphamide and fludarabine read `CAR_T`, and why
lenalidomide and R-mini-CHOP read `MONOCLONAL_ANTIBODY`. Ranking v1 does not use modality at all,
so loncastuximab (ADC) and tafasitamab (antibody) sit among the CAR-Ts in a cell-therapy question.

> **Modality belongs to the asset, not the trial.** An asset's modality comes only from an
> authority's record of the asset's own drug. If there is no such record, the modality is
> UNKNOWN. A trial's modality describes the trial or the query context. It never establishes an
> asset's modality, and an unknown modality is never filled in from it.

`modality_id` and discovery are **unchanged**. Discovery context is still reported, under its
existing DISCOVERY_CONTEXT label. It is simply no longer the only modality shown, and it never
enters the rank.

## 2. The authority

- **Source.** The ChEMBL_37 `molecule_dictionary.molecule_type` field. This is the same ChEMBL
  release the installed ontology snapshot (resolver_v2) was built from. The pinned sqlite is at
  `staging/pdcd1_gold_role_authority_v1/sources/chembl_37/`.
- **Sidecar.** A build script extracts `molecule_type` for every ChEMBL id that some DRUG record in
  the installed snapshot carries. The output file records the release and the sqlite's sha256. It
  is local data, like the snapshot, and is not committed. The script is committed.
- **If the sidecar is absent,** every asset is UNKNOWN. The run does not fail and does not fall
  back to any other source.
- **Open Targets `drugType` is not used.** For every control checked in the survey it gave the same
  answer as ChEMBL, so a second source would add a conflict path and no information.

### 2.1 Which drug is the asset's

This uses the rule `authority_identity_merge_v1` §2 already adopted, and no new identity rule:

- A name identifies drug `D` only when it resolves unambiguously through an `APPROVED_NAME` or
  `DEVELOPMENT_CODE` alias, and is neither a class term nor a biosimilar product code.
- The asset's drugs are the set of `D` over its canonical name and its aliases.
- If the asset has exactly one `D`, it takes `D`'s modality. Zero or more than one gives UNKNOWN.

Trade names, bare synonyms and co-occurrence never confer a modality, just as they confer no
identity.

### 2.2 From molecule type to modality

The drug's ChEMBL ids are those of its source records. If they disagree on molecule type, the
result is UNKNOWN.

| ChEMBL `molecule_type` | Authority modality |
|---|---|
| Small molecule | `SMALL_MOLECULE` |
| Antibody | `ANTIBODY` |
| Antibody drug conjugate | `ANTIBODY_DRUG_CONJUGATE` |
| Cell | `CELL_THERAPY` |
| Gene | `CELL_THERAPY` if the approved name's final word ends in `cel`; otherwise `GENE_THERAPY` |
| Oligonucleotide | `RNA_THERAPEUTIC` |
| Protein, Enzyme | `PROTEIN` |
| Oligosaccharide | `OLIGOSACCHARIDE` |
| Vaccine component | `VACCINE` |
| Unknown, empty, no row | UNKNOWN |

The **Gene rule** is a derivation, disclosed as one.

- ChEMBL files genetically modified autologous cell products as Gene: axi-cel, brexu-cel, liso-cel,
  cilta-cel, obe-cel and inaticabtagene. It files tisa-cel as Cell.
- The WHO INN scheme gives cell-based products the `-cel` suffix (`-leucel`, `-temcel`, …) and
  vector gene therapies `-vec`/`-gene`.
- The rule reads the authority's own approved name. It lists no drug by name.
- A Gene record without such a name stays `GENE_THERAPY`, which is not a cell therapy.

## 3. Match against the question

A match is computed only when the problem declares `strategic_gap.modalities`. If it declares none,
there is no modality dimension, and the ranking is exactly ranking v1.

For each declared query modality, the table below gives the authority modalities that **MATCH**
it, and those that are **too coarse** to decide (these give UNKNOWN). Every other known authority
modality is a **MISMATCH**. With several declared modalities, the best status across them wins
(MATCH over UNKNOWN over MISMATCH).

| Query modality | MATCH | Too coarse, so UNKNOWN |
|---|---|---|
| `CELL_THERAPY` | `CELL_THERAPY` | — |
| `CAR_T` | — | `CELL_THERAPY` (ChEMBL has no CAR class) |
| `MONOCLONAL_ANTIBODY` | `ANTIBODY` | — |
| `BISPECIFIC_ANTIBODY`, `MULTISPECIFIC_ANTIBODY`, `T_CELL_ENGAGER` | — | `ANTIBODY` |
| `ANTIBODY_DRUG_CONJUGATE` | `ANTIBODY_DRUG_CONJUGATE` | — |
| `SMALL_MOLECULE` | `SMALL_MOLECULE` | — |
| `MOLECULAR_GLUE_OR_DEGRADER` | — | `SMALL_MOLECULE` |
| `GENE_THERAPY` | `GENE_THERAPY` | — |
| `GENE_EDITING` | — | `GENE_THERAPY`, `CELL_THERAPY` |
| `RNA_THERAPEUTIC` | `RNA_THERAPEUTIC` | — |
| `VACCINE` | `VACCINE` | — |
| `PEPTIDE`, `FUSION_PROTEIN` | — | `PROTEIN`, `SMALL_MOLECULE` |
| `RADIOLIGAND`, `ONCOLYTIC_VIRUS` | — | everything |

An asset whose authority modality is UNKNOWN is always UNKNOWN. **UNKNOWN is never PASS.**

## 4. Ranking v1 amendment 1

This is the ranking v1 key with one element inserted after eligibility, and nothing else changed:

```
(eligible, MODALITY_MATCH, efficacy, -stage, target decision, target assertion, -#PASS, name, id)
```

- `MODALITY_MATCH` is 0 for MATCH, 1 for UNKNOWN and 2 for MISMATCH.
- It is 0 for every asset when the problem declares no modality.
- The frozen scorer `scripts/se_ranking_v1_compare.py` mirrors the key in `_independent_order`. It
  reads the match status from the run's own candidate JSON, not from the shortlist. R1–R4 are
  otherwise unchanged.
- Each asset carries the new fields `authority_modality` and `modality_match`. The shortlist
  displays the authority modality with its basis (drug, ChEMBL id, molecule type) next to
  the discovery context.

The existing `modality_technology` gate is not changed. It is recorded as a latent defect only.
Modality claims are entailed only when the passage contains the normalized value literally, so in
TAC01 no `CAR_T` or `CELL_THERAPY` claim is ever entailed and the gate is UNKNOWN for 1397 assets.
Fixing it is out of scope. The rank does not read it.

## 5. Expected TAC01 effect (a forecast, not a criterion)

- The resolved CAR-Ts (axi-cel, brexu-cel, liso-cel, tisa-cel) are MATCH and lead.
- Unresolved programme codes are UNKNOWN and come next: CNCT19, CC-97540, KITE-753, ALLO-501A,
  7×19-THEMIS, NKTR-255 and TAC01 itself.
- The following are MISMATCH:
  - loncastuximab, coltuximab and denintuzumab (ADC);
  - tafasitamab and inebilizumab (antibody);
  - cyclophosphamide, fludarabine and lenalidomide (small molecule).
- `Fludarabine-based` and `R-mini-CHOP` resolve to no drug, so they are UNKNOWN. They stay among
  the unknown-modality programmes. This is the known regimen-name population limitation, and this
  document does not address it.

## 6. Acceptance (the same sealed replays: TAC01 `tac01_control_a1` and mint5 `mint5_on` custody)

These are the user's bar, verbatim in substance:

- **A1.** Approved CAR-Ts and named cell-therapy controls keep CELL_THERAPY (or CAR_T). The
  controls are axi-cel, brexu-cel, liso-cel, tisa-cel, cilta-cel, obe-cel and tabelecleucel,
  wherever they appear in either run.
- **A2.** Cyclophosphamide, fludarabine and lenalidomide cannot inherit a cell-therapy or antibody
  modality from trials. Their authority modality is `SMALL_MOLECULE`, and in TAC01 they are
  MISMATCH.
- **A3.** No asset with a known wrong modality (MISMATCH) ranks above a matching-modality (MATCH)
  asset because of PoC or stage. This is checked over the whole TAC01 ranking.
- **A4.** UNKNOWN modality is not treated as PASS. No UNKNOWN asset ranks above a MATCH asset, and
  the gate's modality decision is unchanged.
- **A5.** Ranking v1 is otherwise unchanged.
  - mint5 declares no modality, so its order is identical to `mint5_merge_v1`.
  - R1–R3 pass on both runs with the mirrored scorer.
  - `tests/se` passes.

**Benchmark.** K1 from `ranking_lexicographic_v1.md`, with the same hand rubric, is re-scored on
the TAC01 top 20:

- If K1 passes, stop there.
- If K1 fails, classify the remaining failures. If they are mostly regimen-name rows (the
  `R-mini-CHOP`/`Fludarabine-based` type), report that as the input to the regimen-role-model
  decision. That decision is the user's.

If A1–A5 fail, revert with a normal revert commit and record the result here.

## 7. Results

(appended after measurement)

### 7.1 Measurement — 2026-09-28, implementation `8046ef7`

Sealed replays: `se_runs/tac01_modality_v1` and `se_runs/mint5_modality_v1`. Evaluation output is in
`tac01_modality_v1/modality_eval.txt`; frozen scorer output (with the mirrored key) is in each run's
`ranking_v1_compare.txt`.

- **A1 PASS.** axi-cel, brexu-cel, liso-cel, tisa-cel, cilta-cel, obe-cel and tabelecleucel are
  `CELL_THERAPY` in both runs. In TAC01 they are MATCH (cilta-cel and obe-cel are excluded, so they
  are not ranked).
- **A2 PASS.** Cyclophosphamide, fludarabine and lenalidomide are `SMALL_MOLECULE` in both runs. In
  TAC01 they are MISMATCH at #239, #240 and #241 (they were #8, #9 and #13). Their `modality_id`
  (discovery context) still reads CAR_T/MAB and is unused.
- **A3 PASS.** No MISMATCH asset ranks above any MATCH asset anywhere in TAC01. The TAC01 counts are
  19 MATCH, 217 UNKNOWN and 432 MISMATCH. Loncastuximab (#5→#237) and tafasitamab (#6→#238) fell.
- **A4 PASS.** No UNKNOWN asset ranks above any MATCH asset. The modality gate is untouched.
- **A5 PASS.** mint5 declares no modality: `modality_match` is None for every asset, and its 323-row
  order is identical to `mint5_merge_v1`. R1–R3 PASS on both runs. `tests/se` gives 1511 passed and
  3 xfailed.

**K1 re-judged (TAC01 top 20, same rubric).** This judgement is by hand, from programme knowledge
and not from run evidence.

- RELEVANT (CD19-directed cell therapy), 12 rows: brexu-cel, axi-cel, liso-cel, tisa-cel,
  CC-97540, cemacabtagene ansegedleucel, prizloncabtagene autoleucel, anbalcabtagene autoleucel,
  resecabtagene autoleucel, TAK-007 (CD19 CAR-NK), varnimcabtagene autoleucel and CNCT19.
- OFF_TARGET (a real cell therapy, but not CD19), 8 rows:
  - tabelecleucel (EBV-specific T cells) and lifileucel (TIL);
  - ALLO-715, anitocabtagene, CT053, equecabtagene and orvacabtagene (BCMA);
  - satricabtagene (Claudin18.2).
- DUPLICATE and NON_ASSET: 0.
- The four named CAR-Ts are #1–#4. **RELEVANT = 12 ≥ 10, so K1 PASSES.** Prizloncabtagene is the
  least certain call; K1 still passes without it (11).

The 8 off-target rows are cell therapies whose target is UNRESOLVED, so the target keys cannot
separate them from the CD19 programmes. That is the known target-evidence coverage limitation, not a
modality defect. The regimen names Fludarabine-based (#21) and R-mini-CHOP (#24) are UNKNOWN and
fall just outside the top 20. TAC01 itself is #84.

**Status: ADOPTED.** TAC01 clears the benchmark bar, so work stops here as instructed. No regimen-role
model is indicated by this result.
