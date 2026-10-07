"""Enumerate PROTOCOL_ID_TRIAL_ATTRIBUTION v1 candidate moves (frozen before preregistration).

For each (asset, trial): the trial's own sponsor protocol id (orgStudyIdInfo.id) is read; its
leading code token is the prefix. A move is proposed when the prefix's link key equals a
name of exactly one OTHER asset that is (i) not a generic descriptor and (ii) "demonstrated":
one of its own trials registers the code as an intervention name or otherName.
Antigen-shaped/generic prefixes are excluded.
"""
import json, re, sys, hashlib
import importlib.util
_spec = importlib.util.spec_from_file_location("gd", "research/se_generic_descriptor/enumerate_v1.py")
_src = open("research/se_generic_descriptor/enumerate_v1.py").read().split("out = []")[0]
_ns: dict = {}
exec(compile(_src, "gd", "exec"), _ns)  # frozen generic-descriptor vocabulary, without its main
generic = _ns["generic"]

PREFIX = re.compile(r"^([A-Za-z]{2,8}[- ]?\d{2,5}[A-Za-z]?)(?=$|[-_ .])")
#: A product-code-shaped token: letters then 2+ digits (``JWCAR029``, ``MT103``, ``UTAA09``).
CODE_TOKEN = re.compile(r"[a-z]{1,8}-?\d{2,5}[a-z]?", re.I)
ANTIGENISH = re.compile(r"^(cd\d{1,3}[a-z]?|bcma\d*|car-?t?\d{1,3}|cart\d{1,3})$")
key = lambda s: re.sub(r"[^a-z0-9]", "", s.casefold())

def run(runs):
    out, excluded = [], []
    for bench in ("tac01", "mint5"):
        r = json.load(open(f"{runs}/{bench}_ncitid_v1/result.json"))
        snap = {}
        for d in r["source_documents"]:
            m = re.search(r"NCT\d{8}", d.get("source_url") or "")
            if m and d.get("snapshot_path"):
                snap.setdefault(m.group(0), d["snapshot_path"])
        rec = {t: json.load(open(p)) for t, p in snap.items()}
        cands = {a["asset_id"]: a for a in r["candidates"]}
        ncit_linked = {x["asset_id"] for x in r["ncit_target_dispositions"] if x["reason"] != "ambiguous_link"}
        by_key = {}
        for a in cands.values():
            for n in [a["canonical_name"], *a["aliases"]]:
                by_key.setdefault(key(n), set()).add(a["asset_id"])
        def iv_keys(t):
            ivs = rec[t]["armsInterventionsModule"].get("interventions", []) if t in rec else []
            return {key(x) for iv in ivs for x in [iv.get("name") or "", *(iv.get("otherNames") or [])]} | {
                key(tok) for iv in ivs for x in [iv.get("name") or "", *(iv.get("otherNames") or [])] for tok in re.split(r"[,;()]\s*|\s+", x)}
        for a in sorted(cands.values(), key=lambda x: x["asset_id"]):
            for t in a["trial_ids"]:
                if t not in rec:
                    continue
                oid = (rec[t]["identificationModule"].get("orgStudyIdInfo") or {}).get("id") or ""
                m = PREFIX.match(oid.strip())
                if not m:
                    continue
                pk = key(m.group(1))
                owners = by_key.get(pk, set()) - {a["asset_id"]}
                if not owners or a["asset_id"] in by_key.get(pk, set()):
                    continue
                src_names = [a["canonical_name"], *a["aliases"]]
                src_specific = (
                    (a.get("authority_modality_basis") or "").startswith("DRUG:")
                    or any(not ANTIGENISH.match(key(tok)) and CODE_TOKEN.fullmatch(tok)
                           for n in src_names for tok in re.split(r"[\s/,+()\[\]]+", n) if tok)
                )
                row = {"benchmark": bench, "trial_id": t, "protocol_id": oid, "prefix": m.group(1),
                       "from_asset": a["asset_id"], "from_name": a["canonical_name"],
                       "to": sorted(owners), "to_names": sorted(cands[o]["canonical_name"] for o in owners)}
                if src_specific:
                    excluded.append({**row, "excluded": "source_is_product_specific"}); continue
                if ANTIGENISH.match(pk):
                    excluded.append({**row, "excluded": "antigen_or_designator_prefix"}); continue
                if len(owners) != 1:
                    excluded.append({**row, "excluded": "ambiguous_destination"}); continue
                d = cands[next(iter(owners))]
                if t in d["trial_ids"]:
                    excluded.append({**row, "excluded": "destination_already_holds_trial"}); continue
                if all(generic(n) for n in [d["canonical_name"], *d["aliases"]]):
                    excluded.append({**row, "excluded": "destination_generic"}); continue
                if not any(pk in iv_keys(dt) for dt in d["trial_ids"]):
                    excluded.append({**row, "excluded": "prefix_not_demonstrated_as_intervention"}); continue
                out.append(row)
    return out, excluded

if __name__ == "__main__":
    moves, excluded = run(sys.argv[1])
    for name, data in (("population_v1.json", moves), ("excluded_v1.json", excluded)):
        p = f"research/se_protocol_id/{name}"
        open(p, "w").write(json.dumps(data, indent=1, sort_keys=True) + "\n")
        print(name, len(data), hashlib.sha256(open(p, "rb").read()).hexdigest())
