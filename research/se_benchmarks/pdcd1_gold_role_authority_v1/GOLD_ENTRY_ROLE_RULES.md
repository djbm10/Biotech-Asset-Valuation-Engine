# M8 v2 gold-entry role annotation — frozen adjudication rules

Status: FROZEN before any adjudication pass was run.
Applies to: `pdcd1_reference_universe_m8v2.csv`, sha256 `8f8cfb0a...c0201fd2f`, 224 rows.

M8 is immutable. This is a derived annotation layer. No row is edited, removed, or
reworded; every original entry keeps its `benchmark_id` and is annotated in a separate
file. Lineage recall against all 224 is reported forever.

## Prime directive

Adjudicate on evidence about **what the entry is**, never on whether the pipeline found
it. An adjudicator may not consult run B6 output, the identity-cliff ledger, mention
lists, or any recall figure. Permitted evidence: the M8 row itself (canonical_asset,
aliases, reference_tier) and the frozen CT.gov corpus text.

Rationale: the annotation layer exists because seeing failures first can silently
reshape a denominator to flatter the model. If the annotation cannot be justified
without reference to pipeline output, it is `UNCERTAIN`.

## Three independent dimensions

Stored separately so the evaluation inclusion rule stays explicit rather than baked into
a single label.

### entity_role — what kind of thing the string names
- `ASSET` — a product/drug identity: INN, brand name, development code, or a stable
  named construct. A real drug is an ASSET regardless of what it targets.
- `PLACEHOLDER` — a mechanism or class description with no stable product identity,
  e.g. "PD-1 x VEGF bispecific antibody", "investigational anti-tumor tablet".
- `INDICATION` — a disease, population, or cohort, e.g. "RAS-mutant/amplified solid
  tumors".
- `PROCEDURE` — radiation, transplant, surgery, diagnostic, biospecimen collection.
- `OTHER` — none of the above.

### target_relevance — whether the entity itself engages PDCD1/PD-1
- `PDCD1_MATCH` — affirmative evidence the entity is itself PDCD1-directed: an anti-PD-1
  antibody, a PD-1-containing multispecific, a PD-1 fusion/cell-therapy construct.
- `NON_PDCD1` — a real entity that does not engage PDCD1 (chemotherapy, anti-VEGF,
  anti-CTLA-4, PD-L1-only agents, targeted small molecules).
- `UNCERTAIN` — frozen evidence does not settle it.

**Appearing in a PDCD1 trial is not evidence of PDCD1_MATCH.** Co-administration,
comparison, and combination all place non-PDCD1 drugs in PDCD1 trials. PD-L1 agents are
`NON_PDCD1`: PD-L1 is CD274, a different gene, even though the axis is shared.

### trial_role — how the entity functions in the trials where it appears
- `INVESTIGATIONAL` — an experimental arm subject of the study.
- `COMBINATION_PARTNER` — co-administered with the experimental agent.
- `COMPARATOR` — control/reference arm.
- `BACKBONE` — chemotherapy or SOC scaffold given across arms.
- `UNKNOWN` — not determinable from frozen evidence.

`trial_role` is context-dependent and may differ per trial; record the predominant role
and note variation. It never overrides `target_relevance`: pembrolizumab used as a
comparator is still `PDCD1_MATCH`, which is why these are separate dimensions and not a
precedence chain.

## Evaluation inclusion rules

1. **M8 strict recall** — denominator = all 224. Never changes. Lineage metric.
2. **PDCD1 asset recall** — denominator = `entity_role == ASSET` and
   `target_relevance == PDCD1_MATCH`. `trial_role` does not filter.
3. **Reachable PDCD1 asset recall** — denominator 2, further restricted to entries
   present in the frozen as-of source universe.

`target_relevance == UNCERTAIN` is excluded from denominators 2 and 3 and reported
separately as a named count. It is never silently folded into either side.

## Adjudication protocol

Two passes over the same frozen evidence, both blind to pipeline outcome. Each records
`entity_role`, `target_relevance`, `trial_role`, a one-line reason, and the evidence
used. Agreement is accepted; disagreement goes to explicit written reconciliation;
anything unresolved after reconciliation is `UNCERTAIN`. Both passes and the
reconciliation are preserved.

## Known limitation of this protocol as executed here

Both passes are produced by the same agent. That is weaker than genuine independent
adjudication and must not be described as inter-rater agreement. Pass A is a
deterministic rule engine over frozen evidence; pass B is separate case-by-case
judgment. Agreement between them shows the rules are consistently applicable, not that
two minds concurred. Entries where they disagree are the honest signal, and any entry
whose classification would change the headline number should be treated as provisional
until a human or a genuinely separate adjudicator reviews it.

---

## Evidence amendment A1 — pre-adjudication

Frozen before any gold-entry role adjudication was performed. Rationale: the original
permitted-evidence clause (M8 row + frozen CT.gov corpus text) cannot separate PD-1 from
PD-L1 agents. INN stems do not distinguish them -- nivolumab, sintilimab, tislelizumab
and dostarlimab are PD-1; durvalumab, atezolizumab, avelumab, adebrelimab and sugemalimab
are PD-L1 -- and CT.gov intervention text rarely states the mechanism. Under the original
clause most of the 224 would fall to `UNCERTAIN`, which is excluded from denominators 2
and 3, destroying the metric this layer exists to produce.

Target relevance may therefore be established using the frozen **Open Targets 26.06
drug/mechanism-of-action dataset** and the **ChEMBL 37 mechanism/target dataset**. These
sources are external to the S&E pipeline under evaluation and must be captured as
separately versioned, hashed evidence artifacts.

- Open Targets 26.06 is the **primary** drug-target authority.
- ChEMBL 37 mechanisms are **corroborating / fallback** evidence.
- If neither resolves the drug, or the two materially disagree, the entry is
  `target_relevance = UNCERTAIN`.

Prohibited as evidence for target relevance:
- the pipeline's `QueryVocabulary`, `targets_in()`, or any pipeline-inferred mapping --
  the system under measurement may not grade itself;
- any hand-curated PD-1/PD-L1 list, including one authored by an adjudicator.

**PD-L1 is not PDCD1 for this benchmark.** `CD274` / PD-L1 resolves to `NON_PDCD1`.
The two are distinct genes; shared pathway membership is not target identity. This holds
unless M8 is shown to define the benchmark as PD-1/PD-L1 rather than PDCD1 -- the frozen
BuyerProblem (`d1788139...`) declares the single canonical target `PDCD1`, so it does not.

Evidence retained per adjudicated drug: `gold_entry`, `source_drug_id`,
`source_drug_name`, `target_id`, `target_symbol`, `mechanism/action_type`, `source`,
`source_release`, `source_record_hash`.

Both the upstream releases named here are the same ones already pinned by the run's
ontology artifact (`chembl_ChEMBL_37__open_targets_26.06__resolver_v1`), so the authority
snapshot introduces no new upstream version into the evaluation.

---

## Evidence amendment A2 — pre-adjudication

Recorded while building `pdcd1_gold_role_authority_v1`, before any gold entry was
adjudicated. Two constraints on how the authority snapshot may be read.

**A2.1 — Only curator-sourced drug names are identity evidence.**
Open Targets `drug_molecule.synonyms` and `.tradeNames` are arrays of `{label, source}`
structs. Labels carrying `source: "AACT"` are derived from clinical-trial registration free
text — the same substrate the pipeline under measurement reads — and include non-specific
class terms (`immunotherapy`, `anti-pd-1`, `anti-pd-1/pd-l1 antibodies`, `cpi`, `ici`).
Admitting them would (a) let registry text grade a benchmark about reading registry text,
and (b) collide every checkpoint inhibitor onto every other via shared class strings.
Therefore only `source: "ChEMBL"` labels plus the canonical `drug_molecule.name` are used
for name resolution. Normalised keys shorter than 4 characters are discarded.

**A2.2 — ChEMBL 37 evidence is taken from the pinned release file, not the REST API.**
`https://www.ebi.ac.uk/chembl/api/data/status.json` was returning HTTP 500 during the
build, and the REST API in any case serves whichever release is current rather than the
release named in amendment A1. The corroborating layer is therefore extracted from
`chembl_37_sqlite.tar.gz` under `ChEMBLdb/releases/chembl_37/`, whose published
`checksums.txt` is retained alongside it. Release identity is thus a property of the
evidence file, not of when it was fetched.

A binding is `PDCD1_MATCH` only on gene symbol `PDCD1` (Ensembl `ENSG00000188389`).
`CD274` (`ENSG00000120217`) remains `NON_PDCD1` per A1.

---

## Evidence amendment A3 — pre-adjudication

Recorded while building `pdcd1_gold_role_authority_v1`, before any gold entry was
adjudicated. Constrains how an authority record may be attached to a gold entry.

**A3.1 — Matching is exact and identifier-based.**
Permitted normalisation is limited to Unicode compatibility folding, case, trademark
symbols, punctuation and whitespace collapse. Fuzzy, prefix and edit-distance matching are
prohibited. Normalised keys shorter than 4 characters are discarded.

**A3.2 — A development code must appear verbatim as an authority synonym.**
Sponsor, trial context, indication and co-mention are never used to infer that a code
denotes a given molecule. If the code is not in the authority's name table, the entry stays
unresolved.

**A3.3 — Component targets are not inherited by coformulations or combinations.**
Authority labels of the form `... component of <formulation>` or `... in combination with
...` are evidence about the ingredient only, and are excluded from the name index. A gold
entry that resolves to more than one distinct molecule is flagged `MULTI_MOLECULE_MATCH`;
a gold entry whose own text denotes a coformulation, combination, conjugate or biosimilar
is flagged `COFORMULATION_OR_COMBINATION_STRING`. A flagged entry receives a target verdict
only where the authority data explicitly covers the formulation itself, or where its
composition is independently established under these rules. Otherwise it is `UNCERTAIN`.

**A3.4 — Precedence between the two authorities.**
`AGREE` -> the agreed verdict.
`SINGLE_SOURCE` -> admissible, provided the resolving source is one of the two named
authorities and the identity match is exact under A3.1-A3.2.
`DISAGREE` -> `UNCERTAIN`, unless the precedence chain already frozen in these rules
explicitly resolves that specific disagreement.
`UNRESOLVED` -> decided by role evidence, or `UNCERTAIN`.

**A3.5 — The unresolved set is not to be shrunk before adjudication.**
No rule may be added, and no authority extended, for the purpose of reducing the count of
unresolved gold entries. The unresolved set is a finding, not a defect to be tuned away.

---

## Evidence amendment A4 — pre-adjudication

**The two authorities are not evidentially independent.**
Open Targets `drug_mechanism_of_action` is substantially derived from ChEMBL; the
`chemblIds` join key in the Open Targets records is itself a ChEMBL identifier. Agreement
between them is therefore corroboration across two representations and two processing
pipelines of a largely shared underlying curation -- not two independent biological
confirmations.

Consequences for adjudication:
- `AGREE` means "both representations of the curated record say the same thing". It raises
  confidence that the record was read correctly. It does not raise confidence that the
  record is biologically correct, and it must not be reported as independent confirmation.
- The observed zero true conflicts (no entry where one authority says `PDCD1` and the other
  says `CD274`) is consistent with shared provenance and is weak evidence of correctness.
  It is reported as an internal-consistency check, not as validation.
- A shared upstream error would appear as `AGREE`. Neither authority can detect it.
- `SINGLE_SOURCE` is therefore not a large evidential step down from `AGREE`, and must not
  be discounted as though it were.

No independent third authority is introduced here. Adding one after seeing the failure
distribution would be selecting evidence on the outcome, which these rules exist to prevent.
