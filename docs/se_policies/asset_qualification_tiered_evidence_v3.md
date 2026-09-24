# Asset qualification v3 — tiered evidence and named reasons

Preregistered 2026-09-23, before any v3 code change and before any v3 measurement.
Parent: `0e8beec` (v2, `FAILED_ACCEPTANCE`). Supersedes
`asset_qualification_single_authority_v2.md` on §3b and §3d; §3a (one authority) and §3c
(prose needs an entity) are carried forward unchanged.

## 1. The invariant this policy exists to enforce

> No single weak evidence type may independently promote an ambiguous string into a
> canonical therapeutic asset.

v2 collapsed qualification into one function, which was correct and insufficient. The
function's body is a three-way disjunction, and each disjunct was unconditional and
anonymous. Two of the three admitted non-therapeutics on live data. Collapsing routes
further is not the fix; naming and grading them is.

## 2. What the v2 paired live run established

Measured on `mint2_on` / `mint2_off`, same query and source index, `--as-of 2026-09-23`,
2,902 candidates each side. v2 cleared nine of eleven frozen negatives and lost no real
asset, then failed on three findings:

| finding | route | evidence |
|---|---|---|
| `paper` is a default-path asset, shortlist #10 | `is_identity_bearing_drug_name` | `paper` is a ChEMBL `SYNONYM`. Excluding `TRADE_NAME` removed `frontline`/`choice`/`discase` but not synonym-carried ordinary words. `water` is worse: it is an `APPROVED_NAME`. |
| `choice` is a default-path asset holding a `human_poc` PASS | `identity_authority` (construct description) | Fails every other route (0 trials, 0 owners, 0 targets, not structurally typed). Its `target_assertions` resolve to **VKORC1** — the drug→target authority matched the warfarin brand "Choice". |
| bare `Placebo` is a default-path asset, shortlist #1; `HB2198` (a real tetravalent bispecific) was pushed to `low_support` | `structurally_typed_drug and not comparator_role` | `comparator_role` is one boolean merged with `all()` over an asset's whole trial set. One untyped arm among 35 trials clears the flag permanently, so bare `Placebo` escaped; the decorated one-trial variants (`Matched Placebo`, `Placebo Comparator`, …) were caught. `HB2198` was flagged comparator, which means the intervention↔arm association itself is suspect, not only the aggregation. |

## 3. The rules

### 3a. Ontology evidence is tiered by alias type

Directly qualifying — the ontology asserts what the molecule *is*:

- `APPROVED_NAME`
- `canonical_symbol` / `label` (the record's own canonical name)
- `DEVELOPMENT_CODE`

Identity-only, corroborative — may resolve a mention to a parent asset, may **not** place
that string on the default canonical path by itself:

- `SYNONYM`
- `TRADE_NAME`

`XREF` remains excluded from both: a database accession is not a name a document uses.

A corroborative-tier match needs one independent qualification route to reach the default
path. It keeps its full nomination and resolution behaviour either way; nothing is deleted.

### 3b. Construct/target description is corroboration, not a route

`identity_authority` derived from a construct or target description ceases to be a
standalone qualifier. It may support an otherwise plausible asset identity. It cannot
establish that an arbitrary string denotes a therapeutic. `choice` is the mandatory
negative control: a target statement about VKORC1 says nothing about whether the English
word "choice" is an asset.

### 3c. Comparator role is observation-level and tri-state

Per observation, from the source's own structure:

- `COMPARATOR` — the structured source explicitly places this intervention in a
  comparator/placebo/control relationship.
- `THERAPEUTIC` — explicitly experimental or active treatment.
- `UNKNOWN` — the arm relationship is missing or ambiguous.

Aggregation, conservatively:

- comparator observations plus unknowns only → **comparator-only**; not a canonical
  therapeutic asset.
- at least one genuine `THERAPEUTIC` observation → the asset may qualify.
- `UNKNOWN` never erases an explicit `COMPARATOR` observation. This is the rule `all()`
  violated in the opposite direction.
- a comparator label attached to one intervention must not contaminate a different
  intervention. The intervention↔arm linkage is to be verified directly, not assumed from
  arm membership order or position.

Frozen opposite controls: bare **`Placebo`** must be comparator-only; **`HB2198`** must
carry a therapeutic observation and survive.

### 3d. Every default-path asset carries a machine-readable reason

`qualification_reason`, one of:

- `DIRECT_APPROVED_NAME`
- `DEVELOPMENT_CODE_AUTHORITY`
- `STRUCTURED_THERAPEUTIC`
- `ENTITY_CORROBORATED_SYNONYM`
- `ENTITY_CORROBORATED_TRADE_NAME`
- `CONSTRUCT_CORROBORATED`
- `ENTITY_CORROBORATED_PROSE`

Anonymous admission is a defect. An asset that reaches the default path without a
recognized reason **fails closed to review**. This is what would have answered "why is
`paper` here?" in one line instead of a trace.

### 3e. Carried forward from v2, unchanged

One qualification authority (`qualifies_as_asset`); `is_protected` delegates and does not
decide. Prose-only unknowns need an entity-specific link (`trial_ids`, `company_ids`,
`target_ids` — never `discovery_target_context` or modality). `MIN_PHARMACOLOGIC_DOCUMENTS
= 2` and `MAX_DOCUMENT_FRACTION = 0.05` stay untuned. The per-occurrence modifier veto and
the abbreviation-gloss veto stay. Fragmentation stays adopted.

## 4. Declared recall cost, measured before the v3 run

Measured against `mint2_on`'s 1,240 default-path assets, by re-tiering their names against
the frozen ontology snapshot. Recorded here so it cannot be revised after the result.

| tier of name | default-path assets | have an independent route | would leave the default path |
|---|---|---|---|
| directly qualifying | 525 | — | 0 |
| `SYNONYM`-only | 55 | 16 | **39** |
| `TRADE_NAME`-only | 23 | 8 | **15** |
| in no tier (ontology-absent) | 637 | — | unchanged |

**Total declared cost: 54 assets leave the default path.**

Of the 39 synonym-only losses, ~17 are genuine therapeutics: `efgartigimod`, `Elahere`,
`MCC950`, `chidamide`, `donafenib`, `apatinib`, `RO4929097`, `Taxol`,
`hydroxydaunorubicin`, `amphotericin`, `mycophenolate`, `azatioprina`, `Ogsiveo`,
`botulinum toxin`, `streptozotocin`, `Vincristin`, `tetrahydrocannabinol`. The remaining
~22 are excipients, reagents, foods and prose: `normal saline`, `liquid paraffin`,
`carbopol`, `charcoal`, `methanol`, `calcein`, `fibroin`, `chitosan`, `diazinon`, `yeast`,
`ginseng`, `Ginkgo biloba`, `Zingiber officinale`, `Bifidobacterium`, `hematocrit`,
`revolution`, `Farma`, `Zenas`, `CALLA`, `paper`.

All 15 trade-only losses are real marketed brands. The standing argument is that a brand
resolves to its parent and the parent qualifies on its own evidence; that argument was
checked on this corpus rather than assumed, and it holds for 12 of 14 checked:

- parent present on the default path: Enhertu, Trodelvy, Padcev, Polivy, Adcetris,
  Mylotarg, Lumoxiti, Tivdak, Benlysta, Soliris, Aspaveli, Ogsiveo.
- **parent absent from the corpus entirely: Fintepla (fenfluramine), Uptravi
  (selexipag).** These two are a real, accepted loss. Both are off-thesis for a
  CD19/BCMA autoimmune question; the cost is declared, not excused.

`choice` is the only demoted name holding a `human_poc` PASS, and it is a frozen negative.
**No real human-PoC asset is predicted to be lost by the tiering change.** If one is, that
is a failure, not a cost.

Ontology-wide, for the record: 81,243 directly-qualifying names, 36,523 synonym-only,
13,865 trade-only. Within the synonym-only tier, 1,612 are development-code shaped and 319
carry an INN stem — those ~1,931 are where a future recall problem would concentrate if
one appears.

### 4a. Addendum: the cost of requiring a therapeutic observation

Recorded 2026-09-23, after implementing §3c and before the v3 run. §3c adds a requirement
§4 did not price: the structured-typing route now needs one `THERAPEUTIC` observation, so
any asset whose structured declaration carries no readable arm relationship also leaves the
default path. Measured against `mint2_on`'s sealed CT.gov snapshots and its 1,240
default-path assets:

- 1,872 of 1,910 protocols that declare interventions also declare arm groups; 7,168
  therapeutic, 122 comparator and 114 unknown observations resolve across them.
- 268 default-path assets are structurally typed; 169 of those depend on the structured
  route because their names are neither directly qualifying nor development-code shaped.
- **4 of the 169 lose it**: `CD19/BCMA CAR-T` (one `UNKNOWN`), `LTB4`,
  `Fludarabine, Thiotepa, Melphalan, Thymoglobuline (ATG)`, `Noninterventional`.

Only the first is arguably an asset, and it is a bare class description with more than
twenty sibling variants that keep the path. **Declared cost: 4 more assets, total 58.**
The descriptive dual CD19/BCMA CAR-T population -- the thesis-relevant names this route
exists to protect -- is unaffected.

## 5. Acceptance bar

PASS requires **all** of:

1. Every default-path canonical asset has an auditable `qualification_reason` from the
   single authority. Zero anonymous admissions.
2. None of these is a default-path asset or holds a decisional PASS: `Placebo`, `choice`,
   `paper`, `frontline`, `bsAbs`, `POD24`, `ASCO 2023`, `NEJM 2011`, `WHO 2022`,
   `PRISMA 2020`, `IQR 124`.
3. These survive: `HB2198`, `AMG 420`, `ALLO-715`, `ABBV-383`, `gemcitabine`,
   `pomalidomide`, `teclistamab`, `pembrolizumab`, `belantamab mafodotin`, and the
   repaired multi-token cell therapies.
4. No real human-PoC asset lost.
5. Comparator classification fires on live data, with bare `Placebo` comparator-only and
   `HB2198` therapeutic.
6. Losses beyond the 54 declared in §4 are reported as losses, not absorbed.

Validation is a paired same-day fresh acquisition: v3 worktree and a control at the parent
commit, same query, same source index, same `--as-of`. Sealed replay is not the adoption
test, because the tiering change alters which names qualify.

Headline report, in this order: (1) non-assets with default-path status; (2) non-assets
with any decisional PASS; (3) real assets lost; (4) human_poc real assets lost/gained;
(5) comparator classification counts; (6) `qualification_reason` distribution; (7) top-10
shortlist composition.

## 6. Not to be done

No hand-written blacklist. No threshold tuned after seeing the acceptance corpus. No
change to target rules or `human_poc` rules. No ranking or shortlist-ordering work until
the population passes this bar. No mutation of sealed corpora.

Standing stop condition: if prose or markup junk receives a **target** or **`human_poc`**
PASS, freeze and report a scientific correctness defect before remediating anything else.
