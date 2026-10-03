# CANDIDATE_QUALIFICATION v6 — regimen, procedure and composite entries are not assets (preregistration)

**Status:** PREREGISTERED 2026-10-03. No implementation exists.

**Predecessors:**
- class terms v5 (adopted);
- `ncit_target_sidecar_v1` (adopted);
- `target_authority_arbitration_v1` (adopted).

The baselines are `~/se_runs/{tac01,mint5}_arb_v1`.

## 1. Diagnosis

Qualification has six routes. Two of them admit names that are not therapeutic products.

- **`STRUCTURED_THERAPEUTIC`** (216 names) admits any CT.gov intervention named in an
  experimental arm. Registries also enter these as interventions:
  - regimens: `R-mini-CHOP`, `Hyper-CVAD`;
  - care descriptors: `Standard of Care`, `Treatment`;
  - multi-drug lists: `Cyclophosphamide,Fludarabine`, `Elranatamab + lenalidomide + dexamethasone`.
- **`CONSTRUCT_CORROBORATED`** (251 names) admits procedure names such as `DLI`.

The population is every qualified candidate in either baseline whose route is anything other
than `DIRECT_APPROVED_NAME`: 573 unique names. It is frozen at
`research/se_qualification/population_v1.json`
(sha256 `1569318a5cd4d29ce446d2c297a9bc6735a11f3164fd021f60222ef87a66209c`).

**NKTR-255 is a positive control.** It is avipendekin pegol, an investigational IL-15
receptor agonist. NCIt C175746 types it as Pharmacologic Substance.

## 2. Rules (frozen)

Both vetoes are added to `qualification_reason`:

- **below** the ontology route (`DIRECT_APPROVED_NAME`) and the comparator veto;
- **above** every other route.

A name the drug ontology identifies is therefore never touched. That includes real
fixed-dose combination products.

### Q1. Source-semantic entity type (NCIt)

Normalize the name: casefold, alphanumerics only. If it exactly matches the preferred name
or synonym of one or more NCIt 26.08e concepts, and **every** matched concept's semantic
types fall inside this closed non-product set, the name is not an asset. The reason code is
`NCIT_NON_PRODUCT_TYPE`.

The non-product set comes from the UMLS semantic network, not from the benchmarks:

> Therapeutic or Preventive Procedure, Health Care Activity, Research Activity, Activity,
> Diagnostic Procedure, Laboratory Procedure, Intellectual Product, Conceptual Entity,
> Qualitative Concept, Quantitative Concept, Functional Concept, Temporal Concept, Idea or
> Concept, Classification, Finding, Disease or Syndrome, Neoplastic Process, Event,
> Population Group, Spatial Concept

The rule has three guards:
- If any matched concept carries any other type (for example Pharmacologic Substance, Cell,
  or Amino Acid/Peptide/Protein), there is no veto.
- If there is no match, there is no veto.
- If the sidecar is absent, there is no veto.

**Data.** The rule reads a sidecar of non-product name keys and their concept codes, built
from the pinned zip (`645ad414…`). Its token is recorded under
`extractor_versions["ncit_entity_types"]`. Replay fails closed on mismatch, the same way as
the target sidecar.

### Q2. Composite of independently named drugs

Split the name on these coordinators: `,` `;` `+` `/` `and` `plus` `or` `with`
`followed by` `then` `in combination (with)`. Strip parentheses and brackets from each
segment.

If there are at least 2 segments, and at least 2 *distinct* segments are each
identity-bearing drug names under the existing `drug_name_shape.is_identity_bearing_drug_name`,
the name denotes a regimen or a list, not one product. The reason code is
`COMPOSITE_OF_NAMED_DRUGS`.

### Effect of a veto

`qualification_reason` returns `None`. The candidate keeps all of its provenance, but it is
held out of the default path as low-support, exactly like every other unqualified name.
Nothing is deleted. Every veto is reported in the run output `qualification_vetoes` with its
reason code and the matched NCIt codes or drug segments.

## 3. Expected changes (hand-verified before implementation)

On the frozen population, the two rules veto **27 names**. Each was checked by hand as a
non-product:

- **Regimens:** R-mini-CHOP, Hyper-CVAD, mini-hyperCVD, Preparative regimen.
- **Procedures and care descriptors:** DLI, Genetically Engineered Lymphocyte Therapy,
  Standard of Care, Treatment, Experimental Intervention.
- **Composites (18):**
  - Blinatumomab and Inotuzumab Ozogamicin
  - Carfilzomib, Lenalidomide, Dexamethasone, Belantamab Mafodotin
  - Cyclophosphamide or Bendamustine
  - Cyclophosphamide,Fludarabine
  - Elranatamab + lenalidomide + dexamethasone
  - Elranatamab + Nirogacestat
  - Epcoritamab, lenalidomide and rituximab
  - Fludarabine + Cyclophosphamide + CAR-NK-CD19 Cells
  - fludarabine and cyclophosphamide
  - Fludarabine, Cyclophosphamide
  - Ibrutinib, Acalabrutinib, Zanubrutinib, or Pirtobrutinib
  - PF-06863135 + lenalidomide
  - PF-06863135 + pomalidomide
  - Prednisone, Olverembatinib, Blinatumomab, Chidamide
  - Retlirafusp alfa / … (TP regimen) plus PD-1 inhibitor
  - Rituximab, Cyclophosphamide, and Corticosteroids
  - Tafasitamab plus lenalidomide
  - Tislelizumab + Zanubrutinib

**Declared residuals.** The rules do not reach these names, and none will be patched by a
name list:
- `Fludarabine-based`;
- `Induction Chemotherapy`, `Lymphodepletion Chemotherapy`;
- `Chemotherapy Agents`;
- `Post-CR Consolidation Regimens`;
- `Cyclophosphamide-based chemotherapy`;
- `Withhold IS (…)`;
- `Anti-CD19 CART cells given IV at split doses.`;
- space-joined lists such as `Blinatumomab Inotuzumab Ozogamicin`;
- class names such as `mTOR` and `G-CSF`. These are kept because NCIt types `mTOR` as a
  protein and `G-CSF` as a substance.

These are prose descriptors with no NCIt concept. They need a different representation, a
descriptor/head-noun model, which would be a later milestone if needed.

## 4. Acceptance (frozen)

Sealed replays go into new directories and are compared against `*_arb_v1`.

- **C1.** In each run, the set of newly unqualified names equals the §3 list restricted to
  the names present in that benchmark. A veto outside the list fails C1, and so does a listed
  name that was not vetoed.
- **C2 (precision).** Zero real therapeutic products are disqualified. This holds by C1 plus
  the hand verification in §3.
- **C3 (positive controls stay qualified with an unchanged reason):**
  NKTR-255, AcNK-Sup003 cell injection, Human CD19 Targeted T Cells Injection, SYNCAR-001,
  ssCART-19, Tecartus, AZD0120, FKC289, CLN-978. Every `DIRECT_APPROVED_NAME` reason is
  unchanged.
- **C4.** No `construct_target_set` fact and no target gate changes.
- **C5.** Ranking code is unchanged. Every top-50 movement is explained by a qualification
  change (the entry left the default path) or by deterministic backfill.
- **C6.** Two TAC01 replays give identical vetoes, facts and top 50. The fail-closed sidecar
  check covers both tokens.
- **C7.** `tests/se` and ruff pass.

## 5. Stop condition

- **Adopt** if C1–C7 all pass.
- **Otherwise** record the failure and revert. Do not tune the type set, the coordinators or
  the population.
