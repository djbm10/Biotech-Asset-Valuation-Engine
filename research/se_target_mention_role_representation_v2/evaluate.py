"""Offline frozen v2 acceptance; independent sidecar stream is provenance oracle."""

import gzip
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from bve.se.intent import build_buyer_identity, compile_intent, intent_to_trial_query, parse_query
from bve.se.intent.compiler import IntentNotCompilable
from bve.se.intent.target_mentions import analyze_target_mentions
from bve.se.ontology.assertion_sidecar_lookup import SidecarLookup
from bve.se.ontology.records import normalize_lookup_key

ROOT = Path("/home/djmann/projects/bve-b8")
OLD = ROOT / "research/se_target_mention_role_representation_v1"
OUT = Path("/home/djmann/se_runs/target_mention_role_representation_v2")
SIDE = Path("/home/djmann/se_runs/authority_assertion_provenance_sidecar_v1/seed0")
SEED = os.environ.get("PYTHONHASHSEED", "unset")
BUYER = build_buyer_identity("representation-neutrality", as_of_date=date(2026, 10, 12))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def decision(intent):
    try:
        problem = compile_intent(intent, buyer=BUYER).model_dump(mode="json")
    except IntentNotCompilable as error:
        problem = {"blockers": error.blockers}
    try:
        trial = intent_to_trial_query(intent, as_of_date=date(2026, 10, 12)).model_dump(mode="json")
    except IntentNotCompilable as error:
        trial = {"blockers": error.blockers}
    return {"intent": intent.model_dump(mode="json"), "problem": problem, "trial_query": trial}


def main():
    seed_only = "--seed-only" in sys.argv
    for name, sha in json.loads(
        (ROOT / "research/se_target_mention_role_representation_v2/inputs.json").read_text()
    ).items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha
    manifest = json.loads((SIDE / "manifest.json").read_text())
    snapshot = json.loads(
        (
            ROOT / "research/se_authority_assertion_provenance_sidecar_v1/input_hashes.json"
        ).read_text()
    )["data/se/ontology/current/records.jsonl"]
    assert (
        hashlib.sha256((ROOT / "data/se/ontology/current/records.jsonl").read_bytes()).hexdigest()
        == snapshot
    )
    rows = json.loads((OLD / "baseline.json").read_text())
    requirements = {r["id"]: r for r in json.loads((OLD / "required_mentions.json").read_text())}
    former = json.loads((OLD / "results/provenance_failure_diagnosis.json").read_text())
    if seed_only:
        rows = rows[:1392]
    failures = []
    counts = Counter()
    observations = {}
    seen = {}
    details = []
    with (
        SidecarLookup(
            OUT / "index.sqlite",
            assertions_sha256=manifest["assertions.jsonl.gz"],
            snapshot_sha256=snapshot,
        ) as lookup,
        (OUT / f"mentions_seed_{SEED}.jsonl").open("w") as ledger,
    ):
        for index, row in enumerate(rows):
            intent = parse_query(row["query"])
            before = decision(intent) if not seed_only else None
            if before is not None and digest(before) != row["decision_sha256"]:
                failures.append([row["id"], "R1_baseline"])
            analysis = analyze_target_mentions(intent, provenance=lookup)
            data = analysis.model_dump(mode="json")
            if index < 1392:
                ledger.write(canonical({"id": row["id"], "analysis": data}) + "\n")
            if seed_only:
                continue
            if before != decision(intent):
                failures.append([row["id"], "R1_mutation"])
            if data != analyze_target_mentions(intent, provenance=lookup).model_dump(mode="json"):
                failures.append([row["id"], "R8_repeat"])
            counts["decisions"] += 1
            positions = {
                (m.start, m.end, normalize_lookup_key(m.lookup_text)): m for m in analysis.mentions
            }
            for m in analysis.mentions:
                key = normalize_lookup_key(m.lookup_text)
                ev = [e.model_dump(mode="json") for e in m.authority_evidence]
                if key in observations and ev != observations[key]:
                    failures.append([row["id"], "R8_key_evidence"])
                observations[key] = ev
                seen[(row["id"], key)] = bool(ev)
                if m.surface != row["query"][m.start : m.end]:
                    failures.append([row["id"], "R2_offsets"])
                if m.currently_decision_bearing and not any(
                    s.kind == "TARGET"
                    and s.start == m.start
                    and s.end == m.end
                    and (s.entity_id or ("TARGET:" + s.resolved_to if s.resolved_to else None))
                    == m.canonical_id
                    for s in analysis.production_observations
                ):
                    failures.append([row["id"], "R6_promotion"])
            for required in requirements.get(row["id"], {}).get("required_spans", []):
                # The frozen contract names its interval/lookup fields explicitly.
                target = positions.get(
                    (
                        required["start"],
                        required["end"],
                        normalize_lookup_key(required["lookup_text"]),
                    )
                )
                if target is None:
                    failures.append([row["id"], "R2_missing_span", required])
                elif (target.status, target.canonical_id, target.claimant_ids) != (
                    required["status"],
                    required["entity_id"],
                    required["claimants"],
                ):
                    failures.append([row["id"], "R2_native_state"])
                counts["required_spans"] += 1
            by_id = {m.mention_id: m for m in analysis.mentions}
            if len(analysis.relations) != len(by_id) * (len(by_id) - 1) // 2:
                failures.append([row["id"], "R7_pair_count"])
            for relation in analysis.relations:
                a, b = by_id[relation.left], by_id[relation.right]
                if (a.start, a.end) == (b.start, b.end):
                    expected = "EQUIVALENT"
                elif a.start <= b.start and b.end <= a.end:
                    expected = "CONTAINS"
                elif b.start <= a.start and a.end <= b.end:
                    expected = "CONTAINED"
                elif max(a.start, b.start) < min(a.end, b.end):
                    expected = "OVERLAPPING"
                else:
                    expected = "INDEPENDENT"
                if relation.kind != expected:
                    failures.append([row["id"], "R7_geometry"])
                if expected == "CONTAINS" and a.mention_id not in b.containing_mentions:
                    failures.append([row["id"], "R7_containment"])
                if expected == "CONTAINED" and b.mention_id not in a.containing_mentions:
                    failures.append([row["id"], "R7_containment"])
            if index < 1344:
                counts["diagnostic_queries"] += 1
                counts["one_mention_queries"] += len(by_id) == 1
                counts["multiple_mention_queries"] += len(by_id) > 1
                counts["overlapping_queries"] += any(
                    r.kind != "INDEPENDENT" for r in analysis.relations
                )
                for m in analysis.mentions:
                    counts[m.role.value] += 1
                    counts["mentions_without_raw_match"] += not m.authority_evidence
                req = requirements[row["id"]]
                if req.get("known_English_mismatch") or req.get("protected_Greek"):
                    details.append({"id": row["id"], "analysis": data})
    if not seed_only:
        expected = defaultdict(lambda: defaultdict(list))
        sha = hashlib.sha256()
        with (SIDE / "assertions.jsonl.gz").open("rb") as stream:
            for chunk in iter(lambda: stream.read(1048576), b""):
                sha.update(chunk)
        assert sha.hexdigest() == manifest["assertions.jsonl.gz"]
        with gzip.open(SIDE / "assertions.jsonl.gz", "rt") as stream:
            for line in stream:
                assertion = json.loads(line)
                key = assertion["normalized_key"]
                if key not in observations:
                    continue
                for component in assertion["resolver_components"]:
                    expected[key][(component["canonical_id"], component["component_id"])].append(
                        assertion
                    )
        for key, observed in observations.items():
            oracle = [
                {
                    "entity_id": entity,
                    "component_id": component,
                    "assertion_ids": sorted({a["assertion_id"] for a in origins}),
                    "source_record_keys": sorted({a["source_record_key"] for a in origins}),
                    "assertion_types": sorted({a["assertion_type"] for a in origins}),
                }
                for (entity, component), origins in sorted(expected[key].items())
            ]
            if observed != oracle:
                failures.append([key, "R3_R5_exact_sidecar"])
        for row in former:
            if not seen.get((row["id"], normalize_lookup_key(row["lookup_text"]))):
                failures.append([row["id"], "R4_former_failure"])
        counts["former_failures_checked"] = len(former)
        counts["explanation_rows"] = len(details)
        if counts["required_spans"] != 1687 or len(details) != 245:
            failures.append(["population", "R2_R9_counts"])
        (OUT / "explainability.json").write_text(canonical(details) + "\n")
    result = {
        "seed": SEED,
        "seed_only": seed_only,
        "rows": len(rows),
        "counts": dict(counts),
        "failures": failures,
        "ledger_sha256": hashlib.sha256(
            (OUT / f"mentions_seed_{SEED}.jsonl").read_bytes()
        ).hexdigest(),
    }
    (OUT / f"evaluation_seed_{SEED}.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
