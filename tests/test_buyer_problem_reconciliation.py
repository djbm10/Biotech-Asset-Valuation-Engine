"""Tests for problem-in vs universe-out reconciliation (spec Part 2.3)."""

from __future__ import annotations

from bve.analysis.buyer_problem_reconciliation import (
    ReconciliationLabel,
    reconcile_buyer_problem,
)
from bve.intelligence.science_thesis import (
    BuyerProblemShortlist,
    EvidenceGrade,
    ShortlistEntry,
)


def _shortlist() -> BuyerProblemShortlist:
    return BuyerProblemShortlist(
        buyer_problem_id="vertex-sickle-cell",
        ranked=[
            ShortlistEntry(
                asset_id="agreed-asset",
                bd_actionability=0.72,
                evidence_grade=EvidenceGrade.DILIGENCE_CONFIRMED,
            ),
            ShortlistEntry(
                asset_id="problem-only-asset",
                bd_actionability=0.55,
                evidence_grade=EvidenceGrade.SCREENING_PUBLIC,
            ),
        ],
        excluded=["gate-failed-asset"],
    )


def test_four_labels_are_assigned_correctly() -> None:
    scan_hits = {
        "agreed-asset": 0.80,  # strong scan + on shortlist -> agreed
        "problem-only-asset": 0.20,  # weak scan, on shortlist -> problem_only
        "gate-failed-asset": 0.90,  # strong scan, failed gates -> scan_only
        "random-asset": 0.10,  # weak scan, not on shortlist -> neither
    }

    report = reconcile_buyer_problem(_shortlist(), scan_hits, scan_threshold=0.5)
    labels = {a.asset_id: a.label for a in report.assets}

    assert labels["agreed-asset"] == ReconciliationLabel.AGREED
    assert labels["problem-only-asset"] == ReconciliationLabel.PROBLEM_ONLY
    assert labels["gate-failed-asset"] == ReconciliationLabel.SCAN_ONLY
    assert labels["random-asset"] == ReconciliationLabel.NEITHER


def test_scan_only_flags_gate_failure_for_feedback_loop() -> None:
    scan_hits = {"gate-failed-asset": 0.95}
    report = reconcile_buyer_problem(_shortlist(), scan_hits, scan_threshold=0.5)

    scan_only = report.scan_only
    assert [a.asset_id for a in scan_only] == ["gate-failed-asset"]
    assert scan_only[0].failed_buyer_gates is True
    assert scan_only[0].in_shortlist is False
    assert scan_only[0].scan_score == 0.95


def test_report_carries_rank_and_actionability_for_shortlisted_assets() -> None:
    report = reconcile_buyer_problem(_shortlist(), {}, scan_threshold=0.5)
    by_id = {a.asset_id: a for a in report.assets}

    assert by_id["agreed-asset"].shortlist_rank == 1
    assert by_id["agreed-asset"].bd_actionability == 0.72
    assert by_id["problem-only-asset"].shortlist_rank == 2
    # With no scan hits, every shortlisted asset is problem_only.
    assert by_id["agreed-asset"].label == ReconciliationLabel.PROBLEM_ONLY


def test_threshold_controls_strong_scan_membership() -> None:
    scan_hits = {"agreed-asset": 0.55}

    lenient = reconcile_buyer_problem(_shortlist(), scan_hits, scan_threshold=0.5)
    strict = reconcile_buyer_problem(_shortlist(), scan_hits, scan_threshold=0.6)

    lenient_label = {a.asset_id: a.label for a in lenient.assets}["agreed-asset"]
    strict_label = {a.asset_id: a.label for a in strict.assets}["agreed-asset"]

    assert lenient_label == ReconciliationLabel.AGREED
    assert strict_label == ReconciliationLabel.PROBLEM_ONLY
