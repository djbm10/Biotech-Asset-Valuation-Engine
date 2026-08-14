"""Validation tests for the PDCD1 rebase v1 Milestone 7 candidate chronology
output: the finalized, reconciled ledger under
``artifacts/pipeline/pdcd1_rebase_v1/stages/07_candidate_chronology/``.

These tests check output invariants (counts, guardrails), not re-derive the
chronology from frozen M2/M5/M6-v2 evidence -- that derivation happens once
against the large (GitHub-Release-hosted) M2 registry-history corpus and is
not re-run in CI. See
``tests/test_pdcd1_rebase_v1_candidate_chronology_mapper_independence.py``
for the static independence guard on the two mapper scripts themselves.
"""
from __future__ import annotations

import json
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STAGE_DIR = REPO_ROOT / "artifacts/pipeline/pdcd1_rebase_v1/stages/07_candidate_chronology"


def _latest_run_dir() -> pathlib.Path | None:
    if not STAGE_DIR.exists():
        return None
    candidates = [p for p in STAGE_DIR.iterdir() if p.is_dir()]
    if not candidates:
        return None
    # Single run expected at this milestone; if multiple, prefer the one
    # with a manifest.json (finalized run).
    finalized = [p for p in candidates if (p / "manifest.json").exists()]
    return finalized[0] if finalized else candidates[0]


RUN_DIR = _latest_run_dir()

pytestmark = pytest.mark.skipif(
    RUN_DIR is None,
    reason="No M7 candidate-chronology artifact run present in this checkout.",
)


def _load_jsonl(path: pathlib.Path) -> list[dict]:
    rows = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _finalized_rows() -> list[dict]:
    return _load_jsonl(RUN_DIR / "reconciliation" / "finalized_candidate_chronology_ledger.jsonl")


def _manifest() -> dict:
    return json.loads((RUN_DIR / "manifest.json").read_text())


def test_manifest_declares_finalized_milestone_7() -> None:
    manifest = _manifest()
    assert manifest["milestone"] == "PDCD1_BENCHMARK_REBASE_V1_MILESTONE_7_CANDIDATE_CHRONOLOGY"
    assert manifest["stage_status"] == "FINALIZED"
    assert manifest["candidate_chronology_created"] is True
    assert manifest["mapper_independence_verified"] is True


def test_required_artifacts_present() -> None:
    for rel in [
        "build_a/build_a_candidate_chronology_ledger.jsonl",
        "build_b/build_b_candidate_chronology_ledger.jsonl",
        "reconciliation/reconciliation_ledger.jsonl",
        "reconciliation/finalized_candidate_chronology_ledger.jsonl",
        "reconciliation/reconciliation_summary.json",
        "validation/validation_summary.json",
        "manifest.json",
        "receipt.json",
        "commands.jsonl",
        "logs/build.jsonl",
    ]:
        assert (RUN_DIR / rel).exists(), f"missing artifact: {rel}"


def test_finalized_ledger_covers_every_m6v2_candidate_pair() -> None:
    build_a = _load_jsonl(RUN_DIR / "build_a" / "build_a_candidate_chronology_ledger.jsonl")
    build_b = _load_jsonl(RUN_DIR / "build_b" / "build_b_candidate_chronology_ledger.jsonl")
    finalized = _finalized_rows()

    keys_a = {(r["candidate_id"], r["nct_id"]) for r in build_a}
    keys_b = {(r["candidate_id"], r["nct_id"]) for r in build_b}
    keys_final = {(r["candidate_id"], r["nct_id"]) for r in finalized}

    assert keys_a == keys_b, "Build A and Build B must cover the identical candidate/NCT pair set"
    assert keys_final == keys_a, "Finalized ledger must cover exactly the pairs both builds produced"
    assert len(finalized) == len(keys_final), "No duplicate candidate/NCT pairs in the finalized ledger"


def test_no_inherited_start_date_for_later_added_candidates() -> None:
    """Guardrail: a candidate marked LATER_ADDED (later_added_product_status
    True) must not carry the same registered start date as a candidate that
    was present in the trial's original (version-0) registration, for the
    same nct_id -- that would indicate the later-added candidate silently
    inherited the trial's original start date rather than a candidate-
    specific one."""
    rows = _finalized_rows()
    by_nct: dict[str, list[dict]] = {}
    for r in rows:
        by_nct.setdefault(r["nct_id"], []).append(r)

    for nct_id, nct_rows in by_nct.items():
        original_starts = {
            r["candidate_specific_registered_start"]
            for r in nct_rows
            if r.get("present_in_original_version") is True
            and r.get("candidate_specific_registered_start") is not None
        }
        for r in nct_rows:
            if r.get("later_added_product_status") is True and r.get("candidate_specific_registered_start") is not None:
                assert r["candidate_specific_registered_start"] not in original_starts, (
                    f"Later-added candidate {r['candidate_id']} on {nct_id} appears to have "
                    "inherited an original-version registered start date"
                )


def test_unknown_stays_unknown_not_silently_populated() -> None:
    """Every row where the intervention field was never located must leave
    all intervention-dependent chronology fields UNKNOWN/None, never a
    guessed value."""
    rows = _finalized_rows()
    for r in rows:
        if r["first_candidate_bearing_intervention_appearance"] == "UNKNOWN":
            assert r["candidate_specific_registered_start"] is None
            assert r["start_date_type"] == "UNKNOWN"
            assert r["present_in_original_version"] == "UNKNOWN"
            assert r["later_added_product_status"] == "UNKNOWN"
            assert r["first_known_phase"] == "UNKNOWN"


def test_approval_date_never_fabricated() -> None:
    """M4 at this milestone carries no approval-date assertions; approval_date
    must be None for every row (never inferred/invented)."""
    rows = _finalized_rows()
    for r in rows:
        assert r["approval_date"] is None


def test_date_precision_never_upgraded() -> None:
    """A month-precision date string (e.g. '2020-03') must never appear as a
    day-precision date; this test checks the finalized ledger's registered
    start dates are unmodified strings (length 7 == YYYY-MM, length 10 ==
    YYYY-MM-DD, never anything else synthesized)."""
    rows = _finalized_rows()
    for r in rows:
        val = r["candidate_specific_registered_start"]
        if val is not None:
            assert len(val) in (7, 10), f"Unexpected date precision/format: {val!r}"


def test_build_a_vs_build_b_high_agreement_rate() -> None:
    summary = json.loads((RUN_DIR / "reconciliation" / "reconciliation_summary.json").read_text())
    total = summary["common_pairs"]
    disagreements = summary["rows_with_at_least_one_field_disagreement"]
    assert total > 0
    agreement_rate = (total - disagreements) / total
    assert agreement_rate >= 0.95, (
        f"Build A/Build B agreement rate {agreement_rate:.3f} is below the "
        "expected genuine-cross-check threshold"
    )


def test_every_disagreement_has_documented_rationale() -> None:
    recon = _load_jsonl(RUN_DIR / "reconciliation" / "reconciliation_ledger.jsonl")
    for row in recon:
        if row["has_disagreement"]:
            for field, entry in row["fields"].items():
                if not entry["agree"]:
                    assert entry.get("rationale"), (
                        f"Disagreement on {field} for {row['candidate_id']}/{row['nct_id']} "
                        "has no documented rationale"
                    )
                    assert "resolved_value" in entry
