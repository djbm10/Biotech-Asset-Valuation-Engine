# TARGET_QUERY_ALIAS_COVERAGE v1

**Status: OPEN — diagnosis and authority/design freeze; production unchanged.**
Primary H21–H25 was frozen first in **1e1705c** and remains UNRUN. H17/H20 are
development-only diagnostic queries. H6–H10 remain unrun and secondary. The
human-PoC thread is closed: no recovery of the 14 unsupported ownership claims.
The R7 capitalization defect belongs to a later reproducibility milestone;
the prednisone/prednisolone oracle remains a failed preregistration, unchanged.

## Scope and mandatory boundaries

Resolve protein/common-name language only through authority-backed equivalence
to a specific human biological target. No fuzzy matching, substrings, deletion
of biological qualifiers, target-specific code branches or benchmark exceptions.
Preserve target-affix grammar, dual-target separators, ambiguity, family/complex
and isoform boundaries. No indication, asset identity, qualification, ranking,
human-PoC, routing or live source-discovery behavior change.

## Authority relationships established before implementation

- HGNC:6015 approves **IL4R**, linked to UniProt **P24394** and Ensembl
  **ENSG00000077238**. Reviewed UniProt P24394 names the interleukin-4 receptor
  alpha subunit, lists **IL4RA** as a gene synonym, and explicitly lists
  **IL-4R-alpha** among its protein short names. Thus IL4RA is not the approved
  symbol to substitute blindly. Greek-letter spelling equivalence must retain
  alpha rather than erase the subunit.
- HGNC:3529 approves **F11**, linked to **P03951** and **ENSG00000088926**.
  NCI protein concept **C201572** explicitly lists **Factor XI** as a synonym,
  has Swiss_Prot=P03951, and a Gene_Product_Encoded_By_Gene relationship to
  **C201570**, whose HGNC_ID is HGNC:3529. This is an identifier-backed chain,
  not a substring of “coagulation factor XI.”
- NCI also lists “Factor XI” on **C163435, Factor XI Measurement**. A generic
  synonym search is insufficient: measurement, disease, family, complex and
  protein concepts must be distinguished before any alias is admitted.
- The installed ontology resolves **F11** ambiguously between TARGET:F11 and
  TARGET:ZNF160 (the latter has a historical F11 alias). **FXI** resolves uniquely
  to TARGET:F11. Bare F11 ambiguity must not be silently overridden to make a
  benchmark pass.

Primary sources: [HGNC IL4R](https://rest.genenames.org/fetch/hgnc_id/HGNC:6015),
[UniProt P24394](https://www.uniprot.org/uniprotkb/P24394/entry),
[HGNC F11](https://rest.genenames.org/fetch/hgnc_id/HGNC:3529),
[UniProt P03951](https://www.uniprot.org/uniprotkb/P03951/entry),
[NCI protein C201572](https://evsexplore.semantics.cancer.gov/evsexplore/concept/ncit/C201572).
Exact downloaded payloads and hashes accompany the research packet.

## First failure boundaries

H17: the adopted affix pass removes `anti-` successfully. The remainder
`IL-4Rα` does not equal an installed lookup key. The installed entity already
has authority-provided `IL-4R-alpha`; the missing relationship is conservative
Greek-letter orthography, not a need to invent a gene mapping.

H20: `factor XI` has no installed exact alias; the installed approved name is
`coagulation factor XI`. The two-token phrase reaches the resolver and remains
unresolved. Removing “coagulation” from names would be substring inference and
is not authorized. The NCI relationship above establishes the actual alias.

There is a second, independent boundary: even the already recognized **FXI**
query compiles to the display symbol F11, then `compile_problem_queries` raises
AmbiguousTargetError when that string is resolved again. A valid implementation
must preserve the already certified entity across intent, buyer-problem and
discovery compilation. It cannot merely add a parser alias and claim H20 works.
Existing fully qualified ontology IDs may provide the smallest representation;
their compatibility and semantic deduplication must be tested before choosing
that design. Do not change ambiguity policy or widen query scope to bypass it.

## Frozen development population

`research/se_target_query_alias_coverage_v1/survey_freeze.json` defines an
outcome-independent sample from the installed, versioned Open Targets/ChEMBL
authority: 192 cross-linked protein targets selected by stable identifier hash,
their symbols, approved names and one authority alias each; plus 96 distinct
Greek spelling proposals selected by stable source/alias hash. Total **672
forms across 276 authority entities**, with 16 explicit scientific/ambiguity
controls. No resolver outputs determine selection. The authority rows, exact
strings, identifier links and selection code are frozen before surveying them.
Greek variants are explicitly *proposals*, not newly declared biological aliases.

The survey will record raw resolver outcome, parsed targets, provenance,
affix/separator behavior and downstream compilation where applicable. Long
protein names beyond the existing two-token target path are reported separately;
no silent widening of phrase grammar. Conflicting aliases remain ambiguous.

Primary and secondary heldout biological concepts are excluded before selection.
Their complete bulk-authority presence does not authorize inspection or probing.
H17/H20 and their alternate forms are diagnostic controls, never heldout evidence.

## Implementation prerequisites and acceptance contract

Before production edits, freeze the exact admitted authority-source population,
normalization relation, input/version hashes, expected positives/abstentions,
identity-carrying interface and implementation file scope. This opening document
does not authorize choosing a new rule after its first acceptance score.

The eventual candidate must satisfy all of these measurable checks:

1. Every new alias has a versioned exact authority assertion and a unique
   identifier chain to one existing human target; no name-only entity joins.
2. H17 and H20 resolve to the authority-certified IL4R/F11 entities and compile
   complete discovery plans offline without substituting their query text.
3. All frozen ambiguity, wrong-subunit, confusable-character, disease,
   measurement, family, isoform and activation-state controls preserve their
   stated boundary. Receipt of a similarly named authority hit is insufficient.
4. Bare, affixed and separator forms preserve the adopted grammar and biological
   identity. Alias-equivalent mentions deduplicate as the same entity, including
   mixed old/new aliases. Do not turn two spellings into a dual-target request.
5. Existing canonical benchmark intents and target-affix/separator controls
   preserve their biological targets, operators and refusal semantics. Any
   serialization change needed to carry identity must be explicitly preregistered.
6. Missing, conflicting or unversioned authority data fail closed. Runtime
   resolution uses a pinned local artifact and makes no live authority requests.
7. Full `tests/se` passes except existing xfails; required Ruff checks are clean.
   Human-PoC code and previously frozen failures remain byte-identical.
8. H21–H25 and H6–H10 remain unrun/unprobed; H17/H20 gains are diagnostic only.

If a safe, narrowly scoped identity path cannot be established, record the
architectural boundary and stop before implementation. Do not deploy a partial
alias fix that resolves the displayed target but fails or changes its identity
downstream. If an implemented, fully preregistered candidate fails acceptance,
record and revert normally without post-result rule changes.

## Dependency outcome (2026-10-12)

The separate resolved-identity preservation dependency was preregistered in
533c699, implemented in 612c088, failed in ed33b7d, and reverted in 7e8f58e.
Its three-file approach changes legacy target serialization and leaks internal IDs
into source-query text. Alias coverage remains OPEN; no new alias behavior was
adopted. Next: diagnose an explicit identity-versus-retrieval interface and frozen
consumer migration contract. Do not patch the failed candidate or revise its
acceptance. NCIt bulk structural survey is diagnosis only, not alias admission.
