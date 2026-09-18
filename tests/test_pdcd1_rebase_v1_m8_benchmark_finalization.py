"""Tests for the PDCD1 rebase v1 M8 benchmark finalization assembler/validator.

These tests exercise the pure validation logic (`validate`) and the
modality/intent join (`build_modality_intent_ledger`) against small
synthetic in-memory fixtures shaped like the frozen M1-M7 ledgers, so they
run without any network access or dependency on the real multi-hundred-KB
artifact payloads. They assert both the happy path (all invariants pass)
and that each hard invariant fails closed when violated.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "pdcd1_rebase_v1_m8_benchmark_finalization.py"
spec = importlib.util.spec_from_file_location("pdcd1_m8", MODULE_PATH)
m8 = importlib.util.module_from_spec(spec)
sys.modules["pdcd1_m8"] = m8
spec.loader.exec_module(m8)  # type: ignore[union-attr]


def _make_sources(
    *,
    n_candidates: int = 2,
    n_rows: int = 300,
    orphan_candidate: bool = False,
    orphan_chron_candidate: bool = False,
    orphan_chron_nct: bool = False,
    drop_conflicts: bool = False,
    drop_unresolved: bool = False,
    duplicate_row: bool = False,
):
    candidates = [
        {"candidate_id": f"cand_{i:03d}", "canonical_name": f"Drug {i}"} for i in range(n_candidates)
    ]

    row_outcome = []
    for i in range(n_rows):
        row_outcome.append(
            {
                "frozen_row_id": f"row_{i:03d}_NCT{i:08d}_0",
                "nct_id": f"NCT{i:08d}",
                "canonical_candidate_id": candidates[i % n_candidates]["candidate_id"],
                "outcome": "CANDIDATE_LINKED",
            }
        )
    if duplicate_row and row_outcome:
        row_outcome.append(dict(row_outcome[0]))

    row_candidate_mapping = [
        {
            "frozen_row_id": r["frozen_row_id"],
            "canonical_candidate_id": r["canonical_candidate_id"],
            "binding_path": [
                {
                    "canonical_candidate_id": r["canonical_candidate_id"],
                    "m4_subject_id": f"subj_{r['frozen_row_id']}",
                }
            ],
        }
        for r in row_outcome
    ]

    combination_component = []

    unresolved_row = [] if drop_unresolved else [{"frozen_row_id": row_outcome[0]["frozen_row_id"], "outcome": "CONFLICTING_MULTI_PRODUCT", "reason": "test"}]

    m5_conflicts = [] if drop_conflicts else [{"conflict_id": "c1", "resolution": "test"}]

    m4_assertions = [
        {
            "subject_id": f"subj_{r['frozen_row_id']}",
            "assertion_type": "MODALITY_EXPLICIT",
        }
        for r in row_outcome[:1]
    ]

    chron_candidate_id = candidates[0]["candidate_id"]
    if orphan_chron_candidate:
        chron_candidate_id = "cand_does_not_exist"
    chron_nct_id = row_outcome[0]["nct_id"]
    if orphan_chron_nct:
        chron_nct_id = "NCT_does_not_exist"

    chronology_final = [
        {"candidate_id": chron_candidate_id, "nct_id": chron_nct_id, "canonical_name": "Drug 0"}
    ]

    if orphan_candidate:
        row_candidate_mapping[0]["canonical_candidate_id"] = "cand_orphan"

    return {
        "m5_dir": None,
        "m6_dir": None,
        "m7_dir": None,
        "canonical_candidates": candidates,
        "alias_ledger": [],
        "rejected_alias_ledger": [],
        "m5_conflicts": m5_conflicts,
        "row_outcome": row_outcome,
        "row_candidate_mapping": row_candidate_mapping,
        "combination_component": combination_component,
        "unresolved_row": unresolved_row,
        "m4_assertions": m4_assertions,
        "chronology_final": chronology_final,
        "chronology_validation_summary": {},
    }


def test_happy_path_all_invariants_pass():
    sources = _make_sources(n_candidates=224)
    # m5 canonical count check is hardcoded to 224 in validate(); use exactly 224
    vr = m8.validate(sources)
    failed = {f.check: f.detail for f in vr.failures}
    assert vr.ok, failed
    assert vr.metrics["row_outcome_row_count"] == 300
    assert vr.metrics["row_outcome_unique_row_count"] == 300


def test_wrong_row_count_fails_closed():
    sources = _make_sources(n_candidates=224, n_rows=299)
    vr = m8.validate(sources)
    assert not vr.ok
    assert any(f.check == "exactly_300_rows_accounted_once" for f in vr.failures)


def test_duplicate_row_fails_closed():
    sources = _make_sources(n_candidates=224, n_rows=299, duplicate_row=True)
    vr = m8.validate(sources)
    assert not vr.ok
    checks = {f.check for f in vr.failures}
    assert "exactly_300_rows_accounted_once" in checks


def test_orphan_candidate_id_fails_closed():
    sources = _make_sources(n_candidates=224, orphan_candidate=True)
    vr = m8.validate(sources)
    assert not vr.ok
    assert any(f.check == "all_referenced_candidate_ids_exist_in_m5" for f in vr.failures)


def test_orphan_chronology_candidate_fails_closed():
    sources = _make_sources(n_candidates=224, orphan_chron_candidate=True)
    vr = m8.validate(sources)
    assert not vr.ok
    assert any(f.check == "chronology_candidate_ids_all_in_m6v2" for f in vr.failures)


def test_orphan_chronology_nct_fails_closed():
    sources = _make_sources(n_candidates=224, orphan_chron_nct=True)
    vr = m8.validate(sources)
    assert not vr.ok
    assert any(f.check == "chronology_nct_ids_all_in_m6v2" for f in vr.failures)


def test_missing_m5_conflicts_fails_closed():
    sources = _make_sources(n_candidates=224, drop_conflicts=True)
    vr = m8.validate(sources)
    assert not vr.ok
    assert any(f.check == "m5_unresolved_conflicts_present_and_nonzero" for f in vr.failures)


def test_missing_m6_unresolved_fails_closed():
    sources = _make_sources(n_candidates=224, drop_unresolved=True)
    vr = m8.validate(sources)
    assert not vr.ok
    assert any(f.check == "m6_unresolved_rows_present_and_nonzero" for f in vr.failures)


def test_modality_intent_ledger_mechanical_join():
    sources = _make_sources(n_candidates=224)
    ledger = m8.build_modality_intent_ledger(sources)
    assert len(ledger) == 1
    assert ledger[0]["candidate_id"] == sources["row_outcome"][0]["canonical_candidate_id"]
    assert ledger[0]["modality_assertion_types"] == ["MODALITY_EXPLICIT"]
