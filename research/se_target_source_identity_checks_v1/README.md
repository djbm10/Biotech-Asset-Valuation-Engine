# TARGET SOURCE IDENTITY CHECKS v1 — diagnosis complete

Baseline `f7bcaa8`; read-only diagnosis of the three multi-symbol groups in the frozen Greek proposal population. No production changes, live asset searches/replays, or holdout probes. Authority API reads are captured verbatim with URL/date/SHA-256 in `authority_receipts.json`.

| Installed merged target | Current approved identities | Protein sequences | Shared cross-gene edges | New single-gene alias decision |
|---|---|---|---|---|
| TUBA1B | HGNC:20766/TUBA1A/Q71U36; HGNC:18809/TUBA1B/P68363 | Two distinct 451-aa sequences | Two inactive, demerged accessions | UNRESOLVED |
| IFNA1 | HGNC:5417/IFNA1/P0DY56; HGNC:5419/IFNA13/A0A087WWS6 | Distinct 189/190-aa sequences | Ten edges through inactive, demerged accessions | UNRESOLVED |
| CALM2 | HGNC:1442/CALM1/P0DP23; HGNC:1445/CALM2/P0DP24; HGNC:1449/CALM3/P0DP25 | One identical 149-aa sequence across three genes | 27 inactive/demerged edges; six edges through two unreviewed multi-gene records | UNRESOLVED |

## Grounded interpretation

HGNC supplies distinct approved gene IDs and Ensembl IDs for all seven genes. Reviewed UniProt entries independently link each current primary accession to its corresponding HGNC identity. The complete captures and calculated sequence hashes are in `identity_audit.json`.

Tubulin's shared P04687 and P05209 are explicitly DEMERGED. Interferon's P01562 and the other shared historical identifiers are also inactive/demerged: P01562 points to A0A087WWS6 and P0DY56. These are one-to-many historical relationships, not current equivalence assertions. See the captured [UniProt P01562 record](https://rest.uniprot.org/uniprotkb/P01562.json), [P04687](https://rest.uniprot.org/uniprotkb/P04687.json) and [P05209](https://rest.uniprot.org/uniprotkb/P05209.json).

Calmodulin's identical protein sequences do not make its three approved genes interchangeable. Its shared Q96HK3 resolves to demerged P62158; B4DJ51 and Q96HY3 are unreviewed records spanning multiple gene annotations. A protein-level common-name entity could be a future explicit representation, but the current gene-symbol target cannot elect one gene and claim that the other two are the same gene. See [CALM1](https://rest.genenames.org/fetch/symbol/CALM1), [CALM2](https://rest.genenames.org/fetch/symbol/CALM2), [CALM3](https://rest.genenames.org/fetch/symbol/CALM3), and the three reviewed UniProt captures.

## First failure boundary

`_group_records` unions any shared configured identifier, including secondary, demerged and multi-gene UniProt accessions. `_elect_symbol` overwrites earlier symbols from the same source before calculating canonical disagreement. Consequently a RESOLVED status and absence of that disagreement flag do not certify a single gene. This diagnosis preserves the installed merged groups and all existing resolver outcomes; repairing the graph is a separate behavior-changing milestone.

## Consequence for new alias admission

No new Greek/common-name alias may inherit a single-gene identity from these groups. This is a general abstention requirement, not a three-target blacklist. Examine all contributing gene identities; a shared historical accession, identical sequence, elected display symbol, or missing disagreement flag is insufficient. Require unambiguous authority-backed identity before admitting a new orthographic alias. Shared aliases elsewhere on an otherwise coherent entity do not by themselves invalidate an unrelated, uniquely grounded lookup.

Ninety of the 96 frozen proposals have uniquely resolved original spellings without multiple source-record symbols; three original spellings are ambiguous and three resolved groups are multi-gene. This is diagnosis, not a guarantee of ninety future admissions: any additional normalization collision must remain unresolved. Twenty-nine long names exceed five whitespace tokens, a separate parser coverage boundary.

Next: preregister a conservative target-only Greek orthography rule and explicit source-identity guard, preserving existing exact lookup behavior and raw ambiguity. Freeze the full authority-derived collision oracle before production changes. NCIt common-name admission needs its own source/term annotation checks; do not infer it from this orthographic study. Keep human-PoC recovery stopped and ranking/qualification/duplicates unchanged. H21–H25 remain untouched; H6–H10 remain secondary/unrun.
