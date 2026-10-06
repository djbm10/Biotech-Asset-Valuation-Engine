# NCIT_PRODUCT_IDENTITY v1 — assets linked to one NCIt product concept are one product (preregistration)

**Status:** PREREGISTERED 2026-10-05. No implementation exists.
**Operator decision:** 2026-10-05, Option A, with the generic-designator guard (Option A of
the follow-up fork).
**Baselines:** `~/se_runs/{tac01,mint5}_ncitmod_v1`, ranked under ranking v2.

## 1. Problem

Names the NCIt product concept files as synonyms stay separate assets when no source offered
them together and ChEMBL holds no record uniting them. Examples: ALLO-501A and cemacabtagene
ansegedleucel, CRC01 and anbalcabtagene autoleucel, GC022 and GC022F. TAC01 has 17 such
concepts and mint5 has 16.

**Supersession.** The standing rule that kept GC012F and AZD0120 apart was set when the
only evidence was registry co-occurrence. NCIt C175471 files both as synonyms of one product
concept, which is stronger identity evidence. That rule is **withdrawn**. No pair-specific
exception exists in either direction. CNCT19 and inaticabtagene are not affected: they share
no NCIt concept in the frozen population.

## 2. Rule (frozen)

**P1. Link.** An asset's NCIt link is the adopted unambiguous link (`ncit_target_sidecar_v1`
§3.5): the same names (canonical name, aliases and authority names) and the same
`NcitTargetAuthority.link`. Ambiguous links never take part.

**P2. Product concept.** Only concepts in the NCIt product sidecar take part. That sidecar
holds product concepts only, never classes, regimens, procedures or parent concepts. Every
link disposition takes part (`emit` and every non-emitting reason). Identity does not depend
on whether NCIt's target set was emitted.

**P3. Generic-designator guard (identity only).** An asset takes no part if **every one of
its own names** (canonical name and aliases, not authority-supplied names) matches this
grammar, case-insensitively:

```
^CAR(?:[\s-]?T)?[\s-]?[1-9]\d{0,2}$
```

That is: a modality token (`CAR`, `CART`, `CAR-T`, `CAR T`), an optional separator, and a
1–3-digit antigen designator with no leading zero. It matches `CAR19`, `CART19`, `CAR-T19`,
`CAR-T 19`, `CAR22` and `CART-22`. It does not match sponsor codes with zero-padded serials
(`CAR039`, `CAR-011`), named products, or any other short string.

Rationale: NCIt sometimes files a generic construct label as a synonym of one named product.
That label is valid evidence for target and modality, but it cannot establish which product
a registry entry is. The guard changes nothing else. A guarded asset keeps its NCIt link, its
target fact, its modality, its qualification and all of its own trials.

**P4. Group.** Participating assets are grouped by NCIt code. A group with at least 2
participants merges.

**Not consulted:** shared parent or class membership, name similarity, target overlap,
sponsor overlap, trial co-occurrence, sponsor counts and trial counts. The sponsor table in
`research/se_ncit_identity/member_sponsors_v1.txt` is the diagnosis that justified P3. It is
not an input to the rule.

**Merge mechanics.** The existing reversible `propose_merge` / `apply_merge` is used, with:
- `deterministic_basis = "ncit_product:<code>"`;
- survivor = the member whose canonical name sorts first, casefolded, then by asset id.

Every member's names stay aliases of the merged asset. Trial ids, mention ids and claims are
unioned, as `apply_merge` already does. The pass runs in the IDENTITY stage after
`consolidate_arm_variants`, and its redirects are chained the same way. The NCIt sidecar
token is already recorded and fail-closed on replay.

**Out of scope:** target, modality, qualification, efficacy and ranking code.

## 3. Frozen population (enumerated and verified before code)

The population is `research/se_ncit_identity/population_v2.json`
(sha256 `ec8c28305cc1010a5ac7932aff6b3809d8f6bf16dbbbe8e9d1ac56b94bebad77`). It was enumerated
from `*_ncitmod_v1` with the grammar above: 33 groups, 17 in TAC01 and 16 in mint5.

**Manual verification.** Each group was checked against the frozen NCIt synonym list and the
lead sponsors of every member's trials.
- **32 groups are one product, and every member merges.** The 3 non-obvious groups:
  - C175471 AZD0120 / GC012F: Gracell's product, now AstraZeneca's;
  - C171093 GC022 / GC022F: same hospital sponsor;
  - C205068 HBI0101 / NXC-201: the Hadassah product licensed to Nexcella.
- **C102758 (tisagenlecleucel) in both benchmarks.** KYMRIAH, tisacel and Tisagenlecleucel
  merge. **`CART19` stays separate** under P3. Its 33 trials come from 14 sponsors and cover at
  least 10 distinct products, including MB-CART19.1, PACE CART19, allogeneic CART-19 and RNA
  CART19.

No other asset in either benchmark is changed by P3 inside a merge group. Other all-generic
assets exist (for example `CAR22`, `CART20`), but none sits in a multi-member NCIt group.
**0 false merges are expected.**

## 4. Acceptance (frozen)

Sealed replays go into new directories. Identity, facts and gates are compared against raw
`*_ncitmod_v1`. Ranking is compared against `*_ncitmod_v1` rebuilt under ranking v2 at HEAD.
Determinism comparisons exclude `created_at` and `applied_at`, declared now.

- **P-1.** Exactly the frozen groups merge by this route, with exactly the frozen members.
  Nothing else merges by it.
- **P-2.** Zero false merges, by P-1 plus §3. No product-specific member is excluded by P3.
- **P-3.** Provenance: each merged asset lists every member name among its aliases and the
  union of its members' trial ids. `CART19` keeps exactly its own trial ids, and none of
  them appears on the tisagenlecleucel survivor unless that survivor's members already
  held it.
- **P-4.** Assets outside the merged groups are unchanged: identity, facts, gates,
  qualification, `construct_target_set` and modality. For a merged asset, each decision must
  equal its members' decision wherever all members agreed.
- **P-5.** Ranking code is unchanged. Every top-50 movement is an absorbed duplicate leaving,
  a backfill, or a survivor whose key changed because of the union. Retained relative order
  is otherwise preserved.
- **P-6.** Two TAC01 replays are identical, timestamps excluded.
- **P-7.** `tests/se` and ruff pass.

## 5. Stop condition

- **Adopt** if P-1 to P-7 all pass.
- **Otherwise** record the failure and revert. Do not tune the grammar or the link rule.
