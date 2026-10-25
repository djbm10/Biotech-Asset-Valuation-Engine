"""Per-trial loss diagnostic for the frozen GUCY2C pilot corpus (development only).

For every ClinicalTrials.gov record the pilot acquired, re-run the CT.gov adapter's own
selection functions (imported, not copied) under each query that actually returned the
record, then join the result to the sealed candidate exports. Reads only sealed bytes.

    python research/se_gucy2c_dev_v1/diagnose_ctgov.py \
        --run ~/se_runs/gucy2c_pilot_v1/run --exports ~/se_runs/gucy2c_pilot_v1 \
        --problem research/se_blinded_pilot_v1/gucy2c_oncology_v1/engine_problem.yaml \
        --out research/se_gucy2c_dev_v1/ctgov_trial_diagnostic.json
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from bve.se.discovery import adapters as A
from bve.se.discovery.query import compile_problem_queries
from bve.se.schemas.contracts import BuyerProblemV2, CompiledQuery


def _queries_by_text(problem: BuyerProblemV2) -> dict[str, CompiledQuery]:
    return {q.query: q for q in compile_problem_queries(problem)}


def _query_for(text: str, known: dict[str, CompiledQuery], target_ids: list[str]) -> CompiledQuery:
    if text in known:
        return known[text]
    # Follow-ups are built by the orchestrator exactly like this (orchestrator.py).
    return CompiledQuery(
        query_id=f"followup:{text}", query=text, target_ids=target_ids, aliases=[text],
        expansion_depth=1,
    )


def _matched_target_terms(vocab: A.QueryVocabulary, text: str) -> list[str]:
    folded = A._fold(text)
    out = []
    for _, terms in vocab.targets:
        for term in terms:
            if term and re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", folded):
                out.append(term)
    return sorted(set(out))


_VOCAB: dict[str, A.QueryVocabulary] = {}


def evaluate(protocol: dict, query: CompiledQuery, as_of: date, serialized: str) -> dict:
    """Mirror ClinicalTrialsGovAdapter.search for one protocol, recording each stage."""
    vocab = _VOCAB.get(query.query)
    if vocab is None:
        vocab = _VOCAB[query.query] = A.QueryVocabulary.for_query(query)
    lower = serialized.casefold()
    stage: dict = {"query": query.query[:80], "depth": query.expansion_depth,
                   "seeded": query.seed_provenance}
    if not A._matches_follow_up(query, serialized):
        return stage | {"lost_at": "FOLLOW_UP_TEXT_ABSENT"}
    protocol_targets = vocab.targets_in(lower)
    stage["protocol_target_terms"] = _matched_target_terms(vocab, serialized)
    if query.target_ids and not set(query.target_ids).issubset(protocol_targets):
        return stage | {"lost_at": "PROTOCOL_TARGET_ABSENT"}
    if not vocab.matches_requested_modality(lower):
        return stage | {"lost_at": "MODALITY_ABSENT"}
    last = (protocol.get("statusModule", {}).get("lastUpdatePostDateStruct") or {}).get("date")
    if last and date.fromisoformat(last[:10]) > as_of:
        return stage | {"lost_at": "AFTER_AS_OF"}
    selected = A._candidate_interventions(protocol, vocab, serialized)
    stage["selected"] = [
        {"name": n, "targets": sorted(t), "modality": m} for n, t, m in selected
    ]
    if not selected:
        stage["fallback_title_used"] = True
        selected = [(protocol["identificationModule"].get("briefTitle", ""), protocol_targets, None)]
    emitted = [n for n, t, _ in selected if not query.target_ids or set(query.target_ids) <= t]
    stage["emitted_hits"] = emitted
    if not emitted:
        return stage | {"lost_at": "INTERVENTION_TARGET_ABSENT"}
    return stage | {"lost_at": None}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--exports", type=Path, required=True)
    ap.add_argument("--problem", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    problem = BuyerProblemV2.model_validate(yaml.safe_load(args.problem.read_text()))
    as_of = problem.buyer.as_of_date
    known = _queries_by_text(problem)
    target_ids = [t.canonical_id for t in problem.strategic_gap.target_expression.targets]

    queries_for: dict[str, list[str]] = {}
    for line in (args.run / "custody" / "query_record_map.jsonl").open():
        row = json.loads(line)
        if row["source"] == "clinicaltrials_gov":
            for rid in row["record_ids"]:
                queries_for.setdefault(rid, []).append(row["query_text"])

    snapshots: dict[str, Path] = {}
    for line in (args.run / "custody" / "acquisition_ledger.jsonl").open():
        row = json.loads(line)
        if row["source"] == "clinicaltrials_gov" and row.get("admitted"):
            snapshots[row["record_id"]] = Path(row["snapshot_path"])

    def by_trial(path: Path) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for cand in json.loads(path.read_text())["candidates"]:
            for tid in cand["trial_ids"]:
                out.setdefault(tid, []).append(cand["names"][0])
        return out

    all_cands = by_trial(args.exports / "candidates.json")
    review_cands = by_trial(args.exports / "candidates_review.json")

    rows = []
    for nct, path in sorted(snapshots.items()):
        try:
            protocol = json.loads(path.read_text())
            parsed = bool(protocol.get("identificationModule", {}).get("nctId"))
        except (OSError, ValueError):
            rows.append({"nct": nct, "parsed": False, "lost_at": "UNPARSEABLE"})
            continue
        interventions = [
            {"name": i.get("name"), "type": i.get("type"), "other_names": i.get("otherNames", [])}
            for i in A._extract_interventions(protocol)
        ]
        serialized = A._protocol_text(protocol)
        stages = [evaluate(protocol, _query_for(q, known, target_ids), as_of, serialized)
                  for q in sorted(set(queries_for.get(nct, [])))]
        depth0 = [s for s in stages if s["depth"] == 0]
        emitted = sorted({h for s in stages for h in s.get("emitted_hits", [])})
        losses = Counter(s["lost_at"] for s in stages)
        if all_cands.get(nct):
            outcome = "CANDIDATE"
        elif emitted:
            outcome = "HIT_EMITTED_NO_CANDIDATE"
        else:
            outcome = "NO_HIT"
        rows.append({
            "nct": nct,
            "parsed": parsed,
            "title": protocol.get("identificationModule", {}).get("briefTitle", ""),
            "interventions": interventions,
            "n_queries": len(stages),
            "returned_by_target_query": any(
                s["seeded"] == "TARGET_VOCABULARY" for s in depth0
            ),
            "returned_by_seeded_query": any(
                s["seeded"] != "TARGET_VOCABULARY" for s in depth0
            ),
            "emitted_under_depth0": sorted({h for s in depth0 for h in s.get("emitted_hits", [])}),
            "depth0_loss": sorted({str(s["lost_at"]) for s in depth0}),
            "loss_counts": dict(losses),
            "protocol_target_terms": sorted({t for s in stages for t in s.get("protocol_target_terms", [])}),
            "selected_names": sorted({x["name"] for s in stages for x in s.get("selected", [])}),
            "emitted_hits": emitted,
            "candidates_all": sorted(set(all_cands.get(nct, []))),
            "candidates_review": sorted(set(review_cands.get(nct, []))),
            "outcome": outcome,
        })
    summary = Counter(r["outcome"] for r in rows)
    args.out.write_text(json.dumps({"summary": dict(summary), "n_records": len(rows), "rows": rows}, indent=1))
    print(json.dumps(dict(summary)))


if __name__ == "__main__":
    main()
