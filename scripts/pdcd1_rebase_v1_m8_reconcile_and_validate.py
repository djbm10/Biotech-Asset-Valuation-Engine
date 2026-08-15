"""PDCD1 rebase v1 -- Milestone 8: reconcile Assembler A / Assembler B outputs
into a single merged package, and run the final cross-cutting invariant
validator against it.

This script does NOT perform any new identity research, row adjudication,
chronology derivation, prediction, or model tuning. It:

  1. Copies Assembler A's output verbatim as the reconciled baseline (per
     `docs/pdcd1_rebase_v1/M8_ASSEMBLER_A_VS_B_COMPARISON.md`, 11/12
     artifacts are byte-identical between the two assemblers, and the one
     differing artifact -- `candidate_modality_intent_ledger.jsonl` --
     contains the same 214 records under both assemblers, differing only in
     row order, which carries no semantic meaning for this derived join
     table).
  2. Runs the four required cross-cutting invariants against the reconciled
     package and writes a validator report.

Usage:
    python scripts/pdcd1_rebase_v1_m8_reconcile_and_validate.py \
        --assembler-a-out /tmp/pdcd1_m8_assembler_a_out/<run_id> \
        --assembler-b-out /tmp/pdcd1_m8_assembler_b_out/<run_id> \
        --out-dir /tmp/pdcd1_m8_reconciled_out/<run_id>
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

EXPECTED_ROW_COUNT = 300


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def reconcile(assembler_a_out: Path, assembler_b_out: Path, out_dir: Path) -> dict[str, Any]:
    """Copy Assembler A's ledgers/manifest as the reconciled baseline, then
    cross-check every artifact against Assembler B's, recording agreement
    at the record-set level (order-independent) for artifacts documented as
    order-sensitive-only differences."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    artifacts = [
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
        "evidence/row_evidence_binding_ledger.jsonl",
    ]

    reconciliation_report: dict[str, Any] = {"artifacts": {}}

    for rel_path in artifacts:
        a_path = assembler_a_out / rel_path
        b_path = assembler_b_out / rel_path
        a_text = a_path.read_text()
        b_text = b_path.read_text()

        byte_identical = a_text == b_text
        a_rows = read_jsonl(a_path)
        b_rows = read_jsonl(b_path)
        a_sorted = sorted(json.dumps(r, sort_keys=True) for r in a_rows)
        b_sorted = sorted(json.dumps(r, sort_keys=True) for r in b_rows)
        content_identical = a_sorted == b_sorted

        reconciliation_report["artifacts"][rel_path] = {
            "byte_identical": byte_identical,
            "content_identical_order_independent": content_identical,
            "a_record_count": len(a_rows),
            "b_record_count": len(b_rows),
        }

        if not content_identical:
            raise RuntimeError(
                f"UNRECONCILED DIFFERENCE at {rel_path}: Assembler A and Assembler B "
                "disagree on record content (not just order). This requires a new "
                "judgment call that cannot be resolved from frozen evidence alone -- "
                "stopping, not fabricating a pass."
            )

        # Reconciled baseline = Assembler A's file (per comparison doc).
        dest = out_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(a_text)

    # Non-ledger passthrough files (JSON, not JSONL) -- compared as parsed
    # JSON (order-independent for dict keys is inherent to JSON semantics).
    json_artifacts = ["chronology/m7_validation_summary.json"]
    for rel_path in json_artifacts:
        a_path = assembler_a_out / rel_path
        b_path = assembler_b_out / rel_path
        a_obj = json.loads(a_path.read_text())
        b_obj = json.loads(b_path.read_text())
        identical = a_obj == b_obj
        reconciliation_report["artifacts"][rel_path] = {
            "byte_identical": a_path.read_text() == b_path.read_text(),
            "content_identical_order_independent": identical,
        }
        if not identical:
            raise RuntimeError(f"UNRECONCILED DIFFERENCE at {rel_path}")
        dest = out_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(a_path.read_text())

    (out_dir / "RECONCILIATION_REPORT.json").write_text(
        json.dumps(reconciliation_report, indent=2, sort_keys=True)
    )
    return reconciliation_report


def validate_invariants(out_dir: Path) -> dict[str, Any]:
    """The four required cross-cutting invariants, run against the
    reconciled merged package."""
    row_outcome = read_jsonl(out_dir / "rows" / "row_outcome_ledger.jsonl")
    row_candidate_mapping = read_jsonl(out_dir / "rows" / "row_candidate_mapping_ledger.jsonl")
    combination_component = read_jsonl(out_dir / "rows" / "combination_component_ledger.jsonl")
    unresolved_row = read_jsonl(out_dir / "rows" / "unresolved_row_ledger.jsonl")
    canonical_candidates = read_jsonl(out_dir / "candidates" / "canonical_candidate_ledger.jsonl")
    m5_conflicts = read_jsonl(out_dir / "candidates" / "m5_conflict_resolution_ledger.jsonl")
    chronology_final = read_jsonl(out_dir / "chronology" / "finalized_candidate_chronology_ledger.jsonl")

    results: dict[str, Any] = {"checks": {}, "failures": []}

    def record(name: str, ok: bool, detail: str = "") -> None:
        results["checks"][name] = {"ok": ok, "detail": detail}
        if not ok:
            results["failures"].append({"check": name, "detail": detail})

    # Invariant 1: exactly 300/300 rows accounted for once.
    row_ids = [r["frozen_row_id"] for r in row_outcome]
    record(
        "invariant_1_exactly_300_rows_accounted_once",
        len(row_ids) == EXPECTED_ROW_COUNT and len(set(row_ids)) == EXPECTED_ROW_COUNT,
        f"{len(row_ids)} total / {len(set(row_ids))} unique (expected {EXPECTED_ROW_COUNT}/{EXPECTED_ROW_COUNT})",
    )

    # Invariant 2: all candidate-linked IDs resolve to M5.
    canonical_ids = {c["candidate_id"] for c in canonical_candidates}
    referenced: set[str] = set()
    for o in row_outcome:
        if o.get("canonical_candidate_id"):
            referenced.add(o["canonical_candidate_id"])
    for m in row_candidate_mapping:
        if m.get("canonical_candidate_id"):
            referenced.add(m["canonical_candidate_id"])
        for bp in m.get("binding_path", []):
            if bp.get("canonical_candidate_id"):
                referenced.add(bp["canonical_candidate_id"])
    for c in combination_component:
        for comp in c.get("components", []):
            if comp.get("canonical_candidate_id"):
                referenced.add(comp["canonical_candidate_id"])
    orphans = referenced - canonical_ids
    record(
        "invariant_2_all_candidate_linked_ids_resolve_to_m5",
        not orphans,
        f"{len(orphans)} candidate_id(s) not present in M5 canonical ledger: {sorted(orphans)[:10]}",
    )
    results["metrics_candidate_ids_referenced"] = len(referenced)

    # Invariant 3: all M7 chronology records bind to valid M6-v2 candidate/NCT mappings.
    m6_candidate_ids: set[str] = set()
    for o in row_outcome:
        if o.get("canonical_candidate_id"):
            m6_candidate_ids.add(o["canonical_candidate_id"])
    for c in combination_component:
        for comp in c.get("components", []):
            if comp.get("canonical_candidate_id"):
                m6_candidate_ids.add(comp["canonical_candidate_id"])
    for m in row_candidate_mapping:
        if m.get("canonical_candidate_id"):
            m6_candidate_ids.add(m["canonical_candidate_id"])
        for bp in m.get("binding_path", []):
            if bp.get("canonical_candidate_id"):
                m6_candidate_ids.add(bp["canonical_candidate_id"])
    m6_nct_ids = {o["nct_id"] for o in row_outcome}

    chron_candidate_ids = {f["candidate_id"] for f in chronology_final}
    chron_nct_ids = {f["nct_id"] for f in chronology_final}
    orphan_chron_candidates = chron_candidate_ids - m6_candidate_ids
    orphan_chron_ncts = chron_nct_ids - m6_nct_ids
    record(
        "invariant_3a_chronology_candidate_ids_bind_to_m6v2",
        not orphan_chron_candidates,
        f"{len(orphan_chron_candidates)} orphan chronology candidate_id(s): {sorted(orphan_chron_candidates)[:10]}",
    )
    record(
        "invariant_3b_chronology_nct_ids_bind_to_m6v2",
        not orphan_chron_ncts,
        f"{len(orphan_chron_ncts)} orphan chronology nct_id(s): {sorted(orphan_chron_ncts)[:10]}",
    )

    # Invariant 4: unresolved M5/M6 cases remain visible (not dropped).
    record(
        "invariant_4a_m5_unresolved_conflicts_visible",
        len(m5_conflicts) > 0,
        f"m5_conflict_resolution_ledger has {len(m5_conflicts)} records",
    )
    record(
        "invariant_4b_m6_unresolved_rows_visible",
        len(unresolved_row) > 0,
        f"unresolved_row_ledger has {len(unresolved_row)} records",
    )
    results["ok"] = not results["failures"]
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--assembler-a-out", required=True, type=Path)
    ap.add_argument("--assembler-b-out", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    args = ap.parse_args()

    print("Reconciling Assembler A / Assembler B outputs...")
    reconciliation_report = reconcile(args.assembler_a_out, args.assembler_b_out, args.out_dir)
    print(json.dumps(reconciliation_report, indent=2, sort_keys=True))

    print("\nRunning final invariant validator against reconciled package...")
    validation_report = validate_invariants(args.out_dir)
    (args.out_dir / "FINAL_INVARIANT_VALIDATION.json").write_text(
        json.dumps(validation_report, indent=2, sort_keys=True)
    )
    print(json.dumps(validation_report, indent=2, sort_keys=True))

    if not validation_report["ok"]:
        print("\nINVARIANT VALIDATION FAILED -- fail-closed.")
        return 1

    print("\nAll invariants PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
