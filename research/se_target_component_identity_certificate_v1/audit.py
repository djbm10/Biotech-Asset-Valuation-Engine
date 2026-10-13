"""Frozen source-readiness audit; no production certificates are emitted."""

import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from bve.se.ontology.bulk import iter_rows

ROOT = Path.cwd()
STUDY = ROOT / "research/se_target_component_identity_certificate_v1"
OUT = Path("/tmp/component_certificate_audit")
OUT.mkdir(exist_ok=True)
SIDE = Path("/home/djmann/se_runs/authority_assertion_provenance_sidecar_v1/seed0")


def canonical(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def write(name, v):
    b = (canonical(v) + "\n").encode()
    (OUT / name).write_bytes(gzip.compress(b, mtime=0) if name.endswith(".gz") else b)


for path, sha in json.loads((STUDY / "inputs.json").read_text()).items():
    p = STUDY / path if path == "population.json" else ROOT / path
    assert hashlib.sha256(p.read_bytes()).hexdigest() == sha, path
manifest = json.loads(
    (
        ROOT
        / "research/se_authority_assertion_provenance_sidecar_v1/results/artifact_manifest.json"
    ).read_text()
)
assert (
    hashlib.sha256((SIDE / "assertions.jsonl.gz").read_bytes()).hexdigest()
    == manifest["assertions.jsonl.gz"]
)
pop = json.loads((STUDY / "population.json").read_text())
wanted = {g["component_id"] for g in pop}
keys = {k for g in pop for k in g["record_keys"]}
assertions = {}
by_record = defaultdict(list)
all_components = defaultdict(set)
with gzip.open(SIDE / "assertions.jsonl.gz", "rt") as f:
    for line in f:
        r = json.loads(line)
        for c in r["resolver_components"]:
            all_components[c["canonical_id"]].add(c["component_id"])
        if r["source_record_key"] in keys:
            assertions[r["assertion_id"]] = r
            by_record[r["source_record_key"]].append(r["assertion_id"])
raw = {}
for artifact in json.loads((SIDE / "raw_artifacts.json").read_text()):
    path = Path(artifact["path"])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
    for index, r in enumerate(iter_rows(path)):
        key = "open_targets:" + str(r.get("id") or r.get("ensemblId"))
        if key in keys:
            raw[key] = {
                "artifact_sha256": artifact["sha256"],
                "artifact_path": str(path),
                "row_index": index,
                "record": r,
            }
write("raw_records.json.gz", raw)
write("assertions.json.gz", assertions)
audit = []
by_component = {}
for g in pop:
    genes = []
    members = []
    for key in g["record_keys"]:
        source = key.split(":")[0]
        rr = raw.get(key)
        ids = sorted(by_record[key])
        rows = [assertions[i] for i in ids]
        member = {
            "source_record_key": key,
            "authority": source,
            "release": "26.06" if source == "open_targets" else "ChEMBL_37",
            "raw_record_available": rr is not None,
            "assertion_ids": ids,
            "primary_assertions": [
                r for r in rows if r["field_path"] in [["approvedSymbol"], ["approvedName"]]
            ],
            "normalized_record": next(
                r for r in g["records"] if r["source"] + ":" + r["source_id"] == key
            ),
        }
        if rr:
            r = rr["record"]
            gene = {
                "record_key": key,
                "entity_id": r.get("id"),
                "approvedSymbol": r.get("approvedSymbol"),
                "approvedName": r.get("approvedName"),
                "biotype": r.get("biotype"),
                "raw_locator": {k: v for k, v in rr.items() if k != "record"},
                "symbol_assertion_ids": [
                    a["assertion_id"] for a in rows if a["field_path"] == ["approvedSymbol"]
                ],
            }
            genes.append(gene)
        else:
            member["missing_structure_fields"] = [
                "target_type",
                "target_components[].component_id",
                "target_components[].accession",
                "target_components[].relationship",
                "target_components[].target_component_synonyms",
            ]
        members.append(member)
    symbol = g["canonical_id"].removeprefix("TARGET:")
    canonical_genes = [x["record_key"] for x in genes if x["approvedSymbol"] == symbol]
    missing = [m["source_record_key"] for m in members if not m["raw_record_available"]]
    primary_supported = (
        len(members) == 1
        and len(genes) == 1
        and len(canonical_genes) == 1
        and len(all_components[g["canonical_id"]]) == 1
    )
    result = {
        "component_id": g["component_id"],
        "canonical_id": g["canonical_id"],
        "canonical_label": g["canonical_label"],
        "categories": g["categories"],
        "members": members,
        "source_genes": genes,
        "canonical_gene_candidates": canonical_genes,
        "canonical_id_components": sorted(all_components[g["canonical_id"]]),
        "missing_raw_members": missing,
        "component_structural_type": "UNDETERMINED"
        if missing or len(genes) != 1
        else "SINGLE_GENE_RECORD",
        "primary_gene_mapping_supported": primary_supported,
        "certificate_status": "NOT_ISSUED",
        "diagnostic_status": "AMBIGUOUS",
        "reason": "Original component structure/relationship evidence missing; grouping does not establish equivalence."
        if missing
        else "Primary gene identity may be grounded, but not every alias denotes that entity; no whole-component certificate inferred.",
    }
    audit.append(result)
    by_component[g["component_id"]] = result
write("component_audit.json.gz", audit)
prior = json.loads(
    gzip.decompress(
        (
            ROOT / "research/se_target_mention_role_decision_v1/candidate_component_audit.json.gz"
        ).read_bytes()
    )
)
blocked = [r for r in prior if r["multiple_source_gene_records"]]
decisions = []
for r in blocked:
    observations = []
    for e in r["mention"]["authority_evidence"]:
        group = by_component[e["component_id"]]
        for aid in e["assertion_ids"]:
            a = assertions[aid]
            conflict = (
                a["field_path"] in [["approvedName"], ["approvedSymbol"]]
                and len(group["canonical_gene_candidates"]) == 1
                and a["source_record_key"] not in group["canonical_gene_candidates"]
            )
            observations.append(
                {
                    "assertion_id": aid,
                    "raw_text": a["raw_component"],
                    "raw_locator": {
                        k: a[k]
                        for k in [
                            "artifact_sha256",
                            "artifact_path",
                            "record_id",
                            "row_index",
                            "field_path",
                            "source_record_key",
                            "release",
                        ]
                    },
                    "canonical_gene_candidates": group["canonical_gene_candidates"],
                    "primary_gene_identity_conflict": conflict,
                    "reason": "Explicit source gene approved name/symbol belongs to a different source gene than the elected canonical gene."
                    if conflict
                    else "No single-entity equivalence inferred from a synonym or from membership in the merged group.",
                }
            )
    status = (
        "CONFLICT"
        if any(o["primary_gene_identity_conflict"] for o in observations)
        else "AMBIGUOUS"
    )
    decisions.append(
        {
            "id": r["id"],
            "query": r["query"],
            "canonical_id": r["canonical_id"],
            "diagnostic_status": status,
            "certificate_status": "NOT_ISSUED",
            "evidence": observations,
        }
    )
write("blocked_86_audit.json", decisions)
missing = sorted({k for a in audit for k in a["missing_raw_members"]})
counts = {
    "population_components": len(pop),
    "implicated_components": sum("nine_implicated_groups" in a["categories"] for a in audit),
    "raw_records": len(raw),
    "sidecar_assertions": len(assertions),
    "missing_raw_members": len(missing),
    "missing_raw_member_keys": missing,
    "primary_gene_mapping_supported_controls": sum(
        a["primary_gene_mapping_supported"] for a in audit
    ),
    "blocked_proposals": len(decisions),
    "blocked_diagnostic_statuses": dict(Counter(r["diagnostic_status"] for r in decisions)),
    "certified_single_entity": 0,
    "certified_multi_entity": 0,
    "certified_relational_entity": 0,
    "still_without_permitting_certificate": len(decisions),
    "gate_G0": "FAIL",
    "implementation": "NOT_STARTED",
    "raw_structure_gap": "Original ChEMBL_37 target responses absent. Normalized snapshot discards type, component ownership and relationship fields. Frozen bulk fetch restricts target_type=SINGLE PROTEIN; no positive complex/relational type population can be invented from lexical probes.",
}
write("summary.json", counts)
write(
    "hashes.json",
    {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(OUT.iterdir())
        if p.name != "hashes.json"
    },
)
print(canonical(counts))
