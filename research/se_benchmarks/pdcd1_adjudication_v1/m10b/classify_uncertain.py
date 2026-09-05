"""Classify why each ASSET + target_relevance=UNCERTAIN entry is unresolved.

Descriptive only. This does not assign a target, does not consult any new authority, and
does not touch the frozen V1 adjudication. It partitions existing uncertainty so the size
and shape of the remaining question is visible.
"""
import json, re
from collections import Counter

ev = {json.loads(l)["benchmark_id"]: json.loads(l) for l in open("blinded_evidence.jsonl")}
# Molecule-match state lives in the authority file, not the blinded bundle. Reading it here
# is post-adjudication description, not evidence entering any verdict.
AUTH = "/home/djmann/staging/pdcd1_gold_role_authority_v1/drug_target_bindings.jsonl"
matched = {json.loads(l)["gold_entry"]: (json.loads(l)["matched_chembl_ids"]
                                         + json.loads(l)["chembl_matched_ids"])
           for l in open(AUTH)}
roles = [json.loads(l) for l in open("gold_entry_roles.jsonl")]
d = json.load(open("/home/djmann/staging/pdcd1_baseline/diag/b6_denominator_members.json"))
ident, ext = set(d["member"]["identified_asset"]), set(d["member"]["extracted"])

CELL = re.compile(r"\b(tumou?r[- ]infiltrating lymphocyte|TIL\b|cell therapy|vaccine|"
                  r"oncolytic|mRNA|autologous|CAR[- ]T|autogene)\b", re.I)
BIOSIM = re.compile(r"\bbiosimilar\b", re.I)
COFORM = re.compile(r"coformulat|co-formulat|conjugated to|\bplus\b|\bwith\b.*\badjuvant\b", re.I)
CODE = re.compile(r"\b([A-Z]{2,5}[- ]?\d{2,6}[A-Z]?)\b")
HERBAL = re.compile(r"\b(tang|decoction|hochu|bojungikki|buzhong)\b", re.I)


def why(rec, a):
    entry = rec["gold_entry"]
    if a["agreement"] == "UNCERTAIN_A33":
        return "COFORMULATION_WITHHELD_A33"
    if BIOSIM.search(entry):
        return "BIOSIMILAR_CANDIDATE"
    if COFORM.search(entry):
        return "COFORMULATION_OR_CONJUGATE"
    if CELL.search(entry):
        return "CELL_THERAPY_VACCINE_OR_CONSTRUCT"
    if HERBAL.search(entry):
        return "NON_SMALL_MOLECULE_TRADITIONAL_MEDICINE"
    # The authority knows the molecule but records no mechanism for it, so it cannot say
    # what the drug binds. Distinct from never having resolved the name at all.
    if matched.get(entry):
        return "AUTHORITY_HAS_MOLECULE_BUT_NO_MOA"
    if CODE.search(entry):
        return "DEVELOPMENT_CODE_ABSENT_FROM_AUTHORITY"
    return "NAME_UNRESOLVED_IN_AUTHORITY"


rows = []
for r in roles:
    if r["entity_role"] != "ASSET" or r["target_relevance"] != "UNCERTAIN":
        continue
    rec = ev[r["benchmark_id"]]
    rows.append({**r, "uncertainty_subtype": why(rec, rec["authority"]),
                 "identified": r["benchmark_id"] in ident,
                 "extracted": r["benchmark_id"] in ext})

with open("asset_uncertain_subtypes.jsonl", "w") as fh:
    for r in rows:
        fh.write(json.dumps(r, sort_keys=True) + "\n")

print(f"{'uncertainty subtype':44}{'n':>4}{'ident':>7}{'missed':>8}")
for k, n in Counter(r["uncertainty_subtype"] for r in rows).most_common():
    sub = [r for r in rows if r["uncertainty_subtype"] == k]
    i = sum(r["identified"] for r in sub)
    print(f"{k:44}{n:>4}{i:>7}{n - i:>8}")
print(f"{'TOTAL':44}{len(rows):>4}{sum(r['identified'] for r in rows):>7}"
      f"{len(rows) - sum(r['identified'] for r in rows):>8}")
