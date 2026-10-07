"""Freeze the generic-descriptor population (GENERIC_DESCRIPTOR_SPLIT_DIAGNOSIS v1).

An asset is a generic descriptor when every token of every one of its own names is either a
modality/format word or an antigen designator. No product code, INN or trade name survives.
"""
import json, re, sys, hashlib
GENERIC = set("""car cart car-t cars t tcr nk cell cells lymphocyte lymphocytes injection infusion
therapy therapies treatment targeted targeting target dual bispecific tandem anti autologous
allogeneic allogenic universal u chimeric antigen receptor receptors engineered redirected
modified expressing product products and or plus with of the for directed specific gene
cord blood umbilical derived ucb in vivo nanobody based cord-blood donor donor-derived
cytotoxic gamma delta γδt γδ αβ natural killer infusions group arm""".split())
ANTIGEN = re.compile(r"^(cd\d{1,3}[a-z]?|bcma|tnfrsf17|\d{1,3}|car-?t?[1-9]\d{0,2})$")
def tokens(name):
    return [t for t in re.split(r"[\s/,+()\-–_.:;\[\]]+", name.casefold()) if t]
def generic(name):
    ts = tokens(name)
    return bool(ts) and any(t in ("car","cart","tcr","nk") or t.startswith("car") or t.startswith("cart") for t in ts) and all(t in GENERIC or ANTIGEN.match(t) for t in ts)
out = []
for bench in ("tac01", "mint5"):
    r = json.load(open(f"{sys.argv[1]}/{bench}_ncitid_v1/result.json"))
    for a in sorted(r["candidates"], key=lambda x: x["asset_id"]):
        names = [a["canonical_name"], *a["aliases"]]
        if all(generic(n) for n in names):
            out.append({"benchmark": bench, "asset_id": a["asset_id"], "canonical_name": a["canonical_name"],
                        "aliases": a["aliases"], "trial_ids": a["trial_ids"]})
p = "research/se_generic_descriptor/population_v1.json"
open(p, "w").write(json.dumps(out, indent=1, sort_keys=True) + "\n")
print(len(out), hashlib.sha256(open(p, "rb").read()).hexdigest())
