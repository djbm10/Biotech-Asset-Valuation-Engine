"""Frozen acceptance evaluator; no networking, target selection or gold-label repair."""

import hashlib
import json
import os
from collections import Counter
from datetime import date
from pathlib import Path
import sys

from bve.se.intent import build_buyer_identity, compile_intent, intent_to_trial_query, parse_query
from bve.se.intent.compiler import IntentNotCompilable
from bve.se.intent.target_mentions import analyze_target_mentions
from bve.se.ontology.records import normalize_lookup_key
from bve.se.ontology.targets import get_resolver

ROOT = Path("/home/djmann/projects/bve-b8")
PACKET = ROOT / "research/se_target_mention_role_representation_v1"
OUT = Path("/tmp/mention_v1_results")
OUT.mkdir(exist_ok=True)
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


rows = json.loads((PACKET / "baseline.json").read_text())
requirements = {r["id"]: r for r in json.loads((PACKET / "required_mentions.json").read_text())}
manifest = json.loads((PACKET / "manifest.json").read_text())
for path, h in manifest["input_sha256"].items():
    assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == h
for path, h in manifest["files"].items():
    assert hashlib.sha256((PACKET / path).read_bytes()).hexdigest() == h
seed = os.environ.get("PYTHONHASHSEED", "unset")
seed_only = "--seed-only" in sys.argv
if seed_only:
    rows = rows[:1392]
failures = []
scores = Counter()
counts = Counter()
details = []
ledger = OUT / f"mentions_seed_{seed}.jsonl"
with ledger.open("w") as stream:
    for i, row in enumerate(rows):
        intent = parse_query(row["query"])
        if not seed_only:
            before = decision(intent)
            if digest(before) != row["decision_sha256"]:
                failures.append({"id": row["id"], "criterion": "R1_baseline"})
        analysis = analyze_target_mentions(intent)
        data = analysis.model_dump(mode="json")
        if i < 1392:
            stream.write(canonical({"id": row["id"], "analysis": data}) + "\n")
        if seed_only:
            continue
        after = decision(intent)
        if after != before:
            failures.append({"id": row["id"], "criterion": "R1_mutation"})
        scores["decisions_checked"] += 1
        if data != analyze_target_mentions(intent).model_dump(mode="json"):
            failures.append({"id": row["id"], "criterion": "R5_repeat"})
        scores["repeat_checked"] += 1
        resolver = get_resolver()
        assert resolver is not None
        by_id = {m.mention_id: m for m in analysis.mentions}
        for m in analysis.mentions:
            valid = m.surface == row["query"][m.start : m.end]
            native = resolver.resolve(m.lookup_text)
            valid = (
                valid and m.status == native.status.value and m.canonical_id == native.canonical_id
            )
            valid = valid and m.claimant_ids == list(resolver.claimants_of(m.lookup_text))
            for ev in m.authority_evidence:
                entity = resolver.get(ev.entity_id)
                valid = valid and entity is not None
                source = {r.record_key: r for r in entity.source_records}
                valid = valid and ev.source_record_keys == sorted(source)
                valid = valid and ev.identifier_edges == sorted(entity.identifier_edges)
                for alias in ev.matching_aliases:
                    record = source[alias.record_key]
                    possibilities = {(a.value, a.alias_type.value) for a in record.aliases}
                    possibilities.add((record.canonical_symbol, "SYMBOL"))
                    possibilities.add((record.label, "APPROVED_NAME"))
                    valid = valid and (alias.value, alias.alias_type) in possibilities
                    valid = valid and normalize_lookup_key(alias.value) == normalize_lookup_key(
                        m.lookup_text
                    )
                valid = valid and (bool(ev.matching_aliases) or ev.basis == "CANONICAL_ID")
            if not valid:
                failures.append(
                    {"id": row["id"], "mention": m.mention_id, "criterion": "R3_R7_provenance"}
                )
            scores["mentions_checked"] += 1
            selected = [
                s
                for s in analysis.production_observations
                if s.kind == "TARGET"
                and (s.start, s.end) == (m.start, m.end)
                and s.entity_id == m.canonical_id
                and m.canonical_id is not None
            ]
            if m.currently_decision_bearing != bool(selected):
                failures.append(
                    {"id": row["id"], "mention": m.mention_id, "criterion": "R4_bearing"}
                )
            if any(
                p not in by_id
                or not (
                    by_id[p].start <= m.start
                    and m.end <= by_id[p].end
                    and (by_id[p].start, by_id[p].end) != (m.start, m.end)
                )
                for p in m.containing_mentions
            ):
                failures.append({"id": row["id"], "criterion": "R2_containment"})
        if row["id"] in requirements:
            req = requirements[row["id"]]
            for span in req["required_spans"]:
                matches = [
                    m
                    for m in analysis.mentions
                    if (m.start, m.end) == (span["start"], span["end"])
                    and normalize_lookup_key(m.lookup_text)
                    == normalize_lookup_key(span["lookup_text"])
                ]
                if not any(
                    m.status == span["status"]
                    and m.canonical_id == span["entity_id"]
                    and m.claimant_ids == span["claimants"]
                    for m in matches
                ):
                    failures.append({"id": row["id"], "criterion": "R2_required", "span": span})
                scores["required_spans_checked"] += 1
            n = len(analysis.mentions)
            counts["queries"] += 1
            counts["mentions"] += n
            counts["zero_mentions"] += n == 0
            counts["one_mention"] += n == 1
            counts["multiple_mentions"] += n > 1
            counts["overlapping_mentions_queries"] += any(
                r.kind != "INDEPENDENT" for r in analysis.relations
            )
            counts["crossing_overlap_queries"] += any(
                r.kind == "OVERLAPPING" for r in analysis.relations
            )
            for role, label in [
                ("AMBIGUOUS_ROLE", "ambiguous_roles"),
                ("TARGET_ROLE_CONFIRMED", "confirmed_target_roles"),
                ("EMBEDDED_BIOLOGICAL_MENTION", "embedded_mentions"),
            ]:
                number = sum(m.role.value == role for m in analysis.mentions)
                counts[label] += number
                counts[label + "_queries"] += number > 0
            number = sum(bool(m.identity_conflicts) for m in analysis.mentions)
            counts["authority_conflicts"] += number
            counts["authority_conflict_queries"] += number > 0
            if req["known_English_mismatch"] or req["protected_Greek"]:
                details.append(
                    {
                        "id": row["id"],
                        "witness_id": req["witness_id"],
                        "query": row["query"],
                        "English_mismatch": req["known_English_mismatch"],
                        "protected_Greek": req["protected_Greek"],
                        "mentions": [
                            {
                                "surface": m.surface,
                                "identity": m.canonical_id,
                                "role": m.role.value,
                                "containers": m.containing_mentions,
                                "production_bindings": m.decision_bindings,
                                "decision_bearing": m.currently_decision_bearing,
                            }
                            for m in analysis.mentions
                        ],
                    }
                )
result = {
    "seed": seed,
    "seed_only": seed_only,
    "rows": len(rows),
    "ledger_sha256": hashlib.sha256(ledger.read_bytes()).hexdigest(),
    "checks": dict(scores),
    "diagnostic_counts": dict(counts),
    "failures": failures,
}
(OUT / f"evaluation_seed_{seed}.json").write_text(
    json.dumps(result, indent=2, ensure_ascii=False) + "\n"
)
if not seed_only:
    (OUT / "explainability.json").write_text(
        json.dumps(details, indent=2, ensure_ascii=False) + "\n"
    )
print(json.dumps(result, indent=2, ensure_ascii=False))
