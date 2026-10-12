"""Read-only span/role audit; does not install a parser or choose new production targets."""

import hashlib
import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError

from bve.se.intent.intent import IntentSpan, SpanKind
from bve.se.intent.parser import parse_query
from bve.se.ontology.target_reference import reference_for
from bve.se.ontology.targets import get_resolver, resolve_target

ROOT = Path("/home/djmann/projects/bve-b8")
PACKET = ROOT / "research/se_target_authority_span_query_role_contract_v1"
OUT = Path("/tmp/span_role_results_v1")
OUT.mkdir(exist_ok=True)
trace = json.loads(
    (ROOT / "research/se_target_query_authority_span_boundary_diagnosis_v1/trace.json").read_text()
)
controls = json.loads((PACKET / "structural_controls.json").read_text())["rows"]
resolver = get_resolver()
assert resolver is not None


@lru_cache(maxsize=None)
def authority(text):
    result = resolve_target(text)
    assert result is not None
    return {
        "status": result.status.value,
        "entity_id": result.canonical_id,
        "candidates": [c.canonical_id for c in result.candidates],
        "all_claimants": list(resolver.claimants_of(text)),
        "rule": result.rule,
        "basis": result.basis.model_dump(mode="json") if result.basis else None,
        "source_record_keys": sorted(
            f"{r.source}:{r.source_id}" for r in result.entity.source_records
        )
        if result.entity
        else [],
    }


def selected(intent):
    return [s for s in intent["spans"] if s["kind"] in ("TARGET", "AMBIGUOUS_TARGET")]


def candidates(text, offset=0):
    """Inventory complete whitespace-boundary intervals, never used as target assertions."""
    tokens = list(re.finditer(r"\S+", text))
    spans = []
    for i, first in enumerate(tokens):
        for last in tokens[i:]:
            a, b = first.start(), last.end()
            value = text[a:b]
            resolution = authority(value)
            if (
                resolution["status"] != "UNRESOLVED"
                or resolution["all_claimants"]
                or (a == 0 and b == len(text))
            ):
                spans.append(
                    {
                        "start": offset + a,
                        "end": offset + b,
                        "text": value,
                        "authority": resolution,
                        "role": "CANDIDATE_ONLY",
                        "whole_name": a == 0 and b == len(text),
                    }
                )
    return spans


observations = []
name_summary = []
for source_row in trace["rows"]:
    ref = source_row["reference"]
    expected = ref["query_reference_entity"]
    by_name = []
    for o in source_row["observations"]:
        name = o["name"]
        query = o["query"]
        lo = query.index(name)
        hi = lo + len(name)
        full = authority(name)
        current = selected(o["intent"])
        spans = candidates(name, lo)
        for s in current:
            if not any(s["start"] == c["start"] and s["end"] == c["end"] for c in spans):
                spans.append(
                    {
                        "start": s["start"],
                        "end": s["end"],
                        "text": s["text"],
                        "authority": authority(s["text"]),
                        "role": "CURRENT_SELECTED_ONLY",
                        "whole_name": False,
                    }
                )
        spans.sort(key=lambda s: (s["start"], s["end"], s["text"]))
        for c in spans:
            c["proposed_query_role"] = (
                "TARGET_SLOT" if c["whole_name"] else "NAME_COMPONENT_NOT_INDEPENDENT_TARGET"
            )
        whole_selected = any(
            s["kind"] == "TARGET" and s["start"] == lo and s["end"] == hi for s in current
        )
        correct_ids = bool(expected) and o["targets"] == [expected]
        owning = bool(expected) and full["status"] == "RESOLVED" and full["entity_id"] == expected
        role_conflicts = [
            s
            for s in o["intent"]["spans"]
            if s["start"] < hi
            and s["end"] > lo
            and s["kind"] not in ("TARGET", "AMBIGUOUS_TARGET", "RESIDUAL")
        ]
        categories = []
        if expected is None:
            categories.append("C")
        elif owning:
            categories.append("E" if whole_selected and correct_ids else "A")
        else:
            if o["outside_frozen_reference"]:
                categories.append("A")
            categories.append("D" if full["status"] == "UNRESOLVED" else "C")
        if role_conflicts:
            categories.append("B")
        if "A" in categories:
            boundary = (
                "punctuation_changed_before_lookup"
                if o["token_count"] <= 2 and not o["whole_name_offered"]
                else "complete_name_not_owned_before_component_resolution"
            )
        elif categories[0] == "C":
            boundary = "source_identity_uncertified_or_ambiguous"
        elif categories[0] == "D":
            boundary = "exact_alias_not_supported_no_Greek_equivalence_admitted"
        else:
            boundary = "valid_complete_target_span"
        row = {
            "witness_id": ref["id"],
            "spelling": o["spelling"],
            "frame": o["frame"],
            "query": query,
            "name": name,
            "biological_reference": expected,
            "candidate_spans": spans,
            "current_selected_spans": current,
            "expected_target_span": {"start": lo, "end": hi, "text": name, "role": "TARGET_SLOT"},
            "whole_name_authority": full,
            "smaller_embedded_aliases": [
                c for c in spans if not c["whole_name"] and c["authority"]["status"] == "RESOLVED"
            ],
            "current_targets": o["targets"],
            "current_outside_reference": o["outside_frozen_reference"],
            "current_identity_set_correct": correct_ids,
            "current_whole_span_correct": whole_selected and correct_ids,
            "role_conflicts": role_conflicts,
            "categories": categories,
            "first_failure_boundary": boundary,
            "authority_permitted_design_outcome": {
                "state": "TARGET" if owning else "UNKNOWN",
                "targets": [expected] if owning else [],
                "note": "Exact full-name identity plus existing therapeutic-slot context; not a implemented parser result.",
            },
            "preservation_obligation_unmet_by_whole_name_only": correct_ids and not owning,
            "provenance": {
                "trace_input": "research/se_target_query_authority_span_boundary_diagnosis_v1/trace.json",
                "original_alias": ref["original_authority_name"],
            },
        }
        observations.append(row)
        by_name.append(row)
    original = next(
        r for r in by_name if r["spelling"] == "original_authority_name" and r["frame"] == "{}"
    )
    greek = next(r for r in by_name if r["spelling"] == "query_name" and r["frame"] == "{}")
    name_summary.append(
        {
            "id": ref["id"],
            "original_name": original["name"],
            "Greek_name": greek["name"],
            "reference": expected,
            "English_categories": original["categories"],
            "Greek_categories": greek["categories"],
            "English_current": original["current_targets"],
            "Greek_current": greek["current_targets"],
            "English_permitted": original["authority_permitted_design_outcome"],
            "Greek_permitted": greek["authority_permitted_design_outcome"],
            "known_English_mismatch": bool(original["current_outside_reference"]),
        }
    )

structural = []
for c in controls:
    intent = parse_query(c["query"]).model_dump(mode="json")
    selected_spans = selected(intent)
    targets = [t["target_reference"]["entity_id"] for t in intent["targets"]]
    expected = [s["entity_id"] for s in c["expected_target_spans"]]
    primary = (
        "E"
        if targets == expected
        else (
            "B"
            if c["role_category"]
            in {
                "biomarker",
                "assay",
                "mutation",
                "disease",
                "pathway",
                "family",
                "complex",
                "relationship",
                "scientific_phrase",
                "mixed",
            }
            else "A"
        )
    )
    if c["role_category"] == "unsupported_alias":
        primary = "D"
    if c["role_category"] == "ambiguity":
        primary = "C"
    structural.append(
        {
            **c,
            "candidate_spans": candidates(c["query"]),
            "current_selected_spans": selected_spans,
            "current_targets": targets,
            "current_intent": intent,
            "expected_span_authority": [
                {"text": s["text"], "authority": authority(s["text"])}
                for s in c["expected_target_spans"]
            ],
            "primary_category": primary,
            "target_set_matches_label": targets == expected,
            "operator_matches_label": intent["target_operator"] == c["expected_operator"],
        }
    )

proof = []
reference = reference_for(resolve_target("CD19"))
for kind in (SpanKind.TARGET, SpanKind.RESIDUAL, SpanKind.UNRESOLVED_SCIENTIFIC):
    try:
        span = IntentSpan(
            text="CD19",
            start=0,
            end=4,
            kind=kind,
            resolved_to="CD19",
            rule="design_probe",
            target_reference=reference,
        )
        proof.append(
            {
                "kind": kind.value,
                "accepts_identity_reference": True,
                "serialized": span.model_dump(mode="json"),
            }
        )
    except ValidationError as error:
        proof.append(
            {
                "kind": kind.value,
                "accepts_identity_reference": False,
                "errors": [e["msg"] for e in error.errors()],
            }
        )
summary = {
    "observations": len(observations),
    "names": len(name_summary),
    "known_English_mismatches": sum(r["known_English_mismatch"] for r in name_summary),
    "English_authority_permitted_target_names": sum(
        r["English_permitted"]["state"] == "TARGET" for r in name_summary
    ),
    "Greek_authority_permitted_target_names": sum(
        r["Greek_permitted"]["state"] == "TARGET" for r in name_summary
    ),
    "unmet_preservation_frames_whole_name_only": sum(
        r["preservation_obligation_unmet_by_whole_name_only"] for r in observations
    ),
    "unmet_preservation_names_whole_name_only": sorted(
        {r["name"] for r in observations if r["preservation_obligation_unmet_by_whole_name_only"]}
    ),
    "first_categories": dict(Counter(r["categories"][0] for r in observations)),
    "structural_controls": len(structural),
    "structural_target_set_matches": sum(r["target_set_matches_label"] for r in structural),
    "structural_first_categories": dict(Counter(r["primary_category"] for r in structural)),
    "decision": "B_ARCHITECTURE_EXTENSION_REQUIRED_NO_PRODUCTION_IMPLEMENTATION",
}
for name, value in [
    ("audit.json", observations),
    ("names.json", name_summary),
    ("structural_audit.json", structural),
    ("model_probe.json", proof),
    ("summary.json", summary),
]:
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
(OUT / "inputs.json").write_text(
    json.dumps(
        {
            "baseline": "d3fa60d",
            "ontology_version": resolver.ontology_version,
            "controls_sha256": hashlib.sha256(
                (PACKET / "structural_controls.json").read_bytes()
            ).hexdigest(),
        },
        indent=2,
    )
    + "\n"
)
print(json.dumps(summary, indent=2, ensure_ascii=False))
