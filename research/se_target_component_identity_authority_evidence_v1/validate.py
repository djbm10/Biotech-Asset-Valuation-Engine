"""Independent source-record and assertion replay for the frozen evidence layer."""

import argparse
import gzip
import hashlib
import json
import sqlite3
from collections import Counter
from functools import lru_cache
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while b := f.read(8 * 1024 * 1024):
            h.update(b)
    return h.hexdigest()


def encode(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def lines(path):
    with gzip.open(path, "rt") as f:
        for line in f:
            yield json.loads(line)


def run(raw, build0, build42, root):
    checks = {}
    failures = []

    def check(name, passed, detail=None):
        checks[name] = {"pass": bool(passed), "detail": detail}
        if not passed:
            failures.append(name)

    capture = json.loads((raw / "chembl_tables.json").read_text())
    tables = capture["tables"]
    selection = json.loads((raw / "chembl_selection.json").read_text())
    database = json.loads((raw / "chembl_artifact.json").read_text())
    conn = sqlite3.connect("file:" + database["path"] + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    required = set(selection["required_chembl_ids"])
    available = {r["chembl_id"] for r in tables["target_dictionary"]}
    check("S1_all_29_targets", len(required) == 29 and required <= available)
    check(
        "S1_control_types", len(selection["controls"]) == 7 and all(selection["controls"].values())
    )
    for kind in ["CHIMERIC PROTEIN", "PROTEIN COMPLEX", "PROTEIN-PROTEIN INTERACTION"]:
        check(
            "S1_constituents_" + kind,
            any(
                selection["membership_counts"][str(r["tid"])] >= 2
                for r in selection["controls"][kind]
            ),
        )
    fields = {
        "target_dictionary": ["tid", "target_type", "pref_name", "tax_id", "organism", "chembl_id"],
        "target_components": ["tid", "component_id", "targcomp_id", "homologue"],
        "component_sequences": [
            "component_id",
            "component_type",
            "accession",
            "description",
            "tax_id",
            "db_source",
            "db_version",
        ],
        "component_synonyms": ["compsyn_id", "component_id", "component_synonym", "syn_type"],
        "target_relations": ["tid", "relationship", "related_tid", "targrel_id"],
    }
    check(
        "S1_structural_fields",
        all(tables[t] and all(set(f) <= set(r) for r in tables[t]) for t, f in fields.items()),
    )
    hg = json.loads((raw / "hgnc_selected.json").read_text())["records"]
    check(
        "S1_gene_fields",
        bool(hg)
        and all({"hgnc_id", "symbol", "name", "status", "locus_type"} <= set(x["raw"]) for x in hg),
    )
    receipts = json.loads((raw / "uniprot_receipts.json").read_text())
    uniprot = [
        json.loads((raw / r["artifact"]).read_text())
        for r in receipts
        if r.get("http_status") == 200
    ]
    reviewed = [r for r in uniprot if r.get("entryType") == "UniProtKB reviewed (Swiss-Prot)"]
    check(
        "S1_reviewed_protein_fields",
        bool(reviewed)
        and all(
            {
                "primaryAccession",
                "proteinDescription",
                "organism",
                "entryAudit",
                "uniProtKBCrossReferences",
            }
            <= set(r)
            for r in reviewed
        ),
    )
    check(
        "S1_gene_protein_links",
        any(x["raw"].get("uniprot_ids") for x in hg)
        and any(
            any(x["database"] == "HGNC" for x in r.get("uniProtKBCrossReferences", []))
            for r in reviewed
        ),
    )
    check(
        "S2_release",
        all(r.get("release_matches", False) for r in receipts)
        and any(r["name"] == "ChEMBL_37" for r in tables["version"]),
    )
    manifest = json.loads((raw / "raw_manifest.json").read_text())
    check("S2_raw_hashes", all(sha(raw / name) == v for name, v in manifest.items()))
    check("S2_database_hash", sha(Path(database["path"])) == database["sha256"])

    @lru_cache(maxsize=3)
    def load(name):
        return json.loads((raw / name).read_text())

    records = {}
    record_replay = True
    for r in lines(build0 / "records.jsonl.gz"):
        source = r["source"]
        v = load(source["capture_artifact"])
        for key in source["capture_path"]:
            v = v[key]
        record_replay &= (
            v == r["raw"] and hashlib.sha256(encode(source)).hexdigest() == r["record_id"]
        )
        if source["source"] == "chembl":
            table = source["locator"]["table"]
            pk = source["locator"]["pk"]
            key, value = next(iter(pk.items()))
            original = conn.execute(f"SELECT * FROM {table} WHERE {key}=?", (value,)).fetchall()
            record_replay &= len(original) == 1 and dict(original[0]) == r["raw"]
        records[r["record_id"]] = r
    count = 0
    assertion_replay = True
    seen = set()
    for a in lines(build0 / "assertions.jsonl.gz"):
        record = records[a["record_id"]]
        v = record["raw"]
        for key in a["field_path"]:
            v = v[key]
        identifier = a["assertion_id"]
        body = {k: v for k, v in a.items() if k != "assertion_id"}
        assertion_replay &= (
            v == a["raw_value"]
            and a["source"] == record["source"]
            and a["transformations"] == [{"operation": "identity"}]
            and hashlib.sha256(encode(body)).hexdigest() == identifier
            and identifier not in seen
        )
        seen.add(identifier)
        count += 1
    check("S3_record_replay", record_replay, len(records))
    check("S3_assertion_replay", assertion_replay, count)
    imported_members = [
        r["raw"]
        for r in records.values()
        if r["source"]["source"] == "chembl"
        and r["source"]["locator"]["table"] == "target_components"
    ]
    check(
        "S4_membership_preserved",
        imported_members == tables["target_components"],
        len(imported_members),
    )
    coverage = json.loads((build0 / "coverage.json").read_text())
    prior = json.loads(
        (
            root
            / "research/se_target_component_identity_certificate_v1/results/blocked_86_audit.json"
        ).read_text()
    )
    old = {r["id"]: r for r in prior}
    check(
        "S5_prior_conflicts",
        sum(r["evidence_coverage"] == "CONFLICTING" for r in coverage) == 35
        and all(
            r["prior_diagnostic_status"] == old[r["id"]]["diagnostic_status"]
            and not r["certificate_issued"]
            and (
                r["evidence_coverage"] == "CONFLICTING"
                if old[r["id"]]["diagnostic_status"] == "CONFLICT"
                else True
            )
            for r in coverage
        ),
    )
    check(
        "S6_86_coverage",
        {r["id"] for r in coverage} == set(old) and len(coverage) == 86,
        dict(Counter(r["evidence_coverage"] for r in coverage)),
    )
    check(
        "S7_determinism",
        (build0 / "hashes.json").read_bytes() == (build42 / "hashes.json").read_bytes(),
    )
    protected = json.loads(
        (
            root / "research/se_authority_assertion_provenance_sidecar_v1/input_hashes.json"
        ).read_text()
    )
    check("S9_snapshot_protection", all(sha(root / p) == v for p, v in protected.items()))
    adopted = json.loads(
        (
            root
            / "research/se_authority_assertion_provenance_sidecar_v1/results/artifact_manifest.json"
        ).read_text()
    )
    side = Path("/home/djmann/se_runs/authority_assertion_provenance_sidecar_v1/seed0")
    check("S9_sidecar_protection", all(sha(side / p) == v for p, v in adopted.items()))
    return {
        "checks": checks,
        "failures": failures,
        "pass": not failures,
        "implementation_scope": "offline evidence only; no certificates or production imports",
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for flag in ["raw", "build0", "build42", "root", "output"]:
        p.add_argument("--" + flag, type=Path, required=True)
    a = p.parse_args()
    result = run(a.raw, a.build0, a.build42, a.root)
    a.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"pass": result["pass"], "failures": result["failures"]}))
