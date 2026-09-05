"""Assemble the blinded evidence bundle each adjudicator may see.

Deliberately excluded: b6_identity_cliff.json, b6_attrition_ledger.json,
b6_denominator.json and the run result. Those encode whether the pipeline found or missed
an entry, which is precisely what the adjudicators must not know. The CT.gov field index IS
included -- it is registry evidence, not a pipeline outcome, and it records nothing about
what the pipeline did with any trial.
"""
import csv, hashlib, json, pathlib, re, unicodedata

DIAG = pathlib.Path("/home/djmann/staging/pdcd1_baseline/diag")
AUTH = pathlib.Path("/home/djmann/staging/pdcd1_gold_role_authority_v1")
GOLD = pathlib.Path("/home/djmann/staging/pdcd1_baseline/pdcd1_reference_universe_m8v2.csv")
OUT = pathlib.Path("/home/djmann/staging/pdcd1_adjudication_v1")

fields = json.load(open(DIAG / "b6_field_index.json"))
authority = {json.loads(l)["gold_entry"]: json.loads(l) for l in open(AUTH / "drug_target_bindings.jsonl")}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).replace("™", " ").replace("®", " ")
    return re.sub(r"[^a-z0-9]+", " ", s.casefold()).strip()


def find(term):
    """Where a gold string appears in the frozen corpus. Paired exhibits only:
    every hit records the NCT, the field, and the exact matching text."""
    key = norm(term)
    if len(key) < 4:
        return []
    hits = []
    for nct, rec in fields.items():
        for field in ("interventions", "other_names"):
            for i, value in enumerate(rec.get(field, [])):
                if norm(value) == key:
                    hits.append({
                        "nct": nct, "field": field, "evidence": value,
                        "intervention_type": (rec.get("types") or [None] * (i + 1))[i]
                        if field == "interventions" else None,
                        "title": rec.get("title"),
                    })
        if not any(h["nct"] == nct for h in hits) and key in norm(rec.get("title", "")):
            hits.append({"nct": nct, "field": "title", "evidence": rec.get("title"),
                         "intervention_type": None, "title": rec.get("title")})
    return hits


bundle = []
for g in csv.DictReader(open(GOLD)):
    entry = g["canonical_asset"]
    aliases = [a.strip() for a in (g["aliases"] or "").split("|") if a.strip()]
    exhibits = {}
    for term in [entry] + aliases:
        hits = find(term)
        if hits:
            exhibits[term] = hits[:5]
    a = authority[entry]
    bundle.append({
        "benchmark_id": g["benchmark_id"],
        "reference_tier": g["reference_tier"],
        "gold_entry": entry,
        "aliases": aliases,
        "ctgov_exhibits": exhibits,
        "ctgov_hit_count": sum(len(v) for v in exhibits.values()),
        "authority": {
            "open_targets_verdict": a["open_targets_verdict"],
            "chembl_verdict": a["chembl_verdict"],
            "agreement": a["agreement"],
            "flags": a["flags"],
            "a33_note": a["a33_note"],
            "bindings": [
                {k: b[k] for k in ("source", "source_drug_id", "source_drug_name",
                                   "target_symbol", "mechanism", "action_type")}
                for b in (a["bindings"] + a["chembl_bindings"])
            ][:12],
        },
    })

path = OUT / "blinded_evidence.jsonl"
with open(path, "w") as fh:
    for r in bundle:
        fh.write(json.dumps(r, sort_keys=True) + "\n")
print("entries:", len(bundle))
print("with CT.gov exhibits:", sum(1 for r in bundle if r["ctgov_hit_count"]))
print("sha256:", hashlib.sha256(path.read_bytes()).hexdigest())
