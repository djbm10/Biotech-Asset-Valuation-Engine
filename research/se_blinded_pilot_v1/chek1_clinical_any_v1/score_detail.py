"""Per-reference-asset detail for a scored blinded pilot (reads private artifacts by path).

    python score_detail.py RESULT.json CANDIDATES.json REFERENCE.json OUT.json

Uses the scorer's own matcher (``blinded_pilot._match``). Prints, for every reference asset:
the matching candidates, their engine routes, names, target/modality, and trials found vs
the reference (all ids and NCT-only).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from bve.se.evaluation import blinded_pilot as BP

ROUTES = [("eligible_asset_ids", "ELIGIBLE"), ("unresolved_asset_ids", "REVIEW"),
          ("excluded_asset_ids", "EXCLUDED"), ("low_support_asset_ids", "LOW_SUPPORT")]


def main() -> None:
    result = json.loads(Path(sys.argv[1]).read_text())
    export = BP.CandidateExport.model_validate_json(Path(sys.argv[2]).read_text())
    reference = BP.ReferenceDataset.model_validate_json(Path(sys.argv[3]).read_text())
    route = {i: lab for key, lab in ROUTES for i in result[key]}
    cands = {c["asset_id"]: c for c in result["candidates"]}
    matches = BP._match(export, reference)  # candidate_id -> [reference ids]
    by_ref: dict[str, list[str]] = {}
    for cid, rids in matches.items():
        for rid in rids:
            by_ref.setdefault(rid, []).append(cid)
    rows, nct_hit, nct_den, all_hit, all_den = [], 0, 0, 0, 0
    for ref in reference.assets:
        cids = by_ref.get(ref.reference_id, [])
        found = {t.upper() for cid in cids for t in cands[cid]["trial_ids"]}
        ref_trials = {t.upper() for t in ref.trial_ids}
        ref_nct = {t for t in ref_trials if t.startswith("NCT")}
        if ref.in_scope:
            all_hit += len(ref_trials & found); all_den += len(ref_trials)
            nct_hit += len(ref_nct & found); nct_den += len(ref_nct)
        rows.append({
            "reference_id": ref.reference_id, "in_scope": ref.in_scope, "names": ref.names[:4],
            "candidates": [{"name": cands[c]["canonical_name"], "route": route.get(c),
                            "targets": cands[c]["target_ids"], "modality": cands[c]["modality_id"],
                            "authority_modality": cands[c]["authority_modality"],
                            "trials": len(cands[c]["trial_ids"]),
                            "qualification": cands[c]["qualification_reason"]} for c in cids],
            "ref_trials": len(ref_trials), "ref_nct": len(ref_nct),
            "trials_found": len(ref_trials & found), "nct_found": len(ref_nct & found),
        })
    out = {"trial_coverage_all_ids": all_hit / all_den if all_den else None,
           "trial_coverage_nct_only": nct_hit / nct_den if nct_den else None,
           "trial_counts": {"all": [all_hit, all_den], "nct": [nct_hit, nct_den]}, "assets": rows}
    Path(sys.argv[4]).write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "assets"}))
    for r in rows:
        c = "; ".join(f"{x['name']} [{x['route']}] t={','.join(x['targets']) or '-'} m={x['modality'] or '-'}/{x['authority_modality'] or '-'} trials={x['trials']}"
                      for x in r["candidates"]) or "NOT FOUND"
        print(f"{r['reference_id']} {'IN ' if r['in_scope'] else 'CTL'} {r['names'][0][:22]:22} ref_trials={r['ref_trials']:2} (nct {r['ref_nct']:2}) found={r['trials_found']:2} | {c}")


if __name__ == "__main__":
    main()
