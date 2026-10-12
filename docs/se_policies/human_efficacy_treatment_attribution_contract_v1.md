# HUMAN_EFFICACY_TREATMENT_ATTRIBUTION_CONTRACT v1

**Decision: DESIGN COMPLETE / ARCHITECTURAL EXTENSION REQUIRED. Human-PoC behavior is not implementation-ready.**

The 33-row audit is complete. None of the 14 previously unresolved rows acquires
safe **asset-specific efficacy ownership** from the captured evidence. Nine do
establish that the outcome cohort received the candidate as a regimen component.
That receipt edge is useful, but it cannot license the component to inherit the
regimen's efficacy. Clinical-content labels and the quantity contract remain
unchanged; this is not another numerical-content failure or a holdout rescore.

Baseline: `867275c`. Evidence and control population frozen before evaluation in
**eaf98d2**. No production, extraction, identity, protocol, qualification, target,
indication, modality, ranking or routing change. No live searches or replays.
H6–H10 remain **UNRUN**; H16–H20 remain exposed diagnostic/development data.

## Evidence and scope of the audit

Packet: `research/se_human_efficacy_treatment_attribution_contract_v1/`.

- `attribution_table.md` and `attribution_audit.json`: every one of the 33
  witnesses, candidate and accepted names, exact passage/cohort spans, trial and
  arm information where present, regimen components, edge basis, separate
  receipt/efficacy-owner decisions, expected scoped human-PoC decision and reason.
- `candidate_evidence.json`: candidate records, existing identity edges, trial
  memberships/reattributions, other human-PoC claims, structured clinical results,
  and candidate-connected registry documents. Another claim is never substituted
  for the frozen witness or used to certify a different outcome cohort.
- `structured_registry_evidence.json`: captured registry identification, protocol
  IDs, arms, interventions, both directions of arm linkage, aliases, publication
  references and snapshot hashes for candidate-related and publication-linked
  records. This is source evidence, not newly inferred attribution.
- `capture_inventory.json`: original result hashes and per-run scan counts.
  All seven original result files were hash-verified. Across those runs,
  **9,359 registry document entries** were inspected (includes repeated snapshots
  across runs). Full captured abstract/title text was reviewed for the unresolved
  structures. Sources outside these captured runs were not searched.
- `negative_controls.json`, `positive_attribution_controls.json`,
  `structured_design_cases.json`, `design_freeze.json`: 65 existing negative
  controls, six existing positive attribution controls, and eight explicit
  structured-relation design cases, frozen before the contract check.
- `contract_checks.json`: grounded-record checks and unchanged current-reader
  control probes. This is **not an automatic text-to-attribution classifier**.

For the 14 unresolved rows, no publication NCT/derived-reference bridge or
verified protocol designation establishes the relevant registry result arm.
Candidate-associated trial records do exist for some assets; they are not the
same evidence. Literal protocol/acronym matches such as COMPLETE, CONTROL,
CAR-T, Cell therapy or Atazanavir are recorded as rejected lexical leads.
Ordinary use of an acronym or drug name is not identification of that study.
The audit does not amend the existing protocol attribution subsystem.

All selected candidate records have zero captured normalized ClinicalResult
records. The scanned CT.gov snapshots are protocol payloads with no captured
resultsSection; this does not assert that CT.gov never published results. The
source adapter materializes the protocol, and its current outcome extractor
creates explicitly incomplete endpoint records rather than result-arm effects.

## What structured evidence already supplies

| Existing location | Available information | Attribution limit |
|---|---|---|
| Raw `identificationModule` | NCT ID, organization study/protocol ID, sometimes acronym/secondary IDs | Trial membership does not identify which result cohort received which treatment. |
| Raw `armsInterventionsModule.armGroups` | Arm labels, types, descriptions, `interventionNames` | A protocol arm is planned structure, not an observed efficacy result group. |
| Raw interventions | Name, type, description, `otherNames`, `armGroupLabels` | Names/components must map to the same candidate under accepted identity evidence. |
| `referencesModule` | PMID/citation and reference type | BACKGROUND is not a result/study ownership link. DERIVED still needs cohort/arm alignment. |
| `TrialRecord.raw_payload` and snapshots | Opaque original protocol retained | Evidence is available without fetching it again, but no typed result-to-arm certificate exists. |
| Normalized `TrialIntervention` | Name, type, description, other names | No normalized arm/cohort/result linkage fields. |
| `CandidateHit.arm_relationship` and candidate counters | Comparator/therapeutic/unknown observations | Aggregated role is not result-specific intervention receipt. |
| `ClinicalResult`, `CohortAssignment`, `EfficacyStatement` | Subject/result IDs, clinical population/endpoint fields or sentence/value | They do not carry a proved result-group→arm→intervention→asset chain or regimen ownership scope. |

Existing `_arm_relationships()` already inspects both forward and reverse
links and warns about contradictions with arm labels. The new contract must
preserve that caution; agreement of two entered fields cannot override an
explicitly conflicting arm description/label. No new normalization is applied.

Concrete checks from the frozen population:

- **Obexelimab / NCT05662241:** arm `ZB012` maps to Drug: Obexelimab; the placebo
  arm maps to Other: Placebo. The paper identifies the trial and reports the
  obexelimab cohort's outcome. Prose already provides the treatment edge;
  registry structure corroborates it without transferring placebo results.
- **CNCT19 / NCT02975687:** the publication identifies the trial, whose `Arm A`
  lists Biological: CD19 CAR T cells. That generic intervention has no CNCT19
  alias in the captured intervention record or accepted edge for this trial.
  It does not independently prove same-product identity. Direct CNCT19-treated
  patient prose already supports the existing witnesses, so no generic-CAR-T
  identity or trial-level inheritance is needed.
- **Glepaglutide / NCT03690206:** separately labeled twice-weekly, once-weekly
  plus placebo, and placebo arms have explicit intervention links. The twice-
  weekly prose outcome aligns with a particular treatment schedule; the arm
  distinctions must survive normalization.
- **ROSE-010:** its paper appears as a **BACKGROUND** reference in NCT02731664.
  That registry citation cannot assign the paper's efficacy to this study's
  arms. The frozen paper's explicit dose/placebo result stands on its own.
- **Relugolix / NCT04714554:** this is an erythromycin/PK interaction study,
  not the frozen fibroid-efficacy cohort. It separately names Relugolix/E2/NETA
  FDC (other name Rel-CT) and Relugolix (MVT-601/TAK-385). Merging those scopes
  or borrowing this PK trial's arms would create an unsupported attribution.

## Classification of the 14 unresolved positives

The counts below ask whether the **same frozen result can become an asset-
specific human-PoC fact**, not whether the drug was ever studied or ever given.

| Requested recovery category | Rows |
|---|---:|
| Safely certifiable for asset-specific efficacy from captured evidence | **0** |
| Blocked only by identity resolution | **0** |
| Recoverable by arm/regimen representation alone | **0** |
| Unsupported as asset-specific efficacy by the captured evidence | **14** |

The last count includes **12 regimen/pooled-result limitations and two
non-treatment candidates**. It does not mean all their clinical observations
are false or that no treatment receipt can be proved. Missing typed regimen
representation is an architectural problem, but representing a regimen cannot
supply a missing component-specific effect. Thus the representation-only count
is not inflated by cases that would still fail scientific ownership afterward.

| Frozen row(s) | First missing attribution boundary | Receipt | Efficacy ownership |
|---|---|---|---|
| Venetoclax, mint5 | D: VEN/AZA/IVO induction regimen owns the CR count | Component receipt certified | UNKNOWN |
| Venetoclax, AACR accepted | D: same regimen/result, separate frozen run row | Component receipt certified | UNKNOWN |
| PET30, AACR accepted | E/G: PET response-assessment stratum, not a treatment | UNKNOWN for this candidate | UNKNOWN |
| though, AACR accepted | E/G: conjunction in pooled CAR-T results, not a treatment | UNKNOWN for this candidate | UNKNOWN |
| Relugolix, H16 | D/E: result names relugolix combination therapy, not single-agent identity | Component receipt certified | UNKNOWN; not an alias-only repair |
| Glecaprevir, H16 | D: G/P regimen SVR | Component receipt certified | UNKNOWN |
| pibrentasvir, H16 | D: same G/P regimen SVR | Component receipt certified | UNKNOWN |
| bevacizumab, H16 | D: targeted-agent-plus-chemotherapy arm comparison | Component receipt certified | UNKNOWN |
| atazanavir, H16 | C/D/G: pooled backbone result lacks PI-specific result group | UNKNOWN for the particular outcome cohort | UNKNOWN |
| ritonavir, H16 | D: common boosting component of the compared pooled regimens | Component receipt certified | UNKNOWN |
| Lopinavir, H16 | C/D/G: no LPV-specific outcome stratum | UNKNOWN for the particular outcome cohort | UNKNOWN |
| Fosamprenavir, H16 | C/D/G: no FAPV-specific outcome stratum | UNKNOWN for the particular outcome cohort | UNKNOWN |
| Lamivudine, H16, DOR/3TC/TDF witness | D: 3TC is a component of the arm with 89% attainment | Component receipt certified | UNKNOWN |
| Lamivudine, H16, pooled backbone witness | D: 3TC belongs to the ABC/3TC backbone comparison | Component receipt certified | UNKNOWN |

Therefore **9/14 receipt-only edges** can be retained safely; three require
unavailable PI-stratified result/cohort assignment, and two have no therapeutic
candidate role. No receipt-only edge is promoted to a human-PoC fact.

The H16 bevacizumab result must not be confused with the two older bevacizumab
witnesses in the 33-row population. Those explicitly compare **with/without
bevacizumab** on a stated first-line platinum-based chemotherapy background.
Their named add-on arm is attributable in that observational context; it does
not establish monotherapy efficacy or a causal isolated incremental effect.
The H16 comparison changes the targeted agent and reports regimen-arm PFS,
without isolating bevacizumab's contribution. The distinction is structural,
not a product exception.

## Deterministic attribution contract

Return one of: **CERTIFIED efficacy attribution**, **CERTIFIED receipt only**,
or **UNKNOWN**. These are distinct from the unchanged content/quantity gate.
Only the first status may support a human-PoC fact, and only after the content
and quantity chain also passes. Confidence scores cannot upgrade UNKNOWN.

First establish source and scope prerequisites:

1. Identify one observed result assertion and its cohort/result group, source
   document and version. Planned endpoints or protocol enrollment are not
   observed results. Keep the actual quantity owner fixed.
2. Identify the complete administered treatment expression. Apply existing
   accepted identity/alias and regimen safeguards. The longest matching token,
   a target/modality description, sponsor, study membership, or shared protocol
   prefix does not establish same-product identity.
3. Separate whole treatment, regimen component, add-on context, prior/bridging
   therapy, comparator and background citation. Any conflicting intervention,
   arm, identity or cohort evidence gives UNKNOWN for the disputed edge.

Then evaluate these bases in order, retaining supporting evidence rather than
letting a weaker fallback override a contradiction:

**A — Explicit prose / accepted alias.** The result assertion directly relates
an accepted candidate treatment to its treated/evaluable cohort, or explicitly
reports that treatment's outcome in that cohort. An accepted alias has the
same standing as the canonical name, with its existing identity provenance.
Mere asset mention elsewhere does not qualify. A defined combination product
may own its whole-product result; its component words do not each inherit it.
An explicit with/without/add-on comparison may certify the named treatment
arm **with its background, observational/comparative and non-monotherapy
qualifiers retained**. Do not silently turn that arm outcome into an isolated
causal contribution or attribute it to every background component.

**B — Structured single-cohort/single-treatment proof.** Require a verified
study link, an observed result explicitly linked to the relevant treated
cohort, exactly one therapeutic treatment for that cohort, and a certified
same-asset intervention link. A trial with one active intervention and a
placebo arm is not a single-treated-cohort proof. “One drug listed in the
trial” cannot identify which patients produced a result. Protocol design or
an incomplete ClinicalResult supplies no observed effect.

**C — Structured result-arm proof.** Require an explicit result-group→arm
mapping, the correct study/version, and consistent arm→intervention evidence.
Use `armGroups[].interventionNames` and `interventions[].armGroupLabels` with
arm descriptions/types and conflict checks. Arm labels are source-local, not
global stable arm IDs. Preserve dose, schedule, crossover period, subset and
analysis population when relevant. Multiple trial arms cannot inherit each
other's outcomes. Single-asset assignment additionally requires that the
relevant treatment is that asset; multiple therapeutic components go to D.
Background references, generic acronyms, sample-size similarity and proximity
cannot fill missing links. A generic intervention description also cannot
replace an accepted same-asset bridge.

**D — Regimen semantics (mandatory gate on A–C and F).** Certify exposure as
receipt-only when the candidate is an explicit component of the result's
regimen. A whole regimen result belongs to the regimen. A component gains
asset-specific ownership only if the result itself explicitly separates its
own treatment arm/contrast; presence in the regimen is insufficient. Pooled
backbone comparisons cannot be distributed over each PI. Missing component-
specific results remain UNKNOWN even if every regimen member is known.
Parenthetical expansions, serial lists and alternative components obey the
same rule. Apposition and the targets in a defined dual-target product are
not automatically multiple drugs. Preserve existing positive controls for
whole products and existing negative controls for regimen leakage.

**E — Identity boundary.** When a treatment is explicit but accepted evidence
cannot certify equality to the candidate, keep UNKNOWN with identity reason
and provenance. Never invent aliases or merge components with fixed-dose
combinations. Correcting a non-treatment token such as a response stratum
would change the candidate entity, not resolve an alias of that candidate.
No identity resolution is performed in this milestone.

**F — Explicit discourse carry-forward.** Permit only an immediately adjacent
sentence in the same source section/study context, where a previously
established asset-treated cohort is referenced unambiguously as those/these
patients, its evaluable subset or an equivalent explicit cohort reference.
There must be one compatible antecedent treatment/cohort and no new arm,
intervention, cohort or section switch. No transitive window search. The
prior sentence must establish actual treatment, not manufacture, plans or
mere presence. Later bridging-therapy mention cannot reassign an earlier
other-drug outcome. Apply regimen and same-product checks to the linked
assertion, and preserve both spans as proof.

**G — Otherwise UNKNOWN.** No trial-level inheritance and no asset/query/article
exceptions. An unsupported efficacy-owner edge does not become supported
because a receipt edge, structured subject_id, or another paper is available.
The scientific distinction is between receiving a treatment and owning the
specific observed result under its reported scope.

## Negative controls and offline validation

The frozen controls include all **63 existing negative prose-reader inputs**
from the v1 population, plus previously frozen regimen controls **C055/C056**.
They include CT023's planned-endpoint form, the unnamed-result/manufactured-
asset control, other-drug results with bridging therapy elsewhere, plus-joined
combinations, R-CHOP/FCR/DVRd expansions, final alternatives, and serial lists.

On grounded design records: **65/65 remain UNKNOWN**. Six existing positive
attribution controls retain their original reader outputs (accepted alias,
whole combination product, and single-agent/apposition forms). Eight frozen
structured-relation cases check valid single-arm proof and reject wrong-arm,
missing-group, protocol-only, component, generic-identity, background-reference
and contradictory-map cases. Three previously frozen discourse cases preserve
the unique-cohort versus ambiguous/nonadjacent distinction.

The unchanged current reader was also probed directly: the 63 legacy negatives
and C055 remain rejected, while **C056 still incorrectly passes**. The proposed
regimen contract rejects C056 on its grounded multi-agent structure; no parser
fix has been deployed. This disclosed pre-existing defect must not be hidden
by claiming all raw-text negative tests now pass.

All 33 audit records match the recorded scientific decisions: 15 can support
scoped asset-specific efficacy if the unchanged content/quantity chain passes;
18 remain UNKNOWN (the four known numerical false witnesses and 14 unresolved
asset-ownership rows). This is not classifier accuracy or future generalization
evidence. Source-grounding annotations are manual. The automated checker
validates the contract's predicates on those records and verifies baseline
reader controls; it does not implement arbitrary prose/arm interpretation.

## Minimum architectural extension and next milestone

Raw evidence is already retained, but current typed models cannot represent a
result-specific treatment certificate with separate receipt and efficacy scope.
Do not use `subject_id`, `arm_relationship`, cohort grouping or a normalized
fact confidence as a substitute.

Minimum additional record: **TreatmentCohortAttribution**, local to the existing
human-PoC evidence path and usable by the proposed ResultBinding:

- `attribution_id`, `asset_id`; accepted treatment identity/alias evidence IDs;
- nullable `trial_id`, source-local/versioned `arm_id` or arm-label reference;
- separate `result_id`/result-group reference and cohort/result spans;
- complete intervention/regimen members and roles, comparator/background;
- basis A/B/C/F plus mandatory regimen scope D and identity status E;
- independent `receipt_status` and `efficacy_attribution_status`;
- observed/analysis-set, dose/schedule/period and add-on/non-monotherapy qualifiers;
- source document ID, snapshot hash, JSON pointers and exact text spans;
- reason codes, contradictions and verification/confidence status.

An arm label must be scoped to its trial **and snapshot/version**. An outcome
result-group ID and protocol arm label are separate identifiers until an
explicit mapping is evidenced. Protocol endpoints must remain incomplete.
A certificate cannot discard qualifiers while reducing itself to a True fact.

Smallest eventual interface: a pure resolver consumes an existing result
binding, candidate identity evidence and captured trial-arm evidence, returning
this record or UNKNOWN. It never searches, changes identity or writes human-PoC
facts. The existing emitter would consume only certified ownership records in
a separately preregistered behavior milestone, after the quantity binder and
automatic grounding are independently ready.

**Next narrow candidate milestone: TREATMENT_COHORT_ATTRIBUTION_REPRESENTATION v1.**
Preregister a lossless typed record and arm/result provenance representation
first, with no human-PoC promotion or routing change. This is a proposal, not
an opened or implemented milestone. Automatic result-to-arm grounding, alias
certification and scoped emission still need explicit tests and preregistration;
new arm-specific efficacy evidence would be required to rescue unsupported
component claims. Representation alone does not turn the 14 into positives.

Stop here. The handoff records this diagnosis, the 0/0/0/14 recovery counts and
nine receipt-only edges. Human-efficacy extraction remains unchanged; the
quantity-binding contract is not weakened or implemented.
