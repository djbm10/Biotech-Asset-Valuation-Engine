"""Post-score reporting only; does not modify certificates or acceptance rules."""

import gzip
import hashlib
import json
import shutil
from collections import defaultdict
from pathlib import Path

out = Path("/tmp/certificate_v2_results")
out.mkdir(exist_ok=False)
for p in Path("/tmp/certificate_v2_seed0").iterdir():
    shutil.copy2(p, out / p.name)
for source, target in [
    ("/tmp/certificate_v2_validation.json", "validation.json"),
    ("/tmp/role_baseline_check.json", "baseline_check.json"),
    ("/tmp/certificate_v2_tests.log", "focused_tests.log"),
    ("/tmp/certificate_v2_red.log", "red_first.log"),
    ("/tmp/certificate_v2_ruff.log", "ruff.log"),
]:
    shutil.copy2(source, out / target)
cs = json.loads(gzip.open(out / "certificates.json.gz").read())
registry = json.loads(gzip.open(out / "evidence_registry.json.gz").read())
groups = defaultdict(list)
for c in cs:
    if c["scope"] == "RESOLVER_GROUP":
        groups[c["canonical_id"]].append(
            {
                "component_ids": c["component_ids"],
                "certificate_id": c["certificate_id"],
                "sidecar_origins": len(c["source_assertion_ids"]),
            }
        )
collisions = json.loads(gzip.open(out / "collisions.json.gz").read())
origins = registry["sidecar_origins"]
normalization_distinct = {
    k: v
    for k, v in collisions["normalized_key_origins"].items()
    if len({origins[a]["raw_component"] for a in v}) > 1
}
collision_audit = {
    "component_certificate_collisions": {k: v for k, v in groups.items() if len(v) > 1},
    "recoverable_origin_collision_families": len(collisions["canonical_id_components"]),
    "multiple_origin_keys": len(collisions["normalized_key_origins"]),
    "distinct_raw_text_normalization_collision_keys": len(normalization_distinct),
    "explanation": "Component certificates preserve both SNORA62 and CDC42BPA families. Recoverable sidecar origins cover one collision family; the historical ChEMBL-only CDC42BPA origin is not fabricated. New independent ChEMBL fields remain separately referenced.",
}
(out / "collision_scope_audit.json").write_text(
    json.dumps(collision_audit, sort_keys=True, indent=2) + "\n"
)
statuses = [
    "CERTIFIED_SINGLE_ENTITY",
    "CERTIFIED_MULTI_ENTITY",
    "CERTIFIED_RELATIONAL_ENTITY",
    "CONFLICT",
    "AMBIGUOUS",
    "UNRESOLVED",
]
summary = json.load(open(out / "summary.json"))
adoption = {
    "milestone": "TARGET_COMPONENT_IDENTITY_CERTIFICATE v2",
    "decision": "ADOPT",
    "preregistration": "a9bf585",
    "implementation": "b17f9da",
    "criteria": {f"C{i}": "PASS" for i in range(1, 13)},
    "blocked_86": {s: summary["blocked_86"].get(s, 0) for s in statuses},
    "all_certificates": {s: summary["statuses"].get(s, 0) for s in statuses},
    "focused_and_compatibility_tests": 15,
    "ruff": "PASS",
    "parser_decisions_unchanged": 6199,
    "production_changes": False,
    "full_tests_se": "NOT_RUN: C12 conditional on production changes; none",
    "canonical_collision_families": 2,
    "source_provenance_fields": 11806,
    "sidecar_origins": 3534,
    "source_records": 495,
    "follow_up": "STOP recovery of these 86 cases: evidence-blocked. No new authority or weakened certification. Reassess H19 non-asset/PEPTIDE qualification diagnosis independently; no behavior change authorized by this result.",
}
(out / "adoption.json").write_text(json.dumps(adoption, sort_keys=True, indent=2) + "\n")
lines = [
    "# Frozen certificate table",
    "",
    "| Case | Scope | Proposed identity | Status | Rule |",
    "|---|---|---|---|---|",
]
for c in cs:
    lines.append(
        "| "
        + " | ".join(c[k] for k in ["case_id", "scope", "canonical_id", "status", "rule"])
        + " |"
    )
(out / "certificate_table.md").write_text("\n".join(lines) + "\n")
hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir())}
(out / "result_hashes.json").write_text(json.dumps(hashes, sort_keys=True, indent=2) + "\n")
print(json.dumps(collision_audit, sort_keys=True)[:1000])
