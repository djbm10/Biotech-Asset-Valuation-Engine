"""Trade-name identity diagnosis (prereg e0b3750). Verdict derived by `decide`; diagnosis only."""

import argparse
import copy
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from bve.se.ontology.records import AliasType, EntityType, normalize_lookup_key
from bve.se.ontology.targets import get_resolver, ontology_version
from bve.se.schemas.contracts import IdentityRelationship

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "research/se_trade_name_asset_identity_diagnosis_v1"
RUNS = {
    r: Path.home() / "se_runs" / r / "result.json"
    for r in ("tac01_protoid_v1", "mint5_protoid_v1", "aacr_safety")
}
EXPOSED_H18_H19 = ("Saxenda", "Victoza", "Ozempic", "Wegovy", "Rybelsus", "TRODELVY")
BAD = {"NOT_EQUIVALENT", "AUTHORITY_TOO_COARSE"}


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def via(r, name, cid):
    return {
        t for t, c in r._lookup.get((EntityType.DRUG, normalize_lookup_key(name)), []) if c == cid
    }


def trade_only(r, name):
    res = r.resolve(name, entity_type=EntityType.DRUG)
    if res.status.value != "RESOLVED":
        return None
    v = via(r, name, res.canonical_id)
    if AliasType.TRADE_NAME in v and not v & {AliasType.APPROVED_NAME, AliasType.DEVELOPMENT_CODE}:
        return res.canonical_id
    return None


def doc_text(doc):
    p = Path(doc.get("snapshot_path") or "/nonexistent")
    if not p.is_file():
        return ""
    raw = json.loads(p.read_text())
    if "identificationModule" in raw:
        return json.dumps(raw, ensure_ascii=False)
    return " ".join(str(raw.get(k) or "") for k in ("title", "abstract", "text"))


def measure(r):
    pairs = {}
    for run, path in RUNS.items():
        d = json.loads(path.read_text())
        docs = {x["document_id"]: x for x in d["source_documents"]}
        claims = {c["claim_id"]: c for c in d["claims"]}
        ident = {}
        for c in d["candidates"]:
            for n in [c.get("canonical_name") or "", *(c.get("aliases") or [])]:
                cid = r.resolve_identifier(n) if n else None
                if cid:
                    ident.setdefault(cid, set()).add(c["asset_id"])
        for c in d["candidates"]:
            for n in [c.get("canonical_name") or "", *(c.get("aliases") or [])]:
                cid = trade_only(r, n) if n else None
                if not cid:
                    continue
                key = n.casefold()
                row = pairs.setdefault(
                    key,
                    {
                        "name": key,
                        "canonical_id": cid,
                        "runs": set(),
                        "claimants": None,
                        "alias_provenance": None,
                        "corroborating_documents": set(),
                        "would_merge_partners": 0,
                    },
                )
                row["runs"].add(run)
                ent = r.get(cid, EntityType.DRUG)
                row["claimants"] = len(r.claimants_of(n, EntityType.DRUG))
                row["alias_provenance"] = sorted(
                    {
                        (a.alias_type.value, tuple(a.sources), tuple(a.record_keys))
                        for a in ent.aliases
                        if a.value.casefold() == key
                    }
                )
                approved = [a.value for a in ent.aliases if a.alias_type == AliasType.APPROVED_NAME]
                rx = [
                    re.compile(r"(?<![0-9a-z])" + re.escape(a.casefold()) + r"(?![0-9a-z])")
                    for a in approved
                ]
                doc_ids = {
                    claims[i]["source_document_id"]
                    for i in c.get("supporting_claim_ids") or []
                    if i in claims
                }
                for did in sorted(doc_ids):
                    text = doc_text(docs.get(did, {})).casefold()
                    if any(x.search(text) for x in rx):
                        row["corroborating_documents"].add(did)
                row["would_merge_partners"] = max(
                    row["would_merge_partners"], len(ident.get(cid, set()) - {c["asset_id"]})
                )
    for row in pairs.values():
        row["runs"] = sorted(row["runs"])
        row["corroborating_documents"] = sorted(row["corroborating_documents"])[:5]
        row["corroborated"] = bool(row["corroborating_documents"])
    return dict(sorted(pairs.items()))


def certify(row, contract):
    ok = row["claimants"] == 1
    if contract == "T1":
        ok = ok and row["corroborated"]
    return ok


def decide(pairs, labels, exposed, relationship_values):
    product_relation = any(
        v in relationship_values for v in ("SAME_MOLECULE_DISTINCT_PRODUCT", "BIOSIMILAR_OF")
    )
    results = {}
    for contract in ("T0", "T1"):
        indep = {k: v for k, v in pairs.items() if k not in exposed}
        cert = {k for k, v in indep.items() if certify(v, contract)}
        false = sorted(k for k in cert if labels[k]["class"] in BAD)
        bios = sorted(
            k for k in cert if labels[k]["class"] == "BIOSIMILAR_SAME_MOLECULE_DISTINCT_PRODUCT"
        )
        eq = [
            k
            for k, v in labels.items()
            if v["class"] == "EQUIVALENT_SINGLE_MOLECULE_BRAND" and k not in exposed
        ]
        cov = sum(k in cert for k in eq) / len(eq)
        prov = all(
            pairs[k]["alias_provenance"]
            and (contract == "T0" or pairs[k]["corroborating_documents"])
            for k in cert
        )
        gates = {
            "S1_safety": not false,
            "S2_product_distinction": not bios or product_relation,
            "S3_coverage": cov >= 0.8,
            "S4_provenance": prov,
        }
        failing = [g for g, ok in gates.items() if not ok]
        results[contract] = {
            "gates": gates,
            "first_failing": failing[0] if failing else None,
            "false_certified": false,
            "biosimilar_certified": bios,
            "coverage": cov,
            "certified": len(cert),
            "equivalent_independent": len(eq),
        }
    passing = [c for c, v in results.items() if v["first_failing"] is None]
    return {
        "contracts": results,
        "verdict": "JUSTIFIED" if passing else "STOP",
        "passing_contracts": passing,
    }


def selftest(pairs, labels, exposed, rel):
    good = copy.deepcopy(pairs)
    for k, v in good.items():
        cls = labels[k]["class"]
        v["claimants"] = 1 if cls == "EQUIVALENT_SINGLE_MOLECULE_BRAND" else 2
        v["corroborated"] = cls == "EQUIVALENT_SINGLE_MOLECULE_BRAND"
        v["corroborating_documents"] = ["d"] if v["corroborated"] else []
        v["alias_provenance"] = v["alias_provenance"] or [["TRADE_NAME", ["x"], ["x"]]]
    out = {"valid": decide(good, labels, exposed, rel)["verdict"]}
    word = copy.deepcopy(good)
    word["frontline"].update(claimants=1, corroborated=True, corroborating_documents=["d"])
    out["ordinary_word_certified"] = decide(word, labels, exposed, rel)["contracts"]["T1"][
        "first_failing"
    ]
    bios = copy.deepcopy(good)
    bios["herwenda"].update(claimants=1, corroborated=True, corroborating_documents=["d"])
    out["biosimilar_without_product_relation"] = decide(bios, labels, exposed, rel)["contracts"][
        "T1"
    ]["first_failing"]
    out["biosimilar_with_product_relation"] = decide(
        bios, labels, exposed, rel + ["SAME_MOLECULE_DISTINCT_PRODUCT"]
    )["contracts"]["T1"]["first_failing"]
    low = copy.deepcopy(good)
    for v in low.values():
        v["corroborated"] = False
    out["coverage_loss"] = decide(low, labels, exposed, rel)["contracts"]["T1"]["first_failing"]
    noprov = copy.deepcopy(good)
    noprov["kymriah"]["corroborating_documents"] = []
    out["missing_provenance"] = decide(noprov, labels, exposed, rel)["contracts"]["T1"][
        "first_failing"
    ]
    assert out == {
        "valid": "JUSTIFIED",
        "ordinary_word_certified": "S1_safety",
        "biosimilar_without_product_relation": "S2_product_distinction",
        "biosimilar_with_product_relation": None,
        "coverage_loss": "S3_coverage",
        "missing_provenance": "S4_provenance",
    }, out
    return out


def build(out):
    for line in (STUDY / "freeze_hashes.txt").read_text().splitlines():
        sha, path = line.split(maxsplit=1)
        assert digest(path) == sha, path
    r = get_resolver()
    labels_doc = json.loads((STUDY / "labels.json").read_text())
    labels, exposed = labels_doc["labels"], set(labels_doc["exposed"])
    pairs = measure(r)
    assert set(pairs) == set(labels), sorted(set(pairs) ^ set(labels))
    rel = [v.value for v in IdentityRelationship]
    decision = decide(pairs, labels, exposed, rel)
    exposed_trace = []
    for n in EXPOSED_H18_H19:
        res = r.resolve(n, entity_type=EntityType.DRUG)
        exposed_trace.append(
            {
                "name": n,
                "status": res.status.value,
                "canonical_id": res.canonical_id,
                "alias_types": sorted(t.value for t in via(r, n, res.canonical_id)),
                "claimants": len(r.claimants_of(n, EntityType.DRUG)),
                "resolve_identifier": r.resolve_identifier(n),
            }
        )
    by_class = Counter(labels[k]["class"] for k in pairs if k not in exposed)
    cross = {
        c: dict(
            Counter(
                (labels[k]["class"], certify(v, c)) for k, v in pairs.items() if k not in exposed
            )
        )
        for c in ("T0", "T1")
    }
    summary = {
        **decision,
        "selftest": selftest(pairs, labels, exposed, rel),
        "ontology_version": ontology_version(),
        "independent_pairs": len(pairs) - len(exposed & set(pairs)),
        "classes": dict(sorted(by_class.items())),
        "certification_by_class": {
            c: {f"{a}|{b}": n for (a, b), n in sorted(v.items())} for c, v in cross.items()
        },
        "would_merge_pairs_dev": sorted(
            [k, v["canonical_id"], v["would_merge_partners"]]
            for k, v in pairs.items()
            if v["would_merge_partners"]
        ),
        "exposed_trace": exposed_trace,
        "first_boundary": "resolve_identifier excludes TRADE_NAME (_IDENTIFIER_ALIAS_TYPES), so identifies_drug "
        "returns None and consolidate_by_authority never groups the brand record",
        "production_changes": 0,
    }
    out.mkdir(parents=True, exist_ok=False)
    for name, value in {"pairs.json": pairs, "summary.json": summary}.items():
        (out / name).write_text(canonical(value) + "\n")
    (out / "hashes.json").write_text(
        canonical({p.name: digest(p) for p in sorted(out.iterdir())}) + "\n"
    )
    print(
        canonical(
            {
                "verdict": summary["verdict"],
                "passing": summary["passing_contracts"],
                **{c: v["first_failing"] for c, v in summary["contracts"].items()},
            }
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    build(p.parse_args().output)
