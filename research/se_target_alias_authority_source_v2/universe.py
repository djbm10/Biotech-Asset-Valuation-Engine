"""Candidate universe, policy admission and independent-negative sets (prereg 42b94f7)."""

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from bve.se.intent.parser import _tokenize
from bve.se.ontology.records import EntityType, normalize_lookup_key
from bve.se.ontology.targets import get_resolver

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "research/se_target_alias_authority_source_v2"
COV = ROOT / "research/se_target_query_alias_coverage_v1"
V1 = ROOT / "research/se_target_alias_authority_source_v1"
HGNC = Path.home() / "se_runs/target_component_identity_authority_evidence_v1/raw/hgnc.json"
NCIT_TYPES = ROOT / "data/se/ontology/ncit/ncit_26.08e_entity_types.json"
PROTEIN = "Amino Acid, Peptide, or Protein"
HELDOUT = {"CFD", "DLL3", "ERBB2", "IL1RL2", "IL23A", "KLKB1", "LRRK2", "MSTN", "PCSK9", "TSLP"}
EC = re.compile(r"^EC\s*\d", re.I)
ORDINARY_SHAPE = re.compile(r"^[a-z]+$")
SAMPLE_N = 400


def key(s):
    return normalize_lookup_key(s)


def vals(doc, field):
    v = doc.get(field)
    return [v] if isinstance(v, str) else list(v or [])


def load():
    r = get_resolver()
    hgnc = json.loads(HGNC.read_text())["response"]["docs"]
    by_ens = {d["ensembl_gene_id"]: d for d in hgnc if d.get("ensembl_gene_id")}
    hgnc_claim = defaultdict(set)
    for d in hgnc:
        for f in ("symbol", "name", "alias_symbol", "alias_name", "prev_symbol", "prev_name"):
            for v in vals(d, f):
                hgnc_claim[key(v)].add(d["hgnc_id"])
    ncit = json.loads((COV / "ncit_identifier_records.json").read_text())
    gene_hgnc = {x["code"]: x["P369"] for x in ncit if x["P369"]}
    prot = [x for x in ncit if PROTEIN in x["P106"]]
    for x in prot:
        x["genes"] = sorted({h for g in x["encoded_by"] for h in gene_hgnc.get(g, [])})
    ncit_claim = defaultdict(set)
    by_hgnc, by_up = defaultdict(list), defaultdict(list)
    for x in prot:
        for s in x["P90"]:
            ncit_claim[key(s)].update(x["genes"] or [x["code"]])
        for h in x["genes"]:
            by_hgnc[h].append(x)
        for u in x["P93"]:
            by_up[u].append(x)
    target_keys = defaultdict(set)
    drug_keys = set()
    for (etype, k), hits in r._lookup.items():
        if etype == EntityType.TARGET:
            for _, cid in hits:
                target_keys[cid].add(k)
        elif etype == EntityType.DRUG:
            drug_keys.add(k)
    nonproduct = set(json.loads(NCIT_TYPES.read_text())["non_product_names"])
    return {
        "r": r,
        "by_ens": by_ens,
        "hgnc_claim": hgnc_claim,
        "ncit_claim": ncit_claim,
        "by_hgnc": by_hgnc,
        "by_up": by_up,
        "target_keys": target_keys,
        "drug_keys": drug_keys,
        "nonproduct": nonproduct,
    }


def compact(s):
    return "".join(c for c in s.casefold() if c.isalnum())


def hgnc_for(entity, s):
    for rec in entity.source_records:
        for e in rec.xrefs.get("ensembl", []):
            if e in s["by_ens"]:
                return s["by_ens"][e], set(rec.xrefs.get("uniprot", []))
    return None, set()


def candidates(entity, s):
    hg, ups = hgnc_for(entity, s)
    if hg is None:
        return []
    own = s["target_keys"].get(entity.canonical_id, set())
    out = []
    for f in ("name", "alias_symbol", "alias_name"):
        out += [(v, "B-current", f) for v in vals(hg, f)]
    for f in ("prev_symbol", "prev_name"):
        out += [(v, "B-hist", f) for v in vals(hg, f)]
    concepts = {x["code"]: x for x in s["by_hgnc"].get(hg["hgnc_id"], [])}
    for u in ups:
        concepts.update({x["code"]: x for x in s["by_up"].get(u, [])})
    for c in sorted(concepts.values(), key=lambda x: x["code"]):
        single = c["genes"] == [hg["hgnc_id"]]
        consistent = set(c["P93"]) <= set(hg.get("uniprot_ids") or []) or not c["P93"]
        out += [(v, "A" if single and consistent else "A-unchained", c["code"]) for v in c["P90"]]
    rows, seen = [], set()
    for text, cls, field in out:
        k = key(text)
        if not k or k in own or (k, cls) in seen:
            continue
        seen.add((k, cls))
        rows.append(
            {
                "entity": entity.canonical_id,
                "hgnc_id": hg["hgnc_id"],
                "text": text,
                "key": k,
                "class": cls,
                "field": field,
            }
        )
    return rows


def admit(row, s):
    k = row["key"]
    reasons = []
    if row["class"] == "A-unchained":
        reasons.append("NO_SINGLE_CONSISTENT_CHAIN")
    if set(s["r"].claimants_of(row["text"], EntityType.TARGET)) - {row["entity"]}:
        reasons.append("RUNTIME_TARGET_CLAIMANT")
    if s["hgnc_claim"].get(k, set()) - {row["hgnc_id"]}:
        reasons.append("OTHER_HGNC_CLAIMANT")
    if s["ncit_claim"].get(k, set()) - {row["hgnc_id"]}:
        reasons.append("OTHER_NCIT_PROTEIN_CLAIMANT")
    if EC.match(row["text"].strip()):
        reasons.append("EC_CLASS")
    if len(_tokenize(row["text"])) > 2:
        reasons.append("OVER_TOKEN_CAP")
    if ORDINARY_SHAPE.match(row["text"].strip()):
        reasons.append("ORDINARY_WORD_SHAPE")
    return {
        **row,
        "admitted": not reasons,
        "reasons": reasons,
        "n_drug": k in s["drug_keys"],
        "n_ncit": compact(row["text"]) in s["nonproduct"],
    }


def universe(s):
    rows = []
    for e in s["r"].entities(EntityType.TARGET):
        rows += [admit(c, s) for c in candidates(e, s)]
    rows.sort(key=lambda x: (x["entity"], x["key"], x["class"]))
    return rows


def sample_ids(s):
    v1 = {
        p["authority_record_key"] for p in json.loads((COV / "survey_population.json").read_text())
    }
    v1_ids = set()
    for e in s["r"].entities(EntityType.TARGET):
        if any(f"{rec.source}:{rec.source_id}" in v1 for rec in e.source_records):
            v1_ids.add(e.canonical_id)
    pool = [
        e
        for e in s["r"].entities(EntityType.TARGET)
        if e.canonical_id not in v1_ids
        and e.canonical_id.split(":", 1)[-1] not in HELDOUT
        and hgnc_for(e, s)[0] is not None
    ]
    pool.sort(key=lambda e: hashlib.sha256(e.canonical_id.encode()).hexdigest())
    return [e.canonical_id for e in pool[:SAMPLE_N]], sorted(v1_ids)


if __name__ == "__main__":
    s = load()
    rows = universe(s)
    ids, v1_ids = sample_ids(s)
    (STUDY / "universe.json").write_text(
        json.dumps(rows, ensure_ascii=False, sort_keys=True) + "\n"
    )
    (STUDY / "sample_ids.json").write_text(
        json.dumps({"sample": ids, "v1_excluded": v1_ids}, indent=0) + "\n"
    )
    idset = set(ids)
    packet = sorted(
        {
            (r["text"], r["entity"])
            for r in rows
            if r["entity"] in idset and r["admitted"] and r["class"] in ("A", "B-current", "B-hist")
        }
    )
    (STUDY / "review_packet.json").write_text(
        json.dumps(
            [
                {"id": i, "name": t, "target_symbol": e.split(":", 1)[-1]}
                for i, (t, e) in enumerate(packet)
            ],
            indent=1,
            ensure_ascii=False,
        )
        + "\n"
    )
    print(len(rows), len(ids), len(packet))
