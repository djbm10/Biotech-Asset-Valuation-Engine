"""SHORTLIST_NONPRODUCT_OFFTARGET_DIAGNOSIS v1 -- read-only per-row extraction (diagnosis only)."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from bve.se.ontology.ncit_entity_types import ncit_entity_types  # noqa: E402
from bve.se.ontology.targets import get_authority, get_resolver  # noqa: E402
from bve.se.ontology.resolver import EntityType  # noqa: E402
from bve.se.pipeline import SESearchResult  # noqa: E402
from bve.se.reporting.shortlist import build_shortlist  # noqa: E402
import score_heldout_suite_v1 as s1  # noqa: E402
import score_heldout_suite_v3 as s3  # noqa: E402

QUERIES = {"H2": ("v1", "KRAS"), "H4": ("v1", "TNFSF15"), "H11": ("v3", "TIGIT"), "H12": ("v3", "C5"),
           "H13": ("v3", "IL17A"), "H14": ("v3", "CD38")}
LABELS = {**json.loads((ROOT / "research/se_heldout/labels_v1.json").read_text()),
          **json.loads((ROOT / "research/se_heldout/labels_v3.json").read_text())}
REFS = {**s1.REFS, **s3.REFS}
key = s1.key
resolver, authority, ncit_types = get_resolver(), get_authority(), ncit_entity_types()


def drug_targets(names):
    for n in names:
        res = resolver.resolve(n, entity_type=EntityType.DRUG)
        if res.status.value == "RESOLVED":
            return res.canonical_id, list(authority.targets_of(res.canonical_id))
    return None, []


def main() -> None:
    out = {}
    for qid, (ver, intended) in QUERIES.items():
        run = Path.home() / f"se_runs/heldout_{qid.lower()}_{ver}"
        raw = json.loads((run / "result.json").read_text())
        res = SESearchResult.model_validate(raw)
        sl = build_shortlist(res, limit=100_000)
        cands = {a["asset_id"]: a for a in raw["candidates"]}
        gates = {g["subject_id"]: g for g in raw["gate_evaluations"]}
        facts = {}
        for f in raw["facts"]:
            facts.setdefault(f["subject_id"], []).append(f)
        docs = {d["document_id"]: d for d in raw["source_documents"]}
        mentions = {m["mention_id"]: m for m in raw["identity_mentions"]}
        low = set(raw["low_support_asset_ids"]); exc = set(raw["excluded_asset_ids"])
        rows = []
        for pos, e in enumerate(sl.entries[:20], 1):
            a = cands[e.asset_id]; g = gates.get(e.asset_id)
            fs = facts.get(e.asset_id, [])
            pubs = Counter()
            for mid in a.get("mention_ids", []):
                m = mentions.get(mid)
                if m and m["source_document_id"] in docs:
                    d = docs[m["source_document_id"]]; pubs[f'{d["publisher"]}|{d["document_type"]}'] += 1
            drug_id, auth_targets = drug_targets([a["canonical_name"], *a["aliases"]])
            rows.append({
                "pos": pos, "name": e.name, "label": LABELS[qid][e.name],
                "disposition": g["disposition"] if g else None,
                "gates": {d["requirement_id"]: d["status"] for d in g["decisions"]} if g else {},
                "target_gate_rationale": next((d["rationale"] for d in g["decisions"] if d["requirement_id"] == "target.expression"), None) if g else None,
                "target_assertions": [{"t": t["canonical_target_id"], "status": t["status"], "documented": t["documented_targets"],
                                        "sources": sorted({ev.get("source", "?") for ev in t["evidence"]})} for t in a.get("target_assertions", [])],
                "target_facts": [(f["fact_type"], f["value"]) for f in fs if f["fact_type"] in ("construct_target_set", "target_compatibility_evidence")],
                "target_ids": a["target_ids"], "authority_drug": drug_id, "authority_targets": auth_targets,
                "ncit_non_product": ncit_types.non_product_concepts(a["canonical_name"]) if ncit_types else None,
                "qualification_reason": a.get("qualification_reason"), "provisional": a.get("provisional"),
                "entity_link": bool(a["trial_ids"] or a["company_ids"] or a["target_ids"]),
                "n_trials": len(a["trial_ids"]), "n_companies": len(a["company_ids"]),
                "structurally_typed_drug": a.get("structurally_typed_drug"),
                "obs": (a.get("therapeutic_observations"), a.get("comparator_observations"), a.get("unknown_observations")),
                "origin": dict(pubs), "discovery_context": a.get("discovery_target_context"),
                "modality": (a.get("modality_id"), a.get("authority_modality"), a.get("modality_match")),
                "stage": a.get("development_stage"),
                "fact_types": sorted({f["fact_type"] for f in fs}),
            })
        # reference products: where are they?
        allpos = {}
        for i, e in enumerate(sl.entries, 1):
            for n in [cands[e.asset_id]["canonical_name"], *cands[e.asset_id]["aliases"]]:
                allpos.setdefault(key(n), ("shortlist", i, e.name))
        for aid, a in cands.items():
            where = "excluded" if aid in exc else "low_support" if aid in low else None
            if where:
                for n in [a["canonical_name"], *a["aliases"]]:
                    allpos.setdefault(key(n), (where, None, a["canonical_name"]))
        loose = {}
        for aid, a in cands.items():
            for n in [a["canonical_name"], *a["aliases"]]:
                loose.setdefault(key(n), a["canonical_name"])
        refs = {}
        for r in REFS[qid]:
            hit = next((allpos[key(n)] for n in r if key(n) in allpos), None)
            sub = None if hit else next((v for n in r for k, v in loose.items() if key(n) in k), None)
            refs[r[0]] = hit or (("substring_only", None, sub) if sub else ("absent", None, None))
        out[qid] = {"intended": intended, "shortlist": len(sl.entries), "candidates": len(cands),
                    "low_support": len(low), "excluded": len(exc), "eligible": len(raw["eligible_asset_ids"]),
                    "rows": rows, "references": refs}
    print(json.dumps(out, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
