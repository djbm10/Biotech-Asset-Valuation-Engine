# pdcd1_gold_role_authority_v1 — source provenance

External drug->target authority used to annotate the immutable M8 v2 gold set with
`entity_role` / `target_relevance` / `trial_role`. Built under the frozen classification
rules `pdcd1_baseline/diag/GOLD_ENTRY_ROLE_RULES.md`
(sha256 `79fbaeccf31ce0d5052fccb121ca54b1043d1884ea9dedd7bac88e42ddf2b970`,
amendments A1 and A2 both recorded before any entry was adjudicated).

Nothing here reads the S&E pipeline's `QueryVocabulary`, its ontology snapshot, its target
resolver, or any B-lineage run output. The system being measured does not grade itself.

## Primary authority — Open Targets 26.06

retrieved_at_utc: 2026-09-05
base_url: https://ftp.ebi.ac.uk/pub/databases/opentargets/platform/26.06/output/
release: 26.06
datasets: drug_mechanism_of_action, drug_molecule

Per-file `url`, `byte_length` and `sha256` are recorded in `manifest.json` under `files`.

## Corroborating authority — ChEMBL 37

retrieved_at_utc: 2026-09-05
base_url: https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/releases/chembl_37/
release: 37
files: chembl_37_sqlite.tar.gz, checksums.txt, chembl_37_release_notes.txt

The pinned release file is used rather than the REST API: the API serves whichever release
is current, and its `/status` endpoint was returning HTTP 500 during this build, so it
could not even attest its own version. See amendment A2.2.

## Target identity

PDCD1: ENSG00000188389 / gene symbol `PDCD1`
CD274: ENSG00000120217 / gene symbol `CD274` -- classified `NON_PDCD1`, per A1, because
the frozen BuyerProblem declares the single canonical target `PDCD1`.
