# Class terms v5 — a class label is not an asset

Status: **PREREGISTERED** 2026-09-24. Parent commit: `0dfb18c`.
Follows `asset_qualification_evidence_subjects_v4.md` (kept; PASS_ON_V4_CHANGES).

Written and committed **before** any v5 code change. Costs in §4 were measured against the v4 live
artifact `/home/djmann/se_runs/mint4_on` and are declared here so they cannot be revised after
seeing the v5 result.

## 1. What this closes

v4 satisfied its six criteria on the changes it made, but the frozen criterion 2 — **zero non-assets
with a decisional PASS** — is not met: `CAR19` and `CART19` hold asset-level `human_poc` PASSes.
Neither is a specific therapeutic. `CART19` aggregates **33 trials across 14 companies**; those are
14 different constructs, not 14 sponsors of one molecule. The defect predates v4 and the bar is not
relaxed on that account.

This is the third invariant in the series, and like the other two it is about what a name *is*, not
about a threshold:

> **A class label denotes a set of assets. It cannot be a member of that set.**

v1–v2 asked *is this string a drug name?* v4 asked *is this record about this object?* v5 asks
*does this name denote one thing or a category?*

## 2. The rule

A canonical name is a **class term** when its entire content is exhausted by modality vocabulary,
target designations and grammatical filler — that is, when nothing in it individuates a molecule.

- **Modality vocabulary**: `CAR`, `CAR-T`, `CART`, `NK`, `TCR`, `TIL`, `BiTE`, `ADC`, `mAb`,
  `bsAb`/`bsAbs`, `bispecific`, `trispecific`, `antibody`/`antibodies`, `cell(s)`, `therapy`/
  `therapies`, `vaccine`, `degrader`, `ASO`, `siRNA`, `CRISPR`.
- **Target designations**: any symbol resolving in the ontology, plus a bare number `n` where
  `CD<n>` resolves in the ontology. This is what makes `CART19` a class term (`CD19`) while
  `CAR088` is not (`CD088` does not resolve). **The ontology is the authority — not a hand list of
  CD numbers, and not the target vocabulary of the current run.**
- **Filler**: `anti`, `dual`, `target(ed|ing)`, `specific`, `directed`, `autologous`, `allogeneic`,
  `humanized`, `human`, `murine`, `armored`, `redirected`, `positive`, `based`.

Anything left over individuates, and the name is an asset. `TAC01-CD19` keeps `TAC01`; `ABBV-383`
keeps `ABBV`; `tisagenlecleucel` is a molecule name. A **zero-padded** numeric (`0\d{2,}`) is read
as a sponsor serial and never as a target designation, which is what protects `CAR011`, `CAR066`,
`CAR088`.

### Disposition

Class terms are **retained as metadata and lose asset standing**:

1. Not canonical assets: off the default path, not eligible, not shortlisted as assets.
2. **No asset-level `human_poc`.** A class label cannot hold a decisional efficacy verdict.
3. Not deleted. They remain in the review population with an explicit reason, exactly like every
   other demotion since M18 — routing by support, never deletion.
4. Their trial and target edges are **not** discarded. A class term legitimately groups assets, and
   that grouping is the useful part; it simply is not itself an asset.

## 3. Why not the alternatives

- **Owner count.** Rejected: `pembrolizumab` also appears across many sponsors. Sponsor breadth
  describes a molecule's popularity, not its individuation.
- **A name blacklist.** Forbidden by standing constraint, and it would not generalize past this
  corpus — the whole point of M13–M17 was zero-shot behaviour.
- **Demoting anything whose name contains a target symbol.** Would take `TAC01-CD19` and the
  `FIT-(BCMA+CD19)-CAR-T Cells` family, which are real assets. Individuating residue is the
  discriminator, not target-symbol presence.

## 4. Declared cost

Measured on `mint4_on` (1,136 default-path assets) with the run's own target vocabulary, which
**lacks `CD20`, `CD22` and `CD138`** and therefore *under*counts:

- **35 default-path names classify as class terms**, of which **2 hold a `human_poc` PASS**
  (`CAR19`, `CART19`). Composition: `CAR-T`, `CAR-T cell(s)`, `CAR-T Therapy`, `CAR T-cell therapy`,
  `CD19 CAR-T` (and 14 further orthographic variants of "anti-CD19 CAR-T cells"), `CD19-CAR-NK`,
  `CD19-CAR-NK/T`, `CAR-CD19 T cell(s)`, `CAR-NK-CD19 Cells`, `Allogeneic/Autologous CD19 CAR-T
  cells`, `CAR19`, `CART19`. **Every one of the 35 is a category, not a molecule.** No real asset is
  among them.
- Under the ontology-backed rule required by §2, `CAR-20`, `CART22` and `CART-138` are expected to
  join them (`CD20`, `CD22`, `CD138` all resolve). They are likewise class labels. `TAC01` stays an
  asset on its `TAC01` residue. **Declared range: 35–38 demotions, 2 `human_poc` PASSes withdrawn.**
- **Declared genuine-asset cost: zero.** This is the first milestone in the series with no real
  asset priced in, which is itself a falsifiable claim: if the paired run demotes any name carrying
  individuating residue, that is a **FAIL**, not an accepted cost.

## 5. Acceptance bar

1. `CAR19` and `CART19` are off the default path and hold **no** `human_poc` PASS.
2. **Zero non-assets with a decisional PASS** — criterion 2 of the v4 bar, now met outright.
3. Every v4 frozen positive still survives with an unchanged `qualification_reason`, including
   `SYNCAR-001`, `HB2198`, `ABBV-383`, `ALLO-715`, `AMG 420` and `TAC01-CD19` if present.
4. No name carrying individuating residue is demoted. Zero real-asset loss, as declared in §4.
5. Human-PoC population falls by exactly the class terms that held one (expected 31 → 29) and by
   nothing else.
6. Every remaining default-path asset still carries a named `qualification_reason`; zero anonymous
   admissions.
7. Every demoted class term carries an explicit class-term reason in the review population — the
   demotion must be as auditable as an admission.

Validation is a **fresh paired same-day live acquisition**, `mint5_on` vs `mint5_off` at the v5
parent, on the unchanged v4 acceptance query. Sealed replay is not the adoption test.

## 6. Not to be done under v5

- No hand-written name blacklist.
- No weakening of target or `human_poc` rules — this milestone only *removes* PASSes.
- No threshold tuned after seeing the acceptance corpus.
- No change to v4, fragmentation, or the A3 symmetry rule.
- No ranking work. Ranking begins only after this bar and the A3 positive control both pass.

## 7. Amendment B1 — 2026-09-24, before any v5 measurement

**Direction: narrowing of the declared cost — the rule itself is unchanged.** Recorded because the
§4 figure was wrong, and it was wrong in the direction that flatters the milestone.

### B1.1 The cost is 104, not 35

§4 was measured with a throwaway probe whose token allow-list omitted the bare token `T`. Every
name of the form `… CAR-T …` therefore escaped classification, which is most of them. Re-measured
with the implemented rule against the same artifact (`mint4_on`, 1,136 default-path assets):

**104 class terms, of which 2 hold a `human_poc` PASS** (`CAR19`, `CART19`, as declared).

The composition is the same in kind as the 35 — `CAR-T`, `CAR-T cells`, `CD19 CAR-T cells`,
`Chimeric Antigen Receptor T-Cell Therapy`, `anti-BCMA CAR-T`, `BCMA/CD19 CAR-T`,
`CD22/CD19 Dual-Target CAR-T Cells` and ~90 further orthographic and word-order variants of those.
This is the **9.2%** of the default path that is generic intervention prose from CT.gov
`interventionName` fields, not the asset names of specific programs.

The `FIT-(BCMA+CD19)-CAR-T Cells` family that v4 §4c protected is **kept**, on its `FIT` residue —
the §4c concern does not recur. But the *pure* dual-target descriptors
(`BCMA/CD19 Dual-Target CAR-T`) are class terms and are demoted, which §4 did not say and should
have.

### B1.2 The disputed subset: armored and ligand-based constructs

Re-measurement surfaced a subset §2 did not anticipate. Roughly twelve of the 104 individuate a
construct using a *gene or protein symbol that is not the therapy's target*:

`anti-CD19 IL10/IL15 CAR-NK`, `CD19-BAFF CAR T-cells`, `CD19-IL7Ra CAR-T`,
`CXCR4 modified anti-BCMA CAR T cells`, `CD19 CAR-T TLR2`, `CD19-CAR-DNT`, `CD19.CAR-aNKT`,
`Anti-CD19-CD3E-CAR-T cells`, `Anti-BCMA-GPRC5D CAR-T cells infusion`, `CD19-BCMA CAR-T`,
`anti-CD19/CD22 CAR-T cells`, `CD19/CD22-bispecific CAR-T cells`.

`IL10/IL15`, `BAFF`, `IL7Ra`, `CXCR4` and `TLR2` are armoring or co-stimulatory features, not
antigens the CAR binds. §2 strikes out "any symbol resolving in the ontology", so it strikes these
too, and the name empties. Under a stricter reading they *do* individuate: an IL7Ra-armored CD19
CAR-T is a different construct from a bare one.

**This amendment does not resolve it, and deliberately does not add a carve-out.** Distinguishing an
armoring symbol from a target symbol needs grammar this engine does not reliably have, and inventing
that grammar after seeing the list is exactly the tuning the standing constraints forbid. Instead:

- The rule stays as preregistered in §2 — these are demoted with everything else.
- The v5 report **must break them out as a named subset** rather than folding them into the 104, so
  the operator can rule on them as a separate question.
- Acceptance criterion §5.4 ("no name carrying individuating residue is demoted") is satisfied on
  its letter: under §2 these carry no residue. It is the *definition* of residue that is in
  question, not compliance with it. Saying so here rather than claiming a clean pass.

### B1.3 `CD20` does not resolve

`CAR-20` and `CD20`-only names are **kept as assets**, because `normalize_target("CD20")` returns
`None` in the published snapshot — ambiguous rather than unknown. `CD22` and `CD138` both resolve,
so `CART22` and `CART-138` are demoted. The asymmetry is an ontology fact, not a rule, and it is
the conservative direction (it withholds a demotion). Reported, not patched: hand-adding `CD20`
would make §2's "the ontology is the authority" untrue.
