"""Mechanical first-failure-boundary classification of every non-RELEVANT top-20 row (diagnosis only).

Rules (applied in order, from rows_v1.json; no name-specific logic):
  label DUPLICATE                                   -> H IDENTITY_DUPLICATE
  label NON_ASSET, NCIt non-product concept present -> B QUALIFICATION_MISS (existing v6 veto ranks below the ontology route)
  label NON_ASSET                                   -> A NON_PRODUCT_GENERATION
  label WRONG_TARGET, target gate PASS              -> C TARGET_FALSE_PASS
  label WRONG_TARGET, authority targets exclude it  -> E TARGET_KNOWN_INCOMPATIBLE_NOT_FAILED
  label WRONG_TARGET otherwise                      -> D TARGET_UNKNOWN_FILL
  label UNVERIFIABLE / RELEVANT                     -> not a bad row
"""

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def classify(row, intended):
    lab = row["label"]
    if lab == "DUPLICATE":
        return "H"
    if lab == "NON_ASSET":
        return "B" if row["ncit_non_product"] else "A"
    if lab == "WRONG_TARGET":
        if row["gates"].get("target.expression") == "PASS":
            return "C"
        if row["authority_targets"] and f"TARGET:{intended}" not in row["authority_targets"]:
            return "E"
        return "D"
    return None


def main():
    data = json.loads((HERE / "rows_v1.json").read_text())
    out = {}
    for q, v in data.items():
        rows = []
        for r in v["rows"]:
            rows.append({"pos": r["pos"], "name": r["name"], "label": r["label"], "class": classify(r, v["intended"]),
                         "T": r["gates"].get("target.expression"), "IND": r["gates"].get("strategy.indication"),
                         "modality_match": r["modality"][2], "q": r["qualification_reason"],
                         "drug": r["authority_drug"], "auth": r["authority_targets"], "entity_link": r["entity_link"],
                         "origin": sorted(r["origin"])})
        counts = Counter(x["class"] for x in rows if x["class"])
        refs = Counter(w[0] for w in v["references"].values())
        out[q] = {"class_counts": dict(counts), "reference_location": dict(refs), "references": v["references"], "rows": rows}
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
