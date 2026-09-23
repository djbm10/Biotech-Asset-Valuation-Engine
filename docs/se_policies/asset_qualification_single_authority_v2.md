# Asset qualification: one authority, molecule-specific evidence — v2

Preregistered 2026-09-23, **before any code change and before any measurement**, following the
FAILED_ACCEPTANCE of `a47bc9c` recorded in `docs/se_acceptance_log.md`. Supersedes nothing in
`asset_nomination_evidence_v1.md`: v1's routes were right where they were consulted, and the
failure was that they were not consulted, were widened unsafely, and were not sufficient for
prose. This document fixes those three things in that order.

## 1. What the paired live runs established

`mint_off` (parent `979ba4d`) vs `mint_on` (`a47bc9c`), same day, same query, same source index,
identical 2,873 candidates. Default canonical path 1,428 -> 1,398. `human_poc` PASS 39 -> 37.
`frontline`, `bsAbs`, `Placebo`, `POD24` all retained canonical status.

Three defects, each measured, not inferred:

1. **A second qualification authority.** `mention_support.is_protected()` returns before
   `qualifies_as_asset` is called and carries its own older definitions of "drug".
2. **The spaced development-code widening admits citations.** `ASCO 2023`, `NEJM 2011`,
   `EASL 2025`, `WHO 2022`, `PRISMA 2020`, `IQR 124` were promoted, not demoted.
3. **Prose corroboration does not separate a class from a molecule.** `bsAbs` qualified on two
   independent documents of genuine argument-position use, because it is genuinely used that way.

## 2. Audit performed before writing this rule

Measured against the frozen lexicon and the sealed `mint_on` artifact:

- `amg 420` is absent from the identity-bearing lexicon, but **`amg-420` and `amg420` are
  present**. The miss was a separator, not an absence.
- `allo-715` is absent, but **`allo 715` is present** — the same defect in the other direction.
- Under a separator-insensitive lookup (space/hyphen/no-separator folded), `AMG 420` and
  `ALLO-715` both resolve, and **none** of `ASCO 2023`, `NEJM 2011`, `IQR 124`, `WHO 2022`,
  `PRISMA 2020`, `ALL 2017`, `CLL 004`, `HOVON 139`, `ISB 2001`, `EASL 2025`, `POD24`, `bsAbs`
  resolves. The citation population is not in the drug lexicon under any separator.
- `AMG 420`, `CCS1477`, `ABBV-383`, `gemcitabine` and `pomalidomide` have **no** structured
  evidence in this corpus at all: `structurally_typed_drug=False`, 0 trials, 0 companies. Any
  rule requiring a structured record would delete all five.
- `Placebo` carries `comparator_role=False` in the live run despite 35 trials. **The v1 arm-group
  route did not fire in production.** It is not enough to add the route; this v2 must show it
  firing on live data or say that it does not.

## 3. The rule

### 3a. One qualification authority

`qualifies_as_asset` is the single decision. `is_protected` may not carry an independent
definition of "drug": if a name is protected, it is protected *because* `qualifies_as_asset`
said so. Any future identity fix must therefore reach every route, which is the property whose
absence caused this failure.

### 3b. Identity by authority, not by shape

The spaced development-code form is **removed**. Authority lookup becomes separator-insensitive
so `AMG 420` and `ALLO-715` resolve to the records the ontology already holds.

The remaining shape-based development-code route is **narrowed to a fallback that cannot stand
alone**: a code-shaped string with no authority record qualifies only if it also carries
molecule-specific corroboration under 3c. Declared cost, accepted in advance: a genuinely new
development code that no authority knows and that has no trial, owner or target linkage goes to
**review**, not to deletion. That is the intended direction of failure.

### 3c. Prose needs molecule-specific corroboration

Argument-position use in two independent documents establishes only that the string is a
*therapeutic term*. To become a canonical asset a prose-only unknown must additionally carry at
least one **entity-specific** link — evidence that could not be true of a class:

- an identity-bearing authority record (separator-insensitive), or
- a structured `DRUG` declaration not in comparator role, or
- a described construct identity (`construct_target_set`), or
- a specific trial, owner or target linkage attributable to this name.

A class term has pharmacologic grammar and no entity. That is the distinction, and it is the one
`bsAbs` defeats without it.

### 3d. Unchanged from v1

Trade names confer identity, never qualification (amendment 8a). The comparator role is read from
the source's own arm-group typing, never from a name list. The abbreviation-gloss veto stands.
The modifier veto stands — it demoted `safer`, `cornerstone` and `refine` on live data.
`MAX_DOCUMENT_FRACTION` is not tuned. No hand-written blacklist. Ranking is not touched.

## 4. Frozen controls

**Must NOT reach canonical status or any decisional PASS:**
`frontline` (and no laundering into `FIPRONIL` without genuine fipronil-use evidence), `choice`,
`discase`, `Placebo`, `POD24`, `ASCO 2023`, `NEJM 2011`, `IQR 124`, `WHO 2022`, `PRISMA 2020`,
`bsAbs` (even with multiple treatment-context occurrences), `safer`, `cornerstone`, `refine`.

**Must be retained:**
`AMG 420`, `ALLO-715`, `CCS1477`, `ABBV-383`, `SB-773812`, `benzhexol`, `lestaurinib`,
`ibritumomab`, `gemcitabine`, `pomalidomide`, `busulfan`, `teclistamab`, `pembrolizumab`,
`belantamab mafodotin`, `Idecabtagene Vicleucel`, and every repaired multi-token name from the
adopted fragmentation work.

## 5. Acceptance bar

> **Zero known non-assets in the default canonical population or holding a user-facing decisional
> PASS, while every protected real-asset control survives.**

Decided on a **rerun of the same paired fresh acquisition** (`mint2_on` / `mint2_off`, control at
this commit's parent), both 0 divergent attempts, same query / index / as-of. Sealed replay is not
the acceptance test, because these changes sit upstream of extraction.

Reported alongside: the `human_poc` passer list in full, the demoted and promoted sets by name,
and whether the arm-group comparator route fires at all on live data (§2).

## 6. Not to be done

No threshold may be adjusted after seeing the acceptance corpus. No blacklist. No change to
ranking, to the target rules, or to the `human_poc` rules. Fragmentation stays frozen as adopted.
If prose or markup junk takes a **target** or **`human_poc`** PASS, freeze and report a scientific
correctness defect before remediating anything.
