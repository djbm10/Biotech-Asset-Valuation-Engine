import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path.cwd()
OUT = Path("/tmp/target_identity_authority_raw")
DB = Path(
    "/home/djmann/staging/pdcd1_gold_role_authority_v1/sources/chembl_37/chembl_37/chembl_37_sqlite/chembl_37.db"
)
c = sqlite3.connect("file:" + str(DB) + "?mode=ro", uri=True)
c.row_factory = sqlite3.Row
pop = json.loads(
    (ROOT / "research/se_target_component_identity_certificate_v1/population.json").read_text()
)
required = sorted(
    {k.split(":", 1)[1] for g in pop for k in g["record_keys"] if k.startswith("chembl:")}
)


def rows(sql, args=()):
    return [dict(r) for r in c.execute(sql, args)]


def selected(table, column, ids):
    if not ids:
        return []
    return rows(
        "SELECT * FROM "
        + table
        + " WHERE "
        + column
        + " IN ("
        + ",".join("?" for _ in ids)
        + ") ORDER BY rowid",
        sorted(ids),
    )


types = [
    "SINGLE PROTEIN",
    "CHIMERIC PROTEIN",
    "PROTEIN COMPLEX",
    "PROTEIN COMPLEX GROUP",
    "PROTEIN FAMILY",
    "PROTEIN-PROTEIN INTERACTION",
    "SELECTIVITY GROUP",
]
base = selected("target_dictionary", "chembl_id", required)
controls = {
    t: rows(
        "SELECT * FROM target_dictionary WHERE target_type=? AND tax_id=9606 ORDER BY tid LIMIT 3",
        (t,),
    )
    for t in types
}
initial = {r["tid"] for r in base} | {r["tid"] for rr in controls.values() for r in rr}
q = ",".join("?" for _ in initial)
relations = rows(
    "SELECT * FROM target_relations WHERE tid IN ("
    + q
    + ") OR related_tid IN ("
    + q
    + ") ORDER BY targrel_id",
    sorted(initial) * 2,
)
allids = initial | {r[k] for r in relations for k in ["tid", "related_tid"]}
mem = selected("target_components", "tid", allids)
compids = {r["component_id"] for r in mem}
tables = {
    "target_dictionary": selected("target_dictionary", "tid", allids),
    "target_components": mem,
    "component_sequences": selected("component_sequences", "component_id", compids),
    "component_synonyms": selected("component_synonyms", "component_id", compids),
    "target_relations": relations,
    "target_type": rows("SELECT * FROM target_type ORDER BY target_type"),
    "version": rows("SELECT * FROM version ORDER BY name"),
}
schema = rows(
    "SELECT name,sql FROM sqlite_master WHERE type='table' AND name IN ("
    + ",".join("?" for _ in tables)
    + ") ORDER BY name",
    list(tables),
)
assert any(r["name"] == "ChEMBL_37" for r in tables["version"])
selection = {
    "required_chembl_ids": required,
    "controls": controls,
    "initial_tids": sorted(initial),
    "expanded_tids": sorted(allids),
    "membership_counts": {
        str(tid): len({m["component_id"] for m in mem if m["tid"] == tid}) for tid in initial
    },
}
(OUT / "chembl_selection.json").write_text(json.dumps(selection, sort_keys=True, indent=2) + "\n")
(OUT / "chembl_tables.json").write_text(
    json.dumps(
        {"release": "ChEMBL_37", "database_path": str(DB), "schema": schema, "tables": tables},
        sort_keys=True,
        separators=(",", ":"),
    )
    + "\n"
)
print("acquired", len(base), len(allids), len(compids), flush=True)
print(
    "control membership",
    {t: [selection["membership_counts"][str(r["tid"])] for r in rr] for t, rr in controls.items()},
    flush=True,
)
h = hashlib.sha256()
with DB.open("rb") as f:
    while b := f.read(8 * 1024 * 1024):
        h.update(b)
(OUT / "chembl_artifact.json").write_text(
    json.dumps(
        {
            "path": str(DB),
            "sha256": h.hexdigest(),
            "bytes": DB.stat().st_size,
            "release": "ChEMBL_37",
            "original_lost_api_artifact": False,
        },
        sort_keys=True,
        indent=2,
    )
    + "\n"
)
print("sha", h.hexdigest(), flush=True)
