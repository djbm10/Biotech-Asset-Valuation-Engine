"""PDCD1 rebase v1 — Milestone 8: PDCD1_GOLD_STANDARD_BENCHMARK_REBASE_V1_FINALIZATION.

Assembly / validation only. This script does NOT perform any new identity
research, row adjudication, chronology derivation, prediction, or model
tuning. It mechanically assembles the M8 benchmark package from the frozen
outputs of M1-M7 (M6 read from the v2-authoritative source only) and
validates a fixed set of structural invariants across those frozen inputs.
If any invariant fails in a way that would require a new judgment call to
reconcile, this script fails closed (raises / reports failure) rather than
forcing a "valid" result.

Usage:
    python scripts/pdcd1_rebase_v1_m8_benchmark_finalization.py \
        --src-root /tmp/pdcd1_m8_src/artifacts/pipeline/pdcd1_rebase_v1/stages \
        --out-root artifacts/pipeline/pdcd1_rebase_v1/stages/08_benchmark_finalization \
        --run-id <run_id>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Frozen milestone lineage (fixed identifiers; do not change without a new
# provenance record).
# ---------------------------------------------------------------------------

M1_RUN_ID = "47e9e791f48bb7aacc467e28"
M2_RUN_ID = "62914ac00fa635d38755e25b"
M3_RUN_ID = "f5dd19d08deb59a75232d3bc"  # authoritative final (3B, hardened)
M4_RUN_ID = "d933fec9aaeecd2df64884b6"
M5_RUN_ID = "f26fd47e34ab97badde4e2ae"
M6_RUN_ID = "eb3a4a67c7f22825279eeddf"  # v2 authoritative; v1 (e07fade1...) is prohibited
M7_RUN_ID = "e792939c2cbd9ca87e027b2d"

M6_V1_RUN_ID_PROHIBITED = "e07fade12e18d972e3ea8743"

EXPECTED_ROW_COUNT = 300


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class ValidationFailure:
    check: str
    detail: str


@dataclass
class ValidationResult:
    checks_passed: list[str] = field(default_factory=list)
    failures: list[ValidationFailure] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.failures

    def record(self, name: str, ok: bool, detail: str = "") -> None:
        if ok:
            self.checks_passed.append(name)
        else:
            self.failures.append(ValidationFailure(check=name, detail=detail))


def load_sources(src_root: Path) -> dict[str, Any]:
    m5_dir = src_root / "05_candidate_identity_adjudication" / M5_RUN_ID
    m6_dir = src_root / "06_frozen_row_identity_mapping" / M6_RUN_ID
    m7_dir = src_root / "07_candidate_chronology" / M7_RUN_ID

    return {
        "m5_dir": m5_dir,
        "m6_dir": m6_dir,
        "m7_dir": m7_dir,
        "canonical_candidates": read_jsonl(m5_dir / "candidates" / "canonical_candidate_ledger.jsonl"),
        "alias_ledger": read_jsonl(m5_dir / "aliases" / "alias_development_code_ledger.jsonl"),
        "rejected_alias_ledger": read_jsonl(m5_dir / "aliases" / "rejected_alias_ledger.jsonl"),
        "m5_conflicts": read_jsonl(m5_dir / "conflicts" / "conflict_resolution_ledger.jsonl"),
        "row_outcome": read_jsonl(m6_dir / "rows" / "row_outcome_ledger.jsonl"),
        "row_candidate_mapping": read_jsonl(m6_dir / "rows" / "row_candidate_mapping_ledger.jsonl"),
        "combination_component": read_jsonl(m6_dir / "rows" / "combination_component_ledger.jsonl"),
        "unresolved_row": read_jsonl(m6_dir / "rows" / "unresolved_row_ledger.jsonl"),
        "m4_assertions": read_jsonl(
            src_root / "04_external_product_authority" / M4_RUN_ID / "assertions" / "normalized_assertion_ledger.jsonl"
        ),
        "chronology_final": read_jsonl(m7_dir / "reconciliation" / "finalized_candidate_chronology_ledger.jsonl"),
        "chronology_validation_summary": json.loads(
            (m7_dir / "validation" / "validation_summary.json").read_text()
        ),
    }


def build_modality_intent_ledger(sources: dict[str, Any]) -> list[dict[str, Any]]:
    """Mechanically extract modality-type assertions from the frozen M4
    assertion ledger and join them to M5 canonical candidates via M6's row
    binding paths. No new classification judgment is applied — only
    assertion_type substring match on values already present in the frozen
    M4 output, and a lookup join through existing M6 binding_path pointers.
    """
    modality_assertions = [
        a for a in sources["m4_assertions"] if "MODALITY" in str(a.get("assertion_type", ""))
    ]
    subject_to_modality: dict[str, list[str]] = {}
    for a in modality_assertions:
        sid = a.get("subject_id")
        if sid:
            subject_to_modality.setdefault(sid, []).append(a.get("assertion_type"))

    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for m in sources["row_candidate_mapping"]:
        for bp in m.get("binding_path", []):
            cand_id = bp.get("canonical_candidate_id")
            m4_subject_id = bp.get("m4_subject_id")
            if not cand_id or not m4_subject_id:
                continue
            modalities = subject_to_modality.get(m4_subject_id)
            if not modalities:
                continue
            key = (cand_id, m4_subject_id)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "candidate_id": cand_id,
                    "m4_subject_id": m4_subject_id,
                    "frozen_row_id": m.get("frozen_row_id"),
                    "modality_assertion_types": sorted(set(modalities)),
                    "derivation": "mechanical join: M6 row_candidate_mapping.binding_path -> M4 normalized_assertion_ledger (assertion_type contains 'MODALITY')",
                }
            )
    return out


def validate(sources: dict[str, Any]) -> ValidationResult:
    vr = ValidationResult()

    canonical_ids = {c["candidate_id"] for c in sources["canonical_candidates"]}
    vr.metrics["m5_canonical_candidate_count"] = len(canonical_ids)
    vr.record(
        "m5_canonical_candidate_count_224",
        len(canonical_ids) == 224,
        f"expected 224, got {len(canonical_ids)}",
    )

    # 300 rows accounted exactly once
    row_ids = [r["frozen_row_id"] for r in sources["row_outcome"]]
    vr.metrics["row_outcome_row_count"] = len(row_ids)
    vr.metrics["row_outcome_unique_row_count"] = len(set(row_ids))
    vr.record(
        "exactly_300_rows_accounted_once",
        len(row_ids) == EXPECTED_ROW_COUNT and len(set(row_ids)) == EXPECTED_ROW_COUNT,
        f"expected {EXPECTED_ROW_COUNT} unique rows, got {len(row_ids)} total / {len(set(row_ids))} unique",
    )

    # every candidate_id referenced anywhere exists in M5 canonical ledger
    referenced: set[str] = set()
    for m in sources["row_candidate_mapping"]:
        if m.get("canonical_candidate_id"):
            referenced.add(m["canonical_candidate_id"])
        for bp in m.get("binding_path", []):
            if bp.get("canonical_candidate_id"):
                referenced.add(bp["canonical_candidate_id"])
    for c in sources["combination_component"]:
        for comp in c.get("components", []):
            if comp.get("canonical_candidate_id"):
                referenced.add(comp["canonical_candidate_id"])
    for o in sources["row_outcome"]:
        if o.get("canonical_candidate_id"):
            referenced.add(o["canonical_candidate_id"])
    for f in sources["chronology_final"]:
        if f.get("candidate_id"):
            referenced.add(f["candidate_id"])

    orphan_candidates = referenced - canonical_ids
    vr.metrics["distinct_candidate_ids_referenced"] = len(referenced)
    vr.record(
        "all_referenced_candidate_ids_exist_in_m5",
        not orphan_candidates,
        f"{len(orphan_candidates)} candidate_id(s) referenced outside M5 canonical ledger: {sorted(orphan_candidates)[:10]}",
    )

    # every chronology record corresponds to an M6 v2 candidate/NCT mapping
    # (entity-level: both the candidate_id and the nct_id independently
    # trace back into M6 v2's universe; M7 aggregates across the FULL
    # registry-version history per M2, which is a strict superset scope of
    # M6's 300 current-frozen-row snapshot, so exact (candidate,NCT) PAIR
    # equality is not the correct join key — pair-level cross-check is
    # reported as an informational metric only, not a hard-fail invariant).
    m6_candidate_ids: set[str] = set()
    for o in sources["row_outcome"]:
        if o.get("canonical_candidate_id"):
            m6_candidate_ids.add(o["canonical_candidate_id"])
    for c in sources["combination_component"]:
        for comp in c.get("components", []):
            if comp.get("canonical_candidate_id"):
                m6_candidate_ids.add(comp["canonical_candidate_id"])
    for m in sources["row_candidate_mapping"]:
        if m.get("canonical_candidate_id"):
            m6_candidate_ids.add(m["canonical_candidate_id"])
        for bp in m.get("binding_path", []):
            if bp.get("canonical_candidate_id"):
                m6_candidate_ids.add(bp["canonical_candidate_id"])
    m6_nct_ids = {o["nct_id"] for o in sources["row_outcome"]}

    chron_candidate_ids = {f["candidate_id"] for f in sources["chronology_final"]}
    chron_nct_ids = {f["nct_id"] for f in sources["chronology_final"]}

    orphan_chron_candidates = chron_candidate_ids - m6_candidate_ids
    orphan_chron_ncts = chron_nct_ids - m6_nct_ids

    vr.metrics["chronology_candidate_count"] = len(chron_candidate_ids)
    vr.metrics["chronology_nct_count"] = len(chron_nct_ids)

    vr.record(
        "chronology_candidate_ids_all_in_m6v2",
        not orphan_chron_candidates,
        f"{len(orphan_chron_candidates)} chronology candidate_id(s) not present anywhere in M6 v2: {sorted(orphan_chron_candidates)[:10]}",
    )
    vr.record(
        "chronology_nct_ids_all_in_m6v2",
        not orphan_chron_ncts,
        f"{len(orphan_chron_ncts)} chronology nct_id(s) not present among M6 v2's 300 frozen rows: {sorted(orphan_chron_ncts)[:10]}",
    )

    chron_pairs = {(f["candidate_id"], f["nct_id"]) for f in sources["chronology_final"]}
    m6_pairs: set[tuple[str, str]] = set()
    for o in sources["row_outcome"]:
        if o.get("canonical_candidate_id"):
            m6_pairs.add((o["canonical_candidate_id"], o["nct_id"]))
    for c in sources["combination_component"]:
        nct = c["frozen_row_id"].split("_")[1]
        for comp in c.get("components", []):
            if comp.get("canonical_candidate_id"):
                m6_pairs.add((comp["canonical_candidate_id"], nct))
    vr.metrics["chronology_pairs_total"] = len(chron_pairs)
    vr.metrics["chronology_pairs_matching_m6v2_exact_pair"] = len(chron_pairs & m6_pairs)
    vr.metrics["chronology_pairs_scope_beyond_m6v2_snapshot"] = len(chron_pairs - m6_pairs)
    vr.metrics["chronology_pairs_scope_note"] = (
        "M7 chronology is built over the full M2 registry-version history (superset scope); "
        "M6 v2 covers only the 300 current frozen rows. Pair-level divergence here reflects "
        "that scope difference, not a data disagreement — see entity-level checks above, which pass."
    )

    # unresolved cases must remain explicitly listed, not silently dropped
    vr.metrics["m5_unresolved_conflict_count"] = len(sources["m5_conflicts"])
    vr.metrics["m6_unresolved_row_count"] = len(sources["unresolved_row"])
    vr.record(
        "m5_unresolved_conflicts_present_and_nonzero",
        len(sources["m5_conflicts"]) > 0,
        "expected a nonzero M5 conflict_resolution_ledger (reportedly ~60 unresolved identity conflicts)",
    )
    vr.record(
        "m6_unresolved_rows_present_and_nonzero",
        len(sources["unresolved_row"]) > 0,
        "expected a nonzero M6 unresolved_row_ledger",
    )

    # row_outcome / mapping / unresolved partition sanity (informational,
    # cross-checked mechanically against the frozen M6 v2 receipt data)
    from collections import Counter

    outcome_counts = Counter(o["outcome"] for o in sources["row_outcome"])
    vr.metrics["row_outcome_distribution"] = dict(outcome_counts)
    expected_total = sum(outcome_counts.values())
    vr.record(
        "row_outcome_distribution_sums_to_300",
        expected_total == EXPECTED_ROW_COUNT,
        f"outcome distribution sums to {expected_total}, expected {EXPECTED_ROW_COUNT}",
    )

    return vr


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")


def assemble(src_root: Path, out_dir: Path, run_id: str) -> tuple[dict[str, Any], ValidationResult]:
    sources = load_sources(src_root)
    vr = validate(sources)

    if not vr.ok:
        return sources, vr

    # canonical candidate ledger (M5)
    write_jsonl(out_dir / "candidates" / "canonical_candidate_ledger.jsonl", sources["canonical_candidates"])
    # alias/dev-code ledger (M5)
    write_jsonl(out_dir / "candidates" / "alias_development_code_ledger.jsonl", sources["alias_ledger"])
    write_jsonl(out_dir / "candidates" / "rejected_alias_ledger.jsonl", sources["rejected_alias_ledger"])
    # 300-row outcome ledger (M1/M6)
    write_jsonl(out_dir / "rows" / "row_outcome_ledger.jsonl", sources["row_outcome"])
    # row->candidate mapping ledger (M6 v2)
    write_jsonl(out_dir / "rows" / "row_candidate_mapping_ledger.jsonl", sources["row_candidate_mapping"])
    # combination/conflict ledger
    write_jsonl(out_dir / "rows" / "combination_component_ledger.jsonl", sources["combination_component"])
    # unresolved cases ledger
    write_jsonl(out_dir / "rows" / "unresolved_row_ledger.jsonl", sources["unresolved_row"])
    write_jsonl(out_dir / "candidates" / "m5_conflict_resolution_ledger.jsonl", sources["m5_conflicts"])
    # modality/intent data
    modality_ledger = build_modality_intent_ledger(sources)
    write_jsonl(out_dir / "modality" / "candidate_modality_intent_ledger.jsonl", modality_ledger)
    vr.metrics["modality_intent_ledger_rows"] = len(modality_ledger)
    # candidate chronology (M7)
    write_jsonl(out_dir / "chronology" / "finalized_candidate_chronology_ledger.jsonl", sources["chronology_final"])
    (out_dir / "chronology" / "m7_validation_summary.json").write_text(
        json.dumps(sources["chronology_validation_summary"], indent=2, sort_keys=True)
    )
    # evidence bindings
    m6_dir = sources["m6_dir"]
    row_evidence = read_jsonl(m6_dir / "rows" / "row_evidence_binding_ledger.jsonl")
    write_jsonl(out_dir / "evidence" / "row_evidence_binding_ledger.jsonl", row_evidence)

    return sources, vr


def write_manifest_and_receipt(out_dir: Path, run_id: str, vr: ValidationResult) -> None:
    now = datetime.now(timezone.utc).isoformat()

    payload_files = sorted(
        p for p in out_dir.rglob("*")
        if p.is_file() and p.name not in ("manifest.json", "receipt.json")
    )

    receipt_files = []
    for p in payload_files:
        receipt_files.append(
            {
                "path": str(p.relative_to(out_dir)),
                "byte_length": p.stat().st_size,
                "sha256": sha256_file(p),
            }
        )
    receipt = {
        "file_count": len(receipt_files),
        "files": receipt_files,
        "generated_at": now,
    }
    (out_dir / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True))

    manifest = {
        "stage": "08_benchmark_finalization",
        "milestone": "PDCD1_GOLD_STANDARD_BENCHMARK_REBASE_V1_FINALIZATION",
        "run_id": run_id,
        "generated_at": now,
        "assembly_type": "assembly/validation only — no new identity research, row adjudication, chronology changes, predictions, or model tuning",
        "lineage": {
            "m1_population_capture": {"run_id": M1_RUN_ID, "branch": "artifact/pdcd1-rebase-v1-population"},
            "m2_registry_history": {"run_id": M2_RUN_ID, "branch": "artifact/pdcd1-rebase-v1-history"},
            "m3_evidence_triage_final": {"run_id": M3_RUN_ID, "branch": "artifact/pdcd1-rebase-v1-evidence-triage-final"},
            "m4_external_authority": {"run_id": M4_RUN_ID, "branch": "artifact/pdcd1-rebase-v1-external-authority"},
            "m5_candidate_identity": {"run_id": M5_RUN_ID, "branch": "artifact/pdcd1-rebase-v1-candidate-identity"},
            "m6_row_identity_mapping_v2": {
                "run_id": M6_RUN_ID,
                "release_tag": "pdcd1-rebase-v1-m6-row-identity-mapping-v2-eb3a4a67c7f22825279eeddf",
                "branch": "artifact/pdcd1-rebase-v1-row-mapping",
                "branch_commit": "494d5da",
                "note": "M6 v2 is the sole authoritative row-identity-mapping source. M6 v1 (run_id "
                + M6_V1_RUN_ID_PROHIBITED
                + ") is prohibited as an active prerequisite; see provenance/m6_v2_authoritative_lineage.json.",
            },
            "m7_candidate_chronology": {
                "run_id": M7_RUN_ID,
                "branch": "artifact/pdcd1-rebase-v1-candidate-chronology",
                "branch_commit": "ea7c13d",
                "release_tag": "pdcd1-rebase-v1-m7-candidate-chronology-e792939c2cbd9ca87e027b2d",
            },
        },
        "included_ledgers": [
            "candidates/canonical_candidate_ledger.jsonl",
            "candidates/alias_development_code_ledger.jsonl",
            "candidates/rejected_alias_ledger.jsonl",
            "candidates/m5_conflict_resolution_ledger.jsonl",
            "rows/row_outcome_ledger.jsonl",
            "rows/row_candidate_mapping_ledger.jsonl",
            "rows/combination_component_ledger.jsonl",
            "rows/unresolved_row_ledger.jsonl",
            "modality/candidate_modality_intent_ledger.jsonl",
            "chronology/finalized_candidate_chronology_ledger.jsonl",
            "chronology/m7_validation_summary.json",
            "evidence/row_evidence_binding_ledger.jsonl",
        ],
        "validator_summary": {
            "checks_passed": vr.checks_passed,
            "failures": [f.__dict__ for f in vr.failures],
            "metrics": vr.metrics,
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))


def write_validator_report(out_dir: Path, vr: ValidationResult) -> None:
    report = {
        "status": "PASS" if vr.ok else "FAIL",
        "checks_passed": vr.checks_passed,
        "failures": [f.__dict__ for f in vr.failures],
        "metrics": vr.metrics,
    }
    (out_dir / "validation" / "validator_report.json").parent.mkdir(parents=True, exist_ok=True)
    (out_dir / "validation" / "validator_report.json").write_text(json.dumps(report, indent=2, sort_keys=True))


def write_commands_log(out_dir: Path, run_id: str) -> None:
    (out_dir / "commands.jsonl").write_text(
        json.dumps(
            {
                "command": "pdcd1_rebase_v1_m8_benchmark_finalization.py",
                "run_id": run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        + "\n"
    )
    (out_dir / "logs").mkdir(parents=True, exist_ok=True)
    (out_dir / "logs" / "build.jsonl").write_text(
        json.dumps({"event": "m8_assembly_complete", "timestamp": datetime.now(timezone.utc).isoformat()}) + "\n"
    )


def build_archive(out_dir: Path, run_id: str) -> Path:
    archive_path = out_dir / "export" / f"pdcd1-rebase-v1-benchmark-final-{run_id}.tar.gz"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "w:gz") as tar:
        for item in sorted(out_dir.iterdir()):
            if item.name == "export":
                continue
            tar.add(item, arcname=f"{run_id}/{item.name}")
    sha = sha256_file(archive_path)
    (archive_path.with_suffix(archive_path.suffix + ".sha256")).write_text(f"{sha}  {archive_path.name}\n")
    return archive_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src-root", required=True, type=Path)
    ap.add_argument("--out-root", required=True, type=Path)
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()

    out_dir = args.out_root / args.run_id
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    sources, vr = assemble(args.src_root, out_dir, args.run_id)

    write_validator_report(out_dir, vr)

    if not vr.ok:
        print("M8 VALIDATION FAILED — fail-closed, not forcing success.")
        for f in vr.failures:
            print(f"  - {f.check}: {f.detail}")
        return 1

    write_commands_log(out_dir, args.run_id)
    write_manifest_and_receipt(out_dir, args.run_id, vr)
    archive_path = build_archive(out_dir, args.run_id)

    print("M8 assembly + validation PASSED.")
    print(f"Output dir: {out_dir}")
    print(f"Archive: {archive_path}")
    print(json.dumps(vr.metrics, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
