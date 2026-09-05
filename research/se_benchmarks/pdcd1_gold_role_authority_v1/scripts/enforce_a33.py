"""Apply amendment A3.3 to the merged bindings: withhold inherited verdicts.

The parenthesised-alias lookup in the build is an exact-match convenience for development
codes, but on a combination string it silently resolves a *component*: "LENVIMA
(lenvatinib) plus KEYTRUDA (pembrolizumab)" matched pembrolizumab and inherited PDCD1 onto
the combination. A3.3 forbids exactly that. The evidence is retained for adjudicators; only
the verdict is withheld.
"""
import json, pathlib
from collections import Counter

ROOT = pathlib.Path("/home/djmann/staging/pdcd1_gold_role_authority_v1")
rows = [json.loads(l) for l in open(ROOT / "drug_target_bindings.jsonl")]

out = []
for r in rows:
    flags = set(r["flags"])
    note = None
    withhold = False

    if "COFORMULATION_OR_COMBINATION_STRING" in flags:
        # No authority record covers the formulation itself; every match came through a
        # component alias.
        withhold = True
        note = "A3.3: verdict withheld -- combination/coformulation string resolved only via a component"
    elif "MULTI_MOLECULE_MATCH" in flags:
        # Several molecule records for one single-agent entry (brand and INN carry separate
        # ChEMBL ids). Unanimity makes the verdict independent of which record is picked.
        per_mol = {}
        for b in r["bindings"] + r["chembl_bindings"]:
            per_mol.setdefault(b["source_drug_id"], set()).add(b["target_symbol"])
        verdicts = {
            "PDCD1_MATCH" if "PDCD1" in s else "NON_PDCD1" for s in per_mol.values() if s
        }
        if len(verdicts) > 1:
            withhold = True
            note = "A3.3: verdict withheld -- matched molecules disagree on target"
        else:
            note = "A3.3: multi-molecule match, unanimous across records; verdict retained"

    if withhold:
        r = {
            **r,
            "open_targets_verdict_withheld": r["open_targets_verdict"],
            "chembl_verdict_withheld": r["chembl_verdict"],
            "open_targets_verdict": None,
            "chembl_verdict": None,
            "agreement": "UNCERTAIN_A33",
        }
    out.append({**r, "a33_note": note})

with open(ROOT / "drug_target_bindings.jsonl", "w") as fh:
    for r in out:
        fh.write(json.dumps(r) + "\n")

print("agreement:", dict(Counter(r["agreement"] for r in out)))
print("PDCD1_MATCH:", sum(1 for r in out if r["open_targets_verdict"] == "PDCD1_MATCH"
                          or r["chembl_verdict"] == "PDCD1_MATCH"))
with open("/tmp/withheld.txt", "w") as fh:
    for r in out:
        if r["agreement"] == "UNCERTAIN_A33":
            fh.write(f"{r['gold_entry']} :: was {r['open_targets_verdict_withheld']}/"
                     f"{r['chembl_verdict_withheld']}\n")
