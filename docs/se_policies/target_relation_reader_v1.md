# TARGET_RELATION_READER v1 — explicit asset→therapeutic-target relations (preregistration)

**Status:** PREREGISTERED 2026-10-02. No implementation exists at commit time.
**Predecessors:** `registry_target_lookup_v1.md` (FAILED A2, reverted `7b6d45c`),
`asset_sentence_target_v1.md` (FAILED, route closed). The handoff left a fork:
(a) a strict reader first, or (b) the NCIt sidecar first. The operator chose (a) on 2026-10-02:
build a reusable high-precision relation model *before* retrying any broad acquisition.

## 1. Problem

`intervention_construct_targets` → `attributed_targets_in` (`evidence/construct_targets.py`)
asserts a target when **any** symbol-shaped token sits within 4 tokens of **any** cue word, and
resolves that token through the full alias table. On target-scoped CAR-T/bispecific records this
looked precise. On the broader population that lookup v1 fed it, it failed.

### 1.1 Diagnosis corpus

`research/se_target_reader/lookup_v1_interventions.jsonl.gz`
(sha256 `b1ce7b6cf37c398aa2fee7b3e96c04cab2a31da44ea5e285b8a9b025a32b7bda`).
It holds 33,264 unique DRUG/BIOLOGICAL/GENETIC interventions extracted from the sealed
`~/se_runs/{tac01,mint5}_lookup_v1_custody`.

Run over it, the current reader asserts targets on 845 records. A token trace (scratch, not
committed) attributes every assertion to one of these mechanisms.

| Class | Mechanism | Examples (token → resolved gene) |
|---|---|---|
| F1 | **Abbreviation/alias collision.** A non-gene token is resolved through an OT synonym. Route abbreviations, sponsor code prefixes, and words that are themselves cues or product heads. | `PO`→PRB4 (67), `MS`→MTR, `AMG`→AMELX, `GDC`→SLC25A16, `SC`→ERMAP, `AK`→ADK, `TAK`→CDK9, `KO`→KRT8, `PCI`→SERPINA5, `ATC`→ATM, `CART`→CARTPT, `IV`→ST6GALNAC4, `LN`→MLPH, `MART`→SEPTIN4 |
| F2 | **Family/class term resolved to one member.** | `HDAC`→HDAC9, `MEK`→MAP2K7, `BET`→DNER, `PDE`→ALDH7A1, `P450`→CYP2B6 |
| F3 | **No grammatical attachment.** A real gene inside the 4-token window, but not what the product binds: a metabolising enzyme, a drug-interaction warning, a cell-type descriptor, a TCR clone name. | colchicine→CYP3A4, fluvoxamine→CYP1A2, `CD8+ … -specific`→CD8A, `F5 TCR`→F5, HIV mAb "CD4 binding site"→CD4 |
| F4 | **Construct component / armoring transgene.** | `CD19 CAR-T Expressing IL7 CCL19`→IL7, CCL19; `Anti-CD19 IL-10/IL15 CAR-NK`→IL10, IL15 |
| F5 | **Other therapy's target.** A cue phrase modifying prior or concomitant therapy, or a class of therapies. | "patients who underwent BCMA-targeted treatment" (cevostamab); "mAbs targeting CD19 or CD20" |
| F6 | **Ligand vs receptor / pharmacology cue.** "agonist", "antagonist" and "inhibitor" name ligands or enzymes as often as targets, and also occur in DDI text. | `LHRH agonist`→GNRH1 (the drug acts on GNRHR), `CYP3A4 … inhibitor` |
| F7 | **Partial-part split.** A compound is split on `-` and one fragment resolves. | `MART-1`→`MART`, `Anti-c-ERB-2`→`ERB`→ESR2 |

The ontology complicates any lexical fix. Open Targets synonyms are stored with `alias_type =
SYMBOL`, so alias type cannot separate `BCMA`→TNFRSF17 (wanted) from `IV`→ST6GALNAC4 (not
wanted). `ALK` itself resolves to EML4. That is recorded as an ontology defect, out of scope.
A lexical whitelist is forbidden by the constitution. The fix therefore has to be
**grammatical**: a symbol becomes a target only when it occupies a closed argument slot of an
attributive construction, and only in a locus that describes this product.

## 2. Hypothesis

A reader that

- admits a target only in a closed set of attributive argument slots,
- reads only loci that describe the product itself,
- fails closed on incompleteness and internal disagreement

will eliminate F1–F7, and keep the explicit CD19/BCMA construct relations.

## 3. Rule (frozen)

The reader is the new module `bve.se.evidence.target_relations`. Its pure function is
`relations_in(text, locus) -> RelationReading`. It is reusable for NCIt definitions later, but
v1 wires it **only** into the existing CT.gov intervention route
(`clinicaltrials.py` → `intervention_construct_targets`). Lookup v1 stays reverted. Re-enabling
it is a separate preregistration (§8).

### 3.1 Slots (closed set; X is a *target mention*, §3.2)

| Id | Form | Examples |
|---|---|---|
| S1 `ANTI_PREFIX` | `anti-X` (hyphen required, any case) | anti-CD19, Anti-BCMA |
| S2 `ATTRIBUTIVE_SUFFIX` | `X-directed`, `X-targeted`, `X-targeting`, `X-specific`, `X-redirected`, `X-binding`, or the same suffix as the next whitespace token | CD19-directed, BCMA-specific, CD19 targeting |
| S3 `CAR_HEAD` | X immediately precedes a token whose first hyphen-part is `CAR` or `CART` | CD19 CAR-T, BCMA-CD19 CART, CD19/CD22 CAR |
| S4 `VERBAL` | `targeting X`, `targets X`, `directed against X` — X is the very next token | therapy targeting BCMA |
| S5 `ARM_NOTATION` | a single token `X×Y` / `XxY` with both sides target mentions or effector terms | BCMAxCD3, FcRH5×CD3 |

The following are **not** slots in v1, by design (F6):

- `inhibitor`, `antagonist`, `agonist`, `blocker`, `blockade`, bare `against`;
- free-window proximity of any kind.

Small-molecule targets remain the job of the curated ChEMBL/OT authorities.

### 3.2 Target mentions

- **M1.** Resolve the whole token first (`MART-1`→MLANA). Tier `APPROVED` applies when the
  matched alias equals the entity's approved symbol, case-insensitive and ignoring hyphens.
  Otherwise the tier is `SYNONYM`.
- **M2.** A `SYNONYM` mention needs at least 3 alphanumeric characters.
- **M3.** Cue words and product heads are never mentions: `CAR`, `CART`, `cells`, `antibody`, …
- **M4.** A compound is split only on `/`, `×`, or an `x` between two symbol-shaped parts. A
  hyphen split happens only if **every** part resolves (F7).
- **M5.** Coordination inside one slot is allowed only by those separators, or by a run of
  symbol tokens directly before the CAR head in S3. Comma, `and` and `or` lists are not slot
  arguments.
- **M6.** Effector terms (`CD3`, `CD3E`, `CD3ε`) are recorded as `effector` and excluded from
  the therapeutic target set. Justification: the CD3 arm of a T-cell engager recruits effector
  cells. It is not the disease target.

### 3.3 Loci

- **L1.** The intervention `name` and each `otherNames` entry are read in full.
- **L2.** `description` contributes **only its first sentence**, split at `. `, `;`, `。`, or a
  newline. That is where a registry entry says what the product is. Later sentences carry
  dosing, eligibility and history (F3, F5).
- **L3.** Inside an L2 sentence, a slot that comes after a history or combination marker makes
  the record fail closed. History markers: prior, previous(ly), after, following, failed,
  refractory, relapsed, exposed, naive/naïve, resistant, intolerant, underwent, received,
  pretreated/pre-treated. Combination markers: combined, combination, plus, `+`.
- **L4.** An S1 or S2 modifier whose next token is a therapy-class noun makes the record fail
  closed. Those nouns are: therapy, therapies, treatment(s), agent(s), drug(s), regimen(s),
  mAbs, antibodies, biologics, inhibitors. Such a phrase names a class of therapies, not this
  product (F5).

### 3.4 Record rules

- **R1 (unchanged guards).** Only DRUG/BIOLOGICAL/GENETIC types are read.
  `COMBINATION_PRODUCT` is refused. More than one asset name in `name` is refused.
  `denotes_more_than_one_product(name)` is refused. That guard keeps the **old**
  `attributed_targets_in`: a looser reader inside a refusal guard is the conservative choice.
- **R2 (completeness).** If any slot's mention fails M1–M4 (unresolved, ambiguous, or too
  short), the record emits nothing. A construct set must describe the whole construct.
- **R3 (agreement).** Two disagreements leave the record with no fact:
  - in one locus, S3 juxtaposition and the explicit slots (S1, S2, S4, S5) are both non-empty
    and differ (F4);
  - two loci give non-empty sets that differ.
- **R4 (provenance).** Every emitted relation records:
  - its slot id;
  - its locus;
  - the surface mention;
  - the matched alias;
  - its tier;
  - its canonical id.

  These are written into the claim's `locator`. `extraction_method` is
  `ctgov_target_relation_reader` and `extractor_version` is `target_relation_v1`.

## 4. Controls (frozen)

### 4.1 Negative controls

Each must produce **no** fact containing the named wrong target.

| Control | Source | Expected |
|---|---|---|
| `GB5005 CART` | NCT06875063 | no fact (`CART` is a head, not a mention) |
| `CD19 CAR-T Expressing IL7 CCL19` | NCT04833504 | exactly {CD19}; never IL7/CCL19 |
| dasatinib | NCT01467986, NCT02596828 | no fact |
| docetaxel | NCT00293085 | no fact |
| pantoprazole | NCT00863837 | no fact |
| colchicine | NCT04997551 | no fact |
| `Given IV` / `LN-145 … TIL` / `DPP-4 inhibitor` / `AMG 103 … Anti-CD19` | synthetic | no ST6GALNAC4, MLPH, DSPP, AMELX; the AMG text gives {CD19} |
| cevostamab, the safety-context sentence (`human_poc_safety_context_v1.md` row) | synthetic | never TNFRSF17 |
| `Anti-CD19 IL-10/IL15 CAR-NK` | synthetic | no fact (R3) |
| `Cytochrome P450 inhibitor`, `LHRH agonist`, `HDAC inhibitor`, `MEK Inhibitor` | synthetic | no fact |
| `anti-MART-1 F5 TCR` | synthetic | never SEPTIN4, F5 |

### 4.2 Positive controls

| Control | Source | Expected |
|---|---|---|
| ALLO-715 | NCT04093596 | {TNFRSF17} |
| eque-cel | NCT07752264 | {TNFRSF17} |
| CNCT19 | NCT06316791 | {CD19} |
| CT053 | synthetic "CT053 is a fully human BCMA-specific CAR-T" (no CT053-named record exists in either frozen corpus) | {TNFRSF17} |
| "CLN-978: CD19-directed CD3 bispecific T-cell engager" | synthetic | {CD19} |
| "anti-CD19 CAR-T cells" | synthetic | {CD19} |
| "BCMA/GPRC5D CAR-T cells" | synthetic | {TNFRSF17, GPRC5D} |
| "Teclistamab (BCMAxCD3)" | synthetic | {TNFRSF17} |

### 4.3 Declared residual

**Not** prevented by v1. Non-human antigens can carry a name that collides with a human-gene
synonym, for example EBV `LMP2-specific` CTLs → PSMB9. No principled lexical rule separates
them from `BCMA`, and adding a pathogen ontology is out of scope. Any such fact that appears
counts as **false** in every audit below. It is not excused.

## 5. Acceptance criteria (frozen)

### Stage A — offline, reader level (run by the implementer)

- **A1.** All §4.1 negative controls pass, as unit tests.
- **A2.** All §4.2 positive controls pass, as unit tests.
- **A3 (design check on the diagnosis corpus).** The reader runs over the §1.1 corpus.
  - Every emitted record whose set contains anything other than {CD19} or {TNFRSF17} is audited
    by hand.
  - So are the first 60 CD19/TNFRSF17-only records in key order.
  - The false therapeutic-target attributions must be ≤ 1% of audited records.
  - None of them may be in classes F1, F2, F4, F6 or F7.

  This corpus informed the design, so A3 is a check, not the binding test.
- **A4 (binding, unseen-in-design corpus).**
  `research/se_target_reader/baseline_interventions.jsonl.gz`
  (sha256 `532dfcd604bd2621bdcbad800afc0419784774bea247d1056eb947e01168891c`) holds 3,464
  interventions from the sealed baseline custodies `tac01_control_a1` and `mint5_on`. That is
  the population the live route actually reads.
  - Old and new reader are diffed record by record.
  - Every **gained** (record, target) is hand-verified. Zero false gains are allowed.
  - Every **lost** one is classified as either "false removed" or "true lost", and all of them
    are reported.
  - There is no recall threshold at this stage. Cost is judged in Stage P.

If A fails, the result is recorded, the implementation is reverted, and no pipeline run is
requested.

### Stage P — pipeline replay (operator's terminal)

There are two runs, sequential, into new directories. They replay the same sealed corpora as
`{tac01,mint5}_fragment_a1`, and are compared against those baselines.

- **P1.** Every `construct_target_set` fact that changed on an asset in either top 50 is
  hand-verified. Zero new false target facts.
- **P2.** No asset in the TAC01 or mint5 top 20 whose baseline target-gate PASS rested on a
  **correct** fact loses that PASS. A PASS lost because its fact was false counts as a gain.
- **P3.** Ranking code is unchanged. Every top-20 movement is explained by a target-gate
  change, or by its deterministic consequence.
- **P4.** `tests/se` passes and `ruff check src/` is clean.

## 6. Measurement

- Stage A uses `scripts/eval_target_relation_reader.py`, committed with the implementation.
  It writes `research/se_target_reader/eval_v1.txt`.
- Stage P uses the fragment_a1 scorer pattern: shortlist diff, plus a fact diff of
  `construct_target_set` per asset.

## 7. Stop condition

- **Adoption:** A1–A4 and P1–P4 all pass.
- **Any failure:** record it here, `git revert` the implementation, and return to `7b6d45c`
  semantics. An amendment is permitted only if the failure exposes a principled flaw in §3, not
  an inconvenient example.
- **If adopted,** the next milestone, **M2**, gets its own preregistration: re-enable lookup v1
  retrieval (`12f2d1e`) with this reader. It needs no new reader rules, and its acceptance is
  re-run against the same five A-criteria shape as lookup v1.

## 8. Out of scope

- NCIt sidecar.
- Ranking.
- Stage attribution.
- The ontology defects `ALK`→EML4 and `PD-1` ambiguity: these are recorded, not patched.
- Retiring the old reader inside `denotes_more_than_one_product`.

## 9. Result — 2026-10-02, implementation `7e8471f`

Scorer: `scripts/eval_target_relation_reader.py` → `research/se_target_reader/eval_v1.txt`.

- **A1/A2 (controls): PASS.** Every §4.1 and §4.2 control passes, both as unit tests
  (`tests/se/test_target_relations.py`, 37) and against the pinned ontology on the sealed
  records.
  - Disclosure: the first script run encoded the MART row as "no fact". §4.1 freezes only
    "never SEPTIN4, F5", and `anti-MART-1` → MLANA is the correct reading, because MART-1 is
    MLANA. The script was corrected to match §4.1. The reader was not changed.
- **A4 (binding): FAIL.**
  - Old→new diff over the 3,464 baseline interventions: 13 targets gained, 743 lost.
  - Of the 13 gains, 12 are correct:
    - IL13Rα2-specific CARs ×5;
    - teclistamab → BCMA and talquetamab → GPRC5D, both from "XxCD3";
    - polatuzumab → CD79B;
    - siltuximab → IL6;
    - vonsetamig/REGN5459 → BCMA;
    - V001-FcRH5 → FCRL5;
    - anti-BCMA/FcRL5 CAR → +FCRL5.
  - **One is false:** NCT03579888 "Autologous CD19-CD8-CD28-CD3zeta-CAR-mbIL15-HER1t" gains
    CD247. CD3ζ is the CAR's signaling domain, and CD8 and CD28 (carried over from the old
    reader) are its hinge and costimulatory domains. M4 reads a CAR *architecture* string as a
    coordination of binding arms. That is class F4, the class v1 was built to close.
    Zero false gains were allowed.
- **Recall cost (reported; there was no threshold).** 410 baseline records lose a
  CD19/BCMA target, most of them correctly attributed before. Reasons:

  | Reason | Records | Example |
  |---|---|---|
  | no slot | 190 | "BCMA/GPRC5D dual CAR-T": a word between the mention and its CAR head |
  | unresolved slot argument | 130 | |
  | list-coordinated slot | 48 | "CAR-T targeting CD19 and BCMA" |
  | record guards | 43 | |
  | history/combination marker | 34 | "Following lymphodepletion … " |
  | other | 8 | |

  Stage P would almost certainly also have failed P2.
- **A3:** not hand-audited, because A4 had already failed decisively.
- **Suite:** `tests/se` gave 1552 passed and 3 failed.
  - Two failures are the frozen M6 change: CD3 is no longer a target.
  - One is the "dual" recall loss above.

**Status: FAILED_ACCEPTANCE (A4).** The implementation is reverted. No pipeline run was
requested.

**Diagnosis.** Precision on F1, F2, F5, F6 and F7 behaved as designed, and every named
negative control holds. Two things failed:

1. The grammar has no notion of a CAR's *architecture*: binder, then hinge, then
   costimulatory domain, then signaling domain. Construct components therefore still enter
   through the CAR-head slot.
2. A closed, adjacency-based slot set is far narrower than how registries actually describe
   dual constructs. Examples: "dual CAR-T targeting CD19 and BCMA", "X/CD3 bispecific",
   "Following lymphodepletion …".

Widening the slots after seeing this corpus would be tuning on the binding set. Any successor
needs a new preregistration, and a held-out corpus that this design has not seen.
