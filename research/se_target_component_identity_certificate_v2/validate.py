"""Independent frozen-oracle, provenance and serialization verification."""

import argparse
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


def load(path):
    return json.loads(gzip.open(path).read() if str(path).endswith(".gz") else path.read_bytes())


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def validate(study, first, second):
    population = load(study / "population.json")
    cs = load(first / "certificates.json.gz")
    registry = load(first / "evidence_registry.json.gz")
    inputs = load(study / "inputs.json")
    failures = []

    def check(ok, reason):
        if not ok:
            failures.append(reason)

    check(len(cs) == len(population) == 234, "population count")
    by_id = {c["case_id"]: c for c in cs}
    for case in population:
        check(case["id"] in by_id, "missing case " + case["id"])
        if case["id"] in by_id:
            check(by_id[case["id"]]["status"] == case["expected"], "oracle " + case["id"])
    for path, expected in inputs.items():
        check(hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, "input hash " + path)

    def input_path(name):
        return next(Path(p) for p in inputs if p.endswith("/" + name))

    originals = load(input_path("assertions.json.gz"))
    check(
        all(originals[k] == v for k, v in registry["sidecar_origins"].items()),
        "sidecar exact origins",
    )
    records = {
        r["record_id"]: r for r in map(json.loads, gzip.open(input_path("records.jsonl.gz"), "rt"))
    }
    selected = {a["assertion_id"]: a for r in registry["records"].values() for a in r["assertions"]}
    remaining = set(selected)
    for line in gzip.open(input_path("assertions.jsonl.gz"), "rt"):
        a = json.loads(line)
        if a["assertion_id"] in remaining:
            check(selected[a["assertion_id"]] == a, "field equality " + a["assertion_id"])
            remaining.remove(a["assertion_id"])
    check(not remaining, "invented field assertions")
    for rid, r in registry["records"].items():
        check(rid in records and r["source"] == records[rid]["source"], "record source " + rid)
        for a in r["assertions"]:
            value = records[rid]["raw"]
            for part in a["field_path"]:
                value = value[part]
            check(a["raw_value"] == value, "raw field round trip " + a["assertion_id"])
    for c in cs:
        copy = dict(c)
        cid = copy.pop("certificate_id")
        check(
            hashlib.sha256(canonical(copy).encode()).hexdigest() == cid,
            "certificate ID " + c["case_id"],
        )
        check(all(a in selected for a in c["evidence_assertion_ids"]), "missing evidence reference")
        check(
            all(a in registry["sidecar_origins"] for a in c["source_assertion_ids"]),
            "missing origin reference",
        )
        check(bool(c["raw_components"]), "empty raw component " + c["case_id"])
        check(c["runtime_consumption"] == "NONE", "runtime consumer")
        if c["status"] == "CERTIFIED_SINGLE_ENTITY":
            check(c["scope"] in {"PRIMARY_ASSERTION", "PROTEIN_COMPONENT"}, "wrong single scope")
            if c["scope"] == "PRIMARY_ASSERTION":
                origin = originals[c["matched_assertion_ids"][0]]
                hs = [
                    records[r]["raw"]
                    for r in c["evidence_record_ids"]
                    if records[r]["source"]["source"] == "hgnc"
                    and records[r]["raw"].get("ensembl_gene_id") == origin["record_id"]
                ]
                check(
                    len(hs) == 1
                    and hs[0]["status"] == "Approved"
                    and c["canonical_id"] == "TARGET:" + hs[0]["symbol"],
                    "independent primary convergence " + c["case_id"],
                )
            else:
                rs = [records[r] for r in c["evidence_record_ids"]]
                us = [r["raw"] for r in rs if r["source"]["source"] == "uniprot"]
                hs = [r["raw"] for r in rs if r["source"]["source"] == "hgnc"]
                check(
                    len(us) == len(hs) == 1
                    and c["canonical_id"] == "UNIPROT:" + us[0]["primaryAccession"]
                    and us[0]["entryType"] == "UniProtKB reviewed (Swiss-Prot)"
                    and {
                        x["id"]
                        for x in us[0]["uniProtKBCrossReferences"]
                        if x["database"] == "HGNC"
                    }
                    == {hs[0]["hgnc_id"]},
                    "independent protein convergence " + c["case_id"],
                )
    collisions = load(first / "collisions.json.gz")
    check(collisions["all_source_origin_ids"] == sorted(originals), "collision origin universe")
    norms = defaultdict(list)
    canonical_groups = defaultdict(set)
    for aid, a in originals.items():
        norms[a["normalized_key"]].append(aid)
        for g in a["resolver_components"]:
            canonical_groups[g["canonical_id"]].add(g["component_id"])
    check(
        collisions["normalized_key_origins"]
        == {k: sorted(v) for k, v in norms.items() if len(v) > 1},
        "normalization collisions",
    )
    check(
        collisions["canonical_id_components"]
        == {k: sorted(v) for k, v in canonical_groups.items() if len(v) > 1},
        "canonical collisions",
    )
    for name, expected in load(first / "hashes.json").items():
        check(
            hashlib.sha256((first / name).read_bytes()).hexdigest() == expected,
            "first artifact hash " + name,
        )
        check(
            (first / name).read_bytes() == (second / name).read_bytes(), "independent build " + name
        )
    blocked = Counter(c["status"] for c in cs if c["scope"] == "PROPOSAL")
    check(blocked == {"CONFLICT": 35, "AMBIGUOUS": 51}, "blocked 86")
    result = {
        "passed": not failures,
        "failures": failures,
        "certificates": len(cs),
        "statuses": dict(sorted(Counter(c["status"] for c in cs).items())),
        "blocked_86": dict(blocked),
        "verified_source_fields": len(selected),
        "sidecar_origins": len(registry["sidecar_origins"]),
        "canonical_collision_groups": len(collisions["canonical_id_components"]),
        "normalization_collision_keys": len(collisions["normalized_key_origins"]),
    }
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--study", type=Path, default=Path(__file__).parent)
    p.add_argument("--first", type=Path, required=True)
    p.add_argument("--second", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = validate(args.study, args.first, args.second)
    args.output.write_text(canonical(result) + "\n")
    print(canonical(result))
    raise SystemExit(0 if result["passed"] else 1)
