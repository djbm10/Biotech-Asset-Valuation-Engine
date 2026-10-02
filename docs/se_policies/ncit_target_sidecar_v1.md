# NCIT_TARGET_SIDECAR v1 — curated antigen classes, corroborated by NCIt's mechanism sentence (preregistration)

**Status:** PREREGISTERED 2026-10-02. Only design-half prototyping exists. No pipeline code
has been written.
**Decision:** the operator chose Option B on 2026-10-02 after `target_relation_reader_v1.md`
failed. That makes three CT.gov free-text target readers that have failed. Do not return to a
CT.gov reader unless NCIt fails for a reason NCIt fundamentally cannot solve.

## 1. Source survey (done before this document)

**Release.** NCI Thesaurus **26.08e**, FLAT file:
`https://evs.nci.nih.gov/ftp1/NCI_Thesaurus/archive/26.08e_Release/Thesaurus_26.08e.FLAT.zip`.

- sha256 `645ad414c3a0b6ceecda66e132ca66055c15608f39508597c23a3a94b38309da`.
- Local copy: `~/se_sources/ncit/26.08e/`.
- Licence: public domain (US government work).
- The archived release path is immutable, so the file is pinnable. A later release is a new
  sidecar version and never changes this one.

**Finding 1 — NCIt has curated antigen classes.** NCIt files CAR products under curated
classes such as "Anti-CD19 CAR T Cells Preparation" (C176018, 150 children) and "Anti-BCMA CAR
T Cells Preparation" (C176023). The class definition names the antigen. There are 21 such
classes, all in the CAR-T branch. Assignment is curation, not prose, so it ranks above any
definition reader in the evidence hierarchy.

**Finding 2 — class membership is sound but incomplete.** Dual constructs often lack their
second class:
- "Anti-CD19CAR-HER2t/CD22CAR-EGFRt" → CD19 only;
- "Anti-BCMA/CS1" → BCMA only;
- "Anti-Muc1/CD33/CD38/CD56/CD123" → CD33 + CD123 only.

A `construct_target_set` is read as a *complete* description of the construct, so class
membership alone may not produce one.

**Finding 3 — the mechanism sentence is a second, independent statement.** Each definition has
a templated sentence such as "Upon administration, *X* … induce selective toxicity in
**BCMA-expressing** tumor cells". This sentence names what the product is directed to. CAR
architecture (hinge, costimulatory and signaling domains, safety switches, armoring transgenes)
appears either elsewhere in the definition or inside the product's own name. The v1 reader
failed on exactly that: C150906 "CD19-CD8-CD28-CD3zeta-CAR-mbIL15-HER1t" has class {CD19} and
mechanism {CD19}.

**Finding 4 — identity.** Every TAC01 survey control links by its authority name to exactly
one NCIt product concept. NCIt keeps the following pairs as separate concepts:
- CNCT19 (C175465) and inaticabtagene (C199061);
- varnimcabtagene autoleucel (C179725, ARI-0001, CD19-only) and IMPT-314 (rondecabtagene,
  C199659, CD19/CD20).

The survey's "varnim-cel = CD19+CD20, to verify" conflated the two. Its expected answer is
corrected here to {CD19}, before any measurement. GC012F and AZD0120 link to the same concept
(C175471). The standing unmerged rule is unaffected: a target fact is not an identity merge.

## 2. Hypothesis

A target set emitted **only** when NCIt's curated antigen-class membership and its mechanism
sentence name the same complete set of human genes has zero false therapeutic-target
attributions. That includes CAR architecture components. Such a set also resolves the
NCIt-supported TAC01 rows that today have no target.

## 3. Rule (frozen)

The reference implementation is `research/se_ncit/reader_frozen_v1.py`
(sha256 `3e7960d04aee4a9f6205e9703bf12ccde7e23d582a7740aed6d9ca0f998ba553`). The production
code must reproduce its emit/refuse decision and its target set on every concept in the
population. An evaluation script checks this parity.

### 3.1 Population

NCIt concepts are in scope when they descend from either:
- the CAR roots, C126102, C137999 and C201933;
- or "Antineoplastic Immune Cell" (C129826).

The antigen classes themselves are excluded. This gives the sidecar's product set; the root
and class concepts can never be linked as products.

### 3.2 Class map (E1) — frozen by hand from NCIt's own class definitions

The 21 classes and their surface forms are in `CLASS_MAP` in the reference file.

- Each class maps to one HGNC gene, with surface forms taken only from the NCIt class name and
  the parenthetical in its definition. For example, HER2/ErbB2/HER-2 → ERBB2 and CD20 → MS4A1.
  The map does not depend on the target resolver, which keeps the recorded CD20 ambiguity out
  of this route.
- Two classes are **non-gene**:
  - GD2, a ganglioside (`non_protein_antigen`);
  - Claudin18.2, an isoform-specific antigen (`isoform_specific_antigen`).

  A product carrying either gets no fact, together with that reason. It is not forced onto a
  gene.
- E1 is the set of mapped genes over all of the product's ancestor classes.

### 3.3 Mechanism reading (E2)

- Read only the first definition sentence that begins with Upon, After or Following.
- Collect antigen arguments in four preposition- or frame-governed positions:
  - "in/to/against/kill/… [the] X[-, and/or, or Y]-expressing|-positive";
  - "tumor/cancer/neoplastic/malignant cells expressing X [and/or Y]";
  - "the X antigen on";
  - "bind(s) to X [and Y] on|expressed".
- Split each argument on `/`.
- Resolve each part in order:
  1. a class surface form;
  2. otherwise, if the part is symbol-shaped, the strict target resolver: approved symbol, or a
     synonym of at least 3 characters;
  3. otherwise the part is **unresolved**.

  Any unresolved part refuses the whole reading.

### 3.4 Decision

| Condition | Outcome |
|---|---|
| E1 empty | no fact; `no_antigen_class` |
| E1 contains a non-gene class | no fact; that class's reason |
| E2 refused, empty, or no mechanism sentence | no fact; that reason |
| E1 ≠ E2 | no fact; `class_mechanism_disagree`, with both sets recorded |
| E1 = E2 | **emit** `construct_target_set = E1` |

### 3.5 Asset linking

- **Names.** The asset's canonical name, plus the ChEMBL authority names for the drug it
  resolves to. This is the `authority_names` helper from `12f2d1e`, restored unchanged.
- **Excluded names.** Class terms (`is_class_term`), so `CART19` and `CAR-T` never link.
- **Match.** Normalised exact match (`casefold`, alphanumerics only) against the preferred
  name and every synonym of population concepts.
- **Link rule.** Link only if the matched names reach exactly **one** concept. Two or more
  concepts → `ambiguous_link`, and no fact.

### 3.6 Pipeline use

- **Fill-only.** The step runs in `CONSTRUCT_TARGETS`, after the drug→target authority. An
  NCIt fact is added only when the asset has no `construct_target_set` from any other route.
- **Conflicts.** When the asset already has a fact and NCIt's set differs, the conflict is
  recorded and nothing changes.
- **Provenance.** Each fact carries:
  - document `urn:ncit:26.08e`;
  - a claim whose locator is `NCIt:<code>#class=[…];mechanism=[…];link=<matched name>`;
  - the mechanism sentence as supporting passage;
  - `extraction_method = ncit_class_mechanism_agreement`;
  - `extractor_version = ncit_target_sidecar_v1`.
- **Dispositions.** Every linked asset, emitted or not, gets a record in the run output
  `ncit_target_dispositions.json`, with its reason code. This is how tabelecleucel and
  lifileucel are represented honestly.
- **Versioning.** The sidecar sha256 is added to the run's ontology version token, so replays
  with and without the sidecar can never be confused.

## 4. Controls (frozen)

**Positive**, at concept level and as unit tests:

| Concept | Product | Expected |
|---|---|---|
| C165779 | ALLO-715 | {TNFRSF17} |
| C180584 | anbalcabtagene | {CD19} |
| C199003 | anitocabtagene | {TNFRSF17} |
| C165507 | CT053 / zevor-cel | {TNFRSF17} |
| C185123 | equecabtagene | {TNFRSF17} |
| C147523 | orvacabtagene | {TNFRSF17} |
| C211706 | resecabtagene | {CD19} |
| C203060 | TAK-007 | {CD19} |
| C179725 | varnimcabtagene | {CD19} |
| C175471 | GC012F | {TNFRSF17, CD19} |

**Negative**, at concept level:

| Concept | Product | Expected |
|---|---|---|
| C150906 | CD19-CD8-CD28-CD3zeta-CAR | {CD19} only; never CD247, CD28 or CD8A |
| C155897 | CD19CAR-HER2t/CD22CAR | no fact (class incomplete) |
| C151954 | Muc1/CD33/… | no fact |
| C143140 | tabelecleucel | no fact, `no_antigen_class` |
| C120552 | lifileucel | no fact, `no_antigen_class` |
| C150382 | satricabtagene | no fact (not in the Claudin18.2 class) |
| — | any product under the GD2 class | no fact, `non_protein_antigen` |

**Linking**, as unit tests:
- `CART19`, `CAR-T` and `CARTPT` never link;
- a name that matches two concepts gives no fact;
- class and root concepts are not linkable.

## 5. Acceptance (frozen)

### Stage H — held-out concepts (run by the implementer)

- **H1.** All §4 controls pass.
- **H2.** The production sidecar is at parity with the reference file across the whole
  population.
- **H3 (binding).** The held-out set is the 291 CAR-root products in `split_v1.json["held"]`
  (sha256 `0abea2bf5e6e3c67e6dbb473743ed7ddfffe90e2f04f860b7cb40d4a09d3eb1f`). The split is a
  deterministic hash of the concept code. None of these definitions has been read by the
  reader.
  - Disclosure: some held-out *names* and their class membership were seen while measuring
    Finding 2.
  - Every held-out emitted fact is hand-verified against the full definition and the product
    name.
  - A fact is false if it contains anything that is not an antigen the CAR is stated to
    recognize, or if it omits one.
  - **Zero false facts allowed.**
  - The emit rate is reported; there is no threshold.

### Stage P — pipeline replays (operator's terminal, sequential, new directories)

The baseline is `{tac01,mint5}_fragment_a1`, replayed from the same sealed corpora with the
sidecar installed.

- **P0 (determinism).** A second TAC01 replay has byte-identical `construct_target_set` facts
  and dispositions.
- **P1.** Every new or changed `construct_target_set` on an asset in either top 50 is
  hand-verified. Zero false facts.
- **P2.** Existing target facts are untouched: every baseline `construct_target_set` is still
  present and unchanged. This holds by fill-only construction and is verified anyway.
- **P3 (TAC01 controls).** Each of these rows present in the run gets its NCIt-supported set,
  or an explained reason (already had a fact, link ambiguous, absent from the run):
  - ALLO-715, anbal-cel, anito-cel, CT053, eque-cel, orva-cel, rese-cel, TAK-007, varnim-cel;
  - CNCT19, as its concept C175465 decides.
- **P4.** Tabelecleucel and lifileucel have no target fact, and a disposition with their NCIt
  code and reason.
- **P5.** Ranking code is unchanged. Every top-20 movement is explained by a target-gate
  change, or by its deterministic consequences, including qualification through
  `described_constructs`.
- **P6.** `tests/se` passes and `ruff check src/` is clean.

## 6. Stop condition

- **Adopt** if H1–H3 and P0–P6 all pass.
- **On failure:** record it, revert the implementation, and classify the cause.
  - If the cause is that agreement between two NCIt statements is still wrong, for example
    because CAR architecture leaks into both, that is the **architectural fork**: an explicit
    CAR-construct representation. Escalate to the operator; do not add lexical exceptions.
  - A failure for any other reason (linking, sidecar parity) may be amended only on a
    principled flaw in §3.

## 7. Out of scope

- Non-CAR modalities (antibodies, ADCs, bispecific antibodies). NCIt has no antigen classes
  for them in this branch; this is a candidate v2.
- NCIt roles.
- Ranking.
- Stage.
- Widening class maps beyond the 21 that NCIt curates.

## 8. Result — Stage H, 2026-10-02, implementation `0c5f847`

Sidecar: `ncit_target_sidecar_v1@ncit_26.08e`, sha256 `2cbcd3f4b18d22b6…`, 959 products.
Output: `scripts/eval_ncit_target_sidecar.py` → `research/se_ncit/eval_v1.txt`.

### H1 (controls): FAIL as written

16 of 18 controls pass. Two positive controls fail, and neither failure is a precision error.

| Control | Concept | What NCIt 26.08e holds | Rule outcome |
|---|---|---|---|
| resecabtagene | C211706 | **no definition text**; only the class says CD19 | `no_mechanism_sentence` |
| TAK-007 | C203060 | a CAR-**NK**. NCIt's 21 antigen classes are CAR-T only; only the mechanism sentence says CD19 | `no_antigen_class` |

In both cases the frozen rule fails closed exactly as §3.4 specifies. The §4 expectations were
wrong. I wrote them from the coverage survey without checking that NCIt carries *both* required
statements. The operator's directive set the bar at "where NCIt actually supports them", and
these two lack one statement each. The text of H1, however, requires all §4 controls to pass.

### H2 (parity): PASS

The production reader matches the frozen reference across all 959 concepts with 0 mismatches.
The class maps are identical.

### H3 (binding held-out): PASS

- **Population and outcomes.** The held-out split has 291 products:

  | Outcome | Products |
  |---|---|
  | emit | 136 |
  | `no_antigen_class` | 113 |
  | `class_mechanism_disagree` | 9 |
  | `no_mechanism_sentence` | 8 |
  | `non_protein_antigen` | 8 |
  | `no_antigen` | 7 |
  | `unresolved` | 5 |
  | `isoform_specific_antigen` | 5 |

- **Audit method.**
  - For each of the 136 facts, every gene-like mention in the **full** definition that falls
    outside the emitted set was listed with its context. 98 facts had such mentions; all were
    read.
  - Every fact whose product name looks multi-target was also read.
  - The 38 facts with no other gene mention name only their emitted antigen.
- **What the other mentions were.** All of them are non-binders:

  | Kind | Examples |
  |---|---|
  | construct domains | CD137/4-1BB, CD3ζ, CD28, CD8 hinge, CD27, CD2 |
  | tags and safety switches | EGFRt, CD19t, RQR8 (CD34/CD20 epitopes), iCasp9/FKBP12 |
  | knockouts and knockdowns | PDCD1, B2M, CD52, CD38, HLA |
  | armoring and payloads | IL-15/IL-7/IL-18/IL-2, CCL19, CD40L, PD-1 nanobody |
  | switch or gate receptors | PD-1:CD28, dnTGF-βRII, LIR-1/HLA-A\*02 NOT-gate |
  | effector-side receptors | hnCD16a, CXCR2 |
  | ligand background | BAFF/APRIL in BCMA descriptions |

  Every dual-looking name was architecture written with a slash, not a second binder.
- **Result: 0 false facts out of 136.** This includes the class that sank
  `target_relation_reader_v1`.

### Status: H1_FAILED_AS_WRITTEN

By §6, the implementation is reverted. The cause is not a flaw in §3. It is two control
expectations that the source cannot support. Correcting those two rows would change frozen
acceptance after measurement, so it is escalated to the operator rather than amended
unilaterally. No pipeline wiring or Stage P was started.
