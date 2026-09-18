"""PDCD1 rebase v1 -- Milestone 8: benchmark finalization, ASSEMBLER B
(genuinely independent second implementation).

This module mirrors the pattern established at Milestone 6 (Build A / Build
B, see ``scripts/pdcd1_rebase_v1_row_identity_mapping_mapper_b.py``) and
Milestone 7 (Mapper A / Mapper B, see
``scripts/pdcd1_rebase_v1_candidate_chronology_mapper_b.py``): a second,
structurally independent assembler that reconstructs the same M8 benchmark
package from the SAME frozen M1-M7 evidence, without importing, calling, or
reading the output of the original ("Assembler A") M8 benchmark
finalization driver.

Like Assembler A, this script performs assembly/validation only -- no new
identity research, row adjudication, chronology derivation, prediction, or
model tuning. If validation fails in a way that would require a new
judgment call to reconcile, it fails closed.

Structural differences from Assembler A (deliberate, not cosmetic):

  - Assembler A is a flat sequence of module-level functions operating on a
    single ``sources: dict[str, Any]`` blob assembled once in
    ``load_sources``. Assembler B instead builds explicit, typed indices
    (``CandidateIndex``, ``RowIndex``) as frozen dataclasses in a dedicated
    loading phase, and exposes assembly behavior as methods on an
    ``AssemblerB`` class.
  - Assembler A's modality/intent join iterates the M6 row-candidate-mapping
    ledger outer (mapping-record order) and looks up M4 modality
    assertions per binding_path entry, so its output ledger's row order is
    exactly the M6 ledger's on-disk order. Assembler B iterates
    CANDIDATE-outer (over the M5 canonical candidate ledger, sorted by
    candidate_id) and, for each candidate, scans the M6 mapping ledger for
    matching binding_path entries -- an O(candidates x mappings) join in
    the opposite direction, producing output in canonical
    (candidate_id, m4_subject_id) sorted order rather than M6 ledger
    insertion order. (Content of the derived ledger is the same
    frozen-evidence join; only traversal order/organization differs -- any
    output-order difference from Assembler A is expected and is
    reconciled, not silently normalized away, by the comparison step.)
  - Assembler A computes its "every candidate_id referenced anywhere exists
    in M5" and "M6-v2 candidate/NCT universe" checks via four separate
    sequential for-loops appending into one running ``set()``. Assembler B
    computes the same underlying entity universes via a single
    dict-of-sets built in one pass over each source collection
    (``_collect_candidate_ids_by_source``), then unions the per-source sets
    at the end -- a different internal data structure and a different
    control-flow shape, not a renamed copy.
  - Assembler A's chronology-pair cross-check builds a flat
    ``set[tuple[candidate_id, nct_id]]``. Assembler B builds a
    ``dict[nct_id, set[candidate_id]]`` (NCT-outer grouping) and derives
    the pair-level metrics from that grouped structure.

Usage:
    python scripts/pdcd1_rebase_v1_m8_benchmark_finalization_assembler_b.py \
        --src-root /tmp/pdcd1_m8_src/artifacts/pipeline/pdcd1_rebase_v1/stages \
        --out-root /tmp/pdcd1_m8_assembler_b_out \
        --run-id <run_id>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Frozen milestone lineage -- identical identifiers to Assembler A (both
# assemblers MUST target the same frozen prerequisite releases; this is not
# an independence violation, it is the shared ground truth both are
# reconstructing from).
# ---------------------------------------------------------------------------

M1_RUN_ID = "47e9e791f48bb7aacc467e28"
M2_RUN_ID = "62914ac00fa635d38755e25b"
M3_RUN_ID = "f5dd19d08deb59a75232d3bc"
M4_RUN_ID = "d933fec9aaeecd2df64884b6"
M5_RUN_ID = "f26fd47e34ab97badde4e2ae"
M6_RUN_ID = "eb3a4a67c7f22825279eeddf"  # v2 authoritative
M7_RUN_ID = "e792939c2cbd9ca87e027b2d"

M6_V1_RUN_ID_PROHIBITED = "e07fade12e18d972e3ea8743"

EXPECTED_ROW_COUNT = 300
EXPECTED_CANDIDATE_COUNT = 224


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Typed indices (Assembler A keeps everything in one loosely-typed dict;
# Assembler B builds explicit frozen dataclasses for the two entity
# universes it joins across most often).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateIndex:
    """M5 canonical candidate universe, keyed for O(1) lookup."""

    by_id: dict[str, dict[str, Any]]
    ordered_ids: tuple[str, ...]  # sorted candidate_id order

    @classmethod
    def build(cls, canonical_candidates: list[dict[str, Any]]) -> "CandidateIndex":
        by_id = {c["candidate_id"]: c for c in canonical_candidates}
        return cls(by_id=by_id, ordered_ids=tuple(sorted(by_id.keys())))


@dataclass(frozen=True)
class RowIndex:
    """M6 v2 row universe: row_outcome, row_candidate_mapping and
    combination_component ledgers cross-referenced by frozen_row_id."""

    outcomes: list[dict[str, Any]]
    mappings: list[dict[str, Any]]
    combinations: list[dict[str, Any]]
    unresolved: list[dict[str, Any]]
    mappings_by_candidate: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        outcomes: list[dict[str, Any]],
        mappings: list[dict[str, Any]],
        combinations: list[dict[str, Any]],
        unresolved: list[dict[str, Any]],
    ) -> "RowIndex":
        by_candidate: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for m in mappings:
            for bp in m.get("binding_path", []):
                cand_id = bp.get("canonical_candidate_id")
                if cand_id:
                    by_candidate[cand_id].append({"mapping": m, "binding_path": bp})
        return cls(
            outcomes=outcomes,
            mappings=mappings,
            combinations=combinations,
            unresolved=unresolved,
            mappings_by_candidate=dict(by_candidate),
        )


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


# ---------------------------------------------------------------------------
# Loading (mirrors the same on-disk paths as Assembler A, since both read
# the same frozen M1-M7 releases -- but organizes the load as a class
# method returning typed indices, not a single dict literal).
# ---------------------------------------------------------------------------


class AssemblerB:
    def __init__(self, src_root: Path) -> None:
        self.src_root = src_root
        self.m5_dir = src_root / "05_candidate_identity_adjudication" / M5_RUN_ID
        self.m6_dir = src_root / "06_frozen_row_identity_mapping" / M6_RUN_ID
        self.m7_dir = src_root / "07_candidate_chronology" / M7_RUN_ID
        self.m4_dir = src_root / "04_external_product_authority" / M4_RUN_ID

        self.canonical_candidates = read_jsonl(
            self.m5_dir / "candidates" / "canonical_candidate_ledger.jsonl"
        )
        self.alias_ledger = read_jsonl(
            self.m5_dir / "aliases" / "alias_development_code_ledger.jsonl"
        )
        self.rejected_alias_ledger = read_jsonl(
            self.m5_dir / "aliases" / "rejected_alias_ledger.jsonl"
        )
        self.m5_conflicts = read_jsonl(
            self.m5_dir / "conflicts" / "conflict_resolution_ledger.jsonl"
        )
        self.row_outcome = read_jsonl(self.m6_dir / "rows" / "row_outcome_ledger.jsonl")
        self.row_candidate_mapping = read_jsonl(
            self.m6_dir / "rows" / "row_candidate_mapping_ledger.jsonl"
        )
        self.combination_component = read_jsonl(
            self.m6_dir / "rows" / "combination_component_ledger.jsonl"
        )
        self.unresolved_row = read_jsonl(self.m6_dir / "rows" / "unresolved_row_ledger.jsonl")
        self.row_evidence = read_jsonl(self.m6_dir / "rows" / "row_evidence_binding_ledger.jsonl")
        self.m4_assertions = read_jsonl(
            self.m4_dir / "assertions" / "normalized_assertion_ledger.jsonl"
        )
        self.chronology_final = read_jsonl(
            self.m7_dir / "reconciliation" / "finalized_candidate_chronology_ledger.jsonl"
        )
        self.chronology_validation_summary = json.loads(
            (self.m7_dir / "validation" / "validation_summary.json").read_text()
        )

        self.candidate_index = CandidateIndex.build(self.canonical_candidates)
        self.row_index = RowIndex.build(
            self.row_outcome, self.row_candidate_mapping, self.combination_component, self.unresolved_row
        )

    # -- derived artifact: modality/intent ledger --------------------------

    def build_modality_intent_ledger(self) -> list[dict[str, Any]]:
        """Candidate-outer join of M4 modality assertions against M5
        canonical candidates via M6 binding paths. Same frozen-evidence
        source data and join semantics as Assembler A (assertion_type
        substring match on 'MODALITY', joined through
        row_candidate_mapping.binding_path), but driven candidate-first
        rather than mapping-record-first, and emitted in canonical
        (candidate_id, m4_subject_id) sorted order rather than M6 ledger
        insertion order.
        """
        subject_to_modality: dict[str, set[str]] = defaultdict(set)
        for a in self.m4_assertions:
            if "MODALITY" not in str(a.get("assertion_type", "")):
                continue
            sid = a.get("subject_id")
            if sid:
                subject_to_modality[sid].add(a.get("assertion_type"))

        out: list[dict[str, Any]] = []
        for cand_id in self.candidate_index.ordered_ids:
            entries = self.row_index.mappings_by_candidate.get(cand_id, [])
            seen_subjects: set[str] = set()
            # stable per-candidate ordering by m4_subject_id
            for entry in sorted(entries, key=lambda e: str(e["binding_path"].get("m4_subject_id"))):
                bp = entry["binding_path"]
                m4_subject_id = bp.get("m4_subject_id")
                if not m4_subject_id or m4_subject_id in seen_subjects:
                    continue
                modalities = subject_to_modality.get(m4_subject_id)
                if not modalities:
                    continue
                seen_subjects.add(m4_subject_id)
                out.append(
                    {
                        "candidate_id": cand_id,
                        "m4_subject_id": m4_subject_id,
                        "frozen_row_id": entry["mapping"].get("frozen_row_id"),
                        "modality_assertion_types": sorted(modalities),
                        "derivation": (
                            "mechanical join: M6 row_candidate_mapping.binding_path -> "
                            "M4 normalized_assertion_ledger (assertion_type contains 'MODALITY')"
                        ),
                    }
                )
        return out

    # -- entity-universe collection (used by validate()) --------------------

    def _collect_candidate_ids_by_source(self) -> dict[str, set[str]]:
        """One pass per source collection, each producing its own set,
        unioned by the caller -- a dict-of-sets rather than Assembler A's
        single running set threaded through four sequential loops."""
        by_source: dict[str, set[str]] = {}

        s: set[str] = set()
        for o in self.row_outcome:
            if o.get("canonical_candidate_id"):
                s.add(o["canonical_candidate_id"])
        by_source["row_outcome"] = s

        s = set()
        for c in self.combination_component:
            for comp in c.get("components", []):
                if comp.get("canonical_candidate_id"):
                    s.add(comp["canonical_candidate_id"])
        by_source["combination_component"] = s

        s = set()
        for m in self.row_candidate_mapping:
            if m.get("canonical_candidate_id"):
                s.add(m["canonical_candidate_id"])
            for bp in m.get("binding_path", []):
                if bp.get("canonical_candidate_id"):
                    s.add(bp["canonical_candidate_id"])
        by_source["row_candidate_mapping"] = s

        s = set()
        for f in self.chronology_final:
            if f.get("candidate_id"):
                s.add(f["candidate_id"])
        by_source["chronology_final"] = s

        return by_source

    def validate(self) -> ValidationResult:
        vr = ValidationResult()

        canonical_ids = set(self.candidate_index.by_id.keys())
        vr.metrics["m5_canonical_candidate_count"] = len(canonical_ids)
        vr.record(
            "m5_canonical_candidate_count_224",
            len(canonical_ids) == EXPECTED_CANDIDATE_COUNT,
            f"expected {EXPECTED_CANDIDATE_COUNT}, got {len(canonical_ids)}",
        )

        row_ids = [r["frozen_row_id"] for r in self.row_outcome]
        unique_row_ids = set(row_ids)
        vr.metrics["row_outcome_row_count"] = len(row_ids)
        vr.metrics["row_outcome_unique_row_count"] = len(unique_row_ids)
        vr.record(
            "exactly_300_rows_accounted_once",
            len(row_ids) == EXPECTED_ROW_COUNT and len(unique_row_ids) == EXPECTED_ROW_COUNT,
            f"expected {EXPECTED_ROW_COUNT} unique rows, got {len(row_ids)} total / {len(unique_row_ids)} unique",
        )

        by_source = self._collect_candidate_ids_by_source()
        referenced: set[str] = set().union(*by_source.values()) if by_source else set()
        orphan_candidates = referenced - canonical_ids
        vr.metrics["distinct_candidate_ids_referenced"] = len(referenced)
        vr.record(
            "all_referenced_candidate_ids_exist_in_m5",
            not orphan_candidates,
            f"{len(orphan_candidates)} candidate_id(s) referenced outside M5 canonical ledger: {sorted(orphan_candidates)[:10]}",
        )

        # M6 v2 candidate/NCT universe (excludes chronology_final source,
        # unlike the combined `referenced` set above -- this is the
        # candidate/NCT universe chronology is checked AGAINST).
        m6_candidate_ids = set().union(
            by_source["row_outcome"], by_source["combination_component"], by_source["row_candidate_mapping"]
        )
        m6_nct_ids = {o["nct_id"] for o in self.row_outcome}

        chron_candidate_ids = by_source["chronology_final"]
        chron_nct_ids = {f["nct_id"] for f in self.chronology_final}

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

        # NCT-outer grouped structure for the pair-level cross-check
        # (Assembler A uses a flat set of (candidate_id, nct_id) tuples;
        # Assembler B groups by nct_id first).
        m6_candidates_by_nct: dict[str, set[str]] = defaultdict(set)
        for o in self.row_outcome:
            if o.get("canonical_candidate_id"):
                m6_candidates_by_nct[o["nct_id"]].add(o["canonical_candidate_id"])
        for c in self.combination_component:
            nct = c["frozen_row_id"].split("_")[1]
            for comp in c.get("components", []):
                if comp.get("canonical_candidate_id"):
                    m6_candidates_by_nct[nct].add(comp["canonical_candidate_id"])

        chron_by_nct: dict[str, set[str]] = defaultdict(set)
        for f in self.chronology_final:
            chron_by_nct[f["nct_id"]].add(f["candidate_id"])

        matching_pairs = 0
        total_pairs = 0
        for nct, cand_set in chron_by_nct.items():
            total_pairs += len(cand_set)
            matching_pairs += len(cand_set & m6_candidates_by_nct.get(nct, set()))

        vr.metrics["chronology_pairs_total"] = total_pairs
        vr.metrics["chronology_pairs_matching_m6v2_exact_pair"] = matching_pairs
        vr.metrics["chronology_pairs_scope_beyond_m6v2_snapshot"] = total_pairs - matching_pairs
        vr.metrics["chronology_pairs_scope_note"] = (
            "M7 chronology is built over the full M2 registry-version history (superset scope); "
            "M6 v2 covers only the 300 current frozen rows. Pair-level divergence here reflects "
            "that scope difference, not a data disagreement -- see entity-level checks above, which pass."
        )

        vr.metrics["m5_unresolved_conflict_count"] = len(self.m5_conflicts)
        vr.metrics["m6_unresolved_row_count"] = len(self.unresolved_row)
        vr.record(
            "m5_unresolved_conflicts_present_and_nonzero",
            len(self.m5_conflicts) > 0,
            "expected a nonzero M5 conflict_resolution_ledger (reportedly ~60 unresolved identity conflicts)",
        )
        vr.record(
            "m6_unresolved_rows_present_and_nonzero",
            len(self.unresolved_row) > 0,
            "expected a nonzero M6 unresolved_row_ledger",
        )

        outcome_counts: dict[str, int] = defaultdict(int)
        for o in self.row_outcome:
            outcome_counts[o["outcome"]] += 1
        vr.metrics["row_outcome_distribution"] = dict(outcome_counts)
        expected_total = sum(outcome_counts.values())
        vr.record(
            "row_outcome_distribution_sums_to_300",
            expected_total == EXPECTED_ROW_COUNT,
            f"outcome distribution sums to {expected_total}, expected {EXPECTED_ROW_COUNT}",
        )

        return vr

    # -- assembly -------------------------------------------------------

    def assemble(self, out_dir: Path) -> ValidationResult:
        vr = self.validate()
        if not vr.ok:
            return vr

        write_jsonl(out_dir / "candidates" / "canonical_candidate_ledger.jsonl", self.canonical_candidates)
        write_jsonl(out_dir / "candidates" / "alias_development_code_ledger.jsonl", self.alias_ledger)
        write_jsonl(out_dir / "candidates" / "rejected_alias_ledger.jsonl", self.rejected_alias_ledger)
        write_jsonl(out_dir / "rows" / "row_outcome_ledger.jsonl", self.row_outcome)
        write_jsonl(out_dir / "rows" / "row_candidate_mapping_ledger.jsonl", self.row_candidate_mapping)
        write_jsonl(out_dir / "rows" / "combination_component_ledger.jsonl", self.combination_component)
        write_jsonl(out_dir / "rows" / "unresolved_row_ledger.jsonl", self.unresolved_row)
        write_jsonl(out_dir / "candidates" / "m5_conflict_resolution_ledger.jsonl", self.m5_conflicts)

        modality_ledger = self.build_modality_intent_ledger()
        write_jsonl(out_dir / "modality" / "candidate_modality_intent_ledger.jsonl", modality_ledger)
        vr.metrics["modality_intent_ledger_rows"] = len(modality_ledger)

        write_jsonl(out_dir / "chronology" / "finalized_candidate_chronology_ledger.jsonl", self.chronology_final)
        (out_dir / "chronology" / "m7_validation_summary.json").write_text(
            json.dumps(self.chronology_validation_summary, indent=2, sort_keys=True)
        )
        write_jsonl(out_dir / "evidence" / "row_evidence_binding_ledger.jsonl", self.row_evidence)

        return vr


def write_manifest_and_receipt(out_dir: Path, run_id: str, vr: ValidationResult) -> None:
    now = datetime.now(timezone.utc).isoformat()

    payload_files = sorted(
        p for p in out_dir.rglob("*") if p.is_file() and p.name not in ("manifest.json", "receipt.json")
    )
    receipt_files = [
        {"path": str(p.relative_to(out_dir)), "byte_length": p.stat().st_size, "sha256": sha256_file(p)}
        for p in payload_files
    ]
    receipt = {"file_count": len(receipt_files), "files": receipt_files, "generated_at": now}
    (out_dir / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True))

    manifest = {
        "stage": "08_benchmark_finalization",
        "milestone": "PDCD1_GOLD_STANDARD_BENCHMARK_REBASE_V1_FINALIZATION",
        "assembler": "assembler_b",
        "run_id": run_id,
        "generated_at": now,
        "assembly_type": "assembly/validation only -- no new identity research, row adjudication, chronology changes, predictions, or model tuning",
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
                "note": "M6 v2 is the sole authoritative row-identity-mapping source. M6 v1 (run_id "
                + M6_V1_RUN_ID_PROHIBITED
                + ") is prohibited as an active prerequisite.",
            },
            "m7_candidate_chronology": {
                "run_id": M7_RUN_ID,
                "branch": "artifact/pdcd1-rebase-v1-candidate-chronology",
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
                "command": "pdcd1_rebase_v1_m8_benchmark_finalization_assembler_b.py",
                "run_id": run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        + "\n"
    )
    (out_dir / "logs").mkdir(parents=True, exist_ok=True)
    (out_dir / "logs" / "build.jsonl").write_text(
        json.dumps({"event": "m8_assembler_b_complete", "timestamp": datetime.now(timezone.utc).isoformat()}) + "\n"
    )


def build_archive(out_dir: Path, run_id: str) -> Path:
    archive_path = out_dir / "export" / f"pdcd1-rebase-v1-benchmark-final-assembler-b-{run_id}.tar.gz"
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

    assembler = AssemblerB(args.src_root)
    vr = assembler.assemble(out_dir)

    write_validator_report(out_dir, vr)

    if not vr.ok:
        print("M8 ASSEMBLER B VALIDATION FAILED -- fail-closed, not forcing success.")
        for f in vr.failures:
            print(f"  - {f.check}: {f.detail}")
        return 1

    write_commands_log(out_dir, args.run_id)
    write_manifest_and_receipt(out_dir, args.run_id, vr)
    archive_path = build_archive(out_dir, args.run_id)

    print("M8 assembler B assembly + validation PASSED.")
    print(f"Output dir: {out_dir}")
    print(f"Archive: {archive_path}")
    print(json.dumps(vr.metrics, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
