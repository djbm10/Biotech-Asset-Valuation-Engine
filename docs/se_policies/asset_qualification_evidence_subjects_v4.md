# Asset qualification v4 — evidence subjects

Status: **PREREGISTERED** 2026-09-24. Parent commit: `918512a`. Supersedes
`asset_qualification_tiered_evidence_v3.md` (FAILED_ACCEPTANCE, see `docs/se_acceptance_log.md`).

Written and committed **before** any v4 code change and before any v4 measurement of the
acceptance corpus. Costs in §4 were measured against the v3 live artifacts (`mint3_on`,
`/home/djmann/se_runs/mint3_on`) and the sealed CT.gov snapshots, and are declared here so they
cannot be revised after seeing the v4 result.

## 1. Invariant (carried from v3 §1, unchanged)

No single weak evidence type may independently promote an ambiguous string into a canonical
therapeutic asset.

v4 adds a second invariant, which is what v3 actually violated:

> **An evidence record may only support a fact about the object it is a property of.**

v3 failed not because a threshold sat wrongly but because two structured fields were read as
statements about an asset when their subject was a different object — the arm, and the document.

## 2. Carried forward from v3 unchanged

These are adopted and must not regress:

- Named `QualificationReason` on every default-path asset; fail closed when no reason applies
  (v3 §3d). Zero anonymous admissions.
- SYNONYM / TRADE_NAME as *corroborative* tier, never self-qualifying (v3 §3a).
- Construct description as corroboration, not qualification (v3 §3b).
- Separator-insensitive lexicon authority in `drug_name_shape` (81,243 direct /
  49,832 corroborative).
- The tri-state comparator role (`COMPARATOR` / `THERAPEUTIC` / `UNKNOWN`) and its conservative
  aggregation into `comparator_observations` / `therapeutic_observations` /
  `unknown_observations`.
- The cleaned human-PoC population (33 passers in `mint3_on`, `choice` removed).
- The v3 §4/§4a declared recall costs (58 assets) remain declared and are not re-litigated.

## 3. The three changes

### 3a. Arm type is contextual evidence about the arm, not about the intervention

`type` on a CT.gov `armGroup` describes the arm. A blinded design types an arm `EXPERIMENTAL`
while listing both the active drug and its own placebo as interventions of that arm — 100 such
arms in this corpus. Projecting arm type onto every intervention in the arm is therefore invalid,
and is what gave bare `Placebo` 15 THERAPEUTIC observations.

The rule, stated as a subject rule:

1. `COMPARATOR` is conferred only by an **intervention-specific** relationship: an arm typed
   `PLACEBO_COMPARATOR` / `SHAM_COMPARATOR` whose intervention set is a single intervention.
   In that case the arm type is unambiguously about that one intervention.
2. An intervention-specific `COMPARATOR` observation is **dominant**: it is not cancelled by
   `THERAPEUTIC` observations derived from arm type, because the latter are contextual and the
   former is entity-specific.
3. `THERAPEUTIC` continues to be read from arm type as in v3. It is contextual, and it is
   overridden per (2), but it is not removed — removing it was measured and rejected (see §4c).
4. Where neither applies, the role is `UNKNOWN` and confers nothing.

A structurally identified placebo/control therefore remains `COMPARATOR`, while a real drug
co-administered inside a multi-intervention control arm keeps its role.

`is_comparator_only()` and the §3c v3 requirement that `STRUCTURED_THERAPEUTIC` needs a
therapeutic observation are unchanged.

### 3b. A lone company co-occurrence cannot corroborate identity

`entity_specific_link` must mean an explicit asset↔company relationship: structured ownership or
sponsor attribution (CT.gov `leadSponsor`; a mention-level `company_name` produced by an extractor
that attributed the company to the asset), or an explicit textual attribution of the form
"Company's X".

A document's **publisher** is not such a relationship. `corpus.py:217` assigns
`company_name = document.publisher` whenever the publisher is not in a small generic set; "AACR"
is not in that set, so the venue became the corroborating company for every asset mentioned in an
AACR abstract. Appearing in the same document as a company name is co-occurrence, not
entity-specific corroboration.

v4 therefore drops publisher-derived company attribution from the company evidence that
`_has_entity_link` consults. Trials and targets are unaffected.

### 3c. Revert the unpreregistered abbreviation-gloss widening

v3 §3e said the abbreviation-gloss veto *stays*. Wiring one evidence record for both the mention
disposition and the qualification reason silently widened it into default-path routing, costing
SYNCAR-001 (whose every mention is parenthetical). The veto returns to exactly where v2/v3
preregistered it — mention disposition — and is removed from `qualification_reason`.

## 4. Declared recall cost

### 4a. Cost of 3a

Corpus-wide, exactly **19** interventions carry an intervention-specific comparator observation.
Exactly **1** default-path asset changes disposition: bare `Placebo` (comp=20, ther=15 → no
reason). Positive controls measured unaffected: `HB2198` 0 comparator / 1 therapeutic,
`teclistamab` 0/9, `pomalidomide` 0/15. The 339-asset dual CD19/BCMA CAR-T population has no
comparator observations at all and is untouched.

**Declared cost of 3a: 1 asset, which is a frozen negative.**

### 4b. Cost of 3b

100 default-path assets have a company as their only entity link, and in every one of the 100 that
company is **AACR**. There are zero structured-sponsor-only corroborations in this population, so
no explicit asset↔company relationship is lost. Removing publisher corroboration demotes **64**
assets to review.

Composition of the 64, declared in advance:

- Cell lines: `HEK293`, `HL-60`, `HT29`, `SW620`, `HCT116`, `MCF10A`, `RPMI8226`, `LN229`,
  `HT1080`, `ME180`, `SN12`, `BT474`, `SCC68`, `SCC15`, `KTCTL-140`, `LN1436`
- Gene/protein symbols: `TNFRSF19`, `TNFRSF16`, `OX40`, `CXCL10`, `CXCL12`, `SOX11`, `STK11`,
  `BRAFV600E`, `INTS12`, `FMC63`, `PE38`, `DR18`
- Reagents / tool compounds / vehicles: `PD98059`, `LY294002`, `PKI166`, `PLX4720`, `forskolin`,
  `AM1241`, `Crystal violet`, `saline`, `serum albumin`, `whole blood`
- Prose and measures: `tetravalent`, `neoadjuvant`, `adjuvant`, `approval`, `balance`, `CARTOX-10`,
  `ED50`, `ThioMab`
- The six frozen negatives gained by v3: `equal`, `nature`, `roche`, `saline`, `search`, `success`
- **Genuine therapeutic assets lost: `GNC-038`, `STK-009`, `EPC-001`, `BT7480`, `API-192`,
  `JY108`, `EDP001`, `ABO2015`, `DDT01`, `AT101`, `anlotinib`, `Gleevec`, `CAR-12` (≈13).**

These 13 are a real and accepted cost. They are literature-only mentions whose sole entity is the
venue; under §1 they are correctly held for review rather than admitted on co-occurrence. They are
not lost from the corpus — they remain candidates in the review section. Recovering them requires
a genuine asset↔company or asset↔trial link, which is future work and explicitly **not** a reason
to weaken §3b.

**Declared cost of 3b: 64 assets demoted to review, of which ≈13 are genuine.**

### 4c. Rules measured and rejected before preregistration

Recorded so they are not retried:

- *Arity rule applied to THERAPEUTIC only* (an `EXPERIMENTAL` arm with >1 intervention confers no
  THERAPEUTIC): still leaves `Placebo` therapeutic via 2 sponsor-typed placebo-only experimental
  arms (NCT01981499, NCT04656535), and destroys 3,445 of 4,540 therapeutic observations.
- *Full symmetric arity rule*: default path 1,188 → 849, losing 339 assets that are exactly the
  dual CD19/BCMA CAR-T population under study (`FIT-(BCMA+CD19)-CAR-T Cells`,
  `BCMA/CD19 Dual-Target CAR-T`, …). Rejected.

### 4d. Cost of 3c

Restores SYNCAR-001 to the default path. No other asset measured affected.

## 5. Acceptance bar (the user's v4 bar, adopted verbatim)

1. `Placebo`, `choice`, `paper`, `frontline`, `bsAbs`, `POD24`, `equal`, `nature`, `roche`,
   `saline`, `search`, `success` → **not** default-path.
2. **Zero** non-assets with a decisional PASS.
3. SYNCAR-001 and all prior real positive controls survive.
4. No real human-PoC asset lost.
5. Every default-path asset still has a qualification reason (zero anonymous admissions).
6. Top 10 essentially real therapeutics.

Validation is a **fresh paired same-day live acquisition**: `mint4_on` in `bve-b8` at the v4
commit, `mint4_off` in `bve-mintoff` at the v4 parent. Sealed replay is not the adoption test for
anything that changes which names qualify. Scored by `scripts/se_v3_headline_report.py`.

## 6. Not to be done under v4

- No hand-written blacklist of names.
- No weakening of target or `human_poc` rules.
- No threshold tuning after seeing the acceptance corpus.
- No change to fragmentation (frozen as adopted).
- No ranking or ordering change. Ranking work begins only if this bar passes.

## 7. Amendment A1 — 2026-09-24, before measurement

**Direction: narrowing.**

§3a(1) as written says `COMPARATOR` is conferred *only* by an intervention-specific arm. The
implementation instead keeps v3's existing channel reading — a control arm confers `COMPARATOR`
on the interventions it lists, whatever its arity — and *adds* intervention-specificity as the
condition for **dominance** over contextual `THERAPEUTIC` evidence.

Both readings fix `Placebo`. They differ for a name observed only in multi-intervention control
arms: the strict reading gives it no role at all, the implemented reading calls it a comparator.
The implemented reading therefore withholds more names from the default path, which is the
conservative direction and preserves v3's comparator-only population (`Matched Placebo`,
`Placebo Comparator`, `Placebo (matched to IVA)`, `Placebo (matched to TEZ/IVA)`) without
re-deriving it.

Recorded here, before the v4 paired run, rather than left as an undeclared divergence. The
declared cost in §4a is unchanged: dominance is what moves `Placebo`, and dominance is measured.

Amendment A2 — the self-contradiction exception in §3a is implemented as an explicit carve-out:
where the arm *labels* read an intervention as therapeutic, dominance does not fire. This is the
v2 HB2198 lesson, which §3a assumed but did not state. Direction: narrowing (it withholds a
comparator label the strict text would have applied). Frozen as a test.

## 8. Amendment A3 — 2026-09-24, before the paired run

**Direction: narrowing.** Entity-specificity is **symmetric**.

§3a(1) defined an intervention-specific comparator as the sole occupant of a control arm. Measured
against the sealed CT.gov snapshots, that reading also captured **Descartes-08** (NCT04146051), a
real BCMA cell therapy in generalized myasthenia gravis and squarely inside the query population.
Its sponsor typed the randomized phase `PLACEBO_COMPARATOR` and listed Descartes-08 as that arm's
only intervention — the arm is named for its *design*, not its material — while the same drug is
the sole occupant of two `EXPERIMENTAL` arms in the same record.

Dominance therefore does not fire where the same intervention is *also* the sole occupant of a
therapeutic arm in that protocol. A record that speaks entity-specifically on both sides is
contradicting itself, and the conservative reading of a self-contradicting record is that it did
not say — the same principle as the HB2198 label carve-out in A2.

Re-measured blast radius after A3, on the sealed snapshots: **11** names carry a specific-comparator
observation and dominance changes the verdict for exactly **3** — `Placebo`, `standardofcare`,
`bodycompositionmonitoring`. None is an asset. `HB2198`, `teclistamab`, `pomalidomide`,
`gemcitabine`, `pembrolizumab` and `Descartes-08` are all untouched and purely therapeutic.

This supersedes the §4a figure of 19 specific-comparator interventions, which was measured under
the asymmetric reading. The declared cost of §3a is unchanged at **1 default-path asset, a frozen
negative**.

Implementation note: dominance has to act at the **asset** level, not within a protocol. Bare
`Placebo` is the sole occupant of 24 control arms and is listed beside the active drug inside 13
blinded `EXPERIMENTAL` arms in *other* protocols; a per-protocol rule leaves those 13 therapeutic
observations standing and `Placebo` qualifies anyway. `CanonicalAsset.specific_comparator_observations`
carries the count so the dominance survives aggregation.
