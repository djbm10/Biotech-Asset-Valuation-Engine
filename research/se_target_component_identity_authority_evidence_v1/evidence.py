"""Lossless offline identity evidence. No resolver, certificates or parser consumers."""

import argparse
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def pointer_value(raw, path):
    value = raw
    for key in path:
        value = value[key]
    return value


def leaves(value, path=()):
    if isinstance(value, dict) and value:
        for key in sorted(value):
            yield from leaves(value[key], path + (key,))
    elif isinstance(value, list) and value:
        for index, item in enumerate(value):
            yield from leaves(item, path + (index,))
    else:
        yield list(path), value


def assertions_for(source, raw):
    record_id = digest(source)
    result = []
    for path, value in leaves(raw):
        assertion = {
            "record_id": record_id,
            "source": source,
            "field_path": path,
            "raw_value": value,
            "transformations": [{"operation": "identity"}],
        }
        result.append(dict(assertion, assertion_id=digest(assertion)))
    return result


PK = {
    "target_dictionary": "tid",
    "target_components": "targcomp_id",
    "component_sequences": "component_id",
    "component_synonyms": "compsyn_id",
    "target_relations": "targrel_id",
    "target_type": "target_type",
    "version": "name",
}


def source_records(raw):
    database = json.loads((raw / "chembl_artifact.json").read_text())
    capture = json.loads((raw / "chembl_tables.json").read_text())
    capture_sha = file_hash(raw / "chembl_tables.json")
    for table in sorted(capture["tables"]):
        for i, row in enumerate(capture["tables"][table]):
            source = {
                "source": "chembl",
                "release": "ChEMBL_37",
                "artifact_sha256": database["sha256"],
                "locator": {"table": table, "pk": {PK[table]: row[PK[table]]}},
                "capture_artifact": "chembl_tables.json",
                "capture_sha256": capture_sha,
                "capture_path": ["tables", table, i],
                "entity_key": f"chembl:{table}:{row[PK[table]]}",
            }
            yield source, row
    hgnc = json.loads((raw / "hgnc_selected.json").read_text())
    for r in hgnc["records"]:
        row = r["raw"]
        source = {
            "source": "hgnc",
            "release": "2026-10-13:generation:1791894733877675",
            "artifact_sha256": hgnc["artifact_sha256"],
            "locator": {"json_path": ["response", "docs", r["row_index"]]},
            "capture_artifact": "hgnc.json",
            "capture_sha256": hgnc["artifact_sha256"],
            "capture_path": ["response", "docs", r["row_index"]],
            "entity_key": row["hgnc_id"],
        }
        yield source, row
    receipts = json.loads((raw / "uniprot_receipts.json").read_text())
    for receipt in sorted(receipts, key=lambda r: r["accession"]):
        if receipt.get("http_status") != 200:
            continue
        row = json.loads((raw / receipt["artifact"]).read_text())
        source = {
            "source": "uniprot",
            "release": "2026_03",
            "artifact_sha256": receipt["sha256"],
            "locator": {"requested_accession": receipt["accession"], "json_path": []},
            "capture_artifact": receipt["artifact"],
            "capture_sha256": receipt["sha256"],
            "capture_path": [],
            "entity_key": row.get("primaryAccession", receipt["accession"]),
        }
        yield source, row


class JsonLines:
    def __init__(self, path):
        self.file = path.open("wb")
        self.stream = gzip.GzipFile(filename="", fileobj=self.file, mode="wb", mtime=0)

    def write(self, value):
        self.stream.write((canonical(value) + "\n").encode())

    def close(self):
        self.stream.close()
        self.file.close()


def coverage(raw, root):
    prior = json.loads(
        (
            root
            / "research/se_target_component_identity_certificate_v1/results/blocked_86_audit.json"
        ).read_text()
    )
    groups = json.loads(
        (root / "research/se_target_component_identity_certificate_v1/population.json").read_text()
    )
    by_canonical = {
        g["canonical_id"]: g for g in groups if "nine_implicated_groups" in g["categories"]
    }
    tables = json.loads((raw / "chembl_tables.json").read_text())["tables"]
    targets = {r["chembl_id"]: r for r in tables["target_dictionary"]}
    hgnc = json.loads((raw / "hgnc_selected.json").read_text())["records"]
    proteins = {}
    for receipt in json.loads((raw / "uniprot_receipts.json").read_text()):
        if receipt.get("http_status") == 200:
            proteins[receipt["accession"]] = json.loads((raw / receipt["artifact"]).read_text())
    output = []
    for case in prior:
        group = by_canonical[case["canonical_id"]]
        ids = [k.split(":", 1)[1] for k in group["record_keys"] if k.startswith("chembl:")]
        genes = [k.split(":", 1)[1] for k in group["record_keys"] if k.startswith("open_targets:")]
        records = [targets[i] for i in ids if i in targets]
        types = sorted({r["target_type"] for r in records})
        tids = {r["tid"] for r in records}
        components = sorted(
            {r["component_id"] for r in tables["target_components"] if r["tid"] in tids}
        )
        hg = [r["raw"] for r in hgnc if r["raw"].get("ensembl_gene_id") in genes]
        accessions = sorted(
            {
                r["accession"]
                for r in tables["component_sequences"]
                if r["component_id"] in components and r["accession"]
            }
        )
        unique_path = False
        if len(genes) == len(hg) == len(components) == len(accessions) == 1:
            p = proteins.get(accessions[0], {})
            unique_path = (
                p.get("entryType") == "UniProtKB reviewed (Swiss-Prot)"
                and accessions[0] in hg[0].get("uniprot_ids", [])
                and any(
                    x["database"] == "HGNC" and x["id"] == hg[0]["hgnc_id"]
                    for x in p.get("uniProtKBCrossReferences", [])
                )
            )
        if case["diagnostic_status"] == "CONFLICT":
            status = "CONFLICTING"
        elif set(types) & {
            "CHIMERIC PROTEIN",
            "PROTEIN COMPLEX",
            "PROTEIN-PROTEIN INTERACTION",
            "PROTEIN NUCLEIC-ACID COMPLEX",
        }:
            status = "RELATIONAL"
        elif set(types) & {"PROTEIN FAMILY", "SELECTIVITY GROUP", "PROTEIN COMPLEX GROUP"}:
            status = "MULTI_ENTITY"
        elif unique_path:
            status = "UNIQUELY_SUPPORTED_PATH"
        elif records or hg:
            status = "AMBIGUOUS"
        else:
            status = "NO_EVIDENCE"
        output.append(
            {
                "id": case["id"],
                "canonical_id": case["canonical_id"],
                "prior_diagnostic_status": case["diagnostic_status"],
                "evidence_coverage": status,
                "certificate_issued": False,
                "source_chembl_ids": ids,
                "source_target_types": types,
                "source_component_ids": components,
                "source_ensembl_ids": genes,
                "hgnc_ids": sorted(r["hgnc_id"] for r in hg),
                "uniprot_accessions": accessions,
                "identity_level_note": "Gene, protein, target and relationship claims remain separate; no same-entity certificate.",
            }
        )
    return output


def build(raw, output, root):
    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((raw / "raw_manifest.json").read_text())
    for name, sha in manifest.items():
        assert file_hash(raw / name) == sha, name
    records = JsonLines(output / "records.jsonl.gz")
    assertions = JsonLines(output / "assertions.jsonl.gz")
    n_records = n_assertions = 0
    sources = Counter()
    for source, row in source_records(raw):
        record_id = digest(source)
        records.write(
            {
                "schema": "target_identity_authority_evidence_v1",
                "layer": "NEW_INDEPENDENT_AUTHORITY_EVIDENCE",
                "record_id": record_id,
                "source": source,
                "raw": row,
            }
        )
        n_records += 1
        sources[source["source"]] += 1
        for assertion in assertions_for(source, row):
            assertions.write(assertion)
            n_assertions += 1
    records.close()
    assertions.close()
    rows = coverage(raw, root)
    (output / "coverage.json").write_text(canonical(rows) + "\n")
    summary = {
        "records": n_records,
        "assertions": n_assertions,
        "records_by_source": dict(sources),
        "coverage": dict(Counter(r["evidence_coverage"] for r in rows)),
        "certificates_issued": 0,
        "raw_manifest_sha256": file_hash(raw / "raw_manifest.json"),
    }
    (output / "summary.json").write_text(canonical(summary) + "\n")
    (output / "hashes.json").write_text(
        canonical({p.name: file_hash(p) for p in sorted(output.iterdir())}) + "\n"
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(canonical(build(args.raw, args.output, args.root)))
