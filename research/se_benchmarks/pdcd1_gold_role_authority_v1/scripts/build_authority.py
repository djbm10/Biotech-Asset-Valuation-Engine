"""Build the drug->target authority snapshot for M8 gold-entry role adjudication.

External to the S&E pipeline by construction: Open Targets 26.06 drug/mechanism data is
the primary authority, ChEMBL 37 mechanisms corroborate. Nothing here consults the
pipeline's vocabulary, its target resolver, or any run output. See evidence amendment A1
in GOLD_ENTRY_ROLE_RULES.md (sha256 1cbff8b9...).
"""
import csv, glob, hashlib, json, pathlib, re, unicodedata
import pandas as pd

ROOT = pathlib.Path("/home/djmann/staging/pdcd1_gold_role_authority_v1")
SRC = ROOT / "sources/open_targets_26.06"
GOLD = pathlib.Path("/home/djmann/staging/pdcd1_baseline/pdcd1_reference_universe_m8v2.csv")

PDCD1_ENSG = "ENSG00000188389"
CD274_ENSG = "ENSG00000120217"

moa = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(str(SRC / "drug_mechanism_of_action/*.parquet")))])
mol = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(str(SRC / "drug_molecule/*.parquet")))])

# Exact, identifier-based matching. Normalisation covers only case, punctuation,
# trademark symbols and whitespace; there is no fuzzy or edit-distance matching.
_COMPONENT_LABEL = re.compile(r"\bcomponent of\b|\bin combination with\b", re.I)


def norm(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = s.replace("\u2122", " ").replace("\u00ae", " ")
    return re.sub(r"[^a-z0-9]+", " ", s.casefold()).strip()

# name -> chembl id, over canonical name plus ChEMBL-sourced synonyms and trade names.
# Open Targets labels carry a `source`; AACT-sourced labels are deliberately excluded.
# They are free text scraped from trial registrations -- the same substrate the pipeline
# reads -- and include non-specific class terms ("immunotherapy", "anti-pd-1", "cpi")
# that would collide any checkpoint inhibitor onto any other. Only ChEMBL-curated names
# are treated as drug identity evidence here.
name2id = {}
name_source = {}


def labels(cell):
    if cell is None:
        return []
    # "Pembrolizumab component of mk-1308a" is evidence about pembrolizumab, not about
    # the coformulation. Admitting it would inherit a component's target onto the
    # formulation, which the frozen rules do not permit.
    return [
        e["label"]
        for e in cell
        if e.get("source") == "ChEMBL"
        and e.get("label")
        and not _COMPONENT_LABEL.search(e["label"])
    ]


for r in mol.itertuples():
    for value in [r.name, *labels(r.synonyms), *labels(r.tradeNames)]:
        key = norm(value)
        if len(key) < 4:
            continue
        name2id.setdefault(key, set()).add(r.id)
        name_source.setdefault((key, r.id), value)

id2moa = {}
for r in moa.itertuples():
    for cid in (list(r.chemblIds) if r.chemblIds is not None else []):
        id2moa.setdefault(cid, []).append({
            "actionType": r.actionType,
            "mechanismOfAction": r.mechanismOfAction,
            "targetName": r.targetName,
            "targets": list(r.targets) if r.targets is not None else [],
        })

def record_hash(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]

rows = []
for g in csv.DictReader(open(GOLD)):
    names = [g["canonical_asset"]] + [a for a in (g["aliases"] or "").split("|") if a.strip()]
    # Parenthesised development codes in the gold string are additional lookup keys.
    for extra in re.findall(r"\(([^)]*)\)", g["canonical_asset"]):
        names.extend(re.split(r"[/,]", extra))
    names = [n.strip() for n in names if n.strip()]

    hits = {}
    for n in names:
        for cid in name2id.get(norm(n), ()):
            hits.setdefault(cid, (n, name_source[(norm(n), cid)]))

    bindings = []
    for cid, (gold_alias, authority_label) in hits.items():
        for m in id2moa.get(cid, []):
            for ensg in m["targets"]:
                bindings.append({
                    "gold_entry": g["canonical_asset"],
                    "source_drug_id": cid,
                    "source_drug_name": authority_label,
                    "matched_gold_alias": gold_alias,
                    "target_id": ensg,
                    "target_symbol": ("PDCD1" if ensg == PDCD1_ENSG
                                      else "CD274" if ensg == CD274_ENSG else None),
                    "mechanism": m["mechanismOfAction"],
                    "action_type": m["actionType"],
                    "source": "open_targets",
                    "source_release": "26.06",
                    "source_record_hash": record_hash(m),
                })
    rows.append({
        "gold_entry": g["canonical_asset"],
        "benchmark_id": g["benchmark_id"],
        "matched_chembl_ids": sorted(hits),
        "bindings": bindings,
        "resolved": bool(hits),
        "has_moa": bool(bindings),
    })

with open(ROOT / "drug_target_bindings.jsonl", "w") as fh:
    for r in rows:
        fh.write(json.dumps(r) + "\n")

files = {}
for p in sorted(SRC.rglob("*.parquet")):
    files[str(p.relative_to(ROOT))] = {
        "bytes": p.stat().st_size,
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        "url": "https://ftp.ebi.ac.uk/pub/databases/opentargets/platform/26.06/output/"
               + str(p.relative_to(SRC)),
    }
json.dump({
    "artifact": "pdcd1_gold_role_authority_v1",
    "purpose": "external drug->target authority for M8 gold-entry role adjudication",
    "rules_sha256": "1cbff8b9c9bd8b19fd0aa571d1e95b7fee5e705d343beb44f34c96224977025e",
    "primary_authority": {"source": "open_targets", "release": "26.06"},
    "corroborating_authority": {"source": "chembl", "release": "37", "status": "pending"},
    "pdcd1_ensembl_id": PDCD1_ENSG,
    "cd274_ensembl_id": CD274_ENSG,
    "gold_csv_sha256": hashlib.sha256(GOLD.read_bytes()).hexdigest(),
    "files": files,
}, open(ROOT / "manifest.json", "w"), indent=2)

res = sum(r["resolved"] for r in rows)
withmoa = sum(r["has_moa"] for r in rows)
pd1 = sum(any(b["target_id"] == PDCD1_ENSG for b in r["bindings"]) for r in rows)
pdl1 = sum(any(b["target_id"] == CD274_ENSG for b in r["bindings"]) for r in rows)
print(f"gold entries              {len(rows)}")
print(f"resolved to a molecule    {res}")
print(f"with mechanism-of-action  {withmoa}")
print(f"  -> binds PDCD1          {pd1}")
print(f"  -> binds CD274 (PD-L1)  {pdl1}")
print(f"unresolved                {len(rows)-res}")
