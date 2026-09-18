"""Add the ChEMBL 37 corroborating layer to the Open Targets bindings.

Two independent authorities are kept side by side rather than merged into one verdict.
Adjudicators read `agreement`; they are not handed a pre-decided answer.

Matching is exact and identifier-based. Normalisation is limited to case, punctuation,
trademark symbols and whitespace collapse. There is no fuzzy or edit-distance matching,
and a development code must appear verbatim as an authority synonym -- sponsor and trial
context are never used to infer identity.
"""
import hashlib, json, pathlib, re, unicodedata
from collections import Counter

ROOT = pathlib.Path("/home/djmann/staging/pdcd1_gold_role_authority_v1")

# A label that names a drug only as an ingredient of a fixed combination is evidence about
# the ingredient, not about the combination product. Matching a coformulation gold entry
# through one of these would inherit the component's target onto the formulation, which
# the frozen rules do not permit.
_COMPONENT_LABEL = re.compile(r"\bcomponent of\b|\bin combination with\b", re.I)


def norm(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = s.replace("™", " ").replace("®", " ")
    return re.sub(r"[^a-z0-9]+", " ", s.casefold()).strip()


mech_by_mol = {}
for line in open(ROOT / "chembl37_mechanisms.jsonl"):
    m = json.loads(line)
    mech_by_mol.setdefault(m["molecule_chembl_id"], []).append(m)

name2id = {}
label_of = {}
for line in open(ROOT / "chembl37_molecule_names.jsonl"):
    r = json.loads(line)
    for value in (r.get("pref_name"), r.get("synonyms")):
        if not value or _COMPONENT_LABEL.search(str(value)):
            continue
        key = norm(value)
        if len(key) >= 4:
            name2id.setdefault(key, set()).add(r["chembl_id"])
            label_of.setdefault((key, r["chembl_id"]), value)


def verdict(symbols, any_binding):
    if "PDCD1" in symbols:
        return "PDCD1_MATCH"
    if any_binding:
        return "NON_PDCD1"
    return None


rows = [json.loads(l) for l in open(ROOT / "drug_target_bindings.jsonl")]
out = []
for r in rows:
    ids = set(r["matched_chembl_ids"])
    resolved_by = "open_targets" if ids else None
    matched_labels = {}
    if not ids:
        # Parenthesised development codes are additional exact lookup keys, nothing more.
        keys = [r["gold_entry"]] + [
            p.strip()
            for grp in re.findall(r"\(([^)]*)\)", r["gold_entry"])
            for p in re.split(r"[/,]", grp)
        ]
        for k in keys:
            for cid in name2id.get(norm(k), ()):
                ids.add(cid)
                matched_labels.setdefault(cid, (k, label_of[(norm(k), cid)]))
        if ids:
            resolved_by = "chembl_only"

    chembl_bindings = []
    for cid in sorted(ids):
        gold_alias, authority_label = matched_labels.get(cid, (None, None))
        for m in mech_by_mol.get(cid, []):
            chembl_bindings.append(
                {
                    "gold_entry": r["gold_entry"],
                    "source_drug_id": cid,
                    "source_drug_name": m["molecule_pref_name"],
                    "matched_gold_alias": gold_alias,
                    "matched_authority_label": authority_label,
                    "target_id": m["target_chembl_id"],
                    "target_symbol": m["gene_symbol"],
                    "uniprot_accession": m["uniprot_accession"],
                    "mechanism": m["mechanism_of_action"],
                    "action_type": m["action_type"],
                    "source": "chembl",
                    "source_release": "37",
                    "source_record_hash": hashlib.sha256(
                        json.dumps(m, sort_keys=True).encode()
                    ).hexdigest()[:16],
                }
            )

    ot_v = verdict(
        {b["target_symbol"] for b in r["bindings"] if b["target_symbol"]},
        bool(r["bindings"]),
    )
    ch_v = verdict(
        {b["target_symbol"] for b in chembl_bindings if b["target_symbol"]},
        bool(chembl_bindings),
    )

    # A gold entry that resolves to several distinct molecules is a multi-agent string.
    # Its per-molecule targets are not a target for the string as a whole.
    multi = len(ids) > 1
    flags = []
    if multi:
        flags.append("MULTI_MOLECULE_MATCH")
    if _COMPONENT_LABEL.search(r["gold_entry"]) or re.search(
        r"coformulat|co-formulat|conjugated to|\bplus\b|\band\b.*\bbiosimilar\b",
        r["gold_entry"],
        re.I,
    ):
        flags.append("COFORMULATION_OR_COMBINATION_STRING")

    if ot_v and ch_v:
        agreement = "AGREE" if ot_v == ch_v else "DISAGREE"
    elif ot_v or ch_v:
        agreement = "SINGLE_SOURCE"
    else:
        agreement = "UNRESOLVED"

    out.append(
        {
            **r,
            "resolved_by": resolved_by,
            "chembl_matched_ids": sorted(ids),
            "chembl_bindings": chembl_bindings,
            "open_targets_verdict": ot_v,
            "chembl_verdict": ch_v,
            "agreement": agreement,
            "flags": flags,
        }
    )

with open(ROOT / "drug_target_bindings.jsonl", "w") as fh:
    for r in out:
        fh.write(json.dumps(r) + "\n")


def cell(o, c):
    return sum(1 for r in out if (r["open_targets_verdict"] or "unresolved") == o
               and (r["chembl_verdict"] or "unresolved") == c)


print(f"{'OT':<12}{'ChEMBL':<12}{'count':>6}  meaning")
for o, c, meaning in [
    ("PDCD1_MATCH", "PDCD1_MATCH", "strong PDCD1 match"),
    ("NON_PDCD1", "NON_PDCD1", "strong non-PDCD1"),
    ("PDCD1_MATCH", "NON_PDCD1", "true conflict -> review"),
    ("NON_PDCD1", "PDCD1_MATCH", "true conflict -> review"),
    ("PDCD1_MATCH", "unresolved", "single-source (OT)"),
    ("NON_PDCD1", "unresolved", "single-source (OT)"),
    ("unresolved", "PDCD1_MATCH", "ChEMBL recovery"),
    ("unresolved", "NON_PDCD1", "ChEMBL recovery"),
    ("unresolved", "unresolved", "role evidence must decide / uncertain"),
]:
    print(f"{o:<12}{c:<12}{cell(o, c):>6}  {meaning}")
print()
print("agreement:", Counter(r["agreement"] for r in out))
print("flags:", Counter(f for r in out for f in r["flags"]))
for r in out:
    if r["agreement"] == "DISAGREE":
        print("  DISAGREE:", r["gold_entry"], r["open_targets_verdict"], r["chembl_verdict"])
for r in out:
    if r["flags"] and (r["open_targets_verdict"] or r["chembl_verdict"]):
        print("  FLAGGED+RESOLVED:", r["gold_entry"], r["flags"],
              r["open_targets_verdict"], r["chembl_verdict"])
