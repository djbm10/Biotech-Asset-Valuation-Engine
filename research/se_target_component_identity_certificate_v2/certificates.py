"""Offline, scoped identity certificates. Never imported by production parsing."""

import argparse
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

RELATIONAL = frozenset(
    {
        "CHIMERIC PROTEIN",
        "PROTEIN COMPLEX",
        "PROTEIN COMPLEX GROUP",
        "PROTEIN FAMILY",
        "PROTEIN-PROTEIN INTERACTION",
    }
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def read(path):
    return json.loads(gzip.open(path).read() if str(path).endswith(".gz") else path.read_bytes())


def classify(facts):
    scope = facts["scope"]
    if scope == "PROPOSAL":
        if facts.get("primary_conflicts"):
            return "CONFLICT", "P1_INCOMPATIBLE_PRIMARY_GENE_IDS"
        return "AMBIGUOUS", "P2_NO_SCOPED_EQUIVALENCE_FOR_MERGED_ALIAS"
    if scope == "RESOLVER_GROUP":
        return "AMBIGUOUS", "G1_INGESTION_UNION_NOT_AUTHORITY_ENTITY"
    if scope == "PRIMARY_ASSERTION":
        if facts.get("gene_identity_supported"):
            return "CERTIFIED_SINGLE_ENTITY", "A1_EXACT_PRIMARY_GENE_CONVERGENCE"
        return "AMBIGUOUS", "A2_PRIMARY_GENE_PREMISES_INCOMPLETE"
    if scope == "PROTEIN_COMPONENT":
        if facts.get("protein_identity_supported"):
            return "CERTIFIED_SINGLE_ENTITY", "U1_TYPED_PROTEIN_RECIPROCAL_GENE_LINK"
        return "AMBIGUOUS", "U2_PROTEIN_PREMISES_INCOMPLETE"
    if scope == "STRUCTURED_TARGET":
        if not facts.get("target_exists"):
            return "UNRESOLVED", "S0_NO_STRUCTURED_TARGET"
        if facts.get("complete_membership"):
            if facts["target_type"] in RELATIONAL:
                return "CERTIFIED_RELATIONAL_ENTITY", "S1_EXPLICIT_RELATIONAL_TYPE"
            if facts["target_type"] == "SELECTIVITY GROUP":
                return "CERTIFIED_MULTI_ENTITY", "S2_EXPLICIT_MULTI_ENTITY_TYPE"
        return "AMBIGUOUS", "S3_NO_SEPARATE_IDENTITY_EQUIVALENCE"
    return "UNRESOLVED", "NO_APPLICABLE_EVIDENCE_SCOPE"


class Evidence:
    def __init__(self, inputs):
        for filename, expected in inputs.items():
            if hashlib.sha256(Path(filename).read_bytes()).hexdigest() != expected:
                raise ValueError("Frozen input changed: " + filename)

        def path(name):
            return next(Path(p) for p in inputs if p.endswith("/" + name))

        self.groups = {c["component_id"]: c for c in read(path("component_audit.json.gz"))}
        self.origins = read(path("assertions.json.gz"))
        self.records = {
            r["record_id"]: r for r in map(json.loads, gzip.open(path("records.jsonl.gz"), "rt"))
        }
        self.by_source = defaultdict(list)
        self.tables = defaultdict(list)
        for r in self.records.values():
            self.by_source[r["source"]["source"]].append(r)
            if r["source"]["source"] == "chembl":
                self.tables[r["source"]["locator"]["table"]].append(r)
        self.hg = defaultdict(list)
        self.uni = defaultdict(list)
        for r in self.by_source["hgnc"]:
            self.hg[r["raw"].get("ensembl_gene_id")].append(r)
        for r in self.by_source["uniprot"]:
            self.uni[r["raw"].get("primaryAccession")].append(r)
        self.fields = defaultdict(list)
        for line in gzip.open(path("assertions.jsonl.gz"), "rt"):
            a = json.loads(line)
            if relevant(a, self.records[a["record_id"]]):
                self.fields[a["record_id"]].append(a)

    def gene_evidence(self, gene_id):
        found = list(self.hg.get(gene_id, []))
        for h in list(found):
            for acc in h["raw"].get("uniprot_ids", []):
                found.extend(self.uni.get(acc, []))
        return found

    def target_evidence(self, chembl_id):
        ts = [r for r in self.tables["target_dictionary"] if r["raw"]["chembl_id"] == chembl_id]
        rows = list(ts)
        for t in ts:
            ms = [r for r in self.tables["target_components"] if r["raw"]["tid"] == t["raw"]["tid"]]
            rows.extend(ms)
            for m in ms:
                cs = [
                    r
                    for r in self.tables["component_sequences"]
                    if r["raw"]["component_id"] == m["raw"]["component_id"]
                ]
                rows.extend(cs)
                for c in cs:
                    acc = c["raw"]["accession"]
                    rows.extend(self.uni.get(acc, []))
                    rows.extend(
                        h
                        for h in self.by_source["hgnc"]
                        if acc and acc in h["raw"].get("uniprot_ids", [])
                    )
        return rows

    def group_evidence(self, group):
        records = []
        for gene in group["source_genes"]:
            records.extend(self.gene_evidence(gene["entity_id"]))
        for member in group["members"]:
            if member["authority"] == "chembl":
                records.extend(self.target_evidence(member["normalized_record"]["source_id"]))
        return records

    def analyze(self, case):
        facts = {"scope": case["scope"]}
        origins = [self.origins[a] for a in case.get("assertion_ids", [])]
        groups = []
        if "component_id" in case:
            groups = [self.groups[case["component_id"]]]
        else:
            ids = {
                c["component_id"]
                for a in origins
                for c in a["resolver_components"]
                if c["canonical_id"] == case["canonical_id"]
            }
            groups = [self.groups[k] for k in sorted(ids)]
        rows = [r for g in groups for r in self.group_evidence(g)]
        matrix = []
        conflicts = []
        for a in origins:
            for g in groups:
                if a["source_record_key"] not in {m["source_record_key"] for m in g["members"]}:
                    continue
                ids = [v.split(":", 1)[1] for v in g["canonical_gene_candidates"]]
                primary = a["field_path"] in [["approvedName"], ["approvedSymbol"]]
                conflict = primary and bool(ids) and a["record_id"] not in ids
                matrix.append(
                    {
                        "assertion_id": a["assertion_id"],
                        "source_gene_id": a["record_id"],
                        "proposed_gene_ids": ids,
                        "component_id": g["component_id"],
                        "relationship": "INCOMPATIBLE_GENE_ID"
                        if conflict
                        else "PRIMARY_ID_AGREEMENT"
                        if primary and a["record_id"] in ids
                        else "ALIAS_MEMBERSHIP_NOT_EQUIVALENCE",
                    }
                )
                if conflict:
                    conflicts.append(matrix[-1])
        facts["primary_conflicts"] = conflicts
        facts["group_gene_ids"] = {
            g["component_id"]: sorted(x["entity_id"] for x in g["source_genes"]) for g in groups
        }
        if case["scope"] == "PRIMARY_ASSERTION":
            g = groups[0]
            a = origins[0]
            hs = self.hg.get(a["record_id"], [])
            gene = next((x for x in g["source_genes"] if x["entity_id"] == a["record_id"]), None)
            checks = {
                "complete_primary_field": a["field_path"] in [["approvedName"], ["approvedSymbol"]]
                and a["raw_component"] == a["raw_scalar"],
                "single_group_gene": len(g["source_genes"]) == 1,
                "unique_canonical_component": len(g["canonical_id_components"]) == 1,
                "elected_same_gene": g["canonical_gene_candidates"] == [a["source_record_key"]],
                "unique_hgnc": len(hs) == 1,
                "approved_hgnc": len(hs) == 1 and hs[0]["raw"].get("status") == "Approved",
                "exact_gene_identifier_link": bool(
                    gene
                    and len(hs) == 1
                    and hs[0]["raw"].get("ensembl_gene_id") == gene["entity_id"]
                    and hs[0]["raw"].get("symbol") == gene["approvedSymbol"]
                    and case["canonical_id"] == "TARGET:" + hs[0]["raw"]["symbol"]
                ),
            }
            facts["gene_checks"] = checks
            facts["gene_identity_supported"] = all(checks.values())
        if case["scope"] in {"STRUCTURED_TARGET", "PROTEIN_COMPONENT"}:
            rows = self.target_evidence(case["chembl_id"])
            ts = [
                r
                for r in rows
                if r["source"].get("locator", {}).get("table") == "target_dictionary"
            ]
            cs = [
                r
                for r in rows
                if r["source"].get("locator", {}).get("table") == "component_sequences"
            ]
            ms = [
                r
                for r in rows
                if r["source"].get("locator", {}).get("table") == "target_components"
            ]
            facts["target_exists"] = len(ts) == 1
            facts["target_type"] = ts[0]["raw"]["target_type"] if ts else None
            facts["complete_membership"] = bool(ms) and len(ms) == len(cs)
            facts["constituents"] = [
                c["raw"] | {"sequence": "SEE_FROZEN_SOURCE_RECORD"} for c in cs
            ]
            checks = {
                "single_typed_protein": len(ts) == 1
                and facts["target_type"] == "SINGLE PROTEIN"
                and len(ms) == 1
                and len(cs) == 1
                and cs[0]["raw"]["component_type"] == "PROTEIN",
                "human_component": len(cs) == 1 and cs[0]["raw"]["tax_id"] == 9606,
                "human_target": len(ts) == 1 and ts[0]["raw"]["tax_id"] == 9606,
            }
            acc = cs[0]["raw"]["accession"] if len(cs) == 1 else None
            us = self.uni.get(acc, [])
            hs = [
                h for h in self.by_source["hgnc"] if acc and acc in h["raw"].get("uniprot_ids", [])
            ]
            gids = {
                x["id"]
                for u in us
                for x in u["raw"].get("uniProtKBCrossReferences", [])
                if x["database"] == "HGNC"
            }
            checks.update(
                {
                    "same_primary_accession": bool(
                        acc
                        and case["canonical_id"] == "UNIPROT:" + acc
                        and len(us) == 1
                        and us[0]["raw"].get("primaryAccession") == acc
                    ),
                    "reviewed_active": len(us) == 1
                    and us[0]["raw"].get("entryType") == "UniProtKB reviewed (Swiss-Prot)",
                    "human_protein": len(us) == 1
                    and us[0]["raw"].get("organism", {}).get("taxonId") == 9606,
                    "unique_approved_encoding_gene": len(hs) == 1
                    and hs[0]["raw"].get("status") == "Approved",
                    "reciprocal_hgnc": len(hs) == 1 and gids == {hs[0]["raw"]["hgnc_id"]},
                }
            )
            facts["protein_checks"] = checks
            facts["protein_identity_supported"] = all(checks.values())
            matrix.append(
                {
                    "relationship": "ENCODED_BY_NOT_GENE_PROTEIN_EQUIVALENCE",
                    "protein_accession": acc,
                    "uniprot_hgnc_ids": sorted(gids),
                    "hgnc_encoding_ids": sorted(h["raw"]["hgnc_id"] for h in hs),
                }
            )
        # Preserve every source claim even when it does not permit a decision.
        for r in {r["record_id"]: r for r in rows}.values():
            raw = r["raw"]
            source = r["source"]["source"]
            if source == "hgnc":
                matrix.append(
                    {
                        "record_id": r["record_id"],
                        "relationship": "GENE_IDENTIFIER_AND_ENCODING",
                        "hgnc_id": raw.get("hgnc_id"),
                        "ensembl_gene_id": raw.get("ensembl_gene_id"),
                        "symbol": raw.get("symbol"),
                        "protein_accessions": raw.get("uniprot_ids", []),
                        "status": raw.get("status"),
                    }
                )
            elif source == "uniprot":
                matrix.append(
                    {
                        "record_id": r["record_id"],
                        "relationship": "PROTEIN_WITH_GENE_CROSS_REFERENCES",
                        "accession": raw.get("primaryAccession"),
                        "entry_type": raw.get("entryType"),
                        "hgnc_ids": sorted(
                            x["id"]
                            for x in raw.get("uniProtKBCrossReferences", [])
                            if x["database"] == "HGNC"
                        ),
                    }
                )
        status, rule = classify(facts)
        # Group origins retained in addition to explicitly matched proposal fields.
        all_origins = {a["assertion_id"]: a for a in origins}
        for g in groups:
            for m in g["members"]:
                for aid in m["assertion_ids"]:
                    all_origins[aid] = self.origins[aid]
        result = {
            "schema": "target_component_identity_certificate_v2",
            "case_id": case["id"],
            "scope": case["scope"],
            "canonical_id": case["canonical_id"],
            "component_ids": sorted(g["component_id"] for g in groups),
            "matched_assertion_ids": sorted(case.get("assertion_ids", [])),
            "source_assertion_ids": sorted(all_origins),
            "raw_components": [
                {"assertion_id": a["assertion_id"], "text": a["raw_component"]} for a in origins
            ],
            "evidence_record_ids": sorted({r["record_id"] for r in rows}),
            "agreement_conflict_matrix": sorted(matrix, key=canonical),
            "premises": facts,
            "status": status,
            "rule": rule,
            "permits_exact_single_entity_only": status == "CERTIFIED_SINGLE_ENTITY",
            "runtime_consumption": "NONE",
        }
        if case["scope"] == "RESOLVER_GROUP":
            result["raw_components"] = [
                {"assertion_id": a["assertion_id"], "text": a["raw_component"]}
                for a in sorted(all_origins.values(), key=lambda a: a["assertion_id"])
            ]
        elif case["scope"] in {"STRUCTURED_TARGET", "PROTEIN_COMPONENT"}:
            result["raw_components"] = [
                {"record_id": r["record_id"], "field": field, "text": r["raw"][field]}
                for r in rows
                for field in ("pref_name", "description")
                if field in r["raw"]
            ]
        if case["scope"] == "RESOLVER_GROUP":
            result["raw_components"].extend(
                {"record_id": r["record_id"], "field": field, "text": r["raw"][field]}
                for r in rows
                for field in ("pref_name", "description")
                if field in r["raw"]
            )
        return result, all_origins


def relevant(a, record):
    path = a["field_path"]
    if not path:
        return True
    source = record["source"]["source"]
    if source == "chembl":
        return path[0] != "sequence"
    if source == "hgnc":
        return path[0] in {
            "hgnc_id",
            "ensembl_gene_id",
            "symbol",
            "name",
            "status",
            "uniprot_ids",
            "locus_group",
            "locus_type",
            "alias_symbol",
            "alias_name",
            "prev_symbol",
        }
    if source == "uniprot":
        if path[0] == "uniProtKBCrossReferences" and len(path) > 1:
            return record["raw"][path[0]][path[1]]["database"] in {"HGNC", "Ensembl"}
        return path[0] in {
            "primaryAccession",
            "entryType",
            "secondaryAccessions",
            "organism",
            "genes",
            "proteinDescription",
        }
    return False


def build(study, output):
    inputs = read(study / "inputs.json")
    evidence = Evidence(inputs)
    cases = read(study / "population.json")
    certificates = []
    origins = {}
    used = set()
    for case in cases:
        # Remove oracle fields before any certificate logic sees a case.
        clean = {k: v for k, v in case.items() if k not in {"expected", "oracle_reason"}}
        cert, found = evidence.analyze(clean)
        origins.update(found)
        used.update(cert["evidence_record_ids"])
        certificates.append(cert)
    fields = {
        rid: [a for a in evidence.fields[rid] if relevant(a, evidence.records[rid])]
        for rid in sorted(used)
    }
    for cert in certificates:
        cert["evidence_assertion_ids"] = sorted(
            a["assertion_id"] for rid in cert["evidence_record_ids"] for a in fields[rid]
        )
        cert["certificate_id"] = digest(cert)
    canonical_collisions = defaultdict(set)
    normalized = defaultdict(list)
    for aid, a in evidence.origins.items():
        normalized[a["normalized_key"]].append(aid)
        for c in a["resolver_components"]:
            canonical_collisions[c["canonical_id"]].add(c["component_id"])
    collisions = {
        "canonical_id_components": {
            k: sorted(v) for k, v in sorted(canonical_collisions.items()) if len(v) > 1
        },
        "normalized_key_origins": {
            k: sorted(v) for k, v in sorted(normalized.items()) if len(v) > 1
        },
        "all_source_origin_ids": sorted(evidence.origins),
    }
    registry = {
        "records": {
            rid: {
                "record_id": rid,
                "source": evidence.records[rid]["source"],
                "assertions": fields[rid],
            }
            for rid in sorted(used)
        },
        "sidecar_origins": origins,
    }
    summary = {
        "cases": len(certificates),
        "statuses": dict(sorted(Counter(c["status"] for c in certificates).items())),
        "blocked_86": dict(
            sorted(Counter(c["status"] for c in certificates if c["scope"] == "PROPOSAL").items())
        ),
        "evidence_records": len(used),
        "evidence_assertions": sum(map(len, fields.values())),
        "source_origins": len(origins),
        "production_consumer": False,
    }
    output.mkdir(parents=True, exist_ok=False)
    data = {
        "certificates.json.gz": certificates,
        "evidence_registry.json.gz": registry,
        "collisions.json.gz": collisions,
        "summary.json": summary,
    }
    for name, value in data.items():
        raw = (canonical(value) + "\n").encode()
        (output / name).write_bytes(gzip.compress(raw, mtime=0) if name.endswith(".gz") else raw)
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())}
    (output / "hashes.json").write_text(canonical(hashes) + "\n")
    print(canonical(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", type=Path, default=Path(__file__).parent)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.study, args.output)
