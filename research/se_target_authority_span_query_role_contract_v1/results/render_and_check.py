"""Render and integrity-check diagnosis results without revising frozen labels."""

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path("/home/djmann/projects/bve-b8")
PACKET = ROOT / "research/se_target_authority_span_query_role_contract_v1"
OUT = Path("/tmp/span_role_results_v1")
audit = json.loads((OUT / "audit.json").read_text())
names = json.loads((OUT / "names.json").read_text())
controls = json.loads((OUT / "structural_audit.json").read_text())
manifest = json.loads((PACKET / "population_manifest.json").read_text())
assert len(audit) == 1344 and len(names) == 96 and len(controls) == 48
assert set(Counter(r["witness_id"] for r in audit).values()) == {14}
assert sum(r["known_English_mismatch"] for r in names) == 32
for path, digest in manifest["input_sha256"].items():
    assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
assert (
    hashlib.sha256((PACKET / "structural_controls.json").read_bytes()).hexdigest()
    == manifest["controls_sha256"]
)
for r in audit:
    span = r["expected_target_span"]
    assert r["query"][span["start"] : span["end"]] == span["text"]
    assert r["categories"] and set(r["categories"]) <= set("ABCDE")
    if r["authority_permitted_design_outcome"]["state"] == "TARGET":
        assert r["whole_name_authority"]["status"] == "RESOLVED"
        assert r["whole_name_authority"]["entity_id"] == r["biological_reference"]
    for s in r["current_selected_spans"]:
        s["original_surface"] = r["query"][s["start"] : s["end"]]

reviews = {
    "S002": {
        "categories": ["C"],
        "classification": "AUTHORITY_GAP",
        "note": "Frozen positive biological label is not attainable by span repair: exact PD-1 is AMBIGUOUS among PDCD1/RPL17/RPL17-C18ORF32. No authority disambiguation is authorized.",
    },
    "S041": {
        "categories": ["E"],
        "classification": "FROZEN_LABEL_ERROR",
        "note": "Frozen no-target label conflicts with adopted whole-token safety: ABP/ZF independently resolves to TRPV6 and is emitted as separator_whole_name. CREBZF is not emitted. Do not change the label or suppress the valid whole alias.",
    },
    "S042": {
        "categories": ["E"],
        "classification": "FROZEN_LABEL_ERROR",
        "note": "Frozen no-target label incorrectly equates ambiguity with an uncovered component. CD19 remains a target; CAR remains ambiguous and blocks compilation. This is adopted separator behavior, not an invented target.",
    },
}
for c in controls:
    expected_intervals = []
    for e in c["expected_target_spans"]:
        lo = c["query"].index(e["text"])
        expected_intervals.append((lo, lo + len(e["text"]), e["entity_id"]))
    for s in c["current_selected_spans"]:
        s["original_surface"] = c["query"][s["start"] : s["end"]]
        matching = [
            a for a in c["candidate_spans"] if a["start"] == s["start"] and a["end"] == s["end"]
        ]
        if not matching:
            c["candidate_spans"].append(
                {
                    "start": s["start"],
                    "end": s["end"],
                    "text": s["text"],
                    "role": "CURRENT_SELECTED_ONLY",
                    "authority": None,
                    "provenance": "current_selected_spans.explanation and target_reference; surface introduced by adopted affix/separator normalization",
                }
            )
    for s in c["candidate_spans"]:
        exact = any(s["start"] == a and s["end"] == b for a, b, _ in expected_intervals)
        nested = any(a <= s["start"] and s["end"] <= b for a, b, _ in expected_intervals)
        s["expected_query_role"] = (
            "TARGET"
            if exact
            else (
                "NAME_COMPONENT"
                if nested
                else "NON_TARGET_OR_UNLICENSED_" + c["role_category"].upper()
            )
        )
    c["review"] = reviews.get(
        c["id"],
        {
            "categories": [c["primary_category"]],
            "classification": "DIAGNOSTIC_OBSERVATION",
            "note": "Frozen expectations retained; identity-set agreement alone is not full parse or compiler acceptance.",
        },
    )
    if c["id"] in {"S025", "S026", "S027"}:
        c["review"]["secondary_authority_warning"] = (
            "BRAF lookup currently resolves to KIAA1549 through installed source merges; no BRAF identity repair or equivalence is inferred in this milestone."
        )

(OUT / "annotated_audit.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n")
(OUT / "reviewed_structural_audit.json").write_text(
    json.dumps(controls, indent=2, ensure_ascii=False) + "\n"
)
(OUT / "review_notes.json").write_text(json.dumps(reviews, indent=2) + "\n")


def table(path, header, rows):
    lines = [
        header,
        "",
        "| Name / query | Classification | Current | Authority-permitted / frozen expectation | Boundary or note |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| " + " | ".join(str(x).replace("|", "\\|").replace("\n", " ") for x in row) + " |"
        )
    (OUT / path).write_text("\n".join(lines) + "\n")


table(
    "name_audit.md",
    "# All 96 name pairs (bare frame summary; JSON carries all 1,344 observations)",
    [
        (
            r["original_name"],
            "/".join(r["English_categories"]) + "; Greek " + "/".join(r["Greek_categories"]),
            ", ".join(r["English_current"]) or "none",
            r["English_permitted"]["targets"] or "UNKNOWN",
            "Greek exact authority "
            + r["Greek_permitted"]["state"]
            + "; biological reference "
            + str(r["reference"]),
        )
        for r in names
    ],
)
table(
    "english_32.md",
    "# All 32 known English-name mismatches (all seven frames retained in audit.json)",
    [
        (
            r["original_name"],
            "A",
            r["English_current"],
            r["English_permitted"]["targets"],
            "Exact complete authority identity available; needs target-slot ownership before any component assertion.",
        )
        for r in names
        if r["known_English_mismatch"]
    ],
)
table(
    "structural_controls.md",
    "# All 48 frozen structural controls — disagreements retained, not relabeled",
    [
        (
            r["id"] + " " + r["query"],
            "/".join(r["review"]["categories"]),
            r["current_targets"],
            [s["entity_id"] for s in r["expected_target_spans"]],
            r["review"]["classification"] + ": " + r["review"]["note"],
        )
        for r in controls
    ],
)
checks = {
    "input_hashes_unchanged": True,
    "structural_labels_unchanged": True,
    "observations_accounted": len(audit),
    "each_name_has_14_observations": True,
    "exact_expected_span_offsets": True,
    "authority_projection_uses_exact_supported_whole_identity_only": True,
    "English_known_mismatches_accounted": 32,
    "structural_controls_accounted": 48,
    "frozen_label_errors_retained": ["S041", "S042"],
    "authority_gap_retained": ["S002"],
    "full_contract_acceptance_demonstrated": False,
    "reason": "No autonomous grammatical role arbitrator implemented or validated; 21 existing correct-identity frames not preserved by whole-name-only rule; two frozen labels conflict with adopted separator semantics.",
    "architecture_stop": "B",
    "production_changes": False,
}
(OUT / "integrity_checks.json").write_text(json.dumps(checks, indent=2) + "\n")
print(json.dumps(checks, indent=2))
