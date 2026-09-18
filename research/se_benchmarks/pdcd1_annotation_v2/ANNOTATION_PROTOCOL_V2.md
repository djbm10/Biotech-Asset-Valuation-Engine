# PDCD1 gold-entry annotation protocol V2

Append-only. This protocol does not amend, reinterpret or supersede
`GOLD_ENTRY_ROLE_RULES.md` (V1, hash chain tip `fe5d03d28365c9608de1fc50d2d4e3810eb3a7daac0adcdc4aaff5a85b6b2dd6`).
V1 and its outputs remain immutable and remain the reported V1 result. V2 produces a
second, separately labelled annotation layer over a fixed subset of entries.

M8 v2 itself is never modified. V2 annotates; it does not edit the benchmark.

## V2.0 -- Freeze order

This document is written, hashed and published **before any entry in the subject set is
researched individually**. The subject set is fixed by V1 output alone. No rule below was
chosen after seeing evidence about any specific entry.

## V2.1 -- Subject set

Exactly the 48 entries with V1 `entity_role = ASSET` and V1 `target_relevance = UNCERTAIN`,
as recorded in `pdcd1_adjudication_v1/gold_entry_roles.jsonl`. No entry may be added to or
removed from this set. Entries carrying any other V1 `entity_role` are out of V2's reach,
including every `COMBINATION_REGIMEN` entry withheld by V1 amendment A3.3. V2 may not
recover an A3.3 withholding.

The 48 split into two tracks by the V1 subtype partition in
`pdcd1_adjudication_v1/m10b/asset_uncertain_subtypes.jsonl`, which was computed from
authority-resolution state only and not from any judgement about the drugs.

Track A -- conventional named drug assets, n=38
  AUTHORITY_HAS_MOLECULE_BUT_NO_MOA        20
  DEVELOPMENT_CODE_ABSENT_FROM_AUTHORITY   12
  NAME_UNRESOLVED_IN_AUTHORITY              6

Track B -- structurally different assets, n=10
  CELL_THERAPY_VACCINE_OR_CONSTRUCT         5
  BIOSIMILAR_CANDIDATE                      3
  NON_SMALL_MOLECULE_TRADITIONAL_MEDICINE   2

Track B entries are **not** classified out of scope by construction. They are adjudicated
under V2.5, which states rules appropriate to their modality rather than forcing
drug-database semantics onto products those databases were not built to cover. An
out-of-scope blind spot in the denominator is itself a defect.

## V2.2 -- Admissible sources and their precedence

Ordered. A lower-numbered source outranks a higher-numbered one on conflict.

1. Regulatory product documentation -- FDA labels/approval packages, EMA EPARs/SmPCs, and
   equivalent documentation from other national regulators.
2. Official company pipeline or product pages, on a domain the company controls.
3. Official company filings -- SEC filings and their non-US equivalents.
4. Primary publications -- peer-reviewed papers reporting the product's mechanism.
5. ClinicalTrials.gov, admissible **only** where the registry record explicitly states the
   product's target or mechanism. A registry record that names the drug without stating a
   target is not target evidence under V2.

Not admissible as target evidence at any rank: Open Targets and ChEMBL (already exhausted
in V1); AACT-derived synonym data (excluded by V1 amendment A2.1 and still excluded);
Wikipedia, drug encyclopedias, news, press aggregators, secondary databases, and any
pipeline-derived artefact.

## V2.3 -- Evidence standard

Both identity and target must be explicit in the cited source.

- **Identity.** The source must name the exact entry string or one of its M8 aliases, under
  the same normalisation V1 permits: NFKD folding, case, trademark symbols, punctuation and
  whitespace only. No fuzzy or edit-distance matching. A development code must appear
  verbatim.
- **Target.** The source must state the product's molecular target or mechanism in terms
  that name PDCD1/PD-1, or name some other target, in its own words. The adjudicator quotes
  that statement.

Prohibited inferences, at every rank: sponsor identity; therapeutic indication; the trial's
comparator, backbone or co-administered agents; class or naming convention, including the
`-limab` stem; structural or sequence similarity to a known PD-1 binder; and any reasoning
of the form "it is used with a PD-1 drug, therefore it targets PD-1".

`CD274`/PD-L1 remains `NON_PDCD1`. The benchmark is PDCD1, not the checkpoint pathway.

## V2.4 -- Track A decision rule

`PDCD1_MATCH` -- an admissible source explicitly establishes identity and states PDCD1/PD-1
as the product's target.
`NON_PDCD1` -- an admissible source explicitly establishes identity and states a target that
is not PDCD1. A product that binds PDCD1 among several targets is `PDCD1_MATCH`.
`UNCERTAIN_V2` -- no admissible source establishes both, or admissible sources of equal rank
conflict irreconcilably. Remaining uncertain is an acceptable outcome and is reported as
such.

## V2.5 -- Track B decision rules, by subtype

**Biosimilar candidates.** A biosimilar inherits its reference product's target only where
an admissible source explicitly establishes the biosimilar/reference-product relationship
**and** the reference product's target is established under V2.3 or already established in
V1. Inheritance is never assumed from the sponsor, the code, or the phrase "biosimilar"
alone. Absent an explicit named reference product: `UNCERTAIN_V2`.

**Cell therapies, vaccines and engineered constructs.** `PDCD1_MATCH` only where an
admissible source states that the product itself is designed to target, block, bind,
knock out, knock down, or express a construct against PDCD1/PD-1 -- that is, PDCD1 is part
of the product's own design. Administration alongside a PD-1 agent, use in a PD-1-refractory
population, or a PD-1-related enrolment criterion is explicitly insufficient. A product
whose design targets a tumour antigen and not PDCD1 is `NON_PDCD1`.

**Traditional medicines and other non-small-molecule products.** Require explicit product
identity and a directly stated PDCD1 mechanism of the product itself. Reported effects on
PD-1 expression in a study population, immunomodulatory activity in general, or component
level pharmacology without product-level attribution are insufficient. Default
`UNCERTAIN_V2`.

## V2.6 -- Adjudication procedure

Two adjudicators, A and B, work independently over the same 48 entries. Both are blind to
pipeline outcome, to whether the entry was identified, extracted or reachable, and to the
other adjudicator's output. Each emits, per entry: `target_relevance_v2`, source rank,
source reference, verbatim evidence excerpt, reason code, and confidence.

Reconciliation may apply only the rules frozen in this document. Where A and B disagree and
V2.2 precedence does not resolve it, the entry is `UNCERTAIN_V2`. Reconciliation may not
introduce a source, relax V2.3, or revisit V1.

`entity_role` is not re-adjudicated. V2 decides `target_relevance` only. A V2 verdict never
alters `entity_role`, `trial_role`, or any V1 field.

## V2.7 -- Output and reporting

The V2 layer is append-only and records, per entry: V1 classification, V2 classification,
source rank, source reference, evidence excerpt, reason code, adjudicator A verdict,
adjudicator B verdict, reconciliation result, and unresolved status.

Five figures are reported side by side, and the first two are never restated or replaced:
1. strict M8 recall, denominator permanently n=224
2. V1 confirmed PDCD1 asset recall
3. V2 confirmed PDCD1 asset recall
4. reachable V2 confirmed PDCD1 asset recall
5. residual uncertainty interval after V2

## V2.8 -- What V2 may not do

V2 may not modify M8, modify V1 rules or V1 outputs, extend its subject set, recover an
A3.3 withholding, admit a source not listed in V2.2, or be amended after adjudication
begins. Any future change is a further append-only protocol under a new version and hash.
