"""BD scorer boundary locks (Idea 15).

These pin the agreed value boundary so urgency/FOMO cannot leak back into
bd_actionability on a later refactor:

- time_sensitivity is routing-only and never changes the score.
- a gate-failed asset is never rescued by scarcity.
- scarcity has exactly one home (buyer_owner_advantage, via the matcher) — the
  scorer no longer carries a duplicate linear scarcity term.
- scarcity must be consistent with alternative_assets_available, else it is both
  flagged (scorer warning) and capped away (matcher owner-advantage).
- hard-gate questions (TA/target/modality) are settled at Stage 1, not re-scored.
"""
from __future__ import annotations

from bve.intelligence.layer15_buyer_match import (
    Layer15BuyerMatchInput,
    Layer15BuyerMatcher,
)
from bve.intelligence.science_thesis import (
    BuyerProblem,
    EvidenceGrade,
    ScienceThesis,
    compute_bd_actionability,
)
from bve.intelligence.science_thesis_builder import (
    ScienceThesisBuilder,
    ScienceThesisBuilderInput,
)


def _score(**overrides) -> float:
    kwargs = dict(
        passed_hard_gates=True,
        buyer_problem_fit=0.6,
        human_poc_strength=0.5,
        clinical_meaningfulness=0.5,
        evidence_grade=EvidenceGrade.DILIGENCE_CONFIRMED,
        buyer_owner_advantage=0.5,
    )
    kwargs.update(overrides)
    return compute_bd_actionability(**kwargs).bd_actionability


def test_time_sensitivity_never_changes_score() -> None:
    assert _score(time_sensitivity=0.0) == _score(time_sensitivity=1.0)


def test_scarcity_no_longer_enters_scorer_directly() -> None:
    """The duplicate linear scarcity term is gone — scorer score is scarcity-invariant."""
    assert _score(scarcity_value=0.0) == _score(scarcity_value=1.0)


def test_gate_failure_not_rescued_by_scarcity() -> None:
    low = compute_bd_actionability(
        passed_hard_gates=False,
        failed_gates=["does_not_solve_buyer_problem"],
        scarcity_value=0.0,
    )
    high = compute_bd_actionability(
        passed_hard_gates=False,
        failed_gates=["does_not_solve_buyer_problem"],
        scarcity_value=1.0,
    )
    assert low.bd_actionability == high.bd_actionability == 0.0
    assert low.recommended_bd_route == high.recommended_bd_route


def test_scarcity_inconsistent_with_alternatives_warns() -> None:
    result = compute_bd_actionability(
        passed_hard_gates=True,
        buyer_problem_fit=0.6,
        evidence_grade=EvidenceGrade.DILIGENCE_CONFIRMED,
        scarcity_value=0.85,
        alternative_assets_available=["competitor-asset"],
    )
    assert "scarcity_inconsistent_with_alternatives" in result.warnings


def test_scarcity_not_flagged_when_no_alternatives() -> None:
    result = compute_bd_actionability(
        passed_hard_gates=True,
        buyer_problem_fit=0.6,
        evidence_grade=EvidenceGrade.DILIGENCE_CONFIRMED,
        scarcity_value=0.85,
        alternative_assets_available=[],
    )
    assert "scarcity_inconsistent_with_alternatives" not in result.warnings


# --------------------------------------------------------------------------
# Matcher-level: scarcity supports owner advantage only when alternatives are empty
# --------------------------------------------------------------------------

def _thesis() -> ScienceThesis:
    return ScienceThesisBuilder().build(
        ScienceThesisBuilderInput(
            asset_id="a",
            modality="small molecule",
            target="HBF",
            has_target_rationale=True,
        )
    )


def _match(buyer_problem: BuyerProblem) -> float:
    result = Layer15BuyerMatcher().match(
        Layer15BuyerMatchInput(
            science_thesis=_thesis(),
            buyer_problem=buyer_problem,
            therapeutic_area="hematology",
            target="HBF",
            modality="small molecule",
            solves_buyer_problem=True,
            problem_solution_fit=0.6,
            evidence_grade=EvidenceGrade.DILIGENCE_CONFIRMED,
        )
    )
    return result.bd_actionability


def test_matcher_scarcity_capped_when_alternatives_exist() -> None:
    scarce_no_alts = BuyerProblem(buyer_id="b", scarcity_value=0.9, alternative_assets_available=[])
    scarce_with_alts = BuyerProblem(
        buyer_id="b", scarcity_value=0.9, alternative_assets_available=["x", "y"]
    )
    # With no alternatives, scarcity may lift owner advantage; with alternatives it cannot.
    assert _match(scarce_no_alts) >= _match(scarce_with_alts)
    assert _match(scarce_with_alts) == _match(
        BuyerProblem(buyer_id="b", scarcity_value=0.1, alternative_assets_available=["x"])
    )
