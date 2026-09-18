"""Extract the ChEMBL 37 corroborating drug->target layer from the pinned SQLite release.

The release tarball is version-pinned and checksummed, unlike the live REST API, which
serves whatever release is current and whose /status endpoint was returning 500s when this
was built. Rule A1 names ChEMBL 37 specifically, so the release file is the evidence.
"""
import hashlib, json, pathlib, sqlite3, tarfile

ROOT = pathlib.Path("/home/djmann/staging/pdcd1_gold_role_authority_v1")
SRC = ROOT / "sources/chembl_37"
TARBALL = SRC / "chembl_37_sqlite.tar.gz"

db_path = next(SRC.rglob("chembl_37.db"), None)
if db_path is None:
    with tarfile.open(TARBALL) as tf:
        member = next(m for m in tf.getmembers() if m.name.endswith("chembl_37.db"))
        tf.extract(member, SRC, filter="data")
    db_path = SRC / member.name
print("db:", db_path)

con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
con.row_factory = sqlite3.Row

# One row per (molecule, mechanism, target component). Gene symbol comes from the
# component synonym table, which is how ChEMBL names the protein a target maps to.
rows = con.execute(
    """
    SELECT md.chembl_id            AS molecule_chembl_id,
           md.pref_name            AS molecule_pref_name,
           dm.mec_id               AS mec_id,
           dm.action_type          AS action_type,
           dm.mechanism_of_action  AS mechanism_of_action,
           dm.direct_interaction   AS direct_interaction,
           td.chembl_id            AS target_chembl_id,
           td.pref_name            AS target_pref_name,
           td.target_type          AS target_type,
           td.organism             AS organism,
           cs.component_synonym    AS gene_symbol,
           cseq.accession          AS uniprot_accession
    FROM drug_mechanism dm
    JOIN molecule_dictionary md ON md.molregno = dm.molregno
    LEFT JOIN target_dictionary td ON td.tid = dm.tid
    LEFT JOIN target_components tc ON tc.tid = td.tid
    LEFT JOIN component_sequences cseq ON cseq.component_id = tc.component_id
    LEFT JOIN component_synonyms cs
           ON cs.component_id = tc.component_id AND cs.syn_type = 'GENE_SYMBOL'
    """
).fetchall()

with open(ROOT / "chembl37_mechanisms.jsonl", "w") as fh:
    for r in rows:
        fh.write(json.dumps(dict(r), sort_keys=True) + "\n")
print("mechanism rows:", len(rows))

# Molecule name index, for gold entries Open Targets could not resolve by name.
names = con.execute(
    """
    SELECT md.chembl_id, md.pref_name, ms.synonyms, ms.syn_type
    FROM molecule_dictionary md
    LEFT JOIN molecule_synonyms ms ON ms.molregno = md.molregno
    """
).fetchall()
with open(ROOT / "chembl37_molecule_names.jsonl", "w") as fh:
    for r in names:
        fh.write(json.dumps(dict(r), sort_keys=True) + "\n")
print("name rows:", len(names))

pdcd1 = {r["molecule_chembl_id"] for r in rows if r["gene_symbol"] == "PDCD1"}
cd274 = {r["molecule_chembl_id"] for r in rows if r["gene_symbol"] == "CD274"}
print(f"molecules binding PDCD1: {len(pdcd1)}  CD274: {len(cd274)}")

meta = {
    "source": "chembl",
    "release": "37",
    "role": "corroborating",
    "evidence_file": "chembl_37.db from chembl_37_sqlite.tar.gz",
    "mechanism_rows": len(rows),
    "molecule_name_rows": len(names),
    "pdcd1_molecule_count": len(pdcd1),
    "cd274_molecule_count": len(cd274),
    "mechanisms_sha256": hashlib.sha256((ROOT / "chembl37_mechanisms.jsonl").read_bytes()).hexdigest(),
}
(ROOT / "chembl37_manifest.json").write_text(json.dumps(meta, indent=2))
print(json.dumps(meta, indent=2))
