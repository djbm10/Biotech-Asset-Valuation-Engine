"""Tests for the Chris-aligned BD actionability structure (spec Part 1).

Covers the Stage-2 re-weighting (human-POC + clinical-meaningfulness split),
the Stage-3 screening-grade cap, and the Stage-4 BuyerProblemShortlist output.
"""

from __future__ import annotations

from bve.intelligence.science_thesis import (
    SCREENING_PUBLIC_ACTIONABILITY_CAP,
    BDActionabilityResult,
    BDRoute,
    EvidenceGrade,
    build_buyer_problem_shortlist,
    compute_bd_actionability,
)


def _strong_eligible(**overrides: object) -> BDActionabilityResult:
    kwargs: dict[str, object] = dict(
        passed_hard_gates=True,
        buyer_problem_fit=0.95,
        human_poc_strength=0.90,
        clinical_meaningfulness=0.90,
        evidence_quality=0.90,
        modality_capability_fit=0.90,
        buyer_owner_advantage=0.90,
        deal_feasibility=0.90,
    )
    kwargs.update(overrides)
    return compute_bd_actionability(**kwargs)  # type: ignore[arg-type]


def test_screening_public_caps_actionability_and_flags_pre_diligence() -> None:
    result = _strong_eligible(evidence_grade=EvidenceGrade.SCREENING_PUBLIC)

    assert result.bd_actionability <= SCREENING_PUBLIC_ACTIONABILITY_CAP
    assert result.pre_diligence is True
    assert "capped_screening_public_pre_diligence" in result.warnings


def test_diligence_confirmed_is_not_capped_or_flagged() -> None:
    result = _strong_eligible(evidence_grade=EvidenceGrade.DILIGENCE_CONFIRMED)

    assert result.bd_actionability > SCREENING_PUBLIC_ACTIONABILITY_CAP
    assert result.pre_diligence is False
    assert "capped_screening_public_pre_diligence" not in result.warnings


def test_human_poc_and_clinical_are_separate_terms() -> None:
    # Strong human POC but weak clinical meaningfulness must score below the
    # case where both are strong: clinical effect size is its own 0.15 term.
    weak_clinical = compute_bd_actionability(
        passed_hard_gates=True,
        buyer_problem_fit=0.60,
        human_poc_strength=0.90,
        clinical_meaningfulness=0.10,
        evidence_grade=EvidenceGrade.DILIGENCE_CONFIRMED,
    )
    strong_clinical = compute_bd_actionability(
        passed_hard_gates=True,
        buyer_problem_fit=0.60,
        human_poc_strength=0.90,
        clinical_meaningfulness=0.90,
        evidence_grade=EvidenceGrade.DILIGENCE_CONFIRMED,
    )

    assert strong_clinical.bd_actionability > weak_clinical.bd_actionability
    assert weak_clinical.human_poc_strength == 0.90
    assert weak_clinical.clinical_meaningfulness == 0.10


def test_evidence_quality_term_is_capped() -> None:
    # evidence_quality above the term cap cannot keep inflating the score.
    capped = compute_bd_actionability(
        passed_hard_gates=True,
        buyer_problem_fit=0.50,
        human_poc_strength=0.50,
        clinical_meaningfulness=0.50,
        evidence_quality=0.75,
        evidence_grade=EvidenceGrade.DILIGENCE_CONFIRMED,
    )
    over = compute_bd_actionability(
        passed_hard_gates=True,
        buyer_problem_fit=0.50,
        human_poc_strength=0.50,
        clinical_meaningfulness=0.50,
        evidence_quality=1.00,
        evidence_grade=EvidenceGrade.DILIGENCE_CONFIRMED,
    )

    assert over.bd_actionability == capped.bd_actionability


def test_failed_gate_result_has_no_score_but_carries_grade() -> None:
    result = compute_bd_actionability(
        passed_hard_gates=False,
        failed_gates=["ta_outside_buyer_strategy"],
        evidence_grade=EvidenceGrade.SCREENING_PUBLIC,
    )

    assert result.bd_actionability == 0.0
    assert result.recommended_bd_route == BDRoute.AVOID
    assert result.evidence_grade == EvidenceGrade.SCREENING_PUBLIC
    assert result.pre_diligence is True


def test_shortlist_ranks_eligible_and_excludes_gate_failures() -> None:
    high = _strong_eligible(evidence_grade=EvidenceGrade.DILIGENCE_CONFIRMED)
    low = compute_bd_actionability(
        passed_hard_gates=True,
        buyer_problem_fit=0.30,
        human_poc_strength=0.30,
        clinical_meaningfulness=0.30,
        evidence_grade=EvidenceGrade.DILIGENCE_CONFIRMED,
    )
    blocked = compute_bd_actionability(
        passed_hard_gates=False,
        failed_gates=["does_not_solve_buyer_problem"],
    )

    shortlist = build_buyer_problem_shortlist(
        "vertex-sickle-cell",
        [
            ("asset-low", "Low Co", low),
            ("asset-high", "High Co", high),
            ("asset-blocked", "Blocked Co", blocked),
        ],
    )

    assert shortlist.buyer_problem_id == "vertex-sickle-cell"
    assert [entry.asset_id for entry in shortlist.ranked] == ["asset-high", "asset-low"]
    assert [entry.asset_id for entry in shortlist.excluded] == ["asset-blocked"]
    # Idea 14: the excluded asset carries the exact gate token it tripped.
    assert shortlist.excluded[0].failed_gates == ["does_not_solve_buyer_problem"]
    assert shortlist.excluded[0].asset_name == "Blocked Co"
    assert shortlist.ranked[0].bd_actionability >= shortlist.ranked[1].bd_actionability


def test_shortlist_respects_limit() -> None:
    results = [
        (
            f"asset-{i}",
            f"Co {i}",
            compute_bd_actionability(
                passed_hard_gates=True,
                buyer_problem_fit=0.1 * i,
                human_poc_strength=0.1 * i,
                clinical_meaningfulness=0.1 * i,
                evidence_grade=EvidenceGrade.DILIGENCE_CONFIRMED,
            ),
        )
        for i in range(1, 6)
    ]

    shortlist = build_buyer_problem_shortlist("bp", results, limit=2)

    assert len(shortlist.ranked) == 2
    assert shortlist.ranked[0].asset_id == "asset-5"
    assert shortlist.ranked[1].asset_id == "asset-4"
