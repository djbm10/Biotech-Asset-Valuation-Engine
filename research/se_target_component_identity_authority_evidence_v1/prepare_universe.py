import json
import hashlib
from pathlib import Path

P = Path("/tmp/target_identity_authority_raw")
ROOT = Path.cwd()


def save(name, data):
    (P / name).write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")


h = (P / "hgnc.headers").read_text().lower()
assert "1791894733877675" in h and "f99ab3a0652d842facdc7c3b34961f35" in h
allgenes = json.loads((P / "hgnc.json").read_text())["response"]["docs"]
required = {
    k.split(":", 1)[1]
    for g in json.loads(
        (ROOT / "research/se_target_component_identity_certificate_v1/population.json").read_text()
    )
    for k in g["record_keys"]
    if k.startswith("open_targets:")
}
t = json.loads((P / "chembl_tables.json").read_text())["tables"]
acc = {r["accession"] for r in t["component_sequences"] if r["accession"]}
selected = [
    {"row_index": i, "json_pointer": f"/response/docs/{i}", "raw": r}
    for i, r in enumerate(allgenes)
    if r.get("ensembl_gene_id") in required or acc.intersection(r.get("uniprot_ids", []))
]
save(
    "hgnc_selected.json",
    {
        "artifact_sha256": hashlib.sha256((P / "hgnc.json").read_bytes()).hexdigest(),
        "records": selected,
        "unmatched_existing_ensembl_ids": sorted(
            required - {r["raw"].get("ensembl_gene_id") for r in selected}
        ),
    },
)
universe = sorted(acc | {a for r in selected for a in r["raw"].get("uniprot_ids", [])})
save("uniprot_request_universe.json", universe)
print(len(selected), "genes;", len(universe), "accessions")
