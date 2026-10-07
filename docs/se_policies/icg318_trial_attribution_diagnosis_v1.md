# ICG318_TRIAL_ATTRIBUTION_DIAGNOSIS v1 — which trials are ICG318? (diagnosis only)

**Status:** FROZEN 2026-10-06. No behaviour was changed.
**Baselines:** `~/se_runs/{tac01,mint5}_ncitid_v1`. Frozen evidence:
`research/se_icg318/evidence_v1.txt`, taken from the sealed CT.gov records. There is no NCIt,
ChEMBL or Open Targets record for ICG318 or for any iCell cCAR. No sponsor documents or
publications were used: the one reference, PMID 41669912 on NCT05474885, is a pregnancy case
report and was not read.

## 1. Frozen trials

The frozen set is every trial attached to `ICG318` or `BCMA-CD19 cCAR T cells`, plus every
trial whose sponsor protocol id names ICG318.

| Trial | Current asset | Sponsor protocol id | Start | Intervention as registered |
|---|---|---|---|---|
| NCT07328581 | ICG318 | ICG318-001 | 2026-09 | "ICG318, BCMA-CD19-IL-15/IL-15 sushi Compound CAR T" |
| NCT07544160 | ICG318 | ICG318-002 | 2026-04 | same; "armored, compound CAR" |
| NCT07715136 | ICG318 | ICG318-003 | 2025-03 | same; "armored, compound CAR" |
| NCT06787989 | BCMA-CD19 cCAR T cells | **ICG318-ITP-01** | 2024-08 | "BCMA-CD19 cCAR T cells" (no armour stated) |
| NCT06794008 | *BCMA-CD19 CAR-T therapy* (a third asset) | **ICG318-AAV-02** | 2024-12 | "BCMA-CD19 CAR-T therapy"; sponsor Peking University People's Hospital |
| NCT05474885 | BCMA-CD19 cCAR T cells | **ICG180-001** | 2022-04 | "BCMA-CD19 cCAR T cells" |
| NCT04162353 | BCMA-CD19 cCAR T cells | **ICG185-001** | 2019-07 | "BCMA-CD19 cCAR … two distinct functional CAR molecules" (no armour) |

**Corroborating convention, from iCell's own records in the same corpora.** The
protocol-id prefix tracks the construct in every case:

| Prefix | Construct |
|---|---|
| ICG133 | CD20-CD19 cCAR |
| ICG134 | CD19 CARvac |
| ICG182 | BCMA-CS1 cCAR |
| ICG185 / ICG180 | BCMA-CD19 cCAR |
| ICG318 | BCMA-CD19-IL-15/IL-15sushi cCAR |

None of the 9 iCell records contradicts the convention.

## 2. Classification

| Trial | Verdict | Basis |
|---|---|---|
| NCT07328581, NCT07544160, NCT07715136 | **A** | The intervention record names ICG318, and the protocol id matches. |
| NCT06787989 | **A** | The sponsor protocol id is `ICG318-ITP-01`, from the same sponsor. The intervention text is the family name; nothing in it contradicts ICG318. |
| NCT06794008 | **A**, on weaker evidence | Protocol id `ICG318-AAV-02` only. The sponsor is a hospital (investigator-initiated), and the intervention is a generic descriptor. |
| NCT04162353 | **B** | Protocol code ICG185, a different code. The description says "two distinct functional CAR molecules" with no IL-15 armour. It started in 2019, before any ICG318 record. |
| NCT05474885 | **B** | Protocol code ICG180, a different code, with no armour stated. Whether ICG180 and ICG185 are one product is **D, unresolved**. |

**What ICG318 is:** a later, **armoured** version of iCell's BCMA-CD19 cCAR: the same two
CARs plus IL-15/IL-15sushi. It is not the same product as the 2019–2022 cCAR trials.
"BCMA-CD19 cCAR" is a **construct-family name** that iCell uses for ICG185, ICG180 and
ICG318 alike. It is not an alias of any one of them.

## 3. Architecture

- **Not a whole-product merge.** Merging `BCMA-CD19 cCAR T cells` into ICG318 would attach
  two B trials, ICG185 and ICG180, to ICG318.
- **Not an alias relationship.** The family name denotes several products.
- **Trial-level reattribution is the right structure.** A trial whose own sponsor protocol id
  carries a product code identical to an existing coded asset belongs to that asset,
  whatever descriptor its intervention uses. For this case:
  - ICG318 would take NCT06787989 and NCT06794008;
  - `BCMA-CD19 cCAR T cells` would keep only ICG185 and ICG180;
  - the third asset, *BCMA-CD19 CAR-T therapy*, would be emptied.

**Generality check (exploratory, not frozen).** The protocol-id → existing-asset match was
tried over both benchmarks. It finds real reattributions beyond ICG318, for example
`JWCAR029-005/-007/-017` on *CD19-targeted …* descriptor assets, which belong to relma-cel.
It also finds noise. Antigen-shaped prefixes (`CD19-005`, `CD19 CAR ALL`) match an asset
named `CD19`, and other prefixes are sponsor protocol series rather than product codes
(`STK-009-…` on SYNCAR-001, `PLAT-02`). A production rule therefore needs:
- its own frozen population;
- exclusion of antigen/generic prefixes, reusing the generic-designator vocabulary;
- the target asset to be a coded product, never a generic descriptor;
- manual verification of every reattribution.

**Recommendation.** Preregister **PROTOCOL_ID_TRIAL_ATTRIBUTION**, a general trial-level
reattribution rule, as its own milestone, after the frozen-population diagnosis above. It
must move trials, not merge assets. That needs a new reversible registry operation, because
`apply_merge` works on whole assets. It must contain no ICG318-specific names or ids.
