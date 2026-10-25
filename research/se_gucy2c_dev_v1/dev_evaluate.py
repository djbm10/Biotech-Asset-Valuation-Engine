"""DEVELOPMENT evaluation of a replay of the sealed GUCY2C pilot corpus.

Not a pilot score and not validation: the reference is the pilot's AI-prepared answer key,
already disclosed, and the engine changes being measured were designed after reading the
pilot's failures. Uses the pilot scorer's own calculations (``blinded_pilot._compute``) so
the evaluation definitions are identical to the frozen report's.

    python research/se_gucy2c_dev_v1/dev_evaluate.py --label after \
        --result ~/se_runs/gucy2c_dev_v1/after/run/result.json \
        --time ~/se_runs/gucy2c_dev_v1/after/run.time \
        --reference ~/bve_pilot_reference_isolated/reference.json \
        --out research/se_gucy2c_dev_v1/results/after.json
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from bve.se.evaluation import blinded_pilot as BP
from bve.se.pipeline import SESearchResult

CRITERIA = Path(__file__).resolve().parents[1] / (
    "se_blinded_pilot_v1/gucy2c_oncology_v1/criteria.json"
)


def _receipt(label: str, result: SESearchResult) -> BP.SealReceipt:
    return BP.SealReceipt(
        spec_sha256="DEVELOPMENT", criteria_sha256="DEVELOPMENT",
        candidates_sha256=f"DEVELOPMENT:{label}", spec_id="gucy2c_oncology_v1",
        sealed_at=datetime.now(UTC).isoformat(), scorer_commit="DEVELOPMENT",
        prereg_sha256="DEVELOPMENT", prereg_commit="DEVELOPMENT",
        prereg_committed_at=result.run_manifest.started_at, prereg_on_remote=False,
        run_id=result.run_manifest.run_id, run_started_at=result.run_manifest.started_at,
    )


def _score(export: BP.CandidateExport, reference: BP.ReferenceDataset, receipt) -> dict:
    criteria = BP.EvaluationCriteria.model_validate_json(CRITERIA.read_text())
    report = BP._compute(receipt, criteria, export, reference, "DEVELOPMENT",
                         "UNVALIDATED", "DEVELOPMENT replay of a disclosed example")
    body = report.model_dump(mode="json")
    body.pop("receipt")
    # NCT-only view: the scorer's denominator includes EudraCT/JapicCTI/ChiCTR ids that
    # BVE never emits; the NCT-only number isolates what CT.gov retrieval can reach.
    matches = BP._match(export, reference)
    by_id = {c.candidate_id: c for c in export.candidates}
    hit = den = 0
    for ref in reference.assets:
        if not ref.in_scope:
            continue
        ncts = {t.upper() for t in ref.trial_ids if t.upper().startswith("NCT")}
        got = {
            t.upper()
            for cid, rids in matches.items()
            if rids == {ref.reference_id}
            for t in by_id[cid].trial_ids
        }
        den += len(ncts)
        hit += len(ncts & got)
    body["trial_coverage_overall_nct_only"] = hit / den if den else None
    body["reference_nct_trials"] = den
    return body


def _routing(result: SESearchResult, reference: BP.ReferenceDataset) -> dict:
    eligible, unresolved = set(result.eligible_asset_ids), set(result.unresolved_asset_ids)
    excluded, low = set(result.excluded_asset_ids), set(result.low_support_asset_ids)

    def route(asset_id: str) -> str:
        if asset_id in eligible:
            return "ELIGIBLE"
        if asset_id in unresolved:
            return "REVIEW"
        if asset_id in excluded:
            return "EXCLUDED"
        if asset_id in low:
            return "LOW_SUPPORT"
        return "OTHER"

    keys: dict[str, str] = {}
    for ref in reference.assets:
        for name in ref.names:
            keys[BP._norm(name)] = ref.reference_id
    out: dict[str, list] = {}
    for asset in result.candidates:
        names = [asset.canonical_name, *asset.aliases]
        rids = {keys[BP._norm(n)] for n in names if BP._norm(n) in keys}
        for rid in rids:
            out.setdefault(rid, []).append(
                {"name": asset.canonical_name, "route": route(asset.asset_id),
                 "trials": asset.trial_ids, "targets": asset.target_ids,
                 "authority_modality": asset.authority_modality}
            )
    return out


def _facts_of(result: SESearchResult, asset_ids: set[str], fact_types: set[str]) -> list:
    return [
        {"subject": f.subject_id, "type": f.fact_type, "value": f.value}
        for f in result.facts
        if f.subject_id in asset_ids and f.fact_type in fact_types
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--result", type=Path, required=True)
    ap.add_argument("--time", type=Path)
    ap.add_argument("--reference", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    result = SESearchResult.model_validate_json(args.result.read_text())
    reference = BP.ReferenceDataset.model_validate_json(args.reference.read_text())
    receipt = _receipt(args.label, result)
    export_all = BP.export_candidates(result, spec_id="gucy2c_oncology_v1", engine_commit="DEV")
    visible = set(result.eligible_asset_ids) | set(result.unresolved_asset_ids)
    export_visible = export_all.model_copy(
        update={"candidates": [c for c in export_all.candidates if c.candidate_id in visible]}
    )
    routing = _routing(result, reference)
    by_name = {a.canonical_name.casefold(): a.asset_id for a in result.candidates}
    named = {n: by_name.get(n) for n in
             ("plecanatide", "linaclotide", "dolcanatide", "eb-duo-car-nk-cea/gcc")}
    ids = {v for v in named.values() if v}
    gate_by_subject = {g.subject_id: g for g in result.gate_evaluations}
    control_gates = {
        n: [
            (d.requirement_id, d.status.value)
            for d in gate_by_subject[i].decisions
        ] if i in gate_by_subject else None
        for n, i in named.items() if i
    }
    attempts = Counter(a.outcome.value for a in result.search_attempts)
    timing = {}
    if args.time and args.time.exists():
        text = args.time.read_text()
        wall = re.search(r"Elapsed \(wall clock\) time .*?: (\S+)", text)
        rss = re.search(r"Maximum resident set size \(kbytes\): (\d+)", text)
        timing = {"wall_clock": wall.group(1) if wall else None,
                  "peak_rss_mb": int(rss.group(1)) / 1024 if rss else None}
    body = {
        "label": args.label,
        "grade": "DEVELOPMENT — disclosed example, AI reference, not validation",
        "run_id": result.run_manifest.run_id,
        "run_status": result.run_manifest.status.value,
        "counts": {
            "candidates": len(result.candidates),
            "analyst_visible": len(visible),
            "eligible": len(result.eligible_asset_ids),
            "review": len(result.unresolved_asset_ids),
            "excluded": len(result.excluded_asset_ids),
            "low_support": len(result.low_support_asset_ids),
            "identity_merges": len(result.identity_merges),
            "source_documents": len(result.source_documents),
        },
        "search_attempt_outcomes": dict(attempts),
        "score_all_candidates": _score(export_all, reference, receipt),
        "score_analyst_visible": _score(export_visible, reference, receipt),
        "reference_routing": routing,
        "control_gates": control_gates,
        "checked_facts": _facts_of(
            result, ids,
            {"construct_target_set", "target_action_type", "human_poc_present",
             "human_efficacy_outside_requested_area", "therapeutic_area"},
        ),
        "timing": timing,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(body, indent=1, default=str))
    s, v = body["score_all_candidates"], body["score_analyst_visible"]
    print(json.dumps({
        "label": args.label, **body["counts"],
        "recall_all": s["recall"], "recall_visible": v["recall"],
        "precision_strict_visible": v["precision_strict"],
        "control_hits_visible": v["negative_control_hits"],
        "merge": s["merge_errors"], "split": s["split_errors"],
        "trial_cov_all": s["trial_coverage_overall"],
        "trial_cov_all_nct": s["trial_coverage_overall_nct_only"],
        **timing,
    }, indent=1))


if __name__ == "__main__":
    main()
